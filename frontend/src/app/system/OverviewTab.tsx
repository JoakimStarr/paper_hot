'use client';

import { Database, BookOpen, Hash, Clock, Activity, Brain, Loader2, Save, X, Edit3, Globe, Sun, Moon } from 'lucide-react';
import { SystemStats } from '@/types/paper';
import { useLanguage } from '@/contexts/LanguageContext';
import { useTheme } from '@/contexts/ThemeContext';

interface OverviewTabProps {
  stats: SystemStats | null;
  schedulerRunning: boolean;
  appInfo: { name: string; version: string };
  editingAppName: boolean;
  savingAppName: boolean;
  appNameMessage: string;
  onEditAppNameChange: (name: string) => void;
  onStartEditAppName: () => void;
  onCancelEditAppName: () => void;
  onSaveAppName: () => void;
  cnkiUrlPrefix: string;
  cnkiPrefixDraft: string;
  savingCnkiPrefix: boolean;
  cnkiPrefixMessage: string;
  onCnkiPrefixDraftChange: (value: string) => void;
  onSaveCnkiPrefix: () => void;
}

export default function OverviewTab({
  stats,
  schedulerRunning,
  appInfo,
  editingAppName,
  savingAppName,
  appNameMessage,
  onEditAppNameChange,
  onStartEditAppName,
  onCancelEditAppName,
  onSaveAppName,
  cnkiUrlPrefix,
  cnkiPrefixDraft,
  savingCnkiPrefix,
  cnkiPrefixMessage,
  onCnkiPrefixDraftChange,
  onSaveCnkiPrefix,
}: OverviewTabProps) {
  const { t, language, setLanguage } = useLanguage();
  const { isDark, toggleDark } = useTheme();

  const timeAgo = (dateStr: string | null): string => {
    if (!dateStr) return t('sys.noRecords');
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
    if (hours >= 1) return t('common.hoursAgo', { n: hours });
    if (minutes >= 1) return t('common.minutesAgo', { n: minutes });
    return t('common.justNow');
  };

  return (
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
                      onChange={e => onEditAppNameChange(e.target.value)}
                      className="w-full px-3 py-2 border border-primary-300 dark:border-primary-600 rounded-lg text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
                      placeholder={t('sys.appNameLabel')}
                    />
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={onSaveAppName}
                    disabled={savingAppName}
                    className="flex items-center gap-1 px-3 py-1.5 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors"
                  >
                    {savingAppName ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                    {t('common.save')}
                  </button>
                  <button
                    onClick={onCancelEditAppName}
                    className="flex items-center gap-1 px-3 py-1.5 text-gray-600 dark:text-gray-400 text-sm rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                  >
                    <X className="w-3.5 h-3.5" />
                    {t('common.cancel')}
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
                <h2 className="text-2xl font-bold text-primary-700 dark:text-primary-300">{appInfo.name || stats?.app_name || 'PaperPulse'}</h2>
                <p className="text-sm text-primary-600 dark:text-primary-400 mt-1">{t('sys.appDesc')}</p>
              </>
            )}
          </div>
          <div className="text-right">
            {!editingAppName && (
              <div className="flex items-center gap-3">
                <div className="text-sm text-primary-500 dark:text-primary-400">
                  <div>{t('sys.version')} {appInfo.version || stats?.app_version || '-'}</div>
                  <div className="mt-1">{t('sys.techStack')}</div>
                </div>
                <button
                  onClick={onStartEditAppName}
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

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6 mb-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-3 flex items-center gap-2">
          <Globe className="w-5 h-5 text-gray-500 dark:text-gray-400" />
          {t('sys.cnkiPrefixTitle')}
        </h3>
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">{t('sys.cnkiPrefixDesc')}</p>
        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
          <input
            type="text"
            value={cnkiPrefixDraft}
            onChange={e => onCnkiPrefixDraftChange(e.target.value)}
            placeholder="https://kns.cnki.net"
            className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-primary-500"
          />
          <button
            onClick={onSaveCnkiPrefix}
            disabled={savingCnkiPrefix}
            className="flex items-center justify-center gap-1 px-4 py-2 bg-primary-600 text-white text-sm rounded-lg hover:bg-primary-700 disabled:opacity-50 transition-colors whitespace-nowrap"
          >
            {savingCnkiPrefix ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            {t('common.save')}
          </button>
        </div>
        <div className="mt-2 flex items-center gap-2 flex-wrap">
          <span className={`text-xs ${cnkiUrlPrefix ? 'text-green-600 dark:text-green-400' : 'text-gray-400 dark:text-gray-500'}`}>
            {cnkiUrlPrefix ? t('sys.cnkiPrefixCurrent').replace('{prefix}', cnkiUrlPrefix) : t('sys.cnkiPrefixDefault')}
          </span>
          {cnkiPrefixMessage && (
            <span className={`text-xs ${cnkiPrefixMessage.includes('成功') || cnkiPrefixMessage.includes('保存') ? 'text-green-600' : 'text-red-500'}`}>
              {cnkiPrefixMessage}
            </span>
          )}
        </div>
      </div>

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

      {/* 外观：语言 + 主题 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border p-6">
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-1 flex items-center gap-2">
          <Globe className="w-5 h-5 text-gray-500 dark:text-gray-400" />
          {t('sys.appearance')}
        </h3>
        <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">{t('sys.appearanceHint')}</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('sys.languageLabel')}</label>
            <div className="flex items-center gap-2 bg-gray-50 dark:bg-gray-700/50 rounded-lg px-3 py-2">
              <Globe className="w-4 h-4 text-gray-500 dark:text-gray-400" />
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value as 'zh' | 'en')}
                className="bg-transparent flex-1 text-sm text-gray-900 dark:text-white focus:outline-none cursor-pointer"
              >
                <option value="zh">{t('language.zh')}</option>
                <option value="en">{t('language.en')}</option>
              </select>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">{t('sys.themeLabel')}</label>
            <button
              onClick={toggleDark}
              className="flex items-center gap-2 w-full sm:w-fit px-3 py-2 bg-gray-50 dark:bg-gray-700/50 rounded-lg text-sm text-gray-900 dark:text-white hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
            >
              {isDark ? <Moon className="w-4 h-4 text-gray-500 dark:text-gray-400" /> : <Sun className="w-4 h-4 text-gray-500 dark:text-gray-400" />}
              {isDark ? t('sys.themeDark') : t('sys.themeLight')}
            </button>
          </div>
        </div>
      </div>
    </>
  );
}