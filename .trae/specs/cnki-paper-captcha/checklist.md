# 验证清单

## 文件创建
- [ ] `cnki_paper_captcha.py` 文件已创建，基于 `cnki_paper_threaded.py` 完整功能
- [ ] 文件头注释标注为验证码自动解决版本

## CaptchaSolver 类
- [ ] `CaptchaSolver` 类已定义，包含 ddddocr 实例初始化
- [ ] `detect_captcha_type()` 能区分滑块 / 点选验证码
- [ ] `solve_slider_captcha()` 能截取滑块图和背景图
- [ ] `solve_slider_captcha()` 调用 `slide_match()` 计算距离
- [ ] `solve_slider_captcha()` 使用 Playwright mouse API 模拟人类拖拽
- [ ] `solve_slider_captcha()` 验证拖动结果
- [ ] `solve_click_captcha()` 能获取提示文字
- [ ] `solve_click_captcha()` 调用 `detection()` 获取目标位置
- [ ] `solve_click_captcha()` 按顺序点击文字并验证结果

## wait_for_page_stable 改造
- [ ] 检测到验证码后调用自动解决策略（而非直接 fallback）
- [ ] 自动解决失败时有降级方案（非 headless 时手动解决）
- [ ] 重试计数器正确（最多 3 次）

## 人类行为模拟
- [ ] `human_drag_track()` 生成加速→匀速→减速轨迹
- [ ] 点击操作有随机位置偏移
- [ ] 操作间有合理随机延迟

## 非功能要求
- [ ] 不修改 `cnki_paper_threaded.py`
- [ ] 语法无错误，无新增 linter 警告
- [ ] `ddddocr` 可正常 import