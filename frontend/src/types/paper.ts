export interface Author {
  name: string;
}

export interface PaperFeatures {
  summary: string | null;
  keywords: string[];
  topic: string | null;
}

export interface PaperScore {
  recency_score: number;
  venue_score: number;
  trend_score: number;
  final_score: number;
}

export interface Paper {
  id: string;
  title: string;
  abstract: string;
  authors: string[];
  url: string;
  source: string;
  venue: string | null;
  published_at: string | null;
  created_at: string;
  features: PaperFeatures | null;
  scores: PaperScore | null;
  discipline: string | null;
  journal_name: string | null;
  journal_issue: string | null;
  economics_subfield: string | null;
}

export interface PaperListResponse {
  papers: Paper[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

export interface TrendingTopic {
  topic: string;
  paper_count: number;
  growth_rate: number;
  trend: 'rising' | 'stable' | 'declining';
}

export interface TrendingTopicsResponse {
  topics: TrendingTopic[];
  week_start: string;
  week_end: string;
}

export interface SimilarPaper {
  id: string;
  title: string;
  similarity_score: number;
  topic: string | null;
}

export interface PaperDetailResponse extends Paper {
  similar_papers: SimilarPaper[];
  should_read_score: number | null;
}

export interface AIAnalysisResponse {
  analysis: string;
  model: string | null;
  timestamp: string | null;
  status: string;
}

export interface StructuredAnalysisItem {
  topic?: string;
  description?: string;
  related_keywords?: string[];
  significance?: string;
  trend?: string;
  direction?: string;
  evidence?: string;
  cluster?: string;
  keywords?: string[];
  insight?: string;
  journal?: string;
  focus?: string;
  suggestion?: string;
  area?: string;
  opportunity_level?: string;
}

export interface AIAnalysisReport {
  id: number;
  summary: string | null;
  hot_topics: StructuredAnalysisItem[] | null;
  development_trends: StructuredAnalysisItem[] | null;
  keyword_insights: StructuredAnalysisItem[] | null;
  journal_insights: StructuredAnalysisItem[] | null;
  recommendations: StructuredAnalysisItem[] | null;
  raw_analysis: string | null;
  model: string | null;
  total_papers: number;
  tokens_used: number;
  processing_time_ms: number;
  status: string;
  created_at: string;
}

export interface AIAnalysisResponseV2 {
  report: AIAnalysisReport | null;
  cached: boolean;
  has_history: boolean;
  is_running: boolean;
  running_report_id: number | null;
}
