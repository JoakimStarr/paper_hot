'use client';

/**
 * AI 分析全局单例悬浮窗（P3 性能优化）。
 *
 * 把原来散布在每个 PaperCard 里的弹窗状态与轮询收敛为一个全局实例：
 * - 任意论文卡片点击「AI 分析」都复用同一个弹窗，不再逐卡片渲染弹层，减少 DOM 与内存开销
 * - 关闭/切换论文时用 AbortSignal 中止未完成的请求，并清理轮询定时器，避免后台并发空转
 * - 连续分析多篇不并发：一次只分析一篇（旧的一篇已完成才可开下一篇，会话内天然串行）
 */
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { Sparkles, X, Loader2 } from 'lucide-react';
import MarkdownRenderer from '@/components/MarkdownRenderer';
import { useLanguage } from '@/contexts/LanguageContext';
import { papersApi } from '@/lib/api';

interface AiAnalysisContextValue {
  openAiAnalysis: (paperId: string, title?: string) => void;
}

const AiAnalysisContext = createContext<AiAnalysisContextValue | null>(null);

/** 供任意组件（PaperCard）打开全局 AI 分析悬浮窗。 */
export function useAiAnalysisModal(): AiAnalysisContextValue {
  const ctx = useContext(AiAnalysisContext);
  if (!ctx) throw new Error('useAiAnalysisModal must be used within <AiAnalysisModalProvider>');
  return ctx;
}

