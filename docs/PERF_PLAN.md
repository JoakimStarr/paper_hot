# PaperPulse 性能优化与轻量化设计方案

> 状态：设计稿（未实施）
> 日期：2026-08-26
> 背景：页面切换初始化卡顿、`/api/papers` 偶发 500、模型列表存在写死兜底、前后端存在冗余代码。
> 验证基线：后端接口全部 <15ms（排除后端为卡顿主因）；前端 dev 模式每页需下载/解析 2–16MB 未压缩 JS。

---

## 目录

1. [修复已知问题](#一修复已知问题)
2. [轻量化设计](#二轻量化设计)
3. [冗余清理与功能复用](#三冗余清理与功能复用)
4. [模型选择动态化](#四模型选择动态化)
5. [分期与预期收益](#五分期与预期收益)

---

## 一、修复已知问题

### 1.1 切页卡顿 → 前端 JS 包瘦身

**根因**：dev 模式 chunk 巨大。首页一次加载需下载 `main-app.js` 8.0MB + `app/layout.js` 3.3MB + `app/page.js` 4.3MB；各路由 chunk `dashboard` 4.3MB、`paper/[id]` 4.2MB。markdown 渲染栈（react-markdown + micromark + remark，约 2MB+）因 `AiAnalysisModalProvider` 静态引入 `MarkdownRenderer`、且 `PaperCard` 经 `useAiAnalysisModal` 重复引入，被**逐页重复打包**（`layout.js`/`page.js`/`dashboard.js` 各含 214 处 micromark 引用）。

**方案**：

| 项 | 改法 | 预期 |
|---|---|---|
| P0 markdown 栈动态化 | `MarkdownRenderer` 改 `next/dynamic`（`ssr:false`）；所有使用点（`AiAnalysisModal.tsx:186`、home:323、trends、paper/[id]、topics）统一动态引用 | markdown 栈移出共享壳与各页 chunk，成为按需独立 chunk |
| P0 AiAnalysisModal 拆 context/UI | `AiAnalysisModalContext.tsx`（轻量 context+hook）与 `AiAnalysisModalUI.tsx`（模态 UI + 动态 MarkdownRenderer）分离；Provider 仅 open 时挂载 UI | 列表页 chunk 不再含模态 UI 与 markdown 栈 |
| P1 Layout 上移根布局 | 各页面移除 `<Layout>` 包裹，统一在 `app/layout.tsx` 渲染共享布局 | 导航不重挂载壳，健康探测/initBookmarks/initPins 只跑一次 |
| P1 依赖验证 | lucide-react 确认 dev 是否整包（layout.js 16 处引用）；`experimental.optimizePackageImports` / `webpack.splitChunks` 抽 react/react-dom/next 独立缓存 | 共享壳只解析一次 |
| P1 基线验收 | `npm run build` 记录 prod chunk 大小：main-app < 400KB、路由 chunk < 200KB | 可量化达标 |

### 1.2 偶发 500 → 会话卫生修复

**根因**：`backend/app/routers/papers.py:66-84` 的 `try/except Exception: pass` 吞掉 PinnedPaper / 屏蔽偏好查询异常但**不 `rollback()`**；异常被吞导致 `get_db` 的 except 分支不触发，路由继续用脏会话跑 `PaperCRUD.get_papers` → `sqlalchemy.exc.PendingRollbackError` → 整请求 500，坏连接回池后间歇性污染后续请求。

**方案**：
- **a. 路由内回滚**：两个 except 块补 `await db.rollback()`；抽 helper `_safe_query(db, coro, default)` 统一「失败→回滚→降级」。
- **b. 全局兜底**：`get_db` 或中间件层确保异常路径一定 rollback，防未来再有路由吞异常。
- **c. 可观测**：被吞异常打印 `logger.warning(..., exc_info=True)`，下次触发直接看到首因。
- **附带**：aiosqlite 连接池 `pool_pre_ping=True` 减少坏连接复用。

---

## 二、轻量化设计

### 2.1 前端

**依赖评估**：

| 依赖 | 体积(dev) | 引入处 | 现状 | 方案 |
|---|---|---|---|---|
| react-markdown 栈 | ~2MB | AiAnalysisModal/多页 | 静态、逐页重复 | 动态化（1.1） |
| mermaid | 8–10MB 拆几十 chunk | MarkdownRenderer | 已懒加载 | 收敛单 chunk（`mermaid/dist/mermaid.min.js` 或仅注册用到的 diagram），评估轻量替代 |
| d3 系列 | ~1MB+ | network/NetworkGraph | 页面级 chunk | 保持路由隔离；评估 canvas 渲染降 CPU |
| lucide-react | 待测 | 全站 | 可能 dev 整包 | 验证 tree-shake；必要时子路径导入 |

**请求层**：
- **启用 ETag/304**：后端 `/papers` 已算 ETag，前端 `api.ts` 从不发 `If-None-Match` → 加条件请求，筛选/翻页命中 304 零流量。
- **localStorage 缓存调参**：`cache.ts` TTL 5min / 50 条目；列表缓存可至 10min，与 304 二选一避免双缓存复杂化。
- **并行加载**：首页 `/papers`、`/read-ids`、筛选统计确认无串行依赖后 `Promise.all`。

**渲染层**：列表已分页 20/页 + `PaperCard` 已 `memo`；数据量增长后再评估 react-window 虚拟化（P2）。

### 2.2 后端

- **聚合接口进程内 TTL 缓存（P0）**：`filter-statistics`、`subfield-distribution`、`trending-topics` 加 30–60s 内存缓存（复用 dashboard `_briefing_ai_note` 1h TTL 模式）。
- **索引（P1）**：`/papers` 常用过滤列加 SQLite 索引：`published_at`、`journal_name`、`source`、`economics_subfield`、`cnki_subject`、`venue`、`PaperScore.final_score`。
- **写路径（P1）**：爬虫/批处理与读并发时 SQLite 锁 → 写已串行化（`_db_lock`）；读侧 `pool_pre_ping`；写冲突退避重试。
- **分页（P2）**：`get_papers` 深翻页改 keyset（`published_at,id` 游标）。

---

## 三、冗余清理与功能复用

### 3.1 前端

| 项 | 现状 | 方案 |
|---|---|---|
| 三 hook 合并（最大收益） | `useBookmarks` / `usePins` / `usePreferences` 结构一致（subscribe+init+version+ready+has/toggle）；`cache.ts` 三段「state+listeners+version+hydrate」同模板 | 抽通用工厂 `createRemoteStore<T>({ key, fetchApi })` 生成「存储层 + React hook」，三个功能实例化，删约 200 行重复 |
| `providerLabel`/`bareModelName` 重复 | `paper/[id]/page.tsx:49-55` 与 `trends/page.tsx:42-49` 逐字相同 | 移入 `lib/utils.ts` 单一导出 |
| 硬编码中文绕过 i18n | trends 48 处、system 25 处、dashboard 18 处、network 9 处等 | 补词表 key，按高频标签优先迁移 |
| 已复用良好（保持） | `usePapersPage`、`Filters/SearchBar/Pagination/PaperCard`、`trendIcon` 仅一处 | — |

### 3.2 后端

| 项 | 现状 | 方案 |
|---|---|---|
| CNKI 爬虫双栈（最大重复源） | `fetchers_cnki*.py`（DrissionPage）与 `cnki_paper_captcha.py`（Playwright）各有整套「期刊→详情→入库」 | P0 抽 `backend/app/cnki_common.py` 集中与浏览器栈无关的纯逻辑（详情页 HTML 解析、`_ensure_db`/`_db_existing_urls`/`_create_crawl_log`/`_update_crawl_log`/`save_to_database`、历史缓存读写），双栈引用；P2 收敛单栈（保留 Playwright 版） |
| `json_each` 关键词过滤重复 | `papers.py`/`ai.py`/`stats.py`/`crud.py` 四处各写一份 | 抽共享函数 `crud.keyword_filter_condition(column, keywords)` |
| 会话卫生 helper | 各路由 `try/except: pass` | `_safe_query` 统一（见 1.2） |
| 已集中良好（保持） | `_paper_to_card`/`_user_id`/`_isoformat_utc` 在 `deps.py`；`_load_hidden_preferences` 复用；`stats.py` 的 `_gap_score`/`_cooc_from_paper_keywords` 无重复 | — |

---

## 四、模型选择动态化

### 现状核查
- 前端模型下拉全部走 `getAIAnalysisModels()`（`/ai/models` → `get_model_status()`），**已动态**，无硬编码模型名。
- 任务级选模型走 `_resolve_model_provider(body.model)` / `_get_default_model`（默认取 `settings.default_model`），**已动态**。
- **写死残留**：
  1. `ai_service.py:37-39` `DEFAULT_MODELS`（内置 provider 未配模型时的硬编码兜底列表，易过期）。
  2. `ai_service.py:210-211` 每 provider 的 embedding 默认模型。
  3. 前端 `providerLabel` 显示名映射写死且两处重复。

### 方案
1. **内置 provider 无显式模型时自动拉取 `/models`**：把系统页 `fetch_provider_models`（`system.py:39`）逻辑抽到 `ai_service`；`_load_model_order()` 里 provider 有 API key 但 models 为空 → 调其 OpenAI 兼容 `GET /models` 获取真实可用模型，内存 TTL 10min 缓存；拉取失败才回退 `DEFAULT_MODELS`（收敛为保守少量或提示配置）。
2. **embedding 模型同理**：`embedding_model` 未配置时从 provider `/models` 动态选 embedding 类模型，拉不到才用 `ai_service.py:210` 默认。
3. **新增 provider 元数据接口** `GET /api/settings/providers` → `[{name, display_name, base_url, available}]`；前端 `providerLabel` 改由该接口下发（或移入 `utils.ts` 单一来源）。
4. **统一「当前可用模型」来源**：所有选模型 UI 与「默认模型」设置都基于 `get_model_status()`，不做第二套列表。

---

## 五、分期与预期收益

| 期 | 内容 | 预期 |
|---|---|---|
| **P0** | ① markdown 栈动态化 + AiAnalysisModal 拆分 ② papers 会话回滚 + `_safe_query` ③ 聚合接口 TTL 缓存 ④ 模型自动 `/models` 拉取 ⑤ 爬虫公共模块 `cnki_common.py` 抽取 ⑥ 三 hook 工厂合并 | 每页省 2–4MB；偶发 500 消失；聚合接口 0ms；模型不再依赖写死列表；CNKI 双栈逻辑合一；前端删 ~200 行重复 |
| **P1** | Layout 上移根布局 + ETag/304 + 索引 + `providerLabel` 收拢 utils + `json_each` 抽函数 + i18n 补词表 + provider 元数据接口 + lucide/vendor 验证 | 共享壳只解析一次；列表刷新走 304；过滤列走索引；模型显示名动态下发 |
| **P2** | 爬虫单栈收敛 + mermaid 收敛 + react-window 虚拟化 + keyset 分页 + 关键词表拆分 | 数据量增长后的长期可扩展与可维护 |

**验收基线**：`npm run build` 后 main-app < 400KB、路由 chunk < 200KB、markdown/mermaid 为按需 chunk；后端接口平均 < 5ms；日志零 500；模型列表与所选模型全部来自运行时配置/`/models` 拉取。
