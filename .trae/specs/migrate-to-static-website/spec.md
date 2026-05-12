# 静态网站迁移规格说明

## Why
将现有的 Next.js + FastAPI 学术论文平台完整迁移为纯静态网站（HTML+JS+CSS），以便部署到 GitHub Pages，保留所有功能、效果和用户体验。

## What Changes
- 将 Next.js React 组件转换为纯 HTML + 原生 JavaScript + CSS
- 将后端 API 数据导出为静态 JSON 文件
- AI 分析功能改为客户端直接调用 AI API（需用户配置 API Key）
- 移除爬虫相关功能和系统管理页面
- 使用 D3.js 保留网络可视化功能
- 实现客户端数据筛选、搜索、分页功能
- **完整保留所有 UI 效果**：动画、过渡、骨架屏、Toast 通知等
- **完整保留所有 AI 功能**：论文分析、追问讨论、趋势分析、选题分析对话等
- **BREAKING**: 移除所有需要后端的功能（爬虫、系统管理、数据库操作）

## Impact
- Affected specs: 所有前端页面和功能
- Affected code: frontend/src/* 全部重写为静态文件

## ADDED Requirements

### Requirement: 静态数据存储
系统 SHALL 使用静态 JSON 文件存储论文数据，支持客户端加载和查询。

#### Scenario: 数据加载
- **WHEN** 用户访问网站
- **THEN** 系统从静态 JSON 文件加载论文数据到内存

#### Scenario: 数据分片
- **WHEN** 论文数据量较大（>1000篇）
- **THEN** 系统将数据分片存储，按需加载

#### Scenario: 数据缓存
- **WHEN** 数据加载完成后
- **THEN** 系统将数据缓存到 localStorage，下次访问直接使用缓存

### Requirement: 客户端筛选与搜索
系统 SHALL 在客户端实现论文筛选、搜索和分页功能。

#### Scenario: 多维度筛选
- **WHEN** 用户选择期刊、学科、子领域、CNKI学科、关键词等筛选条件
- **THEN** 系统在客户端过滤数据并更新显示，保持原有筛选器 UI 效果

#### Scenario: 关键词搜索
- **WHEN** 用户输入搜索关键词
- **THEN** 系统在客户端搜索标题、作者、关键词字段并返回结果

#### Scenario: 自动补全
- **WHEN** 用户在搜索框输入内容
- **THEN** 系统展示自动补全建议（关键词、标题、作者）

#### Scenario: 分页
- **WHEN** 用户切换页码或每页数量
- **THEN** 系统更新显示并滚动到顶部

#### Scenario: 排序
- **WHEN** 用户选择排序方式（日期/综合评分）和排序顺序
- **THEN** 系统重新排序并更新显示

### Requirement: 论文详情页面
系统 SHALL 提供完整的论文详情展示功能，包括元数据、摘要、相似论文、评分、AI 分析。

#### Scenario: 查看论文详情
- **WHEN** 用户点击论文卡片
- **THEN** 系统展示论文完整信息，包括：
  - 标题、作者（可点击跳转作者页）
  - 摘要、关键词（可点击跳转搜索）
  - DOI（可点击跳转原文）、期刊名称、期号
  - 学科、子领域、来源
  - 发表日期

#### Scenario: 评分展示
- **WHEN** 用户查看论文详情
- **THEN** 系统展示三个评分维度：
  - Recency Score（时效性评分）
  - Venue Score（期刊评分）
  - Trend Score（趋势评分）
  - Should Read Score（推荐阅读评分）

#### Scenario: 相似论文推荐
- **WHEN** 用户查看论文详情
- **THEN** 系统基于预计算的相似度数据展示 TOP 5 相关论文，显示相似度百分比

#### Scenario: 返回导航
- **WHEN** 用户点击返回按钮
- **THEN** 系统返回首页，保持之前的筛选状态

### Requirement: AI 论文分析功能（客户端）
系统 SHALL 支持用户配置 AI API Key 后使用完整的 AI 分析功能。

#### Scenario: 配置 API Key
- **WHEN** 用户在设置页面输入 Zhipu/SiliconFlow API Key
- **THEN** 系统保存配置到 localStorage 并启用 AI 功能

#### Scenario: 论文 AI 分析
- **WHEN** 用户点击"AI 分析"按钮
- **THEN** 系统调用 AI API 分析论文，展示：
  - 研究背景
  - 方法论创新
  - 关键发现
  - 研究意义
- **AND** 分析过程中显示加载动画

#### Scenario: 分析状态持久化
- **WHEN** 用户刷新页面或重新访问
- **THEN** 系统从 localStorage 恢复分析状态和结果

#### Scenario: 重新分析
- **WHEN** 用户点击"重新分析"按钮
- **THEN** 系统重新调用 AI API 分析论文

#### Scenario: 追问讨论
- **WHEN** 用户在论文详情页输入问题
- **THEN** 系统调用 AI API 进行对话，流式展示回答
- **AND** 支持多轮对话，保留上下文
- **AND** 对话历史保存到 localStorage

#### Scenario: 模型选择
- **WHEN** 用户选择不同的 AI 模型
- **THEN** 系统使用指定模型进行分析和对话

### Requirement: 作者页面
系统 SHALL 展示作者的完整论文列表和详细统计信息。

#### Scenario: 查看作者页面
- **WHEN** 用户点击作者名称
- **THEN** 系统展示该作者的所有论文（分页显示）

#### Scenario: 作者统计
- **WHEN** 用户查看作者页面
- **THEN** 系统展示：
  - 论文总数
  - 第一作者论文数
  - 最近发表年份
  - 主要发表期刊
  - 热门关键词
  - 主要研究领域

#### Scenario: 合作者展示
- **WHEN** 用户查看作者页面
- **THEN** 系统展示合作者列表和合作次数

### Requirement: 搜索页面
系统 SHALL 提供完整的全文搜索功能。

#### Scenario: 搜索执行
- **WHEN** 用户输入搜索词并提交
- **THEN** 系统搜索标题、作者、关键词字段并返回结果

#### Scenario: 搜索字段选择
- **WHEN** 用户选择搜索字段（全部/标题/作者/关键词）
- **THEN** 系统仅在选定字段中搜索

#### Scenario: 自动补全
- **WHEN** 用户在搜索框输入内容
- **THEN** 系统展示自动补全建议，显示类型标签和匹配次数

#### Scenario: 期刊筛选
- **WHEN** 用户从 URL 参数带期刊筛选进入搜索页
- **THEN** 系统展示该期刊的论文列表

### Requirement: 趋势分析页面
系统 SHALL 展示完整的趋势分析功能，包括热点主题、雷达图、AI 趋势分析。

#### Scenario: 热点主题展示
- **WHEN** 用户访问趋势页面
- **THEN** 系统展示预计算的热点主题，包括：
  - 主题名称
  - 论文数量
  - 增长率
  - 趋势方向（上升/稳定/下降）

#### Scenario: 时间范围选择
- **WHEN** 用户选择时间范围（1个月/3个月/6个月）
- **THEN** 系统更新热点主题数据

#### Scenario: 趋势图表
- **WHEN** 用户查看趋势页面
- **THEN** 系统展示趋势折线图，支持交互（悬停显示详情）

#### Scenario: 研究热点雷达图
- **WHEN** 用户查看趋势页面
- **THEN** 系统展示各子领域论文分布的雷达图

#### Scenario: AI 趋势分析
- **WHEN** 用户点击"开始分析"并已配置 API Key
- **THEN** 系统调用 AI API 分析趋势，展示：
  - 分析摘要
  - 研究热点（TOP N）
  - 发展趋势
  - 关键词聚类分析
  - 期刊分析
  - 研究建议
- **AND** 显示分析进度动画

#### Scenario: 选题分析对话
- **WHEN** 用户在趋势分析页输入问题
- **THEN** 系统调用 AI API 进行对话，流式展示回答
- **AND** 支持快捷问题按钮
- **AND** 支持模型选择
- **AND** 支持导出对话记录
- **AND** 支持清空对话

#### Scenario: 历史报告
- **WHEN** 用户点击"查看历史报告"
- **THEN** 系统展示历史分析报告列表，支持恢复查看

### Requirement: 网络可视化
系统 SHALL 使用 D3.js 展示完整的交互式网络可视化。

#### Scenario: 作者合作网络
- **WHEN** 用户选择"作者合作网络"标签
- **THEN** 系统展示 D3.js 力导向图：
  - 节点为作者，大小表示论文数量
  - 边为合作关系，粗细表示合作次数
  - 支持缩放和拖拽

#### Scenario: 关键词共现网络
- **WHEN** 用户选择"关键词共现网络"标签
- **THEN** 系统展示 D3.js 力导向图：
  - 节点为关键词，大小表示出现次数
  - 边为共现关系，粗细表示共现次数
  - 支持缩放和拖拽

#### Scenario: 节点交互
- **WHEN** 用户点击节点
- **THEN** 系统高亮该节点及其关联节点，展示节点详情
- **AND** 展示关联节点列表，支持点击切换

#### Scenario: 节点导航
- **WHEN** 用户点击节点的跳转按钮
- **THEN** 系统跳转到搜索页面，搜索该节点相关论文

#### Scenario: 清除高亮
- **WHEN** 用户点击"清除高亮"按钮或空白区域
- **THEN** 系统恢复全局视图

### Requirement: 设置页面
系统 SHALL 提供完整的设置功能。

#### Scenario: API Key 配置
- **WHEN** 用户输入 Zhipu/SiliconFlow API Key
- **THEN** 系统保存到 localStorage，显示配置状态

#### Scenario: API Key 验证
- **WHEN** 用户保存 API Key
- **THEN** 系统验证 Key 有效性并显示结果

#### Scenario: 模型优先级
- **WHEN** 用户调整模型优先级
- **THEN** 系统保存配置，AI 功能使用优先级最高的可用模型

### Requirement: 深色模式
系统 SHALL 支持完整的明暗主题切换。

#### Scenario: 切换主题
- **WHEN** 用户点击主题切换按钮
- **THEN** 系统切换明暗主题，平滑过渡

#### Scenario: 系统偏好检测
- **WHEN** 用户首次访问网站
- **THEN** 系统检测系统主题偏好并应用

#### Scenario: 主题持久化
- **WHEN** 用户切换主题
- **THEN** 系统保存偏好到 localStorage

### Requirement: 国际化
系统 SHALL 支持完整的中英文界面切换。

#### Scenario: 切换语言
- **WHEN** 用户点击语言切换按钮
- **THEN** 系统切换界面语言，所有文本更新

#### Scenario: 语言持久化
- **WHEN** 用户切换语言
- **THEN** 系统保存偏好到 localStorage

### Requirement: 收藏功能
系统 SHALL 支持完整的论文收藏功能。

#### Scenario: 收藏论文
- **WHEN** 用户点击收藏按钮
- **THEN** 系统将论文 ID 保存到 localStorage，显示收藏状态

#### Scenario: 取消收藏
- **WHEN** 用户再次点击收藏按钮
- **THEN** 系统从 localStorage 移除论文 ID

#### Scenario: 查看收藏
- **WHEN** 用户选择"仅显示收藏"
- **THEN** 系统仅展示已收藏的论文

#### Scenario: 收藏持久化
- **WHEN** 用户刷新页面
- **THEN** 系统恢复收藏状态

### Requirement: UI 效果
系统 SHALL 保留所有原有 UI 效果。

#### Scenario: 骨架屏加载
- **WHEN** 数据加载中
- **THEN** 系统展示骨架屏动画

#### Scenario: 过渡动画
- **WHEN** 用户切换页面、筛选、排序
- **THEN** 系统展示平滑过渡动画

#### Scenario: Toast 通知
- **WHEN** 操作成功或失败
- **THEN** 系统展示 Toast 通知，自动消失

#### Scenario: 悬停效果
- **WHEN** 用户悬停在卡片、按钮上
- **THEN** 系统展示悬停效果（阴影、颜色变化）

#### Scenario: 滚动动画
- **WHEN** 用户切换页面
- **THEN** 系统平滑滚动到顶部

## MODIFIED Requirements

### Requirement: 数据来源
原系统从后端 API 获取数据，现改为从静态 JSON 文件加载。

### Requirement: AI 功能
原系统通过后端代理调用 AI API，现改为客户端直接调用。

### Requirement: 分析状态管理
原系统将分析状态存储在数据库，现改为存储在 localStorage。

## REMOVED Requirements

### Requirement: 爬虫功能
**Reason**: 静态网站无法执行爬虫任务
**Migration**: 移除所有爬虫相关页面和功能

### Requirement: 系统管理页面
**Reason**: 静态网站无后端服务可管理
**Migration**: 移除系统管理页面，保留设置页面用于配置 API Key

### Requirement: 数据库操作
**Reason**: 静态网站无数据库
**Migration**: 使用静态 JSON 文件替代

### Requirement: 用户认证
**Reason**: 静态网站无后端认证
**Migration**: 移除认证功能，API Key 保存在客户端

### Requirement: 调度器管理
**Reason**: 静态网站无后端调度器
**Migration**: 移除调度器相关功能

## 文件结构规划

```
/home/joakim/Project/hmAPP/blog/source/paper/
├── index.html              # 首页（论文列表）
├── paper.html              # 论文详情页
├── author.html             # 作者页面
├── search.html             # 搜索页面
├── trends.html             # 趋势分析页面
├── network.html            # 网络可视化页面
├── settings.html           # 设置页面（API Key 配置）
├── css/
│   ├── main.css            # 主样式（布局、排版）
│   ├── components.css      # 组件样式（卡片、按钮、表单）
│   ├── animations.css      # 动画效果（骨架屏、过渡）
│   └── dark.css            # 深色模式样式
├── js/
│   ├── app.js              # 主应用逻辑（初始化、路由）
│   ├── api.js              # 数据加载和 AI API 调用
│   ├── utils.js            # 工具函数
│   ├── storage.js          # localStorage 管理
│   ├── filters.js          # 筛选逻辑
│   ├── search.js           # 搜索逻辑
│   ├── paper.js            # 论文详情逻辑
│   ├── author.js           # 作者页面逻辑
│   ├── trends.js           # 趋势分析逻辑
│   ├── network.js          # 网络可视化逻辑
│   ├── ai.js               # AI 分析逻辑
│   ├── chat.js             # 对话逻辑（SSE 流式）
│   ├── i18n.js             # 国际化
│   ├── theme.js            # 主题切换
│   └── components/
│       ├── navbar.js       # 导航栏组件
│       ├── paperCard.js    # 论文卡片组件
│       ├── pagination.js   # 分页组件
│       ├── skeleton.js     # 骨架屏组件
│       ├── toast.js        # Toast 通知组件
│       └── modal.js        # 模态框组件
├── data/
│   ├── papers.json         # 论文数据
│   ├── papers.meta.json    # 元数据（统计、筛选选项）
│   ├── similarities.json   # 相似论文数据
│   ├── network.authors.json    # 作者网络数据
│   ├── network.keywords.json   # 关键词网络数据
│   ├── trends.json         # 趋势数据
│   └── subfield.distribution.json  # 子领域分布数据
├── lib/
│   ├── d3.min.js           # D3.js 库
│   ├── marked.min.js       # Markdown 解析库
│   └── chart.min.js        # 图表库
└── assets/
    └── icons/              # 图标资源（SVG）
```

## 数据导出策略

1. **论文数据**: 从 SQLite 导出为 JSON，包含所有字段
2. **相似论文**: 预计算 TF-IDF 相似度，导出每篇论文的 TOP 5 相似论文
3. **网络数据**: 预计算作者合作网络（TOP 50 作者）和关键词共现网络（TOP 200 关键词）
4. **趋势数据**: 预计算热点主题和增长趋势（1个月/3个月/6个月）
5. **筛选选项**: 导出期刊列表、学科列表、子领域列表、CNKI 学科列表
6. **统计数据**: 导出论文总数、期刊分布、年份分布、来源分布

## AI API 集成

### 支持的 AI 服务
1. **Zhipu GLM**: glm-4.7, glm-4.5-air, glm-4.7-flash
2. **SiliconFlow**: Qwen3.5-4B, Qwen3-8B, DeepSeek-R1

### API 调用方式
- 论文分析: POST 请求，返回完整分析结果
- 对话: SSE 流式响应，实时展示内容
- 趋势分析: POST 请求，返回结构化分析结果

### 错误处理
- API Key 无效: 提示用户检查配置
- 请求失败: 显示错误信息，支持重试
- 模型不可用: 自动切换到备用模型

## 性能优化策略

1. **数据加载**: 首次加载后缓存到 localStorage
2. **分片加载**: 大数据量时分片加载
3. **懒加载**: 网络可视化节点按需渲染
4. **防抖节流**: 搜索输入、筛选操作使用防抖
5. **虚拟滚动**: 长列表使用虚拟滚动（如需要）
