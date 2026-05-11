# PaperPulse

<p align="center">
  <strong>Chinese Economics Paper Discovery & Analysis Platform</strong>
</p>

<p align="center">
  Tracks 50+ top-tier economics journals and arXiv AI papers, providing AI-powered analysis, chat discussions, similarity matching, trend analysis, and network visualization.
</p>

---

## ✨ Features

### 📚 Paper Discovery
- **Multi-source Aggregation**: Covers CNKI Economics TOP50 journals, 6 site-specific crawlers (管理世界, 经济研究, 经济学季刊, 世界经济, 中国工业经济, American Economic Review), and arXiv AI papers
- **Smart Multi-dimensional Filters**: Filter by journal, discipline, economics subfield, CNKI subject, keyword search, score range, time range; Enter key search support
- **Sorting & Pagination**: Sort by publish time + issue number, or composite score; pre-fetch first 3 pages with localStorage caching for instant loading
- **Dedicated Search Page**: Standalone search page with full-field keyword search + auto-complete suggestions (keywords/authors/titles)
- **Skeleton Loading**: Skeleton card animations during data loading for better UX

### 📄 Paper Detail
- **Complete Metadata**: Title, authors, abstract, keywords, journal name + issue, DOI (clickable to original), publication date
- **AI Analysis**: In-depth single-paper analysis powered by Zhipu GLM / SiliconFlow Qwen, covering research background, methodological innovation, key findings, and research significance
- **Status Tracking**: Persistent analysis status (pending → success/failed), survives page refresh
- **Follow-up Chat**: SSE streaming Q&A conversation, Markdown rendering, automatic chat history persistence
- **Similar Papers**: jieba tokenization + TF-IDF cosine similarity, real-time TOP 5 related papers with similarity scores

### 👤 Author Profile
- **Author Paper List**: Aggregated papers by author with pagination
- **Author Statistics**: Total papers, first-author count, most recent year, primary journal, top keywords, main subfield
- **Co-author Network**: Display co-authors and collaboration frequency

### 📈 Trend Analysis
- **Trending Topics**: Dynamic topic trends based on keyword frequency growth rates, with rising/stable/declining status markers
- **AI Trend Reports**: Async background AI analysis generating structured trend reports (hot topics, development trends, keyword insights, journal insights, research recommendations), with polling status support
- **Trend Report Chat**: Follow-up Q&A on AI trend reports for deeper insights into research hotspots and topic opportunities

### 🕸️ Network Visualization
- **Keyword Co-occurrence Network**: D3.js interactive force-directed graph visualizing keyword co-occurrence relationships, with zoom and drag support
- **Author Collaboration Network**: D3.js interactive author collaboration graph showing academic collaboration ecosystems

### 🕷️ Crawler Management
- **Multi-threaded CNKI Crawler**: DrissionPage-based crawler for automated batch scraping of Economics TOP50 journals
- **Site-specific Crawlers**: 6 dedicated crawlers for key economics journals with resume support
- **Captcha Handling**: Auto-detection + manual-assisted captcha resolution
- **Crawl History**: URL deduplication, incremental crawling, persistent crawl logs

### ⚙️ System Management
- **Database Statistics**: System overview including total papers, journal distribution, year distribution, source statistics, AI usage metrics
- **Crawl Logs**: Real-time crawl status and historical logs
- **Manual Triggers**: Manual crawl task initiation, trend score updates, full similarity recomputation
- **Online Settings**: Dynamic configuration of API keys, model priority, ports, application name
- **Scheduler Management**: Pause/resume scheduled tasks, manual trigger of scheduler jobs
- **Database Maintenance**: Cleanup of invalid data and zombie analysis reports

### 🌐 i18n & Theme
- **Bilingual Interface**: Full Chinese/English interface switching
- **Dark Mode**: Light/dark theme toggle with system preference detection

---

## 📊 Data Sources

| Source | Count | Description |
|---|---|---|
| CNKI | 50 | Economics TOP50 journals, crawled by priority tiers |
| Site-specific Crawlers | 6 | 管理世界, 经济研究, 经济学季刊, 世界经济, 中国工业经济, AER |
| arXiv | 4 categories | cs.AI, cs.CL, cs.LG, cs.CV |

### CNKI Economics TOP50 Journals

**Tier 1 Journals**: 经济研究, 管理世界, 经济学（季刊）, 世界经济, 中国工业经济, 中国社会科学, 金融研究, 数量经济技术经济研究

**Tier 2 Journals**: 财贸经济, 中国农村经济, 经济学动态, 国际经济评论, 改革, 中国人口科学, 农业经济问题, 中国农村观察, 财政研究, 税务研究, 会计研究, 审计研究

