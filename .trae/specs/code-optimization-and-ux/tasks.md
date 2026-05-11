# Tasks

## 第1组：代码清理（可并行）

- [x] 1. 创建公共工具模块 `frontend/src/lib/utils.ts`
  - 从 `PaperCard.tsx` 提取 `getIssuePeriod` 函数和 `topicColors` 常量到 `utils.ts`
  - 在 `PaperCard.tsx` 和 `paper/[id]/page.tsx` 中删除本地定义，改为从 `@/lib/utils` 导入

- [x] 2. 修复网络页面 `connectedNodes` 的类型安全
  - 在 `network/page.tsx` 中为 link.source 和 link.target 添加类型守卫函数 `getLinkNodeId(link, direction)`，消除 `(link.source as any).id` 断言

## 第2组：后端性能优化（可并行）

- [x] 3. 优化 `get_system_stats` 查询
  - 合并 `total_papers`、`journal_count`、`keyword_count` 为一次 SQL 查询
  - 用子查询或 CTE 实现，目标从 8 次查询降至 ≤3 次

- [x] 4. `_collect_papers_and_keywords` 添加限制
  - 在查询中添加 `.limit(500)`，防止论文数量增长后 OOM

- [x] 5. 相似度重算支持分批
  - 修改 `recompute_all_similarities`（api.py）和 `compute_all_similarities`（similarity.py）
  - 每次用 `OFFSET/LIMIT` 取 200 篇，分批计算后合并

- [x] 6. 作者网络 API 查询优化
  - 修改 `/network/authors` 端点，使用 SQL 级 `json_each(authors)` 展开后再聚合，替代全量加载 JSON 到 Python 循环

## 第3组：前端性能优化（可并行）

- [x] 7. D3 网络图增量更新
  - 修改 `network/page.tsx` 的 graph useEffect，tab 切换时保留 SVG/zoom/g 容器，只更新 nodes/links data 和 simulation

- [x] 8. D3 动态导入
  - 将 `network/page.tsx` 中 D3 相关代码拆分为动态加载组件
  - 用 `next/dynamic` 包装 NetworkPage，`ssr: false`，d3 不入首屏 bundle

- [x] 9. 首页预取并行化
  - 修改 `page.tsx` 中预取逻辑，把 `for` 循环改为 `Promise.all([fetchPage(2), fetchPage(3)])`

- [x] 10. localStorage 缓存限制
  - 修改 `cache.ts`：添加 `MAX_ENTRIES = 50` 和 LRU 淘汰逻辑
  - 添加单条缓存大小检查（超 100KB 不缓存）

## 第4组：UX 改进（可并行）

- [x] 11. 骨架屏加载
  - 创建 `components/SkeletonCard.tsx` 骨架屏组件
  - 在 `page.tsx` 和 `search/page.tsx` 中用骨架屏替代 loader spinner

- [x] 12. 筛选器多选
  - 修改 `Filters.tsx`：期刊/学科下拉改为多选 checkbox 面板
  - 修改 `page.tsx`：`selectedJournal`、`selectedDiscipline` 改为数组类型
  - 修改后端 `get_papers`（crud.py）：`journal_name` 和 `discipline` 参数支持逗号分隔多值

- [x] 13. 论文收藏功能
  - 在 `PaperCard.tsx` 添加收藏按钮（心形图标），点击切换收藏状态
  - 在 `cache.ts` 添加收藏相关函数：`getBookmarks`、`toggleBookmark`、`isBookmarked`
  - 在 `Filters.tsx` 添加"仅看收藏"复选框
  - 在 `page.tsx` 添加收藏筛选逻辑（从 localStorage 读取收藏 ID，前端过滤或传给后端）

- [x] 14. 网络节点名称点击跳转
  - 修改 `network/page.tsx` 详情面板：关联节点名称改为 `<Link>` 或 `router.push`
  - 关键词网络：跳转 `/search?search=名称&search_field=keyword`
  - 作者网络：跳转 `/search?search=名称&search_field=author`

- [x] 15. 趋势时间范围选择器
  - 在 `trends/page.tsx` 添加时间范围下拉/按钮组（1月/3月/6月）
  - 选中值驱动 `weeks_back` 参数（4/12/24）传递给 `getTrendingTopics`
  - TrendChart 同步更新

- [x] 16. 分页大小选择器
  - 在 `Pagination.tsx` 组件添加"每页条数"选择器（10/20/50）
  - 通过 props 回调触发父组件更新 `pageSize`
  - `page.tsx` 和 `search/page.tsx` 使用 `PAGE_SIZE` 状态替代常量

## 第5组：Bug 修复

- [x] 17. 修复趋势轮询清理
  - 在 `trends/page.tsx` 中确保 `useEffect` cleanup 同时清理 `pollRef` 和 `cooldownRef`
  - 使用 `useRef` 追踪组件是否已卸载（`isMountedRef`），在 setState 前检查

# Task Dependencies

- 任务 1-2（代码清理）：无依赖，可与其他所有任务并行
- 任务 3-6（后端优化）：无依赖，可与其他所有任务并行
- 任务 7-10（前端性能）：无依赖，可与其他所有任务并行
- 任务 11-16（UX 改进）：无依赖，可与其他所有任务并行
- 任务 17（Bug 修复）：无依赖，可独立执行