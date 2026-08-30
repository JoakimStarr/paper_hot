import { PaperListResponse, PaperCardListResponse, PaperCard, TrendingTopicsResponse, PaperDetailResponse, AIAnalysisResponseV2, AIAnalysisReport, SystemStats, DataHealth, NetworkData, CrawlLog, SettingsInfo, SchedulerJob, MaintenanceResult, ModelLinkTestResult, ResearchGapsResponse, GapAnalysisResponse, ValidatorStatus, TopicProject, TopicProjectPayload, CNKISearchRequest, CNKISearchInfo, ReferencesCrawlInfo, PaperReferencesResponse, PaperCitedByResponse, TopicClustersResponse, KeywordTrendsResponse, ProjectPaper, ProjectSearchPaper, ProjectRecommendedPaper, ExportedSettings, TopicIdeaGenerateRequest, TopicIdeaCandidate, MethodPlaybookEntry } from '@/types/paper';
import { getUserId } from '@/lib/user';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || '/api'; // 默认走同源 /api，由 next.config rewrites 代理到后端实际端口

// 可选 API Token：若后端配置了 api_token，前端需在同一处注入才能通过鉴权。
// 不配置时（NEXT_PUBLIC_API_TOKEN 为空/未设置）行为与之前一致——后端未设 token 时默认放行。
const API_TOKEN = process.env.NEXT_PUBLIC_API_TOKEN || '';

// 统一请求封装（原生 fetch 替代 axios，自动注入 x-api-token，行为与旧 apiClient 完全一致）
//
// 幂等请求（GET/HEAD）自动重试：后端重启/启动期间，next dev 代理连不上后端时
// 会以 500「socket hang up」返回浏览器（典型报错：api/network/gaps/analysis 500）。
// 对这类瞬时故障短退避重试，避免页面一打开就报错；非幂等方法一律不重试。
const RETRYABLE_METHODS = new Set(['GET', 'HEAD']);
const RETRY_DELAYS = [600, 1200]; // 重试间隔（ms）

/** 公共请求头：x-api-token 鉴权 + x-user-id 本地身份（P1-10 个人化）。 */
function buildHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (API_TOKEN) headers['x-api-token'] = API_TOKEN;
  try {
    headers['x-user-id'] = getUserId();
  } catch { /* SSR 环境忽略 */ }
  return headers;
}

/** 后端业务错误：携带 HTTP 状态码与 detail 文案。
 *  调用方以 `e instanceof ApiError ? e.detail : e.message` 取可展示信息（对应旧 axios 响应体的 detail 字段）。 */
export class ApiError extends Error {
  status?: number;
  detail?: string;

