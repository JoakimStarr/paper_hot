# 知网爬虫验证码自动解决版本 Spec

## Why

现有 `cnki_paper_threaded.py` 遇到验证码时只能等待用户手动解决（无头模式下直接失败），无法在无头模式下自动完成爬取。需要新建一个携带自动验证码解决能力的版本，使用 `ddddocr` 库自动识别并突破知网的两类验证码：滑块验证码（期刊论文链接页面）和文字点选验证码（论文详情页面）。

## What Changes

* 新建 `cnki_paper_captcha.py`，基于 `cnki_paper_threaded.py` 完整功能 + 验证码自动解决模块

* 集成 `ddddocr` 库（`pip install ddddocr`）

* 实现滑块验证码自动识别与拖动（用于期刊页面/论文链接页面）

* 实现文字点选验证码自动识别与点击（用于论文详情页面）

* 保留手动降级方案：自动识别失败时 fallback 到等待手动解决

* 不修改已有文件（`cnki_paper_threaded.py` 保持不变）

## Impact

* 新建文件：`cnki_paper_captcha.py`

* 新增依赖：`ddddocr`、`Pillow`（ddddocr 内部依赖）

* 受影响的已有规范：无（新增文件，不影响现有代码）

***

## ADDED Requirements

### Requirement: Slider Captcha Auto-Solve

系统 SHALL 在访问知网期刊页面触发了滑块验证码时，自动截取滑块图和背景图，利用 ddddocr 的 `slide_match()` 方法计算滑块移动距离，并通过 Playwright 模拟人类拖动行为完成验证。

#### Scenario: 期刊页面触发滑块验证码

* **WHEN** 页面跳转到 `https://kns.cnki.net/verify/` 且页面内容包含滑块验证码元素

* **THEN** 系统自动截取滑块图和背景图，计算滑动距离，模拟拖动

* **AND** 验证通过后继续原流程

#### Scenario: 滑块识别失败降级

* **WHEN** 滑块验证码识别失败（多次尝试后仍无法通过）

* **THEN** 如果非 headless 模式，fallback 到等待用户手动解决

* **AND** 如果 headless 模式，记录失败日志并跳过当前操作

### Requirement: Text-Click Captcha Auto-Solve

系统 SHALL 在访问论文详情页面触发了文字点选验证码时，自动截取验证码图片，利用 ddddocr 的 `detection()` 目标检测方法定位可点击文字位置，结合 OCR 识别提示文字，并按顺序点击验证码中的对应文字。

#### Scenario: 论文详情页触发点选验证码

* **WHEN** 页面跳转到验证码页面且页面内容包含文字点选验证码元素

* **THEN** 系统自动识别提示文字和可点击区域，按顺序点击

* **AND** 验证通过后继续获取论文详情

#### Scenario: 点选验证码识别失败降级

* **WHEN** 点选验证码识别失败（多次尝试后仍无法通过）

* **THEN** 如果非 headless 模式，fallback 到等待用户手动解决

* **AND** 如果 headless 模式，记录失败日志并跳过当前论文

### Requirement: Captcha Detection

系统 SHALL 在 `wait_for_page_stable()` 中正确检测验证码页面，并能区分是滑块验证码还是点选验证码，以便调用对应的解决策略。

#### Scenario: 识别验证码类型

* **WHEN** 检测到当前 URL 为 `/verify/` 路径

* **THEN** 分析页面 DOM 判断是滑块还是点选类型

* **AND** 调用对应的 `solve_slider_captcha()` 或 `solve_click_captcha()`

### Requirement: Captcha Retry and Cool-down

系统 SHALL 在每次验证码解决失败后等待冷却时间再重试，最多重试 N 次，防止频繁失败触发更严格的反爬机制。

#### Scenario: 多次重试失败后放弃

* **WHEN** 同一操作连续 3 次触发验证码

* **THEN** 系统放弃当前操作，记录错误日志

* **AND** 继续处理下一项任务

***

## 技术方案

### 依赖

```
ddddocr>=1.5.0   # 验证码识别核心库
Pillow           # 图像处理（ddddocr 会依赖）
```

### 滑块验证码流程

1. 检测到验证码页面 → 分析 DOM 确认是滑块类型
2. 截取滑块小图（`.slider` / 可拖拽元素截图）
3. 截取背景大图（背景缺口图片截图）
4. 调用 `ddddocr.DdddOcr(det=False, ocr=False).slide_match(target_bytes, background_bytes, simple_target=True)`
5. 获取滑动距离 `res['target'][0]`
6. 用 Playwright `mouse.move()` + `mouse.down()` + `mouse.move()` + `mouse.up()` 模拟人类拖拽轨迹
7. 验证拖动结果（检查页面是否跳转回正常页面）

### 点选验证码流程

1. 检测到验证码页面 → 分析 DOM 确认是点选类型
2. 识别提示文字（如"请依次点击【知】【网】"）
3. 截取带文字的区域图片
4. 调用 `ddddocr.DdddOcr(det=True).detection(image_bytes)` 获取所有可点击文字区域的 bbox
5. 结合 OCR 识别每个 bbox 内的文字
6. 按提示文字顺序依次点击对应位置（带随机延迟模拟人类）
7. 验证点击结果

### 人类行为模拟

* 滑块拖动添加随机轨迹偏移（加速→匀速→减速）

* 点击操作添加随机位置偏移和延迟

* 两次验证码触发之间添加较长冷却等待

