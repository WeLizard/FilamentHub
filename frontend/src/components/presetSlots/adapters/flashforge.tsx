import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Activity, Check, Clock, Loader2, LockKeyhole, RefreshCw, Settings2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  configureFlashforgeBridgeInPlugin,
  isPluginEmbed,
  requestFlashforgeObservationRefresh,
  requestPluginCapabilities,
  subscribeToPluginCapabilities,
} from '../../../utils/pluginBridge';
import type { FlashforgeBridgeResult } from '../../../utils/pluginBridge';
import { printerBridgeAPI } from '../../../api/client';
import { translateApiError } from '../../../utils/translateApiError';
import { formatLastSeen, getDeviceLinkState, latestDeviceContact, useNow } from '../../../utils/deviceLink';
import { toast } from '../../Toast';
import type { FeedAdapter } from './types';
import { retryPairingStatusQuery } from '../pairingPolling';

const STATION_SLOTS = 4;
// Outcomes that leave the one-time code unused, so a retry may send it again.
const KEEPS_PAIRING_CODE = new Set(['choose', 'permission']);

/**
 * The OrcaSlicer route. The plugin reads the printer's address, serial number
 * and check code from its connection settings in OrcaSlicer, so this card asks
 * for nothing: it issues a pairing code and reports what the plugin answered.
 * The printer is read on connect, when this card opens and on sync, never on a
 * timer; FH Edge is the route for continuous observation.
 */
function FlashforgeSetup({
  printer,
  system,
  autoConnect = false,
  connectionRef,
  onConnectionObserved,
}: Parameters<NonNullable<FeedAdapter['renderSetup']>>[0]) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const pluginEmbed = isPluginEmbed();
  const inWizard = Boolean(onConnectionObserved);
  const [supported, setSupported] = useState(false);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<string | null>(null);
  const [choices, setChoices] = useState<NonNullable<FlashforgeBridgeResult['candidates']>>([]);
  const pairing = useRef<{ code: string; expiresAt: number } | null>(null);
  const autoConnectAttempted = useRef(false);
  const refreshedOnOpen = useRef(false);
  const now = useNow();
  const connector = (printer.connectors ?? []).find(
    (item) => item.provider === 'flashforge'
      && item.transport === 'orca_plugin_lan'
      && item.material_system_id === system.id,
  ) ?? null;
  const canAct = pluginEmbed && supported;
  // Outside OrcaSlicer a printer linked only through FH Edge has nothing to show here.
  const relevant = inWizard || canAct || connector != null;

  const statusQuery = useQuery({
    queryKey: ['printer-bridge-status', printer.id, system.id],
    queryFn: () => printerBridgeAPI.status(printer.id, system.id),
    enabled: relevant,
    staleTime: 10_000,
    refetchOnWindowFocus: true,
    retry: retryPairingStatusQuery,
  });
  const paired = Boolean(statusQuery.data?.paired);
  const lastObservationAt = latestDeviceContact(
    statusQuery.data?.last_observation_at, connector?.status_observation?.received_at,
  );
  const freshData = getDeviceLinkState(lastObservationAt, now) === 'active';

  useEffect(() => {
    if (!pluginEmbed) return undefined;
    const unsubscribe = subscribeToPluginCapabilities((capabilities) => {
      setSupported(capabilities.has('flashforge-lan-bridge'));
    });
    requestPluginCapabilities();
    return unsubscribe;
  }, [pluginEmbed]);

  useEffect(() => {
    if (lastObservationAt) onConnectionObserved?.();
  }, [lastObservationAt, onConnectionObserved]);

  const settle = async (result: FlashforgeBridgeResult) => {
    setOutcome(result.ok && result.code === 'ok' ? null : result.code);
    setChoices(result.code === 'choose' ? result.candidates ?? [] : []);
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['printer-bridge-status', printer.id, system.id] }),
      queryClient.invalidateQueries({ queryKey: ['physical-printers'] }),
    ]);
  };

  const run = async (request: () => Promise<FlashforgeBridgeResult>) => {
    setBusy(true);
    setOutcome(null);
    try {
      await settle(await request());
    } catch (err: any) {
      if (err?.response) {
        toast.error(translateApiError(t, err.response.data?.detail, t('common.error')));
      } else {
        setOutcome('unavailable');
      }
    } finally {
      setBusy(false);
    }
  };

  const connect = (chosenRef?: string) => run(async () => {
    let current = pairing.current;
    if (!current || current.expiresAt - Date.now() < 15_000) {
      const issued = await printerBridgeAPI.issuePairingCode(printer.id, system.id);
      current = { code: issued.pairing_code, expiresAt: Date.parse(issued.expires_at) };
    }
    const result = await configureFlashforgeBridgeInPlugin(
      printer.id, system.id, current.code, chosenRef ?? connectionRef,
    );
    pairing.current = KEEPS_PAIRING_CODE.has(result.code) ? current : null;
    return result;
  });

  const refresh = () => run(() => requestFlashforgeObservationRefresh(printer.id, system.id));

  useEffect(() => {
    if (!canAct || statusQuery.isLoading || busy) return;
    if (autoConnect && !paired && !autoConnectAttempted.current) {
      autoConnectAttempted.current = true;
      void connect();
    } else if (paired && !refreshedOnOpen.current) {
      // One read when the card opens; nothing polls the printer afterwards.
      refreshedOnOpen.current = true;
      void refresh();
    }
  }, [autoConnect, busy, canAct, paired, statusQuery.isLoading]);

  if (!relevant) return null;

  const button = 'inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-white/5 px-2.5 py-1 text-[11px] font-medium text-gray-200 transition hover:bg-white/10 hover:text-white disabled:opacity-40';
  return (
    <div className="mb-3 rounded-lg border border-white/10 bg-white/5 px-3 py-2">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <Activity className="h-3.5 w-3.5 shrink-0 text-gray-400" />
        <span className="text-xs font-medium text-gray-200">{t('presetSlots.flashforge.title')}</span>
        {/* State wording is shared with the Bambu card: same meaning, same text. */}
        {lastObservationAt ? (
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
            {t(paired ? 'presetSlots.bambu.awaitingFirstData' : 'presetSlots.bambu.notConnected')}
          </span>
        )}
        {canAct ? (
          <span className="ml-auto inline-flex flex-wrap items-center gap-1.5">
            {paired && (
              <button type="button" onClick={() => void refresh()} disabled={busy} className={button}>
                {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                {t('presetSlots.flashforge.refresh')}
              </button>
            )}
            <button type="button" onClick={() => void connect()} disabled={busy} className={button}>
              {busy && !paired ? <Loader2 className="h-3 w-3 animate-spin" /> : <Settings2 className="h-3 w-3" />}
              {t(paired ? 'presetSlots.flashforge.reconnect' : 'presetSlots.flashforge.connect')}
            </button>
          </span>
        ) : !lastObservationAt && (
          <span className="ml-auto inline-flex items-center gap-1.5 rounded-lg bg-white/5 px-2.5 py-1 text-[11px] text-gray-400">
            <LockKeyhole className="h-3 w-3" />
            {t(pluginEmbed ? 'presetSlots.bambu.updatePlugin' : 'presetSlots.bambu.openInPlugin')}
          </span>
        )}
      </div>

      {!paired && (
        <p className="mt-1 text-[11px] leading-4 text-gray-400">{t('presetSlots.flashforge.description')}</p>
      )}
      {outcome && outcome !== 'choose' && (
        <p role="alert" className="mt-1.5 text-[11px] leading-4 text-amber-200">
          {t(`presetSlots.flashforge.result.${outcome}`, {
            defaultValue: t('presetSlots.flashforge.result.invalid'),
          })}
        </p>
      )}
      {choices.length > 0 && (
        <div className="mt-2">
          <p className="text-[11px] leading-4 text-gray-300">{t('presetSlots.flashforge.choose')}</p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {choices.map((choice) => (
              <button key={choice.connectionRef} type="button" disabled={busy}
                onClick={() => void connect(choice.connectionRef)} className={button}>
                {choice.label}
              </button>
            ))}
          </div>
        </div>
      )}
      <p className="mt-1.5 text-[10px] leading-4 text-gray-500">{t('presetSlots.flashforge.onDemand')}</p>
      {!paired && (
        <p className="mt-1 flex items-start gap-1.5 text-[10px] leading-4 text-gray-500">
          <LockKeyhole className="mt-0.5 h-3 w-3 shrink-0" />
          {t('presetSlots.flashforge.localOnly')}
        </p>
      )}
    </div>
  );
}

