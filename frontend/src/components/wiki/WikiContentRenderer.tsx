import React, { Children, useEffect, useMemo, useRef, useState } from 'react';
import type { ExtraProps } from 'react-markdown';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { wikiAPI } from '../../api/client';
import { safeStorage } from '../../utils/storage';
import { generateHeadingId, headingIdsBySourceLine } from './wikiHeadings';

interface WikiContentRendererProps {
  content: string;
  className?: string;
  taskStorageKey?: string;
  privateMedia?: boolean;
}

const SyntaxHighlighter = React.lazy(() => import('./LightweightSyntaxHighlighter').then(
  ({ LightweightSyntaxHighlighter }) => ({ default: LightweightSyntaxHighlighter }),
));

type MermaidApi = typeof import('mermaid')['default'];

let mermaidPromise: Promise<MermaidApi> | null = null;

function loadMermaid(): Promise<MermaidApi> {
  if (!mermaidPromise) {
    mermaidPromise = import('mermaid').then(({ default: mermaid }) => {
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        theme: 'dark',
        themeVariables: {
          background: '#111827',
          primaryColor: '#6366f1',
          primaryTextColor: '#ffffff',
          primaryBorderColor: '#818cf8',
          lineColor: '#94a3b8',
          secondaryColor: '#263449',
          tertiaryColor: '#0b1220',
        },
      });
      return mermaid;
    });
  }
  return mermaidPromise;
}

function MermaidDiagram({ chart }: { chart: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!ref.current || !chart) return;
    const node = ref.current;
    let cancelled = false;
    setFailed(false);
    node.removeAttribute('data-processed');
    node.textContent = chart;
    void loadMermaid()
      .then((mermaid) => {
        if (cancelled) return;
        return mermaid.run({ nodes: [node] });
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [chart]);

  if (failed) {
    return (
      <pre className="my-6 overflow-x-auto rounded-xl border border-amber-300/20 bg-amber-500/[0.05] p-4">
        <code className="language-mermaid">{chart}</code>
      </pre>
    );
  }

  return <div ref={ref} className="mermaid my-6 overflow-x-auto rounded-xl border border-white/10 bg-black/10 p-4" />;
}

function AuthenticatedWikiImage({
  src,
  alt,
  ...rest
}: React.ComponentPropsWithoutRef<'img'>) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!src) return;
    let active = true;
    let createdUrl: string | null = null;
    void wikiAPI.getMediaBlob(src)
      .then((blob) => {
        if (!active) return;
        createdUrl = URL.createObjectURL(blob);
        setObjectUrl(createdUrl);
      })
      .catch(() => {
        if (active) setObjectUrl(null);
      });
    return () => {
      active = false;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [src]);

  return (
    <img
      src={objectUrl || undefined}
      alt={alt || ''}
      loading="lazy"
      aria-busy={!objectUrl}
      {...rest}
    />
  );
}

function textFromChildren(children: React.ReactNode): string {
  return Children.toArray(children)
    .map((child) => {
      if (typeof child === 'string' || typeof child === 'number') return String(child);
      if (!React.isValidElement(child)) return '';
      const props = child.props as { children?: React.ReactNode };
      return textFromChildren(props.children);
    })
    .join('');
}

function taskKey(children: React.ReactNode, line?: number): string {
  const textKey = textFromChildren(children)
    .toLowerCase()
    .replace(/[^a-zа-яё0-9\s]/gi, '')
    .trim()
    .replace(/\s+/g, '-')
    .slice(0, 80);
  return `${line ?? 'task'}-${textKey}`;
}

