'use client';

import React, { useEffect, useRef, useState, memo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';

interface MarkdownRendererProps {
  content: string;
  className?: string;
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
  return (
    <div className={`prose prose-sm max-w-none dark:prose-invert ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
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