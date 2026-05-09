# 知网爬虫问题分析 Spec

## Why
系统现有的两个知网爬虫文件（`cnki_paper.py` 单线程版、`cnki_paper_threaded.py` 多线程版）存在多处逻辑缺陷、代码错误、功能缺失以及与后端集成不完整的问题，需要系统梳理以便后续修复。

## What Changes（本 spec 为纯分析文档，不涉及代码修改）
- 全面分析两个爬虫文件存在的问题
- 分析 `import_papers_to_db.py` 的问题
- 分析与后端（scheduler、scoring、ai_processor）的集成缺失
- 列出未实现的功能
- 不修改任何代码

## Impact
- 受影响版本：`cnki_paper.py`（单线程版）、`cnki_paper_threaded.py`（多线程版）、`import_papers_to_db.py`
- 受影响的后端集成：scheduler、scoring、ai_processor、CrawlLog

---

## 问题分类

### A. 【严重】多线程版本缺少 `paper_details_history` 持久化机制

#### 描述
`cnki_paper.py` 定义了 `DETAILS_HISTORY_FILE`、`load_details_history()`、`save_details_history()`、`update_paper_status()`、`is_paper_crawled()` 等方法，用于缓存论文详情，实现断点续传。但 `cnki_paper_threaded.py` **完全缺少这些功能**：

- 没有 `DETAILS_HISTORY_FILE` 常量
- 没有 `load_details_history()` / `save_details_history()` 方法
- 没有 `update_paper_status()` 方法
- 没有 `is_paper_crawled()` 方法

**后果**：多线程爬虫在爬取论文详情阶段如果中途中断，无法恢复进度，会重复爬取已爬取的论文。

#### 代码位置
- 缺少处：`cnki_paper_threaded.py`（第30-35行仅定义3个常量，缺少第4个）
- 对照参考：`cnki_paper.py` 第33行、第78-146行

### B. 【严重】多线程版本爬取详情后未更新 JSON 历史记录

#### 描述
在 `cnki_paper_threaded.py` 的 `crawl_paper_detail()` 方法（第553行）中，成功获取论文详情后（第665行），直接调用 `await self.save_to_database(result, journal_name)` 保存到数据库，但**没有调用类似 `update_paper_status()` 的方法更新 details JSON 文件**。

**对照**：单线程版本 `cnki_paper.py` 第1046行调用了 `HistoryManager.update_paper_status(paper_url, 1, result, journal_name)`。

**后果**：多线程版即使成功爬取了论文详情，json 历史文件中也没有记录，无法实现断点续传。

#### 代码位置
- `cnki_paper_threaded.py` 第553-673行（`crawl_paper_detail` 方法）
- 第665行：`await self.save_to_database(result, journal_name)` — 缺少 update_paper_status 调用
- 单线程对照：`cnki_paper.py` 第1043-1046行

### C. 【中】多线程版 `process_journal()` 中详情获取后未使用 `existing_urls` 过滤

#### 描述
在 `cnki_paper_threaded.py` 的 `process_journal()` 方法（第718行）中：
1. 第739-751行：获取了 `existing_urls`（数据库中已有的 URL 列表）
2. 第760行：使用 `existing_urls` 过滤了 `papers_to_process`
3. 但是 `crawl_paper_detail()` 内部（第557-570行）仍然会再次检查数据库

这本身不是大问题，但因为缺少 `details_history` 缓存，如果某个论文虽然不在数据库中（`existing_urls` 过滤通过），但实际上已经爬取过但保存数据库失败，程序不会知道，会重新爬取。

#### 代码位置
- `cnki_paper_threaded.py` 第718-786行（`process_journal` 方法）

### D. 【中】线程 ID 计算导致日志标识重复

#### 描述
第901行：`thread_id = i % self.max_workers + 1`

当期刊数量多于线程数时，thread_id 会循环重复（例如 3 个线程处理 10 个期刊：1,2,3,1,2,3,1,2,3,1）。这导致不同期刊的日志使用相同的 `[线程1]` 标识，排查问题时难以区分是哪个期刊的日志。

#### 代码位置
- `cnki_paper_threaded.py` 第900-903行

### E. 【中】多线程并发写入 JSON 文件的竞态条件

#### 描述
`HistoryManager.add_papers_for_journal_issue()` 使用 `load -> modify -> save` 模式操作 `papers_history.json`。多线程环境下，多个线程同时：
1. `load_papers_history()` 读取文件
2. 修改内存中的数据
3. `save_papers_history()` 写回文件

会导致**后保存的线程覆盖先保存的线程**的修改，造成数据丢失。

#### 代码位置
- `cnki_paper_threaded.py` 第121-136行（`add_papers_for_journal_issue`）
- `cnki_paper.py` 第172-187行（同样的问题，但单线程不会触发）

### F. 【中】`crawl_papers_for_journal()` 中年份缓存检查逻辑缺陷

#### 描述
在第476-482行（多线程版）和第718-727行（单线程版）：
1. 先检查每个年份是否已缓存，如果已缓存则加入 `all_papers`
2. 然后检查 `all()` 是否所有年份都已缓存
3. 如果部分年份已缓存、部分未缓存，会继续爬取未缓存的年份

