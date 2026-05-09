# Tasks（修复计划，按优先级排列）

- [ ] Task 1: 为多线程版本添加 `paper_details_history` 持久化机制
  - 在 `HistoryManager` 中添加 `DETAILS_HISTORY_FILE`、`load_details_history()`、`save_details_history()`、`update_paper_status()`、`is_paper_crawled()` 方法
  - 在 `crawl_paper_detail()` 成功获取详情后调用 `update_paper_status()`
  - 在爬取详情前检查 `is_paper_crawled()` 跳过已爬取论文

- [ ] Task 2: 修复多线程并发写入 JSON 的竞态条件
  - 使用 `threading.Lock` 或文件锁保护所有 JSON 文件的读写操作
  - 确保 `load -> modify -> save` 操作是原子性的

- [ ] Task 3: 修复线程 ID 计算逻辑
  - 将 `thread_id = i % self.max_workers + 1` 改为 `thread_id = i + 1`
  - 确保每个期刊有唯一的线程标识

- [ ] Task 4: 修复 `crawl_papers_for_journal()` 中年份缓存检查逻辑
  - 修复部分年份缓存时的重复数据问题
  - 确保 `all_papers` 中不会出现重复的论文条目

- [ ] Task 5: 删除单线程版本中的死代码
  - 删除 `cnki_paper.py` 第917-918行的不可达代码

- [ ] Task 6: 集成 CrawlLog 爬取日志
  - 在爬虫启动时创建 `CrawlLog` 记录
  - 在爬取过程中更新论文统计
  - 在爬取完成或失败时更新状态

- [ ] Task 7: 集成 AI 处理和评分系统
  - 在 `save_to_database()` 或后续流程中调用 `ai_processor.process_paper()`
  - 调用 `scoring_system` 计算评分
  - 更新 `features` 和 `scores` 表

- [ ] Task 8: 保存 `journal_issue` 到数据库
  - 修改 `create_paper_from_cnki()` 传递 `journal_issue` 字段
  - 确保期次信息被持久化

- [ ] Task 9: 添加 HTTP 重试机制
  - 实现指数退避重试策略
  - 在页面加载、点击等关键操作添加重试

- [ ] Task 10: 修复 `import_papers_to_db.py` 中的默认年份硬编码
  - 将默认年份从 `2026` 硬编码改为动态获取（当前年份）

# 任务依赖关系
- Task 1 无依赖
- Task 2 无依赖
- Task 3 无依赖
- Task 4 无依赖
- Task 5 无依赖
- Task 6 依赖 Task 2（需要线程安全的文件操作）
- Task 7 无依赖
- Task 8 无依赖
- Task 9 无依赖
- Task 10 无依赖

# 并行化建议
- Task 1、2、3、4、5、7、8、9、10 可以并行实现
- Task 6 最好在 Task 2 完成后进行