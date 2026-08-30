'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import dynamic from 'next/dynamic';
import Layout from '@/components/Layout';
import { useToast } from '@/components/Toast';
import ConfirmModal from '@/app/system/ConfirmModal';
import { topicsApi, papersApi, personalApi, workbenchApi } from '@/lib/api';
import { downloadTextFile } from '@/lib/utils';
import { reportPageContext } from '@/lib/assistantBus';
import { useLanguage } from '@/contexts/LanguageContext';
import type { TopicProject, ResearchGap, TrendingTopic, GapAnalysisResponse } from '@/types/paper';
import IdeaWizard from './IdeaWizard';
import {
  Compass, Sparkles, Loader2, Plus, Lightbulb, Flame, BookmarkCheck,
  ChevronRight, Wand2, Trash2, ArrowRight, Brain, Download,
} from 'lucide-react';

const MarkdownRenderer = dynamic(() => import('@/components/MarkdownRenderer'), {
  ssr: false,
  loading: () => <div className="h-16 flex items-center justify-center text-gray-400 text-sm animate-pulse">加载中...</div>,
});

const STEP_NAMES = ['', '选题定义', '选题验证', '文献管理', '数据与方法', '写作输出'];
const SOURCE_LABELS: Record<string, string> = {
  gap: '空白',
  keyword: '热点',
  idea: '想法',
  ai: 'AI 推荐',
  manual: '手动',
};

const STATUS_LABELS: Record<string, string> = {
  to_validate: '验证中',
  validated: '已验证',
  subscribed: '已立项',
  abandoned: '已搁置',
};
const STATUS_STYLES: Record<string, string> = {
  to_validate: 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300',
  validated: 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300',
  subscribed: 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300',
  abandoned: 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400',
};

const STEP_FILTERS = [
  { value: '', label: '全部步骤' },
  { value: '1', label: '选题定义(1)' },
  { value: '2', label: '选题验证(2)' },
  { value: '3', label: '文献管理(3)' },
  { value: '4', label: '数据与方法(4)' },
  { value: '5', label: '写作输出(5)' },
];

const SOURCE_FILTERS = [
  { value: '', label: '全部来源' },
  { value: 'idea', label: '想法(idea)' },
  { value: 'keyword', label: '热点(keyword)' },
  { value: 'gap', label: '空白(gap)' },
  { value: 'ai', label: 'AI 推荐(ai)' },
  { value: 'manual', label: '手动(manual)' },
];

const STATUS_FILTERS = [
  { value: '', label: '全部状态' },
  { value: 'to_validate', label: '验证中' },
  { value: 'validated', label: '已验证' },
  { value: 'subscribed', label: '已立项' },
  { value: 'abandoned', label: '已搁置' },
];