**International Trade & World Economy**: 国际贸易问题, 国际经贸探索, 世界经济研究, 经济社会体制比较

**Comprehensive Economics Journals**: 经济学家, 经济科学, 经济理论与经济管理, 南开经济研究, 当代经济科学, 当代经济研究, and more

> See [fetchers_cnki.py](backend/app/fetchers_cnki.py) for the complete list of 50 journals

---

## 🛠️ Tech Stack

### Backend

| Category | Technology |
|---|---|
| Framework | FastAPI + Uvicorn |
| Database | SQLite + aiosqlite + SQLAlchemy ORM (PostgreSQL compatible) |
| AI Service | zai-sdk (Zhipu GLM-4.7 / GLM-4.5-Air / GLM-4.7-Flash) + OpenAI SDK (SiliconFlow Qwen3.5-4B / Qwen3-8B / DeepSeek-R1) |
| Similarity | jieba tokenization + scikit-learn TF-IDF + cosine similarity |
| Scheduling | APScheduler (scheduled crawling, trend updates) |
| Crawling | DrissionPage (CNKI), BeautifulSoup4 + lxml (site-specific) |
| Streaming | SSE (Server-Sent Events) |
| Containerization | Docker + Dockerfile |

### Frontend

| Category | Technology |
|---|---|
| Framework | Next.js 14 + React 18 + TypeScript |
| Styling | Tailwind CSS + @tailwindcss/typography + Dark Mode |
| Charts | Recharts (trends) + D3.js (networks) |
| Markdown | react-markdown + remark-gfm |
| HTTP | axios |
| Icons | lucide-react |
| Dates | date-fns |
| i18n | Custom LanguageContext + i18n |
| Caching | localStorage page prefetch cache |
| Containerization | Docker + Dockerfile |

---

## 📐 Scoring System

Paper composite scores are computed from three weighted dimensions:

| Dimension | Weight | Method |
|---|---|---|
| Recency | 50% | Exponential decay function `e^(-0.1 × days)` — newer papers score higher |
| Venue Authority | 30% | Journal tier-based authority score |
| Trend Heat | 20% | Topic growth rate with Sigmoid(tanh) smoothing |

---

## 🔗 Similarity Algorithm

Using **jieba Chinese tokenization** + **TF-IDF vectorization** + **cosine similarity**:

1. Tokenize all paper abstracts with jieba
2. Build TF-IDF matrix with TfidfVectorizer (max_features=10,000)
3. Compute pairwise cosine similarity
4. Filter pairs with score > 0.05 and persist to `paper_similarities` table
5. Query TOP 5 from table at millisecond-level response

Supports single-paper recompute or full recompute after new papers are added.

---

## 🤖 AI Dual-Channel Architecture

The system supports both Zhipu AI and SiliconFlow channels with automatic failover:

| Channel | Models | Usage |
|---|---|---|
| Zhipu GLM | glm-4.7 → glm-4.5-air → glm-4.7-flash | Trend analysis, paper analysis, chat |
| SiliconFlow | Qwen3.5-4B → Qwen3-8B → DeepSeek-R1 | Fallback channel |

Features:
- Up to 2 retries per model
- GLM channel has priority; automatic fallback to SiliconFlow on failure
- Online dynamic model priority configuration
- Structured JSON output (trend analysis)

---

## 🗄️ Database Schema

| Table | Description |
|---|---|
| papers | Main paper table (title, authors, abstract, DOI, keywords, journal issue, etc.) |
| paper_features | Paper features (AI summary, keyword extraction, topic classification) |
| paper_scores | Scores (recency, venue, trend, composite) |
| paper_analyses | Single-paper AI analysis history (with status tracking) |
| paper_chats | Follow-up chat records (stored by user/assistant role) |
| paper_similarities | Pre-computed TF-IDF cosine similarities (persisted) |
| topic_trends | Topic trend data (topic, week, growth rate) |
| crawl_logs | Crawler execution logs |
| ai_analysis_reports | Trend analysis reports (structured JSON + raw analysis text) |
| trend_chats | Trend report follow-up chat records |

---

## 🔌 API Endpoints

All endpoints prefixed with `/api`

### Papers

| Method | Path | Description |
|---|---|---|
| GET | `/papers` | Paper list (pagination, filtering, sorting, search) |
| GET | `/papers/{id}` | Paper detail (with similar papers + similarity scores) |
| GET | `/filter-statistics` | Filter statistics |
| GET | `/stats` | Database statistics summary (counts, journal distribution, year distribution, AI usage) |
| GET | `/authors/{name}/papers` | Author paper list |
| GET | `/search/suggest` | Search auto-complete suggestions |
| GET | `/subfield-distribution` | Economics subfield distribution |

