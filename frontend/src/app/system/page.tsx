'use client';

import React, { useState, useEffect } from 'react';
import Layout from '@/components/Layout';
import { papersApi } from '@/lib/api';
import { SystemStats, CrawlLog, SettingsInfo, SchedulerJob, MaintenanceResult } from '@/types/paper';
import {
  Settings, Activity, Database, BookOpen, Hash, Clock,
  Play, Loader2, CheckCircle, XCircle, RefreshCw, AlertCircle,
  Key, Brain, Trash2, ArrowUp, ArrowDown, Save, ToggleLeft, ToggleRight
} from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';

type TabType = 'overview' | 'crawler' | 'api' | 'models' | 'maintenance';

export default function SystemPage() {
  const { t } = useLanguage();
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [crawlLogs, setCrawlLogs] = useState<CrawlLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [crawling, setCrawling] = useState(false);
  const [message, setMessage] = useState('');

  const [settingsInfo, setSettingsInfo] = useState<SettingsInfo | null>(null);
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
  const [apiMessage, setApiMessage] = useState<Record<string, string>>({});
  const [updatingKey, setUpdatingKey] = useState<string | null>(null);

  const [modelList, setModelList] = useState<SettingsInfo['models']>([]);
  const [savingModels, setSavingModels] = useState(false);
  const [modelMessage, setModelMessage] = useState('');

  const [schedulerRunning, setSchedulerRunning] = useState(false);
  const [schedulerJobs, setSchedulerJobs] = useState<SchedulerJob[]>([]);
  const [togglingScheduler, setTogglingScheduler] = useState(false);
  const [triggeringJob, setTriggeringJob] = useState<string | null>(null);

  const [cleaning, setCleaning] = useState(false);
  const [cleanupResult, setCleanupResult] = useState<MaintenanceResult | null>(null);
  const [cleanupMessage, setCleanupMessage] = useState('');

  const [ports, setPorts] = useState({ backend: 8000, frontend: 3000 });
  const [savingPorts, setSavingPorts] = useState(false);
  const [portMessage, setPortMessage] = useState('');

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

  const fetchSettings = async () => {
    try {
      const res = await papersApi.getSettings();
      setSettingsInfo(res);
      setModelList([...res.models].sort((a, b) => a.priority - b.priority));
      setSchedulerRunning(res.scheduler.running);
      if (res.ports) {
        setPorts(res.ports);
      }
    } catch (error) {
      console.error('Error fetching settings:', error);
    }
  };

  const fetchSchedulerJobs = async () => {
    try {
      const jobs = await papersApi.getSchedulerJobs();
      setSchedulerJobs(jobs);
    } catch (error) {
      console.error('Error fetching scheduler jobs:', error);
    }
  };

  useEffect(() => {
    if (activeTab === 'api' || activeTab === 'models') {
      fetchSettings();
    }
    if (activeTab === 'crawler') {
      fetchSchedulerJobs();
    }
  }, [activeTab]);

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

  const handleUpdateApiKey = async (provider: string) => {
    const key = apiKeys[provider];
    if (!key || !key.trim()) return;
    setUpdatingKey(provider);
    setApiMessage(prev => ({ ...prev, [provider]: '' }));
    try {
      await papersApi.updateSettings({ api_keys: { [provider]: key.trim() } });
      setApiMessage(prev => ({ ...prev, [provider]: '更新成功' }));
      setApiKeys(prev => ({ ...prev, [provider]: '' }));
      fetchSettings();
    } catch (error: any) {
      setApiMessage(prev => ({ ...prev, [provider]: error.response?.data?.detail || '更新失败' }));
    } finally {
      setUpdatingKey(null);
    }
  };

  const handleMoveModel = (index: number, direction: 'up' | 'down') => {
    const newList = [...modelList];
    const targetIndex = direction === 'up' ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= newList.length) return;
    [newList[index], newList[targetIndex]] = [newList[targetIndex], newList[index]];
    setModelList(newList);
  };

  const handleSaveModelPriority = async () => {
    setSavingModels(true);
    setModelMessage('');
    try {
      const modelPriority = modelList.map(m => m.name);
      await papersApi.updateSettings({ model_priority: modelPriority });
      setModelMessage('模型优先级已保存');
      fetchSettings();
    } catch (error: any) {
      setModelMessage(error.response?.data?.detail || '保存失败');
    } finally {
      setSavingModels(false);
    }
  };

  const handleToggleScheduler = async () => {
    setTogglingScheduler(true);
    try {
      const res = await papersApi.toggleScheduler();
      setSchedulerRunning(res.running);
    } catch (error) {
      console.error('Error toggling scheduler:', error);
    } finally {
      setTogglingScheduler(false);
    }
  };

  const handleTriggerJob = async (jobId: string) => {
    setTriggeringJob(jobId);
    try {
      await papersApi.triggerSchedulerJob(jobId);
      setTimeout(fetchSchedulerJobs, 2000);
    } catch (error) {
      console.error('Error triggering job:', error);
    } finally {
      setTriggeringJob(null);
    }
  };

  const handleCleanup = async () => {
    if (!confirm('确定要清理无效数据吗？此操作不可撤销。')) return;
    setCleaning(true);
    setCleanupResult(null);
    setCleanupMessage('');
    try {
      const res = await papersApi.cleanupData();
      setCleanupResult(res);
      setCleanupMessage('清理完成');
      fetchData();
    } catch (error: any) {
      setCleanupMessage(error.response?.data?.detail || '清理失败');
    } finally {
      setCleaning(false);
    }
  };

  const handleUpdatePorts = async () => {
    setSavingPorts(true);
    setPortMessage('');
    try {
      await papersApi.updateSettings({ ports: { backend_port: ports.backend, frontend_port: ports.frontend } });
      setPortMessage('端口配置已保存，重启后生效');
    } catch (error: any) {
      setPortMessage(error.response?.data?.detail || '保存失败');
    } finally {
      setSavingPorts(false);
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

  const tabs: { key: TabType; label: string; icon: React.ReactNode }[] = [
    { key: 'overview', label: '概览', icon: <Activity className="w-4 h-4" /> },
    { key: 'crawler', label: '爬虫管理', icon: <Database className="w-4 h-4" /> },
    { key: 'api', label: 'API 配置', icon: <Key className="w-4 h-4" /> },
    { key: 'models', label: 'AI 模型', icon: <Brain className="w-4 h-4" /> },
    { key: 'maintenance', label: '数据维护', icon: <Trash2 className="w-4 h-4" /> },
  ];

  const renderOverview = () => (
    <>
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-4">
            <div className="flex items-center gap-2 text-blue-600 mb-2">
              <Database className="w-5 h-5" />
              <span className="text-sm font-medium">论文总数</span>
            </div>
            <div className="text-2xl font-bold text-gray-900 dark:text-white">{stats.total_papers}</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-4">
            <div className="flex items-center gap-2 text-green-600 mb-2">
              <BookOpen className="w-5 h-5" />
              <span className="text-sm font-medium">期刊数量</span>
            </div>
            <div className="text-2xl font-bold text-gray-900 dark:text-white">{stats.journal_count}</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-4">
            <div className="flex items-center gap-2 text-purple-600 mb-2">
              <Hash className="w-5 h-5" />
              <span className="text-sm font-medium">关键词数</span>
            </div>
            <div className="text-2xl font-bold text-gray-900 dark:text-white">{stats.keyword_count}</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-4">
            <div className="flex items-center gap-2 text-orange-600 mb-2">
              <Clock className="w-5 h-5" />
              <span className="text-sm font-medium">最近更新</span>
            </div>
            <div className="text-sm font-semibold text-gray-900 dark:text-white">
              {timeAgo(stats.latest_paper_at)}
            </div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-4">
            <div className="flex items-center gap-2 text-cyan-600 mb-2">
              <Database className="w-5 h-5" />
              <span className="text-sm font-medium">数据库大小</span>
            </div>
            <div className="text-2xl font-bold text-gray-900 dark:text-white">
              {stats.db_size_mb ? `${stats.db_size_mb.toFixed(1)} MB` : '-'}
            </div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-4">
            <div className="flex items-center gap-2 text-emerald-600 mb-2">
              <Activity className="w-5 h-5" />
              <span className="text-sm font-medium">调度器状态</span>
            </div>
            <div className="flex items-center gap-2">
              <span className={`w-2.5 h-2.5 rounded-full ${schedulerRunning ? 'bg-green-500' : 'bg-red-500'}`} />
              <span className="text-sm font-semibold text-gray-900 dark:text-white">
                {schedulerRunning ? '运行中' : '已停止'}
              </span>
            </div>
          </div>
        </div>
      )}

      {stats?.ai_usage && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6 mb-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
            <Brain className="w-5 h-5 text-gray-500 dark:text-gray-400" />
            AI 使用统计
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
              <div className="text-xs text-gray-500 dark:text-gray-400">分析次数</div>
              <div className="text-xl font-bold text-gray-900 dark:text-white">{stats.ai_usage.total_analyses}</div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
              <div className="text-xs text-gray-500 dark:text-gray-400">总 Token 消耗</div>
              <div className="text-xl font-bold text-gray-900 dark:text-white">{stats.ai_usage.total_tokens.toLocaleString()}</div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
              <div className="text-xs text-gray-500 dark:text-gray-400">总处理时间</div>
              <div className="text-xl font-bold text-gray-900 dark:text-white">{(stats.ai_usage.total_processing_ms / 1000).toFixed(1)}s</div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
              <div className="text-xs text-gray-500 dark:text-gray-400">分析论文总数</div>
              <div className="text-xl font-bold text-gray-900 dark:text-white">{stats.ai_usage.total_papers_analyzed.toLocaleString()}</div>
            </div>
          </div>
          {stats.ai_usage.by_model && stats.ai_usage.by_model.length > 0 && (
            <div className="space-y-2">
              <div className="text-sm font-medium text-gray-700 dark:text-gray-300">按模型统计</div>
              {stats.ai_usage.by_model.map(item => (
                <div key={item.model} className="flex items-center justify-between bg-gray-50 dark:bg-gray-700/50 rounded px-3 py-2">
                  <span className="text-sm text-gray-700 dark:text-gray-300">{item.model}</span>
                  <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
                    <span>{item.count}次</span>
                    <span>{item.tokens.toLocaleString()} tokens</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {stats?.source_counts && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6 mb-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
            <Activity className="w-5 h-5 text-gray-500 dark:text-gray-400" />
            来源分布
          </h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(stats.source_counts).map(([source, count]) => (
              <span key={source} className="px-3 py-1.5 bg-blue-50 dark:bg-blue-900/30 text-blue-700 rounded-full text-sm border border-blue-100">
                {source}: {count}篇
              </span>
            ))}
          </div>
        </div>
      )}

      {stats?.top_journals && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6 mb-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-gray-500 dark:text-gray-400" />
            Top 10 期刊
          </h3>
          <div className="space-y-2">
            {Object.entries(stats.top_journals).map(([journal, count], idx) => (
              <div key={journal} className="flex items-center justify-between bg-gray-50 dark:bg-gray-700/50 rounded px-3 py-2">
                <div className="flex items-center gap-2">
                  <span className="w-6 h-6 rounded-full bg-primary-100 text-primary-700 flex items-center justify-center text-xs font-bold">
                    {idx + 1}
                  </span>
                  <span className="text-sm text-gray-700 dark:text-gray-300">{journal}</span>
                </div>
                <span className="text-sm font-medium text-gray-500 dark:text-gray-400">{count}篇</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {stats?.year_counts && Object.keys(stats.year_counts).length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6 mb-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
            <Hash className="w-5 h-5 text-gray-500 dark:text-gray-400" />
            年份分布
          </h3>
          <div className="space-y-2">
            {Object.entries(stats.year_counts)
              .sort(([a], [b]) => Number(b) - Number(a))
              .map(([year, count]) => (
                <div key={year} className="flex items-center justify-between bg-gray-50 dark:bg-gray-700/50 rounded px-3 py-2">
                  <span className="text-sm text-gray-700 dark:text-gray-300">{year}</span>
                  <span className="text-sm font-medium text-gray-500 dark:text-gray-400">{count}篇</span>
                </div>
              ))}
          </div>
        </div>
      )}
    </>
  );

  const renderCrawler = () => (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="space-y-6">
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <Settings className="w-6 h-6 text-primary-600" />
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">{t('system.crawlControl')}</h2>
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
            <div className={`p-3 rounded-lg text-sm ${message.includes('失败') ? 'bg-red-50 dark:bg-red-900/30 text-red-600' : 'bg-green-50 dark:bg-green-900/30 text-green-600'}`}>
              {message}
            </div>
          )}
          <div className="mt-4 flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
            <AlertCircle className="w-4 h-4" />
            爬虫将抓取所有已配置的期刊和arXiv最新论文
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <Activity className="w-6 h-6 text-primary-600" />
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">调度器控制</h2>
            </div>
            <button
              onClick={handleToggleScheduler}
              disabled={togglingScheduler}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            >
              {togglingScheduler ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : schedulerRunning ? (
                <ToggleRight className="w-6 h-6 text-green-600" />
              ) : (
                <ToggleLeft className="w-6 h-6 text-gray-400" />
              )}
              <span className={schedulerRunning ? 'text-green-600' : 'text-gray-500 dark:text-gray-400'}>
                {schedulerRunning ? '运行中' : '已停止'}
              </span>
            </button>
          </div>
          {schedulerJobs.length > 0 && (
            <div className="space-y-2">
              {schedulerJobs.map(job => (
                <div key={job.id} className="flex items-center justify-between bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
                  <div>
                    <div className="text-sm font-medium text-gray-700 dark:text-gray-300">{job.name}</div>
                    <div className="text-xs text-gray-500 dark:text-gray-400">
                      {job.trigger} · 下次执行: {job.next_run_time ? formatTime(job.next_run_time) : '无'}
                    </div>
                  </div>
                  <button
                    onClick={() => handleTriggerJob(job.id)}
                    disabled={triggeringJob === job.id}
                    className="flex items-center gap-1 px-3 py-1.5 text-xs font-medium bg-primary-50 dark:bg-primary-900/30 text-primary-700 rounded-md hover:bg-primary-100 disabled:opacity-50 transition-colors"
                  >
                    {triggeringJob === job.id ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <Play className="w-3 h-3" />
                    )}
                    立即执行
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <Activity className="w-6 h-6 text-primary-600" />
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">{t('system.crawlLogs')}</h2>
          </div>
          <button onClick={fetchData} className="p-2 hover:bg-gray-100 dark:bg-gray-700 rounded-lg transition-colors">
            <RefreshCw className="w-4 h-4 text-gray-500 dark:text-gray-400" />
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
                <div key={log.id} className="border border-gray-100 dark:border-gray-700 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{log.journal_name}</span>
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
                  <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
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
  );

  const renderApiConfig = () => {
    const providers = [
      { key: 'zhipu', label: 'Zhipu（智谱）' },
      { key: 'openai', label: 'OpenAI' },
      { key: 'siliconflow', label: 'SiliconFlow（硅基流动）' },
    ];

    return (
      <div className="space-y-6">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {providers.map(provider => {
            const status = settingsInfo?.api_keys?.[provider.key as keyof typeof settingsInfo.api_keys];
            return (
              <div key={provider.key} className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <Key className="w-5 h-5 text-primary-600" />
                    <h3 className="font-semibold text-gray-900 dark:text-white">{provider.label}</h3>
                  </div>
                  {status?.configured ? (
                    <span className="flex items-center gap-1 text-xs font-medium text-green-600">
                      <CheckCircle className="w-4 h-4" />
                      已配置
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-xs font-medium text-red-500">
                      <XCircle className="w-4 h-4" />
                      未配置
                    </span>
                  )}
                </div>
                {status?.masked && (
                  <div className="mb-3 px-3 py-2 bg-gray-50 dark:bg-gray-700/50 rounded text-sm text-gray-600 dark:text-gray-400 font-mono">
                    {status.masked}
                  </div>
                )}
                <div className="flex gap-2">
                  <input
                    type="password"
                    placeholder="输入新的 API Key"
                    value={apiKeys[provider.key] || ''}
                    onChange={e => setApiKeys(prev => ({ ...prev, [provider.key]: e.target.value }))}
                    className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                  />
                  <button
                    onClick={() => handleUpdateApiKey(provider.key)}
                    disabled={updatingKey === provider.key || !apiKeys[provider.key]?.trim()}
                    className="px-4 py-2 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
                  >
                    {updatingKey === provider.key ? <Loader2 className="w-4 h-4 animate-spin" /> : '更新'}
                  </button>
                </div>
                {apiMessage[provider.key] && (
                  <div className={`mt-2 text-xs ${apiMessage[provider.key].includes('成功') ? 'text-green-600' : 'text-red-500'}`}>
                    {apiMessage[provider.key]}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-5 h-5 text-gray-500 dark:text-gray-400" />
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">API Token 配置状态</span>
          </div>
          <div className="mt-2">
            {settingsInfo?.api_token_configured ? (
              <span className="flex items-center gap-1 text-sm text-green-600">
                <CheckCircle className="w-4 h-4" />
                API Token 已配置
              </span>
            ) : (
              <span className="flex items-center gap-1 text-sm text-red-500">
                <XCircle className="w-4 h-4" />
                API Token 未配置
              </span>
            )}
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
          <div className="flex items-center gap-2 mb-4">
            <Settings className="w-5 h-5 text-gray-500 dark:text-gray-400" />
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">端口配置</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">后端端口</label>
              <div className="flex gap-2">
                <input
                  type="number"
                  value={ports.backend}
                  onChange={e => setPorts(prev => ({ ...prev, backend: parseInt(e.target.value) || 8000 }))}
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
            </div>
            <div>
              <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">前端端口</label>
              <div className="flex gap-2">
                <input
                  type="number"
                  value={ports.frontend}
                  onChange={e => setPorts(prev => ({ ...prev, frontend: parseInt(e.target.value) || 3000 }))}
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
            </div>
          </div>
          <div className="mt-3 flex items-center gap-3">
            <button
              onClick={handleUpdatePorts}
              disabled={savingPorts}
              className="px-4 py-2 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
            >
              {savingPorts ? <Loader2 className="w-4 h-4 animate-spin" /> : '保存'}
            </button>
            {portMessage && (
              <span className={`text-xs ${portMessage.includes('成功') || portMessage.includes('保存') ? 'text-green-600' : 'text-red-500'}`}>
                {portMessage}
              </span>
            )}
          </div>
          <p className="mt-2 text-xs text-gray-400">修改端口后需要重启服务才能生效</p>
        </div>
      </div>
    );
  };

  const renderModels = () => (
    <div className="space-y-6">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <Brain className="w-6 h-6 text-primary-600" />
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">模型优先级</h2>
          </div>
          <button
            onClick={handleSaveModelPriority}
            disabled={savingModels}
            className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
          >
            {savingModels ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            保存排序
          </button>
        </div>
        {modelMessage && (
          <div className={`mb-4 p-3 rounded-lg text-sm ${modelMessage.includes('失败') ? 'bg-red-50 dark:bg-red-900/30 text-red-600' : 'bg-green-50 dark:bg-green-900/30 text-green-600'}`}>
            {modelMessage}
          </div>
        )}
        <div className="space-y-2">
          {modelList.map((model, index) => (
            <div key={model.name} className="flex items-center justify-between bg-gray-50 dark:bg-gray-700/50 rounded-lg px-4 py-3">
              <div className="flex items-center gap-3">
                <span className="w-7 h-7 rounded-full bg-primary-100 text-primary-700 flex items-center justify-center text-xs font-bold">
                  {index + 1}
                </span>
                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{model.name}</span>
                {model.available ? (
                  <span className="flex items-center gap-1 text-xs text-green-600">
                    <CheckCircle className="w-3.5 h-3.5" />
                    可用
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-xs text-red-500">
                    <XCircle className="w-3.5 h-3.5" />
                    不可用
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => handleMoveModel(index, 'up')}
                  disabled={index === 0}
                  className="p-1.5 hover:bg-gray-200 rounded disabled:opacity-30 transition-colors"
                >
                  <ArrowUp className="w-4 h-4" />
                </button>
                <button
                  onClick={() => handleMoveModel(index, 'down')}
                  disabled={index === modelList.length - 1}
                  className="p-1.5 hover:bg-gray-200 rounded disabled:opacity-30 transition-colors"
                >
                  <ArrowDown className="w-4 h-4" />
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-gray-500 dark:text-gray-400" />
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">AI 服务状态</span>
        </div>
        <div className="mt-2">
          {settingsInfo?.models?.some(m => m.available) ? (
            <span className="flex items-center gap-1 text-sm text-green-600">
              <CheckCircle className="w-4 h-4" />
              AI 服务可用
            </span>
          ) : (
            <span className="flex items-center gap-1 text-sm text-red-500">
              <XCircle className="w-4 h-4" />
              AI 服务不可用
            </span>
          )}
        </div>
      </div>
    </div>
  );

  const renderMaintenance = () => (
    <div className="space-y-6">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
        <div className="flex items-center gap-3 mb-4">
          <Database className="w-6 h-6 text-primary-600" />
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">数据库统计</h2>
        </div>
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
              <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">论文总数</div>
              <div className="text-xl font-bold text-gray-900 dark:text-white">{stats.total_papers}</div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
              <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">期刊数量</div>
              <div className="text-xl font-bold text-gray-900 dark:text-white">{stats.journal_count}</div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
              <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">关键词数</div>
              <div className="text-xl font-bold text-gray-900 dark:text-white">{stats.keyword_count}</div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
              <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">数据库大小</div>
              <div className="text-xl font-bold text-gray-900 dark:text-white">
                {stats.db_size_mb ? `${stats.db_size_mb.toFixed(1)} MB` : '-'}
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <Trash2 className="w-6 h-6 text-red-500" />
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">清理无效数据</h2>
          </div>
          <button
            onClick={handleCleanup}
            disabled={cleaning}
            className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors"
          >
            {cleaning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
            清理无效数据
          </button>
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          清理数据库中没有关联特征的论文、孤立的特征数据、无效评分和过期报告。
        </p>
        {cleanupMessage && (
          <div className={`p-3 rounded-lg text-sm ${cleanupMessage.includes('失败') ? 'bg-red-50 dark:bg-red-900/30 text-red-600' : 'bg-green-50 dark:bg-green-900/30 text-green-600'}`}>
            {cleanupMessage}
          </div>
        )}
        {cleanupResult && (
          <div className="mt-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">清理结果</h4>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">删除论文</div>
                <div className="text-lg font-bold text-gray-900 dark:text-white">{cleanupResult.deleted_papers}</div>
              </div>
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">删除特征</div>
                <div className="text-lg font-bold text-gray-900 dark:text-white">{cleanupResult.deleted_features}</div>
              </div>
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">删除评分</div>
                <div className="text-lg font-bold text-gray-900 dark:text-white">{cleanupResult.deleted_scores}</div>
              </div>
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">删除报告</div>
                <div className="text-lg font-bold text-gray-900 dark:text-white">{cleanupResult.deleted_reports}</div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );

  const renderTabContent = () => {
    switch (activeTab) {
      case 'overview':
        return renderOverview();
      case 'crawler':
        return renderCrawler();
      case 'api':
        return renderApiConfig();
      case 'models':
        return renderModels();
      case 'maintenance':
        return renderMaintenance();
    }
  };

  return (
    <Layout>
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">{t('system.title')}</h1>
        <p className="text-gray-600 dark:text-gray-400">{t('system.subtitle')}</p>
      </div>

      <div className="border-b border-gray-200 dark:border-gray-700 mb-6">
        <nav className="flex gap-6">
          {tabs.map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-2 px-1 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.key
                  ? 'text-purple-700 border-purple-600'
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:text-gray-300 border-transparent'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
        </div>
      ) : (
        renderTabContent()
      )}
    </Layout>
  );
}
