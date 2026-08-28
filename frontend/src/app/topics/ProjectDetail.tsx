'use client';

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useRouter } from 'next/navigation';
import Layout from '@/components/Layout';
import { useToast } from '@/components/Toast';
import { workbenchApi } from '@/lib/api';
import { reportPageContext } from '@/lib/assistantBus';
import type { TopicProject } from '@/types/paper';
import { ArrowLeft, Loader2, CheckCircle2 } from 'lucide-react';
import Step1Topic from './steps/Step1Topic';
import Step2Validate from './steps/Step2Validate';
import Step3Literature from './steps/Step3Literature';
import Step4Data from './steps/Step4Data';
import Step5Writing from './steps/Step5Writing';

const STEPS = [
  { n: 1, name: '选题定义', desc: '打磨题目与研究问题' },
  { n: 2, name: '选题验证', desc: '新颖性 / 拥挤度 / 竞争' },
  { n: 3, name: '文献管理', desc: '收集与精读相关论文' },
  { n: 4, name: '数据与方法', desc: '数据来源与识别策略' },
  { n: 5, name: '写作输出', desc: '综述 / 立项书 / 期刊' },
];

export default function ProjectDetail({ projectId, initialStep }: { projectId: number; initialStep?: number }) {
  const { toast } = useToast();
  const router = useRouter();

  const [project, setProject] = useState<TopicProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
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

  // ai_pending 期间轮询项目详情，直到后台任务完成
  useEffect(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    if (!project?.ai_pending) return;
    pollRef.current = setInterval(async () => {
      try {
        const p = await workbenchApi.getProject(projectId);
        setProject(p);
        if (!p.ai_pending) {
          if (pollRef.current) clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch { /* 忽略瞬时错误 */ }
    }, 3000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [project?.ai_pending, projectId]);

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
    setProject({ ...project, current_step: n });
    workbenchApi.updateProject(project.id, { current_step: n }).catch(() => {});
    router.replace(`/topics?project=${project.id}&step=${n}`);
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

  const current = project.current_step || 1;
  const stepProps = { project, onRefresh, onPatch, runAi };

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
        <h1 className="text-xl sm:text-2xl font-bold text-gray-900 dark:text-white leading-snug">{project.title}</h1>
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

      {/* 步骤条 */}
      <div className="flex gap-1 mb-6 overflow-x-auto pb-1">
        {STEPS.map((s) => {
          const active = s.n === current;
          const done = s.n < current;
          return (
            <button
              key={s.n}
              onClick={() => goStep(s.n)}
              className={`flex-1 min-w-[120px] px-3 py-2.5 rounded-lg border text-left transition-colors ${
                active
                  ? 'bg-primary-600 text-white border-primary-600'
                  : done
                  ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300 border-green-200 dark:border-green-800 hover:border-green-400'
                  : 'bg-white dark:bg-gray-800 text-gray-600 dark:text-gray-300 border-gray-200 dark:border-gray-700 hover:border-primary-300'
              }`}
            >
              <div className="flex items-center gap-1.5 text-xs font-semibold">
                {done ? <CheckCircle2 className="w-3.5 h-3.5" /> : <span className="opacity-70">{s.n}</span>}
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
    </Layout>
  );
}
