'use client';

import { useState } from 'react';
import {
  Settings, Activity, Play, Pause, Square, ChevronDown, Loader2, CheckCircle, XCircle, RefreshCw, AlertCircle,
  ToggleRight, ToggleLeft, Search, History as HistoryIcon, BookOpen,
} from 'lucide-react';
import { CrawlLog, SchedulerJob, CNKISearchInfo, ReferencesCrawlInfo, Msg } from '@/types/paper';
import { useLanguage } from '@/contexts/LanguageContext';
import TaskStatusPanel from './TaskStatusPanel';
import { rememberRefsShowBrowser } from '@/lib/utils';

export interface KeywordCrawlForm {
  keyword: string;
  search_field: string;
  years: string;
  max_pages: string;
  detail_workers: string;
  show_browser: boolean;
  detail_refs: boolean;
}

export interface ReferencesCrawlForm {
  /** 链接 textarea：每行一个详情页链接，多行走批量模式 */
  url: string;
  title: string;
  maxItems: string;
  interval: string;
  showBrowser: boolean;
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
  refsInfo: ReferencesCrawlInfo | null;
  refsStarting: boolean;
  refsStopping: boolean;
  refsForm: ReferencesCrawlForm;
  setRefsForm: (form: ReferencesCrawlForm) => void;
  onStartReferencesCrawl: (opts: { paper_url?: string; urls?: string[]; paper_title?: string; max_items?: number; interval?: number; show_browser?: boolean }) => void;
  onStopReferencesCrawl: () => void;
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
  refsInfo,
  refsStarting,
  refsStopping,
  refsForm,
  setRefsForm,
  onStartReferencesCrawl,
  onStopReferencesCrawl,
}: CrawlerTabProps) {
  const { t } = useLanguage();
  const [expandedLogId, setExpandedLogId] = useState<number | null>(null);
  // 参考文献表单校验：链接每行一个、需 http(s):// 前缀；篇间隔 1~60 秒
  const refUrlLines = refsForm.url.split('\n').map(s => s.trim()).filter(Boolean);
  const refUrlInvalid = refUrlLines.some(u => !/^https?:\/\//i.test(u));
  const refIntervalNum = refsForm.interval.trim() !== '' ? Number(refsForm.interval) : null;
  const refIntervalInvalid = refIntervalNum !== null && (!Number.isFinite(refIntervalNum) || refIntervalNum < 1 || refIntervalNum > 60);
  const refCanStart = !refsStarting && !refsInfo?.running && (refUrlLines.length > 0 || refsForm.title.trim().length > 0) && !refUrlInvalid && !refIntervalInvalid;

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
            <label className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={kwForm.detail_refs}
                onChange={e => {
                  const checked = e.target.checked;
                  // 顺带抓参考文献时每个详情 tab 都可能翻页，自动把并发压到建议值 ≤ 2
                  const autoWorkers = checked && Number(kwForm.detail_workers) > 2 ? '2' : kwForm.detail_workers;
                  setKwForm({ ...kwForm, detail_refs: checked, detail_workers: autoWorkers });
                }}
                disabled={kwStarting || !!kwInfo?.running}
                className="mt-0.5 w-4 h-4 accent-blue-600 disabled:opacity-50"
              />
              <span>
                {t('sys.detailRefsToggle')}
                <span className="block text-[11px] text-gray-400 dark:text-gray-500">{t('sys.detailRefsHint')}</span>
                {kwForm.detail_refs && Number(kwForm.detail_workers) > 2 && (
                  <span className="block text-[11px] text-amber-600 dark:text-amber-400">{t('sys.detailRefsWorkersHint')}</span>
                )}
              </span>
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
              <TaskStatusPanel
                tone="blue"
                running={!!kwInfo.running}
                runningText={kwInfo.paused ? t('sys.kwPausedBadge') : t('sys.kwRunningBadge')}
                idleText={kwInfo.progress && (kwInfo.progress.phase === 'done' || kwInfo.progress.phase === 'stopped')
                  ? phaseText(kwInfo.progress.phase)
                  : t('sys.simIdle')}
                statusLabel={t('sys.kwStatus')}
                title={kwInfo.keyword}
                actions={kwInfo.running ? (
                  <>
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
                  </>
                ) : null}
                children={kwInfo.progress && (kwInfo.progress.phase !== 'starting' || kwInfo.progress.page > 0 || kwInfo.progress.collected > 0 || kwInfo.progress.done > 0) ? (
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
                  </div>
                ) : null}
                metrics={[
                  ...(kwInfo.progress && kwInfo.progress.page > 0 ? [{ label: t('sys.kwPage'), value: kwInfo.progress.page }] : []),
                  ...(kwInfo.progress && kwInfo.progress.collected > 0 ? [{ label: t('sys.kwCollected'), value: kwInfo.progress.collected }] : []),
                  ...(kwInfo.progress && kwInfo.progress.ok > 0 ? [{ label: t('sys.kwOk'), value: kwInfo.progress.ok, tone: 'good' as const }] : []),
                  ...(kwInfo.progress && kwInfo.progress.refs_ok ? [{ label: t('sys.kwRefsDone'), value: kwInfo.progress.refs_ok, tone: 'accent' as const }] : []),
                  ...(kwInfo.progress && kwInfo.progress.refs_failed ? [{ label: t('sys.kwRefsFail'), value: kwInfo.progress.refs_failed, tone: 'bad' as const }] : []),
                  ...(kwInfo.progress && kwInfo.progress.already_exists > 0 ? [{ label: t('sys.kwAlreadyExists'), value: kwInfo.progress.already_exists }] : []),
                  ...(kwInfo.progress && kwInfo.progress.filtered > 0 ? [{ label: t('sys.kwFiltered'), value: kwInfo.progress.filtered }] : []),
                  ...(kwInfo.progress && kwInfo.progress.failed > 0 ? [{ label: t('sys.kwFailed'), value: kwInfo.progress.failed, tone: 'bad' as const }] : []),
                ]}
                log={kwInfo.last_log}
                logTitle={t('sys.kwRecentLog')}
                message={kwInfo.message}
              />
            )}
          </div>
        </div>

        {/* 参考文献爬取 */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
          <div className="flex items-center gap-3 mb-2">
            <BookOpen className="w-6 h-6 text-teal-600" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{t('sys.refsTitle')}</h2>
          </div>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">{t('sys.refsDesc')}</p>

          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">{t('sys.refsUrlLabel')}</label>
              <textarea
                value={refsForm.url}
                onChange={e => setRefsForm({ ...refsForm, url: e.target.value })}
                rows={3}
                placeholder={t('sys.refsBatchPlaceholder')}
                disabled={refsStarting || !!refsInfo?.running}
                className="w-full px-3 py-2 text-xs font-mono border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-teal-500 disabled:opacity-50 break-all"
              />
              {refUrlInvalid && (
                <p className="mt-1 text-[11px] text-red-500">{t('sys.refsUrlInvalid')}</p>
              )}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div className="sm:col-span-2">
                <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">{t('sys.refsTitleLabel')}</label>
                <input
                  value={refsForm.title}
                  onChange={e => setRefsForm({ ...refsForm, title: e.target.value })}
                  placeholder={t('sys.refsTitlePlaceholder')}
                  disabled={refsStarting || !!refsInfo?.running}
                  className="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-teal-500 disabled:opacity-50"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">{t('sys.refsMaxLabel')}</label>
                  <input
                    value={refsForm.maxItems}
                    onChange={e => setRefsForm({ ...refsForm, maxItems: e.target.value.replace(/\D/g, '') })}
                    type="text"
                    inputMode="numeric"
                    placeholder="—"
                    disabled={refsStarting || !!refsInfo?.running}
                    className="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-teal-500 disabled:opacity-50"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-600 dark:text-gray-300 mb-1">{t('sys.refsIntervalLabel')}</label>
                  <input
                    value={refsForm.interval}
                    onChange={e => setRefsForm({ ...refsForm, interval: e.target.value.replace(/[^\d.]/g, '') })}
                    type="text"
                    inputMode="decimal"
                    placeholder="6"
                    disabled={refsStarting || !!refsInfo?.running}
                    className="w-full px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-teal-500 disabled:opacity-50"
                  />
                  {refIntervalInvalid && (
                    <p className="mt-1 text-[11px] text-red-500">{t('sys.refsIntervalInvalid')}</p>
                  )}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => onStartReferencesCrawl({
                  paper_url: refUrlLines.length === 1 ? refUrlLines[0] : undefined,
                  urls: refUrlLines.length > 1 ? refUrlLines : undefined,
                  paper_title: refUrlLines.length ? undefined : refsForm.title.trim(),
                  max_items: refsForm.maxItems ? Number(refsForm.maxItems) : undefined,
                  interval: refsForm.interval.trim() ? Number(refsForm.interval) : undefined,
                  show_browser: refsForm.showBrowser,
                })}
                disabled={!refCanStart}
                className="flex items-center gap-2 px-4 py-2.5 bg-teal-600 text-white text-sm rounded-lg hover:bg-teal-700 disabled:opacity-50 transition-colors"
              >
                {refsStarting || refsInfo?.running ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                {refsStarting || refsInfo?.running ? t('sys.refsRunning') : t('sys.refsRun')}
              </button>
              {refsInfo?.running && (
                <button
                  onClick={onStopReferencesCrawl}
                  disabled={refsStopping}
                  className="flex items-center gap-1 px-3 py-2 text-xs font-medium bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50 transition-colors"
                >
                  {refsStopping ? <Loader2 className="w-3 h-3 animate-spin" /> : <Square className="w-3 h-3" />}
                  {t('sys.kwStop')}
                </button>
              )}
            </div>
            <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={refsForm.showBrowser}
                onChange={e => {
                  // 与论文详情页的抓取开关共用同一份 localStorage 偏好，双页同步
                  setRefsForm({ ...refsForm, showBrowser: e.target.checked });
                  rememberRefsShowBrowser(e.target.checked);
                }}
                disabled={refsStarting || !!refsInfo?.running}
                className="w-4 h-4 accent-teal-600 disabled:opacity-50"
              />
              {t('sys.kwShowBrowser')}
            </label>

            {refsInfo && (refsInfo.running || refsInfo.message) && (
              <TaskStatusPanel
                tone="teal"
                running={!!refsInfo.running}
                runningText={t('sys.refsRunningBadge')}
                idleText={phaseText(refsInfo.progress?.phase) || t('sys.simIdle')}
                statusLabel={t('sys.kwStatus')}
                title={refsInfo.paper_title}
                metrics={[
                  ...(refsInfo.progress && refsInfo.progress.page > 0 ? [{ label: t('sys.refsPage'), value: refsInfo.progress.page }] : []),
                  ...(refsInfo.progress && refsInfo.progress.collected > 0 ? [{ label: t('sys.refsCollected'), value: refsInfo.progress.collected, tone: 'accent' as const }] : []),
                  ...(refsInfo.progress && refsInfo.progress.failed > 0 ? [{ label: t('sys.kwFailed'), value: refsInfo.progress.failed, tone: 'bad' as const }] : []),
                ]}
                log={refsInfo.last_log}
                logTitle={t('sys.kwRecentLog')}
                message={refsInfo.message}
              />
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
                const isRefs = log.task_type === 'references';
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
                            {isRefs && (
                              <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded bg-teal-50 dark:bg-teal-900/30 text-teal-600 dark:text-teal-300">{t('sys.refsBadge')}</span>
                            )}
                          </div>
                          <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
                            <span>{t('sys.fetchedLabel')}: {log.papers_fetched}{isRefs ? t('sys.refsUnit') : t('sys.papersUnit')}</span>
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