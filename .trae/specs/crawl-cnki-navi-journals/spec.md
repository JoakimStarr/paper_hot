# 知网期刊导航爬虫 Spec

## Why

当前系统需要按照新的知网期刊导航方法爬取经济学期刊论文。这个方法通过知网期刊导航页面(https://navi.cnki.net)获取期刊列表，然后逐期爬取论文详细信息。

## What Changes

* 实现知网期刊导航页面爬虫
* 获取经济与管理科学分类下的期刊列表
* 按年份(2025, 2026)和期号逐期爬取论文
* 提取论文详细信息(标题、作者、摘要、关键词、DOI等)
* 保存期刊信息、论文信息到数据库

## Impact

* Affected code:
  * backend/app/fetchers_cnki_navi.py (新建知网导航爬虫)
  * backend/app/scheduler.py (添加爬虫任务)
  * backend/app/crud.py (可能需要添加批量保存方法)

## ADDED Requirements

### Requirement: 期刊列表获取

系统 SHALL 从知网期刊导航页面获取期刊列表：

* 访问 https://navi.cnki.net/knavi/journals/index
* 点击"经济与管理科学"分类
* 获取div.result中的期刊链接和名称
* 保存为{title: href}格式
* 只获取第一页数据

#### Scenario: 成功获取期刊列表
* **WHEN** 系统访问知网期刊导航页面
* **THEN** 成功加载经济与管理科学分类
* **AND** 获取期刊名称和链接
* **AND** 保存到JSON格式

### Requirement: 按年份和期号爬取论文

系统 SHALL 按年份和期号逐期爬取论文：

* 进入期刊详情页
* 获取div#"YearIssueTree"内容
* 点击dl#2026_Year_Issue选择年份(2025, 2026)
* 默认选择当年最晚的一期
* 获取div#listbox中的所有论文链接和标题
* 点击span#larrow去前一期，重复获取直到span#larrow的class为btn-larrow disable
* 然后获取上一年的数据，重复上述步骤

#### Scenario: 成功获取所有期号论文
* **WHEN** 系统进入期刊详情页
* **THEN** 选择年份2026
* **AND** 从最晚一期开始往前获取
* **AND** 获取完2026年所有期号后，切换到2025年
* **AND** 直到获取完所有选择年份的论文

### Requirement: 论文详情提取

系统 SHALL 从论文详情页提取完整信息：

* 访问论文链接
* 从div.doc中提取：
  * h1: 标题
  * h3.author: 作者信息
  * span.abstract-text: 摘要
  * p.keywords: 关键词
  * div.row下面的li: 元数据(如DOI)
* 保存期刊名称、论文标题、DOI、摘要、关键词、专题、论文链接
* 同时保存期刊信息和链接

#### Scenario: 成功提取论文详情
* **WHEN** 系统访问论文详情页
* **THEN** 成功提取标题、作者、摘要、关键词
* **AND** 提取DOI等元数据
* **AND** 保存到数据库

### Requirement: 数据保存

系统 SHALL 将爬取的数据保存到数据库：

* 保存期刊信息(名称、链接)
* 保存论文信息(标题、作者、摘要、关键词、DOI、链接)
* 建立期刊和论文的关联
* 避免重复保存

#### Scenario: 数据保存成功
* **WHEN** 成功提取论文数据
* **THEN** 检查是否已存在(根据DOI或链接)
* **AND** 如果不存在则保存到数据库
* **AND** 记录保存的论文数量

### Requirement: 反爬机制处理

系统 SHALL 处理知网的反爬机制：

* 随机User-Agent
* 请求间隔控制(2-5秒)
* 页面加载等待策略
* 验证码检测和手动处理
* 错误重试机制

#### Scenario: 遇到反爬机制
* **WHEN** 爬虫触发反爬机制
* **THEN** 检测到验证码或限制
* **AND** 弹出浏览器让用户手动处理
* **AND** 记录异常情况

## MODIFIED Requirements

无修改的需求

## REMOVED Requirements

无移除的需求