**问题**：已缓存年份的论文数据被加入 `all_papers` 后，后续爬取未缓存年份时，可能会在同一个运行过程中重复爬取到相同论文。而且 `all_papers` 中会有重复数据（已缓存的 + 新爬取的）。

#### 代码位置
- `cnki_paper.py` 第718-729行
- `cnki_paper_threaded.py` 第476-486行

### G. 【中】两个版本都缺少对爬取过程的 `CrawlLog` 记录

#### 描述
数据库中已定义 `CrawlLog` 模型（`models.py` 第80-91行）和 `CrawlLogCRUD`（`crud.py` 第343-438行），`scheduler.py` 中也使用了 CrawlLog 记录爬取日志。但 `cnki_paper.py` 和 `cnki_paper_threaded.py` 都没有在爬取过程中创建或更新 `CrawlLog` 记录。

**后果**：无法在系统中查看这些爬虫的运行状态和历史。

### H. 【中】两个版本爬取论文后缺少 AI 处理和评分

#### 描述
`cnki_paper.py` 和 `cnki_paper_threaded.py` 中使用 `create_paper_from_cnki()` 方法保存数据，该方法（`crud.py` 第287-341行）创建论文记录时：
- 设置 `features.keywords` 但 `topic=None`
- 设置默认评分 `final_score=0.55`

而 `scheduler.py` 中对 Arxiv 和 CNKI 爬取的论文会调用 `ai_processor.process_paper()` 进行 AI 摘要、关键词提取、embedding 和主题分类，然后调用 `scoring_system` 计算评分。

**后果**：通过这两个爬虫导入的论文没有经过 AI 处理和评分，都是默认值，影响后续的热点分析和排序功能。

#### 代码位置
- `cnki_paper.py` 第1056-1102行（`save_to_database`）
- `cnki_paper_threaded.py` 第675-716行（`save_to_database`）
- `crud.py` 第287-341行（`create_paper_from_cnki`）
- `scheduler.py` 第96-136行（含 AI 处理和评分的流程）

### I. 【低】单线程版本 `crawl_papers_for_journal()` 中存在死代码

#### 描述
`cnki_paper.py` 第917-918行有以下代码，但永远不会被执行到：
```python
print(f"\n期刊 {journal_name} 共获取 {len(all_papers)} 篇论文")
return all_papers
```
因为第806行已经是 `crawl_papers_for_journal()` 中 for 循环的最后一条语句，且第806行前的代码没有提前返回或跳出整个函数的结构。实际上第805行 `all_papers.extend(year_papers)` 后的第806行是该方法的末尾，但第917-918行的重复代码由于缩进问题成为了不可达代码。

#### 代码位置
- `cnki_paper.py` 第917-918行

### J. 【低】`verify_page` 检测在 `wait_for_page_stable` 中重复

#### 描述
`wait_for_page_stable()` 方法（两个版本都有）第一次进入时检查当前 URL 是否是验证码页面，如果不是则立即返回 `True`。但 `is_verify_page()` 在 `crawl_year_papers_with_larrow` 中点击前一期按钮后又被调用一次检查验证码。这种双重检查增加了代码复杂度，但并非错误。

### K. 【低】`import_papers_to_db.py` 年份提取逻辑可能不准确

#### 描述
第62-63行使用 `re.search(r'\.(\d{4})\.', doi)` 从 DOI 提取年份，但知网 DOI 格式如 `10.19581/j.cnki.ciejournal.2026.03.001` 中第一个 `.2026.` 被匹配，结果正确。但如果 DOI 中包含其他 4 位数字，可能提取错误。

第59行默认年份写死为 `2026`，未来需要动态获取。

---

## 未实现的功能

### 1. 断点续传机制不完整
- 单线程版：有 `details_history` 但实际恢复逻辑较弱（只检查数据库，不检查 JSON 缓存）
- 多线程版：完全缺少 `details_history`

### 2. 多线程版缺少 `is_paper_crawled()` 缓存检查
- 多线程版爬取详情前没有检查 `details_history` 缓存
- 即使已经爬取过详情并保存在 JSON 中，也会重新爬取

### 3. 论文评分系统未集成
- 两个版本都没有调用 `scoring.py` 的评分功能
- 数据库中的 `recency_score`、`venue_score`、`trend_score`、`final_score` 都是硬编码默认值

### 4. AI 处理未集成
- 两个版本都没有调用 `ai_processor.py` 的功能
- 不生成 embedding，不进行主题分类
- `features.topic` 始终为 `None`

### 5. 爬取日志 (CrawlLog) 未集成
- 无法在系统中查询这两个爬虫的历史运行记录

### 6. 论文期次号 (journal_issue) 未保存到数据库
- `crud.py` 第298-309行创建 Paper 对象时没有使用 `journal_issue` 字段
- 数据库中 `paper.journal_issue` 始终为 `None`

### 7. HTTP 重试机制
- 两个版本都没有实现指数退避重试策略
- 网络错误时直接失败退出，缺乏鲁棒性

### 8. 多线程版本缺少文件锁
- 并发写入 JSON 文件没有加锁保护