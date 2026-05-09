#!/usr/bin/env python3
"""
知网期刊爬虫 - 验证码自动解决版本
基于 cnki_paper_threaded.py，集成 ddddocr 自动解决验证码
支持滑块验证码（期刊页面）和文字点选验证码（论文详情页面）

依赖安装:
    pip install ddddocr Pillow

使用方法:
    python cnki_paper_captcha.py --show-browser
    python cnki_paper_captcha.py --threads 3
"""

import json
import re
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
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    print("建议运行: pip install paddlepaddle paddleocr")

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

# 文件路径
BACKEND_DIR = Path('backend')
DATA_DIR = BACKEND_DIR / 'data'
JOURNALS_HISTORY_FILE = DATA_DIR / 'journals_history.json'
PAPERS_HISTORY_FILE = DATA_DIR / 'papers_history.json'


class CaptchaSolver:
    """验证码解决器 - 使用 ddddocr 和 PaddleOCR 自动识别和解决验证码"""

    def __init__(self, thread_id: int = 0):
        self.thread_id = thread_id
        self._slider_ocr: Optional[ddddocr.DdddOcr] = None
        self._det_ocr: Optional[ddddocr.DdddOcr] = None
        self._text_ocr: Optional[ddddocr.DdddOcr] = None
        self._paddle_ocr: Optional[PaddleOCR] = None
        self._init_ocr()

    def _init_ocr(self):
        """初始化 OCR 实例"""
        # 初始化 ddddocr
        if DDDDOCR_AVAILABLE:
            try:
                # 滑块识别专用（关闭 OCR 和目标检测）
                self._slider_ocr = ddddocr.DdddOcr(det=False, ocr=False, show_ad=False)
                # 目标检测专用（用于点选验证码定位文字位置）
                self._det_ocr = ddddocr.DdddOcr(det=True, ocr=False, show_ad=False)
                # 文字识别专用（备用）
                self._text_ocr = ddddocr.DdddOcr(det=False, ocr=True, show_ad=False)
                print(f"  [线程{self.thread_id}] ddddocr 初始化完成")
            except Exception as e:
                print(f"  [线程{self.thread_id}] ddddocr 初始化失败: {e}")

        # 初始化 PaddleOCR（主要文字识别引擎）
        if PADDLEOCR_AVAILABLE:
            try:
                # 使用最简参数初始化
                self._paddle_ocr = PaddleOCR(lang='ch')
                print(f"  [线程{self.thread_id}] PaddleOCR 初始化完成")
            except Exception as e:
                print(f"  [线程{self.thread_id}] PaddleOCR 初始化失败: {e}")
                self._paddle_ocr = None

    def is_available(self) -> bool:
        """检查验证码解决器是否可用"""
        has_ddddocr = DDDDOCR_AVAILABLE and self._slider_ocr is not None
        has_paddle = PADDLEOCR_AVAILABLE and self._paddle_ocr is not None
        return has_ddddocr or has_paddle

    def _preprocess_char_image(self, char_img_bytes: bytes) -> bytes:
        """
        预处理单个文字图片，提高 OCR 识别准确率
        使用 OpenCV 进行：灰度化 -> 自适应二值化 -> 去噪
        """
        if not CV2_AVAILABLE:
            return char_img_bytes

        try:
            # 将 bytes 转换为 OpenCV 图像
            nparr = np.frombuffer(char_img_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if img is None:
                return char_img_bytes

            # 1. 转换为灰度图
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # 2. 自适应二值化（比固定阈值更能应对光照不均）
            binary = cv2.adaptiveThreshold(
                gray, 255,
                cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                cv2.THRESH_BINARY_INV,  # 反转：文字为白色，背景为黑色
                11, 2
            )

            # 3. 开运算去噪（去除小噪点）
            kernel = np.ones((2, 2), np.uint8)
            denoised = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

            # 4. 可选：膨胀操作使文字更清晰
            kernel_dilate = np.ones((2, 2), np.uint8)
            enhanced = cv2.morphologyEx(denoised, cv2.MORPH_CLOSE, kernel_dilate)

            # 5. 反转回正常颜色（文字黑色，背景白色）
            final = cv2.bitwise_not(enhanced)

            # 转换回 bytes
            _, buffer = cv2.imencode('.png', final)
            return buffer.tobytes()

        except Exception as e:
            print(f"    [线程{self.thread_id}] 图像预处理失败: {e}")
            return char_img_bytes

    def _recognize_char_fusion(self, char_img_bytes: bytes) -> list:
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
                    result = self._paddle_ocr.ocr(img, det=False, cls=False)
                    if result and result[0]:
                        text = result[0][0][0] if isinstance(result[0][0], tuple) else result[0][0]
                        if text and text.strip():
                            # 清理结果：只保留中文字符和常见字符
                            cleaned = self._clean_ocr_result(text.strip())
                            if cleaned:
                                all_results.update(cleaned)
            except Exception:
                pass

        # 策略2：使用预处理后的图片 + ddddocr
        if CV2_AVAILABLE and self._text_ocr is not None:
            try:
                processed_bytes = self._preprocess_char_image(char_img_bytes)
                result = self._text_ocr.classification(processed_bytes)
                if result and result.strip():
                    cleaned = self._clean_ocr_result(result.strip())
                    if cleaned:
                        all_results.update(cleaned)
            except Exception:
                pass

        # 策略3：使用原图 + ddddocr
        if self._text_ocr is not None:
            try:
                result = self._text_ocr.classification(char_img_bytes)
                if result and result.strip():
                    cleaned = self._clean_ocr_result(result.strip())
                    if cleaned:
                        all_results.update(cleaned)
            except Exception:
                pass

        # 策略4：尝试调整图片大小 + ddddocr
        if CV2_AVAILABLE and self._text_ocr is not None:
            try:
                nparr = np.frombuffer(char_img_bytes, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                if img is not None:
                    height, width = img.shape[:2]
                    resized = cv2.resize(img, (width * 2, height * 2), interpolation=cv2.INTER_CUBIC)
                    _, buffer = cv2.imencode('.png', resized)
                    result = self._text_ocr.classification(buffer.tobytes())
                    if result and result.strip():
                        cleaned = self._clean_ocr_result(result.strip())
                        if cleaned:
                            all_results.update(cleaned)
            except Exception:
                pass

        return list(all_results)

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
        返回: 'slider' (滑块), 'click' (点选)
        
        知网验证码特点：
        - 期刊页面：通常是滑块验证码
        - 论文详情页：通常是文字点选验证码
        """
        try:
            # 优先使用 Playwright 查询动态加载的元素（更准确）
            # 检查点选验证码特征
            verify_img_panel = await page.query_selector('div.verify-img-panel')
            verify_msg = await page.query_selector('span.verify-msg')
            if verify_img_panel and verify_msg:
                print(f"    [线程{self.thread_id}] 检测到点选验证码元素 (verify-img-panel + verify-msg)")
                return 'click'

            # 检查滑块验证码特征
            slider_elem = await page.query_selector('.verify-slider, .slider, [class*="slider"]')
            if slider_elem:
                print(f"    [线程{self.thread_id}] 检测到滑块验证码元素")
                return 'slider'

            # 备用：通过页面文本判断
            html = await page.content()
            soup = BeautifulSoup(html, 'lxml')
            page_text = soup.get_text()

            # 检查点选验证码文本特征
            if '请依次点击' in page_text or '请点击' in page_text:
                print(f"    [线程{self.thread_id}] 通过文本检测到点选验证码")
                return 'click'

            # 检查滑块验证码文本特征
            if '滑块' in page_text or '拖动' in page_text:
                print(f"    [线程{self.thread_id}] 通过文本检测到滑块验证码")
                return 'slider'

            # 默认返回点选（论文详情页最常见）
            print(f"    [线程{self.thread_id}] 无法确定验证码类型，默认尝试点选验证码")
            return 'click'
        except Exception as e:
            print(f"    [线程{self.thread_id}] 检测验证码类型失败: {e}")
            return 'click'  # 默认返回点选类型（论文详情页更常见）

    async def solve_slider_captcha(self, page: Page, max_retries: int = 3) -> bool:
        """
        解决滑块验证码
        使用 ddddocr 的 slide_match 计算滑动距离并模拟拖动
        """
        if not self.is_available():
            print(f"    [线程{self.thread_id}] ddddocr 不可用，无法自动解决滑块验证码")
            return False

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
                    # 常见的滑块验证码选择器
                    slider_selectors = [
                        '.verify-slider',
                        '.slider-img',
                        '[class*="slider"]',
                        'img[src*="slider"]',
                    ]
                    bg_selectors = [
                        '.verify-bg',
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
                result = self._slider_ocr.slide_match(
                    target_bytes,
                    background_bytes,
                    simple_target=True
                )

                if not result or 'target' not in result:
                    print(f"    [线程{self.thread_id}] 滑块识别失败")
                    await asyncio.sleep(1)
                    continue

                distance = result['target'][0]
                print(f"    [线程{self.thread_id}] 计算滑动距离: {distance}px")

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
        return False

    async def _human_drag(self, page: Page, distance: float):
        """模拟人类拖动滑块"""
        try:
            # 获取滑块元素
            slider_selectors = [
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

    async def solve_click_captcha(self, page: Page, max_retries: int = 20) -> bool:
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

        for attempt in range(max_retries):
            try:
                print(f"    [线程{self.thread_id}] 尝试解决点选验证码 (第 {attempt + 1}/{max_retries} 次)")

                await asyncio.sleep(2)

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

                print(f"    [线程{self.thread_id}] 验证码图片已截取，开始识别文字位置和文字内容...")

                # 使用目标检测获取所有文字位置
                bboxes = self._det_ocr.detection(captcha_bytes)

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

                # 使用 OCR 识别每个位置上的文字
                from PIL import Image
                import io

                char_map = {}  # 文字 -> 位置的映射
                img = Image.open(io.BytesIO(captcha_bytes))

                for i, bbox in enumerate(bboxes):
                    x1, y1, x2, y2 = bbox
                    # 裁剪出单个文字区域
                    char_img = img.crop((x1, y1, x2, y2))
                    # 转换为 bytes
                    img_buffer = io.BytesIO()
                    char_img.save(img_buffer, format='PNG')
                    char_img_bytes = img_buffer.getvalue()

                    # 使用多引擎融合识别
                    recognized_chars = self._recognize_char_fusion(char_img_bytes)

                    if recognized_chars:
                        # 将相对坐标转换为绝对坐标
                        abs_x = panel_x + (x1 + x2) / 2
                        abs_y = panel_y + (y1 + y2) / 2

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
    def save_journals_history(journals: dict):
        """保存期刊历史记录"""
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            'last_updated': datetime.now().isoformat(),
            'journals': journals
        }
        with open(JOURNALS_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

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
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            'last_updated': datetime.now().isoformat(),
            'papers': papers
        }
        with open(PAPERS_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

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
    """单个期刊爬虫（每个线程一个实例）"""

    def __init__(self, headless=True, thread_id=0):
        self.headless = headless
        self.thread_id = thread_id
        self.page = None
        self.browser = None
        self.playwright = None
        self.db_initialized = False
        self.captcha_solver = CaptchaSolver(thread_id=thread_id)
        self._captcha_retry_count = 0
        self._max_captcha_retries = 3

    async def init_browser(self):
        """初始化浏览器"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--no-sandbox',
                '--disable-gpu',
                '--disable-dev-shm-usage',
                '--disable-blink-features=AutomationControlled',
                '--disable-web-security',
                '--disable-features=IsolateOrigins,site-per-process',
            ]
        )

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

        context = await self.browser.new_context(
            user_agent=user_agent,
            viewport=viewport,
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
            permissions=['geolocation'],
            geolocation={'latitude': 39.9042, 'longitude': 116.4074},
        )

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

    async def random_scroll(self):
        """随机滚动页面模拟人类行为"""
        try:
            scroll_times = random.randint(1, 3)
            for _ in range(scroll_times):
                scroll_y = random.randint(100, 500)
                await self.page.evaluate(f'window.scrollBy(0, {scroll_y})')
                await asyncio.sleep(random.uniform(0.5, 2))
        except Exception:
            pass

    def is_verify_page(self, page_url: str) -> bool:
        """检查是否是验证码页面"""
        return page_url.startswith(VERIFY_URL_PREFIX)

    async def wait_for_page_stable(self, target_url: str, max_wait_time: int = 300) -> bool:
        """等待页面稳定，自动解决验证码"""
        current_url = self.page.url

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
            captcha_type = await self.captcha_solver.detect_captcha_type(self.page)
            print(f"    [线程{self.thread_id}] 检测到验证码类型: {captcha_type}")

            if captcha_type == 'slider':
                success = await self.captcha_solver.solve_slider_captcha(self.page)
                if success:
                    self._captcha_retry_count = 0  # 成功后重置计数器
                    return True
            elif captcha_type == 'click':
                success = await self.captcha_solver.solve_click_captcha(self.page)
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

            current_url = self.page.url

            if not self.is_verify_page(current_url):
                print(f"    [线程{self.thread_id}] ✓ 验证码已解决")
                self._captcha_retry_count = 0  # 成功后重置计数器
                return True

            await asyncio.sleep(1)

    async def get_year_issues(self, journal_url: str) -> list:
        """获取期刊的年份期次列表"""
        print(f"  [线程{self.thread_id}] 访问期刊页面: {journal_url[:60]}...")
        await self.page.goto(journal_url, wait_until='domcontentloaded', timeout=60000)

        if not await self.wait_for_page_stable(journal_url):
            return []

        await asyncio.sleep(8)

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
                await self.page.evaluate('document.getElementById("larrow").click()')
                await asyncio.sleep(8)
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

    async def crawl_paper_detail(self, paper_info: dict, journal_name: str = None) -> dict:
        """获取论文详情"""
        paper_url = paper_info['url']

        try:
            import sys
            sys.path.insert(0, str(BACKEND_DIR))

            from app.crud import PaperCRUD
            from app.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                existing = await PaperCRUD.get_paper_by_url(db, paper_url)
                if existing:
                    print(f"  [线程{self.thread_id}] 数据库中已存在，跳过")
                    return {'error': 'already_exists'}
        except Exception:
            pass

        print(f"  [线程{self.thread_id}] 获取论文详情: {paper_info['title'][:50]}...")

        wait_time = random.uniform(5, 10)
        await asyncio.sleep(wait_time)

        try:
            await self.page.goto(paper_url, wait_until='domcontentloaded', timeout=60000)

            if not await self.wait_for_page_stable(paper_url):
                return {'error': 'verify_page'}

            await self.random_scroll()
            await asyncio.sleep(random.uniform(3, 6))

            html = await self.page.content()
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
                    if author_name:
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
                **meta
            }

            if title:
                print(f"    [线程{self.thread_id}] ✓ 成功获取: {title[:40]}...")
                await self.save_to_database(result, journal_name)
                return result
            else:
                print(f"    [线程{self.thread_id}] ✗ 获取失败: 无标题")
                return {'error': 'no_title'}

        except Exception as e:
            print(f"    [线程{self.thread_id}] ✗ 获取失败: {e}")
            return {'error': str(e)}

    async def save_to_database(self, paper_data: dict, journal_name: str = None):
        """异步保存到数据库"""
        try:
            import sys
            import re
            sys.path.insert(0, str(BACKEND_DIR))

            from app.database import init_db
            from app.crud import PaperCRUD
            from app.database import AsyncSessionLocal

            if not self.db_initialized:
                db_file = BACKEND_DIR / 'data' / 'paperpulse.db'
                if not db_file.exists():
                    print(f"    [线程{self.thread_id}] 数据库文件不存在，正在创建...")
                    await init_db()
                    print(f"    [线程{self.thread_id}] ✓ 数据库已创建")
                self.db_initialized = True

            async with AsyncSessionLocal() as db:
                existing = await PaperCRUD.get_paper_by_url(db, paper_data['url'])
                if existing:
                    print(f"    [线程{self.thread_id}] 数据库中已存在，跳过")
                    return

                if journal_name:
                    paper_data['journal_name'] = journal_name

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

    async def process_journal(self, journal_name: str, journal_info: dict):
        """处理单个期刊（线程入口）"""
        crawl_log_id = None
        try:
            await self.init_browser()

            papers = await self.crawl_papers_for_journal(journal_name, journal_info)

            if not papers:
                print(f"[线程{self.thread_id}] 期刊 {journal_name} 未获取到论文")
                return

            # 创建爬取日志
            try:
                import sys
                sys.path.insert(0, str(BACKEND_DIR))
                from app.schemas import CrawlLogCreate
                from app.crud import CrawlLogCRUD
                from app.database import AsyncSessionLocal
                async with AsyncSessionLocal() as db:
                    crawl_log_data = CrawlLogCreate(
                        journal_name=journal_name,
                        crawl_start_time=datetime.now()
                    )
                    crawl_log = await CrawlLogCRUD.create_crawl_log(db, crawl_log_data)
                    crawl_log_id = crawl_log.id
                    await db.commit()
            except Exception as e:
                print(f"  [线程{self.thread_id}] 创建爬取日志失败: {e}")

            print(f"\n[线程{self.thread_id}] {'=' * 60}")
            print(f"[线程{self.thread_id}] 步骤8: 获取论文详情 - {journal_name}")
            print(f"[线程{self.thread_id}] {'=' * 60}")

            papers_history = HistoryManager.load_papers_history()
            journal_data = papers_history.get('papers', {}).get(journal_name, {})

            total_processed = 0
            total_papers = 0

            try:
                import sys
                sys.path.insert(0, str(BACKEND_DIR))

                from app.crud import PaperCRUD
                from app.database import AsyncSessionLocal

                async with AsyncSessionLocal() as db:
                    existing_urls = set(await PaperCRUD.get_all_paper_urls(db))
                    print(f"  [线程{self.thread_id}] 数据库中已有 {len(existing_urls)} 篇论文")
            except Exception as e:
                existing_urls = set()
                print(f"  [线程{self.thread_id}] 获取数据库已有论文失败: {e}")

            for year in sorted(journal_data.keys(), reverse=True):
                year_data = journal_data[year]
                for issue in sorted(year_data.keys(), reverse=True):
                    issue_data = year_data[issue]
                    papers_list = issue_data.get('papers', [])
                    total_papers += len(papers_list)

                    papers_to_process = [p for p in papers_list if p['url'] not in existing_urls]

                    if not papers_to_process:
                        print(f"  [线程{self.thread_id}] {year}年{issue}期: 所有论文已在数据库中，跳过")
                        continue

                    print(f"\n  [线程{self.thread_id}] {year}年{issue}期: 需要处理 {len(papers_to_process)}/{len(papers_list)} 篇论文")

                    for i, paper in enumerate(papers_to_process, 1):
                        print(f"\n  [线程{self.thread_id}] [{i}/{len(papers_to_process)}] {paper['title'][:50]}...")
                        detail = await self.crawl_paper_detail(paper, journal_name)

                        if 'error' not in detail:
                            total_processed += 1

                        await asyncio.sleep(random.uniform(3, 6))

            print(f"\n[线程{self.thread_id}] 期刊 {journal_name} 处理完成: {total_processed}/{total_papers} 篇论文")

            # 更新爬取日志为成功
            if crawl_log_id:
                try:
                    import sys
                    sys.path.insert(0, str(BACKEND_DIR))
                    from app.crud import CrawlLogCRUD
                    from app.database import AsyncSessionLocal
                    async with AsyncSessionLocal() as db:
                        await CrawlLogCRUD.update_crawl_log(
                            db, crawl_log_id,
                            crawl_end_time=datetime.now(),
                            papers_fetched=total_processed,
                            papers_failed=total_papers - total_processed,
                            status="completed"
                        )
                        await db.commit()
                except Exception as e:
                    print(f"  [线程{self.thread_id}] 更新爬取日志失败: {e}")

        except Exception as e:
            print(f"[线程{self.thread_id}] 处理期刊 {journal_name} 时出错: {e}")
            import traceback
            traceback.print_exc()

            # 更新爬取日志为失败
            if crawl_log_id:
                try:
                    import sys
                    sys.path.insert(0, str(BACKEND_DIR))
                    from app.crud import CrawlLogCRUD
                    from app.database import AsyncSessionLocal
                    async with AsyncSessionLocal() as db:
                        await CrawlLogCRUD.update_crawl_log(
                            db, crawl_log_id,
                            crawl_end_time=datetime.now(),
                            status="failed",
                            error_message=str(e)
                        )
                        await db.commit()
                except Exception:
                    pass

        finally:
            await self.close_browser()


