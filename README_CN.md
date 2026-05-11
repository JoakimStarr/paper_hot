# PaperPulse 论文脉搏

<p align="center">
  <strong>中文经济学论文发现与分析平台</strong>
</p>

<p align="center">
  追踪 50+ 个顶级经济学期刊和 arXiv AI 论文，提供 AI 智能分析、追问讨论、相似度匹配、趋势分析和关系网络可视化。
</p>

---

## ✨ 功能特性

### 📚 论文发现
- **多源数据聚合**：覆盖 CNKI 知网经济学 TOP50 期刊、6 个自建站点爬虫（管理世界、经济研究、经济学季刊、世界经济、中国工业经济、American Economic Review）、arXiv AI 领域论文
- **智能多维筛选**：按期刊、学科领域、经济学子领域、CNKI 学科分类、关键词搜索、评分范围、时间范围多维筛选，支持回车搜索
- **排序与分页**：支持按发布时间+期数、综合评分排序；首页预加载前 3 页，localStorage 缓存秒开
- **专用搜索页**：独立搜索页面，支持全字段搜索 + 搜索自动补全建议（关键词/作者/标题）
- **骨架屏加载**：数据加载时展示骨架屏动画，优化用户体验

### 📄 论文详情
- **完整元数据展示**：标题、作者、摘要、关键词、期刊名+期数、DOI（可点击跳转原文）、发表时间
- **AI 智能分析**：基于智谱 GLM / 硅基流动 Qwen 的单篇论文深度分析，从研究背景、方法创新、主要发现、研究意义四个维度解读
- **状态追踪**：分析状态持久化（pending → success/failed），页面刷新不丢失
- **追问讨论**：SSE 流式输出的追问对话，Markdown 渲染，聊天历史自动持久化
- **相似论文推荐**：基于 jieba 分词 + TF-IDF 余弦相似度，实时展示 TOP 5 相关论文及相似度分数

### 👤 作者主页
- **作者论文列表**：按作者聚合所有论文，分页展示
- **作者统计信息**：论文总数、第一作者论文数、最近发表年份、主要期刊、热门关键词、主要子领域
- **合作者网络**：展示该作者的合作者及合作频次

### 📈 趋势分析
- **趋势话题追踪**：基于关键词频率增长率的动态话题趋势，支持 rising/stable/declining 状态标记
- **AI 趋势报告**：异步后台 AI 分析生成结构化趋势报告（研究热点、发展趋势、关键词洞察、期刊洞察、研究建议），支持轮询状态
- **趋势报告追问**：对 AI 趋势报告进行追问讨论，深入解读研究热点和选题机会

### 🕸️ 关系网络
- **关键词共现网络**：D3.js 交互式力导向图，可视化关键词之间的共现关系，支持缩放拖拽
- **作者合作网络**：D3.js 交互式作者合作关系图，展示学术合作生态

### 🕷️ 爬虫管理
- **多线程 CNKI 爬虫**：基于 DrissionPage 的知网期刊爬虫，支持经济学 TOP50 期刊自动化批量爬取
- **自建站点爬虫**：6 个经济学重点期刊的专用爬虫，支持断点续爬
- **验证码识别**：自动检测 + 手动辅助验证码处理
- **爬取历史**：URL 去重、增量爬取、爬取日志持久化

### ⚙️ 系统管理
- **数据库统计**：论文总数、期刊分布、年份分布、来源统计、AI 使用量统计等系统概览
- **爬虫日志**：实时查看爬虫运行状态和历史记录
- **手动触发**：支持手动触发爬虫任务、趋势分数更新、相似度全量重算
- **在线设置**：动态配置 API Key、模型优先级、端口、应用名称
- **调度器管理**：暂停/恢复定时任务、手动触发调度任务
- **数据库维护**：清理无效数据和僵尸分析报告

