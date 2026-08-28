'use client';

import React, { useState, useEffect, useRef, useCallback } from 'react';
import Layout from '@/components/Layout';
import { papersApi, ApiError } from '@/lib/api';
import { SystemStats, CrawlLog, SettingsInfo, SchedulerJob, MaintenanceResult, CNKISearchInfo, Msg, ExportedSettings } from '@/types/paper';
import { Activity, Settings, Database, Brain, ScrollText, Loader2 } from 'lucide-react';
import { KeywordCrawlForm } from './CrawlerTab';
import { useLanguage } from '@/contexts/LanguageContext';
import OverviewTab from './OverviewTab';
import CrawlerTab from './CrawlerTab';
import DataTab from './DataTab';
import ModelConfigTab from './ModelConfigTab';
import LogsTab from './LogsTab';
import ConfirmModal from './ConfirmModal';

type TabType = 'overview' | 'crawler' | 'data' | 'modelConfig' | 'logs';

const TAB_KEYS: TabType[] = ['overview', 'crawler', 'data', 'modelConfig', 'logs'];

/** 操作反馈 5s 后自动消失 */
function useAutoClear(value: unknown, clear: () => void, ms = 5000) {
  useEffect(() => {
    if (!value) return;
    const id = setTimeout(clear, ms);
    return () => clearTimeout(id);
  }, [value, clear, ms]);
}

