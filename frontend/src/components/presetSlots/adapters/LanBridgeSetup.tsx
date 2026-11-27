import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Activity, Check, Clock, Loader2, LockKeyhole, RefreshCw, Settings2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  isPluginEmbed,
  requestPluginCapabilities,
  subscribeToPluginCapabilities,
} from '../../../utils/pluginBridge';
import type { LanBridgeResult } from '../../../utils/pluginBridge';
import { printerBridgeAPI } from '../../../api/client';
import { translateApiError } from '../../../utils/translateApiError';
import { formatLastSeen, getDeviceLinkState, latestDeviceContact, useNow } from '../../../utils/deviceLink';
import { toast } from '../../Toast';
import type { AdapterViewContext } from './types';
import { retryPairingStatusQuery } from '../pairingPolling';

// Outcomes that leave the one-time code unused, so a retry may send it again.
const KEEPS_PAIRING_CODE = new Set(['choose', 'permission', 'check_code']);

export interface LanBridgeRoute {
  /** Stored on the connector as its provider. */
  provider: string;
  /** The plugin capability without which this card can only inform. */
  capability: string;
  /** Section of `presetSlots` holding this printer family's wording. */
  textKey: string;
  configure: (
    physicalPrinterId: number, materialSystemId: number, pairingCode: string, connectionRef?: string,
  ) => Promise<LanBridgeResult>;
  refresh: (physicalPrinterId: number, materialSystemId: number) => Promise<LanBridgeResult>;
  /**
   * A code only the person knows, asked on this card when the plugin cannot
   * find it and says so with one of `outcomes`. It goes to the plugin only.
   */
  secret?: {
    outcomes: ReadonlySet<string>;
    maxLength: number;
    configure: (
      physicalPrinterId: number, materialSystemId: number, pairingCode: string,
      connectionRef: string | undefined, secret: string,
    ) => Promise<LanBridgeResult>;
  };
}

/**
 * The OrcaSlicer route of a printer the plugin reads over the local network.
 * The plugin takes what it needs from the printer's connection settings in
 * OrcaSlicer and from the printer itself, so this card asks for nothing but a
 * code only the person knows, and only when the plugin found none: it issues a
 * pairing code and reports what the plugin answered. The card asks for a reading on connect and
 * when it opens. While OrcaSlicer is open the plugin also follows the printer on
 * its own to count a job's filament.
 */
