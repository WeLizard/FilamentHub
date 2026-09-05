import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Activity,
  Check,
  Clock,
  Loader2,
  LockKeyhole,
  RefreshCw,
  Settings2,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  configureBambuBridgeInPlugin,
  isPluginEmbed,
  requestBambuObservationRefresh,
  requestBambuSlotAssignment,
  requestPluginCapabilities,
  subscribeToPluginCapabilities,
  subscribeToLocalPrinterSetup,
} from '../../../utils/pluginBridge';
import { printerBridgeAPI } from '../../../api/client';
import { translateApiError } from '../../../utils/translateApiError';
import { formatLastSeen, getDeviceLinkState, latestDeviceContact, useNow } from '../../../utils/deviceLink';
import { toast } from '../../Toast';
import type { AdapterViewContext, FeedAdapter } from './types';
import { isPairingAccessDenied, retryPairingStatusQuery } from '../pairingPolling';

export function bambuPairingRefetchInterval(
  error: unknown,
  status: { paired?: boolean; last_seen_at?: string | null } | undefined,
  pairingStarted: boolean,
  pollDeadline: number,
  now = Date.now(),
): 5_000 | false {
  if (isPairingAccessDenied(error)) return false;
  if (pairingStarted && now < pollDeadline) return 5_000;
  return status?.paired && !status.last_seen_at && now < pollDeadline ? 5_000 : false;
}

function BambuCreateHelp() {
  const { t } = useTranslation();
  return (
    <p className="mt-3 max-w-2xl text-xs leading-5 text-gray-400">
      {t('presetSlots.bambu.createDescription')}
    </p>
  );
}

