# Tasks

## Phase 1: 数据导出与准备
- [x] Task 1: 创建数据导出脚本，从 SQLite 导出论文数据为 JSON
  - [x] SubTask 1.1: 导出论文基础数据（papers.json）- 包含所有字段
  - [x] SubTask 1.2: 导出论文元数据（papers.meta.json）- 统计、筛选选项、期刊列表、学科列表、子领域列表
  - [x] SubTask 1.3: 导出相似论文数据（similarities.json）- 每篇论文 TOP 5 相似论文
  - [x] SubTask 1.4: 导出作者网络数据（network.authors.json）- TOP 50 作者合作网络
  - [x] SubTask 1.5: 导出关键词网络数据（network.keywords.json）- TOP 200 关键词共现网络
  - [x] SubTask 1.6: 导出趋势数据（trends.json）- 热点主题、增长率（1个月/3个月/6个月）
  - [x] SubTask 1.7: 导出子领域分布数据（subfield.distribution.json）- 用于雷达图

## Phase 2: 基础框架搭建
- [x] Task 2: 创建静态网站目录结构
  - [x] SubTask 2.1: 创建 /home/joakim/Project/hmAPP/blog/source/paper/ 目录
  - [x] SubTask 2.2: 创建 css/、js/、data/、lib/、assets/ 子目录
  - [x] SubTask 2.3: 复制第三方库（D3.js、marked.js、Chart.js）
- [x] Task 3: 创建基础 CSS 样式文件
  - [x] SubTask 3.1: 创建 main.css - 主样式（布局、排版、响应式）
  - [x] SubTask 3.2: 创建 components.css - 组件样式（卡片、按钮、表单、标签、分页）
  - [x] SubTask 3.3: 创建 animations.css - 动画效果（骨架屏、过渡、脉冲）
  - [x] SubTask 3.4: 创建 dark.css - 深色模式样式
- [x] Task 4: 创建核心 JavaScript 模块
  - [x] SubTask 4.1: 创建 utils.js - 工具函数（日期格式化、URL 参数解析、防抖节流）
  - [x] SubTask 4.2: 创建 i18n.js - 国际化翻译（中英文完整翻译）
  - [x] SubTask 4.3: 创建 theme.js - 主题切换逻辑（系统偏好检测、localStorage 持久化）
  - [x] SubTask 4.4: 创建 storage.js - localStorage 管理（收藏、API Key、分析状态）
  - [x] SubTask 4.5: 创建 api.js - 数据加载、缓存、AI API 调用封装

## Phase 3: 通用组件开发
- [x] Task 5: 创建导航栏组件
  - [x] SubTask 5.1: 创建导航栏 HTML 结构
  - [x] SubTask 5.2: 实现导航栏响应式布局
  - [x] SubTask 5.3: 实现主题切换按钮
  - [x] SubTask 5.4: 实现语言切换按钮
- [x] Task 6: 创建论文卡片组件
  - [x] SubTask 6.1: 创建论文卡片 HTML 结构
  - [x] SubTask 6.2: 实现卡片悬停效果
  - [x] SubTask 6.3: 实现收藏按钮功能
  - [x] SubTask 6.4: 实现关键词点击跳转
- [x] Task 7: 创建分页组件
  - [x] SubTask 7.1: 创建分页 HTML 结构
  - [x] SubTask 7.2: 实现页码切换逻辑
  - [x] SubTask 7.3: 实现每页数量选择
  - [x] SubTask 7.4: 实现总数显示
- [x] Task 8: 创建骨架屏组件
  - [x] SubTask 8.1: 创建骨架屏 HTML 结构
  - [x] SubTask 8.2: 实现骨架屏动画效果
- [x] Task 9: 创建 Toast 通知组件
  - [x] SubTask 9.1: 创建 Toast HTML 结构
  - [x] SubTask 9.2: 实现 Toast 显示/隐藏动画
  - [x] SubTask 9.3: 实现 Toast 自动消失

