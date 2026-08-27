# PaperPulse

**极简的学术论文智能分析平台**

聚合 50+ 经济学权威期刊（知网 CNKI TOP50）、6 大经济学期刊站点与 arXiv 论文，提供 AI 论文分析、选题对话、相似度匹配、趋势分析与关键词/作者网络可视化。

> **轻量化设计**：服务器只装服务端依赖即可运行；爬虫依赖按需单独安装，**爬取数据无需在服务器上执行**。

---

## ✨ 核心功能

| 模块 | 说明 |
|---|---|
| 📚 **论文发现** | 多源聚合（CNKI TOP50 / 6 期刊站点 / arXiv）、多维度筛选（期刊/学科/子领域/关键词/时间/分数）、排序分页、搜索联想 |
| 📄 **论文详情** | 完整元数据、**AI 深度分析**（智谱 GLM / 硅基流动 Qwen）、SSE 流式追问对话、jieba+TF-IDF 相似论文 |
| 👤 **作者画像** | 作者论文列表、统计画像（首发年份/主期刊/关键词/子领域）、合著网络 |
| 📈 **趋势分析** | 热点关键词趋势、**AI 趋势报告**、趋势报告追问对话 |
| 🕸️ **网络可视化** | D3.js 关键词共现网络、作者合作网络 |
| 🎯 **选题智脑** | 研究空白识别、**选题验证**（本地 bge-m3 召回 → 硅基流动 bge-reranker 重排）、选题库、综述生成、期刊适配、引用导出 |
| 🕷️ **爬虫管理** | CNKI DrissionPage 批量抓取、6 期刊站点爬虫（含断点续传）、验证码自动解决 |
| ⚙️ **系统管理** | 数据统计、爬虫日志、手动触发、在线配置（API Key/模型优先级）、定时任务、数据维护 |

支持**中英双语界面**与**深色模式**。

---

## 🚀 快速开始（克隆即用）

### 环境要求
- **Python 3.11+**（服务端）
- **Node.js 18+**（前端构建）

### 方式一：轻量服务器部署（推荐，不需爬虫）

只需服务端依赖，一条命令装齐，**不需要安装任何爬虫库**：

```bash
# 0. 一键安装（venv + 服务端依赖；--with-ollama 可选装本地向量模型 bge-m3，国内加速）
./install.sh --with-ollama

# 或手动安装：
# 1. 克隆
git clone <repo-url> paper-hot && cd paper-hot

# 2. 建虚拟环境并安装服务端依赖（不含爬虫）
python3 -m venv venv
venv/bin/pip install -r requirements.txt

# 3. 配置 .env（提供 AI Key）
cp backend/.env.example backend/.env
# 编辑 backend/.env：填入 ZHIPU_API_KEY 或 SILICONFLOW_API_KEY

# 4. 启动
./start.sh
```

启动后：
| 服务 | 地址 |
|---|---|
| 前端 | http://localhost:3000 |
| 后端 API | http://localhost:8000 |
| API 文档 | http://localhost:8000/docs |

> 服务器默认不启用调度（`SCHEDULER_ENABLED=false`），只展示与分析已入库数据；需先导入数据（见下文"数据来源"）。停止用 `./start.sh stop`。

### 方式二：Docker 部署（含前后端）

```bash
docker compose up -d
```

> `docker-compose.yml` 已内置资源限制（后端 512M / 前端 256M），并默认 `SCHEDULER_ENABLED=false`，适合轻量云主机。

---

## 📦 依赖说明（关键）

项目**拆分为两种依赖**，互不影响，按需安装：

| 文件 | 用途 | 是否服务器必需 |
|---|---|---|
| `requirements.txt` | **服务端依赖**（FastAPI / SQLite / AI / 相似度） | ✅ 必需 |
| `backend/requirements.txt` | 同上（服务端独立版本，被根文件引用） | ✅ 必需 |
| `requirements-crawler.txt` | **爬虫扩展依赖**（arxiv / DrissionPage / bs4 / playwright / ddddocr） | ❌ 非必需 |
| `faiss-cpu`（可选） | 选题验证向量召回加速（FAISS 索引；未安装自动降级为 numpy 暴力余弦） | ❌ 可选 |

```bash
# 仅运行 Web 服务 + AI 分析（服务器推荐）
pip install -r requirements.txt

# 需要爬取数据时，再额外安装爬虫依赖
pip install -r requirements-crawler.txt
```

**架构上已解耦**：爬虫模块采用**惰性导入**。服务器即便只装了服务端依赖，`import app.main` 也不会因缺爬虫库而失败；只有真正触发爬虫/调度任务时才加载爬虫库。

---

## 🕷️ 数据来源（爬虫，可选）

爬取功能默认不在服务器上运行，可在本机或单独机器执行：

| 数据源 | 说明 | 依赖 |
|---|---|---|
| **CNKI TOP50** | DrissionPage 批量抓取经济学 TOP50 期刊 | `requirements-crawler.txt` + `playwright install chromium` |
| **6 大经济学期刊** | 管理世界 / 经济研究 / 经济学季刊 / 世界经济 / 中国工业经济 / AER | `requirements-crawler.txt` |
| **arXiv** | AI 论文自动抓取 | `requirements-crawler.txt` |

