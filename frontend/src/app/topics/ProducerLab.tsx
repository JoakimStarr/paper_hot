'use client';

import React, { useState, useEffect, useRef, useMemo } from 'react';
import dynamic from 'next/dynamic';
import { BookMarked, Building2, Loader2, Sparkles, Download, History, FileText, Trash2 } from 'lucide-react';
import { producerApi, ReviewBrief } from '@/lib/api';
import { useToast } from '@/components/Toast';
import { downloadTextFile, downloadAsWord } from '@/lib/utils';

const MarkdownRenderer = dynamic(() => import('@/components/MarkdownRenderer'), {
  ssr: false,
  loading: () => (
    <div className="h-20 flex items-center justify-center text-gray-400 text-sm animate-pulse">加载中...</div>
  ),
});

// 后台综述生成轮询间隔（前密后疏）
const POLL_INTERVALS = [3000, 5000, 8000, 12000, 15000];

export default function ProducerLab({ initialReviewId }: { initialReviewId?: number | null }) {
  const { toast } = useToast();

  // —— 综述生成 ——
  const [topic, setTopic] = useState('');
  const [reviewBusy, setReviewBusy] = useState(false);
  const [reviewId, setReviewId] = useState<number | null>(null);
  const [reviewContent, setReviewContent] = useState<string | null>(null);
  const [reviewPapers, setReviewPapers] = useState<Array<Record<string, unknown>>>([]);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollCountRef = useRef(0);

  // 综述引用编号 → 论文：正文 [n] 渲染为可点击的论文详情页链接（对应下方引用文献列表序号）
  const reviewCitations = useMemo(() => {
    const map: Record<number, { id: string; title?: string }> = {};
    reviewPapers.forEach((p, i) => {
      const pid = p.id ? String(p.id) : '';
      if (pid) map[i + 1] = { id: pid, title: p.title ? String(p.title) : undefined };
    });
    return map;
  }, [reviewPapers]);

  // —— 期刊适配 ——
  const [journalResult, setJournalResult] = useState<{ recommendations: string; ai_used: boolean; suggestions: Array<{ journal: string; reason: string }> } | null>(null);
  const [journalBusy, setJournalBusy] = useState(false);

  // —— 历史综述 ——
  const [history, setHistory] = useState<ReviewBrief[]>([]);

  const loadHistory = async () => {
    try {
      setHistory(await producerApi.listReviews(8));
    } catch { /* ignore */ }
  };

  useEffect(() => {
    loadHistory();
    return () => {
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, []);

  // 综述后台任务轮询：ref 式自调度（对齐 trends 页 startPolling），
  // 网络抖动不断链；连续失败超过 10 次或总次数超限才放弃
  useEffect(() => {
    if (!reviewBusy || reviewId === null) return;

    const stopPolling = () => {
      if (pollRef.current) {
        clearTimeout(pollRef.current);
        pollRef.current = null;
      }
    };

    if (pollRef.current) return;
    pollCountRef.current = 0;
    let failCount = 0;

    const tick = async () => {
      try {
        const res = await producerApi.getReview(reviewId);
        failCount = 0;
        if (res.status === 'success') {
          setReviewContent(res.content || '');
          setReviewPapers((res.papers as Array<Record<string, unknown>>) || []);
          setReviewBusy(false);
          loadHistory();
          pollRef.current = null;
          return;
        } else if (res.status === 'failed') {
          setReviewError(res.content || '生成失败，请重试');
          setReviewBusy(false);
          pollRef.current = null;
          return;
        } else if (pollCountRef.current > 40) {
          setReviewError('等待超时，请稍后在历史记录中查看结果');
          setReviewBusy(false);
          pollRef.current = null;
          return;
        }
      } catch {
        // 网络抖动继续轮询；连续失败超过 10 次则放弃
        failCount += 1;
        if (failCount > 10) {
          setReviewError('网络连接不稳定，已停止等待，请稍后在历史记录中查看结果');
          setReviewBusy(false);
          pollRef.current = null;
          return;
        }
      }
      pollCountRef.current = Math.min(pollCountRef.current + 1, POLL_INTERVALS.length - 1);
      pollRef.current = setTimeout(tick, POLL_INTERVALS[pollCountRef.current]);
    };

    pollRef.current = setTimeout(tick, POLL_INTERVALS[0]);
    return stopPolling;
  }, [reviewBusy, reviewId]);

  const startReview = async () => {
    const t = topic.trim();
    if (!t || reviewBusy) return;
    setReviewBusy(true);
    setReviewContent(null);
    setReviewError(null);
    setReviewPapers([]);
    pollCountRef.current = 0;
    try {
      const res = await producerApi.startReview(t);
      setReviewId(res.review_id);
    } catch (e) {
      setReviewError(e instanceof Error ? e.message : '启动失败');
      setReviewBusy(false);
    }
  };

  const suggestJournal = async () => {
    const t = topic.trim();
    if (!t || journalBusy) return;
    setJournalBusy(true);
    setJournalResult(null);
    try {
      // 把已生成的综述作为 abstract 上下文传给后端（可提升期刊推荐贴合度）
      const res = await producerApi.suggestJournal(t, reviewContent || undefined);
      setJournalResult(res);
    } catch (e) {
      toast(`期刊适配失败：${e instanceof Error ? e.message : '未知错误'}`, 'error');
    } finally {
      setJournalBusy(false);
    }
  };

  const loadHistoryItem = async (id: number) => {
    try {
      const res = await producerApi.getReview(id);
      setTopic(res.topic || '');
      setReviewId(id);
      if (res.status === 'success') {
        setReviewContent(res.content || '');
        setReviewPapers((res.papers as Array<Record<string, unknown>>) || []);
        setReviewBusy(false);
        setReviewError(null);
      } else if (res.status === 'failed') {
        setReviewError('该次生成失败');
        setReviewContent(null);
        setReviewBusy(false);
      } else {
        // running：恢复轮询
        setReviewContent(null);
        setReviewBusy(true);
      }
    } catch { /* ignore */ }
  };

  // 深链：从工作台点开某条历史综述时直接加载（切到 producer tab 后挂载本组件）
  useEffect(() => {
    if (initialReviewId) {
      loadHistoryItem(initialReviewId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialReviewId]);

  const exportReview = (fmt: 'md' | 'doc') => {
    if (!reviewContent) return;
    const title = topic.trim() || '文献综述';
    if (fmt === 'md') {
      downloadTextFile(`${title}_综述_${Date.now()}.md`, reviewContent, 'text/markdown;charset=utf-8');
    } else {
      downloadAsWord(`${title}_综述_${Date.now()}.doc`, title, reviewContent);
    }
  };

  return (
    <div className="space-y-6">
      {/* 输入区 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sm:p-6">
        <h3 className="font-semibold text-gray-900 dark:text-white mb-1">产出工作台</h3>
        <p className="text-xs text-gray-400 mb-4">
          输入一个选题：AI 从论文库检索 20-25 篇相关文献生成结构化综述（研究脉络 / 方法演进 / 争议点 / 研究空白），并给出投稿期刊建议
        </p>
        <div className="flex flex-col sm:flex-row gap-2">
          <input
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !reviewBusy) startReview(); }}
            placeholder="例：数字普惠金融对小微企业创新的影响机制"
            className="flex-1 border border-gray-300 dark:border-gray-600 rounded-lg px-4 py-2.5 text-sm bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 outline-none focus:ring-2 focus:ring-primary-500"
          />
          <div className="flex gap-2">
            <button
              onClick={startReview}
              disabled={!topic.trim() || reviewBusy}
              className="flex items-center gap-1.5 px-4 py-2.5 rounded-lg bg-purple-600 text-white text-sm disabled:opacity-50 hover:bg-purple-700 transition-colors whitespace-nowrap"
            >
              {reviewBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <BookMarked className="w-4 h-4" />}
              生成综述
            </button>
            <button
              onClick={suggestJournal}
              disabled={!topic.trim() || journalBusy}
              className="flex items-center gap-1.5 px-4 py-2.5 rounded-lg border border-primary-300 text-primary-700 dark:text-primary-400 text-sm disabled:opacity-50 hover:bg-primary-50 dark:hover:bg-primary-900/20 transition-colors whitespace-nowrap"
            >
              {journalBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Building2 className="w-4 h-4" />}
              期刊适配
            </button>
          </div>
        </div>
      </div>

      {reviewError && (
        <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 rounded-lg p-4 text-sm text-red-700">{reviewError}</div>
      )}

      {reviewBusy && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-8 text-center">
          <Loader2 className="w-6 h-6 animate-spin text-purple-500 mx-auto mb-3" />
          <p className="text-sm text-gray-500">正在检索文献并生成综述，通常需要 30 秒到 2 分钟…</p>
        </div>
      )}

      {/* 期刊适配结果 */}
      {journalResult && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sm:p-6">
          <div className="flex items-center justify-between mb-3">
            <h4 className="font-semibold text-gray-900 dark:text-white flex items-center gap-1.5">
              <Building2 className="w-4 h-4 text-blue-500" /> 投稿期刊适配建议
            </h4>
            {!journalResult.ai_used && (
              <span className="text-xs bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded text-gray-500">规则推荐（AI 未配置）</span>
            )}
          </div>
          <MarkdownRenderer content={journalResult.recommendations} />
          {journalResult.suggestions.length > 0 && (
            <div className="mt-3 pt-3 border-t border-gray-100 dark:border-gray-700 space-y-1.5">
              {journalResult.suggestions.map((s, i) => (
                <p key={i} className="text-xs text-gray-500"><span className="font-medium text-gray-700 dark:text-gray-300">{s.journal}：</span>{s.reason}</p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 综述结果 */}
      {reviewContent && !reviewBusy && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sm:p-6">
          <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
            <h4 className="font-semibold text-gray-900 dark:text-white flex items-center gap-1.5">
              <Sparkles className="w-4 h-4 text-purple-500" /> 文献综述{topic ? `：${topic}` : ''}
            </h4>
            <div className="flex items-center gap-2">
              <button onClick={() => exportReview('md')} className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 hover:border-primary-400 text-gray-700 dark:text-gray-300">
                <Download className="w-3.5 h-3.5" /> Markdown
              </button>
              <button onClick={() => exportReview('doc')} className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg border border-gray-300 dark:border-gray-600 hover:border-primary-400 text-gray-700 dark:text-gray-300">
                <FileText className="w-3.5 h-3.5" /> Word
              </button>
            </div>
          </div>
          <MarkdownRenderer content={reviewContent} citations={reviewCitations} />

          {reviewPapers.length > 0 && (
            <div className="mt-4 pt-4 border-t border-gray-100 dark:border-gray-700">
              <h5 className="text-xs font-medium text-gray-500 mb-2">引用文献（{reviewPapers.length} 篇，与综述【编号】对应）</h5>
              <ol className="space-y-1 max-h-64 overflow-y-auto">
                {reviewPapers.map((p, i) => {
                  const pid = p.id ? String(p.id) : '';
                  return (
                    <li key={i} className="text-xs text-gray-500 leading-relaxed">
                      <span className="text-gray-400 mr-1">【{i + 1}】</span>
                      {pid ? (
                        <a
                          href={`/paper/${pid}`}
                          target="_blank"
                          rel="noreferrer"
                          className="text-gray-700 dark:text-gray-300 hover:text-primary-600"
                        >
                          {(p.title as string) || ''}
                        </a>
                      ) : (
                        <span>{(p.title as string) || ''}</span>
                      )}
                      <span className="text-gray-400"> — {(p.journal_name as string) || ''}</span>
                    </li>
                  );
                })}
              </ol>
            </div>
          )}
        </div>
      )}

      {/* 历史综述 */}
      {history.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sm:p-6">
          <h4 className="font-semibold text-gray-900 dark:text-white flex items-center gap-1.5 mb-3">
            <History className="w-4 h-4 text-gray-400" /> 历史综述
          </h4>
          <div className="space-y-1.5">
            {history.map((h) => (
              <button
                key={h.id}
                onClick={() => loadHistoryItem(h.id)}
                className={`w-full text-left px-3 py-2 rounded-lg border text-sm transition-colors ${
                  reviewId === h.id
                    ? 'border-purple-300 bg-purple-50 dark:bg-purple-900/20'
                    : 'border-gray-100 dark:border-gray-700 hover:border-purple-200'
                }`}
              >
                <span className="text-gray-800 dark:text-gray-200 line-clamp-1">{h.topic}</span>
                <span className="ml-2 text-xs text-gray-400">
                  {h.status === 'success' ? '已完成' : h.status === 'running' ? '生成中' : '失败'}
                  {h.created_at ? ` · ${new Date(h.created_at).toLocaleDateString()}` : ''}
                </span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
