/** Preset version history — timeline + human-readable diff + restore.
 *
 * Unobtrusive addition: opened from a preset's detail view, not a top-level
 * route. Lets the owner browse versions, compare a selected version against
 * the latest, and restore.
 */

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { ModalOverlay } from '../ModalOverlay';
import { toast } from '../Toast';
import { translateApiError } from '../../utils/translateApiError';
import {
  presetVersionsAPI,
  type PresetVersionListItem,
} from '../../api/client';

interface Props {
  presetId: number;
  /** Whether the current user may restore (owner/admin). */
  canRestore?: boolean;
  onClose: () => void;
}

const SOURCE_COLORS: Record<string, string> = {
  web_edit: 'bg-blue-500/15 text-blue-300',
  orca_sync: 'bg-purple-500/15 text-purple-300',
  restore: 'bg-amber-500/15 text-amber-300',
  admin: 'bg-red-500/15 text-red-300',
  enrichment: 'bg-emerald-500/15 text-emerald-300',
  migration: 'bg-gray-500/15 text-gray-400',
};

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return iso;
  }
}

export const PresetHistoryModal: React.FC<Props> = ({ presetId, canRestore = false, onClose }) => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const [labeledOnly, setLabeledOnly] = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [confirmRestore, setConfirmRestore] = useState(false);
  const [editingLabel, setEditingLabel] = useState(false);
  const [labelValue, setLabelValue] = useState('');
  const [labelDescValue, setLabelDescValue] = useState('');

  const versionsQuery = useQuery({
    queryKey: ['preset-versions', presetId, labeledOnly],
    queryFn: () => presetVersionsAPI.list(presetId, { labeled_only: labeledOnly, limit: 100 }),
  });

  const versions = versionsQuery.data?.items ?? [];
  const latest = useMemo(
    () => versions.reduce<PresetVersionListItem | null>(
      (acc, v) => (acc === null || v.version_number > acc.version_number ? v : acc),
      null,
    ),
    [versions],
  );

  // Effective selection: explicit, else the second-newest (so the modal opens
  // showing "what changed in the latest version").
  const effectiveSelectedId =
    selectedId ??
    (versions.length > 1
      ? [...versions].sort((a, b) => b.version_number - a.version_number)[1]?.id ?? null
      : null);

  const selected = versions.find((v) => v.id === effectiveSelectedId) ?? null;
  const isLatestSelected = selected !== null && latest !== null && selected.id === latest.id;

  const diffQuery = useQuery({
    queryKey: ['preset-version-diff', presetId, selected?.id, latest?.id],
    queryFn: () => presetVersionsAPI.diff(presetId, selected!.id, latest!.id),
    enabled: selected !== null && latest !== null && selected.id !== latest.id,
  });

  const restoreMutation = useMutation({
    mutationFn: (versionId: number) => presetVersionsAPI.restore(presetId, versionId),
    onSuccess: () => {
      toast.success(t('presetVersions.restore.success'));
      queryClient.invalidateQueries({ queryKey: ['preset-versions', presetId] });
      queryClient.invalidateQueries({ queryKey: ['presets'] });
      queryClient.invalidateQueries({ queryKey: ['preset', presetId] });
      setConfirmRestore(false);
      setSelectedId(null);
    },
    onError: (err: any) => {
      toast.error(translateApiError(t, err?.response?.data?.detail, t('common.error')));
      setConfirmRestore(false);
    },
  });

  const labelMutation = useMutation({
    mutationFn: ({ versionId, label, description }: { versionId: number; label: string; description: string | null }) =>
      presetVersionsAPI.setLabel(presetId, versionId, label, description),
    onSuccess: () => {
      toast.success(t('presetVersions.label.saved'));
      queryClient.invalidateQueries({ queryKey: ['preset-versions', presetId] });
      setEditingLabel(false);
    },
    onError: (err: any) => {
      toast.error(translateApiError(t, err?.response?.data?.detail, t('common.error')));
    },
  });

  const startEditLabel = (item: PresetVersionListItem) => {
    setLabelValue(item.label);
    setLabelDescValue(item.label_description ?? '');
    setEditingLabel(true);
  };

  return (
    <ModalOverlay onClose={onClose}>
      <div className="bg-gray-900 rounded-2xl border border-white/20 w-full max-w-4xl max-h-[85vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
          <h2 className="text-lg font-semibold text-white">{t('presetVersions.title')}</h2>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
              <input
                type="checkbox"
                checked={labeledOnly}
                onChange={(e) => setLabeledOnly(e.target.checked)}
                className="accent-purple-500"
              />
              {t('presetVersions.timeline.labeledOnly')}
            </label>
            <button onClick={onClose} className="text-gray-400 hover:text-white text-xl leading-none">×</button>
          </div>
        </div>

        <div className="flex flex-1 min-h-0">
          {/* Timeline */}
          <div className="w-2/5 border-r border-white/10 overflow-y-auto">
            {versionsQuery.isLoading && (
              <div className="p-6 text-gray-500 text-sm">{t('common.loading')}</div>
            )}
            {!versionsQuery.isLoading && versions.length === 0 && (
              <div className="p-6 text-gray-500 text-sm">{t('presetVersions.timeline.empty')}</div>
            )}
            <ul>
              {[...versions]
                .sort((a, b) => b.version_number - a.version_number)
                .map((v) => {
                  const isSel = v.id === effectiveSelectedId;
                  const isLat = latest !== null && v.id === latest.id;
                  return (
                    <li key={v.id}>
                      <button
                        onClick={() => {
                          setSelectedId(v.id);
                          setEditingLabel(false);
                        }}
                        className={`w-full text-left px-4 py-3 border-b border-white/5 transition-colors ${
                          isSel ? 'bg-purple-500/10' : 'hover:bg-white/5'
                        }`}
                      >
                        <div className="flex items-center gap-2 mb-1">
                          <span className="text-white font-medium text-sm">v{v.version_number}</span>
                          {isLat && (
                            <span className="text-[10px] uppercase tracking-wide text-emerald-400">
                              {t('presetVersions.timeline.current')}
                            </span>
                          )}
                          <span
                            className={`text-[10px] px-1.5 py-0.5 rounded ${
                              SOURCE_COLORS[v.change_source] ?? SOURCE_COLORS.migration
                            }`}
                          >
                            {t(`presetVersions.source.${v.change_source}`, v.change_source)}
                          </span>
                          {v.squash_count > 1 && (
                            <span className="text-[10px] text-gray-500">
                              {t('presetVersions.squash.editedNtimes', { count: v.squash_count })}
                            </span>
                          )}
                        </div>
                        {v.label && (
                          <div className="text-xs text-amber-300 font-medium">🏷 {v.label}</div>
                        )}
                        <div className="text-[11px] text-gray-500">{formatDate(v.created_at)}</div>
                      </button>
                    </li>
                  );
                })}
            </ul>
          </div>

          {/* Diff panel */}
          <div className="flex-1 overflow-y-auto p-5">
            {selected === null && (
              <div className="text-gray-500 text-sm">{t('presetVersions.diff.selectPrompt')}</div>
            )}

            {/* Label management for the selected version (owner/admin) */}
            {selected !== null && canRestore && (
              <div className="mb-4 pb-4 border-b border-white/10">
                {editingLabel ? (
                  <div className="space-y-2">
                    <input
                      type="text"
                      value={labelValue}
                      onChange={(e) => setLabelValue(e.target.value)}
                      maxLength={120}
                      placeholder={t('presetVersions.label.placeholder')}
                      className="w-full bg-white/5 border border-white/15 rounded-lg px-3 py-1.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                    />
                    <textarea
                      value={labelDescValue}
                      onChange={(e) => setLabelDescValue(e.target.value)}
                      maxLength={2000}
                      rows={2}
                      placeholder={t('presetVersions.label.descPlaceholder')}
                      className="w-full bg-white/5 border border-white/15 rounded-lg px-3 py-1.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 resize-none"
                    />
                    <div className="flex gap-2">
                      <button
                        onClick={() =>
                          labelMutation.mutate({
                            versionId: selected.id,
                            label: labelValue.trim(),
                            description: labelDescValue.trim() || null,
                          })
                        }
                        disabled={labelMutation.isPending || !labelValue.trim()}
                        className="px-3 py-1.5 bg-purple-600 hover:bg-purple-500 text-white text-xs font-medium rounded-lg disabled:opacity-50"
                      >
                        {t('presetVersions.label.save')}
                      </button>
                      <button
                        onClick={() => setEditingLabel(false)}
                        className="px-3 py-1.5 bg-white/10 hover:bg-white/20 text-gray-200 text-xs rounded-lg"
                      >
                        {t('common.cancel')}
                      </button>
                    </div>
                  </div>
                ) : selected.label ? (
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="text-sm text-amber-300 font-medium">🏷 {selected.label}</div>
                      {selected.label_description && (
                        <div className="text-xs text-gray-400 mt-0.5">{selected.label_description}</div>
                      )}
                    </div>
                    <div className="flex gap-1 shrink-0">
                      <button
                        onClick={() => startEditLabel(selected)}
                        className="px-2 py-1 text-xs text-gray-300 hover:text-white hover:bg-white/10 rounded"
                      >
                        {t('presetVersions.label.edit')}
                      </button>
                      <button
                        onClick={() =>
                          labelMutation.mutate({ versionId: selected.id, label: '', description: null })
                        }
                        disabled={labelMutation.isPending}
                        className="px-2 py-1 text-xs text-gray-400 hover:text-red-300 hover:bg-white/10 rounded disabled:opacity-50"
                      >
                        {t('presetVersions.label.remove')}
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    onClick={() => startEditLabel(selected)}
                    className="text-xs text-gray-400 hover:text-white transition-colors"
                  >
                    {t('presetVersions.label.add')}
                  </button>
                )}
              </div>
            )}

            {selected !== null && isLatestSelected && (
              <div className="text-gray-500 text-sm">{t('presetVersions.diff.isCurrent')}</div>
            )}

            {selected !== null && !isLatestSelected && (
              <>
                <div className="text-xs text-gray-400 mb-3">
                  {t('presetVersions.diff.comparing', {
                    from: selected.version_number,
                    to: latest?.version_number,
                  })}
                </div>

                {diffQuery.isLoading && (
                  <div className="text-gray-500 text-sm">{t('common.loading')}</div>
                )}

                {diffQuery.data && (
                  <div className="space-y-1.5">
                    {diffQuery.data.changes.length === 0 &&
                      diffQuery.data.unmapped_changes.length === 0 && (
                        <div className="text-gray-500 text-sm">{t('presetVersions.diff.noChanges')}</div>
                      )}

                    {diffQuery.data.changes.map((c) => (
                      <div key={c.key} className="text-sm flex flex-wrap items-baseline gap-2">
                        <span className="text-gray-300 min-w-[180px]">{c.label}</span>
                        <span className="text-red-400 line-through">
                          {c.old ?? '—'}
                          {c.unit && c.old != null ? ` ${c.unit}` : ''}
                        </span>
                        <span className="text-gray-500">→</span>
                        <span className="text-emerald-400">
                          {c.new ?? '—'}
                          {c.unit && c.new != null ? ` ${c.unit}` : ''}
                        </span>
                      </div>
                    ))}

                    {diffQuery.data.unmapped_changes.length > 0 && (
                      <details className="mt-3">
                        <summary className="text-xs text-gray-500 cursor-pointer">
                          {t('presetVersions.diff.technicalFields', {
                            count: diffQuery.data.unmapped_changes.length,
                          })}
                        </summary>
                        <div className="mt-2 space-y-1">
                          {diffQuery.data.unmapped_changes.map((c) => (
                            <div key={c.key} className="text-[11px] text-gray-500 flex flex-wrap gap-2">
                              <span className="font-mono min-w-[180px]">{c.key}</span>
                              <span className="text-red-400/70 line-through">{c.old ?? '—'}</span>
                              <span>→</span>
                              <span className="text-emerald-400/70">{c.new ?? '—'}</span>
                            </div>
                          ))}
                        </div>
                      </details>
                    )}
                  </div>
                )}

                {canRestore && (
                  <div className="mt-6 pt-4 border-t border-white/10">
                    {!confirmRestore ? (
                      <button
                        onClick={() => setConfirmRestore(true)}
                        className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white text-sm font-medium rounded-lg transition-colors"
                      >
                        {t('presetVersions.restore.button', { version: selected.version_number })}
                      </button>
                    ) : (
                      <div className="space-y-2">
                        <p className="text-sm text-gray-300">
                          {t('presetVersions.restore.confirmBody', { version: selected.version_number })}
                        </p>
                        <div className="flex gap-2">
                          <button
                            onClick={() => restoreMutation.mutate(selected.id)}
                            disabled={restoreMutation.isPending}
                            className="px-4 py-2 bg-amber-600 hover:bg-amber-500 text-white text-sm font-medium rounded-lg disabled:opacity-50"
                          >
                            {t('presetVersions.restore.confirm')}
                          </button>
                          <button
                            onClick={() => setConfirmRestore(false)}
                            className="px-4 py-2 bg-white/10 hover:bg-white/20 text-gray-200 text-sm rounded-lg"
                          >
                            {t('common.cancel')}
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </div>
    </ModalOverlay>
  );
};
