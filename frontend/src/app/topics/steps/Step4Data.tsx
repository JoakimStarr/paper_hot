'use client';

import React, { useEffect, useState } from 'react';
import { Database, Loader2, Sparkles, Save, Check, BookMarked } from 'lucide-react';
import { skillsApi } from '@/lib/api';
import type { DataInsights, MethodPlaybookEntry } from '@/types/paper';
import type { StepProps } from './types';

export default function Step4Data({ project, onPatch, runAi }: StepProps) {
  const [myNotes, setMyNotes] = useState(project.data_insights?.my_notes || '');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  // 方法手册全量条目（系统预置，挂载时取一次；按 matched_methods 渲染命中卡）
  const [playbook, setPlaybook] = useState<MethodPlaybookEntry[]>([]);

  useEffect(() => {
    let cancelled = false;
    skillsApi.getMethodPlaybook()
      .then((res) => { if (!cancelled) setPlaybook(res.entries || []); })
      .catch(() => { /* 静默失败：手册卡不渲染即可 */ });
    return () => { cancelled = true; };
  }, []);

  const aiRunning = project.ai_pending === 'data_insights';
  const insights: DataInsights | null = project.data_insights || null;
  const hasAi = !!(insights && (insights.data_sources?.length || insights.methods?.length || insights.advice));
  const matchedEntries = (insights?.matched_methods || [])
    .map((id) => playbook.find((e) => e.id === id))
    .filter((e): e is MethodPlaybookEntry => !!e);

  const [aiModels, setAiModels] = useState<Array<{ id: string; label: string }>>([]);
  const [aiModel, setAiModel] = useState('');
  const [showModelSelect, setShowModelSelect] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { papersApi, getLastModel, rememberModel } = await import('@/lib/api');
        const res = await papersApi.getAIAnalysisModels();
        const bare = (n: string) => (n.includes('/') ? n.split('/').slice(1).join('/') : n);
        const label = (provider?: string) => (provider ? `${provider} · ` : '');
        const list = (res.models || [])
          .filter((m) => m.available)
          .map((m) => ({ id: m.name, label: `${label(m.provider)}${bare(m.name)}` }));
        if (!cancelled) {
          setAiModels(list);
          const last = getLastModel('step4_insights');
          if (last && list.some((m) => m.id === last)) setAiModel(last);
        }
      } catch { /* 模型列表加载失败：仍可用默认模型 */ }
    })();
    return () => { cancelled = true; };
  }, []);

  const saveNotes = async () => {
    setSaving(true);
    const base = (insights || {}) as DataInsights;
    await onPatch({ data_insights: { ...base, my_notes: myNotes } });
    setSaving(false);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const extract = async () => {
    if (aiModel) {
      const { rememberModel } = await import('@/lib/api');
      rememberModel('step4_insights', aiModel);
    }
    await runAi('data_insights', undefined);
  };

  return (
    <div className="space-y-5">
      {/* AI 数据线索 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-purple-200 dark:border-purple-800 p-4 sm:p-6">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div>
            <h2 className="flex items-center gap-1.5 text-base font-semibold text-gray-900 dark:text-white">
              <Database className="w-4 h-4 text-blue-600" /> 数据与方法线索
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">
              从项目文献集提取已有研究用的数据来源与识别策略，并给数据可得性建议
            </p>
          </div>
          <div className="flex items-center gap-2">
            {/* 模型选择（默认跟随全局 default_model） */}
            <div className="relative">
              <button
                onClick={() => setShowModelSelect((v) => !v)}
                className="inline-flex items-center gap-1 px-2.5 py-2 text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                title="选择提取线索用的模型（默认自动）"
              >
                {aiModel ? (aiModels.find((m) => m.id === aiModel)?.label || aiModel) : '默认模型'}
              </button>
              {showModelSelect && (
                <div className="absolute right-0 top-9 z-10 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg py-1 min-w-[200px] max-h-72 overflow-y-auto">
                  <button
                    onClick={() => { setAiModel(''); setShowModelSelect(false); }}
                    className={`w-full text-left px-3 py-1.5 text-xs hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors ${aiModel === '' ? 'text-purple-600 font-medium' : 'text-gray-700 dark:text-gray-300'}`}
                  >
                    默认（跟随全局设置）
                  </button>
                  {aiModels.map((m) => (
                    <button
                      key={m.id}
                      onClick={() => { setAiModel(m.id); setShowModelSelect(false); }}
                      className={`w-full text-left px-3 py-1.5 text-xs hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors ${aiModel === m.id ? 'text-purple-600 font-medium' : 'text-gray-700 dark:text-gray-300'}`}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button
              onClick={extract}
              disabled={aiRunning || (project.papers?.length || 0) === 0}
              title={aiRunning ? 'AI 正在提取中…' : (project.papers?.length || 0) === 0 ? '文献集为空：先到第 3 步「文献管理」收集论文（或回第 2 步验证召回），才能从中提取数据与方法线索' : undefined}
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white text-sm rounded-lg transition-colors"
            >
              {aiRunning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
              {hasAi ? '重新提取' : '提取线索'}
            </button>
          </div>
        </div>

        {aiRunning && (
          <div className="flex items-center justify-center gap-2 text-sm text-purple-600 dark:text-purple-400 py-6">
            <Loader2 className="w-5 h-5 animate-spin" /> AI 正在提取数据与方法线索…
          </div>
        )}

        {!aiRunning && hasAi && insights && (
          <div className="space-y-4">
            {insights.data_sources && insights.data_sources.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold text-gray-600 dark:text-gray-300 mb-2">数据来源</h3>
                <ul className="space-y-1.5">
                  {insights.data_sources.map((d, i) => (
                    <li key={i} className="text-xs bg-gray-50 dark:bg-gray-700/40 rounded-md px-3 py-2">
                      <span className="font-medium text-gray-800 dark:text-gray-200">{d.name}</span>
                      {d.papers?.length > 0 && (
                        <span className="text-gray-400 ml-2">用于 [{d.papers.join('][')}]</span>
                      )}
                      {d.usage && <span className="block text-gray-500 mt-0.5">{d.usage}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {insights.methods && insights.methods.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold text-gray-600 dark:text-gray-300 mb-2">研究方法</h3>
                <ul className="space-y-1.5">
                  {insights.methods.map((m, i) => (
                    <li key={i} className="text-xs bg-gray-50 dark:bg-gray-700/40 rounded-md px-3 py-2">
                      <span className="font-medium text-gray-800 dark:text-gray-200">{m.name}</span>
                      {m.papers?.length > 0 && <span className="text-gray-400 ml-2">用于 [{m.papers.join('][')}]</span>}
                      {m.note && <span className="block text-gray-500 mt-0.5">{m.note}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {insights.advice && (
              <div>
                <h3 className="text-xs font-semibold text-gray-600 dark:text-gray-300 mb-2">数据可得性建议</h3>
                <p className="text-xs text-gray-600 dark:text-gray-400 leading-relaxed bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800/50 rounded-md px-3 py-2">
                  {insights.advice}
                </p>
              </div>
            )}
          </div>
        )}
        {!aiRunning && !hasAi && (
          <p className="text-xs text-gray-400">先在「文献管理」添加论文（或第 2 步验证召回），再提取数据与方法线索。</p>
        )}
      </div>

      {/* 方法手册（系统预置条目，按选题关键词命中；设计/数据/假设/诊断三元组） */}
      {matchedEntries.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-blue-200 dark:border-blue-800 p-4 sm:p-6">
          <div className="flex items-center gap-2 mb-1">
            <BookMarked className="w-4 h-4 text-blue-600" />
            <h2 className="text-base font-semibold text-gray-900 dark:text-white">方法手册</h2>
            <span className="text-xs text-gray-400">按选题关键词命中的系统预置方法条目（{matchedEntries.length}）</span>
          </div>
          <p className="text-xs text-gray-400 mb-4">每条含适用场景、数据需求、关键假设、必做诊断与参考实现——立项书方法论章节可直接引用</p>
          <div className="space-y-3">
            {matchedEntries.map((e) => (
              <div key={e.id} className="border border-blue-100 dark:border-blue-800/50 rounded-lg p-3.5">
                <h3 className="text-sm font-semibold text-gray-900 dark:text-white">{e.name}</h3>
                <p className="text-xs text-gray-600 dark:text-gray-300 mt-1"><span className="font-medium text-gray-500">适用：</span>{e.applies}</p>
                <p className="text-xs text-gray-600 dark:text-gray-300 mt-1"><span className="font-medium text-gray-500">数据需求：</span>{e.data_needs}</p>
                <p className="text-xs text-gray-600 dark:text-gray-300 mt-1"><span className="font-medium text-gray-500">关键假设：</span>{e.assumptions}</p>
                <div className="mt-2">
                  <p className="text-xs font-medium text-gray-500 mb-1">必做诊断</p>
                  <ul className="space-y-0.5">
                    {e.diagnostics.map((d, i) => (
                      <li key={i} className="text-xs text-gray-500 dark:text-gray-400">• {d}</li>
                    ))}
                  </ul>
                </div>
                <p className="mt-2 text-[11px] text-gray-400 bg-gray-50 dark:bg-gray-700/40 rounded px-2.5 py-1.5 font-mono">{e.code_hint}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 手动补充 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sm:p-6">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-base font-semibold text-gray-900 dark:text-white">我的数据与补充</h2>
          <button
            onClick={saveNotes}
            disabled={saving}
            className="inline-flex items-center gap-1 text-xs px-3 py-1.5 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white rounded-md transition-colors"
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : saved ? <Check className="w-3.5 h-3.5" /> : <Save className="w-3.5 h-3.5" />}
            {saved ? '已保存' : '保存'}
          </button>
        </div>
        <p className="text-xs text-gray-400 mb-2">记录你自己已获得/计划申请的数据，作为项目的一部分沉淀下来</p>
        <textarea
          value={myNotes}
          onChange={(e) => setMyNotes(e.target.value)}
          rows={4}
          placeholder="例：已获取某省中小企业数据库 2015-2024；计划申请上市公司专利数据…"
          className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 outline-none focus:ring-2 focus:ring-primary-500"
        />
      </div>
    </div>
  );
}
