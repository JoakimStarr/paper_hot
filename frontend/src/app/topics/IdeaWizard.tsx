'use client';

import React, { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Sparkles, Loader2, Plus, ChevronLeft, ChevronRight, Wand2, Check, RotateCcw, X, Star } from 'lucide-react';
import { topicsApi, topicIdeasApi } from '@/lib/api';
import { useToast } from '@/components/Toast';
import { useIdeaDraft } from '@/lib/useIdeaDraft';
import type { TopicIdeaPreferences, TopicIdeaCandidate } from '@/types/paper';

type Step = 'idea' | 'prefs' | 'candidates';

const IDEA_FAVORITES_KEY = 'paperpulse-idea-favorites';

const IDENTITY_OPTIONS: Array<{ value: TopicIdeaPreferences['identity']; label: string }> = [
  { value: 'bachelor', label: '本科生开题' },
  { value: 'master', label: '硕士论文' },
  { value: 'phd', label: '博士论文' },
  { value: 'faculty', label: '科研投稿' },
];
const PAPER_TYPE_OPTIONS: Array<{ value: TopicIdeaPreferences['paper_type']; label: string }> = [
  { value: 'empirical', label: '实证研究' },
  { value: 'review', label: '文献综述' },
  { value: 'case', label: '案例研究' },
  { value: 'theory', label: '理论研究' },
];
const VENUE_OPTIONS: Array<{ value: TopicIdeaPreferences['venue']; label: string }> = [
  { value: 'cn_top', label: '中文顶刊' },
  { value: 'cn_regular', label: '中文普通期刊' },
  { value: 'en_top', label: '英文顶刊' },
  { value: 'any', label: '不限' },
];
const SUBFIELD_OPTIONS = [
  '宏观经济学', '微观经济学', '计量经济学', '金融经济学', '产业经济学',
  '发展经济学', '国际经济学', '劳动经济学', '公共经济学', '行为经济学',
];
const METHOD_OPTIONS = [
  '因果识别/DID', 'PSM-DID', '工具变量', '断点回归', '面板回归',
  '案例研究', '文本分析', '机器学习', '结构方程',
];
const DATA_OPTIONS = [
  '上市公司数据', '省级面板数据', 'CFPS', 'CHFS', 'CGSS',
  '工业企业数据库', '海关数据', '文本/公告数据', '宏观数据',
];

const ASSESS_LABELS: Array<{ key: 'novelty' | 'feasibility' | 'literature_support'; label: string; color: string }> = [
  { key: 'novelty', label: '新颖度', color: 'bg-purple-500' },
  { key: 'feasibility', label: '可行性', color: 'bg-green-500' },
  { key: 'literature_support', label: '文献支撑', color: 'bg-blue-500' },
];

