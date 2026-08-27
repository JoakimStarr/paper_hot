'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { logsApi, ActionLogItem, ErrorLogItem } from '@/lib/api';
import { Loader2, RefreshCw, ChevronDown, ChevronUp, AlertTriangle, ScrollText, Bug } from 'lucide-react';

type LogsView = 'errors' | 'actions';

const PAGE_SIZE = 30;

const SOURCE_LABELS: Record<string, string> = {
  backend: '后端',
  frontend: '前端',
  scheduler: '后台任务',
};

const STATUS_CLASS = (code: number | null) =>
  code === null ? 'text-gray-500' : code >= 500 ? 'text-red-600 dark:text-red-400' : code >= 400 ? 'text-amber-600 dark:text-amber-400' : 'text-green-600 dark:text-green-400';

function fmtTime(ts: string | null): string {
  if (!ts) return '-';
  const d = new Date(ts);
  return isNaN(d.getTime()) ? String(ts) : d.toLocaleString('zh-CN', { hour12: false });
}

export default function LogsTab() {
  const [view, setView] = useState<LogsView>('errors');
  const [errors, setErrors] = useState<ErrorLogItem[]>([]);
  const [actions, setActions] = useState<ActionLogItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  // 筛选条件
  const [userId, setUserId] = useState('');
  const [keyword, setKeyword] = useState('');
  const [status, setStatus] = useState('');
  const [source, setSource] = useState('');

  const switchView = (v: LogsView) => {
    setView(v);
    setPage(1);
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Record<string, unknown> = { page, page_size: PAGE_SIZE };
      if (userId.trim()) params.user_id = userId.trim();
      if (status.trim()) params.status = Number(status.trim());
      if (view === 'errors') {
        if (source.trim()) params.source = source.trim();
        if (keyword.trim()) params.keyword = keyword.trim();
        const res = await logsApi.listErrorLogs(params);
        setErrors(res.items);
        setTotal(res.total);
      } else {
        if (keyword.trim()) params.path = keyword.trim();
        const res = await logsApi.listActionLogs(params);
        setActions(res.items);
        setTotal(res.total);
      }
    } catch (e: any) {
      setError(e instanceof Error ? e.message : '日志加载失败');
    } finally {
      setLoading(false);
    }
  }, [view, page, userId, keyword, status, source]);

  useEffect(() => { load(); }, [load]);

  const resetFilters = () => {
    setUserId('');
    setKeyword('');
    setStatus('');
    setSource('');
    setPage(1);
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const filterRow = (
    <div className="flex flex-wrap items-center gap-2 mb-3">
      {view === 'errors' && (
        <select
          value={source}
          onChange={(e) => { setSource(e.target.value); setPage(1); }}
          className="px-2 py-1.5 text-xs border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-200"
        >
          <option value="">全部来源</option>
          {Object.entries(SOURCE_LABELS).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
      )}
      <input
        value={userId}
        onChange={(e) => { setUserId(e.target.value); setPage(1); }}
        placeholder="用户 ID"
        className="w-32 px-2 py-1.5 text-xs border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-200 placeholder-gray-400"
      />
      <input
        value={keyword}
        onChange={(e) => { setKeyword(e.target.value); setPage(1); }}
        placeholder={view === 'errors' ? '关键词（消息/路径）' : '路径关键字'}
        className="w-44 px-2 py-1.5 text-xs border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-200 placeholder-gray-400"
      />
      <input
        value={status}
        onChange={(e) => { setStatus(e.target.value); setPage(1); }}
        placeholder="状态码"
        className="w-24 px-2 py-1.5 text-xs border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-700 dark:text-gray-200 placeholder-gray-400"
      />
      <button
        onClick={() => setPage(1)}
        className="px-3 py-1.5 text-xs rounded-lg bg-primary-600 text-white hover:bg-primary-700 transition-colors"
      >
        查询
      </button>
      <button
        onClick={resetFilters}
        className="px-3 py-1.5 text-xs rounded-lg border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:border-primary-400 transition-colors"
      >
        重置
      </button>
      <button
        onClick={load}
        className="ml-auto flex items-center gap-1 px-3 py-1.5 text-xs rounded-lg border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:border-primary-400 transition-colors"
      >
        <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} />
        刷新
      </button>
    </div>
  );

  const pagination = (
    <div className="flex items-center justify-between mt-3 text-xs text-gray-500">
      <span>共 {total} 条 · 第 {page}/{totalPages} 页</span>
      <div className="flex gap-2">
        <button
          disabled={page <= 1}
          onClick={() => setPage(page - 1)}
          className="px-2.5 py-1 rounded-lg border border-gray-300 dark:border-gray-600 disabled:opacity-40 hover:border-primary-400 transition-colors"
        >
          上一页
        </button>
        <button
          disabled={page >= totalPages}
          onClick={() => setPage(page + 1)}
          className="px-2.5 py-1 rounded-lg border border-gray-300 dark:border-gray-600 disabled:opacity-40 hover:border-primary-400 transition-colors"
        >
          下一页
        </button>
      </div>
    </div>
  );

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sm:p-6">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <h3 className="font-semibold text-gray-900 dark:text-white flex items-center gap-1.5">
          <ScrollText className="w-4 h-4 text-blue-500" /> 日志中心
        </h3>
        <div className="flex gap-2">
          <button
            onClick={() => switchView('errors')}
            className={`flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs transition-colors ${
              view === 'errors'
                ? 'bg-red-500 text-white'
                : 'border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:border-red-400'
            }`}
          >
            <Bug className="w-3.5 h-3.5" /> 错误日志
          </button>
          <button
            onClick={() => switchView('actions')}
            className={`flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs transition-colors ${
              view === 'actions'
                ? 'bg-blue-500 text-white'
                : 'border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:border-blue-400'
            }`}
          >
            <ActivityIcon /> 动作日志
          </button>
        </div>
      </div>

      {filterRow}

      {error && (
        <div className="mb-3 bg-red-50 dark:bg-red-900/30 border border-red-200 rounded-lg p-3 text-xs text-red-700">{error}</div>
      )}

      {loading && !errors.length && !actions.length ? (
        <div className="flex items-center justify-center py-10">
          <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
        </div>
      ) : view === 'errors' ? (
        <div className="space-y-1.5">
          {errors.length === 0 && <p className="text-xs text-gray-400 text-center py-8">暂无错误日志</p>}
          {errors.map((e) => (
            <div key={e.id} className="border border-gray-100 dark:border-gray-700 rounded-lg">
              <button
                onClick={() => setExpandedId(expandedId === e.id ? null : e.id)}
                className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-gray-50 dark:hover:bg-gray-700/40 transition-colors"
              >
                <span className={`shrink-0 ${e.status_code === null ? 'text-gray-400' : 'text-red-500'}`}>
                  {e.source === 'frontend' ? <AlertTriangle className="w-3.5 h-3.5" /> : <Bug className="w-3.5 h-3.5" />}
                </span>
                <span className="shrink-0 w-14 text-[11px] font-medium text-gray-500">{SOURCE_LABELS[e.source] || e.source}</span>
                <span className="shrink-0 w-10 text-xs font-mono text-gray-400">{e.status_code ?? '-'}</span>
                <span className="shrink-0 text-xs font-mono text-gray-500 max-w-[140px] truncate">{e.error_type}</span>
                <span className="flex-1 min-w-0 text-xs text-gray-700 dark:text-gray-200 truncate">{e.error_message}</span>
                <span className="shrink-0 text-[11px] text-gray-400 hidden sm:inline">{e.user_id}</span>
                <span className="shrink-0 text-[11px] text-gray-400 hidden md:inline">{fmtTime(e.created_at)}</span>
                {expandedId === e.id ? <ChevronUp className="w-3.5 h-3.5 shrink-0 text-gray-400" /> : <ChevronDown className="w-3.5 h-3.5 shrink-0 text-gray-400" />}
              </button>
              {expandedId === e.id && (
                <div className="px-3 pb-3 text-xs space-y-1.5">
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-gray-500">
                    <span>request_id: <span className="font-mono text-gray-700 dark:text-gray-300">{e.request_id}</span></span>
                    <span>path: <span className="font-mono text-gray-700 dark:text-gray-300">{e.method} {e.path || '-'}</span></span>
                    {e.request_info?.url ? <span>url: <span className="font-mono text-gray-700 dark:text-gray-300">{String(e.request_info.url)}</span></span> : null}
                  </div>
                  {e.traceback ? (
                    <pre className="bg-gray-50 dark:bg-gray-900 rounded p-2 overflow-x-auto text-[11px] leading-relaxed text-gray-600 dark:text-gray-300 whitespace-pre-wrap break-words">
                      {e.traceback}
                    </pre>
                  ) : (
                    <p className="text-gray-400">（无堆栈信息）</p>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-gray-400 border-b border-gray-100 dark:border-gray-700">
                <th className="py-2 pr-3 font-medium">时间</th>
                <th className="py-2 pr-3 font-medium">用户</th>
                <th className="py-2 pr-3 font-medium">方法</th>
                <th className="py-2 pr-3 font-medium">路径</th>
                <th className="py-2 pr-3 font-medium">状态</th>
                <th className="py-2 pr-3 font-medium">耗时</th>
                <th className="py-2 font-medium">request_id</th>
              </tr>
            </thead>
            <tbody>
              {actions.length === 0 && (
                <tr><td colSpan={7} className="py-8 text-center text-gray-400">暂无动作日志</td></tr>
              )}
              {actions.map((a) => (
                <React.Fragment key={a.id}>
                  <tr
                    onClick={() => setExpandedId(expandedId === a.id ? null : a.id)}
                    className="border-b border-gray-50 dark:border-gray-700/60 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/40 transition-colors"
                  >
                    <td className="py-1.5 pr-3 text-gray-500 whitespace-nowrap">{fmtTime(a.created_at)}</td>
                    <td className="py-1.5 pr-3 text-gray-500">{a.user_id}</td>
                    <td className="py-1.5 pr-3 font-mono text-gray-600 dark:text-gray-300">{a.method}</td>
                    <td className="py-1.5 pr-3 text-gray-700 dark:text-gray-200 truncate max-w-[240px]">{a.path}</td>
                    <td className={`py-1.5 pr-3 font-mono ${STATUS_CLASS(a.status_code)}`}>{a.status_code}</td>
                    <td className="py-1.5 pr-3 text-gray-500">{a.duration_ms}ms</td>
                    <td className="py-1.5 font-mono text-gray-400 truncate max-w-[140px]">
                      <span className="inline-flex items-center gap-1">
                        {a.request_id}
                        {expandedId === a.id ? <ChevronUp className="w-3 h-3 shrink-0 text-gray-400" /> : <ChevronDown className="w-3 h-3 shrink-0 text-gray-400" />}
                      </span>
                    </td>
                  </tr>
                  {expandedId === a.id && (
                    <tr className="border-b border-gray-100 dark:border-gray-700">
                      <td colSpan={7} className="px-3 py-3">
                        <div className="text-xs space-y-1.5 bg-gray-50 dark:bg-gray-900 rounded p-3">
                          <div className="flex flex-wrap gap-x-4 gap-y-1 text-gray-500">
                            <span>request_id: <span className="font-mono text-gray-700 dark:text-gray-300">{a.request_id}</span></span>
                            <span>用户: <span className="font-mono text-gray-700 dark:text-gray-300">{a.user_id}</span></span>
                            <span>时间: <span className="text-gray-700 dark:text-gray-300">{fmtTime(a.created_at)}</span></span>
                            <span>耗时: <span className="text-gray-700 dark:text-gray-300">{a.duration_ms}ms</span></span>
                          </div>
                          <div className="text-gray-500">
                            完整请求：
                            <span className="font-mono text-gray-700 dark:text-gray-300 break-all">
                              {a.method} {a.path}{a.query ? `?${a.query}` : ''}
                            </span>
                          </div>
                          {a.query ? (
                            <div className="text-gray-500">
                              查询串：
                              <span className="font-mono text-gray-700 dark:text-gray-300 break-all">{a.query}</span>
                            </div>
                          ) : (
                            <div className="text-gray-400">（无查询参数）</div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pagination}
    </div>
  );
}

function ActivityIcon() {
  return (
    <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  );
}