  constructor(message: string, status?: number, detail?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

// —— 前端错误上报（日志系统）：统一入口，静默失败，按内容去重防刷屏 ——
const _reportedErrors = new Map<string, number>();
const _REPORT_DEDUP_MS = 10_000;

export function logClientError(message: string, stack?: string, level: 'error' | 'warning' = 'error') {
  try {
    const key = `${level}:${String(message).slice(0, 120)}`;
    const now = Date.now();
    const last = _reportedErrors.get(key);
    if (last && now - last < _REPORT_DEDUP_MS) return;
    _reportedErrors.set(key, now);
    if (_reportedErrors.size > 200) {
      _reportedErrors.forEach((t, k) => {
        if (Date.now() - t > 60_000) _reportedErrors.delete(k);
      });
    }
    void fetch(`${API_BASE_URL}/logs/client`, {
      method: 'POST',
      headers: buildHeaders(),
      body: JSON.stringify({
        message: String(message).slice(0, 2000),
        stack: stack ? stack.slice(0, 20_000) : undefined,
        url: typeof window !== 'undefined' ? window.location.href.slice(0, 500) : undefined,
        level,
        user_agent: typeof navigator !== 'undefined' ? navigator.userAgent.slice(0, 300) : undefined,
      }),
    }).catch(() => {});
  } catch { /* 上报本身失败忽略，不影响业务 */ }
}

async function request<T>(
  url: string,
  options?: { method?: string; params?: Record<string, unknown>; body?: unknown; signal?: AbortSignal },
): Promise<T> {
  const method = options?.method || 'GET';
  const headers = buildHeaders();

  let fullUrl = `${API_BASE_URL}${url}`;
  if (options?.params) {
    const qs = new URLSearchParams(
      Object.entries(options.params)
        .filter(([, v]) => v !== undefined && v !== null)
        .map(([k, v]) => [k, String(v)]),
    ).toString();
    if (qs) fullUrl += `?${qs}`;
  }

  const maxRetries = RETRYABLE_METHODS.has(method) ? RETRY_DELAYS.length : 0;

  for (let attempt = 0; ; attempt++) {
    let res: Response;
    try {
      res = await fetch(fullUrl, {
        method,
        headers,
        body: options?.body !== undefined ? JSON.stringify(options.body) : undefined,
        signal: options?.signal,
      });
    } catch (e: any) {
      // 网络层失败（代理/后端不可达），幂等请求重试，AbortError 不重试
      if (attempt < maxRetries && (!e || e?.name !== 'AbortError')) {
        await new Promise(r => setTimeout(r, RETRY_DELAYS[attempt]));
        continue;
      }
      if (e?.name !== 'AbortError') {
        logClientError(`API network error: ${method} ${url} — ${e?.message || ''}`, e?.stack);
      }
      throw e;
    }

    // 5xx（含代理转发的 500）通常为后端临时不可用，幂等请求重试
    if (res.status >= 500 && attempt < maxRetries) {
      await new Promise(r => setTimeout(r, RETRY_DELAYS[attempt]));
      continue;
    }

    if (!res.ok) {
      const err = (await res.json().catch(() => null)) as { detail?: string } | null;
      const detail = err?.detail || `Request failed: ${res.status}`;
      if (res.status >= 500) logClientError(`API ${res.status}: ${method} ${url} — ${detail}`);
      throw new ApiError(detail, res.status, typeof detail === 'string' ? detail : undefined);
    }

    // 部分 DELETE/空响应无 body，返回 undefined
    const text = await res.text();
    return (text ? JSON.parse(text) : undefined) as T;
  }
}

export interface FilterStatistics {
  discipline_counts: Record<string, number>;
  subfield_counts: Record<string, number>;
  cnki_subject_counts: Record<string, number>;
  journal_counts: Record<string, number>;
  source_counts: Record<string, number>;
  topic_counts: Record<string, number>;
  score_counts: Record<string, number>;
  total_papers: number;
}

export interface AuthorPapersResponse {
  papers: PaperCard[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
  author_name: string;
}

export interface AuthorStatsResponse {
  total_papers: number;
  first_author_count: number;
  recent_year: string | null;
  top_journal: string | null;
  top_keywords: string[];
  top_subfield: string | null;
  coauthors: Array<{ name: string; count: number }>;
}

export interface KeywordMapResponse {
  keyword: string;
  total_papers: number;
  cooccurring_keywords: Array<[string, number]>;
  yearly_trend: Array<[string, number]>;
  representative_papers: Array<{ id: string; title: string; journal_name: string | null; score: number | null }>;
  journal_distribution: Array<[string, number]>;
}

export interface SearchSuggestion {
  text: string;
  type: 'keyword' | 'title' | 'author';
  count: number;
}

export interface SearchSuggestResponse {
  suggestions: SearchSuggestion[];
}

export interface SubfieldDistributionItem {
  subfield: string;
  count: number;
}

export interface SubfieldDistributionResponse {
  distribution: SubfieldDistributionItem[];
}

export const papersApi = {
  getPapers: async (params: {
    page?: number;
    page_size?: number;
    topic?: string;
    source?: string;
    min_score?: number;
    days_back?: number;
    discipline?: string;
    economics_subfield?: string;
    cnki_subject?: string;
    journal_name?: string;
    search?: string;
    search_field?: string;
    sort_by?: string;
    sort_order?: string;
  }): Promise<PaperCardListResponse> => request<PaperCardListResponse>('/papers', { params }),

  getPaperById: async (id: string): Promise<PaperDetailResponse> =>
    request<PaperDetailResponse>(`/papers/${id}`),

  getTrendingTopics: async (weeks_back?: number): Promise<TrendingTopicsResponse> =>
    request<TrendingTopicsResponse>('/trending-topics', { params: { weeks_back } }),

  explainTrend: async (topic: string): Promise<{ topic: string; explanation: string; ai_used: boolean; series: Array<{ week: string; paper_count: number; growth_rate: number }> }> =>
    request('/trends/explain', { params: { topic } }),

  getKeywordMap: async (keyword: string): Promise<KeywordMapResponse> =>
    request('/network/keyword-map', { params: { keyword } }),

  getAIAnalysisV2: async (): Promise<AIAnalysisResponseV2> =>
    request<AIAnalysisResponseV2>('/ai-analysis/v2'),

  startAIAnalysis: async (model?: string): Promise<AIAnalysisResponseV2> =>
    request<AIAnalysisResponseV2>('/ai-analysis/v2/analyze', { method: 'POST', body: { model } }),

  getAIAnalysisModels: async (): Promise<{ models: Array<{ name: string; available: boolean; priority: number; provider?: string }> }> =>
    request('/ai-analysis/models'),

  getAIAnalysisReports: async (limit: number = 10): Promise<{ reports: AIAnalysisReport[]; total: number }> =>
    request('/ai-analysis/reports', { params: { limit } }),

  getAIAnalysisReportById: async (reportId: number): Promise<AIAnalysisReport> =>
    request(`/ai-analysis/reports/${reportId}`),

  getTrendChats: async (reportId: number): Promise<Array<{ role: string; content: string }>> =>
    request(`/ai-analysis/reports/${reportId}/chats`),

  saveTrendChats: async (reportId: number, messages: Array<{ role: string; content: string }>): Promise<void> =>
    request(`/ai-analysis/reports/${reportId}/chats`, { method: 'POST', body: { messages } }),

  clearTrendChats: async (reportId: number): Promise<void> =>
    request(`/ai-analysis/reports/${reportId}/chats`, { method: 'DELETE' }),

  getFilterStatistics: async (): Promise<FilterStatistics> =>
    request('/filter-statistics'),

  getSystemStats: async (): Promise<SystemStats> =>
    request('/stats'),

  // —— 数据健康中心（P3）：向量/趋势/相关性三块状态聚合 ——
  getDataHealth: async (): Promise<DataHealth> =>
    request('/data-health'),

  // 一键刷新趋势（复用既有接口）
  triggerTrendUpdate: async (): Promise<{ status: string; message?: string }> =>
    request('/update-trend-scores', { method: 'POST' }),

  // 相似度全量重算 + 状态（复用既有接口）
  triggerRecomputeSimilarities: async (): Promise<{ status: string; message?: string }> =>
    request('/recompute-all-similarities', { method: 'POST' }),
  getSimilaritiesStatus: async (): Promise<{ running: boolean; last_pairs?: number; last_error?: string | null }> =>
    request('/recompute-all-similarities'),

  // —— CNKI 关键词检索爬取（复用 cnki_paper_captcha.py --search，子进程触发）——
  startCNKISearchCrawl: async (opts: CNKISearchRequest): Promise<{ status: string; keyword: string }> =>
    request('/crawl/cnki/search/start', { method: 'POST', body: opts }),
  getCNKISearchStatus: async (): Promise<CNKISearchInfo> =>
    request('/crawl/cnki/search/status'),
  pauseCNKISearch: async (): Promise<{ status: string }> =>
    request('/crawl/cnki/search/pause', { method: 'POST' }),
  resumeCNKISearch: async (): Promise<{ status: string }> =>
    request('/crawl/cnki/search/resume', { method: 'POST' }),
  stopCNKISearch: async (): Promise<{ status: string }> =>
    request('/crawl/cnki/search/stop', { method: 'POST' }),

  startReferencesCrawl: async (opts: { paper_url?: string; urls?: string[]; paper_title?: string; max_items?: number; interval?: number; show_browser?: boolean }): Promise<{ status: string }> =>
    request('/crawl/references/start', { method: 'POST', body: opts }),
  getReferencesStatus: async (): Promise<ReferencesCrawlInfo> =>
    request('/crawl/references/status'),
  stopReferencesCrawl: async (): Promise<{ status: string }> =>
    request('/crawl/references/stop', { method: 'POST' }),
  /** 论文参考文献列表（未抓取过返回空列表）。 */
  getPaperReferences: async (paperId: string): Promise<PaperReferencesResponse> =>
    request(`/papers/${paperId}/references`),
  /** 被引查询：库内哪些论文的参考文献引用了该论文。 */
  getPaperCitedBy: async (paperId: string): Promise<PaperCitedByResponse> =>
    request(`/papers/${paperId}/cited-by`),
  /** 智能批量补抓：按 置顶>收藏>已读>评分 优先级自动选出未抓取论文队列（复用 references 后台任务）。 */
  backfillReferencesCrawl: async (opts: { limit?: number; max_items?: number; interval?: number }): Promise<{ status: string; queued?: number; message?: string; paper_title?: string }> =>
    request('/crawl/references/backfill', { method: 'POST', body: opts }),
  /** 参考文献覆盖率：已抓论文数 / 有效链接论文总数。 */
  getReferencesCoverage: async (): Promise<{ papers_with_refs: number; papers_total: number }> =>
    request('/crawl/references/coverage'),
  sendFeedback: async (body: { surface: string; ref_id?: string; content_hash?: string; rating: 1 | -1; model?: string }): Promise<{ status: string }> =>
    request('/ai/feedback', { method: 'POST', body }),

  getKeywordNetwork: async (): Promise<NetworkData> =>
    request('/network/keywords'),

  getTopicClusters: async (): Promise<TopicClustersResponse> =>
    request('/network/topic-clusters'),

  getKeywordTrends: async (top = 12): Promise<KeywordTrendsResponse> =>
    request('/network/keyword-trends', { params: { top } }),

  getCrawlStatus: async (limit: number = 10): Promise<{ logs: CrawlLog[]; total: number }> =>
    request('/crawl/status', { params: { limit } }),

  rerunCrawl: async (logId: number): Promise<{ status: string; task_type: string; name: string }> =>
    request('/crawl/rerun', { method: 'POST', body: { log_id: logId } }),

  startCrawl: async (journalNames?: string[]): Promise<{ crawl_log_id: string; status: string; message: string }> =>
    request('/crawl/start', { method: 'POST', body: { journal_names: journalNames || null } }),

  startCNKITop50Crawl: async (opts?: { journal_names?: string[]; max_results_per_journal?: number; max_journals?: number }): Promise<{ status: string; message: string }> =>
    request('/crawl/cnki/top50/start', { method: 'POST', body: opts || {} }),

  startCNKNaviCrawl: async (): Promise<{ status: string; message: string }> =>
    request('/crawl/cnki/navi/start', { method: 'POST', body: {} }),

  analyzePaper: async (paperId: string, model?: string, signal?: AbortSignal): Promise<{ analysis: string | null; status: string; model?: string }> =>
    request(`/papers/${paperId}/analyze`, { method: 'POST', body: model ? { model } : {}, signal }),

  /**
   * 单篇论文 AI 分析——SSE 流式版（POST /papers/{id}/analyze/stream）。
   * 帧格式对齐后端 _stream_llm_content：{"content": "..."} | {"error": "..."} | {"done": true}。
   * 若后端返回 JSON（如已有新鲜 pending 分析，HTTP 200 非 SSE），经 onDone({status:'pending'}) 通知调用方退回轮询。
   */
  streamPaperAnalysis: async (
    paperId: string,
    cb: { onContent: (delta: string) => void; onError: (msg: string) => void; onDone: (result?: { status?: string; analysis?: string | null }) => void },
    model?: string,
    signal?: AbortSignal,
  ): Promise<void> => {
    let response: Response;
    try {
      response = await fetch(`${API_BASE_URL}/papers/${paperId}/analyze/stream`, {
        method: 'POST',
        headers: buildHeaders(),
        body: JSON.stringify(model ? { model } : {}),
        signal,
      });
    } catch (e: any) {
      if (e?.name === 'AbortError') return;
      cb.onError(String(e?.message || 'Request failed'));
      return;
    }
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Request failed' }));
      const rawDetail = err.detail || 'Request failed';
      const message = typeof rawDetail === 'string'
        ? rawDetail
        : Array.isArray(rawDetail)
          ? rawDetail.map((e: any) => `${e?.loc?.join('.') ?? ''}: ${e?.msg ?? String(e)}`).filter(Boolean).join('; ')
          : JSON.stringify(rawDetail);
      cb.onError(message);
      return;
    }
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/json')) {
      // 非 SSE：pending 等 JSON 语义，交调用方处理
      const data = await response.json().catch(() => ({}));
      cb.onDone({ status: data.status, analysis: data.analysis });
      return;
    }
    const reader = response.body!.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let errored = false;
    for (;;) {
      const { done: readerDone, value } = await reader.read();
      if (readerDone) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const data = JSON.parse(line.slice(6));
          if (data.error) {
            errored = true;
            cb.onError(String(data.error));
            break;
          }
          if (data.content) cb.onContent(String(data.content));
        } catch { /* 跳过不完整帧 */ }
      }
      if (errored) break;
    }
    if (!errored) cb.onDone();
  },

  getLatestAnalysis: async (paperId: string): Promise<{ analysis: string | null; status: string | null; model?: string; created_at?: string }> =>
    request(`/papers/${paperId}/analyses/latest`),

  getTopicRelevance: async (paperId: string, topic?: string): Promise<{ score: number | null; reason: string; ai_used: boolean; overlaps?: string[] }> =>
    request(`/papers/${paperId}/relevance`, { method: 'POST', body: { ...(topic ? { topic } : {}) } }),

  getAuthorPapers: async (authorName: string, page: number = 1, pageSize: number = 20): Promise<AuthorPapersResponse> =>
    request(`/authors/${encodeURIComponent(authorName)}/papers`, { params: { page, page_size: pageSize } }),

  getAuthorStats: async (authorName: string): Promise<AuthorStatsResponse> =>
    request(`/authors/${encodeURIComponent(authorName)}/stats`),

  getSearchSuggestions: async (q: string, limit: number = 8): Promise<SearchSuggestResponse> =>
    request('/search/suggest', { params: { q, limit } }),

  getSubfieldDistribution: async (): Promise<SubfieldDistributionResponse> =>
    request('/subfield-distribution'),

  getKeywordDistribution: async (): Promise<{ distribution: Array<{ keyword: string; count: number }> }> =>
    request('/keyword-distribution'),

  getSettings: async (): Promise<SettingsInfo> =>
    request('/settings'),

  updateSettings: async (data: { api_keys?: Record<string, string>; model_priority?: string[]; ports?: Record<string, number>; app_name?: string; default_model?: string | null; embedding_model?: string | null; custom_providers?: Array<{name: string; base_url: string; api_key: string; models: string[]; previous_name?: string}>; cnki_url_prefix?: string | null; agent_enabled?: boolean; ai_model_prices?: Record<string, number> }): Promise<{ success: boolean }> =>
    request('/settings', { method: 'PUT', body: data }),

  exportSettings: async (): Promise<ExportedSettings> =>
    request('/settings/export'),

  restartServices: async (): Promise<{ status: string; message: string }> =>
    request('/system/restart', { method: 'POST' }),

  testModelLink: async (model: string): Promise<ModelLinkTestResult> =>
    request('/settings/test-model', { method: 'POST', body: { model } }),

  fetchProviderModels: async (body: { name?: string; base_url?: string; api_key?: string }): Promise<{ models?: string[]; message?: string }> =>
    request('/settings/fetch-models', { method: 'POST', body }),

  getSchedulerJobs: async (): Promise<SchedulerJob[]> =>
    request('/scheduler/jobs'),

  triggerSchedulerJob: async (jobId: string): Promise<{ success: boolean; message: string }> =>
    request(`/scheduler/trigger/${jobId}`, { method: 'POST' }),

  toggleScheduler: async (): Promise<{ running: boolean; message: string }> =>
    request('/scheduler/toggle', { method: 'POST' }),

  cleanupData: async (): Promise<MaintenanceResult> =>
    request('/maintenance/cleanup', { method: 'POST' }),

  backfillAbstracts: async (): Promise<{ status: string; task_id: string }> =>
    request('/maintenance/backfill-abstracts', { method: 'POST' }),

  getBackfillStatus: async (): Promise<{ tasks: Record<string, { status: string; stats?: Record<string, number> }> }> =>
    request('/maintenance/backfill-abstracts'),

  // #7 异步化：批量分析先拿 batch_id，再轮询 getBatchAnalyze 拿结果
  startBatchAnalyze: async (paperIds: string[], model?: string): Promise<{ batch_id: number; status: string; paper_count: number }> =>
    request('/papers/batch-analyze', { method: 'POST', body: { paper_ids: paperIds, ...(model ? { model } : {}) } }),

  getBatchAnalyze: async (batchId: number): Promise<{ batch_id: number; status: string; content?: string; paper_count?: number; model?: string; error_message?: string }> =>
    request(`/papers/batch-analyze/${batchId}`),
};