### 🌐 国际化 & 主题
- **中英双语**：界面完整支持中文/英文切换
- **暗黑模式**：支持亮色/暗色主题切换，自动跟随系统偏好

---

## 📊 数据源

| 来源 | 期刊数 | 说明 |
|---|---|---|
| CNKI 知网 | 50 | 经济学 TOP50 期刊，按优先级分类抓取 |
| 自建站点爬虫 | 6 | 管理世界、经济研究、经济学季刊、世界经济、中国工业经济、AER |
| arXiv | 4 类别 | cs.AI, cs.CL, cs.LG, cs.CV |

### CNKI 经济学 TOP50 期刊

**顶级期刊**：经济研究、管理世界、经济学（季刊）、世界经济、中国工业经济、中国社会科学、金融研究、数量经济技术经济研究

**重要期刊**：财贸经济、中国农村经济、经济学动态、国际经济评论、改革、中国人口科学、农业经济问题、中国农村观察、财政研究、税务研究、会计研究、审计研究

**国际贸易与世界经济**：国际贸易问题、国际经贸探索、世界经济研究、经济社会体制比较

**综合性经济期刊**：经济学家、经济科学、经济理论与经济管理、南开经济研究、当代经济科学、当代经济研究等

> 完整 50 个期刊列表见 [fetchers_cnki.py](backend/app/fetchers_cnki.py)

---

## 🛠️ 技术栈

### 后端

| 类别 | 技术 |
|---|---|
| 框架 | FastAPI + Uvicorn |
| 数据库 | SQLite + aiosqlite + SQLAlchemy ORM（兼容 PostgreSQL） |
| AI 服务 | zai-sdk（智谱 GLM-4.7 / GLM-4.5-Air / GLM-4.7-Flash）+ OpenAI SDK（硅基流动 Qwen3.5-4B / Qwen3-8B / DeepSeek-R1） |
| 相似度 | jieba 分词 + scikit-learn TF-IDF + 余弦相似度 |
| 任务调度 | APScheduler（定时爬取、趋势更新） |
| 爬虫 | DrissionPage（知网）、BeautifulSoup4 + lxml（自建站点） |
| 流式传输 | SSE (Server-Sent Events) |
| 容器化 | Docker + Dockerfile |

### 前端

| 类别 | 技术 |
|---|---|
| 框架 | Next.js 14 + React 18 + TypeScript |
| 样式 | Tailwind CSS + @tailwindcss/typography + 暗黑模式 |
| 图表 | Recharts（趋势图）+ D3.js（关系网络） |
| Markdown | react-markdown + remark-gfm |
| HTTP | axios |
| 图标 | lucide-react |
| 日期 | date-fns |
| 国际化 | 自研 LanguageContext + i18n |
| 缓存 | localStorage 分页预缓存 |
| 容器化 | Docker + Dockerfile |

---

## 📐 评分系统

论文综合评分由三个维度加权计算：

| 维度 | 权重 | 计算方法 |
|---|---|---|
| 时效性 (Recency) | 50% | 指数衰减函数 `e^(-0.1 × 天数)`，论文越新分数越高 |
| 期刊权威性 (Venue) | 30% | 基于期刊分级的权威分数 |
| 趋势热度 (Trend) | 20% | 基于主题增长率 + Sigmoid(tanh) 平滑映射 |

---

## 🔗 相似度算法

使用 **jieba 中文分词** + **TF-IDF 向量化** + **余弦相似度**：

1. 对所有论文摘要进行 jieba 分词
2. TfidfVectorizer 构建 TF-IDF 矩阵（max_features=10,000）
3. 两两计算余弦相似度
4. 筛选 score > 0.05 的对存入 `paper_similarities` 表
5. 查询时从表读取 TOP 5，毫秒级响应

支持新论文入库后单篇重算或全量重算。

---

## 🤖 AI 双通道架构

系统支持智谱 AI 和硅基流动双通道，自动降级切换：

