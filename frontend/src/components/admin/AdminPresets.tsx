/** Компонент для модерации пресетов */

import { lazy, Suspense, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Settings, CheckCircle, XCircle, Pencil, Trash2, Sparkles, Loader2 } from 'lucide-react';
import { adminAPI, presetsAPI } from '../../api/client';
import { toast } from '../Toast';
import type { Preset } from '../../types/api';
const CreatePresetModal = lazy(() =>
  import('../CreatePresetModal').then(m => ({ default: m.CreatePresetModal }))
);
import { translateApiError } from '../../utils/translateApiError';

type ModerationFlag = {
  code?: string;
  params?: Record<string, unknown>;
  severity?: string;
};

type ModerationReasonPayload = {
  code?: string;
  params?: Record<string, unknown>;
  flags?: ModerationFlag[];
};

const parseModerationReason = (value: string | null | undefined): ModerationReasonPayload | null => {
  if (!value) {
    return null;
  }

  try {
    const parsed = JSON.parse(value) as unknown;
    if (!parsed || typeof parsed !== 'object') {
      return null;
    }
    return parsed as ModerationReasonPayload;
  } catch {
    return null;
  }
};

export function AdminPresets() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [page, _setPage] = useState(1);
  const [editingPreset, setEditingPreset] = useState<Preset | null>(null);

  // Загрузка пресетов ожидающих модерации
  const { data: pendingPresets, isLoading } = useQuery({
    queryKey: ['admin-pending-presets', page],
    queryFn: () => adminAPI.listPendingPresets({ page, size: 20 }),
  });

  // Одобрение пресета
  const approveMutation = useMutation({
    mutationFn: (presetId: number) => adminAPI.approvePreset(presetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-pending-presets'] });
    },
  });

  // Отклонение пресета
  const rejectMutation = useMutation({
    mutationFn: ({ presetId, reason }: { presetId: number; reason: string }) =>
      adminAPI.rejectPreset(presetId, reason),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-pending-presets'] });
    },
  });

  // Обогащение черновиков-пресетов дефолтами по материалу (batch)
  const enrichMutation = useMutation({
    mutationFn: () => adminAPI.enrichDraftPresets(),
    onSuccess: (stats) => {
      toast.success(
        t('adminPresets.enrichResult', {
          enriched: stats.enriched,
          total: stats.total,
          skipped: stats.skipped,
          errors: stats.errors,
        }),
      );
      queryClient.invalidateQueries({ queryKey: ['admin-pending-presets'] });
    },
    onError: (error) => {
      const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      toast.error(translateApiError(t, detail, t('adminPresets.enrichError')));
    },
  });

  // Удаление пресета (жесткое удаление для явно мусорных/некорректных пресетов)
  const deleteMutation = useMutation({
    mutationFn: (presetId: number) => presetsAPI.delete(presetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-pending-presets'] });
    },
  });

  if (isLoading) {
    return <div className="text-center py-12 text-gray-400">{t('adminPresets.loading')}</div>;
  }

  const presets = pendingPresets || [];

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h2 className="text-2xl font-bold text-white mb-2">{t('adminPresets.title')}</h2>
          <p className="text-gray-400">{t('adminPresets.pending')}: {presets.length}</p>
        </div>
        <button
          onClick={() => enrichMutation.mutate()}
          disabled={enrichMutation.isPending}
          title={t('adminPresets.enrichHint')}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-white/20 text-sm text-white hover:bg-white/10 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {enrichMutation.isPending ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Sparkles className="w-4 h-4 text-purple-300" />
          )}
          {enrichMutation.isPending ? t('adminPresets.enrichButtonPending') : t('adminPresets.enrichButton')}
        </button>
      </div>

      {presets.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <Settings className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p>{t('adminPresets.empty')}</p>
        </div>
      ) : (
        <div className="space-y-4">
          {presets.map((preset) => {
            const moderationReason = parseModerationReason(preset.moderation_reason);
            const moderationFlags = moderationReason?.flags ?? [];

            return (
              <div
                key={preset.id}
                className="bg-white/5 rounded-xl p-4 border border-white/10 hover:border-white/20 transition-all"
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center space-x-3 mb-2">
                      <Settings className="w-5 h-5 text-purple-400" />
                      <h3 className="text-lg font-semibold text-white">{preset.name}</h3>
                    </div>
                    {preset.description && (
                      <p className="text-sm text-gray-400 mb-2">{preset.description}</p>
                    )}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm text-gray-400">
                      <div>{t('adminPresets.nozzle')}: {preset.extruder_temp}°C</div>
                      <div>{t('adminPresets.bed')}: {preset.bed_temp}°C</div>
                      <div>{t('adminPresets.speed')}: {preset.print_speed}mm/s</div>
                      <div>{t('adminPresets.usages')}: {preset.usage_count}</div>
                    </div>
                    <p className="text-xs text-gray-500 mt-2">
                      {t('adminPresets.created')}: {new Date(preset.created_at).toLocaleString('ru-RU')}
                    </p>
                    {moderationReason?.code && (
                      <div className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
                        <p className="text-xs font-medium text-amber-200">
                          {translateApiError(t, moderationReason, t('adminPresets.manualReviewFallback'))}
                        </p>
                        {moderationFlags.length > 0 && (
                          <ul className="mt-2 space-y-1">
                            {moderationFlags.map((flag, index) => (
                              <li key={`${preset.id}-flag-${index}`} className="text-xs text-amber-100/90">
                                • {translateApiError(t, flag, t('adminPresets.flagFallback'))}
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-2 ml-4 shrink-0">
                    <button
                      onClick={() => setEditingPreset(preset)}
                      className="flex items-center justify-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-all"
                    >
                      <Pencil className="w-4 h-4" />
                      <span>{t('adminPresets.edit')}</span>
                    </button>
                    <button
                      onClick={() => {
                        if (confirm(t('adminPresets.confirmApprove', { name: preset.name }))) {
                          approveMutation.mutate(preset.id);
                        }
                      }}
                      disabled={approveMutation.isPending}
                      className="flex items-center justify-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg transition-all disabled:opacity-50"
                    >
                      <CheckCircle className="w-4 h-4" />
                      <span>{t('adminPresets.approve')}</span>
                    </button>
                    <button
                      onClick={() => {
                        const reason = prompt(t('adminPresets.rejectReasonPrompt'));
                        if (reason && reason.trim()) {
                          rejectMutation.mutate({ presetId: preset.id, reason: reason.trim() });
                        }
                      }}
                      disabled={rejectMutation.isPending}
                      className="flex items-center justify-center gap-2 px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition-all disabled:opacity-50"
                    >
                      <XCircle className="w-4 h-4" />
                      <span>{t('adminPresets.reject')}</span>
                    </button>
                    <button
                      onClick={() => {
                        if (confirm(t('adminPresets.confirmDelete', { name: preset.name }))) {
                          deleteMutation.mutate(preset.id);
                        }
                      }}
                      disabled={deleteMutation.isPending}
                      className="flex items-center justify-center gap-2 px-4 py-2 bg-red-900/70 hover:bg-red-900 text-white rounded-lg transition-all disabled:opacity-50 border border-red-500/40"
                    >
                      <Trash2 className="w-4 h-4" />
                      <span>{t('adminPresets.delete')}</span>
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <Suspense fallback={null}>
        <CreatePresetModal
          isOpen={!!editingPreset}
          onClose={() => {
            setEditingPreset(null);
            queryClient.invalidateQueries({ queryKey: ['admin-pending-presets'] });
          }}
          preset={editingPreset}
        />
      </Suspense>
    </div>
  );
}
