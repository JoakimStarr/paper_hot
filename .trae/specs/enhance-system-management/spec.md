# 系统管理页面完善 Spec

## Why

当前系统管理页面功能单薄，仅有基础统计、爬虫控制和爬取日志三个模块。缺少 API Key 管理、AI 模型配置、定时任务管理、数据维护等管理员核心功能，无法在不修改代码/重启服务的情况下调整系统配置。

## What Changes

* 新增 API Key 管理模块：查看/更新 Zhipu/OpenAI/SiliconFlow API Key，支持脱敏显示和即时生效

* 新增 AI 模型管理模块：查看/切换当前使用的模型优先级列表，显示模型可用状态y以及使用情况

* 新增定时任务管理模块：查看定时任务状态、手动触发任务、启用/禁用调度器

* 新增数据维护模块：数据库统计信息、一键清理僵尸数据、重建索引

* 重构系统页面布局：从单列改为分区 Tab 布局，各模块独立互不干扰

* 后端新增配置管理 API：GET/PUT /api/settings 端点，支持运行时修改配置

## Impact

* Affected code:

  * `backend/app/api.py` — 新增配置管理端点

  * `backend/app/config.py` — 添加运行时配置更新方法

  * `backend/app/ai_service.py` — 支持模型列表查询和热重载

  * `backend/app/scheduler.py` — 暴露任务状态和控制接口

  * `frontend/src/app/system/page.tsx` — 重构为 Tab 布局

  * `frontend/src/lib/api.ts` — 新增配置管理 API 调用

  * `frontend/src/types/paper.ts` — 新增类型定义

## ADDED Requirements

### Requirement: API Key 管理

系统 SHALL 提供运行时 API Key 管理功能。

#### Scenario: 查看 API Key 状态

* **WHEN** 管理员访问系统管理页面

* **THEN** 显示各 API Key 的配置状态（已配置/未配置），已配置的 Key 脱敏显示（仅显示前4位和后4位）

#### Scenario: 更新 API Key

* **WHEN** 管理员输入新的 API Key 并提交

* **THEN** 后端更新 .env 文件中的对应值，并即时重载 AI 服务，无需重启

### Requirement: AI 模型管理

系统 SHALL 提供 AI 模型优先级列表的查看和调整功能。

#### Scenario: 查看模型列表

* **WHEN** 管理员访问模型管理面板

* **THEN** 显示当前模型优先级列表及每个模型的可用状态（基于 API Key 是否配置）

#### Scenario: 调整模型优先级

* **WHEN** 管理员拖拽或选择调整模型顺序并保存

* **THEN** 后端更新模型优先级列表，下次分析时使用新顺序

### Requirement: 定时任务管理

系统 SHALL 提供定时任务的可视化管理。

#### Scenario: 查看任务状态

* **WHEN** 管理员访问任务管理面板

* **THEN** 显示所有定时任务的名称、调度频率、上次执行时间、下次执行时间、启用状态

#### Scenario: 手动触发任务

* **WHEN** 管理员点击某任务的"立即执行"按钮

* **THEN** 后端立即触发该任务，前端显示执行状态

#### Scenario: 启用/禁用调度器

* **WHEN** 管理员切换调度器开关

* **THEN** 后端暂停/恢复所有定时任务

### Requirement: 数据维护

系统 SHALL 提供数据库维护功能。

#### Scenario: 查看数据库统计

* **WHEN** 管理员访问数据维护面板

* **THEN** 显示数据库文件大小、各表记录数、最早的/最新的论文时间

#### Scenario: 清理无效数据

* **WHEN** 管理员点击"清理数据"按钮

* **THEN** 后端清理无标题/无摘要的论文、孤立的评分/特征记录、过期的僵尸分析报告

### Requirement: 系统页面 Tab 布局

系统管理页面 SHALL 使用 Tab 布局组织各功能模块。

#### Scenario: Tab 导航

* **WHEN** 管理员访问系统管理页面

* **THEN** 显示以下 Tab：概览、爬虫管理、API 配置、AI 模型、数据维护

* **AND** 每个 Tab 下展示对应的功能模块

## MODIFIED Requirements

### Requirement: 系统统计信息

系统统计信息 SHALL 增加数据库大小和调度器状态字段。

#### Scenario: 获取增强统计

* **WHEN** 前端请求 /api/stats

* **THEN** 返回数据中新增 db\_size\_mb（数据库文件大小MB）、scheduler\_running（调度器是否运行中）字段