function BambuSetup({
  printer,
  system,
  autoConnect = false,
  connectionRef,
  onConnectionObserved,
}: Parameters<NonNullable<FeedAdapter['renderSetup']>>[0]) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const pluginEmbed = isPluginEmbed();
  const [supported, setSupported] = useState(false);
  const [issuing, setIssuing] = useState(false);
  const [pairingStarted, setPairingStarted] = useState(false);
  const [dataPollDeadline, setDataPollDeadline] = useState(() => Date.now() + 60_000);
  const [pairingBaselineLastSeen, setPairingBaselineLastSeen] = useState<string | null>(null);
  const autoConnectAttempted = useRef(false);
  const now = useNow();
  const connector = (printer.connectors ?? []).find(
    (item) => item.provider === 'bambu'
      && item.transport === 'orca_plugin_lan'
      && item.material_system_id === system.id,
  ) ?? null;
  const observation = connector?.status_observation ?? null;

  const statusQuery = useQuery({
    queryKey: ['printer-bridge-status', printer.id, system.id],
    queryFn: () => printerBridgeAPI.status(printer.id, system.id),
    staleTime: 10_000,
    refetchOnWindowFocus: true,
    retry: retryPairingStatusQuery,
    // Pairing is the only fast-polling state. Once it succeeds or the one-time
    // code expires, the normal focus/user-action refresh policy takes over.
    refetchInterval: (query) => bambuPairingRefetchInterval(
      query.state.error,
      query.state.data,
      pairingStarted,
      dataPollDeadline,
    ),
  });
  const bridgeStatus = statusQuery.data;
  const pairingPending = Boolean(
    bridgeStatus?.pairing_expires_at
      && Date.parse(bridgeStatus.pairing_expires_at) > Date.now(),
  );
  const needsConnection = !statusQuery.isLoading && !bridgeStatus?.paired;
  // A contact heartbeat is not a printer snapshot. An older pairing query
  // must not hide telemetry already delivered with the printer record.
  const lastObservationAt = latestDeviceContact(
    bridgeStatus?.last_observation_at, observation?.received_at,
  );
  const awaitingFirstData = !statusQuery.isLoading
    && Boolean(bridgeStatus?.paired)
    && !lastObservationAt;
  const hasReceivedData = Boolean(lastObservationAt);
  const freshData = getDeviceLinkState(lastObservationAt, now) === 'active';

  useEffect(() => {
    if (!pluginEmbed) return undefined;
    const unsubscribe = subscribeToPluginCapabilities((capabilities) => {
      setSupported(capabilities.has('bambu-lan-bridge'));
    });
    requestPluginCapabilities();
    return unsubscribe;
  }, [pluginEmbed]);

  useEffect(() => {
    if (!pluginEmbed) return;
    return subscribeToLocalPrinterSetup((state) => {
      if (state.provider !== 'bambu' || state.open || state.physicalPrinterId !== printer.id
        || state.materialSystemId !== system.id) return;
      if (state.outcome !== 'saved') setPairingStarted(false);
      void queryClient.invalidateQueries({ queryKey: ['printer-bridge-status', printer.id, system.id] });
      void queryClient.invalidateQueries({ queryKey: ['physical-printers'] });
    });
  }, [pluginEmbed, printer.id, queryClient, system.id]);

  useEffect(() => {
    const lastSeenAt = bridgeStatus?.last_seen_at;
    if (!lastSeenAt) return;
    if (lastSeenAt !== connector?.last_seen_at) {
      void queryClient.invalidateQueries({ queryKey: ['physical-printers'] });
    }
    if (pairingStarted && lastSeenAt !== pairingBaselineLastSeen) {
      setPairingStarted(false);
    }
  }, [
    bridgeStatus?.last_seen_at,
    connector?.last_seen_at,
    pairingBaselineLastSeen,
    pairingStarted,
    queryClient,
  ]);

  useEffect(() => {
    if (hasReceivedData) onConnectionObserved?.();
  }, [hasReceivedData, onConnectionObserved]);

  useEffect(() => {
    if (!pairingStarted) return undefined;
    const remaining = dataPollDeadline - Date.now();
    if (remaining <= 0) {
      setPairingStarted(false);
      return undefined;
    }
    const timer = window.setTimeout(() => setPairingStarted(false), remaining);
    return () => window.clearTimeout(timer);
  }, [dataPollDeadline, pairingStarted]);

  const configure = async () => {
    setIssuing(true);
    try {
      const pairing = await printerBridgeAPI.issuePairingCode(printer.id, system.id);
      // Observe the pending code before opening the local form. This makes the
      // later transition back to `null` an unambiguous successful pairing even
      // when an older bridge was already connected.
      const refreshed = await statusQuery.refetch();
      setPairingBaselineLastSeen(refreshed.data?.last_seen_at ?? null);
      setPairingStarted(true);
      setDataPollDeadline(Date.parse(pairing.expires_at));
      configureBambuBridgeInPlugin(
        printer.id,
        system.id,
        printer.name,
        pairing.pairing_code,
        connectionRef,
      );
    } catch (err: any) {
      toast.error(translateApiError(t, err?.response?.data?.detail, t('common.error')));
    } finally {
      setIssuing(false);
    }
  };

  useEffect(() => {
    if (
      !autoConnect
      || autoConnectAttempted.current
      || !pluginEmbed
      || !supported
      || statusQuery.isLoading
      || !needsConnection
      || issuing
    ) return;
    autoConnectAttempted.current = true;
    void configure();
  }, [autoConnect, issuing, needsConnection, pluginEmbed, statusQuery.isLoading, supported]);

  return (
    <div className="mb-3 rounded-lg border border-white/10 bg-white/5 px-3 py-2">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <Activity className="h-3.5 w-3.5 shrink-0 text-gray-400" />
        <span className="text-xs font-medium text-gray-200">{t('presetSlots.bambu.title')}</span>
        {hasReceivedData ? (
          <span className={`inline-flex items-center gap-1 text-[11px] ${freshData ? 'text-emerald-300' : 'text-gray-400'}`}>
            {freshData ? <Check className="h-3 w-3" /> : <Clock className="h-3 w-3" />}
            {freshData ? t('presetSlots.bambu.connected') : t('deviceLink.lastData', {
              time: formatLastSeen(lastObservationAt, t, i18n.language, now),
            })}
          </span>
        ) : statusQuery.isLoading ? (
          <span className="inline-flex items-center gap-1 text-[11px] text-gray-400">
            <Loader2 className="h-3 w-3 animate-spin" />{t('presetSlots.bambu.checking')}
          </span>
        ) : (
          <span className="text-[11px] text-gray-400">
            {t(awaitingFirstData ? 'presetSlots.bambu.awaitingFirstData'
              : pairingStarted && pairingPending ? 'presetSlots.bambu.waiting'
                : 'presetSlots.bambu.notConnected')}
          </span>
        )}
        {pluginEmbed && supported ? (
          <button type="button" onClick={configure} disabled={issuing}
            className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] font-medium text-gray-200 transition hover:bg-white/10 hover:text-white disabled:opacity-40">
            {issuing ? <Loader2 className="h-3 w-3 animate-spin" /> : <Settings2 className="h-3 w-3" />}
            {t(bridgeStatus?.paired || hasReceivedData
              ? 'presetSlots.bambu.changeConnection' : 'presetSlots.bambu.connect')}
          </button>
        ) : !hasReceivedData && (
          <span className="ml-auto inline-flex items-center gap-1.5 rounded-lg bg-white/5 px-2.5 py-1 text-[11px] text-gray-400">
            <LockKeyhole className="h-3 w-3" />
            {t(pluginEmbed ? 'presetSlots.bambu.updatePlugin' : 'presetSlots.bambu.openInPlugin')}
          </span>
        )}
      </div>
      {!hasReceivedData && <p className="mt-1 text-[11px] leading-4 text-gray-400">
        {t(awaitingFirstData ? 'presetSlots.bambu.awaitingFirstDataDescription' : 'presetSlots.bambu.description')}
      </p>}

      {observation && (
        <div className="mt-2 grid gap-1.5 text-xs sm:grid-cols-2 lg:grid-cols-4">
          <Fact
            label={t('presetSlots.bambu.stateLabel')}
            value={t(`presetSlots.bambu.state.${observation.state}`, {
              defaultValue: observation.state,
            })}
          />
          <Fact
            label={t('presetSlots.bambu.progress')}
            value={observation.progress_percent == null ? '—' : `${observation.progress_percent}%`}
          />
          <Fact
            label={t('presetSlots.bambu.layers')}
            value={observation.current_layer == null
              ? '—'
              : `${observation.current_layer}${observation.total_layers == null ? '' : ` / ${observation.total_layers}`}`}
          />
          <Fact
            label={t('presetSlots.bambu.temperatures')}
            value={[
              observation.nozzle_temperature == null ? null : `${Math.round(observation.nozzle_temperature)}°`,
              observation.bed_temperature == null ? null : `${Math.round(observation.bed_temperature)}°`,
              observation.chamber_temperature == null ? null : `${Math.round(observation.chamber_temperature)}°`,
            ].filter(Boolean).join(' · ') || '—'}
          />
        </div>
      )}
      {!hasReceivedData && <p className="mt-1.5 flex items-start gap-1.5 text-[10px] leading-4 text-gray-500">
        <LockKeyhole className="mt-0.5 h-3 w-3 shrink-0" />
        {t('presetSlots.bambu.localOnly')}
      </p>}
    </div>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-black/15 px-2.5 py-1.5">
      <p className="text-[10px] uppercase tracking-wide text-gray-500">{label}</p>
      <p className="mt-0.5 truncate text-gray-200" title={value}>{value}</p>
    </div>
  );
}

