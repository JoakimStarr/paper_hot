# Debug Session: playwright-start-error

**Status:** [OPEN]
**Created:** 2026-07-06
**Bug:** `TypeError: 'coroutine' object does not support the asynchronous context manager protocol`
**File:** cnki_paper_captcha.py:1645

## Symptoms
- 运行 `python cnki_paper_captcha.py --show-browser --threads 6` 报错
- 错误位置：`async with async_playwright().start() as playwright:`
- 警告：`coroutine 'PlaywrightContextManager.start' was never awaited`

## Hypotheses

### H1: Playwright API 调用方式错误
- **假设**: `async_playwright().start()` 已经返回 coroutine，不应该再使用 `async with` 包装
- **观察点**: 标准用法应该是 `async with async_playwright() as playwright:`（不需要 .start()）
- **状态**: 待验证

### H2: Playwright 版本兼容性问题
- **假设**: 某些版本的 playwright 中 `start()` 方法返回的是 coroutine 而不是 async context manager
- **观察点**: 检查 playwright 版本及 API
- **状态**: 待验证

### H3: 代码混合了同步/异步 API
- **假设**: `async_playwright().start()` 实际返回 coroutine，应该 await 而不是 async with
- **观察点**: 错误信息显示 `coroutine 'PlaywrightContextManager.start' was never awaited`
- **状态**: 待验证（错误信息强烈支持此假设）

## Root Cause Analysis

错误信息明确指出：
1. `coroutine 'PlaywrightContextManager.start' was never awaited` - 警告
2. `TypeError: 'coroutine' object does not support the asynchronous context manager protocol` - 主错误

**根本原因**: `async_playwright().start()` 在新版 Playwright 中返回 coroutine，不能直接用 `async with`。
正确用法是 `async with async_playwright() as playwright:` （去掉 .start()）

## Fix Plan

将第 1645 行：
```python
async with async_playwright().start() as playwright:
```
改为：
```python
async with async_playwright() as playwright:
```

## Verification
- [ ] 修复后运行 `python cnki_paper_captcha.py --show-browser --threads 6`
- [ ] 确认无 TypeError
- [ ] 确认无 RuntimeWarning

## Cleanup
- [ ] 删除 debug 文件
