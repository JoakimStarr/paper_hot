'use client';

import React, { useEffect, useMemo, useState, memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MarkdownRendererProps {
  content: string;
  className?: string;
  /** 论文引用编号 → 论文信息：把 AI 回答里的 [n] 渲染成可点击的论文详情页链接 */
  citations?: Record<number, { id: string; title?: string }>;
}

// 检测正文是否含 LaTeX 公式：\(...\) / \[...\] / \begin{env} / $$...$$ / $...$
const MATH_RE = /\\\(|\\\)|\\\[|\\\]|\\begin\{[a-zA-Z]+\}|\$\$|\$[^\$\n]+\$/;
// KaTeX 资产已复制到 public/katex（node_modules/katex/dist 的 css+fonts），仅含公式时才注入
const KATEX_CSS_HREF = '/katex/katex.min.css';

interface MathPlugins {
  remark: unknown;
  rehype: unknown;
}

/**
 * 对 mermaid 渲染出的 SVG 做基本消毒：移除所有 on* 事件属性与 javascript: 协议链接。
 * securityLevel:'strict' 已在源头拦截，这里对最终注入 innerHTML 的字符串再加一层兜底。
 */
function sanitizeMermaidSvg(raw: string): string {
  try {
    const doc = new DOMParser().parseFromString(raw, 'image/svg+xml');
    if (doc.querySelector('parsererror')) return '';
    doc.querySelectorAll('*').forEach((el) => {
      el.getAttributeNames().forEach((name) => {
        const lower = name.toLowerCase();
        if (lower.startsWith('on')) {
          el.removeAttribute(name);
          return;
        }
        const value = (el.getAttribute(name) || '').trim().toLowerCase();
        if ((lower === 'href' || lower === 'xlink:href') && value.startsWith('javascript:')) {
          el.removeAttribute(name);
        }
      });
    });
    return new XMLSerializer().serializeToString(doc.documentElement);
  } catch {
    // 解析失败退回正则剔除，宁可误伤也不放行事件属性
    return raw
      .replace(/\son\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)/gi, '')
      .replace(/javascript:/gi, '');
  }
}

const MermaidBlock = memo(function MermaidBlock({ definition }: { definition: string }) {
  const [svg, setSvg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const mermaid = (await import('mermaid')).default;
        if (cancelled) return;
        mermaid.initialize({
          startOnLoad: false,
          theme: 'default',
          securityLevel: 'strict',
          flowchart: { useMaxWidth: true, htmlLabels: true },
        });
        const id = `mermaid-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const { svg: rendered } = await mermaid.render(id, definition);
        if (!cancelled) setSvg(sanitizeMermaidSvg(rendered));
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : '图表渲染失败');
      }
    })();
    return () => { cancelled = true; };
  }, [definition]);

  if (error) {
    return <div className="text-red-500 text-sm p-2 border border-red-300 rounded">图表渲染失败: {error}</div>;
  }
  if (!svg) {
    return <div className="text-gray-400 text-sm p-2 animate-pulse">图表加载中...</div>;
  }
  return (
    <div
      className="mermaid-diagram my-4 overflow-x-auto"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
});

function MarkdownRenderer({ content, className = '', citations }: MarkdownRendererProps) {
  const needsMath = useMemo(() => MATH_RE.test(content), [content]);
  const [math, setMath] = useState<MathPlugins | null>(null);

  // 把 [n] 引用编号替换为论文链接（避免覆盖已有 markdown 链接的 [n] 文本）
  const renderedContent = useMemo(() => {
    if (!citations) return content;
    return content.replace(/\[(\d+)\]/g, (m, n) => {
      const c = citations[Number(n)];
      return c && c.id ? `[${n}](/paper/${c.id})` : m;
    });
  }, [content, citations]);

  useEffect(() => {
    if (!needsMath || math) return;
    let cancelled = false;
    (async () => {
      try {
        // 仅当正文含公式时才加载 KaTeX 的 JS 处理管线
        const [{ default: remarkMath }, { default: rehypeKatex }] = await Promise.all([
          import('remark-math'),
          import('rehype-katex'),
        ]);
        // 按需注入 KaTeX CSS（浏览器此刻才真正下载 css+字体）
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = KATEX_CSS_HREF;
        document.head.appendChild(link);
        if (!cancelled) setMath({ remark: remarkMath, rehype: rehypeKatex });
      } catch {
        // 公式渲染失败则回退为普通渲染，保证内容不丢
        console.warn('KaTeX 加载失败，已回退为普通 markdown 渲染');
      }
    })();
    return () => { cancelled = true; };
  }, [needsMath, math]);

  const remarkPlugins = useMemo<unknown[]>(
    () => [remarkGfm, ...(math ? [math.remark] : [])],
    [math]
  );
  const rehypePlugins = useMemo<unknown[]>(() => (math ? [math.rehype] : []), [math]);

  return (
    <div className={`prose prose-sm max-w-none dark:prose-invert ${className}`}>
      <ReactMarkdown
        remarkPlugins={remarkPlugins as never}
        rehypePlugins={rehypePlugins as never}
        components={{
          a: ({ href, children, ...props }) => {
            // 论文引用 [n] → 上标形式链接（标题右上角），点击跳转论文详情页
            const linkText = Array.isArray(children)
              ? children.map((c) => (typeof c === 'string' ? c : '')).join('')
              : String(children ?? '');
            const isCitation = typeof href === 'string' && href.startsWith('/paper/') && /^\[\d+\]$/.test(linkText);
            return (
              <a
                href={href}
                {...props}
                className={isCitation ? `ai-citation-link${props.className ? ` ${props.className}` : ''}` : (props.className as string | undefined)}
                target={href?.startsWith('http') ? '_blank' : undefined}
                rel="noreferrer"
                title={isCitation ? '查看论文详情' : undefined}
              >
                {children}
              </a>
            );
          },
          pre: ({ children, ...props }) => {
            const codeElement = children as React.ReactElement | undefined;
            const codeClassName = codeElement?.props?.className || '';
            if (codeClassName.includes('language-mermaid') || codeClassName.includes('mermaid')) {
              const definition = String(codeElement?.props?.children || '');
              return <MermaidBlock definition={definition} />;
            }
            return <pre {...props}>{children}</pre>;
          },
          code: ({ className: cls, children, ...props }) => {
            const match = /language-(\w+)/.exec(cls || '');
            if (match?.[1] === 'mermaid') {
              return (
                <code className="language-mermaid" {...props}>
                  {children}
                </code>
              );
            }
            return (
              <code className={cls} {...props}>
                {children}
              </code>
            );
          },
        }}
      >
        {renderedContent}
      </ReactMarkdown>
    </div>
  );
}

export default memo(MarkdownRenderer, (prev, next) =>
  prev.content === next.content && prev.className === next.className && prev.citations === next.citations
);