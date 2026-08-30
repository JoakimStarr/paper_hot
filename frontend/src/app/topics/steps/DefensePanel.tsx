'use client';

import React, { useState, useRef, useEffect } from 'react';
import { Loader2, ChevronDown, Gavel, MessageSquareText, CheckCircle2, User } from 'lucide-react';
import { streamDefenseTopic, streamDefenseContinue, papersApi, getLastModel, rememberModel } from '@/lib/api';
import { downloadTextFile } from '@/lib/utils';
import type { DebateTranscript } from '@/types/paper';
import DebateModelSelect from './DebateModelSelect';
import StreamBubble from './StreamBubble';

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

// 答辩角色头像（聊天窗口式）
function defenseAvatar(role: DefenseRole): React.ReactNode {
  if (role === 'candidate') {
    return <div className="w-8 h-8 rounded-full bg-emerald-100 dark:bg-emerald-900/40 flex items-center justify-center"><User className="w-4 h-4 text-emerald-600 dark:text-emerald-400" /></div>;
  }
  if (role === 'examiner') {
    return <div className="w-8 h-8 rounded-full bg-amber-100 dark:bg-amber-900/40 flex items-center justify-center"><Gavel className="w-4 h-4 text-amber-600 dark:text-amber-400" /></div>;
  }
  return <div className="w-8 h-8 rounded-full bg-violet-100 dark:bg-violet-900/40 flex items-center justify-center"><Gavel className="w-4 h-4 text-violet-600 dark:text-violet-400" /></div>;
}

const DEFENSE_ROLE_LABELS: Record<DefenseRole, string> = { candidate: '候选人', examiner: '评委', panel: '合议' };

// 继续追问角色 -> 轮次标签/角色
const DEFENSE_FOLLOWUP_META: Record<string, { label: string; role: DefenseRole }> = {
  candidate: { label: '候选人再回应', role: 'candidate' },
  examiner: { label: '评委再质询', role: 'examiner' },
  panel: { label: '合议补充', role: 'panel' },
  assistant: { label: '继续追问', role: 'panel' },
};

