# Tasks

- [x] Task 1: 创建 SearchBar 组件
  - [x] 在 `frontend/src/components/SearchBar.tsx` 新建组件
  - [x] 包含搜索输入框、搜索字段下拉（关键词/标题/全部）、搜索按钮
  - [x] 支持回车触发搜索
  - [x] 接收 `initialQuery`, `initialField` props 初始化
  - [x] 提交时调用 `onSearch(query, field)` 回调

- [x] Task 2: 创建 /search 页面
  - [x] 新建 `frontend/src/app/search/page.tsx`
  - [x] 使用 `useSearchParams()` 读取 `search`, `search_field`, `journal` 参数
  - [x] 集成 SearchBar 组件
  - [x] 根据参数调用 API 获取论文列表（复用现有搜索 API）
  - [x] 支持分页
  - [x] 无结果时显示空状态提示 + 返回首页链接
  - [x] 搜索/标签点击时 URL 更新（`router.push` 或 `router.replace`）

- [x] Task 3: 更新 PaperCard 标签导航目标
  - [x] 修改 `frontend/src/components/PaperCard.tsx`
  - [x] 关键词标签点击 → `router.push('/search?search=KEYWORD&search_field=keyword')`
  - [x] 期刊标签点击 → `router.push('/search?journal=JOURNAL_NAME')`

- [x] Task 4: 更新论文详情页标签导航目标
  - [x] 修改 `frontend/src/app/paper/[id]/page.tsx`
  - [x] 顶部关键词区域点击 → `/search?search=KEYWORD&search_field=keyword`
  - [x] 详情信息区关键词点击 → `/search?search=KEYWORD&search_field=keyword`
  - [x] 相似论文关键词点击 → `/search?search=KEYWORD&search_field=keyword`

- [x] Task 5: 更新首页，移除搜索框
  - [x] 修改 `frontend/src/app/page.tsx`
  - [x] 移除搜索框相关 state 和逻辑（`searchQuery`, `searchField`, `handleSearchSubmit` 等）
  - [x] 移除传给 Filters 的搜索相关 props
  - [x] 保留期刊、学科、评分的筛选逻辑

- [x] Task 6: 更新 Filters 组件
  - [x] 修改 `frontend/src/components/Filters.tsx`
  - [x] 移除 `searchQuery`, `searchField`, `onSearchChange`, `onSearchSubmit`, `onSearchFieldChange` props
  - [x] 移除搜索输入框和搜索字段下拉的 UI

- [x] Task 7: 更新 Layout 导航栏
  - [x] 修改 `frontend/src/components/Layout.tsx`
  - [x] 在导航链接中添加"搜索"入口，链接到 `/search`

# Task Dependencies
- Task 2 依赖 Task 1（搜索页需要 SearchBar 组件）
- Task 3, 4, 5, 6, 7 可并行进行