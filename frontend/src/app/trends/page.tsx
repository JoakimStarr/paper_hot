'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import Layout from '@/components/Layout';
import TrendChart from '@/components/TrendChart';
import { papersApi } from '@/lib/api';
import { API_BASE_URL } from '@/lib/api';
import { TrendingTopic, AIAnalysisReport, StructuredAnalysisItem } from '@/types/paper';
import { Loader2, Sparkles, RefreshCw, History, Clock, AlertCircle, ChevronDown, ChevronUp, Brain, Send, Bot, Trash2, Download, Settings2, Maximize2, Minimize2 } from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';
import { useTheme } from '@/contexts/ThemeContext';
import MarkdownRenderer from '@/components/MarkdownRenderer';
import { RadarChart, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Radar, ResponsiveContainer, Tooltip } from 'recharts';

const POLL_INTERVALS = [3000, 5000, 8000, 13000, 13000];
const ERROR_COOLDOWN_SECONDS = 30;
const MAX_CONTEXT_MESSAGES = 20;

type ModelOption = {
  id: string;          // 'provider/model'
  label: string;
  provider?: string;
  available: boolean;
};

const providerLabel = (provider?: string) => {
  if (provider === 'zhipu') return '智谱';
  if (provider === 'siliconflow') return '硅基流动';
  if (provider === 'openai') return 'OpenAI';
  return provider || '未知';
};

const bareModelName = (name: string) => {
  // 去掉 'provider/' 前缀，保留真实模型名（模型名本身可能含 '/'）
  const slashIndex = name.indexOf('/');
  return slashIndex >= 0 ? name.slice(slashIndex + 1) : name;
};

const COLLAPSE_STORAGE_KEY = 'trends_collapse_state';
const CHAT_FULLSCREEN_STORAGE_KEY = 'trends_chat_fullscreen';