// —— 个人化（P1-10）：收藏 / 阅读历史 / 关注子领域 ——
export const personalApi = {
  getMe: async (): Promise<{ user_id: string; followed_subfields: string[]; read_count: number; favorite_count: number }> =>
    request('/personal/me'),

  getFavorites: async (): Promise<{ papers: PaperCard[]; total: number }> =>
    request('/personal/favorites'),

  toggleFavorite: async (paperId: string): Promise<{ bookmarked: boolean }> =>
    request('/personal/favorites/toggle', { method: 'POST', body: { paper_id: paperId } }),

  getPins: async (): Promise<{ paper_ids: string[] }> =>
    request('/personal/pins'),

  togglePin: async (paperId: string): Promise<{ pinned: boolean }> =>
    request('/personal/pins/toggle', { method: 'POST', body: { paper_id: paperId } }),

  // —— "不感兴趣"屏蔽（P2）：领域/期刊/关键词/作者 ——
  getPreferences: async (): Promise<{ items: Array<{ entity_type: string; entity_value: string }> }> =>
    request('/personal/preferences'),
  addPreference: async (entity_type: string, entity_value: string): Promise<{ added: boolean }> =>
    request('/personal/preferences', { method: 'POST', body: { entity_type, entity_value } }),
  removePreference: async (entity_type: string, entity_value: string): Promise<{ removed: boolean }> =>
    request('/personal/preferences', { method: 'DELETE', params: { entity_type, entity_value } }),

  recordReading: async (paperId: string): Promise<{ recorded: boolean }> =>
    request('/personal/reading', { method: 'POST', body: { paper_id: paperId } }),

  getReadingHistory: async (): Promise<{ papers: PaperCard[]; total: number }> =>
    request('/personal/reading-history'),

  getReadIds: async (): Promise<{ paper_ids: string[] }> =>
    request('/personal/read-ids'),

  getSubfields: async (): Promise<{ subfields: string[] }> =>
    request('/personal/subfields'),

  setSubfields: async (subfields: string[]): Promise<{ subfields: string[] }> =>
    request('/personal/subfields', { method: 'PUT', body: { subfields } }),

  getKeywords: async (): Promise<{ keywords: string[] }> =>
    request('/personal/keywords'),

  setKeywords: async (keywords: string[]): Promise<{ keywords: string[] }> =>
    request('/personal/keywords', { method: 'PUT', body: { keywords } }),

  getSuggestions: async (): Promise<{ subfields: Array<{ name: string; reason: string; paper_count: number }>; keywords: Array<{ name: string; reason: string; paper_count: number }> }> =>
    request('/personal/suggestions'),

  // —— 推荐反馈闭环（工作台优化）：多推这类 / 少推这类 ——
  recommendFeedback: async (paperId: string, action: 'more' | 'less'): Promise<{ applied: boolean; entity_type?: string; entity_value?: string }> =>
    request('/personal/recommend-feedback', { method: 'POST', body: { paper_id: paperId, action } }),

  recordReadingBatch: async (paperIds: string[]): Promise<{ recorded: number }> =>
    request('/personal/reading/batch', { method: 'POST', body: { paper_ids: paperIds } }),

  // —— 稍后读队列 ——
  getReadLater: async (): Promise<{ paper_ids: string[] }> =>
    request('/personal/read-later'),

  toggleReadLater: async (paperId: string): Promise<{ queued: boolean }> =>
    request('/personal/read-later/toggle', { method: 'POST', body: { paper_id: paperId } }),

  getReadLaterPapers: async (): Promise<{ papers: PaperCard[]; total: number }> =>
    request('/personal/read-later/papers'),
};

