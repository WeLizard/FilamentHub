import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Download, Loader2, Plus, RefreshCw, Settings, Wifi } from 'lucide-react';
import {
  physicalPrintersAPI,
  type PhysicalPrinter,
  type PrinterConnectionBinding,
} from '../api/client';
import type { PrinterProfile } from '../types/api';
import { PhysicalPrinterSettingsModal } from './PhysicalPrinterSettingsModal';
import { PrinterConfigurationRow } from './PrinterConfigurationRow';
import { AddPhysicalPrinterModal } from './AddPhysicalPrinterModal';
import { toast } from './Toast';
import {
  installPrinterBundleInPlugin,
  isPluginEmbed,
  requestPluginCapabilities,
  subscribeToPluginCapabilities,
} from '../utils/pluginBridge';
import { downloadBlob, safeDownloadStem } from '../utils/download';
import { translateApiError } from '../utils/translateApiError';
import { LayeredPrinterIcon } from './icons/LayeredPrinterIcon';

interface MyPrintersListProps {
  /** The user's Orca machine profiles, shown under the printer they belong to. */
  printerProfiles: PrinterProfile[];
  /** How many print profiles each configuration carries, by configuration id. */
  printProfileCounts?: Map<number, number>;
  /** Open the configuration (PrinterProfile) editor. */
  onEditConfiguration?: (profile: PrinterProfile) => void;
  /** Open the read-only configuration view. */
  onViewConfiguration?: (profile: PrinterProfile) => void;
}

/**
 * Seamless list of the user's real printers, auto-discovered from OrcaSlicer.
 * Identity is physical_printer_id; the endpoint is only a label. Gate/spool
 * layout lives in "My Filaments" — here we only show how a printer is equipped.
 */