const ARTICLE_PROSE = `prose prose-lg max-w-none break-words text-slate-200
  [&>*]:text-slate-200
  [&_h1]:mt-8 [&_h1]:mb-4 [&_h1]:border-b [&_h1]:border-white/15 [&_h1]:pb-3 [&_h1]:text-3xl [&_h1]:font-bold [&_h1]:text-white
  [&_h2]:mt-8 [&_h2]:mb-4 [&_h2]:text-2xl [&_h2]:font-bold [&_h2]:text-white
  [&_h3]:mt-6 [&_h3]:mb-3 [&_h3]:text-xl [&_h3]:font-bold [&_h3]:text-white
  [&_h4]:mt-4 [&_h4]:mb-2 [&_h4]:text-lg [&_h4]:font-semibold [&_h4]:text-white
  [&_p]:my-4 [&_p]:break-words [&_p]:leading-7 [&_p]:text-slate-200
  [&_a]:text-cyan-300 [&_a]:no-underline hover:[&_a]:text-cyan-200 hover:[&_a]:underline
  [&_strong]:font-semibold [&_strong]:text-white
  [&_pre]:overflow-x-auto [&_pre]:rounded-xl [&_pre]:border [&_pre]:border-white/15 [&_pre]:bg-black/60 [&_pre]:p-4
  [&_blockquote]:my-6 [&_blockquote]:rounded-r-xl [&_blockquote]:border-l-4 [&_blockquote]:border-cyan-400 [&_blockquote]:bg-cyan-400/[0.06] [&_blockquote]:py-2 [&_blockquote]:pl-6 [&_blockquote]:pr-4 [&_blockquote]:text-slate-200
  [&_ul]:my-4 [&_ul]:list-disc [&_ul]:space-y-2 [&_ul]:pl-6
  [&_ol]:my-4 [&_ol]:list-decimal [&_ol]:space-y-2 [&_ol]:pl-6
  [&_li]:pl-2 [&_li]:text-slate-200 [&_li]:marker:text-cyan-300
  [&_img]:my-6 [&_img]:h-auto [&_img]:max-w-full [&_img]:rounded-xl [&_img]:shadow-xl
  [&_hr]:my-8 [&_hr]:border-white/15`;

