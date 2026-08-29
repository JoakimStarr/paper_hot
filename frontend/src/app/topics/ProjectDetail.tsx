'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import Layout from '@/components/Layout';
import { useToast } from '@/components/Toast';
import { workbenchApi } from '@/lib/api';
import { reportPageContext } from '@/lib/assistantBus';
import type { TopicProject } from '@/types/paper';
import { ArrowLeft, Loader2, CheckCircle2, Circle, Flag, Archive, RotateCcw } from 'lucide-react';
import Step1Topic from './steps/Step1Topic';
import Step2Validate from './steps/Step2Validate';
import Step3Literature from './steps/Step3Literature';
import Step4Data from './steps/Step4Data';
import Step5Writing from './steps/Step5Writing';
import StepFooter from './steps/StepFooter';

/** 每步的命名产出物与完成条件（完成度真实化：勾选按内容判定，不再按位置） */
const STEPS = [
  {
    n: 1, name: '选题定义', desc: '打磨题目与研究问题',
    doneHint: '填好选题标题，并至少添加 1 个研究问题',
    isDone: (p: TopicProject) => !!p.title?.trim() && (p.research_questions?.filter((q) => q.trim()).length ?? 0) >= 1,
  },
  {
    n: 2, name: '选题验证', desc: '新颖性 / 拥挤度 / 竞争',
    doneHint: '跑一次「开始验证」生成验证报告',
    isDone: (p: TopicProject) => !!p.validation_report,
  },
  {
    n: 3, name: '文献管理', desc: '收集与精读相关论文',
    doneHint: '文献集里至少收集 3 篇相关论文',
    isDone: (p: TopicProject) => (p.papers?.length ?? 0) >= 3,
  },
  {
    n: 4, name: '数据与方法', desc: '数据来源与识别策略',
    doneHint: '提取一次数据与方法线索（或写下你自己的数据补充）',
    isDone: (p: TopicProject) => !!p.data_insights,
  },
  {
    n: 5, name: '写作输出', desc: '综述 / 立项书 / 期刊',
    doneHint: '生成选题立项书（验证通过后会自动生成）',
    isDone: (p: TopicProject) => !!p.proposal,
  },
];

