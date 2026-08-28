'use client';

import React, { useState, useRef, useMemo } from 'react';
import dynamic from 'next/dynamic';
import { ShieldCheck, Loader2, Square, Sparkles, ChevronDown, Brain, RefreshCw } from 'lucide-react';
import { streamValidateTopic, workbenchApi } from '@/lib/api';
import type { RetrievedPaper } from '@/types/paper';
import type { StepProps } from './types';

const MarkdownRenderer = dynamic(() => import('@/components/MarkdownRenderer'), {
  ssr: false,
  loading: () => <div className="h-16 flex items-center justify-center text-gray-400 text-sm animate-pulse">加载中...</div>,
});

export default function Step2Validate({ project, onPatch, runAi }: StepProps) {
  const [validating, setValidating] = useState(false);
  const [reportContent, setReportContent] = useState('');
  const [reportError, setReportError] = useState<string | null>(null);
  const [reportReasoning, setReportReasoning] = useState('');
  const [reasoningOpen, setReasoningOpen] = useState(true);
  const [retrievedPapers, setRetrievedPapers] = useState<RetrievedPaper[]>([]);
  const [retrievedMode, setRetrievedMode] = useState('');
  const [competition, setCompetition] = useState<{
    top_authors: Array<{ name: string; count: number }>;
    journal_distribution: Array<{ journal: string; count: number }>;
    recent_1y_count: number;
  } | null>(null);
  const [proposalBusy, setProposalBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const aiRunning = project.ai_pending === 'overview';
  const hasReport = !!(project.validation_report || reportContent);

  const citations = useMemo(() => {
    const map: Record<number, { id: string; title?: string }> = {};
    for (const p of retrievedPapers) {
      if (p.n !== undefined) map[p.n] = { id: String(p.id), title: p.title };
    }
    return map;
  }, [retrievedPapers]);

  const handleValidate = async () => {
    const topic = project.title.trim();
    if (!topic || validating) return;
    setValidating(true);
    setReportContent('');
    setReportError(null);
    setReportReasoning('');
    setRetrievedPapers([]);
    setRetrievedMode('');
    setCompetition(null);
    const controller = new AbortController();
    abortRef.current = controller;
    let full = '';
    await streamValidateTopic(
      topic,
      undefined,
      {
        onContent: (text) => { full += text; setReportContent(full); },
        onReasoning: (text) => setReportReasoning((prev) => prev + text),
        onMeta: (data) => {
          if (data && typeof data === 'object' && 'papers' in data) {
            const meta = data as any;
            setRetrievedPapers(Array.isArray(meta.papers) ? meta.papers : []);
            setRetrievedMode(typeof meta.mode === 'string' ? meta.mode : '');
            if (meta.stats?.competition) setCompetition(meta.stats.competition);
          }
        },
        onDone: () => {
          setValidating(false);
          // 验证报告沉淀回项目 + 自动生成立项书
          if (full) {
            onPatch({ validation_report: full, novelty: undefined, crowding: undefined, feasibility: undefined });
            autoProposal(full);
          }
        },
        onError: (msg) => {
          setReportError(msg);
          setValidating(false);
        },
      },
      controller.signal,
    );
  };

  const autoProposal = async (validationReport: string) => {
    setProposalBusy(true);
    try {
      const res = await workbenchApi.generateProposal(project.id, validationReport);
      await onPatch({ proposal: res.proposal });
    } catch { /* 立项书失败不阻塞 */ }
    finally {
      setProposalBusy(false);
    }
  };

  const handleAbort = () => {
    abortRef.current?.abort();
    setValidating(false);
  };

  // 验证用的初始报告：优先当前流式内容，其次项目已保存的
  const displayReport = reportContent || project.validation_report || '';

  return (
    <div className="space-y-5">
      {/* 验证操作区 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sm:p-6">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div>
            <h2 className="flex items-center gap-1.5 text-base font-semibold text-gray-900 dark:text-white">
              <ShieldCheck className="w-4 h-4 text-blue-600" /> 选题验证
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">
              基于论文库 embedding 召回 + 拥挤度统计 + 竞争地图，评估「{project.title}」
            </p>
          </div>
          <div className="flex gap-2">
            {validating ? (
              <button
                onClick={handleAbort}
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-red-500 hover:bg-red-600 text-white text-sm rounded-lg transition-colors"
              >
                <Square className="w-4 h-4" /> 停止
              </button>
            ) : (
              <button
                onClick={handleValidate}
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-sm rounded-lg transition-colors"
              >
                {project.validation_report ? <RefreshCw className="w-4 h-4" /> : <ShieldCheck className="w-4 h-4" />}
                {project.validation_report ? '重新验证' : '开始验证'}
              </button>
            )}
          </div>
        </div>

        {!hasReport && !validating && (
          <p className="text-xs text-gray-400">点击「开始验证」，AI 将基于论文库生成一份含新颖性/拥挤度/机会窗口的验证报告。</p>
        )}

        {/* 召回论文 */}
        {retrievedPapers.length > 0 && (
          <div className="mt-4">
            <div className="text-xs font-medium text-gray-500 mb-1.5">
              召回依据（{retrievedPapers.length} 篇 · {retrievedMode === 'embedding+rerank' ? '语义检索+重排' : retrievedMode === 'embedding' ? '语义检索' : 'TF-IDF'}）
            </div>
            <ul className="space-y-1 max-h-64 overflow-y-auto">
              {retrievedPapers.slice(0, 12).map((p) => (
                <li key={p.id}>
                  <a
                    href={`/paper/${p.id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center justify-between gap-3 px-3 py-1.5 bg-gray-50 dark:bg-gray-700/40 border border-gray-200 dark:border-gray-600 rounded-md hover:border-primary-400 transition-colors"
                  >
                    <span className="flex-1 min-w-0 text-xs text-gray-700 dark:text-gray-300 truncate">
                      {p.n !== undefined && <span className="text-gray-400 mr-1.5 font-mono">[{p.n}]</span>}
                      {p.title}
                    </span>
                    <span className="text-[11px] text-gray-400 font-mono shrink-0">{(p.similarity * 100).toFixed(1)}%</span>
                  </a>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* 竞争地图 */}
        {competition && (competition.top_authors.length > 0 || competition.journal_distribution.length > 0) && (
          <div className="mt-4 bg-indigo-50/60 dark:bg-indigo-900/15 border border-indigo-100 dark:border-indigo-800/40 rounded-lg p-3">
            <h3 className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
              竞争地图 <span className="ml-1 text-[11px] font-normal text-gray-400">近一年 {competition.recent_1y_count} 篇</span>
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <p className="text-[11px] text-gray-500 mb-1">谁在做（活跃作者）</p>
                <div className="flex flex-wrap gap-1">
                  {competition.top_authors.map((a) => (
                    <a
                      key={a.name}
                      href={`/author/${encodeURIComponent(a.name)}`}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-[11px] px-2 py-0.5 bg-white dark:bg-gray-700/50 border border-indigo-200 dark:border-indigo-800 rounded-full hover:border-indigo-400 transition-colors"
                    >
                      {a.name} <span className="text-gray-400">{a.count}</span>
                    </a>
                  ))}
                  {competition.top_authors.length === 0 && <span className="text-[11px] text-gray-400">无</span>}
                </div>
              </div>
              <div>
                <p className="text-[11px] text-gray-500 mb-1">发到哪里（期刊分布）</p>
                <div className="flex flex-wrap gap-1">
                  {competition.journal_distribution.map((j) => (
                    <span key={j.journal} className="text-[11px] px-2 py-0.5 bg-white dark:bg-gray-700/50 border border-gray-200 dark:border-gray-600 rounded-full">
                      {j.journal} <span className="text-gray-400">{j.count}</span>
                    </span>
                  ))}
                  {competition.journal_distribution.length === 0 && <span className="text-[11px] text-gray-400">无</span>}
                </div>
              </div>
            </div>
          </div>
        )}

        {/* 思考过程 */}
        {reportReasoning && (
          <div className="mt-4">
            <button
              onClick={() => setReasoningOpen(!reasoningOpen)}
              className="flex items-center gap-1.5 text-xs font-medium text-gray-600 dark:text-gray-300 hover:text-gray-800 dark:hover:text-gray-100 transition-colors"
            >
              <Brain className="w-3.5 h-3.5" /> 思考过程
              <span className="px-1.5 py-px text-[10px] bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-300 rounded">深度思考</span>
              <ChevronDown className={`w-3.5 h-3.5 transition-transform ${reasoningOpen ? 'rotate-180' : ''}`} />
            </button>
            {reasoningOpen && (
              <div className="mt-2 max-h-56 overflow-y-auto rounded-md bg-gray-50 dark:bg-gray-700/40 border border-gray-200 dark:border-gray-600 p-3 text-xs text-gray-500 dark:text-gray-400 whitespace-pre-wrap leading-relaxed">
                {reportReasoning}
              </div>
            )}
          </div>
        )}
      </div>

      {/* 验证报告 */}
      {hasReport && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sm:p-6">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-white">验证报告</h3>
            {validating && <Loader2 className="w-4 h-4 animate-spin text-primary-500" />}
          </div>
          {reportError ? (
            <div className="text-sm text-red-500 py-2">{reportError}</div>
          ) : (
            <div className="prose prose-sm dark:prose-invert max-w-none">
              <MarkdownRenderer content={displayReport || '...'} citations={citations} />
            </div>
          )}
          {(proposalBusy || project.proposal) && (
            <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
              <h4 className="text-xs font-medium text-gray-500 mb-2 flex items-center gap-1.5">
                <FileIcon /> 立项书（自动生成，见第 5 步写作输出）
              </h4>
              {proposalBusy ? (
                <div className="flex items-center gap-2 text-xs text-gray-400"><Loader2 className="w-3.5 h-3.5 animate-spin" /> 正在生成立项书…</div>
              ) : project.proposal ? (
                <p className="text-xs text-gray-500 line-clamp-2">{project.proposal.replace(/^#+.*$/m, '').trim().slice(0, 160)}…</p>
              ) : null}
            </div>
          )}
        </div>
      )}

      {/* 已有研究盘点 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-purple-200 dark:border-purple-800 p-4 sm:p-6">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div>
            <h2 className="flex items-center gap-1.5 text-base font-semibold text-gray-900 dark:text-white">
              <Sparkles className="w-4 h-4 text-purple-600" /> 已有研究盘点
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">
              谁做了什么、用的什么方法/数据、结论共识与争议、差异化空白——让差异化切入有据
            </p>
          </div>
          <button
            onClick={() => runAi('overview')}
            disabled={aiRunning}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white text-sm rounded-lg transition-colors"
          >
            {aiRunning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
            {project.overview ? '重新盘点' : '生成盘点'}
          </button>
        </div>
        {aiRunning && (
          <div className="flex items-center justify-center gap-2 text-sm text-purple-600 dark:text-purple-400 py-6">
            <Loader2 className="w-5 h-5 animate-spin" /> AI 正在盘点已有研究（约 30 秒）…
          </div>
        )}
        {!aiRunning && project.overview && (
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <MarkdownRenderer content={project.overview} citations={citations} />
          </div>
        )}
        {!aiRunning && !project.overview && (
          <p className="text-xs text-gray-400">先「开始验证」召回论文，或到第 3 步「文献管理」添加论文后再生成盘点。</p>
        )}
      </div>
    </div>
  );
}

function FileIcon() {
  return <span className="text-gray-400">📄</span>;
}
