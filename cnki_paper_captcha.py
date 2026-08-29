"""
知网期刊爬虫 - 验证码自动解决版本（按期刊 / 按关键词检索 / 参考文献抓取）
基于 cnki_paper_threaded.py，集成 ddddocr 自动解决验证码
支持滑块验证码（期刊页面）和文字点选验证码（论文详情页面）

参考文献抓取（ReferenceCrawler）：进入论文详情页先点击「参考文献」页签
<li data-id="references" onclick="changeRefTypeTag(this)">，列表渲染后条目在
//ul[@class="ebBd"] 下（文本+链接），点击 <a class="next">下一页</a> 继续抓取，
「下一页」按钮消失（或置灰）即末页；仅抓列表条目，不递归参考文献详情页。
结果按 paper_url 覆盖式写入 paper_references 表（表由脚本自建，与 backend 模型解耦）。

防风控：详情页导航与翻页请求均计节奏 —— 篇间隔默认 6s（随机上浮至 ~1.8 倍，
--ref-interval 可调）、每次翻页前随机停 2~4.5s 并过全局导航闸；先滚动后点页签
模拟真人。易触发验证码时：调大 --ref-interval（如 12），或 --show-browser 人工配合。

合并抓取：--detail-refs 开启后，抓论文详情时在同一详情页顺带抓参考文献入库
（期刊/关键词检索模式均生效），省去二次导航，总体请求数更少、更不易触发风控；
参考文献失败只记日志，不影响已入库的论文详情。

依赖安装:
    pip install ddddocr Pillow
    # 验证码文字识别（可选；PaddleOCR 3.x 默认能力即含通用 OCR，无需单独装 paddlepaddle）:
    python -m pip install paddleocr
    # 需要文档解析、文档理解、文档翻译、关键信息抽取等全部可选能力时:
    # python -m pip install "paddleocr[all]"

使用方法:
    python cnki_paper_captcha.py --show-browser
    python cnki_paper_captcha.py --threads 3
    # 关键词检索
    python cnki_paper_captcha.py --search "新质生产力" --show-browser
    # 参考文献抓取
    python cnki_paper_captcha.py --ref-paper-url "https://kns.cnki.net/kcms2/article/abstract?..."
    python cnki_paper_captcha.py --ref-urls-file .cache/urls.txt --ref-max-items 200
    python cnki_paper_captcha.py --ref-title "论文标题"
"""

import json
import re
import sys
import time
import random
import asyncio
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page
import threading
from typing import Optional, List, Tuple
import io

# ddddocr 用于验证码识别
try:
    import ddddocr
    DDDDOCR_AVAILABLE = True
except ImportError:
    DDDDOCR_AVAILABLE = False
    print("警告: ddddocr 未安装，验证码自动解决功能不可用")
    print("请运行: pip install ddddocr Pillow")

# PaddleOCR 用于文字识别（比 ddddocr 更准确）
try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    PADDLEOCR_AVAILABLE = False
    print("提示: paddleocr 未安装，将使用 ddddocr 进行文字识别")
    print("建议运行: python -m pip install paddleocr")
    print('       （PaddleOCR 3.x 默认能力即含通用 OCR；需文档解析/理解/翻译/信息抽取等全部能力: python -m pip install "paddleocr[all]"）')

# OpenCV 用于图像预处理（提高识别准确率）
try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False
    print("提示: opencv-python 未安装，图像预处理功能不可用")
    print("建议运行: pip install opencv-python numpy")

# 常量
BASE_URL = 'https://navi.cnki.net'
VERIFY_URL_PREFIX = 'https://kns.cnki.net/verify/'
TARGET_YEARS = ['2025', '2026']
JOURNAL_CACHE_DAYS = 7
PAPER_CACHE_DAYS = 30

# —— 防检测 / 网络相关可调参数（集中在此，避免散落的魔数）——
# 详情页 goto 后的等待：事件驱动为主，以下仅作「确认内容已渲染」后的随机小延迟（防检测）
MIN_DETAIL_DELAY = 0.5
MAX_DETAIL_DELAY = 1.5
# 翻页 / 期次切换后等待目录容器出现的最长时长
PAGE_STABLE_TIMEOUT = 30
# 详情页抓取失败重试次数与退避间隔（秒）
DETAIL_MAX_RETRIES = 2
DETAIL_RETRY_BACKOFF = [3.0, 8.0]
# 首页检索触发后，若被风控以 403 拦截（页面落到 chrome-error），最多重试次数
SEARCH_MAX_RETRIES = 3
# 验证码自动解决最大尝试次数（点选验证码每次刷新都是一次风控交互，不宜过高）
CLICK_CAPTCHA_MAX_RETRIES = 10  # 测试期临时调高到 10，定位识别问题后应收敛
SLIDER_CAPTCHA_MAX_RETRIES = 3

# —— 全局请求节流 + 验证码熔断（跨浏览器 / 跨 tab 共享，进程内单例）——
# 核心思想：无论开多少个浏览器/tab，全局「导航」速率被令牌桶锁死，
# 避免聚合请求率过高触发知网风控；验证码连续出现时熔断翻倍并短暂停顿。
PACING_BASE_INTERVAL = 1.5       # 全局最小导航间隔（秒）
PACING_MAX_INTERVAL = 8.0        # 熔断后间隔上限
CIRCUIT_BREAKER_WINDOW = 60      # 熔断计数窗口（秒）
CIRCUIT_BREAKER_THRESHOLD = 2    # 窗口内出现几次验证码即熔断
CIRCUIT_BREAKER_COOLDOWN = 15    # 熔断时额外停顿（秒）
PACING_DECAY_FACTOR = 0.5        # 安静期后间隔衰减系数
PACING_DECAY_AFTER = 180         # 多久无验证码后开始衰减（秒）

_pacing = {
    'interval': PACING_BASE_INTERVAL,
    'next_token': 0.0,            # time.monotonic() 时间戳
    'cooldown_until': 0.0,
    'captcha_times': [],          # 窗口内验证码时间戳（time.monotonic()）
}


async def _pacing_wait():
    """全局导航闸：单事件循环内同步 check-and-set，保证全局导航间隔。"""
    loop = asyncio.get_event_loop()
    # 静默期衰减（间隔向基础值回落）
    if _pacing['captcha_times']:
        latest = max(_pacing['captcha_times'])
        if time.monotonic() - latest > PACING_DECAY_AFTER and _pacing['interval'] > PACING_BASE_INTERVAL:
            _pacing['interval'] = max(PACING_BASE_INTERVAL, _pacing['interval'] * PACING_DECAY_FACTOR)
    while True:
        now = time.monotonic()
        # 熔断冷却：额外停顿
        if now < _pacing['cooldown_until']:
            await asyncio.sleep(_pacing['cooldown_until'] - now)
            continue
        if now >= _pacing['next_token']:
            _pacing['next_token'] = now + _pacing['interval']
            return
        await asyncio.sleep(_pacing['next_token'] - now)


def _report_captcha(tag: str = ""):
    """记录一次验证码事件；窗口内达到阈值则熔断（间隔翻倍 + 冷却）。"""
    now = time.monotonic()
    _pacing['captcha_times'] = [t for t in _pacing['captcha_times'] if now - t < CIRCUIT_BREAKER_WINDOW]
    _pacing['captcha_times'].append(now)
    if len(_pacing['captcha_times']) >= CIRCUIT_BREAKER_THRESHOLD:
        new_int = min(_pacing['interval'] * 2, PACING_MAX_INTERVAL)
        if new_int != _pacing['interval']:
            print(f"  [熔断{tag}] {CIRCUIT_BREAKER_WINDOW}s 内 {len(_pacing['captcha_times'])} 次验证码，"
                  f"全局导航间隔 {_pacing['interval']}s -> {new_int}s")
            _pacing['interval'] = new_int
        _pacing['captcha_times'] = []
        _pacing['cooldown_until'] = now + CIRCUIT_BREAKER_COOLDOWN
        print(f"  [熔断{tag}] 全部爬取暂停 {CIRCUIT_BREAKER_COOLDOWN}s 冷却")

# —— 运行时缓存目录：会话态 / urls / 检索结果页 URL / 调试 HTML 统一落到脚本同级的 .cache/ 下 ——
CACHE_DIR = Path(__file__).resolve().parent / '.cache'
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# —— 关键词检索断点：停止/中断后可从上次进度续跑（collect=翻页收集中 / detail=详情入库中）——
# 注意：详情阶段本身逐篇入库即持久化，恢复时靠 URL 去重跳过已入库论文
SEARCH_CHECKPOINT_FILE = CACHE_DIR / 'search_checkpoint.json'


def _load_search_checkpoint():
    try:
        import json
        return json.loads(SEARCH_CHECKPOINT_FILE.read_text(encoding='utf-8'))
    except Exception:
        return None


def _save_search_checkpoint(data: dict):
    try:
        import json
        from datetime import datetime as _dt
        data = dict(data)
        data['saved_at'] = _dt.now().isoformat(timespec='seconds')
        SEARCH_CHECKPOINT_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    except Exception as e:
        print(f"  [checkpoint] 写入断点失败: {e}")


def _clear_search_checkpoint():
    try:
        SEARCH_CHECKPOINT_FILE.unlink(missing_ok=True)
    except Exception:
        pass


# CNKI 检索字段全集（取值即知网站点字段名，前端下拉与 --search-field 均基于此，见 demo.py）
CNKI_SEARCH_FIELDS = [
    "主题", "篇关摘", "关键词", "篇名", "全文", "作者", "第一作者", "通讯作者",
    "作者单位", "基金", "摘要", "小标题", "参考文献", "分类号", "文献来源", "DOI",
]

# 检索字段 → 侧边栏筛选分组(div#divGroup 中 dl@dt@groupitem) 的映射：
# 命中分组时，在该分组内按关键词匹配最恰当的一项并点选，进一步收窄结果。
# 无映射的字段（篇关摘/篇名/关键词/全文/摘要/小标题/参考文献/DOI）不做分组筛选。
# 注意：检索字段「文献来源」对应侧边栏分组「文献来源」(WXLY)，不是「期刊」(QK)。
SEARCH_FIELD_GROUP_MAP = {
    "主题": "主题",
    "作者": "作者",
    "第一作者": "作者",
    "通讯作者": "作者",
    "作者单位": "机构",
    "基金": "基金",
    "文献来源": "文献来源",
    "分类号": "学科",
}

# 会话态文件：期刊收集各浏览器独立一份，详情浏览器复用 cnki_state.json
CNKI_STATE_FILE = CACHE_DIR / 'cnki_state.json'


def _collect_state_file(index: int) -> Path:
    return CACHE_DIR / f'cnki_state_collect_{index}.json'



# 文件路径
BACKEND_DIR = Path(__file__).resolve().parent / 'backend'
DATA_DIR = BACKEND_DIR / 'data'
JOURNALS_HISTORY_FILE = DATA_DIR / 'journals_history.json'
PAPERS_HISTORY_FILE = DATA_DIR / 'papers_history.json'

# 脚本需要复用后端 app 包（PaperCRUD / AsyncSessionLocal）入库；
# 一次性把 backend/ 放入 sys.path，替代原先在每个函数里重复 sys.path.insert
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# OCR 引擎进程级共享 + 串行锁：
# 单事件循环下多 tab 并发，OCR 推理是同步阻塞调用，统一丢到 to_thread 并由
# threading.Lock 串行化，避免阻塞事件循环、也避免共享引擎实例的并发不安全。
_OCR_THREAD_LOCK = threading.Lock()
_ENGINE_LOCK = threading.Lock()
_slider_ocr_shared: Optional['ddddocr.DdddOcr'] = None
_det_ocr_shared: Optional['ddddocr.DdddOcr'] = None
_text_ocr_shared: Optional['ddddocr.DdddOcr'] = None
_paddle_ocr_shared: Optional['PaddleOCR'] = None


def _launch_kwargs(headless: bool) -> dict:
    """统一的浏览器启动参数（三处启动点共用）。

    移除了 --disable-web-security / --disable-features=IsolateOrigins 等
    非必需且可能被检测的 flag，仅保留稳定性必需的参数。
    """
    kwargs = {
        'headless': headless,
        'args': [
            '--no-sandbox',
            '--disable-gpu',
            '--disable-dev-shm-usage',
            '--disable-blink-features=AutomationControlled',
        ]
    }
    # 优先复用系统已安装的浏览器（Windows 用 Edge，Linux 用 Chrome），避免下载自带内核
    channel = detect_browser_channel()
    if channel:
        kwargs['channel'] = channel
    return kwargs



def detect_browser_channel():
    """检测可用的系统浏览器，返回 playwright channel 名；都没有则返回 None。

    优先复用本机已安装的浏览器，避免下载 Playwright 自带内核：
    - Windows: 使用系统 Edge（channel='msedge'）
    - Linux:   使用系统 Chrome（channel='chrome'）
    """
    import os
    import shutil
    if os.name == 'nt':
        # Windows 下 Edge 几乎必然存在
        edge_path = shutil.which('msedge')
        if not edge_path:
            candidates = [
                r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',
                r'C:\Program Files\Microsoft\Edge\Application\msedge.exe',
            ]
            edge_path = next((p for p in candidates if os.path.exists(p)), None)
        if edge_path:
            return 'msedge'
    else:
        # Linux / macOS：优先 Chrome，其次 Edge
        if shutil.which('google-chrome') or shutil.which('google-chrome-stable'):
            return 'chrome'
        if shutil.which('microsoft-edge') or shutil.which('microsoft-edge-stable'):
            return 'msedge'
    return None


