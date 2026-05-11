# Tasks

- [x] Task 1: 重写后端搜索查询逻辑 — 使用 json_each 精确匹配关键词和作者
  - [x] SubTask 1.1: 修改 `crud.py` 的 `get_papers` 方法，`search_field=keyword` 时使用 `json_each(keywords_cn)` 精确匹配
  - [x] SubTask 1.2: 修改 `crud.py` 的 `get_papers` 方法，`search_field=author` 时使用 `json_each(authors)` 精确匹配
  - [x] SubTask 1.3: 验证 `search_field=all` 时仍搜索标题和摘要

- [x] Task 2: 重写作者详情页端点 — 使用 SQL json_each 替代 Python 内存过滤
  - [x] SubTask 2.1: 修改 `/authors/{name}/papers` 端点，使用 `json_each(authors)` SQL 过滤
  - [x] SubTask 2.2: 保留分页和 JOIN paper_features/paper_scores 逻辑

- [x] Task 3: 增强搜索建议端点 — 添加作者名建议
  - [x] SubTask 3.1: 在 `/search/suggest` 端点添加 `json_each(authors)` 查询匹配作者名
  - [x] SubTask 3.2: 返回作者建议时标记类型为 `author`，并统计该作者的论文数

- [x] Task 4: 前端搜索栏增加"作者"搜索字段选项
  - [x] SubTask 4.1: 在 `SearchBar.tsx` 的 `SEARCH_FIELDS` 数组中添加 `{ value: 'author', label: '作者' }`
  - [x] SubTask 4.2: 在搜索建议下拉中添加"作者"类型标签样式（橙色）

- [x] Task 5: 验证关键词标签点击跳转逻辑
  - [x] SubTask 5.1: 确认 `PaperCard.tsx` 关键词点击跳转使用 `search_field=keyword`
  - [x] SubTask 5.2: 确认搜索页正确读取并传递 `search_field` 参数

- [x] Task 6: 重启服务并端到端验证
  - [x] SubTask 6.1: 运行 `./stop.sh && ./start.sh`
  - [x] SubTask 6.2: 验证关键词搜索精确匹配
  - [x] SubTask 6.3: 验证作者搜索精确匹配
  - [x] SubTask 6.4: 验证作者详情页显示所有论文
  - [x] SubTask 6.5: 验证搜索建议包含作者

# Task Dependencies
- Task 2 depends on Task 1 (共享 json_each 查询模式)
- Task 3 depends on Task 1 (共享 json_each 查询模式)
- Task 4 is independent of backend tasks
- Task 5 is independent of backend tasks
- Task 6 depends on all other tasks
