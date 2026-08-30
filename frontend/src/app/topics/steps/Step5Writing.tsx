'use client';

import React, { useState, useMemo } from 'react';
import dynamic from 'next/dynamic';
import { FileText, Loader2, Sparkles, Building2, Download, BookMarked, RefreshCw, MessageSquareText } from 'lucide-react';
import { workbenchApi, producerApi } from '@/lib/api';
import { openAssistant } from '@/lib/assistantBus';
import { downloadTextFile, downloadAsWord } from '@/lib/utils';
import type { StepProps } from './types';

const MarkdownRenderer = dynamic(() => import('@/components/MarkdownRenderer'), {
  ssr: false,
  loading: () => <div className="h-16 flex items-center justify-center text-gray-400 text-sm animate-pulse">加载中...</div>,
});

export default function Step5Writing({ project, onPatch, onRefresh, runAi, goStep }: StepProps) {
  const [journalBusy, setJournalBusy] = useState(false);
  const [proposalBusy, setProposalBusy] = useState(false);
  const [exportAllBusy, setExportAllBusy] = useState(false);

  const aiRunning = project.ai_pending === 'literature_review';
  const papers = project.papers || [];
  const insights = project.data_insights || null;

  const citations = useMemo(() => {
    const map: Record<number, { id: string; title?: string }> = {};
    papers.forEach((p, i) => { if (p.paper_id) map[i + 1] = { id: p.paper_id, title: p.title }; });
    return map;
  }, [papers]);

  const exportReview = (fmt: 'md' | 'doc') => {
    const content = project.literature_review || '';
    if (!content) return;
    const title = project.title || '文献综述';
    if (fmt === 'md') {
      downloadTextFile(`${title}_文献综述.md`, content, 'text/markdown;charset=utf-8');
    } else {
      downloadAsWord(`${title}_文献综述.doc`, title, content);
    }
  };

  const exportProposal = () => {
    if (!project.proposal) return;
    downloadTextFile(`${project.title}_立项书.md`, project.proposal, 'text/markdown;charset=utf-8');
  };

  const regenerateProposal = async () => {
    setProposalBusy(true);
    try {
      const res = await workbenchApi.generateProposal(project.id, project.validation_report || undefined);
      await onPatch({ proposal: res.proposal });
    } catch { /* ignore */ }
    finally { setProposalBusy(false); }
  };

  const suggestJournal = async () => {
    setJournalBusy(true);
    try {
      const res = await workbenchApi.suggestJournal(project.id);
      await onRefresh();
      if (!res.ai_used && res.suggestions.length > 0) {
        // 规则兜底时后端已存 journal_advice；无需额外处理
      }
    } catch { /* ignore */ }
    finally { setJournalBusy(false); }
  };

  const exportCitations = async (fmt: 'gbt7714' | 'bibtex') => {
    const snapshots = papers.map((p) => ({
      title: p.title,
      journal_name: p.journal,
      authors: p.authors || [],
      published_at: p.published_at,
    }));
    try {
      const res = await producerApi.exportCitations(snapshots, fmt);
      const text = res.citations.join('\n\n');
      const ext = fmt === 'bibtex' ? 'bib' : 'md';
      downloadTextFile(`${project.title}_参考文献.${ext}`, text, 'text/plain;charset=utf-8');
    } catch { /* ignore */ }
  };

  /** 一键导出全部：五步全流程成果打包为单份 markdown 研究资料包，可直接写作或投喂 AI。 */
  const exportAll = async () => {
    setExportAllBusy(true);
    try {
      const ev = project.validation_evidence;
      const parts: string[] = [];
      // 项目概览
      parts.push(`# 研究资料包：${project.title}\n`);
      const meta: string[] = [];
      meta.push(`- 来源：${project.source_type || 'manual'}${project.source_ref ? `（${project.source_ref}）` : ''}`);
      meta.push(`- 状态：${project.status || 'to_validate'}`);
      if (project.novelty != null) meta.push(`- 新颖性评分：${project.novelty}/10`);
      if (project.crowding) meta.push(`- 竞争拥挤度：${project.crowding}`);
      if (project.feasibility != null) meta.push(`- 可行性评分：${project.feasibility}/10`);
      if (ev?.validated_at) meta.push(`- 验证时间：${new Date(ev.validated_at).toLocaleString()}`);
      if (project.research_questions?.length) {
        meta.push('- 研究问题：');
        project.research_questions.forEach((q, i) => meta.push(`  ${i + 1}. ${q}`));
      }
      parts.push(`## 项目概览\n\n${meta.join('\n')}\n`);

      if (project.validation_report) parts.push(`# 一、选题验证报告\n\n${project.validation_report}\n`);
      if (project.overview) parts.push(`# 二、已有研究盘点\n\n${project.overview}\n`);

      if (papers.length > 0) {
        const lines = papers.map((p, i) => {
          const status = p.read_status === 'read' ? '已读' : p.read_status === 'reading' ? '精读中' : '待读';
          const note = p.note ? `｜笔记：${p.note}` : '';
          return `${i + 1}. 《${p.title}》（${p.journal || '未知'}）［${status}］${note}`;
        });
        parts.push(`# 三、项目文献集（${papers.length} 篇）\n\n${lines.join('\n')}\n`);
      }

      if (project.literature_review) parts.push(`# 四、文献脉络综述\n\n${project.literature_review}\n`);

      if (insights && (insights.data_sources?.length || insights.methods?.length || insights.advice || insights.my_notes)) {
        const di: string[] = [];
        if (insights.data_sources?.length) {
          di.push('## 数据来源');
          insights.data_sources.forEach((d) => di.push(`- ${d.name}${d.papers?.length ? `（用于 [${d.papers.join('][')}]）` : ''}${d.usage ? `：${d.usage}` : ''}`));
        }
        if (insights.methods?.length) {
          di.push('## 研究方法');
          insights.methods.forEach((m) => di.push(`- ${m.name}${m.papers?.length ? `（用于 [${m.papers.join('][')}]）` : ''}${m.note ? `：${m.note}` : ''}`));
        }
        if (insights.advice) di.push(`## 数据可得性建议\n\n${insights.advice}`);
        if (insights.my_notes) di.push(`## 我的补充\n\n${insights.my_notes}`);
        parts.push(`# 五、数据与方法\n\n${di.join('\n')}\n`);
      }

      if (project.proposal) parts.push(`# 六、选题立项书\n\n${project.proposal}\n`);
      if (project.journal_advice) parts.push(`# 七、投稿期刊适配\n\n${project.journal_advice}\n`);

      // 参考文献（GB/T 7714，来自论文库结构化数据）
      if (papers.length > 0) {
        try {
          const snapshots = papers.map((p) => ({
            title: p.title,
            journal_name: p.journal,
            authors: p.authors || [],
            published_at: p.published_at,
          }));
          const res = await producerApi.exportCitations(snapshots, 'gbt7714');
          if (res.citations?.length) {
            parts.push(`# 八、参考文献（GB/T 7714）\n\n${res.citations.join('\n\n')}\n`);
          }
        } catch { /* 引用服务失败不阻塞导出 */ }
      }

      downloadTextFile(`${project.title}_研究资料包.md`, parts.join('\n---\n\n'), 'text/markdown;charset=utf-8');
    } finally {
      setExportAllBusy(false);
    }
  };

  return (
    <div className="space-y-5">
      {/* 综述 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-purple-200 dark:border-purple-800 p-4 sm:p-6">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div>
            <h2 className="flex items-center gap-1.5 text-base font-semibold text-gray-900 dark:text-white">
              <BookMarked className="w-4 h-4 text-purple-600" /> 文献综述
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">
              基于项目文献集生成结构化综述（研究脉络/方法演进/争议/空白）
              <span className="text-gray-300 dark:text-gray-500">（与第 3 步的文献脉络为同一份内容，文献集完善后可在此重新生成并导出）</span>
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => runAi('literature_review')}
              disabled={aiRunning || papers.length === 0}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white text-xs rounded-lg transition-colors"
            >
              {aiRunning ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
              {project.literature_review ? '重新生成' : '生成综述'}
            </button>
            {project.literature_review && (
              <>
                <button onClick={() => exportReview('md')} className="inline-flex items-center gap-1 text-xs px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                  <Download className="w-3.5 h-3.5" /> Markdown
                </button>
                <button onClick={() => exportReview('doc')} className="inline-flex items-center gap-1 text-xs px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                  <FileText className="w-3.5 h-3.5" /> Word
                </button>
              </>
            )}
          </div>
        </div>
        {aiRunning && (
          <div className="flex items-center justify-center gap-2 text-sm text-purple-600 dark:text-purple-400 py-6">
            <Loader2 className="w-5 h-5 animate-spin" /> AI 正在生成综述（约 1 分钟）…
          </div>
        )}
        {!aiRunning && project.literature_review && (
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <MarkdownRenderer content={project.literature_review} citations={citations} />
          </div>
        )}
        {!aiRunning && !project.literature_review && (
          <p className="text-xs text-gray-400">点击「生成综述」，AI 将基于项目文献集撰写。文献集为空时可先到第 3 步添加。</p>
        )}
      </div>

      {/* 立项书 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-green-200 dark:border-green-800 p-4 sm:p-6">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div>
            <h2 className="flex items-center gap-1.5 text-base font-semibold text-gray-900 dark:text-white">
              <FileText className="w-4 h-4 text-green-600" /> 选题立项书
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">研究问题/数据来源建议/方法论/研究步骤/预期贡献</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => openAssistant({ contextText: project.title, autoPrompt: '请以期刊审稿人的视角审视这份选题立项书，指出方法论与贡献陈述上最容易被审稿人质疑的点' })}
              className="inline-flex items-center gap-1 text-xs px-3 py-1.5 border border-purple-200 dark:border-purple-800 text-purple-600 dark:text-purple-300 rounded-lg hover:bg-purple-50 dark:hover:bg-purple-900/20 transition-colors"
            >
              <Sparkles className="w-3.5 h-3.5" /> 问 AI
            </button>
            <button
              onClick={regenerateProposal}
              disabled={proposalBusy}
              className="inline-flex items-center gap-1 text-xs px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/50 disabled:opacity-50 transition-colors"
            >
              {proposalBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
              重新生成
            </button>
            {project.proposal && (
              <button onClick={exportProposal} className="inline-flex items-center gap-1 text-xs px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors">
                <Download className="w-3.5 h-3.5" /> 下载
              </button>
            )}
          </div>
        </div>
        {project.proposal ? (
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <MarkdownRenderer content={project.proposal} />
          </div>
        ) : (
          <div className="flex flex-col items-start gap-2">
            <p className="text-xs text-gray-400">立项书尚未生成。可直接生成，或先完成文献与数据步骤后再生成更完整。</p>
            <button
              onClick={regenerateProposal}
              disabled={proposalBusy}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-green-600 hover:bg-green-700 disabled:opacity-50 text-white text-xs rounded-lg transition-colors"
            >
              {proposalBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <FileText className="w-3.5 h-3.5" />}
              {proposalBusy ? '生成中…' : '生成立项书'}
            </button>
          </div>
        )}
      </div>

      {/* 模拟答辩（复用悬浮助手对话，流式输出有保障，可追问） */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-emerald-200 dark:border-emerald-800 p-4 sm:p-6">
        <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
          <h3 className="flex items-center gap-1.5 text-sm font-semibold text-gray-900 dark:text-white">
            <MessageSquareText className="w-4 h-4 text-emerald-600" /> 模拟答辩
            <span className="text-[11px] font-normal text-gray-400">模拟开题答辩 · 自述 + 质询 + 合议</span>
          </h3>
          <button
            onClick={() => openAssistant({
              contextText: project.title,
              autoPrompt: `请为选题「${project.title}」模拟一场开题答辩：
1. 以候选人身份自述研究设计（研究问题/方法/数据/创新点）；
2. 以评委身份质询 2 轮（新颖性差异、识别策略、数据可得性、竞争状况）；
3. 候选人逐一应答；
4. 最后合议裁定：新颖性/拥挤度/可行性/门控 4 项评分 + 结论（通过/修改后通过/不通过）+ 修改意见。
涉及论文库数据请先用工具检索并基于结果作答。`,
            })}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs rounded-lg transition-colors"
          >
            <MessageSquareText className="w-3.5 h-3.5" /> 在 AI 对话中模拟答辩
          </button>
        </div>
        <p className="text-xs text-gray-400">
          AI 对话流式输出，候选人/评委/合议由模型自主分角色呈现，支持模型选择与随时追问质询细节。
        </p>
      </div>

      {/* 期刊适配 + 引用 */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-blue-200 dark:border-blue-800 p-4 sm:p-6">
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div>
            <h2 className="flex items-center gap-1.5 text-base font-semibold text-gray-900 dark:text-white">
              <Building2 className="w-4 h-4 text-blue-600" /> 投稿期刊适配
            </h2>
            <p className="text-xs text-gray-400 mt-0.5">依据论文库期刊分布 + 期刊画像推荐 2-3 个投稿目标</p>
          </div>
          <button
            onClick={suggestJournal}
            disabled={journalBusy}
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-sm rounded-lg transition-colors"
          >
            {journalBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Building2 className="w-4 h-4" />}
            {project.journal_advice ? '重新适配' : '获取期刊建议'}
          </button>
        </div>
        {project.journal_advice ? (
          <div className="prose prose-sm dark:prose-invert max-w-none">
            <MarkdownRenderer content={project.journal_advice} />
          </div>
        ) : (
          <p className="text-xs text-gray-400">生成综述后获取期刊建议，推荐会更贴合。</p>
        )}

        {/* 引用导出 */}
        <div className="mt-4 pt-4 border-t border-gray-200 dark:border-gray-700">
          <h3 className="text-xs font-semibold text-gray-600 dark:text-gray-300 mb-2">引用导出（{papers.length} 篇）</h3>
          <div className="flex gap-2">
            <button
              onClick={() => exportCitations('gbt7714')}
              disabled={papers.length === 0}
              className="inline-flex items-center gap-1 text-xs px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700/50 disabled:opacity-50 transition-colors"
            >
              <Download className="w-3.5 h-3.5" /> GB/T 7714
            </button>
            <button
              onClick={() => exportCitations('bibtex')}
              disabled={papers.length === 0}
              className="inline-flex items-center gap-1 text-xs px-3 py-1.5 border border-gray-300 dark:border-gray-600 text-gray-600 dark:text-gray-300 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700/50 disabled:opacity-50 transition-colors"
            >
              <Download className="w-3.5 h-3.5" /> BibTeX
            </button>
            <button
              onClick={exportAll}
              disabled={exportAllBusy || (!project.validation_report && !project.overview && !project.literature_review && !project.proposal && !project.journal_advice && papers.length === 0)}
              title="把验证报告、盘点、文献集、综述、数据方法、立项书、期刊建议、参考文献打包为单份 markdown，可直接写作或投喂 AI"
              className="inline-flex items-center gap-1 text-xs px-3 py-1.5 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white rounded-md transition-colors"
            >
              {exportAllBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />} 一键导出全部
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
