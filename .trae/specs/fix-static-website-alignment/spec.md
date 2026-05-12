# 静态网站功能对齐修复规格

## Why
当前静态网站与原 Next.js 项目相比，存在功能不完整和样式不一致的问题，需要全面修复以确保用户体验一致。

## What Changes
- 修复论文详情页的 AI 分析功能（完整实现，包括 SSE 流式对话）
- 修复趋势页的 AI 分析功能（结构化分析结果展示）
- 统一所有页面的样式和布局（与原 Next.js 项目对齐）
- 修复页面结构和组件样式不一致的问题
- 完善追问讨论功能的 SSE 流式响应
- 完善历史报告功能
- **BREAKING**: 部分样式类名可能需要调整以统一

## Impact
- Affected specs: 论文详情页、趋势分析页、所有页面的样式
- Affected code: paper.html, trends.html, 所有 CSS 文件, api.js

## ADDED Requirements

### Requirement: 论文详情页 AI 分析完整实现
系统 SHALL 提供完整的 AI 论文分析功能，包括分析结果展示和追问讨论。

#### Scenario: AI 分析论文
- **WHEN** 用户点击"AI 分析"按钮
- **THEN** 系统调用 AI API 分析论文
- **AND** 展示结构化分析结果（研究背景、方法论创新、关键发现、研究意义）
- **AND** 分析状态保存到 localStorage

#### Scenario: 追问讨论
- **WHEN** 用户在论文详情页输入问题
- **THEN** 系统使用 SSE 流式响应展示 AI 回答
- **AND** 支持多轮对话
- **AND** 对话历史保存到 localStorage

### Requirement: 趋势页 AI 分析完整实现
系统 SHALL 提供完整的 AI 趋势分析功能，包括结构化分析结果和选题对话。

#### Scenario: AI 趋势分析
- **WHEN** 用户点击"开始分析"按钮
- **THEN** 系统调用 AI API 分析趋势数据
- **AND** 展示结构化分析结果：
  - 分析摘要
  - 研究热点（TOP N，包含描述和相关关键词）
  - 发展趋势（方向、描述）
  - 关键词聚类分析
  - 期刊分析
  - 研究建议

#### Scenario: 选题分析对话
- **WHEN** 用户在趋势页输入问题
- **THEN** 系统使用 SSE 流式响应展示 AI 回答
- **AND** 支持快捷问题按钮
- **AND** 支持对话历史导出

### Requirement: 页面样式统一
系统 SHALL 统一所有页面的样式和布局，与原 Next.js 项目保持一致。

#### Scenario: 样式一致性
- **WHEN** 用户浏览不同页面
- **THEN** 所有页面的颜色、间距、字体、组件样式保持一致
- **AND** 深色模式切换正常工作
- **AND** 响应式布局正常工作

## MODIFIED Requirements

### Requirement: 现有 AI 功能增强
原系统的 AI 功能需要增强以支持完整的分析和对话功能。

### Requirement: 样式系统统一
原系统的样式需要统一，确保所有页面使用一致的 CSS 变量和组件样式。

## REMOVED Requirements

### Requirement: 后端依赖功能
**Reason**: 静态网站无法使用后端 API
**Migration**: 改为客户端直接调用 AI API
