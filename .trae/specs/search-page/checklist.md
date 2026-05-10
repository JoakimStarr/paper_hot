# Checklist

- [x] SearchBar 组件正确渲染输入框、字段下拉、搜索按钮
- [x] SearchBar 支持回车触发搜索
- [x] /search 页面可通过 URL 直接访问
- [x] /search?search=KEYWORD&search_field=keyword 正确展示关键词搜索结果
- [x] /search?journal=JOURNAL_NAME 正确展示期刊筛选结果
- [x] 搜索页支持分页浏览结果
- [x] 无搜索结果时显示空状态提示和返回首页链接
- [x] PaperCard 关键词标签点击跳转到 /search?search=...&search_field=keyword
- [x] PaperCard 期刊标签点击跳转到 /search?journal=...
- [x] 论文详情页顶部关键词点击跳转到 /search?search=...&search_field=keyword
- [x] 论文详情页信息区关键词点击跳转到 /search?search=...&search_field=keyword
- [x] 相似论文关键词点击跳转到 /search?search=...&search_field=keyword
- [x] 首页不再显示搜索输入框和搜索字段下拉
- [x] 首页期刊/学科/评分筛选功能正常
- [x] Filters 组件不再接收搜索相关 props
- [x] Layout 导航栏包含搜索入口链接
- [x] 前端 `npm run build` 无报错