export default function ProjectList() {
  const { t } = useLanguage();
  const { toast } = useToast();
  const router = useRouter();

  // ---- 项目列表 ----
  const [projects, setProjects] = useState<TopicProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [idea, setIdea] = useState('');

  // ---- 项目列表筛选（客户端） ----
  const [query, setQuery] = useState('');
  const [stepFilter, setStepFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  // 删除确认（ConfirmModal 替代原生 confirm）
  const [deleteTarget, setDeleteTarget] = useState<TopicProject | null>(null);
  const [exportingAll, setExportingAll] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const filteredProjects = useMemo(() => {
    const q = query.trim().toLowerCase();
    return projects.filter((p) => {
      if (q && !(p.title || '').toLowerCase().includes(q)) return false;
      if (stepFilter && String(p.current_step || 1) !== stepFilter) return false;
      if (sourceFilter && (p.source_type || 'manual') !== sourceFilter) return false;
      if (statusFilter && (p.status || 'to_validate') !== statusFilter) return false;
      return true;
    });
  }, [projects, query, stepFilter, sourceFilter, statusFilter]);

  // ---- 灵感区 ----
  const [gaps, setGaps] = useState<ResearchGap[]>([]);
  const [gapAnalysis, setGapAnalysis] = useState<GapAnalysisResponse | null>(null);
  const [gapAnalyzing, setGapAnalyzing] = useState(false);
  const [hotTopics, setHotTopics] = useState<TrendingTopic[]>([]);
  const [followedSubfields, setFollowedSubfields] = useState<string[]>([]);
  const [followedKeywords, setFollowedKeywords] = useState<string[]>([]);
  const [inspirationOpen, setInspirationOpen] = useState(true);
  const [wizardOpen, setWizardOpen] = useState(false);
  // AI 个性化灵感推荐
  const [recommendations, setRecommendations] = useState<Array<{ title: string; why: string; angle?: string }>>([]);
  const [recommending, setRecommending] = useState(false);

  const loadProjects = useCallback(async () => {
    try {
      setProjects(await topicsApi.listTopicProjects());
    } catch {
      setProjects([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProjects();
    reportPageContext({ tab: 'list' });
    // 灵感数据（静默加载，失败不阻塞）
    topicsApi.getResearchGaps(10).then((r) => setGaps(r.gaps || [])).catch(() => {});
    topicsApi.getGapAnalysis().then((r) => setGapAnalysis(r)).catch(() => {});
    papersApi.getTrendingTopics().then((r) => setHotTopics(r.topics || [])).catch(() => {});
    personalApi.getSubfields().then((r) => setFollowedSubfields(r.subfields || [])).catch(() => {});
    personalApi.getKeywords().then((r) => setFollowedKeywords(r.keywords || [])).catch(() => {});
  }, [loadProjects]);

  /** AI 个性化灵感推荐（基于关注/阅读/空白，结果后端缓存 10 分钟）。 */
  const loadRecommendations = async () => {
    if (recommending) return;
    setRecommending(true);
    try {
      const res = await workbenchApi.recommendTopics();
      setRecommendations(res.recommendations || []);
    } catch (e: any) {
      toast(`推荐失败：${e?.message || '未知错误'}`, 'error');
    } finally {
      setRecommending(false);
    }
  };

  const startGapAnalysis = async () => {
    if (gapAnalyzing) return;
    setGapAnalyzing(true);
    try {
      await topicsApi.startGapAnalysis(undefined, 10);
      setGapAnalysis((prev) => (prev ? { ...prev, status: 'running' } : prev));
      // 轮询
      let attempts = 0;
      const poll = async () => {
        attempts += 1;
        try {
          const r = await topicsApi.getGapAnalysis();
          setGapAnalysis(r);
          if (!r.is_running || attempts > 40) return;
        } catch { /* ignore */ }
        setTimeout(poll, 4000);
      };
      setTimeout(poll, 3000);
    } catch (e: any) {
      toast(`分析启动失败：${e?.message || '未知错误'}`, 'error');
      setGapAnalyzing(false);
    }
  };

  /** 从灵感创建研究项目（自动召回初始文献集，跳转详情）。 */
  const createProject = async (title: string, sourceType: string, sourceRef?: string) => {
    const trimmed = title.trim();
    if (!trimmed || creating) return;
    setCreating(true);
    try {
      const p = await topicsApi.createTopicProject({
        title: trimmed,
        source_type: sourceType,
        source_ref: sourceRef || undefined,
      });
      toast('研究项目已创建', 'success');
      router.push(`/topics?project=${p.id}`);
    } catch (e: any) {
      toast(`创建失败：${e?.message || '未知错误'}`, 'error');
    } finally {
      setCreating(false);
    }
  };

  const deleteProject = async (id: number) => {
    setDeleting(true);
    try {
      await topicsApi.deleteTopicProject(id);
      setProjects((prev) => prev.filter((x) => x.id !== id));
      setDeleteTarget(null);
    } catch { /* ignore */ }
    finally { setDeleting(false); }
  };

  /** 一键导出全部研究项目：逐项打包为单份 markdown 研究资料包（可直接写作或投喂 AI）。 */
  const exportAllProjects = async () => {
    if (exportingAll || projects.length === 0) return;
    setExportingAll(true);
    try {
      const details = await Promise.all(projects.map((p) => workbenchApi.getProject(p.id).catch(() => null)));
      const parts: string[] = [`# 研究项目全集（${projects.length} 个）\n`];
      details.forEach((d, idx) => {
        if (!d) return;
        const statusLabel = { to_validate: '验证中', validated: '已验证', subscribed: '已立项', abandoned: '已搁置' }[d.status] || d.status;
        const sec: string[] = [`# ${idx + 1}. ${d.title}\n`];
        const meta: string[] = [];
        meta.push(`- 来源：${d.source_type || 'manual'}${d.source_ref ? `（${d.source_ref}）` : ''}｜状态：${statusLabel}｜当前步骤：第 ${d.current_step || 1}/5 步`);
        if (d.novelty != null) meta.push(`- 新颖性 ${d.novelty}/10${d.crowding ? `｜拥挤度：${d.crowding}` : ''}${d.feasibility != null ? `｜可行性 ${d.feasibility}/10` : ''}`);
        if (d.updated_at) meta.push(`- 更新时间：${String(d.updated_at).slice(0, 10)}`);
        sec.push(`## 项目概览\n\n${meta.join('\n')}\n`);
        if (d.research_questions?.length) {
          sec.push('## 研究问题\n');
          d.research_questions.forEach((q, i) => sec.push(`${i + 1}. ${q}`));
          sec.push('');
        }
        if (d.validation_report) sec.push(`## 选题验证报告\n\n${d.validation_report}\n`);
        if (d.overview) sec.push(`## 已有研究盘点\n\n${d.overview}\n`);
        if (d.literature_review) sec.push(`## 文献脉络综述\n\n${d.literature_review}\n`);
        if (d.data_insights) {
          const di: string[] = ['## 数据与方法'];
          (d.data_insights.data_sources || []).forEach((x: any) => di.push(`- 数据源：${x.name}${x.usage ? `：${x.usage}` : ''}`));
          (d.data_insights.methods || []).forEach((x: any) => di.push(`- 方法：${x.name}${x.note ? `：${x.note}` : ''}`));
          if (d.data_insights.advice) di.push(`- 建议：${d.data_insights.advice}`);
          if (d.data_insights.my_notes) di.push(`- 我的补充：${d.data_insights.my_notes}`);
          if (di.length > 1) sec.push(di.join('\n') + '\n');
        }
        if (d.proposal) sec.push(`## 选题立项书\n\n${d.proposal}\n`);
        if (d.journal_advice) sec.push(`## 投稿期刊适配\n\n${d.journal_advice}\n`);
        if (d.papers?.length) {
          sec.push(`## 文献集（${d.papers.length} 篇）\n`);
          d.papers.forEach((pp: any, i: number) => sec.push(`${i + 1}. 《${pp.title}》${pp.journal ? `（${pp.journal}）` : ''}`));
          sec.push('');
        }
        parts.push(sec.join('\n---\n\n'));
      });
      downloadTextFile(`研究项目全集_${new Date().toISOString().slice(0, 10)}.md`, parts.join('\n\n———\n\n'), 'text/markdown;charset=utf-8');
    } catch (e: any) {
      toast(`导出失败：${e?.message || '未知错误'}`, 'error');
    } finally {
      setExportingAll(false);
    }
  };

  const stepDots = (step: number) => (
    <div className="flex items-center gap-1" title={`第 ${step} 步：${STEP_NAMES[step] || ''}`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <span
          key={i}
          className={`w-1.5 h-1.5 rounded-full ${i <= step ? 'bg-primary-600' : 'bg-gray-200 dark:bg-gray-700'}`}
        />
      ))}
    </div>
  );

  return (
    <Layout>
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-1">
          <Compass className="w-6 h-6 text-primary-600" />
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white">研究工作台</h1>
        </div>
        <p className="text-sm sm:text-base text-gray-600 dark:text-gray-400">
          从一个想法开始，贯穿 选题定义 → 验证 → 文献 → 数据与方法 → 写作输出 的完整研究项目
        </p>
      </div>

      {/* 灵感区 */}
      <div className="mb-6 bg-gradient-to-r from-purple-50 to-amber-50 dark:from-purple-900/20 dark:to-amber-900/20 border border-purple-200 dark:border-purple-800 rounded-xl p-4 sm:p-6">
        <button
          onClick={() => setInspirationOpen(!inspirationOpen)}
          className="flex items-center gap-2 text-sm font-semibold text-gray-800 dark:text-gray-200"
        >
          <Lightbulb className="w-4 h-4 text-amber-500" />
          选题灵感
          <span className="text-xs font-normal text-gray-400">
            从研究空白 / 热点趋势 / 你的关注 一键开题
          </span>
          <ChevronRight className={`w-4 h-4 transition-transform ${inspirationOpen ? 'rotate-90' : ''}`} />
        </button>

        {inspirationOpen && (
          <div className="mt-4 space-y-5">
            {/* AI 选题向导：一句话想法 → 偏好 → 选题方向+参考文献 → 立项 */}
            <div>
              <button
                onClick={() => setWizardOpen(!wizardOpen)}
                className="inline-flex items-center gap-2 px-4 py-2.5 bg-gradient-to-r from-purple-600 to-amber-600 hover:from-purple-700 hover:to-amber-700 text-white text-sm font-medium rounded-lg transition-colors shadow-sm"
              >
                <Brain className="w-4 h-4" />
                {wizardOpen ? '收起 AI 选题向导' : '打开 AI 选题向导'}
                <span className="text-[11px] font-normal opacity-80">想法 → 偏好 → 选题+参考文献 → 立项</span>
              </button>
              {wizardOpen && <div className="mt-3"><IdeaWizard /></div>}
            </div>

            {/* AI 个性化灵感推荐 */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-1.5 text-xs font-medium text-gray-600 dark:text-gray-300">
                  <Sparkles className="w-3.5 h-3.5 text-purple-600" />
                  AI 灵感推荐（基于你的关注 / 阅读 / 库内空白）
                </div>
                <button
                  onClick={loadRecommendations}
                  disabled={recommending}
                  className="inline-flex items-center gap-1 text-xs text-purple-600 dark:text-purple-400 hover:underline disabled:opacity-50"
                >
                  {recommending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Wand2 className="w-3 h-3" />}
                  {recommendations.length ? '换一批' : '为我推荐'}
                </button>
              </div>
              {recommending && (
                <p className="text-xs text-gray-400 flex items-center gap-1.5 py-2">
                  <Loader2 className="w-3 h-3 animate-spin" /> AI 正在结合你的画像推荐（约 20 秒）…
                </p>
              )}
              {!recommending && recommendations.length > 0 && (
                <div className="space-y-2">
                  {recommendations.map((r, i) => (
                    <div
                      key={i}
                      className="flex items-start justify-between gap-3 bg-white dark:bg-gray-800 border border-purple-200 dark:border-purple-800 rounded-lg p-3 hover:border-purple-400 transition-colors"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="text-sm text-gray-800 dark:text-gray-200 font-medium leading-snug">{r.title}</div>
                        <div className="text-xs text-gray-500 dark:text-gray-400 mt-0.5 line-clamp-2">{r.why}</div>
                        {r.angle && <div className="text-[11px] text-gray-400 mt-0.5">切入：{r.angle}</div>}
                      </div>
                      <button
                        onClick={() => createProject(r.title, 'ai', 'AI 灵感推荐')}
                        disabled={creating}
                        className="inline-flex items-center gap-1 text-xs px-2.5 py-1.5 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white rounded-md shrink-0 transition-colors"
                      >
                        <Plus className="w-3 h-3" /> 开题
                      </button>
                    </div>
                  ))}
                </div>
              )}
              {!recommending && recommendations.length === 0 && (
                <p className="text-xs text-gray-400">
                  点「为我推荐」，AI 结合你的关注子领域/关键词、最近阅读和库内研究空白，生成贴合你的选题方向
                </p>
              )}
            </div>

            {/* 一句话想法 */}
            <div>
              <div className="flex items-center gap-1.5 text-xs font-medium text-gray-600 dark:text-gray-300 mb-2">
                <Wand2 className="w-3.5 h-3.5 text-purple-500" />
                从一句话想法开始
              </div>
              <div className="flex flex-col sm:flex-row gap-2">
                <input
                  value={idea}
                  onChange={(e) => setIdea(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') createProject(idea, 'idea', idea); }}
                  placeholder="例：我想研究数字金融如何影响实体企业创新"
                  className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 outline-none focus:ring-2 focus:ring-purple-500"
                />
                <button
                  onClick={() => createProject(idea, 'idea', idea)}
                  disabled={creating || !idea.trim()}
                  className="inline-flex items-center justify-center gap-1.5 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white text-sm rounded-lg transition-colors shrink-0"
                >
                  {creating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
                  创建研究项目
                </button>
              </div>
            </div>

            {/* 热点趋势 */}
            {hotTopics.length > 0 && (
              <div>
                <div className="flex items-center gap-1.5 text-xs font-medium text-gray-600 dark:text-gray-300 mb-2">
                  <TrendingIcon className="w-3.5 h-3.5 text-red-500" />
                  热点趋势 Top 8
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {hotTopics.slice(0, 8).map((tp) => (
                    <button
                      key={tp.topic}
                      onClick={() => createProject(tp.topic, 'keyword', tp.topic)}
                      title={`开题：${tp.topic}（当年 ${tp.paper_count} 篇，增速 ${(tp.growth_rate * 100).toFixed(0)}%）`}
                      className="group inline-flex items-center gap-1 px-2.5 py-1.5 bg-white dark:bg-gray-800 border border-red-200 dark:border-red-900/50 rounded-lg text-xs hover:border-red-400 transition-colors"
                    >
                      <span className="text-gray-800 dark:text-gray-200">{tp.topic}</span>
                      <span className="text-[10px] text-gray-400">{tp.paper_count}篇</span>
                      <ArrowRight className="w-3 h-3 text-gray-300 group-hover:text-red-500 transition-colors" />
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* 我的关注 */}
            {(followedSubfields.length > 0 || followedKeywords.length > 0) && (
              <div>
                <div className="flex items-center gap-1.5 text-xs font-medium text-gray-600 dark:text-gray-300 mb-2">
                  <BookmarkCheck className="w-3.5 h-3.5 text-green-500" />
                  我的关注
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {[...followedSubfields.map((s) => ({ name: s, type: '子领域' })), ...followedKeywords.map((k) => ({ name: k, type: '关键词' }))].map((it) => (
                    <button
                      key={`${it.type}:${it.name}`}
                      onClick={() => createProject(it.name, 'keyword', it.name)}
                      title={`从关注开题：${it.name}`}
                      className="group inline-flex items-center gap-1 px-2.5 py-1.5 bg-white dark:bg-gray-800 border border-green-200 dark:border-green-900/50 rounded-lg text-xs hover:border-green-400 transition-colors"
                    >
                      <span className="text-gray-800 dark:text-gray-200">{it.name}</span>
                      <span className="text-[10px] text-gray-400">{it.type}</span>
                      <ArrowRight className="w-3 h-3 text-gray-300 group-hover:text-green-500 transition-colors" />
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 项目列表 */}
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <Brain className="w-4 h-4 text-primary-600" />
          我的研究项目
          <span className="text-xs font-normal text-gray-400">{projects.length}</span>
        </h2>
        {projects.length > 0 && (
          <button
            onClick={exportAllProjects}
            disabled={exportingAll}
            title="把所有项目的验证报告、综述、立项书等打包为单份 markdown"
            className="inline-flex items-center gap-1 text-xs px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700/50 disabled:opacity-50 transition-colors"
          >
            {exportingAll ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
            导出全部项目
          </button>
        )}
      </div>

      {loading ? (
        <div className="flex justify-center items-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-primary-600" />
        </div>
      ) : projects.length === 0 ? (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-10 text-center">
          <p className="text-sm text-gray-400 mb-2">还没有研究项目</p>
          <p className="text-xs text-gray-400">在上方灵感区点一个空白/热点/关注开题，或输入一句话想法创建第一个项目</p>
        </div>
      ) : (
        <>
          <div className="flex flex-col sm:flex-row gap-2 mb-4">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="按标题搜索…"
              className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 outline-none focus:ring-2 focus:ring-primary-500"
            />
            <select
              value={stepFilter}
              onChange={(e) => setStepFilter(e.target.value)}
              className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 outline-none focus:ring-2 focus:ring-primary-500"
            >
              {STEP_FILTERS.map((s) => (
                <option key={s.value || 'all'} value={s.value}>{s.label}</option>
              ))}
            </select>
            <select
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value)}
              className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 outline-none focus:ring-2 focus:ring-primary-500"
            >
              {SOURCE_FILTERS.map((s) => (
                <option key={s.value || 'all'} value={s.value}>{s.label}</option>
              ))}
            </select>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 outline-none focus:ring-2 focus:ring-primary-500"
            >
              {STATUS_FILTERS.map((s) => (
                <option key={s.value || 'all'} value={s.value}>{s.label}</option>
              ))}
            </select>
          </div>

          {filteredProjects.length === 0 ? (
            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-10 text-center">
              <p className="text-sm text-gray-400">没有匹配的项目，试试调整筛选条件</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {filteredProjects.map((p) => (
            <div
              key={p.id}
              onClick={() => router.push(`/topics?project=${p.id}`)}
              className="group bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 hover:border-primary-300 hover:shadow-md transition-all cursor-pointer"
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <h3 className="font-medium text-gray-900 dark:text-white line-clamp-2 leading-snug flex-1">{p.title}</h3>
                <button
                  onClick={(e) => { e.stopPropagation(); setDeleteTarget(p); }}
                  className="p-1 text-gray-300 hover:text-red-500 transition-colors shrink-0"
                  title="删除项目"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-1.5 min-w-0">
                  <span className={`inline-flex px-2 py-0.5 text-[11px] rounded-full font-medium shrink-0 ${STATUS_STYLES[p.status] || STATUS_STYLES.to_validate}`}>
                    {STATUS_LABELS[p.status] || '验证中'}
                  </span>
                  <span className="inline-flex px-2 py-0.5 text-[11px] rounded-full bg-purple-50 dark:bg-purple-900/30 text-purple-600 dark:text-purple-300 shrink-0">
                    {SOURCE_LABELS[p.source_type || 'manual'] || '手动'}
                  </span>
                  {p.source_ref && p.source_ref !== p.title && (
                    <span
                      title={p.source_ref}
                      className="inline-flex px-2 py-0.5 text-[11px] rounded-full bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 truncate max-w-[7rem]"
                    >
                      {p.source_ref}
                    </span>
                  )}
                </div>
                {stepDots(p.current_step || 1)}
              </div>
              {(p.novelty != null || p.crowding) && (
                <div className="flex items-center gap-2 mb-2 text-[11px]">
                  {p.novelty != null && (
                    <span className="inline-flex items-center gap-1 text-gray-500 dark:text-gray-400">
                      新颖性
                      <span className="inline-flex w-12 h-1.5 rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
                        <span className="bg-primary-500 h-full" style={{ width: `${(p.novelty / 10) * 100}%` }} />
                      </span>
                      <span className="font-medium text-gray-700 dark:text-gray-300">{p.novelty}/10</span>
                    </span>
                  )}
                  {p.crowding && (
                    <span className={`inline-flex px-1.5 py-0.5 rounded ${
                      p.crowding === '高' ? 'bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-300'
                      : p.crowding === '中' ? 'bg-amber-50 dark:bg-amber-900/30 text-amber-600 dark:text-amber-300'
                      : 'bg-green-50 dark:bg-green-900/30 text-green-600 dark:text-green-300'
                    }`}>
                      拥挤度 {p.crowding}
                    </span>
                  )}
                  {p.gate && (
                    <span className={`inline-flex px-1.5 py-0.5 rounded ${
                      p.gate === 'pass' ? 'bg-green-50 dark:bg-green-900/30 text-green-600 dark:text-green-300'
                      : p.gate === 'caution' ? 'bg-amber-50 dark:bg-amber-900/30 text-amber-600 dark:text-amber-300'
                      : 'bg-red-50 dark:bg-red-900/30 text-red-600 dark:text-red-300'
                    }`}>
                      门控 {p.gate}
                    </span>
                  )}
                  {p.verdict && (
                    <span className="inline-flex px-1.5 py-0.5 rounded bg-violet-50 dark:bg-violet-900/30 text-violet-600 dark:text-violet-300">
                      {p.verdict}
                    </span>
                  )}
                </div>
              )}
              <div className="flex items-center justify-between text-xs text-gray-400">
                <span>
                  {STEP_NAMES[p.current_step || 1] || '选题定义'}
                  <span className="text-gray-300"> · 第 {(p.current_step || 1)}/5 步</span>
                  {p.updated_at && <span className="text-gray-300"> · 更新 {p.updated_at.slice(0, 10)}</span>}
                </span>
                <span className="flex items-center gap-1 text-primary-600 dark:text-primary-400 group-hover:gap-1.5 transition-all">
                  继续 <ChevronRight className="w-3 h-3" />
                </span>
              </div>
            </div>
          ))}
            </div>
          )}
        </>
      )}

      {/* 删除确认 */}
      <ConfirmModal
        open={!!deleteTarget}
        danger
        confirming={deleting}
        title="删除研究项目？"
        description={`「${deleteTarget?.title || ''}」的文献集、验证报告、综述与立项书将一并删除且不可恢复。`}
        onConfirm={() => deleteTarget && deleteProject(deleteTarget.id)}
        onCancel={() => setDeleteTarget(null)}
      />

      {/* 研究空白（常驻） */}
      <div className="mt-8 bg-white dark:bg-gray-800 rounded-lg border border-purple-200 dark:border-purple-800 p-4 sm:p-6">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <div>
            <h2 className="flex items-center gap-1.5 text-lg font-semibold text-gray-900 dark:text-white">
              <Flame className="w-4 h-4 text-orange-500" /> 研究空白
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">各自高频但少有人交叉的组合——可能的选题机会，点「开题」直接创建项目</p>
          </div>
          <button
            onClick={startGapAnalysis}
            disabled={gapAnalyzing || gaps.length === 0}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white text-xs rounded-md transition-colors"
          >
            {gapAnalyzing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
            {gapAnalysis?.status === 'success' ? '重新解读' : 'AI 空白解读'}
          </button>
        </div>

        {gaps.length === 0 ? (
          <p className="text-xs text-gray-400 py-3">暂无空白数据</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm min-w-[520px]">
              <thead>
                <tr className="text-left text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
                  <th className="py-2 px-2 font-medium">#</th>
                  <th className="py-2 px-2 font-medium">关键词 A</th>
                  <th className="py-2 px-2 font-medium">关键词 B</th>
                  <th className="py-2 px-2 font-medium text-right">频次</th>
                  <th className="py-2 px-2 font-medium text-right">共现</th>
                  <th className="py-2 px-2 font-medium text-right">空白分</th>
                  <th className="py-2 px-2 font-medium text-center">操作</th>
                </tr>
              </thead>
              <tbody>
                {gaps.slice(0, 10).map((g, i) => (
                  <tr key={`${g.source}-${g.target}`} className="border-b border-gray-100 dark:border-gray-700/50 hover:bg-gray-50 dark:hover:bg-gray-700/30 transition-colors">
                    <td className="py-2 px-2 text-gray-400 text-xs">{i + 1}</td>
                    <td className="py-2 px-2">
                      <span className="inline-flex px-2 py-0.5 bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 rounded text-xs font-medium">{g.source}</span>
                    </td>
                    <td className="py-2 px-2">
                      <span className="inline-flex px-2 py-0.5 bg-green-50 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded text-xs font-medium">{g.target}</span>
                    </td>
                    <td className="py-2 px-2 text-right text-xs text-gray-500">{g.source_count}/{g.target_count}</td>
                    <td className="py-2 px-2 text-right text-xs text-gray-500">{g.cooccurrence}</td>
                    <td className="py-2 px-2 text-right text-xs font-semibold text-purple-600 dark:text-purple-400">{(g.gap_score * 100).toFixed(1)}</td>
                    <td className="py-2 px-2 text-center">
                      <button
                        onClick={() => createProject(`交叉研究：${g.source} 与 ${g.target} 的结合`, 'gap', `${g.source}×${g.target}`)}
                        disabled={creating}
                        className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-primary-600 dark:text-primary-400 border border-primary-200 dark:border-primary-700/50 rounded-md hover:bg-primary-50 dark:hover:bg-primary-900/30 transition-colors disabled:opacity-40"
                        title={`开题：${g.source} × ${g.target}`}
                      >
                        <Plus className="w-3 h-3" /> 开题
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {gapAnalyzing && (
          <p className="mt-3 text-xs text-gray-400 flex items-center gap-1.5">
            <Loader2 className="w-3 h-3 animate-spin" /> AI 正在解读空白（约 1 分钟）…
          </p>
        )}
        {gapAnalysis?.status === 'success' && gapAnalysis.raw_analysis && (
          <div className="mt-3 max-h-72 overflow-y-auto bg-gray-50 dark:bg-gray-700/30 rounded-lg border border-purple-100 dark:border-purple-800/50 p-3">
            <div className="text-xs font-medium text-gray-500 mb-2 flex items-center gap-1.5">
              <Sparkles className="w-3 h-3 text-purple-500" /> AI 空白解读卡片
            </div>
            <MarkdownRenderer content={gapAnalysis.raw_analysis} />
          </div>
        )}
      </div>
    </Layout>
  );
}

function TrendingIcon({ className }: { className?: string }) {
  return <Flame className={className} />;
}
