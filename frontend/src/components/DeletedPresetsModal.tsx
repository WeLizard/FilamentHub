/** Resolve presets removed locally in OrcaSlicer. */

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { CheckCircle2, RotateCcw, SkipForward, Trash2, X } from 'lucide-react';
import { useInfiniteQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';

import { orcaslicerDeletedPresetsAPI } from '../api/client';
import type { Notification } from '../types/api';
import { translateApiError } from '../utils/translateApiError';
import { ModalOverlay } from './ModalOverlay';

interface DeletedPresetsModalProps {
  isOpen: boolean;
  onClose: () => void;
  notification: Notification;
}

type DecisionAction = 'restore' | 'delete' | 'skip';

export const DeletedPresetsModal: React.FC<DeletedPresetsModalProps> = ({
  isOpen,
  onClose,
  notification,
}) => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [selectedPresetIds, setSelectedPresetIds] = useState<Set<number>>(new Set());
  const [action, setAction] = useState<DecisionAction | null>(null);
  const [applyToAll, setApplyToAll] = useState(false);
  const [saveRule, setSaveRule] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const queryKey = ['notification', notification.id, 'deleted-presets'] as const;

  const decisionsQuery = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam, signal }) => orcaslicerDeletedPresetsAPI.list(
      notification.id,
      { limit: 50, cursor: pageParam },
      signal,
    ),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    enabled: isOpen,
  });
  const decisions = useMemo(
    () => decisionsQuery.data?.pages.flatMap((page) => page.items) ?? [],
    [decisionsQuery.data],
  );
  const summary = decisionsQuery.data?.pages[decisionsQuery.data.pages.length - 1];

  useEffect(() => {
    if (!isOpen) {
      setSelectedPresetIds(new Set());
      setAction(null);
      setApplyToAll(false);
      setSaveRule(false);
      setSuccessMessage(null);
    }
  }, [isOpen]);

  useEffect(() => {
    const loadedIds = new Set(decisions.map((item) => item.preset_id));
    setSelectedPresetIds((current) => new Set([...current].filter((id) => loadedIds.has(id))));
  }, [decisions]);

  const mutation = useMutation({
    mutationFn: () => orcaslicerDeletedPresetsAPI.handleAction(notification.id, {
      action: action!,
      preset_ids: applyToAll ? null : [...selectedPresetIds],
      apply_to_all: applyToAll,
      save_rule: saveRule,
    }),
    onSuccess: async (response) => {
      setSuccessMessage(t(`deletedPresetsModal.success_message_${response.action}_other`, {
        count: response.total_count,
      }));
      setSelectedPresetIds(new Set());
      setAction(null);
      setApplyToAll(false);
      setSaveRule(false);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey }),
        queryClient.invalidateQueries({ queryKey: ['notification', notification.id], exact: true }),
        queryClient.invalidateQueries({ queryKey: ['notifications'] }),
      ]);
    },
  });

  if (!isOpen) return null;

  const togglePreset = (presetId: number) => {
    setSelectedPresetIds((current) => {
      const next = new Set(current);
      if (next.has(presetId)) next.delete(presetId);
      else next.add(presetId);
      return next;
    });
  };
  const allLoadedSelected = decisions.length > 0
    && decisions.every((item) => selectedPresetIds.has(item.preset_id));
  const canApply = Boolean(action) && (applyToAll || selectedPresetIds.size > 0);
  const errorMessage = mutation.error
    ? translateApiError(t, (mutation.error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail, t('deletedPresetsModal.error_unknown'))
    : null;

  const actions: Array<{ value: DecisionAction; icon: ReactNode }> = [
    { value: 'restore', icon: <RotateCcw className="h-4 w-4" /> },
    { value: 'delete', icon: <Trash2 className="h-4 w-4" /> },
    { value: 'skip', icon: <SkipForward className="h-4 w-4" /> },
  ];

  return (
    <ModalOverlay onClose={onClose} closeOnOverlayClick={!mutation.isPending}>
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="deleted-presets-title"
        className="flex max-h-[calc(100dvh-2rem)] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-white/20 bg-gradient-to-br from-purple-900 to-indigo-900 shadow-xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3 border-b border-white/10 p-4 sm:p-6">
          <div className="min-w-0">
            <h3 id="deleted-presets-title" className="text-xl font-bold text-white">{t('deletedPresetsModal.title')}</h3>
            <p className="mt-1 text-sm text-gray-300">
              {t('deletedPresetsModal.subtitle', { count: summary?.remaining_count ?? 0 })}
            </p>
          </div>
          <button type="button" onClick={onClose} disabled={mutation.isPending} aria-label={t('deletedPresetsModal.close_button')} className="flex min-h-11 min-w-11 items-center justify-center rounded-lg text-gray-300 hover:bg-white/10 hover:text-white disabled:opacity-50">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 sm:p-6">
          {successMessage && <p className="mb-4 rounded-lg border border-green-500/50 bg-green-500/20 p-3 text-sm text-green-200">{successMessage}</p>}
          {decisionsQuery.isPending ? (
            <p className="text-sm text-gray-300">{t('deletedPresetsModal.loading')}</p>
          ) : decisionsQuery.isError && !decisionsQuery.data ? (
            <div role="alert" className="space-y-3 rounded-lg border border-red-500/40 bg-red-500/10 p-4 text-red-200">
              <p>{t('deletedPresetsModal.load_error')}</p>
              <button type="button" onClick={() => void decisionsQuery.refetch()} className="min-h-11 rounded-lg bg-white/10 px-4 py-2 font-medium hover:bg-white/20">{t('deletedPresetsModal.retry')}</button>
            </div>
          ) : (
            <>
              <dl className="mb-4 grid gap-2 rounded-lg bg-white/5 p-3 text-sm sm:grid-cols-3">
                <div><dt className="text-gray-300">{t('deletedPresetsModal.stats_total')}</dt><dd className="font-semibold text-white">{summary?.remaining_count ?? 0}</dd></div>
                <div><dt className="text-gray-300">{t('deletedPresetsModal.stats_created')}</dt><dd className="font-semibold text-blue-300">{summary?.created_count ?? 0}</dd></div>
                <div><dt className="text-gray-300">{t('deletedPresetsModal.stats_saved')}</dt><dd className="font-semibold text-green-300">{summary?.saved_count ?? 0}</dd></div>
              </dl>

              {summary?.remaining_count === 0 ? (
                <p className="rounded-lg bg-white/5 p-4 text-sm text-gray-300">{t('deletedPresetsModal.empty')}</p>
              ) : (
                <>
                  <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                    <h4 className="text-sm font-semibold text-white">{t('deletedPresetsModal.select_presets')}</h4>
                    <button type="button" disabled={applyToAll} onClick={() => setSelectedPresetIds(allLoadedSelected ? new Set() : new Set(decisions.map((item) => item.preset_id)))} className="min-h-11 rounded-lg px-3 text-sm text-purple-200 hover:bg-white/10 disabled:opacity-50">
                      {allLoadedSelected ? t('deletedPresetsModal.deselect_all') : t('deletedPresetsModal.select_loaded')}
                    </button>
                  </div>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {decisions.map((preset) => (
                      <label key={preset.id} className="flex min-h-11 cursor-pointer items-start gap-2 rounded-lg bg-white/5 p-3 hover:bg-white/10">
                        <input type="checkbox" disabled={applyToAll} checked={applyToAll || selectedPresetIds.has(preset.preset_id)} onChange={() => togglePreset(preset.preset_id)} className="mt-1 h-5 w-5 shrink-0" />
                        <span className="min-w-0 text-sm text-white">
                          <span className="break-words font-medium">{preset.preset_name}</span>
                          {preset.bundle_preset_name && <span className="mt-1 block break-words text-xs text-gray-300">{t('deletedPresetsModal.orcaslicer_prefix')} {preset.bundle_preset_name}</span>}
                        </span>
                      </label>
                    ))}
                  </div>
                  {decisionsQuery.hasNextPage && (
                    <button type="button" onClick={() => void decisionsQuery.fetchNextPage()} disabled={decisionsQuery.isFetchingNextPage} className="mt-3 min-h-11 rounded-lg bg-white/10 px-4 py-2 text-sm font-medium text-white hover:bg-white/20 disabled:opacity-50">
                      {decisionsQuery.isFetchingNextPage ? t('deletedPresetsModal.loading_more') : t('deletedPresetsModal.load_more')}
                    </button>
                  )}
                  {decisionsQuery.isFetchNextPageError && <div role="alert" className="mt-3 flex flex-wrap items-center gap-3 text-sm text-red-200"><span>{t('deletedPresetsModal.load_more_error')}</span><button type="button" onClick={() => void decisionsQuery.fetchNextPage()} className="min-h-11 rounded-lg bg-white/10 px-4">{t('deletedPresetsModal.retry')}</button></div>}
                </>
              )}

              {(summary?.remaining_count ?? 0) > 0 && (
                <>
                  <label className="mt-5 flex min-h-11 items-center gap-3 rounded-lg border border-purple-300/30 p-3 text-sm text-white">
                    <input type="checkbox" checked={applyToAll} onChange={(event) => setApplyToAll(event.target.checked)} className="h-5 w-5 shrink-0" />
                    <span>{t('deletedPresetsModal.apply_all_remaining', { count: summary?.remaining_count ?? 0 })}</span>
                  </label>
                  <div className="mt-4 grid gap-3 sm:grid-cols-3">
                    {actions.map(({ value, icon }) => (
                      <button key={value} type="button" onClick={() => setAction(value)} className={`min-h-11 rounded-lg border p-3 text-left text-sm text-white ${action === value ? 'border-white/60 bg-purple-600' : 'border-transparent bg-white/10 hover:bg-white/20'}`}>
                        <span className="flex items-center gap-2 font-semibold">{icon}{t(`deletedPresetsModal.action_${value}_label`)}</span>
                        <span className="mt-1 block text-xs text-gray-200">{t(`deletedPresetsModal.action_${value}_short`)}</span>
                      </button>
                    ))}
                  </div>
                  {action && <label className="mt-4 flex min-h-11 items-center gap-3 text-sm text-gray-200"><input type="checkbox" checked={saveRule} onChange={(event) => setSaveRule(event.target.checked)} className="h-5 w-5" />{t('deletedPresetsModal.save_rule_checkbox')}</label>}
                </>
              )}
            </>
          )}
          {errorMessage && <p role="alert" className="mt-4 text-sm text-red-200">{t('deletedPresetsModal.error_handling_action', { message: errorMessage })}</p>}
        </div>

        <div className="flex flex-wrap justify-end gap-3 border-t border-white/10 p-4 sm:p-6">
          <button type="button" onClick={onClose} disabled={mutation.isPending} className="min-h-11 rounded-xl bg-white/10 px-5 py-2.5 text-white hover:bg-white/20 disabled:opacity-50">{t('deletedPresetsModal.close_button')}</button>
          {(summary?.remaining_count ?? 0) > 0 && <button type="button" onClick={() => mutation.mutate()} disabled={!canApply || mutation.isPending} className="flex min-h-11 items-center gap-2 rounded-xl bg-purple-600 px-5 py-2.5 text-white hover:bg-purple-700 disabled:opacity-50"><CheckCircle2 className="h-4 w-4" />{mutation.isPending ? t('deletedPresetsModal.executing_button') : t('deletedPresetsModal.apply_button')}</button>}
        </div>
      </div>
    </ModalOverlay>
  );
};
