# AI 趋势分析优化 Spec

## Why
当前 AI 趋势分析存在两套重复服务、分析 prompt 信息量不足（不含论文摘要和子领域分布）、后台任务无超时保护导致僵尸记录、JSON 解析脆弱、前端轮询无退避策略等问题，严重影响分析质量和系统稳定性。

## What Changes
- **删除旧版 GLMAnalyzer**：统一使用 AITrendService，旧接口 `/ai-analysis` 内部转发到 V2 逻辑
- **增强分析 prompt**：加入子领域分布、TOP 论文标题+摘要摘要、关键词共现信息
- **后台任务超时保护**：添加 `asyncio.wait_for(timeout=120)` 和启动时清理僵尸记录
- **JSON 解析增强**：使用 `response_format` 参数强制 JSON 输出，改进降级逻辑
- **前端轮询退避**：采用递增间隔策略（3s → 5s → 8s → 13s）
- **冷却时间调整**：从 60 秒增加到 300 秒
- **历史报告入口**：前端添加可展开的历史报告列表
- **静态功能卡片**：改为可点击锚点链接到对应分析章节

## Impact
- Affected code: `backend/app/glm_analyzer.py`（删除）、`backend/app/ai_service.py`（增强 prompt+超时）、`backend/app/api.py`（旧接口转发+僵尸清理）、`frontend/src/app/trends/page.tsx`（轮询退避+历史报告+卡片链接）
- Affected specs: implement-trend-analysis（兼容，不破坏已有功能）

## ADDED Requirements

### Requirement: 统一 AI 分析服务
系统 SHALL 仅使用 `AITrendService` 作为 AI 分析服务，删除 `GLMAnalyzer`。旧版 `/ai-analysis` 接口 SHALL 内部调用 V2 逻辑并返回兼容格式。

#### Scenario: 调用旧版接口
- **WHEN** 用户调用 `GET /api/ai-analysis`
- **THEN** 系统使用 AITrendService 执行分析，返回 AIAnalysisResponse 格式

### Requirement: 增强分析 Prompt
系统 SHALL 在分析 prompt 中包含以下额外信息：
1. 子领域（economics_subfield）分布统计
2. TOP 20 论文的标题和摘要前 100 字
3. 关键词共现 TOP 10 对（在相同论文中同时出现的关键词对）

#### Scenario: 分析数据包含子领域信息
- **WHEN** AI 分析任务执行
- **THEN** prompt 中包含子领域分布统计，AI 可以基于此分析各领域研究热度

### Requirement: 后台任务超时保护
系统 SHALL 对后台分析任务设置 120 秒超时。超时后自动标记为 "failed"。

#### Scenario: 分析任务超时
- **WHEN** 后台分析任务执行超过 120 秒
- **THEN** 任务自动终止，报告状态标记为 "failed"，error_message 记录超时信息

### Requirement: 僵尸记录清理
系统 SHALL 在启动时检查并清理超过 10 分钟仍在 "running" 状态的报告记录。

#### Scenario: 服务重启后清理僵尸记录
- **WHEN** 后端服务启动
- **THEN** 所有 created_at 超过 10 分钟且 status="running" 的记录被标记为 "failed"

### Requirement: 前端轮询退避
前端 SHALL 采用递增间隔轮询策略：3s → 5s → 8s → 13s → 13s（上限）。

#### Scenario: 长时间分析中的轮询
- **WHEN** 分析任务运行超过 10 秒
- **THEN** 轮询间隔从 3 秒逐步增加到 13 秒上限

### Requirement: 历史报告列表
前端 SHALL 在趋势页展示可折叠的历史报告列表，调用 `/api/ai-analysis/reports` 获取数据。

#### Scenario: 查看历史报告
- **WHEN** 用户点击"历史报告"折叠面板
- **THEN** 展示最近 10 条报告的摘要、时间、模型信息，可点击查看详情

## MODIFIED Requirements

### Requirement: 冷却时间
分析完成后的冷却等待时间从 60 秒修改为 300 秒。

### Requirement: 静态功能卡片
趋势页底部的 3 个功能卡片（热点预测/关键词关联/发展趋势）从纯静态展示改为可点击锚点，点击后滚动到对应的分析章节。

## REMOVED Requirements

### Requirement: GLMAnalyzer 旧版分析服务
**Reason**: 与 AITrendService 功能重复，且配置不一致（max_tokens/temperature 不同），维护成本高
**Migration**: 旧版 `/ai-analysis` 接口内部转发到 V2 逻辑，返回兼容格式
