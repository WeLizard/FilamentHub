import { useMemo } from 'react';
import { FileDiff } from 'lucide-react';

export type WikiDiffKind = 'equal' | 'added' | 'removed';

export interface WikiDiffLine {
  kind: WikiDiffKind;
  text: string;
  beforeLine: number | null;
  afterLine: number | null;
}

export interface WikiMetadataDiffItem {
  label: string;
  before: string;
  after: string;
}

function fallbackDiff(before: string[], after: string[]): WikiDiffLine[] {
  let prefix = 0;
  while (prefix < before.length && prefix < after.length && before[prefix] === after[prefix]) prefix += 1;
  let suffix = 0;
  while (
    suffix < before.length - prefix
    && suffix < after.length - prefix
    && before[before.length - 1 - suffix] === after[after.length - 1 - suffix]
  ) suffix += 1;

  const lines: WikiDiffLine[] = [];
  for (let index = 0; index < prefix; index += 1) {
    lines.push({ kind: 'equal', text: before[index], beforeLine: index + 1, afterLine: index + 1 });
  }
  for (let index = prefix; index < before.length - suffix; index += 1) {
    lines.push({ kind: 'removed', text: before[index], beforeLine: index + 1, afterLine: null });
  }
  for (let index = prefix; index < after.length - suffix; index += 1) {
    lines.push({ kind: 'added', text: after[index], beforeLine: null, afterLine: index + 1 });
  }
  for (let index = suffix; index > 0; index -= 1) {
    const beforeIndex = before.length - index;
    const afterIndex = after.length - index;
    lines.push({ kind: 'equal', text: before[beforeIndex], beforeLine: beforeIndex + 1, afterLine: afterIndex + 1 });
  }
  return lines;
}

export function buildWikiLineDiff(beforeText: string, afterText: string): WikiDiffLine[] {
  const before = beforeText.split('\n');
  const after = afterText.split('\n');
  if (before.length * after.length > 1_500_000) return fallbackDiff(before, after);

  const table = Array.from({ length: before.length + 1 }, () => new Uint32Array(after.length + 1));
  for (let left = before.length - 1; left >= 0; left -= 1) {
    for (let right = after.length - 1; right >= 0; right -= 1) {
      table[left][right] = before[left] === after[right]
        ? table[left + 1][right + 1] + 1
        : Math.max(table[left + 1][right], table[left][right + 1]);
    }
  }

  const result: WikiDiffLine[] = [];
  let left = 0;
  let right = 0;
  while (left < before.length && right < after.length) {
    if (before[left] === after[right]) {
      result.push({ kind: 'equal', text: before[left], beforeLine: left + 1, afterLine: right + 1 });
      left += 1;
      right += 1;
    } else if (table[left + 1][right] >= table[left][right + 1]) {
      result.push({ kind: 'removed', text: before[left], beforeLine: left + 1, afterLine: null });
      left += 1;
    } else {
      result.push({ kind: 'added', text: after[right], beforeLine: null, afterLine: right + 1 });
      right += 1;
    }
  }
  while (left < before.length) {
    result.push({ kind: 'removed', text: before[left], beforeLine: left + 1, afterLine: null });
    left += 1;
  }
  while (right < after.length) {
    result.push({ kind: 'added', text: after[right], beforeLine: null, afterLine: right + 1 });
    right += 1;
  }
  return result;
}

interface WikiRevisionDiffProps {
  before: string;
  after: string;
  title: string;
  emptyLabel: string;
}

export function WikiRevisionDiff({ before, after, title, emptyLabel }: WikiRevisionDiffProps) {
  const lines = useMemo(() => buildWikiLineDiff(before, after), [before, after]);
  const changed = lines.some((line) => line.kind !== 'equal');

  return (
    <section className="overflow-hidden rounded-2xl border border-white/10 bg-[#09111f]">
      <header className="flex items-center gap-2 border-b border-white/10 bg-white/[0.03] px-4 py-3 text-sm font-medium text-slate-200">
        <FileDiff className="h-4 w-4 text-cyan-300" />
        {title}
      </header>
      {!changed ? (
        <div className="px-5 py-10 text-center text-sm text-slate-500">{emptyLabel}</div>
      ) : (
        <div className="max-h-[46vh] overflow-auto font-mono text-xs leading-5" role="table" aria-label={title}>
          {lines.map((line, index) => {
            const tone = line.kind === 'added'
              ? 'border-emerald-400/20 bg-emerald-500/10 text-emerald-100'
              : line.kind === 'removed'
                ? 'border-red-400/20 bg-red-500/10 text-red-100'
                : 'border-transparent text-slate-400';
            const marker = line.kind === 'added' ? '+' : line.kind === 'removed' ? '−' : ' ';
            return (
              <div key={`${index}-${line.kind}`} className={`grid min-w-max grid-cols-[3.5rem_3.5rem_1.5rem_minmax(32rem,1fr)] border-l-2 ${tone}`} role="row">
                <span className="select-none border-r border-white/[0.06] px-2 text-right text-slate-600">{line.beforeLine ?? ''}</span>
                <span className="select-none border-r border-white/[0.06] px-2 text-right text-slate-600">{line.afterLine ?? ''}</span>
                <span className="select-none px-1 text-center">{marker}</span>
                <span className="whitespace-pre-wrap break-words px-2">{line.text || ' '}</span>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

export function WikiRevisionMetadataDiff({
  items,
  title,
}: {
  items: WikiMetadataDiffItem[];
  title: string;
}) {
  const changed = items.filter((item) => item.before !== item.after);
  if (!changed.length) return null;

  return (
    <section className="mb-4 overflow-hidden rounded-2xl border border-white/10 bg-white/[0.025]">
      <header className="border-b border-white/10 px-4 py-3 text-sm font-medium text-slate-200">{title}</header>
      <div className="divide-y divide-white/[0.06]">
        {changed.map((item) => (
          <div key={item.label} className="grid gap-2 px-4 py-3 md:grid-cols-[9rem_minmax(0,1fr)]">
            <div className="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500">{item.label}</div>
            <div className="grid min-w-0 gap-2 lg:grid-cols-2">
              <div className="min-w-0 rounded-lg border border-red-400/15 bg-red-500/[0.07] px-3 py-2 text-sm text-red-100/80 line-through decoration-red-300/50">
                {item.before || '—'}
              </div>
              <div className="min-w-0 rounded-lg border border-emerald-400/15 bg-emerald-500/[0.07] px-3 py-2 text-sm text-emerald-100">
                {item.after || '—'}
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
