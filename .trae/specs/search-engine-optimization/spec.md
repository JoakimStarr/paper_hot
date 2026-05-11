# 搜索引擎优化 Spec

## Why
当前搜索功能存在多个严重逻辑缺陷：关键词点击后搜索的是全字段而非仅关键词字段；作者搜索使用 CAST+ILIKE 导致匹配不精确（子串误匹配、JSON结构干扰）；作者详情页使用 Python 内存过滤全表数据性能差且匹配逻辑脆弱；搜索建议端点使用 json_each 对脏数据容错差。

## What Changes
- **关键词搜索逻辑修复**：点击关键词标签时，后端使用 `json_each(keywords_cn)` 精确匹配关键词，而非 `CAST(keywords_cn AS TEXT) ILIKE`
- **作者搜索逻辑重写**：后端 `search_field=author` 改为使用 `json_each(authors)` 精确匹配作者名，而非 `CAST(authors AS TEXT) ILIKE`
- **作者详情页端点重写**：`/authors/{name}/papers` 改用 SQL `json_each` 在数据库层过滤，避免 Python 内存全表扫描
- **搜索建议端点增强**：添加作者名建议，修复 json_each 对异常 JSON 的容错
- **前端关键词点击跳转修复**：关键词标签点击跳转到搜索页时，确保使用 `search_field=keyword` 参数
- **搜索页增加作者搜索字段选项**：SearchBar 的搜索字段下拉框增加"作者"选项

## Impact
- Affected code: `backend/app/crud.py`（搜索查询逻辑）、`backend/app/api.py`（作者端点、搜索建议端点）、`frontend/src/components/PaperCard.tsx`（关键词点击）、`frontend/src/components/SearchBar.tsx`（搜索字段选项）、`frontend/src/app/search/page.tsx`（搜索参数传递）

## ADDED Requirements

### Requirement: 精确关键词搜索
系统 SHALL 在 `search_field=keyword` 时，使用 `json_each(keywords_cn)` 在数据库层精确匹配关键词值，而非对整个 JSON 字符串做 ILIKE 子串匹配。

#### Scenario: 用户点击关键词标签
- **WHEN** 用户在 PaperCard 上点击关键词标签（如"数字经济"）
- **THEN** 跳转到搜索页，仅返回 `keywords_cn` 中包含精确匹配"数字经济"的论文，不返回标题含"数字经济"但关键词不含的论文，也不返回关键词为"数字经济高质量发展"的论文（除非也精确包含"数字经济"）

### Requirement: 精确作者搜索
系统 SHALL 在 `search_field=author` 时，使用 `json_each(authors)` 在数据库层精确匹配作者名，而非对整个 JSON 字符串做 ILIKE 子串匹配。

#### Scenario: 用户按作者搜索
- **WHEN** 用户搜索作者"肖祖沔"
- **THEN** 返回所有作者列表中包含"肖祖沔"的论文（无论一作还是合作者），不返回作者名包含"肖"的其他论文

### Requirement: 作者详情页数据库层过滤
系统 SHALL 使用 SQL `json_each(authors)` 在数据库层过滤作者论文，而非加载全表到 Python 内存中过滤。

#### Scenario: 访问作者详情页
- **WHEN** 用户访问 `/author/肖祖沔`
- **THEN** 后端使用 SQL 查询过滤，返回该作者的所有论文，性能与普通分页查询一致

### Requirement: 搜索建议包含作者
系统 SHALL 在搜索建议中返回匹配的作者名，类型标记为 `author`。

#### Scenario: 用户输入作者名部分字符
- **WHEN** 用户在搜索框输入"肖祖"
- **THEN** 搜索建议中包含作者"肖祖沔"，标记为"作者"类型

### Requirement: 搜索栏支持作者搜索字段
系统 SHALL 在搜索字段下拉框中提供"作者"选项，允许用户指定按作者名搜索。

#### Scenario: 用户选择作者搜索字段
- **WHEN** 用户在搜索栏选择"作者"字段并输入名字
- **THEN** 搜索请求使用 `search_field=author` 参数

## MODIFIED Requirements

### Requirement: 关键词标签点击行为
关键词标签点击 SHALL 跳转到 `/search?search={keyword}&search_field=keyword`，确保搜索仅匹配关键词字段。

### Requirement: 搜索建议端点
`/search/suggest` 端点 SHALL 返回三种类型的建议：关键词（keyword）、标题（title）、作者（author），每种类型使用精确的数据库查询。
