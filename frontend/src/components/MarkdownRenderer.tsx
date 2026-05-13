'use client';

import React, { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import mermaid from 'mermaid';
import 'katex/dist/katex.min.css';

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

// Initialize mermaid
mermaid.initialize({
  startOnLoad: false,
  theme: 'default',
  securityLevel: 'loose',
  flowchart: {
    useMaxWidth: true,
    htmlLabels: true,
  },
});

export default function MarkdownRenderer({ content, className = '' }: MarkdownRendererProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [mermaidRendered, setMermaidRendered] = useState(false);

  useEffect(() => {
    if (containerRef.current && !mermaidRendered) {
      const mermaidElements = containerRef.current.querySelectorAll('.language-mermaid, .mermaid');
      mermaidElements.forEach((element, index) => {
        const graphDefinition = element.textContent || '';
        const id = `mermaid-${Date.now()}-${index}`;
        
        try {
          mermaid.render(id, graphDefinition).then(({ svg }) => {
            const wrapper = document.createElement('div');
            wrapper.className = 'mermaid-diagram my-4';
            wrapper.innerHTML = svg;
            element.parentNode?.replaceChild(wrapper, element);
          });
        } catch (error) {
          console.error('Mermaid rendering error:', error);
        }
      });
      setMermaidRendered(true);
    }
  }, [content, mermaidRendered]);

  // Reset mermaid rendered state when content changes
  useEffect(() => {
    setMermaidRendered(false);
  }, [content]);

  return (
    <div ref={containerRef} className={`prose prose-sm max-w-none dark:prose-invert ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          pre: ({ children, ...props }) => {
            // Check if this is a mermaid code block
            const codeElement = children as React.ReactElement;
            if (codeElement?.props?.className?.includes('language-mermaid')) {
              return <div className="mermaid">{codeElement.props.children}</div>;
            }
            return <pre {...props}>{children}</pre>;
          },
          code: ({ className, children, ...props }) => {
            const match = /language-(\w+)/.exec(className || '');
            const language = match ? match[1] : '';
            
            if (language === 'mermaid') {
              return <code className="mermaid">{children}</code>;
            }
            
            return (
              <code className={className} {...props}>
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