export default function SystemPage() {
  const { t } = useLanguage();
  const [activeTab, setActiveTabState] = useState<TabType>('overview');
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [crawlLogs, setCrawlLogs] = useState<CrawlLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [crawling, setCrawling] = useState(false);
  const [cnkiCrawling, setCnkiCrawling] = useState<'top50' | 'navi' | null>(null);
  const [message, setMessage] = useState<Msg>(null);

  const [settingsInfo, setSettingsInfo] = useState<SettingsInfo | null>(null);
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({});
  const [apiMessage, setApiMessage] = useState<Record<string, Msg>>({});
  const [updatingKey, setUpdatingKey] = useState<string | null>(null);

  const [modelList, setModelList] = useState<SettingsInfo['models']>([]);
  const [savingModels, setSavingModels] = useState(false);
  const [modelMessage, setModelMessage] = useState<Msg>(null);

  const [schedulerRunning, setSchedulerRunning] = useState(false);
  const [schedulerJobs, setSchedulerJobs] = useState<SchedulerJob[]>([]);
  const [togglingScheduler, setTogglingScheduler] = useState(false);
  const [triggeringJob, setTriggeringJob] = useState<string | null>(null);

  const [cleaning, setCleaning] = useState(false);
  const [cleanupResult, setCleanupResult] = useState<MaintenanceResult | null>(null);
  const [cleanupMessage, setCleanupMessage] = useState<Msg>(null);

  // 确认弹窗（替代原生 confirm）
  type ConfirmState =
    | { type: 'cleanup' }
    | { type: 'deleteProvider'; name: string }
    | { type: 'import'; data: ExportedSettings }
    | { type: 'restart' }
    | null;
  const [confirm, setConfirm] = useState<ConfirmState>(null);
  const [importing, setImporting] = useState(false);
  const [restarting, setRestarting] = useState(false);

  // 关键词检索爬取
  const [kwInfo, setKwInfo] = useState<CNKISearchInfo | null>(null);
  const [kwStarting, setKwStarting] = useState(false);
  const [kwStopping, setKwStopping] = useState(false);
  const [rerunningLogId, setRerunningLogId] = useState<number | null>(null);
  const [kwForm, setKwForm] = useState<KeywordCrawlForm>({ keyword: '', search_field: '主题', years: '', max_pages: '', detail_workers: '3', show_browser: false });
  const kwPollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /** 统一把异常转成结构化反馈 */
  const errMsg = useCallback((error: unknown, fallback: string): Msg => ({
    ok: false,
    text: error instanceof ApiError ? (error.detail || error.message) : (error as Error)?.message || fallback,
  }), []);
  const okMsg = useCallback((text: string): Msg => ({ ok: true, text }), []);

  const loadKwStatus = async () => {
    try {
      const info = await papersApi.getCNKISearchStatus();
      setKwInfo(info);
    } catch { /* ignore */ }
  };

  // 关键词爬取状态轮询（启动/重跑共用）；上限 200 次（约 10 分钟），超时停止自动刷新
  const startKwStatusPoll = () => {
    if (kwPollRef.current) clearInterval(kwPollRef.current);
    let kwAttempts = 0;
    kwPollRef.current = setInterval(async () => {
      kwAttempts += 1;
      const info = await papersApi.getCNKISearchStatus().catch(() => null);
      if (!info) return;
      setKwInfo(info);
      if (!info.running && kwPollRef.current) {
        clearInterval(kwPollRef.current);
        kwPollRef.current = null;
        setKwStarting(false);
      } else if (kwAttempts > 200 && kwPollRef.current) {
        clearInterval(kwPollRef.current);
        kwPollRef.current = null;
        setKwStarting(false);
        setMessage({ ok: true, text: t('sys.kwPollTimeout') });
      }
    }, 3000);
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
        detail_workers: kwForm.detail_workers ? Math.min(Math.max(1, Number(kwForm.detail_workers)), 12) : 3,
        show_browser: kwForm.show_browser,
      });
      setMessage(okMsg(t('sys.kwStarted')));
      startKwStatusPoll();
      void res;
    } catch (error: unknown) {
      setMessage(errMsg(error, t('sys.kwStartFailed')));
      setKwStarting(false);
    }
  };

  const handlePauseKeywordCrawl = async () => {
    try {
      const res = await papersApi.pauseCNKISearch();
      setMessage(res.status === 'paused' ? okMsg(t('sys.kwPaused')) : { ok: false, text: t('sys.kwPauseFailed') });
    } catch (error: unknown) {
      setMessage(errMsg(error, t('sys.kwPauseFailed')));
    }
  };

  const handleResumeKeywordCrawl = async () => {
    try {
      await papersApi.resumeCNKISearch();
      setMessage(okMsg(t('sys.kwResumed')));
    } catch (error: unknown) {
      setMessage(errMsg(error, t('sys.kwResumeFailed')));
    }
  };

  const handleStopKeywordCrawl = async () => {
    if (!kwInfo?.running) return;
    setKwStopping(true);
    try {
      await papersApi.stopCNKISearch();
      setMessage(okMsg(t('sys.kwStopped')));
      setKwStopping(false);
      // 状态轮询很快会拉到 running=false 并自动复位
    } catch (error: unknown) {
      setKwStopping(false);
      setMessage(errMsg(error, t('sys.kwStopFailed')));
    }
  };

  const handleRerunTask = async (logId: number) => {
    if (rerunningLogId !== null) return;
    setRerunningLogId(logId);
    try {
      const res = await papersApi.rerunCrawl(logId);
      setMessage(okMsg(res.task_type === 'keyword'
        ? t('sys.rerunKw', { name: res.name })
        : t('sys.rerunCrawl', { name: res.name })));
      if (res.task_type === 'keyword') {
        // 关键词任务重跑：立即拉一次状态并启动轮询，进度实时更新
        loadKwStatus();
        startKwStatusPoll();
      }
    } catch (error: unknown) {
      setMessage(errMsg(error, t('sys.rerunFailed')));
    } finally {
      setRerunningLogId(null);
      fetchData();
    }
  };

  const [ports, setPorts] = useState({ backend: 8000, frontend: 3000 });
  const [savingPorts, setSavingPorts] = useState(false);
  const [portMessage, setPortMessage] = useState<Msg>(null);

  const [appInfo, setAppInfo] = useState({ name: '', version: '' });
  const [editingAppName, setEditingAppName] = useState(false);
  const [savingAppName, setSavingAppName] = useState(false);
  const [appNameMessage, setAppNameMessage] = useState<Msg>(null);

  // CNKI 论文详情跳转域名头
  const [cnkiUrlPrefix, setCnkiUrlPrefix] = useState('');
  const [cnkiPrefixDraft, setCnkiPrefixDraft] = useState('');
  const [savingCnkiPrefix, setSavingCnkiPrefix] = useState(false);
  const [cnkiPrefixMessage, setCnkiPrefixMessage] = useState<Msg>(null);

  // Custom providers state
  const [customProviders, setCustomProviders] = useState<Array<{
    name: string;
    base_url: string;
    api_key: string;
    models: string[];
  }>>([]);
  const [newProvider, setNewProvider] = useState({ name: '', base_url: '', api_key: '', models: '' });
  const [savingCustomProvider, setSavingCustomProvider] = useState(false);
  const [customProviderMessage, setCustomProviderMessage] = useState<Msg>(null);
  const [editingProviderName, setEditingProviderName] = useState<string | null>(null);

  // Default model + link test state
  const [defaultModel, setDefaultModel] = useState<string | null>(null);
  const [savingDefaultModel, setSavingDefaultModel] = useState(false);
  const [defaultModelMessage, setDefaultModelMessage] = useState<Msg>(null);
  const [testingModel, setTestingModel] = useState('');
  const [testResults, setTestResults] = useState<Record<string, { ok: boolean; latency_ms?: number; message: string }>>({});

  // 自定义 provider「获取模型列表」：读取 OpenAI 兼容接口的 /models 并回填 models 输入
  const [fetchingModels, setFetchingModels] = useState(false);

  // Embedding model state（选题验证器的向量模型，可自定义到任意 provider）
  const [embeddingModel, setEmbeddingModel] = useState<string | null>(null);
  const [embeddingModelDraft, setEmbeddingModelDraft] = useState('');
  const [savingEmbeddingModel, setSavingEmbeddingModel] = useState(false);
  const [embeddingModelMessage, setEmbeddingModelMessage] = useState<Msg>(null);

  // AI 追问数据库检索（Agent 工具）全局开关
  const [agentEnabled, setAgentEnabled] = useState(false);
  const [savingAgent, setSavingAgent] = useState(false);
  const [agentMessage, setAgentMessage] = useState<Msg>(null);

  // AI 模型单价（成本估算）
  const aiModelPrices = settingsInfo?.ai_model_prices || {};

  // 各类反馈 5s 自动消失
  useAutoClear(message, () => setMessage(null));
  useAutoClear(apiMessage, () => setApiMessage({}));
  useAutoClear(modelMessage, () => setModelMessage(null));
  useAutoClear(cleanupMessage, () => setCleanupMessage(null));
  useAutoClear(appNameMessage, () => setAppNameMessage(null));
  useAutoClear(cnkiPrefixMessage, () => setCnkiPrefixMessage(null));
  useAutoClear(portMessage, () => setPortMessage(null));
  useAutoClear(customProviderMessage, () => setCustomProviderMessage(null));
  useAutoClear(defaultModelMessage, () => setDefaultModelMessage(null));
  useAutoClear(embeddingModelMessage, () => setEmbeddingModelMessage(null));
  useAutoClear(agentMessage, () => setAgentMessage(null));

  useEffect(() => {
    fetchData();
    // 设置页所有页签都依赖 settings（CNKI 前缀、应用名、端口、模型等），进入即加载
    fetchSettings();
  }, []);

  // 挂载后从 URL ?tab= 恢复页签：不在 useState 初始化器里读 URL，
  // 避免服务端预渲染(overview)与客户端(logs)不一致导致水合后页签高亮与内容割裂
  useEffect(() => {
    const tab = new URLSearchParams(window.location.search).get('tab') as TabType | null;
    if (tab && TAB_KEYS.includes(tab)) setActiveTabState(tab);
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
      setAgentEnabled(!!res.agent_enabled);
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
    if (activeTab === 'crawler') {
      fetchSchedulerJobs();
      loadKwStatus();
    }
  }, [activeTab]);

  // 页签切换同步到 URL（replaceState 不触发导航），刷新/分享后停留在原页签
  const setActiveTab = (tab: TabType) => {
    setActiveTabState(tab);
    try {
      const url = new URL(window.location.href);
      url.searchParams.set('tab', tab);
      window.history.replaceState(null, '', url.toString());
    } catch { /* URL 同步失败不影响切换 */ }
  };

  const handleStartCrawl = async () => {
    setCrawling(true);
    setMessage(null);
    try {
      const res = await papersApi.startCrawl();
      setMessage(okMsg(res.message || t('sys.crawlStarted')));
      setTimeout(fetchData, 3000);
    } catch (error: unknown) {
      setMessage(errMsg(error, t('sys.crawlStartFailed')));
    } finally {
      setCrawling(false);
    }
  };

  const handleCNKICrawl = async (kind: 'top50' | 'navi') => {
    setCnkiCrawling(kind);
    setMessage(null);
    try {
      const res = kind === 'top50'
        ? await papersApi.startCNKITop50Crawl()
        : await papersApi.startCNKNaviCrawl();
      setMessage(okMsg(res.message || t('sys.cnkiStarted')));
    } catch (error: unknown) {
      setMessage(errMsg(error, t('sys.cnkiStartFailed')));
    } finally {
      setCnkiCrawling(null);
    }
  };

  const handleUpdateApiKey = async (provider: string) => {
    const key = apiKeys[provider];
    if (!key || !key.trim()) return;
    setUpdatingKey(provider);
    setApiMessage(prev => ({ ...prev, [provider]: null }));
    try {
      await papersApi.updateSettings({ api_keys: { [provider]: key.trim() } });
      setApiMessage(prev => ({ ...prev, [provider]: okMsg(t('sys.updatedMsg')) }));
      setApiKeys(prev => ({ ...prev, [provider]: '' }));
      fetchSettings();
    } catch (error: unknown) {
      setApiMessage(prev => ({ ...prev, [provider]: errMsg(error, t('sys.updateFailedMsg')) }));
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

  // 拖拽排序：把 from 位置的模型移动到 to 位置
  const handleReorderModel = (from: number, to: number) => {
    if (from === to || from < 0 || to < 0 || from >= modelList.length || to >= modelList.length) return;
    const newList = [...modelList];
    const [moved] = newList.splice(from, 1);
    newList.splice(to, 0, moved);
    setModelList(newList);
  };

  const handleSaveModelPriority = async () => {
    setSavingModels(true);
    setModelMessage(null);
    try {
      // 发送完整模型顺序（含自定义 Provider），后端会分别保存内置与自定义 Provider 的顺序
      const modelPriority = modelList.map(m => m.name);
      await papersApi.updateSettings({ model_priority: modelPriority });
      setModelMessage(okMsg(t('sys.orderSaved')));
      fetchSettings();
    } catch (error: unknown) {
      setModelMessage(errMsg(error, t('sys.saveFailed')));
    } finally {
      setSavingModels(false);
    }
  };

  const handleToggleScheduler = async () => {
    setTogglingScheduler(true);
    try {
      const res = await papersApi.toggleScheduler();
      setSchedulerRunning(res.running);
      setMessage(okMsg(res.running ? t('sys.running') : t('sys.stopped')));
    } catch (error) {
      console.error('Error toggling scheduler:', error);
      setMessage(errMsg(error, t('sys.schedulerToggleFailed')));
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
      setMessage(errMsg(error, t('sys.schedulerToggleFailed')));
    } finally {
      setTriggeringJob(null);
    }
  };

  const handleCleanup = async () => {
    setCleaning(true);
    setCleanupResult(null);
    setCleanupMessage(null);
    try {
      const res = await papersApi.cleanupData();
      setCleanupResult(res);
      setCleanupMessage(okMsg(t('sys.cleanupDone')));
      fetchData();
    } catch (error: unknown) {
      setCleanupMessage(errMsg(error, t('sys.cleanupFailed')));
    } finally {
      setCleaning(false);
      setConfirm(null);
    }
  };

  const handleSaveCnkiPrefix = async () => {
    const value = cnkiPrefixDraft.trim();
    if (value && !/^https?:\/\//.test(value)) {
      setCnkiPrefixMessage({ ok: false, text: t('sys.cnkiPrefixInvalid') });
      return;
    }
    setSavingCnkiPrefix(true);
    setCnkiPrefixMessage(null);
    try {
      await papersApi.updateSettings({ cnki_url_prefix: value });
      setCnkiUrlPrefix(value);
      setCnkiPrefixDraft(value);
      setCnkiPrefixMessage(okMsg(t('sys.cnkiPrefixSaved')));
      fetchData();
    } catch (error: unknown) {
      setCnkiPrefixMessage(errMsg(error, t('sys.saveFailed')));
    } finally {
      setSavingCnkiPrefix(false);
    }
  };

  const handleUpdatePorts = async () => {
    const invalid = (p: number) => !Number.isInteger(p) || p < 1 || p > 65535;
    if (invalid(ports.backend) || invalid(ports.frontend)) {
      setPortMessage({ ok: false, text: t('sys.portInvalid') });
      return;
    }
    if (ports.backend === ports.frontend) {
      setPortMessage({ ok: false, text: t('sys.portConflict') });
      return;
    }
    setSavingPorts(true);
    setPortMessage(null);
    try {
      await papersApi.updateSettings({ ports: { backend_port: ports.backend, frontend_port: ports.frontend } });
      setPortMessage(okMsg(t('sys.portSaved')));
    } catch (error: unknown) {
      setPortMessage(errMsg(error, t('sys.saveFailed')));
    } finally {
      setSavingPorts(false);
    }
  };

  // 一键重启：触发后端执行 start.sh restart（前后端一起重启），轮询 /health 恢复后自动刷新页面
  const handleRestartService = async () => {
    setRestarting(true);
    setConfirm(null);
    setPortMessage(null);
    try {
      await papersApi.restartServices();
    } catch {
      // 网络中断（进程已被杀）也视为已触发
    }
    setPortMessage({ ok: true, text: t('sys.restartTriggered') });
    const started = Date.now();
    const timer = setInterval(async () => {
      try {
        const res = await fetch('/health');
        if (res.ok) {
          clearInterval(timer);
          setPortMessage({ ok: true, text: t('sys.restartDone') });
          setTimeout(() => window.location.reload(), 800);
          return;
        }
      } catch { /* 服务重启中 */ }
      if (Date.now() - started > 120000) {
        clearInterval(timer);
        setRestarting(false);
        setPortMessage({ ok: false, text: t('sys.restartTimeout') });
      }
    }, 2000);
  };

  const handleSaveAppName = async () => {
    if (!appInfo.name.trim()) {
      setAppNameMessage({ ok: false, text: t('sys.appNameLabel') });
      return;
    }
    setSavingAppName(true);
    setAppNameMessage(null);
    try {
      await papersApi.updateSettings({ app_name: appInfo.name.trim() });
      setAppNameMessage(okMsg(t('sys.appNameSaved')));
      setEditingAppName(false);
      fetchData();
    } catch (error: unknown) {
      setAppNameMessage(errMsg(error, t('sys.saveFailed')));
    } finally {
      setSavingAppName(false);
    }
  };

  const handleStartEditAppName = () => setEditingAppName(true);

  const handleEditAppNameChange = (name: string) => setAppInfo(prev => ({ ...prev, name }));

  const handleCancelEditAppName = () => {
    setEditingAppName(false);
    setAppInfo(prev => ({ ...prev, name: stats?.app_name || settingsInfo?.app_name || '' }));
    setAppNameMessage(null);
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
    setCustomProviderMessage(null);
  };

  const handleCancelEditProvider = () => {
    setNewProvider({ name: '', base_url: '', api_key: '', models: '' });
    setEditingProviderName(null);
    setCustomProviderMessage(null);
  };

  const handleSaveCustomProvider = async () => {
    const name = newProvider.name.trim();
    const base_url = newProvider.base_url.trim();
    if (!name || !base_url) {
      setCustomProviderMessage({ ok: false, text: t('sys.providerNameRequired') });
      return;
    }
    if (!/^https?:\/\//.test(base_url)) {
      setCustomProviderMessage({ ok: false, text: t('sys.cnkiPrefixInvalid') });
      return;
    }
    // 新增时必须提供 API Key；编辑时可留空（保留原 Key）
    if (!editingProviderName && !newProvider.api_key.trim()) {
      setCustomProviderMessage({ ok: false, text: t('sys.providerKeyRequired') });
      return;
    }
    setSavingCustomProvider(true);
    setCustomProviderMessage(null);
    try {
      const models = newProvider.models.split(',').map(m => m.trim()).filter(m => m);
      const renamed = editingProviderName && editingProviderName !== name;
      const updatedProviders: Array<{ name: string; base_url: string; api_key: string; models: string[]; previous_name?: string }> = [
        // 编辑改名时同时剔除新旧两个名字，避免旧条目残留造成"复制"
        ...customProviders.filter(p => p.name !== name && p.name !== editingProviderName),
        {
          name,
          base_url,
          api_key: newProvider.api_key.trim(),
          models,
          // 改名时携带原名，后端按原名继承已存的 API Key
          ...(renamed && editingProviderName ? { previous_name: editingProviderName } : {}),
        },
      ];
      await papersApi.updateSettings({ custom_providers: updatedProviders });
      setCustomProviderMessage(okMsg(editingProviderName ? t('sys.providerUpdated') : t('sys.providerAdded')));
      handleCancelEditProvider();
      fetchSettings();
    } catch (error: unknown) {
      setCustomProviderMessage(errMsg(error, t('sys.saveFailed')));
    } finally {
      setSavingCustomProvider(false);
    }
  };

  const handleDeleteCustomProvider = async (name: string) => {
    setSavingCustomProvider(true);
    setCustomProviderMessage(null);
    try {
      const updatedProviders = customProviders.filter(p => p.name !== name);
      await papersApi.updateSettings({ custom_providers: updatedProviders });
      setCustomProviderMessage(okMsg(t('sys.providerDeleteMsg', { name })));
      fetchSettings();
    } catch (error: unknown) {
      setCustomProviderMessage(errMsg(error, t('sys.deleteFailed')));
    } finally {
      setSavingCustomProvider(false);
      setConfirm(null);
    }
  };

  const handleSetDefaultModel = async (model: string) => {
    setSavingDefaultModel(true);
    setDefaultModelMessage(null);
    try {
      await papersApi.updateSettings({ default_model: model });
      setDefaultModel(model);
      setDefaultModelMessage(okMsg(t('sys.defaultSaved')));
    } catch (error: unknown) {
      setDefaultModelMessage(errMsg(error, t('sys.defaultSaveFailed')));
    } finally {
      setSavingDefaultModel(false);
    }
  };

  const handleClearDefaultModel = async () => {
    setSavingDefaultModel(true);
    setDefaultModelMessage(null);
    try {
      // 空字符串 = 清除（后端与"未传字段"区分）
      await papersApi.updateSettings({ default_model: '' });
      setDefaultModel(null);
      setDefaultModelMessage(okMsg(t('sys.defaultSaved')));
    } catch (error: unknown) {
      setDefaultModelMessage(errMsg(error, t('sys.defaultSaveFailed')));
    } finally {
      setSavingDefaultModel(false);
    }
  };

  const handleSaveEmbeddingModel = async () => {
    const value = embeddingModelDraft.trim();
    setSavingEmbeddingModel(true);
    setEmbeddingModelMessage(null);
    try {
      // 空字符串 = 清除（后端与"未传字段"区分）
      await papersApi.updateSettings({ embedding_model: value });
      setEmbeddingModel(value || null);
      setEmbeddingModelMessage(okMsg(t('sys.embeddingSaved')));
    } catch (error: unknown) {
      setEmbeddingModelMessage(errMsg(error, t('sys.embeddingSaveFailed')));
    } finally {
      setSavingEmbeddingModel(false);
    }
  };

  const handleToggleAgent = async () => {
    const next = !agentEnabled;
    setSavingAgent(true);
    setAgentMessage(null);
    try {
      await papersApi.updateSettings({ agent_enabled: next });
      setAgentEnabled(next);
      setAgentMessage(okMsg(t('sys.saved')));
    } catch (error: unknown) {
      console.error('Error toggling agent:', error);
      setAgentMessage(errMsg(error, t('sys.agentSaveFailed')));
    } finally {
      setSavingAgent(false);
    }
  };

  const handleTestModelLink = async (model: string) => {
    setTestingModel(model);
    setTestResults(prev => ({ ...prev, [model]: prev[model] || { ok: false, message: '' } }));
    try {
      const res = await papersApi.testModelLink(model);
      setTestResults(prev => ({ ...prev, [model]: res }));
    } catch (error: unknown) {
      setTestResults(prev => ({
        ...prev,
        [model]: { ok: false, message: error instanceof ApiError ? (error.detail || error.message) : (error as Error)?.message || t('sys.testFailed') },
      }));
    } finally {
      setTestingModel('');
    }
  };

  const handleFetchModels = async () => {
    const base_url = newProvider.base_url.trim();
    if (!base_url) {
      setCustomProviderMessage({ ok: false, text: t('sys.fetchModelsNeedUrl') });
      return;
    }
    setFetchingModels(true);
    setCustomProviderMessage(null);
    try {
      const res = await papersApi.fetchProviderModels({
        name: newProvider.name.trim() || undefined,
        base_url,
        api_key: newProvider.api_key.trim() || undefined,
      });
      if (res.models && res.models.length > 0) {
        const ids = res.models;
        setNewProvider(prev => ({ ...prev, models: ids.join(', ') }));
        setCustomProviderMessage(okMsg(t('sys.fetchModelsOk', { n: ids.length })));
      } else {
        setCustomProviderMessage({ ok: false, text: res.message || t('sys.fetchModelsEmpty') });
      }
    } catch (error: unknown) {
      setCustomProviderMessage(errMsg(error, t('sys.fetchModelsFailed')));
    } finally {
      setFetchingModels(false);
    }
  };

  // 配置导出：下载含明文 Key 的 JSON 备份
  const handleExportConfig = async () => {
    try {
      const data = await papersApi.exportSettings();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `paperpulse-config-${new Date().toISOString().slice(0, 10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error: unknown) {
      setCustomProviderMessage(errMsg(error, t('sys.importFailed')));
    }
  };

  // 配置导入：解析文件后弹确认，确认后应用
  const handleImportConfigFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const data = JSON.parse(String(reader.result));
        if (typeof data !== 'object' || data === null || Array.isArray(data)) throw new Error('invalid');
        setConfirm({ type: 'import', data });
      } catch {
        setCustomProviderMessage({ ok: false, text: t('sys.importInvalid') });
      }
    };
    reader.readAsText(file);
  };

  const applyImportConfig = async (data: ExportedSettings) => {
    setImporting(true);
    try {
      await papersApi.updateSettings({
        ...(data.api_keys ? { api_keys: data.api_keys } : {}),
        ...(data.custom_providers ? { custom_providers: data.custom_providers } : {}),
        ...(data.ports ? { ports: { backend_port: data.ports.backend_port, frontend_port: data.ports.frontend_port } } : {}),
        ...(data.default_model !== undefined ? { default_model: data.default_model ?? '' } : {}),
        ...(data.embedding_model !== undefined ? { embedding_model: data.embedding_model ?? '' } : {}),
        ...(data.app_name !== undefined ? { app_name: data.app_name } : {}),
        ...(data.cnki_url_prefix !== undefined ? { cnki_url_prefix: data.cnki_url_prefix } : {}),
        ...(data.agent_enabled !== undefined ? { agent_enabled: data.agent_enabled } : {}),
        ...(data.ai_model_prices !== undefined ? { ai_model_prices: data.ai_model_prices } : {}),
      });
      setCustomProviderMessage(okMsg(t('sys.importOk')));
      fetchSettings();
      fetchData();
    } catch (error: unknown) {
      setCustomProviderMessage(errMsg(error, t('sys.importFailed')));
    } finally {
      setImporting(false);
      setConfirm(null);
    }
  };

  // AI 模型单价保存（成本估算）；返回错误文案供 DataTab 展示
  const handleSaveAiModelPrices = async (prices: Record<string, number>): Promise<string | null> => {
    try {
      await papersApi.updateSettings({ ai_model_prices: prices });
      fetchSettings();
      return null;
    } catch (error: unknown) {
      return errMsg(error, t('sys.aiCostPricesInvalid'))?.text ?? t('sys.aiCostPricesInvalid');
    }
  };

  const tabs: { key: TabType; label: string; icon: React.ReactNode }[] = [
    { key: 'overview', label: t('systemTab.overview'), icon: <Activity className="w-4 h-4" /> },
    { key: 'crawler', label: t('systemTab.crawler'), icon: <Settings className="w-4 h-4" /> },
    { key: 'data', label: t('systemTab.data'), icon: <Database className="w-4 h-4" /> },
    { key: 'modelConfig', label: t('systemTab.modelConfig'), icon: <Brain className="w-4 h-4" /> },
    { key: 'logs', label: t('systemTab.logs'), icon: <ScrollText className="w-4 h-4" /> },
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
            onRerunTask={handleRerunTask}
            rerunningLogId={rerunningLogId}
            kwInfo={kwInfo}
            kwStarting={kwStarting}
            kwStopping={kwStopping}
            kwForm={kwForm}
            setKwForm={setKwForm}
            onStartKeywordCrawl={handleStartKeywordCrawl}
            onPauseKeywordCrawl={handlePauseKeywordCrawl}
            onResumeKeywordCrawl={handleResumeKeywordCrawl}
            onStopKeywordCrawl={handleStopKeywordCrawl}
          />
        );
      case 'data':
        return (
          <DataTab
            stats={stats}
            cleaning={cleaning}
            cleanupMessage={cleanupMessage}
            cleanupResult={cleanupResult}
            onCleanup={() => setConfirm({ type: 'cleanup' })}
            aiModelPrices={aiModelPrices}
            onSaveAiModelPrices={handleSaveAiModelPrices}
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
            onDeleteCustomProvider={(name) => setConfirm({ type: 'deleteProvider', name })}
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
            onReorderModel={handleReorderModel}
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
            agentEnabled={agentEnabled}
            savingAgent={savingAgent}
            agentMessage={agentMessage}
            onToggleAgent={handleToggleAgent}
            fetchingModels={fetchingModels}
            onFetchModels={handleFetchModels}
            onExportConfig={handleExportConfig}
            onImportConfig={handleImportConfigFile}
            onRestartService={() => setConfirm({ type: 'restart' })}
          />
        );
      case 'logs':
        return <LogsTab />;
    }
  };

  return (
    <Layout>
      <div className="mb-6 sm:mb-8">
        <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white mb-2">{t('system.title')}</h1>
        <p className="text-sm sm:text-base text-gray-600 dark:text-gray-400">{t('system.subtitle')}</p>
      </div>

      <div className="border-b border-gray-200 dark:border-gray-700 mb-4 sm:mb-6 overflow-x-auto" role="tablist">
        <nav className="flex gap-4 sm:gap-6 min-w-max">
          {tabs.map(tab => (
            <button
              key={tab.key}
              role="tab"
              aria-selected={activeTab === tab.key}
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

      {/* 统一确认弹窗（替代原生 confirm） */}
      <ConfirmModal
        open={confirm?.type === 'cleanup'}
        title={t('sys.cleanupConfirm')}
        description={t('sys.cleanupDesc')}
        danger
        confirming={cleaning}
        onConfirm={handleCleanup}
        onCancel={() => setConfirm(null)}
      />
      <ConfirmModal
        open={confirm?.type === 'deleteProvider'}
        title={t('sys.confirmDeleteProvider', { name: confirm?.type === 'deleteProvider' ? confirm.name : '' })}
        description={t('sys.confirmDeleteProviderDesc')}
        danger
        confirming={savingCustomProvider}
        onConfirm={() => confirm?.type === 'deleteProvider' && handleDeleteCustomProvider(confirm.name)}
        onCancel={() => setConfirm(null)}
      />
      <ConfirmModal
        open={confirm?.type === 'import'}
        title={t('sys.importConfig')}
        description={t('sys.importConfigConfirm')}
        danger
        confirming={importing}
        onConfirm={() => confirm?.type === 'import' && applyImportConfig(confirm.data)}
        onCancel={() => setConfirm(null)}
      />
      <ConfirmModal
        open={confirm?.type === 'restart'}
        title={t('sys.restartConfirm')}
        description={t('sys.restartConfirmDesc')}
        danger
        confirming={restarting}
        onConfirm={handleRestartService}
        onCancel={() => setConfirm(null)}
      />
    </Layout>
  );
}
