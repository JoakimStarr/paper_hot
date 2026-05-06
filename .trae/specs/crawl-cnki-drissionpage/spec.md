# 使用 DrissionPage 爬取知网经济学TOP50期刊 Spec

## Why

当前系统需要从 CNKI（中国知网）爬取经济学TOP50期刊2025年至今的论文。知网有严格的反爬机制（验证码、动态加载、登录限制），需要使用 DrissionPage 浏览器自动化工具来实现可靠的数据爬取。DrissionPage 相比 Playwright 更轻量、更适合中文网站爬取。

## What Changes

* 安装 DrissionPage 依赖
* 实现 CNKI 登录和验证码处理机制
* 配置经济学TOP50期刊列表
* 使用 DrissionPage 爬取知网期刊论文
* 提取论文元数据（标题、作者、摘要、关键词、期刊、期号、DOI等）
* 将爬取的数据保存到数据库
* 实现验证码自动检测和人工处理流程

## Impact

* Affected code:
  * backend/requirements.txt (添加 DrissionPage 依赖)
  * backend/app/fetchers_cnki.py (新建 CNKI 爬虫模块)
  * backend/app/scheduler.py (添加 CNKI 定时任务)
  * backend/app/config.py (添加 CNKI 配置)

## ADDED Requirements

### Requirement: DrissionPage 环境配置

系统 SHALL 配置 DrissionPage 环境：

* 安装 DrissionPage Python 库
* 配置浏览器启动参数（headless, viewport, user-agent）
* 配置 Chrome/Chromium 浏览器路径

#### Scenario: 环境初始化
* **WHEN** 系统启动时
* **THEN** DrissionPage 环境准备就绪
* **AND** 可以正常启动浏览器实例

### Requirement: CNKI 爬虫实现

系统 SHALL 实现 CNKI 期刊爬虫：

* 使用 DrissionPage 打开知网期刊页面
* 处理登录流程（如需要）
* 检测并处理验证码（支持人工干预）
* 爬取指定期刊的论文列表
* 提取每篇论文的详细信息

#### Scenario: 成功爬取期刊
* **WHEN** 爬虫访问知网期刊页面
* **THEN** 成功加载页面内容
* **AND** 获取论文列表
* **AND** 提取每篇论文的元数据

#### Scenario: 遇到验证码
* **WHEN** 页面出现验证码
* **THEN** 检测验证码并暂停爬取
* **AND** 提示用户手动完成验证码
* **AND** 完成后继续爬取

### Requirement: 经济学TOP50期刊配置

系统 SHALL 配置经济学TOP50期刊列表，包括但不限于：

* 经济研究
* 管理世界
* 经济学（季刊）
* 世界经济
* 中国工业经济
* 中国社会科学
* 金融研究
* 数量经济技术经济研究
* 财贸经济
* 中国农村经济
* 经济学动态
* 国际经济评论
* 改革
* 中国人口科学
* 中国农村经济
* 农业经济问题
* 中国农村观察
* 财政研究
* 税务研究
* 会计研究
* 审计研究
* 国际贸易问题
* 国际经贸探索
* 世界经济研究
* 经济社会体制比较
* 经济学家
* 经济科学
* 经济理论与经济管理
* 南开经济研究
* 当代经济科学
* 当代经济研究
* 财经科学
* 财经问题研究
* 上海经济研究
* 经济纵横
* 经济问题探索
* 经济问题
* 经济经纬
* 经济评论
* 经济导刊
* 经济研究参考
* 经济研究导刊
* 经济师
* 经济界
* 经济视角
* 经济论坛
* 经济工作导刊
* 经济师论坛
* 经济学家论坛
* 经济学消息报

#### Scenario: 爬取TOP50期刊
* **WHEN** 用户指定爬取TOP50期刊
* **THEN** 依次爬取配置的期刊列表
* **AND** 汇总爬取结果
* **AND** 支持2025年至今的时间过滤

### Requirement: 反爬机制处理

系统 SHALL 处理知网的反爬机制：

* 随机 User-Agent
* 请求间隔控制（3-8秒随机延迟）
* 页面加载等待策略
* 验证码检测和处理
* 登录状态保持
* 使用系统浏览器配置（如有登录状态）

#### Scenario: 遇到反爬机制
* **WHEN** 爬虫触发反爬机制
* **THEN** 自动等待并重试
* **AND** 记录异常情况
* **AND** 必要时切换代理或暂停

### Requirement: 数据提取和保存

系统 SHALL 提取并保存论文数据：

* 标题
* 作者列表
* 摘要
* 关键词
* 期刊名称
* 发表年份和期号
* DOI（如有）
* 论文链接（知网链接）
* 发表日期

#### Scenario: 数据保存
* **WHEN** 成功提取论文数据
* **THEN** 保存到数据库
* **AND** 避免重复保存（基于标题+作者+期刊去重）

## MODIFIED Requirements

无修改的需求

## REMOVED Requirements

无移除的需求
