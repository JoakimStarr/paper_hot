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
  cnki_subject: string | null;
  doi: string | null;
  keywords_cn: string[];
}

export interface PaperListResponse {
  papers: Paper[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}

export interface PaperCard {
  id: string;
  title: string;
  abstract: string | null;
  authors: string[];
  url: string;
  source: string;
  venue: string | null;
  journal_name: string | null;
  journal_issue: string | null;
  economics_subfield: string | null;
  cnki_subject: string | null;
  doi: string | null;
  keywords_cn: string[];
  published_at: string | null;
  topic: string | null;
  recency_score: number;
  venue_score: number;
  trend_score: number;
  final_score: number;
  created_at: string;
}

export interface PaperCardListResponse {
  papers: PaperCard[];
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
  keywords_cn: string[];
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

export interface SystemStats {
  app_name?: string;
  app_version?: string;
  total_papers: number;
  journal_count: number;
  keyword_count: number;
  latest_paper_at: string | null;
  latest_crawl_at: string | null;
  source_counts: Record<string, number>;
  year_counts: Record<string, number>;
  top_journals: Record<string, number>;
  db_size_mb?: number;
  scheduler_running?: boolean;
  ai_usage?: {
    total_analyses: number;
    total_tokens: number;
    total_processing_ms: number;
    total_papers_analyzed: number;
    by_model: { model: string; count: number; tokens: number }[];
  };
}

export interface NetworkNode {
  id: string;
  name: string;
  papers?: number;
  count?: number;
  group: string;
}

export interface NetworkLink {
  source: string;
  target: string;
  value: number;
}

export interface NetworkData {
  nodes: NetworkNode[];
  links: NetworkLink[];
}

export interface CrawlLog {
  id: number;
  journal_name: string;
  crawl_start_time: string;
  crawl_end_time: string | null;
  papers_fetched: number;
  papers_failed: number;
  status: string;
  error_message: string | null;
  created_at: string;
}

export interface ApiKeyStatus {
  configured: boolean;
  masked: string;
}

export interface SettingsInfo {
  api_keys: {
    zhipu: ApiKeyStatus;
    openai: ApiKeyStatus;
    siliconflow: ApiKeyStatus;
  };
  models: {
    name: string;
    available: boolean;
    priority: number;
    provider?: string;
  }[];
  scheduler: {
    running: boolean;
    jobs: SchedulerJob[];
  };
  api_token_configured: boolean;
  ports: {
    backend: number;
    frontend: number;
  };
  app_name?: string;
  app_version?: string;
  custom_providers?: CustomProviderStatus[];
  default_model?: string | null;
  embedding_model?: string | null;
}

export interface ModelLinkTestResult {
  ok: boolean;
  model: string;
  latency_ms?: number;
  message: string;
}

export interface CustomProviderStatus {
  name: string;
  base_url: string;
  api_key_configured: boolean;
  api_key_masked: string;
  models: string[];
}

export interface SchedulerJob {
  id: string;
  name: string;
  trigger: string;
  next_run_time: string | null;
  pending: boolean;
}

export interface MaintenanceResult {
  deleted_papers: number;
  deleted_features: number;
  deleted_scores: number;
  deleted_reports: number;
}

// ============ 选题中心（研究空白 + 选题验证器） ============

export interface ResearchGap {
  source: string;
  target: string;
  source_count: number;
  target_count: number;
  cooccurrence: number;
  gap_score: number;
}

export interface ResearchGapsResponse {
  gaps: ResearchGap[];
  total: number;
}

export interface GapAnalysisResponse {
  report_id: number | null;
  status: string | null;
  is_running: boolean;
  model: string | null;
  created_at: string | null;
  raw_analysis: string | null;
  gaps_snapshot: ResearchGap[] | null;
  error_message: string | null;
}

export interface ValidatorStatus {
  embedded_papers: number;
  total_papers: number;
}

/** 验证器召回的一篇近似论文（recall 可见化）。 */
export interface RetrievedPaper {
  id: number;
  title: string;
  source: string | null;
  published_at: string | null;
  keywords: string[];
  similarity: number;
}

/** 验证器 SSE 流首条论文元消息（召回数据 + 模式 + 拥挤度统计）。 */
export interface ValidatorMeta {
  papers: RetrievedPaper[];
  mode: string;
  stats: {
    top30_avg_similarity?: number;
    max_similarity?: number;
    recent_3m_count?: number;
    keyword_overlap?: Array<{ keyword: string; count: number }>;
  };
}

// ============ 选题库（决策层：选题工作台项目） ============

export type TopicProjectStatus = 'to_validate' | 'validated' | 'subscribed' | 'abandoned';

export interface TopicProject {
  id: number;
  title: string;
  source_gap: string | null;
  source_paper_id: number | null;
  novelty: number | null;
  crowding: string | null;
  feasibility: number | null;
  status: TopicProjectStatus;
  created_at: string | null;
  updated_at: string | null;
}

export interface TopicProjectPayload {
  title: string;
  source_gap?: string | null;
  source_paper_id?: number | null;
  validation_report?: string | null;
  novelty?: number | null;
  crowding?: string | null;
  feasibility?: number | null;
}
