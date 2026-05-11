# Tasks

- [x] Task 1: 删除旧版 GLMAnalyzer，统一分析服务
  - [x] SubTask 1.1: 修改 `api.py` 的 `get_ai_analysis_legacy`，内部调用 AITrendService 并返回 AIAnalysisResponse 格式
  - [x] SubTask 1.2: 删除 `glm_analyzer.py` 文件
  - [x] SubTask 1.3: 清理 `api.py` 中对 `glm_analyzer` 的导入

- [x] Task 2: 增强分析 Prompt — 添加子领域、TOP 论文、关键词共现
  - [x] SubTask 2.1: 修改 `_collect_papers_and_keywords`，增加子领域分布统计和 TOP 20 论文摘要
  - [x] SubTask 2.2: 修改 `ai_service.py` 的 `_build_structured_prompt`，在 prompt 中加入子领域分布、TOP 论文标题+摘要摘要、关键词共现信息
  - [x] SubTask 2.3: 确保 prompt 总长度不超过 GLM 上下文窗口限制

- [x] Task 3: 后台任务超时保护 + 僵尸记录清理
  - [x] SubTask 3.1: 在 `_run_analysis_background` 中添加 `asyncio.wait_for(timeout=120)` 超时保护
  - [x] SubTask 3.2: 在 `main.py` 的 startup 事件中添加僵尸记录清理逻辑
  - [x] SubTask 3.3: 超时后标记报告 status="failed"，error_message 记录超时信息

- [x] Task 4: JSON 解析增强
  - [x] SubTask 4.1: 在 `_call_glm_with_model` 中添加 `response_format={"type": "json_object"}` 参数
  - [x] SubTask 4.2: 改进 `_parse_structured_result` 的降级逻辑，区分 partial 和 failed 状态

- [x] Task 5: 前端轮询退避 + 冷却时间调整
  - [x] SubTask 5.1: 修改 `trends/page.tsx` 轮询逻辑，采用递增间隔（3s → 5s → 8s → 13s）
  - [x] SubTask 5.2: 将 `DEBOUNCE_SECONDS` 从 60 改为 300

- [x] Task 6: 历史报告列表 + 功能卡片改为锚点
  - [x] SubTask 6.1: 在趋势页 AI 分析区域下方添加可折叠的历史报告列表
  - [x] SubTask 6.2: 底部 3 个功能卡片改为可点击锚点，滚动到对应章节

- [x] Task 7: 重启服务并验证
  - [x] SubTask 7.1: 运行 `./stop.sh && ./start.sh`
  - [x] SubTask 7.2: 验证旧版接口仍可用
  - [x] SubTask 7.3: 验证增强 prompt 后分析结果包含子领域信息
  - [x] SubTask 7.4: 验证超时保护和僵尸清理
  - [x] SubTask 7.5: 验证前端轮询退避和历史报告列表

# Task Dependencies
- Task 1 必须先完成（删除旧服务后才能统一逻辑）
- Task 2 依赖 Task 1（在统一服务后增强 prompt）
- Task 3, Task 4 可并行（与 prompt 无关）
- Task 5, Task 6 可并行（纯前端修改）
- Task 7 依赖所有其他任务
