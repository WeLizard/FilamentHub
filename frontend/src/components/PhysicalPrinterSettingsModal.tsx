/** Settings for a user's physical printer: name, catalog model, linked Orca
 *  configurations, and explicit connection management. Slicing parameters (nozzle,
 *  volume, limits) live in the configuration (PrinterProfile), not here. */

import { useMemo, useRef, useState, FormEvent } from 'react';
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Coins, Loader2, Save, Wifi, X, Link2Off, SlidersHorizontal, Trash2 } from 'lucide-react';
import type { AxiosError } from 'axios';
import { physicalPrintersAPI, printerProfilesAPI, printersAPI } from '../api/client';
import type { PhysicalPrinter, PrinterConnectionBinding, PrinterMergePreview } from '../api/client';
import type { PrinterProfile } from '../types/api';
import { useAuth } from '../contexts/AuthContext';
import { useDebounce } from '../hooks/useDebounce';
import { useUserCurrency } from '../hooks/useUserCurrency';
import { ModalOverlay } from './ModalOverlay';
import { PrinterCostModal } from './calculator/PrinterCostModal';
import { ConfirmModal } from './ConfirmModal';
import { Dropdown } from './Dropdown';
import { configLabel } from '../utils/printerConfig';
import { formatLastSeen } from '../utils/deviceLink';
import { translateApiError } from '../utils/translateApiError';

interface PhysicalPrinterSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  printer: PhysicalPrinter;
  bindings?: PrinterConnectionBinding[];
  onEditConfiguration?: (profile: PrinterProfile) => void;
}

