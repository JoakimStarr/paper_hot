'use client';

import React, { useState, useEffect } from 'react';
import Layout from '@/components/Layout';
import { papersApi } from '@/lib/api';
import { SystemStats, CrawlLog, SettingsInfo, SchedulerJob, MaintenanceResult, CNKISearchInfo } from '@/types/paper';
import { Activity, Settings, Database, Brain, Loader2 } from 'lucide-react';
import { KeywordCrawlForm } from './CrawlerTab';
import { useLanguage } from '@/contexts/LanguageContext';
import OverviewTab from './OverviewTab';
import CrawlerTab from './CrawlerTab';
import DataTab from './DataTab';
import ModelConfigTab from './ModelConfigTab';

type TabType = 'overview' | 'crawler' | 'data' | 'modelConfig';

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

  // 关键词检索爬取
  const [kwInfo, setKwInfo] = useState<CNKISearchInfo | null>(null);
  const [kwStarting, setKwStarting] = useState(false);
  const [kwForm, setKwForm] = useState<KeywordCrawlForm>({ keyword: '', search_field: '主题', years: '', max_pages: '', show_browser: false });
  const kwPollRef = React.useRef<ReturnType<typeof setInterval> | null>(null);

  const loadKwStatus = async () => {
    try {
      const info = await papersApi.getCNKISearchStatus();
      setKwInfo(info);
    } catch { /* ignore */ }
  };

  useEffect(() => () => { if (kwPollRef.current) clearInterval(kwPollRef.current); }, []);

  const handleStartKeywordCrawl = async () => {
    const keyword = kwForm.keyword.trim();
    if (!keyword) return;
    setKwStarting(true);
    try {
      const res = await papersApi.startCNKISearchCrawl({
        keyword,
        search_field: kwForm.search_field || '主题',
        years: kwForm.years.trim() || undefined,
        max_pages: kwForm.max_pages ? Number(kwForm.max_pages) : undefined,
        show_browser: kwForm.show_browser,
      });
      setMessage(t('sys.kwStarted'));
      if (kwPollRef.current) clearInterval(kwPollRef.current);
      kwPollRef.current = setInterval(async () => {
        const info = await papersApi.getCNKISearchStatus().catch(() => null);
        if (info) {
          setKwInfo(info);
          if (!info.running && kwPollRef.current) {
            clearInterval(kwPollRef.current);
            kwPollRef.current = null;
            setKwStarting(false);
          }
        }
      }, 3000);
      void res;
    } catch (error: any) {
      setMessage(error.response?.data?.detail || t('sys.kwStartFailed'));
      setKwStarting(false);
    }
  };

  const handlePauseKeywordCrawl = async () => {
    try {
      const res = await papersApi.pauseCNKISearch();
      setMessage(res.status === 'paused' ? t('sys.kwPaused') : t('sys.kwPauseFailed'));
    } catch (error: any) {
      setMessage(error.response?.data?.detail || t('sys.kwPauseFailed'));
    }
  };

  const handleResumeKeywordCrawl = async () => {
    try {
      await papersApi.resumeCNKISearch();
      setMessage(t('sys.kwResumed'));
    } catch (error: any) {
      setMessage(error.response?.data?.detail || t('sys.kwResumeFailed'));
    }
  };

  const [ports, setPorts] = useState({ backend: 8000, frontend: 3000 });
  const [savingPorts, setSavingPorts] = useState(false);
  const [portMessage, setPortMessage] = useState('');

  const [appInfo, setAppInfo] = useState({ name: '', version: '' });
  const [editingAppName, setEditingAppName] = useState(false);
  const [savingAppName, setSavingAppName] = useState(false);
  const [appNameMessage, setAppNameMessage] = useState('');

  // CNKI 论文详情跳转域名头
  const [cnkiUrlPrefix, setCnkiUrlPrefix] = useState('');
  const [cnkiPrefixDraft, setCnkiPrefixDraft] = useState('');
  const [savingCnkiPrefix, setSavingCnkiPrefix] = useState(false);
  const [cnkiPrefixMessage, setCnkiPrefixMessage] = useState('');

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

  // Default model + link test state
  const [defaultModel, setDefaultModel] = useState<string | null>(null);
  const [savingDefaultModel, setSavingDefaultModel] = useState(false);
  const [defaultModelMessage, setDefaultModelMessage] = useState('');
  const [testingModel, setTestingModel] = useState('');
  const [testResults, setTestResults] = useState<Record<string, { ok: boolean; latency_ms?: number; message: string }>>({});

  // 自定义 provider「获取模型列表」：读取 OpenAI 兼容接口的 /models 并回填 models 输入
  const [fetchingModels, setFetchingModels] = useState(false);

  // Embedding model state（选题验证器的向量模型，可自定义到任意 provider）
  const [embeddingModel, setEmbeddingModel] = useState<string | null>(null);
  const [embeddingModelDraft, setEmbeddingModelDraft] = useState('');
  const [savingEmbeddingModel, setSavingEmbeddingModel] = useState(false);
  const [embeddingModelMessage, setEmbeddingModelMessage] = useState('');

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
      setDefaultModel(res.default_model || null);
      setEmbeddingModel(res.embedding_model || null);
      setEmbeddingModelDraft(res.embedding_model || '');
      if (res.ports) {
        setPorts(res.ports);
      }
      if (res.app_name || res.app_version) {
        setAppInfo({
          name: res.app_name || '',
          version: res.app_version || '',
        });
      }
      if (typeof res.cnki_url_prefix === 'string') {
        setCnkiUrlPrefix(res.cnki_url_prefix);
        setCnkiPrefixDraft(res.cnki_url_prefix);
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
    if (activeTab === 'modelConfig') {
      fetchSettings();
    }
    if (activeTab === 'crawler') {
      fetchSchedulerJobs();
      loadKwStatus();
    }
  }, [activeTab]);

  const handleStartCrawl = async () => {
    setCrawling(true);
    setMessage('');
    try {
      const res = await papersApi.startCrawl();
      setMessage(res.message || t('sys.crawlStarted'));
      setTimeout(fetchData, 3000);
    } catch (error: any) {
      setMessage(error.response?.data?.detail || t('sys.crawlStartFailed'));
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
      setMessage(res.message || t('sys.cnkiStarted'));
    } catch (error: any) {
      setMessage(error.response?.data?.detail || t('sys.cnkiStartFailed'));
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
      setApiMessage(prev => ({ ...prev, [provider]: t('sys.updatedMsg') }));
      setApiKeys(prev => ({ ...prev, [provider]: '' }));
      fetchSettings();
    } catch (error: any) {
      setApiMessage(prev => ({ ...prev, [provider]: error.response?.data?.detail || t('sys.updateFailedMsg') }));
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
      setModelMessage(error.response?.data?.detail || t('sys.saveFailed'));
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
      setCleanupMessage(error.response?.data?.detail || t('sys.cleanupFailed'));
    } finally {
      setCleaning(false);
    }
  };

  const handleSaveCnkiPrefix = async () => {
    setSavingCnkiPrefix(true);
    setCnkiPrefixMessage('');
    try {
      const value = cnkiPrefixDraft.trim();
      await papersApi.updateSettings({ cnki_url_prefix: value });
      setCnkiUrlPrefix(value);
      setCnkiPrefixDraft(value);
      setCnkiPrefixMessage(t('sys.cnkiPrefixSaved'));
      fetchData();
    } catch (error: any) {
      setCnkiPrefixMessage(error.response?.data?.detail || t('sys.saveFailed'));
    } finally {
      setSavingCnkiPrefix(false);
    }
  };

  const handleUpdatePorts = async () => {
    setSavingPorts(true);
    setPortMessage('');
    try {
      await papersApi.updateSettings({ ports: { backend_port: ports.backend, frontend_port: ports.frontend } });
      setPortMessage(t('sys.portSaved'));
    } catch (error: any) {
      setPortMessage(error.response?.data?.detail || t('sys.saveFailed'));
    } finally {
      setSavingPorts(false);
    }
  };

  const handleSaveAppName = async () => {
    setSavingAppName(true);
    setAppNameMessage('');
    try {
      await papersApi.updateSettings({ app_name: appInfo.name });
      setAppNameMessage(t('sys.appNameSaved'));
      setEditingAppName(false);
      fetchData();
    } catch (error: any) {
      setAppNameMessage(error.response?.data?.detail || t('sys.saveFailed'));
    } finally {
      setSavingAppName(false);
    }
  };

  const handleStartEditAppName = () => setEditingAppName(true);

  const handleEditAppNameChange = (name: string) => setAppInfo(prev => ({ ...prev, name }));

  const handleCancelEditAppName = () => {
    setEditingAppName(false);
    setAppInfo(prev => ({ ...prev, name: stats?.app_name || settingsInfo?.app_name || '' }));
    setAppNameMessage('');
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
      setCustomProviderMessage(t('sys.providerNameRequired'));
      return;
    }
    // 新增时必须提供 API Key；编辑时可留空（保留原 Key）
    if (!editingProviderName && !newProvider.api_key.trim()) {
      setCustomProviderMessage(t('sys.providerKeyRequired'));
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
      setCustomProviderMessage(editingProviderName ? t('sys.providerUpdated') : t('sys.providerAdded'));
      handleCancelEditProvider();
      fetchSettings();
    } catch (error: any) {
      setCustomProviderMessage(error.response?.data?.detail || t('sys.saveFailed'));
    } finally {
      setSavingCustomProvider(false);
    }
  };

  const handleDeleteCustomProvider = async (name: string) => {
    if (!confirm(t('sys.confirmDeleteProvider', { name }))) return;
    setSavingCustomProvider(true);
    setCustomProviderMessage('');
    try {
      const updatedProviders = customProviders.filter(p => p.name !== name);
      await papersApi.updateSettings({ custom_providers: updatedProviders });
      setCustomProviderMessage(t('sys.providerDeleteMsg', { name }));
      fetchSettings();
    } catch (error: any) {
      setCustomProviderMessage(error.response?.data?.detail || t('sys.deleteFailed'));
    } finally {
      setSavingCustomProvider(false);
    }
  };

  const handleSetDefaultModel = async (model: string) => {
    setSavingDefaultModel(true);
    setDefaultModelMessage('');
    try {
      await papersApi.updateSettings({ default_model: model });
      setDefaultModel(model);
      setDefaultModelMessage(t('sys.defaultSaved'));
    } catch (error: any) {
      setDefaultModelMessage(error.response?.data?.detail || t('sys.defaultSaveFailed'));
    } finally {
      setSavingDefaultModel(false);
    }
  };

  const handleClearDefaultModel = async () => {
    setSavingDefaultModel(true);
    setDefaultModelMessage('');
    try {
      await papersApi.updateSettings({ default_model: null });
      setDefaultModel(null);
      setDefaultModelMessage(t('sys.defaultSaved'));
    } catch (error: any) {
      setDefaultModelMessage(error.response?.data?.detail || t('sys.defaultSaveFailed'));
    } finally {
      setSavingDefaultModel(false);
    }
  };

  const handleSaveEmbeddingModel = async () => {
    const value = embeddingModelDraft.trim();
    setSavingEmbeddingModel(true);
    setEmbeddingModelMessage('');
    try {
      await papersApi.updateSettings({ embedding_model: value || null });
      setEmbeddingModel(value || null);
      setEmbeddingModelMessage(t('sys.embeddingSaved'));
    } catch (error: any) {
      setEmbeddingModelMessage(error.response?.data?.detail || t('sys.embeddingSaveFailed'));
    } finally {
      setSavingEmbeddingModel(false);
    }
  };

  const handleTestModelLink = async (model: string) => {
    setTestingModel(model);
    setTestResults(prev => ({ ...prev, [model]: prev[model] || { ok: false, message: '' } }));
    try {
      const res = await papersApi.testModelLink(model);
      setTestResults(prev => ({ ...prev, [model]: res }));
    } catch (error: any) {
      setTestResults(prev => ({
        ...prev,
        [model]: { ok: false, message: error.response?.data?.detail || error.message || t('sys.testFailed') },
      }));
    } finally {
      setTestingModel('');
    }
  };

  const handleFetchModels = async () => {
    const base_url = newProvider.base_url.trim();
    if (!base_url) {
      setCustomProviderMessage(t('sys.fetchModelsNeedUrl'));
      return;
    }
    setFetchingModels(true);
    setCustomProviderMessage('');
    try {
      const res = await papersApi.fetchProviderModels({
        name: newProvider.name.trim() || undefined,
        base_url,
        api_key: newProvider.api_key.trim() || undefined,
      });
      if (res.models && res.models.length > 0) {
        const ids = res.models;
        setNewProvider(prev => ({ ...prev, models: ids.join(', ') }));
        setCustomProviderMessage(t('sys.fetchModelsOk', { n: ids.length }));
      } else {
        setCustomProviderMessage(res.message || t('sys.fetchModelsEmpty'));
      }
    } catch (error: any) {
      setCustomProviderMessage(error.response?.data?.detail || t('sys.fetchModelsFailed'));
    } finally {
      setFetchingModels(false);
    }
  };

  const tabs: { key: TabType; label: string; icon: React.ReactNode }[] = [
    { key: 'overview', label: t('systemTab.overview'), icon: <Activity className="w-4 h-4" /> },
    { key: 'crawler', label: t('systemTab.crawler'), icon: <Settings className="w-4 h-4" /> },
    { key: 'data', label: t('systemTab.data'), icon: <Database className="w-4 h-4" /> },
    { key: 'modelConfig', label: t('systemTab.modelConfig'), icon: <Brain className="w-4 h-4" /> },
  ];

  const renderTabContent = () => {
    switch (activeTab) {
      case 'overview':
        return (
          <OverviewTab
            stats={stats}
            schedulerRunning={schedulerRunning}
            appInfo={appInfo}
            editingAppName={editingAppName}
            savingAppName={savingAppName}
            appNameMessage={appNameMessage}
            onEditAppNameChange={handleEditAppNameChange}
            onStartEditAppName={handleStartEditAppName}
            onCancelEditAppName={handleCancelEditAppName}
            onSaveAppName={handleSaveAppName}
            cnkiUrlPrefix={cnkiUrlPrefix}
            cnkiPrefixDraft={cnkiPrefixDraft}
            savingCnkiPrefix={savingCnkiPrefix}
            cnkiPrefixMessage={cnkiPrefixMessage}
            onCnkiPrefixDraftChange={setCnkiPrefixDraft}
            onSaveCnkiPrefix={handleSaveCnkiPrefix}
          />
        );
      case 'crawler':
        return (
          <CrawlerTab
            message={message}
            crawling={crawling}
            cnkiCrawling={cnkiCrawling}
            onStartCrawl={handleStartCrawl}
            onCNKICrawl={handleCNKICrawl}
            schedulerRunning={schedulerRunning}
            schedulerJobs={schedulerJobs}
            togglingScheduler={togglingScheduler}
            triggeringJob={triggeringJob}
            onToggleScheduler={handleToggleScheduler}
            onTriggerJob={handleTriggerJob}
            crawlLogs={crawlLogs}
            onRefresh={fetchData}
            kwInfo={kwInfo}
            kwStarting={kwStarting}
            kwForm={kwForm}
            setKwForm={setKwForm}
            onStartKeywordCrawl={handleStartKeywordCrawl}
            onPauseKeywordCrawl={handlePauseKeywordCrawl}
            onResumeKeywordCrawl={handleResumeKeywordCrawl}
          />
        );
      case 'data':
        return (
          <DataTab
            stats={stats}
            cleaning={cleaning}
            cleanupMessage={cleanupMessage}
            cleanupResult={cleanupResult}
            onCleanup={handleCleanup}
          />
        );
      case 'modelConfig':
        return (
          <ModelConfigTab
            settingsInfo={settingsInfo}
            apiKeys={apiKeys}
            apiMessage={apiMessage}
            updatingKey={updatingKey}
            onUpdateApiKey={handleUpdateApiKey}
            setApiKeys={setApiKeys}
            newProvider={newProvider}
            setNewProvider={setNewProvider}
            editingProviderName={editingProviderName}
            savingCustomProvider={savingCustomProvider}
            customProviderMessage={customProviderMessage}
            onEditCustomProvider={handleEditCustomProvider}
            onCancelEditProvider={handleCancelEditProvider}
            onSaveCustomProvider={handleSaveCustomProvider}
            onDeleteCustomProvider={handleDeleteCustomProvider}
            ports={ports}
            setPorts={setPorts}
            savingPorts={savingPorts}
            portMessage={portMessage}
            onUpdatePorts={handleUpdatePorts}
            modelList={modelList}
            savingModels={savingModels}
            modelMessage={modelMessage}
            onSaveModelPriority={handleSaveModelPriority}
            onMoveModel={handleMoveModel}
            defaultModel={defaultModel}
            savingDefaultModel={savingDefaultModel}
            defaultModelMessage={defaultModelMessage}
            embeddingModel={embeddingModel}
            embeddingModelDraft={embeddingModelDraft}
            setEmbeddingModelDraft={setEmbeddingModelDraft}
            savingEmbeddingModel={savingEmbeddingModel}
            embeddingModelMessage={embeddingModelMessage}
            onSaveEmbeddingModel={handleSaveEmbeddingModel}
            onClearDefaultModel={handleClearDefaultModel}
            onSetDefaultModel={handleSetDefaultModel}
            testingModel={testingModel}
            testResults={testResults}
            onTestModelLink={handleTestModelLink}
            fetchingModels={fetchingModels}
            onFetchModels={handleFetchModels}
          />
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