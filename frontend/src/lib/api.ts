import axios from 'axios';
import { PaperListResponse, TrendingTopicsResponse, PaperDetailResponse } from '@/types/paper';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 添加请求拦截器，禁用缓存
apiClient.interceptors.request.use((config) => {
  // 添加时间戳参数，防止浏览器缓存
  if (config.params) {
    config.params._t = Date.now();
  } else {
    config.params = { _t: Date.now() };
  }
  // 添加禁用缓存的请求头
  config.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate';
  config.headers['Pragma'] = 'no-cache';
  config.headers['Expires'] = '0';
  return config;
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
  }): Promise<PaperListResponse> => {
    const response = await apiClient.get<PaperListResponse>('/papers', { params });
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

  getFilterStatistics: async (): Promise<FilterStatistics> => {
    const response = await apiClient.get<FilterStatistics>('/filter-statistics');
    return response.data;
  },
};