### AI Analysis (Paper Detail)

| Method | Path | Description |
|---|---|---|
| POST | `/papers/{id}/analyze` | Start AI analysis (deduplicated, status tracked) |
| GET | `/papers/{id}/analyses` | Analysis history list |
| GET | `/papers/{id}/analyses/latest` | Latest analysis result (with status) |
| POST | `/papers/{id}/chat` | Follow-up chat (SSE streaming) |
| GET | `/papers/{id}/chats` | Load chat history |
| POST | `/papers/{id}/chats` | Save chat messages |

### Similarity

| Method | Path | Description |
|---|---|---|
| POST | `/papers/{id}/recompute-similarities` | Recompute similarities for a single paper |
| POST | `/recompute-all-similarities` | Full recompute of all paper similarities |

### Trends & Network

| Method | Path | Description |
|---|---|---|
| GET | `/trending-topics` | Trending topics list |
| GET | `/network/authors` | Author collaboration network data |
| GET | `/network/keywords` | Keyword co-occurrence network data |
| GET | `/ai-analysis` | AI trend analysis (legacy compatibility endpoint) |
| GET | `/ai-analysis/v2` | AI trend analysis status query |
| POST | `/ai-analysis/v2/analyze` | Trigger async background trend analysis |
| GET | `/ai-analysis/reports` | Historical analysis report list |
| GET | `/ai-analysis/reports/{id}` | Report detail |
| POST | `/ai-analysis/reports/{id}/chat` | Trend report follow-up chat (SSE streaming) |
| GET | `/ai-analysis/reports/{id}/chats` | Trend report chat history |
| POST | `/ai-analysis/reports/{id}/chats` | Save trend report chat messages |
| DELETE | `/ai-analysis/reports/{id}/chats` | Clear trend report chat history |

### Crawler

| Method | Path | Description |
|---|---|---|
| POST | `/crawl/start` | Start crawl task (supports specifying journals) |
| GET | `/crawl/status` | Crawl execution logs |

### Management

| Method | Path | Description |
|---|---|---|
| GET | `/settings` | Get system settings (API key status, models, scheduler) |
| PUT | `/settings` | Update system settings (API keys, model priority, ports, app name) |
| POST | `/update-trend-scores` | Manually trigger trend score update |
| GET | `/scheduler/jobs` | Scheduler job list |
| POST | `/scheduler/trigger/{job_id}` | Manually trigger a scheduler job |
| POST | `/scheduler/toggle` | Pause/resume scheduler |
| POST | `/maintenance/cleanup` | Database cleanup (invalid papers, orphan records, zombie reports) |

---

## 🖥️ Frontend Routes

| Route | Description |
|---|---|
| `/` | Home — paper list, multi-dimensional filters, search |
| `/paper/[id]` | Paper Detail — metadata, AI analysis, follow-up chat, similar papers |
| `/author/[name]` | Author Profile — paper list, statistics, co-authors |
| `/search` | Search — full-field keyword search + auto-complete |
| `/trends` | Trends — trending topics + AI trend report + chat |
| `/network` | Network — keyword co-occurrence + author collaboration D3.js visualization |
| `/system` | System — crawl logs, database stats, settings, maintenance |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+
- Zhipu API Key or SiliconFlow API Key (for AI analysis features)

### 1. Install Dependencies

```bash
# Backend
cd backend
pip install -r requirements.txt

# Frontend
cd frontend
npm install
```

### 2. Configuration

Create a `.env` file in the `backend/` directory:

```env
# AI Service (at least one required)
ZHIPU_API_KEY=your_zhipu_api_key_here
SILICONFLOW_API_KEY=your_siliconflow_api_key_here

# Optional
OPENAI_API_KEY=your_openai_api_key_here
SCHEDULER_ENABLED=true
FETCH_INTERVAL_HOURS=24
API_TOKEN=your_api_token_here
```

See [.env.example](backend/.env.example) for full configuration options.

### 3. Launch

```bash
./start.sh
```

### 4. Access

| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| Backend API | http://localhost:8000 |
| API Docs (Swagger) | http://localhost:8000/docs |

### 5. Stop

```bash
./stop.sh
```

---

## 🐳 Docker Deployment

```bash
# Backend
cd backend
docker build -t paperpulse-backend .
docker run -d -p 8000:8000 --env-file .env paperpulse-backend

# Frontend
cd frontend
docker build -t paperpulse-frontend .
docker run -d -p 3000:3000 paperpulse-frontend
```

---

## 🕷️ Crawler Architecture

### CNKI Crawler

DrissionPage-based browser automation crawler with the following core classes:

