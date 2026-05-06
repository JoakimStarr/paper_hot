# PaperPulse

A production-ready web application for discovering and understanding trending AI research papers. PaperPulse combines fast sources (arXiv) with high-quality venues (top conferences/journals) to help researchers stay updated with the latest developments in AI.

## Features

- **Paper Discovery**: Browse AI research papers from arXiv and top venues
- **Smart Scoring**: Papers ranked by recency, venue quality, and trend analysis
- **AI-Powered Summaries**: Auto-generated plain English summaries
- **Topic Classification**: Automatic categorization (LLM, Agent, CV, RL, etc.)
- **Trend Analysis**: Track which topics are gaining momentum
- **Similar Papers**: Find related research using embeddings
- **"Should I Read This?" Score**: AI-generated recommendation score

## Architecture

### Backend (FastAPI)
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Data Fetching**: Scheduled jobs to fetch papers from arXiv
- **AI Processing**: OpenAI API for summaries, keywords, and embeddings
- **Scoring System**: Multi-factor ranking algorithm
- **Trend Analysis**: Clustering and growth rate computation

### Frontend (Next.js)
- **UI**: Clean, responsive dashboard
- **Pages**: Home, Trends, Paper Detail
- **Components**: Paper cards, filters, trend charts
- **Real-time Updates**: Live data fetching

## Tech Stack

### Backend
- Python 3.11+
- FastAPI
- PostgreSQL
- SQLAlchemy
- OpenAI API
- arxiv library
- scikit-learn

### Frontend
- Next.js 14
- React 18
- TypeScript
- Tailwind CSS
- Recharts
- Axios

## Setup Instructions

### Prerequisites
- Python 3.11 or higher
- Node.js 18 or higher
- PostgreSQL 14 or higher
- OpenAI API key (optional, but recommended)

### 1. Database Setup

```bash
# Create PostgreSQL database
createdb paperpulse

# Or using psql
psql -U postgres
CREATE DATABASE paperpulse;
\q

# Run the schema initialization
psql -U postgres -d paperpulse -f database/init.sql
```

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env

# Edit .env with your settings
# DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/paperpulse
# OPENAI_API_KEY=your_openai_api_key_here

# Run the backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Create .env.local file
echo "NEXT_PUBLIC_API_URL=http://localhost:8000/api" > .env.local

# Run the development server
npm run dev
```

### 4. Access the Application

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Documentation: http://localhost:8000/docs

## API Endpoints

### Papers

- `GET /api/papers` - List papers with filters and pagination
  - Query params: `page`, `page_size`, `topic`, `source`, `min_score`, `days_back`
  
- `GET /api/papers/{id}` - Get paper details with similar papers

### Trends

- `GET /api/trending-topics` - Get trending topics with growth rates
  - Query params: `weeks_back`

## Example API Responses

### GET /api/papers

```json
{
  "papers": [
    {
      "id": "uuid",
      "title": "Attention Is All You Need",
      "abstract": "The dominant sequence transduction models...",
      "authors": ["Ashish Vaswani", "Noam Shazeer"],
      "url": "https://arxiv.org/abs/1706.03762",
      "source": "arxiv",
      "venue": "NeurIPS",
      "published_at": "2017-06-12T00:00:00",
      "created_at": "2024-01-15T10:30:00",
      "features": {
        "summary": "This paper introduces the Transformer architecture...",
        "keywords": ["transformer", "attention", "neural network"],
        "topic": "LLM"
      },
      "scores": {
        "recency_score": 0.45,
        "venue_score": 1.0,
        "trend_score": 0.85,
        "final_score": 0.72
      }
    }
  ],
  "total": 150,
  "page": 1,
  "page_size": 20,
  "has_next": true
}
```

### GET /api/trending-topics

```json
{
  "topics": [
    {
      "topic": "LLM",
      "paper_count": 45,
      "growth_rate": 0.35,
      "trend": "rising"
    },
    {
      "topic": "Agent",
      "paper_count": 28,
      "growth_rate": 0.22,
      "trend": "rising"
    }
  ],
  "week_start": "2024-01-08T00:00:00",
  "week_end": "2024-01-15T00:00:00"
}
```

## Scoring System

Papers are scored using a multi-factor algorithm:

```
final_score = 0.5 * recency_score + 0.3 * venue_score + 0.2 * trend_score
```

### Recency Score
- Exponential decay based on publication date
- Recent papers score higher

### Venue Score
- NeurIPS, ICML, ICLR: 1.0
- CVPR, ACL: 0.9
- Nature, Science: 1.0
- JMLR: 0.95
- arXiv: 0.6

### Trend Score
- Based on keyword frequency growth
- Papers with trending keywords score higher

## Configuration

### Backend Environment Variables

- `DATABASE_URL`: PostgreSQL connection string
- `OPENAI_API_KEY`: OpenAI API key for AI features
- `SCHEDULER_ENABLED`: Enable/disable automatic paper fetching (default: true)
- `FETCH_INTERVAL_HOURS`: How often to fetch new papers (default: 24)
- `CORS_ORIGINS`: Allowed CORS origins for frontend

### Frontend Environment Variables

- `NEXT_PUBLIC_API_URL`: Backend API URL

## Development

### Running Tests

```bash
# Backend
cd backend
pytest

# Frontend
cd frontend
npm test
```

### Building for Production

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend
cd frontend
npm run build
npm start
```

## Future Enhancements

- [ ] User authentication and saved papers
- [ ] Personalized recommendations
- [ ] Email weekly digest
- [ ] Citation network analysis
- [ ] Paper reading lists
- [ ] Export to BibTeX
- [ ] Mobile app

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
