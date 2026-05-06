# 使用 Playwright 爬取知网经济学TOP期刊 Spec

## Why

当前系统缺少从 CNKI（中国知网）爬取经济学TOP期刊论文的功能。CNKI是国内最大的学术文献数据库，包含大量高质量的经济学期刊。由于CNKI有严格的反爬机制（验证码、动态加载、登录限制），需要使用 Playwright 浏览器自动化工具来实现可靠的数据爬取。

## What Changes

* 安装 Playwright 依赖
* 实现 CNKI 登录和验证码处理
* 实现经济学TOP期刊列表配置
* 使用 Playwright 爬取知网期刊论文
* 提取论文元数据（标题、作者、摘要、关键词、期刊、期号等）
* 将爬取的数据保存到数据库

## Impact

* Affected code:
  * backend/requirements.txt (添加 Playwright 依赖)
  * backend/app/fetchers.py (实现 CNKI 爬虫)
  * backend/app/scheduler.py (添加 CNKI 定时任务)
  * backend/app/config.py (添加 CNKI 配置)

## ADDED Requirements

### Requirement: Playwright 环境配置

系统 SHALL 配置 Playwright 环境：

* 安装 Playwright Python 库
* 安装 Chromium 浏览器
* 配置浏览器启动参数（headless, viewport, user-agent）

#### Scenario: 环境初始化
* **WHEN** 系统启动时
* **THEN** Playwright 环境准备就绪
* **AND** 可以正常启动浏览器实例

### Requirement: CNKI 爬虫实现

系统 SHALL 实现 CNKI 期刊爬虫：

* 使用 Playwright 打开知网期刊页面
* 处理登录流程（如需要）
* 处理验证码（如需要）
* 爬取指定期刊的论文列表
* 提取每篇论文的详细信息

#### Scenario: 成功爬取期刊
* **WHEN** 爬虫访问知网期刊页面
* **THEN** 成功加载页面内容
* **AND** 获取论文列表
* **AND** 提取每篇论文的元数据

### Requirement: 经济学TOP期刊配置

系统 SHALL 配置经济学TOP期刊列表：

* 经济研究
* 管理世界
* 经济学（季刊）
* 世界经济
* 中国工业经济
* 中国社会科学
* 金融研究
* 数量经济技术经济研究

#### Scenario: 爬取TOP期刊
* **WHEN** 用户指定爬取TOP期刊
* **THEN** 依次爬取配置的期刊列表
* **AND** 汇总爬取结果

### Requirement: 反爬机制处理

系统 SHALL 处理知网的反爬机制：

* 随机 User-Agent
* 请求间隔控制（3-5秒）
* 页面加载等待策略
* 验证码检测和处理
* 登录状态保持

#### Scenario: 遇到反爬机制
* **WHEN** 爬虫触发反爬机制
* **THEN** 自动等待并重试
* **AND** 记录异常情况

### Requirement: 数据提取和保存

系统 SHALL 提取并保存论文数据：

* 标题
* 作者列表
* 摘要
* 关键词
* 期刊名称
* 发表年份和期号
* DOI（如有）
* 论文链接

#### Scenario: 数据保存
* **WHEN** 成功提取论文数据
* **THEN** 保存到数据库
* **AND** 避免重复保存

## MODIFIED Requirements

无修改的需求

## REMOVED Requirements

无移除的需求
