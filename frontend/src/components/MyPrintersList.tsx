import { useEffect, useMemo, useState } from 'react';
import { useQueries, useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Activity, ChevronDown, Download, History, Loader2, Plus, RefreshCw, Settings, Wifi } from 'lucide-react';
import {
  physicalPrintersAPI,
  printProfilesAPI,
  printerProfilesAPI,
  type PhysicalPrinter,
  type PrinterConnectionBinding,
} from '../api/client';
import type { PrinterProfile, PrintProfile } from '../types/api';
import { PhysicalPrinterSettingsModal } from './PhysicalPrinterSettingsModal';
import {
  PrinterConfigurationRow,
  type ConfigurationPrintProfile,
} from './PrinterConfigurationRow';
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
import { PrintJobHistoryModal } from './PrintJobHistoryModal';
import { visiblePrinterConnections } from '../utils/printerConnections';
import { GuidedEmptyState } from './GuidedEmptyState';

const COLLAPSED_CONFIGURATION_LIMIT = 4;

function primaryNozzle(profile: PrinterProfile): number | null {
  const nozzle = profile.nozzle_diameters?.[0];
  return typeof nozzle === 'number' && Number.isFinite(nozzle) ? nozzle : null;
}

interface MyPrintersListProps {
  /** The user's Orca machine profiles, shown under the printer they belong to. */
  printerProfiles: PrinterProfile[];
  /** Process profiles assigned to each machine configuration. */
  printProfilesByConfiguration?: Map<number, ConfigurationPrintProfile[]>;
  currentUserId?: number | null;
  showNewcomerGuide?: boolean;
  /** Open the configuration (PrinterProfile) editor. */
  onEditConfiguration?: (profile: PrinterProfile) => void;
  /** Open the read-only configuration view. */
  onViewConfiguration?: (profile: PrinterProfile) => void;
  onViewPrintProfile?: (profile: PrintProfile) => void;
  onEditPrintProfile?: (
    profile: PrintProfile,
    configuration: PrinterProfile,
  ) => void;
  onCreatePrintProfile?: (configuration: PrinterProfile) => void;
  onDownloadPrintProfile?: (profile: PrintProfile) => void;
}

/**
 * Seamless list of the user's real printers, auto-discovered from OrcaSlicer.
 * Identity is physical_printer_id; the endpoint is only a label. Gate/spool
 * layout lives in "My Filaments" — here we only show how a printer is equipped.
 */