| 通道 | 模型 | 用途 |
|---|---|---|
| 智谱 GLM | glm-4.7 → glm-4.5-air → glm-4.7-flash | 趋势分析、论文分析、追问对话 |
| 硅基流动 | Qwen3.5-4B → Qwen3-8B → DeepSeek-R1 | 降级备选通道 |

特性：
- 每个模型最多重试 2 次
- GLM 通道优先，失败后自动切换硅基流动
- 支持在线动态配置模型优先级
- 结构化 JSON 输出（趋势分析）

---

## 🗄️ 数据库架构

| 表 | 说明 |
|---|---|
| papers | 论文主表（标题、作者、摘要、DOI、关键词、期刊期数等） |
| paper_features | 论文特征（AI 摘要、关键词提取、主题分类） |
| paper_scores | 评分（时效、期刊、趋势、综合） |
| paper_analyses | 单篇 AI 分析历史（含 status 状态追踪） |
| paper_chats | 追问聊天记录（按 user/assistant 角色存储） |
| paper_similarities | 预计算 TF-IDF 余弦相似度（持久化） |
| topic_trends | 话题趋势数据（话题、周次、增长率） |
| crawl_logs | 爬虫运行日志 |
| ai_analysis_reports | 趋势分析报告（结构化 JSON + 原始分析文本） |
| trend_chats | 趋势报告追问聊天记录 |

---

## 🔌 API 端点

所有端点前缀 `/api`

### 论文

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/papers` | 论文列表（分页、筛选、排序、搜索） |
| GET | `/papers/{id}` | 论文详情（含相似论文 + 相似度分数） |
| GET | `/filter-statistics` | 筛选统计数据 |
| GET | `/stats` | 数据库统计摘要（论文数、期刊分布、年份分布、AI 使用量） |
| GET | `/authors/{name}/papers` | 作者论文列表 |
| GET | `/search/suggest` | 搜索自动补全建议 |
| GET | `/subfield-distribution` | 经济学子领域分布 |

### AI 分析（论文详情）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/papers/{id}/analyze` | 开始 AI 分析（防重复，状态追踪） |
| GET | `/papers/{id}/analyses` | 分析历史列表 |
| GET | `/papers/{id}/analyses/latest` | 最新分析结果（含 status） |
| POST | `/papers/{id}/chat` | 追问对话（SSE 流式输出） |
| GET | `/papers/{id}/chats` | 加载聊天历史 |
| POST | `/papers/{id}/chats` | 保存聊天记录 |

### 相似度

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/papers/{id}/recompute-similarities` | 重算单篇论文相似度 |
| POST | `/recompute-all-similarities` | 全量重算所有论文相似度 |

### 趋势 & 网络

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/trending-topics` | 趋势话题列表 |
| GET | `/network/authors` | 作者合作网络数据 |
| GET | `/network/keywords` | 关键词共现网络数据 |
| GET | `/ai-analysis` | AI 趋势分析（旧版兼容接口） |
| GET | `/ai-analysis/v2` | AI 趋势分析状态查询 |
| POST | `/ai-analysis/v2/analyze` | 发起后台异步趋势分析 |
| GET | `/ai-analysis/reports` | 历史分析报告列表 |
| GET | `/ai-analysis/reports/{id}` | 报告详情 |
| POST | `/ai-analysis/reports/{id}/chat` | 趋势报告追问对话（SSE 流式） |
| GET | `/ai-analysis/reports/{id}/chats` | 趋势报告聊天历史 |
| POST | `/ai-analysis/reports/{id}/chats` | 保存趋势报告聊天 |
| DELETE | `/ai-analysis/reports/{id}/chats` | 清空趋势报告聊天 |

