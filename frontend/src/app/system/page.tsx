'use client';

import React, { useState, useEffect } from 'react';
import Layout from '@/components/Layout';
import { papersApi } from '@/lib/api';
import { SystemStats, CrawlLog, SettingsInfo, SchedulerJob, MaintenanceResult } from '@/types/paper';
import {
  Settings, Activity, Database, BookOpen, Hash, Clock,
  Play, Loader2, CheckCircle, XCircle, RefreshCw, AlertCircle,
  Key, Brain, Trash2, ArrowUp, ArrowDown, Save, ToggleLeft, ToggleRight,
  Edit3, X
} from 'lucide-react';
import { useLanguage } from '@/contexts/LanguageContext';

type TabType = 'overview' | 'crawlerData' | 'aiConfig';

export default function SystemPage() {
  const { t } = useLanguage();
  const [activeTab, setActiveTab] = useState<TabType>('overview');
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [crawlLogs, setCrawlLogs] = useState<CrawlLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [crawling, setCrawling] = useState(false);
  const [cnkiCrawling, setCnkiCrawling] = useState<'top50' | 'navi' | null>(null);
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

  const [appInfo, setAppInfo] = useState({ name: '', version: '' });
  const [editingAppName, setEditingAppName] = useState(false);
  const [savingAppName, setSavingAppName] = useState(false);
  const [appNameMessage, setAppNameMessage] = useState('');

  // Custom providers state
  const [customProviders, setCustomProviders] = useState<Array<{
    name: string;
    base_url: string;
    api_key: string;
    models: string[];
  }>>([]);
  const [newProvider, setNewProvider] = useState({ name: '', base_url: '', api_key: '', models: '' });
  const [savingCustomProvider, setSavingCustomProvider] = useState(false);
  const [customProviderMessage, setCustomProviderMessage] = useState('');
  const [editingProviderName, setEditingProviderName] = useState<string | null>(null);

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
      if (statsRes.app_name || statsRes.app_version) {
        setAppInfo({
          name: statsRes.app_name || '',
          version: statsRes.app_version || '',
        });
      }
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
      if (res.app_name || res.app_version) {
        setAppInfo({
          name: res.app_name || '',
          version: res.app_version || '',
        });
      }
      // Load custom providers
      if (res.custom_providers) {
        setCustomProviders(res.custom_providers.map(cp => ({
          name: cp.name,
          base_url: cp.base_url,
          api_key: '',  // Don't store the actual key in state
          models: cp.models,
        })));
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
    if (activeTab === 'aiConfig') {
      fetchSettings();
    }
    if (activeTab === 'crawlerData') {
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

  const handleCNKICrawl = async (kind: 'top50' | 'navi') => {
    setCnkiCrawling(kind);
    setMessage('');
    try {
      const res = kind === 'top50'
        ? await papersApi.startCNKITop50Crawl()
        : await papersApi.startCNKNaviCrawl();
      setMessage(res.message || '知网爬取任务已启动');
    } catch (error: any) {
      setMessage(error.response?.data?.detail || '启动知网爬取失败');
    } finally {
      setCnkiCrawling(null);
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
      // 发送完整模型顺序（含自定义 Provider），后端会分别保存内置与自定义 Provider 的顺序
      const modelPriority = modelList.map(m => m.name);
      await papersApi.updateSettings({ model_priority: modelPriority });
      setModelMessage(t('sys.orderSaved'));
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
    if (!confirm(t('sys.cleanupConfirm'))) return;
    setCleaning(true);
    setCleanupResult(null);
    setCleanupMessage('');
    try {
      const res = await papersApi.cleanupData();
      setCleanupResult(res);
      setCleanupMessage(t('sys.cleanupDone'));
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
      setPortMessage(t('sys.portSaved'));
    } catch (error: any) {
      setPortMessage(error.response?.data?.detail || '保存失败');
    } finally {
      setSavingPorts(false);
    }
  };

  const handleSaveAppName = async () => {
    setSavingAppName(true);
    setAppNameMessage('');
    try {
      await papersApi.updateSettings({ app_name: appInfo.name });
      setAppNameMessage('应用名称已保存');
      setEditingAppName(false);
      fetchData();
    } catch (error: any) {
      setAppNameMessage(error.response?.data?.detail || '保存失败');
    } finally {
      setSavingAppName(false);
    }
  };

  // Custom provider handlers
  const handleEditCustomProvider = (name: string) => {
    const cp = settingsInfo?.custom_providers?.find(p => p.name === name);
    if (!cp) return;
    setNewProvider({
      name: cp.name,
      base_url: cp.base_url,
      api_key: '',  // 留空表示保留原 Key
      models: cp.models.join(', '),
    });
    setEditingProviderName(name);
    setCustomProviderMessage('');
  };

  const handleCancelEditProvider = () => {
    setNewProvider({ name: '', base_url: '', api_key: '', models: '' });
    setEditingProviderName(null);
    setCustomProviderMessage('');
  };

  const handleSaveCustomProvider = async () => {
    const name = newProvider.name.trim();
    const base_url = newProvider.base_url.trim();
    if (!name || !base_url) {
      setCustomProviderMessage('请填写名称和 Base URL');
      return;
    }
    // 新增时必须提供 API Key；编辑时可留空（保留原 Key）
    if (!editingProviderName && !newProvider.api_key.trim()) {
      setCustomProviderMessage('新增 Provider 必须填写 API Key');
      return;
    }
    setSavingCustomProvider(true);
    setCustomProviderMessage('');
    try {
      const models = newProvider.models.split(',').map(m => m.trim()).filter(m => m);
      const updatedProviders = [
        ...customProviders.filter(p => p.name !== name),
        {
          name,
          base_url,
          api_key: newProvider.api_key.trim(),
          models: models,
        }
      ];
      await papersApi.updateSettings({ custom_providers: updatedProviders });
      setCustomProviderMessage(editingProviderName ? 'Provider 已更新' : '自定义 Provider 已添加');
      handleCancelEditProvider();
      fetchSettings();
    } catch (error: any) {
      setCustomProviderMessage(error.response?.data?.detail || '保存失败');
    } finally {
      setSavingCustomProvider(false);
    }
  };

  const handleDeleteCustomProvider = async (name: string) => {
    if (!confirm(`确定要删除 Provider "${name}" 吗？`)) return;
    setSavingCustomProvider(true);
    setCustomProviderMessage('');
    try {
      const updatedProviders = customProviders.filter(p => p.name !== name);
      await papersApi.updateSettings({ custom_providers: updatedProviders });
      setCustomProviderMessage(`Provider "${name}" 已删除`);
      fetchSettings();
    } catch (error: any) {
      setCustomProviderMessage(error.response?.data?.detail || '删除失败');
    } finally {
      setSavingCustomProvider(false);
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
    { key: 'overview', label: t('systemTab.overview'), icon: <Activity className="w-4 h-4" /> },
    { key: 'crawlerData', label: t('systemTab.crawlerData'), icon: <Database className="w-4 h-4" /> },
    { key: 'aiConfig', label: t('systemTab.aiConfig'), icon: <Brain className="w-4 h-4" /> },
  ];

  const renderOverview = () => (
    <>
      <div className="bg-gradient-to-r from-primary-50 to-blue-50 dark:from-primary-900/30 dark:to-blue-900/30 rounded-lg shadow-sm border border-primary-200 dark:border-primary-800 p-6 mb-6">
        <div className="flex items-center justify-between">
          <div className="flex-1">
            {editingAppName ? (
              <div className="space-y-3">
                <div className="flex items-center gap-3">
                  <div className="flex-1">
                    <label className="block text-xs text-primary-600 dark:text-primary-400 mb-1">{t('sys.appNameLabel')}</label>
                    <input
                      type="text"
                      value={appInfo.name}
                      onChange={e => setAppInfo(prev => ({ ...prev, name: e.target.value }))}
                      className="w-full px-3 py-2 border border-primary-300 dark:border-primary-600 rounded-lg text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
                      placeholder={t('sys.appNameLabel')}
                    />
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleSaveAppName}
                    disabled={savingAppName}
                    className="flex items-center gap-1 px-3 py-1.5 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
                  >
                    {savingAppName ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                    {t('common.save')}
                  </button>
                  <button
                    onClick={() => {
                      setEditingAppName(false);
                      setAppInfo(prev => ({ ...prev, name: stats?.app_name || settingsInfo?.app_name || '' }));
                      setAppNameMessage('');
                    }}
                    className="flex items-center gap-1 px-3 py-1.5 text-gray-600 dark:text-gray-400 text-sm rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                  >
                    <X className="w-3.5 h-3.5" />
                    取消
                  </button>
                  {appNameMessage && (
                    <span className={`text-xs ${appNameMessage.includes('成功') || appNameMessage.includes('保存') ? 'text-green-600' : 'text-red-500'}`}>
                      {appNameMessage}
                    </span>
                  )}
                </div>
              </div>
            ) : (
              <>
                <h2 className="text-2xl font-bold text-primary-700 dark:text-primary-300">{appInfo.name || stats?.app_name || 'ApplePaper'}</h2>
                <p className="text-sm text-primary-600 dark:text-primary-400 mt-1">{t('sys.appDesc')}</p>
              </>
            )}
          </div>
          <div className="text-right">
            {!editingAppName && (
              <div className="flex items-center gap-3">
                <div className="text-sm text-primary-500 dark:text-primary-400">
                  <div>{t('sys.version')} {appInfo.version || stats?.app_version || '-'}</div>
                  <div className="mt-1">FastAPI + Next.js</div>
                </div>
                <button
                  onClick={() => setEditingAppName(true)}
                  className="p-2 text-primary-500 hover:text-primary-700 dark:hover:text-primary-300 hover:bg-primary-100 dark:hover:bg-primary-900/50 rounded-lg transition-colors"
                  title={t('sys.editAppName')}
                >
                  <Edit3 className="w-4 h-4" />
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-6">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-4">
            <div className="flex items-center gap-2 text-blue-600 mb-2">
              <Database className="w-5 h-5" />
              <span className="text-sm font-medium">{t('sys.totalPapers')}</span>
            </div>
            <div className="text-2xl font-bold text-gray-900 dark:text-white">{stats.total_papers}</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-4">
            <div className="flex items-center gap-2 text-green-600 mb-2">
              <BookOpen className="w-5 h-5" />
              <span className="text-sm font-medium">{t('sys.journals')}</span>
            </div>
            <div className="text-2xl font-bold text-gray-900 dark:text-white">{stats.journal_count}</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-4">
            <div className="flex items-center gap-2 text-purple-600 mb-2">
              <Hash className="w-5 h-5" />
              <span className="text-sm font-medium">{t('sys.keywords')}</span>
            </div>
            <div className="text-2xl font-bold text-gray-900 dark:text-white">{stats.keyword_count}</div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-4">
            <div className="flex items-center gap-2 text-orange-600 mb-2">
              <Clock className="w-5 h-5" />
              <span className="text-sm font-medium">{t('sys.latestUpdate')}</span>
            </div>
            <div className="text-sm font-semibold text-gray-900 dark:text-white">
              {timeAgo(stats.latest_paper_at)}
            </div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-4">
            <div className="flex items-center gap-2 text-cyan-600 mb-2">
              <Database className="w-5 h-5" />
              <span className="text-sm font-medium">{t('sys.dbSize')}</span>
            </div>
            <div className="text-2xl font-bold text-gray-900 dark:text-white">
              {stats.db_size_mb ? `${stats.db_size_mb.toFixed(1)} MB` : '-'}
            </div>
          </div>
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-4">
            <div className="flex items-center gap-2 text-emerald-600 mb-2">
              <Activity className="w-5 h-5" />
              <span className="text-sm font-medium">{t('sys.schedulerStatus')}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className={`w-2.5 h-2.5 rounded-full ${schedulerRunning ? 'bg-green-500' : 'bg-red-500'}`} />
              <span className="text-sm font-semibold text-gray-900 dark:text-white">
                {schedulerRunning ? t('sys.running') : t('sys.stopped')}
              </span>
            </div>
          </div>
        </div>
      )}

      {stats?.ai_usage && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6 mb-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
            <Brain className="w-5 h-5 text-gray-500 dark:text-gray-400" />
            {t('sys.aiUsage')}
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
              <div className="text-xs text-gray-500 dark:text-gray-400">{t('sys.totalAnalyses')}</div>
              <div className="text-xl font-bold text-gray-900 dark:text-white">{stats.ai_usage.total_analyses}</div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
              <div className="text-xs text-gray-500 dark:text-gray-400">{t('sys.totalTokens')}</div>
              <div className="text-xl font-bold text-gray-900 dark:text-white">{stats.ai_usage.total_tokens.toLocaleString()}</div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
              <div className="text-xs text-gray-500 dark:text-gray-400">{t('sys.totalTime')}</div>
              <div className="text-xl font-bold text-gray-900 dark:text-white">{(stats.ai_usage.total_processing_ms / 1000).toFixed(1)}s</div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-3">
              <div className="text-xs text-gray-500 dark:text-gray-400">{t('sys.papersAnalyzed')}</div>
              <div className="text-xl font-bold text-gray-900 dark:text-white">{stats.ai_usage.total_papers_analyzed.toLocaleString()}</div>
            </div>
          </div>
          {stats.ai_usage.by_model && stats.ai_usage.by_model.length > 0 && (
            <div className="space-y-2">
              <div className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('sys.byModel')}</div>
              {stats.ai_usage.by_model.map(item => (
                <div key={item.model} className="flex items-center justify-between bg-gray-50 dark:bg-gray-700/50 rounded px-3 py-2">
                  <span className="text-sm text-gray-700 dark:text-gray-300">{item.model}</span>
                  <div className="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
                    <span>{item.count} {t('sys.times')}</span>
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
            {t('sys.sourceDist')}
          </h3>
          <div className="flex flex-wrap gap-2">
            {Object.entries(stats.source_counts).map(([source, count]) => (
              <span key={source} className="px-3 py-1.5 bg-blue-50 dark:bg-blue-900/30 text-blue-700 rounded-full text-sm border border-blue-100">
                {source}: {count}{t('sys.papersUnit')}
              </span>
            ))}
          </div>
        </div>
      )}

      {stats?.top_journals && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6 mb-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-gray-500 dark:text-gray-400" />
            {t('sys.topJournals')}
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
                <span className="text-sm font-medium text-gray-500 dark:text-gray-400">{count}{t('sys.papersUnit')}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {stats?.year_counts && Object.keys(stats.year_counts).length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6 mb-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
            <Hash className="w-5 h-5 text-gray-500 dark:text-gray-400" />
            {t('sys.yearDist')}
          </h3>
          <div className="space-y-2">
            {Object.entries(stats.year_counts)
              .sort(([a], [b]) => Number(b) - Number(a))
              .map(([year, count]) => (
                <div key={year} className="flex items-center justify-between bg-gray-50 dark:bg-gray-700/50 rounded px-3 py-2">
                  <span className="text-sm text-gray-700 dark:text-gray-300">{year}</span>
                  <span className="text-sm font-medium text-gray-500 dark:text-gray-400">{count}{t('sys.papersUnit')}</span>
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
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-3">
            <button
              onClick={() => handleCNKICrawl('top50')}
              disabled={cnkiCrawling !== null}
              className="flex items-center justify-center gap-2 px-4 py-2.5 border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 text-amber-800 dark:text-amber-300 text-sm rounded-lg hover:bg-amber-100 dark:hover:bg-amber-900/40 disabled:opacity-50 transition-colors"
              title="知网TOP50期刊爬取（浏览器爬虫）"
            >
              {cnkiCrawling === 'top50' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              知网TOP50爬取
            </button>
            <button
              onClick={() => handleCNKICrawl('navi')}
              disabled={cnkiCrawling !== null}
              className="flex items-center justify-center gap-2 px-4 py-2.5 border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 text-amber-800 dark:text-amber-300 text-sm rounded-lg hover:bg-amber-100 dark:hover:bg-amber-900/40 disabled:opacity-50 transition-colors"
              title="知网期刊导航爬取（浏览器爬虫）"
            >
              {cnkiCrawling === 'navi' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              知网导航爬取
            </button>
          </div>

          {message && (
            <div className={`p-3 rounded-lg text-sm ${message.includes('失败') ? 'bg-red-50 dark:bg-red-900/30 text-red-600' : 'bg-green-50 dark:bg-green-900/30 text-green-600'}`}>
              {message}
            </div>
          )}
          <div className="mt-4 flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
            <AlertCircle className="w-4 h-4" />
            期刊爬虫抓取经济学核心期刊；知网爬虫为本机浏览器模式，遇验证码请在弹出窗口中人工处理
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
                {schedulerRunning ? t('sys.running') : t('sys.stopped')}
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
                      {job.trigger} · 下次执行: {job.next_run_time ? formatTime(job.next_run_time) : t('sys.noneLabel')}
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
                    {t('sys.runNow')}
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
              {t('sys.noCrawlLogs')}
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
                    <span>{t('sys.fetchedLabel')}: {log.papers_fetched}{t('sys.papersUnit')}</span>
                    {log.papers_failed > 0 && <span className="text-red-500">{t('sys.failedLabel')}: {log.papers_failed}{t('sys.papersUnit')}</span>}
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
      { key: 'zhipu', label: 'Zhipu' },
      { key: 'openai', label: 'OpenAI' },
      { key: 'siliconflow', label: 'SiliconFlow' },
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
                      {t('sys.configured')}
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-xs font-medium text-red-500">
                      <XCircle className="w-4 h-4" />
                      {t('sys.notConfigured')}
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
                    placeholder={t('sys.newKeyPlaceholder')}
                    value={apiKeys[provider.key] || ''}
                    onChange={e => setApiKeys(prev => ({ ...prev, [provider.key]: e.target.value }))}
                    className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent"
                  />
                  <button
                    onClick={() => handleUpdateApiKey(provider.key)}
                    disabled={updatingKey === provider.key || !apiKeys[provider.key]?.trim()}
                    className="px-4 py-2 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
                  >
                    {updatingKey === provider.key ? <Loader2 className="w-4 h-4 animate-spin" /> : t('sys.updateBtn')}
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

        {/* Custom Providers Section */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <Key className="w-5 h-5 text-purple-600" />
              <h3 className="font-semibold text-gray-900 dark:text-white">{t('sys.customProviders')}</h3>
            </div>
            <span className="text-xs text-gray-500 dark:text-gray-400">{t('sys.openaiCompatible')}</span>
          </div>

          {/* Existing custom providers */}
          {settingsInfo?.custom_providers && settingsInfo.custom_providers.length > 0 && (
            <div className="mb-4 space-y-3">
              {settingsInfo.custom_providers.map((cp) => (
                <div key={cp.name} className="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-700/50 rounded-lg">
                  <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-900 dark:text-white">{cp.name}</span>
                      {cp.api_key_configured ? (
                        <span className="flex items-center gap-1 text-xs text-green-600">
                          <CheckCircle className="w-3 h-3" />
                          已配置
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 text-xs text-red-500">
                          <XCircle className="w-3 h-3" />
                          未配置
                        </span>
                      )}
                    </div>
                    <span className="text-xs text-gray-500 dark:text-gray-400 font-mono">{cp.base_url}</span>
                    {cp.models.length > 0 && (
                      <span className="text-xs text-gray-500 dark:text-gray-400">
                        模型: {cp.models.join(', ')}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => handleEditCustomProvider(cp.name)}
                      disabled={savingCustomProvider}
                      className="p-1 text-gray-500 hover:text-purple-600 hover:bg-purple-50 dark:hover:bg-purple-900/20 rounded transition-colors"
                      title={t('sys.editProvider')}
                    >
                      <Edit3 className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleDeleteCustomProvider(cp.name)}
                      disabled={savingCustomProvider}
                      className="p-1 text-red-500 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900/20 rounded transition-colors"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Add / edit custom provider */}
          <div className="border-t dark:border-gray-700 pt-4">
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
              {editingProviderName ? `${t('sys.editProvider')}: ${editingProviderName}` : t('sys.addNewProvider')}
            </h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">{t('sys.nameLabel')} *</label>
                <input
                  type="text"
                  placeholder="my-llm"
                  value={newProvider.name}
                  onChange={e => setNewProvider(prev => ({ ...prev, name: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Base URL *</label>
                <input
                  type="text"
                  placeholder="例如: https://api.example.com/v1"
                  value={newProvider.base_url}
                  onChange={e => setNewProvider(prev => ({ ...prev, base_url: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">
                  API Key {editingProviderName ? '(留空保留原 Key)' : '*'}
                </label>
                <input
                  type="password"
                  placeholder={editingProviderName ? t('sys.keepKeyHint') : t('sys.newKeyPlaceholder')}
                  value={newProvider.api_key}
                  onChange={e => setNewProvider(prev => ({ ...prev, api_key: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">{t('sys.modelsLabel')}</label>
                <input
                  type="text"
                  placeholder="例如: gpt-4o, gpt-4o-mini"
                  value={newProvider.models}
                  onChange={e => setNewProvider(prev => ({ ...prev, models: e.target.value }))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"
                />
              </div>
            </div>
            <div className="mt-3 flex items-center gap-3">
              <button
                onClick={handleSaveCustomProvider}
                disabled={savingCustomProvider || !newProvider.name.trim() || !newProvider.base_url.trim() || (!editingProviderName && !newProvider.api_key.trim())}
                className="px-4 py-2 bg-purple-600 text-white text-sm rounded-lg hover:bg-purple-700 disabled:opacity-50 transition-colors"
              >
                {savingCustomProvider ? <Loader2 className="w-4 h-4 animate-spin" /> : (editingProviderName ? t('sys.saveChanges') : t('sys.addProvider'))}
              </button>
              {editingProviderName && (
                <button
                  onClick={handleCancelEditProvider}
                  disabled={savingCustomProvider}
                  className="px-4 py-2 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 text-sm rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                >
                  {t('common.cancel')}
                </button>
              )}
              {customProviderMessage && (
                <span className={`text-xs ${customProviderMessage.includes('成功') || customProviderMessage.includes('已') ? 'text-green-600' : 'text-red-500'}`}>
                  {customProviderMessage}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-5 h-5 text-gray-500 dark:text-gray-400" />
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('sys.tokenStatus')}</span>
          </div>
          <div className="mt-2">
            {settingsInfo?.api_token_configured ? (
              <span className="flex items-center gap-1 text-sm text-green-600">
                <CheckCircle className="w-4 h-4" />
                {t('sys.tokenConfigured')}
              </span>
            ) : (
              <span className="flex items-center gap-1 text-sm text-red-500">
                <XCircle className="w-4 h-4" />
                {t('sys.tokenNotConfigured')}
              </span>
            )}
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
          <div className="flex items-center gap-2 mb-4">
            <Settings className="w-5 h-5 text-gray-500 dark:text-gray-400" />
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('sys.portConfig')}</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">{t('sys.backendPort')}</label>
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
              <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">{t('sys.frontendPort')}</label>
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
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">{t('sys.modelPriority')}</h2>
          </div>
          <button
            onClick={handleSaveModelPriority}
            disabled={savingModels}
            className="flex items-center gap-2 px-4 py-2 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
          >
            {savingModels ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            {t('sys.saveOrder')}
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
                {model.provider && (
                  <span className={`text-xs px-1.5 py-0.5 rounded ${
                    model.provider === 'siliconflow'
                      ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400'
                      : model.provider === 'zhipu'
                        ? 'bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400'
                        : model.provider === 'openai'
                          ? 'bg-emerald-100 dark:bg-emerald-900/30 text-emerald-600 dark:text-emerald-400'
                          : 'bg-green-100 dark:bg-green-900/30 text-green-600 dark:text-green-400'
                  }`}>
                    {model.provider === 'siliconflow' ? '硅基流动' : model.provider === 'zhipu' ? '智谱' : model.provider === 'openai' ? 'OpenAI' : model.provider}
                  </span>
                )}
                {model.available ? (
                  <span className="flex items-center gap-1 text-xs text-green-600">
                    <CheckCircle className="w-3.5 h-3.5" />
                    {t('sys.available')}
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-xs text-red-500">
                    <XCircle className="w-3.5 h-3.5" />
                    {t('sys.unavailable')}
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
          {modelList.length === 0 && (
            <p className="text-sm text-gray-400 py-4">{t('sys.noModels')}</p>
          )}
        </div>
        <p className="mt-3 text-xs text-gray-400">{t('sys.customOrderHint')}</p>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-gray-500 dark:text-gray-400" />
          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{t('sys.aiServiceStatus')}</span>
        </div>
        <div className="mt-2">
          {settingsInfo?.models?.some(m => m.available) ? (
            <span className="flex items-center gap-1 text-sm text-green-600">
              <CheckCircle className="w-4 h-4" />
              {t('sys.aiAvailable')}
            </span>
          ) : (
            <span className="flex items-center gap-1 text-sm text-red-500">
              <XCircle className="w-4 h-4" />
              {t('sys.aiUnavailable')}
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
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white">{t('sys.dbStats')}</h2>
        </div>
        {stats && (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
              <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{t('sys.totalPapers')}</div>
              <div className="text-xl font-bold text-gray-900 dark:text-white">{stats.total_papers}</div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
              <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{t('sys.journals')}</div>
              <div className="text-xl font-bold text-gray-900 dark:text-white">{stats.journal_count}</div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
              <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{t('sys.keywords')}</div>
              <div className="text-xl font-bold text-gray-900 dark:text-white">{stats.keyword_count}</div>
            </div>
            <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
              <div className="text-xs text-gray-500 dark:text-gray-400 mb-1">{t('sys.dbSize')}</div>
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
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">{t('sys.cleanupTitle')}</h2>
          </div>
          <button
            onClick={handleCleanup}
            disabled={cleaning}
            className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors"
          >
            {cleaning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
            {t('sys.cleanupTitle')}
          </button>
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
          {t('sys.cleanupDesc')}
        </p>
        {cleanupMessage && (
          <div className={`p-3 rounded-lg text-sm ${cleanupMessage.includes('失败') ? 'bg-red-50 dark:bg-red-900/30 text-red-600' : 'bg-green-50 dark:bg-green-900/30 text-green-600'}`}>
            {cleanupMessage}
          </div>
        )}
        {cleanupResult && (
          <div className="mt-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
            <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">{t('sys.cleanupResult')}</h4>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">{t('sys.deletedPapers')}</div>
                <div className="text-lg font-bold text-gray-900 dark:text-white">{cleanupResult.deleted_papers}</div>
              </div>
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">{t('sys.deletedFeatures')}</div>
                <div className="text-lg font-bold text-gray-900 dark:text-white">{cleanupResult.deleted_features}</div>
              </div>
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">{t('sys.deletedScores')}</div>
                <div className="text-lg font-bold text-gray-900 dark:text-white">{cleanupResult.deleted_scores}</div>
              </div>
              <div>
                <div className="text-xs text-gray-500 dark:text-gray-400">{t('sys.deletedReports')}</div>
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
      case 'crawlerData':
        return (
          <>
            {renderCrawler()}
            {renderMaintenance()}
          </>
        );
      case 'aiConfig':
        return (
          <>
            {renderApiConfig()}
            {renderModels()}
          </>
        );
    }
  };

  return (
    <Layout>
      <div className="mb-6 sm:mb-8">
        <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white mb-2">{t('system.title')}</h1>
        <p className="text-sm sm:text-base text-gray-600 dark:text-gray-400">{t('system.subtitle')}</p>
      </div>

      <div className="border-b border-gray-200 dark:border-gray-700 mb-4 sm:mb-6 overflow-x-auto">
        <nav className="flex gap-4 sm:gap-6 min-w-max">
          {tabs.map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`flex items-center gap-1.5 sm:gap-2 px-1 py-2 sm:py-3 text-xs sm:text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                activeTab === tab.key
                  ? 'text-purple-700 border-purple-600'
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 border-transparent'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {loading ? (
        <div className="flex justify-center py-8 sm:py-12">
          <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
        </div>
      ) : (
        renderTabContent()
      )}
    </Layout>
  );
}