export function WikiContentRenderer({
  content,
  className = '',
  taskStorageKey,
  privateMedia = false,
}: WikiContentRendererProps) {
  const [checkboxStates, setCheckboxStates] = useState<Record<string, boolean>>({});
  const headingIds = useMemo(() => headingIdsBySourceLine(content), [content]);

  useEffect(() => {
    if (!taskStorageKey) {
      setCheckboxStates({});
      return;
    }
    const saved = safeStorage.get(taskStorageKey);
    if (!saved) {
      setCheckboxStates({});
      return;
    }
    try {
      setCheckboxStates(JSON.parse(saved) as Record<string, boolean>);
    } catch {
      setCheckboxStates({});
    }
  }, [taskStorageKey]);

  const components = useMemo(() => ({
    code(props: React.ComponentPropsWithoutRef<'code'> & ExtraProps & { inline?: boolean }) {
      const { inline, className: codeClassName, children, ...rest } = props;
      const match = /language-(\w+)/.exec(codeClassName || '');
      const rawValue = String(children);
      // react-markdown no longer supplies `inline` in every supported version.
      // A fenced block keeps its trailing newline, while inline code does not.
      // Detecting that distinction prevents a lazy block highlighter from being
      // mounted inside the paragraph generated for ordinary `inline code`.
      const isInline = inline ?? (!codeClassName && !rawValue.includes('\n'));
      const value = rawValue.replace(/\n$/, '');

      if (!isInline && match?.[1] === 'mermaid') return <MermaidDiagram chart={value} />;
      if (!isInline) {
        if (!match || match[1] === 'text') {
          return (
            <pre>
              <code className="text-sm text-slate-100">{value}</code>
            </pre>
          );
        }
        return (
          <React.Suspense fallback={<pre><code className="text-sm text-slate-100">{value}</code></pre>}>
            <SyntaxHighlighter
              language={match?.[1] || 'text'}
            >
              {value}
            </SyntaxHighlighter>
          </React.Suspense>
        );
      }
      return (
        <code
          className={`rounded bg-black/40 px-1.5 py-0.5 text-sm text-cyan-300 ${codeClassName || ''}`}
          {...rest}
        >
          {children}
        </code>
      );
    },
    pre(props: React.ComponentPropsWithoutRef<'pre'> & ExtraProps) {
      const { children } = props;
      // Block renderers own their frame. Removing react-markdown's additional
      // wrapper prevents a visible nested <pre> swap when the lazy syntax
      // highlighter finishes loading.
      return <>{children}</>;
    },
    table(props: React.ComponentPropsWithoutRef<'table'> & ExtraProps) {
      const { children, ...rest } = props;
      return (
        <div className="my-6 -mx-2 overflow-x-auto px-2">
          <table
            className="w-full border-collapse overflow-hidden rounded-lg text-sm [&_thead]:bg-white/10 [&_th]:border-b [&_th]:border-white/20 [&_th]:px-3 [&_th]:py-2.5 [&_th]:text-left [&_th]:font-semibold [&_th]:text-white [&_tbody]:bg-white/[0.03] [&_td]:border-b [&_td]:border-white/10 [&_td]:px-3 [&_td]:py-2.5 [&_td]:text-slate-200 [&_tr:last-child_td]:border-b-0 [&_tr:hover]:bg-white/[0.06]"
            {...rest}
          >
            {children}
          </table>
        </div>
      );
    },
    img(props: React.ComponentPropsWithoutRef<'img'> & ExtraProps) {
      const { src, alt, node: _node, ...rest } = props;
      if (privateMedia && src?.startsWith('/api/v1/wiki/media/')) {
        return <AuthenticatedWikiImage src={src} alt={alt || ''} {...rest} />;
      }
      return <img src={src} alt={alt || ''} loading="lazy" {...rest} />;
    },
    a(props: React.ComponentPropsWithoutRef<'a'> & ExtraProps) {
      const { href, children, ...rest } = props;
      const external = Boolean(href && /^(https?:)?\/\//i.test(href));
      return (
        <a href={href} target={external ? '_blank' : undefined} rel={external ? 'noopener noreferrer' : undefined} {...rest}>
          {children}
        </a>
      );
    },
    h1(props: React.ComponentPropsWithoutRef<'h1'> & ExtraProps) {
      const { children, node, ...rest } = props;
      const line = node?.position?.start.line;
      const id = (line && headingIds.get(line)) || `${generateHeadingId(textFromChildren(children))}-${line ?? 'heading'}`;
      return <h1 id={id} className="scroll-mt-24" {...rest}>{children}</h1>;
    },
    h2(props: React.ComponentPropsWithoutRef<'h2'> & ExtraProps) {
      const { children, node, ...rest } = props;
      const line = node?.position?.start.line;
      const id = (line && headingIds.get(line)) || `${generateHeadingId(textFromChildren(children))}-${line ?? 'heading'}`;
      return <h2 id={id} className="scroll-mt-24" {...rest}>{children}</h2>;
    },
    h3(props: React.ComponentPropsWithoutRef<'h3'> & ExtraProps) {
      const { children, node, ...rest } = props;
      const line = node?.position?.start.line;
      const id = (line && headingIds.get(line)) || `${generateHeadingId(textFromChildren(children))}-${line ?? 'heading'}`;
      return <h3 id={id} className="scroll-mt-24" {...rest}>{children}</h3>;
    },
    li(props: React.ComponentPropsWithoutRef<'li'> & ExtraProps) {
      const { children, className: itemClassName, node, ...rest } = props;
      if (!taskStorageKey) return <li className={itemClassName} {...rest}>{children}</li>;

      const childArray = Children.toArray(children);
      const checkboxChild = childArray.find((child) =>
        React.isValidElement(child)
        && (child as React.ReactElement<{ type?: string }>).props?.type === 'checkbox',
      );
      if (!checkboxChild) return <li className={itemClassName} {...rest}>{children}</li>;

      const originalChecked = Boolean((checkboxChild as React.ReactElement<{ checked?: boolean }>).props.checked);
      const key = taskKey(children, node?.position?.start.line);
      const checked = checkboxStates[key] ?? originalChecked;
      const otherChildren = childArray.filter((child) => child !== checkboxChild);
      const taskLabel = textFromChildren(otherChildren).trim();
      const toggle = () => {
        setCheckboxStates((previous) => {
          const next = { ...previous, [key]: !checked };
          safeStorage.set(taskStorageKey, JSON.stringify(next));
          return next;
        });
      };
      return (
        <li className={`${itemClassName || ''} flex items-start gap-2`} {...rest}>
          <input type="checkbox" checked={checked} onChange={toggle} aria-label={taskLabel} className="mt-1.5 h-4 w-4 cursor-pointer rounded accent-cyan-500" />
          <span className={`flex-1 ${checked ? 'text-slate-500 line-through' : ''}`}>
            {otherChildren}
          </span>
        </li>
      );
    },
  }), [checkboxStates, headingIds, privateMedia, taskStorageKey]);

  return (
    <div className={`${ARTICLE_PROSE} ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{content}</ReactMarkdown>
    </div>
  );
}
