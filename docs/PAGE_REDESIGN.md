# 全站页面重设计方案 v3.1 · Atlas 版（优化修订稿）

> 状态：设计稿（未实施）
> 日期：2026-08-26
> 基于：v3 Atlas 版 + 对现有代码的可行性核实修订
> 关联：`docs/PERF_PLAN.md`（性能重构，IA 定型后实施）

## 修订说明（相对 v3）

1. **作者网络是「新增功能」，不是「从 keywords tab 中独立」**——现有代码无任何作者图谱实现（`/api/network/author-map` 不存在）。需新建后端作者合著图 + 前端力导图，排期上单列。
2. 作者页 `/author/[name]` **已存在**（前端路由 + `/api/authors/{name}/papers|stats`），纳入 IA 即可，无需新建。
3. 移除 network「年度演化」tab 后，**顺带删除 `app/network/TrendChart.tsx`**，避免 4.7MB 死 chunk 残留。
4. 「上下文操作」实现为**可选操作集合**组件（查地图仅 Atlas 需要）。
5. 系统管理分工只改展示层，**不动 `stats.py` 共享聚合**（被 Atlas/趋势页复用）。
6. 排期与进行中的趋势后端改动（crud.py/papers.py/scheduler.py）**错峰**，避免文件级冲突。
7. `docs/` 目录已建，`PERF_PLAN.md` 已归档于此。
8. **新增「AI 简易 Agent」章节**（第九章）：对全站 AI 使用点做了调研分级，多轮对话类 AI 升级为工具调用（可查库），一次性产出类保持预聚合。

---

## 〇、总纲：双维度主页 + 个人 Hub

全站按「两个分析主入口 + 一个个人中心」组织：

| 入口 | 页面 | 维度 | 回答的问题 |
|---|---|---|---|
| 领域 Atlas | `/network` | 结构（空间切片） | 领域长什么样？哪里有空白？ |
| 趋势洞察 | `/trends` | 时间（演化） | 什么在涨、什么在退？AI 怎么看？ |
| 我的 | 工作台/阅读历史/系统管理 | 个人 | 我的进展与系统健康 |

发现（首页/搜索）→ 理解（Atlas + 趋势）→ 选题（topics）→ 沉淀（我的）。

## 一、领域 Atlas `/network`（核心升级）

定位：**一站式领域全景地图**，回答「领域由哪些块组成、怎么连、哪里是空白」。

tab 结构（重排默认序，保留 4 tab 但去掉年度演化）：

| tab | 内容 | 变化 |
|---|---|---|
| **主题聚类地图**（默认） | 现 clusters：全景鸟瞰，点簇下钻关键词网络 | 升为默认 tab |
| **关键词网络** | 力导图 + 节点详情 + 研究版图（年度趋势/共现词/期刊/代表论文） | 保持，全站唯一关键词详情视图 |
| **作者网络** | 作者力导图 + 合作者，节点直连 `/author/[name]` | **新增**（见下方） |
| **研究空白** | 现 GapsPanel：空白列表 + 一键验证（预填 validator） | 保留并强化；选题中心不再重复实现 gaps |

- **作者网络 = 新增能力**：后端新建 `/network/authors`（作者合著共现，从 `papers.authors` JSON 聚合，复用 keyword 共现同法），前端复用 `NetworkGraph` 的 d3-force。**建议分两期**：R1 先上轻量版（Top 作者榜 + 合著者面板），力导图版 R2 后补。
- 年度演化：简化为聚类地图/关键词详情内的年度概览（迷你柱状已有）；详细演化归趋势页；Atlas 顶部留「查看趋势分析 →」入口卡。
- 移除 `trends` tab 时**删除 `app/network/TrendChart.tsx`**（动态 chunk 4.7MB，一并消失）。
- 每个关键词/热点/空白统一挂「上下文操作」：查论文（→搜索）/ 查趋势（→趋势页）/ 转选题（→验证器）；「查地图」仅 Atlas 内出现。

## 二、趋势洞察 `/trends`（时间主场 + AI 分析师）

区块顺序：① 研究热点榜（年度粒度、增长率排序，点击→论文列表）② 年度演化图（全站唯一完整版）③ 子领域雷达 ④ **AI 领域分析师**（合并）⑤ 历史报告恢复。

- **合并**：AI 趋势报告 + 趋势问答 → 一个「AI 领域分析师」区块：报告为默认产出，输入框对报告追问（共享上下文与模型选择器，**砍掉第二个模型选择器** `selectedModel`）。
- 裁剪：报告 keyword_insights 详情让位 Atlas 研究版图，关键词改为可点击跳 Atlas。
- 热点榜关键词挂上下文操作（查论文/查地图/转选题）。
- **风险提示**：trends 页是全局最重页面（48 处硬编码中文 + 报告轮询 + 问答流），合并改动面大，**单独一次 commit 保留回滚点**。

