'use client';

import React, { useState, useEffect } from 'react';
import Layout from '@/components/Layout';
import { papersApi } from '@/lib/api';
import { SystemStats, CrawlLog } from '@/types/paper';
import {
  Settings, Activity, Database, BookOpen, Hash, Clock,
  Play, Loader2, CheckCircle, XCircle, RefreshCw, AlertCircle
} from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';

export default function SystemPage() {
  const { t } = useLanguage();
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [crawlLogs, setCrawlLogs] = useState<CrawlLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [crawling, setCrawling] = useState(false);
  const [message, setMessage] = useState('');

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [statsRes, crawlRes] = await Promise.all([
        papersApi.getSystemStats(),
        papersApi.getCrawlStatus(20),
      ]);
      setStats(statsRes);
      setCrawlLogs(crawlRes.logs || []);
    } catch (error) {
      console.error('Error fetching system data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleStartCrawl = async () => {
    setCrawling(true);
    setMessage('');
    try {
      const res = await papersApi.startCrawl();
      setMessage(res.message || '爬取任务已启动');
      setTimeout(fetchData, 3000);
    } catch (error: any) {
      setMessage(error.response?.data?.detail || '启动爬取失败');
    } finally {
      setCrawling(false);
    }
  };

  const formatTime = (dateStr: string | null) => {
    if (!dateStr) return '-';
    const safeStr = (/[Zz]$/.test(dateStr) || /[+\-]\d{2}:\d{2}$/.test(dateStr)) ? dateStr : dateStr + 'Z';
    return new Date(safeStr).toLocaleString('zh-CN');
  };

  const timeAgo = (dateStr: string | null) => {
    if (!dateStr) return '无记录';
    const safeStr = (/[Zz]$/.test(dateStr) || /[+\-]\d{2}:\d{2}$/.test(dateStr)) ? dateStr : dateStr + 'Z';
    const date = new Date(safeStr);
    const diff = Date.now() - date.getTime();
    const hours = Math.floor(diff / 3600000);
    const minutes = Math.floor(diff / 60000);

    if (hours >= 12) {
      return date.toLocaleString('zh-CN', {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit',
      });
    }
    if (hours >= 1) return `${hours}小时前`;
    if (minutes >= 1) return `${minutes}分钟前`;
    return '刚刚';
  };

  return (
    <Layout>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">{t('system.title')}</h1>
        <p className="text-gray-600">{t('system.subtitle')}</p>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
        </div>
      ) : (
        <>
          {stats && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
              <div className="bg-white rounded-lg shadow-sm border p-4">
                <div className="flex items-center gap-2 text-blue-600 mb-2">
                  <Database className="w-5 h-5" />
                  <span className="text-sm font-medium">论文总数</span>
                </div>
                <div className="text-2xl font-bold text-gray-900">{stats.total_papers}</div>
              </div>
              <div className="bg-white rounded-lg shadow-sm border p-4">
                <div className="flex items-center gap-2 text-green-600 mb-2">
                  <BookOpen className="w-5 h-5" />
                  <span className="text-sm font-medium">期刊数量</span>
                </div>
                <div className="text-2xl font-bold text-gray-900">{stats.journal_count}</div>
              </div>
              <div className="bg-white rounded-lg shadow-sm border p-4">
                <div className="flex items-center gap-2 text-purple-600 mb-2">
                  <Hash className="w-5 h-5" />
                  <span className="text-sm font-medium">关键词数</span>
                </div>
                <div className="text-2xl font-bold text-gray-900">{stats.keyword_count}</div>
              </div>
              <div className="bg-white rounded-lg shadow-sm border p-4">
                <div className="flex items-center gap-2 text-orange-600 mb-2">
                  <Clock className="w-5 h-5" />
                  <span className="text-sm font-medium">最近更新</span>
                </div>
                <div className="text-sm font-semibold text-gray-900">
                  {timeAgo(stats.latest_paper_at)}
                </div>
              </div>
            </div>
          )}

          {stats?.source_counts && (
            <div className="bg-white rounded-lg shadow-sm border p-6 mb-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-3 flex items-center gap-2">
                <Activity className="w-5 h-5 text-gray-500" />
                来源分布
              </h3>
              <div className="flex flex-wrap gap-2">
                {Object.entries(stats.source_counts).map(([source, count]) => (
                  <span key={source} className="px-3 py-1.5 bg-blue-50 text-blue-700 rounded-full text-sm border border-blue-100">
                    {source}: {count}篇
                  </span>
                ))}
              </div>
            </div>
          )}

          {stats?.top_journals && (
            <div className="bg-white rounded-lg shadow-sm border p-6 mb-6">
              <h3 className="text-lg font-semibold text-gray-900 mb-3 flex items-center gap-2">
                <BookOpen className="w-5 h-5 text-gray-500" />
                Top 10 期刊
              </h3>
              <div className="space-y-2">
                {Object.entries(stats.top_journals).map(([journal, count], idx) => (
                  <div key={journal} className="flex items-center justify-between bg-gray-50 rounded px-3 py-2">
                    <div className="flex items-center gap-2">
                      <span className="w-6 h-6 rounded-full bg-primary-100 text-primary-700 flex items-center justify-center text-xs font-bold">
                        {idx + 1}
                      </span>
                      <span className="text-sm text-gray-700">{journal}</span>
                    </div>
                    <span className="text-sm font-medium text-gray-500">{count}篇</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-white rounded-lg shadow-sm border p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <Settings className="w-6 h-6 text-primary-600" />
                  <h2 className="text-xl font-semibold text-gray-900">{t('system.crawlControl')}</h2>
                </div>
              </div>
              <button
                onClick={handleStartCrawl}
                disabled={crawling}
                className="flex items-center gap-2 w-full justify-center px-4 py-3 bg-primary-600 text-white rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors mb-4"
              >
                {crawling ? (
                  <><Loader2 className="w-4 h-4 animate-spin" />{t('system.crawling')}</>
                ) : (
                  <><Play className="w-4 h-4" />{t('system.startCrawl')}</>
                )}
              </button>
              {message && (
                <div className={`p-3 rounded-lg text-sm ${message.includes('失败') ? 'bg-red-50 text-red-600' : 'bg-green-50 text-green-600'}`}>
                  {message}
                </div>
              )}
              <div className="mt-4 flex items-center gap-2 text-sm text-gray-500">
                <AlertCircle className="w-4 h-4" />
                爬虫将抓取所有已配置的期刊和arXiv最新论文
              </div>
            </div>

            <div className="bg-white rounded-lg shadow-sm border p-6">
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-3">
                  <Activity className="w-6 h-6 text-primary-600" />
                  <h2 className="text-xl font-semibold text-gray-900">{t('system.crawlLogs')}</h2>
                </div>
                <button onClick={fetchData} className="p-2 hover:bg-gray-100 rounded-lg transition-colors">
                  <RefreshCw className="w-4 h-4 text-gray-500" />
                </button>
              </div>
              <div className="max-h-96 overflow-y-auto">
                {crawlLogs.length === 0 ? (
                  <div className="text-center py-8 text-gray-400">
                    暂无爬取记录
                  </div>
                ) : (
                  <div className="space-y-2">
                    {crawlLogs.map((log) => (
                      <div key={log.id} className="border border-gray-100 rounded-lg p-3">
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm font-medium text-gray-700">{log.journal_name}</span>
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                            log.status === 'success' || log.status === 'completed'
                              ? 'bg-green-100 text-green-700'
                              : log.status === 'running'
                              ? 'bg-blue-100 text-blue-700'
                              : 'bg-red-100 text-red-700'
                          }`}>
                            {log.status === 'success' || log.status === 'completed' ? (
                              <CheckCircle className="w-3 h-3" />
                            ) : log.status === 'running' ? (
                              <Loader2 className="w-3 h-3 animate-spin" />
                            ) : (
                              <XCircle className="w-3 h-3" />
                            )}
                            {log.status}
                          </span>
                        </div>
                        <div className="flex items-center gap-4 text-xs text-gray-500">
                          <span>获取: {log.papers_fetched}篇</span>
                          {log.papers_failed > 0 && <span className="text-red-500">失败: {log.papers_failed}篇</span>}
                          <span>{formatTime(log.created_at)}</span>
                        </div>
                        {log.error_message && (
                          <p className="text-xs text-red-500 mt-1 truncate">{log.error_message}</p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </Layout>
  );
}