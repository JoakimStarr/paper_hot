# 搜索页 Search Page Spec

## Why
当前关键词和期刊标签点击后跳转首页 `/?search=xxx`，搜索结果和首页浏览混在一起，用户体验割裂。需要一个独立的搜索页承载搜索功能和标签点击跳转结果。

## What Changes
- 新建 `/search` 页面路由
- 新建 `SearchBar` 组件（搜索框 + 搜索字段切换）
- 首页移除搜索框，仅保留筛选器（期刊、学科、评分）
- 所有关键词/期刊标签点击改为跳转 `/search?...` 而非 `/?...`
- Layout 导航栏新增搜索入口

## Impact
- Affected specs: 无
- Affected code: `frontend/src/app/search/page.tsx`（新建）、`frontend/src/components/PaperCard.tsx`、`frontend/src/app/paper/[id]/page.tsx`、`frontend/src/app/page.tsx`、`frontend/src/components/Filters.tsx`、`frontend/src/components/Layout.tsx`

## ADDED Requirements

### Requirement: 搜索页面
系统 SHALL 提供 `/search` 页面，接受 URL 查询参数并展示搜索结果。

#### Scenario: 通过关键词标签进入搜索页
- **WHEN** 用户在 PaperCard/论文详情页点击关键词标签
- **THEN** 跳转到 `/search?search=关键词&search_field=keyword`，展示包含该关键词的论文列表

#### Scenario: 通过期刊标签进入搜索页
- **WHEN** 用户在 PaperCard 点击期刊标签
- **THEN** 跳转到 `/search?journal=期刊名`，展示该期刊的全部论文

#### Scenario: 搜索页直接搜索
- **WHEN** 用户在搜索页输入关键词并按回车或点击搜索按钮
- **THEN** URL 更新为 `/search?search=xxx&search_field=keyword`，展示搜索结果

#### Scenario: 搜索字段切换
- **WHEN** 用户切换搜索字段（关键词/标题/全部）
- **THEN** `search_field` 参数对应更新为 `keyword`/`title`/`all`

#### Scenario: 无搜索结果
- **WHEN** 搜索无匹配结果
- **THEN** 显示 "未找到符合条件的论文" 提示，附带返回首页链接

### Requirement: 搜索栏组件
系统 SHALL 提供独立的 `SearchBar` 组件用于搜索页。

#### Scenario: 搜索栏渲染
- **WHEN** 渲染搜索栏
- **THEN** 包含输入框、搜索字段下拉、搜索按钮，支持回车搜索

### Requirement: 主页搜索功能迁移
系统 SHALL 从首页 Filters 移除搜索框，保持筛选功能。

#### Scenario: 首页筛选
- **WHEN** 用户访问首页
- **THEN** 仅显示期刊、学科、评分范围筛选器，无搜索输入框

## MODIFIED Requirements

### Requirement: 标签点击导航目标
**Before**: 关键词/期刊标签点击跳转 `/?search=xxx`
**After**: 跳转 `/search?search=xxx`

#### Scenario: PaperCard 关键词点击
- **WHEN** 点击论文卡片上的关键词标签
- **THEN** 导航到 `/search?search=KEYWORD&search_field=keyword`

#### Scenario: 论文详情页关键词点击
- **WHEN** 点击详情页的关键词标签
- **THEN** 导航到 `/search?search=KEYWORD&search_field=keyword`

#### Scenario: 相似论文章节关键词点击
- **WHEN** 点击相似论文列表中的关键词标签
- **THEN** 导航到 `/search?search=KEYWORD&search_field=keyword`

#### Scenario: 论文卡片期刊标签点击
- **WHEN** 点击 PaperCard 上的期刊标签
- **THEN** 导航到 `/search?journal=JOURNAL_NAME`