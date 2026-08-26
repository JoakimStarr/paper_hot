'use client';

import {
  Settings, Activity, Play, Loader2, CheckCircle, XCircle, RefreshCw, AlertCircle,
  ToggleRight, ToggleLeft, Search,
} from 'lucide-react';
import { CrawlLog, SchedulerJob, CNKISearchInfo } from '@/types/paper';
import { useLanguage } from '@/contexts/LanguageContext';

export interface KeywordCrawlForm {
  keyword: string;
  search_field: string;
  years: string;
  max_pages: string;
}

interface CrawlerTabProps {
  message: string;
  crawling: boolean;
  cnkiCrawling: 'top50' | 'navi' | null;
  onStartCrawl: () => void;
  onCNKICrawl: (kind: 'top50' | 'navi') => void;
  schedulerRunning: boolean;
  schedulerJobs: SchedulerJob[];
  togglingScheduler: boolean;
  triggeringJob: string | null;
  onToggleScheduler: () => void;
  onTriggerJob: (jobId: string) => void;
  crawlLogs: CrawlLog[];
  onRefresh: () => void;
  kwInfo: CNKISearchInfo | null;
  kwStarting: boolean;
  kwForm: KeywordCrawlForm;
  setKwForm: (form: KeywordCrawlForm) => void;
  onStartKeywordCrawl: () => void;
}

export default function CrawlerTab({
  message,
  crawling,
  cnkiCrawling,
  onStartCrawl,
  onCNKICrawl,
  schedulerRunning,
  schedulerJobs,
  togglingScheduler,
  triggeringJob,
  onToggleScheduler,
  onTriggerJob,
  crawlLogs,
  onRefresh,
  kwInfo,
  kwStarting,
  kwForm,
  setKwForm,
  onStartKeywordCrawl,
}: CrawlerTabProps) {
  const { t } = useLanguage();

  const formatTime = (dateStr: string | null) => {
    if (!dateStr) return '-';
    const safeStr = (/[Zz]$/.test(dateStr) || /[+\-]\d{2}:\d{2}$/.test(dateStr)) ? dateStr : dateStr + 'Z';
    return new Date(safeStr).toLocaleString('zh-CN');
  };

  return (
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
            onClick={onStartCrawl}
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
              onClick={() => onCNKICrawl('top50')}
              disabled={cnkiCrawling !== null}
              className="flex items-center justify-center gap-2 px-4 py-2.5 border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 text-amber-800 dark:text-amber-300 text-sm rounded-lg hover:bg-amber-100 dark:hover:bg-amber-900/40 disabled:opacity-50 transition-colors"
              title={t('sys.cnkiTop50Title')}
            >
              {cnkiCrawling === 'top50' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              {t('sys.cnkiTop50')}
            </button>
            <button
              onClick={() => onCNKICrawl('navi')}
              disabled={cnkiCrawling !== null}
              className="flex items-center justify-center gap-2 px-4 py-2.5 border border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 text-amber-800 dark:text-amber-300 text-sm rounded-lg hover:bg-amber-100 dark:hover:bg-amber-900/40 disabled:opacity-50 transition-colors"
              title={t('sys.cnkiNaviTitle')}
            >
              {cnkiCrawling === 'navi' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              {t('sys.cnkiNavi')}
            </button>
          </div>

          {message && (
            <div className={`p-3 rounded-lg text-sm ${message.includes('失败') ? 'bg-red-50 dark:bg-red-900/30 text-red-600' : 'bg-green-50 dark:bg-green-900/30 text-green-600'}`}>
              {message}
            </div>
          )}
          <div className="mt-4 flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
            <AlertCircle className="w-4 h-4" />
            {t('sys.crawlHint')}
          </div>
        </div>

        {/* 关键词检索爬取 */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
          <div className="flex items-center gap-3 mb-2">
            <Search className="w-6 h-6 text-blue-600" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{t('sys.cnkiKeywordTitle')}</h2>
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">{t('sys.cnkiKeywordDesc')}</p>

          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">{t('sys.kwKeywordLabel')}</label>
              <input
                value={kwForm.keyword}
                onChange={e => setKwForm({ ...kwForm, keyword: e.target.value })}
                placeholder="供应链韧性"
                disabled={kwStarting || !!kwInfo?.running}
                className="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
              />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">{t('sys.kwFieldLabel')}</label>
                <select
                  value={kwForm.search_field}
                  onChange={e => setKwForm({ ...kwForm, search_field: e.target.value })}
                  disabled={kwStarting || !!kwInfo?.running}
                  className="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                >
                  <option value="主题">{t('sys.kwFieldTheme')}</option>
                  <option value="篇名">{t('sys.kwFieldTitle')}</option>
                  <option value="关键词">{t('sys.kwFieldKeyword')}</option>
                  <option value="作者">{t('sys.kwFieldAuthor')}</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">{t('sys.kwYearLabel')}</label>
                <input
                  value={kwForm.years}
                  onChange={e => setKwForm({ ...kwForm, years: e.target.value })}
                  placeholder={t('sys.kwYearPlaceholder')}
                  disabled={kwStarting || !!kwInfo?.running}
                  className="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">{t('sys.kwPagesLabel')}</label>
                <input
                  value={kwForm.max_pages}
                  onChange={e => setKwForm({ ...kwForm, max_pages: e.target.value.replace(/\D/g, '') })}
                  type="text"
                  inputMode="numeric"
                  placeholder="—"
                  disabled={kwStarting || !!kwInfo?.running}
                  className="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                />
              </div>
            </div>
            <button
              onClick={onStartKeywordCrawl}
              disabled={kwStarting || !!kwInfo?.running || !kwForm.keyword.trim()}
              className="flex items-center gap-2 w-full justify-center px-4 py-2.5 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
            >
              {kwStarting || kwInfo?.running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              {kwStarting || kwInfo?.running ? t('sys.kwRunning') : t('sys.kwRun')}
            </button>
            {kwInfo && (kwInfo.running || kwInfo.keyword || kwInfo.message) && (
              <div className="mt-2 p-3 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 text-xs text-gray-700 dark:text-gray-200 space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-gray-500 dark:text-gray-400">{t('sys.kwStatus')}:</span>
                  <span className={`inline-flex items-center gap-1 font-medium ${kwInfo.running ? 'text-blue-600' : 'text-green-600'}`}>
                    {kwInfo.running && <Loader2 className="w-3 h-3 animate-spin" />}
                    {kwInfo.running ? t('sys.kwRunningBadge') : t('sys.simIdle')}
                  </span>
                </div>
                {kwInfo.keyword && (
                  <div><span className="text-gray-500 dark:text-gray-400">{t('sys.kwKeywordHint')}:</span> <span className="font-medium">{kwInfo.keyword}</span></div>
                )}
                {kwInfo.message && <div className="text-gray-600 dark:text-gray-300 break-words">{kwInfo.message}</div>}
              </div>
            )}
          </div>
        </div>

        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-3">
              <Activity className="w-6 h-6 text-primary-600" />
              <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{t('sys.schedulerControl')}</h2>
            </div>
            <button
              onClick={onToggleScheduler}
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
                      {job.trigger} · {t('sys.nextRun')}: {job.next_run_time ? formatTime(job.next_run_time) : t('sys.noneLabel')}
                    </div>
                  </div>
                  <button
                    onClick={() => onTriggerJob(job.id)}
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
          <button onClick={onRefresh} className="p-2 hover:bg-gray-100 dark:bg-gray-700 rounded-lg transition-colors">
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
}