'use client';

import React, { useState, useRef, useMemo, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { ShieldCheck, Loader2, Square, Sparkles, ChevronDown, Brain, RefreshCw, CheckCircle2, Gavel, MessageSquareText } from 'lucide-react';
import { streamValidateTopic, streamDebateTopic, papersApi, getLastModel } from '@/lib/api';
import { parseValidationScores } from '@/lib/topicReport';
import { openAssistant } from '@/lib/assistantBus';
import type { RetrievedPaper, ValidationEvidence } from '@/types/paper';
import type { StepProps } from './types';
import DebateModelSelect from './DebateModelSelect';
import StreamBubble from './StreamBubble';

const MarkdownRenderer = dynamic(() => import('@/components/MarkdownRenderer'), {
  ssr: false,
  loading: () => <div className="h-16 flex items-center justify-center text-gray-400 text-sm animate-pulse">加载中...</div>,
});

type DebateSide = 'pro' | 'con' | 'judge';

interface DebateRound {
  id: string;
  label: string;
  side: DebateSide;
  text: string;
  reasoning: string;
  model?: string;
}

// 默认五轮（每方 2 轮）的展示标签（与后端 skills/debate.py 对齐）
const DEBATE_ROUNDS: Record<string, { label: string; side: DebateSide }> = {
  pro_1: { label: '正方陈述', side: 'pro' },
  con_1: { label: '反方反驳', side: 'con' },
  pro_2: { label: '正方再回应', side: 'pro' },
  con_2: { label: '反方再回应', side: 'con' },
  judge: { label: '评审裁决', side: 'judge' },
};

// 多轮自适应标签（后端 build_round_sequence 可产生 pro_3/con_3 等）
function debateRoundMeta(roundId: string): { label: string; side: DebateSide } {
  const known = DEBATE_ROUNDS[roundId];
  if (known) return known;
  const m = /^(pro|con)_(\d+)$/.exec(roundId);
  if (m) {
    const i = Number(m[2]);
    if (m[1] === 'pro') return { label: i === 1 ? '正方陈述' : `正方第${i}轮`, side: 'pro' };
    return { label: i === 1 ? '反方反驳' : `反方第${i}轮`, side: 'con' };
  }
  return { label: roundId || '辩论', side: 'pro' };
}

export default function Step2Validate({ project, onPatch, goStep }: StepProps) {
  const [validating, setValidating] = useState(false);
  const [reportContent, setReportContent] = useState('');
  const [reportError, setReportError] = useState<string | null>(null);
  const [reportReasoning, setReportReasoning] = useState('');
  const [reasoningOpen, setReasoningOpen] = useState(true);
  const [retrievedPapers, setRetrievedPapers] = useState<RetrievedPaper[]>([]);
  const [retrievedMode, setRetrievedMode] = useState('');
  // 本次验证解析出的结构化评分（驱动完成后的跨步引导卡）
  const [parsed, setParsed] = useState<ReturnType<typeof parseValidationScores>>({});
  const [competition, setCompetition] = useState<{
    top_authors: Array<{ name: string; count: number }>;
    journal_distribution: Array<{ journal: string; count: number }>;
    recent_1y_count: number;
  } | null>(null);
  // Agent 工具模式：验证时允许 AI 调用定量工具查询论文库（拥挤度/空白/趋势）
  const [useTools, setUseTools] = useState(true);
  const [toolProgress, setToolProgress] = useState('');
  const abortRef = useRef<AbortController | null>(null);

  // —— 选题评估辩论状态 ——
  const [debating, setDebating] = useState(false);
  const [debateError, setDebateError] = useState<string | null>(null);
  const [debateRounds, setDebateRounds] = useState<DebateRound[]>([]);
  const [debateScores, setDebateScores] = useState<Record<string, unknown> | null>(null);
  const debateAbortRef = useRef<AbortController | null>(null);
  // onContent/onReasoning 传「全局累积全文」，用前缀差取当前轮增量
  const debateFullTextRef = useRef('');
  const debateReasoningRef = useRef('');
  // 辩论设置：每方轮数、按角色模型（'provider/model'，''=默认）、统一模型开关
  const [debateRoundsPerSide, setDebateRoundsPerSide] = useState(2);
  const [debateModels, setDebateModels] = useState<Record<'pro' | 'con' | 'judge', string>>({ pro: '', con: '', judge: '' });
  const [debateUnified, setDebateUnified] = useState(false);
  const [debateUnifiedModel, setDebateUnifiedModel] = useState('');
  const [debateAiModels, setDebateAiModels] = useState<Array<{ id: string; label: string }>>([]);
  const [debateSettingsOpen, setDebateSettingsOpen] = useState(true);
  const debateScrollRef = useRef<HTMLDivElement | null>(null);
  // 先配置后开跑：辩论 Tab 展开后调好轮数/模型，点「开始辩论」才启动
  const [step2Tab, setStep2Tab] = useState<'validate' | 'debate'>('validate');

  // 加载可用模型列表 + 恢复辩论/答辩各角色的模型记忆
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await papersApi.getAIAnalysisModels();
        const bare = (n: string) => (n.includes('/') ? n.split('/').slice(1).join('/') : n);
        const list = (res.models || [])
          .filter((m) => m.available)
          .map((m) => ({ id: m.name, label: `${m.provider ? `${m.provider} · ` : ''}${bare(m.name)}` }));
        if (cancelled) return;
        setDebateAiModels(list);
        const restored: Record<'pro' | 'con' | 'judge', string> = { pro: '', con: '', judge: '' };
        (['pro', 'con', 'judge'] as const).forEach((role) => {
          const last = getLastModel(`debate_${role}`);
          if (last && list.some((m) => m.id === last)) restored[role] = last;
        });
        setDebateModels(restored);
      } catch { /* 模型列表加载失败：仍可用默认模型 */ }
    })();
    return () => { cancelled = true; };
  }, []);

  // 自动滚动到最新一轮
  useEffect(() => {
    if (debating && debateScrollRef.current) {
      debateScrollRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [debateRounds, debating]);

  const hasReport = !!(project.validation_report || reportContent);

  // 检索关键词：优先 Step1 手动维护的 search_keywords，回退灵感快照 generated_topics[*].keywords
  const keywords = useMemo(() => {
    const saved = (project.search_keywords || []).map((k) => (k || '').trim()).filter(Boolean);
    if (saved.length > 0) return saved;
    const set = new Set<string>();
    for (const g of project.generated_topics || []) {
      for (const k of g.keywords || []) {
        const t = k.trim();
        if (t) set.add(t);
      }
    }
    return Array.from(set);
  }, [project.search_keywords, project.generated_topics]);

  const citations = useMemo(() => {
    const map: Record<number, { id: string; title?: string }> = {};
    for (const p of retrievedPapers) {
      if (p.n !== undefined) map[p.n] = { id: String(p.id), title: p.title };
    }
    return map;
  }, [retrievedPapers]);

  // 进入步骤时恢复上一次验证记录的证据（召回列表/模式/竞争地图随报告一起沉淀在项目上）
  const lastEvidence = project.validation_evidence as ValidationEvidence | null | undefined;
  useEffect(() => {
    if (!lastEvidence?.papers?.length) return;
    setRetrievedPapers(lastEvidence.papers);
    setRetrievedMode(lastEvidence.mode || '');
    if (lastEvidence.competition) setCompetition(lastEvidence.competition);
    // 仅在进入该步骤（项目切换）时恢复一次；重新验证由流式回调解覆盖
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [project.id]);

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
    setParsed({});
    const controller = new AbortController();
    abortRef.current = controller;
    // 流式期间的证据暂存（onDone 时随报告一起落库）
    let metaPapers: RetrievedPaper[] = [];
    let metaMode = '';
    let metaCompetition: ValidationEvidence['competition'] = null;
    await streamValidateTopic(
      topic,
      undefined,
      {
        // streamChat 的 onContent/onReasoning 传的是「已累积全文」（与 trends 页一致），
        // 不能再本地累加，否则报告会随流式片段成倍重复
        onContent: (text) => setReportContent(text),
        onReasoning: (text) => setReportReasoning(text),
        onToolProgress: (data) => {
          setToolProgress(data?.tool || '');
        },
        onMeta: (data) => {
          if (data && typeof data === 'object' && 'papers' in data) {
            const meta = data as any;
            metaPapers = Array.isArray(meta.papers) ? meta.papers : [];
            metaMode = typeof meta.mode === 'string' ? meta.mode : '';
            metaCompetition = meta.stats?.competition || null;
            setRetrievedPapers(metaPapers);
            setRetrievedMode(metaMode);
            if (metaCompetition) setCompetition(metaCompetition);
          }
        },
        onDone: (fullContent) => {
          setValidating(false);
          setToolProgress('');
          // 验证报告 + 证据快照 + 结构化评分一并沉淀回项目（评分驱动列表展示与状态）
          if (fullContent) {
            const scores = parseValidationScores(fullContent);
            setParsed(scores);
            onPatch({
              validation_report: fullContent,
              validation_evidence: {
                papers: metaPapers,
                mode: metaMode,
                competition: metaCompetition,
                validated_at: new Date().toISOString(),
              },
              novelty: scores.novelty ?? undefined,
              crowding: scores.crowding ?? undefined,
              feasibility: undefined,
            });
          }
        },
        onError: (msg) => {
          setReportError(msg);
          setValidating(false);
          setToolProgress('');
        },
      },
      controller.signal,
      project.id,
      useTools,
    );
  };

  const handleAbort = () => {
    abortRef.current?.abort();
    setValidating(false);
  };

  const handleDebateAbort = () => {
    debateAbortRef.current?.abort();
    setDebating(false);
  };

  const handleDebate = async () => {
    const topic = project.title.trim();
    if (!topic || debating) return;
    setDebating(true);
    setDebateError(null);
    setDebateRounds([]);
    setDebateScores(null);
    debateFullTextRef.current = '';
    debateReasoningRef.current = '';
    const controller = new AbortController();
    debateAbortRef.current = controller;
    let metaPapers: RetrievedPaper[] = [];
    let metaMode = '';
    let metaCompetition: ValidationEvidence['competition'] = null;
    // 按角色模型载荷（统一开关时三键同值；'' 默认项省略，走全局默认）
    const modelsPayload: Record<string, string> = {};
    if (debateUnified) {
      if (debateUnifiedModel) {
        modelsPayload.pro = debateUnifiedModel;
        modelsPayload.con = debateUnifiedModel;
        modelsPayload.judge = debateUnifiedModel;
      }
    } else {
      (['pro', 'con', 'judge'] as const).forEach((role) => {
        if (debateModels[role]) modelsPayload[role] = debateModels[role];
      });
    }
    await streamDebateTopic(
      topic,
      project.id,
      {
        onContent: (text) => {
          const delta = text.slice(debateFullTextRef.current.length);
          debateFullTextRef.current = text;
          if (!delta) return;
          setDebateRounds((prev) => {
            const arr = [...prev];
            const last = arr[arr.length - 1];
            if (!last) return arr; // 首个 round 元帧到达前丢弃正文增量
            arr[arr.length - 1] = { ...last, text: last.text + delta };
            return arr;
          });
        },
        onReasoning: (text) => {
          const delta = text.slice(debateReasoningRef.current.length);
          debateReasoningRef.current = text;
          if (!delta) return;
          setDebateRounds((prev) => {
            const arr = [...prev];
            const last = arr[arr.length - 1];
            if (!last) return arr;
            arr[arr.length - 1] = { ...last, reasoning: (last.reasoning || '') + delta };
            return arr;
          });
        },
        onMeta: (data) => {
          if (!data || typeof data !== 'object') return;
          const d = data as Record<string, unknown>;
          if ('round' in d) {
            const roundId = String(d.round ?? '');
            const meta = debateRoundMeta(roundId);
            const model = typeof d.model === 'string' ? d.model : undefined;
            setDebateRounds((prev) => [...prev, { id: roundId, label: meta.label, side: meta.side, text: '', reasoning: '', model }]);
          } else if ('debate_scores' in d) {
            setDebateScores((d.debate_scores as Record<string, unknown>) || null);
          } else if ('papers' in d) {
            const p = d.papers as any[];
            metaPapers = Array.isArray(p) ? p : [];
            metaMode = typeof d.mode === 'string' ? d.mode : '';
            metaCompetition = (d as any).stats?.competition || null;
            setRetrievedPapers(metaPapers);
            setRetrievedMode(metaMode);
            if (metaCompetition) setCompetition(metaCompetition);
          }
        },
        onDone: () => {
          setDebating(false);
        },
        onError: (msg) => {
          setDebateError(msg);
          setDebating(false);
        },
      },
      controller.signal,
      debateRoundsPerSide,
      modelsPayload,
    );
  };

  // 验证用的初始报告：优先当前流式内容，其次项目已保存的
  const displayReport = reportContent || project.validation_report || '';

  return (
    <div className="space-y-5">
      {/* Tab：选题验证 | 进阶评估·辩论 */}
      <div className="flex items-center gap-1 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-1 w-fit">
        {([
          { key: 'validate', label: '选题验证' },
          { key: 'debate', label: '进阶评估 · 辩论' },
        ] as const).map((t) => (
          <button
            key={t.key}
            onClick={() => setStep2Tab(t.key)}
            className={`px-3.5 py-1.5 text-sm rounded-md transition-colors ${
              step2Tab === t.key
                ? 'bg-primary-600 text-white font-medium'
                : 'text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {step2Tab === 'validate' && (
      <>
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
            {keywords.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
                <span className="text-xs text-gray-400">检索关键词</span>
                {keywords.map((k) => (
                  <span
                    key={k}
                    className="text-[11px] px-2 py-0.5 bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 border border-gray-200 dark:border-gray-600 rounded-full"
                  >
                    {k}
                  </span>
                ))}
              </div>
            )}
          </div>
          <div className="flex gap-2 items-center">
            <label
              className="inline-flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 cursor-pointer select-none"
              title="开启后 AI 可在写报告前调用论文库工具（拥挤度统计/空白组合/趋势）核验证据"
            >
              <input
                type="checkbox"
                checked={useTools}
                onChange={(e) => setUseTools(e.target.checked)}
                className="w-3.5 h-3.5 accent-purple-600"
              />
              工具查询
            </label>
            {validating ? (
              <>
                <span className="inline-flex items-center gap-1 text-xs text-purple-600 dark:text-purple-400">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  {toolProgress ? `正在查询：${toolProgress}` : 'AI 正在验证'}
                </span>
                <button
                  onClick={handleAbort}
                  className="inline-flex items-center gap-1.5 px-4 py-2 bg-red-500 hover:bg-red-600 text-white text-sm rounded-lg transition-colors"
                >
                  <Square className="w-4 h-4" /> 停止
                </button>
              </>
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
      </>
      )}

      {step2Tab === 'debate' && (
      <>
      {/* 选题辩论：正方/反方各 N 轮（左右双栏）+ 评审裁决（跨栏居中） */}
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-violet-200 dark:border-violet-800 p-4 sm:p-6">
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <h3 className="flex items-center gap-1.5 text-sm font-semibold text-gray-900 dark:text-white">
              <MessageSquareText className="w-4 h-4 text-violet-600" /> 选题辩论
              <span className="text-[11px] font-normal text-gray-400">
                正反交锋 · 基于论文库证据 · 每方 {debateRoundsPerSide} 轮
              </span>
            </h3>
            {debating && (
              <span className="inline-flex items-center gap-1 text-xs text-violet-600 dark:text-violet-400">
                <Loader2 className="w-3.5 h-3.5 animate-spin" /> 辩论进行中…
              </span>
            )}
          </div>

          {/* 辩论设置（可折叠） */}
          <div className="mb-3">
            <button
              onClick={() => setDebateSettingsOpen((v) => !v)}
              className="flex items-center gap-1 text-[11px] font-medium text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
            >
              <Gavel className="w-3 h-3" /> 辩论设置
              <ChevronDown className={`w-3 h-3 transition-transform ${debateSettingsOpen ? 'rotate-180' : ''}`} />
            </button>
            {debateSettingsOpen && (
              <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg bg-gray-50 dark:bg-gray-700/30 border border-gray-200 dark:border-gray-600 p-3">
                {/* 每方轮数 */}
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0">每方轮数</span>
                  <div className="inline-flex rounded-md border border-gray-200 dark:border-gray-600 overflow-hidden">
                    {[1, 2, 3].map((n) => (
                      <button
                        key={n}
                        onClick={() => setDebateRoundsPerSide(n)}
                        disabled={debating}
                        className={`px-2.5 py-1 text-xs transition-colors disabled:opacity-50 ${
                          debateRoundsPerSide === n
                            ? 'bg-violet-600 text-white'
                            : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                        }`}
                      >
                        {n}
                      </button>
                    ))}
                  </div>
                </div>
                {/* 统一模型快捷开关 */}
                <label className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 cursor-pointer select-none" title="所有角色用同一个模型">
                  <input
                    type="checkbox"
                    checked={debateUnified}
                    onChange={(e) => setDebateUnified(e.target.checked)}
                    className="w-3.5 h-3.5 accent-violet-600"
                  />
                  统一使用同一模型
                </label>
                {/* 模型选择：统一开关时单个下拉，否则三角色各一个 */}
                {debateUnified ? (
                  <DebateModelSelect
                    roleLabel="模型"
                    memKey="debate_unified"
                    value={debateUnifiedModel}
                    models={debateAiModels}
                    onChange={setDebateUnifiedModel}
                  />
                ) : (
                  <>
                    <DebateModelSelect roleLabel="正方" memKey="debate_pro" value={debateModels.pro} models={debateAiModels}
                      onChange={(v) => setDebateModels((m) => ({ ...m, pro: v }))} />
                    <DebateModelSelect roleLabel="反方" memKey="debate_con" value={debateModels.con} models={debateAiModels}
                      onChange={(v) => setDebateModels((m) => ({ ...m, con: v }))} />
                    <DebateModelSelect roleLabel="评审" memKey="debate_judge" value={debateModels.judge} models={debateAiModels}
                      onChange={(v) => setDebateModels((m) => ({ ...m, judge: v }))} />
                  </>
                )}
                {/* 先配置后开跑：调好轮数/模型后点此启动 */}
                {!debating && (
                  <button
                    onClick={handleDebate}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-violet-600 hover:bg-violet-700 text-white text-xs rounded-lg transition-colors ml-auto"
                  >
                    <Gavel className="w-3.5 h-3.5" /> 开始辩论（{debateRoundsPerSide} 轮）
                  </button>
                )}
              </div>
            )}
          </div>

          {debateError && <div className="text-sm text-red-500 py-2">{debateError}</div>}

          {/* 左右双栏：正方 / 反方，评审跨栏居中 */}
          {(() => {
            const proRounds = debateRounds.filter((r) => r.side === 'pro');
            const conRounds = debateRounds.filter((r) => r.side === 'con');
            const judgeRounds = debateRounds.filter((r) => r.side === 'judge');
            const isLatest = (r: DebateRound) => debateRounds[debateRounds.length - 1]?.id === r.id;

            const colorCls = (side: DebateSide) =>
              side === 'pro'
                ? 'bg-blue-50 dark:bg-blue-900/15 border-blue-200 dark:border-blue-800'
                : side === 'con'
                  ? 'bg-red-50 dark:bg-red-900/15 border-red-200 dark:border-red-800'
                  : 'bg-violet-50 dark:bg-violet-900/15 border-violet-200 dark:border-violet-800';

            // StreamBubble：流式中纯文本逐 token 渲染，结束后切 Markdown；
            // React.memo 保证增量只重渲染当前轮（已完成轮次不重解析 markdown）
            const bubble = (r: DebateRound) => (
              <StreamBubble key={r.id} r={r} colorCls={colorCls(r.side)} streaming={debating && isLatest(r)} citations={citations} />
            );

            return (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-5 gap-y-4">
                {/* 正方列 */}
                <div className="space-y-3">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-blue-600 dark:text-blue-400">
                    <span className="w-2 h-2 rounded-full bg-blue-500" /> 正方 · 支持
                  </div>
                  {proRounds.length === 0 && debating && (
                    <div className="text-xs text-gray-400 animate-pulse">正方尚未发言…</div>
                  )}
                  {proRounds.map(bubble)}
                </div>
                {/* 反方列 */}
                <div className="space-y-3">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-red-600 dark:text-red-400">
                    <span className="w-2 h-2 rounded-full bg-red-500" /> 反方 · 质疑
                  </div>
                  {conRounds.length === 0 && debating && (
                    <div className="text-xs text-gray-400 animate-pulse">反方尚未发言…</div>
                  )}
                  {conRounds.map(bubble)}
                </div>
                {/* 评审轮：跨栏居中 */}
                {judgeRounds.length > 0 && (
                  <div className="lg:col-span-2 space-y-3">
                    <div className="flex items-center justify-center gap-1.5 text-xs font-semibold text-violet-600 dark:text-violet-400">
                      <Gavel className="w-3 h-3" /> 评审裁决
                    </div>
                    <div className="max-w-2xl mx-auto">{judgeRounds.map(bubble)}</div>
                  </div>
                )}
                <div ref={debateScrollRef} className="lg:col-span-2" />
              </div>
            );
          })()}

          {/* 裁决分数（复用 validate 评分轴；前端解析展示，服务端已落库） */}
          {debateScores && !debating && (
            <div className="mt-4 flex items-center gap-2 flex-wrap bg-violet-50 dark:bg-violet-900/15 border border-violet-200 dark:border-violet-800/60 rounded-lg p-3">
              <CheckCircle2 className="w-4 h-4 text-violet-600 shrink-0" />
              <span className="text-xs text-violet-700 dark:text-violet-300">
                裁决
                {debateScores.novelty != null && <> · 新颖性 <strong>{String(debateScores.novelty)}/10</strong></>}
                {!!debateScores.crowding && <> · 拥挤度 <strong>{String(debateScores.crowding)}</strong></>}
                {debateScores.feasibility != null && <> · 可行性 <strong>{String(debateScores.feasibility)}/10</strong></>}
                {!!debateScores.gate && <> · 门控 <strong>{String(debateScores.gate)}</strong></>}
              </span>
              <button onClick={() => goStep(1)} className="text-xs font-medium text-violet-600 dark:text-violet-400 hover:underline">
                带着结论去改题 →
              </button>
              <button onClick={() => goStep(3)} className="text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline">
                去第 3 步召回文献 →
              </button>
            </div>
          )}
        </div>
      </>
      )}

      {step2Tab === 'validate' && (
      <>
      {/* 验证报告 */}
      {hasReport && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sm:p-6">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white">验证报告</h3>
              {lastEvidence?.validated_at && (
                <span className="text-[11px] text-gray-400">
                  上次验证：{new Date(lastEvidence.validated_at).toLocaleString()}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => openAssistant({ contextText: project.title, autoPrompt: '请帮我解读这份选题验证报告的关键结论，并指出最值得注意的风险' })}
                disabled={validating}
                className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded-md border border-purple-200 dark:border-purple-800 text-purple-600 dark:text-purple-300 hover:bg-purple-50 dark:hover:bg-purple-900/20 transition-colors disabled:opacity-50"
              >
                <Sparkles className="w-3 h-3" /> 问 AI 解读
              </button>
              {validating && <Loader2 className="w-4 h-4 animate-spin text-primary-500" />}
            </div>
          </div>
          {reportError ? (
            <div className="text-sm text-red-500 py-2">{reportError}</div>
          ) : (
            <div className="prose prose-sm dark:prose-invert max-w-none">
              <MarkdownRenderer content={displayReport || '...'} citations={citations} />
            </div>
          )}
          {/* 验证通过后可去第 5 步生成立项书（此时文献/数据步骤完整，报告更扎实） */}
          <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
            <p className="text-xs text-gray-500 mb-2">
              验证结论可用于生成立项书；建议先完成文献与数据步骤，再在第 5 步生成更完整的立项书。
            </p>
            <button
              onClick={() => goStep(5)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-primary-600 hover:bg-primary-700 text-white text-xs rounded-lg transition-colors"
            >
              去第 5 步生成立项书 →
            </button>
          </div>
        </div>
      )}

      {/* 验证完成后的跨步引导卡（评分由后端结构化落库；正则结果仅用于展示） */}
      {!validating && reportContent && (
        <div className="flex items-center gap-2 flex-wrap bg-green-50 dark:bg-green-900/10 border border-green-200 dark:border-green-800/60 rounded-lg p-3">
          <CheckCircle2 className="w-4 h-4 text-green-600 shrink-0" />
          <span className="text-xs text-green-700 dark:text-green-300">
            验证完成
            {parsed.novelty != null && <> · 新颖性 <strong>{parsed.novelty}/10</strong></>}
            {parsed.crowding && <> · 拥挤度：<strong>{parsed.crowding}</strong></>}
          </span>
          <button onClick={() => goStep(1)} className="text-xs font-medium text-green-700 dark:text-green-300 hover:underline">
            带着结论去改题 →
          </button>
          <button onClick={() => goStep(3)} className="text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline">
            去第 3 步召回文献 →
          </button>
        </div>
      )}
      </>
      )}
    </div>
  );
}