爬取论文会写入同一数据库（`backend/data/paperpulse.db`），随后即可在 Web 端展示分析。

### 直接获取论文数据库快照（推荐）

数据库以压缩快照发布在 GitHub Release，克隆仓库后无需自己爬取：

```bash
./download-db.sh                    # 下载默认快照并解压到 backend/data/paperpulse.db
./download-db.sh <tag>              # 指定标签（如 data-20260827）
./download-db.sh <tag> <sha256>     # 指定校验和验证
```

> 数据库不再纳入 git/LFS 跟踪（174MB 太大且消耗 LFS 配额），更新快照时我们会发布新的 Release 标签。

---

## 🤖 配置

在 `backend/.env` 中配置（完整项见 `backend/.env.example`）：

```env
# AI 服务（至少填一个）
ZHIPU_API_KEY=your_key
SILICONFLOW_API_KEY=your_key
# 可选
OPENAI_API_KEY=your_key
SCHEDULER_ENABLED=false       # 服务器不建议开启爬虫调度
API_TOKEN=optional_restriction
```

> 模型调用统一走 OpenAI 兼容格式，可在系统管理页面配置默认模型 / 模型优先级，并支持"链接测试"。

### 本地 Embedding 模型（Ollama + bge-m3，可选）

Run paper embeddings fully offline with Ollama (CPU is enough, no API cost):

```bash
# 1. Install Ollama (full runtime) and start it
curl -fsSL https://ollama.com/install.sh | sh && systemctl start ollama

# 2. Pull bge-m3 via ModelScope mirror (fastest in CN, ~1MB/s; official registry ~0.34MB/s)
ollama pull modelscope.cn/gpustack/bge-m3-GGUF
ollama cp modelscope.cn/gpustack/bge-m3-GGUF bge-m3
```

Configure `backend/.env`:

```env
CUSTOM_PROVIDERS=[{"name":"ollama","base_url":"http://localhost:11434/v1","api_key":"ollama","models":["bge-m3"]}]
EMBEDDING_MODEL=ollama/bge-m3
```

**Important**: embeddings from different models are incompatible. After switching models, back up the DB, clear `paper_features.embedding`, restart, then trigger a full rebuild:

```bash
curl -X POST "http://localhost:8000/api/topic-validator/embeddings/backfill"
```

See [README_CN.md](README_CN.md) for the detailed guide (speed benchmarks, FP16 import fallback, troubleshooting).

### 两阶段检索：重排（可选，强烈建议）

选题验证使用**两阶段检索**：本地 bge-m3 召回 Top100 → 硅基流动 bge-reranker-v2-m3 重排 → Top30 喂给 LLM（召回速度较全量余弦快约 2 倍，重排把相似度区分度从 0.77 拉开到 0.98）。

```env
# 在 backend/.env 中配置（key 在 https://siliconflow.cn 免费获取）
RERANK_API_KEY=sk-...
RERANK_MODEL=siliconflow/BAAI/bge-reranker-v2-m3
RERANK_BASE_URL=https://api.siliconflow.cn/v1
```

未配置 `RERANK_API_KEY` 时自动跳过重排（降级为 embedding 顺序）；`faiss-cpu` 未安装时召回自动降级为 numpy 暴力余弦。两项均为可选增强，不影响基本功能。

---

## 🛠️ 技术栈

- **后端**：FastAPI · SQLAlchemy (asyncio) · SQLite/aiosqlite · apscheduler
- **AI**：OpenAI 兼容接口（智谱 GLM / 硅基流动 Qwen / OpenAI）· SSE 流式
- **相似度/检索**：jieba 分词 + TF-IDF + 余弦相似度（scikit-learn）· FAISS 召回（可选加速）· bge-reranker 重排（硅基流动 API）
- **爬虫**：DrissionPage · BeautifulSoup · playwright · ddddocr（验证码）
- **前端**：Next.js · React · TypeScript · D3.js · Tailwind

---

## 📁 项目结构

```
├── backend/                  # FastAPI 后端
│   ├── app/
│   │   ├── main.py           # 应用入口
│   │   ├── api.py            # 路由注册
│   │   ├── scheduler.py      # 定时任务（爬虫惰性加载）
│   │   ├── config.py         # 配置（.env）
│   │   ├── database.py       # 数据库连接
│   │   ├── models.py         # ORM 模型
│   │   ├── schemas.py        # Pydantic 校验
│   │   ├── fetchers*.py      # 爬虫抓取（依赖爬虫扩展包）
│   │   ├── ai_service.py     # AI 分析与对话
│   │   ├── vector_index.py   # FAISS 向量索引（召回加速，可选）
│   │   └── routers/          # 各业务路由
│   └── requirements.txt      # 服务端依赖
├── frontend/                 # Next.js 前端
├── requirements.txt          # 服务端依赖（入口）
├── requirements-crawler.txt  # 爬虫扩展依赖（可选）
├── cnki_paper_captcha.py     # 知网关键词检索脚本（爬虫）
├── docker-compose.yml        # 容器编排（预构建镜像）
└── start.sh / install.sh    # 启停控制 / 一键安装
    download-db.sh            # 从 GitHub Release 下载论文数据库快照
```

---

## 📑 License

项目为个人研究工具，不做商业用途。