// —— 研究工作台（P1-7）——
export interface DashboardData {
  today_read: PaperCard[];
  briefing: {
    topics: Array<{ topic: string; paper_count: number; growth_rate: number; trend: 'rising' | 'declining' | 'stable' }>;
    ai_note: string | null;
  };
  mine: {
    favorites: PaperCard[];
    recent_analyses: Array<{ paper_id: string; title: string; status: string | null; created_at: string | null }>;
    topic_projects: Array<{ id: number; title: string; status: string; novelty: number | null; crowding: number | null; current_step?: number; paper_count?: number; read_count?: number }>;
    reviews: Array<{ id: number; topic: string; paper_count: number; created_at: string | null }>;
    latest_report_summary: string | null;
    latest_report_id: number | null;
    favorite_count: number;
    has_followed_subfields: boolean;
  };
}

// —— 个人页「今日速览条」统计（首页 TodayBriefBar 用）——
export interface TodayBrief {
  today_count: number;
  month_count: number;
  watch_subfield_count: number | null;
  generated_at: string;
}

// —— 技能层（skills）：方法手册等系统预置能力 ——
export const skillsApi = {
  getMethodPlaybook: async (): Promise<{ entries: MethodPlaybookEntry[] }> =>
    request('/skills/method-playbook'),
};

