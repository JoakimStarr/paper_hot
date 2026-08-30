'use client';

import React, { useState } from 'react';
import { Loader2, Sparkles, Wand2, Plus, X, Check, Trash2, CheckCircle2 } from 'lucide-react';
import type { GeneratedTopic } from '@/types/paper';
import type { StepProps } from './types';

const SOURCE_LABELS: Record<string, string> = {
  gap: '研究空白',
  keyword: '热点/关注',
  idea: '一句话想法',
  manual: '手动创建',
};

export default function Step1Topic({ project, onPatch, runAi, goStep }: StepProps) {
  const [title, setTitle] = useState(project.title);
  const [questions, setQuestions] = useState<string[]>(project.research_questions || []);
  const [newQuestion, setNewQuestion] = useState('');
  // 检索关键词：优先已保存的 search_keywords，否则从灵感快照 generated_topics 派生默认值
  const defaultKeywords = React.useMemo(() => {
    const saved = project.search_keywords || [];
    if (saved.length > 0) return saved;
    const set = new Set<string>();
    for (const g of project.generated_topics || []) {
      for (const k of g.keywords || []) {
        const t = k.trim();
        if (t) set.add(t);
      }
    }
    return Array.from(set);
  }, [project.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const [keywords, setKeywords] = useState<string[]>(defaultKeywords);
  const [newKeyword, setNewKeyword] = useState('');
  const [saving, setSaving] = useState(false);
  const [adopted, setAdopted] = useState(false);

  const aiRunning = project.ai_pending === 'generate_topics';

  const saveBasic = async () => {
    const t = title.trim();
    if (!t) return;
    setSaving(true);
    await onPatch({
      title: t,
      research_questions: questions.filter((q) => q.trim()),
      search_keywords: keywords.map((k) => k.trim()).filter(Boolean),
    });
    setSaving(false);
  };

  const addQuestion = () => {
    const q = newQuestion.trim();
    if (!q) return;
    setQuestions((prev) => [...prev, q]);
    setNewQuestion('');
  };

  const addKeyword = () => {
    const k = newKeyword.trim();
    if (!k || keywords.includes(k)) return;
    setKeywords((prev) => [...prev, k]);
    setNewKeyword('');
  };

  const applyTopic = async (g: GeneratedTopic) => {
    setAdopted(true);
    await onPatch({
      title: g.title,
      research_questions: g.research_questions || [],
      generated_topics: project.generated_topics,
    });
    setTitle(g.title);
    setQuestions(g.research_questions || []);
    // 采纳候选时把其检索关键词合并进编辑器（去重），供第 2/3 步直接使用
    setKeywords((prev) => {
      const set = new Set(prev);
      for (const k of g.keywords || []) {
        const t = k.trim();
        if (t) set.add(t);
      }
      return Array.from(set);
    });
    setTimeout(() => setAdopted(false), 2000);
  };

  return (
    <div className="space-y-5">
      {/* 最新评估结论（反向闭环：验证/辩论/答辩结论可带回来改题） */}
      {(project.novelty != null || project.validation_report) && (
        <div className="flex items-center gap-2 flex-wrap bg-green-50 dark:bg-green-900/10 border border-green-200 dark:border-green-800/60 rounded-lg p-3">
          <CheckCircle2 className="w-4 h-4 text-green-600 shrink-0" />
          <span className="text-xs text-green-700 dark:text-green-300">
            最新评估结论
            {project.novelty != null && <> · 新颖性 <strong>{project.novelty}/10</strong></>}
            {project.crowding && <> · 拥挤度 <strong>{project.crowding}</strong></>}
            {project.gate && <> · 门控 <strong>{project.gate}</strong></>}
            {project.verdict && <> · 答辩结论 <strong>{project.verdict}</strong></>}
          </span>
          {goStep && (
            <>
              <button onClick={() => goStep(2)} className="text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline">
                去第 2 步查看 →
              </button>
              <button onClick={() => goStep(5)} className="text-xs font-medium text-primary-600 dark:text-primary-400 hover:underline">
                去第 5 步生成立项书 →
              </button>
            </>
          )}
        </div>
      )}

      {/* 基本信息 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sm:p-6">
        <div className="flex items-center gap-2 mb-4">
          <Wand2 className="w-4 h-4 text-purple-600" />
          <h2 className="text-base font-semibold text-gray-900 dark:text-white">选题定义</h2>
          <span className="text-xs text-gray-400">第 1 步</span>
        </div>

        {project.source_type && project.source_type !== 'manual' && (
          <div className="mb-4 text-xs text-gray-500 dark:text-gray-400 bg-gray-50 dark:bg-gray-700/40 rounded-md px-3 py-2">
            来源：{SOURCE_LABELS[project.source_type] || project.source_type}
            {project.source_ref ? ` · ${project.source_ref}` : ''}
          </div>
        )}

        <label className="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1.5">选题标题</label>
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="输入选题标题"
          className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 outline-none focus:ring-2 focus:ring-primary-500 mb-4"
        />

        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs font-medium text-gray-500 dark:text-gray-400">研究问题</label>
          <button
            onClick={saveBasic}
            disabled={saving || !title.trim()}
            className="inline-flex items-center gap-1 text-xs px-3 py-1.5 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white rounded-md transition-colors"
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
            保存
          </button>
        </div>
        <div className="space-y-1.5 mb-2">
          {questions.map((q, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="text-xs text-gray-400 w-5 text-right shrink-0">{i + 1}.</span>
              <input
                value={q}
                onChange={(e) => setQuestions((prev) => prev.map((x, j) => (j === i ? e.target.value : x)))}
                className="flex-1 px-2.5 py-1.5 text-sm border border-gray-200 dark:border-gray-700 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 outline-none focus:ring-1 focus:ring-primary-400"
              />
              <button
                onClick={() => setQuestions((prev) => prev.filter((_, j) => j !== i))}
                className="p-1 text-gray-300 hover:text-red-500 transition-colors"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
        <div className="flex gap-2">
          <input
            value={newQuestion}
            onChange={(e) => setNewQuestion(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') addQuestion(); }}
            placeholder="添加一个研究问题，Enter 确认"
            className="flex-1 px-2.5 py-1.5 text-sm border border-gray-200 dark:border-gray-700 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 outline-none focus:ring-1 focus:ring-primary-400"
          />
          <button
            onClick={addQuestion}
            disabled={!newQuestion.trim()}
            className="inline-flex items-center gap-1 text-xs px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700/50 disabled:opacity-50 transition-colors"
          >
            <Plus className="w-3.5 h-3.5" /> 添加
          </button>
        </div>

        {/* 检索关键词：驱动第 2 步验证检索与第 3 步文献召回 */}
        <div className="mt-5 pt-4 border-t border-gray-100 dark:border-gray-700">
          <div className="flex items-center justify-between mb-1.5">
            <label className="text-xs font-medium text-gray-500 dark:text-gray-400">
              检索关键词
              <span className="ml-1.5 font-normal text-gray-400">驱动第 2 步验证与第 3 步文献召回</span>
            </label>
            <button
              onClick={saveBasic}
              disabled={saving || !title.trim()}
              className="inline-flex items-center gap-1 text-xs px-3 py-1.5 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white rounded-md transition-colors"
            >
              {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
              保存
            </button>
          </div>
          {keywords.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-2">
              {keywords.map((k) => (
                <span
                  key={k}
                  className="inline-flex items-center gap-1 px-2.5 py-1 text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300 rounded-full"
                >
                  {k}
                  <button
                    onClick={() => setKeywords((prev) => prev.filter((x) => x !== k))}
                    className="text-gray-400 hover:text-red-500 transition-colors"
                    title="移除关键词"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
          )}
          <div className="flex gap-2">
            <input
              value={newKeyword}
              onChange={(e) => setNewKeyword(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') addKeyword(); }}
              placeholder="添加检索关键词，Enter 确认（如：耐心资本、PSM-DID）"
              className="flex-1 px-2.5 py-1.5 text-sm border border-gray-200 dark:border-gray-700 rounded-md bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100 placeholder-gray-400 outline-none focus:ring-1 focus:ring-primary-400"
            />
            <button
              onClick={addKeyword}
              disabled={!newKeyword.trim()}
              className="inline-flex items-center gap-1 text-xs px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700/50 disabled:opacity-50 transition-colors"
            >
              <Plus className="w-3.5 h-3.5" /> 添加
            </button>
          </div>
        </div>
      </div>

      {/* AI 选题建议 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-purple-200 dark:border-purple-800 p-4 sm:p-6">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div>
            <h2 className="flex items-center gap-1.5 text-base font-semibold text-gray-900 dark:text-white">
              <Sparkles className="w-4 h-4 text-purple-600" /> AI 选题建议
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">
              让 AI 把当前想法打磨成 3 个具体可研究、可发表的选题（基于论文库相关文献）
            </p>
          </div>
          <button
            onClick={() => runAi('generate_topics', title)}
            disabled={aiRunning || !title.trim()}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white text-sm rounded-lg transition-colors"
          >
            {aiRunning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
            {project.generated_topics?.length ? '重新生成' : '生成选题建议'}
          </button>
        </div>

        {aiRunning && (
          <div className="flex items-center gap-2 text-sm text-purple-600 dark:text-purple-400 py-6 justify-center">
            <Loader2 className="w-5 h-5 animate-spin" /> AI 正在生成选题（约 30 秒）…
          </div>
        )}

        {!aiRunning && project.generated_topics && project.generated_topics.length > 0 && (
          <div className="space-y-3">
            {project.generated_topics.map((g, i) => (
              <div key={i} className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:border-purple-300 transition-colors">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1">
                    <div className="font-medium text-gray-900 dark:text-white text-sm leading-snug">{g.title}</div>
                    {g.research_questions?.length > 0 && (
                      <ul className="mt-1.5 space-y-0.5">
                        {g.research_questions.map((q, qi) => (
                          <li key={qi} className="text-xs text-gray-500 dark:text-gray-400">• {q}</li>
                        ))}
                      </ul>
                    )}
                    {g.hypothesis && (
                      <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-400">
                        <span className="font-medium">假设：</span>{g.hypothesis}
                      </p>
                    )}
                    {g.why && (
                      <p className="mt-1 text-xs text-gray-400">
                        <span className="font-medium">为什么值得做：</span>{g.why}
                      </p>
                    )}
                  </div>
                  <button
                    onClick={() => applyTopic(g)}
                    className="inline-flex items-center gap-1 text-xs px-3 py-1.5 bg-primary-600 hover:bg-primary-700 text-white rounded-md shrink-0 transition-colors"
                  >
                    {adopted ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Check className="w-3.5 h-3.5" />}
                    采用
                  </button>
                </div>
              </div>
            ))}
            {adopted && (
              <p className="text-xs text-green-600 dark:text-green-400 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" /> 已应用到项目，点下方「下一步：选题验证」继续
              </p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
