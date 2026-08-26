'use client';

/**
 * AI 分析悬浮窗 · 轻量 Context 层（PERF_PLAN 1.1 P0）。
 *
 * 仅包含状态管理与轮询逻辑；模态 UI 与 markdown 渲染栈隔离在
 * AiAnalysisModalView（经 next/dynamic 按需加载），不再进入共享 layout chunk。
 * 交互约定：打开弹窗只做被动检查，生成必须由用户显式点击触发。
 */
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { papersApi } from '@/lib/api';

const ModalView = dynamic(() => import('./AiAnalysisModalView'), { ssr: false });

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
  const [open, setOpen] = useState(false);
  const [paperId, setPaperId] = useState<string | null>(null);
  const [paperTitle, setPaperTitle] = useState('');
  const [loading, setLoading] = useState(true);
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState(false);
  // 无历史分析时置 true：等待用户手动点击才开始生成（避免打开即烧 LLM 调用）
  const [needsStart, setNeedsStart] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const activePaperRef = useRef<string | null>(null);

  useEffect(() => () => {
    if (pollRef.current) clearInterval(pollRef.current);
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

  /** 纯轮询：只读 latest 直到完成（服务端已在生成的场景），不触发 POST。 */
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
        pollUntilDone(target);
        return;
      }
      setNeedsStart(true);
      setLoading(false);
    } catch {
      setNeedsStart(true);
      setLoading(false);
    }
  }, [pollUntilDone]);

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
        return false;
      } catch (e: unknown) {
        if ((e as Error).name === 'AbortError') return true;
        setError(true);
        setLoading(false);
        return true;
      }
    };

    (async () => {
      if (await pollLatest()) { stopPolling(); return; }
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        if (!activePaperRef.current) return;
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
    setNeedsStart(false);
    activePaperRef.current = pid;
    setOpen(true);
    void loadLatestOnly(pid);
  }, [loadLatestOnly]);

  const value = useMemo(() => ({ openAiAnalysis }), [openAiAnalysis]);

  return (
    <AiAnalysisContext.Provider value={value}>
      {children}
      {open && (
        <ModalView
          paperTitle={paperTitle}
          loading={loading}
          content={content}
          error={error}
          needsStart={needsStart}
          onClose={close}
          onStart={() => { if (paperId) startAnalysis(paperId); }}
        />
      )}
    </AiAnalysisContext.Provider>
  );
}