export const dashboardApi = {
  // sections：按页签只取所需子集（today_read/briefing/mine），降低首屏与切页成本
  getDashboard: async (seed = 0, sections?: Array<'today_read' | 'briefing' | 'mine'>): Promise<Partial<DashboardData>> => {
    const params = new URLSearchParams();
    if (seed) params.set('seed', String(seed));
    if (sections?.length) params.set('sections', sections.join(','));
    const qs = params.toString();
    return request<Partial<DashboardData>>(`/dashboard${qs ? `?${qs}` : ''}`);
  },

  // 关注子领域近 30 天新论文（工作台「新论文提醒」就地展开）
  getWatchNewPapers: async (limit = 10): Promise<{ papers: PaperCard[]; total: number }> =>
    request(`/dashboard/watch-new-papers?limit=${limit}`),

  getTodayBrief: async (): Promise<TodayBrief> => request<TodayBrief>('/dashboard/today-brief'),
};

// —— 日志系统（系统页「日志」标签页）——
export interface ActionLogItem {
  id: number;
  request_id: string;
  user_id: string;
  method: string;
  path: string;
  status_code: number;
  duration_ms: number;
  query: string | null;
  created_at: string | null;
}

export interface ErrorLogItem {
  id: number;
  source: string;
  request_id: string;
  user_id: string;
  method: string | null;
  path: string | null;
  status_code: number | null;
  error_type: string;
  error_message: string;
  traceback: string | null;
  request_info: Record<string, unknown> | null;
  created_at: string | null;
}

export interface LogListResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export const logsApi = {
  listActionLogs: async (params: Record<string, unknown>): Promise<LogListResponse<ActionLogItem>> =>
    request('/system/action-logs', { params }),
  listErrorLogs: async (params: Record<string, unknown>): Promise<LogListResponse<ErrorLogItem>> =>
    request('/system/error-logs', { params }),
  getErrorLog: async (id: number): Promise<ErrorLogItem> =>
    request(`/system/error-logs/${id}`),
};

// —— 产出环节（P2-11）：综述生成 / 期刊适配 / 引用导出 ——
export interface ReviewBrief { id: number; topic: string; status: string; model: string | null; created_at: string | null }
export interface ReviewDetail extends ReviewBrief { content: string | null; papers: Array<Record<string, unknown>> | null }

export const producerApi = {
  startReview: async (topic: string, model?: string): Promise<{ review_id: number; status: string; topic: string }> =>
    request('/producer/review', { method: 'POST', body: { topic, ...(model ? { model } : {}) } }),

  getReview: async (reviewId: number): Promise<ReviewDetail> =>
    request(`/producer/review/${reviewId}`),

  listReviews: async (limit = 10): Promise<ReviewBrief[]> =>
    request('/producer/reviews', { params: { limit } }),

  suggestJournal: async (topic: string, abstract?: string, model?: string): Promise<{ topic: string; recommendations: string; suggestions: Array<{ journal: string; reason: string }>; ai_used: boolean }> =>
    request('/producer/journal', { method: 'POST', body: { topic, abstract, ...(model ? { model } : {}) } }),

  exportCitations: async (papers: Array<Record<string, unknown>>, format: 'gbt7714' | 'bibtex'): Promise<{ format: string; citations: string[]; total: number }> =>
    request('/producer/citations', { method: 'POST', body: { papers, format } }),
};

