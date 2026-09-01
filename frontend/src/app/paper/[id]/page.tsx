'use client';

import dynamic from 'next/dynamic';
import React, { useState, useEffect, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Layout from '@/components/Layout';
import { papersApi, producerApi, getLastModel, rememberModel, ApiError } from '@/lib/api';
import { PaperDetailResponse, PaperReferencesResponse, PaperCitedByResponse } from '@/types/paper';
import { Loader2, ExternalLink, Calendar, TrendingUp, ArrowLeft, AlertCircle, Sparkles, Bot, Brain, ChevronDown, FileText, Target, Copy, Check, Bookmark, Pin, MessageSquare, Download } from 'lucide-react';
import Link from 'next/link';
const MarkdownRenderer = dynamic(() => import('@/components/MarkdownRenderer'), {
  ssr: false,
});
import { useLanguage } from '@/contexts/LanguageContext';
import { usePageTitle } from '@/lib/usePageTitle';
import { getIssuePeriod, topicColors, downloadTextFile, getRefsShowBrowser, rememberRefsShowBrowser } from '@/lib/utils';
import { useBookmarks } from '@/lib/useBookmarks';
import { usePins } from '@/lib/usePins';
import { useToast } from '@/components/Toast';
import { openAssistant } from '@/lib/assistantBus';

export default function PaperDetailPage() {
  const { t } = useLanguage();
  const params = useParams();
  const router = useRouter();
  const [paper, setPaper] = useState<PaperDetailResponse | null>(null);
  usePageTitle(paper?.title);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [aiAnalysis, setAiAnalysis] = useState<string | null>(null);
  const [aiAnalyzing, setAiAnalyzing] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  // —— P1-8c：结构化分析卡片 + 与我的选题相关性 ——
  const [analysisSections, setAnalysisSections] = useState<Array<{ title: string; content: string }>>([]);
  const [relevance, setRelevance] = useState<{ score: number | null; reason: string; ai_used: boolean } | null>(null);
  const [relevanceLoading, setRelevanceLoading] = useState(false);

  // —— P2-11a：引用导出 ——
  const [citationBusy, setCitationBusy] = useState(false);
  const [copiedFormat, setCopiedFormat] = useState<string | null>(null);

  // —— 参考文献列表（懒加载：首次展开时拉取，paper_references 表未抓取过则为空）——
  const [refsOpen, setRefsOpen] = useState(false);
  const [refsLoading, setRefsLoading] = useState(false);
  const [refsError, setRefsError] = useState(false);
  const [refsData, setRefsData] = useState<PaperReferencesResponse | null>(null);
  // 被引查询：库内哪些论文的参考文献引用了本文（随参考文献一并懒加载，失败静默）
  const [citedBy, setCitedBy] = useState<PaperCitedByResponse | null>(null);
  // 「一键抓取本篇参考文献」：复用系统页 references 后台任务，完成后自动刷新列表
  const [refsCrawling, setRefsCrawling] = useState(false);
  const refsCrawlTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // 抓取时是否显示浏览器（localStorage 持久化，与系统页-爬虫同一份偏好）
  const [refsShowBrowser, setRefsShowBrowser] = useState(false);
  useEffect(() => { setRefsShowBrowser(getRefsShowBrowser()); }, []);

  const loadRefs = async () => {
    if (refsLoading || refsData) return;
    setRefsLoading(true);
    setRefsError(false);
    try {
      const [refs, cited] = await Promise.all([
        papersApi.getPaperReferences(params.id as string),
        papersApi.getPaperCitedBy(params.id as string).catch(() => null),
      ]);
      setRefsData(refs);
      if (cited) setCitedBy(cited);
    } catch {
      setRefsError(true);
    } finally {
      setRefsLoading(false);
    }
  };

  // 用 ref 保存最新 loadRefs，避免 effect/回调里的闭包过期问题
  const loadRefsRef = useRef(loadRefs);
  loadRefsRef.current = loadRefs;

  const handleCrawlRefs = async () => {
    if (!paper || refsCrawling) return;
    setRefsCrawling(true);
    setRefsError(false);
    try {
      // 只传标题走默认检索定位：库里存的 CNKI 链接带会话令牌（v=...），过期后直接打开会失败
      const res = await papersApi.startReferencesCrawl({ paper_title: paper.title, show_browser: refsShowBrowser });
      if (res.status === 'already_running') {
        toast(t('pd.refsCrawlAlready'), 'info');
      }
      let attempts = 0;
      const tick = async () => {
        attempts += 1;
        if (attempts > 100) {  // 上限 5 分钟，防止无限轮询
          setRefsCrawling(false);
          return;
        }
        try {
          const info = await papersApi.getReferencesStatus();
          if (!info.running) {
            setRefsCrawling(false);
            if (info.stopped_by_user) {
              toast(t('pd.refsCrawlStopped'), 'info');
            } else {
              setRefsData(null);
              setCitedBy(null);
              setRefsOpen(true);
              toast(t('pd.refsCrawlDone'), 'success');
            }
            return;
          }
        } catch { /* 忽略单次轮询失败 */ }
        refsCrawlTimerRef.current = setTimeout(tick, 3000);
      };
      refsCrawlTimerRef.current = setTimeout(tick, 3000);
    } catch {
      toast(t('pd.refsCrawlFailed'), 'error');
      setRefsCrawling(false);
    }
  };

  // 爬取完成/展开时：refsData 为空且未在加载 → 拉取（含爬取完成后的强制刷新路径）
  useEffect(() => {
    if (refsOpen && !refsData && !refsLoading && !refsError) void loadRefsRef.current();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refsOpen, refsData, refsError]);

  const analysisTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // —— 阅读进度条 ——
  const [readProgress, setReadProgress] = useState(0);
  useEffect(() => {
    const onScroll = () => {
      const el = document.documentElement;
      const total = el.scrollHeight - el.clientHeight;
      setReadProgress(total > 0 ? Math.min((el.scrollTop / total) * 100, 100) : 0);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  // —— 模型选择（OpenAI 兼容）——
  const [availableModels, setAvailableModels] = useState<Array<{ id: string; label: string; available: boolean }>>([]);
  const [analysisModel, setAnalysisModel] = useState('');
  const [showAnalysisModelSelect, setShowAnalysisModelSelect] = useState(false);

  // —— 收藏/置顶 ——
  const { has: isBookmarkedNow, toggle: toggleBookmarkState } = useBookmarks();
  const { has: isPinnedNow, toggle: togglePinState } = usePins();
  const { toast } = useToast();

  const providerLabel = (provider?: string) => {
    if (provider === 'zhipu') return '智谱';
    if (provider === 'siliconflow') return '硅基流动';
    if (provider === 'openai') return 'OpenAI';
    return provider || '未知';
  };
  const bareModelName = (name: string) => {
    const slashIndex = name.indexOf('/');
    return slashIndex >= 0 ? name.slice(slashIndex + 1) : name;
  };

  useEffect(() => {
    papersApi.getAIAnalysisModels()
      .then(res => {
        const list = res.models
          .filter(m => m.available)
          .map(m => ({
            id: m.name,
            label: `${providerLabel(m.provider)} ${bareModelName(m.name)}`,
            available: m.available,
          }));
        setAvailableModels(list);
        const lastAnalysis = getLastModel('paper_analysis');
        if (lastAnalysis && list.some(m => m.id === lastAnalysis)) setAnalysisModel(lastAnalysis);
      })
      .catch(() => setAvailableModels([]));
  }, []);

  useEffect(() => {
    return () => {
      if (analysisTimerRef.current) clearInterval(analysisTimerRef.current);
      if (refsCrawlTimerRef.current) clearTimeout(refsCrawlTimerRef.current);
    };
  }, []);

  // 切换论文时重置参考文献/被引状态，避免展示上一篇文章的数据
  useEffect(() => {
    setRefsOpen(false);
    setRefsData(null);
    setRefsError(false);
    setCitedBy(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params.id]);

  useEffect(() => {
    if (!params.id) return;
    // 竞态保护：id 切换/卸载时丢弃过期响应（对齐 usePapersPage 的 cancelled 模式）
    let cancelled = false;

    const fetchPaper = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await papersApi.getPaperById(params.id as string);
        if (!cancelled) setPaper(response);
      } catch (error: any) {
        console.error('Error fetching paper:', error);
        const errMsg = error instanceof ApiError ? (error.detail || error.message) : error.message || '加载论文详情失败';
        if (!cancelled) setError(errMsg);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchPaper();
    // P1-10：上报阅读历史（幂等，失败不影响页面）
    import('@/lib/api').then(({ personalApi }) =>
      personalApi.recordReading(params.id as string).catch(() => {})
    );

    return () => {
      cancelled = true;
    };
  }, [params.id]);

  useEffect(() => {
    if (!paper) return;
    const loadAnalysis = async () => {
      let result;
      try {
        result = await papersApi.getLatestAnalysis(paper.id);
      } catch {
        return false;
      }
      if (result.status === "pending") {
        setAiAnalyzing(true);
        return true;
      } else if (result.status === "success" && result.analysis) {
        setAiAnalysis(result.analysis);
        setAiAnalyzing(false);
      } else if (result.status === "failed") {
        setAiAnalysis(result.analysis);
        setAiError(t('pd.lastFailed'));
        setAiAnalyzing(false);
      }
      return false;
    };

    let timer: ReturnType<typeof setInterval>;
    const start = async () => {
      const isPending = await loadAnalysis();
      if (isPending) {
        timer = setInterval(async () => {
          const stillPending = await loadAnalysis();
          if (!stillPending) {
            clearInterval(timer);
          }
        }, 2000);
      }
    };
    start();
    return () => clearInterval(timer);
  }, [paper]);

  // P1-8c：把 AI 分析文本解析为结构化卡片（背景/方法/发现/意义），解析不出则回退整文渲染
  useEffect(() => {
    if (!aiAnalysis) {
      setAnalysisSections([]);
      return;
    }
    const lines = aiAnalysis.split('\n');
    const headingIdx: Array<{ idx: number; title: string }> = [];
    lines.forEach((line, i) => {
      const m = line.match(/^\s*(?:\d+[.、]\s*)?\*\*(.{2,20})\*\*\s*$/) || line.match(/^#{2,3}\s+(.{2,24})\s*$/);
      if (m && !line.includes('：') ) headingIdx.push({ idx: i, title: m[1].replace(/^\d+[.、]\s*/, '') });
    });
    if (headingIdx.length >= 2) {
      const sections = headingIdx.map((h, i) => {
        const end = i + 1 < headingIdx.length ? headingIdx[i + 1].idx : lines.length;
        return { title: h.title, content: lines.slice(h.idx + 1, end).join('\n').trim() };
      }).filter((s) => s.content);
      setAnalysisSections(sections);
    } else {
      setAnalysisSections([]);
    }
  }, [aiAnalysis]);

  // P1-8c：与我的选题相关性（有选题时自动加载）
  useEffect(() => {
    if (!paper) return;
    let cancelled = false;
    papersApi.getTopicRelevance(paper.id)
      .then((res) => { if (!cancelled) setRelevance(res); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, [paper]);

  // P2-11a：引用导出（GB/T 7714 / BibTeX）
  const buildCitationSnapshot = () => ({
    id: paper!.id,
    title: paper!.title,
    authors: paper!.authors || [],
    journal_name: paper!.journal_name,
    journal_issue: paper!.journal_issue,
    published_at: paper!.published_at,
  });

  const handleExportCitation = async (format: 'gbt7714' | 'bibtex') => {
    if (!paper || citationBusy) return;
    setCitationBusy(true);
    try {
      const res = await producerApi.exportCitations([buildCitationSnapshot()], format);
      downloadTextFile(
        `citation_${format}.${format === 'bibtex' ? 'bib' : 'txt'}`,
        res.citations.join('\n\n'),
      );
    } catch { /* ignore */ }
    setCitationBusy(false);
  };

  const handleCopyCitation = async (format: 'gbt7714' | 'bibtex') => {
    if (!paper || citationBusy) return;
    setCitationBusy(true);
    try {
      const res = await producerApi.exportCitations([buildCitationSnapshot()], format);
      await navigator.clipboard.writeText(res.citations.join('\n\n'));
      setCopiedFormat(format);
      setTimeout(() => setCopiedFormat(null), 1500);
    } catch { /* ignore */ }
    setCitationBusy(false);
  };

  const handleToggleBookmark = async () => {
    if (!paper) return;
    try {
      const res = await toggleBookmarkState(paper.id);
      toast(t(res ? 'paper.bookmarkMsg' : 'paper.unbookmarkMsg'), 'success');
    } catch {
      toast(t('paper.bookmarkFailed'), 'error');
    }
  };

  const handleTogglePin = async () => {
    if (!paper) return;
    try {
      const res = await togglePinState(paper.id);
      if (res.limited) {
        toast(t('paper.pinLimit'), 'warning');
      } else {
        toast(t(res.pinned ? 'paper.pinnedMsg' : 'paper.unpinnedMsg'), 'success');
      }
    } catch {
      toast(t('paper.pinFailed'), 'error');
    }
  };

  const handleAskAi = () => {
    if (!paper) return;
    openAssistant({ paperId: paper.id, contextText: paper.title, autoPrompt: '请帮我深入分析这篇论文的贡献与不足' });
  };

  /** pending 轮询兜底：流式入口被占用（已有后台分析）或历史 pending 时复用。 */
  const startPendingPoll = () => {
    if (analysisTimerRef.current) clearInterval(analysisTimerRef.current);
    let attempts = 0;
    analysisTimerRef.current = setInterval(async () => {
      attempts += 1;
      if (attempts > 90) {  // 上限3分钟，防止无限轮询
        clearInterval(analysisTimerRef.current!);
        analysisTimerRef.current = null;
        setAiError(t('pd.timeout'));
        setAiAnalyzing(false);
        return;
      }
      try {
        const latest = await papersApi.getLatestAnalysis(params.id as string);
        if (latest.status === "success" && latest.analysis) {
          setAiAnalysis(latest.analysis);
          setAiAnalyzing(false);
          clearInterval(analysisTimerRef.current!);
          analysisTimerRef.current = null;
        } else if (latest.status === "failed") {
          setAiAnalysis(latest.analysis);
          setAiError(t('pd.failed'));
          setAiAnalyzing(false);
          clearInterval(analysisTimerRef.current!);
          analysisTimerRef.current = null;
        }
      } catch {}
    }, 2000);
  };

  // 流式分析：正文逐 token 渲染；后端返回 JSON pending（已有后台分析在跑）时退回轮询
  const analyzePaper = async () => {
    if (!params.id) return;
    setAiAnalyzing(true);
    setAiError(null);
    setAiAnalysis(null);
    await papersApi.streamPaperAnalysis(
      params.id as string,
      {
        onContent: (delta) => setAiAnalysis((prev) => (prev || '') + delta),
        onError: (msg) => {
          setAiError(msg);
          setAiAnalyzing(false);
        },
        onDone: (result) => {
          if (result?.status === 'pending') {
            startPendingPoll();
            return;
          }
          setAiAnalyzing(false);
          if (result?.analysis) setAiAnalysis(result.analysis);
        },
      },
      analysisModel || undefined,
    );
  };

  if (loading) {
    return (
      <Layout>
        <div className="mb-4 h-5 w-24 bg-gray-200 dark:bg-gray-700 rounded animate-pulse" />
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 sm:p-8 mb-4 sm:mb-6 animate-pulse">
          <div className="h-7 sm:h-8 bg-gray-200 dark:bg-gray-700 rounded w-3/4 mb-3" />
          <div className="flex gap-2 mb-4">
            <div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-16" />
            <div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-20" />
            <div className="h-6 bg-gray-200 dark:bg-gray-700 rounded w-24" />
          </div>
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-full mb-2" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-5/6 mb-2" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-2/3 mb-6" />
          <div className="h-40 bg-gray-100 dark:bg-gray-700/50 rounded-lg mb-4" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-full mb-2" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-1/2" />
        </div>
      </Layout>
    );
  }

  if (error) {
    return (
      <Layout>
        <div className="text-center py-12">
          <AlertCircle className="w-12 h-12 text-red-400 mx-auto mb-4" />
          <p className="text-red-600 font-medium mb-2">{t('pd.loadFailed')}</p>
          <p className="text-gray-500 dark:text-gray-400 text-sm mb-4">{error}</p>
          <Link href="/" className="text-primary-600 hover:underline mt-4 inline-block">
            {t('nav.home')}
          </Link>
        </div>
      </Layout>
    );
  }

  if (!paper) {
    return (
      <Layout>
        <div className="text-center py-12">
          <p className="text-gray-600 dark:text-gray-400">{t('paper.notFound')}</p>
          <Link href="/" className="text-primary-600 hover:underline mt-4 inline-block">
            {t('nav.home')}
          </Link>
        </div>
      </Layout>
    );
  }

  const score = paper.scores?.final_score || 0;

  return (
    <Layout>
      {/* 阅读进度条 */}
      <div className="fixed top-0 left-0 right-0 z-50 h-1 bg-gray-200/50 dark:bg-gray-700/50">
        <div
          className="h-full bg-primary-500 transition-[width] duration-150 ease-out"
          style={{ width: `${readProgress}%` }}
        />
      </div>

      <div className="mb-4 sm:mb-6">
        <Link href="/" className="flex items-center gap-2 text-gray-600 dark:text-gray-400 hover:text-primary-600 transition-colors">
          <ArrowLeft className="w-5 h-5" />
          <span className="text-sm sm:text-base">{t('nav.backHome')}</span>
        </Link>
      </div>

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 sm:p-8 mb-4 sm:mb-6">
        <div className="flex justify-between items-start gap-2 mb-3 sm:mb-4">
          <h1 className="text-lg sm:text-2xl font-bold text-gray-900 dark:text-white flex-1">
            {paper.title}
          </h1>
          <div className="flex items-center gap-1.5 shrink-0">
            {/* 收藏 */}
            <button
              onClick={handleToggleBookmark}
              className={`p-1.5 rounded transition-colors ${paper && isBookmarkedNow(paper.id) ? 'text-yellow-500 hover:text-yellow-600' : 'text-gray-400 hover:text-yellow-500'}`}
              title={paper && isBookmarkedNow(paper.id) ? t('paper.unbookmarkMsg') : t('paper.bookmarkMsg')}
            >
              <Bookmark className="w-4.5 h-4.5 sm:w-5 sm:h-5" fill={paper && isBookmarkedNow(paper.id) ? 'currentColor' : 'none'} />
            </button>
            {/* 置顶 */}
            <button
              onClick={handleTogglePin}
              className={`p-1.5 rounded transition-colors ${paper && isPinnedNow(paper.id) ? 'text-blue-500 hover:text-blue-600' : 'text-gray-400 hover:text-blue-500'}`}
              title={paper && isPinnedNow(paper.id) ? t('paper.unpinnedMsg') : t('paper.pinnedMsg')}
            >
              <Pin className="w-4.5 h-4.5 sm:w-5 sm:h-5" fill={paper && isPinnedNow(paper.id) ? 'currentColor' : 'none'} />
            </button>
            {/* AI 追问 */}
            <button
              onClick={handleAskAi}
              className="flex items-center gap-1 text-xs px-2 py-1.5 rounded bg-primary-50 dark:bg-primary-900/30 text-primary-600 hover:bg-primary-100 dark:hover:bg-primary-900/50 transition-colors"
              title="向 AI 助手追问此论文"
            >
              <MessageSquare className="w-3.5 h-3.5" />
              <span className="hidden md:inline">追问</span>
            </button>
            {/* P2-11a：引用导出 */}
            <button
              onClick={() => handleCopyCitation('bibtex')}
              disabled={citationBusy}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:border-primary-400 transition-colors disabled:opacity-50"
              title="复制 BibTeX"
            >
              {copiedFormat === 'bibtex' ? <Check className="w-3.5 h-3.5 text-green-500" /> : <Copy className="w-3.5 h-3.5" />}
              <span className="hidden md:inline">BibTeX</span>
            </button>
            <button
              onClick={() => handleExportCitation('gbt7714')}
              disabled={citationBusy}
              className="flex items-center gap-1 text-xs px-2 py-1 rounded border border-gray-200 dark:border-gray-600 text-gray-600 dark:text-gray-300 hover:border-primary-400 transition-colors disabled:opacity-50"
              title="下载 GB/T 7714 引用"
            >
              <FileText className="w-3.5 h-3.5" />
              <span className="hidden md:inline">GB/T 7714</span>
            </button>
            <a
              href={paper.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary-600 hover:text-primary-700"
            >
              <ExternalLink className="w-5 h-5 sm:w-6 sm:h-6" />
            </a>
          </div>
        </div>

        <div className="flex flex-wrap gap-1.5 sm:gap-2 mb-3 sm:mb-4">
          {paper.features?.topic && paper.features.topic !== 'Other' && (
            <span className={`text-xs sm:text-sm font-medium px-2 sm:px-3 py-0.5 sm:py-1 rounded ${topicColors[paper.features.topic] || 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200'}`}>
              {paper.features.topic}
            </span>
          )}
          {paper.economics_subfield && (
            <span className="bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 dark:text-indigo-300 text-xs sm:text-sm px-2 sm:px-3 py-0.5 sm:py-1 rounded">
              {paper.economics_subfield}
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-2 sm:gap-6 text-xs sm:text-sm text-gray-600 dark:text-gray-400 mb-4 sm:mb-6">
          <span className="flex items-center gap-1">
            <Calendar className="w-3.5 h-3.5 sm:w-4 sm:h-4" />
            {getIssuePeriod(paper.doi, paper.published_at, paper.journal_issue) || 'Unknown'}
          </span>
          {paper.discipline && (
            <span className="bg-purple-50 dark:bg-purple-900/30 text-purple-700 px-2 sm:px-3 py-0.5 sm:py-1 rounded">
              {paper.discipline}
            </span>
          )}
          {paper.economics_subfield && (
            <span className="bg-indigo-50 dark:bg-indigo-900/30 text-indigo-700 px-2 sm:px-3 py-0.5 sm:py-1 rounded hidden sm:inline">
              {paper.economics_subfield}
            </span>
          )}
          <span className="bg-gray-100 dark:bg-gray-700 px-2 sm:px-3 py-0.5 sm:py-1 rounded">
            {paper.source}
          </span>
          {/* venue 与 journal_name 相同（CNKI 论文两字段都是刊名）时只显示 journal_name，避免重复 */}
          {paper.venue && paper.venue !== paper.journal_name && (
            <span className="bg-primary-50 dark:bg-primary-900/30 text-primary-700 px-2 sm:px-3 py-0.5 sm:py-1 rounded hidden sm:inline">
              {paper.venue}
            </span>
          )}
          {paper.journal_name && (
            <span className="bg-blue-50 dark:bg-blue-900/30 text-blue-700 px-2 sm:px-3 py-0.5 sm:py-1 rounded truncate max-w-[120px] sm:max-w-none">
              {paper.journal_name}
            </span>
          )}
        </div>

        {paper.doi && (
          <div className="mb-4 sm:mb-6">
            <h2 className="text-base sm:text-lg font-semibold text-gray-900 dark:text-white mb-1.5 sm:mb-2">DOI</h2>
            <a
              href={paper.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary-600 hover:underline text-xs sm:text-sm break-all"
            >
              {paper.doi} &rarr;
            </a>
          </div>
        )}

        {paper.authors && paper.authors.length > 0 && (
          <div className="mb-4 sm:mb-6">
            <h2 className="text-base sm:text-lg font-semibold text-gray-900 dark:text-white mb-1.5 sm:mb-2">{t('paper.authors')}</h2>
            <div className="flex flex-wrap gap-1.5 sm:gap-2">
              {paper.authors.map((author, index) => (
                <Link
                  key={index}
                  href={`/author/${encodeURIComponent(author)}`}
                  className="bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 text-xs sm:text-sm px-2 sm:px-3 py-0.5 sm:py-1 rounded hover:bg-primary-100 hover:text-primary-700 dark:hover:bg-primary-900/30 dark:hover:text-primary-300 transition-colors"
                >
                  {author}
                </Link>
              ))}
            </div>
          </div>
        )}

        {paper.keywords_cn && paper.keywords_cn.length > 0 && (
          <div className="mb-4 sm:mb-6">
            <h2 className="text-base sm:text-lg font-semibold text-gray-900 dark:text-white mb-1.5 sm:mb-2">{t('paper.keywords')}</h2>
            <div className="flex flex-wrap gap-1.5 sm:gap-2">
              {paper.keywords_cn.map((keyword, index) => (
                <button
                  key={index}
                  onClick={() => router.push(`/search?search=${encodeURIComponent(keyword)}&search_field=keyword`)}
                  className="bg-primary-100 text-primary-800 text-xs sm:text-sm px-2 sm:px-3 py-0.5 sm:py-1 rounded-full hover:bg-primary-200 transition-colors cursor-pointer"
                >
                  {keyword}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="mb-4 sm:mb-6">
          <h2 className="text-base sm:text-lg font-semibold text-gray-900 dark:text-white mb-1.5 sm:mb-2">{t('paper.abstract')}</h2>
          <p className="text-gray-700 dark:text-gray-300 leading-relaxed text-sm sm:text-base">
            {paper.features?.summary || paper.abstract}
          </p>
        </div>

        {paper && (
          <div className="mb-4 sm:mb-6 border border-gray-200 dark:border-gray-700 rounded-lg">
            <button
              onClick={() => { const next = !refsOpen; setRefsOpen(next); if (next) void loadRefs(); }}
              className="w-full flex items-center justify-between px-3 sm:px-4 py-2.5 text-left gap-2"
            >
              <span className="text-sm sm:text-base font-semibold text-gray-900 dark:text-white flex items-center gap-2 min-w-0">
                {t('pd.refsSection')}{refsData ? ` (${refsData.total})` : ''}
                {citedBy && citedBy.total > 0 && (
                  <span className="shrink-0 text-[10px] sm:text-[11px] font-normal px-1.5 py-0.5 rounded bg-teal-50 dark:bg-teal-900/30 text-teal-600 dark:text-teal-300">
                    {t('pd.citedByCount', { n: citedBy.total })}
                  </span>
                )}
              </span>
              <span className="text-xs text-primary-600 dark:text-primary-400 shrink-0 ml-2">
                {refsOpen ? t('pd.refsHide') : t('pd.refsShow')}
              </span>
            </button>
            {refsOpen && (
              <div className="px-3 sm:px-4 pb-3 sm:pb-4 border-t border-gray-100 dark:border-gray-800 pt-3">
                {refsLoading && <div className="text-sm text-gray-400 py-2"><Loader2 className="w-4 h-4 animate-spin inline mr-1" />…</div>}
                {!refsLoading && refsError && (
                  <div className="text-sm text-red-500 py-2 flex items-center gap-2 flex-wrap">
                    {t('pd.refsLoadFailed')}
                    <button onClick={() => setRefsError(false)} className="text-xs text-primary-600 hover:underline">
                      {t('pd.refsRetry')}
                    </button>
                  </div>
                )}
                {!refsLoading && refsData && refsData.total === 0 && (
                  <div className="text-xs sm:text-sm text-gray-400 py-2">
                    {t('pd.refsEmpty')}
                    <span className="block text-[11px] text-gray-300 dark:text-gray-500 mt-0.5">{t('pd.refsEmptyHint')}</span>
                    <div className="mt-2 flex items-center gap-3 flex-wrap">
                      <button
                        onClick={handleCrawlRefs}
                        disabled={refsCrawling}
                        className="flex items-center gap-1.5 text-xs px-3 py-1.5 rounded-md bg-primary-50 dark:bg-primary-900/30 text-primary-600 dark:text-primary-300 hover:bg-primary-100 dark:hover:bg-primary-900/50 transition-colors disabled:opacity-60"
                      >
                        {refsCrawling
                          ? <><Loader2 className="w-3.5 h-3.5 animate-spin" />{t('pd.refsCrawling')}</>
                          : <><Download className="w-3.5 h-3.5" />{t('pd.refsCrawlBtn')}</>}
                      </button>
                      <label className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400 cursor-pointer select-none">
                        <input
                          type="checkbox"
                          checked={refsShowBrowser}
                          onChange={e => { setRefsShowBrowser(e.target.checked); rememberRefsShowBrowser(e.target.checked); }}
                          disabled={refsCrawling}
                          className="w-3.5 h-3.5 accent-primary-600 disabled:opacity-50"
                        />
                        {t('sys.kwShowBrowser')}
                      </label>
                    </div>
                  </div>
                )}
                {!refsLoading && refsData && refsData.total > 0 && (
                  <ol className="space-y-1.5 max-h-96 overflow-y-auto">
                    {refsData.references.map((ref) => (
                      <li key={ref.ref_index} className="text-xs sm:text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
                        <span className="text-gray-400 mr-1">[{ref.ref_index}]</span>
                        {ref.matched_paper_id ? (
                          <Link href={`/paper/${ref.matched_paper_id}`} className="hover:text-primary-600 hover:underline break-all" title={ref.matched_paper_title || undefined}>
                            {ref.raw_text}
                          </Link>
                        ) : ref.ref_url ? (
                          <a href={ref.ref_url} target="_blank" rel="noopener noreferrer" className="hover:text-primary-600 hover:underline break-all">
                            {ref.raw_text}
                          </a>
                        ) : (
                          <span className="break-all">{ref.raw_text}</span>
                        )}
                      </li>
                    ))}
                  </ol>
                )}
                {citedBy && citedBy.total > 0 && (
                  <div className="mt-3 pt-2 border-t border-gray-100 dark:border-gray-800">
                    <div className="text-[11px] text-gray-400 mb-1">{t('pd.citedBy')}</div>
                    <div className="space-y-1">
                      {citedBy.citing_papers.map((p) => (
                        <Link key={p.id} href={`/paper/${p.id}`} className="block text-xs sm:text-sm text-gray-700 dark:text-gray-300 hover:text-primary-600 hover:underline truncate">
                          {p.title}
                        </Link>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        <div className="border-t pt-4 sm:pt-6">
          <div className="grid grid-cols-3 gap-2 sm:gap-4">
            <div className="bg-green-50 dark:bg-green-900/30 p-2 sm:p-4 rounded-lg">
              <div className="text-xs sm:text-sm text-gray-600 dark:text-gray-400 mb-0.5 sm:mb-1">Recency</div>
              <div className="text-base sm:text-lg font-bold text-gray-900 dark:text-white">
                {((paper.scores?.recency_score || 0) * 100).toFixed(0)}%
              </div>
            </div>
            <div className="bg-blue-50 dark:bg-blue-900/30 p-2 sm:p-4 rounded-lg">
              <div className="text-xs sm:text-sm text-gray-600 dark:text-gray-400 mb-0.5 sm:mb-1">Venue</div>
              <div className="text-base sm:text-lg font-bold text-gray-900 dark:text-white">
                {((paper.scores?.venue_score || 0) * 100).toFixed(0)}%
              </div>
            </div>
            <div className="bg-purple-50 dark:bg-purple-900/30 p-2 sm:p-4 rounded-lg">
              <div className="text-xs sm:text-sm text-gray-600 dark:text-gray-400 mb-0.5 sm:mb-1">Trend</div>
              <div className="text-base sm:text-lg font-bold text-gray-900 dark:text-white">
                {((paper.scores?.trend_score || 0) * 100).toFixed(0)}%
              </div>
            </div>
          </div>

        </div>
      </div>

      {paper.similar_papers && paper.similar_papers.length > 0 && (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 sm:p-8 mb-6">
          <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">{t('paper.similarPapers')}</h2>
          <div className="space-y-3">
            {paper.similar_papers.map((similar) => (
              <Link
                key={similar.id}
                href={`/paper/${similar.id}`}
                className="block border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:shadow-md transition-shadow"
              >
                <div className="flex justify-between items-start">
                  <div className="flex-1">
                    <h3 className="font-semibold text-gray-900 dark:text-white mb-2">
                      {similar.title}
                    </h3>
                    <div className="flex flex-wrap gap-1.5">
                      {similar.topic && similar.topic !== 'Other' && (
                        <span className={`text-xs font-medium px-2 py-0.5 rounded ${topicColors[similar.topic] || 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200'}`}>
                          {similar.topic}
                        </span>
                      )}
                      {similar.keywords_cn?.slice(0, 5).map((keyword, index) => (
                        <span
                          key={index}
                          className="bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 text-xs px-2 py-0.5 rounded"
                        >
                          {keyword}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="text-sm text-gray-600 dark:text-gray-400 ml-4 shrink-0">
                    {t('paper.similarity')}: {similar.similarity_score != null ? `${(similar.similarity_score * 100).toFixed(0)}%` : '—'}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        </div>
      )}

      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-md p-4 sm:p-8 mb-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-primary-600" />
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">{t('pd.aiSection')}</h2>
            <div className="relative ml-1">
              <button
                onClick={() => setShowAnalysisModelSelect(!showAnalysisModelSelect)}
                className="flex items-center gap-1 px-2 py-1 text-xs text-gray-500 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                title={t('pd.selectModel')}
              >
                <Brain className="w-3.5 h-3.5" />
                {availableModels.find(m => m.id === analysisModel)?.label || t('pd.defaultModel')}
                <ChevronDown className="w-3 h-3" />
              </button>
              {showAnalysisModelSelect && (
                <div className="absolute left-0 top-8 z-20 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg shadow-lg py-1 min-w-[200px] max-h-72 overflow-y-auto">
                  <button
                    onClick={() => { setAnalysisModel(''); rememberModel('paper_analysis', null); setShowAnalysisModelSelect(false); }}
                    className={`w-full text-left px-3 py-1.5 text-xs hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors ${analysisModel === '' ? 'text-primary-600 font-medium' : 'text-gray-700 dark:text-gray-300'}`}
                  >
                    {t('pd.defaultModel')}
                  </button>
                  {availableModels.map(model => (
                    <button
                      key={model.id}
                      disabled={!model.available}
                      onClick={() => { setAnalysisModel(model.id); rememberModel('paper_analysis', model.id); setShowAnalysisModelSelect(false); }}
                      className={`w-full text-left px-3 py-1.5 text-xs hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${analysisModel === model.id ? 'text-primary-600 font-medium' : 'text-gray-700 dark:text-gray-300'}`}
                    >
                      {model.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
          {aiAnalysis && !aiAnalyzing && (
            <button
              onClick={analyzePaper}
              className="text-sm text-primary-600 hover:underline"
            >
              {t('pd.reanalyze')}
            </button>
          )}
        </div>

        {aiAnalyzing && !aiAnalysis && (
          <div className="flex items-center gap-3 py-8 justify-center">
            <Loader2 className="w-5 h-5 animate-spin text-primary-600" />
            <span className="text-gray-500 dark:text-gray-400">{t('pd.analyzing')}</span>
          </div>
        )}

        {aiError && !aiAnalyzing && (
          <div className="bg-red-50 dark:bg-red-900/30 border border-red-200 rounded-lg p-4 mb-4">
            <p className="text-red-700 text-sm">{aiError}</p>
            <button
              onClick={analyzePaper}
              className="mt-2 text-sm text-primary-600 hover:underline"
            >
              {t('pd.retryBtn')}
            </button>
          </div>
        )}

        {!aiAnalysis && !aiAnalyzing && !aiError && (
          <div className="text-center py-8">
            <Bot className="w-12 h-12 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500 dark:text-gray-400 text-sm mb-4">{t('pd.analyzeHint')}</p>
            <button
              onClick={analyzePaper}
              className="bg-primary-600 text-white px-6 py-2.5 rounded-lg hover:bg-primary-700 text-sm font-medium"
            >
              <Sparkles className="w-4 h-4 inline mr-2" />
              {t('pd.startAnalysis')}
            </button>
          </div>
        )}

        {aiAnalysis && (
          <div className="text-sm">
            {/* P1-8c：结构化卡片（背景/方法/发现/意义），解析失败回退整文；流式生成中实时渲染 */}
            {analysisSections.length >= 2 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {analysisSections.map((section, i) => (
                  <div
                    key={i}
                    className={`border border-gray-200 dark:border-gray-700 rounded-lg p-4 ${
                      i === analysisSections.length - 1 ? 'md:col-span-2' : ''
                    }`}
                  >
                    <h4 className="flex items-center gap-1.5 font-semibold text-gray-900 dark:text-white mb-2 text-sm">
                      <Sparkles className="w-3.5 h-3.5 text-primary-500 shrink-0" />
                      {section.title}
                    </h4>
                    <MarkdownRenderer content={section.content} />
                  </div>
                ))}
              </div>
            ) : (
              <MarkdownRenderer content={aiAnalysis} />
            )}

            {/* 与我的选题相关性评分（P1-8c） */}
            {(relevanceLoading || relevance) && (
              <div className="mt-4 border-t pt-4">
                {relevanceLoading ? (
                  <div className="flex items-center gap-2 text-xs text-gray-400">
                    <Loader2 className="w-3.5 h-3.5 animate-spin" /> 正在评估与你的选题的相关性…
                  </div>
                ) : relevance?.score !== null && relevance ? (
                  <div className="bg-indigo-50 dark:bg-indigo-900/20 rounded-lg p-3 flex items-start gap-3">
                    <Target className="w-4 h-4 text-indigo-500 mt-0.5 shrink-0" />
                    <div className="text-sm">
                      <span className="font-semibold text-indigo-700 dark:text-indigo-300">
                        与我的选题相关性：{(relevance.score! * 100).toFixed(0)}%
                      </span>
                      {relevance.reason && (
                        <p className="text-xs text-gray-600 dark:text-gray-400 mt-0.5">{relevance.reason}</p>
                      )}
                    </div>
                  </div>
                ) : null}
              </div>
            )}
          </div>
        )}
      </div>
    </Layout>
  );
}