/** 模拟答辩（选题向导 Step5：模拟开题答辩）。自包含，仅依赖选题标题与 projectId。 */
export default function DefensePanel({ topic, projectId, goStep, initialTranscript }: {
  topic: string;
  projectId?: number;
  goStep?: (n: number) => void;
  initialTranscript?: DebateTranscript | null;
}) {
  const [defending, setDefending] = useState(false);
  const [defenseError, setDefenseError] = useState<string | null>(null);
  const [defenseRounds, setDefenseRounds] = useState<DefenseRound[]>([]);
  const [defenseScores, setDefenseScores] = useState<Record<string, unknown> | null>(null);
  const [retrievedPapers, setRetrievedPapers] = useState<Array<{ id: string; n?: number; title?: string }>>([]);
  const defenseAbortRef = useRef<AbortController | null>(null);
  const defenseFullTextRef = useRef('');
  const defenseReasoningRef = useRef('');
  const defenseScrollRef = useRef<HTMLDivElement | null>(null);
  // 继续追问输入
  const [defenseFollowup, setDefenseFollowup] = useState('');

  const [defenseRoundsPerSide, setDefenseRoundsPerSide] = useState(2);
  const [defenseModels, setDefenseModels] = useState<Record<'candidate' | 'examiner' | 'panel', string>>({ candidate: '', examiner: '', panel: '' });
  const [defenseUnified, setDefenseUnified] = useState(false);
  const [defenseUnifiedModel, setDefenseUnifiedModel] = useState('');
  const [debateAiModels, setDebateAiModels] = useState<Array<{ id: string; label: string }>>([]);
  const [defenseSettingsOpen, setDefenseSettingsOpen] = useState(true);

  // 加载可用模型列表 + 恢复角色模型记忆
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
        const restored: Record<'candidate' | 'examiner' | 'panel', string> = { candidate: '', examiner: '', panel: '' };
        (['candidate', 'examiner', 'panel'] as const).forEach((role) => {
          const last = getLastModel(`defense_${role}`);
          if (last && list.some((m) => m.id === last)) restored[role] = last;
        });
        setDefenseModels(restored);
      } catch { /* 模型列表加载失败：仍可用默认模型 */ }
    })();
    return () => { cancelled = true; };
  }, []);

  // 自动滚动到最新一轮
  useEffect(() => {
    if (defending && defenseScrollRef.current) {
      defenseScrollRef.current.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  }, [defenseRounds, defending]);

  // 进入时恢复上次答辩记录（全文 + 合议 + 轮数；随项目 debate_transcript 一起持久化）
  useEffect(() => {
    const t = initialTranscript;
    if (!t || t.surface !== 'defense' || !t.rounds?.length) return;
    setDefenseRounds(t.rounds.map((r) => ({
      id: r.id,
      label: r.label,
      role: defenseRoundMeta(r.id).role,
      text: r.text,
      reasoning: '',
      model: r.model,
    })));
    setDefenseScores(t.scores || null);
    if (t.rounds_per_side) setDefenseRoundsPerSide(t.rounds_per_side);
    // 仅在选题变化（重新挂载）时恢复一次；重新答辩由 handleDefense 覆盖
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topic]);

  const citations = React.useMemo(() => {
    const map: Record<number, { id: string; title?: string }> = {};
    for (const p of retrievedPapers) {
      if (p.n !== undefined) map[p.n] = { id: String(p.id), title: p.title };
    }
    return map;
  }, [retrievedPapers]);

  const handleDefenseAbort = () => {
    defenseAbortRef.current?.abort();
    setDefending(false);
  };

  const handleDefense = async () => {
    const t = (topic || '').trim();
    if (!t || defending) return;
    setDefending(true);
    setDefenseError(null);
    setDefenseRounds([]);
    setDefenseScores(null);
    setRetrievedPapers([]);
    defenseFullTextRef.current = '';
    defenseReasoningRef.current = '';
    const controller = new AbortController();
    defenseAbortRef.current = controller;
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
      t,
      projectId,
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
            if (Array.isArray(p)) setRetrievedPapers(p);
          }
        },
        onDone: () => setDefending(false),
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

  // 继续追问：基于已完成环节追加一轮（指定角色或自由追问）
  const handleDefenseContinue = async (role: string, prompt: string) => {
    const t = (topic || '').trim();
    const q = (prompt || '').trim();
    if (!t || !q || defending) return;
    setDefending(true);
    setDefenseError(null);
    defenseFullTextRef.current = '';
    defenseReasoningRef.current = '';
    const controller = new AbortController();
    defenseAbortRef.current = controller;
    const history = defenseRounds.map((r) => ({ id: r.id, label: r.label, model: r.model, text: r.text }));
    const meta = DEFENSE_FOLLOWUP_META[role] || { label: '继续追问', role: 'panel' as DefenseRole };
    await streamDefenseContinue(t, projectId, history, role, q, {
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
        if (data && typeof data === 'object' && 'round' in data) {
          const d = data as Record<string, unknown>;
          const model = typeof d.model === 'string' ? d.model : undefined;
          setDefenseRounds((prev) => [...prev, { id: `followup_${Date.now()}`, label: meta.label, role: meta.role, text: '', reasoning: '', model }]);
        }
      },
      onDone: () => setDefending(false),
      onError: (msg) => {
        setDefenseError(msg);
        setDefending(false);
      },
    }, controller.signal);
    setDefenseFollowup('');
  };

  // 导出答辩记录 markdown
  const exportDefense = () => {
    if (defenseRounds.length === 0) return;
    const parts = defenseRounds.map((r) => `### ${r.label}${r.model ? `（${r.model}）` : ''}\n\n${r.text}`);
    downloadTextFile(`${topic}_答辩记录.md`, `# 模拟答辩：${topic}\n\n${parts.join('\n\n---\n\n')}\n`, 'text/markdown;charset=utf-8');
  };

  const opening = defenseRounds.find((r) => r.id === 'candidate_0');
  const isLatest = (r: DefenseRound) => defenseRounds[defenseRounds.length - 1]?.id === r.id;

  const colorCls = (role: DefenseRole) =>
    role === 'candidate'
      ? 'bg-emerald-50 dark:bg-emerald-900/15 border-emerald-200 dark:border-emerald-800'
      : role === 'examiner'
        ? 'bg-amber-50 dark:bg-amber-900/15 border-amber-200 dark:border-amber-800'
        : 'bg-violet-50 dark:bg-violet-900/15 border-violet-200 dark:border-violet-800';

  // StreamBubble：流式中纯文本逐 token 渲染，结束后切 Markdown；增量只重渲染当前轮
  const bubble = (r: DefenseRound) => (
    <StreamBubble
      key={r.id}
      r={r}
      colorCls={colorCls(r.role)}
      streaming={defending && isLatest(r)}
      citations={citations}
      avatar={defenseAvatar(r.role)}
      avatarSide={r.role === 'examiner' ? 'right' : 'left'}
      sideLabel={DEFENSE_ROLE_LABELS[r.role]}
    />
  );

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg border border-emerald-200 dark:border-emerald-800 p-4 sm:p-6">
      <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
        <h3 className="flex items-center gap-1.5 text-sm font-semibold text-gray-900 dark:text-white">
          <MessageSquareText className="w-4 h-4 text-emerald-600" /> 模拟答辩
          <span className="text-[11px] font-normal text-gray-400">
            模拟开题答辩 · 自述 + {defenseRoundsPerSide} 轮质询 + 合议
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
            {!defending && (
              <button
                onClick={handleDefense}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs rounded-lg transition-colors ml-auto"
              >
                <MessageSquareText className="w-3.5 h-3.5" /> 开始答辩（{defenseRoundsPerSide} 轮质询）
              </button>
            )}
          </div>
        )}
      </div>

      {defenseError && <div className="text-sm text-red-500 py-2">{defenseError}</div>}

      {/* 对话流：候选人应答左 / 评委质询右 / 自述与合议居中（聊天窗口式） */}
      <div className="space-y-3 max-h-[520px] overflow-y-auto pr-1">
        {opening && (
          <div className="flex justify-center">
            <div className="w-full max-w-2xl">{bubble(opening)}</div>
          </div>
        )}
        {!opening && defending && (
          <div className="text-xs text-gray-400 animate-pulse">候选人正在自述研究设计…</div>
        )}
        {defenseRounds
          .filter((r) => r.id !== 'candidate_0')
          .map((r) => (
            <div key={r.id} className={`flex ${r.role === 'examiner' ? 'justify-end' : r.role === 'candidate' ? 'justify-start' : 'justify-center'}`}>
              <div className={r.role === 'panel' ? 'w-full max-w-2xl' : 'max-w-[85%]'}>{bubble(r)}</div>
            </div>
          ))}
        <div ref={defenseScrollRef} />
      </div>

      {/* 继续追问 + 导出记录 */}
      {defenseRounds.length > 0 && !defending && (
        <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-1.5 flex-wrap mb-2">
            <span className="text-xs text-gray-400">继续追问</span>
            <button
              onClick={() => handleDefenseContinue('examiner', '请评委再质询一点：针对候选人尚未充分回答的环节继续追问。')}
              className="text-[11px] px-2 py-1 rounded-md border border-amber-200 dark:border-amber-800 text-amber-600 dark:text-amber-300 hover:bg-amber-50 dark:hover:bg-amber-900/20 transition-colors"
            >
              评委再质询
            </button>
            <button
              onClick={() => handleDefenseContinue('candidate', '请候选人针对最新质询再作补充应答。')}
              className="text-[11px] px-2 py-1 rounded-md border border-emerald-200 dark:border-emerald-800 text-emerald-600 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-900/20 transition-colors"
            >
              候选人再回应
            </button>
            <button
              onClick={() => handleDefenseContinue('panel', '请合议组补充裁定意见与修改建议。')}
              className="text-[11px] px-2 py-1 rounded-md border border-violet-200 dark:border-violet-800 text-violet-600 dark:text-violet-300 hover:bg-violet-50 dark:hover:bg-violet-900/20 transition-colors"
            >
              合议补充
            </button>
            <button
              onClick={exportDefense}
              className="text-[11px] px-2 py-1 rounded-md border border-gray-300 dark:border-gray-600 text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors ml-auto"
            >
              导出记录
            </button>
          </div>
          <div className="flex gap-2">
            <input
              value={defenseFollowup}
              onChange={(e) => setDefenseFollowup(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleDefenseContinue('assistant', defenseFollowup); }}
              placeholder="自由追问（如：请针对数据可得性展开论证）…"
              className="flex-1 px-2.5 py-1.5 text-xs border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 outline-none focus:ring-1 focus:ring-primary-400"
            />
            <button
              onClick={() => handleDefenseContinue('assistant', defenseFollowup)}
              disabled={!defenseFollowup.trim()}
              className="inline-flex items-center gap-1 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 text-white text-xs rounded-lg transition-colors"
            >
              <MessageSquareText className="w-3.5 h-3.5" /> 追问
            </button>
          </div>
        </div>
      )}

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
          {goStep && (
            <>
              <button onClick={() => goStep(1)} className="text-xs font-medium text-emerald-600 dark:text-emerald-400 hover:underline">
                带着结论去改题 →
              </button>
              <button onClick={() => goStep(3)} className="text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline">
                去第 3 步召回文献 →
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
