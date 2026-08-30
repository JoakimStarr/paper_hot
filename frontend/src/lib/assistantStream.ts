'use client';

/**
 * 悬浮助手直连后端 SSE 流式（复用自 AIAssistant，供内嵌对话组件共用）。
 *
 * 关键：**直连后端**（默认 http://localhost:8000），绕过 Next dev 代理的 gzip 缓冲——
 * 经代理的 SSE 会被缓冲成整块到达，表现为"不是流式、输出慢"；
 * 直连可保证浏览器真正逐字流式。
 */
import { getUserId } from '@/lib/user';

const ASSISTANT_BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://localhost:8000';
const ASSISTANT_API_TOKEN = process.env.NEXT_PUBLIC_API_TOKEN || '';

function assistantHeaders(): Record<string, string> {
  const h: Record<string, string> = { 'Content-Type': 'application/json' };
  if (ASSISTANT_API_TOKEN) h['x-api-token'] = ASSISTANT_API_TOKEN;
  // 会话按用户隔离（后端 _load_session 校验 user_id），必须带与创建会话一致的 x-user-id
  try {
    h['x-user-id'] = getUserId();
  } catch { /* SSR 环境忽略 */ }
  return h;
}

export interface AssistantStreamEvent {
  content?: string;
  reasoning?: string;
  tool_progress?: { tool: string; args?: Record<string, unknown> };
  tools?: unknown[];
  error?: string;
  done?: boolean;
  usage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number };
}

/** 直连后端 POST /api/assistant/chat 的 SSE 流式读取（逐帧解析 content/reasoning/tool_progress/tools/usage/error/done）。 */
export async function streamAssistantDirect(
  sessionId: number,
  messages: Array<{ role: string; content: string }>,
  onEvent: (ev: AssistantStreamEvent) => void,
  signal?: AbortSignal,
  agentEnabled?: boolean,
  model?: string,
  extraContext?: string,
): Promise<void> {
  const body: Record<string, unknown> = { messages, session_id: sessionId };
  if (agentEnabled !== undefined) body.agent_enabled = agentEnabled;
  if (model) body.model = model;
  if (extraContext) body.extra_context = extraContext;
  const res = await fetch(`${ASSISTANT_BACKEND_URL}/api/assistant/chat`, {
    method: 'POST',
    headers: assistantHeaders(),
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const err: unknown = await res.json();
      if (err && typeof err === 'object' && typeof (err as { detail?: unknown }).detail === 'string') {
        detail = (err as { detail: string }).detail;
      }
    } catch { /* 忽略解析失败 */ }
    onEvent({ error: detail });
    return;
  }
  if (!res.body) {
    onEvent({ error: '响应无内容' });
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        let data: Record<string, unknown>;
        try {
          data = JSON.parse(line.slice(6));
        } catch {
          continue;
        }
        if (data.error) {
          onEvent({ error: String(data.error) });
          return;
        }
        if (data.done) {
          onEvent({ done: true });
          return;
        }
        if (typeof data.content === 'string' && data.content) onEvent({ content: data.content });
        else if (typeof data.reasoning === 'string' && data.reasoning) onEvent({ reasoning: data.reasoning });
        else if (data.tool_progress && typeof data.tool_progress === 'object') {
          onEvent({ tool_progress: data.tool_progress as { tool: string; args?: Record<string, unknown> } });
        } else if (Array.isArray(data.tools)) {
          onEvent({ tools: data.tools as unknown[] });
        } else if (data.usage && typeof data.usage === 'object') {
          onEvent({ usage: data.usage as { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number } });
        }
      }
    }
  } catch (e: unknown) {
    if ((e as Error).name !== 'AbortError') throw e;
    return;
  }
  onEvent({ done: true });
}