export default function TrendsPage() {
  const { t } = useLanguage();
  const { isDark } = useTheme();
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
  const [timeRange, setTimeRange] = useState<'1m' | '3m' | '6m'>('1m');
  const [radarData, setRadarData] = useState<{ subfield: string; count: number }[]>([]);
  const [radarLoading, setRadarLoading] = useState(true);
  const [showHistory, setShowHistory] = useState(false);
  const [historyReports, setHistoryReports] = useState<AIAnalysisReport[]>([]);
  const [restoringId, setRestoringId] = useState<number | null>(null);

  const [chatMessages, setChatMessages] = useState<Array<{ role: string; content: string }>>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatStreaming, setChatStreaming] = useState(false);
  const [streamContent, setStreamContent] = useState('');
  const [streamReasoning, setStreamReasoning] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [selectedModel, setSelectedModel] = useState('');
  const [showModelSelect, setShowModelSelect] = useState(false);
  const [analysisModel, setAnalysisModel] = useState('');
  const [showAnalysisModelSelect, setShowAnalysisModelSelect] = useState(false);
  const [availableModels, setAvailableModels] = useState<ModelOption[]>([]);
  const [isAIAnalysisCollapsed, setIsAIAnalysisCollapsed] = useState(false);
  const [isTrendingTopicsCollapsed, setIsTrendingTopicsCollapsed] = useState(false);
  const [isChatFullscreen, setIsChatFullscreen] = useState(false);
  const chatEndRef = useRef<HTMLDivElement | null>(null);

  // Load collapse state from localStorage
  useEffect(() => {
    const savedState = localStorage.getItem(COLLAPSE_STORAGE_KEY);
    if (savedState) {
      try {
        const state = JSON.parse(savedState);
        setIsAIAnalysisCollapsed(state.aiAnalysis ?? false);
        setIsTrendingTopicsCollapsed(state.trendingTopics ?? false);
      } catch {}
    }
    const savedFullscreen = localStorage.getItem(CHAT_FULLSCREEN_STORAGE_KEY);
    if (savedFullscreen) {
      setIsChatFullscreen(savedFullscreen === 'true');
    }
  }, []);

  // Load available AI models for the selectors (from configured providers)
  useEffect(() => {
    papersApi.getAIAnalysisModels()
      .then(res => {
        setAvailableModels(res.models.map(m => ({
          id: m.name,
          label: `${providerLabel(m.provider)} ${bareModelName(m.name)}`,
          provider: m.provider,
          available: m.available,
        })));
      })
      .catch(() => setAvailableModels([]));
  }, []);

  // Save collapse state to localStorage
  const saveCollapseState = (aiAnalysis: boolean, trendingTopics: boolean) => {
    localStorage.setItem(COLLAPSE_STORAGE_KEY, JSON.stringify({
      aiAnalysis,
      trendingTopics,
    }));
  };

  const toggleAIAnalysis = () => {
    const newState = !isAIAnalysisCollapsed;
    setIsAIAnalysisCollapsed(newState);
    saveCollapseState(newState, isTrendingTopicsCollapsed);
  };

  const toggleTrendingTopics = () => {
    const newState = !isTrendingTopicsCollapsed;
    setIsTrendingTopicsCollapsed(newState);
    saveCollapseState(isAIAnalysisCollapsed, newState);
  };

  const toggleChatFullscreen = () => {
    const newState = !isChatFullscreen;
    setIsChatFullscreen(newState);
    localStorage.setItem(CHAT_FULLSCREEN_STORAGE_KEY, String(newState));
  };

  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const cooldownRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isRunningRef = useRef(false);
  const isMountedRef = useRef(true);
  const pollStepRef = useRef(0);

  const startPolling = useCallback(() => {
    if (pollRef.current) return;
    pollStepRef.current = 0;

    const poll = async () => {
      try {
        if (!isMountedRef.current) {
          // 组件已卸载：清掉 pollRef，避免残留的引用阻塞下一次 startPolling
          pollRef.current = null;
          return;
        }
        const status = await papersApi.getAIAnalysisV2();
        if (!status.is_running) {
          isRunningRef.current = false;
          setIsRunning(false);
          setRunningReportId(null);
          if (status.report) {
            setReport(status.report);
            setHasHistory(true);
            loadTrendChats(status.report.id);
          } else {
            setAiError(t('tr.analysisNoResult'));
          }
          setAnalysisStarted(false);
          pollRef.current = null;
          return;
        } else {
          isRunningRef.current = true;
          setRunningReportId(status.running_report_id);
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
      pollStepRef.current = Math.min(pollStepRef.current + 1, POLL_INTERVALS.length - 1);
      const nextInterval = POLL_INTERVALS[pollStepRef.current];
      pollRef.current = setTimeout(poll, nextInterval);
    };

    pollRef.current = setTimeout(poll, POLL_INTERVALS[0]);
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearTimeout(pollRef.current);
      pollRef.current = null;
    }
    isRunningRef.current = false;
    setIsRunning(false);
  }, []);

  useEffect(() => {
    // StrictMode 下 effect 会「挂载→卸载→重挂载」执行两次，重挂载时必须恢复 isMountedRef，
    // 否则轮询首轮就静默退出，分析完成后界面不会自动刷新
    isMountedRef.current = true;
    // topics 由下方 [timeRange] effect 统一拉取（含首次），这里避免重复请求
    checkStatus();
    fetchRadarData();
    return () => {
      isMountedRef.current = false;
      stopPolling();
      if (cooldownRef.current) clearInterval(cooldownRef.current);
    };
  }, []);

  useEffect(() => {
    if (cooldown > 0) {
      cooldownRef.current = setInterval(() => {
        if (!isMountedRef.current) return;
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

  useEffect(() => {
    const weeksBackMap = { '1m': 4, '3m': 12, '6m': 24 };
    papersApi.getTrendingTopics(weeksBackMap[timeRange]).then(response => {
      setTopics(response.topics);
    }).catch(error => {
      console.error('Error fetching trends:', error);
    }).finally(() => {
      setLoading(false);
    });
  }, [timeRange]);

  const fetchTrends = async () => {
    const weeksBackMap = { '1m': 4, '3m': 12, '6m': 24 };
    try {
      const response = await papersApi.getTrendingTopics(weeksBackMap[timeRange]);
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
        if (status.report) {
          loadTrendChats(status.report.id);
        }
      }
    } catch (error) {
      console.error('Error checking analysis status:', error);
    }
  };

  const fetchRadarData = async () => {
    setRadarLoading(true);
    try {
      const result = await papersApi.getSubfieldDistribution();
      setRadarData(result.distribution);
    } catch (error) {
      console.error('Error fetching radar data:', error);
    } finally {
      setRadarLoading(false);
    }
  };

  const fetchHistory = async () => {
    try {
      const result = await papersApi.getAIAnalysisReports(10);
      setHistoryReports(result.reports || []);
    } catch (error) {
      console.error('Error fetching history:', error);
    }
  };

  const restoreReport = async (reportId: number) => {
    if (isRunning) return;
    setRestoringId(reportId);
    setChatLoading(true);
    try {
      const fullReport = await papersApi.getAIAnalysisReportById(reportId);
      if (fullReport) {
        setReport(fullReport);
        setHasHistory(true);
        setShowHistory(false);
        await loadTrendChats(reportId);
      }
    } catch (error) {
      console.error('Error restoring report:', error);
    } finally {
      setRestoringId(null);
      setChatLoading(false);
    }
  };

  useEffect(() => {
    if (showHistory) {
      fetchHistory();
    }
  }, [showHistory]);

  const startAnalysis = useCallback(async () => {
    if (cooldown > 0 || isRunningRef.current) return;

    setAiError(null);
    setAnalysisStarted(true);

    try {
      const response = await papersApi.startAIAnalysis(analysisModel || undefined);
      if (response.is_running) {
        isRunningRef.current = true;
        setIsRunning(true);
        setRunningReportId(response.running_report_id);
        startPolling();
      } else if (response.report) {
        // 后端未启动新任务但返回了已有报告（如服务不可用时带出最近报告），直接展示
        setReport(response.report);
        setHasHistory(true);
        loadTrendChats(response.report.id);
        setAnalysisStarted(false);
      } else {
        setAnalysisStarted(false);
      }
    } catch (error: any) {
      setAnalysisStarted(false);
      console.error('Error starting AI analysis:', error);
      const errMsg = error.response?.data?.detail || 'AI分析服务暂时不可用';
      setAiError(errMsg);
      setCooldown(ERROR_COOLDOWN_SECONDS);
    }
  }, [cooldown, startPolling, analysisModel]);

  useEffect(() => {
    // 仅在流式回复进行中自动滚动，避免打开页面/加载历史对话就跳到底部
    if (chatStreaming) {
      chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [streamContent, streamReasoning, chatStreaming]);

  const loadTrendChats = async (reportId: number) => {
    setChatLoading(true);
    try {
      const chats = await papersApi.getTrendChats(reportId);
      if (chats.length > 0) {
        setChatMessages(chats.map(c => ({ role: c.role, content: c.content })));
      } else {
        setChatMessages([]);
      }
    } catch {
      setChatMessages([]);
    } finally {
      setChatLoading(false);
    }
  };

  const handleTrendChatSubmit = async (overrideInput?: string) => {
    const inputText = overrideInput || chatInput;
    if (!inputText.trim() || !report) return;

    const userMsg = { role: 'user', content: inputText.trim() };
    const allMessages = [...chatMessages, userMsg];
    setChatMessages(allMessages);
    setChatInput('');
    setChatStreaming(true);
    setStreamContent('');
    setStreamReasoning('');

    try {
      papersApi.saveTrendChats(report.id, [userMsg]);

      const contextMessages = allMessages.slice(-MAX_CONTEXT_MESSAGES);

      const response = await fetch(`${API_BASE_URL}/ai-analysis/reports/${report.id}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ messages: contextMessages, model: selectedModel || undefined }),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({ detail: 'Request failed' }));
        setChatMessages(m => [...m, { role: 'assistant', content: `[Error] ${err.detail}` }]);
        setChatStreaming(false);
        return;
      }

      const reader = response.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let fullContent = '';
      let fullReasoning = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.done) {
                setChatMessages(m => [...m, { role: 'assistant', content: fullContent }]);
                setStreamContent('');
                setStreamReasoning('');
                papersApi.saveTrendChats(report.id, [
                  { role: 'assistant', content: fullContent }
                ]);
              } else if (data.reasoning) {
                fullReasoning += data.reasoning;
                setStreamReasoning(fullReasoning);
              } else if (data.content) {
                fullContent += data.content;
                setStreamContent(fullContent);
              }
            } catch {}
          }
        }
      }
    } catch (e: any) {
      setChatMessages(m => [...m, { role: 'assistant', content: `[Error] ${e.message}` }]);
    } finally {
      setChatStreaming(false);
    }
  };

  const handleClearChats = async () => {
    if (!report) return;
    try {
      await papersApi.clearTrendChats(report.id);
      setChatMessages([]);
    } catch {}
  };

  const handleExportChats = () => {
    if (chatMessages.length === 0) return;
    const lines = chatMessages.map(msg => {
      const role = msg.role === 'user' ? '👤 用户' : '🤖 选题分析师';
      return `### ${role}\n\n${msg.content}\n`;
    });
    const content = `# 选题分析对话记录\n\n> 导出时间：${new Date().toLocaleString('zh-CN')}\n> 分析报告：${report?.summary || ''}\n\n---\n\n${lines.join('\n---\n\n')}`;
    const blob = new Blob([content], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `选题分析对话_${new Date().toISOString().slice(0, 10)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const getDirectionColor = (direction?: string) => {
    switch (direction) {
      case 'up': return 'text-green-600 bg-green-50 dark:bg-green-900/30 border-green-200';
      case 'down': return 'text-red-600 bg-red-50 dark:bg-red-900/30 border-red-200';
      case 'stable': return 'text-yellow-600 bg-yellow-50 dark:bg-yellow-900/30 border-yellow-200';
      default: return 'text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-700/50 border-gray-200 dark:border-gray-700';
    }
  };

  const getDirectionLabel = (direction?: string) => {
    switch (direction) {
      case 'up': return t('trends.rising');
      case 'down': return t('trends.declining');
      case 'stable': return t('trends.stable');
      default: return t('common.unknown');
    }
  };

  const getOpportunityColor = (level?: string) => {
    switch (level) {
      case 'high': return 'bg-green-100 text-green-700 border-green-300';
      case 'medium': return 'bg-yellow-100 text-yellow-700 border-yellow-300';
      case 'low': return 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 border-gray-300';
      default: return 'bg-blue-100 text-blue-700 border-blue-300';
    }
  };

  const parseDate = (dateStr: string): Date => {
    if (/[Zz]$/.test(dateStr) || /[+\-]\d{2}:\d{2}$/.test(dateStr)) {
      return new Date(dateStr);
    }
    return new Date(dateStr + 'Z');
  };

  const formatTimeAgo = (dateStr: string) => {
    const date = parseDate(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    const diffMinutes = Math.floor(diffMs / (1000 * 60));

    if (diffHours >= 12) {
      return date.toLocaleString('zh-CN', {
        year: 'numeric', month: '2-digit', day: '2-digit',
        hour: '2-digit', minute: '2-digit',
      });
    }
    if (diffHours >= 1) {
      return `${diffHours}小时前`;
    }
    if (diffMinutes >= 1) {
      return `${diffMinutes}分钟前`;
    }
    return '刚刚';
  };

  const renderSection = (title: string, icon: string, items: StructuredAnalysisItem[] | null | undefined, renderItem: (item: StructuredAnalysisItem, index: number) => React.ReactNode, sectionId?: string) => {
    if (!items || items.length === 0) return null;
    return (
      <div className="mb-8" id={sectionId}>
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center gap-2">
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
    <div className="bg-gradient-to-r from-purple-50 to-blue-50 dark:from-purple-900/30 dark:to-blue-900/30 rounded-lg p-8">
      <div className="flex flex-col items-center justify-center">
        <div className="relative mb-6">
          <Brain className="w-16 h-16 text-purple-400 animate-pulse" />
          <Loader2 className="w-6 h-6 absolute -bottom-1 -right-1 animate-spin text-purple-600" />
        </div>
        <p className="text-gray-700 dark:text-gray-300 text-lg font-medium">{t('tr.analyzingTitle')}</p>
        <p className="text-gray-500 dark:text-gray-400 text-sm mt-2">{t('tr.analyzingSub', { n: topics.length })}</p>
        <div className="flex items-center gap-2 mt-4">
          <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '0s' }} />
          <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '0.15s' }} />
          <div className="w-2 h-2 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: '0.3s' }} />
        </div>
        <p className="text-gray-400 text-xs mt-4">{t('tr.stateKeepHint')}</p>
      </div>
    </div>
  );

  return (
    <Layout>
      <div className="mb-6 sm:mb-8">
        <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white mb-2">
          {t('trends.title')}
        </h1>
        <p className="text-sm sm:text-base text-gray-600 dark:text-gray-400">
          {t('trends.subtitle')}
        </p>
      </div>

      {loading ? (
        <div className="flex justify-center items-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
        </div>
      ) : (
        <>
          <div className="flex flex-wrap gap-2 mb-4">
            {(['1m', '3m', '6m'] as const).map(range => (
              <button
                key={range}
                onClick={() => setTimeRange(range)}
                className={`px-2.5 sm:px-3 py-1.5 text-xs sm:text-sm rounded-md transition-colors ${
                  timeRange === range
                    ? 'bg-primary-600 text-white'
                    : 'bg-white dark:bg-gray-800 border border-gray-300 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:bg-gray-700/50'
                }`}
              >
                {range === '1m' ? '1个月' : range === '3m' ? '3个月' : '6个月'}
              </button>
            ))}
          </div>

          <TrendChart topics={topics} />

          {!radarLoading && radarData.length > 0 && (
            <div className="mt-6 sm:mt-8 bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 sm:p-6">
              <div className="flex items-center gap-2 mb-4">
                <span className="text-lg sm:text-xl">🎯</span>
                <h2 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-white">{t('tr.radarTitle')}</h2>
                <span className="text-xs text-gray-400 hidden sm:inline">{t('tr.radarSub')}</span>
              </div>
              <ResponsiveContainer width="100%" height={280}>
                <RadarChart data={radarData} cx="50%" cy="50%" outerRadius="70%">
                  <PolarGrid stroke={isDark ? '#4b5563' : '#e5e7eb'} />
                  <PolarAngleAxis
                    dataKey="subfield"
                    tick={{ fontSize: 10, fill: isDark ? '#d1d5db' : '#4b5563' }}
                  />
                  <PolarRadiusAxis
                    angle={30}
                    domain={[0, 'auto']}
                    tick={{ fontSize: 9, fill: '#9ca3af' }}
                  />
                  <Tooltip
                    formatter={(value: number) => [`${value}`, t('tr.radarUnit')]}
                    labelFormatter={(label: string) => `${t('tr.subfieldLabel')}: ${label}`}
                    contentStyle={isDark ? { backgroundColor: '#1f2937', border: '1px solid #374151', borderRadius: '8px', color: '#e5e7eb' } : undefined}
                  />
                  <Radar
                    name={t('tr.radarUnit')}
                    dataKey="count"
                    stroke="#7c3aed"
                    fill="#7c3aed"
                    fillOpacity={0.25}
                  />
                </RadarChart>
              </ResponsiveContainer>
            </div>
          )}

          <div className="mt-6 sm:mt-8 bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 sm:p-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-0 mb-4 sm:mb-6">
              <div className="flex items-center gap-2">
                <Sparkles className="w-5 h-5 sm:w-6 sm:h-6 text-purple-600" />
                <h2 className="text-lg sm:text-xl font-semibold text-gray-900 dark:text-white">{t('tr.aiTrend')}</h2>
                {hasHistory && report && !isRunning && (
                  <span className="flex items-center gap-1 px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 text-xs rounded-full">
                    <Clock className="w-3 h-3" />
                    {formatTimeAgo(report.created_at)}
                  </span>
                )}
                {isRunning && (
                  <span className="flex items-center gap-1 px-2 py-0.5 bg-purple-100 text-purple-600 text-xs rounded-full animate-pulse">
                    <Loader2 className="w-3 h-3 animate-spin" />
                    {t('tr.analyzingBadge')}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={toggleAIAnalysis}
                  className="flex items-center gap-1 px-2 py-1.5 text-sm text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                  title={isAIAnalysisCollapsed ? t('tr.expand') : t('tr.collapse')}
                >
                  {isAIAnalysisCollapsed ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
                  {isAIAnalysisCollapsed ? t('tr.expand') : t('tr.collapse')}
                </button>
                <div className="relative">
                  <button
                    onClick={() => setShowAnalysisModelSelect(!showAnalysisModelSelect)}
                    className="flex items-center gap-1 px-2 py-1.5 text-sm text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                    title={t('tr.selectModel')}
                  >
                    <Brain className="w-4 h-4" />
                    {availableModels.find(m => m.id === analysisModel)?.label || t('tr.defaultModelAuto')}
                  </button>
                  {showAnalysisModelSelect && (
                    <div className="absolute right-0 top-9 z-10 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg py-1 min-w-[200px] max-h-72 overflow-y-auto">
                      <button
                        onClick={() => { setAnalysisModel(''); setShowAnalysisModelSelect(false); }}
                        className={`w-full text-left px-3 py-1.5 text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors ${analysisModel === '' ? 'text-purple-600 font-medium' : 'text-gray-700 dark:text-gray-300'}`}
                      >
                        {t('tr.defaultModelAutoSelect')}
                      </button>
                      {availableModels.map(model => (
                        <button
                          key={model.id}
                          disabled={!model.available}
                          onClick={() => { setAnalysisModel(model.id); setShowAnalysisModelSelect(false); }}
                          className={`w-full text-left px-3 py-1.5 text-sm hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${analysisModel === model.id ? 'text-purple-600 font-medium' : 'text-gray-700 dark:text-gray-300'}`}
                        >
                          {model.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <button
                  onClick={startAnalysis}
                  disabled={isRunning || cooldown > 0}
                  className="flex items-center justify-center gap-1.5 sm:gap-2 px-3 sm:px-4 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors text-sm sm:text-base"
                >
                  {isRunning ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span className="hidden sm:inline">{t('tr.analyzingBadge')}...</span>
                      <span className="sm:hidden">{t('tr.analyzingBadge')}</span>
                    </>
                  ) : cooldown > 0 ? (
                    <>
                      <RefreshCw className="w-4 h-4" />
                      {t('tr.retryIn', { n: cooldown })}
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4" />
                      {hasHistory ? t('tr.reanalyze') : t('tr.startAnalysis')}
                    </>
                  )}
                </button>
              </div>
            </div>
            {!isAIAnalysisCollapsed && (<>

            {isRunning ? (
              renderRunningState()
            ) : aiError && !report ? (
              <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 rounded-lg p-6">
                <div className="flex items-center gap-2 text-red-600 mb-2">
                  <AlertCircle className="w-5 h-5" />
                  <span className="font-medium">{t('tr.analysisFailed')}</span>
                </div>
                <p className="text-red-600">{aiError}</p>
                <p className="text-red-500 text-sm mt-2">{t('tr.checkKeyHint')}</p>
              </div>
            ) : report ? (
              <div className="space-y-6">
                {report.summary && (
                  <div className="bg-gradient-to-r from-purple-50 to-blue-50 dark:from-purple-900/30 dark:to-blue-900/30 rounded-lg p-4 sm:p-6">
                    <p className="text-gray-700 dark:text-gray-300 text-sm sm:text-lg leading-relaxed">{report.summary}</p>
                  </div>
                )}

                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
                  <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 text-center">
                    <div className="text-2xl font-bold text-purple-600">{report.total_papers}</div>
                    <div className="text-sm text-gray-500 dark:text-gray-400">{t('tr.analyzedPapers')}</div>
                  </div>
                  <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 text-center">
                    <div className="text-2xl font-bold text-blue-600">{report.model || '-'}</div>
                    <div className="text-sm text-gray-500 dark:text-gray-400">{t('tr.usedModel')}</div>
                  </div>
                  <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 text-center">
                    <div className="text-2xl font-bold text-green-600">{report.tokens_used}</div>
                    <div className="text-sm text-gray-500 dark:text-gray-400">{t('tr.tokenCost')}</div>
                  </div>
                  <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 text-center">
                    <div className="text-2xl font-bold text-orange-600">{report.processing_time_ms > 1000 ? `${(report.processing_time_ms / 1000).toFixed(1)}s` : `${report.processing_time_ms}ms`}</div>
                    <div className="text-sm text-gray-500 dark:text-gray-400">{t('tr.processTime')}</div>
                  </div>
                </div>

                {renderSection(t('tr.hotTopics'), '🔥', report.hot_topics, (item, i) => (
                  <div key={i} className="border border-purple-100 rounded-lg p-4 bg-white dark:bg-gray-800 hover:shadow-sm transition-shadow">
                    <div className="flex items-start gap-3">
                      <span className="w-7 h-7 rounded-full bg-purple-100 text-purple-700 flex items-center justify-center text-sm font-bold shrink-0 mt-0.5">
                        {i + 1}
                      </span>
                      <div className="flex-1">
                        <h4 className="font-semibold text-gray-900 dark:text-white text-base">{item.topic}</h4>
                        <p className="text-gray-600 dark:text-gray-400 text-sm mt-1">{item.description}</p>
                        {item.evidence && (
                          <p className="text-gray-400 text-xs mt-1">{t('tr.evidenceLabel')}: {item.evidence}</p>
                        )}
                        {item.related_keywords && item.related_keywords.length > 0 && (
                          <div className="flex flex-wrap gap-1.5 mt-2">
                            {item.related_keywords.map((kw, ki) => (
                              <span key={ki} className="px-2 py-0.5 bg-purple-50 dark:bg-purple-900/30 text-purple-600 text-xs rounded-full border border-purple-100">
                                {kw}
                              </span>
                            ))}
                          </div>
                        )}
                        {item.significance && (
                          <p className="text-gray-500 dark:text-gray-400 text-xs mt-2 italic">{item.significance}</p>
                        )}
                      </div>
                    </div>
                  </div>
                ), 'section-hot-topics')}

                {renderSection(t('tr.devTrends'), '📈', report.development_trends, (item, i) => (
                  <div key={i} className="border border-blue-100 rounded-lg p-4 bg-white dark:bg-gray-800">
                    <div className="flex items-center gap-3 mb-2">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium border ${getDirectionColor(item.direction)}`}>
                        {getDirectionLabel(item.direction)}
                      </span>
                      <h4 className="font-semibold text-gray-900 dark:text-white">{item.trend}</h4>
                    </div>
                    <p className="text-gray-600 dark:text-gray-400 text-sm">{item.description}</p>
                    {item.evidence && (
                      <p className="text-gray-400 text-xs mt-1">{t('tr.basisLabel')}: {item.evidence}</p>
                    )}
                  </div>
                ), 'section-dev-trends')}

                {renderSection(t('tr.keywordInsights'), '🔍', report.keyword_insights, (item, i) => (
                  <div key={i} className="border border-green-100 rounded-lg p-4 bg-white dark:bg-gray-800">
                    <h4 className="font-semibold text-gray-900 dark:text-white mb-2">{item.cluster}</h4>
                    {item.keywords && item.keywords.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mb-2">
                        {item.keywords.map((kw, ki) => (
                          <span key={ki} className="px-2 py-0.5 bg-green-50 dark:bg-green-900/30 text-green-600 text-xs rounded-full border border-green-100">
                            {kw}
                          </span>
                        ))}
                      </div>
                    )}
                    <p className="text-gray-600 dark:text-gray-400 text-sm">{item.insight}</p>
                  </div>
                ), 'section-keyword-insights')}

                {renderSection(t('tr.journalInsights'), '📰', report.journal_insights, (item, i) => (
                  <div key={i} className="border border-yellow-100 rounded-lg p-4 bg-white dark:bg-gray-800">
                    <h4 className="font-semibold text-gray-900 dark:text-white">{item.journal}</h4>
                    <p className="text-gray-600 dark:text-gray-400 text-sm mt-1">
                      <span className="font-medium text-gray-700 dark:text-gray-300">{t('tr.focusLabel')}: </span>
                      {item.focus}
                    </p>
                    {item.suggestion && (
                      <p className="text-gray-500 dark:text-gray-400 text-sm mt-1">
                        <span className="font-medium text-gray-600 dark:text-gray-400">{t('tr.suggestionLabel')}: </span>
                        {item.suggestion}
                      </p>
                    )}
                  </div>
                ))}

                {renderSection(t('tr.recommendations'), '💡', report.recommendations, (item, i) => (
                  <div key={i} className="border border-orange-100 rounded-lg p-4 bg-white dark:bg-gray-800">
                    <div className="flex items-center gap-3 mb-2">
                      <span className={`px-2 py-0.5 rounded-full text-xs font-medium border ${getOpportunityColor(item.opportunity_level)}`}>
                        {item.opportunity_level === 'high' ? t('tr.highOpp') : item.opportunity_level === 'medium' ? t('tr.mediumOpp') : t('tr.lowOpp')}
                      </span>
                      <h4 className="font-semibold text-gray-900 dark:text-white">{item.area}</h4>
                    </div>
                    <p className="text-gray-600 dark:text-gray-400 text-sm">{item.description}</p>
                    {item.related_keywords && item.related_keywords.length > 0 && (
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {item.related_keywords.map((kw, ki) => (
                          <span key={ki} className="px-2 py-0.5 bg-orange-50 dark:bg-orange-900/30 text-orange-600 text-xs rounded-full border border-orange-100">
                            {kw}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}

                <div className="border-t border-gray-100 dark:border-gray-700 pt-4">
                  <button
                    onClick={() => setShowRawAnalysis(!showRawAnalysis)}
                    className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:text-gray-300 transition-colors"
                  >
                    {showRawAnalysis ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                    {showRawAnalysis ? t('tr.collapseRaw') : t('tr.viewRaw')}
                  </button>
                  {showRawAnalysis && report.raw_analysis && (
                    <div className="mt-4 p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-700">
                      <MarkdownRenderer content={report.raw_analysis} />
                    </div>
                  )}
                </div>

                <div className={`border-t border-gray-100 dark:border-gray-700 mt-6 pt-6 ${isChatFullscreen ? 'fixed inset-y-0 right-0 z-50 bg-white dark:bg-gray-900 p-4 sm:p-6 overflow-hidden w-full md:w-[600px] lg:w-[800px] shadow-2xl' : ''}`}>
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-0 mb-4">
                    <div>
                      <h3 className="text-sm sm:text-base font-semibold text-gray-900 dark:text-white flex items-center gap-2">
                        <Bot className="w-4 h-4 text-purple-600" />
                        {t('tr.chatTitle')}
                      </h3>
                      <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 mt-1">{t('tr.chatSub')}</p>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={toggleChatFullscreen}
                        className="flex items-center gap-1 px-2 py-1 text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 rounded hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                        title={isChatFullscreen ? t('tr.exitFullscreen') : t('tr.fullscreen')}
                      >
                        {isChatFullscreen ? <Minimize2 className="w-3 h-3" /> : <Maximize2 className="w-3 h-3" />}
                        {isChatFullscreen ? t('tr.exitFullscreen') : t('tr.fullscreen')}
                      </button>
                      <div className="relative">
                        <button
                          onClick={() => setShowModelSelect(!showModelSelect)}
                          className="flex items-center gap-1 px-2 py-1 text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 rounded hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                          title={t('tr.selectModelShort')}
                        >
                          <Settings2 className="w-3 h-3" />
                          {availableModels.find(m => m.id === selectedModel)?.label || t('tr.defaultModel')}
                        </button>
                        {showModelSelect && (
                          <div className="absolute right-0 top-8 z-10 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg py-1 min-w-[180px] max-h-64 overflow-y-auto">
                            <button
                              onClick={() => { setSelectedModel(''); setShowModelSelect(false); }}
                              className={`w-full text-left px-3 py-1.5 text-xs hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors ${selectedModel === '' ? 'text-purple-600 font-medium' : 'text-gray-700 dark:text-gray-300'}`}
                            >
                              {t('tr.defaultModel')}
                            </button>
                            {availableModels.map(model => (
                              <button
                                key={model.id}
                                disabled={!model.available}
                                onClick={() => { setSelectedModel(model.id); setShowModelSelect(false); }}
                                className={`w-full text-left px-3 py-1.5 text-xs hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${selectedModel === model.id ? 'text-purple-600 font-medium' : 'text-gray-700 dark:text-gray-300'}`}
                              >
                                {model.label}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                      <button
                        onClick={handleExportChats}
                        disabled={chatMessages.length === 0}
                        className="flex items-center gap-1 px-2 py-1 text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 rounded hover:bg-gray-200 dark:hover:bg-gray-600 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                        title={t('tr.exportChatTitle')}
                      >
                        <Download className="w-3 h-3" />
                        {t('tr.exportChat')}
                      </button>
                      <button
                        onClick={handleClearChats}
                        disabled={chatMessages.length === 0 || chatStreaming}
                        className="flex items-center gap-1 px-2 py-1 text-xs text-red-500 bg-red-50 dark:bg-red-900/20 rounded hover:bg-red-100 dark:hover:bg-red-900/40 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                        title={t('tr.clearChatTitle')}
                      >
                        <Trash2 className="w-3 h-3" />
                        {t('tr.clearChat')}
                      </button>
                    </div>
                  </div>

                  {chatLoading ? (
                    <div className="flex items-center justify-center py-8">
                      <Loader2 className="w-5 h-5 animate-spin text-purple-400" />
                      <span className="ml-2 text-sm text-gray-400">{t('tr.loadChats')}</span>
                    </div>
                  ) : (
                    <>
                      <div className={`space-y-4 mb-4 overflow-y-auto ${isChatFullscreen ? 'max-h-[calc(100vh-200px)]' : 'max-h-[500px]'}`}>
                        {chatMessages.length === 0 && !chatStreaming && (
                          <div className="text-center py-6">
                            <div className="flex flex-wrap gap-2 justify-center">
                              {[
                                t('tr.suggestion1'),
                                t('tr.suggestion2'),
                                t('tr.suggestion3'),
                                t('tr.suggestion4'),
                              ].map((suggestion, i) => (
                                <button
                                  key={i}
                                  onClick={() => handleTrendChatSubmit(suggestion)}
                                  className="px-3 py-1.5 text-sm bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400 rounded-full border border-purple-100 dark:border-purple-800 hover:bg-purple-100 dark:hover:bg-purple-900/50 transition-colors"
                                >
                                  {suggestion}
                                </button>
                              ))}
                            </div>
                          </div>
                        )}
                        {chatMessages.map((msg, i) => (
                          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                            <div className={`max-w-[80%] rounded-lg px-4 py-2 text-sm ${
                              msg.role === 'user'
                                ? 'bg-purple-600 text-white'
                                : 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200'
                            }`}>
                              {msg.role === 'user' ? msg.content : (
                                <MarkdownRenderer content={msg.content} />
                              )}
                            </div>
                          </div>
                        ))}
                        {chatStreaming && streamReasoning && !streamContent && (
                          <div className="flex justify-start">
                            <div className="max-w-[80%] rounded-lg px-4 py-2 text-sm bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800">
                              <div className="text-xs text-blue-500 dark:text-blue-400 mb-1 font-medium">💭 {t('tr.thinking')}</div>
                              <div className="text-xs text-blue-600 dark:text-blue-300 whitespace-pre-wrap">{streamReasoning}</div>
                            </div>
                          </div>
                        )}
                        {chatStreaming && streamContent && (
                          <div className="flex justify-start">
                            <div className="max-w-[80%] rounded-lg px-4 py-2 text-sm bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200">
                              {streamReasoning && (
                                <details className="mb-2">
                                  <summary className="text-xs text-blue-500 dark:text-blue-400 cursor-pointer hover:text-blue-600">💭 {t('tr.viewThinking')}</summary>
                                  <div className="mt-1 p-2 bg-blue-50 dark:bg-blue-900/20 rounded text-xs text-blue-600 dark:text-blue-300 whitespace-pre-wrap">{streamReasoning}</div>
                                </details>
                              )}
                              <MarkdownRenderer content={streamContent} />
                              <span className="inline-block w-1.5 h-4 bg-purple-600 ml-0.5 animate-pulse align-middle" />
                            </div>
                          </div>
                        )}
                        {chatStreaming && !streamContent && !streamReasoning && (
                          <div className="flex justify-start">
                            <div className="bg-gray-100 dark:bg-gray-700 rounded-lg px-4 py-3">
                              <Loader2 className="w-4 h-4 animate-spin text-gray-400" />
                            </div>
                          </div>
                        )}
                        <div ref={chatEndRef} />
                      </div>

                      <div className="flex gap-2">
                        <input
                          type="text"
                          value={chatInput}
                          onChange={(e) => setChatInput(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey && !chatStreaming) {
                              e.preventDefault();
                              handleTrendChatSubmit();
                            }
                          }}
                          placeholder={t('tr.chatPlaceholder')}
                          disabled={chatStreaming}
                          className="flex-1 border border-gray-300 dark:border-gray-600 rounded-lg px-3 sm:px-4 py-2 text-sm outline-none focus:ring-1 focus:ring-purple-500 disabled:bg-gray-50 dark:bg-gray-800 dark:text-white"
                        />
                        <button
                          onClick={() => handleTrendChatSubmit()}
                          disabled={chatStreaming || !chatInput.trim()}
                          className="bg-purple-600 text-white rounded-lg px-3 sm:px-4 py-2 hover:bg-purple-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shrink-0"
                        >
                          <Send className="w-4 h-4" />
                        </button>
                      </div>
                      {chatMessages.length > 0 && (
                        <div className="flex items-center justify-between mt-2">
                          <span className="text-xs text-gray-400">{t('tr.chatRounds', { n: Math.floor(chatMessages.length / 2) })} | {t('tr.contextHint', { n: MAX_CONTEXT_MESSAGES })}</span>
                        </div>
                      )}
                    </>
                  )}
                </div>
              </div>
            ) : (
              <div className="bg-gradient-to-r from-purple-50 to-blue-50 dark:from-purple-900/30 dark:to-blue-900/30 rounded-lg p-8">
                <div className="flex flex-col items-center justify-center">
                  <History className="w-16 h-16 text-purple-300 mb-4" />
                  <p className="text-gray-600 dark:text-gray-400 text-lg font-medium">{t('tr.noAnalysis')}</p>
                  <p className="text-gray-400 text-sm mt-1">{t('tr.noAnalysisHint')}</p>
                </div>
              </div>
            )}

            </>)}

            <div className="mt-6 border-t border-gray-100 dark:border-gray-700 pt-4">
              <button
                onClick={() => setShowHistory(!showHistory)}
                className="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:text-gray-300 transition-colors"
              >
                {showHistory ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                <History className="w-4 h-4" />
                {showHistory ? t('tr.collapseHistory') : t('tr.viewHistory')}
              </button>
              {showHistory && (
                <div className="mt-3 space-y-2">
                  {historyReports.length === 0 ? (
                    <p className="text-sm text-gray-400 py-2">{t('tr.noHistory')}</p>
                  ) : (
                    historyReports.map((r) => (
                      <div
                        key={r.id}
                        onClick={() => restoreReport(r.id)}
                        className={`flex items-center justify-between p-3 rounded-lg transition-colors cursor-pointer ${
                          restoringId === r.id
                            ? 'bg-purple-100 ring-2 ring-purple-300'
                            : r.id === report?.id
                            ? 'bg-purple-50 dark:bg-purple-900/30 ring-1 ring-purple-200'
                            : 'bg-gray-50 dark:bg-gray-700/50 hover:bg-gray-100 dark:bg-gray-700'
                        }`}
                      >
                        <div className="flex-1 min-w-0">
                          <p className="text-sm text-gray-700 dark:text-gray-300 truncate">{r.summary || t('tr.noSummary')}</p>
                          <div className="flex items-center gap-2 mt-1">
                            <span className="text-xs text-gray-400">{r.model}</span>
                            <span className="text-xs text-gray-400">{formatTimeAgo(r.created_at)}</span>
                            {r.id === report?.id && (
                              <span className="text-xs px-1.5 py-0.5 rounded bg-purple-100 text-purple-600">{t('tr.current')}</span>
                            )}
                          </div>
                        </div>
                        {restoringId === r.id ? (
                          <Loader2 className="w-4 h-4 text-purple-500 animate-spin ml-2 flex-shrink-0" />
                        ) : (
                          <span className="text-xs text-purple-500 ml-2 flex-shrink-0 hover:text-purple-700">{t('tr.view')}</span>
                        )}
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>

            <div className="mt-6 grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
              <a href="#" onClick={(e) => { e.preventDefault(); document.getElementById('section-hot-topics')?.scrollIntoView({ behavior: 'smooth' }); }} className="border border-gray-200 dark:border-gray-700 rounded-lg p-3 sm:p-4 hover:border-purple-200 hover:bg-purple-50 dark:hover:bg-purple-900/30 transition-colors cursor-pointer">
                <h3 className="font-medium text-gray-900 dark:text-white mb-1 sm:mb-2 text-sm sm:text-base">🔥 {t('tr.quickHot')}</h3>
                <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">{t('tr.quickHotDesc')}</p>
              </a>
              <a href="#" onClick={(e) => { e.preventDefault(); document.getElementById('section-keyword-insights')?.scrollIntoView({ behavior: 'smooth' }); }} className="border border-gray-200 dark:border-gray-700 rounded-lg p-3 sm:p-4 hover:border-purple-200 hover:bg-purple-50 dark:hover:bg-purple-900/30 transition-colors cursor-pointer">
                <h3 className="font-medium text-gray-900 dark:text-white mb-1 sm:mb-2 text-sm sm:text-base">🔍 {t('tr.quickKw')}</h3>
                <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">{t('tr.quickKwDesc')}</p>
              </a>
              <a href="#" onClick={(e) => { e.preventDefault(); document.getElementById('section-dev-trends')?.scrollIntoView({ behavior: 'smooth' }); }} className="border border-gray-200 dark:border-gray-700 rounded-lg p-3 sm:p-4 hover:border-purple-200 hover:bg-purple-50 dark:hover:bg-purple-900/30 transition-colors cursor-pointer">
                <h3 className="font-medium text-gray-900 dark:text-white mb-1 sm:mb-2 text-sm sm:text-base">📈 {t('tr.quickTrend')}</h3>
                <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">{t('tr.quickTrendDesc')}</p>
              </a>
            </div>
          </div>
        </>
      )}
    </Layout>
  );
}