class CaptchaSolver:
    """验证码解决器 - 使用 ddddocr 和 PaddleOCR 自动识别和解决验证码

    OCR 引擎按需惰性初始化（首次遇到验证码才加载），进程级共享单例；
    推理统一经 _ocr_call 丢到后台线程并串行化，避免阻塞事件循环。
    """

    def __init__(self, thread_id: int = 0):
        self.thread_id = thread_id
        self._slider_ocr = None
        self._det_ocr = None
        self._text_ocr = None
        self._paddle_ocr = None

    def _ensure_engines(self):
        """惰性初始化 OCR 引擎（进程级共享单例，线程安全）。"""
        global _slider_ocr_shared, _det_ocr_shared, _text_ocr_shared, _paddle_ocr_shared
        with _ENGINE_LOCK:
            if DDDDOCR_AVAILABLE:
                if _slider_ocr_shared is None:
                    try:
                        _slider_ocr_shared = ddddocr.DdddOcr(det=False, ocr=False, show_ad=False)
                        print(f"  [线程{self.thread_id}] ddddocr 滑块引擎初始化完成")
                    except Exception as e:
                        print(f"  [线程{self.thread_id}] ddddocr 滑块引擎初始化失败: {e}")
                if _det_ocr_shared is None:
                    try:
                        _det_ocr_shared = ddddocr.DdddOcr(det=True, ocr=False, show_ad=False)
                        print(f"  [线程{self.thread_id}] ddddocr 检测引擎初始化完成")
                    except Exception as e:
                        print(f"  [线程{self.thread_id}] ddddocr 检测引擎初始化失败: {e}")
                if _text_ocr_shared is None:
                    try:
                        _text_ocr_shared = ddddocr.DdddOcr(det=False, ocr=True, show_ad=False)
                        print(f"  [线程{self.thread_id}] ddddocr 文字引擎初始化完成")
                    except Exception as e:
                        print(f"  [线程{self.thread_id}] ddddocr 文字引擎初始化失败: {e}")
            # PaddleOCR（主要文字识别引擎）
            if PADDLEOCR_AVAILABLE and _paddle_ocr_shared is None:
                try:
                    _paddle_ocr_shared = PaddleOCR(lang='ch')
                    print(f"  [线程{self.thread_id}] PaddleOCR 初始化完成")
                except Exception as e:
                    print(f"  [线程{self.thread_id}] PaddleOCR 初始化失败: {e}")
                    _paddle_ocr_shared = None
            self._slider_ocr = _slider_ocr_shared
            self._det_ocr = _det_ocr_shared
            self._text_ocr = _text_ocr_shared
            self._paddle_ocr = _paddle_ocr_shared

    def is_available(self) -> bool:
        """检查验证码解决器是否可用（按库可用性判断，不触发初始化）"""
        return DDDDOCR_AVAILABLE or PADDLEOCR_AVAILABLE

    async def _ocr_call(self, fn, *args, **kwargs):
        """把同步 OCR 推理丢到后台线程，并用全局锁串行化。"""
        def _run():
            with _OCR_THREAD_LOCK:
                return fn(*args, **kwargs)
        return await asyncio.to_thread(_run)

    async def _recognize_char_fusion(self, char_img_bytes: bytes) -> list:
        """
        多引擎融合识别单个文字
        返回: 识别到的所有可能文字列表（去重后）
        策略：
        1. 使用 PaddleOCR 识别
        2. 使用 ddddocr 多种预处理方式识别
        3. 合并结果，去重后返回
        """
        all_results = set()

        # 策略1：使用 PaddleOCR（准确率更高）
        if PADDLEOCR_AVAILABLE and self._paddle_ocr is not None:
            try:
                nparr = np.frombuffer(char_img_bytes, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is not None:
                    result = await self._ocr_call(self._paddle_ocr.ocr, img, det=False, cls=False)
                    if result and result[0]:
                        text = result[0][0][0] if isinstance(result[0][0], tuple) else result[0][0]
                        if text and text.strip():
                            # 清理结果：只保留中文字符和常见字符
                            cleaned = self._clean_ocr_result(text.strip())
                            if cleaned:
                                all_results.update(cleaned)
            except Exception:
                pass

        # 策略2-4：ddddocr 多预处理变体识别（原图 / 自适应二值化 / Otsu / 灰度 / 2x / 3x 放大），
        # 合并所有候选字。不同变体在噪声、底色、对比度不同的验证码上互补，提升命中率。
        if self._text_ocr is not None:
            for variant_bytes in self._char_image_variants(char_img_bytes):
                try:
                    result = await self._ocr_call(self._text_ocr.classification, variant_bytes)
                    if result and result.strip():
                        cleaned = self._clean_ocr_result(result.strip())
                        if cleaned:
                            all_results.update(cleaned)
                except Exception:
                    pass

        return list(all_results)

    def _char_image_variants(self, char_img_bytes: bytes) -> list:
        """生成单字图片的多种预处理变体，供 ddddocr 分别识别。

        返回 [原图, 灰度, 自适应二值化, Otsu二值化, 2x放大, 3x放大]（CV2 不可用时退化为 [原图]）。
        """
        variants = [char_img_bytes]
        if not CV2_AVAILABLE:
            return variants

        try:
            nparr = np.frombuffer(char_img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if img is None:
                return variants

            height, width = img.shape[:2]

            # 灰度
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            variants.append(self._enc_png(gray))

            # 自适应二值化（保留原 _preprocess_char_image 的核心）
            binary = cv2.adaptiveThreshold(
                gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV, 11, 2,
            )
            variants.append(self._enc_png(binary))

            # Otsu 全局二值化（对低对比度/渐变底色更稳）
            _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            variants.append(self._enc_png(otsu))

            # 2x / 3x 放大（小图放大后笔画更连续）
            for scale in (2, 3):
                try:
                    resized = cv2.resize(img, (width * scale, height * scale), interpolation=cv2.INTER_CUBIC)
                    variants.append(self._enc_png(resized))
                except Exception:
                    pass
        except Exception:
            pass

        return variants

    @staticmethod
    def _enc_png(img) -> bytes:
        """将 OpenCV 图像编码为 PNG bytes。"""
        try:
            _, buffer = cv2.imencode('.png', img)
            return buffer.tobytes()
        except Exception:
            return None

    def _clean_ocr_result(self, text: str) -> list:
        """
        清理 OCR 结果，提取可能的单字
        返回: 可能的单字列表
        """
        if not text:
            return []

        results = []

        # 清理文本：移除空格和特殊字符
        cleaned = text.strip().replace(' ', '')

        # 如果结果是单个字符，直接返回
        if len(cleaned) == 1:
            return [cleaned]

        # 如果结果是多个字符，拆分成单个字符
        for char in cleaned:
            # 只保留中文字符、数字和字母
            if '\u4e00' <= char <= '\u9fff' or char.isalnum():
                results.append(char)

        return results

    def _find_best_match(self, target_char: str, char_map: dict) -> tuple:
        """
        在已识别的文字中查找与目标文字最匹配的
        返回: (matched_char, position_info) 或 (None, None)
        """
        # 直接匹配
        if target_char in char_map:
            return target_char, char_map[target_char]

        # 常见 OCR 错误映射表（基于观察到的错误）
        similar_chars = {
            '阵': ['军', '连', '陈'],
            '飞': ['乙', '几', '凡'],
            '枪': ['抢', '仓', '创'],
            '个': ['人', '介', '八'],
            '难': ['准', '谁', '堆'],
            '更': ['便', '史', '吏'],
            '家': ['嫁', '稼', '寥'],
            '望': ['塑', '壁', '璧'],
            '谁': ['准', '堆', '推'],
            '得': ['德', '待', '很'],
            '同': ['司', '句', '旬'],
            '造': ['告', '浩', '酷'],
            '也': ['他', '地', '池'],
            # —— 补充常见混淆字对（结构相似/易误识）——
            '已': ['己', '巳'],
            '己': ['已', '巳'],
            '千': ['干', '于', '十'],
            '干': ['千', '于'],
            '未': ['末', '来'],
            '末': ['未', '来', '木'],
            '人': ['入', '八', '个'],
            '入': ['人', '八'],
            '日': ['曰', '目', '田'],
            '曰': ['日', '目'],
            '目': ['日', '自', '且'],
            '自': ['目', '白', '首'],
            '白': ['自', '百', '日'],
            '百': ['白', '自'],
            '大': ['太', '犬', '人'],
            '太': ['大', '犬', '天'],
            '天': ['夫', '无', '大'],
            '夫': ['天', '大', '失'],
            '王': ['玉', '主', '五'],
            '玉': ['王', '主'],
            '土': ['士', '工', '上'],
            '士': ['土', '上', '工'],
            '田': ['由', '甲', '申', '日'],
            '由': ['田', '甲', '申'],
            '甲': ['由', '申', '田'],
            '申': ['由', '甲', '田'],
            '月': ['用', '目', '同', '内'],
            '用': ['月', '甩'],
            '方': ['万', '才'],
            '万': ['方', '乃'],
            '力': ['刀', '九'],
            '刀': ['力', '刃'],
            '九': ['力', '几'],
            '几': ['九', '儿'],
            '儿': ['几', '九'],
            '开': ['井', '升', '开'],
            '井': ['开', '并', '并'],
            '并': ['并', '开', '井'],
            '风': ['凤', '风'],
            '贝': ['见', '只'],
            '见': ['贝', '只'],
            '只': ['贝', '见', '双'],
            '内': ['肉', '丙'],
            '半': ['羊', '丰'],
            '羊': ['半', '丰', '美'],
            '丰': ['半', '羊'],
            '关': ['美', '天', '开'],
            '美': ['关', '羊', '差'],
            '问': ['间', '向'],
            '间': ['问', '同'],
            '向': ['问', '同'],
            '主': ['王', '玉', '生'],
            '生': ['主', '牛', '王'],
            '牛': ['生', '午'],
            '午': ['牛', '干'],
            '本': ['木', '未', '末'],
            '木': ['本', '末', '未', '才'],
            '才': ['木', '方'],
            '米': ['来', '采'],
            '来': ['米', '未', '末'],
            '采': ['米', '来'],
            '果': ['里', '田'],
            '里': ['果', '重', '田'],
            '重': ['里', '垂'],
            '厂': ['广', '丿'],
            '广': ['厂', '扩'],
            '云': ['去', '会'],
            '去': ['云', '丢'],
            '会': ['云', '合', '今'],
            '合': ['会', '令', '今'],
            '今': ['令', '合', '会'],
            '令': ['今', '合'],
            '全': ['金', '企'],
            '金': ['全', '企'],
            '企': ['全', '金', '合'],
            '无': ['天', '元', '夫'],
            '元': ['无', '天', '示'],
            '示': ['元', '不'],
            '不': ['示', '个'],
            '丁': ['了', '子'],
            '了': ['丁', '子'],
            '子': ['了', '孑'],
            '十': ['干', '千', '士'],
            '下': ['上', '不'],
            '上': ['下', '止'],
            '止': ['上', '正'],
            '正': ['止', '证'],
            '直': ['真', '且'],
            '真': ['直', '具'],
            '具': ['直', '真', '且'],
            '且': ['目', '具', '且'],
            '成': ['戊', '戌', '戎'],
            '戌': ['戊', '戍', '成'],
            '戍': ['戌', '戊'],
            '戊': ['戌', '戍', '成'],
            '特': ['持', '待', '侍'],
            '持': ['特', '待'],
            '待': ['持', '侍'],
            '构': ['构', '沟', '购'],
            '购': ['构', '沟'],
            '值': ['植', '直', '债'],
            '债': ['值', '植'],
            '植': ['值', '债'],
            '优': ['尤', '忧', '忧'],
            '尤': ['优', '龙'],
            '忧': ['优', '扰'],
            '扰': ['忧', '拢'],
            '晚': ['晓', '挽'],
            '晓': ['晚', '烧'],
            '烧': ['晓', '浇'],
            '浇': ['烧', '绕'],
            '绕': ['浇', '饶'],
            '饶': ['绕', '烧'],
            '纸': ['低', '抵', '邸'],
            '抵': ['低', '纸'],
            '低': ['抵', '纸'],
            '护': ['扩', '拧'],
            '扩': ['护', '广'],
            '拔': ['拨', '泼'],
            '拨': ['拔', '泼'],
            '泼': ['拔', '拨'],
        }

        # 尝试相似字符匹配
        if target_char in similar_chars:
            for similar in similar_chars[target_char]:
                if similar in char_map:
                    print(f"      [线程{self.thread_id}] 模糊匹配: '{target_char}' -> '{similar}'")
                    return similar, char_map[similar]

        return None, None

    async def detect_captcha_type(self, page: Page) -> str:
        """
        检测验证码类型
        返回: 'slider' (滑块/拼图), 'click' (点选)

        知网验证码特点：
        - 期刊页面 / 检索验证：blockPuzzle 拼图滑块（verify-img-panel + verify-move-block + verify-sub-block）
        - 论文详情页：文字点选验证码
        拼图滑块和点选验证码共用 verify-img-panel / verify-msg 元素，必须先按
        URL captchaType 参数和提示文字区分，否则会把滑块误判为点选。
        """
        tag = f"[线程{self.thread_id}]"
        try:
            # 1) 首选 URL captchaType 参数（最可靠）
            try:
                m = re.search(r'captchaType=([^&]+)', page.url)
                ctype = m.group(1) if m else ''
                if ctype:
                    if 'uzzle' in ctype or 'lider' in ctype:
                        print(f"    {tag} URL captchaType={ctype} → 滑块验证码")
                        return 'slider'
                    if 'lick' in ctype or 'Word' in ctype or 'word' in ctype:
                        print(f"    {tag} URL captchaType={ctype} → 点选验证码")
                        return 'click'
            except Exception:
                pass

            # 2) 提示文字判断（拼图滑块提示「向右滑动完成验证」）
            try:
                msg_elem = await page.query_selector('span.verify-msg')
                if msg_elem:
                    text = (await msg_elem.inner_text()) or ''
                    if '向右滑动' in text or '拖动' in text or '滑动' in text:
                        print(f"    {tag} 提示「{text}」→ 滑块验证码")
                        return 'slider'
                    if '点击' in text or '依次' in text:
                        print(f"    {tag} 提示「{text}」→ 点选验证码")
                        return 'click'
            except Exception:
                pass

            # 3) 结构判断：存在滑块把手/拼图块 → 滑块
            try:
                if await page.query_selector('div.verify-move-block, div.verify-sub-block, .yidun_slider, .nc-container'):
                    print(f"    {tag} 检测到滑块把手元素")
                    return 'slider'
            except Exception:
                pass

            # 4) 点选特征（verify-img-panel + verify-msg）——放在滑块判断之后，避免误判
            verify_img_panel = await page.query_selector('div.verify-img-panel')
            verify_msg = await page.query_selector('span.verify-msg')
            if verify_img_panel and verify_msg:
                print(f"    {tag} 检测到点选验证码元素 (verify-img-panel + verify-msg)")
                return 'click'

            # 5) 滑块验证码特征（用知网验证码专有的精确类，避免误命中结果页普通元素）
            slider_elem = await page.query_selector('.verify-slider, .slider-img, .nc-container, .yidun_slider, .jy-captcha')
            if slider_elem:
                print(f"    {tag} 检测到滑块验证码元素")
                return 'slider'

            # 6) 备用：通过页面文本判断
            html = await page.content()
            soup = BeautifulSoup(html, 'lxml')
            page_text = soup.get_text()

            # 检查点选验证码文本特征
            if '请依次点击' in page_text or '请点击' in page_text:
                print(f"    {tag} 通过文本检测到点选验证码")
                return 'click'

            # 检查滑块验证码文本特征
            if '滑块' in page_text or '拖动' in page_text:
                print(f"    {tag} 通过文本检测到滑块验证码")
                return 'slider'

            # 默认返回点选（论文详情页最常见）
            print(f"    {tag} 无法确定验证码类型，默认尝试点选验证码")
            return 'click'
        except Exception as e:
            print(f"    {tag} 检测验证码类型失败: {e}")
            return 'click'  # 默认返回点选类型（论文详情页更常见）

    async def solve_slider_captcha(self, page: Page, max_retries: int = SLIDER_CAPTCHA_MAX_RETRIES) -> bool:
        """
        解决滑块验证码
        使用 ddddocr 的 slide_match 计算滑动距离并模拟拖动
        """
        if not self.is_available():
            print(f"    [线程{self.thread_id}] ddddocr 不可用，无法自动解决滑块验证码")
            return False
        await asyncio.to_thread(self._ensure_engines)

        for attempt in range(max_retries):
            try:
                print(f"    [线程{self.thread_id}] 尝试解决滑块验证码 (第 {attempt + 1}/{max_retries} 次)")

                # 等待验证码元素加载
                await asyncio.sleep(2)

                # 获取滑块和背景图
                # 知网验证码通常有两个图片：滑块小图和背景大图
                html = await page.content()
                soup = BeautifulSoup(html, 'lxml')

                # 尝试定位滑块和背景图片
                images = soup.find_all('img')
                if len(images) < 2:
                    print(f"    [线程{self.thread_id}] 未找到足够的验证码图片")
                    await asyncio.sleep(1)
                    continue

                # 截图获取图片数据
                # 策略：分别截取滑块区域和背景区域
                target_bytes = None
                background_bytes = None

                # 尝试通过选择器获取
                try:
                    # 常见的滑块验证码选择器（含知网检索验证 blockPuzzle 的 yidun 结构）
                    slider_selectors = [
                        'div.verify-sub-block',   # yidun 拼图块（与背景同源，截图即目标）
                        'div.verify-slider',
                        '.slider-img',
                        '[class*="slider"]',
                        'img[src*="slider"]',
                    ]
                    bg_selectors = [
                        'div.verify-img-panel',   # yidun 背景图
                        'div.verify-bg',
                        '.bg-img',
                        '[class*="background"]',
                        'img[src*="bg"]',
                    ]

                    for selector in slider_selectors:
                        try:
                            slider_elem = await page.query_selector(selector)
                            if slider_elem:
                                target_bytes = await slider_elem.screenshot()
                                break
                        except:
                            continue

                    for selector in bg_selectors:
                        try:
                            bg_elem = await page.query_selector(selector)
                            if bg_elem:
                                background_bytes = await bg_elem.screenshot()
                                break
                        except:
                            continue

                except Exception as e:
                    print(f"    [线程{self.thread_id}] 获取验证码图片失败: {e}")

                # 如果通过选择器获取失败，尝试截取整个验证码区域
                if not target_bytes or not background_bytes:
                    # 截取整个页面，然后手动裁剪
                    full_screenshot = await page.screenshot()
                    # 这里简化处理，实际应该根据页面结构裁剪
                    print(f"    [线程{self.thread_id}] 使用备用截图方案")
                    # 对于知网，通常滑块图在左侧，背景图在右侧
                    # 这里需要根据实际情况调整
                    continue

                if not target_bytes or not background_bytes:
                    print(f"    [线程{self.thread_id}] 无法获取验证码图片")
                    await asyncio.sleep(1)
                    continue

                # 使用 ddddocr 计算滑动距离
                result = await self._ocr_call(
                    self._slider_ocr.slide_match,
                    target_bytes,
                    background_bytes,
                    simple_target=True,
                )

                if not result or 'target' not in result:
                    print(f"    [线程{self.thread_id}] 滑块识别失败")
                    await asyncio.sleep(1)
                    continue

                distance = result['target'][0]
                # 截图按设备像素比缩放：ddddocr 返回的是截图像素坐标，拖动需换算回 CSS 像素
                try:
                    dpr = await page.evaluate('window.devicePixelRatio') or 1
                    if dpr > 1:
                        distance = distance / dpr
                except Exception:
                    pass
                print(f"    [线程{self.thread_id}] 计算滑动距离: {distance:.0f}px")

                # 模拟人类拖动
                await self._human_drag(page, distance)

                # 等待验证结果
                await asyncio.sleep(3)

                # 检查是否验证通过
                current_url = page.url
                if not current_url.startswith(VERIFY_URL_PREFIX):
                    print(f"    [线程{self.thread_id}] ✓ 滑块验证码解决成功")
                    return True

                print(f"    [线程{self.thread_id}] 滑块验证未通过，重试...")
                await asyncio.sleep(2)

            except Exception as e:
                print(f"    [线程{self.thread_id}] 解决滑块验证码出错: {e}")
                await asyncio.sleep(1)

        print(f"    [线程{self.thread_id}] 滑块验证码解决失败，已达到最大重试次数")
        _report_captcha(tag=f"[线程{self.thread_id}]")
        return False

    async def _human_drag(self, page: Page, distance: float):
        """模拟人类拖动滑块"""
        try:
            # 获取滑块元素
            slider_selectors = [
                'div.verify-move-block',  # yidun 拖动把手（知网检索验证 blockPuzzle）
                '.verify-slider',
                '.slider',
                '[class*="slider"]',
                'img[src*="slider"]',
            ]

            slider_elem = None
            for selector in slider_selectors:
                try:
                    slider_elem = await page.query_selector(selector)
                    if slider_elem:
                        break
                except:
                    continue

            if not slider_elem:
                # 如果找不到特定滑块元素，使用鼠标在页面中心拖动
                viewport = await page.viewport_size()
                start_x = viewport['width'] // 4
                start_y = viewport['height'] // 2
            else:
                # 获取滑块位置
                box = await slider_elem.bounding_box()
                start_x = box['x'] + box['width'] / 2
                start_y = box['y'] + box['height'] / 2

            # 生成拖动轨迹（加速→匀速→减速）
            track = self._generate_drag_track(distance)

            # 执行拖动
            await page.mouse.move(start_x, start_y)
            await page.mouse.down()

            for offset_x, delay_ms in track:
                await page.mouse.move(start_x + offset_x, start_y + random.randint(-2, 2))
                await asyncio.sleep(delay_ms / 1000)

            await page.mouse.up()
            print(f"    [线程{self.thread_id}] 滑块拖动完成")

        except Exception as e:
            print(f"    [线程{self.thread_id}] 拖动滑块失败: {e}")

    def _generate_drag_track(self, distance: float) -> List[Tuple[float, float]]:
        """
        生成人类化拖动轨迹
        返回: [(offset_x, delay_ms), ...]
        """
        track = []
        current = 0

        # 加速阶段
        while current < distance * 0.3:
            step = random.uniform(2, 5)
            delay = random.uniform(10, 20)
            current += step
            track.append((current, delay))

        # 匀速阶段
        while current < distance * 0.7:
            step = random.uniform(3, 6)
            delay = random.uniform(15, 25)
            current += step
            track.append((current, delay))

        # 减速阶段
        while current < distance:
            step = random.uniform(1, 3)
            delay = random.uniform(20, 40)
            current += step
            if current > distance:
                current = distance
            track.append((current, delay))

        return track

    async def solve_click_captcha(self, page: Page, max_retries: int = CLICK_CAPTCHA_MAX_RETRIES) -> bool:
        """
        解决文字点选验证码
        根据知网验证码结构：
        - div.verify-img-panel > img 是验证码图片
        - div.verify-bar-area > span.verify-msg 是提示文字
        - div.verify-refresh 是刷新按钮
        
        逻辑：
        - 识别所有文字位置，建立文字->位置映射
        - 如果所有目标文字都能找到对应位置，则按顺序点击
        - 如果有任何一个目标文字找不到位置，则不点击，直接刷新重试
        - 最多尝试10次
        """
        if not self.is_available():
            print(f"    [线程{self.thread_id}] ddddocr 不可用，无法自动解决点选验证码")
            return False
        await asyncio.to_thread(self._ensure_engines)

        for attempt in range(max_retries):
            try:
                print(f"    [线程{self.thread_id}] 尝试解决点选验证码 (第 {attempt + 1}/{max_retries} 次)")

                await asyncio.sleep(2)

                # 预检：每次重试开始前，先判断当前 URL 是否仍在验证码页面。
                # 若已离开（验证已通过或已自动跳转），直接判定成功返回，
                # 避免「找不到 verify-msg 元素 / 找不到刷新按钮」时无限空转刷新。
                if page.is_closed():
                    print(f"    [线程{self.thread_id}] 页面已关闭，无法继续解决验证码")
                    return False
                current_url = page.url
                if not current_url.startswith(VERIFY_URL_PREFIX):
                    print(f"    [线程{self.thread_id}] 当前 URL 已不在验证码页，视为验证已通过")
                    return True

                # 获取提示文字 - 使用正确的选择器
                verify_msg_elem = await page.query_selector('div.verify-bar-area span.verify-msg')
                if not verify_msg_elem:
                    print(f"    [线程{self.thread_id}] 未找到 verify-msg 元素，点击刷新...")
                    await self._click_refresh(page)
                    continue

                prompt_text_full = await verify_msg_elem.text_content()
                print(f"    [线程{self.thread_id}] 提示文字: {prompt_text_full}")

                # 提取需要点击的文字（格式："请依次点击【整,研,力】"）
                match = re.search(r'[【\[](.+?)[】\]]', prompt_text_full)
                if not match:
                    print(f"    [线程{self.thread_id}] 无法从提示中提取目标文字，点击刷新...")
                    await self._click_refresh(page)
                    continue

                target_chars_str = match.group(1)
                # 支持逗号、顿号、空格分隔
                target_chars = [c.strip() for c in re.split(r'[,，、\s]+', target_chars_str) if c.strip()]
                print(f"    [线程{self.thread_id}] 需要点击的文字: {target_chars}")

                if not target_chars:
                    print(f"    [线程{self.thread_id}] 无法识别点选目标，点击刷新...")
                    await self._click_refresh(page)
                    continue

                # 截取验证码图片 - 使用正确的选择器
                verify_img_panel = await page.query_selector('div.verify-img-panel')
                if not verify_img_panel:
                    print(f"    [线程{self.thread_id}] 未找到 verify-img-panel 元素，点击刷新...")
                    await self._click_refresh(page)
                    continue

                # 截取验证码区域
                captcha_bytes = await verify_img_panel.screenshot()

                if not captcha_bytes:
                    print(f"    [线程{self.thread_id}] 无法截取验证码图片，点击刷新...")
                    await self._click_refresh(page)
                    continue

                # 校验截图字节为有效图片：页面跳转/刷新瞬间可能截到空或损坏字节，
                # 会令 PIL / ddddocr 抛 cannot identify image file，提前拦截并刷新重试
                from PIL import Image
                import io
                try:
                    img = Image.open(io.BytesIO(captcha_bytes))
                    img.load()
                except Exception as img_err:
                    print(f"    [线程{self.thread_id}] 截图非有效图片（{img_err}），刷新重试...")
                    await self._click_refresh(page)
                    continue

                print(f"    [线程{self.thread_id}] 验证码图片已截取，开始识别文字位置和文字内容...")

                # 使用目标检测获取所有文字位置
                bboxes = await self._ocr_call(self._det_ocr.detection, captcha_bytes)

                if not bboxes:
                    print(f"    [线程{self.thread_id}] 未检测到文字位置，点击刷新...")
                    await self._click_refresh(page)
                    continue

                print(f"    [线程{self.thread_id}] 检测到 {len(bboxes)} 个文字位置")

                # 获取验证码图片在页面中的位置
                panel_box = await verify_img_panel.bounding_box()
                if not panel_box:
                    print(f"    [线程{self.thread_id}] 无法获取验证码区域位置，点击刷新...")
                    await self._click_refresh(page)
                    continue

                panel_x = panel_box['x']
                panel_y = panel_box['y']

                # 关键：screenshot() 返回的是设备像素，bounding_box() 返回的是 CSS 像素。
                # 显示器 DPI 缩放（Windows 125%/150% 等）时两者不一致，直接相加会把点击坐标整体偏移。
                # 必须把 OCR 输出的设备像素坐标除以 devicePixelRatio 换算回 CSS 像素再点击。
                dpr = 1.0
                try:
                    dpr = float(await page.evaluate('window.devicePixelRatio') or 1.0)
                except Exception:
                    dpr = 1.0
                if dpr <= 0:
                    dpr = 1.0

                # 使用 OCR 识别每个位置上的文字（img 已在截图校验时打开，直接复用）
                char_map = {}  # 文字 -> 位置的映射

                for i, bbox in enumerate(bboxes):
                    x1, y1, x2, y2 = bbox
                    # 裁剪时外扩 3px，避免笔画贴边被截断导致识别率下降
                    pad = 3
                    crop_box = (
                        max(0, x1 - pad), max(0, y1 - pad),
                        min(img.width, x2 + pad), min(img.height, y2 + pad),
                    )
                    char_img = img.crop(crop_box)
                    # 转换为 bytes
                    img_buffer = io.BytesIO()
                    char_img.save(img_buffer, format='PNG')
                    char_img_bytes = img_buffer.getvalue()

                    # 使用多引擎融合识别
                    recognized_chars = await self._recognize_char_fusion(char_img_bytes)

                    if recognized_chars:
                        # 将设备像素坐标转换为 CSS 像素后，再加页面偏移得到绝对坐标
                        abs_x = panel_x + ((x1 + x2) / 2) / dpr
                        abs_y = panel_y + ((y1 + y2) / 2) / dpr

                        # 存储该位置的所有可能识别结果
                        for char in recognized_chars:
                            if char not in char_map:
                                char_map[char] = {
                                    'center_x': abs_x,
                                    'center_y': abs_y,
                                    'bbox': bbox,
                                    'alternatives': recognized_chars
                                }

                        print(f"      [线程{self.thread_id}] 位置 {i+1}: 识别到文字 {recognized_chars}")

                # 检查是否所有目标文字都能找到对应位置（支持模糊匹配）
                matched_positions = []  # 存储 (target_char, position_info)
                missing_chars = []

                for target_char in target_chars:
                    matched_char, pos = self._find_best_match(target_char, char_map)
                    if pos:
                        matched_positions.append((target_char, matched_char, pos))
                    else:
                        missing_chars.append(target_char)

                if missing_chars:
                    print(f"    [线程{self.thread_id}] 未能找到以下文字的位置: {missing_chars}")
                    print(f"    [线程{self.thread_id}] 识别到的文字: {list(char_map.keys())}")
                    print(f"    [线程{self.thread_id}] 不点击，直接刷新重试...")
                    await self._click_refresh(page)
                    continue

                # 所有目标文字都找到了，按顺序点击
                print(f"    [线程{self.thread_id}] 所有目标文字位置已确认（含模糊匹配），开始按顺序点击...")
                for i, (target_char, matched_char, pos) in enumerate(matched_positions):
                    if target_char == matched_char:
                        print(f"      [线程{self.thread_id}] 点击第 {i+1} 个文字 '{target_char}' 位置: ({pos['center_x']:.0f}, {pos['center_y']:.0f})")
                    else:
                        print(f"      [线程{self.thread_id}] 点击第 {i+1} 个文字 '{target_char}'(匹配到'{matched_char}') 位置: ({pos['center_x']:.0f}, {pos['center_y']:.0f})")
                    await self._click_with_offset(page, pos['center_x'], pos['center_y'])
                    await asyncio.sleep(random.uniform(0.8, 1.5))

                # 等待验证结果
                await asyncio.sleep(3)

                current_url = page.url
                if not current_url.startswith(VERIFY_URL_PREFIX):
                    print(f"    [线程{self.thread_id}] ✓ 点选验证码解决成功")
                    return True

                print(f"    [线程{self.thread_id}] 点选验证未通过，刷新重试...")
                await self._click_refresh(page)

            except Exception as e:
                print(f"    [线程{self.thread_id}] 解决点选验证码出错: {e}")
                import traceback
                traceback.print_exc()
                await self._click_refresh(page)

        print(f"    [线程{self.thread_id}] 点选验证码解决失败，已达到最大重试次数 ({max_retries})")
        _report_captcha(tag=f"[线程{self.thread_id}]")
        return False

    async def _click_refresh(self, page: Page):
        """点击刷新按钮"""
        try:
            # 检查页面是否已关闭
            if page.is_closed():
                print(f"    [线程{self.thread_id}] 页面已关闭，无法点击刷新按钮")
                return False

            refresh_btn = await page.query_selector('div.verify-refresh')
            if refresh_btn:
                await refresh_btn.click()
                print(f"    [线程{self.thread_id}] 已点击刷新按钮")
                await asyncio.sleep(2)
                return True
            else:
                print(f"    [线程{self.thread_id}] 未找到刷新按钮，等待后重试...")
                await asyncio.sleep(3)
                return False
        except Exception as e:
            print(f"    [线程{self.thread_id}] 点击刷新按钮失败: {e}")
            await asyncio.sleep(3)
            return False

    async def _click_with_offset(self, page: Page, base_x: float, base_y: float):
        """带随机偏移的点击"""
        offset_x = random.randint(-5, 5)
        offset_y = random.randint(-5, 5)
        await page.mouse.click(base_x + offset_x, base_y + offset_y)


class HistoryManager:
    """历史记录管理器"""
    _lock = threading.Lock()

    @staticmethod
    def load_journals_history() -> dict:
        """加载期刊历史记录"""
        if JOURNALS_HISTORY_FILE.exists():
            with open(JOURNALS_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {'last_updated': None, 'journals': {}}

    @staticmethod
    def _atomic_write(path: Path, data: dict):
        """原子写 JSON：先写临时文件再 rename，避免崩溃/中断时损坏缓存文件。"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + '.tmp')
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        tmp.replace(path)

    @staticmethod
    def save_journals_history(journals: dict):
        """保存期刊历史记录"""
        data = {
            'last_updated': datetime.now().isoformat(),
            'journals': journals
        }
        HistoryManager._atomic_write(JOURNALS_HISTORY_FILE, data)

    @staticmethod
    def load_papers_history() -> dict:
        """加载论文链接历史记录"""
        if PAPERS_HISTORY_FILE.exists():
            with open(PAPERS_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {'last_updated': None, 'papers': {}}

    @staticmethod
    def save_papers_history(papers: dict):
        """保存论文链接历史记录"""
        data = {
            'last_updated': datetime.now().isoformat(),
            'papers': papers
        }
        HistoryManager._atomic_write(PAPERS_HISTORY_FILE, data)

    @staticmethod
    def is_journals_cache_valid() -> bool:
        """检查期刊缓存是否有效"""
        history = HistoryManager.load_journals_history()
        if not history['last_updated']:
            return False
        last_updated = datetime.fromisoformat(history['last_updated'])
        return datetime.now() - last_updated < timedelta(days=JOURNAL_CACHE_DAYS)

    @staticmethod
    def is_journal_year_crawled(journal_name: str, year: str) -> bool:
        """检查期刊某年份是否已爬取"""
        history = HistoryManager.load_papers_history()
        papers = history.get('papers', {})
        if journal_name not in papers:
            return False
        if year not in papers[journal_name]:
            return False
        year_data = papers[journal_name][year]
        return len(year_data) > 0

    @staticmethod
    def get_papers_for_journal_year(journal_name: str, year: str) -> list:
        """获取期刊某年份的所有论文链接（过滤非论文条目）"""
        history = HistoryManager.load_papers_history()
        papers = history.get('papers', {})
        if journal_name not in papers:
            return []
        if year not in papers[journal_name]:
            return []

        skip_keywords = [
            '征稿启事', '征稿', '征文', '征订', '稿约', '投稿须知', '投稿指南',
            '总目录', '目录', '索引', '内容提要',
            '编辑部公告', '编辑部关于', '编辑部声明', '公告', '声明', '启事', '通知', '更正', '勘误', '补遗',
            '书评', '评介', '学院简介', '中心简介', '新书介绍', '新书评介',
            '会议纪要', '会议综述', '会议报道', '会议简报',
            '新闻', '消息', '简讯', '报道',
            '广告', '致谢名单', '致谢专家', '鸣谢',
            '卷首语', '编者按', '导读', '操作指南', '使用指南', '手册',
            '人才招聘', '全球人才招聘', '招生', '培训', '课程', '讲座',
            '版权声明', '著作权', '授权声明',
            '欢迎订阅', '订阅杂志', '订购', '欢迎购买',
        ]

        all_papers = []
        for issue_num, issue_data in papers[journal_name][year].items():
            if 'papers' in issue_data:
                for paper in issue_data['papers']:
                    title = paper.get('title', '')
                    if any(keyword in title for keyword in skip_keywords):
                        continue
                    all_papers.append(paper)
        return all_papers

    @staticmethod
    def add_papers_for_journal_issue(journal_name: str, year: str, issue: str, papers: list):
        """添加期刊某期次的论文链接"""
        with HistoryManager._lock:
            history = HistoryManager.load_papers_history()
            if 'papers' not in history:
                history['papers'] = {}
            if journal_name not in history['papers']:
                history['papers'][journal_name] = {}
            if year not in history['papers'][journal_name]:
                history['papers'][journal_name][year] = {}

            history['papers'][journal_name][year][issue] = {
                'last_crawled': datetime.now().isoformat(),
                'papers': papers
            }
            HistoryManager.save_papers_history(history['papers'])


class JournalCrawler:
    """期刊/详情爬虫基类（单浏览器 + 多标签页并发模型）"""

    def __init__(self, headless=True, thread_id=0, state_file=None,
                 refs_with_details=False, ref_max_items=None):
        self.headless = headless
        self.thread_id = thread_id
        # --detail-refs：详情入库后在同一页顺带抓参考文献（省二次导航，防风控）
        self.refs_with_details = refs_with_details
        self.max_items = ref_max_items
        self.page = None
        self.browser = None
        self.playwright = None
        self.context = None
        # 会话态文件：存在则复用（暖会话），结束时保存（供下次/详情阶段使用）
        self.state_file = Path(state_file) if state_file else None
        self.db_initialized = False
        self.captcha_solver = CaptchaSolver(thread_id=thread_id)
        self._captcha_retry_count = 0
        self._max_captcha_retries = 3

    async def init_browser(self):
        """初始化浏览器"""
        self.playwright = await async_playwright().start()
        launch_kwargs = _launch_kwargs(self.headless)
        self.browser = await self.playwright.chromium.launch(**launch_kwargs)

        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
        ]
        user_agent = random.choice(user_agents)

        viewports = [
            {'width': 1280, 'height': 800},
            {'width': 1366, 'height': 768},
            {'width': 1440, 'height': 900},
            {'width': 1536, 'height': 864},
            {'width': 1920, 'height': 1080},
        ]
        viewport = random.choice(viewports)

        ctx_kwargs = {
            'user_agent': user_agent,
            'viewport': viewport,
            'locale': 'zh-CN',
            'timezone_id': 'Asia/Shanghai',
            'permissions': ['geolocation'],
            'geolocation': {'latitude': 39.9042, 'longitude': 116.4074},
        }
        # 复用已保存的会话态（暖会话，显著降低冷会话首波验证码）
        if self.state_file and self.state_file.exists():
            ctx_kwargs['storage_state'] = str(self.state_file)
            print(f"  [线程{self.thread_id}] 复用会话态: {self.state_file}")

        context = await self.browser.new_context(**ctx_kwargs)

        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en']
            });
            window.chrome = { runtime: {} };
        """)

        # 保存 context，供详情并发阶段（fetch_details_concurrent）开 worker tab
        self.context = context
        self.page = await context.new_page()
        print(f"  [线程{self.thread_id}] 浏览器已启动")
        print(f"  [线程{self.thread_id}] 指纹: {user_agent[:40]}...")

    async def close_browser(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        print(f"  [线程{self.thread_id}] 浏览器已关闭")

    async def save_storage_state(self):
        """保存会话态到 state_file（供下次运行 / 详情阶段复用）。"""
        if not self.state_file or not self.page:
            return
        try:
            await self.page.context.storage_state(path=str(self.state_file))
            print(f"  [线程{self.thread_id}] 会话态已保存: {self.state_file}")
        except Exception as e:
            print(f"  [线程{self.thread_id}] 保存会话态失败: {e}")

    async def _warmup(self):
        """暖场：访问知网首页停留片刻并保存会话态，降低冷会话首波验证码概率。"""
        if not self.page:
            return
        try:
            await _pacing_wait()
            await self.page.goto('https://www.cnki.net/', wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(random.uniform(2, 4))
            await self.random_scroll()
            await self.save_storage_state()
            print(f"  [线程{self.thread_id}] 暖场完成")
        except Exception as e:
            print(f"  [线程{self.thread_id}] 暖场跳过: {e}")

    async def random_scroll(self, page=None):
        """随机滚动页面模拟人类行为"""
        page = page or self.page
        try:
            scroll_times = random.randint(1, 3)
            for _ in range(scroll_times):
                scroll_y = random.randint(100, 500)
                await page.evaluate(f'window.scrollBy(0, {scroll_y})')
                await asyncio.sleep(random.uniform(0.5, 2))
        except Exception:
            pass

    def is_verify_page(self, page_url: str) -> bool:
        """检查是否是验证码页面"""
        return page_url.startswith(VERIFY_URL_PREFIX)

    async def wait_for_page_stable(self, target_url: str, max_wait_time: int = 300, page=None) -> bool:
        """等待页面稳定，自动解决验证码"""
        page = page or self.page
        current_url = page.url

        if not self.is_verify_page(current_url):
            return True

        print(f"    [线程{self.thread_id}] ⚠ 遇到验证码页面")

        # 检查是否超过最大重试次数
        if self._captcha_retry_count >= self._max_captcha_retries:
            print(f"    [线程{self.thread_id}] 验证码重试次数已达上限 ({self._max_captcha_retries})，放弃")
            return False

        self._captcha_retry_count += 1

        # 尝试自动解决验证码
        if self.captcha_solver.is_available():
            captcha_type = await self.captcha_solver.detect_captcha_type(page)
            print(f"    [线程{self.thread_id}] 检测到验证码类型: {captcha_type}")

            if captcha_type == 'slider':
                success = await self.captcha_solver.solve_slider_captcha(page)
                if success:
                    self._captcha_retry_count = 0  # 成功后重置计数器
                    return True
            elif captcha_type == 'click':
                success = await self.captcha_solver.solve_click_captcha(page)
                if success:
                    self._captcha_retry_count = 0
                    return True

            print(f"    [线程{self.thread_id}] 自动解决验证码失败，尝试手动解决...")
        else:
            print(f"    [线程{self.thread_id}] ddddocr 不可用，无法自动解决验证码")

        # 自动解决失败，降级到手动解决（仅非 headless 模式）
        if self.headless:
            print(f"    [线程{self.thread_id}] 当前为无头模式，无法手动解决验证码")
            return False

        print(f"    [线程{self.thread_id}] 请在浏览器窗口中手动完成验证...")

        start_time = asyncio.get_event_loop().time()

        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > max_wait_time:
                print(f"    [线程{self.thread_id}] 等待验证码解决超时")
                return False

            current_url = page.url

            if not self.is_verify_page(current_url):
                print(f"    [线程{self.thread_id}] ✓ 验证码已解决")
                self._captcha_retry_count = 0  # 成功后重置计数器
                return True

            await asyncio.sleep(1)

    async def get_year_issues(self, journal_url: str) -> list:
        """获取期刊的年份期次列表"""
        print(f"  [线程{self.thread_id}] 访问期刊页面: {journal_url[:60]}...")
        await _pacing_wait()
        await self.page.goto(journal_url, wait_until='domcontentloaded', timeout=60000)

        if not await self.wait_for_page_stable(journal_url):
            return []

        # 事件驱动：等期次树容器出现再解析，替代固定 8s 等待
        try:
            await self.page.wait_for_selector(
                'div.yearissuepage, #YearIssueTree', timeout=PAGE_STABLE_TIMEOUT * 1000
            )
        except Exception:
            print(f"  [线程{self.thread_id}] 等待期次容器超时，继续尝试解析")
        await asyncio.sleep(random.uniform(MIN_DETAIL_DELAY, MAX_DETAIL_DELAY))

        current_year = datetime.now().year
        latest_issue = max(1, datetime.now().month - 2)

        print(f"  [线程{self.thread_id}] 应获取最新期次: {current_year}年第{latest_issue}期")

        issues = []
        html = await self.page.content()
        soup = BeautifulSoup(html, 'lxml')

        year_issue_container = soup.find('div', class_='yearissuepage')
        if not year_issue_container:
            year_issue_container = soup.find('div', id='YearIssueTree')

        if year_issue_container:
            year_dls = year_issue_container.find_all('dl')

            for year_dl in year_dls:
                dt = year_dl.find('dt')
                if not dt:
                    continue

                em = dt.find('em')
                if not em:
                    continue

                year_text = em.get_text(strip=True)
                year_match = re.search(r'(\d{4})', year_text)
                if not year_match:
                    continue

                year = year_match.group(1)

                if year not in TARGET_YEARS:
                    continue

                dd = year_dl.find('dd')
                if not dd:
                    continue

                issue_links = dd.find_all('a', id=True)

                for link in issue_links:
                    issue_id = link.get('id', '')
                    issue_text = link.get_text(strip=True)

                    if issue_id.startswith('yq'):
                        match = re.match(r'yq(\d{4})(\d{2})', issue_id)
                        if match:
                            issue_year = int(match.group(1))
                            issue_num = int(match.group(2))

                            should_include = False

                            if issue_year == current_year:
                                if issue_num <= latest_issue:
                                    should_include = True
                            elif issue_year < current_year:
                                should_include = True

                            if should_include:
                                issues.append({
                                    'year': str(issue_year),
                                    'issue_id': issue_id,
                                    'issue_text': issue_text,
                                    'issue_num': issue_num
                                })

        issues.sort(key=lambda x: (x['year'], x['issue_num']), reverse=True)
        print(f"  [线程{self.thread_id}] 共找到 {len(issues)} 个应获取的期次")

        return issues

    async def get_papers_from_page(self) -> list:
        """从当前页面获取论文列表（过滤非论文条目）"""
        papers = []
        html = await self.page.content()
        soup = BeautifulSoup(html, 'lxml')

        catalog = soup.find('div', id='rightCataloglist')
        if not catalog:
            catalog = soup.find('div', id='originalCatalogview')

        skip_keywords = [
            '征稿启事', '征稿', '征文', '征订', '稿约', '投稿须知', '投稿指南',
            '总目录', '目录', '索引', '内容提要',
            '编辑部公告', '编辑部关于', '编辑部声明', '公告', '声明', '启事', '通知', '更正', '勘误', '补遗',
            '书评', '评介', '学院简介', '中心简介', '新书介绍', '新书评介',
            '会议纪要', '会议综述', '会议报道', '会议简报',
            '新闻', '消息', '简讯', '报道',
            '广告', '致谢名单', '致谢专家', '鸣谢',
            '卷首语', '编者按', '导读', '操作指南', '使用指南', '手册',
            '人才招聘', '全球人才招聘', '招生', '培训', '课程', '讲座',
            '版权声明', '著作权', '授权声明',
            '欢迎订阅', '订阅杂志', '订购', '欢迎购买',
        ]

        if catalog:
            rows = catalog.find_all('dd', class_='row')
            for row in rows:
                name_span = row.find('span', class_='name')
                if name_span:
                    link = name_span.find('a')
                    if link:
                        title = link.get_text(strip=True)
                        href = link.get('href', '')
                        if title and href:
                            if any(keyword in title for keyword in skip_keywords):
                                print(f"    [线程{self.thread_id}] 过滤非论文条目: {title[:40]}...")
                                continue
                            if href.startswith('/'):
                                href = urljoin(BASE_URL, href)
                            papers.append({'title': title, 'url': href, 'status': 0})

        return papers

    async def crawl_year_papers_with_larrow(self, journal_name: str, year: str, year_issue_list: list) -> list:
        """使用"前一期"按钮获取该年份的所有论文"""
        year_papers = []
        crawled_issues = set()

        target_issue_count = len(year_issue_list)
        print(f"    [线程{self.thread_id}] 应该获取的期次: {target_issue_count} 个")

        issue_count = 0
        while True:
            issue_count += 1

            html = await self.page.content()
            soup = BeautifulSoup(html, 'lxml')

            date_list_span = soup.find('span', class_='date-list')
            if date_list_span:
                date_list_value = date_list_span.get('value', '')
                date_list_text = date_list_span.get_text(strip=True)
                print(f"\n    [线程{self.thread_id}] 当前显示: {date_list_text} ({date_list_value})")
            else:
                current_issue_link = soup.find('a', class_='current', id=re.compile(r'yq\d+'))
                if current_issue_link:
                    date_list_value = current_issue_link.get('id', '')
                    date_list_text = current_issue_link.get_text(strip=True)
                    print(f"\n    [线程{self.thread_id}] 当前显示: {date_list_text} ({date_list_value})")
                else:
                    print(f"    [线程{self.thread_id}] 无法获取当前期次信息，跳过")
                    break

            match = re.match(r'yq(\d{4})(\d{2})', date_list_value)
            if match:
                current_year = match.group(1)
                issue_num = match.group(2)
            else:
                print(f"    [线程{self.thread_id}] 无法解析期次ID: {date_list_value}")
                break

            if current_year != year:
                print(f"    [线程{self.thread_id}] 当前年份 {current_year} 与目标年份 {year} 不一致，结束")
                break

            if date_list_value in crawled_issues:
                print(f"      [线程{self.thread_id}] 期次 {date_list_text} 已获取过，跳过")
            else:
                papers = await self.get_papers_from_page()
                print(f"      [线程{self.thread_id}] 当前期次获取到 {len(papers)} 篇论文")

                crawled_issues.add(date_list_value)
                HistoryManager.add_papers_for_journal_issue(journal_name, year, issue_num, papers)
                year_papers.extend(papers)

                print(f"      [线程{self.thread_id}] 期次 {date_list_text} 共 {len(papers)} 篇论文已保存")

            if len(crawled_issues) >= target_issue_count:
                print(f"    [线程{self.thread_id}] 已获取完所有目标期次 ({len(crawled_issues)}/{target_issue_count})，结束")
                break

            larrow = await self.page.query_selector('#larrow')
            if not larrow:
                print(f"    [线程{self.thread_id}] 未找到前一期按钮，结束")
                break

            class_attr = await larrow.get_attribute('class') or ''
            if 'disable' in class_attr:
                print(f"    [线程{self.thread_id}] 前一期按钮已禁用，该年份获取完成")
                break

            print(f"    [线程{self.thread_id}] 点击前一期按钮...")
            try:
                await _pacing_wait()
                await self.page.evaluate('document.getElementById("larrow").click()')
                # 事件驱动：等目录容器重新出现再继续，替代固定 8s
                try:
                    await self.page.wait_for_selector(
                        '#rightCataloglist, #originalCatalogview', timeout=PAGE_STABLE_TIMEOUT * 1000
                    )
                except Exception:
                    print(f"    [线程{self.thread_id}] 等待目录容器超时，继续尝试解析")
                await asyncio.sleep(random.uniform(MIN_DETAIL_DELAY, MAX_DETAIL_DELAY))
            except Exception as e:
                print(f"    [线程{self.thread_id}] 点击前一期按钮失败: {e}")
                break

            if self.is_verify_page(self.page.url):
                print(f"    [线程{self.thread_id}] ⚠ 遇到验证码页面，等待解决...")
                if not await self.wait_for_page_stable(self.page.url):
                    print(f"    [线程{self.thread_id}] 验证码未解决，结束该年份获取")
                    break

        print(f"\n    [线程{self.thread_id}] 年份 {year} 共获取 {len(year_papers)} 篇论文，{len(crawled_issues)}/{target_issue_count} 个期次")
        return year_papers

    async def crawl_papers_for_journal(self, journal_name: str, journal_info: dict) -> list:
        """获取期刊论文链接"""
        journal_url = journal_info['url'] if isinstance(journal_info, dict) else journal_info

        print(f"\n[线程{self.thread_id}] {'=' * 60}")
        print(f"[线程{self.thread_id}] 处理期刊: {journal_name}")
        print(f"[线程{self.thread_id}] {'=' * 60}")

        all_papers = []

        for year in TARGET_YEARS:
            if HistoryManager.is_journal_year_crawled(journal_name, year):
                print(f"[线程{self.thread_id}] 年份 {year} 已存在历史记录，直接复用")
                papers = HistoryManager.get_papers_for_journal_year(journal_name, year)
                all_papers.extend(papers)
            else:
                print(f"[线程{self.thread_id}] 年份 {year} 无历史记录，需要爬取")

        if all(HistoryManager.is_journal_year_crawled(journal_name, year) for year in TARGET_YEARS):
            print(f"[线程{self.thread_id}] 所有年份已缓存，共 {len(all_papers)} 篇论文")
            return all_papers

        issues = await self.get_year_issues(journal_url)
        if not issues:
            print(f"[线程{self.thread_id}] 未找到期次列表")
            return all_papers

        issues_to_crawl = []
        for issue in issues:
            year = issue['year']
            issue_num = f"{issue['issue_num']:02d}"
            history = HistoryManager.load_papers_history()
            if (journal_name in history.get('papers', {}) and
                year in history['papers'][journal_name] and
                issue_num in history['papers'][journal_name][year]):
                print(f"  [线程{self.thread_id}] 期次 {issue['issue_text']} 已缓存，跳过")
            else:
                issues_to_crawl.append(issue)

        print(f"[线程{self.thread_id}] 需要爬取 {len(issues_to_crawl)} 个期次")

        from collections import defaultdict
        year_issues = defaultdict(list)
        for issue in issues_to_crawl:
            year_issues[issue['year']].append(issue)

        current_year = str(datetime.now().year)

        for year in sorted(year_issues.keys(), reverse=True):
            year_issue_list = year_issues[year]
            print(f"\n  [线程{self.thread_id}] 处理年份: {year}年，共 {len(year_issue_list)} 个期次")

            if year != current_year:
                year_dl_id = f"{year}_Year_Issue"
                print(f"    [线程{self.thread_id}] 点击年份按钮展开: {year_dl_id}")
                try:
                    await self.page.evaluate(f'''
                        var dl = document.getElementById("{year_dl_id}");
                        if (dl) {{
                            var dt = dl.querySelector("dt");
                            if (dt) dt.click();
                        }}
                    ''')
                    await asyncio.sleep(3)
                    print(f"    [线程{self.thread_id}] 年份 {year} 已展开")

                    year_issues_sorted = sorted(year_issue_list, key=lambda x: x['issue_num'], reverse=True)
                    if year_issues_sorted:
                        latest_issue = year_issues_sorted[0]
                        latest_issue_id = latest_issue['issue_id']
                        latest_issue_text = latest_issue['issue_text']
                        print(f"    [线程{self.thread_id}] 点击最新期次: {latest_issue_text} ({latest_issue_id})")
                        await self.page.evaluate(f'document.getElementById("{latest_issue_id}").click()')
                        await asyncio.sleep(5)
                        print(f"    [线程{self.thread_id}] 已切换到 {year} 年最新期次")
                except Exception as e:
                    print(f"    [线程{self.thread_id}] 点击年份按钮或期次失败: {e}")
                    continue
            else:
                print(f"    [线程{self.thread_id}] 年份 {year} 是当前年份，无需点击展开")

            year_papers = await self.crawl_year_papers_with_larrow(journal_name, year, year_issue_list)
            all_papers.extend(year_papers)

        print(f"\n[线程{self.thread_id}] 期刊 {journal_name} 共获取 {len(all_papers)} 篇论文")
        return all_papers

    async def crawl_paper_detail(self, paper_info: dict, journal_name: str = None, year: str = None, issue: str = None, page=None) -> dict:
        """获取论文详情"""
        page = page or self.page
        paper_url = paper_info['url']

        # 去重检查（并发 worker 间安全网；批量阶段已预取 existing_urls 做过一次过滤）
        if await self._db_paper_exists(paper_url):
            print(f"  [线程{self.thread_id}] 数据库中已存在，跳过")
            return {'error': 'already_exists'}

        print(f"  [线程{self.thread_id}] 获取论文详情: {paper_info['title'][:50]}...")

        # 详情页抓取：goto + 等标题元素出现（事件驱动），网络/解析失败退避重试
        html = None
        for attempt in range(DETAIL_MAX_RETRIES + 1):
            try:
                await _pacing_wait()
                await page.goto(paper_url, wait_until='domcontentloaded', timeout=60000)

                if not await self.wait_for_page_stable(paper_url, page=page):
                    return {'error': 'verify_page'}

                await self.random_scroll(page=page)
                try:
                    await page.wait_for_selector('div.doc h1, h1', timeout=20000)
                except Exception:
                    pass
                await asyncio.sleep(random.uniform(MIN_DETAIL_DELAY, MAX_DETAIL_DELAY))

                html = await page.content()
                break
            except Exception as e:
                if attempt < DETAIL_MAX_RETRIES:
                    backoff = DETAIL_RETRY_BACKOFF[min(attempt, len(DETAIL_RETRY_BACKOFF) - 1)]
                    print(f"    [线程{self.thread_id}] 详情页加载失败（{e}），{backoff}s 后重试 ({attempt + 1}/{DETAIL_MAX_RETRIES})")
                    await asyncio.sleep(backoff)
                else:
                    print(f"    [线程{self.thread_id}] ✗ 获取失败: {e}")
                    return {'error': str(e)}

        try:
            soup = BeautifulSoup(html, 'lxml')

            title = ''
            title_elem = soup.find('div', class_='doc')
            if title_elem:
                h1 = title_elem.find('h1')
                if h1:
                    title = h1.get_text(strip=True)
            if not title:
                h1_elem = soup.find('h1')
                if h1_elem:
                    title = h1_elem.get_text(strip=True)

            skip_keywords = [
                '征稿启事', '征稿', '征文', '征订', '稿约', '投稿须知', '投稿指南',
                '总目录', '目录', '索引', '内容提要',
                '编辑部公告', '编辑部关于', '编辑部声明', '公告', '声明', '启事', '通知', '更正', '勘误', '补遗',
                '书评', '评介', '学院简介', '中心简介', '新书介绍', '新书评介',
                '会议纪要', '会议综述', '会议报道', '会议简报',
                '新闻', '消息', '简讯', '报道',
                '广告', '致谢名单', '致谢专家', '鸣谢',
                '卷首语', '编者按', '导读', '操作指南', '使用指南', '手册',
                '人才招聘', '全球人才招聘', '招生', '培训', '课程', '讲座',
                '版权声明', '著作权', '授权声明',
                '欢迎订阅', '订阅杂志', '订购', '欢迎购买',
            ]
            if any(keyword in title for keyword in skip_keywords):
                print(f"    [线程{self.thread_id}] ✗ 跳过非论文条目: {title[:40]}...")
                return {'error': 'filtered_non_paper'}

            title = title.replace('附视频', '').strip()

            authors = []
            author_elem = soup.find('h3', class_='author')
            if author_elem:
                author_links = author_elem.find_all('a')
                for link in author_links:
                    author_name = link.get_text(strip=True)
                    author_name = re.sub(r'\d+', '', author_name).strip()
                    author_name = re.sub(r'[\w.+-]+@[\w.+-]+', '', author_name).strip()
                    author_name = re.sub(r'@\.com', '', author_name).strip()
                    author_name = author_name.strip().rstrip(',').rstrip('，').strip()
                    author_name = re.sub(r'\s+', '', author_name)
                    if not author_name or len(author_name) < 2:
                        continue
                    if not re.search(r'[\u4e00-\u9fff]', author_name):
                        continue
                    if re.search(r'[@\d]', author_name):
                        continue
                    authors.append(author_name)

            abstract = ''
            abstract_elem = soup.find('span', class_='abstract-text')
            if abstract_elem:
                abstract = abstract_elem.get_text(strip=True)

            keywords = []
            keywords_elem = soup.find('p', class_='keywords')
            if keywords_elem:
                keywords_text = keywords_elem.get_text(strip=True)
                keywords_text = keywords_text.replace('关键词：', '').replace('关键词:', '')
                keywords = [k.strip() for k in keywords_text.split(';') if k.strip()]

            meta = {}
            row_divs = soup.find_all('div', class_='row')
            for row in row_divs:
                ul = row.find('ul')
                if ul:
                    for li in ul.find_all('li', class_='top-space'):
                        label_elem = li.find('span', class_='rowtit')
                        value_elem = li.find('p')
                        if label_elem and value_elem:
                            label = label_elem.get_text(strip=True).replace('：', '').replace(':', '')
                            value = value_elem.get_text(strip=True)
                            if label == 'DOI':
                                meta['doi'] = value
                            elif label == '专辑':
                                meta['album'] = value
                            elif label == '专题':
                                meta['subject'] = value
                            elif label == '分类号':
                                meta['classification'] = value
                            elif '在线公开时间' in label:
                                meta['online_date'] = value.split('（')[0].strip()

            result = {
                'title': title,
                'authors': authors,
                'abstract': abstract,
                'keywords': keywords,
                'url': paper_url,
                'journal': paper_info.get('journal', ''),
                **meta
            }

            if title:
                print(f"    [线程{self.thread_id}] ✓ 成功获取: {title[:40]}...")
                await self.save_to_database(result, journal_name, year, issue)
                # --detail-refs：详情入库后顺带抓参考文献（失败只记日志，不回滚详情）
                if self.refs_with_details:
                    await self._fetch_refs_for_detail(paper_url, title)
                return result
            else:
                print(f"    [线程{self.thread_id}] ✗ 获取失败: 无标题")
                return {'error': 'no_title'}

        except Exception as e:
            print(f"    [线程{self.thread_id}] ✗ 获取失败: {e}")
            return {'error': str(e)}

    async def _ensure_db(self):
        """确保数据库文件存在并初始化表结构（首次运行自动建库）。"""
        if self.db_initialized:
            return
        from app.database import init_db
        db_file = BACKEND_DIR / 'data' / 'paperpulse.db'
        # SQLite 不会自动创建父目录：先确保 backend/data/ 存在，
        # 否则 init_db() 报 unable to open database file
        db_file.parent.mkdir(parents=True, exist_ok=True)
        if not db_file.exists():
            print(f"    [线程{self.thread_id}] 数据库文件不存在，正在创建...")
            await init_db()
            print(f"    [线程{self.thread_id}] ✓ 数据库已创建")
        self.db_initialized = True

    async def _db_paper_exists(self, paper_url: str) -> bool:
        """按 URL 判断论文是否已在库中。"""
        try:
            from app.crud import PaperCRUD
            from app.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                return (await PaperCRUD.get_paper_by_url(db, paper_url)) is not None
        except Exception:
            return False

    async def _db_existing_urls(self) -> set:
        """批量获取库中全部论文 URL（详情阶段开始时调用一次，避免逐篇 roundtrip）。"""
        try:
            from app.crud import PaperCRUD
            from app.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                return set(await PaperCRUD.get_all_paper_urls(db))
        except Exception as e:
            print(f"  [线程{self.thread_id}] 获取数据库已有论文失败: {e}")
            return set()

    async def _create_crawl_log(self, journal_name: str) -> Optional[int]:
        """创建爬取日志，返回 crawl_log_id。"""
        try:
            from app.schemas import CrawlLogCreate
            from app.crud import CrawlLogCRUD
            from app.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                crawl_log = await CrawlLogCRUD.create_crawl_log(
                    db, CrawlLogCreate(journal_name=journal_name, crawl_start_time=datetime.now())
                )
                await db.commit()
                return crawl_log.id
        except Exception as e:
            print(f"  [线程{self.thread_id}] 创建爬取日志失败: {e}")
            return None

    async def _update_crawl_log(self, crawl_log_id: Optional[int], **fields):
        """更新爬取日志（成功/失败均走这里）。"""
        if not crawl_log_id:
            return
        try:
            from app.crud import CrawlLogCRUD
            from app.database import AsyncSessionLocal
            async with AsyncSessionLocal() as db:
                await CrawlLogCRUD.update_crawl_log(db, crawl_log_id, **fields)
                await db.commit()
        except Exception as e:
            print(f"  [线程{self.thread_id}] 更新爬取日志失败: {e}")

    async def save_to_database(self, paper_data: dict, journal_name: str = None, year: str = None, issue: str = None):
        """异步保存到数据库"""
        # 多 worker 并发写库会撞 SQLite 写锁：实例级锁串行化写操作
        if not hasattr(self, "_db_lock"):
            self._db_lock = asyncio.Lock()
        async with self._db_lock:
            try:
                import re
                await self._ensure_db()

                from app.crud import PaperCRUD
                from app.database import AsyncSessionLocal

                async with AsyncSessionLocal() as db:
                    existing = await PaperCRUD.get_paper_by_url(db, paper_data['url'])
                    if existing:
                        print(f"    [线程{self.thread_id}] 数据库中已存在，跳过")
                        return

                    if journal_name:
                        paper_data['journal_name'] = journal_name
                    elif paper_data.get('journal'):
                        paper_data['journal_name'] = paper_data.pop('journal')

                    if year and issue:
                        paper_data['journal_issue'] = f"{year}年第{issue}期"

                    doi = paper_data.get('doi', '')
                    if doi:
                        match = re.search(r'\.(\d{4})\.', doi)
                        if match:
                            paper_data['year'] = int(match.group(1))

                    paper = await PaperCRUD.create_paper_from_cnki(db, paper_data)
                    if paper:
                        await db.commit()
                        print(f"    [线程{self.thread_id}] ✓ 已保存到数据库")
            except Exception as e:
                print(f"    [线程{self.thread_id}] ✗ 保存到数据库失败: {e}")
                import traceback
                traceback.print_exc()

    # —— 参考文献抓取（详情流程 --detail-refs 与独立参考文献模式共用）——
    REF_LIST_SELECTOR = 'ul.ebBd'
    REF_NEXT_SELECTOR = 'a.next'
    # 「参考文献」页签：先点击（onclick=changeRefTypeTag）列表才渲染，按优先级逐个尝试
    REF_TAB_SELECTORS = [
        'li[data-id="references"]',
        'li[onclick*="changeRefTypeTag"]',
        'li:text-is("参考文献")',
        'a:text-is("参考文献")',
    ]
    # 防风控节奏（参考文献抓取专用，默认偏保守）
    REF_PAGE_INTERVAL = (2.0, 4.5)   # 每次翻页前的随机间隔（秒）
    REF_TAB_WAIT = 15                # 点击页签后等待 ul.ebBd 渲染的超时（秒）

    async def _fetch_refs_for_detail(self, paper_url: str, title: str):
        """--detail-refs：详情入库后在同一页顺带抓参考文献；任何失败只记日志不回滚详情。"""
        tag = f"[线程{self.thread_id}]"
        try:
            refs = await self._crawl_references(tag)
            if not refs:
                print(f"    {tag} 该详情页未抓到参考文献条目，跳过")
                return
            if self.max_items and len(refs) > self.max_items:
                refs = refs[:self.max_items]
            await self._save_references(paper_url, title, refs)
            self._refs_done = getattr(self, '_refs_done', 0) + 1
        except Exception as e:
            print(f"    {tag} ✗ 参考文献抓取失败（不影响已入库详情）: {e}")
            self._refs_failed = getattr(self, '_refs_failed', 0) + 1

    async def _open_references_tab(self, tag: str):
        """点击详情页「参考文献」页签（li[data-id="references"]，onclick=changeRefTypeTag）。

        列表在点击页签后才异步渲染；按优先级逐个尝试选择器，普通点击失败时
        用 JS click 兜底（onclick 绑定在 li 上，JS 触发同样生效），点击后等待
        ul.ebBd 渲染出来再返回。
        """
        for sel in self.REF_TAB_SELECTORS:
            loc = self.page.locator(sel).first
            if await loc.count() == 0:
                continue
            try:
                await loc.scroll_into_view_if_needed(timeout=3000)
            except Exception:
                pass
            try:
                await loc.click(timeout=5000)
            except Exception:
                try:
                    await loc.evaluate('el => el.click()')
                except Exception as e:
                    print(f"{tag} 点击页签 {sel} 失败: {e}")
                    continue
            print(f"{tag} 已点击「参考文献」页签: {sel}")
            # 列表多为滚动到可视区域才懒加载渲染：点完页签把文献区滚进视口，边滚边等 ul.ebBd 出现
            deadline = asyncio.get_event_loop().time() + self.REF_TAB_WAIT
            while asyncio.get_event_loop().time() < deadline:
                if await self.page.locator(self.REF_LIST_SELECTOR).count() > 0:
                    break
                try:
                    await loc.scroll_into_view_if_needed(timeout=2000)
                except Exception:
                    pass
                try:
                    await self.page.evaluate('window.scrollBy(0, 320)')
                except Exception:
                    pass
                await asyncio.sleep(random.uniform(0.4, 0.8))
            try:
                await self.page.locator(self.REF_LIST_SELECTOR).first.wait_for(
                    state='visible', timeout=3000)
            except Exception:
                print(f"{tag} 点击页签并滚动后仍未见到 ul.ebBd，继续尝试直接解析")
            return True
        print(f"{tag} 未找到「参考文献」页签，尝试直接解析列表")
        return False

    async def _crawl_references(self, tag: str) -> list:
        """抓取参考文献条目：ul.ebBd 下每页 li，a.next 翻页，按钮消失即末页。"""
        refs: list = []
        seen = set()
        page_no = 1
        while True:
            # 需求确认：先点击「参考文献」页签（changeRefTypeTag）列表才渲染，每篇开始必点
            if page_no == 1:
                await self._open_references_tab(tag)
            loc = self.page.locator(self.REF_LIST_SELECTOR)
            if await loc.count() == 0:
                print(f"{tag} 第 {page_no} 页未找到参考文献容器 ul.ebBd（可加 --show-browser 人工核对页面）")
                break
            # 懒加载：把列表滚进视口再取（翻页后的新条目同样需要滚到可见才渲染）
            try:
                await loc.first.scroll_into_view_if_needed(timeout=3000)
            except Exception:
                pass
            items = await loc.locator('xpath=./li').evaluate_all(
                """(lis) => lis.map((li) => {
                    const a = li.querySelector('a[href]');
                    const text = (li.innerText || '').replace(/\\s+/g, ' ').trim();
                    return { text, url: a ? a.href : null };
                }).filter((x) => x.text)"""
            )
            # 跨页去重：翻页未生效时重复收集的同一页内容会被去重掉，不会重复入库
            new_count = 0
            for it in items:
                key = (it.get('url') or '', it['text'])
                if key in seen:
                    continue
                seen.add(key)
                refs.append(it)
                new_count += 1
            print(f"{tag} 参考文献 第 {page_no} 页获取 {len(items)} 条（新增 {new_count}），累计 {len(refs)} 条")
            if self.max_items and len(refs) >= self.max_items:
                print(f"{tag} 已达上限 {self.max_items} 条，停止翻页")
                break
            # 「下一页」按钮：不存在即末页（需求）；置灰(disable)同样视为末页
            nxt = self.page.locator(self.REF_NEXT_SELECTOR).first
            if await nxt.count() == 0:
                print(f"{tag} 「下一页」按钮已消失，参考文献抓取完成")
                break
            cls = (await nxt.get_attribute('class')) or ''
            if 'disable' in cls:
                print(f"{tag} 「下一页」按钮已置灰，已是末页，参考文献抓取完成")
                break
            first_before = items[0]['text'][:60] if items else ''
            # 翻页请求同样计入风控：先随机停顿，再过全局导航闸
            await asyncio.sleep(random.uniform(*self.REF_PAGE_INTERVAL))
            await _pacing_wait()
            try:
                await nxt.click(timeout=8000)
            except Exception as e:
                print(f"{tag} 点击下一页失败: {e}")
                break
            # 等翻页真正生效：列表重新可见且首条内容变化（最多约 20s），防点击未生效导致死循环
            advanced = False
            deadline = asyncio.get_event_loop().time() + 20
            while asyncio.get_event_loop().time() < deadline:
                try:
                    await self.page.locator(self.REF_LIST_SELECTOR).first.wait_for(state='visible', timeout=5000)
                except Exception:
                    pass
                cur_first = await self._first_ref_text()
                if cur_first and cur_first != first_before:
                    advanced = True
                    break
                if await self.page.locator(self.REF_LIST_SELECTOR).count() == 0:
                    break
                await asyncio.sleep(0.8)
            if not advanced:
                print(f"{tag} 点击下一页后列表内容未变化，视为已到末页，停止")
                break
            page_no += 1
        return refs

    async def _first_ref_text(self) -> str:
        """读取当前参考文献列表首条文本（用于判断翻页是否生效）。"""
        try:
            loc = self.page.locator(f'{self.REF_LIST_SELECTOR} > li').first
            text = await loc.inner_text(timeout=3000)
            return (text or '').replace('\n', ' ').strip()[:60]
        except Exception:
            return ''

    async def _save_references(self, paper_url: str, paper_title: str, refs: list):
        """覆盖式写入论文行的 references_cn JSON（[{index, text, url}]）。

        知网 kcms2 URL 的 v 令牌随入口变化：先按 URL 精确更新，未命中再按标题更新；
        论文不在库中则明确提示（参考文献随论文行存储，未入库无处挂载）。
        """
        payload = json.dumps(
            [{"index": i, "text": (r.get('text') or '')[:2000], "url": r.get('url')}
             for i, r in enumerate(refs, start=1)],
            ensure_ascii=False)
        if not hasattr(self, "_db_lock"):
            self._db_lock = asyncio.Lock()
        async with self._db_lock:
            try:
                await self._ensure_db()
                from sqlalchemy import update
                from app.models import Paper
                from app.database import AsyncSessionLocal
                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        update(Paper).where(Paper.url == paper_url).values(references_cn=payload))
                    if result.rowcount == 0 and (paper_title or '').strip():
                        result = await db.execute(
                            update(Paper).where(Paper.title == paper_title.strip()).values(references_cn=payload))
                    await db.commit()
                    if result.rowcount:
                        print(f"    [线程{self.thread_id}] ✓ 参考文献已写入论文 {len(refs)} 条 -> {(paper_title or paper_url)[:60]}")
                    else:
                        print(f"    [线程{self.thread_id}] ⚠ 该论文不在库中，参考文献未保存（可先入库再抓取）: {(paper_title or paper_url)[:60]}")
            except Exception as e:
                print(f"    [线程{self.thread_id}] ✗ 参考文献写入失败: {e}")
                import traceback
                traceback.print_exc()

    async def fetch_journals(self) -> dict:
        """获取期刊列表（复用共享浏览器的主页面，不再单独开浏览器）。"""
        print("=" * 60)
        print("步骤1-3: 获取期刊列表")
        print("=" * 60)

        if HistoryManager.is_journals_cache_valid():
            print("发现有效的期刊历史记录，直接复用")
            history = HistoryManager.load_journals_history()
            return history['journals']

        print("未找到有效的期刊历史记录，开始爬取...")

        page = self.page
        try:
            print("访问期刊导航页...")
            await _pacing_wait()
            await page.goto(f'{BASE_URL}/knavi/journals/index', wait_until='domcontentloaded', timeout=60000)

            print("点击'经济与管理科学'按钮...")
            try:
                # 尝试多种选择器
                selectors = [
                    'a[title="经济与管理科学"]',
                    'a:has-text("经济与管理科学")',
                    'a:text("经济与管理科学")',
                ]
                btn = None
                for selector in selectors:
                    try:
                        btn = await page.wait_for_selector(selector, timeout=5000)
                        if btn:
                            print(f"  使用选择器找到按钮: {selector}")
                            break
                    except:
                        continue

                if btn:
                    await btn.click()
                else:
                    print("  未找到按钮，尝试通过文本查找...")
                    # 通过页面文本查找
                    elements = await page.query_selector_all('a')
                    for elem in elements:
                        text = await elem.text_content()
                        if text and '经济与管理科学' in text:
                            await elem.click()
                            print("  通过文本内容找到并点击")
                            break
                # 事件驱动：等期刊列表容器出现，替代固定 5s
                try:
                    await page.wait_for_selector('div.result, div.resultList, #gridTable', timeout=PAGE_STABLE_TIMEOUT * 1000)
                except Exception:
                    print("  等待期刊列表容器超时，继续尝试解析")
                await asyncio.sleep(random.uniform(MIN_DETAIL_DELAY, MAX_DETAIL_DELAY))
            except Exception as e:
                print(f"点击按钮失败: {e}")

            html = await page.content()
            soup = BeautifulSoup(html, 'lxml')

            result_div = soup.find('div', class_='result')
            if not result_div:
                # 尝试其他选择器
                result_div = soup.find('div', class_='resultList')
                if not result_div:
                    result_div = soup.find('div', id='gridTable')
            if not result_div:
                print("未找到期刊列表容器")
                print("页面标题:", await page.title())
                print("当前URL:", page.url)
                # 保存页面HTML用于调试
                debug_file = BACKEND_DIR / 'data' / 'debug_journals.html'
                with open(debug_file, 'w', encoding='utf-8') as f:
                    f.write(html)
                print(f"已保存页面HTML到: {debug_file}")
                return {}

            journals = {}
            links = result_div.find_all('a')
            for link in links:
                full_title = link.get_text(strip=True)
                href = link.get('href', '')
                if full_title and href:
                    if href.startswith('/'):
                        href = urljoin(BASE_URL, href)

                    match = re.match(r'(.+?)(?:网络首发|复合影响因子|$)', full_title)
                    if match:
                        clean_title = match.group(1).strip()
                    else:
                        clean_title = full_title

                    impact_factor = {}
                    if '复合影响因子：' in full_title:
                        match = re.search(r'复合影响因子：([\d.]+)', full_title)
                        if match:
                            impact_factor['composite'] = float(match.group(1))
                    if '综合影响因子：' in full_title:
                        match = re.search(r'综合影响因子：([\d.]+)', full_title)
                        if match:
                            impact_factor['comprehensive'] = float(match.group(1))

                    journals[clean_title] = {
                        'url': href,
                        'impact_factor': impact_factor,
                        'original_title': full_title
                    }

            print(f"获取到 {len(journals)} 个期刊")
            HistoryManager.save_journals_history(journals)

            return journals

        except Exception as e:
            print(f"爬取期刊列表失败: {e}")
            import traceback
            traceback.print_exc()
            return {}

    async def fetch_details_concurrent(self, workers: int, collected_journals: list):
        """集中并发抓详情入库（单浏览器 + N 个 worker tab）。

        collected_journals: [{'name': str, 'log_id': int|None, 'count': int}, ...]
        论文清单从 HistoryManager 读取（收集阶段已写入），并对库中已有 URL 批量去重。
        """
        if not collected_journals:
            return
        tag = f"[线程{self.thread_id}]"
        journal_names = [j['name'] for j in collected_journals]
        log_by_name = {j['name']: j['log_id'] for j in collected_journals}

        # 从 HistoryManager 摊平出 (journal, year, issue, paper) 任务
        history = HistoryManager.load_papers_history()
        tasks = []
        per_journal_total = {jn: 0 for jn in journal_names}
        for jn in journal_names:
            jdata = history.get('papers', {}).get(jn, {})
            for year in sorted(jdata.keys(), reverse=True):
                for issue in sorted(jdata[year].keys(), reverse=True):
                    for p in jdata[year][issue].get('papers', []):
                        tasks.append((jn, year, issue, p))
                        per_journal_total[jn] += 1

        print(f"\n{tag} 共收集 {len(tasks)} 篇待处理论文，预取数据库已有 URL ...")
        existing_urls = await self._db_existing_urls()
        print(f"{tag} 数据库中已有 {len(existing_urls)} 篇论文")

        queue = asyncio.Queue()
        skipped = 0
        for jn, year, issue, p in tasks:
            if p.get('url') in existing_urls:
                skipped += 1
                continue
            queue.put_nowait((jn, year, issue, p))
        print(f"{tag} 已在库跳过 {skipped} 篇，待抓 {queue.qsize()} 篇")

        total = queue.qsize()
        done = ok = 0
        stats = {'already_exists': skipped, 'filtered': 0, 'verify_failed': 0, 'failed': 0}
        per_journal_ok = {jn: 0 for jn in journal_names}

        async def detail_worker(wid: int):
            nonlocal done, ok
            wtag = f"{tag}[W{wid}]"
            page = await self.context.new_page()
            try:
                while True:
                    try:
                        jn, year, issue, paper = queue.get_nowait()
                    except asyncio.QueueEmpty:
                        return
                    done += 1
                    print(f"{wtag} [{done}/{total}] 处理: {paper['title'][:30]}...")
                    res = await self.crawl_paper_detail(paper, jn, year, issue, page=page)
                    if res and res.get('title'):
                        ok += 1
                        per_journal_ok[jn] += 1
                    else:
                        reason = res.get('error', 'failed') if res else 'failed'
                        if reason == 'already_exists':
                            stats['already_exists'] += 1
                        elif reason == 'verify_page':
                            stats['verify_failed'] += 1
                        elif reason == 'filtered_non_paper':
                            stats['filtered'] += 1
                        else:
                            stats['failed'] += 1
                    await asyncio.sleep(random.uniform(0.5, 1.5))
            finally:
                try:
                    await page.close()
                except Exception:
                    pass

        n = max(1, workers)
        print(f"{tag} 详情并发数: {n}")
        await asyncio.gather(*[detail_worker(i) for i in range(n)])

        # 汇总输出（按原因统计，便于定位问题）
        print(f"\n{tag} {'=' * 60}")
        print(f"{tag} 完成：成功 {ok}/{total} 篇 | 已在库 {stats['already_exists']} | "
              f"被过滤 {stats['filtered']} | 验证码未过 {stats['verify_failed']} | 失败 {stats['failed']}")
        if getattr(self, '_refs_done', 0) or getattr(self, '_refs_failed', 0):
            print(f"{tag} 参考文献（--detail-refs）：成功 {getattr(self, '_refs_done', 0)} 篇 | "
                  f"失败 {getattr(self, '_refs_failed', 0)} 篇")
        print(f"{tag} {'=' * 60}")

        # 更新各期刊爬取日志
        for jn in journal_names:
            ok_j = per_journal_ok[jn]
            total_j = per_journal_total[jn]
            await self._update_crawl_log(
                log_by_name.get(jn),
                crawl_end_time=datetime.now(),
                papers_fetched=ok_j,
                papers_failed=total_j - ok_j,
                status="completed",
            )


class JournalCollector:
    """期刊链接收集器：一个浏览器负责一批期刊，并行收集论文链接写入 HistoryManager。"""

    def __init__(self, headless: bool, thread_id: int, journals: list, state_file: Optional[Path]):
        self.crawler = JournalCrawler(headless=headless, thread_id=thread_id, state_file=state_file)
        self.journals = journals
        self.results: list = []  # [{'name','log_id','count'}, ...]

    async def run(self):
        tag = f"[收集器{self.crawler.thread_id}]"
        await self.crawler.init_browser()
        try:
            await self.crawler._warmup()
            total = len(self.journals)
            for i, (journal_name, journal_info) in enumerate(self.journals, 1):
                print(f"\n{tag} [{i}/{total}] 收集期刊: {journal_name}")
                try:
                    papers = await self.crawler.crawl_papers_for_journal(journal_name, journal_info)
                    crawl_log_id = await self.crawler._create_crawl_log(journal_name)
                    self.results.append({
                        'name': journal_name,
                        'log_id': crawl_log_id,
                        'count': len(papers),
                    })
                    print(f"{tag} [{i}/{total}] 期刊 {journal_name} 共收集 {len(papers)} 篇论文")
                except Exception as e:
                    print(f"{tag} 收集期刊 {journal_name} 出错: {e}")
                    import traceback
                    traceback.print_exc()
                    # 单期刊失败不阻塞其他期刊（继续下一批）
        finally:
            await self.crawler.save_storage_state()
            await self.crawler.close_browser()


class MultiThreadedCrawler:
    """期刊模式爬虫管理器。

    阶段一（收集）：N 个浏览器（--threads）并行收集各期刊论文链接；
    阶段二（详情）：单浏览器 + M 个 worker tab（--detail-workers）并发抓详情入库。
    两个阶段共享全局导航闸/熔断，避免聚合请求率过高触发验证码。
    """

    def __init__(self, headless=True, max_workers=3, detail_workers=3,
                 refs_with_details=False, ref_max_items=None):
        self.headless = headless
        self.max_workers = max(1, int(max_workers))
        self.detail_workers = max(1, int(detail_workers))
        self.refs_with_details = refs_with_details
        self.ref_max_items = ref_max_items

    async def run(self):
        """运行期刊爬虫（收集并行 -> 详情并发）。"""
        print("=" * 60)
        print(f"知网期刊爬虫 - 验证码自动解决版本")
        print(f"收集并发浏览器数: {self.max_workers} | 详情并发 tab 数: {self.detail_workers}")
        print(f"全局导航间隔: {PACING_BASE_INTERVAL}s（熔断上限 {PACING_MAX_INTERVAL}s）")
        print(f"浏览器模式: {'无头' if self.headless else '显示窗口'}")
        if DDDDOCR_AVAILABLE:
            print("验证码解决: ddddocr 已启用")
        else:
            print("验证码解决: ddddocr 未安装，将使用手动模式")
        print("=" * 60)

        # 步骤0：单个浏览器获取期刊列表（复用暖会话）
        listing = JournalCrawler(headless=self.headless, thread_id=0, state_file=CNKI_STATE_FILE)
        await listing.init_browser()
        try:
            journals = await listing.fetch_journals()
        finally:
            await listing.save_storage_state()
            await listing.close_browser()
        if not journals:
            print("未获取到期刊列表，退出")
            return

        journal_list = list(journals.items())
        print(f"\n共 {len(journal_list)} 个期刊需要处理")

        # 阶段一：N 个浏览器并行收集（每个浏览器独立会话态文件，避免共享 cookie）
        n = self.max_workers
        slices = [journal_list[i::n] for i in range(n)]
        slices = [s for s in slices if s]
        collectors = [
            JournalCollector(self.headless, i + 1, sl, _collect_state_file(i))
            for i, sl in enumerate(slices)
        ]
        print(f"使用 {len(collectors)} 个收集浏览器并行处理\n")
        await asyncio.gather(*[c.run() for c in collectors])

        collected_journals = [item for c in collectors for item in c.results]
        print(f"\n共收集 {len(collected_journals)} 个期刊的论文链接")

        # 阶段二：单浏览器 + M tab 并发抓详情入库（复用收集阶段保存的暖会话）
        detail = JournalCrawler(headless=self.headless, thread_id=0, state_file=CNKI_STATE_FILE,
                                refs_with_details=self.refs_with_details,
                                ref_max_items=self.ref_max_items)
        await detail.init_browser()
        try:
            await detail._warmup()
            await detail.fetch_details_concurrent(self.detail_workers, collected_journals)
        finally:
            await detail.save_storage_state()
            await detail.close_browser()

        print("\n" + "=" * 60)
        print("所有期刊处理完成")
        print("=" * 60)


class KeywordSearchCrawler(JournalCrawler):
    """按关键词/主题检索知网论文（结合关键词检索流程与主脚本的验证码/入库能力）。

    复用父类：CaptchaSolver 自动解验证码、wait_for_page_stable、
    random_scroll、crawl_paper_detail / save_to_database（去重入库）。
    新增：登录态复用(storage_state)、检索入口、主要主题/学术期刊筛选、翻页。

    用法:
        python cnki_paper_captcha.py --search "新质生产力" --show-browser
        python cnki_paper_captcha.py --search "新质生产力" --max-pages 3 --years 2025-2026
    """

    VERIFY_MARK = "/verify"
    # CNKI 检索页 XPath 选择器
    SEARCH_SELECTOR = '//textarea[@id="txt_SearchText"]'
    # 检索字段下拉：现行首页/检索页（参考 demo.py）
    FIELD_SORT_DEFAULT_SELECTOR = '//div[contains(@class, "sort-default")]'
    FIELD_LIST_SELECTOR = '//div[@id="DBFieldList"]'
    FIELD_LI_SELECTOR = '//div[@id="DBFieldList"]//li'
    # 旧版检索字段下拉（兜底）
    FIELD_SELECTOR = '//dd[@id="searchField"]'
    # 侧边栏筛选容器（搜索结果页左侧分组：主题/学科/年度/研究层次/期刊/文献来源/来源类别/作者/机构/基金/OA出版）
    GROUP_CONTAINER_SELECTOR = '//div[@id="divGroup"]'
    RESULT_TABLE_SELECTOR = '//table[contains(@class, "result-table-list")]'
    NEXT_PAGE_SELECTOR = '//a[@id="PageNext"]'
    TITLE_LINK_SELECTOR = './/a[contains(@class, "fz14")]'
    ROW_LINK_SELECTOR = './/td[1]//a'
    # 验证码弹窗/遮罩检测（不改变 URL 时的滑块 iframe 等，选择器需精确，避免误命中结果页普通元素）
    # 主判据是 URL 是否含 /verify（见 _ensure_no_captcha），此处仅做严格辅助
    CAPTCHA_POPUP_SELECTORS = [
        '//iframe[contains(@src,"captcha") or contains(@src,"verify") or contains(@src,"nc_") or contains(@src,"yidun")]',
        '//div[contains(@class,"verify-slide") or contains(@class,"verify-slider")]',
        '//div[contains(@class,"nc-container") or contains(@class,"yidun")]',
        '//div[@id="captcha"]',
    ]

    def __init__(self, headless=True, keyword="", search_field="主题", max_pages=None,
                 min_year=None, max_year=None, state_file=None, thread_id=0,
                 urls_only=False, urls_file=None, debug_html=None,
                 search_url=None, search_url_file=None, detail_workers=3,
                 resume=False, refs_with_details=False, ref_max_items=None):
        super().__init__(headless=headless, thread_id=thread_id,
                         refs_with_details=refs_with_details, ref_max_items=ref_max_items)
        self.keyword = keyword
        self.search_field = search_field
        self.max_pages = max_pages
        self.min_year = min_year
        self.max_year = max_year
        self.state_file = Path(state_file) if state_file else None
        # 断点续跑：同关键词存在断点时从上次进度继续（详情阶段靠 URL 去重跳过已入库）
        self.resume = resume
        # 只收集 URL 模式（不抓详情入库），并保存到 urls_file
        self.urls_only = urls_only
        self.urls_file = Path(urls_file) if urls_file else CACHE_DIR / 'urls.txt'
        self.search_url = search_url
        # 保存/复用检索结果页 URL（供 --search-url 直接跳转，跳过首页重复检索）
        self.search_url_file = Path(search_url_file) if search_url_file else CACHE_DIR / 'search_url.txt'
        self.debug_html = Path(debug_html) if debug_html else CACHE_DIR / 'debug_page1.html'

        # 详情页并发抓取数（翻页收集仍串行）
        self.detail_workers = max(1, int(detail_workers))
        self.context = None  # init_browser 时保存，供详情并发阶段开 worker tab

    async def init_browser(self):
        """初始化浏览器（支持复用已保存的登录态）。"""
        self.playwright = await async_playwright().start()
        launch_kwargs = _launch_kwargs(self.headless)
        self.browser = await self.playwright.chromium.launch(**launch_kwargs)

        ctx_kwargs = {
            'locale': 'zh-CN',
            'timezone_id': 'Asia/Shanghai',
        }
        if self.state_file and self.state_file.exists():
            ctx_kwargs['storage_state'] = str(self.state_file)
            print(f"  [关键词#{self.thread_id}] 复用登录态: {self.state_file}")

        self.context = await self.browser.new_context(**ctx_kwargs)
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1,2,3,4,5] });
            Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN','zh','en'] });
            window.chrome = { runtime: {} };
        """)
        self.page = await self.context.new_page()
        print(f"  [关键词#{self.thread_id}] 浏览器已启动 (headless={self.headless})")

    async def _fast_forward(self, target_page: int) -> int:
        """断点恢复：从结果页第 1 页连续点「下一页」直达 target_page，返回实际到达的页码。

        知网结果页翻页为 AJAX（URL 不变），只能逐页点击前进；站点结构变化导致
        无法到达目标页时提前停在上 reach 到的页（重复收集的论文由入库去重兜底）。
        """
        cur = await self._current_page_num() or 1
        while cur < target_page:
            if not await self._next_page_exists():
                print(f"  [关键词#{self.thread_id}] 快进翻页时已是末页（第 {cur} 页），停止快进")
                break
            await self._wait_loading_gone()
            await _pacing_wait()
            prev = cur
            try:
                await self.page.locator(self.NEXT_PAGE_SELECTOR).first.evaluate('el => el.click()')
            except Exception:
                try:
                    await self.page.locator(self.NEXT_PAGE_SELECTOR).first.click(force=True, timeout=10000)
                except Exception:
                    pass
            await self._ensure_no_captcha(timeout=120)
            advanced = False
            deadline = asyncio.get_event_loop().time() + 20
            while asyncio.get_event_loop().time() < deadline:
                await self._wait_loading_gone(timeout=5000)
                try:
                    await self.page.locator(self.RESULT_TABLE_SELECTOR).first.wait_for(state='visible', timeout=3000)
                except Exception:
                    continue
                new_cur = await self._current_page_num()
                if new_cur is not None and new_cur > prev:
                    cur = new_cur
                    advanced = True
                    break
                if not await self._next_page_exists():
                    break
                await asyncio.sleep(0.5)
            if not advanced:
                break
        return cur

    async def _captcha_popup_visible(self) -> bool:
        """检测不改变 URL 的验证码弹窗/遮罩。"""
        for sel in self.CAPTCHA_POPUP_SELECTORS:
            try:
                loc = self.page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    return True
            except Exception:
                continue
        return False

    async def _ensure_no_captcha(self, timeout: int = 180) -> bool:
        """确保当前无安全验证：优先自动解（滑块/点选），失败则提示手动（非无头）。"""
        start = asyncio.get_event_loop().time()
        prompted = False
        while True:
            url_verify = self.VERIFY_MARK in self.page.url
            popup = await self._captcha_popup_visible()
            if not url_verify and not popup:
                if prompted:
                    print(f"  [关键词#{self.thread_id}] ✓ 安全验证已通过")
                return True
            if asyncio.get_event_loop().time() - start > timeout:
                print(f"  [关键词#{self.thread_id}] 等待安全验证超时")
                _report_captcha(tag=f"[关键词#{self.thread_id}]")
                return False
            # 优先尝试自动解决（仅首次）
            if not prompted and self.captcha_solver.is_available():
                try:
                    ctype = await self.captcha_solver.detect_captcha_type(self.page)
                    ok = False
                    if ctype == 'slider':
                        ok = await self.captcha_solver.solve_slider_captcha(self.page)
                    elif ctype == 'click':
                        ok = await self.captcha_solver.solve_click_captcha(self.page)
                    if ok:
                        continue
                except Exception:
                    pass
            if not prompted and not self.headless:
                print(f"  [关键词#{self.thread_id}] 请在浏览器中手动完成安全验证/滑块...")
                prompted = True
            await asyncio.sleep(1.5)

    async def _pick_field_filter(self) -> bool:
        """按检索字段在侧边栏筛选(div#divGroup)中做分组匹配并点选。

        检索字段 → 分组：主题→「主题」，作者/第一作者/通讯作者→「作者」，
        作者单位→「机构」，基金→「基金」，文献来源→「文献来源」，分类号→「学科」。
        在对应分组里选出与关键词最匹配的一项并点击；无匹配或无需筛选返回 False。
        """
        tag = f"[关键词#{self.thread_id}]"
        target = SEARCH_FIELD_GROUP_MAP.get((self.search_field or '').strip())
        if not target:
            print(f"{tag} 检索字段「{self.search_field}」无对应侧边栏分组，跳过分组筛选")
            return False

        # 等待侧边栏容器出现后再定位分组（结果页异步渲染，直接定位可能扑空）
        try:
            await self.page.locator(self.GROUP_CONTAINER_SELECTOR).first.wait_for(state='visible', timeout=15000)
        except Exception:
            print(f"{tag} 侧边栏筛选容器(#divGroup)未出现")
            return False

        # 按 groupitem 定位分组 dl（如 主题/作者/机构/基金/文献来源/学科）
        dl = self.page.locator(
            f'{self.GROUP_CONTAINER_SELECTOR}//dl[dt[@groupitem="{target}"]]'
        )
        if await dl.count() == 0:
            print(f"{tag} 未找到侧边栏分组「{target}」")
            return False

        # 分组列表若为空（分组默认折叠、懒加载），点击 dt 标题展开并等待列表加载
        lis = dl.locator('xpath=.//dd//li')
        if await lis.count() == 0:
            try:
                await dl.locator('xpath=.//dt').first.click()
            except Exception:
                pass
            try:
                await lis.first.wait_for(state='visible', timeout=15000)
            except Exception:
                pass
            if await lis.count() == 0:
                print(f"{tag} 分组「{target}」列表未加载")
                return False

        # 一次性批量取所有候选项文本，避免逐项 inner_text 的多次往返
        texts = await lis.evaluate_all(
            """(lis) => lis.map((li) => (li.textContent || '').trim())"""
        )
        best_i, best_score = None, 0
        for i, text in enumerate(texts):
            base = re.split(r"[（(]", text)[0].strip()
            if base == self.keyword:
                score = 100
            elif base in self.keyword or self.keyword in base:
                score = 50
            else:
                score = len(set(base) & set(self.keyword))
            if score > best_score:
                best_i, best_score = i, score
        if best_i is None or best_score <= 0:
            print(f"{tag} 分组「{target}」中没有与关键词匹配的项")
            return False
        try:
            best_li = lis.nth(best_i)
            clickable = best_li.locator('xpath=.//a').first
            if await clickable.count() == 0:
                clickable = best_li
            await clickable.click()
            print(f"{tag} 已在「{target}」分组选中: {texts[best_i][:30]}")
            return True
        except Exception as e:
            print(f"{tag} 点击分组「{target}」项失败: {e}")
            return False

    async def _search_navigation_failed(self, timeout: int = 20) -> bool:
        """判断首页检索触发后的导航是否被风控拦截。

        触发搜索后可能出现三种落点：
        - /verify 验证码页、defaultresult 结果页：正常，返回 False
        - chrome-error（403 被拦）：失败，返回 True，调用方需重试
        超时未明确失败按成功处理（翻页收集阶段会对缺失结果表格兜底）。
        """
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            url = self.page.url
            if 'chrome-error' in url or 'chromewebdata' in url:
                return True
            if 'defaultresult' in url or 'verify' in url:
                return False
            try:
                if await self.page.locator(self.RESULT_TABLE_SELECTOR).first.count() > 0:
                    return False
            except Exception:
                pass
            await asyncio.sleep(1)
        return False

    async def _set_search_field(self) -> bool:
        """设置检索字段（主题/篇关摘/关键词/篇名/作者...）。

        参考 demo.py：悬停展开「检索字段」下拉框（div.sort-default）→ 在
        #DBFieldList 中点击目标字段；旧版 dd#searchField 下拉保留作兜底。
        失败静默回到默认字段（通常为「主题」）。
        """
        target = (self.search_field or '').strip() or '主题'
        if target == '主题':
            return True  # 默认主题无需切换

        # 方案一：现行首页/检索页的检索字段下拉（sort-default + #DBFieldList）
        try:
            cur = ''
            try:
                cur = (await self.page.locator(self.FIELD_SORT_DEFAULT_SELECTOR + '/span').first.inner_text()).strip()
            except Exception:
                pass
            if cur == target:
                return True
            await self.page.locator(self.FIELD_SORT_DEFAULT_SELECTOR).first.hover()
            await self.page.locator(self.FIELD_LIST_SELECTOR).first.wait_for(state='visible', timeout=8000)
            texts = await self.page.locator(self.FIELD_LI_SELECTOR).evaluate_all(
                """(lis) => lis.map((li) => (li.textContent || '').trim())"""
            )
            for i, text in enumerate(texts):
                if text == target:
                    item = self.page.locator(self.FIELD_LI_SELECTOR).nth(i)
                    clickable = item.locator('xpath=.//a').first
                    if await clickable.count() == 0:
                        clickable = item
                    await clickable.click()
                    print(f"  [关键词#{self.thread_id}] 已切换检索字段为: {target}")
                    return True
        except Exception as e:
            print(f"  [关键词#{self.thread_id}] sort-default 下拉切换检索字段失败，尝试旧版选择器: {e}")

        # 方案二：旧版 dd#searchField 下拉（兜底）
        try:
            dd = self.page.locator(self.FIELD_SELECTOR)
            if await dd.count() == 0:
                return False
            await dd.click()
            texts = await dd.locator('xpath=.//li').evaluate_all(
                """(lis) => lis.map((li) => (li.textContent || '').trim())"""
            )
            for text in texts:
                if target in text:
                    await dd.locator('xpath=.//li', has_text=text).first.click()
                    print(f"  [关键词#{self.thread_id}] 已切换检索字段为: {target}")
                    return True
        except Exception:
            pass
        print(f"  [关键词#{self.thread_id}] 未找到检索字段: {target}，保持默认")
        return False

    async def _collect_papers_from_rows(self) -> list:
        """从结果表格收集论文（url + title + 年份信息）。

        用 evaluate_all 在浏览器端一次性批量提取，避免逐行的多次往返通信
        （每调用一次内燃 inner_text / count 都是一次 CDP 往返，是收集阶段的性能热点）。
        """
        loc = self.page.locator(self.RESULT_TABLE_SELECTOR)
        if await loc.count() == 0:
            return []
        raw = await loc.locator('xpath=.//tr').evaluate_all(
            """(rows) => rows.map((row) => {
                const titleA = row.querySelector('a.fz14');
                const fallbackA = row.querySelector('td:first-child a');
                const a = (titleA || fallbackA);
                if (!a) return null;
                const href = a.getAttribute('href') || '';
                const title = (a.textContent || '').trim();
                if (!href || href === 'javascript:void(0)' || !title) return null;
                const ym = (row.textContent || '').match(/(20\\d{2})/);
                const srcA = row.querySelector('.source a, td.source a');
                const journal = srcA ? (srcA.textContent || '').trim() : '';
                return { href, title, year: ym ? Number(ym[1]) : null, journal };
            })"""
        )
        papers = []
        for r in raw:
            if r is None:
                continue
            papers.append({
                'url': urljoin('https://kns.cnki.net/', r['href']),
                'title': r['title'],
                'year': r['year'],
                'journal': r['journal'],
            })
        return papers

    async def _dump_page_html(self):
        """把当前页面 HTML 保存到文件，便于核对真实结构。"""
        try:
            self.debug_html.write_text(await self.page.content(), encoding='utf-8')
            print(f"  [关键词#{self.thread_id}] 已保存页面 HTML 到 {self.debug_html}")
        except Exception as e:
            print(f"  [关键词#{self.thread_id}] 保存调试 HTML 失败: {e}")

    def _within_year_range(self, year) -> bool:
        if not year:
            return True
        if self.min_year is not None and year < self.min_year:
            return False
        if self.max_year is not None and year > self.max_year:
            return False
        return True

    async def _next_page_exists(self) -> bool:
        nxt = self.page.locator(self.NEXT_PAGE_SELECTOR)
        if await nxt.count() == 0:
            return False
        cls = await nxt.first.get_attribute("class") or ""
        return "disabled" not in cls

    async def _current_page_num(self) -> int | None:
        """读取「下一页」按钮上的 data-curpage（当前页码），用于判断翻页是否真的前进。"""
        try:
            nxt = self.page.locator(self.NEXT_PAGE_SELECTOR)
            if await nxt.count() == 0:
                return None
            v = await nxt.first.get_attribute("data-curpage")
            if v is None:
                return None
            return int(v)
        except Exception:
            return None
    async def _wait_loading_gone(self, timeout=30000):
        """等待结果页分页 loading 遮罩（div.divLoading）消失，避免遮挡翻页点击。"""
        try:
            loader = self.page.locator('div.divLoading')
            if await loader.count() > 0:
                await loader.first.wait_for(state='hidden', timeout=timeout)
        except Exception:
            pass

    async def run_search(self):
        """执行关键词检索：搜索 -> 按检索字段做侧边栏分组筛选 -> 翻页收集 -> 详情入库。"""
        tag = f"[关键词#{self.thread_id}]"
        print("=" * 60)
        print(f"{tag} 关键词检索: {self.keyword} (字段: {self.search_field})")
        print(f"{tag} 当前年份区间: {self.min_year or '不限'} ~ {self.max_year or '不限'}, 最大翻页: {self.max_pages or '不限'}")
        print("=" * 60)

        await self.init_browser()
        try:
            # —— 断点恢复：--resume 且断点属于同一关键词时，从上次进度继续 ——
            cp = _load_search_checkpoint() if self.resume else None
            if cp and cp.get('keyword') != self.keyword:
                print(f"{tag} 断点属于其他关键词（{cp.get('keyword')}），忽略并从头执行")
                cp = None
            if not cp:
                _clear_search_checkpoint()
            resumed_papers: list = list(cp.get('papers') or []) if cp else []
            resume_page = int(cp.get('page') or 0) if cp else 0
            resume_phase = cp.get('phase') if cp else None
            resume_url = cp.get('search_url') if cp else None
            if cp:
                print(f"{tag} 检测到断点：phase={resume_phase}，已收集 {len(resumed_papers)} 篇（第 {resume_page} 页，存档 {cp.get('saved_at')}）")
                if resume_url:
                    self.search_url = resume_url  # 复用断点里的检索结果页 URL，跳过首页检索

            if self.search_url:
                # 复用已保存的检索结果页 URL，跳过首页检索/主题/类型筛选
                print(f"{tag} 直接打开已保存的检索结果页: {self.search_url}")
                await _pacing_wait()
                await self.page.goto(self.search_url, wait_until='domcontentloaded', timeout=60000)
                await self._ensure_no_captcha(timeout=180)
                await asyncio.sleep(random.uniform(2, 4))
            else:
                # 1. 打开知网首页（校外经登录态直接进，否则等待手动登录跳回）
                print(f"{tag} 打开知网首页...")
                await _pacing_wait()
                await self.page.goto('https://www.cnki.net/', wait_until='domcontentloaded', timeout=60000)
                for _ in range(90):
                    if 'cnki.net' in self.page.url:
                        break
                    await asyncio.sleep(2)

                # 2. 等待搜索框
                box = self.page.locator(self.SEARCH_SELECTOR)
                await box.wait_for(state='visible', timeout=60000)
                print(f"{tag} 已进入检索页")

                # 保存登录态（供下次复用）
                if self.state_file:
                    try:
                        await self.page.context.storage_state(path=str(self.state_file))
                        print(f"{tag} 登录态已保存: {self.state_file}")
                    except Exception:
                        pass

                # 3. 设置检索字段并输入关键词触发搜索。
                #    知网风控可能以 403 拦截首页表单提交（页面落到 chrome-error）。
                #    直连导航比表单提交稳定（实测直连返回 302→verify 页，可被验证码逻辑处理），
                #    失败时用页面 JS 拼好的检索 URL 直连重试。
                search_ok = False
                nav_url = None

                def _capture_nav_url(req):
                    nonlocal nav_url
                    if 'defaultresult' in req.url and req.method == 'GET':
                        nav_url = req.url

                self.page.on('request', _capture_nav_url)
                try:
                    for attempt in range(1, SEARCH_MAX_RETRIES + 1):
                        await self._set_search_field()
                        await self.random_scroll()
                        await box.click()
                        await box.fill(self.keyword)
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                        nav_url = None
                        await box.press('Enter')
                        await self._ensure_no_captcha(timeout=180)
                        if not await self._search_navigation_failed(timeout=20):
                            search_ok = True
                            break
                        print(f"{tag} 搜索请求被风控拦截(403/chrome-error)，第 {attempt}/{SEARCH_MAX_RETRIES} 次重试...")
                        # 短停顿让风控降级后再直连（连续快速重试会持续 403）
                        await asyncio.sleep(random.uniform(5, 9))
                        if nav_url:
                            # 表单提交被拦：改用直连导航（crossids/korder/kw 已由页面 JS 拼好）
                            await _pacing_wait()
                            try:
                                await self.page.goto(nav_url, wait_until='domcontentloaded', timeout=60000)
                                await self._ensure_no_captcha(timeout=180)
                                if not await self._search_navigation_failed(timeout=20):
                                    search_ok = True
                                    break
                            except Exception as e:
                                print(f"{tag} 直连重试失败: {e}")
                        # 回到首页准备下一次尝试
                        await asyncio.sleep(random.uniform(3, 6))
                        await _pacing_wait()
                        try:
                            await self.page.goto('https://www.cnki.net/', wait_until='domcontentloaded', timeout=60000)
                        except Exception:
                            pass
                        box = self.page.locator(self.SEARCH_SELECTOR)
                        try:
                            await box.wait_for(state='visible', timeout=60000)
                        except Exception:
                            pass
                finally:
                    try:
                        self.page.remove_listener('request', _capture_nav_url)
                    except Exception:
                        pass
                if not search_ok:
                    print(f"{tag} 搜索重试 {SEARCH_MAX_RETRIES} 次仍被拦截，放弃本次关键词检索")
                    return

                # 4. 按检索字段做侧边栏分组筛选（主题/作者/机构/基金/文献来源/学科）
                # 点击最匹配的分组项后等待结果刷新（参考 demo 的 zyzt 点击流程）
                if await self._pick_field_filter():
                    try:
                        await self.page.wait_for_load_state('domcontentloaded')
                    except Exception:
                        pass
                    await asyncio.sleep(random.uniform(2.5, 5))

                # 4.5 记录当前检索结果页 URL 到本地，供下次 --search-url 直接复用
                try:
                    self.search_url_file.write_text(self.page.url, encoding='utf-8')
                    print(f"{tag} 已保存检索结果页 URL -> {self.search_url_file}")
                except Exception as e:
                    print(f"{tag} 保存检索 URL 失败: {e}")

            # 5. 翻页收集论文
            all_papers: list = list(resumed_papers)
            # phase=detail：上次在详情入库阶段被中断，收集已完成，直接跳过翻页
            skip_collect = bool(cp and resume_phase == 'detail')
            page_no = 1
            if cp and resume_phase == 'collect' and resume_page > 0:
                # 快进到断点页的下一页（第 1..resume_page 页已收集过）
                reached = await self._fast_forward(resume_page + 1)
                print(f"{tag} 断点快进完成：当前第 {reached} 页")
                page_no = max(1, reached)
            if skip_collect:
                print(f"{tag} 断点恢复：跳过翻页收集，直接进入详情入库（{len(all_papers)} 篇待处理）")
            while not skip_collect:
                await self._ensure_no_captcha(timeout=120)
                try:
                    await self.page.locator(self.RESULT_TABLE_SELECTOR).first.wait_for(state='visible', timeout=30000)
                except Exception:
                    print(f"{tag} 第 {page_no} 页结果表格未出现")
                page_papers = await self._collect_papers_from_rows()
                page_papers = [p for p in page_papers if self._within_year_range(p.get('year'))]
                all_papers.extend(page_papers)
                print(f"{tag} 第 {page_no} 页获取 {len(page_papers)} 条，累计 {len(all_papers)} 条")
                # 每页收集完写断点：停止/崩溃后可从下一页续跑
                _save_search_checkpoint({
                    'keyword': self.keyword, 'search_field': self.search_field,
                    'search_url': self.page.url, 'phase': 'collect',
                    'page': page_no, 'papers': all_papers,
                })
                # 首页无内容时 dump 页面 HTML 便于核对真实结构
                if not page_papers and page_no == 1:
                    await self._dump_page_html()

                if self.max_pages is not None and page_no >= self.max_pages:
                    print(f"{tag} 已达到最大翻页数 {self.max_pages}，停止")
                    break
                if not await self._next_page_exists():
                    print(f"{tag} 已是最后一页")
                    break
                # 翻页：等 loading 遮罩消失后「单击」下一页（JS 点击优先，失败才用 force 兜底；
                # 不能两种点击都执行——双击会把分页器状态点乱，导致页码误判提前停止）
                await self._wait_loading_gone()
                await _pacing_wait()
                prev_cur = await self._current_page_num()
                click_ok = False
                try:
                    await self.page.locator(self.NEXT_PAGE_SELECTOR).first.evaluate('el => el.click()')
                    click_ok = True
                except Exception:
                    try:
                        await self.page.locator(self.NEXT_PAGE_SELECTOR).first.click(force=True, timeout=10000)
                        click_ok = True
                    except Exception:
                        click_ok = False
                if not click_ok:
                    print(f"{tag} 「下一页」点击失败（元素脱离/被遮挡），等待页面稳定后判断")
                await self._ensure_no_captcha(timeout=120)

                # 等翻页真正完成：loading 消失 + 结果表格重新可见 + 页码前进（最多 20 秒）
                advanced = False
                deadline = asyncio.get_event_loop().time() + 20
                while asyncio.get_event_loop().time() < deadline:
                    await self._wait_loading_gone(timeout=5000)
                    try:
                        await self.page.locator(self.RESULT_TABLE_SELECTOR).first.wait_for(state='visible', timeout=3000)
                    except Exception:
                        continue  # 结果表格还没重绘完，继续等
                    new_cur = await self._current_page_num()
                    if new_cur is not None and prev_cur is not None and new_cur > prev_cur:
                        advanced = True
                        break
                    if not await self._next_page_exists():
                        break  # 页面稳定后按钮已消失 → 翻到了真正的末页
                    await asyncio.sleep(0.5)

                if not advanced:
                    # 首要停止条件：下一页按钮不存在
                    if not await self._next_page_exists():
                        print(f"{tag} 下一页按钮不存在，已是最后一页")
                        break
                    # 按钮还在但页码未前进：复核一次，仍未前进才视为末页
                    await asyncio.sleep(2)
                    new_cur = await self._current_page_num()
                    if new_cur is not None and prev_cur is not None and new_cur <= prev_cur:
                        print(f"{tag} 翻页后页码未前进（{prev_cur} -> {new_cur}），视为已到末页，停止")
                        break
                page_no += 1

            print(f"{tag} 共收集 {len(all_papers)} 篇待处理论文")

            # —— 分支：只收集 URL vs 抓详情入库 ——
            if self.urls_only:
                hrefs = [p.get('url') for p in all_papers if p.get('url')]
                try:
                    self.urls_file.write_text("\n".join(hrefs), encoding='utf-8')
                    print(f"{tag} 已写入 {len(hrefs)} 条 URL 到 {self.urls_file}")
                except Exception as e:
                    print(f"{tag} 写入 URL 文件失败: {e}")
                return

            # 并发获取详情并入库（含去重，见 crawl_paper_detail）：
            # 翻页收集必须串行（同一结果页），详情抓取用 detail_workers 个 tab 并行
            # 先批量预取库中已有 URL，跳过已入库论文（逐篇检查仍保留作安全网）
            # 详情阶段断点：中断后恢复时跳过翻页收集，直接对本列表续抓（已入库 URL 会被跳过）
            _save_search_checkpoint({
                'keyword': self.keyword, 'search_field': self.search_field,
                'search_url': self.page.url, 'phase': 'detail',
                'page': page_no, 'papers': all_papers,
            })
            existing_urls = await self._db_existing_urls()
            queue = asyncio.Queue()
            skipped = 0
            for p in all_papers:
                if p.get('url') in existing_urls:
                    skipped += 1
                    continue
                queue.put_nowait(p)
            total = queue.qsize()
            done = 0
            ok = 0
            stats = {'already_exists': skipped, 'filtered': 0, 'verify_failed': 0, 'failed': 0}

            async def detail_worker(wid: int):
                nonlocal done, ok
                wtag = f"{tag}[W{wid}]"
                page = await self.context.new_page()
                try:
                    while True:
                        try:
                            paper = queue.get_nowait()
                        except asyncio.QueueEmpty:
                            return
                        done += 1
                        print(f"{wtag} [{done}/{total}] 处理: {paper['title'][:30]}...")
                        res = await self.crawl_paper_detail(paper, page=page)
                        if res and res.get('title'):
                            ok += 1
                        else:
                            reason = res.get('error', 'failed') if res else 'failed'
                            if reason == 'already_exists':
                                stats['already_exists'] += 1
                            elif reason == 'verify_page':
                                stats['verify_failed'] += 1
                            elif reason == 'filtered_non_paper':
                                stats['filtered'] += 1
                            else:
                                stats['failed'] += 1
                        await asyncio.sleep(random.uniform(0.5, 1.5))
                finally:
                    try:
                        await page.close()
                    except Exception:
                        pass

            n = max(1, self.detail_workers)
            print(f"{tag} 详情并发数: {n}，待抓 {total} 篇（已在库跳过 {skipped}）")
            await asyncio.gather(*[detail_worker(i) for i in range(n)])

            print(f"{tag} 完成：成功 {ok}/{total} 篇 | 已在库 {stats['already_exists']} | "
                  f"被过滤 {stats['filtered']} | 验证码未过 {stats['verify_failed']} | 失败 {stats['failed']}")
            if getattr(self, '_refs_done', 0) or getattr(self, '_refs_failed', 0):
                print(f"{tag} 参考文献（--detail-refs）：成功 {getattr(self, '_refs_done', 0)} 篇 | "
                      f"失败 {getattr(self, '_refs_failed', 0)} 篇")
            _clear_search_checkpoint()
            print(f"{tag} 断点已清除")
        except Exception as e:
            print(f"{tag} 检索流程异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.close_browser()


class ReferenceCrawler(KeywordSearchCrawler):
    """参考文献爬取：给定论文详情页链接（可批量）或论文标题，进入详情页抓取参考文献列表条目。

    抓取/翻页/入库复用 JournalCrawler 上的共享实现（_open_references_tab /
    _crawl_references / _save_references 等，页面结构与防风控节奏见其 REF_* 常量）。
    仅抓列表条目（文本+链接），不递归打开参考文献自身的详情页；结果按 paper_url
    覆盖式写入 paper_references 表。

    防风控：详情页导航与翻页请求都计入节奏——篇间隔默认 6s（随机上浮，--ref-interval
    可调）；触发验证码多时调大 --ref-interval 或 --show-browser 人工配合。

    用法:
        python cnki_paper_captcha.py --ref-paper-url "https://kns.cnki.net/..."
        python cnki_paper_captcha.py --ref-urls-file .cache/urls.txt
        python cnki_paper_captcha.py --ref-title "论文标题" --ref-max-items 100
    """


    def __init__(self, headless=True, thread_id=0, state_file=None,
                 paper_urls=None, paper_title=None, max_items=None, interval=6.0):
        super().__init__(headless=headless, thread_id=thread_id, state_file=state_file)
        self.paper_urls = list(paper_urls or [])
        self.paper_title = (paper_title or '').strip()
        self.max_items = max_items
        self.ref_interval = max(1.0, float(interval))

    async def run(self):
        tag = f"[参考文献#{self.thread_id}]"
        print("=" * 60)
        print(f"{tag} 参考文献爬取: {len(self.paper_urls)} 个链接"
              + (f" + 标题「{self.paper_title}」" if self.paper_title else "")
              + f" | 篇间隔 {self.ref_interval}s（防风控）")
        print("=" * 60)

        # 组装任务：URL 直接打开；标题先检索定位（默认取第一条结果）
        tasks = [{'paper_url': u, 'paper_title': ''} for u in self.paper_urls]
        if self.paper_title:
            tasks.append({'paper_url': None, 'paper_title': self.paper_title})
        if not tasks:
            print(f"{tag} 未提供论文链接/标题，退出")
            return

        await self.init_browser()
        total_refs = 0
        ok_papers = 0
        try:
            for i, task in enumerate(tasks, 1):
                paper_url = task['paper_url']
                paper_title = task['paper_title']
                print(f"\n{tag} [{i}/{len(tasks)}] 处理论文: {paper_title or paper_url[:70]}")
                try:
                    # —— 定位论文详情页 ——
                    if not paper_url:
                        located = await self._locate_paper_by_title(tag)
                        if not located:
                            print(f"{tag} 未能在检索结果中定位到论文，跳过")
                            continue
                        paper_url, paper_title = located
                    else:
                        print(f"{tag} 直接打开论文详情页: {paper_url}")

                    await _pacing_wait()
                    await self.page.goto(paper_url, wait_until='domcontentloaded', timeout=60000)
                    if not await self.wait_for_page_stable(paper_url):
                        print(f"{tag} ✗ 详情页遇到安全验证且未通过，跳过")
                        continue
                    await self._ensure_no_captcha(timeout=120)
                    # 模拟真人浏览：先随机滚动再点页签，降低风控敏感度
                    await self.random_scroll()
                    await asyncio.sleep(random.uniform(MIN_DETAIL_DELAY, MAX_DETAIL_DELAY))

                    # URL 入口时从详情页提取标题（标题入口在检索阶段已拿到）
                    if not paper_title:
                        try:
                            paper_title = (await self.page.locator('div.doc h1, h1')
                                           .first.inner_text(timeout=8000)).strip()
                        except Exception:
                            paper_title = ''

                    refs = await self._crawl_references(tag)
                    if not refs:
                        print(f"{tag} 未抓到参考文献（详情页可能没有参考文献区块）")
                        continue
                    if self.max_items and len(refs) > self.max_items:
                        print(f"{tag} 超过上限 {self.max_items} 条，截断")
                        refs = refs[:self.max_items]

                    print(f"{tag} 完成：共抓取参考文献 {len(refs)} 条，前 3 条预览：")
                    for r in refs[:3]:
                        print(f"{tag}   - {r['text'][:70]}")
                    await self._save_references(paper_url, paper_title, refs)
                    total_refs += len(refs)
                    ok_papers += 1
                except Exception as e:
                    print(f"{tag} 处理论文异常: {e}")
                    import traceback
                    traceback.print_exc()
                # 篇间退避：详情页导航频率是触发风控的主因，宁慢勿封
                if i < len(tasks):
                    gap = random.uniform(self.ref_interval, self.ref_interval * 1.8)
                    print(f"{tag} 停 {gap:.1f}s 再处理下一篇（防风控）")
                    await asyncio.sleep(gap)
        finally:
            await self.close_browser()

        print(f"\n{tag} {'=' * 60}")
        print(f"{tag} 全部完成：{ok_papers}/{len(tasks)} 篇论文，共入库参考文献 {total_refs} 条")
        print(f"{tag} {'=' * 60}")

    async def _locate_paper_by_title(self, tag: str):
        """按论文标题搜索知网并定位详情页：默认取第一条结果，其余候选打印到日志供人工核对。"""
        print(f"{tag} 按标题检索: {self.paper_title}")
        await _pacing_wait()
        await self.page.goto('https://www.cnki.net/', wait_until='domcontentloaded', timeout=60000)
        for _ in range(90):
            if 'cnki.net' in self.page.url:
                break
            await asyncio.sleep(2)
        box = self.page.locator(self.SEARCH_SELECTOR).first
        await box.wait_for(state='visible', timeout=60000)
        # 检索触发可能被风控以 403 拦截（页面落到 chrome-error）：退避重试，
        # 策略与关键词检索流程一致（重试间回首页、过全局导航闸）
        nav_ok = False
        for attempt in range(1, SEARCH_MAX_RETRIES + 1):
            await self.random_scroll()
            await box.click()
            await box.fill(self.paper_title)
            await asyncio.sleep(random.uniform(0.5, 1.5))
            await box.press('Enter')
            await self._ensure_no_captcha(timeout=180)
            if not await self._search_navigation_failed(timeout=20):
                nav_ok = True
                break
            print(f"{tag} 检索被风控拦截（第 {attempt}/{SEARCH_MAX_RETRIES} 次），退避后重试...")
            await asyncio.sleep(random.uniform(5, 9))
            try:
                await _pacing_wait()
                await self.page.goto('https://www.cnki.net/', wait_until='domcontentloaded', timeout=60000)
                box = self.page.locator(self.SEARCH_SELECTOR).first
                await box.wait_for(state='visible', timeout=60000)
            except Exception as e:
                print(f"{tag} 回首页准备重试失败: {e}")
                return None
        if not nav_ok:
            print(f"{tag} 检索连续 {SEARCH_MAX_RETRIES} 次被风控拦截，退出")
            return None

        # 事件驱动等检索结果表渲染（站点反应快慢不一，固定 sleep 会拿到空结果）
        try:
            await self.page.locator(self.RESULT_TABLE_SELECTOR).first.wait_for(
                state='visible', timeout=30000)
        except Exception:
            print(f"{tag} 等待检索结果表 30s 未出现，进入兜底重试")

        # 结果可能懒加载：多轮重试收集，仍为空才放弃并落调试 HTML 供核对
        candidates: list = []
        for attempt in range(4):
            candidates = await self._collect_papers_from_rows()
            if candidates:
                break
            if attempt < 3:
                print(f"{tag} 第 {attempt + 1} 次未取到结果，等待页面加载后重试...")
                await asyncio.sleep(random.uniform(2.5, 4))
        if not candidates:
            print(f"{tag} 检索结果为空，已保存页面 HTML 供核对")
            await self._dump_page_html()
            return None
        print(f"{tag} 检索到 {len(candidates)} 条候选，前 5 条：")
        for i, c in enumerate(candidates[:5]):
            print(f"{tag}   [{i + 1}] {c['title'][:60]} ({c.get('journal', '')} {c.get('year') or ''})")
        first = candidates[0]
        print(f"{tag} 默认取第 1 条: {first['title'][:60]}")
        return first['url'], first['title']


async def main():
    parser = argparse.ArgumentParser(description='知网爬虫 - 验证码自动解决版本（按期刊 / 按关键词检索 / 参考文献抓取）')
    parser.add_argument('--show-browser', action='store_true', help='显示浏览器窗口（默认不显示）')
    parser.add_argument('--threads', type=int, default=3, help='期刊收集阶段的并发浏览器数（默认3）')
    parser.add_argument('--search', type=str, default=None,
                        help='按关键词/主题检索知网并入库（启用检索模式，替代按期刊爬取）')
    parser.add_argument('--search-field', type=str, default='主题',
                        help=f'检索字段（可选：{" / ".join(CNKI_SEARCH_FIELDS)}，默认主题）')
    parser.add_argument('--max-pages', type=int, default=None,
                        help='检索模式最大翻页数（不设则翻到最后一页）')
    parser.add_argument('--years', type=str, default=None,
                        help='年份区间，如 2024-2026（仅检索模式，按结果行年份过滤，可选）')
    parser.add_argument('--no-login-state', action='store_true',
                        help='禁用登录态复用（默认自动复用 .cache/cnki_state.json）')
    parser.add_argument('--urls-only', action='store_true',
                        help='只收集论文 URL 写入文件，不抓详情入库（仅检索模式）')
    parser.add_argument('--urls-file', type=str, default=None,
                        help='URL 输出文件路径（默认 .cache/urls.txt，配合 --urls-only）')
    parser.add_argument('--search-url', type=str, default=None,
                        help='直接复用已保存的检索结果页 URL（传完整URL，或传含URL的文本文件路径）')
    parser.add_argument('--save-url-file', type=str, default=None,
                        help='检索结果页 URL 保存路径（默认 .cache/search_url.txt）')
    parser.add_argument('--detail-workers', type=int, default=3,
                        help='详情页并发抓取 tab 数（默认3；期刊模式与检索模式均有效，翻页/收集仍按各自并发模型）')
    parser.add_argument('--resume', action='store_true',
                        help='断点续跑：存在同关键词断点（.cache/search_checkpoint.json）时从上次进度继续')
    parser.add_argument('--ref-paper-url', type=str, action='append', default=None,
                        help='参考文献模式：论文详情页链接，可重复传多个；批量可配合 --ref-urls-file')
    parser.add_argument('--ref-title', type=str, default=None,
                        help='参考文献模式：论文标题（检索后取第一条结果进详情页抓参考文献）')
    parser.add_argument('--ref-urls-file', type=str, default=None,
                        help='参考文献模式：论文详情页链接清单文件（每行一个 URL，# 开头为注释）')
    parser.add_argument('--ref-max-items', type=int, default=None,
                        help='单篇参考文献条数上限（默认不限）')
    parser.add_argument('--ref-interval', type=float, default=6.0,
                        help='参考文献模式两篇论文之间的基础间隔秒数（实际随机上浮至约1.8倍；默认6，易触发验证码时调大）')
    parser.add_argument('--detail-refs', action='store_true',
                        help='抓论文详情时在同一详情页顺带抓取参考文献入库（省二次导航，总体更不易触发风控；期刊/检索模式均生效）')
    args = parser.parse_args()

    if args.detail_refs and args.detail_workers > 2:
        print("[提示] --detail-refs 开启时建议 --detail-workers ≤ 2：每个 tab 都可能翻参考文献页，请求经全局导航闸排队，并发多会更慢且更易触发风控")

    # 参考文献模式：--ref-paper-url（可多个）/ --ref-urls-file / --ref-title 任一提供即启用
    ref_urls = list(args.ref_paper_url or [])
    if args.ref_urls_file:
        try:
            for line in Path(args.ref_urls_file).read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if line and not line.startswith('#'):
                    ref_urls.append(line)
        except Exception as e:
            print(f"[WARN] 读取 URL 清单文件失败: {e}")
    if ref_urls or args.ref_title:
        state_file = None if args.no_login_state else str(CACHE_DIR / 'cnki_state.json')
        ref_crawler = ReferenceCrawler(
            headless=not args.show_browser,
            state_file=state_file,
            paper_urls=ref_urls,
            paper_title=args.ref_title,
            max_items=args.ref_max_items,
            interval=args.ref_interval,
        )
        await ref_crawler.run()
        return

    if args.search:
        # 校验检索字段，未知值回退到默认「主题」
        if args.search_field not in CNKI_SEARCH_FIELDS:
            print(f"[WARN] 未知检索字段: {args.search_field}，可选: {' / '.join(CNKI_SEARCH_FIELDS)}，回退为默认「主题」")
            args.search_field = '主题'
        min_year = max_year = None
        if args.years:
            parts = args.years.replace('，', ',').split('-')
            try:
                min_year = int(parts[0].strip())
                max_year = int(parts[1].strip()) if len(parts) > 1 else min_year
            except Exception:
                print("年份格式错误，忽略 --years，应为如 2024-2026")
                min_year = max_year = None
        state_file = None if args.no_login_state else str(CACHE_DIR / 'cnki_state.json')
        # --search-url 支持直接传 URL，或传一个含 URL 的本地文件路径（自动读取）
        search_url = args.search_url
        if search_url and Path(search_url).is_file():
            search_url = Path(search_url).read_text(encoding='utf-8').strip()
        crawler = KeywordSearchCrawler(
            headless=not args.show_browser,
            keyword=args.search,
            search_field=args.search_field,
            max_pages=args.max_pages,
            min_year=min_year,
            max_year=max_year,
            state_file=state_file,
            urls_only=args.urls_only,
            urls_file=args.urls_file,
            search_url=search_url,
            search_url_file=args.save_url_file,
            detail_workers=args.detail_workers,
            resume=args.resume,
            refs_with_details=args.detail_refs,
            ref_max_items=args.ref_max_items,
        )
        await crawler.run_search()
        return

    crawler = MultiThreadedCrawler(
        headless=not args.show_browser,
        max_workers=args.threads,
        detail_workers=args.detail_workers,
        refs_with_details=args.detail_refs,
        ref_max_items=args.ref_max_items,
    )
    await crawler.run()


if __name__ == '__main__':
    asyncio.run(main())