## 三、选题中心 `/topics`（决策主场）

- tab 由 4 → 3：**选题验证（默认）→ 选题库 → 生产者实验室**；`gaps` tab 移除（研究空白归 Atlas，Atlas 空白卡片「一键验证」直达此处并预填——现有 localStorage 跨页预填机制已支持）。
- 选题库卡片操作：继续验证 / 导出立项书 / 删除。
- 竞争地图（验证报告内，单选题态势）与生产者实验室（跨选题找合作者）不合并。
- validator 保留：流式报告 + 检索证据 + 竞争地图 + 立项书生成。

## 四、作者页 `/author/[name]`（纳入 IA，已存在）

全站唯一作者详情视图。入口统一：Atlas 作者网络节点、论文详情页作者名、PaperCard 作者、搜索结果。
板块：作者统计卡（发文量/活跃年份/主要期刊）→ 发文趋势 → 合作者 → 论文列表。

## 五、首页 / 搜索 / 工作台 / 阅读历史 / 系统管理

- **首页 `/`**：论文流核心保持（置顶/收藏/AI 悬浮窗/已读/批量操作）；新增「今日速览条」（今日入库 N 篇·关注子领域 M 篇，一键筛出，需小聚合端点）；高级筛选收进抽屉，首屏只留排序+期刊/子领域。
- **搜索 `/search`**：主动检索定位，与首页共用 usePapersPage 与 PaperCard；可选「保存检索条件」。
- **工作台 `/dashboard`**：维持 4 tab；stack 补「最近阅读」内嵌（复用 /reading 数据源）+ 查看全部。
- **阅读历史 `/reading`**：时间分组（今天/本周/更早）+ 一键重开 + 批量清空。
- **系统管理 `/system`**：概览=运行状态（任务/调度/错误），数据=数据资产（分布/向量/趋势/相关性），消除两 tab 统计重叠；**只改展示层，不动 `stats.py` 共享聚合**；爬虫、模型配置不变。

## 六、组件层汇总

| 动作 | 内容 |
|---|---|
| 新增共享 | `KeywordContextActions`（可选操作集合：查论文/查趋势/查地图/转选题，全站复用）、`SectionCard`（标题+折叠+查看全部统一壳）、`EntryCard`（跨页入口卡） |
| 迁移/重组 | 年度演化完整版归 trends；GapsPanel 留 network、topics 删除重复实现；删除 `app/network/TrendChart.tsx` |
| 复用 | PaperCard、usePapersPage、TrendList（趋势榜/工作台领域快讯共用） |
| 裁剪 | trends 第二个模型选择器；报告 keyword_insights 详情；topics gaps tab；首页常驻高级筛选 |

## 七、与 PERF_PLAN 的关系

先 IA 定型（本方案）→ 再性能重构（PERF_PLAN：Layout 上移根布局会翻动所有页面，避免二次返工）。

## 八、实施分期

- **R1 · Atlas 定型**：聚类默认、关键词网络保持、作者网络轻量版（Top 作者榜 + 合著者面板）+ 后端 `/network/authors`、年度演化简化 + 入口卡、移除 network trends tab 并清理 TrendChart、`KeywordContextActions`/`SectionCard`/`EntryCard` 落地。
- **R2 · 趋势 + 选题**：trends AI 分析师合并（单独 commit）；topics 去 gaps、默认 validator；**趋势追问接入 Agent**（见第九章 P0）。
- **R3 · 各页**：首页速览条/筛选抽屉（+小聚合端点）；阅读历史分组；工作台 stack 最近阅读；系统管理分工；**论文详情追问、选题验证证据接入 Agent**（第九章 P1）。
- **R4 · 性能**：接 PERF_PLAN。

**排期约束**：R1 触及 network 页、R2 触及 trends 页——待进行中的趋势后端改动（crud.py/papers.py/scheduler.py）合入后再动对应文件，避免冲突。

---

## 九、AI 简易 Agent（工具调用）升级

### 9.1 现状与动机

全站所有 AI 都是「**一次性上下文注入**」：代码预聚合好数据塞进 prompt，模型不能主动查库；追问也只是把报告快照原样带上。结果：模型对「近 3 年数字经济论文量变化」「列出供应链韧性相关 5 篇论文」「还有哪些空白没被覆盖」这类问题只能靠猜。