### 爬虫

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/crawl/start` | 启动爬虫任务（支持指定期刊） |
| GET | `/crawl/status` | 爬虫运行日志 |

### 管理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/settings` | 获取系统设置（API Key 状态、模型、调度器） |
| PUT | `/settings` | 更新系统设置（API Key、模型优先级、端口、应用名） |
| POST | `/update-trend-scores` | 手动触发趋势分数更新 |
| GET | `/scheduler/jobs` | 调度器任务列表 |
| POST | `/scheduler/trigger/{job_id}` | 手动触发调度任务 |
| POST | `/scheduler/toggle` | 暂停/恢复调度器 |
| POST | `/maintenance/cleanup` | 数据库清理（无效论文、孤儿记录、僵尸报告） |

---

## 🖥️ 页面路由

| 路由 | 说明 |
|---|---|
| `/` | 首页 — 论文列表、多维筛选、搜索 |
| `/paper/[id]` | 论文详情 — 元数据、AI 分析、追问讨论、相似论文 |
| `/author/[name]` | 作者主页 — 论文列表、统计信息、合作者 |
| `/search` | 搜索页 — 全字段关键词搜索 + 自动补全 |
| `/trends` | 趋势分析 — 趋势话题 + AI 趋势报告 + 追问 |
| `/network` | 关系网络 — 关键词共现 + 作者合作 D3.js 可视化 |
| `/system` | 系统管理 — 爬虫日志、数据库统计、设置、维护 |

---

## 🚀 快速开始

### 环境要求
- Python 3.11+
- Node.js 18+
- 智谱 API Key 或 硅基流动 API Key（用于 AI 分析功能）

### 1. 安装依赖

```bash
# 后端
cd backend
pip install -r requirements.txt

# 前端
cd frontend
npm install
```

### 2. 配置环境变量

在 `backend/` 目录下创建 `.env` 文件：

```env
# AI 服务（至少配置一个）
ZHIPU_API_KEY=your_zhipu_api_key_here
SILICONFLOW_API_KEY=your_siliconflow_api_key_here

# 可选配置
OPENAI_API_KEY=your_openai_api_key_here
SCHEDULER_ENABLED=true
FETCH_INTERVAL_HOURS=24
API_TOKEN=your_api_token_here
```

完整配置参考 [.env.example](backend/.env.example)

### 3. 启动服务

```bash
./start.sh
```

### 4. 访问

| 服务 | 地址 |
|---|---|
| 前端 | http://localhost:3000 |
| 后端 API | http://localhost:8000 |
| API 文档 (Swagger) | http://localhost:8000/docs |

### 5. 停止服务

```bash
./stop.sh
```

---

## 🐳 Docker 部署

```bash
# 后端
cd backend
docker build -t paperpulse-backend .
docker run -d -p 8000:8000 --env-file .env paperpulse-backend

# 前端
cd frontend
docker build -t paperpulse-frontend .
docker run -d -p 3000:3000 paperpulse-frontend
```

---

## 🕷️ 爬虫架构

### CNKI 知网爬虫

基于 **DrissionPage** 的浏览器自动化爬虫，核心类：

- **DrissionPageBase**: 浏览器生命周期管理、随机 User-Agent、反自动化检测、验证码检测与处理
- **CNKIDrissionFetcher**: 单期刊爬虫（搜索→论文列表→详情页→数据提取）
- **CNKITop50BatchFetcher**: 50 个期刊的批量调度，按优先级排序执行

特性：
- 随机延迟模拟人工浏览，降低反爬风险
- 支持有头/无头模式切换
- 支持手动辅助完成验证码
- URL 去重 + 历史记录，支持断点续爬

### 自建站点爬虫

针对 6 个重点经济学期刊官网的专用爬虫，通过 `EconomicsJournalFetcher` 基类统一接口：

| 爬虫类 | 目标站点 |
|---|---|
| GuanliShijieFetcher | 管理世界 |
| JingjiYanjiuFetcher | 经济研究 |
| JingjixueJikanFetcher | 经济学（季刊） |
| ShijieJingjiFetcher | 世界经济 |
| ZhongguoGongyeJingjiFetcher | 中国工业经济 |
| AmericanEconomicReviewFetcher | AER |

