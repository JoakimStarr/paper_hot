# Tasks

## 后端开发

- [x] Task 1: 扩展数据库模型以支持经济学期刊
  - [x] SubTask 1.1: 在 Paper 模型中添加 discipline、journal、issue、doi、keywords_cn 字段
  - [x] SubTask 1.2: 创建 CrawlLog 模型用于存储爬取日志
  - [x] SubTask 1.3: 创建数据库迁移脚本
  - [x] SubTask 1.4: 更新 Pydantic schemas 以支持新字段

- [x] Task 2: 实现经济学期刊爬取器
  - [x] SubTask 2.1: 创建 EconomicsJournalFetcher 基类
  - [x] SubTask 2.2: 实现知网爬取器（CNKIFetcher）
  - [x] SubTask 2.3: 实现《经济研究》爬取器
  - [x] SubTask 2.4: 实现《管理世界》爬取器
  - [x] SubTask 2.5: 实现其他经济学顶刊爬取器
  - [x] SubTask 2.6: 添加爬取错误处理和重试机制

- [x] Task 3: 实现经济学论文分类器
  - [x] SubTask 3.1: 创建经济学子领域关键词库
  - [x] SubTask 3.2: 实现基于关键词的经济学分类器
  - [x] SubTask 3.3: 添加经济学论文评分逻辑

- [x] Task 4: 创建爬取日志管理功能
  - [x] SubTask 4.1: 创建 CrawlLogCRUD 类
  - [x] SubTask 4.2: 实现日志记录功能
  - [x] SubTask 4.3: 实现日志查询功能

- [x] Task 5: 扩展 API 接口
  - [x] SubTask 5.1: 添加 GET /api/papers 接口的经济学筛选参数
  - [x] SubTask 5.2: 创建 POST /api/crawl/start 接口用于启动爬取
  - [x] SubTask 5.3: 创建 GET /api/crawl/logs 接口用于查询日志
  - [x] SubTask 5.4: 创建 GET /api/crawl/status 接口用于查看爬取状态
  - [x] SubTask 5.5: 创建 GET /api/journals 接口用于获取支持的期刊列表

- [x] Task 6: 更新调度器
  - [x] SubTask 6.1: 添加经济学期刊爬取定时任务
  - [x] SubTask 6.2: 实现手动触发爬取功能
  - [x] SubTask 6.3: 添加爬取任务状态管理

## 前端开发

- [x] Task 7: 创建系统管理页面
  - [x] SubTask 7.1: 创建 /system 路由和页面组件
  - [x] SubTask 7.2: 设计系统管理页面布局
  - [x] SubTask 7.3: 添加导航链接到系统管理页面

- [ ] Task 8: 实现爬取控制组件
  - [ ] SubTask 8.1: 创建爬取控制面板组件
  - [ ] SubTask 8.2: 实现启动爬取按钮和确认对话框
  - [ ] SubTask 8.3: 实现爬取进度显示
  - [ ] SubTask 8.4: 实现期刊选择功能

- [ ] Task 9: 实现爬取日志组件
  - [ ] SubTask 9.1: 创建日志列表组件
  - [ ] SubTask 9.2: 实现日志详情查看
  - [ ] SubTask 9.3: 实现日志筛选功能（日期、状态）
  - [ ] SubTask 9.4: 实现日志分页

- [x] Task 10: 更新论文列表页面
  - [x] SubTask 10.1: 在筛选器中添加学科领域选择
  - [x] SubTask 10.2: 在筛选器中添加经济学子领域选择
  - [x] SubTask 10.3: 在筛选器中添加期刊名称选择
  - [x] SubTask 10.4: 更新论文卡片显示期刊信息

## 测试与文档

- [ ] Task 11: 编写测试
  - [ ] SubTask 11.1: 编写经济学期刊爬取器单元测试
  - [ ] SubTask 11.2: 编写经济学分类器单元测试
  - [ ] SubTask 11.3: 编写系统管理 API 集成测试
  - [ ] SubTask 11.4: 编写前端组件测试

- [ ] Task 12: 更新文档
  - [ ] SubTask 12.1: 更新 README.md 添加经济学期刊说明
  - [ ] SubTask 12.2: 更新 API 文档
  - [ ] SubTask 12.3: 创建经济学期刊爬取配置说明

# Task Dependencies
- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 1]
- [Task 4] depends on [Task 1]
- [Task 5] depends on [Task 1, Task 2, Task 3, Task 4]
- [Task 6] depends on [Task 2]
- [Task 7] 可以并行执行
- [Task 8] depends on [Task 7, Task 5]
- [Task 9] depends on [Task 7, Task 5]
- [Task 10] 可以并行执行
- [Task 11] depends on [Task 1-10]
- [Task 12] depends on [Task 1-11]