function useBambuMaterialRefresh(): boolean | null {
  const embedded = isPluginEmbed();
  const [available, setAvailable] = useState<boolean | null>(embedded ? null : false);

  useEffect(() => {
    if (!embedded) {
      setAvailable(false);
      return undefined;
    }
    const unsubscribe = subscribeToPluginCapabilities((capabilities) => {
      setAvailable(capabilities.has('material-observation-refresh-v1'));
    });
    requestPluginCapabilities();
    const timeout = window.setTimeout(() => setAvailable((current) => current ?? false), 1500);
    return () => {
      window.clearTimeout(timeout);
      unsubscribe();
    };
  }, [embedded]);

  return available;
}

function BambuMaterialActions({
  printer,
  system,
}: Pick<AdapterViewContext, 'printer' | 'system'>) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const pluginAvailable = useBambuMaterialRefresh();
  const [loading, setLoading] = useState(false);
  const feedbackKey = `bambu-materials-${printer.id}-${system.id}`;
  const connector = (printer.connectors ?? []).find(
    (item) => item.active
      && item.provider === 'bambu'
      && item.transport === 'orca_plugin_lan'
      && item.material_system_id === system.id,
  );
  const errorText = (code?: string | null) => t(
    `presetSlots.bambu.materials.errors.${code || 'unknown'}`,
    { defaultValue: t('presetSlots.bambu.materials.errors.unknown') },
  );

  const refresh = async () => {
    setLoading(true);
    try {
      const result = await requestBambuObservationRefresh(printer.id, system.id);
      await queryClient.invalidateQueries({ queryKey: ['physical-printers'] });
      if (result.ok && result.observationUploaded) {
        toast.success(t('presetSlots.bambu.materials.refreshed'), undefined, feedbackKey);
      } else {
        toast.error(errorText(result.code), undefined, feedbackKey);
      }
    } catch {
      toast.error(errorText('timeout'), undefined, feedbackKey);
    } finally {
      setLoading(false);
    }
  };

  if (!connector || pluginAvailable === false) return null;

  return (
    <button
      type="button"
      onClick={() => void refresh()}
      disabled={pluginAvailable == null || loading}
      title={t('presetSlots.bambu.materials.description')}
      className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-300/25 bg-emerald-500/10 px-2.5 py-1.5 text-xs font-medium text-emerald-100 transition hover:bg-emerald-500/20 disabled:cursor-wait disabled:opacity-40"
    >
      {loading
        ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
        : <RefreshCw className="h-3.5 w-3.5" />}
      {t('presetSlots.bambu.materials.check')}
    </button>
  );
}
export const bambuAdapter: FeedAdapter = {
  id: 'bambu',
  onboarding: {
    connectionProviders: ['bambu'],
    connectionLabelKey: 'printerSetup.connections.bambu',
    connectionHintKey: 'printerSetup.connections.bambuHint',
    methods: ['orca'],
    matchesModel: (model) => /^(bambu|bambulab|bambu lab)$/i.test(model.manufacturer?.trim() ?? ''),
    topologies: [
      { id: 'external', labelKey: 'printerSetup.feed.noAms', kind: 'direct_feed',
        slots: () => [{ provider_index: 255, kind: 'external' }],
        extras: [{ labelKey: 'printerSetup.feed.secondExternal', index: 254, kind: 'external' }] },
      { id: 'ams', labelKey: 'printerSetup.feed.ams', kind: 'mmu',
        count: { labelKey: 'printerSetup.feed.amsSlots', initial: 4, max: 252 },
        slots: (count) => Array.from({ length: count }, (_, provider_index) => ({ provider_index, kind: 'slot' })),
        extras: [{ labelKey: 'printerSetup.feed.external', index: 255, kind: 'external', checked: true },
          { labelKey: 'printerSetup.feed.secondExternal', index: 254, kind: 'external' }] },
    ],
  },
  labelKey: 'printerSetup.connections.bambu',
  fixedSlots: null,
  topologyFromProvider: true,
  capabilities: ['read', 'write', 'presence'],
  link: null,
  deliverAssignment: async ({ printer, system, slot }) => {
    const result = await requestBambuSlotAssignment(printer.id, system.id, {
      materialSlotId: slot.id,
      providerIndex: slot.provider_index,
      assignmentRevision: slot.assignment_revision,
      desired: slot.assignment ? {
        presetId: slot.assignment.preset_id,
        spoolId: slot.assignment.spool_id,
        sourceTs: slot.assignment.source_ts,
      } : null,
    });
    if (result.ok && result.applied && result.observationUploaded) {
      return { status: 'delivered' };
    }
    if (result.code === 'physical_clear_unsupported') {
      return { status: 'unsupported', code: result.code };
    }
    return {
      status: 'saved_only',
      code: result.code,
      physicallyApplied: result.applied === true,
    };
  },
  renderCreateHelp: () => <BambuCreateHelp />,
  renderActions: (context) => <BambuMaterialActions {...context} />,
  renderSetup: (context) => <BambuSetup {...context} />,
};