### 调度策略

- **arXiv 论文**：每 24 小时自动抓取
- **经济学期刊**：每天凌晨 2:00 自动抓取
- **趋势分数**：每 6 小时自动更新
- **手动触发**：通过系统管理页面或 API 随时触发

---

## 📁 项目结构

```
paper_hot/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 应用入口 + 生命周期管理
│   │   ├── api.py               # 所有 API 端点（论文、AI、爬虫、趋势、网络、设置、维护）
│   │   ├── models.py            # SQLAlchemy ORM 模型（10 个表）
│   │   ├── schemas.py           # Pydantic 请求/响应模型
│   │   ├── crud.py              # 数据库操作层（7 个 CRUD 类）
│   │   ├── database.py          # 数据库连接与会话管理
│   │   ├── config.py            # 配置管理（pydantic-settings + 动态更新）
│   │   ├── scheduler.py         # APScheduler 定时任务调度
│   │   ├── scoring.py           # 论文评分系统
│   │   ├── similarity.py        # TF-IDF 相似度计算
│   │   ├── ai_processor.py      # AI 处理器（摘要、关键词提取、主题分类）
│   │   ├── ai_service.py        # AI 趋势分析服务（双通道 + 降级）
│   │   ├── fetchers.py          # 论文抓取基类 + 自建站点爬虫
│   │   ├── fetchers_cnki.py     # CNKI 知网爬虫（DrissionPage）
│   │   └── fetchers_cnki_navi.py # CNKI 期刊导航爬虫
│   ├── data/
│   │   ├── paperpulse.db              # SQLite 数据库
│   │   ├── papers_history.json        # 爬虫历史记录（URL → 去重）
│   │   ├── paper_details_history.json # 论文详情历史
│   │   └── journals_history.json      # 期刊历史
│   ├── .env.example
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── app/
│       │   ├── page.tsx                    # 首页（论文列表）
│       │   ├── layout.tsx                  # 根布局
│       │   ├── paper/[id]/page.tsx         # 论文详情页
│       │   ├── author/[name]/page.tsx      # 作者主页
│       │   ├── search/page.tsx             # 搜索页
│       │   ├── trends/page.tsx             # 趋势分析页
│       │   ├── network/
│       │   │   ├── page.tsx                # 关系网络页
│       │   │   └── NetworkGraph.tsx        # D3.js 网络图组件
│       │   └── system/page.tsx             # 系统管理页
│       ├── components/
│       │   ├── Filters.tsx                 # 筛选器组件
│       │   ├── PaperCard.tsx               # 论文卡片
│       │   ├── Pagination.tsx              # 分页组件
│       │   ├── SearchBar.tsx               # 搜索栏
│       │   ├── Layout.tsx                  # 布局组件
│       │   ├── TrendChart.tsx              # 趋势图表
│       │   ├── LanguageSwitcher.tsx        # 语言切换
│       │   └── SkeletonCard.tsx            # 骨架屏加载
│       ├── contexts/
│       │   ├── LanguageContext.tsx         # 国际化上下文
│       │   └── ThemeContext.tsx            # 暗黑模式上下文
│       ├── lib/
│       │   ├── api.ts                      # API 客户端
│       │   ├── cache.ts                    # localStorage 缓存 + 书签
│       │   ├── i18n.ts                     # 国际化翻译文件
│       │   └── utils.ts                    # 工具函数
│       ├── types/
│       │   └── paper.ts                    # TypeScript 类型定义
│       └── styles/
│           └── globals.css                 # 全局样式（含暗黑模式）
├── cnki_paper_captcha.py                   # CNKI 验证码识别模块
├── start.sh                                # 启动脚本
├── stop.sh                                 # 停止脚本
├── README.md                               # 英文文档
└── README_CN.md                            # 中文文档
```

---

## 📜 许可证

MIT License