## Phase 4: 首页开发
- [x] Task 10: 创建首页（index.html）
  - [x] SubTask 10.1: 创建 HTML 结构（导航栏、标题、搜索框、筛选器、论文列表、分页）
  - [x] SubTask 10.2: 创建筛选器组件（期刊、学科、子领域、CNKI学科、评分、排序）
  - [x] SubTask 10.3: 实现数据加载和缓存
  - [x] SubTask 10.4: 实现筛选逻辑（客户端过滤）
  - [x] SubTask 10.5: 实现分页逻辑
  - [x] SubTask 10.6: 实现排序逻辑
  - [x] SubTask 10.7: 实现收藏功能
  - [x] SubTask 10.8: 实现骨架屏加载效果
  - [x] SubTask 10.9: 实现搜索跳转

## Phase 5: 论文详情页开发
- [x] Task 11: 创建论文详情页（paper.html）
  - [x] SubTask 11.1: 创建 HTML 结构（返回按钮、论文信息、评分卡片、相似论文、AI 分析区域）
  - [x] SubTask 11.2: 实现论文数据加载（从 URL 参数获取 ID）
  - [x] SubTask 11.3: 实现论文信息展示（标题、作者、摘要、关键词、DOI、期刊等）
  - [x] SubTask 11.4: 实现评分展示（Recency、Venue、Trend、Should Read）
  - [x] SubTask 11.5: 实现相似论文展示
  - [x] SubTask 11.6: 实现 AI 分析按钮和加载状态
  - [x] SubTask 11.7: 实现 AI 分析结果展示（Markdown 渲染）
  - [x] SubTask 11.8: 实现追问讨论功能（SSE 流式响应）
  - [x] SubTask 11.9: 实现分析状态持久化（localStorage）
  - [x] SubTask 11.10: 实现模型选择功能

## Phase 6: 作者页面开发
- [x] Task 12: 创建作者页面（author.html）
  - [x] SubTask 12.1: 创建 HTML 结构（作者信息、统计卡片、论文列表）
  - [x] SubTask 12.2: 实现作者数据加载（从 URL 参数获取作者名）
  - [x] SubTask 12.3: 实现作者统计展示（论文总数、第一作者数、最近年份、主要期刊、热门关键词、主要领域）
  - [x] SubTask 12.4: 实现作者论文列表（分页）
  - [x] SubTask 12.5: 实现合作者展示

## Phase 7: 搜索页面开发
- [x] Task 13: 创建搜索页面（search.html）
  - [x] SubTask 13.1: 创建 HTML 结构（搜索框、搜索字段选择、搜索结果）
  - [x] SubTask 13.2: 实现搜索逻辑（标题、作者、关键词搜索）
  - [x] SubTask 13.3: 实现自动补全功能
  - [x] SubTask 13.4: 实现搜索结果展示
  - [x] SubTask 13.5: 实现期刊筛选功能
  - [x] SubTask 13.6: 实现分页功能

## Phase 8: 趋势分析页面开发
- [x] Task 14: 创建趋势分析页面（trends.html）
  - [x] SubTask 14.1: 创建 HTML 结构（时间范围选择、趋势图表、雷达图、AI 分析区域）
  - [x] SubTask 14.2: 实现热点主题展示（主题名称、论文数量、增长率、趋势方向）
  - [x] SubTask 14.3: 实现趋势折线图（Chart.js）
  - [x] SubTask 14.4: 实现研究热点雷达图（Chart.js Radar）
  - [x] SubTask 14.5: 实现时间范围切换
  - [x] SubTask 14.6: 实现 AI 趋势分析按钮和加载动画
  - [x] SubTask 14.7: 实现 AI 分析结果展示（摘要、热点、趋势、关键词聚类、期刊分析、研究建议）
  - [x] SubTask 14.8: 实现选题分析对话功能（SSE 流式响应）
  - [x] SubTask 14.9: 实现快捷问题按钮
  - [x] SubTask 14.10: 实现模型选择功能
  - [x] SubTask 14.11: 实现对话记录导出功能
  - [x] SubTask 14.12: 实现对话清空功能
  - [x] SubTask 14.13: 实现历史报告功能

## Phase 9: 网络可视化页面开发
- [x] Task 15: 创建网络可视化页面（network.html）
  - [x] SubTask 15.1: 创建 HTML 结构（标签切换、D3.js 画布、节点详情面板）
  - [x] SubTask 15.2: 实现 D3.js 力导向图基础框架
  - [x] SubTask 15.3: 实现作者合作网络可视化
  - [x] SubTask 15.4: 实现关键词共现网络可视化
  - [x] SubTask 15.5: 实现节点大小映射（论文数/出现次数）
  - [x] SubTask 15.6: 实现边粗细映射（合作次数/共现次数）
  - [x] SubTask 15.7: 实现缩放和拖拽功能
  - [x] SubTask 15.8: 实现节点点击高亮
  - [x] SubTask 15.9: 实现节点详情展示
  - [x] SubTask 15.10: 实现关联节点列表
  - [x] SubTask 15.11: 实现节点导航功能（跳转搜索）
  - [x] SubTask 15.12: 实现清除高亮功能

