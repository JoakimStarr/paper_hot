import axios from 'axios';
import { PaperListResponse, PaperCardListResponse, PaperCard, TrendingTopicsResponse, PaperDetailResponse, AIAnalysisResponseV2, AIAnalysisReport, SystemStats, NetworkData, CrawlLog, SettingsInfo, SchedulerJob, MaintenanceResult, ModelLinkTestResult } from '@/types/paper';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || '/api'; // 默认走同源 /api，由 next.config rewrites 代理到后端实际端口

// 可选 API Token：若后端配置了 api_token，前端需在同一处注入才能通过鉴权。
// 不配置时（NEXT_PUBLIC_API_TOKEN 为空/未设置）行为与之前一致——后端未设 token 时默认放行。
const API_TOKEN = process.env.NEXT_PUBLIC_API_TOKEN || '';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 统一注入 x-api-token：所有走 apiClient 的请求（含 /chat、/analyze、/chats 的写操作）自动携带
apiClient.interceptors.request.use((config) => {
  if (API_TOKEN) {
    config.headers = config.headers || {};
    config.headers['x-api-token'] = API_TOKEN;
  }
  return config;
});

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
  }): Promise<PaperCardListResponse> => {
    const response = await apiClient.get<PaperCardListResponse>('/papers', { params });
    return response.data;
  },

  getPaperById: async (id: string): Promise<PaperDetailResponse> => {
    const response = await apiClient.get<PaperDetailResponse>(`/papers/${id}`);
    return response.data;
  },

  getTrendingTopics: async (weeks_back?: number): Promise<TrendingTopicsResponse> => {
    const response = await apiClient.get<TrendingTopicsResponse>('/trending-topics', {
      params: { weeks_back },
    });
    return response.data;
  },

  getAIAnalysisV2: async (): Promise<AIAnalysisResponseV2> => {
    const response = await apiClient.get<AIAnalysisResponseV2>('/ai-analysis/v2');
    return response.data;
  },

  startAIAnalysis: async (model?: string): Promise<AIAnalysisResponseV2> => {
    const response = await apiClient.post<AIAnalysisResponseV2>('/ai-analysis/v2/analyze', { model });
    return response.data;
  },

  getAIAnalysisModels: async (): Promise<{ models: Array<{ name: string; available: boolean; priority: number; provider?: string }> }> => {
    const response = await apiClient.get<{ models: Array<{ name: string; available: boolean; priority: number; provider?: string }> }>('/ai-analysis/models');
    return response.data;
  },

  getAIAnalysisReports: async (limit: number = 10): Promise<{ reports: AIAnalysisReport[]; total: number }> => {
    const response = await apiClient.get<{ reports: AIAnalysisReport[]; total: number }>('/ai-analysis/reports', {
      params: { limit },
    });
    return response.data;
  },

  getAIAnalysisReportById: async (reportId: number): Promise<AIAnalysisReport> => {
    const response = await apiClient.get<AIAnalysisReport>(`/ai-analysis/reports/${reportId}`);
    return response.data;
  },

  getTrendChats: async (reportId: number): Promise<Array<{ role: string; content: string }>> => {
    const response = await apiClient.get(`/ai-analysis/reports/${reportId}/chats`);
    return response.data;
  },

  saveTrendChats: async (reportId: number, messages: Array<{ role: string; content: string }>): Promise<void> => {
    await apiClient.post(`/ai-analysis/reports/${reportId}/chats`, { messages });
  },

  clearTrendChats: async (reportId: number): Promise<void> => {
    await apiClient.delete(`/ai-analysis/reports/${reportId}/chats`);
  },

  getFilterStatistics: async (): Promise<FilterStatistics> => {
    const response = await apiClient.get<FilterStatistics>('/filter-statistics');
    return response.data;
  },

  getSystemStats: async (): Promise<SystemStats> => {
    const response = await apiClient.get<SystemStats>('/stats');
    return response.data;
  },

  getAuthorNetwork: async (limit: number = 50): Promise<NetworkData> => {
    const response = await apiClient.get<NetworkData>('/network/authors', { params: { limit } });
    return response.data;
  },

  getKeywordNetwork: async (limit: number = 200): Promise<NetworkData> => {
    const response = await apiClient.get<NetworkData>('/network/keywords', { params: { limit } });
    return response.data;
  },

  getCrawlStatus: async (limit: number = 10): Promise<{ logs: CrawlLog[]; total: number }> => {
    const response = await apiClient.get<{ logs: CrawlLog[]; total: number }>('/crawl/status', { params: { limit } });
    return response.data;
  },

  startCrawl: async (journalNames?: string[]): Promise<{ crawl_log_id: string; status: string; message: string }> => {
    const response = await apiClient.post('/crawl/start', { journal_names: journalNames || null });
    return response.data;
  },

  startCNKITop50Crawl: async (opts?: { journal_names?: string[]; max_results_per_journal?: number; max_journals?: number }): Promise<{ status: string; message: string }> => {
    const response = await apiClient.post('/crawl/cnki/top50/start', opts || {});
    return response.data;
  },

  startCNKNaviCrawl: async (): Promise<{ status: string; message: string }> => {
    const response = await apiClient.post('/crawl/cnki/navi/start', {});
    return response.data;
  },

  analyzePaper: async (paperId: string, model?: string): Promise<{ analysis: string | null; status: string; model?: string }> => {
    const response = await apiClient.post<{ analysis: string | null; status: string; model?: string }>(`/papers/${paperId}/analyze`, model ? { model } : {});
    return response.data;
  },

  getLatestAnalysis: async (paperId: string): Promise<{ analysis: string | null; status: string | null; model?: string; created_at?: string }> => {
    const response = await apiClient.get(`/papers/${paperId}/analyses/latest`);
    return response.data;
  },

  getChats: async (paperId: string): Promise<Array<{ role: string; content: string }>> => {
    const response = await apiClient.get(`/papers/${paperId}/chats`);
    return response.data;
  },

  saveChats: async (paperId: string, messages: Array<{ role: string; content: string }>): Promise<void> => {
    await apiClient.post(`/papers/${paperId}/chats`, { messages });
  },

  getAuthorPapers: async (authorName: string, page: number = 1, pageSize: number = 20): Promise<AuthorPapersResponse> => {
    const response = await apiClient.get<AuthorPapersResponse>(`/authors/${encodeURIComponent(authorName)}/papers`, {
      params: { page, page_size: pageSize },
    });
    return response.data;
  },

  getSearchSuggestions: async (q: string, limit: number = 8): Promise<SearchSuggestResponse> => {
    const response = await apiClient.get<SearchSuggestResponse>('/search/suggest', {
      params: { q, limit },
    });
    return response.data;
  },

  getSubfieldDistribution: async (): Promise<SubfieldDistributionResponse> => {
    const response = await apiClient.get<SubfieldDistributionResponse>('/subfield-distribution');
    return response.data;
  },

  getSettings: async (): Promise<SettingsInfo> => {
    const response = await apiClient.get<SettingsInfo>('/settings');
    return response.data;
  },

  updateSettings: async (data: { api_keys?: Record<string, string>; model_priority?: string[]; ports?: Record<string, number>; app_name?: string; default_model?: string | null; custom_providers?: Array<{name: string; base_url: string; api_key: string; models: string[]}> }): Promise<{ success: boolean }> => {
    const response = await apiClient.put<{ success: boolean }>('/settings', data);
    return response.data;
  },

  testModelLink: async (model: string): Promise<ModelLinkTestResult> => {
    const response = await apiClient.post<ModelLinkTestResult>('/settings/test-model', { model });
    return response.data;
  },

  getSchedulerJobs: async (): Promise<SchedulerJob[]> => {
    const response = await apiClient.get<SchedulerJob[]>('/scheduler/jobs');
    return response.data;
  },

  triggerSchedulerJob: async (jobId: string): Promise<{ success: boolean; message: string }> => {
    const response = await apiClient.post<{ success: boolean; message: string }>(`/scheduler/trigger/${jobId}`);
    return response.data;
  },

  toggleScheduler: async (): Promise<{ running: boolean; message: string }> => {
    const response = await apiClient.post<{ running: boolean; message: string }>('/scheduler/toggle');
    return response.data;
  },

  cleanupData: async (): Promise<MaintenanceResult> => {
    const response = await apiClient.post<MaintenanceResult>('/maintenance/cleanup');
    return response.data;
  },
};

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
}

/** 通过 fetch + 手动读流发起对话，注入与 apiClient 相同的 x-api-token（保持鉴权一致）。 */
export async function streamChat(
  url: string,
  messages: Array<{ role: string; content: string }>,
  model: string | undefined,
  cb: ChatStreamCallbacks,
  signal?: AbortSignal,
): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (API_TOKEN) headers['x-api-token'] = API_TOKEN;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${url}`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ messages, ...(model ? { model } : {}) }),
      signal,
    });
  } catch (e: any) {
    if (e.name === 'AbortError') return;
    cb.onError(e.message || 'Request failed');
    return;
  }

  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: 'Request failed' }));
    cb.onError(err.detail || 'Request failed');
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
