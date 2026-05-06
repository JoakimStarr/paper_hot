# Tasks

## 环境配置

- [x] Task 1: 安装 DrissionPage 依赖
  - [x] SubTask 1.1: 检查 requirements.txt 中是否有 DrissionPage
  - [x] SubTask 1.2: 安装 DrissionPage Python 库
  - [x] SubTask 1.3: 验证 DrissionPage 环境是否正常

## CNKI 期刊导航爬虫开发

- [x] Task 2: 实现期刊列表获取
  - [x] SubTask 2.1: 访问知网期刊导航页面 https://navi.cnki.net/knavi/journals/index
  - [x] SubTask 2.2: 点击"经济与管理科学"分类按钮
  - [x] SubTask 2.3: 获取 div.result 中的期刊名称和链接
  - [x] SubTask 2.4: 保存为 {title: href} JSON 格式
  - [x] SubTask 2.5: 只获取第一页数据

- [x] Task 3: 实现按年份和期号爬取论文列表
  - [x] SubTask 3.1: 进入期刊详情页
  - [x] SubTask 3.2: 获取 div#YearIssueTree 内容
  - [x] SubTask 3.3: 点击 dl#2026_Year_Issue 选择年份 2026
  - [x] SubTask 3.4: 获取 div#listbox 中的论文链接和标题
  - [x] SubTask 3.5: 点击 span#larrow 去前一期
  - [x] SubTask 3.6: 重复获取直到 span#larrow class 为 btn-larrow disable
  - [x] SubTask 3.7: 切换到 2025 年，重复上述步骤
  - [x] SubTask 3.8: 保存所有论文链接和标题到列表

- [x] Task 4: 实现论文详情提取
  - [x] SubTask 4.1: 访问论文详情页
  - [x] SubTask 4.2: 从 div.doc h1 提取标题
  - [x] SubTask 4.3: 从 h3.author 提取作者信息
  - [x] SubTask 4.4: 从 span.abstract-text 提取摘要
  - [x] SubTask 4.5: 从 p.keywords 提取关键词
  - [x] SubTask 4.6: 从 div.row li 提取 DOI 等元数据
  - [x] SubTask 4.7: 保存期刊名称、论文标题、DOI、摘要、关键词、论文链接

- [x] Task 5: 实现数据保存
  - [x] SubTask 5.1: 检查论文是否已存在(根据 DOI 或链接)
  - [x] SubTask 5.2: 保存期刊信息到数据库
  - [x] SubTask 5.3: 保存论文信息到数据库
  - [x] SubTask 5.4: 建立期刊和论文的关联

## 错误处理和优化

- [x] Task 6: 实现反爬机制处理
  - [x] SubTask 6.1: 随机 User-Agent
  - [x] SubTask 6.2: 请求间隔控制(2-5秒)
  - [x] SubTask 6.3: 验证码检测
  - [x] SubTask 6.4: 弹出浏览器让用户手动处理验证码
  - [x] SubTask 6.5: 页面加载等待策略

- [x] Task 7: 实现错误处理和重试
  - [x] SubTask 7.1: 网络错误处理
  - [x] SubTask 7.2: 页面加载超时处理
  - [x] SubTask 7.3: 数据提取失败处理
  - [x] SubTask 7.4: 实现重试机制

## 集成和测试

- [x] Task 8: 集成到系统
  - [x] SubTask 8.1: 创建 fetchers_cnki_navi.py 模块
  - [x] SubTask 8.2: 实现 CNKINaviFetcher 类
  - [x] SubTask 8.3: 更新 scheduler.py 添加爬虫任务
  - [x] SubTask 8.4: 创建测试脚本

- [x] Task 9: 验证和测试
  - [x] SubTask 9.1: 测试期刊列表获取
  - [x] SubTask 9.2: 测试论文列表爬取
  - [x] SubTask 9.3: 测试论文详情提取
  - [x] SubTask 9.4: 测试数据保存

# Task Dependencies
- [Task 1] 必须在其他任务之前完成
- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 2]
- [Task 4] depends on [Task 3]
- [Task 5] depends on [Task 4]
- [Task 6] depends on [Task 2]
- [Task 7] depends on [Task 2]
- [Task 8] depends on [Task 5, Task 6, Task 7]
- [Task 9] depends on [Task 8]
