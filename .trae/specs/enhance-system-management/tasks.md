# Tasks

- [x] Task 1: 后端 — 新增配置管理 API
  - [x] SubTask 1.1: 在 config.py 中添加 `update_setting()` 方法，支持运行时修改配置并写入 .env 文件
  - [x] SubTask 1.2: 在 api.py 中添加 `GET /api/settings` 端点，返回当前配置（API Key 脱敏、模型列表、调度器状态）
  - [x] SubTask 1.3: 在 api.py 中添加 `PUT /api/settings` 端点，支持更新 API Key 和模型优先级
  - [x] SubTask 1.4: 在 ai_service.py 中添加 `reload()` 方法和 `get_model_status()` 方法
  - [x] SubTask 1.5: 在 scheduler.py 中添加 `get_jobs_info()`、`trigger_job()`、`pause()`、`resume()` 方法
  - [x] SubTask 1.6: 在 api.py 中添加 `POST /api/scheduler/trigger/{job_id}`、`POST /api/scheduler/toggle` 端点
  - [x] SubTask 1.7: 增强 `GET /api/stats` 端点，新增 db_size_mb 和 scheduler_running 字段
  - [x] SubTask 1.8: 添加 `POST /api/maintenance/cleanup` 端点，清理无效数据

- [x] Task 2: 前端 — 重构系统管理页面为 Tab 布局
  - [x] SubTask 2.1: 在 types/paper.ts 中新增 SettingsInfo、SchedulerJob、MaintenanceResult 类型定义
  - [x] SubTask 2.2: 在 api.ts 中新增 getSettings、updateSettings、getSchedulerJobs、triggerJob、toggleScheduler、cleanupData API 调用
  - [x] SubTask 2.3: 重构 system/page.tsx 为 Tab 布局（概览、爬虫管理、API 配置、AI 模型、数据维护）
  - [x] SubTask 2.4: 实现概览 Tab：保留原有统计卡片 + 来源分布 + Top期刊 + 新增数据库大小和调度器状态
  - [x] SubTask 2.5: 实现爬虫管理 Tab：迁移原有爬虫控制和日志功能
  - [x] SubTask 2.6: 实现 API 配置 Tab：显示各 API Key 状态（脱敏），支持输入更新
  - [x] SubTask 2.7: 实现 AI 模型 Tab：显示模型列表和可用状态，支持拖拽排序调整优先级
  - [x] SubTask 2.8: 实现数据维护 Tab：数据库统计、清理按钮和结果反馈

# Task Dependencies
- Task 2 depends on Task 1（前端 API 调用依赖后端端点）
- SubTask 2.4-2.8 可并行开发（各 Tab 独立）
