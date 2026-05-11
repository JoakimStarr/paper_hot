# 代码优化与UX改进 Spec

## Why
基于全面代码分析报告，当前程序存在多处代码重复、性能瓶颈、UX缺失和潜在bug，需要系统性地修复和优化以提升代码质量、性能和用户体验。

## What Changes

### 代码清理
- 提取 `getIssuePeriod` 公共工具函数，消除 PaperCard 与论文详情页的重复定义
- 提取 `topicColors` 常量到公共模块
- 网络页面 `connectedNodes` 解析 link.source/target 消除 `any` 类型断言

### 后端性能优化
- `get_system_stats` 合并 8 次独立查询为批量查询
- `_collect_papers_and_keywords` 添加 limit 防止全量加载 OOM
- 全量相似度重算支持分批处理，避免一次性加载全部论文到内存
- 作者网络 API 使用优化查询，避免加载完整 JSON 后在 Python 层截断

### 前端性能优化
- D3 力导向图支持数据更新而不完全重建 SVG
- 首页预取改为并行请求
- D3 库改为动态 import 减少首屏体积
- localStorage 缓存增加 LRU 淘汰和大小上限

### UX 改进
- 论文列表加载时显示骨架屏（Skeleton）
- 筛选器支持多选（期刊、学科可多选）
- 添加论文收藏/书签功能（localStorage 持久化）
- 关系网络节点点击支持跳转到关键词筛选搜索结果
- 趋势图表增加时间范围选择器（1月/3月/6月）
- 首页增加分页大小选择器（10/20/50条）

### Bug 修复
- 趋势页面轮询组件卸载时正确清理

## Impact
- Affected specs: 无已有 spec 受影响
- Affected code:
  - 后端: `api.py`, `crud.py`, `similarity.py`
  - 前端: `page.tsx`, `paper/[id]/page.tsx`, `search/page.tsx`, `network/page.tsx`, `trends/page.tsx`, `PaperCard.tsx`, `Filters.tsx`, `Pagination.tsx`, `cache.ts`, `api.ts`

## ADDED Requirements

### Requirement: 公共工具函数模块
系统 SHALL 提供 `frontend/src/lib/utils.ts` 公共工具模块，包含 `getIssuePeriod` 函数和 `topicColors` 常量。
- **WHEN** PaperCard 或论文详情页需要使用期号解析或主题颜色
- **THEN** 从 `@/lib/utils` 导入，不再各自定义

### Requirement: 骨架屏加载
系统 SHALL 在论文列表和搜索页加载时显示骨架屏替代纯 spinner。
- **WHEN** 页面处于 loading 状态且无缓存数据
- **THEN** 显示 4 个卡片骨架占位块（灰色脉冲动画），替代单一的 Loader2 spinner

### Requirement: 筛选器多选
系统 SHALL 支持期刊和学科的多选筛选。
- **WHEN** 用户选择多个期刊
- **THEN** 后端接收逗号分隔的 `journal_name` 参数，返回匹配任一选中期刊的论文
- **WHEN** 前端 Filters 组件渲染期刊列表
- **THEN** 使用多选下拉（checkbox 样式）替代单选 select

### Requirement: 论文收藏功能
系统 SHALL 提供论文收藏/书签功能。
- **WHEN** 用户点击 PaperCard 上的收藏按钮（心形/书签图标）
- **THEN** 论文 ID 存入 localStorage 收藏列表，图标变为实心
- **WHEN** 用户再次点击已收藏论文的按钮
- **THEN** 从收藏列表移除，图标恢复空心
- **WHEN** 用户在首页选择"仅看收藏"
- **THEN** 显示所有已收藏论文

### Requirement: 网络节点跳转
系统 SHALL 支持在网络详情面板点击关联节点名称跳转到搜索页。
- **WHEN** 用户在网络详情面板点击关联节点名称
- **THEN** 跳转到 `/search?search=节点名称&search_field=keyword`（关键词网络）或 `/search?search=节点名称&search_field=author`（作者网络）

### Requirement: 趋势时间范围选择
系统 SHALL 支持趋势图切换时间范围。
- **WHEN** 用户切换时间范围选择器（1月/3月/6月）
- **THEN** 趋势话题列表和图表按对应 `weeks_back` 参数（4/12/24）重新加载

### Requirement: 分页大小选择
系统 SHALL 在首页和搜索页底部分页区域提供每页条数选择器。
- **WHEN** 用户选择 10/20/50 条/页
- **THEN** 列表重新加载并显示对应数量论文，当前页码重置为第 1 页

## MODIFIED Requirements

### Requirement: 相似度重算分批处理
原一次性加载全部论文的 `recompute_all_similarities` SHALL 改为分批模式：每次处理最多 200 篇，使用 `OFFSET/LIMIT` 分批计算后再合并结果。

### Requirement: D3 网络图增量更新
D3 力导向图在 tab 切换时 SHALL 只更新 data 绑定和 simulation 数据，不销毁重建 SVG 容器和 zoom 行为。

### Requirement: D3 动态导入
D3 库 SHALL 通过 Next.js `dynamic(() => import(...))` 方式加载网络页面组件，d3 包不入首屏 bundle。

### Requirement: localStorage 缓存限制
localStorage 缓存 SHALL 添加条目数上限（50 条），超出时按 LRU 淘汰最早条目；单条缓存最大 100KB。

### Requirement: 首页预取并行化
首页预取 SHALL 使用 `Promise.all([fetchPage(2), fetchPage(3)])` 替代 `for` 循环串行请求。

### Requirement: 趋势轮询清理修复
趋势页面 SHALL 在 `useEffect` cleanup 中同时清理 `pollRef` 和 `cooldownRef`，防止组件卸载后 setState 警告。

### Requirement: 系统统计批量查询
`get_system_stats` SHALL 将 `total_papers`、`journal_count`、`keyword_count` 合并为一次查询（使用子查询），其余按需合并至最多 3 次查询。

### Requirement: 数据收集添加限制
`_collect_papers_and_keywords` SHALL 添加 `.limit(500)` 硬限制，论文总数超过 500 时只取最新 500 篇用于 AI 分析。

### Requirement: 作者网络查询优化
作者网络 API SHALL 使用 SQL 层 `json_each` 展开 authors JSON 后再聚合，替代全量加载后在 Python 层循环解析。