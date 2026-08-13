import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { Activity, AlertTriangle, Check, Clock, Loader2, LockKeyhole, Settings2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  configureBambuBridgeInPlugin,
  isPluginEmbed,
  requestPluginCapabilities,
  subscribeToPluginCapabilities,
} from '../../../utils/pluginBridge';
import { printerBridgeAPI } from '../../../api/client';
import { translateApiError } from '../../../utils/translateApiError';
import { toast } from '../../Toast';
import type { FeedAdapter } from './types';

function BambuCreateHelp() {
  const { t } = useTranslation();
  return (
    <p className="mt-3 max-w-2xl text-xs leading-5 text-gray-400">
      {t('presetSlots.bambu.createDescription')}
    </p>
  );
}

function BambuSetup({ printer, system }: Parameters<NonNullable<FeedAdapter['renderSetup']>>[0]) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const pluginEmbed = isPluginEmbed();
  const [supported, setSupported] = useState(false);
  const [issuing, setIssuing] = useState(false);
  const [pairingStarted, setPairingStarted] = useState(false);
  const connector = (printer.connectors ?? []).find(
    (item) => item.provider === 'bambu' && item.material_system_id === system.id,
  ) ?? null;
  const observation = connector?.status_observation ?? null;

  const statusQuery = useQuery({
    queryKey: ['printer-bridge-status', printer.id, system.id],
    queryFn: () => printerBridgeAPI.status(printer.id, system.id),
    staleTime: 10_000,
    refetchOnWindowFocus: true,
    // Pairing is the only fast-polling state. Once it succeeds or the one-time
    // code expires, the normal focus/user-action refresh policy takes over.
    refetchInterval: (query) => {
      if (!pairingStarted) return false;
      const expiresAt = query.state.data?.pairing_expires_at;
      if (expiresAt && Date.parse(expiresAt) <= Date.now()) return false;
      return 5_000;
    },
  });
  const bridgeStatus = statusQuery.data;
  const pairingPending = Boolean(
    bridgeStatus?.pairing_expires_at
      && Date.parse(bridgeStatus.pairing_expires_at) > Date.now(),
  );
  const needsConnection = !statusQuery.isLoading && !bridgeStatus?.paired;

  useEffect(() => {
    if (!pluginEmbed) return undefined;
    const unsubscribe = subscribeToPluginCapabilities((capabilities) => {
      setSupported(capabilities.has('bambu-lan-bridge'));
    });
    requestPluginCapabilities();
    return unsubscribe;
  }, [pluginEmbed]);

  useEffect(() => {
    if (!pairingStarted || bridgeStatus?.pairing_expires_at != null) return;
    setPairingStarted(false);
    void queryClient.invalidateQueries({ queryKey: ['physical-printers'] });
  }, [bridgeStatus?.pairing_expires_at, pairingStarted, queryClient]);

  const configure = async () => {
    setIssuing(true);
    try {
      const pairing = await printerBridgeAPI.issuePairingCode(printer.id, system.id);
      // Observe the pending code before opening the local form. This makes the
      // later transition back to `null` an unambiguous successful pairing even
      // when an older bridge was already connected.
      await statusQuery.refetch();
      setPairingStarted(true);
      configureBambuBridgeInPlugin(
        printer.id,
        system.id,
        printer.name,
        pairing.pairing_code,
      );
    } catch (err: any) {
      toast.error(translateApiError(t, err?.response?.data?.detail, t('common.error')));
    } finally {
      setIssuing(false);
    }
  };

  return (
    <div className={[
      'mb-3 rounded-lg border px-3 py-2',
      needsConnection
        ? 'border-amber-400/25 bg-amber-500/10'
        : 'border-white/10 bg-white/5',
    ].join(' ')}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        {needsConnection
          ? <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-300" />
          : <Activity className="h-3.5 w-3.5 shrink-0 text-gray-400" />}
        <span className={needsConnection
          ? 'text-xs font-medium text-amber-100'
          : 'text-xs font-medium text-gray-200'}>
          {t('presetSlots.bambu.title')}
        </span>
        {statusQuery.isLoading ? (
          <span className="inline-flex items-center gap-1 text-[11px] text-gray-400">
            <Loader2 className="h-3 w-3 animate-spin" />
            {t('presetSlots.bambu.checking')}
          </span>
        ) : bridgeStatus?.paired ? (
          <span className="inline-flex items-center gap-1 text-[11px] text-emerald-300">
            <Check className="h-3 w-3" />
            {t('presetSlots.bambu.connected')}
          </span>
        ) : pairingPending ? (
          <span className="inline-flex items-center gap-1 text-[11px] text-amber-200">
            <Clock className="h-3 w-3" />
            {t('presetSlots.bambu.waiting')}
          </span>
        ) : (
          <span className="text-[11px] text-gray-500">{t('presetSlots.bambu.notConnected')}</span>
        )}
        {pluginEmbed && supported ? (
          <button
            type="button"
            onClick={configure}
            disabled={issuing}
            className={[
              'ml-auto inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[11px] font-medium transition disabled:opacity-40',
              needsConnection
                ? 'bg-amber-300/15 text-amber-100 hover:bg-amber-300/25'
                : 'border border-white/10 bg-white/5 text-gray-200 hover:bg-white/10 hover:text-white',
            ].join(' ')}
          >
            {issuing
              ? <Loader2 className="h-3 w-3 animate-spin" />
              : <Settings2 className="h-3 w-3" />}
            {t(bridgeStatus?.paired
              ? 'presetSlots.bambu.changeConnection'
              : 'presetSlots.bambu.connect')}
          </button>
        ) : (
          <span className={[
            'ml-auto inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[11px]',
            needsConnection
              ? 'bg-amber-300/10 text-amber-100/70'
              : 'bg-white/5 text-gray-400',
          ].join(' ')}>
            <LockKeyhole className="h-3 w-3" />
            {t(pluginEmbed ? 'presetSlots.bambu.updatePlugin' : 'presetSlots.bambu.openInPlugin')}
          </span>
        )}
      </div>
      <p className={needsConnection
        ? 'mt-1 text-[11px] leading-4 text-amber-100/70'
        : 'mt-1 text-[11px] leading-4 text-gray-400'}>
        {t('presetSlots.bambu.description')}
      </p>

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
      <p className={[
        'mt-1.5 flex items-start gap-1.5 text-[10px] leading-4',
        needsConnection ? 'text-amber-100/60' : 'text-gray-500',
      ].join(' ')}>
        <LockKeyhole className="mt-0.5 h-3 w-3 shrink-0" />
        {t('presetSlots.bambu.localOnly')}
      </p>
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

export const bambuAdapter: FeedAdapter = {
  id: 'bambu',
  labelKey: 'presetSlots.feedSystem.bambu',
  fixedSlots: null,
  topologyFromProvider: true,
  capabilities: ['read', 'presence'],
  slotCountSummaryKey: 'presetSlots.bambu.slots',
  link: null,
  renderCreateHelp: () => <BambuCreateHelp />,
  renderSetup: (context) => <BambuSetup {...context} />,
};