升级为简易 Agent = OpenAI 兼容 **tools / function calling**：模型按需调用后端封装的查询工具，结果回填后继续推理。当前技术栈天然支持——`ai_service`/`deps._stream_chat_response` 全部走 OpenAI 兼容接口，`tools` 参数直接透传；已配置模型（kimi-k3 / qwen3.8 / deepseek-v4 / GLM-5.3）均支持 function calling。

### 9.2 调研：全站 AI 使用点分级

| 表面 | 位置 | 当前输入 | Agent 价值 | 落点 |
|---|---|---|---|---|
| 单篇论文分析 | `papers.py:400/550` | abstract+title | 分析本体不需要（输入即论文） | 保持预聚合 |
| **单篇论文追问** | `papers.py:733` streamPaperChat | 论文+对话 | **高**（相似论文/方法对比/找证据） | 追问接 Agent |
| 趋势报告 | `ai.py:337` analyze_trends | 全量预聚合快照 | 报告保持预聚合（快/省/确定） | 保持 |
| **趋势追问** | `ai.py:491` chat_about_trend | 报告快照+对话 | **最高**（热度查询/论文列举/空白） | 追问接 Agent（P0） |
| **工作台 AI 简报** | `dashboard.py:177` | 关注子领域 topics 预聚合 | 中高（按子领域查新论文再写） | 可选（P2） |
| 话题热度解读 | `papers.py:290` | 年份序列 | 低（输入已足够） | 保持 |
| **选题验证报告+检索证据+追问** | `topic.py:207/845/761` | 预聚合证据 | 高（语义检索证据/竞争态势/空白） | 验证+追问接 Agent（P1） |
| 综述生成 | `producer.py:211/342` | 选定论文 | 中（可扩查相关文献） | 保持或可选 |
| 内部管道（摘要/关键词/主题分类/embedding） | `ai_processor.py` | 单篇输入 | 无 | 不动 |

**结论**：Agent 不是某个页面的专属能力，而是**通用对话能力**——凡是「多轮对话/深挖」类 AI 都接；「一次性产出」类保持预聚合。

### 9.3 核心设计（通用能力）

新模块 `backend/app/agent.py`：
- **工具注册表**：每个工具 `{name, description, parameters(JSON schema), handler}`，handler 复用现有查询（`crud.py` / `stats.py` / 各 router 查询函数），不改数据层。
- **执行循环** `run_agent_chat(messages, client, provider, model, db, tool_names=None, max_rounds=5)`：
  1. 工具轮用 `stream=False` + `tools=[...]`，拿到 `tool_calls`；
  2. 逐个执行（独立 async DB session，LIMIT ≤20，单工具超时）；
  3. 以 `role:"tool"` 回填消息，继续，最多 5–8 轮防死循环；
  4. 最终回答 `stream=True`，复用现有 SSE 通道；工具执行期间发 `agent_status` 事件（前端显示「正在查询数据库…」）。
- **按表面启用工具子集**：

| 表面 | 启用工具 |
|---|---|
| 单篇论文追问 | `search_papers` + `similar_papers` + `get_paper_detail` |
| 趋势追问 | `search_papers` + `paper_trend` + `subfield_distribution` + `keyword_cooccurrence` + `keyword_gaps` + `author_papers` |
| 选题验证/追问 | `search_papers` + `paper_trend` + `keyword_gaps` + `author_papers`（证据用 embedding 语义检索） |
| 工作台简报 | `search_papers`（按关注子领域） |

- **工具清单**（均封装现有查询）：`search_papers`（关键词/字段/年份/期刊/主题）、`get_paper_detail`、`similar_papers`（复用相似度表）、`paper_trend`（按年计数）、`subfield_distribution`、`keyword_cooccurrence`、`keyword_gaps`、`author_papers`。

### 9.4 混合策略与约束

- **混合**：一次性产出（报告/分析/摘要）保持预聚合快照——1 次调用、结果确定、成本低；**Agent 只用于多轮对话/深挖**（追问、证据检索、验证）。避免每次开报告都跑 N 轮工具循环。
- **约束**：工具参数 JSON schema 严格校验 + 类型钳制；LIMIT 封顶与结果截断（防上下文膨胀）；单工具超时；`max_rounds` 上限；模型不返回合法 `tool_calls` 时降级为普通对话（不破坏现有功能）；每工具独立 DB 会话（异常回滚）。

### 9.5 落点与分期

- **P0（R2）**：趋势页「AI 领域分析师」追问接 Agent。
- **P1（R3）**：论文详情页追问、选题验证证据检索接 Agent。
- **P2（R3 可选）**：工作台 AI 简报接 Agent。
- 一次性产出（趋势报告、单篇分析、综述初稿）明确保持预聚合，不做工具循环。
