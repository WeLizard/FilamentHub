import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { AxiosError } from 'axios';
import { Copy, ExternalLink, GitMerge, Loader2, ScanSearch, X } from 'lucide-react';
import { adminAPI } from '../../api/client';
import type { FilamentDuplicateReview, MergeFilamentSummary } from '../../types/api';
import { translateApiError } from '../../utils/translateApiError';
import { FilamentMergeModal, MergeContributions, MergeFilamentOption } from '../FilamentMergeModal';
import { toast } from '../Toast';

const PAGE_SIZE = 20;

const DuplicateSide: React.FC<{ label: string; filament: MergeFilamentSummary; note?: string }> = ({
  label,
  filament,
  note,
}) => (
  <div className="min-w-0 rounded-lg border border-white/10 bg-black/15 px-3 py-2">
    <div className="mb-1 flex items-center justify-between gap-2 text-[11px] uppercase tracking-wide text-gray-500">
      <span>{label}</span>
      <a
        href={`/filaments/${filament.id}`}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1 normal-case tracking-normal text-gray-400 hover:text-white"
      >
        #{filament.id}
        <ExternalLink className="h-3 w-3" />
      </a>
    </div>
    <div className="text-sm text-white">
      <MergeFilamentOption filament={filament} />
    </div>
    <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5">
      <span className="text-xs text-purple-300">{filament.material_type}</span>
      <MergeContributions filament={filament} />
    </div>
    {note && <p className="mt-1 truncate text-xs text-gray-500">{note}</p>}
  </div>
);

export function AdminFilamentDuplicates() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [merging, setMerging] = useState<FilamentDuplicateReview | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ['admin-filament-duplicates', page],
    queryFn: () => adminAPI.listFilamentDuplicates({ page, size: PAGE_SIZE }),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ['admin-filament-duplicates'] });
    queryClient.invalidateQueries({ queryKey: ['admin-filament-duplicates-count'] });
  };

  const dismissMutation = useMutation({
    mutationFn: (reviewId: number) => adminAPI.dismissFilamentDuplicate(reviewId),
    onSuccess: () => {
      refresh();
      toast.success(t('adminMaterials.duplicates.dismissed'));
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      toast.error(translateApiError(t, err.response?.data?.detail, t('adminMaterials.duplicates.actionFailed')));
    },
  });

  const scanMutation = useMutation({
    mutationFn: () => adminAPI.scanFilamentDuplicates(),
    onSuccess: ({ added }) => {
      refresh();
      toast.success(
        added > 0
          ? t('adminMaterials.duplicates.scanFound', { count: added })
          : t('adminMaterials.duplicates.scanNothing'),
      );
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      toast.error(translateApiError(t, err.response?.data?.detail, t('adminMaterials.duplicates.actionFailed')));
    },
  });

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  // Resolving the last pair of the last page must not leave an empty page.
  useEffect(() => {
    if (page > pages) setPage(pages);
  }, [page, pages]);

  return (
    <section
      className={`rounded-xl border p-4 ${
        total > 0 ? 'border-amber-400/30 bg-amber-500/[0.07]' : 'border-white/10 bg-white/5'
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <Copy className={`h-5 w-5 shrink-0 ${total > 0 ? 'text-amber-300' : 'text-gray-400'}`} />
          <h3 className="font-semibold text-white">{t('adminMaterials.duplicates.title')}</h3>
          {total > 0 && (
            <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-xs font-semibold text-amber-200">
              {total}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={() => scanMutation.mutate()}
          disabled={scanMutation.isPending}
          className="inline-flex items-center gap-2 rounded-lg bg-white/10 px-3 py-1.5 text-sm text-white transition-all hover:bg-white/20 disabled:opacity-50"
        >
          {scanMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <ScanSearch className="h-4 w-4" />}
          {t('adminMaterials.duplicates.scan')}
        </button>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-4">
          <Loader2 className="h-5 w-5 animate-spin text-purple-400" />
        </div>
      ) : items.length === 0 ? (
        <p className="mt-2 text-sm text-gray-400">{t('adminMaterials.duplicates.empty')}</p>
      ) : (
        <>
          <p className="mt-1 text-xs leading-5 text-gray-400">{t('adminMaterials.duplicates.hint')}</p>
          <ul className="mt-3 space-y-2">
            {items.map((review) => (
              <li key={review.id} className="rounded-lg border border-white/10 bg-white/5 p-3">
                <div className="mb-2 text-xs text-gray-400">{review.brand_name}</div>
                <div className="grid gap-2 md:grid-cols-[1fr_1fr_auto] md:items-center">
                  <DuplicateSide
                    label={t('adminMaterials.duplicates.newer')}
                    filament={review.filament}
                    note={
                      review.created_by
                        ? t('adminMaterials.duplicates.addedBy', { name: review.created_by.username })
                        : undefined
                    }
                  />
                  <DuplicateSide label={t('adminMaterials.duplicates.older')} filament={review.candidate} />
                  <div className="flex gap-2 md:flex-col">
                    <button
                      type="button"
                      onClick={() => setMerging(review)}
                      className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-purple-500/20 px-3 py-1.5 text-sm text-purple-100 transition-all hover:bg-purple-500/30"
                    >
                      <GitMerge className="h-4 w-4" />
                      {t('adminMaterials.duplicates.merge')}
                    </button>
                    <button
                      type="button"
                      onClick={() => dismissMutation.mutate(review.id)}
                      disabled={dismissMutation.isPending}
                      className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-white/10 px-3 py-1.5 text-sm text-gray-200 transition-all hover:bg-white/20 disabled:opacity-50"
                    >
                      <X className="h-4 w-4" />
                      {t('adminMaterials.duplicates.notDuplicate')}
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
          {pages > 1 && (
            <div className="mt-3 flex items-center justify-center gap-2 text-sm">
              <button
                type="button"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="rounded-lg bg-white/5 px-3 py-1 text-gray-300 hover:bg-white/10 disabled:opacity-50"
              >
                {t('adminMaterials.prev')}
              </button>
              <span className="text-gray-400">
                {t('adminMaterials.page')} {page} {t('adminMaterials.of')} {pages}
              </span>
              <button
                type="button"
                onClick={() => setPage((p) => Math.min(pages, p + 1))}
                disabled={page === pages}
                className="rounded-lg bg-white/5 px-3 py-1 text-gray-300 hover:bg-white/10 disabled:opacity-50"
              >
                {t('adminMaterials.next')}
              </button>
            </div>
          )}
        </>
      )}

      {merging && (
        <FilamentMergeModal
          filament={merging.filament}
          initialTargetId={merging.candidate.id}
          onClose={() => setMerging(null)}
          onMerged={refresh}
        />
      )}
    </section>
  );
}
