# Tasks

- [x] Task 1: 完善 PaperCRUD 的趋势数据查询方法
  - [x] 添加 `get_topic_weekly_counts()` 方法：按周和主题聚合论文数量
  - [x] 添加 `update_topic_trends()` 方法：批量更新 TopicTrend 表
  - [x] 添加 `bulk_update_paper_trend_scores()` 方法：批量重算论文 trend_score

- [x] Task 2: 实现 scheduler.update_trend_scores() 定时任务
  - [x] 实现真正的趋势计算逻辑（目前为空操作）
  - [x] 调用 `PaperCRUD` 的新方法填充 TopicTrend 表
  - [x] 重新计算论文的 trend_score
  - [x] 记录日志

- [x] Task 3: 完善 /trending-topics API
  - [x] 增强响应数据（返回更多信息）
  - [x] 按增长率过滤主题（上升/下降/稳定）
  - [x] 支持分页

- [x] Task 4: 完善 ScoringSystem.trend_score 计算
  - [x] 基于主题增长率计算 trend_score
  - [x] 使用平滑函数：0.5 + 0.5 * tanh(growth_rate)

- [x] Task 5: 测试验证
  - [x] 验证 PaperCRUD 新方法语法正确
  - [x] 验证 scheduler 更新逻辑语法正确
  - [x] 验证 API 端点语法正确
  - [x] 验证 ScoringSystem 语法正确
  - [x] 验证数据格式正确（当前论文无 topic 标签，数据为空是预期行为）

# Task Dependencies
- Task 2 依赖 Task 1
- Task 4 依赖 Task 1
- Task 3 无依赖
- Task 5 依赖 Task 1, Task 2, Task 4

# 并行化建议
- Task 1 必须先完成
- Task 2, Task 3, Task 4 可以在 Task 1 完成后并行实现