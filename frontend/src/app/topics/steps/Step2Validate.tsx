'use client';

import React, { useState, useRef, useMemo, useEffect } from 'react';
import dynamic from 'next/dynamic';
import { ShieldCheck, Loader2, Square, Sparkles, ChevronDown, Brain, RefreshCw, CheckCircle2, FileText, Gavel, MessageSquareText } from 'lucide-react';
import { streamValidateTopic, streamDebateTopic, streamDefenseTopic, workbenchApi, papersApi, getLastModel, rememberModel } from '@/lib/api';
import { parseValidationScores } from '@/lib/topicReport';
import { openAssistant } from '@/lib/assistantBus';
import type { RetrievedPaper, ValidationEvidence } from '@/types/paper';
import type { StepProps } from './types';

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

// —— 答辩（defense）类型与标签 ——
type DefenseRole = 'candidate' | 'examiner' | 'panel';

interface DefenseRound {
  id: string;
  label: string;
  role: DefenseRole;
  text: string;
  reasoning: string;
  model?: string;
}

// 后端 build_round_sequence：candidate_0 -> examiner_k/candidate_k 交替 -> panel
function defenseRoundMeta(roundId: string): { label: string; role: DefenseRole } {
  const m = /^(candidate|examiner)_(\d+)$/.exec(roundId);
  if (m) {
    const i = Number(m[2]);
    if (m[1] === 'candidate') return { label: i === 0 ? '候选人自述' : `候选人应答·第${i}轮`, role: 'candidate' };
    return { label: `评委质询·第${i}问`, role: 'examiner' };
  }
  if (roundId === 'panel') return { label: '合议裁定', role: 'panel' };
  return { label: roundId || '答辩', role: 'panel' };
}