export function MyPrintersList({
  printerProfiles,
  printProfileCounts,
  onEditConfiguration,
  onViewConfiguration,
}: MyPrintersListProps) {
  const { t } = useTranslation();
  const pluginEmbed = isPluginEmbed();
  const [settingsPrinter, setSettingsPrinter] = useState<PhysicalPrinter | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [pluginCanInstallBundle, setPluginCanInstallBundle] = useState(!pluginEmbed);
  const [bundleActionPrinterIds, setBundleActionPrinterIds] = useState<Set<number>>(
    () => new Set(),
  );

  useEffect(() => {
    if (!pluginEmbed) {
      setPluginCanInstallBundle(true);
      return;
    }
    const unsubscribe = subscribeToPluginCapabilities((capabilities) => {
      setPluginCanInstallBundle(capabilities.has('printer-bundle-install'));
    });
    requestPluginCapabilities();
    return unsubscribe;
  }, [pluginEmbed]);

  const { data: printers, isLoading, isError } = useQuery({
    queryKey: ['physical-printers'],
    queryFn: physicalPrintersAPI.list,
  });
  const { data: bindings } = useQuery({
    queryKey: ['printer-bindings'],
    queryFn: physicalPrintersAPI.listBindings,
  });

  const profileById = useMemo(() => {
    const map = new Map<number, PrinterProfile>();
    printerProfiles.forEach((p) => map.set(p.id, p));
    return map;
  }, [printerProfiles]);

  const bindingByPrinter = useMemo(() => {
    const map = new Map<number, PrinterConnectionBinding>();
    (bindings ?? []).forEach((b) => map.set(b.physical_printer_id, b));
    return map;
  }, [bindings]);

  const list = printers ?? [];

  const handlePrinterBundle = async (printer: PhysicalPrinter) => {
    if (
      printer.printer_profile_ids.length === 0 ||
      bundleActionPrinterIds.has(printer.id)
    ) {
      return;
    }
    setBundleActionPrinterIds((current) => {
      const next = new Set(current);
      next.add(printer.id);
      return next;
    });
    try {
      if (pluginEmbed) {
        installPrinterBundleInPlugin(printer.id);
        toast.info(t('myPrinters.bundleRequestSent'));
      } else {
        const bundle = await physicalPrintersAPI.downloadOrcaBundle(printer.id);
        downloadBlob(
          bundle,
          `${safeDownloadStem(printer.name, `printer-${printer.id}`)}-orcaslicer.zip`,
        );
        toast.success(t('myPrinters.bundleDownloaded'));
      }
    } catch (error: any) {
      toast.error(
        translateApiError(
          t,
          error?.response?.data?.detail,
          t('myPrinters.bundleError'),
        ),
      );
    } finally {
      setBundleActionPrinterIds((current) => {
        const next = new Set(current);
        next.delete(printer.id);
        return next;
      });
    }
  };

  return (
    <>
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-white">{t('myPrinters.title')}</h3>
          <p className="text-xs text-gray-400">{t('myPrinters.subtitle')}</p>
        </div>
        <button
          type="button"
          onClick={() => setShowAdd(true)}
          className="flex items-center gap-2 rounded-lg border border-white/20 px-3 py-1.5 text-sm text-white transition-colors hover:bg-white/10"
        >
          <Plus className="h-4 w-4" />
          {t('addPrinter.title')}
        </button>
      </div>

      {isLoading ? (
        <p className="text-sm text-gray-400">{t('myPrinters.loading')}</p>
      ) : isError ? (
        <p className="text-sm text-amber-300/80">{t('myPrinters.loadError')}</p>
      ) : list.length === 0 ? (
        <div className="rounded-xl border border-dashed border-white/15 p-6 text-center">
          <LayeredPrinterIcon className="w-7 h-7 text-gray-500 mx-auto mb-2" />
          <p className="text-sm text-gray-400">{t('myPrinters.empty')}</p>
          <p className="mt-1 text-xs text-gray-500">{t('myPrinters.emptyHint')}</p>
        </div>
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {list.map((printer) => {
            const binding = bindingByPrinter.get(printer.id);
            return (
              <div key={printer.id} className="bg-white/5 rounded-xl border border-white/10 p-4 flex flex-col gap-3">
                <div className="flex items-center gap-2 min-w-0">
                  <LayeredPrinterIcon className="w-5 h-5 text-purple-400 flex-shrink-0" />
                  <h4 className="flex-1 text-sm font-semibold text-white truncate">{printer.name}</h4>
                  {pluginCanInstallBundle && <button
                    type="button"
                    onClick={() => void handlePrinterBundle(printer)}
                    disabled={
                      printer.printer_profile_ids.length === 0 ||
                      bundleActionPrinterIds.has(printer.id)
                    }
                    className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md text-gray-400 transition-colors hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-35"
                    title={
                      printer.printer_profile_ids.length === 0
                        ? t('myPrinters.bundleUnavailable')
                        : pluginEmbed
                          ? t('myPrinters.installBundleInOrca')
                          : t('myPrinters.downloadBundle')
                    }
                    aria-label={
                      pluginEmbed
                        ? t('myPrinters.installBundleInOrca')
                        : t('myPrinters.downloadBundle')
                    }
                  >
                    {bundleActionPrinterIds.has(printer.id) ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : pluginEmbed ? (
                      <RefreshCw className="h-4 w-4" />
                    ) : (
                      <Download className="h-4 w-4" />
                    )}
                  </button>}
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
                    <div className="space-y-1.5">
                      {printer.printer_profile_ids.map((id) => {
                        const profile = profileById.get(id);
                        return profile ? (
                          <PrinterConfigurationRow
                            key={id}
                            profile={profile}
                            printProfileCount={printProfileCounts?.get(id) ?? 0}
                            onEdit={onEditConfiguration}
                            onView={onViewConfiguration}
                          />
                        ) : null;
                      })}
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
                    <span className="text-xs px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-gray-400">
                      {t('myPrinters.noFeedSystem')}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>

    <AddPhysicalPrinterModal isOpen={showAdd} onClose={() => setShowAdd(false)} />

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
