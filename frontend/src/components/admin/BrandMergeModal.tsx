import { useDeferredValue, useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import type { AxiosError } from 'axios';
import { AlertTriangle, ArrowLeftRight, GitMerge, Loader2 } from 'lucide-react';
import { adminAPI } from '../../api/client';
import type { BrandMergeFilamentRow } from '../../types/api';
import { translateApiError } from '../../utils/translateApiError';
import { Dropdown } from '../Dropdown';
import { MergeContributions, MergeFilamentOption, mergeFilamentLabel } from '../FilamentMergeModal';
import { ModalOverlay } from '../ModalOverlay';
import { toast } from '../Toast';

const KEEP_SEPARATE = 0;

interface BrandRef {
  id: number;
  name: string;
}

interface BrandMergeModalProps {
  duplicate: BrandRef;
  kept?: BrandRef | null;
  onClose: () => void;
}

export const BrandMergeModal: React.FC<BrandMergeModalProps> = ({ duplicate, kept = null, onClose }) => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [source, setSource] = useState<BrandRef>(duplicate);
  const [target, setTarget] = useState<BrandRef | null>(kept);
  const [brandSearch, setBrandSearch] = useState('');
  const deferredSearch = useDeferredValue(brandSearch.trim());
  const [pairs, setPairs] = useState<Record<number, number>>({});

  const { data: searchData } = useQuery({
    queryKey: ['admin-brand-merge-search', deferredSearch],
    queryFn: () => adminAPI.listBrands({ page: 1, size: 20, active_only: false, search: deferredSearch || undefined }),
    enabled: target === null,
    staleTime: 30_000,
  });

  const previewQuery = useQuery({
    queryKey: ['admin-brand-merge-preview', source.id, target?.id],
    queryFn: () => adminAPI.getBrandMergePreview(source.id, target!.id),
    enabled: target !== null,
  });
  const preview = previewQuery.data;

  useEffect(() => {
    if (!preview) return;
    setPairs(
      Object.fromEntries(
        preview.filaments.map((row) => [row.source.id, row.suggested_target_id ?? KEEP_SEPARATE]),
      ),
    );
  }, [preview]);

  const unresolved = useMemo(
    () => (preview?.filaments ?? []).filter((row) => row.needs_pair && !pairs[row.source.id]),
    [preview, pairs],
  );

  const mergeMutation = useMutation({
    mutationFn: () =>
      adminAPI.mergeBrand(source.id, {
        target_id: target!.id,
        filament_pairs: Object.entries(pairs)
          .filter(([, targetId]) => targetId !== KEEP_SEPARATE)
          .map(([sourceId, targetId]) => ({
            source_filament_id: Number(sourceId),
            target_filament_id: targetId,
          })),
      }),
    onSuccess: (brand) => {
      queryClient.invalidateQueries({ queryKey: ['admin-brands'] });
      queryClient.invalidateQueries({ queryKey: ['admin-brand-duplicates'] });
      queryClient.invalidateQueries({ queryKey: ['admin-materials'] });
      queryClient.invalidateQueries({ queryKey: ['filaments'] });
      toast.success(t('catalogMerge.brandMerged', { duplicate: source.name, name: brand.name }));
      onClose();
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      toast.error(translateApiError(t, err.response?.data?.detail, t('catalogMerge.mergeFailed')), 12000);
    },
  });

  const swap = () => {
    if (!target) return;
    setSource(target);
    setTarget(source);
  };

  const rowOptions = (row: BrandMergeFilamentRow) => [
    { value: KEEP_SEPARATE, label: t('catalogMerge.keepSeparate') },
    ...row.candidates.map((item) => ({ value: item.id, label: mergeFilamentLabel(item) })),
  ];

  const brandOptions = (searchData?.items ?? [])
    .filter((brand) => brand.id !== source.id)
    .map((brand) => ({ value: brand.id, label: brand.name }));

  return (
    <ModalOverlay
      onClose={onClose}
      closeOnOverlayClick={!mergeMutation.isPending}
      closeOnEscape={!mergeMutation.isPending}
    >
      <div className="flex max-h-[85vh] w-full max-w-3xl flex-col rounded-2xl border border-white/20 bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 shadow-2xl">
        <div className="flex items-center gap-3 border-b border-white/10 p-6">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-purple-500/20">
            <GitMerge className="h-5 w-5 text-purple-300" />
          </div>
          <h3 className="text-lg font-bold text-white">{t('catalogMerge.brandTitle')}</h3>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto p-6">
          <div className="flex flex-wrap items-end gap-3">
            <div className="min-w-0">
              <p className="text-xs text-gray-400">{t('catalogMerge.duplicateBrand')}</p>
              <p className="font-semibold text-white">{source.name}</p>
            </div>
            <button
              type="button"
              onClick={swap}
              disabled={!target || mergeMutation.isPending}
              className="rounded-lg bg-white/10 p-2 text-white transition-all hover:bg-white/20 disabled:opacity-40"
              title={t('catalogMerge.swap')}
              aria-label={t('catalogMerge.swap')}
            >
              <ArrowLeftRight className="h-4 w-4" />
            </button>
            <div className="min-w-0">
              <p className="text-xs text-gray-400">{t('catalogMerge.keptBrand')}</p>
              {target ? (
                <div className="flex items-center gap-2">
                  <p className="font-semibold text-white">{target.name}</p>
                  {!kept && (
                    <button
                      type="button"
                      onClick={() => setTarget(null)}
                      className="text-xs text-purple-300 underline hover:text-purple-200"
                    >
                      {t('catalogMerge.changeBrand')}
                    </button>
                  )}
                </div>
              ) : (
                <div className="w-72 max-w-full">
                  <Dropdown
                    value=""
                    options={brandOptions}
                    placeholder={t('catalogMerge.chooseBrand')}
                    filterable
                    filterValue={brandSearch}
                    onFilterChange={setBrandSearch}
                    onChange={(value) => {
                      const brand = searchData?.items.find((item) => item.id === Number(value));
                      if (brand) setTarget({ id: brand.id, name: brand.name });
                    }}
                  />
                </div>
              )}
            </div>
          </div>

          <p className="text-sm text-gray-300">{t('catalogMerge.brandExplanation')}</p>

          {previewQuery.isLoading && (
            <div className="flex items-center gap-2 text-gray-300">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>{t('catalogMerge.loading')}</span>
            </div>
          )}

          {previewQuery.error && (
            <p className="text-sm text-red-300">
              {translateApiError(
                t,
                (previewQuery.error as AxiosError<{ detail: unknown }>).response?.data?.detail,
                t('catalogMerge.loadFailed'),
              )}
            </p>
          )}

          {preview?.source_represented && (
            <p className="flex items-start gap-2 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{t('catalogMerge.sourceRepresented')}</span>
            </p>
          )}

          {preview && !preview.source_represented && (
            <div className="space-y-3">
              <h4 className="text-sm font-semibold text-white">
                {t('catalogMerge.filamentsOfDuplicate', { count: preview.filaments.length })}
              </h4>
              {preview.filaments.length === 0 && (
                <p className="text-sm text-gray-400">{t('catalogMerge.noFilaments')}</p>
              )}
              {preview.filaments.map((row) => {
                const needsDecision = row.needs_pair && !pairs[row.source.id];
                return (
                  <div
                    key={row.source.id}
                    className={`grid gap-3 rounded-xl border p-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)] md:items-center ${
                      needsDecision ? 'border-red-500/40 bg-red-500/10' : 'border-white/10 bg-white/5'
                    }`}
                  >
                    <div className="min-w-0">
                      <div className="text-sm text-white">
                        <MergeFilamentOption filament={row.source} />
                      </div>
                      <MergeContributions filament={row.source} />
                      {needsDecision && (
                        <p className="mt-1 text-xs text-red-300">{t('catalogMerge.needsPair')}</p>
                      )}
                    </div>
                    <Dropdown
                      size="sm"
                      clearable={false}
                      value={pairs[row.source.id] ?? KEEP_SEPARATE}
                      options={rowOptions(row)}
                      renderOption={(option) => {
                        const item = row.candidates.find((candidate) => candidate.id === option.value);
                        return item ? <MergeFilamentOption filament={item} likelySame={item.likely_same} /> : option.label;
                      }}
                      onChange={(value) => setPairs((current) => ({ ...current, [row.source.id]: Number(value) }))}
                    />
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="flex flex-wrap justify-end gap-3 border-t border-white/10 p-6">
          <button
            type="button"
            onClick={onClose}
            disabled={mergeMutation.isPending}
            className="rounded-xl bg-white/10 px-4 py-2 text-white transition-all hover:bg-white/20 disabled:opacity-50"
          >
            {t('catalogMerge.cancel')}
          </button>
          <button
            type="button"
            onClick={() => mergeMutation.mutate()}
            disabled={
              !preview || preview.source_represented || unresolved.length > 0 || mergeMutation.isPending
            }
            className="flex items-center gap-2 rounded-xl bg-purple-600 px-4 py-2 text-white transition-all hover:bg-purple-700 disabled:opacity-50"
          >
            {mergeMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <GitMerge className="h-4 w-4" />}
            <span>{t('catalogMerge.mergeBrand', { duplicate: source.name, name: target?.name ?? '' })}</span>
          </button>
        </div>
      </div>
    </ModalOverlay>
  );
};
