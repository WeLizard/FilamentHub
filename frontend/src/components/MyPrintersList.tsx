import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Printer, Settings, Wifi } from 'lucide-react';
import {
  physicalPrintersAPI,
  type PhysicalPrinter,
  type PrinterConnectionBinding,
} from '../api/client';
import type { PrinterProfile } from '../types/api';
import { PhysicalPrinterSettingsModal } from './PhysicalPrinterSettingsModal';

interface AttachableProfile {
  id: number;
  name: string;
}

interface MyPrintersListProps {
  /** The user's Orca machine profiles, to resolve a printer's config names. */
  printerProfiles: AttachableProfile[];
  /** Open the configuration (PrinterProfile) editor from a printer's settings. */
  onEditConfiguration?: (profile: PrinterProfile) => void;
}

/**
 * Seamless list of the user's real printers, auto-discovered from OrcaSlicer.
 * Identity is physical_printer_id; the endpoint is only a label. Gate/spool
 * layout lives in "My Filaments" — here we only show how a printer is equipped.
 */
export function MyPrintersList({ printerProfiles, onEditConfiguration }: MyPrintersListProps) {
  const { t } = useTranslation();
  const [settingsPrinter, setSettingsPrinter] = useState<PhysicalPrinter | null>(null);

  const { data: printers, isLoading, isError } = useQuery({
    queryKey: ['physical-printers'],
    queryFn: physicalPrintersAPI.list,
  });
  const { data: bindings } = useQuery({
    queryKey: ['printer-bindings'],
    queryFn: physicalPrintersAPI.listBindings,
  });

  const profileName = useMemo(() => {
    const map = new Map<number, string>();
    printerProfiles.forEach((p) => map.set(p.id, p.name));
    return map;
  }, [printerProfiles]);

  const bindingByPrinter = useMemo(() => {
    const map = new Map<number, PrinterConnectionBinding>();
    (bindings ?? []).forEach((b) => map.set(b.physical_printer_id, b));
    return map;
  }, [bindings]);

  const list = printers ?? [];

  return (
    <>
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-semibold text-white">{t('myPrinters.title')}</h3>
        <p className="text-xs text-gray-400">{t('myPrinters.subtitle')}</p>
      </div>

      {isLoading ? (
        <p className="text-sm text-gray-400">{t('myPrinters.loading')}</p>
      ) : isError ? (
        <p className="text-sm text-amber-300/80">{t('myPrinters.loadError')}</p>
      ) : list.length === 0 ? (
        <div className="rounded-xl border border-dashed border-white/15 p-6 text-center">
          <Printer className="w-7 h-7 text-gray-500 mx-auto mb-2" />
          <p className="text-sm text-gray-400">{t('myPrinters.empty')}</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {list.map((printer) => {
            const binding = bindingByPrinter.get(printer.id);
            return (
              <div key={printer.id} className="bg-white/5 rounded-xl border border-white/10 p-4 flex flex-col gap-3">
                <div className="flex items-center gap-2 min-w-0">
                  <Printer className="w-5 h-5 text-purple-400 flex-shrink-0" />
                  <h4 className="flex-1 text-sm font-semibold text-white truncate">{printer.name}</h4>
                  <button
                    type="button"
                    onClick={() => setSettingsPrinter(printer)}
                    className="text-gray-400 hover:text-white transition-colors flex-shrink-0"
                    title={t('printerSettings.title')}
                  >
                    <Settings className="w-4 h-4" />
                  </button>
                </div>

                {binding && (binding.provider || binding.display_endpoint) && (
                  <div className="flex items-center gap-1.5 text-xs text-gray-400">
                    <Wifi className="w-3.5 h-3.5 flex-shrink-0" />
                    <span className="truncate">
                      {[binding.provider, binding.display_endpoint].filter(Boolean).join(' · ')}
                    </span>
                  </div>
                )}

                <div>
                  <p className="text-[11px] uppercase tracking-wide text-gray-500 mb-1">
                    {t('myPrinters.configurations')}
                  </p>
                  {printer.printer_profile_ids.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                      {printer.printer_profile_ids.map((id) => (
                        <span
                          key={id}
                          className="text-xs px-2 py-0.5 rounded-full bg-blue-500/15 border border-blue-400/25 text-blue-200"
                        >
                          {profileName.get(id) ?? `#${id}`}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <p className="text-xs text-gray-500">{t('myPrinters.noConfigurations')}</p>
                  )}
                </div>

                <div className="mt-auto">
                  {printer.material_systems.length > 0 ? (
                    <div className="flex flex-wrap gap-1.5">
                      {printer.material_systems.map((system) => (
                        <span
                          key={system.id}
                          className="text-xs px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-400/25 text-emerald-200"
                        >
                          {system.name} · {t('myPrinters.gates', { count: system.slots.length })}
                        </span>
                      ))}
                    </div>
                  ) : (
                    <span className="text-xs text-gray-500">{t('myPrinters.directFeed')}</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>

    {settingsPrinter && (
      <PhysicalPrinterSettingsModal
        isOpen
        printer={settingsPrinter}
        binding={bindingByPrinter.get(settingsPrinter.id) ?? null}
        onClose={() => setSettingsPrinter(null)}
        onEditConfiguration={(profile) => {
          setSettingsPrinter(null);
          onEditConfiguration?.(profile);
        }}
      />
    )}
    </>
  );
}
