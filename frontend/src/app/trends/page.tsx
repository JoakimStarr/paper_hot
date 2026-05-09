'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import Layout from '@/components/Layout';
import TrendChart from '@/components/TrendChart';
import { papersApi } from '@/lib/api';
import { TrendingTopic, AIAnalysisReport, StructuredAnalysisItem } from '@/types/paper';
import { Loader2, Sparkles, RefreshCw, History, Clock, AlertCircle, ChevronDown, ChevronUp, Brain } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

const POLL_INTERVAL_MS = 3000;
const DEBOUNCE_SECONDS = 60;

export default function TrendsPage() {
  const { t } = useLanguage();
  const [topics, setTopics] = useState<TrendingTopic[]>([]);
  const [loading, setLoading] = useState(true);

  const [report, setReport] = useState<AIAnalysisReport | null>(null);
  const [hasHistory, setHasHistory] = useState(false);
  const [isRunning, setIsRunning] = useState(false);
  const [runningReportId, setRunningReportId] = useState<number | null>(null);

  const [analysisStarted, setAnalysisStarted] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(0);
  const [showRawAnalysis, setShowRawAnalysis] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const cooldownRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isRunningRef = useRef(false);

  const startPolling = useCallback(() => {
    if (pollRef.current) return;

    pollRef.current = setInterval(async () => {
      try {
        const status = await papersApi.getAIAnalysisV2();
        if (!status.is_running) {
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
          isRunningRef.current = false;
          setIsRunning(false);
          setRunningReportId(null);
          if (status.report) {
            setReport(status.report);
            setHasHistory(true);
          } else {
            setAiError('分析未返回有效结果');
          }
          setAnalysisStarted(false);
        } else {
          isRunningRef.current = true;
          setRunningReportId(status.running_report_id);
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    }, POLL_INTERVAL_MS);
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    isRunningRef.current = false;
    setIsRunning(false);
  }, []);

  useEffect(() => {
    fetchTrends();
    checkStatus();
    return () => {
      stopPolling();
      if (cooldownRef.current) clearInterval(cooldownRef.current);
    };
  }, []);

  useEffect(() => {
    if (cooldown > 0) {
      cooldownRef.current = setInterval(() => {
        setCooldown((prev) => {
          if (prev <= 1) {
            if (cooldownRef.current) clearInterval(cooldownRef.current);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);
    }
    return () => {
      if (cooldownRef.current) clearInterval(cooldownRef.current);
    };
  }, [cooldown]);

  const fetchTrends = async () => {
    try {
      const response = await papersApi.getTrendingTopics(4);
      setTopics(response.topics);
    } catch (error) {
      console.error('Error fetching trends:', error);
    } finally {
      setLoading(false);
    }
  };

  const checkStatus = async () => {
    try {
      const status = await papersApi.getAIAnalysisV2();
      if (status.is_running) {
        isRunningRef.current = true;
        setIsRunning(true);
        setRunningReportId(status.running_report_id);
        startPolling();
      } else {
        setReport(status.report);
        setHasHistory(status.has_history);
      }
    } catch (error) {
      console.error('Error checking analysis status:', error);
    }
  };

  const startAnalysis = useCallback(async () => {
    if (cooldown > 0 || isRunningRef.current) return;

    setAiError(null);
    setAnalysisStarted(true);

    try {
      const response = await papersApi.startAIAnalysis();
      if (response.is_running) {
        isRunningRef.current = true;
        setIsRunning(true);
        setRunningReportId(response.running_report_id);
        startPolling();
      }
    } catch (error: any) {
      setAnalysisStarted(false);
      console.error('Error starting AI analysis:', error);
      const errMsg = error.response?.data?.detail || 'AI分析服务暂时不可用';
      setAiError(errMsg);
    }
  }, [cooldown, startPolling]);

  const getDirectionColor = (direction?: string) => {
    switch (direction) {
      case 'up': return 'text-green-600 bg-green-50 border-green-200';
      case 'down': return 'text-red-600 bg-red-50 border-red-200';
      case 'stable': return 'text-yellow-600 bg-yellow-50 border-yellow-200';
      default: return 'text-gray-600 bg-gray-50 border-gray-200';
    }
  };

  const getDirectionLabel = (direction?: string) => {
    switch (direction) {
      case 'up': return '上升';
      case 'down': return '下降';
      case 'stable': return '稳定';
      default: return '未知';
    }
  };

  const getOpportunityColor = (level?: string) => {
    switch (level) {
      case 'high': return 'bg-green-100 text-green-700 border-green-300';
      case 'medium': return 'bg-yellow-100 text-yellow-700 border-yellow-300';
      case 'low': return 'bg-gray-100 text-gray-600 border-gray-300';
      default: return 'bg-blue-100 text-blue-700 border-blue-300';
    }
  };

  const formatTimeAgo = (dateStr: string) => {
    const now = new Date();
    const date = new Date(dateStr);
    const diffMs = now.getTime() - date.getTime();
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffMinutes = Math.floor(diffMs / (1000 * 60));

    if (diffHours > 24) {
      return `${Math.floor(diffHours / 24)}天前`;
    } else if (diffHours > 0) {
      return `${diffHours}小时前`;
    } else {
      return `${diffMinutes}分钟前`;
    }
  };

  const renderSection = (title: string, icon: string, items: StructuredAnalysisItem[] | null | undefined, renderItem: (item: StructuredAnalysisItem, index: number) => React.ReactNode) => {
    if (!items || items.length === 0) return null;
    return (
      <div className="mb-8">
        <h3 className="text-lg font-semibold text-gray-900 mb-4 flex items-center gap-2">
          <span className="text-xl">{icon}</span>
          {title}
        </h3>
        <div className="space-y-3">
          {items.map((item, index) => renderItem(item, index))}
        </div>
      </div>
    );
  };

  const renderRunningState = () => (
    <div className="bg-gradient-to-r from-purple-50 to-blue-50 rounded-lg p-8">
      <div className="flex flex-col items-center justify-center">
        <div className="relative mb-6">
          <Brain className="w-16 h-16 text-purple-400 animate-pulse" />
          <Loader2 className="w-6 h-6 absolute -bottom-1 -right-1 animate-spin text-purple-600" />
        </div>
        <p className="text-gray-700 text-lg font-medium">AI正在分析论文数据...</p>
        <p className="text-gray-500 text-sm mt-2">正在分析 {topics.length} 个热点主题的相关论文</p>
        <div className="flex items-center gap-2 mt-4">
          <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '0s' }} />
          <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '0.15s' }} />
          <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '0.3s' }} />
        </div>
        <p className="text-gray-400 text-xs mt-4">刷新页面或切换页面后，分析状态将持续保留</p>
      </div>
    </div>
  );

  return (
    <Layout>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">
          {t('trends.title')}
        </h1>
        <p className="text-gray-600">
          {t('trends.subtitle')}
        </p>
      </div>

      {loading ? (
        <div className="flex justify-center items-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
        </div>
      ) : (
        <>
          <TrendChart topics={topics} />

          <div className="mt-8 bg-white rounded-lg shadow-md p-6">
            <div className="flex items-center justify-between mb-6">
              <div className="flex items-center gap-2">
                <Sparkles className="w-6 h-6 text-purple-600" />
                <h2 className="text-xl font-semibold text-gray-900">AI 趋势分析</h2>
                {hasHistory && report && !isRunning && (
                  <span className="flex items-center gap-1 px-2 py-0.5 bg-gray-100 text-gray-500 text-xs rounded-full">
                    <Clock className="w-3 h-3" />
                    {formatTimeAgo(report.created_at)}
                  </span>
                )}
                {isRunning && (
                  <span className="flex items-center gap-1 px-2 py-0.5 bg-purple-100 text-purple-600 text-xs rounded-full animate-pulse">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    分析中
                  </span>
                )}
              </div>
              <button
                onClick={startAnalysis}
                disabled={isRunning || cooldown > 0}
                className="flex items-center gap-2 px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {isRunning ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    分析中...
                  </>
                ) : cooldown > 0 ? (
                  <>
                    <RefreshCw className="w-4 h-4" />
                    {cooldown}秒后重试
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" />
                    {hasHistory ? '重新分析' : '开始分析'}
                  </>
                )}
              </button>
            </div>

            {isRunning ? (
              renderRunningState()
            ) : aiError && !report ? (
              <div className="bg-red-50 border border-red-200 rounded-lg p-6">
                <div className="flex items-center gap-2 text-red-600 mb-2">
                  <AlertCircle className="w-5 h-5" />
                  <span className="font-medium">分析失败</span>
                </div>
                <p className="text-red-600">{aiError}</p>
                <p className="text-red-500 text-sm mt-2">请检查Zhipu API Key配置或稍后重试</p>
              </div>
            ) : report ? (
              <div className="space-y-6">
                {report.summary && (
                  <div className="bg-gradient-to-r from-purple-50 to-blue-50 rounded-lg p-6">
                    <p className="text-gray-700 text-lg leading-relaxed">{report.summary}</p>
                  </div>
                )}

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-gray-50 rounded-lg p-4 text-center">
                    <div className="text-2xl font-bold text-purple-600">{report.total_papers}</div>
                    <div className="text-sm text-gray-500">分析论文数</div>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-4 text-center">
                    <div className="text-2xl font-bold text-blue-600">{report.model || '-'}</div>
                    <div className="text-sm text-gray-500">使用模型</div>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-4 text-center">
                    <div className="text-2xl font-bold text-green-600">{report.tokens_used}</div>
                    <div className="text-sm text-gray-500">Token消耗</div>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-4 text-center">
                    <div className="text-2xl font-bold text-orange-600">{report.processing_time_ms > 1000 ? `${(report.processing_time_ms / 1000).toFixed(1)}s` : `${report.processing_time_ms}ms`}</div>
                    <div className="text-sm text-gray-500">处理时长</div>
                  </div>
                </div>

                {renderSection('研究热点', '🔥', report.hot_topics, (item, i) => (
                  <div key={i} className="border border-purple-100 rounded-lg p-4 bg-white hover:shadow-sm transition-shadow">
                    <div className="flex items-start gap-3">
                      <span className="w-7 h-7 rounded-full bg-purple-100 text-purple-700 flex items-center justify-center text-sm font-bold shrink-0 mt-0.5">
                        {i + 1}
                      </span>
                      <div className="flex-1">
                        <h4 className="font-semibold text-gray-900 text-base">{item.topic}</h4>
                        <p className="text-gray-600 text-sm mt-1">{item.description}</p>
                        {item.related_keywords && item.related_keywords.length > 0 && (
                          <div className="flex flex-wrap gap-1.5 mt-2">
                            {item.related_keywords.map((kw, ki) => (
                              <span key={ki} className="px-2 py-0.5 bg-purple-50 text-purple-600 text-xs rounded-full border border-purple-100">
                                {kw}
                              </span>
                            ))}
                          </div>
                        )}
                        {item.significance && (
                          <p className="text-gray-500 text-xs mt-2 italic">{item.significance}</p>
                        )}
                      </div>
                    </div>
                  </div>
                ))}

                {renderSection('发展趋势', '📈', report.development_trends, (item, i) => (
                  <div key={i} className="border border-blue-100 rounded-lg p-4 bg-white">
                    <div className="flex items-center gap-3 mb-2">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium border ${getDirectionColor(item.direction)}`}>
                        {getDirectionLabel(item.direction)}
                      </span>
                      <h4 className="font-semibold text-gray-900">{item.trend}</h4>
                    </div>
                    <p className="text-gray-600 text-sm">{item.description}</p>
                    {item.evidence && (
                      <p className="text-gray-400 text-xs mt-1">依据: {item.evidence}</p>
                    )}
                  </div>
                ))}

                {renderSection('关键词聚类分析', '🔍', report.keyword_insights, (item, i) => (
                  <div key={i} className="border border-green-100 rounded-lg p-4 bg-white">
                    <h4 className="font-semibold text-gray-900 mb-2">{item.cluster}</h4>
                    {item.keywords && item.keywords.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mb-2">
                        {item.keywords.map((kw, ki) => (
                          <span key={ki} className="px-2 py-0.5 bg-green-50 text-green-600 text-xs rounded-full border border-green-100">
                            {kw}
                          </span>
                        ))}
                      </div>
                    )}
                    <p className="text-gray-600 text-sm">{item.insight}</p>
                  </div>
                ))}

                {renderSection('期刊分析', '📰', report.journal_insights, (item, i) => (
                  <div key={i} className="border border-yellow-100 rounded-lg p-4 bg-white">
                    <h4 className="font-semibold text-gray-900">{item.journal}</h4>
                    <p className="text-gray-600 text-sm mt-1">
                      <span className="font-medium text-gray-700">研究偏好: </span>
                      {item.focus}
                    </p>
                    {item.suggestion && (
                      <p className="text-gray-500 text-sm mt-1">
                        <span className="font-medium text-gray-600">建议: </span>
                        {item.suggestion}
                      </p>
                    )}
                  </div>
                ))}

                {renderSection('研究建议', '💡', report.recommendations, (item, i) => (
                  <div key={i} className="border border-orange-100 rounded-lg p-4 bg-white">
                    <div className="flex items-center gap-3 mb-2">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium border ${getOpportunityColor(item.opportunity_level)}`}>
                        {item.opportunity_level === 'high' ? '高机遇' : item.opportunity_level === 'medium' ? '中等' : '一般'}
                      </span>
                      <h4 className="font-semibold text-gray-900">{item.area}</h4>
                    </div>
                    <p className="text-gray-600 text-sm">{item.description}</p>
                  </div>
                ))}

                <div className="border-t border-gray-100 pt-4">
                  <button
                    onClick={() => setShowRawAnalysis(!showRawAnalysis)}
                    className="flex items-center gap-2 text-sm text-gray-500 hover:text-gray-700 transition-colors"
                  >
                    {showRawAnalysis ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    {showRawAnalysis ? '收起原始分析报告' : '查看原始分析报告'}
                  </button>
                  {showRawAnalysis && report.raw_analysis && (
                    <div className="mt-4 p-4 bg-gray-50 rounded-lg border border-gray-200 prose prose-sm max-w-none">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {report.raw_analysis}
                      </ReactMarkdown>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="bg-gradient-to-r from-purple-50 to-blue-50 rounded-lg p-8">
                <div className="flex flex-col items-center justify-center">
                  <History className="w-16 h-16 text-purple-300 mb-4" />
                  <p className="text-gray-600 text-lg font-medium">暂无AI分析记录</p>
                  <p className="text-gray-400 text-sm mt-1">点击上方「开始分析」按钮，AI将分析整个数据库的论文趋势</p>
                </div>
              </div>
            )}

            <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="border border-gray-200 rounded-lg p-4 hover:border-purple-200 transition-colors">
                <h3 className="font-medium text-gray-900 mb-2">🔥 热点预测</h3>
                <p className="text-sm text-gray-500">基于历史数据预测未来研究热点</p>
              </div>
              <div className="border border-gray-200 rounded-lg p-4 hover:border-purple-200 transition-colors">
                <h3 className="font-medium text-gray-900 mb-2">🔍 关键词关联</h3>
                <p className="text-sm text-gray-500">分析关键词之间的关联关系</p>
              </div>
              <div className="border border-gray-200 rounded-lg p-4 hover:border-purple-200 transition-colors">
                <h3 className="font-medium text-gray-900 mb-2">📈 发展趋势</h3>
                <p className="text-sm text-gray-500">生成详细的研究趋势报告</p>
              </div>
            </div>
          </div>
        </>
      )}
    </Layout>
  );
}