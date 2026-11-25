/** Pick another colour of the preset's material and make a private copy for it. */

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Loader2, Search, X } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { filamentsAPI, presetsAPI } from '../api/client';
import type { Preset } from '../types/api';
import { normalizeFilamentColor } from '../utils/calculatorMaterialColors';
import { colorLabel, colorVariantsQueryKey } from '../utils/presetColorCopy';
import { translateApiError } from '../utils/translateApiError';
import { ModalOverlay } from './ModalOverlay';
import { toast } from './Toast';

// Past this many colours a search field is quicker than scanning swatches.
const SEARCH_FROM = 12;

interface PresetColorCopyDialogProps {
  source: Pick<Preset, 'id' | 'name' | 'filament_id'>;
  /** Colour the source preset has now, shown for orientation. */
  currentColor?: string | null;
  /** A colour the person already picked elsewhere, e.g. while changing the material. */
  initialSelectedId?: number | null;
  hasUnsavedChanges?: boolean;
  onClose: () => void;
  onCopied: (copy: Preset) => void;
}

export function PresetColorCopyDialog({
  source,
  currentColor,
  initialSelectedId = null,
  hasUnsavedChanges = false,
  onClose,
  onCopied,
}: PresetColorCopyDialogProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<number | null>(initialSelectedId);
  const [search, setSearch] = useState('');

  const variants = useQuery({
    queryKey: colorVariantsQueryKey(source.filament_id),
    queryFn: () => filamentsAPI.colorVariants(source.filament_id!),
    enabled: !!source.filament_id,
    staleTime: 60_000,
  });

  const shown = useMemo(() => {
    const items = variants.data ?? [];
    const needle = search.trim().toLocaleLowerCase();
    if (!needle) return items;
    return items.filter((variant) =>
      [variant.color_name, variant.color_hex, variant.name]
        .some((value) => value?.toLocaleLowerCase().includes(needle)),
    );
  }, [variants.data, search]);

  const copy = useMutation({
    mutationFn: (filamentId: number) => presetsAPI.copyForColor(source.id, filamentId),
    onSuccess: ({ preset, created }) => {
      queryClient.invalidateQueries({ queryKey: ['user-presets'] });
      queryClient.invalidateQueries({ queryKey: ['presets'] });
      toast.success(t(created ? 'presetColorCopy.created' : 'presetColorCopy.existing'), 6000);
      onCopied(preset);
    },
  });

  const copyError = copy.error as { response?: { data?: { detail?: unknown } } } | null;
  const loadError = variants.error as { response?: { data?: { detail?: unknown } } } | null;

  return (
    <ModalOverlay onClose={onClose} className="!bg-black/60">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="preset-color-copy-title"
        className="flex max-h-[85vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-white/20 bg-gray-900 shadow-2xl"
      >
        <div className="flex items-start justify-between gap-4 border-b border-white/10 p-5">
          <div className="min-w-0">
            <h2 id="preset-color-copy-title" className="text-lg font-semibold text-white">
              {t('presetColorCopy.title')}
            </h2>
            <p className="mt-1 text-sm leading-5 text-gray-300">
              {t('presetColorCopy.description', { name: source.name })}
            </p>
            {currentColor && (
              <p className="mt-1 text-xs text-gray-400">
                {t('presetColorCopy.currentColor', { color: currentColor })}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('presetColorCopy.cancel')}
            className="rounded-lg p-1.5 text-gray-400 transition hover:bg-white/10 hover:text-white"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {hasUnsavedChanges && (
            <p className="mb-4 rounded-lg border border-amber-300/25 bg-amber-400/10 px-3 py-2 text-xs text-amber-100">
              {t('presetColorCopy.unsavedChanges')}
            </p>
          )}

          {(variants.data?.length ?? 0) > SEARCH_FROM && (
            <label className="relative mb-3 block">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400" />
              <input
                type="search"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={t('presetColorCopy.searchPlaceholder')}
                aria-label={t('presetColorCopy.searchPlaceholder')}
                className="w-full rounded-lg border border-white/20 bg-white/10 py-2 pl-9 pr-3 text-sm text-white placeholder-gray-400 focus:border-transparent focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </label>
          )}

          {variants.isLoading && (
            <p className="flex items-center gap-2 text-sm text-gray-300">
              <Loader2 className="h-4 w-4 animate-spin" />
              {t('presetColorCopy.loading')}
            </p>
          )}
          {variants.isError && (
            <p className="text-sm text-red-300">
              {translateApiError(t, loadError?.response?.data?.detail, t('presetColorCopy.loadError'))}
            </p>
          )}
          {variants.isSuccess && variants.data.length === 0 && (
            <p className="text-sm text-gray-300">{t('presetColorCopy.empty')}</p>
          )}
          {variants.isSuccess && variants.data.length > 0 && shown.length === 0 && (
            <p className="text-sm text-gray-300">{t('presetColorCopy.noMatch')}</p>
          )}

          {shown.length > 0 && (
            <div
              role="radiogroup"
              aria-label={t('presetColorCopy.title')}
              className="grid grid-cols-[repeat(auto-fill,minmax(9.5rem,1fr))] gap-2"
            >
              {shown.map((variant) => {
                const selected = variant.id === selectedId;
                const swatch = normalizeFilamentColor(variant.color_hex);
                return (
                  <button
                    key={variant.id}
                    type="button"
                    role="radio"
                    aria-checked={selected}
                    onClick={() => setSelectedId(variant.id)}
                    title={variant.color_name ? `${variant.name} · ${variant.color_name}` : variant.name}
                    className={`flex min-w-0 items-center gap-2.5 rounded-lg border px-3 py-2 text-left text-sm transition ${
                      selected
                        ? 'border-purple-400 bg-purple-500/20 text-white'
                        : 'border-white/15 bg-white/5 text-gray-200 hover:border-white/30 hover:bg-white/10'
                    }`}
                  >
                    <span
                      aria-hidden="true"
                      className="h-5 w-5 shrink-0 rounded-full border border-white/40 shadow-sm"
                      style={swatch
                        ? { backgroundColor: swatch }
                        : { background: 'repeating-linear-gradient(45deg,#4b5563 0 3px,#1f2937 3px 6px)' }}
                    />
                    <span className="min-w-0 flex-1 truncate">{colorLabel(variant)}</span>
                    {selected && <Check className="h-4 w-4 shrink-0 text-purple-200" />}
                  </button>
                );
              })}
            </div>
          )}

          {copy.isError && (
            <p className="mt-4 rounded-lg border border-red-500/30 bg-red-500/15 px-3 py-2 text-sm text-red-200">
              {translateApiError(t, copyError?.response?.data?.detail)}
            </p>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-end gap-3 border-t border-white/10 p-5">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl px-4 py-2.5 text-sm text-gray-300 transition hover:bg-white/10 hover:text-white"
          >
            {t('presetColorCopy.cancel')}
          </button>
          <button
            type="button"
            disabled={selectedId === null || copy.isPending}
            onClick={() => selectedId !== null && copy.mutate(selectedId)}
            className="flex items-center gap-2 rounded-xl bg-purple-600 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-purple-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {copy.isPending && <Loader2 className="h-4 w-4 animate-spin" />}
            {t('presetColorCopy.create')}
          </button>
        </div>
      </div>
    </ModalOverlay>
  );
}
