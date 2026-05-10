import axios from 'axios';
import { PaperListResponse, PaperCardListResponse, TrendingTopicsResponse, PaperDetailResponse, AIAnalysisResponse, AIAnalysisResponseV2, AIAnalysisReport, SystemStats, NetworkData, CrawlLog } from '@/types/paper';

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

  analyzePaper: async (paperId: string): Promise<{ analysis: string }> => {
    const response = await apiClient.post<{ analysis: string }>(`/papers/${paperId}/analyze`);
    return response.data;
  },

  getLatestAnalysis: async (paperId: string): Promise<{ analysis: string | null; model?: string; created_at?: string }> => {
    const response = await apiClient.get(`/papers/${paperId}/analyses/latest`);
    return response.data;
  },

  getPaperAnalyses: async (paperId: string): Promise<Array<{ id: number; analysis: string; model: string; created_at: string }>> => {
    const response = await apiClient.get(`/papers/${paperId}/analyses`);
    return response.data;
  },
};

export { API_BASE_URL };
