export interface Author {
  name: string;
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
  features: { summary: string | null; keywords: string[]; topic: string | null } | null;
  scores: { recency_score: number; venue_score: number; trend_score: number; final_score: number } | null;
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
  /** 工作台「今日值得读」专用：推荐理由（profile/subfield/keyword/top） */
  reason?: { type: string; label: string } | null;
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
  /** 工作台「领域快讯」专用：逐年篇数序列（年份桶对齐，供迷你柱状图展示） */
  series?: Array<{ year: string; count: number }>;
}

export interface TrendingTopicsResponse {
  topics: TrendingTopic[];
  week_start: string;
  week_end: string;
}

export interface PaperDetailResponse extends Paper {
  similar_papers: Array<{ id: string; title: string; similarity_score: number; topic: string | null; keywords_cn: string[] }>;
  should_read_score: number | null;
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

// —— 数据健康中心（P3）：向量/趋势/相关性三块状态 ——
export interface DataHealth {
  embedding: {
    embedded: number;
    total: number;
    missing: number;
  };
  trend: {
    topics: number;
    records: number;
    latest_week_start: string | null;
    latest_updated_at: string | null;
  };
  similarity: {
    pairs: number;
    covered_papers: number;
    latest_computed_at: string | null;
    running: boolean;
  };
}

// —— CNKI 关键词检索爬取 ——
export interface CNKISearchRequest {
  keyword: string;
  search_field?: string;
  years?: string;
  max_pages?: number;
  detail_workers?: number;
  show_browser?: boolean;  // 显示浏览器窗口（无头模式验证码只能自动解；勾选后可人工处理）
  detail_refs?: boolean;   // 详情入库后在同一详情页顺带抓参考文献（省二次导航）
}

export interface CNKISearchProgress {
  phase: 'starting' | 'collecting' | 'details' | 'done' | 'stopped' | string;
  page: number;
  collected: number;
  done: number;
  total: number;
  ok: number;
  already_exists: number;
  filtered: number;
  verify_failed: number;
  failed: number;
}

export interface CNKISearchInfo {
  running: boolean;
  paused?: boolean;
  keyword: string | null;
  started_at: string | null;
  finished_at: string | null;
  message: string | null;
  progress?: CNKISearchProgress | null;
  last_log?: string[];
  /** 断点摘要（.cache/search_checkpoint.json）：同关键词启动将自动从上次进度续跑 */
  checkpoint?: { keyword: string; phase: string; page: number; papers: number; saved_at?: string } | null;
}

/** 参考文献爬取任务状态 */
export interface ReferencesCrawlInfo {
  running: boolean;
  paper_url: string | null;
  paper_title: string | null;
  started_at: string | null;
  finished_at: string | null;
  message: string | null;
  stopped_by_user?: boolean;
  progress?: CNKISearchProgress | null;
  last_log?: string[];
}

/** 论文参考文献条目 */
export interface PaperReferenceItem {
  ref_index: number;
  raw_text: string | null;
  ref_url: string | null;
}

/** 论文参考文献响应 */
export interface PaperReferencesResponse {
  paper_id: string;
  paper_url: string;
  total: number;
  references: PaperReferenceItem[];
}

export interface NetworkNode {
  id: string;
  name: string;
  papers?: number;
  count?: number;
  group: string;
}

export interface NetworkData {
  nodes: NetworkNode[];
  links: Array<{ source: string; target: string; value: number }>;
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
  task_type?: string;
  log_detail?: string | null;
  rerun_params?: string | null;
}

export interface SettingsInfo {
  api_keys: {
    zhipu: { configured: boolean; masked: string };
    openai: { configured: boolean; masked: string };
    siliconflow: { configured: boolean; masked: string };
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
  custom_providers?: Array<{ name: string; base_url: string; api_key_configured: boolean; api_key_masked: string; models: string[] }>;
  default_model?: string | null;
  embedding_model?: string | null;
  cnki_url_prefix?: string;
  agent_enabled?: boolean;
  /** 模型单价（每百万 tokens，元），用于 AI 用量成本估算 */
  ai_model_prices?: Record<string, number>;
}

/** 设置页操作反馈：ok 决定颜色，替代旧的"中文字符串猜测"方案 */
export type Msg = { ok: boolean; text: string } | null;

/** GET /settings/export 导出的用户配置（含明文 API Key） */
export interface ExportedSettings {
  exported_at?: string;
  app_version?: string;
  api_keys?: Record<string, string>;
  custom_providers?: Array<{ name: string; base_url: string; api_key: string; models: string[] }>;
  ports?: { backend_port: number; frontend_port: number };
  default_model?: string | null;
  embedding_model?: string | null;
  app_name?: string;
  cnki_url_prefix?: string;
  agent_enabled?: boolean;
  ai_model_prices?: Record<string, number>;
}

export interface ModelLinkTestResult {
  ok: boolean;
  model: string;
  latency_ms?: number;
  message: string;
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

export interface TopicCluster {
  id: number;
  rank: number;
  label: string;
  top_keywords: string[];
  size: number;
  cx: number;
  cy: number;
  year_range: string;
  representative_papers: Array<{ id: string; title: string; score: number }>;
  points: Array<{ id: string; title: string; x: number; y: number }>;
}

export interface TopicClustersResponse {
  total: number;
  k: number;
  clusters: TopicCluster[];
}

export interface KeywordTrendsResponse {
  years: string[];
  series: Array<{
    name: string;
    yearly: Array<{ year: string; count: number }>;
    total: number;
    last12: number;
    prev12: number;
    trend: 'emerging' | 'declining' | 'stable';
  }>;
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
  n?: number; // 与 AI 回答中的 [n] 引用编号对齐
}

// ============ 选题库（决策层：选题工作台项目） ============

export interface TopicProject {
  id: number;
  title: string;
  source_gap: string | null;
  source_type?: string;
  source_ref?: string | null;
  source_paper_id: number | null;
  novelty: number | null;
  crowding: string | null;
  feasibility: number | null;
  status: 'to_validate' | 'validated' | 'subscribed' | 'abandoned';
  validation_report?: string | null;
  research_questions?: string[];
  current_step?: number;
  generated_topics?: GeneratedTopic[];
  overview?: string | null;
  data_insights?: DataInsights | null;
  literature_review?: string | null;
  proposal?: string | null;
  journal_advice?: string | null;
  ai_pending?: string | null;
  ai_error?: string | null;
  papers?: ProjectPaper[];
  created_at: string | null;
  updated_at: string | null;
}

export interface TopicProjectPayload {
  title: string;
  source_gap?: string | null;
  source_type?: string;
  source_ref?: string | null;
  source_paper_id?: number | null;
  validation_report?: string | null;
  novelty?: number | null;
  crowding?: string | null;
  feasibility?: number | null;
  research_questions?: string[];
  current_step?: number;
}

/** 项目文献集条目（Step3 文献管理）。 */
export interface ProjectPaper {
  id: number;
  paper_id: string;
  similarity: number | null;
  read_status: 'to_read' | 'reading' | 'read';
  note: string | null;
  title: string;
  journal: string | null;
  authors: string[];
  published_at: string | null;
  keywords: string[];
  abstract: string;
}

/** Step1 LLM 生成的候选选题。 */
export interface GeneratedTopic {
  title: string;
  research_questions: string[];
  hypothesis: string;
  why: string;
  /** 检索关键词（选题拆分，供验证步知网爬虫 / 文献检索使用）。 */
  keywords?: string[];
  methods?: string[];
  data?: string[];
}

/** Step4 数据与方法线索。 */
export interface DataInsights {
  data_sources?: Array<{ name: string; papers: string[]; usage: string }>;
  methods?: Array<{ name: string; papers: string[]; note: string }>;
  advice?: string;
  my_notes?: string;
}

/** 文献检索候选（search-papers 返回）。 */
export interface ProjectSearchPaper {
  id: string;
  title: string;
  abstract: string;
  journal: string | null;
  source: string | null;
  published_at: string | null;
  keywords: string[];
  similarity: number | null;
  in_project: boolean;
}

/** 相关文献推荐（recommend-papers 返回）：基于文献集相似论文，供用户决定是否加入引用。 */
export interface ProjectRecommendedPaper extends ProjectSearchPaper {
  /** 由哪篇项目文献引出（用于展示推荐理由） */
  via_title: string | null;
}

// ============ 选题灵感向导（一句话想法 → 偏好 → AI 候选选题） ============

export interface TopicIdeaPreferences {
  identity?: 'bachelor' | 'master' | 'phd' | 'faculty';
  paper_type?: 'empirical' | 'review' | 'case' | 'theory';
  subfields?: string[];
  methods?: string[];
  data?: string[];
  venue?: 'cn_top' | 'cn_regular' | 'en_top' | 'any';
  prefer_novelty?: number;
  focus_china?: boolean;
  extra?: string;
}

export interface TopicIdeaReference {
  id: string;
  title: string;
  journal: string | null;
  published_at: string | null;
  similarity: number | null;
}

export interface TopicIdeaCandidate {
  id: string;
  title: string;
  research_questions: string[];
  hypothesis: string;
  why: string;
  angle: string;
  methods: string[];
  data: string[];
  subfield: string;
  /** 检索关键词：选题拆分，供验证步知网爬虫 / 文献检索使用 */
  keywords: string[];
  assessment: {
    novelty: number;
    feasibility: number;
    literature_support: number;
    comment: string;
  };
  references: TopicIdeaReference[];
}

export interface TopicIdeaGenerateRequest {
  idea: string;
  preferences?: TopicIdeaPreferences;
  feedback?: string | null;
  previous_candidates?: Array<{ title: string; research_questions: string[] }>;
}

export interface TopicIdeaGenerateResponse {
  round: number;
  candidates: TopicIdeaCandidate[];
}