- **DrissionPageBase**: Browser lifecycle management, random User-Agent rotation, anti-automation detection, captcha detection & handling
- **CNKIDrissionFetcher**: Single journal crawler (search → paper list → detail page → data extraction)
- **CNKITop50BatchFetcher**: Batch scheduler for 50 journals, executed by priority order

Features:
- Random delays to simulate human browsing and reduce anti-crawling risk
- Headless/headed mode switching
- Manual-assisted captcha resolution
- URL deduplication + history records with incremental crawling support

### Site-specific Crawlers

Dedicated crawlers for 6 key economics journal websites, unified via `EconomicsJournalFetcher` base class:

| Crawler Class | Target Site |
|---|---|
| GuanliShijieFetcher | 管理世界 (Management World) |
| JingjiYanjiuFetcher | 经济研究 (Economic Research Journal) |
| JingjixueJikanFetcher | 经济学（季刊）(China Economic Quarterly) |
| ShijieJingjiFetcher | 世界经济 (The Journal of World Economy) |
| ZhongguoGongyeJingjiFetcher | 中国工业经济 (China Industrial Economics) |
| AmericanEconomicReviewFetcher | AER |

### Scheduling Strategy

- **arXiv papers**: Automatic fetch every 24 hours
- **Economics journals**: Automatic fetch daily at 2:00 AM
- **Trend scores**: Automatic update every 6 hours
- **Manual triggers**: Available anytime via System page or API

---

## 📁 Project Structure

```
paper_hot/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app entry + lifecycle management
│   │   ├── api.py               # All API endpoints (papers, AI, crawling, trends, network, settings, maintenance)
│   │   ├── models.py            # SQLAlchemy ORM models (10 tables)
│   │   ├── schemas.py           # Pydantic request/response models
│   │   ├── crud.py              # Database operations layer (7 CRUD classes)
│   │   ├── database.py          # Database connection & session management
│   │   ├── config.py            # Configuration management (pydantic-settings + dynamic update)
│   │   ├── scheduler.py         # APScheduler job scheduling
│   │   ├── scoring.py           # Paper scoring system
│   │   ├── similarity.py        # TF-IDF similarity computation
│   │   ├── ai_processor.py      # AI processor (summarization, keyword extraction, topic classification)
│   │   ├── ai_service.py        # AI trend analysis service (dual-channel + failover)
│   │   ├── fetchers.py          # Paper fetching base + site-specific crawlers
│   │   ├── fetchers_cnki.py     # CNKI crawler (DrissionPage)
│   │   └── fetchers_cnki_navi.py # CNKI journal navigation crawler
│   ├── data/
│   │   ├── paperpulse.db              # SQLite database
│   │   ├── papers_history.json        # Crawler history (URL → deduplication)
│   │   ├── paper_details_history.json # Paper detail history
│   │   └── journals_history.json      # Journal history
│   ├── .env.example
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── app/
│       │   ├── page.tsx                    # Home page (paper list)
│       │   ├── layout.tsx                  # Root layout
│       │   ├── paper/[id]/page.tsx         # Paper detail page
│       │   ├── author/[name]/page.tsx      # Author profile page
│       │   ├── search/page.tsx             # Search page
│       │   ├── trends/page.tsx             # Trend analysis page
│       │   ├── network/
│       │   │   ├── page.tsx                # Network visualization page
│       │   │   └── NetworkGraph.tsx        # D3.js network graph component
│       │   └── system/page.tsx             # System management page
│       ├── components/
│       │   ├── Filters.tsx                 # Filter component
│       │   ├── PaperCard.tsx               # Paper card component
│       │   ├── Pagination.tsx              # Pagination component
│       │   ├── SearchBar.tsx               # Search bar component
│       │   ├── Layout.tsx                  # Layout component
│       │   ├── TrendChart.tsx              # Trend chart component
│       │   ├── LanguageSwitcher.tsx        # Language switcher
│       │   └── SkeletonCard.tsx            # Skeleton loading card
│       ├── contexts/
│       │   ├── LanguageContext.tsx         # i18n context
│       │   └── ThemeContext.tsx            # Dark mode context
│       ├── lib/
│       │   ├── api.ts                      # API client
│       │   ├── cache.ts                    # localStorage cache + bookmarks
│       │   ├── i18n.ts                     # i18n translations
│       │   └── utils.ts                    # Utility functions
│       ├── types/
│       │   └── paper.ts                    # TypeScript type definitions
│       └── styles/
│           └── globals.css                 # Global styles (with dark mode)
├── cnki_paper_captcha.py                   # CNKI captcha recognition module
├── start.sh                                # Startup script
├── stop.sh                                 # Shutdown script
├── README.md                               # English documentation
└── README_CN.md                            # Chinese documentation
```

---

## 📜 License

MIT License
