# Checklist

## 代码清理
- [x] 1.1 `frontend/src/lib/utils.ts` 文件存在，导出 `getIssuePeriod` 函数
- [x] 1.2 `frontend/src/lib/utils.ts` 导出 `topicColors` 常量
- [x] 1.3 `PaperCard.tsx` 不再定义本地 `getIssuePeriod` 和 `topicColors`，改为从 `@/lib/utils` 导入
- [x] 1.4 `paper/[id]/page.tsx` 不再定义本地 `getIssuePeriod` 和 `topicColors`，改为从 `@/lib/utils` 导入
- [x] 2.1 `network/page.tsx` 和 `NetworkGraph.tsx` 中不再使用 `(link.source as any).id` 类型断言，使用 `getLinkNodeId` 类型守卫

## 后端性能
- [x] 3.1 `get_system_stats` 查询次数从 8 次降至 3 次（使用子查询 + UNION ALL）
- [x] 4.1 `_collect_papers_and_keywords` 查询包含 `.limit(500)` 和 `.order_by(paper.published_at.desc())`
- [x] 5.1 `recompute_all_similarities` 每批最多处理 200 篇论文，循环 OFFSET/LIMIT
- [x] 6.1 `/network/authors` 端点使用 `json_each(authors)` 在 SQL 层展开+聚合

## 前端性能
- [x] 7.1 `NetworkGraph.tsx` tab 切换时保留 SVG/zoom/g 容器，使用 `initializedRef` 追踪
- [x] 8.1 D3 相关代码拆到 `NetworkGraph.tsx`，通过 `dynamic(() => import('./NetworkGraph'), { ssr: false })` 加载
- [x] 9.1 首页预取使用 `Promise.all([fetchPage(2), fetchPage(3)])` 并行执行
- [x] 10.1 `cache.ts` 包含 `MAX_ENTRIES = 50`、LRU 淘汰逻辑和 100KB 大小检查

## UX 改进
- [x] 11.1 `SkeletonCard.tsx` 组件存在且正确使用 `animate-pulse` 脉冲动画
- [x] 11.2 首页和搜索页在 loading 时显示 4 个 SkeletonCard 而非 spinner
- [x] 12.1 筛选器期刊下拉支持多选（MultiSelect checkbox 面板）
- [x] 12.2 筛选器学科下拉支持多选（MultiSelect checkbox 面板）
- [x] 12.3 后端 `get_papers` 支持逗号分隔的多值 `discipline`、`economics_subfield`、`journal_name` 参数
- [x] 13.1 PaperCard 右上角有可点击的收藏按钮（Bookmark 图标，收藏态黄色填充）
- [x] 13.2 收藏状态持久化到 localStorage（`pp_bookmarks` key）
- [x] 13.3 筛选器有"仅看收藏"复选框，支持前端按收藏列表过滤
- [x] 14.1 网络详情面板关联节点旁有 ExternalLink 按钮，点击跳转到搜索页
- [x] 15.1 趋势页面有时间范围选择器（1个月/3个月/6个月按钮组）
- [x] 16.1 分页组件有每页条数选择器（10/20/50 下拉）
- [x] 16.2 首页和搜索页支持切换 pageSize，切换时重置页码+清缓存

## Bug 修复
- [x] 17.1 趋势页面添加 `isMountedRef` 追踪卸载状态，setState 前检查
- [x] 17.2 `pollRef` 和 `cooldownRef` 在 cleanup 中正确清理

## 整体验证
- [x] V1 `npx next build --no-lint` 编译无错误
- [x] V2 `./stop.sh && ./start.sh` 服务正常启动
- [x] V3 `/health` 返回 healthy，`/api/papers` 正常返回论文，`/api/stats` 正常返回统计数据，前端 HTTP 200