'use client';

/** 全局 AI 悬浮助手的外部打开入口（事件总线）。
 * 任何组件（如论文卡片的「AI 分析」按钮）调用 openAssistant()，
 * 悬浮助手组件（AIAssistant）监听事件后打开窗口并注入指定上下文。
 */
export interface OpenAssistantOptions {
  /** 论文 id：传入后悬浮助手以该论文为上下文（后端会拉取论文信息） */
  paperId?: string;
  /** 补充上下文文本（如论文标题/检索词） */
  contextText?: string;
  /** 打开后自动发送的问题（如「请帮我分析这篇论文」），让窗口直接展示分析内容 */
  autoPrompt?: string;
}

const OPEN_ASSISTANT_EVENT = 'pp:open-assistant';
const PAGE_CONTEXT_EVENT = 'pp:page-context';

export function openAssistant(opts: OpenAssistantOptions = {}) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(OPEN_ASSISTANT_EVENT, { detail: opts }));
}

/** 页面内部子 tab 切换时上报（如工作台/选题中心的 tab），浮窗据此切换上下文与预设问题。 */
export interface PageContext {
  tab?: string;
  /** 研究工作台项目标题（注入助手上下文，让助手能基于当前项目回答） */
  projectTitle?: string;
  /** 研究工作台当前步骤 */
  projectStep?: number;
}

export function reportPageContext(context: PageContext = {}) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(new CustomEvent(PAGE_CONTEXT_EVENT, { detail: context }));
}
