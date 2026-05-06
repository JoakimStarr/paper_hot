# 实现期刊爬虫 Spec

## Why

当前 PaperPulse 只实现了《世界经济》的真实爬虫，其他期刊（管理世界、经济研究、经济学季刊、中国工业经济、AER）都是空实现。需要根据 `期刊爬取方法.md` 文档实现这些期刊的真实爬虫。

## What Changes

* 实现管理世界期刊爬虫
* 实现经济研究期刊爬虫（使用API）
* 实现经济学季刊期刊爬虫
* 实现中国工业经济期刊爬虫
* 实现 American Economic Review 期刊爬虫
* 创建简单的爬虫运行脚本 `crawl.py` 放在项目根目录
* 更新 scheduler 配置

## Impact

* Affected code:
  * backend/app/fetchers.py (实现真实爬虫)
  * backend/app/scheduler.py (更新期刊列表)
  * /home/joakim/Project/paper_hot/crawl.py (新建爬虫运行脚本)

## ADDED Requirements

### Requirement: 管理世界期刊爬虫

系统 SHALL 实现管理世界期刊的真实爬虫：

* 爬取URL: `https://glsj.cbpt.cnki.net/WKB2/WebPublication/wkTextContent.aspx?colType=4&yt={year}&st={issue:02d}`
* 解析 `div.zxlist` 下的论文列表
* 提取标题、作者、摘要、期号、论文链接

#### Scenario: 成功爬取
* **WHEN** 爬虫访问管理世界网站
* **THEN** 成功获取指定年份和期数的论文列表
* **AND** 每篇论文包含完整元数据

### Requirement: 经济研究期刊爬虫

系统 SHALL 实现经济研究期刊的真实爬虫：

* 使用API: `https://api.ajcass.com/api/JournalInfoApi/GetIssueinfoList`
* POST请求获取JSON数据
* 提取标题、作者、期号等信息

#### Scenario: 成功爬取
* **WHEN** 爬虫调用经济研究API
* **THEN** 成功获取论文列表
* **AND** 数据格式正确解析

### Requirement: 经济学季刊爬虫

系统 SHALL 实现经济学季刊的真实爬虫：

* 网站: `https://www.oaj.pku.edu.cn/Journalxjjx`
* 解析期刊列表页面
* 提取论文元数据

### Requirement: 中国工业经济爬虫

系统 SHALL 实现中国工业经济期刊的真实爬虫：

* 网站: `https://ciejournal.ajcass.com/`
* 解析期刊列表
* 提取论文信息

### Requirement: AER爬虫

系统 SHALL 实现 American Economic Review 的爬虫：

* 网站: `https://www.aeaweb.org/journals/aer`
* 解析期刊issue页面
* 提取论文元数据

### Requirement: 爬虫运行脚本

系统 SHALL 提供简单的爬虫运行脚本：

* 文件位置: `/home/joakim/Project/paper_hot/crawl.py`
* 支持命令行参数指定期刊
* 支持爬取所有期刊
* 显示爬取进度和结果

#### Scenario: 运行爬虫脚本
* **WHEN** 用户运行 `python crawl.py --journal 管理世界`
* **THEN** 启动指定期刊的爬取
* **AND** 显示爬取结果统计

#### Scenario: 爬取所有期刊
* **WHEN** 用户运行 `python crawl.py --all`
* **THEN** 依次爬取所有已实现的期刊
* **AND** 汇总显示各期刊爬取结果

## MODIFIED Requirements

### Requirement: Scheduler期刊列表

更新 scheduler 中的期刊列表，添加已实现的真实爬虫：

* 管理世界
* 经济研究
* 经济学季刊
* 中国工业经济
* American Economic Review

## REMOVED Requirements

无移除的需求
