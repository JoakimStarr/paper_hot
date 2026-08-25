'use client';

import React, { useEffect, useMemo, useState, memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

// 检测正文是否含 LaTeX 公式：\(...\) / \[...\] / \begin{env} / $$...$$ / $...$
const MATH_RE = /\\\(|\\\)|\\\[|\\\]|\\begin\{[a-zA-Z]+\}|\$\$|\$[^\$\n]+\$/;
// KaTeX 资产已复制到 public/katex（node_modules/katex/dist 的 css+fonts），仅含公式时才注入
const KATEX_CSS_HREF = '/katex/katex.min.css';

interface MathPlugins {
  remark: unknown;
  rehype: unknown;
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
          securityLevel: 'loose',
          flowchart: { useMaxWidth: true, htmlLabels: true },
        });
        const id = `mermaid-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        const { svg: rendered } = await mermaid.render(id, definition);
        if (!cancelled) setSvg(rendered);
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

function MarkdownRenderer({ content, className = '' }: MarkdownRendererProps) {
  const needsMath = useMemo(() => MATH_RE.test(content), [content]);
  const [math, setMath] = useState<MathPlugins | null>(null);

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
        {content}
      </ReactMarkdown>
    </div>
  );
}

export default memo(MarkdownRenderer, (prev, next) =>
  prev.content === next.content && prev.className === next.className
);