## Phase 10: 设置页面开发
- [x] Task 16: 创建设置页面（settings.html）
  - [x] SubTask 16.1: 创建 HTML 结构（API Key 配置表单、模型选择）
  - [x] SubTask 16.2: 实现 API Key 输入和保存
  - [x] SubTask 16.3: 实现 API Key 验证
  - [x] SubTask 16.4: 实现配置状态展示
  - [x] SubTask 16.5: 实现模型优先级配置

## Phase 11: AI 功能集成
- [x] Task 17: 实现 AI 分析核心功能
  - [x] SubTask 17.1: 创建 ai.js - AI API 调用封装
  - [x] SubTask 17.2: 实现 Zhipu GLM API 调用
  - [x] SubTask 17.3: 实现 SiliconFlow API 调用
  - [x] SubTask 17.4: 实现 SSE 流式响应处理
  - [x] SubTask 17.5: 实现 Markdown 渲染（marked.js）
  - [x] SubTask 17.6: 实现错误处理和重试
  - [x] SubTask 17.7: 实现模型自动切换

## Phase 12: 测试与优化
- [x] Task 18: 功能测试
  - [x] SubTask 18.1: 测试首页论文列表加载
  - [x] SubTask 18.2: 测试首页筛选功能
  - [x] SubTask 18.3: 测试首页分页功能
  - [x] SubTask 18.4: 测试首页收藏功能
  - [x] SubTask 18.5: 测试论文详情页展示
  - [x] SubTask 18.6: 测试论文详情页 AI 分析
  - [x] SubTask 18.7: 测试论文详情页追问讨论
  - [x] SubTask 18.8: 测试作者页面展示
  - [x] SubTask 18.9: 测试搜索功能
  - [x] SubTask 18.10: 测试趋势页面展示
  - [x] SubTask 18.11: 测试趋势页面 AI 分析
  - [x] SubTask 18.12: 测试网络可视化
  - [x] SubTask 18.13: 测试设置页面
  - [x] SubTask 18.14: 测试深色模式
  - [x] SubTask 18.15: 测试国际化
- [x] Task 19: 性能优化
  - [x] SubTask 19.1: 优化数据加载（懒加载、分片加载）
  - [x] SubTask 19.2: 优化网络可视化性能
  - [x] SubTask 19.3: 添加数据缓存策略
  - [x] SubTask 19.4: 优化搜索防抖

## Phase 13: 部署准备
- [x] Task 20: 准备 GitHub Pages 部署
  - [x] SubTask 20.1: 测试本地静态服务器
  - [x] SubTask 20.2: 验证所有链接和资源路径（相对路径）
  - [x] SubTask 20.3: 验证所有页面功能正常
  - [x] SubTask 20.4: 创建 README.md 说明部署方法

# Task Dependencies
- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 2]
- [Task 4] depends on [Task 2]
- [Task 5] depends on [Task 3]
- [Task 6] depends on [Task 3]
- [Task 7] depends on [Task 3]
- [Task 8] depends on [Task 3]
- [Task 9] depends on [Task 3]
- [Task 10] depends on [Task 3, Task 4, Task 5, Task 6, Task 7, Task 8]
- [Task 11] depends on [Task 3, Task 4, Task 6, Task 8, Task 9]
- [Task 12] depends on [Task 3, Task 4, Task 6, Task 7, Task 8]
- [Task 13] depends on [Task 3, Task 4, Task 6, Task 7, Task 8]
- [Task 14] depends on [Task 3, Task 4, Task 8, Task 9]
- [Task 15] depends on [Task 3, Task 4]
- [Task 16] depends on [Task 3, Task 4, Task 9]
- [Task 17] depends on [Task 4]
- [Task 18] depends on [Task 10-17]
- [Task 19] depends on [Task 18]
- [Task 20] depends on [Task 19]
