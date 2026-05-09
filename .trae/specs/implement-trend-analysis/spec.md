# 趋势分析功能实现 Spec

## Why
当前系统已有论文评分中的 `trend_score` 计算（关键词频率变化趋势），但"趋势分析"页面所需的核心数据（TopicTrend 表）从未被填充，导致 `/trending-topics` API 返回空数据，趋势分析页面无法展示。

## What Changes
- 修复 `scheduler.update_trend_scores()` 定时任务，让其真正计算并填充 `TopicTrend` 表
- 每周按主题聚合论文数量，计算增长率
- 为论文重新计算 `trend_score`（基于主题趋势）
- 完善前端趋势分析页面

## Impact
- 受影响文件：`backend/app/scheduler.py`、`backend/app/scoring.py`、`backend/app/crud.py`
- 新增/修改功能：趋势数据聚合、趋势评分重算、前端趋势图表

---

## ADDED Requirements

### Requirement: TopicTrend 定时聚合
系统 SHALL 每 6 小时运行一次定时任务，统计每个主题在过去 N 周的论文数量，计算增长率，并存储到 `TopicTrend` 表。

#### Scenario: 每周主题趋势计算
- **WHEN** 定时任务触发（每 6 小时）
- **THEN** 计算过去 4 周内每周各主题的论文数量
- **AND** 计算增长率：`(本周论文数 - 上周论文数) / 上周论文数`
- **AND** 更新 `TopicTrend` 表

### Requirement: 论文趋势分数重算
系统 SHALL 在主题趋势计算完成后，重新计算每篇论文的 `trend_score`，基于其所属主题的增长率。

#### Scenario: 趋势分数更新
- **WHEN** 主题趋势数据更新后
- **THEN** 获取论文的主题标签
- **AND** 查询该主题的最新增长率
- **AND** 更新 `PaperScore.trend_score`

### Requirement: 热门主题列表
系统 SHALL 提供 `/trending-topics` API，返回增长率最高的主题列表及其统计数据。

#### Scenario: 获取热门主题
- **WHEN** 前端请求 `/trending-topics?weeks_back=4`
- **THEN** 返回增长率 > 20% 的上升主题
- **AND** 返回增长率 < -10% 的下降主题
- **AND** 按增长率排序

---

## MODIFIED Requirements

### Requirement: update_trend_scores 定时任务
scheduler.py 中的 `update_trend_scores()` 方法目前为空操作，需要实现真正的趋势计算逻辑。

**原逻辑**：仅打印日志
**新逻辑**：
1. 查询过去 N 周的论文，按周聚合
2. 按主题聚合论文数量
3. 计算每个主题的周增长率
4. 存储到 `TopicTrend` 表
5. 重新计算论文的 `trend_score`

---

## 技术方案

### 数据流程
```
定时任务触发 (每6小时)
    ↓
查询近4周论文，按 (周, 主题) 聚合
    ↓
计算周增长率
    ↓
更新 TopicTrend 表
    ↓
更新 PaperScore.trend_score
```

### 增长率算法详细设计

#### 1. 数据来源
- **主表**: `papers` 表的 `published_at` 字段（发布时间）
- **主题表**: `paper_features` 表的 `topic` 字段（AI 分类的主题标签）
- **聚合维度**: 按周聚合，每周一作为周起始日

#### 2. 数据聚合逻辑
```sql
-- 示例查询
SELECT 
    topic,
    DATE_TRUNC('week', published_at) as week_start,
    COUNT(*) as paper_count
FROM papers p
JOIN paper_features pf ON p.id = pf.paper_id
WHERE published_at >= NOW() - INTERVAL '4 weeks'
  AND topic IS NOT NULL
GROUP BY topic, DATE_TRUNC('week', published_at)
ORDER BY topic, week_start
```

#### 3. 增长率计算公式
**周增长率**（Week-over-Week Growth Rate）：
```
growth_rate = (current_week_count - previous_week_count) / previous_week_count

特殊情况处理：
- 如果 previous_week_count = 0 且 current_week_count > 0：growth_rate = 1.0（100%增长）
- 如果 previous_week_count = 0 且 current_week_count = 0：growth_rate = 0.0（无变化）
- 如果 growth_rate > 10：截断为 10.0（避免极端值）
- 如果 growth_rate < -1：截断为 -1.0（避免极端值）
```

#### 4. 平滑处理（可选）
为了避免单周数据波动过大，可以使用 **3周移动平均**：
```
smoothed_growth = (week1_growth * 0.2 + week2_growth * 0.3 + week3_growth * 0.5)
```

#### 5. 趋势状态判定
- **rising（上升）**: growth_rate > 0.2（增长率 > 20%）
- **stable（稳定）**: -0.1 <= growth_rate <= 0.2（-10% 到 20% 之间）
- **declining（下降）**: growth_rate < -0.1（下降率 > 10%）

### TopicTrend 表填充
- 每周聚合一次：`GROUP BY topic, DATE_TRUNC('week', published_at)`
- 存储字段：topic, week_start, paper_count, growth_rate
- 更新策略：先删除该周的旧数据，再插入新数据

### 论文 trend_score 重算
- 从 `TopicTrend` 表获取主题最新增长率
- 使用 Sigmoid 平滑函数将增长率映射到 0-1 分数：
  ```
  trend_score = 0.5 + 0.5 * tanh(growth_rate)
  
  示例：
  - growth_rate = 0（无增长）→ trend_score = 0.5
  - growth_rate = 1（100%增长）→ trend_score = 0.88
  - growth_rate = -0.5（下降50%）→ trend_score = 0.27
  ```

### API 响应优化
- 增加更多元数据（周开始/结束时间、论文总数等）
- 支持按增长率过滤（上升/下降/稳定）
- 返回 TOP N 主题