function ChipGroup<T extends string>({
  title, options, values, onToggle,
}: {
  title: string;
  options: string[];
  values: T[];
  onToggle: (v: string) => void;
}) {
  return (
    <div>
      <div className="text-xs font-medium text-gray-600 dark:text-gray-300 mb-1.5">{title}</div>
      <div className="flex flex-wrap gap-1.5">
        {options.map((o) => {
          const active = values.includes(o as T);
          return (
            <button
              key={o}
              type="button"
              onClick={() => onToggle(o)}
              className={`px-2.5 py-1 text-xs rounded-full border transition-colors ${
                active
                  ? 'bg-primary-600 text-white border-primary-600'
                  : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-600 hover:border-primary-300'
              }`}
            >
              {o}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default function IdeaWizard() {
  const { toast } = useToast();
  const router = useRouter();
  const { draft, hydrated, update, clear } = useIdeaDraft();

  const [step, setStep] = useState<Step>('idea');
  const [idea, setIdea] = useState('');
  const [prefs, setPrefs] = useState<TopicIdeaPreferences>({});
  const [rounds, setRounds] = useState<TopicIdeaCandidate[][]>([]);
  const [currentRound, setCurrentRound] = useState(0);
  const [feedback, setFeedback] = useState('');
  const [generating, setGenerating] = useState(false);
  const [genPhase, setGenPhase] = useState<string>('');
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editDraft, setEditDraft] = useState<{ title: string; questions: string }>({ title: '', questions: '' });
  const [favorites, setFavorites] = useState<Set<string>>(() => {
    if (typeof window === 'undefined') return new Set();
    try {
      return new Set(JSON.parse(window.localStorage.getItem(IDEA_FAVORITES_KEY) || '[]') as string[]);
    } catch {
      return new Set();
    }
  });
  const [onlyFavorites, setOnlyFavorites] = useState(false);

  // 恢复草稿
  React.useEffect(() => {
    if (!hydrated) return;
    if (draft) {
      setIdea(draft.idea);
      setPrefs(draft.preferences);
      setRounds(draft.rounds);
      setCurrentRound(Math.max(draft.rounds.length - 1, 0));
      setStep(draft.rounds.length ? 'candidates' : 'idea');
    }
  }, [hydrated]); // eslint-disable-line react-hooks/exhaustive-deps

  const candidates = rounds[currentRound] || [];
  const visibleCandidates = onlyFavorites ? candidates.filter((c) => favorites.has(c.id)) : candidates;

  const togglePref = <T extends string>(key: 'subfields' | 'methods' | 'data', value: string) => {
    setPrefs((prev) => {
      const cur = (prev[key] || []) as string[];
      const next = cur.includes(value) ? cur.filter((x) => x !== value) : [...cur, value];
      return { ...prev, [key]: next };
    });
  };

  const savePrefsStep = () => {
    update({ idea, preferences: prefs });
    setStep('candidates');
    void runGenerate();
  };

  const runGenerate = async (iterFeedback?: string, previous?: TopicIdeaCandidate[]) => {
    const trimmed = (iterFeedback ?? feedback).trim();
    setGenerating(true);
    setError(null);
    try {
      const res = await topicIdeasApi.generate({
        idea,
        preferences: prefs,
        feedback: trimmed || null,
        previous_candidates: (previous || rounds[currentRound] || []).map((c) => ({
          title: c.title,
          research_questions: c.research_questions,
        })),
      });
      // 后台生成（LLM 耗时 1 分钟+），轮询结果
      let result: { status: string; round?: number; candidates?: TopicIdeaCandidate[]; error?: string } | null = null;
      for (let i = 0; i < 80; i++) {
        await new Promise((r) => setTimeout(r, 3000));
        const poll = await topicIdeasApi.getGenerateResult(res.task_id);
        const phase = (poll as { phase?: string }).phase;
        setGenPhase(phase || '');
        if (poll.status === 'done') { result = poll; break; }
        if (poll.status === 'error') { throw new Error(poll.error || 'AI 生成失败，请重试'); }
      }
      if (!result?.candidates) throw new Error('生成超时，请重试');
      const next = [...rounds, result.candidates];
      setRounds(next);
      setCurrentRound(next.length - 1);
      setFeedback('');
      setEditingId(null);
      update({ idea, preferences: prefs, rounds: next });
    } catch (e: any) {
      setError(e instanceof Error ? (e as any).message : 'AI 生成失败，请重试');
    } finally {
      setGenerating(false);
      setGenPhase('');
    }
  };

  // 采纳候选 → 创建研究项目（进入验证步），候选快照（含 keywords）存入 generated_topics 供后续爬虫/检索使用
  const adopt = async (c: TopicIdeaCandidate) => {
    if (creating) return;
    setCreating(true);
    try {
      const p = await topicsApi.createTopicProject({
        title: c.title,
        source_type: 'idea',
        source_ref: idea,
        research_questions: c.research_questions,
        current_step: 1, // 落「选题定义」：确认/微调标题与问题后再进验证
      });
      const snapshot = rounds.flat().map((x) => ({
        title: x.title,
        research_questions: x.research_questions,
        hypothesis: x.hypothesis,
        why: x.why,
        keywords: x.keywords,
        methods: x.methods,
        data: x.data,
      }));
      await topicsApi.updateTopicProject(p.id, { generated_topics: snapshot }).catch(() => {});
      clear();
      toast('研究项目已创建', 'success');
      router.push(`/topics?project=${p.id}&step=1`);
    } catch (e: any) {
      toast(`创建失败：${e?.message || '未知错误'}`, 'error');
      setCreating(false);
    }
  };

  const startEdit = (c: TopicIdeaCandidate) => {
    setEditingId(c.id);
    setEditDraft({ title: c.title, questions: c.research_questions.join('\n') });
  };

  // 编辑候选 → 以此调整（带修改内容进入新一轮迭代）
  const refineFromEdit = (c: TopicIdeaCandidate) => {
    const questions = editDraft.questions.split('\n').map((q) => q.trim()).filter(Boolean);
    const instruction = `将候选「${c.title}」调整为「${editDraft.title.trim()}」（研究问题：${questions.join('；') || '无'}），围绕调整后的方向重新生成选题`;
    void runGenerate(instruction, rounds[currentRound]);
  };

  const goBackRound = () => {
    if (currentRound > 0) {
      setCurrentRound(currentRound - 1);
      setEditingId(null);
      setFeedback('');
    }
  };

  const toggleFavorite = (id: string) => {
    setFavorites((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      try {
        window.localStorage.setItem(IDEA_FAVORITES_KEY, JSON.stringify(Array.from(next)));
      } catch {
        /* localStorage 不可用时仅保留内存态 */
      }
      return next;
    });
  };

  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl border border-purple-200 dark:border-purple-800 p-4 sm:p-6">
      {/* 头部 */}
      <div className="flex items-center gap-2 mb-1">
        <Wand2 className="w-4 h-4 text-purple-600" />
        <h3 className="text-base font-semibold text-gray-900 dark:text-white">AI 选题向导</h3>
        <span className="text-xs text-gray-400">一句话想法 → 偏好 → AI 选题方向 + 参考文献 → 立项</span>
      </div>
      {/* 步骤指示 */}
      <div className="flex items-center gap-1.5 mb-4 text-xs">
        {(['idea', 'prefs', 'candidates'] as Step[]).map((s, i) => {
          const labels: Record<Step, string> = { idea: '想法', prefs: '偏好', candidates: '选题' };
          const active = step === s;
          const done = step === 'candidates' && s !== 'candidates' || (s === 'idea' && step !== 'idea');
          return (
            <React.Fragment key={s}>
              {i > 0 && <span className="text-gray-300 dark:text-gray-600">→</span>}
              <button
                type="button"
                onClick={() => { if (step === 'candidates' && s !== 'candidates') setStep(s); }}
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full transition-colors ${
                  active ? 'bg-purple-600 text-white' : done ? 'text-purple-600 dark:text-purple-400' : 'text-gray-400'
                } ${step === 'candidates' && s !== 'candidates' ? 'cursor-pointer hover:underline' : 'cursor-default'}`}
              >
                {done ? <Check className="w-3 h-3" /> : <span className="w-1.5 h-1.5 rounded-full bg-current" />}
                {i + 1} {labels[s]}
              </button>
            </React.Fragment>
          );
        })}
        {rounds.length > 0 && (
          <span className="ml-auto text-[11px] text-gray-400">
            第 {currentRound + 1}/{rounds.length} 轮
          </span>
        )}
      </div>

      {/* Step 1：一句话想法 */}
      {step === 'idea' && (
        <div className="space-y-3">
          <textarea
            value={idea}
            onChange={(e) => { setIdea(e.target.value); update({ idea: e.target.value }); }}
            rows={3}
            placeholder="例：我想研究数字普惠金融如何影响实体企业创新"
            className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 outline-none focus:ring-2 focus:ring-purple-500 resize-none"
          />
          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => setStep('prefs')}
              disabled={!idea.trim()}
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white text-sm rounded-lg transition-colors"
            >
              下一步：设置偏好 <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}

      {/* Step 2：偏好 */}
      {step === 'prefs' && (
        <div className="space-y-4">
          <ChipGroup
            title="身份（影响选题难度与期刊定位）"
            options={IDENTITY_OPTIONS.map((o) => o.label)}
            values={(prefs.identity ? [IDENTITY_OPTIONS.find((o) => o.value === prefs.identity)?.label || ''] : []) as string[]}
            onToggle={(label) => {
              const opt = IDENTITY_OPTIONS.find((o) => o.label === label);
              setPrefs((prev) => ({ ...prev, identity: opt?.value }));
            }}
          />
          <ChipGroup
            title="论文类型"
            options={PAPER_TYPE_OPTIONS.map((o) => o.label)}
            values={(prefs.paper_type ? [PAPER_TYPE_OPTIONS.find((o) => o.value === prefs.paper_type)?.label || ''] : []) as string[]}
            onToggle={(label) => {
              const opt = PAPER_TYPE_OPTIONS.find((o) => o.label === label);
              setPrefs((prev) => ({ ...prev, paper_type: opt?.value }));
            }}
          />
          <ChipGroup title="倾向子领域" options={SUBFIELD_OPTIONS} values={prefs.subfields || []} onToggle={(v) => togglePref('subfields', v)} />
          <ChipGroup title="方法偏好" options={METHOD_OPTIONS} values={prefs.methods || []} onToggle={(v) => togglePref('methods', v)} />
          <ChipGroup title="数据偏好" options={DATA_OPTIONS} values={prefs.data || []} onToggle={(v) => togglePref('data', v)} />
          <ChipGroup
            title="期刊定位"
            options={VENUE_OPTIONS.map((o) => o.label)}
            values={(prefs.venue ? [VENUE_OPTIONS.find((o) => o.value === prefs.venue)?.label || ''] : []) as string[]}
            onToggle={(label) => {
              const opt = VENUE_OPTIONS.find((o) => o.label === label);
              setPrefs((prev) => ({ ...prev, venue: opt?.value }));
            }}
          />
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-medium text-gray-600 dark:text-gray-300">新颖度 ↔ 可行性</span>
              <span className="text-[11px] text-gray-400">
                {(prefs.prefer_novelty ?? 0.5) >= 0.7 ? '偏新颖' : (prefs.prefer_novelty ?? 0.5) <= 0.3 ? '偏可行' : '均衡'}
              </span>
            </div>
            <input
              type="range"
              min={0}
              max={100}
              value={Math.round((prefs.prefer_novelty ?? 0.5) * 100)}
              onChange={(e) => setPrefs((prev) => ({ ...prev, prefer_novelty: Number(e.target.value) / 100 }))}
              className="w-full accent-purple-600"
            />
          </div>
          <label className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-300 cursor-pointer">
            <input
              type="checkbox"
              checked={prefs.focus_china ?? true}
              onChange={(e) => setPrefs((prev) => ({ ...prev, focus_china: e.target.checked }))}
              className="accent-purple-600"
            />
            聚焦中国情境
          </label>
          <input
            value={prefs.extra || ''}
            onChange={(e) => setPrefs((prev) => ({ ...prev, extra: e.target.value }))}
            placeholder="其他要求（可选）：如必须用某个数据/方法、要突出政策评估…"
            className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 outline-none focus:ring-2 focus:ring-purple-500"
          />
          <div className="flex justify-between">
            <button
              type="button"
              onClick={() => setStep('idea')}
              className="inline-flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
            >
              <ChevronLeft className="w-4 h-4" /> 上一步
            </button>
            <button
              type="button"
              onClick={savePrefsStep}
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white text-sm rounded-lg transition-colors"
            >
              {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              生成选题
            </button>
          </div>
        </div>
      )}

      {/* Step 3：候选选题 */}
      {step === 'candidates' && (
        <div className="space-y-4">
          {/* 顶部工具条 */}
          <div className="flex items-center gap-2 flex-wrap">
            {currentRound > 0 && (
              <button
                type="button"
                onClick={goBackRound}
                className="inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-md border border-gray-300 dark:border-gray-600 text-gray-500 dark:text-gray-400 hover:text-purple-600 hover:border-purple-400 transition-colors"
              >
                <RotateCcw className="w-3 h-3" /> 上一轮
              </button>
            )}
            <button
              type="button"
              onClick={() => { setStep('idea'); setEditingId(null); }}
              className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors"
            >
              修改想法/偏好
            </button>
            {error && (
              <span className="text-xs text-red-500 flex items-center gap-1">
                {error}
                <button type="button" onClick={() => runGenerate()} className="underline hover:no-underline">重试</button>
              </span>
            )}
          </div>

          {generating && (
            <div className="flex items-center justify-center gap-2 text-sm text-purple-600 dark:text-purple-400 py-8">
              <Loader2 className="w-5 h-5 animate-spin" />
              {genPhase === 'recalling'
                ? '选题方向已生成，正在召回库内参考文献…'
                : 'AI 正在构思选题方向（约 1 分钟）…'}
            </div>
          )}

          {!generating && candidates.length === 0 && (
            <div className="text-center py-8">
              <p className="text-sm text-gray-400 mb-2">还没有候选选题</p>
              <button
                type="button"
                onClick={() => runGenerate()}
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white text-sm rounded-lg transition-colors"
              >
                <Sparkles className="w-4 h-4" /> 开始生成
              </button>
            </div>
          )}

          {!generating && candidates.length > 0 && (
            <div className="space-y-4">
              <div className="flex items-center justify-end">
                <button
                  type="button"
                  onClick={() => setOnlyFavorites((v) => !v)}
                  className={`inline-flex items-center gap-1 text-xs px-2.5 py-1 rounded-md border transition-colors ${
                    onlyFavorites
                      ? 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-300 dark:border-yellow-700 text-yellow-600 dark:text-yellow-400'
                      : 'border-gray-200 dark:border-gray-600 text-gray-500 dark:text-gray-400 hover:text-yellow-600 hover:border-yellow-400'
                  }`}
                >
                  <Star className={`w-3 h-3 ${onlyFavorites ? 'fill-yellow-400 text-yellow-400' : ''}`} />
                  只看收藏
                </button>
              </div>
              {visibleCandidates.length === 0 && (
                <div className="text-center text-xs text-gray-400 py-6">还没有收藏的选题，点击卡片右上角 ☆ 即可收藏</div>
              )}
              {visibleCandidates.map((c) => (
                <div key={c.id} className="border border-purple-200 dark:border-purple-800 rounded-lg p-3 sm:p-4">
                  {/* 标题 + 评估 */}
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      {editingId === c.id ? (
                        <input
                          value={editDraft.title}
                          onChange={(e) => setEditDraft((prev) => ({ ...prev, title: e.target.value }))}
                          className="w-full px-2.5 py-1.5 text-sm border border-purple-300 dark:border-purple-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 outline-none focus:ring-1 focus:ring-purple-400"
                        />
                      ) : (
                        <div className="text-sm font-medium text-gray-900 dark:text-white leading-snug">{c.title}</div>
                      )}
                      <div className="flex flex-wrap gap-1.5 mt-1.5">
                        {c.subfield && (
                          <span className="text-[11px] px-1.5 py-0.5 rounded bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300">{c.subfield}</span>
                        )}
                        {c.keywords.slice(0, 4).map((kw) => (
                          <span key={kw} className="text-[11px] px-1.5 py-0.5 rounded bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400">{kw}</span>
                        ))}
                      </div>
                    </div>
                    {/* 收藏 + AI 评估 */}
                    <div className="shrink-0 flex flex-col items-end gap-1.5">
                      <button
                        type="button"
                        onClick={() => toggleFavorite(c.id)}
                        aria-label={favorites.has(c.id) ? '取消收藏' : '收藏'}
                        title={favorites.has(c.id) ? '取消收藏' : '收藏'}
                        className="p-1 rounded-md transition-colors hover:bg-gray-100 dark:hover:bg-gray-700"
                      >
                        <Star className={`w-4 h-4 ${favorites.has(c.id) ? 'fill-yellow-400 text-yellow-400' : 'text-gray-300 dark:text-gray-500'}`} />
                      </button>
                      <div className="w-28 space-y-1">
                        {ASSESS_LABELS.map((a) => {
                          const v = c.assessment?.[a.key] ?? 0;
                          return (
                            <div key={a.key} className="flex items-center gap-1 text-[10px] text-gray-400">
                              <span className="w-9 shrink-0">{a.label}</span>
                              <div className="flex-1 h-1.5 bg-gray-100 dark:bg-gray-700 rounded-full overflow-hidden">
                                <div className={`h-full ${a.color}`} style={{ width: `${(v / 5) * 100}%` }} />
                              </div>
                              <span className="w-3 text-right">{v}</span>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  </div>

                  {c.assessment?.comment && (
                    <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-2">点评：{c.assessment.comment}</p>
                  )}

                  {/* 研究问题 / 假设 / 角度 */}
                  <div className="mt-2.5 space-y-1 text-xs text-gray-600 dark:text-gray-300">
                    {c.research_questions.length > 0 && (
                      <div>
                        <span className="text-gray-400 mr-1">研究问题：</span>
                        {c.research_questions.join('；')}
                      </div>
                    )}
                    {c.hypothesis && (
                      <div><span className="text-gray-400 mr-1">假设：</span>{c.hypothesis}</div>
                    )}
                    {c.why && (
                      <div><span className="text-gray-400 mr-1">为什么值得做：</span>{c.why}</div>
                    )}
                    {c.angle && (
                      <div><span className="text-gray-400 mr-1">切入角度：</span>{c.angle}</div>
                    )}
                    {(c.methods.length > 0 || c.data.length > 0) && (
                      <div>
                        {c.methods.length > 0 && <span className="text-gray-400 mr-1">方法：{c.methods.join('、')}</span>}
                        {c.data.length > 0 && <span className="text-gray-400 mr-1">数据：{c.data.join('、')}</span>}
                      </div>
                    )}
                  </div>

                  {/* 编辑态：研究问题 */}
                  {editingId === c.id && (
                    <div className="mt-2">
                      <textarea
                        value={editDraft.questions}
                        onChange={(e) => setEditDraft((prev) => ({ ...prev, questions: e.target.value }))}
                        rows={2}
                        placeholder="研究问题（每行一个）"
                        className="w-full px-2.5 py-1.5 text-xs border border-purple-300 dark:border-purple-600 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 outline-none focus:ring-1 focus:ring-purple-400 resize-none"
                      />
                    </div>
                  )}

                  {/* 参考文献 */}
                  {c.references.length > 0 && (
                    <div className="mt-2.5 pt-2 border-t border-gray-100 dark:border-gray-700">
                      <div className="text-[11px] text-gray-400 mb-1">参考文献（库内）</div>
                      <div className="space-y-0.5">
                        {c.references.map((r) => (
                          <a
                            key={r.id}
                            href={`/paper/${r.id}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="block text-xs text-primary-600 dark:text-primary-400 hover:underline truncate"
                          >
                            {r.title}
                            {r.journal ? `（${r.journal}${r.published_at ? `，${r.published_at}` : ''}）` : ''}
                          </a>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 操作 */}
                  <div className="flex items-center gap-2 mt-3">
                    {editingId === c.id ? (
                      <>
                        <button
                          type="button"
                          onClick={() => refineFromEdit(c)}
                          disabled={generating || !editDraft.title.trim()}
                          className="inline-flex items-center gap-1 text-xs px-3 py-1.5 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-md transition-colors"
                        >
                          {generating ? <Loader2 className="w-3 h-3 animate-spin" /> : <Wand2 className="w-3 h-3" />}
                          以此调整（重新生成）
                        </button>
                        <button
                          type="button"
                          onClick={() => setEditingId(null)}
                          className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-500 dark:text-gray-400 rounded-md hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
                        >
                          <X className="w-3 h-3" /> 取消
                        </button>
                      </>
                    ) : (
                      <>
                        <button
                          type="button"
                          onClick={() => startEdit(c)}
                          disabled={generating || creating}
                          className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-500 dark:text-gray-400 rounded-md hover:text-purple-600 hover:border-purple-400 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                        >
                          <Wand2 className="w-3 h-3" /> 编辑
                        </button>
                        <button
                          type="button"
                          onClick={() => adopt(c)}
                          disabled={creating}
                          className="inline-flex items-center gap-1 text-xs px-3 py-1.5 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-md transition-colors"
                        >
                          {creating ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
                          采纳并立项
                        </button>
                      </>
                    )}
                  </div>
                </div>
              ))}

              {/* 迭代：调整指令 */}
              <div className="border border-dashed border-purple-300 dark:border-purple-700 rounded-lg p-3">
                <div className="text-xs text-gray-500 dark:text-gray-400 mb-2">
                  不满意？输入调整指令后重新生成一轮（如「更聚焦制造业」「偏重政策评估」）
                </div>
                <div className="flex flex-col sm:flex-row gap-2">
                  <input
                    value={feedback}
                    onChange={(e) => setFeedback(e.target.value)}
                    onKeyDown={(e) => { if (e.key === 'Enter') runGenerate(); }}
                    placeholder="调整指令…"
                    className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 outline-none focus:ring-2 focus:ring-purple-500"
                  />
                  <button
                    type="button"
                    onClick={() => runGenerate()}
                    disabled={generating}
                    className="inline-flex items-center justify-center gap-1.5 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white text-sm rounded-lg transition-colors shrink-0"
                  >
                    {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <RotateCcw className="w-4 h-4" />}
                    重新生成
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
