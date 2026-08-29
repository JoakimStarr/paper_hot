"""验证码解决器：OCR（ddddocr / PaddleOCR / opencv）+ 滑块 + 文字点选。

OCR 引擎按需惰性初始化（进程级共享单例），推理统一经 `_ocr_call` 丢到后台线程并
串行化，避免阻塞事件循环。可选依赖（ddddocr / paddleocr / opencv）不在此处强制
导入，由 `probe()` 探测并在 cli 启动时调用一次。
"""
import asyncio
import io
import json
import random
import re
import threading
import time
from pathlib import Path
from typing import List, Optional, Tuple

from playwright.async_api import Page

from cnki_crawler.pacing import _report_captcha
from cnki_crawler.parsing import VERIFY_URL_PREFIX
from bs4 import BeautifulSoup

# —— OCR 引擎进程级共享 + 串行锁 ——
# 单事件循环下多 tab 并发，OCR 推理是同步阻塞调用，统一丢到 to_thread 并由
# threading.Lock 串行化，避免阻塞事件循环、也避免共享引擎实例的并发不安全。
_OCR_THREAD_LOCK = threading.Lock()
_ENGINE_LOCK = threading.Lock()
_slider_ocr_shared: Optional['ddddocr.DdddOcr'] = None
_det_ocr_shared: Optional['ddddocr.DdddOcr'] = None
_text_ocr_shared: Optional['ddddocr.DdddOcr'] = None
_paddle_ocr_shared: Optional['PaddleOCR'] = None

# 可选依赖占位（由 probe() 填充）
ddddocr = None
PaddleOCR = None
cv2 = None
np = None
DDDDOCR_AVAILABLE = False
PADDLEOCR_AVAILABLE = False
CV2_AVAILABLE = False

CLICK_CAPTCHA_MAX_RETRIES = 10  # 测试期临时调高到 10，定位识别问题后应收敛
SLIDER_CAPTCHA_MAX_RETRIES = 3


def probe():
    """探测可选 OCR 依赖并打印警告（cli 启动时调用一次，幂等）。

    原单文件脚本在模块顶层做探测并 print，这里收口成显式调用，避免包导入即有副作用。
    """
    global ddddocr, PaddleOCR, cv2, np
    global DDDDOCR_AVAILABLE, PADDLEOCR_AVAILABLE, CV2_AVAILABLE
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