// —— 选题中心：研究空白发现（P1）+ 选题验证器（P2）——
export const topicsApi = {
  getResearchGaps: async (limit = 10): Promise<ResearchGapsResponse> =>
    request('/network/gaps', { params: { limit } }),

  startGapAnalysis: async (model?: string, limit = 10): Promise<GapAnalysisResponse> =>
    request('/network/gaps/analyze', { method: 'POST', body: { model, limit } }),

  getGapAnalysis: async (): Promise<GapAnalysisResponse> =>
    request('/network/gaps/analysis'),

  getValidatorStatus: async (): Promise<ValidatorStatus> =>
    request('/topic-validator/status'),

  backfillEmbeddings: async (batchSize = 100): Promise<{ status: string; batch_size: number }> =>
    request('/topic-validator/embeddings/backfill', { method: 'POST', params: { batch_size: batchSize } }),

  // —— 选题库（决策层）——
  listTopicProjects: async (status?: string): Promise<TopicProject[]> =>
    request<TopicProject[]>('/topic-projects', { params: status ? { status } : {} }),

  createTopicProject: async (payload: TopicProjectPayload): Promise<TopicProject> =>
    request<TopicProject>('/topic-projects', { method: 'POST', body: payload }),

  updateTopicProject: async (
    id: number,
    payload: Partial<Pick<TopicProject, 'title' | 'status' | 'novelty' | 'crowding' | 'feasibility' | 'research_questions' | 'current_step' | 'generated_topics'>>,
  ): Promise<TopicProject> =>
    request<TopicProject>(`/topic-projects/${id}`, { method: 'PATCH', body: payload }),

  deleteTopicProject: async (id: number): Promise<void> =>
    request<void>(`/topic-projects/${id}`, { method: 'DELETE' }),
};

// —— 研究工作台（Workbench）：项目详情 / 文献集 / 统一 AI 操作 ——
export const workbenchApi = {
  /** 项目详情（全字段 + 文献集 + ai_pending/ai_error 状态）。 */
  getProject: async (id: number): Promise<TopicProject> =>
    request<TopicProject>(`/topic-projects/${id}`),

  /** 更新项目任意步骤字段（research_questions/current_step/validation_report 等）。 */
  updateProject: async (id: number, payload: Record<string, unknown>): Promise<TopicProject> =>
    request<TopicProject>(`/topic-projects/${id}`, { method: 'PATCH', body: payload }),

  // —— 文献集 ——
  listProjectPapers: async (id: number): Promise<ProjectPaper[]> =>
    request<ProjectPaper[]>(`/topic-projects/${id}/papers`),

  addProjectPaper: async (id: number, paperId: string, similarity?: number | null): Promise<ProjectPaper> =>
    request<ProjectPaper>(`/topic-projects/${id}/papers`, {
      method: 'POST',
      body: { paper_id: paperId, ...(similarity != null ? { similarity } : {}) },
    }),

  updateProjectPaper: async (
    id: number,
    paperId: string,
    payload: Partial<Pick<ProjectPaper, 'read_status' | 'note'>>,
  ): Promise<ProjectPaper> =>
    request<ProjectPaper>(`/topic-projects/${id}/papers/${paperId}`, { method: 'PATCH', body: payload }),

  deleteProjectPaper: async (id: number, paperId: string): Promise<void> =>
    request<void>(`/topic-projects/${id}/papers/${paperId}`, { method: 'DELETE' }),

  /** 检索候选论文（embedding 召回，带 in_project 标记）。 */
  searchProjectPapers: async (id: number, query: string, limit = 12): Promise<{ mode: string; count: number; papers: ProjectSearchPaper[] }> =>
    request(`/topic-projects/${id}/search-papers`, { method: 'POST', body: { query, limit } }),

  /** 相关文献推荐：基于文献集相似论文（PaperSimilarity），排除已在文献集的。 */
  recommendProjectPapers: async (id: number, limit = 10, paperId?: string): Promise<{ mode: string; count: number; papers: ProjectRecommendedPaper[] }> =>
    request(`/topic-projects/${id}/recommend-papers`, {
      method: 'POST',
      body: { limit, ...(paperId ? { paper_id: paperId } : {}) },
    }),

  /** 轻量项目状态（AI 任务轮询用，不含大文本字段）。 */
  getProjectStatus: async (id: number): Promise<{ id: number; status: string; ai_pending: string | null; ai_error: string | null; updated_at: string | null }> =>
    request(`/topic-projects/${id}/status`),

  /** 按选题标题 embedding 召回 Top-10 相似论文进文献集（去重），返回新增数量。 */
  recallProjectPapers: async (id: number): Promise<{ recalled: number }> =>
    request(`/topic-projects/${id}/recall-papers`, { method: 'POST' }),

  // —— 统一 AI 操作（后台任务，轮询项目详情等待完成）——
  aiAction: async (id: number, action: string, ideaText?: string, model?: string): Promise<{ status: string; action: string }> =>
    request(`/topic-projects/${id}/ai`, {
      method: 'POST',
      body: { action, ...(ideaText ? { idea_text: ideaText } : {}), ...(model ? { model } : {}) },
    }),

  /** 立项书（结果存回项目 proposal）。 */
  generateProposal: async (id: number, validationReport?: string): Promise<{ proposal: string; model: string }> =>
    request(`/topic-projects/${id}/proposal`, {
      method: 'POST',
      body: { ...(validationReport ? { validation_report: validationReport } : {}) },
    }),

  /** 期刊适配（结果存回项目 journal_advice）。 */
  suggestJournal: async (id: number): Promise<{ recommendations: string; suggestions: Array<{ journal: string; reason: string }>; ai_used: boolean }> =>
    request(`/topic-projects/${id}/journal`, { method: 'POST' }),

  /** 个性化选题灵感推荐（基于关注/阅读/空白，结果缓存 10 分钟）。 */
  recommendTopics: async (): Promise<{ recommendations: Array<{ title: string; why: string; angle?: string }>; cached: boolean }> =>
    request('/topic-projects/recommend', { method: 'POST' }),
};

/** 选题灵感向导：一句话想法 + 偏好 → AI 候选选题（后台任务 + 轮询，避开代理 30s 超时）。 */
export const topicIdeasApi = {
  /** 提交生成任务，立即返回 task_id（生成耗时可能 1 分钟+）。 */
  generate: async (payload: TopicIdeaGenerateRequest): Promise<{ task_id: string; status: string }> =>
    request('/topic-ideas/generate', { method: 'POST', body: payload }),

  /** 轮询任务结果：pending → 继续等；done → 返回候选；error → 携带原因。 */
  getGenerateResult: async (taskId: string): Promise<{ status: string; round?: number; candidates?: TopicIdeaCandidate[]; error?: string }> =>
    request(`/topic-ideas/generate/${taskId}`),
};

