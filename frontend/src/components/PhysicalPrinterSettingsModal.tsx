/** Settings for a user's physical printer: name, catalog model, linked Orca
 *  configurations, and read-only connection info. Slicing parameters (nozzle,
 *  volume, limits) live in the configuration (PrinterProfile), not here. */

import { useMemo, useRef, useState, FormEvent } from 'react';
import { useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Coins, Loader2, Save, Wifi, X, Link2Off, SlidersHorizontal, Trash2 } from 'lucide-react';
import type { AxiosError } from 'axios';
import { physicalPrintersAPI, printerProfilesAPI, printersAPI } from '../api/client';
import type { PhysicalPrinter, PrinterConnectionBinding } from '../api/client';
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
import { visiblePrinterConnections } from '../utils/printerConnections';

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
  const pendingActionRef = useRef<(() => void) | null>(null);
  const debouncedSearch = useDebounce(printerSearch, 250);
  const visibleBindings = useMemo(
    () => visiblePrinterConnections(bindings),
    [bindings],
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
    <ModalOverlay onClose={() => guard(onClose)}>
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

            {/* Подключение (read-only) */}
            <section className="space-y-2">
              <h3 className="text-xs uppercase tracking-wide text-gray-500">
                {t('printerSettings.connection')}
              </h3>
              {visibleBindings.length > 0 ? (
                <div className="space-y-1.5">
                  {visibleBindings.map((binding, index) => (
                    <div
                      key={`${binding.connection_ref ?? binding.display_endpoint ?? 'binding'}-${index}`}
                      className="flex items-center gap-2 text-sm text-gray-300"
                    >
                      <Wifi className="w-4 h-4 text-gray-400 flex-shrink-0" />
                      <span className="truncate">
                        {[
                          binding.provider
                            ? t(`presetSlots.connectionProvider.${binding.provider}`, {
                              defaultValue: binding.provider,
                            })
                            : null,
                          binding.display_endpoint
                            ?? (binding.connection_ref ? t('myPrinters.localConnection') : null),
                        ].filter(Boolean).join(' · ')}
                      </span>
                      <span className="text-xs text-gray-500 ml-auto flex-shrink-0">
                        {formatLastSeen(binding.last_seen_at, t, i18n.language)}
                      </span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-gray-500">{t('printerSettings.noConnection')}</p>
              )}
            </section>

            {error && <p className="text-sm text-rose-400">{error}</p>}
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
