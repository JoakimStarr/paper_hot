'use client';

import { useState } from 'react';
import {
  Settings, Activity, Play, Pause, Square, ChevronDown, Loader2, CheckCircle, XCircle, RefreshCw, AlertCircle,
  ToggleRight, ToggleLeft, Search, History as HistoryIcon,
} from 'lucide-react';
import { CrawlLog, SchedulerJob, CNKISearchInfo, Msg } from '@/types/paper';
import { useLanguage } from '@/contexts/LanguageContext';

export interface KeywordCrawlForm {
  keyword: string;
  search_field: string;
  years: string;
  max_pages: string;
  detail_workers: string;
  show_browser: boolean;
}

// CNKI 检索字段全集（value 即知网站点字段名，后端/爬虫按此匹配，与 cnki_paper_captcha.py CNKI_SEARCH_FIELDS 保持一致）
const CNKI_SEARCH_FIELDS: { value: string; labelKey: string }[] = [
  { value: '主题', labelKey: 'sys.kwFieldTheme' },
  { value: '篇关摘', labelKey: 'sys.kwFieldTka' },
  { value: '关键词', labelKey: 'sys.kwFieldKeyword' },
  { value: '篇名', labelKey: 'sys.kwFieldTitle' },
  { value: '全文', labelKey: 'sys.kwFieldFullText' },
  { value: '作者', labelKey: 'sys.kwFieldAuthor' },
  { value: '第一作者', labelKey: 'sys.kwFieldFirstAuthor' },
  { value: '通讯作者', labelKey: 'sys.kwFieldCorrespondingAuthor' },
  { value: '作者单位', labelKey: 'sys.kwFieldAffiliation' },
  { value: '基金', labelKey: 'sys.kwFieldFund' },
  { value: '摘要', labelKey: 'sys.kwFieldAbstract' },
  { value: '小标题', labelKey: 'sys.kwFieldSubtitle' },
  { value: '参考文献', labelKey: 'sys.kwFieldReferences' },
  { value: '分类号', labelKey: 'sys.kwFieldClassification' },
  { value: '文献来源', labelKey: 'sys.kwFieldSource' },
  { value: 'DOI', labelKey: 'sys.kwFieldDoi' },
];

