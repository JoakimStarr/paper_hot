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

> 服务器默认不启用调度（`SCHEDULER_ENABLED=false`），只展示与分析已入库数据；需先导入数据（见下文"数据来源"）。停止用 `./stop.sh`。

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

---

## 🛠️ 技术栈

- **后端**：FastAPI · SQLAlchemy (asyncio) · SQLite/aiosqlite · apscheduler
- **AI**：OpenAI 兼容接口（智谱 GLM / 硅基流动 Qwen / OpenAI）· SSE 流式
- **相似度**：jieba 分词 + TF-IDF + 余弦相似度（scikit-learn）
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
│   │   └── routers/          # 各业务路由
│   └── requirements.txt      # 服务端依赖
├── frontend/                 # Next.js 前端
├── requirements.txt          # 服务端依赖（入口）
├── requirements-crawler.txt  # 爬虫扩展依赖（可选）
├── cnki_paper_captcha.py     # 知网关键词检索脚本（爬虫）
├── docker-compose.yml        # 容器编排（预构建镜像）
└── start.sh / stop.sh        # 快捷启动/停止
```

---

## 📑 License

项目为个人研究工具，不做商业用途。