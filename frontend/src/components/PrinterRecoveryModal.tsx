import { useEffect, useMemo, useState } from 'react';
import { AlertTriangle, ArchiveRestore, CheckCircle2, Loader2, Trash2, X } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  physicalPrintersAPI,
  type PrinterRecoveryPlan,
  type PrinterRecoveryProfileEntry,
} from '../api/client';
import {
  applyPrinterRecoveryInPlugin,
  removePrinterRecoveryFromPlugin,
  requestPrinterRecoveryState,
  type PrinterRecoveryActionResult,
  type PrinterRecoveryLocalArtifact,
  type PrinterRecoveryLocalState,
} from '../utils/pluginBridge';

interface PrinterRecoveryModalProps {
  ownerUserId: number;
  onClose: () => void;
}

type RecoveryRow = PrinterRecoveryProfileEntry & { kind: 'machine' | 'process' };

function rowKey(kind: 'machine' | 'process', profileId: number): string {
  return `${kind}:${profileId}`;
}

function errorText(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  return fallback;
}

export function PrinterRecoveryModal({ ownerUserId, onClose }: PrinterRecoveryModalProps) {
  const { t } = useTranslation();
  const [localState, setLocalState] = useState<PrinterRecoveryLocalState | null>(null);
  const [plan, setPlan] = useState<PrinterRecoveryPlan | null>(null);
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [removingKey, setRemovingKey] = useState<string | null>(null);
  const [planError, setPlanError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<PrinterRecoveryActionResult | null>(null);

  const refreshLocal = async () => {
    const state = await requestPrinterRecoveryState(ownerUserId);
    setLocalState(state);
    return state;
  };

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const state = await requestPrinterRecoveryState(ownerUserId);
        if (cancelled) return;
        setLocalState(state);
        try {
          const response = await physicalPrintersAPI.getOrcaRecoveryPlan(
            state.context.source_instance_id,
            state.context.account_id,
            state.originalObservations,
          );
          if (cancelled) return;
          setPlan(response);
          const localByProfile = new Map<string, PrinterRecoveryLocalArtifact[]>();
          for (const item of state.artifacts) {
            if (item.profileId == null) continue;
            const key = rowKey(item.kind, item.profileId);
            localByProfile.set(key, [...(localByProfile.get(key) ?? []), item]);
          }
          const defaults = new Set<string>();
          for (const [kind, entries] of [
            ['machine', response.machine_profiles],
            ['process', response.process_profiles],
          ] as const) {
            for (const entry of entries) {
              const local = localByProfile.get(rowKey(kind, entry.id)) ?? [];
              const conflict = local.length > 1 || local.some(
                (item) => !item.healthy || item.ownership !== 'current',
              );
              const installedCurrentVersion = local.length === 1
                && local[0].healthy
                && local[0].ownership === 'current'
                && local[0].contentHash === entry.content_hash;
              if (
                entry.original_state === 'missing'
                && !conflict
                && !installedCurrentVersion
              ) {
                defaults.add(rowKey(kind, entry.id));
              }
            }
          }
          setSelected(defaults);
        } catch (error) {
          if (!cancelled) {
            setPlanError(errorText(error, t('printerRecovery.planError')));
          }
        }
      } catch (error) {
        if (!cancelled) {
          setActionError(errorText(error, t('printerRecovery.localStateError')));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ownerUserId, t]);

  const rows = useMemo<RecoveryRow[]>(
    () => plan
      ? [
        ...plan.machine_profiles.map((entry) => ({ ...entry, kind: 'machine' as const })),
        ...plan.process_profiles.map((entry) => ({ ...entry, kind: 'process' as const })),
      ]
      : [],
    [plan],
  );
  const localByProfile = useMemo(() => {
    const indexed = new Map<string, PrinterRecoveryLocalArtifact[]>();
    for (const item of localState?.artifacts ?? []) {
      if (item.profileId == null) continue;
      const key = rowKey(item.kind, item.profileId);
      indexed.set(key, [...(indexed.get(key) ?? []), item]);
    }
    return indexed;
  }, [localState]);
  const printerNames = useMemo(
    () => new Map((plan?.physical_printers ?? []).map((printer) => [printer.id, printer.name])),
    [plan],
  );

  const applySelected = async () => {
    if (!plan || selected.size === 0 || working) return;
    setWorking(true);
    setActionError(null);
    setLastResult(null);
    try {
      const machineProfiles = plan.machine_profiles.filter((entry) =>
        selected.has(rowKey('machine', entry.id)),
      );
      const processProfiles = plan.process_profiles.filter((entry) =>
        selected.has(rowKey('process', entry.id)),
      );
      const result = await applyPrinterRecoveryInPlugin({
        ...plan,
        machine_profiles: machineProfiles,
        process_profiles: processProfiles,
      });
      setLastResult(result);
      setSelected(new Set());
      await refreshLocal();
    } catch (error) {
      setActionError(errorText(error, t('printerRecovery.applyError')));
    } finally {
      setWorking(false);
    }
  };

  const removeLocal = async (artifact: PrinterRecoveryLocalArtifact) => {
    if (removingKey) return;
    setRemovingKey(artifact.artifactKey);
    setActionError(null);
    setLastResult(null);
    try {
      const result = await removePrinterRecoveryFromPlugin([artifact.artifactKey]);
      setLastResult(result);
      await refreshLocal();
    } catch (error) {
      setActionError(errorText(error, t('printerRecovery.removeError')));
    } finally {
      setRemovingKey(null);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-4" role="dialog" aria-modal="true">
      <div className="flex max-h-[88vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-white/15 bg-[#181329] shadow-2xl">
        <div className="flex items-start gap-3 border-b border-white/10 px-5 py-4">
          <ArchiveRestore className="mt-0.5 h-5 w-5 shrink-0 text-purple-300" />
          <div className="min-w-0 flex-1">
            <h2 className="text-lg font-semibold text-white">{t('printerRecovery.title')}</h2>
            <p className="mt-1 text-xs text-gray-400">{t('printerRecovery.subtitle')}</p>
          </div>
          <button type="button" onClick={onClose} className="rounded-md p-1 text-gray-400 hover:bg-white/10 hover:text-white" aria-label={t('common.close')}>
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-5">
          {loading && (
            <div className="flex items-center gap-2 text-sm text-gray-300">
              <Loader2 className="h-4 w-4 animate-spin" />
              {t('printerRecovery.loading')}
            </div>
          )}

          {actionError && (
            <div className="rounded-lg border border-red-400/25 bg-red-500/10 px-3 py-2 text-sm text-red-200">{actionError}</div>
          )}
          {lastResult && (
            <div className="rounded-lg border border-emerald-400/25 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-100">
              {lastResult.message || t('printerRecovery.done')}
              {lastResult.results.some((item) => item.state.includes('restart_required')) && (
                <p className="mt-1 text-xs text-emerald-100/70">{t('printerRecovery.restartRequired')}</p>
              )}
            </div>
          )}

          {plan && (
            <section>
              <div className="mb-2 flex items-baseline justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-white">{t('printerRecovery.availableTitle')}</h3>
                  <p className="text-xs text-gray-500">{t('printerRecovery.availableHint')}</p>
                </div>
                <span className="text-xs text-gray-500">{t('printerRecovery.selected', { count: selected.size })}</span>
              </div>
              <div className="space-y-2">
                {rows.length === 0 && <p className="text-sm text-gray-500">{t('printerRecovery.noneAvailable')}</p>}
                {rows.map((row) => {
                  const key = rowKey(row.kind, row.id);
                  const local = localByProfile.get(key) ?? [];
                  const originalPresent = row.original_state === 'present';
                  const localConflict = local.length > 1 || local.some(
                    (item) => !item.healthy || item.ownership !== 'current',
                  );
                  const installedCurrent = local.length === 1
                    && local[0].healthy
                    && local[0].ownership === 'current';
                  const installedCurrentVersion = installedCurrent
                    && local[0].contentHash === row.content_hash;
                  const groups = row.physical_printer_ids
                    .map((id) => printerNames.get(id))
                    .filter((name): name is string => Boolean(name));
                  return (
                    <label key={key} className={`flex gap-3 rounded-xl border px-3 py-2.5 ${originalPresent || installedCurrentVersion || localConflict ? 'border-white/5 bg-white/[0.025]' : 'cursor-pointer border-white/10 bg-white/[0.045] hover:border-purple-400/25'}`}>
                      <input
                        type="checkbox"
                        checked={selected.has(key)}
                        disabled={originalPresent || installedCurrentVersion || localConflict || working}
                        onChange={(event) => setSelected((current) => {
                          const next = new Set(current);
                          if (event.target.checked) next.add(key);
                          else next.delete(key);
                          return next;
                        })}
                        className="mt-1 h-4 w-4 accent-purple-500"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-medium text-white">{row.name}</span>
                          <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] uppercase text-gray-400">{t(`printerRecovery.kind.${row.kind}`)}</span>
                        </div>
                        {groups.length > 0 && <p className="mt-0.5 truncate text-xs text-gray-500" title={groups.join(', ')}>{groups.join(' · ')}</p>}
                        <p className={`mt-1 text-xs ${row.original_state === 'missing' ? 'text-amber-300' : row.original_state === 'present' ? 'text-emerald-300' : 'text-gray-400'}`}>
                          {t(`printerRecovery.original.${row.original_state}`)}
                          {installedCurrentVersion ? ` · ${t('printerRecovery.managedInstalled')}` : installedCurrent ? ` · ${t('printerRecovery.managedOutdated')}` : ''}
                          {localConflict ? ` · ${t('printerRecovery.managedConflict')}` : ''}
                        </p>
                      </div>
                    </label>
                  );
                })}
              </div>
            </section>
          )}

          {planError && (
            <div className="flex gap-2 rounded-lg border border-amber-400/25 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{planError}</span>
            </div>
          )}

          {localState && (
            <section>
              <h3 className="text-sm font-semibold text-white">{t('printerRecovery.localTitle')}</h3>
              <p className="mb-2 text-xs text-gray-500">{t('printerRecovery.localHint')}</p>
              <div className="space-y-2">
                {localState.artifacts.length === 0 && <p className="text-sm text-gray-500">{t('printerRecovery.noneInstalled')}</p>}
                {localState.artifacts.map((artifact) => (
                  <div key={artifact.artifactKey} className="flex items-center gap-3 rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2">
                    {artifact.healthy ? <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-300" /> : <AlertTriangle className="h-4 w-4 shrink-0 text-amber-300" />}
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm text-gray-200">{artifact.name}</p>
                      <p className="text-xs text-gray-500">{t(`printerRecovery.kind.${artifact.kind}`)} · {t(`printerRecovery.ownership.${artifact.ownership}`)}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => void removeLocal(artifact)}
                      disabled={removingKey != null}
                      className="flex items-center gap-1.5 rounded-md border border-red-400/20 px-2 py-1 text-xs text-red-200 hover:bg-red-500/10 disabled:opacity-50"
                    >
                      {removingKey === artifact.artifactKey ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                      {t('printerRecovery.removeLocal')}
                    </button>
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>

        <div className="flex items-center justify-end gap-3 border-t border-white/10 px-5 py-4">
          <button type="button" onClick={onClose} className="rounded-lg border border-white/15 px-4 py-2 text-sm text-gray-200 hover:bg-white/5">{t('common.close')}</button>
          <button
            type="button"
            onClick={() => void applySelected()}
            disabled={!plan || selected.size === 0 || working}
            className="flex items-center gap-2 rounded-lg bg-purple-600 px-4 py-2 text-sm font-medium text-white hover:bg-purple-500 disabled:cursor-not-allowed disabled:opacity-45"
          >
            {working ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArchiveRestore className="h-4 w-4" />}
            {t('printerRecovery.restoreSelected')}
          </button>
        </div>
      </div>
    </div>
  );
}