class MultiThreadedCrawler:
    """多线程爬虫管理器"""

    def __init__(self, headless=True, max_workers=3):
        self.headless = headless
        self.max_workers = max_workers

    async def crawl_journals(self) -> dict:
        """获取期刊列表"""
        print("=" * 60)
        print("步骤1-3: 获取期刊列表")
        print("=" * 60)

        if HistoryManager.is_journals_cache_valid():
            print("发现有效的期刊历史记录，直接复用")
            history = HistoryManager.load_journals_history()
            return history['journals']

        print("未找到有效的期刊历史记录，开始爬取...")

        from playwright.async_api import async_playwright

        async with async_playwright().start() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            print("访问期刊导航页...")
            await page.goto(f'{BASE_URL}/knavi/journals/index', wait_until='domcontentloaded', timeout=60000)
            await asyncio.sleep(5)

            print("点击'经济与管理科学'按钮...")
            try:
                btn = await page.wait_for_selector('a[title="经济与管理科学"]', timeout=10000)
                if btn:
                    await btn.click()
                    await asyncio.sleep(5)
            except Exception as e:
                print(f"点击按钮失败: {e}")

            html = await page.content()
            soup = BeautifulSoup(html, 'lxml')

            result_div = soup.find('div', class_='result')
            if not result_div:
                print("未找到div.result")
                await browser.close()
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

            await browser.close()

        return journals

    def run_thread(self, journal_name: str, journal_info: dict, headless: bool, thread_id: int):
        """运行单个线程"""
        crawler = JournalCrawler(headless=headless, thread_id=thread_id)
        asyncio.run(crawler.process_journal(journal_name, journal_info))

    async def run(self):
        """运行多线程爬虫"""
        print("=" * 60)
        print(f"知网期刊爬虫 - 验证码自动解决版本 (线程数: {self.max_workers})")
        print(f"浏览器模式: {'无头' if self.headless else '显示窗口'}")
        if DDDDOCR_AVAILABLE:
            print("验证码解决: ddddocr 已启用")
        else:
            print("验证码解决: ddddocr 未安装，将使用手动模式")
        print("=" * 60)

        # 获取期刊列表（单线程）
        journals = await self.crawl_journals()
        if not journals:
            print("未获取到期刊列表，退出")
            return

        journal_list = list(journals.items())
        print(f"\n共 {len(journal_list)} 个期刊需要处理")
        print(f"使用 {self.max_workers} 个线程同时处理\n")

        # 使用线程池处理期刊
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = []
            for i, (journal_name, journal_info) in enumerate(journal_list):
                thread_id = i + 1
                future = executor.submit(
                    self.run_thread,
                    journal_name,
                    journal_info,
                    self.headless,
                    thread_id
                )
                futures.append(future)

            # 等待所有线程完成
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"线程执行出错: {e}")

        print("\n" + "=" * 60)
        print("所有期刊处理完成")
        print("=" * 60)


async def main():
    parser = argparse.ArgumentParser(description='知网期刊爬虫 - 验证码自动解决版本')
    parser.add_argument('--show-browser', action='store_true', help='显示浏览器窗口（默认不显示）')
    parser.add_argument('--threads', type=int, default=3, help='线程数/浏览器窗口数（默认3）')
    args = parser.parse_args()

    crawler = MultiThreadedCrawler(headless=not args.show_browser, max_workers=args.threads)
    await crawler.run()


if __name__ == '__main__':
    asyncio.run(main())