// 角色模型下拉（Step4Data 同款交互：默认项 + provider · bare）
function DebateModelSelect({ roleLabel, memKey, value, models, onChange }: {
  roleLabel: string;
  memKey: string;
  value: string;
  models: Array<{ id: string; label: string }>;
  onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const pick = (v: string) => {
    rememberModel(memKey, v || null);
    onChange(v);
    setOpen(false);
  };
  return (
    <div className="relative inline-flex items-center gap-1.5">
      <span className="text-xs text-gray-400 shrink-0">{roleLabel}</span>
      <button
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs text-gray-500 dark:text-gray-400 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors"
        title="选择该角色的模型（默认自动跟随全局设置）"
      >
        {value ? (models.find((m) => m.id === value)?.label || value) : '默认模型'}
        <ChevronDown className={`w-3 h-3 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div className="absolute right-0 top-9 z-20 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg py-1 min-w-[200px] max-h-72 overflow-y-auto">
          <button
            onClick={() => pick('')}
            className={`w-full text-left px-3 py-1.5 text-xs hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors ${value === '' ? 'text-violet-600 font-medium' : 'text-gray-700 dark:text-gray-300'}`}
          >
            默认（跟随全局设置）
          </button>
          {models.map((m) => (
            <button
              key={m.id}
              onClick={() => pick(m.id)}
              className={`w-full text-left px-3 py-1.5 text-xs hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors ${value === m.id ? 'text-violet-600 font-medium' : 'text-gray-700 dark:text-gray-300'}`}
            >
              {m.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Step2Validate({ project, onPatch, runAi, goStep }: StepProps) {
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
  const [proposalBusy, setProposalBusy] = useState(false);
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

  // —— 选题答辩状态 ——
  const [defending, setDefending] = useState(false);
  const [defenseError, setDefenseError] = useState<string | null>(null);
  const [defenseRounds, setDefenseRounds] = useState<DefenseRound[]>([]);
  const [defenseScores, setDefenseScores] = useState<Record<string, unknown> | null>(null);
  const defenseAbortRef = useRef<AbortController | null>(null);
  const defenseFullTextRef = useRef('');
  const defenseReasoningRef = useRef('');
  const [defenseRoundsPerSide, setDefenseRoundsPerSide] = useState(2);
  const [defenseModels, setDefenseModels] = useState<Record<'candidate' | 'examiner' | 'panel', string>>({ candidate: '', examiner: '', panel: '' });
  const [defenseUnified, setDefenseUnified] = useState(false);
  const [defenseUnifiedModel, setDefenseUnifiedModel] = useState('');
  const [defenseSettingsOpen, setDefenseSettingsOpen] = useState(true);
  const defenseScrollRef = useRef<HTMLDivElement | null>(null);

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
        const dRestored: Record<'candidate' | 'examiner' | 'panel', string> = { candidate: '', examiner: '', panel: '' };
        (['candidate', 'examiner', 'panel'] as const).forEach((role) => {
          const last = getLastModel(`defense_${role}`);
          if (last && list.some((m) => m.id === last)) dRestored[role] = last;
        });
        setDefenseModels(dRestored);
      } catch { /* 模型列表加载失败：仍可用默认模型 */ }
    })();
    return () => { cancelled = true; };
  }, []);

  // 自动滚动到最新一轮（辩论/答辩共用）
  useEffect(() => {
    if (debating && debateScrollRef.current) {
      debateScrollRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    if (defending && defenseScrollRef.current) {
      defenseScrollRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [debateRounds, defenseRounds, debating, defending]);

  const aiRunning = project.ai_pending === 'overview';
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
            autoProposal(fullContent);
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

  const handleDebateAbort = () => {
    debateAbortRef.current?.abort();
    setDebating(false);
  };

  const handleDefenseAbort = () => {
    defenseAbortRef.current?.abort();
    setDefending(false);
  };

  const handleDefense = async () => {
    const topic = project.title.trim();
    if (!topic || defending) return;
    setDefending(true);
    setDefenseError(null);
    setDefenseRounds([]);
    setDefenseScores(null);
    defenseFullTextRef.current = '';
    defenseReasoningRef.current = '';
    const controller = new AbortController();
    defenseAbortRef.current = controller;
    let metaPapers: RetrievedPaper[] = [];
    let metaMode = '';
    let metaCompetition: ValidationEvidence['competition'] = null;
    const modelsPayload: Record<string, string> = {};
    if (defenseUnified) {
      if (defenseUnifiedModel) {
        modelsPayload.candidate = defenseUnifiedModel;
        modelsPayload.examiner = defenseUnifiedModel;
        modelsPayload.panel = defenseUnifiedModel;
      }
    } else {
      (['candidate', 'examiner', 'panel'] as const).forEach((role) => {
        if (defenseModels[role]) modelsPayload[role] = defenseModels[role];
      });
    }
    await streamDefenseTopic(
      topic,
      project.id,
      {
        onContent: (text) => {
          const delta = text.slice(defenseFullTextRef.current.length);
          defenseFullTextRef.current = text;
          if (!delta) return;
          setDefenseRounds((prev) => {
            const arr = [...prev];
            const last = arr[arr.length - 1];
            if (!last) return arr;
            arr[arr.length - 1] = { ...last, text: last.text + delta };
            return arr;
          });
        },
        onReasoning: (text) => {
          const delta = text.slice(defenseReasoningRef.current.length);
          defenseReasoningRef.current = text;
          if (!delta) return;
          setDefenseRounds((prev) => {
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
            const meta = defenseRoundMeta(roundId);
            const model = typeof d.model === 'string' ? d.model : undefined;
            setDefenseRounds((prev) => [...prev, { id: roundId, label: meta.label, role: meta.role, text: '', reasoning: '', model }]);
          } else if ('defense_scores' in d) {
            setDefenseScores((d.defense_scores as Record<string, unknown>) || null);
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
          setDefending(false);
        },
        onError: (msg) => {
          setDefenseError(msg);
          setDefending(false);
        },
      },
      controller.signal,
      defenseRoundsPerSide,
      modelsPayload,
    );
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
            ) : debating ? (
              <>
                <span className="inline-flex items-center gap-1 text-xs text-violet-600 dark:text-violet-400">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" /> 辩论进行中
                </span>
                <button
                  onClick={handleDebateAbort}
                  className="inline-flex items-center gap-1.5 px-4 py-2 bg-red-500 hover:bg-red-600 text-white text-sm rounded-lg transition-colors"
                >
                  <Square className="w-4 h-4" /> 停止
                </button>
              </>
            ) : defending ? (
              <>
                <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                  <Loader2 className="w-3.5 h-3.5 animate-spin" /> 答辩进行中
                </span>
                <button
                  onClick={handleDefenseAbort}
                  className="inline-flex items-center gap-1.5 px-4 py-2 bg-red-500 hover:bg-red-600 text-white text-sm rounded-lg transition-colors"
                >
                  <Square className="w-4 h-4" /> 停止
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={handleDebate}
                  title="正方/反方各 N 轮交锋 + 评审按预承诺标准裁决（基于论文库证据）"
                  className="inline-flex items-center gap-1.5 px-4 py-2 bg-violet-600 hover:bg-violet-700 text-white text-sm rounded-lg transition-colors"
                >
                  <Gavel className="w-4 h-4" />
                  {debateRounds.length > 0 ? '再次辩论' : '发起辩论'}
                </button>
                <button
                  onClick={handleDefense}
                  title="候选人自述 + 评委质询/候选人应答 N 轮 + 合议裁定（模拟论文答辩）"
                  className="inline-flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm rounded-lg transition-colors"
                >
                  <MessageSquareText className="w-4 h-4" />
                  {defenseRounds.length > 0 ? '再次答辩' : '模拟答辩'}
                </button>
                <button
                  onClick={handleValidate}
                  className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-sm rounded-lg transition-colors"
                >
                  {project.validation_report ? <RefreshCw className="w-4 h-4" /> : <ShieldCheck className="w-4 h-4" />}
                  {project.validation_report ? '重新验证' : '开始验证'}
                </button>
              </>
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

      {/* 选题辩论：正方/反方各 N 轮（左右双栏）+ 评审裁决（跨栏居中） */}
      {(debateRounds.length > 0 || debating || debateError) && (
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

            const bubble = (r: DebateRound) => (
              <div
                key={r.id}
                className={`rounded-lg border p-3 transition-all duration-300 ${
                  r.side === 'pro'
                    ? 'bg-blue-50 dark:bg-blue-900/15 border-blue-200 dark:border-blue-800'
                    : r.side === 'con'
                      ? 'bg-red-50 dark:bg-red-900/15 border-red-200 dark:border-red-800'
                      : 'bg-violet-50 dark:bg-violet-900/15 border-violet-200 dark:border-violet-800'
                }`}
              >
                <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                  <span className="text-[11px] font-semibold text-gray-500 dark:text-gray-400">{r.label}</span>
                  {r.model && (
                    <span className="text-[10px] px-1.5 py-px rounded bg-white/70 dark:bg-gray-700/70 text-gray-400 font-mono">
                      {r.model.split('/').pop()}
                    </span>
                  )}
                  {debating && isLatest(r) && !r.text && (
                    <span className="inline-flex items-center gap-1 text-[11px] text-gray-400 animate-pulse">
                      <Loader2 className="w-3 h-3 animate-spin" />
                      {r.reasoning ? '思考中，即将成文…' : '思考中…'}
                    </span>
                  )}
                </div>
                {r.reasoning && (
                  <details className="mb-1.5" open={debating && isLatest(r)}>
                    <summary className="text-[10px] text-gray-400 cursor-pointer select-none hover:text-gray-500">思考过程</summary>
                    <div className="mt-1 max-h-40 overflow-y-auto whitespace-pre-wrap text-[11px] leading-relaxed text-gray-400/90 dark:text-gray-500">
                      {r.reasoning}
                    </div>
                  </details>
                )}
                <div className="prose prose-sm dark:prose-invert max-w-none">
                  <MarkdownRenderer content={r.text || (debating && isLatest(r) && !r.reasoning ? '…' : '')} citations={citations} />
                </div>
              </div>
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
              <button onClick={() => goStep(3)} className="text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline">
                去第 3 步召回文献 →
              </button>
            </div>
          )}
        </div>
      )}

      {/* 选题答辩：候选人自述 + 评委质询/候选人应答 N 轮 + 合议裁定 */}
      {(defenseRounds.length > 0 || defending || defenseError) && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-emerald-200 dark:border-emerald-800 p-4 sm:p-6">
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <h3 className="flex items-center gap-1.5 text-sm font-semibold text-gray-900 dark:text-white">
              <MessageSquareText className="w-4 h-4 text-emerald-600" /> 选题答辩
              <span className="text-[11px] font-normal text-gray-400">
                模拟论文答辩 · 自述 + {defenseRoundsPerSide} 轮质询 + 合议
              </span>
            </h3>
            {defending && (
              <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                <Loader2 className="w-3.5 h-3.5 animate-spin" /> 答辩进行中…
              </span>
            )}
          </div>

          {/* 答辩设置（可折叠） */}
          <div className="mb-3">
            <button
              onClick={() => setDefenseSettingsOpen((v) => !v)}
              className="flex items-center gap-1 text-[11px] font-medium text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
            >
              <Gavel className="w-3 h-3" /> 答辩设置
              <ChevronDown className={`w-3 h-3 transition-transform ${defenseSettingsOpen ? 'rotate-180' : ''}`} />
            </button>
            {defenseSettingsOpen && (
              <div className="mt-2 flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg bg-gray-50 dark:bg-gray-700/30 border border-gray-200 dark:border-gray-600 p-3">
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-gray-500 dark:text-gray-400 shrink-0">质询轮数</span>
                  <div className="inline-flex rounded-md border border-gray-200 dark:border-gray-600 overflow-hidden">
                    {[1, 2, 3].map((n) => (
                      <button
                        key={n}
                        onClick={() => setDefenseRoundsPerSide(n)}
                        disabled={defending}
                        className={`px-2.5 py-1 text-xs transition-colors disabled:opacity-50 ${
                          defenseRoundsPerSide === n
                            ? 'bg-emerald-600 text-white'
                            : 'bg-white dark:bg-gray-700 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                        }`}
                      >
                        {n}
                      </button>
                    ))}
                  </div>
                </div>
                <label className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 cursor-pointer select-none" title="所有角色用同一个模型">
                  <input
                    type="checkbox"
                    checked={defenseUnified}
                    onChange={(e) => setDefenseUnified(e.target.checked)}
                    className="w-3.5 h-3.5 accent-emerald-600"
                  />
                  统一使用同一模型
                </label>
                {defenseUnified ? (
                  <DebateModelSelect
                    roleLabel="模型"
                    memKey="defense_unified"
                    value={defenseUnifiedModel}
                    models={debateAiModels}
                    onChange={setDefenseUnifiedModel}
                  />
                ) : (
                  <>
                    <DebateModelSelect roleLabel="候选人" memKey="defense_candidate" value={defenseModels.candidate} models={debateAiModels}
                      onChange={(v) => setDefenseModels((m) => ({ ...m, candidate: v }))} />
                    <DebateModelSelect roleLabel="评委" memKey="defense_examiner" value={defenseModels.examiner} models={debateAiModels}
                      onChange={(v) => setDefenseModels((m) => ({ ...m, examiner: v }))} />
                    <DebateModelSelect roleLabel="合议" memKey="defense_panel" value={defenseModels.panel} models={debateAiModels}
                      onChange={(v) => setDefenseModels((m) => ({ ...m, panel: v }))} />
                  </>
                )}
              </div>
            )}
          </div>

          {defenseError && <div className="text-sm text-red-500 py-2">{defenseError}</div>}

          {/* 布局：自述跨栏置顶 → 双栏（评委质询左/候选人应答右）→ 合议跨栏置底 */}
          {(() => {
            const opening = defenseRounds.find((r) => r.id === 'candidate_0');
            const examinerRounds = defenseRounds.filter((r) => r.role === 'examiner');
            const answerRounds = defenseRounds.filter((r) => r.role === 'candidate' && r.id !== 'candidate_0');
            const panelRounds = defenseRounds.filter((r) => r.role === 'panel');
            const isLatest = (r: DefenseRound) => defenseRounds[defenseRounds.length - 1]?.id === r.id;

            const bubble = (r: DefenseRound) => (
              <div
                key={r.id}
                className={`rounded-lg border p-3 transition-all duration-300 ${
                  r.role === 'candidate'
                    ? 'bg-emerald-50 dark:bg-emerald-900/15 border-emerald-200 dark:border-emerald-800'
                    : r.role === 'examiner'
                      ? 'bg-amber-50 dark:bg-amber-900/15 border-amber-200 dark:border-amber-800'
                      : 'bg-violet-50 dark:bg-violet-900/15 border-violet-200 dark:border-violet-800'
                }`}
              >
                <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                  <span className="text-[11px] font-semibold text-gray-500 dark:text-gray-400">{r.label}</span>
                  {r.model && (
                    <span className="text-[10px] px-1.5 py-px rounded bg-white/70 dark:bg-gray-700/70 text-gray-400 font-mono">
                      {r.model.split('/').pop()}
                    </span>
                  )}
                  {defending && isLatest(r) && !r.text && (
                    <span className="inline-flex items-center gap-1 text-[11px] text-gray-400 animate-pulse">
                      <Loader2 className="w-3 h-3 animate-spin" />
                      {r.reasoning ? '思考中，即将成文…' : '思考中…'}
                    </span>
                  )}
                </div>
                {r.reasoning && (
                  <details className="mb-1.5" open={defending && isLatest(r)}>
                    <summary className="text-[10px] text-gray-400 cursor-pointer select-none hover:text-gray-500">思考过程</summary>
                    <div className="mt-1 max-h-40 overflow-y-auto whitespace-pre-wrap text-[11px] leading-relaxed text-gray-400/90 dark:text-gray-500">
                      {r.reasoning}
                    </div>
                  </details>
                )}
                <div className="prose prose-sm dark:prose-invert max-w-none">
                  <MarkdownRenderer content={r.text || (defending && isLatest(r) && !r.reasoning ? '…' : '')} citations={citations} />
                </div>
              </div>
            );

            return (
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-x-5 gap-y-4">
                {/* 候选人自述：跨栏置顶 */}
                {opening && <div className="lg:col-span-2 space-y-3">{bubble(opening)}</div>}
                {!opening && defending && (
                  <div className="lg:col-span-2 text-xs text-gray-400 animate-pulse">候选人正在自述研究设计…</div>
                )}
                {/* 评委质询列 */}
                <div className="space-y-3">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-600 dark:text-amber-400">
                    <span className="w-2 h-2 rounded-full bg-amber-500" /> 评委质询
                  </div>
                  {examinerRounds.length === 0 && defending && (
                    <div className="text-xs text-gray-400 animate-pulse">评委尚未质询…</div>
                  )}
                  {examinerRounds.map(bubble)}
                </div>
                {/* 候选人应答列 */}
                <div className="space-y-3">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                    <span className="w-2 h-2 rounded-full bg-emerald-500" /> 候选人应答
                  </div>
                  {answerRounds.length === 0 && defending && (
                    <div className="text-xs text-gray-400 animate-pulse">候选人尚未应答…</div>
                  )}
                  {answerRounds.map(bubble)}
                </div>
                {/* 合议裁定：跨栏置底 */}
                {panelRounds.length > 0 && (
                  <div className="lg:col-span-2 space-y-3">
                    <div className="flex items-center justify-center gap-1.5 text-xs font-semibold text-violet-600 dark:text-violet-400">
                      <Gavel className="w-3 h-3" /> 合议裁定
                    </div>
                    <div className="max-w-2xl mx-auto">{panelRounds.map(bubble)}</div>
                  </div>
                )}
                <div ref={defenseScrollRef} className="lg:col-span-2" />
              </div>
            );
          })()}

          {/* 合议分数 + verdict（前端解析展示，4 轴分数服务端已落库） */}
          {defenseScores && !defending && (
            <div className="mt-4 flex items-center gap-2 flex-wrap bg-emerald-50 dark:bg-emerald-900/15 border border-emerald-200 dark:border-emerald-800/60 rounded-lg p-3">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              <span className="text-xs text-emerald-700 dark:text-emerald-300">
                合议
                {!!defenseScores.verdict && (
                  <span className="inline-flex items-center gap-1 ml-1 px-2 py-px rounded-md bg-emerald-600 text-white text-[11px] font-semibold">
                    结论：{String(defenseScores.verdict)}
                  </span>
                )}
                {defenseScores.novelty != null && <> · 新颖性 <strong>{String(defenseScores.novelty)}/10</strong></>}
                {!!defenseScores.crowding && <> · 拥挤度 <strong>{String(defenseScores.crowding)}</strong></>}
                {defenseScores.feasibility != null && <> · 可行性 <strong>{String(defenseScores.feasibility)}/10</strong></>}
                {!!defenseScores.gate && <> · 门控 <strong>{String(defenseScores.gate)}</strong></>}
              </span>
              <button onClick={() => goStep(3)} className="text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline">
                去第 3 步召回文献 →
              </button>
            </div>
          )}
        </div>
      )}

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
          {(proposalBusy || project.proposal) && (
            <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
              <h4 className="text-xs font-medium text-gray-500 mb-2 flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5" /> 立项书（自动生成）
                <button
                  onClick={() => goStep(5)}
                  className="ml-1 inline-flex items-center gap-0.5 text-primary-600 dark:text-primary-400 hover:underline"
                >
                  去第 5 步查看/下载 →
                </button>
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

      {/* 验证完成后的跨步引导卡（评分由后端结构化落库；正则结果仅用于展示） */}
      {!validating && reportContent && (
        <div className="flex items-center gap-2 flex-wrap bg-green-50 dark:bg-green-900/10 border border-green-200 dark:border-green-800/60 rounded-lg p-3">
          <CheckCircle2 className="w-4 h-4 text-green-600 shrink-0" />
          <span className="text-xs text-green-700 dark:text-green-300">
            验证完成
            {parsed.novelty != null && <> · 新颖性 <strong>{parsed.novelty}/10</strong></>}
            {parsed.crowding && <> · 拥挤度：<strong>{parsed.crowding}</strong></>}
          </span>
          <button onClick={() => goStep(3)} className="text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline">
            去第 3 步召回文献 →
          </button>
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