interface CrawlerTabProps {
  message: Msg;
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
  onRerunTask: (log: CrawlLog) => void;
  rerunningLogId: number | null;
  kwInfo: CNKISearchInfo | null;
  kwStarting: boolean;
  kwStopping: boolean;
  kwForm: KeywordCrawlForm;
  setKwForm: (form: KeywordCrawlForm) => void;
  onStartKeywordCrawl: () => void;
  onPauseKeywordCrawl: () => void;
  onResumeKeywordCrawl: () => void;
  onStopKeywordCrawl: () => void;
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
  onRerunTask,
  rerunningLogId,
  kwInfo,
  kwStarting,
  kwStopping,
  kwForm,
  setKwForm,
  onStartKeywordCrawl,
  onPauseKeywordCrawl,
  onResumeKeywordCrawl,
  onStopKeywordCrawl,
}: CrawlerTabProps) {
  const { t } = useLanguage();
  const [expandedLogId, setExpandedLogId] = useState<number | null>(null);

  const phaseText = (phase?: string) => {
    const map: Record<string, string> = {
      starting: t('sys.kwPhaseStarting'),
      collecting: t('sys.kwPhaseCollecting'),
      collecting_check: t('sys.kwPhaseCollecting'),
      details: t('sys.kwPhaseDetails'),
      detail: t('sys.kwPhaseDetails'),
      collect: t('sys.kwPhaseCollecting'),
      done: t('sys.kwPhaseDone'),
      stopped: t('sys.kwPhaseStopped'),
    };
    return phase ? (map[phase] || phase) : '';
  };

  // 断点信息：非运行状态下展示上次进度；关键词与表单一致时启动按钮变为「从断点继续」
  const ckpt = kwInfo?.checkpoint;
  const resumable = !kwInfo?.running && !!ckpt && ckpt.keyword === kwForm.keyword.trim();

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
            <div className={`p-3 rounded-lg text-sm ${message.ok ? 'bg-green-50 dark:bg-green-900/30 text-green-600' : 'bg-red-50 dark:bg-red-900/30 text-red-600'}`}>
              {message.text}
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

          {/* 断点提示条：上次任务被停止/中断后，同关键词启动自动从断点续跑 */}
          {!kwInfo?.running && ckpt && (
            <div className="mb-3 flex items-start gap-2 p-3 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 text-xs text-amber-700 dark:text-amber-300">
              <HistoryIcon className="w-4 h-4 shrink-0 mt-0.5" />
              <span>
                {t('sys.kwCheckpointHint', { keyword: ckpt.keyword, page: ckpt.page, papers: ckpt.papers, phase: phaseText(ckpt.phase) })}
                {ckpt.saved_at ? ` (${ckpt.saved_at.replace('T', ' ')})` : ''}
              </span>
            </div>
          )}

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
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">{t('sys.kwFieldLabel')}</label>
                <select
                  value={kwForm.search_field}
                  onChange={e => setKwForm({ ...kwForm, search_field: e.target.value })}
                  disabled={kwStarting || !!kwInfo?.running}
                  className="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                >
                  {CNKI_SEARCH_FIELDS.map(f => (
                    <option key={f.value} value={f.value}>{t(f.labelKey)}</option>
                  ))}
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
              <div>
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1" title={t('sys.kwThreadsHint')}>
                  {t('sys.kwThreadsLabel')}
                </label>
                <select
                  value={kwForm.detail_workers}
                  onChange={e => setKwForm({ ...kwForm, detail_workers: e.target.value })}
                  title={t('sys.kwThreadsHint')}
                  disabled={kwStarting || !!kwInfo?.running}
                  className="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
                >
                  {[1, 2, 3, 4, 6, 8].map(n => (
                    <option key={n} value={String(n)}>{n}</option>
                  ))}
                </select>
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={kwForm.show_browser}
                onChange={e => setKwForm({ ...kwForm, show_browser: e.target.checked })}
                disabled={kwStarting || !!kwInfo?.running}
                className="w-4 h-4 accent-blue-600 disabled:opacity-50"
              />
              {t('sys.kwShowBrowser')}
            </label>
            <button
              onClick={onStartKeywordCrawl}
              disabled={kwStarting || !!kwInfo?.running || !kwForm.keyword.trim()}
              className={`flex items-center gap-2 w-full justify-center px-4 py-2.5 text-white text-sm rounded-lg disabled:opacity-50 transition-colors ${
                resumable ? 'bg-amber-600 hover:bg-amber-700' : 'bg-blue-600 hover:bg-blue-700'
              }`}
            >
              {kwStarting || kwInfo?.running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              {kwStarting || kwInfo?.running ? t('sys.kwRunning') : (resumable ? t('sys.kwResumeRun') : t('sys.kwRun'))}
            </button>
            {kwInfo && (kwInfo.running || kwInfo.keyword || kwInfo.message) && (
              <div className="mt-2 p-3 rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 text-xs text-gray-700 dark:text-gray-200 space-y-1">
                <div className="flex items-center gap-2">
                  <span className="text-gray-500 dark:text-gray-400">{t('sys.kwStatus')}:</span>
                  <span className={`inline-flex items-center gap-1 font-medium ${
                    kwInfo.running
                      ? (kwInfo.paused ? 'text-amber-600' : 'text-blue-600')
                      : (kwInfo.progress && (kwInfo.progress.phase === 'done' || kwInfo.progress.phase === 'stopped')
                          ? 'text-gray-600 dark:text-gray-300'
                          : 'text-green-600')
                  }`}>
                    {kwInfo.running && !kwInfo.paused && <Loader2 className="w-3 h-3 animate-spin" />}
                    {kwInfo.running
                      ? (kwInfo.paused ? t('sys.kwPausedBadge') : t('sys.kwRunningBadge'))
                      : (kwInfo.progress && (kwInfo.progress.phase === 'done' || kwInfo.progress.phase === 'stopped')
                          ? phaseText(kwInfo.progress.phase)
                          : t('sys.simIdle'))}
                  </span>
                  {kwInfo.running && (
                    <span className="flex items-center gap-1 ml-auto">
                      {kwInfo.paused ? (
                        <button
                          onClick={onResumeKeywordCrawl}
                          disabled={kwStopping}
                          className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium bg-green-600 text-white rounded hover:bg-green-700 disabled:opacity-50 transition-colors"
                        >
                          <Play className="w-3 h-3" />
                          {t('sys.kwResume')}
                        </button>
                      ) : (
                        <button
                          onClick={onPauseKeywordCrawl}
                          disabled={kwStopping}
                          className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium bg-amber-500 text-white rounded hover:bg-amber-600 disabled:opacity-50 transition-colors"
                        >
                          <Pause className="w-3 h-3" />
                          {t('sys.kwPause')}
                        </button>
                      )}
                      <button
                        onClick={onStopKeywordCrawl}
                        disabled={kwStopping}
                        className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50 transition-colors"
                        title={t('sys.kwStop')}
                      >
                        {kwStopping ? <Loader2 className="w-3 h-3 animate-spin" /> : <Square className="w-3 h-3" />}
                        {t('sys.kwStop')}
                      </button>
                    </span>
                  )}
                </div>
                {kwInfo.keyword && (
                  <div><span className="text-gray-500 dark:text-gray-400">{t('sys.kwKeywordHint')}:</span> <span className="font-medium">{kwInfo.keyword}</span></div>
                )}
                {kwInfo.progress && (kwInfo.progress.phase !== 'starting' || kwInfo.progress.page > 0 || kwInfo.progress.collected > 0 || kwInfo.progress.done > 0) && (
                  <div className="pt-2 mt-1 border-t border-blue-100 dark:border-blue-800/40 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-gray-500 dark:text-gray-400">
                        {t('sys.kwPhaseLabel')}: <b className="text-gray-700 dark:text-gray-200">{phaseText(kwInfo.progress.phase)}</b>
                      </span>
                      <span className="text-gray-500 dark:text-gray-400">{kwInfo.progress.done} / {kwInfo.progress.total}</span>
                    </div>
                    {kwInfo.progress.total > 0 && (
                      <div className="h-2 w-full bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-blue-500 rounded-full transition-all"
                          style={{ width: `${Math.min(100, Math.round((kwInfo.progress.done / kwInfo.progress.total) * 100))}%` }}
                        />
                      </div>
                    )}
                    <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-gray-500 dark:text-gray-400">
                      {kwInfo.progress.page > 0 && <span>{t('sys.kwPage')}: {kwInfo.progress.page}</span>}
                      {kwInfo.progress.collected > 0 && <span>{t('sys.kwCollected')}: {kwInfo.progress.collected}</span>}
                      {kwInfo.progress.ok > 0 && <span className="text-green-600 dark:text-green-400">{t('sys.kwOk')}: {kwInfo.progress.ok}</span>}
                      {kwInfo.progress.already_exists > 0 && <span>{t('sys.kwAlreadyExists')}: {kwInfo.progress.already_exists}</span>}
                      {kwInfo.progress.filtered > 0 && <span>{t('sys.kwFiltered')}: {kwInfo.progress.filtered}</span>}
                      {kwInfo.progress.failed > 0 && <span className="text-red-500">{t('sys.kwFailed')}: {kwInfo.progress.failed}</span>}
                    </div>
                  </div>
                )}
                {kwInfo.last_log && kwInfo.last_log.length > 0 && (
                  <div className="pt-1">
                    <div className="text-[11px] text-gray-400 mb-1">{t('sys.kwRecentLog')}</div>
                    <div className="max-h-24 overflow-y-auto rounded-md bg-gray-50 dark:bg-gray-900/60 p-2 text-[10px] leading-4 text-gray-500 dark:text-gray-400 font-mono break-all">
                      {kwInfo.last_log.slice(-6).map((l, i) => <div key={i}>{l}</div>)}
                    </div>
                  </div>
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
              {crawlLogs.map((log) => {
                const expanded = expandedLogId === log.id;
                const isKeyword = log.task_type === 'keyword';
                const done = log.status === 'success' || log.status === 'completed';
                return (
                  <div key={log.id} className="border border-gray-100 dark:border-gray-700 rounded-lg">
                    <div
                      className="flex items-center justify-between gap-2 p-3 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/40 transition-colors"
                      onClick={() => setExpandedLogId(expanded ? null : log.id)}
                      title={t('sys.taskLog')}
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <ChevronDown className={`w-3.5 h-3.5 text-gray-400 flex-shrink-0 transition-transform ${expanded ? '' : '-rotate-90'}`} />
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-gray-700 dark:text-gray-300 truncate">{log.journal_name}</span>
                            {isKeyword && (
                              <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-300">{t('sys.kwKeywordLabel')}</span>
                            )}
                          </div>
                          <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
                            <span>{t('sys.fetchedLabel')}: {log.papers_fetched}{t('sys.papersUnit')}</span>
                            {log.papers_failed > 0 && <span className="text-red-500">{t('sys.failedLabel')}: {log.papers_failed}{t('sys.papersUnit')}</span>}
                            <span>{formatTime(log.created_at)}</span>
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${
                          done
                            ? 'bg-green-100 text-green-700'
                            : log.status === 'running'
                            ? 'bg-blue-100 text-blue-700'
                            : log.status === 'stopped'
                            ? 'bg-amber-100 text-amber-700'
                            : 'bg-red-100 text-red-700'
                        }`}>
                          {done ? (
                            <CheckCircle className="w-3 h-3" />
                          ) : log.status === 'running' ? (
                            <Loader2 className="w-3 h-3 animate-spin" />
                          ) : (
                            <XCircle className="w-3 h-3" />
                          )}
                          {log.status}
                        </span>
                        <button
                          onClick={(e) => { e.stopPropagation(); onRerunTask(log); }}
                          disabled={rerunningLogId === log.id || log.status === 'running'}
                          className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium bg-primary-50 dark:bg-primary-900/30 text-primary-700 dark:text-primary-300 rounded-md hover:bg-primary-100 disabled:opacity-50 transition-colors"
                          title={t('sys.taskRerun')}
                        >
                          {rerunningLogId === log.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
                          {t('sys.taskRerun')}
                        </button>
                      </div>
                    </div>
                    {expanded && (
                      <div className="px-3 pb-3 pt-2 border-t border-gray-100 dark:border-gray-700">
                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
                          <span>开始: {formatTime(log.crawl_start_time)}</span>
                          <span>结束: {log.crawl_end_time ? formatTime(log.crawl_end_time) : '-'}</span>
                        </div>
                        {log.error_message && <p className="text-xs text-red-500 mt-1">{log.error_message}</p>}
                        <div className="mt-2">
                          <div className="text-[11px] text-gray-400 mb-1">{t('sys.taskLog')}</div>
                          {log.log_detail ? (
                            <pre className="max-h-48 overflow-y-auto rounded-md bg-gray-50 dark:bg-gray-900/60 p-2 text-[10px] leading-4 text-gray-500 dark:text-gray-400 font-mono whitespace-pre-wrap break-all">
                              {log.log_detail}
                            </pre>
                          ) : (
                            <p className="text-xs text-gray-400">{t('sys.taskNoLog')}</p>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}