export function AiAnalysisModalProvider({ children }: { children: React.ReactNode }) {
  const { t } = useLanguage();

  const [open, setOpen] = useState(false);
  const [paperId, setPaperId] = useState<string | null>(null);
  const [paperTitle, setPaperTitle] = useState('');
  const [loading, setLoading] = useState(true);
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState(false);
  // 无历史分析时置 true：等待用户手动点击才开始生成（避免打开即烧 LLM 调用）
  const [needsStart, setNeedsStart] = useState(false);

  // 请求中止控制器：关闭/切换论文时终止未完成的 analyzePaper 请求
  const abortRef = useRef<AbortController | null>(null);
  // 轮询定时器：仅存在于"生成中"阶段，done/close 时清理
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // 组件卸载时统一清理，避免泄漏
  const activePaperRef = useRef<string | null>(null);

  useEffect(() => () => {
    if (pollRef.current) clearInterval(pollRef.current);
    // 卸载时兜底再 abort 一次（以防 open 状态残留）
    abortRef.current?.abort();
  }, []);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const close = useCallback(() => {
    setOpen(false);
    setPaperId(null);
    stopPolling();
    abortRef.current?.abort();
    abortRef.current = null;
  }, [stopPolling]);

  /** 纯轮询：只读 latest 直到完成（用于服务端已在生成的场景），不触发任何 POST。 */
  const pollUntilDone = useCallback((target: string) => {
    if (abortRef.current) abortRef.current.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    const check = async (): Promise<boolean> => {
      try {
        const res = await papersApi.getLatestAnalysis(target);
        if (res.status === 'success' && res.analysis) {
          setContent(res.analysis);
          setLoading(false);
          return true;
        }
        if (res.status === 'failed' || res.status === 'error') {
          setError(true);
          setLoading(false);
          return true;
        }
        return false;
      } catch (e: unknown) {
        if ((e as Error).name === 'AbortError') return true;
        setError(true);
        setLoading(false);
        return true;
      }
    };

    (async () => {
      if (await check()) { stopPolling(); return; }
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        if (!activePaperRef.current) return;
        const done = await check();
        if (done) stopPolling();
      }, 4000);
    })();
  }, [stopPolling]);

  /** 打开弹窗时的被动检查：只读 latest，绝不触发生成。 */
  const loadLatestOnly = useCallback(async (target: string): Promise<void> => {
    try {
      const res = await papersApi.getLatestAnalysis(target);
      if (res.status === 'success' && res.analysis) {
        setContent(res.analysis);
        setLoading(false);
        return;
      }
      if (res.status === 'pending') {
        // 服务端确实在生成（此前显式启动过），继续轮询直到完成
        pollUntilDone(target);
        return;
      }
      setNeedsStart(true);
      setLoading(false);
    } catch {
      setNeedsStart(true);
      setLoading(false);
    }
  }, []);

  /** 显式开始：POST 提交生成，随后轮询结果。仅由用户点击触发。 */
  const startAnalysis = useCallback((target: string) => {
    if (abortRef.current) abortRef.current.abort();
    const ac = new AbortController();
    abortRef.current = ac;

    let started = false;
    const pollLatest = async (): Promise<boolean> => {
      if (!started) {
        started = true;
        try {
          await papersApi.analyzePaper(target, undefined, ac.signal);
        } catch (e: unknown) {
          if ((e as Error).name === 'AbortError') return true;
          setError(true);
          setLoading(false);
          stopPolling();
          return true;
        }
      }
      try {
        const res = await papersApi.getLatestAnalysis(target);
        if (res.status === 'success' && res.analysis) {
          setContent(res.analysis);
          setLoading(false);
          return true;
        }
        if (res.status === 'failed' || res.status === 'error') {
          setError(true);
          setLoading(false);
          return true;
        }
        return false; // 仍在生成，继续轮询
      } catch (e: unknown) {
        if ((e as Error).name === 'AbortError') return true;
        setError(true);
        setLoading(false);
        return true;
      }
    };

    // 先跑一次，若未完成再进入固定间隔轮询；被 Abort 时清理
    (async () => {
      if (await pollLatest()) {
        stopPolling();
        return;
      }
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        const active = activePaperRef.current;
        if (!active) return; // 已关闭，忽略
        const done = await pollLatest();
        if (done) stopPolling();
      }, 4000);
    })();
  }, [stopPolling]);

  const openAiAnalysis = useCallback((pid: string, title?: string) => {
    setPaperId(pid);
    setPaperTitle(title || '');
    setLoading(true);
    setContent(null);
    setError(false);
    activePaperRef.current = pid;
    setOpen(true);
    void loadLatestOnly(pid);
  }, [loadLatestOnly]);

  const value = useMemo(() => ({ openAiAnalysis }), [openAiAnalysis]);

  return (
    <AiAnalysisContext.Provider value={value}>
      {children}

      {/* 全局单例悬浮窗 */}
      {open && (
        <>
          <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm" onClick={close} />
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4 pointer-events-none">
            <div className="pointer-events-auto w-full max-w-2xl max-h-[80vh] flex flex-col bg-white dark:bg-gray-800 rounded-xl shadow-2xl border border-gray-200 dark:border-gray-700 overflow-hidden">
              <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-gray-200 dark:border-gray-700 shrink-0">
                <div className="flex items-center gap-2 text-sm font-semibold text-gray-800 dark:text-gray-100 min-w-0">
                  <Sparkles className="w-4 h-4 text-purple-500 shrink-0" />
                  {paperTitle ? (
                    <span className="truncate">{paperTitle}</span>
                  ) : (
                    <span>{t('paper.aiAnalyze')}</span>
                  )}
                </div>
                <button onClick={close} className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors p-1 shrink-0" title={t('paper.aiClose')}>
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto px-5 py-4 text-sm text-gray-700 dark:text-gray-300">
                {loading ? (
                  <div className="flex flex-col items-center justify-center py-14 gap-3">
                    <Loader2 className="w-6 h-6 animate-spin text-purple-500" />
                    <span className="text-gray-400 text-sm">{t('paper.aiAnalyzing')}</span>
                  </div>
                ) : error ? (
                  <div className="flex flex-col items-center justify-center py-14 gap-3 text-center">
                    <p className="text-red-500 text-sm">{t('paper.aiAnalyzeFailed')}</p>
                    <button
                      onClick={() => {
                        if (!paperId) return;
                        setError(false);
                        setLoading(true);
                        setContent(null);
                        startAnalysis(paperId);
                      }}
                      className="px-3 py-1.5 text-xs rounded border border-purple-300 dark:border-purple-700 text-purple-600 dark:text-purple-300 hover:bg-purple-50 dark:hover:bg-purple-900/30 transition-colors"
                    >
                      {t('paper.aiRetry')}
                    </button>
                  </div>
                ) : content ? (
                  <MarkdownRenderer content={content} />
                ) : needsStart ? (
                  <div className="flex flex-col items-center justify-center py-14 gap-3 text-center">
                    <p className="text-gray-400 text-sm">{t('paper.aiNoContent')}</p>
                    <button
                      onClick={() => {
                        if (!paperId) return;
                        setNeedsStart(false);
                        setLoading(true);
                        setContent(null);
                        startAnalysis(paperId);
                      }}
                      className="px-4 py-2 text-sm rounded-lg bg-primary-600 text-white hover:bg-primary-700 transition-colors"
                    >
                      {t('pd.startAnalysis')}
                    </button>
                  </div>
                ) : (
                  <div className="py-14 text-center text-gray-400 text-sm">{t('paper.aiNoContent')}</div>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </AiAnalysisContext.Provider>
  );
}