export function MyPrintersList({
  printerProfiles,
  printProfilesByConfiguration,
  currentUserId,
  showNewcomerGuide = false,
  onEditConfiguration,
  onViewConfiguration,
  onViewPrintProfile,
  onEditPrintProfile,
  onCreatePrintProfile,
  onDownloadPrintProfile,
}: MyPrintersListProps) {
  const { t, i18n } = useTranslation();
  const pluginEmbed = isPluginEmbed();
  const [settingsPrinter, setSettingsPrinter] = useState<PhysicalPrinter | null>(null);
  const [historyPrinter, setHistoryPrinter] = useState<PhysicalPrinter | null>(null);
  const [showAdd, setShowAdd] = useState(false);
  const [pluginCanInstallBundle, setPluginCanInstallBundle] = useState(!pluginEmbed);
  const [bundleActionPrinterIds, setBundleActionPrinterIds] = useState<Set<number>>(
    () => new Set(),
  );
  const [openConfigurationPrinterIds, setOpenConfigurationPrinterIds] =
    useState<Set<number>>(() => new Set());
  const [expandedConfigurationPrinterIds, setExpandedConfigurationPrinterIds] =
    useState<Set<number>>(() => new Set());

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

  const knownProfileIds = useMemo(
    () => new Set(printerProfiles.map((profile) => profile.id)),
    [printerProfiles],
  );
  const missingLinkedProfileIds = useMemo(
    () =>
      Array.from(
        new Set(
          (printers ?? []).flatMap((printer) => printer.printer_profile_ids),
        ),
      )
        .filter((profileId) => !knownProfileIds.has(profileId))
        .sort((left, right) => left - right),
    [knownProfileIds, printers],
  );
  const linkedProfileQueries = useQueries({
    queries: missingLinkedProfileIds.map((profileId) => ({
      queryKey: ['printer-profile', profileId],
      queryFn: () => printerProfilesAPI.get(profileId),
      staleTime: 60_000,
    })),
  });
  const { data: linkedPrintProfiles = [] } = useQuery({
    queryKey: ['print-profiles', 'for-configurations', missingLinkedProfileIds],
    queryFn: () => printProfilesAPI.listAllForConfigurations(missingLinkedProfileIds),
    enabled: missingLinkedProfileIds.length > 0,
    staleTime: 60_000,
  });

  const profileById = new Map<number, PrinterProfile>();
  printerProfiles.forEach((profile) => profileById.set(profile.id, profile));
  linkedProfileQueries.forEach((query) => {
    if (query.data) profileById.set(query.data.id, query.data);
  });

  const printProfilesForConfiguration = (
    configurationId: number,
    configuration: PrinterProfile,
  ): ConfigurationPrintProfile[] => {
    const merged = new Map<number, ConfigurationPrintProfile>();
    (printProfilesByConfiguration?.get(configurationId) ?? []).forEach((entry) => {
      merged.set(entry.profile.id, entry);
    });

    linkedPrintProfiles.forEach((profile) => {
      const exact = (profile.printer_profile_ids ?? []).includes(configurationId);
      const modelCompatible =
        profile.configuration_links_resolved !== true &&
        profile.printer_links.some(
          (link) =>
            link.relation_type === 'explicit' &&
            ((link.printer_id != null && link.printer_id === configuration.printer_id) ||
              link.printer_slug === configuration.printer_slug),
        );
      if (exact || modelCompatible) {
        const previous = merged.get(profile.id);
        merged.set(profile.id, { profile, exact: exact || previous?.exact === true });
      }
    });

    return Array.from(merged.values()).sort((left, right) =>
      left.profile.name.localeCompare(right.profile.name),
    );
  };

  const hasRestorableBundle = (printer: PhysicalPrinter): boolean =>
    printer.printer_profile_ids.some((configurationId) => {
      const configuration = profileById.get(configurationId);
      if (!configuration) return false;
      if (configuration.owner_user_id === currentUserId) return true;
      return printProfilesForConfiguration(configurationId, configuration).some(
        (entry) => entry.profile.owner_user_id === currentUserId,
      );
    });

  const bindingsByPrinter = useMemo(() => {
    const map = new Map<number, PrinterConnectionBinding[]>();
    (bindings ?? []).forEach((binding) => {
      const current = map.get(binding.physical_printer_id) ?? [];
      current.push(binding);
      map.set(binding.physical_printer_id, current);
    });
    map.forEach((items, printerId) => {
      map.set(printerId, visiblePrinterConnections(items));
    });
    return map;
  }, [bindings]);

  const list = printers ?? [];

  const handlePrinterBundle = async (printer: PhysicalPrinter) => {
    if (
      !hasRestorableBundle(printer) ||
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
        const result = await installPrinterBundleInPlugin(printer.id);
        toast.success(result.message || t('myPrinters.bundleRequestSent'));
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
        showNewcomerGuide ? (
          <GuidedEmptyState
            icon={<LayeredPrinterIcon className="h-5 w-5" />}
            eyebrow={t('profilePage.newcomer.printers.eyebrow')}
            title={t('profilePage.newcomer.printers.title')}
            description={t('profilePage.newcomer.printers.description')}
            actionLabel={t('addPrinter.title')}
            onAction={() => setShowAdd(true)}
            guideLabel={t('profilePage.newcomer.howTo')}
            guideTo="/wiki/articles/printer-feed-guide?start=1&journey=user%3Aprinter&returnTo=%2Fprofile%3Ftab%3Dprinter-profiles"
          />
        ) : (
          <div className="rounded-xl border border-dashed border-white/15 p-6 text-center">
            <LayeredPrinterIcon className="w-7 h-7 text-gray-500 mx-auto mb-2" />
            <p className="text-sm text-gray-400">{t('myPrinters.empty')}</p>
            <p className="mt-1 text-xs text-gray-500">{t('myPrinters.emptyHint')}</p>
          </div>
        )
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {list.map((printer) => {
            const printerBindings = bindingsByPrinter.get(printer.id) ?? [];
            const liveConnector = (printer.connectors ?? []).find(
              (connector) => connector.active && connector.status_observation,
            );
            const live = liveConnector?.status_observation ?? null;
            const bundleAvailable = hasRestorableBundle(printer);
            const printerConfigurations = printer.printer_profile_ids
              .map((id) => {
                const profile = profileById.get(id);
                return profile ? { id, profile } : null;
              })
              .filter(
                (entry): entry is { id: number; profile: PrinterProfile } =>
                  entry != null,
              )
              .sort((left, right) => {
                const leftNozzle = primaryNozzle(left.profile);
                const rightNozzle = primaryNozzle(right.profile);
                if (leftNozzle != null && rightNozzle != null && leftNozzle !== rightNozzle) {
                  return leftNozzle - rightNozzle;
                }
                if (leftNozzle != null && rightNozzle == null) return -1;
                if (leftNozzle == null && rightNozzle != null) return 1;
                return left.profile.name.localeCompare(right.profile.name, i18n.language);
              });
            const configurationListExpanded =
              expandedConfigurationPrinterIds.has(printer.id);
            const configurationSectionOpen =
              openConfigurationPrinterIds.has(printer.id);
            const visibleConfigurations = configurationListExpanded
              ? printerConfigurations
              : printerConfigurations.slice(0, COLLAPSED_CONFIGURATION_LIMIT);
            const hiddenConfigurationCount =
              printerConfigurations.length - visibleConfigurations.length;
            const nozzleValues = Array.from(
              new Set(
                printerConfigurations.flatMap(({ profile }) =>
                  (profile.nozzle_diameters ?? []).filter(
                    (value) => typeof value === 'number' && Number.isFinite(value),
                  ),
                ),
              ),
            ).sort((left, right) => left - right);
            const formatNozzle = (value: number) =>
              value.toLocaleString(i18n.language, { maximumFractionDigits: 2 });
            const nozzleRange =
              nozzleValues.length === 0
                ? null
                : nozzleValues.length === 1
                  ? formatNozzle(nozzleValues[0])
                  : `${formatNozzle(nozzleValues[0])}–${formatNozzle(nozzleValues.at(-1)!)}`;
            return (
              <div key={printer.id} className="bg-white/5 rounded-xl border border-white/10 p-4 flex flex-col gap-3">
                <div className="flex items-center gap-2 min-w-0">
                  <LayeredPrinterIcon className="w-5 h-5 text-purple-400 flex-shrink-0" />
                  <h4 className="flex-1 text-sm font-semibold text-white truncate">{printer.name}</h4>
                  {pluginCanInstallBundle && <button
                    type="button"
                    onClick={() => void handlePrinterBundle(printer)}
                    disabled={
                      !bundleAvailable ||
                      bundleActionPrinterIds.has(printer.id)
                    }
                    className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md text-gray-400 transition-colors hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-35"
                    title={
                      !bundleAvailable
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
                    onClick={() => setHistoryPrinter(printer)}
                    className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-md text-gray-400 transition-colors hover:bg-white/10 hover:text-white"
                    title={t('printJobs.open')}
                    aria-label={t('printJobs.open')}
                  >
                    <History className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setSettingsPrinter(printer)}
                    className="text-gray-400 hover:text-white transition-colors flex-shrink-0"
                    title={t('printerSettings.title')}
                  >
                    <Settings className="w-4 h-4" />
                  </button>
                </div>

                {printerBindings.length > 0 && (
                  <div className="space-y-1">
                    {printerBindings.map((binding, index) => (
                      <div
                        key={`${binding.connection_ref ?? binding.display_endpoint ?? 'binding'}-${index}`}
                        className="flex items-center gap-1.5 text-xs text-gray-400"
                      >
                        <Wifi className="w-3.5 h-3.5 flex-shrink-0" />
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
                      </div>
                    ))}
                  </div>
                )}

                {live && (
                  <div className="rounded-lg border border-cyan-400/15 bg-cyan-400/[0.06] px-2.5 py-2 text-[11px] text-cyan-100/80">
                    <div className="flex min-w-0 items-center gap-1.5">
                      <Activity className="h-3.5 w-3.5 shrink-0 text-cyan-300" />
                      <span className="font-medium text-cyan-100">
                        {t(`presetSlots.bambu.state.${live.state}`, { defaultValue: live.state })}
                      </span>
                      {live.progress_percent != null && (
                        <span className="tabular-nums">{live.progress_percent}%</span>
                      )}
                      {live.current_layer != null && (
                        <span className="tabular-nums">
                          {t('myPrinters.liveLayer', {
                            current: live.current_layer,
                            total: live.total_layers ?? '—',
                          })}
                        </span>
                      )}
                      {liveConnector?.last_seen_at && (
                        <span className="ml-auto shrink-0 text-cyan-100/45">
                          {new Date(liveConnector.last_seen_at).toLocaleTimeString(i18n.language, {
                            hour: '2-digit',
                            minute: '2-digit',
                          })}
                        </span>
                      )}
                    </div>
                    {live.job_name && (
                      <p className="mt-1 truncate text-cyan-100/55" title={live.job_name}>
                        {live.job_name}
                      </p>
                    )}
                  </div>
                )}

                <div>
                  {printerConfigurations.length > 0 ? (
                    <div className="space-y-1.5">
                      <button
                        type="button"
                        onClick={() =>
                          setOpenConfigurationPrinterIds((current) => {
                            const next = new Set(current);
                            if (next.has(printer.id)) next.delete(printer.id);
                            else next.add(printer.id);
                            return next;
                          })
                        }
                        className={`flex w-full items-center gap-2 rounded-lg border px-2.5 py-1.5 text-left text-[11px] transition-colors ${
                          configurationSectionOpen
                            ? 'border-purple-400/20 bg-purple-500/[0.08] text-gray-200'
                            : 'border-white/10 bg-white/[0.035] text-gray-400 hover:border-purple-400/20 hover:bg-purple-500/[0.06] hover:text-gray-200'
                        }`}
                        aria-expanded={configurationSectionOpen}
                      >
                        <span className="min-w-0 flex-1">
                        {t('profilePage.profilesCount', {
                          count: printerConfigurations.length,
                        })}
                        {nozzleRange && (
                          <>
                            {' · '}
                            {t('profilePage.nozzles')}: {nozzleRange} {t('profilePage.mm')}
                          </>
                        )}
                        </span>
                        <ChevronDown
                          className={`h-3.5 w-3.5 shrink-0 text-purple-300 transition-transform ${configurationSectionOpen ? 'rotate-180' : ''}`}
                        />
                      </button>
                      {configurationSectionOpen && visibleConfigurations.map(({ id, profile }) => (
                          <PrinterConfigurationRow
                            key={id}
                            profile={profile}
                            physicalPrinterName={printer.name}
                            printProfiles={printProfilesForConfiguration(id, profile)}
                            currentUserId={currentUserId}
                            onEdit={onEditConfiguration}
                            onView={onViewConfiguration}
                            onViewPrintProfile={onViewPrintProfile}
                            onEditPrintProfile={onEditPrintProfile}
                            onCreatePrintProfile={onCreatePrintProfile}
                            onDownloadPrintProfile={onDownloadPrintProfile}
                          />
                      ))}
                      {configurationSectionOpen && printerConfigurations.length > COLLAPSED_CONFIGURATION_LIMIT && (
                        <button
                          type="button"
                          onClick={() =>
                            setExpandedConfigurationPrinterIds((current) => {
                              const next = new Set(current);
                              if (next.has(printer.id)) next.delete(printer.id);
                              else next.add(printer.id);
                              return next;
                            })
                          }
                          className="flex w-full items-center justify-center rounded-lg border border-dashed border-white/10 px-2.5 py-1.5 text-[11px] text-purple-200 transition-colors hover:border-white/20 hover:bg-white/5 hover:text-white"
                          aria-expanded={configurationListExpanded}
                        >
                          {configurationListExpanded
                            ? t('profilePage.hideDetails')
                            : `${t('filamentDetailPage.showMorePresets')} +${hiddenConfigurationCount}`}
                        </button>
                      )}
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
                          {system.name} · {t('myPrinters.gates', {
                            count: system.slots.filter((slot) => slot.active).length,
                          })}
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
        bindings={bindingsByPrinter.get(settingsPrinter.id) ?? []}
        onClose={() => setSettingsPrinter(null)}
        onEditConfiguration={(profile) => {
          setSettingsPrinter(null);
          onEditConfiguration?.(profile);
        }}
      />
    )}
    {historyPrinter && (
      <PrintJobHistoryModal
        printer={historyPrinter}
        onClose={() => setHistoryPrinter(null)}
      />
    )}
    </>
  );
}
