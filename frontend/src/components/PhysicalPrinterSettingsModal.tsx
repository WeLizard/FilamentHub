/** Settings for a user's physical printer: name, catalog model, linked Orca
 *  configurations, and read-only connection info. Slicing parameters (nozzle,
 *  volume, limits) live in the configuration (PrinterProfile), not here. */

import { useMemo, useState, FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Loader2, Save, Wifi, X, Link2Off, SlidersHorizontal } from 'lucide-react';
import type { AxiosError } from 'axios';
import { physicalPrintersAPI, printerProfilesAPI, printersAPI } from '../api/client';
import type { PhysicalPrinter, PrinterConnectionBinding } from '../api/client';
import type { PrinterProfile } from '../types/api';
import { useAuth } from '../contexts/AuthContext';
import { useDebounce } from '../hooks/useDebounce';
import { ModalOverlay } from './ModalOverlay';
import { Dropdown } from './Dropdown';
import { configLabel } from '../utils/printerConfig';
import { formatLastSeen } from '../utils/deviceLink';
import { translateApiError } from '../utils/translateApiError';

interface PhysicalPrinterSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  printer: PhysicalPrinter;
  binding?: PrinterConnectionBinding | null;
  onEditConfiguration?: (profile: PrinterProfile) => void;
}

export const PhysicalPrinterSettingsModal: React.FC<PhysicalPrinterSettingsModalProps> = ({
  isOpen,
  onClose,
  printer,
  binding,
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
  const debouncedSearch = useDebounce(printerSearch, 250);

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
  const { data: profilesData } = useQuery({
    queryKey: ['printer-profiles', user?.id],
    queryFn: () =>
      printerProfilesAPI.list({ owner_user_id: user!.id, page: 1, size: 100, active_only: false }),
    enabled: isOpen && !!user,
  });

  const profileById = useMemo(() => {
    const map = new Map<number, PrinterProfile>();
    (profilesData?.items ?? []).forEach((p) => map.set(p.id, p));
    return map;
  }, [profilesData]);

  const catalogOptions = useMemo(() => {
    const list = [...(catalogList?.items ?? [])];
    if (currentCatalog && !list.some((p) => p.id === currentCatalog.id)) list.push(currentCatalog);
    return list.map((p) => ({ value: p.id, label: p.name }));
  }, [catalogList, currentCatalog]);

  const attachableOptions = useMemo(
    () =>
      (profilesData?.items ?? [])
        .filter((p) => !profileIds.includes(p.id))
        .map((p) => ({ value: p.id, label: configLabel(p, t) })),
    [profilesData, profileIds, t],
  );

  const saveMutation = useMutation({
    mutationFn: async () => {
      await physicalPrintersAPI.update(printer.id, { name: name.trim(), printer_id: printerId });
      const same =
        profileIds.length === printer.printer_profile_ids.length &&
        profileIds.every((id) => printer.printer_profile_ids.includes(id));
      if (!same) await physicalPrintersAPI.setConfigurations(printer.id, profileIds);
    },
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ['physical-printers'] });
      onClose();
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      setError(translateApiError(t, err.response?.data?.detail, t('printerSettings.saveError')));
    },
  });

  if (!isOpen) return null;

  const nameInvalid = name.trim().length === 0;

  return (
    <ModalOverlay onClose={onClose}>
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
              onClick={onClose}
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
                        {profile && onEditConfiguration && (
                          <button
                            type="button"
                            onClick={() => onEditConfiguration(profile)}
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

            {/* Подключение (read-only) */}
            <section className="space-y-2">
              <h3 className="text-xs uppercase tracking-wide text-gray-500">
                {t('printerSettings.connection')}
              </h3>
              {binding && (binding.provider || binding.display_endpoint) ? (
                <div className="flex items-center gap-2 text-sm text-gray-300">
                  <Wifi className="w-4 h-4 text-gray-400 flex-shrink-0" />
                  <span className="truncate">
                    {[binding.provider, binding.display_endpoint].filter(Boolean).join(' · ')}
                  </span>
                  <span className="text-xs text-gray-500 ml-auto flex-shrink-0">
                    {formatLastSeen(binding.last_seen_at, t, i18n.language)}
                  </span>
                </div>
              ) : (
                <p className="text-xs text-gray-500">{t('printerSettings.noConnection')}</p>
              )}
            </section>

            {error && <p className="text-sm text-rose-400">{error}</p>}
          </div>

          <div className="flex justify-end gap-3 px-6 py-4 border-t border-white/10">
            <button
              type="button"
              onClick={onClose}
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
        </form>
      </div>
    </ModalOverlay>
  );
};