const STATUS_META: Record<string, { label: string; cls: string }> = {
  to_validate: { label: '验证中', cls: 'bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300' },
  validated: { label: '已验证', cls: 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300' },
  subscribed: { label: '已立项', cls: 'bg-green-100 dark:bg-green-900/40 text-green-700 dark:text-green-300' },
  abandoned: { label: '已搁置', cls: 'bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400' },
};

export default function ProjectDetail({ projectId, initialStep }: { projectId: number; initialStep?: number }) {
  const { toast } = useToast();
  const router = useRouter();

  const [project, setProject] = useState<TopicProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // 深链：?step= 参数优先显示指定步骤；未传时跟随后端 current_step（点击步骤条后以本地为准）
  const [stepOverride, setStepOverride] = useState<number | null>(
    initialStep && initialStep >= 1 && initialStep <= 5 ? initialStep : null
  );
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const p = await workbenchApi.getProject(projectId);
      setProject(p);
      setError(null);
      return p;
    } catch (e: any) {
      setError(e?.message || '项目加载失败');
      return null;
    } finally {
      if (!silent) setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    load();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [load]);

  // 向全局助手上报当前项目与步骤（助手据此注入项目上下文）
  useEffect(() => {
    if (!project) return;
    reportPageContext({
      tab: `step${project.current_step || 1}`,
      projectTitle: project.title,
      projectStep: project.current_step || 1,
    });
  }, [project?.id, project?.current_step, project?.title]);

  // ai_pending 期间轮询轻量 /status 接口（只更新顶栏状态），任务结束再全量刷新
  useEffect(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    if (!project?.ai_pending) return;
    pollRef.current = setInterval(async () => {
      try {
        const s = await workbenchApi.getProjectStatus(projectId);
        // 仅更新顶栏展示的 ai_pending/ai_error，避免每 3s 拉全量项目
        setProject((prev) => (prev ? { ...prev, ai_pending: s.ai_pending, ai_error: s.ai_error } : prev));
        if (!s.ai_pending) {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
          // AI 任务完成（或出错）→ 全量刷新，拿到各步骤最新内容
          await load(true);
        }
      } catch { /* 忽略瞬时错误 */ }
    }, 3000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [project?.ai_pending, projectId, load]);

  const onRefresh = useCallback(async () => {
    await load(true);
  }, [load]);

  const onPatch = useCallback(async (patch: Record<string, unknown>) => {
    if (!project) return;
    try {
      const updated = await workbenchApi.updateProject(project.id, patch);
      setProject(updated);
    } catch (e: any) {
      toast(`保存失败：${e?.message || '未知错误'}`, 'error');
    }
  }, [project, toast]);

  const runAi = useCallback(async (action: string, ideaText?: string) => {
    if (!project) return;
    try {
      await workbenchApi.aiAction(project.id, action, ideaText);
      await load(true);
    } catch (e: any) {
      toast(e?.message || '任务启动失败', 'error');
    }
  }, [project, load, toast]);

  const goStep = (n: number) => {
    if (!project) return;
    setStepOverride(n);
    setProject({ ...project, current_step: n });
    workbenchApi.updateProject(project.id, { current_step: n }).catch(() => {});
    router.replace(`/topics?project=${project.id}&step=${n}`);
  };

  /** 状态流转（激活闲置的 status 状态机） */
  const changeStatus = async (status: 'subscribed' | 'abandoned' | 'to_validate') => {
    await onPatch({ status });
    toast(status === 'subscribed' ? '已标记为立项' : status === 'abandoned' ? '已标记为搁置' : '已恢复为进行中', 'success');
  };

  if (loading) {
    return (
      <Layout>
        <div className="flex justify-center items-center py-16">
          <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
        </div>
      </Layout>
    );
  }

  if (error || !project) {
    return (
      <Layout>
        <div className="text-center py-16">
          <p className="text-red-500 mb-4">{error || '项目不存在'}</p>
          <button onClick={() => router.push('/topics')} className="text-primary-600 hover:underline text-sm">返回研究工作台</button>
        </div>
      </Layout>
    );
  }

  const current = stepOverride ?? (project.current_step || 1);
  const stepProps = { project, onRefresh, onPatch, runAi, goStep };
  const statusMeta = STATUS_META[project.status] || STATUS_META.to_validate;
  const isLast = current === 5;

  const handleFooterPrimary = async () => {
    if (isLast) {
      // 走完五步：状态置为已立项，回到选题库
      if (project.status !== 'subscribed') await onPatch({ status: 'subscribed' });
      router.push('/topics');
      return;
    }
    goStep(current + 1);
  };

  return (
    <Layout>
      {/* 顶栏 */}
      <div className="mb-4">
        <button
          onClick={() => router.push('/topics')}
          className="inline-flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" /> 返回项目列表
        </button>
      </div>
      <div className="mb-5">
        <div className="flex items-start gap-2.5 flex-wrap">
          <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-white leading-snug">{project.title}</h1>
          <span className={`shrink-0 mt-1.5 inline-flex px-2 py-0.5 text-[11px] rounded-full font-medium ${statusMeta.cls}`}>
            {statusMeta.label}
          </span>
        </div>
        {/* 状态流转操作 */}
        <div className="mt-2 flex items-center gap-2 flex-wrap">
          {project.status !== 'subscribed' && (
            <button onClick={() => changeStatus('subscribed')} className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded-md border border-green-200 dark:border-green-800 text-green-700 dark:text-green-300 hover:bg-green-50 dark:hover:bg-green-900/20 transition-colors">
              <Flag className="w-3 h-3" /> 标记已立项
            </button>
          )}
          {project.status !== 'abandoned' && (
            <button onClick={() => changeStatus('abandoned')} className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded-md border border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700/40 transition-colors">
              <Archive className="w-3 h-3" /> 暂时搁置
            </button>
          )}
          {project.status !== 'to_validate' && (
            <button onClick={() => changeStatus('to_validate')} className="inline-flex items-center gap-1 text-[11px] px-2 py-1 rounded-md border border-gray-200 dark:border-gray-700 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700/40 transition-colors">
              <RotateCcw className="w-3 h-3" /> 恢复进行中
            </button>
          )}
        </div>
        {project.ai_pending && (
          <span className="mt-2 inline-flex items-center gap-1.5 text-xs text-purple-600 dark:text-purple-400">
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
            AI 正在执行「{project.ai_pending}」…
          </span>
        )}
        {!project.ai_pending && project.ai_error && (
          <span className="mt-2 inline-flex items-center gap-1 text-xs text-red-500">
            AI 任务失败：{project.ai_error}
          </span>
        )}
      </div>

      {/* 步骤条（完成状态按内容判定） */}
      <div className="flex gap-1 mb-6 overflow-x-auto pb-1">
        {STEPS.map((s) => {
          const active = s.n === current;
          const done = s.isDone(project) && !active;
          return (
            <button
              key={s.n}
              onClick={() => goStep(s.n)}
              title={`完成条件：${s.doneHint}`}
              className={`flex-1 min-w-[120px] px-3 py-2.5 rounded-lg border text-left transition-colors ${
                active
                  ? 'bg-primary-600 text-white border-primary-600'
                  : done
                  ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300 border-green-200 dark:border-green-800 hover:border-green-400'
                  : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:border-primary-300'
              }`}
            >
              <div className="flex items-center gap-1.5 text-xs font-semibold">
                {done ? <CheckCircle2 className="w-3.5 h-3.5" /> : active ? <Loader2 className="w-3.5 h-3.5" /> : <Circle className="w-3.5 h-3.5 opacity-60" />}
                {s.name}
              </div>
              <div className={`text-[11px] mt-0.5 ${active ? 'text-white/80' : 'text-gray-400'}`}>{s.desc}</div>
            </button>
          );
        })}
      </div>

      {/* 当前步骤 */}
      {current === 1 && <Step1Topic {...stepProps} />}
      {current === 2 && <Step2Validate {...stepProps} />}
      {current === 3 && <Step3Literature {...stepProps} />}
      {current === 4 && <Step4Data {...stepProps} />}
      {current === 5 && <Step5Writing {...stepProps} />}

      {/* 统一主线引导：完成条件提示 + 下一步主 CTA */}
      <div className="mt-6">
        <StepFooter
          stepDone={STEPS[current - 1].isDone(project)}
          doneHint={STEPS[current - 1].doneHint}
          primaryLabel={isLast ? '完成，回到选题库' : `下一步：${STEPS[current].name}`}
          onPrimary={handleFooterPrimary}
        />
      </div>
    </Layout>
  );
}
