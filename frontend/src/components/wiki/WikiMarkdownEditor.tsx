import { useRef } from 'react';
import {
  Bold,
  Code2,
  Heading2,
  Heading3,
  Image,
  Italic,
  Link,
  List,
  ListOrdered,
  Quote,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';


interface WikiMarkdownEditorProps {
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}

interface ToolbarAction {
  key: string;
  icon: typeof Bold;
  labelKey: string;
  before: string;
  after?: string;
  placeholder: string;
  linePrefix?: boolean;
}

const ACTIONS: ToolbarAction[] = [
  { key: 'bold', icon: Bold, labelKey: 'bold', before: '**', after: '**', placeholder: 'text' },
  { key: 'italic', icon: Italic, labelKey: 'italic', before: '*', after: '*', placeholder: 'text' },
  { key: 'h2', icon: Heading2, labelKey: 'heading2', before: '## ', placeholder: 'Heading', linePrefix: true },
  { key: 'h3', icon: Heading3, labelKey: 'heading3', before: '### ', placeholder: 'Heading', linePrefix: true },
  { key: 'bullet', icon: List, labelKey: 'bulletList', before: '- ', placeholder: 'List item', linePrefix: true },
  { key: 'ordered', icon: ListOrdered, labelKey: 'numberedList', before: '1. ', placeholder: 'List item', linePrefix: true },
  { key: 'quote', icon: Quote, labelKey: 'quote', before: '> ', placeholder: 'Quote', linePrefix: true },
  { key: 'code', icon: Code2, labelKey: 'code', before: '`', after: '`', placeholder: 'code' },
  { key: 'link', icon: Link, labelKey: 'link', before: '[', after: '](https://)', placeholder: 'link text' },
  { key: 'image', icon: Image, labelKey: 'image', before: '![', after: '](https://)', placeholder: 'image description' },
];

export function WikiMarkdownEditor({ value, onChange, placeholder }: WikiMarkdownEditorProps) {
  const { t } = useTranslation();
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const applyAction = (action: ToolbarAction) => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    const selectionStart = textarea.selectionStart;
    const selectionEnd = textarea.selectionEnd;
    if (action.linePrefix) {
      const lineStart = value.lastIndexOf('\n', Math.max(0, selectionStart - 1)) + 1;
      const effectiveEnd = selectionEnd > selectionStart && value[selectionEnd - 1] === '\n'
        ? selectionEnd - 1
        : selectionEnd;
      const nextLineBreak = value.indexOf('\n', effectiveEnd);
      const lineEnd = nextLineBreak === -1 ? value.length : nextLineBreak;
      const selectedLines = value.slice(lineStart, lineEnd);
      const replacement = selectedLines
        ? selectedLines.split('\n').map((line) => `${action.before}${line}`).join('\n')
        : `${action.before}${action.placeholder}`;
      onChange(`${value.slice(0, lineStart)}${replacement}${value.slice(lineEnd)}`);

      requestAnimationFrame(() => {
        textarea.focus();
        textarea.setSelectionRange(
          lineStart + action.before.length,
          lineStart + replacement.length,
        );
      });
      return;
    }

    const selected = value.slice(selectionStart, selectionEnd) || action.placeholder;
    const replacement = `${action.before}${selected}${action.after ?? ''}`;
    const nextValue = `${value.slice(0, selectionStart)}${replacement}${value.slice(selectionEnd)}`;
    onChange(nextValue);

    requestAnimationFrame(() => {
      textarea.focus();
      textarea.setSelectionRange(
        selectionStart + action.before.length,
        selectionStart + action.before.length + selected.length,
      );
    });
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Tab') {
      event.preventDefault();
      const textarea = event.currentTarget;
      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      if (start === end) {
        onChange(`${value.slice(0, start)}  ${value.slice(end)}`);
        requestAnimationFrame(() => textarea.setSelectionRange(start + 2, start + 2));
        return;
      }

      const lineStart = value.lastIndexOf('\n', Math.max(0, start - 1)) + 1;
      const selectedBlock = value.slice(lineStart, end);
      const indentedBlock = selectedBlock.split('\n').map((line) => `  ${line}`).join('\n');
      onChange(`${value.slice(0, lineStart)}${indentedBlock}${value.slice(end)}`);
      const addedCharacters = indentedBlock.length - selectedBlock.length;
      requestAnimationFrame(() => textarea.setSelectionRange(lineStart, end + addedCharacters));
      return;
    }
    if (!(event.ctrlKey || event.metaKey)) return;
    const action = event.key.toLowerCase() === 'b'
      ? ACTIONS[0]
      : event.key.toLowerCase() === 'i'
        ? ACTIONS[1]
        : null;
    if (!action) return;
    event.preventDefault();
    applyAction(action);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-white/15 bg-[#0b1220] focus-within:border-blue-400/60 focus-within:ring-2 focus-within:ring-blue-500/15">
      <div className="flex shrink-0 flex-wrap items-center gap-1 border-b border-white/10 bg-white/[0.035] p-2" role="toolbar" aria-label={t('wikiAuthoring.markdownToolbar')}>
        {ACTIONS.map((action) => {
          const Icon = action.icon;
          const label = t(`wikiAuthoring.toolbar.${action.labelKey}`);
          return (
            <button
              key={action.key}
              type="button"
              onClick={() => applyAction(action)}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-400"
              title={label}
              aria-label={label}
            >
              <Icon className="h-4 w-4" />
            </button>
          );
        })}
        <span className="ml-auto px-2 text-[11px] font-medium uppercase tracking-wider text-slate-600">Markdown</span>
      </div>
      <textarea
        ref={textareaRef}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={handleKeyDown}
        className="min-h-[320px] flex-1 resize-none overflow-y-auto bg-transparent px-4 py-3 font-mono text-sm leading-6 text-slate-200 outline-none placeholder:text-slate-600"
        placeholder={placeholder}
        spellCheck
      />
    </div>
  );
}