export function LanBridgeSetup({
  route,
  printer,
  system,
  autoConnect = false,
  connectionRef,
  onConnectionObserved,
}: AdapterViewContext & { route: LanBridgeRoute }) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const pluginEmbed = isPluginEmbed();
  const inWizard = Boolean(onConnectionObserved);
  const [supported, setSupported] = useState(false);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<string | null>(null);
  const [choices, setChoices] = useState<NonNullable<LanBridgeResult['candidates']>>([]);
  const [secret, setSecret] = useState('');
  const pairing = useRef<{ code: string; expiresAt: number } | null>(null);
  // The printer last tried, so a code typed after a choice goes to the same one.
  const lastRef = useRef<string | undefined>(undefined);
  const autoConnectAttempted = useRef(false);
  const refreshedOnOpen = useRef(false);
  const now = useNow();
  const text = `presetSlots.${route.textKey}`;
  const connector = (printer.connectors ?? []).find(
    (item) => item.provider === route.provider
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
      setSupported(capabilities.has(route.capability));
    });
    requestPluginCapabilities();
    return unsubscribe;
  }, [pluginEmbed, route.capability]);

  useEffect(() => {
    if (lastObservationAt) onConnectionObserved?.();
  }, [lastObservationAt, onConnectionObserved]);

  const settle = async (result: LanBridgeResult) => {
    setOutcome(result.ok && result.code === 'ok' ? null : result.code);
    setChoices(result.code === 'choose' ? result.candidates ?? [] : []);
    if (result.ok) setSecret('');
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['printer-bridge-status', printer.id, system.id] }),
      queryClient.invalidateQueries({ queryKey: ['physical-printers'] }),
    ]);
  };

  const run = async (request: () => Promise<LanBridgeResult>) => {
    setBusy(true);
    setOutcome(null);
    try {
      await settle(await request());
    } catch (err: unknown) {
      const response = (err as { response?: { data?: { detail?: unknown } } } | null)?.response;
      if (response) {
        toast.error(translateApiError(t, response.data?.detail, t('common.error')));
      } else {
        setOutcome('unavailable');
      }
    } finally {
      setBusy(false);
    }
  };

  const connect = (chosenRef?: string, typed?: string) => run(async () => {
    let current = pairing.current;
    if (!current || current.expiresAt - Date.now() < 15_000) {
      const issued = await printerBridgeAPI.issuePairingCode(printer.id, system.id);
      current = { code: issued.pairing_code, expiresAt: Date.parse(issued.expires_at) };
    }
    const target = chosenRef ?? (typed ? lastRef.current : undefined) ?? connectionRef;
    lastRef.current = target;
    const result = typed && route.secret
      ? await route.secret.configure(printer.id, system.id, current.code, target, typed)
      : await route.configure(printer.id, system.id, current.code, target);
    pairing.current = KEEPS_PAIRING_CODE.has(result.code) ? current : null;
    return result;
  });

  const refresh = () => run(() => route.refresh(printer.id, system.id));

  useEffect(() => {
    if (!canAct || statusQuery.isLoading || busy) return;
    if (autoConnect && !paired && !autoConnectAttempted.current) {
      autoConnectAttempted.current = true;
      void connect();
    } else if (paired && !refreshedOnOpen.current) {
      // One read when the card opens; the page itself never polls the printer.
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
        <span className="text-xs font-medium text-gray-200">{t(`${text}.title`)}</span>
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
                {t(`${text}.refresh`)}
              </button>
            )}
            <button type="button" onClick={() => void connect()} disabled={busy} className={button}>
              {busy && !paired ? <Loader2 className="h-3 w-3 animate-spin" /> : <Settings2 className="h-3 w-3" />}
              {t(paired ? `${text}.reconnect` : `${text}.connect`)}
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
        <p className="mt-1 text-[11px] leading-4 text-gray-400">{t(`${text}.description`)}</p>
      )}
      {outcome && outcome !== 'choose' && (
        <p role="alert" className="mt-1.5 text-[11px] leading-4 text-amber-200">
          {t(`${text}.result.${outcome}`, {
            defaultValue: t(`${text}.result.invalid`),
          })}
        </p>
      )}
      {canAct && route.secret && outcome && route.secret.outcomes.has(outcome) && (
        <form
          className="mt-2"
          onSubmit={(event) => {
            event.preventDefault();
            const typed = secret.trim();
            if (typed) void connect(undefined, typed);
          }}
        >
          <label htmlFor={`lan-secret-${system.id}`} className="block text-[11px] leading-4 text-gray-300">
            {t(`${text}.secret.label`)}
          </label>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            {/* Room for the printer's eight-character code, not the whole row. */}
            <input
              id={`lan-secret-${system.id}`}
              type="text"
              value={secret}
              onChange={(event) => setSecret(event.target.value)}
              maxLength={route.secret.maxLength}
              autoComplete="off"
              spellCheck={false}
              className="w-[14ch] rounded-lg border border-white/10 bg-black/20 px-2 py-1 font-mono text-xs text-gray-100 focus:border-white/30 focus:outline-none"
            />
            <button type="submit" disabled={busy || !secret.trim()} className={button}>
              {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Settings2 className="h-3 w-3" />}
              {t(`${text}.secret.submit`)}
            </button>
          </div>
          <p className="mt-1 text-[10px] leading-4 text-gray-500">{t(`${text}.secret.hint`)}</p>
        </form>
      )}
      {choices.length > 0 && (
        <div className="mt-2">
          <p className="text-[11px] leading-4 text-gray-300">{t(`${text}.choose`)}</p>
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
      <p className="mt-1.5 text-[10px] leading-4 text-gray-500">{t(`${text}.onDemand`)}</p>
      {!paired && (
        <p className="mt-1 flex items-start gap-1.5 text-[10px] leading-4 text-gray-500">
          <LockKeyhole className="mt-0.5 h-3 w-3 shrink-0" />
          {t(`${text}.localOnly`)}
        </p>
      )}
    </div>
  );
}
