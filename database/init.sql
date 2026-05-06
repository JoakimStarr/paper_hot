-- PaperPulse Database Schema

-- Create papers table
CREATE TABLE IF NOT EXISTS papers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title VARCHAR(500) NOT NULL,
    abstract TEXT NOT NULL,
    authors JSONB DEFAULT '[]'::jsonb,
    url VARCHAR(500) NOT NULL UNIQUE,
    source VARCHAR(50) NOT NULL,
    venue VARCHAR(100),
    published_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

-- Create indexes for papers
CREATE INDEX idx_papers_title ON papers(title);
CREATE INDEX idx_papers_source ON papers(source);
CREATE INDEX idx_papers_published_at ON papers(published_at);
CREATE INDEX idx_papers_created_at ON papers(created_at);

-- Create paper_features table
CREATE TABLE IF NOT EXISTS paper_features (
    id SERIAL PRIMARY KEY,
    paper_id UUID NOT NULL UNIQUE REFERENCES papers(id) ON DELETE CASCADE,
    summary TEXT,
    keywords JSONB DEFAULT '[]'::jsonb,
    embedding TEXT,
    topic VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for paper_features
CREATE INDEX idx_paper_features_topic ON paper_features(topic);
CREATE INDEX idx_paper_features_paper_id ON paper_features(paper_id);

-- Create paper_scores table
CREATE TABLE IF NOT EXISTS paper_scores (
    id SERIAL PRIMARY KEY,
    paper_id UUID NOT NULL UNIQUE REFERENCES papers(id) ON DELETE CASCADE,
    recency_score FLOAT DEFAULT 0.0,
    venue_score FLOAT DEFAULT 0.0,
    trend_score FLOAT DEFAULT 0.0,
    final_score FLOAT DEFAULT 0.0,
    computed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for paper_scores
CREATE INDEX idx_paper_scores_final_score ON paper_scores(final_score);
CREATE INDEX idx_paper_scores_paper_id ON paper_scores(paper_id);

-- Create topic_trends table
CREATE TABLE IF NOT EXISTS topic_trends (
    id SERIAL PRIMARY KEY,
    topic VARCHAR(50) NOT NULL,
    week_start TIMESTAMP WITH TIME ZONE NOT NULL,
    paper_count INTEGER DEFAULT 0,
    growth_rate FLOAT DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for topic_trends
CREATE INDEX idx_topic_trends_topic ON topic_trends(topic);
CREATE INDEX idx_topic_trends_week_start ON topic_trends(week_start);

-- Create composite indexes for common queries
CREATE INDEX idx_papers_source_published ON papers(source, published_at DESC);
CREATE INDEX idx_paper_features_topic_created ON paper_features(topic, created_at DESC);
