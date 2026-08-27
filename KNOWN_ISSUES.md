# 遗留问题清单（2026-08-27 全量审查修复后）

> 2026-08-27 基于五路并行代码审查（数据层/路由/AI·调度/爬虫/前端）完成一轮全量修复。
> 验证基线：后端 pytest 45 passed、`from app.main import app` 冒烟通过、前端 `tsc --noEmit` 通过。

---

## 一、本轮修复的高危缺陷（历史记录）

### 1. ✅ 摘要回填 CompileError（P0-2 整体失效）
`crud.update_paper_abstract` 曾写入不存在的 `updated_at` 列导致 SA2.0 编译报错、整批回滚。已删除幽灵列；
同时 `_process_and_score_paper` 改为特征/评分按 paper_id **upsert**（`create_paper_score(update_if_exists=True)`），
重复入库/回填重算不再撞唯一约束。

### 2. ✅ Agent 工具循环从未真正执行
`agent.run_agent_chat` 对 sync OpenAI 客户端直接 `await` 必然 TypeError 被吞。已改为 `asyncio.to_thread(...)`
下放线程池；工具会话 rollback 移入绑定保护内。

### 3. ✅ 爬虫单篇失败毒化整个批次
三个爬取循环的 `except ... continue` 现在都会先 `await db.rollback()`，一颗重复 DOI 不再丢掉整期期刊。

### 4. ✅ CNKI 验证码检测自锁死循环
注入页面的提示横幅文本自身触发检出词匹配。横幅加 `id=crawler-banner-overlay` 并在采样前剥离；
指示词删除裸「验证」；连续多轮页面无变化时提前退出不再满 300s 白等。

### 5. ✅ user_id 隔离割裂
topic.py 的 TopicProject / ResearchGapReport 写读两端曾硬编码 `"local"`。统一 `_uid_from(request)`
（x-user-id 头），patch/delete 校验归属；历史 "local" 行对 uid=="local" 会话天然可见。

### 6. ✅ 设置持久化改数据库
新增 `system_settings` 表 + `app/settings_store.py`：
- **优先级：system_settings(DB) > 环境变量 > backend/.env 基线**
- 启动早期同步加载覆盖（SQLite 直读，必须在 FastAPI app 构建前生效）
- 设置页保存写 DB 并即时生效；端口键额外镜像写 `.env`（start.sh 启动前要读）
- `config.Settings.update_setting`（裸写 .env）已删除，`.env.example` 全量重写

### 7. ✅ 其他高危
- arXiv 抓取包 `asyncio.wait_for(timeout=180)`，不再可能无限挂起调度 worker
- 浏览器爬虫重流程（CNKI TOP50 / NAVI）整体 `asyncio.to_thread` 化，等验证码期间后端仍有响应
- backfill_abstracts 的惰性 import 移入 try、run_backfill 加兜底，任务状态不会永久 running
- 手动触发爬虫三入口全部防重入（同类型 running 直接 400），返回的 task_id 现在真的可追踪
- 单篇分析：启动清理回收 `paper_analyses.pending` 僵尸（>30min）；运行中悬挂 pending 超 30min 允许重新提交
- 仅配 key 未配模型列表时回退内置候选模型（此前表现为「点了分析静默消失」）

## 二、一致性/性能修复摘要

- TopicTrend 年桶粒度：dashboard 领域快讯与 topic 空白解读改为「最近 N 个年份桶」聚合，
  「除 1~2 月外恒空」的问题消除；`get_keyword_monthly_counts` 更名 `get_keyword_yearly_counts`
  （旧名保留 deprecated 别名），同比严格相邻年份比对
- ETag 缓存键纳入 pinned/hidden 个性化成分；Cache-Control 改 `private, no-cache`（仅协商缓存）
- embed_texts：按 item.index 重排+数量校验防错位；分批容错不丢成功批次；截断默认收紧 4000→2000 字符；
  自定义 provider 只选名字含 "embed" 的模型作 embedding 候选
- 计算密集/网络调用全面让出事件循环：compute_embedding_async、embed_texts_async、空白解读 to_thread
- 扩展依赖保持按需加载（本次复核确认）：jieba/sklearn/numpy 只在爬虫/召回路径函数内 import；
  openai 客户端构建在函数内；前端 mermaid/docx 动态 import、D3 按 subpath 且仅网络图路由加载
- 时区统一 UTC 口径，弃用 `datetime.utcnow()` 全部替换；personal 计数下推 SQL COUNT
- AI 服务 reload() 原子替换 + 旧客户端显式 close；死代码批量清除（schemas×5、scheduler 方法×2、
  scoring 第二公式与僵尸常量、config 死配置 fetch_interval_hours 等）

## 三、刻意保留 / 已知边界

### 1. 经济学季刊摘要/卷期 —— 维持「刻意不做」（KNOWN_ISSUES v1 #1 结论不变）

### 2. CNKI 验证码滑块选择器需真机校准
守卫式方案 + ddddocr 已就位，失败自动转人工；navi 版 `_check_captcha` 已恢复元素级探测（保守 False 兜底）。

### 3. 根目录登录态文件（cnki_state*.json）
含有效知网会话 Cookie，已被 .gitignore 覆盖且从未入库；是 cnki_paper_captcha.py 断点续爬的工作文件，
保留本机使用。**严禁拷贝到仓库外或提交。**

### 4. fetchers_cnki.CNKIDrissionFetcher 复合检索 URL 方案存疑
复合查询串塞 `kw=` 参数的方式与真实知网检索页不符，疑从未端到端跑通（NAVI/关键词脚本栈可用）。
待真机验证后再决定去留，暂保留入口。

### 5. P3 明确未做（计划内后续，非缺陷）
- 数据源扩展：CSSCI、Crossref/OpenAlex 接入
- 多用户 + 团队协作（选题库共享）
- 新论文订阅推送（每日邮件/接口）
- CNKI 三套爬虫栈公共逻辑抽 `app/cnki_common.py`（P2 单栈化一并处理）

---

## 快速验证备忘

```bash
# 后端测试（仓库根目录）
cd backend && ../venv/bin/python -m pytest tests/ -q
# 应用可导入冒烟
cd backend && ../venv/bin/python -c "from app.main import app"
# 前端类型检查
cd frontend && npx tsc --noEmit
# 冒烟（服务启动后）
curl "localhost:8000/api/dashboard"
curl "localhost:8000/api/papers?search=%22数字%22%20NOT%20社会"
curl "localhost:8000/api/network/keyword-map?keyword=数字经济"
```
