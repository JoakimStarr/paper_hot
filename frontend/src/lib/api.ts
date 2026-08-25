import { PaperListResponse, PaperCardListResponse, PaperCard, TrendingTopicsResponse, PaperDetailResponse, AIAnalysisResponseV2, AIAnalysisReport, SystemStats, NetworkData, CrawlLog, SettingsInfo, SchedulerJob, MaintenanceResult, ModelLinkTestResult, ResearchGapsResponse, GapAnalysisResponse, ValidatorStatus, TopicProject, TopicProjectPayload } from '@/types/paper';

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

async function request<T>(
  url: string,
  options?: { method?: string; params?: Record<string, unknown>; body?: unknown },
): Promise<T> {
  const method = options?.method || 'GET';
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (API_TOKEN) headers['x-api-token'] = API_TOKEN;

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
      });
    } catch (e: any) {
      // 网络层失败（代理/后端不可达），幂等请求重试，AbortError 不重试
      if (attempt < maxRetries && (!e || e?.name !== 'AbortError')) {
        await new Promise(r => setTimeout(r, RETRY_DELAYS[attempt]));
        continue;
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
      throw new Error(err?.detail || `Request failed: ${res.status}`);
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

  getAuthorNetwork: async (limit: number = 50): Promise<NetworkData> =>
    request('/network/authors', { params: { limit } }),

  getKeywordNetwork: async (limit: number = 200): Promise<NetworkData> =>
    request('/network/keywords', { params: { limit } }),

  getCrawlStatus: async (limit: number = 10): Promise<{ logs: CrawlLog[]; total: number }> =>
    request('/crawl/status', { params: { limit } }),

  startCrawl: async (journalNames?: string[]): Promise<{ crawl_log_id: string; status: string; message: string }> =>
    request('/crawl/start', { method: 'POST', body: { journal_names: journalNames || null } }),

  startCNKITop50Crawl: async (opts?: { journal_names?: string[]; max_results_per_journal?: number; max_journals?: number }): Promise<{ status: string; message: string }> =>
    request('/crawl/cnki/top50/start', { method: 'POST', body: opts || {} }),

  startCNKNaviCrawl: async (): Promise<{ status: string; message: string }> =>
    request('/crawl/cnki/navi/start', { method: 'POST', body: {} }),

  analyzePaper: async (paperId: string, model?: string): Promise<{ analysis: string | null; status: string; model?: string }> =>
    request(`/papers/${paperId}/analyze`, { method: 'POST', body: model ? { model } : {} }),

  getLatestAnalysis: async (paperId: string): Promise<{ analysis: string | null; status: string | null; model?: string; created_at?: string }> =>
    request(`/papers/${paperId}/analyses/latest`),

  getChats: async (paperId: string): Promise<Array<{ role: string; content: string }>> =>
    request(`/papers/${paperId}/chats`),

  saveChats: async (paperId: string, messages: Array<{ role: string; content: string }>): Promise<void> =>
    request(`/papers/${paperId}/chats`, { method: 'POST', body: { messages } }),

  getAuthorPapers: async (authorName: string, page: number = 1, pageSize: number = 20): Promise<AuthorPapersResponse> =>
    request(`/authors/${encodeURIComponent(authorName)}/papers`, { params: { page, page_size: pageSize } }),

  getSearchSuggestions: async (q: string, limit: number = 8): Promise<SearchSuggestResponse> =>
    request('/search/suggest', { params: { q, limit } }),

  getSubfieldDistribution: async (): Promise<SubfieldDistributionResponse> =>
    request('/subfield-distribution'),

  getSettings: async (): Promise<SettingsInfo> =>
    request('/settings'),

  updateSettings: async (data: { api_keys?: Record<string, string>; model_priority?: string[]; ports?: Record<string, number>; app_name?: string; default_model?: string | null; embedding_model?: string | null; custom_providers?: Array<{name: string; base_url: string; api_key: string; models: string[]}> }): Promise<{ success: boolean }> =>
    request('/settings', { method: 'PUT', body: data }),

  testModelLink: async (model: string): Promise<ModelLinkTestResult> =>
    request('/settings/test-model', { method: 'POST', body: { model } }),

  getSchedulerJobs: async (): Promise<SchedulerJob[]> =>
    request('/scheduler/jobs'),

  triggerSchedulerJob: async (jobId: string): Promise<{ success: boolean; message: string }> =>
    request(`/scheduler/trigger/${jobId}`, { method: 'POST' }),

  toggleScheduler: async (): Promise<{ running: boolean; message: string }> =>
    request('/scheduler/toggle', { method: 'POST' }),

  cleanupData: async (): Promise<MaintenanceResult> =>
    request('/maintenance/cleanup', { method: 'POST' }),
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
    payload: Partial<Pick<TopicProject, 'title' | 'status' | 'novelty' | 'crowding' | 'feasibility'>>,
  ): Promise<TopicProject> =>
    request<TopicProject>(`/topic-projects/${id}`, { method: 'PATCH', body: payload }),

  deleteTopicProject: async (id: number): Promise<void> =>
    request<void>(`/topic-projects/${id}`, { method: 'DELETE' }),
};

/** 选题验证器（SSE 流式，带 token）。 */
export function streamValidateTopic(
  topic: string,
  model: string | undefined,
  cb: ChatStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  return streamChat('/topic-validator/validate', [{ role: 'user', content: topic }], model, cb, signal, { topic });
}

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
//   data: {"content": "..."} | {"reasoning": "..."} | {"done": true}
export interface ChatStreamCallbacks {
  onContent: (text: string) => void;        // 累积全文内容
  onReasoning?: (text: string) => void;     // 累积思考内容（可选，调用方不关心思考时可不传）
  onDone: (fullContent: string) => void;    // 流结束，传完整正文
  onError: (message: string) => void;
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
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (API_TOKEN) headers['x-api-token'] = API_TOKEN;

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
          if (data.done) {
            done = true;
            cb.onDone(fullContent);
            break;
          } else if (data.reasoning) {
            fullReasoning += data.reasoning;
            if (cb.onReasoning) cb.onReasoning(fullReasoning);
          } else if (data.content) {
            fullContent += data.content;
            cb.onContent(fullContent);
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

/** 单篇论文多轮对话（SSE 流式，带 token）。 */
export function streamPaperChat(
  paperId: string,
  messages: Array<{ role: string; content: string }>,
  model: string | undefined,
  cb: ChatStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  return streamChat(`/papers/${paperId}/chat`, messages, model, cb, signal);
}