// Flashforge printers on the LAN API (port 8898): the AD5X and Creator 5 /
// 5 Pro report a four-slot material station, the Adventurer 5M / 5M Pro one
// spool with the material set on the printer. There is no per-tool usage,
// active tool or spool identity, so both routes claim read and presence only.
export const flashforgeAdapter: FeedAdapter = {
  id: 'flashforge',
  onboarding: {
    connectionProviders: ['flashforge'],
    connectionLabelKey: 'printerSetup.connections.flashforge',
    connectionHintKey: 'printerSetup.connections.flashforgeHint',
    methods: ['orca', 'edge'],
    matchesModel: (model) => /^flash\s*forge$/i.test(model.manufacturer?.trim() ?? ''),
    topologies: [
      { id: 'station', labelKey: 'printerSetup.feed.flashforgeStation', kind: 'mmu',
        slots: () => Array.from({ length: STATION_SLOTS }, (_, provider_index) => ({ provider_index, kind: 'slot' })) },
      { id: 'single', labelKey: 'printerSetup.feed.flashforgeSingle', kind: 'direct_feed',
        slots: () => [{ provider_index: 0, kind: 'external' }] },
    ],
  },
  labelKey: 'presetSlots.feedSystem.flashforge',
  fixedSlots: null,
  capabilities: ['read', 'presence'],
  supportsEdge: true,
  edgeKinds: ['mmu', 'direct_feed'],
  orcaBridge: true,
  link: null,
  renderSetup: (context) => <FlashforgeSetup {...context} />,
};
