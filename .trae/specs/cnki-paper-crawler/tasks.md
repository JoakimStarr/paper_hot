# 知网期刊爬虫实现任务

## [x] Task 1: 创建 cnki_paper.py 基础结构
- **Priority**: P0
- **Depends On**: None
- **Description**: 
  - 创建 `cnki_paper.py` 文件
  - 实现 `CNKIPaperCrawler` 类
  - 配置日志和常量
  - 实现 `_get_html()` HTTP请求方法（支持retry、timeout、headers、sleep）
- **Acceptance Criteria Addressed**: 期刊列表获取、HTTP请求
- **Test Requirements**:
  - `programmatic` TR-1.1: 文件可以正常导入，无语法错误
  - `programmatic` TR-1.2: `_get_html()` 能成功获取网页内容

## [x] Task 2: 实现期刊列表获取
- **Priority**: P0
- **Depends On**: Task 1
- **Description**: 
  - 实现 `_get_journals()` 方法
  - 访问 `https://navi.cnki.net/knavi/journals/index`
  - 解析 `div.result a` 获取期刊名称和链接
  - 实现 `_save_journals_list()` 和 `_load_journals_list()`
- **Acceptance Criteria Addressed**: 期刊列表获取
- **Test Requirements**:
  - `programmatic` TR-2.1: 能成功获取期刊列表
  - `programmatic` TR-2.2: 期刊列表正确保存到 `journals_list.json`

## [x] Task 3: 实现期次列表获取
- **Priority**: P0
- **Depends On**: Task 2
- **Description**: 
  - 实现 `_get_journal_issues()` 方法
  - 解析 `div#YearIssueTree` 获取年份和期次
  - 只获取 2025、2026 年的期次
  - 支持通过点击遍历所有期次
- **Acceptance Criteria Addressed**: 期次列表获取
- **Test Requirements**:
  - `programmatic` TR-3.1: 能成功获取期次列表
  - `programmatic` TR-3.2: 只包含 2025、2026 年的期次

## [x] Task 4: 实现论文列表获取
- **Priority**: P0
- **Depends On**: Task 3
- **Description**: 
  - 实现 `_get_issue_papers()` 方法
  - 解析 `div#listbox a` 获取论文标题和链接
- **Acceptance Criteria Addressed**: 论文列表获取
- **Test Requirements**:
  - `programmatic` TR-4.1: 能成功获取论文列表

## [x] Task 5: 实现论文详情解析
- **Priority**: P0
- **Depends On**: Task 4
- **Description**: 
  - 实现 `_get_paper_detail()` 方法
  - 实现 `_parse_paper_detail()` 方法
  - 拆分解析方法：`_parse_title()`、`_parse_authors()`、`_parse_abstract()`、`_parse_keywords()`、`_parse_meta()`
  - 解析所有字段：标题、作者、摘要、关键词、DOI、专辑、专题、分类号、在线公开时间
- **Acceptance Criteria Addressed**: 论文详情解析
- **Test Requirements**:
  - `programmatic` TR-5.1: 能成功解析论文详情
  - `programmatic` TR-5.2: 所有字段都能正确提取

## [x] Task 6: 实现数据库存储
- **Priority**: P0
- **Depends On**: Task 5
- **Description**: 
  - 实现 `_save_paper()` 方法
  - 使用 `PaperCRUD.create_paper_from_cnki()` 保存数据
  - 确保所有字段都保存到数据库
- **Acceptance Criteria Addressed**: 数据库存储
- **Test Requirements**:
  - `programmatic` TR-6.1: 论文能成功保存到数据库
  - `programmatic` TR-6.2: 所有字段都正确存储

## [x] Task 7: 实现主运行流程
- **Priority**: P0
- **Depends On**: Task 6
- **Description**: 
  - 实现 `run()` 方法
  - 流程：加载期刊列表 → 遍历期刊 → 获取期次 → 遍历期次 → 获取论文列表 → 遍历论文 → 获取详情 → 保存数据库
  - 添加适当的日志输出
- **Acceptance Criteria Addressed**: 完整爬虫流程
- **Test Requirements**:
  - `programmatic` TR-7.1: 完整流程能正常运行
  - `human-judgment` TR-7.2: 日志输出清晰，便于跟踪进度