/** 选题验证器（SSE 流式，带 token）。projectId：服务端流结束后直接落库评分/报告/状态。 */
export function streamValidateTopic(
  topic: string,
  model: string | undefined,
  cb: ChatStreamCallbacks,
  signal?: AbortSignal,
  projectId?: number,
  useTools?: boolean,
): Promise<void> {
  const extra: Record<string, unknown> = { topic };
  if (projectId) extra.project_id = projectId;
  if (useTools !== undefined) extra.use_tools = useTools;
  return streamChat('/topic-validator/validate', [{ role: 'user', content: topic }], model, cb, signal, extra);
}

/**
 * 选题评估辩论（SSE 流式）：正方/反方各 roundsPerSide 轮 + 评审裁决。
 * projectId 可选：提供时裁决分数（novelty/crowding/feasibility/gate）由服务端落库。
 * models 可选：按角色指定模型（键 pro/con/judge，值 'provider/model'），缺省角色跟随全局默认。
 * SSE 帧约定：{"round": "pro_1|...|judge", "model": "provider/bare"} 开新轮次并标注模型；
 * {"debate_scores": {...}} 裁决分数（先于 done 帧）；content 为当前轮次正文增量。
 */
export function streamDebateTopic(
  topic: string,
  projectId: number | undefined,
  cb: ChatStreamCallbacks,
  signal?: AbortSignal,
  roundsPerSide?: number,
  models?: Record<string, string>,
): Promise<void> {
  const extra: Record<string, unknown> = { topic };
  if (projectId) extra.project_id = projectId;
  if (roundsPerSide) extra.rounds_per_side = roundsPerSide;
  if (models && Object.keys(models).length > 0) extra.models = models;
  return streamChat('/topic-validator/debate', [{ role: 'user', content: topic }], undefined, cb, signal, extra);
}

/**
 * 选题答辩（SSE 流式）：候选人自述 + 评委质询/候选人应答 N 轮 + 合议裁定。
 * projectId 可选：合议分数（validate 4 轴）由服务端落库。
 * models 可选：按角色指定（键 candidate/examiner/panel，值 'provider/model'）。
 * SSE 帧约定：{"round": "candidate_0|examiner_k|candidate_k|panel", "model": ...}；
 * {"defense_scores": {...4轴 + verdict}} 合议分数（先于 done）；content 为当前环节正文增量。
 */
export function streamDefenseTopic(
  topic: string,
  projectId: number | undefined,
  cb: ChatStreamCallbacks,
  signal?: AbortSignal,
  roundsPerSide?: number,
  models?: Record<string, string>,
): Promise<void> {
  const extra: Record<string, unknown> = { topic };
  if (projectId) extra.project_id = projectId;
  if (roundsPerSide) extra.rounds_per_side = roundsPerSide;
  if (models && Object.keys(models).length > 0) extra.models = models;
  return streamChat('/topic-validator/defense', [{ role: 'user', content: topic }], undefined, cb, signal, extra);
}

/** 选题立项书（P2-12a）：验证通过后生成一页立项书。 */
export const generateTopicProposal = async (
  topic: string,
  validationReport?: string,
): Promise<{ topic: string; proposal: string; model: string }> =>
  request('/topic-validator/proposal', {
    method: 'POST',
    body: { topic, ...(validationReport ? { validation_report: validationReport } : {}) },
  });

export { API_BASE_URL };

// —— 记住上次选择的模型（localStorage）——
const MODEL_MEM_PREFIX = 'pp_last_model:';

/** 读取某场景下上次选择的模型（'provider/model'）。 */
export function getLastModel(context: string): string | null {
  try {
    return localStorage.getItem(MODEL_MEM_PREFIX + context);
  } catch {
    return null;
  }
}

/** 记录某场景下本次选择的模型；传 null 表示清除。 */
export function rememberModel(context: string, model: string | null): void {
  try {
    if (model) {
      localStorage.setItem(MODEL_MEM_PREFIX + context, model);
    } else {
      localStorage.removeItem(MODEL_MEM_PREFIX + context);
    }
  } catch {
    /* ignore */
  }
}

// —— 统一的 SSE 流式对话封装 ——
// 原先 trends/paper 页用裸 fetch 调 /chat，既不经过 apiClient 注入 token，又各自重复解析 SSE。
// 这里收敛为单一实现，随后端 _stream_chat_response 的 SSE 数据格式对齐：
//   data: {"content": "..."} | {"reasoning": "..."} | {"tool_progress": {...}} | {"tools": [...]} | {"done": true}
export interface ChatStreamCallbacks {
  onContent: (text: string) => void;        // 累积全文内容
  onReasoning?: (text: string) => void;     // 累积思考内容（可选，调用方不关心思考时可不传）
  onDone: (fullContent: string) => void;    // 流结束，传完整正文
  onError: (message: string) => void;
  onToolProgress?: (data: { tool: string; args?: Record<string, unknown> }) => void;  // 可选：Agent 正在调用工具
  onTools?: (tools: Array<{ tool: string; args?: Record<string, unknown>; papers?: Array<Record<string, unknown>> }>) => void; // 可选：Agent 工具轨迹（结束后）
  onMeta?: (data: Record<string, unknown>) => void;  // 可选：非 content/reasoning/done 的结构化 SSE 载荷
}

