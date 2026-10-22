import { useMemo } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

interface AdminPagerProps {
  /** One-based current page. */
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  disabled?: boolean;
  label: string;
  previousLabel: string;
  nextLabel: string;
}

const arrowButtonClass =
  'inline-flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] text-gray-400 transition hover:border-white/20 hover:bg-white/[0.09] hover:text-white disabled:cursor-not-allowed disabled:opacity-40';

export function AdminPager({
  page, totalPages, onPageChange, disabled = false, label, previousLabel, nextLabel,
}: AdminPagerProps) {
  // First and last page stay reachable; a gap between them and the window around the current
  // page shows that more pages exist.
  const pageNumbers = useMemo<(number | 'gap')[]>(() => {
    if (totalPages <= 7) {
      return Array.from({ length: totalPages }, (_, index) => index + 1);
    }
    const start = Math.min(Math.max(page - 1, 2), totalPages - 3);
    const window = [start, start + 1, start + 2];
    return [1, ...(start > 2 ? ['gap' as const] : []), ...window,
      ...(start + 2 < totalPages - 1 ? ['gap' as const] : []), totalPages];
  }, [page, totalPages]);

  if (totalPages <= 1) return null;

  return (
    <nav className="flex flex-wrap items-center gap-1" aria-label={label}>
      <button
        type="button"
        onClick={() => onPageChange(Math.max(1, page - 1))}
        disabled={page <= 1 || disabled}
        className={arrowButtonClass}
        title={previousLabel}
        aria-label={previousLabel}
      >
        <ChevronLeft className="h-4 w-4" />
      </button>
      {pageNumbers.map((pageNumber, index) => pageNumber === 'gap' ? (
        <span key={`gap-${index}`} className="px-1 text-xs text-gray-600" aria-hidden="true">…</span>
      ) : (
        <button
          key={pageNumber}
          type="button"
          onClick={() => onPageChange(pageNumber)}
          disabled={disabled}
          aria-current={pageNumber === page ? 'page' : undefined}
          className={`h-8 min-w-8 rounded-lg px-2 text-xs font-medium transition ${
            pageNumber === page
              ? 'bg-purple-500/20 text-purple-100 ring-1 ring-inset ring-purple-400/25'
              : 'text-gray-500 hover:bg-white/[0.07] hover:text-gray-200'
          }`}
        >
          {pageNumber}
        </button>
      ))}
      <button
        type="button"
        onClick={() => onPageChange(Math.min(totalPages, page + 1))}
        disabled={page >= totalPages || disabled}
        className={arrowButtonClass}
        title={nextLabel}
        aria-label={nextLabel}
      >
        <ChevronRight className="h-4 w-4" />
      </button>
    </nav>
  );
}
