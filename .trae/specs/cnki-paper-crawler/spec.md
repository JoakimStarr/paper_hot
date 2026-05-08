# 知网期刊爬虫重写

## Why
根据详细的知网期刊爬取方法文档，需要创建一个完整的爬虫，支持从知网期刊导航页获取期刊列表、年份期次、论文列表、论文详情，并保存到数据库。

## What Changes
- 新建 `cnki_paper.py` 文件，实现完整爬虫
- 支持期刊列表获取
- 支持年份/期次获取（2025、2026年）
- 支持论文列表获取
- 支持论文详情解析（标题、作者、摘要、关键词、DOI、专辑、专题、分类号等）
- 支持数据库存储

## Impact
- 新增文件: `cnki_paper.py`
- 依赖: `backend/app/crud.py`, `backend/app/models.py`, `backend/app/database.py`

## ADDED Requirements
### Requirement: 期刊列表获取
从知网期刊导航页 `https://navi.cnki.net/knavi/journals/index` 获取期刊列表。

#### Scenario: 成功获取
- **WHEN** 访问期刊导航页
- **THEN** 解析 `div.result a` 获取期刊名称和链接
- **AND** 保存为 `journals_list.json`

### Requirement: 期次列表获取
进入期刊详情页，获取年份和期次列表。

#### Scenario: 成功获取
- **WHEN** 访问期刊详情页
- **THEN** 解析 `div#YearIssueTree` 获取年份和期次
- **AND** 只获取 2025、2026 年的期次
- **AND** 通过点击 `span#larrow` 按钮遍历所有期次

### Requirement: 论文列表获取
获取某期次的所有论文列表。

#### Scenario: 成功获取
- **WHEN** 访问期次页面
- **THEN** 解析 `div#listbox a` 获取论文标题和链接

### Requirement: 论文详情解析
解析论文详情页的所有字段。

#### Scenario: 成功解析
- **WHEN** 访问论文详情页
- **THEN** 解析以下字段：
  - 标题：`div.doc h1`
  - 作者：`h3.author`
  - 摘要：`span.abstract-text`
  - 关键词：`p.keywords`
  - DOI、专辑、专题、分类号、在线公开时间：`div.row ul li` 中的 `span.rowtit` 和 `p`

### Requirement: 数据库存储
将获取的论文信息保存到数据库。

#### Scenario: 成功保存
- **WHEN** 获取到完整的论文详情
- **THEN** 使用 `PaperCRUD.create_paper_from_cnki()` 保存到数据库
- **AND** 包含所有字段：期刊、标题、作者、摘要、关键词、DOI、专辑、专题、分类号、链接