/** 通过 fetch + 手动读流发起对话，注入与 apiClient 相同的 x-api-token（保持鉴权一致）。 */
export async function streamChat(
  url: string,
  messages: Array<{ role: string; content: string }>,
  model: string | undefined,
  cb: ChatStreamCallbacks,
  signal?: AbortSignal,
  extraBody?: Record<string, unknown>,
): Promise<void> {
  const headers = buildHeaders();

  let response: Response;
  try {
    const body = extraBody ? { ...extraBody, messages } : { messages, ...(model ? { model } : {}) };
    response = await fetch(`${API_BASE_URL}${url}`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal,
    });
  } catch (e: any) {
    if (e.name === 'AbortError') return;
    cb.onError(String(e?.message || 'Request failed'));
    return;
  }

  if (!response.ok) {
    // 后端可能返回字符串 detail，也可能是 pydantic 校验错误对象数组（{type,loc,msg,input}）
    // 一律安全转成可展示字符串，避免把对象注入 React child 触发渲染崩溃
    const err = await response.json().catch(() => ({ detail: 'Request failed' }));
    const rawDetail = err.detail || 'Request failed';
    let message: string;
    if (typeof rawDetail === 'string') {
      message = rawDetail;
    } else if (Array.isArray(rawDetail)) {
      message = rawDetail
        .map((e: any) => `${e?.loc?.join('.') ?? ''}: ${e?.msg ?? String(e)}`)
        .filter(Boolean)
        .join('; ');
    } else {
      message = JSON.stringify(rawDetail);
    }
    cb.onError(message);
    return;
  }

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let fullContent = '';
  let fullReasoning = '';
  let done = false;

  try {
    while (!done) {
      const { done: readerDone, value } = await reader.read();
      if (readerDone) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const data = JSON.parse(line.slice(6));
          if (data.error) {
            // 后端错误帧（{error: msg}）：以错误终止，不再渲染为正文
            cb.onError(String(data.error));
            done = true;
            break;
          } else if (data.done) {
            done = true;
            // 流式调试：done 到达时的累计量
            if (typeof console !== 'undefined') {
              console.debug('[stream:done]', JSON.stringify({ contentChars: fullContent.length, reasoningChars: fullReasoning.length }));
            }
            cb.onDone(fullContent);
            break;
          } else if (data.reasoning) {
            fullReasoning += data.reasoning;
            if (typeof console !== 'undefined') {
              console.debug('[stream:reasoning]', fullReasoning.length);
            }
            if (cb.onReasoning) cb.onReasoning(fullReasoning);
          } else if (data.content) {
            fullContent += data.content;
            if (typeof console !== 'undefined') {
              console.debug('[stream:content]', fullContent.length);
            }
            cb.onContent(fullContent);
          } else if (data.tool_progress && cb.onToolProgress) {
            // Agent 工具调用进度：前端显示"正在调用…"提示
            cb.onToolProgress(data.tool_progress);
          } else if (data.tools && cb.onTools) {
            // Agent 工具轨迹（流结束后的汇总）：前端渲染"AI 工作流"面板
            cb.onTools(data.tools);
          } else if (cb.onMeta) {
            // 结构化元消息（如验证器的 papers 召回载荷）原样交回调处理
            cb.onMeta(data);
          }
        } catch {
          /* 忽略单条解析失败 */
        }
      }
    }
    if (!done) cb.onDone(fullContent);
  } catch (e: any) {
    if (e.name !== 'AbortError') cb.onError(e.message || 'Stream read failed');
  }
}

/** 趋势报告选题对话（SSE 流式，带 token）。 */
export function streamTrendChat(
  reportId: number,
  messages: Array<{ role: string; content: string }>,
  model: string | undefined,
  cb: ChatStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  return streamChat(`/ai-analysis/reports/${reportId}/chat`, messages, model, cb, signal);
}

// —— 全局 AI 悬浮助手（会话管理 + 历史记录）——
export interface AssistantSession {
  id: number;
  title: string | null;
  page: string;
  paper_id: string | null;
  created_at: string | null;
  updated_at: string | null;
  message_count: number;
}

export interface AssistantSessionDetail extends AssistantSession {
  messages: Array<{ role: string; content: string; reasoning?: string | null }>;
}

export const assistantApi = {
  createSession: async (page: string, opts?: { paper_id?: string; context_text?: string }): Promise<AssistantSession> =>
    request('/assistant/sessions', {
      method: 'POST',
      body: {
        page,
        ...(opts?.paper_id ? { paper_id: opts.paper_id } : {}),
        ...(opts?.context_text ? { context_text: opts.context_text } : {}),
      },
    }),
  listSessions: async (limit = 50): Promise<AssistantSession[]> =>
    request('/assistant/sessions', { params: { limit } }),
  getSession: async (id: number): Promise<AssistantSessionDetail> =>
    request(`/assistant/sessions/${id}`),
  deleteSession: async (id: number): Promise<{ ok: boolean }> =>
    request(`/assistant/sessions/${id}`, { method: 'DELETE' }),
  saveMessages: async (id: number, messages: Array<{ role: string; content: string; reasoning?: string | null }>): Promise<{ ok: boolean }> =>
    request(`/assistant/sessions/${id}/messages`, { method: 'POST', body: { messages } }),
  submitFeedback: async (data: { surface?: string; ref_id?: string; content_hash?: string; rating: 1 | -1; model?: string }): Promise<{ status: string }> =>
    request('/ai/feedback', { method: 'POST', body: data }),
};


// —— 用户行为埋点 ——

export interface TrackEvent {
  event_type: 'impression' | 'click' | 'favorite' | 'unfavorite';
  surface: string;
  ref_id?: string;
  meta?: Record<string, unknown>;
}

export interface AnalyticsData {
  period_days: number;
  event_counts: Record<string, number>;
  funnel: { impressions: number; clicks: number; favorites: number; ctr: number; fav_rate: number };
  daily: Record<string, Record<string, number>>;
  top_clicked: Array<{ paper_id: string; clicks: number }>;
}

export const trackingApi = {
  trackEvent: async (event: TrackEvent): Promise<{ ok: boolean }> =>
    request('/tracking/event', { method: 'POST', body: event }),

  trackEvents: async (events: TrackEvent[]): Promise<{ ok: boolean; count: number }> =>
    request('/tracking/events', { method: 'POST', body: { events } }),

  getAnalytics: async (days = 7, surface?: string): Promise<AnalyticsData> =>
    request('/tracking/analytics', { params: { days, ...(surface ? { surface } : {}) } }),
};