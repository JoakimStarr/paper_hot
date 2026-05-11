import axios from 'axios';
import { PaperListResponse, PaperCardListResponse, PaperCard, TrendingTopicsResponse, PaperDetailResponse, AIAnalysisResponse, AIAnalysisResponseV2, AIAnalysisReport, SystemStats, NetworkData, CrawlLog, SettingsInfo, SchedulerJob, MaintenanceResult } from '@/types/paper';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export interface FilterStatistics {
  discipline_counts: Record<string, number>;
  subfield_counts: Record<string, number>;
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

  getAIAnalysis: async (): Promise<AIAnalysisResponse> => {
    const response = await apiClient.get<AIAnalysisResponse>('/ai-analysis');
    return response.data;
  },

  getAIAnalysisV2: async (): Promise<AIAnalysisResponseV2> => {
    const response = await apiClient.get<AIAnalysisResponseV2>('/ai-analysis/v2');
    return response.data;
  },

  startAIAnalysis: async (): Promise<AIAnalysisResponseV2> => {
    const response = await apiClient.post<AIAnalysisResponseV2>('/ai-analysis/v2/analyze');
    return response.data;
  },

  getAIAnalysisReports: async (page: number = 1, limit: number = 10): Promise<{ reports: AIAnalysisReport[]; total: number }> => {
    const response = await apiClient.get<{ reports: AIAnalysisReport[]; total: number }>('/ai-analysis/reports', {
      params: { page, limit },
    });
    return response.data;
  },

  getAIAnalysisReportById: async (reportId: number): Promise<AIAnalysisReport> => {
    const response = await apiClient.get<AIAnalysisReport>(`/ai-analysis/reports/${reportId}`);
    return response.data;
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

  startCrawl: async (journalNames?: string[]): Promise<{ crawl_log_id: number; status: string; message: string }> => {
    const response = await apiClient.post('/crawl/start', { journal_names: journalNames || null });
    return response.data;
  },

  analyzePaper: async (paperId: string): Promise<{ analysis: string | null; status: string }> => {
    const response = await apiClient.post<{ analysis: string | null; status: string }>(`/papers/${paperId}/analyze`);
    return response.data;
  },

  getLatestAnalysis: async (paperId: string): Promise<{ analysis: string | null; status: string | null; model?: string; created_at?: string }> => {
    const response = await apiClient.get(`/papers/${paperId}/analyses/latest`);
    return response.data;
  },

  getPaperAnalyses: async (paperId: string): Promise<Array<{ id: number; analysis: string; model: string; created_at: string }>> => {
    const response = await apiClient.get(`/papers/${paperId}/analyses`);
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

  updateSettings: async (data: { api_keys?: Record<string, string>; model_priority?: string[] }): Promise<{ success: boolean }> => {
    const response = await apiClient.put<{ success: boolean }>('/settings', data);
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