export const PhysicalPrinterSettingsModal: React.FC<PhysicalPrinterSettingsModalProps> = ({
  isOpen,
  onClose,
  printer,
  bindings = [],
  onEditConfiguration,
}) => {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const [name, setName] = useState(printer.name);
  const [printerId, setPrinterId] = useState<number | null>(printer.printer_id);
  const [profileIds, setProfileIds] = useState<number[]>(printer.printer_profile_ids);
  const [printerSearch, setPrinterSearch] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [showDiscard, setShowDiscard] = useState(false);
  const [showDelete, setShowDelete] = useState(false);
  const [costModalOpen, setCostModalOpen] = useState(false);
  const [selectedBindingId, setSelectedBindingId] = useState<number | null>(null);
  const [detachBinding, setDetachBinding] = useState<PrinterConnectionBinding | null>(null);
  const { data: settingsBindings = bindings } = useQuery({
    queryKey: ['printer-bindings', 'settings'], queryFn: physicalPrintersAPI.listBindingsForSettings,
    enabled: isOpen,
  });
  const [mergeTarget, setMergeTarget] = useState<number | null>(null);
  const [mergePreview, setMergePreview] = useState<PrinterMergePreview | null>(null);
  const { data: allPrinters = [] } = useQuery({
    queryKey: ['physical-printers'], queryFn: physicalPrintersAPI.list, enabled: isOpen,
  });
  const previewMerge = useMutation({
    mutationFn: () => physicalPrintersAPI.previewMerge(printer.id, mergeTarget!),
    onSuccess: (preview) => {
      if (preview.allowed) { setMergePreview(preview); setError(null); }
      else setError(t(`printerConnections.mergeReasons.${preview.reason}`));
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      setError(translateApiError(t, err.response?.data?.detail, t('printerConnections.failed')));
    },
  });
  const mergeMutation = useMutation({
    mutationFn: () => physicalPrintersAPI.merge(printer.id, mergePreview!.target_id, mergePreview!.revision),
    onSuccess: async () => {
      await Promise.all(['physical-printers', 'printer-bindings', 'printer-connections-pending', 'devices', 'print-jobs']
        .map((key) => queryClient.invalidateQueries({ queryKey: [key] })));
      setMergePreview(null);
      onClose();
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      setMergePreview(null);
      setError(translateApiError(t, err.response?.data?.detail, t('printerConnections.failed')));
    },
  });
  const pendingActionRef = useRef<(() => void) | null>(null);
  const debouncedSearch = useDebounce(printerSearch, 250);
  const printerBindings = useMemo(
    () => settingsBindings.filter((binding) => binding.physical_printer_id === printer.id),
    [settingsBindings, printer.id],
  );
  const visibleBindings = useMemo(
    () => printerBindings.filter((binding) => binding.status !== 'detached')
      .sort((left, right) => right.last_seen_at.localeCompare(left.last_seen_at)),
    [printerBindings],
  );
  const assignableBindings = useMemo(
    () =>
      settingsBindings
        .filter(
          (binding) =>
            binding.connection_ref != null && binding.physical_printer_id !== printer.id,
        )
        .sort((left, right) => right.last_seen_at.localeCompare(left.last_seen_at)),
    [settingsBindings, printer.id],
  );
  const bindingOptions = useMemo(
    () =>
      assignableBindings.map((binding) => ({
        value: binding.id,
        label: [
          binding.preset_name,
          binding.provider
            ? t(`presetSlots.connectionProvider.${binding.provider}`, {
              defaultValue: binding.provider,
            })
            : null,
          binding.display_endpoint ?? t('myPrinters.localConnection'),
          binding.status === 'detached' ? t('printerSettings.connectionDetached') : t('printerSettings.connectionAssignedTo', {
            name: binding.physical_printer_name,
          }),
        ].filter(Boolean).join(' · '),
      })),
    [assignableBindings, t],
  );

  const { data: catalogList } = useQuery({
    queryKey: ['printers', 'settings-picker', debouncedSearch],
    queryFn: () =>
      printersAPI.list({ page: 1, size: 50, active_only: true, search: debouncedSearch.trim() || undefined }),
    enabled: isOpen,
  });
  const { data: currentCatalog } = useQuery({
    queryKey: ['printer', printerId],
    queryFn: () => (printerId ? printersAPI.get(printerId) : null),
    enabled: isOpen && !!printerId,
  });
  const { currency: economicsCurrency } = useUserCurrency();

  const { data: profilesList } = useQuery({
    queryKey: ['printer-profiles', 'all-owned', user?.id],
    queryFn: () => printerProfilesAPI.listAllOwned(user!.id),
    enabled: isOpen && !!user,
  });
  const { data: catalogProfiles = [] } = useQuery({
    queryKey: ['printer-profiles', 'for-printer', printerId],
    queryFn: () => printerProfilesAPI.listAllForPrinter(printerId!),
    enabled: isOpen && printerId != null,
    staleTime: 60_000,
  });
  const { data: currentOrcaContext } = useQuery({
    queryKey: ['printer-context', 'current'],
    queryFn: physicalPrintersAPI.getCurrent,
    enabled: isOpen,
    staleTime: 30_000,
  });

  const availableProfiles = useMemo(() => {
    const map = new Map<number, PrinterProfile>();
    (profilesList ?? []).forEach((profile) => map.set(profile.id, profile));
    catalogProfiles.forEach((profile) => map.set(profile.id, profile));
    return Array.from(map.values());
  }, [catalogProfiles, profilesList]);

  const ownedProfileIds = useMemo(
    () => new Set(availableProfiles.map((profile) => profile.id)),
    [availableProfiles],
  );
  const missingLinkedProfileIds = useMemo(
    () => profileIds.filter((id) => !ownedProfileIds.has(id)),
    [ownedProfileIds, profileIds],
  );
  const linkedProfileQueries = useQueries({
    queries: missingLinkedProfileIds.map((profileId) => ({
      queryKey: ['printer-profile', profileId],
      queryFn: () => printerProfilesAPI.get(profileId),
      staleTime: 60_000,
    })),
  });

  const profileById = useMemo(() => {
    const map = new Map<number, PrinterProfile>();
    availableProfiles.forEach((p) => map.set(p.id, p));
    linkedProfileQueries.forEach((query) => {
      if (query.data) map.set(query.data.id, query.data);
    });
    return map;
  }, [availableProfiles, linkedProfileQueries]);

  const catalogOptions = useMemo(() => {
    const list = [...(catalogList?.items ?? [])];
    if (currentCatalog && !list.some((p) => p.id === currentCatalog.id)) list.push(currentCatalog);
    return list.map((p) => ({ value: p.id, label: p.name }));
  }, [catalogList, currentCatalog]);

  const attachableOptions = useMemo(
    () =>
      availableProfiles
        .filter((p) => !profileIds.includes(p.id))
        .sort((left, right) => {
          const currentId = currentOrcaContext?.printer_profile_id;
          if (left.id === currentId) return -1;
          if (right.id === currentId) return 1;
          return left.name.localeCompare(right.name);
        })
        .map((p) => ({
          value: p.id,
          label:
            p.id === currentOrcaContext?.printer_profile_id
              ? `${configLabel(p, t)} · ${t('printerSettings.currentInOrca')}`
              : configLabel(p, t),
        })),
    [availableProfiles, currentOrcaContext?.printer_profile_id, profileIds, t],
  );

  // Save is two calls (basics, then configurations). Report the partial case
  // honestly instead of a single generic error, and keep what persisted visible.
  const saveMutation = useMutation({
    mutationFn: async (): Promise<{ partial: boolean }> => {
      await physicalPrintersAPI.update(printer.id, { name: name.trim(), printer_id: printerId });
      const same =
        profileIds.length === printer.printer_profile_ids.length &&
        profileIds.every((id) => printer.printer_profile_ids.includes(id));
      if (same) return { partial: false };
      try {
        await physicalPrintersAPI.setConfigurations(printer.id, profileIds);
        return { partial: false };
      } catch {
        return { partial: true };
      }
    },
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['physical-printers'] });
      if (result.partial) {
        // Name/model saved; configurations did not. Stay open so the user retries.
        setError(t('printerSettings.savePartialError'));
      } else {
        setError(null);
        onClose();
      }
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      // The basics call itself failed — nothing was persisted.
      setError(translateApiError(t, err.response?.data?.detail, t('printerSettings.saveError')));
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => physicalPrintersAPI.remove(printer.id),
    onSuccess: () => {
      // Spools leave their gates on the backend, so the filament lists change too.
      queryClient.invalidateQueries({ queryKey: ['physical-printers'] });
      queryClient.invalidateQueries({ queryKey: ['printer-bindings'] });
      queryClient.invalidateQueries({ queryKey: ['spools'] });
      setShowDelete(false);
      onClose();
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      setShowDelete(false);
      setError(translateApiError(t, err.response?.data?.detail, t('printerSettings.deleteError')));
    },
  });

  const assignBindingMutation = useMutation({
    mutationFn: (bindingId: number) =>
      physicalPrintersAPI.assignBinding(bindingId, printer.id),
    onSuccess: () => {
      setSelectedBindingId(null);
      setError(null);
      queryClient.invalidateQueries({ queryKey: ['printer-bindings'] });
      queryClient.invalidateQueries({ queryKey: ['printer-context'] });
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      setError(
        translateApiError(
          t,
          err.response?.data?.detail,
          t('printerSettings.connectionAssignError'),
        ),
      );
    },
  });

  const detachBindingMutation = useMutation({
    mutationFn: (bindingId: number) => physicalPrintersAPI.detachBinding(bindingId, printer.id),
    onSuccess: async () => {
      setDetachBinding(null); setError(null);
      await Promise.all(['printer-bindings', 'physical-printers', 'printer-context', 'printer-connections-pending', 'devices']
        .map((key) => queryClient.invalidateQueries({ queryKey: [key] })));
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      setDetachBinding(null);
      setError(translateApiError(t, err.response?.data?.detail, t('printerSettings.connectionDetachError')));
    },
  });
  const connectionLabel = (binding: PrinterConnectionBinding) => [
    binding.preset_name,
    binding.provider ? t(`presetSlots.connectionProvider.${binding.provider}`, { defaultValue: binding.provider }) : null,
    binding.display_endpoint ?? (binding.connection_ref ? t('myPrinters.localConnection') : null),
  ].filter(Boolean).join(' · ');

  if (!isOpen) return null;

  const nameInvalid = name.trim().length === 0;

  const isDirty =
    name.trim() !== printer.name ||
    printerId !== printer.printer_id ||
    profileIds.length !== printer.printer_profile_ids.length ||
    profileIds.some((id) => !printer.printer_profile_ids.includes(id));

  // Guard destructive navigation (close / open configuration editor) when there
  // are unsaved changes — same confirmation pattern as the filament modal.
  const guard = (action: () => void) => {
    if (isDirty) {
      pendingActionRef.current = action;
      setShowDiscard(true);
    } else {
      action();
    }
  };

  if (costModalOpen) {
    return (
      <PrinterCostModal
        printerId={printer.id}
        printerName={printer.name}
        currency={economicsCurrency}
        onClose={() => setCostModalOpen(false)}
      />
    );
  }

  return (
    <ModalOverlay onClose={() => guard(onClose)} closeOnEscape={!detachBinding} closeOnOverlayClick={!detachBinding}>
      <div className="bg-gray-900 rounded-2xl border border-white/20 w-full max-w-lg max-h-[85vh] overflow-y-auto">
        <form
          onSubmit={(e: FormEvent) => {
            e.preventDefault();
            if (!nameInvalid) saveMutation.mutate();
          }}
        >
          <div className="flex items-center justify-between px-6 py-4 border-b border-white/10">
            <h2 className="text-lg font-semibold text-white">{t('printerSettings.title')}</h2>
            <button
              type="button"
              onClick={() => guard(onClose)}
              className="text-gray-400 hover:text-white transition-colors"
              aria-label={t('common.close')}
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <div className="px-6 py-5 space-y-6">
            {/* Основное */}
            <section className="space-y-3">
              <h3 className="text-xs uppercase tracking-wide text-gray-500">
                {t('printerSettings.basics')}
              </h3>
              <label className="block">
                <span className="text-sm text-gray-300">{t('printerSettings.name')}</span>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  maxLength={200}
                  className="mt-1 w-full px-3 py-2 rounded-lg bg-white/5 border border-white/15 text-white text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </label>
              <div>
                <span className="text-sm text-gray-300">{t('printerSettings.catalogModel')}</span>
                <Dropdown
                  className="mt-1"
                  size="sm"
                  value={printerId ?? ''}
                  options={catalogOptions}
                  onChange={(val) => {
                    setPrinterId(val === '' ? null : Number(val));
                    setPrinterSearch('');
                  }}
                  placeholder={t('printerSettings.catalogModelPlaceholder')}
                  filterable
                  filterValue={printerSearch}
                  onFilterChange={setPrinterSearch}
                  emptyMessage={t('printerSettings.catalogModelNotFound')}
                />
              </div>
            </section>

            {/* Конфигурации Orca */}
            <section className="space-y-3">
              <h3 className="text-xs uppercase tracking-wide text-gray-500">
                {t('printerSettings.configurations')}
              </h3>
              {profileIds.length > 0 ? (
                <ul className="space-y-2">
                  {profileIds.map((id) => {
                    const profile = profileById.get(id);
                    return (
                      <li
                        key={id}
                        className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white/5 border border-white/10"
                      >
                        <span className="flex-1 text-sm text-white truncate">
                          {profile ? configLabel(profile, t) : `#${id}`}
                        </span>
                        {profile && profile.owner_user_id === user?.id && onEditConfiguration && (
                          <button
                            type="button"
                            onClick={() => guard(() => onEditConfiguration(profile))}
                            className="text-gray-400 hover:text-purple-300 transition-colors"
                            title={t('printerSettings.editConfiguration')}
                          >
                            <SlidersHorizontal className="w-4 h-4" />
                          </button>
                        )}
                        <button
                          type="button"
                          onClick={() => setProfileIds((prev) => prev.filter((x) => x !== id))}
                          className="text-gray-400 hover:text-rose-400 transition-colors"
                          title={t('printerSettings.detach')}
                        >
                          <Link2Off className="w-4 h-4" />
                        </button>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="text-xs text-gray-500">{t('printerSettings.noConfigurations')}</p>
              )}
              {attachableOptions.length > 0 && (
                <Dropdown
                  size="sm"
                  value=""
                  options={attachableOptions}
                  placeholder={t('printerSettings.attachConfiguration')}
                  onChange={(val) => {
                    if (val !== '') setProfileIds((prev) => [...prev, Number(val)]);
                  }}
                />
              )}
            </section>

            {/* Стоимость работы машины: то же окно, что открывается из расчёта */}
            <section className="space-y-2">
              <h3 className="text-xs uppercase tracking-wide text-gray-500">
                {t('printerCost.title')}
              </h3>
              <button
                type="button"
                onClick={() => setCostModalOpen(true)}
                className="flex w-full items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-gray-300 transition hover:border-white/20 hover:text-white"
              >
                <Coins className="h-4 w-4 flex-shrink-0 text-gray-400" />
                <span className="flex-1 text-left">{t('printerCost.configure')}</span>
              </button>
            </section>

            {/* Наблюдаемая связь Orca с физическим принтером */}
            <section className="space-y-2">
              <h3 className="text-xs uppercase tracking-wide text-gray-500">
                {t('printerSettings.connection')}
              </h3>
              {visibleBindings.length > 0 ? (
                <div className="space-y-1.5">
                  {visibleBindings.map((binding) => (
                    <div
                      key={binding.id}
                      className="flex items-center gap-2 text-sm text-gray-300"
                    >
                      <Wifi className="w-4 h-4 text-gray-400 flex-shrink-0" />
                      <span className="min-w-0 truncate" title={connectionLabel(binding)}>{connectionLabel(binding)}</span>
                      <span className="text-xs text-gray-500 ml-auto flex-shrink-0">
                        {formatLastSeen(binding.last_seen_at, t, i18n.language)}
                      </span>
                      <button type="button" className="shrink-0 rounded p-1 text-gray-400 hover:bg-white/10 hover:text-rose-300 disabled:opacity-40"
                        disabled={detachBindingMutation.isPending || assignBindingMutation.isPending}
                        title={t('printerSettings.connectionDetach')}
                        aria-label={t('printerSettings.connectionDetach') + ' · ' + connectionLabel(binding)}
                        onClick={() => setDetachBinding(binding)}><Link2Off className="h-4 w-4" /></button>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-gray-500">{t('printerSettings.noConnection')}</p>
              )}
              {printerBindings.some((binding) => binding.status === 'detached') && <details className="text-xs text-gray-400">
                <summary className="cursor-pointer">{t('printerSettings.detachedConnections')}</summary>
                <div className="mt-2 space-y-2">{printerBindings.filter((binding) => binding.status === 'detached').map((binding) => (
                  <div key={binding.id} className="flex items-center gap-2">
                    <span className="min-w-0 flex-1 truncate" title={connectionLabel(binding)}>{connectionLabel(binding)}</span>
                    <button type="button" disabled={assignBindingMutation.isPending || detachBindingMutation.isPending}
                      onClick={() => assignBindingMutation.mutate(binding.id)} className="shrink-0 text-purple-300 underline disabled:opacity-40">
                      {t('printerSettings.connectionRestore')}
                    </button>
                  </div>
                ))}</div>
              </details>}
              {bindingOptions.length > 0 && (
                <div className="space-y-2 pt-2">
                  <p className="text-xs text-gray-500">
                    {t('printerSettings.connectionAssignHint')}
                  </p>
                  <Dropdown
                    size="sm"
                    value={selectedBindingId ?? ''}
                    options={bindingOptions}
                    placeholder={t('printerSettings.connectionSelect')}
                    onChange={(value) =>
                      setSelectedBindingId(value === '' ? null : Number(value))
                    }
                  />
                  <button
                    type="button"
                    disabled={selectedBindingId == null || assignBindingMutation.isPending}
                    onClick={() => {
                      if (selectedBindingId != null) {
                        assignBindingMutation.mutate(selectedBindingId);
                      }
                    }}
                    className="flex items-center gap-2 rounded-lg border border-purple-400/30 bg-purple-500/10 px-3 py-2 text-sm text-purple-200 transition hover:bg-purple-500/20 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {assignBindingMutation.isPending && (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    )}
                    {t('printerSettings.connectionAssign')}
                  </button>
                </div>
              )}
            </section>

            {error && <p className="text-sm text-rose-400">{error}</p>}
            {allPrinters.length > 1 && <section className="space-y-2">
              <h3 className="text-sm text-gray-200">{t('printerConnections.mergeTitle')}</h3>
              <p className="text-xs text-gray-400">{t('printerConnections.mergeHint')}</p>
              <Dropdown size="sm" value={mergeTarget ?? ''}
                options={allPrinters.filter((p) => p.id !== printer.id).map((p) => ({ value: p.id, label: `${p.name} · #${p.id}` }))}
                placeholder={t('printerConnections.mergeChoose')}
                onChange={(value) => setMergeTarget(value === '' ? null : Number(value))} />
              <button type="button" disabled={mergeTarget == null || previewMerge.isPending}
                onClick={() => guard(() => previewMerge.mutate())}
                className="rounded-lg border border-white/20 px-3 py-2 text-sm text-gray-200 disabled:opacity-50">
                {t('printerConnections.previewMerge')}
              </button>
            </section>}
          </div>

          <div className="flex items-center justify-between gap-3 px-6 py-4 border-t border-white/10">
            <button
              type="button"
              onClick={() => setShowDelete(true)}
              className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-rose-300 transition-colors hover:bg-rose-500/10"
            >
              <Trash2 className="h-4 w-4" />
              {t('printerSettings.delete')}
            </button>
            <div className="flex gap-3">
            <button
              type="button"
              onClick={() => guard(onClose)}
              className="px-4 py-2 rounded-lg border border-white/20 text-sm text-gray-200 hover:bg-white/10 transition-colors"
            >
              {t('common.cancel')}
            </button>
            <button
              type="submit"
              disabled={nameInvalid || saveMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-sm transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {saveMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Save className="w-4 h-4" />
              )}
              {t('common.save')}
            </button>
            </div>
          </div>
        </form>
      </div>

      <ConfirmModal
        isOpen={showDelete}
        onClose={() => setShowDelete(false)}
        onConfirm={() => deleteMutation.mutate()}
        isLoading={deleteMutation.isPending}
        variant="danger"
        title={t('printerSettings.deleteTitle')}
        message={t('printerSettings.deleteMessage', { name: printer.name })}
        confirmText={t('printerSettings.delete')}
        cancelText={t('common.cancel')}
      />
      <ConfirmModal isOpen={detachBinding !== null}
        onClose={() => { if (!detachBindingMutation.isPending) setDetachBinding(null); }}
        onConfirm={() => { if (detachBinding) detachBindingMutation.mutate(detachBinding.id); }}
        isLoading={detachBindingMutation.isPending} title={t('printerSettings.connectionDetach')}
        message={t('printerSettings.connectionDetachMessage', { name: detachBinding ? connectionLabel(detachBinding) : '' })}
        confirmText={t('printerSettings.connectionDetach')} cancelText={t('common.cancel')} />
      <ConfirmModal isOpen={mergePreview !== null} onClose={() => setMergePreview(null)}
        onConfirm={() => mergeMutation.mutate()} isLoading={mergeMutation.isPending}
        title={t('printerConnections.mergeTitle')}
        message={mergePreview ? t('printerConnections.mergeConfirm', {
          source: `${mergePreview.source_name} · #${mergePreview.source_id}`,
          target: `${mergePreview.target_name} · #${mergePreview.target_id}`,
          configurations: mergePreview.configurations, connections: mergePreview.connections,
          history: mergePreview.history,
        }) : ''}
        confirmText={t('printerConnections.mergeAction')} cancelText={t('common.cancel')} />

      <ConfirmModal
        isOpen={showDiscard}
        onClose={() => setShowDiscard(false)}
        onConfirm={() => {
          setShowDiscard(false);
          const action = pendingActionRef.current;
          pendingActionRef.current = null;
          action?.();
        }}
        title={t('unsavedGuard.title')}
        message={t('unsavedGuard.message')}
        confirmText={t('unsavedGuard.confirm')}
        cancelText={t('unsavedGuard.cancel')}
      />
    </ModalOverlay>
  );
};
