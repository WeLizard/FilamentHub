import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Activity,
  AlertTriangle,
  Check,
  Clock,
  Loader2,
  LockKeyhole,
  RefreshCw,
  Settings2,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  configureBambuBridgeInPlugin,
  isPluginEmbed,
  requestBambuMaterialAction,
  requestPluginCapabilities,
  subscribeToPluginCapabilities,
} from '../../../utils/pluginBridge';
import type { BambuMaterialActionResult } from '../../../utils/pluginBridge';
import { printerBridgeAPI } from '../../../api/client';
import { translateApiError } from '../../../utils/translateApiError';
import { toast } from '../../Toast';
import { ModalOverlay } from '../../ModalOverlay';
import type { AdapterViewContext, FeedAdapter } from './types';

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
  const [dataPollDeadline, setDataPollDeadline] = useState(() => Date.now() + 60_000);
  const [pairingBaselineLastSeen, setPairingBaselineLastSeen] = useState<string | null>(null);
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
      if (pairingStarted && Date.now() < dataPollDeadline) {
        return 5_000;
      }
      const status = query.state.data;
      return status?.paired && !status.last_seen_at && Date.now() < dataPollDeadline
        ? 5_000
        : false;
    },
  });
  const bridgeStatus = statusQuery.data;
  const pairingPending = Boolean(
    bridgeStatus?.pairing_expires_at
      && Date.parse(bridgeStatus.pairing_expires_at) > Date.now(),
  );
  const needsConnection = !statusQuery.isLoading && !bridgeStatus?.paired;
  const awaitingReplacementData = pairingStarted
    && Boolean(bridgeStatus?.paired)
    && bridgeStatus?.last_seen_at === pairingBaselineLastSeen;
  const awaitingFirstData = !statusQuery.isLoading
    && Boolean(bridgeStatus?.paired)
    && (!bridgeStatus?.last_seen_at || awaitingReplacementData);
  const hasReceivedData = Boolean(
    bridgeStatus?.paired && bridgeStatus.last_seen_at && !awaitingReplacementData,
  );
  const needsAttention = needsConnection || awaitingFirstData;

  useEffect(() => {
    if (!pluginEmbed) return undefined;
    const unsubscribe = subscribeToPluginCapabilities((capabilities) => {
      setSupported(capabilities.has('bambu-lan-bridge'));
    });
    requestPluginCapabilities();
    return unsubscribe;
  }, [pluginEmbed]);

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
      await statusQuery.refetch();
      setPairingBaselineLastSeen(bridgeStatus?.last_seen_at ?? null);
      setPairingStarted(true);
      setDataPollDeadline(Date.parse(pairing.expires_at));
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
      needsAttention
        ? 'border-amber-400/25 bg-amber-500/10'
        : 'border-white/10 bg-white/5',
    ].join(' ')}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        {needsAttention
          ? <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-300" />
          : <Activity className="h-3.5 w-3.5 shrink-0 text-gray-400" />}
        <span className={needsAttention
          ? 'text-xs font-medium text-amber-100'
          : 'text-xs font-medium text-gray-200'}>
          {t('presetSlots.bambu.title')}
        </span>
        {statusQuery.isLoading ? (
          <span className="inline-flex items-center gap-1 text-[11px] text-gray-400">
            <Loader2 className="h-3 w-3 animate-spin" />
            {t('presetSlots.bambu.checking')}
          </span>
        ) : hasReceivedData ? (
          <span className="inline-flex items-center gap-1 text-[11px] text-emerald-300">
            <Check className="h-3 w-3" />
            {t('presetSlots.bambu.connected')}
          </span>
        ) : awaitingFirstData ? (
          <span className="inline-flex items-center gap-1 text-[11px] text-amber-200">
            <Clock className="h-3 w-3" />
            {t('presetSlots.bambu.awaitingFirstData')}
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
              needsAttention
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
            needsAttention
              ? 'bg-amber-300/10 text-amber-100/70'
              : 'bg-white/5 text-gray-400',
          ].join(' ')}>
            <LockKeyhole className="h-3 w-3" />
            {t(pluginEmbed ? 'presetSlots.bambu.updatePlugin' : 'presetSlots.bambu.openInPlugin')}
          </span>
        )}
      </div>
      <p className={needsAttention
        ? 'mt-1 text-[11px] leading-4 text-amber-100/70'
        : 'mt-1 text-[11px] leading-4 text-gray-400'}>
        {t(awaitingFirstData
          ? 'presetSlots.bambu.awaitingFirstDataDescription'
          : 'presetSlots.bambu.description')}
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
        needsAttention ? 'text-amber-100/60' : 'text-gray-500',
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

function useBambuMaterialWrite(): boolean | null {
  const embedded = isPluginEmbed();
  const [available, setAvailable] = useState<boolean | null>(embedded ? null : false);

  useEffect(() => {
    if (!embedded) {
      setAvailable(false);
      return undefined;
    }
    const unsubscribe = subscribeToPluginCapabilities((capabilities) => {
      setAvailable(capabilities.has('bambu-material-write'));
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
  const pluginAvailable = useBambuMaterialWrite();
  const [loading, setLoading] = useState<'preview' | 'apply' | null>(null);
  const [preview, setPreview] = useState<BambuMaterialActionResult | null>(null);
  const connector = (printer.connectors ?? []).find(
    (item) => item.active
      && item.provider === 'bambu'
      && item.transport === 'orca_plugin_lan'
      && item.material_system_id === system.id,
  );
  const changes = preview?.changes ?? [];
  const unresolved = preview?.unresolved ?? [];
  const canApply = preview?.ok === true
    && changes.length > 0
    && ['idle', 'finished', 'failed'].includes(preview.printState ?? '');
  const slotName = (slot: number) => (
    system.slots.find((item) => item.provider_index === slot)?.label
      || t('presetSlots.bambu.materials.slot', { slot: slot + 1 })
  );
  const errorText = (code?: string | null) => t(
    `presetSlots.bambu.materials.errors.${code || 'unknown'}`,
    { defaultValue: t('presetSlots.bambu.materials.errors.unknown') },
  );

  const refreshData = async () => {
    await queryClient.invalidateQueries({ queryKey: ['physical-printers'] });
  };

  const check = async () => {
    setLoading('preview');
    try {
      const result = await requestBambuMaterialAction('preview', printer.id, system.id);
      await refreshData();
      if (!result.ok) {
        setPreview(null);
        toast.error(errorText(result.code));
      } else if ((result.changes?.length ?? 0) === 0 && (result.unresolved?.length ?? 0) === 0) {
        setPreview(null);
        toast.success(t('presetSlots.bambu.materials.inSync'));
      } else {
        setPreview(result);
      }
    } catch {
      setPreview(null);
      toast.error(errorText('timeout'));
    } finally {
      setLoading(null);
    }
  };

  const apply = async () => {
    if (!canApply) return;
    setLoading('apply');
    try {
      const result = await requestBambuMaterialAction(
        'apply',
        printer.id,
        system.id,
        preview?.desiredAssignments,
      );
      await refreshData();
      const remainingChanges = result.remainingChanges ?? [];
      const remainingUnresolved = result.unresolved ?? [];
      if (result.ok && remainingChanges.length === 0 && remainingUnresolved.length === 0) {
        toast.success(t('presetSlots.bambu.materials.applied'));
        setPreview(null);
      } else if (result.ok) {
        toast.success(t('presetSlots.bambu.materials.partiallyApplied'));
        setPreview({
          ...result,
          changes: remainingChanges,
          unresolved: remainingUnresolved,
        });
      } else {
        toast.error(errorText(result.code || 'verification_failed'));
      }
    } catch {
      toast.error(errorText('timeout'));
    } finally {
      setLoading(null);
    }
  };

  if (!connector || pluginAvailable === false) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => void check()}
        disabled={pluginAvailable == null || loading != null}
        title={t('presetSlots.bambu.materials.description')}
        className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-300/25 bg-emerald-500/10 px-2.5 py-1.5 text-xs font-medium text-emerald-100 transition hover:bg-emerald-500/20 disabled:cursor-wait disabled:opacity-40"
      >
        {loading === 'preview'
          ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
          : <RefreshCw className="h-3.5 w-3.5" />}
        {t('presetSlots.bambu.materials.check')}
      </button>

      {preview?.ok && (changes.length > 0 || unresolved.length > 0) && (
        <ModalOverlay
          onClose={() => { if (!loading) setPreview(null); }}
          closeOnOverlayClick={!loading}
          closeOnEscape={!loading}
        >
          <div className="w-full max-w-2xl rounded-2xl border border-white/15 bg-gray-950 p-5 text-white shadow-2xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-lg font-semibold">
                  {t('presetSlots.bambu.materials.previewTitle')}
                </h3>
                <p className="mt-1 text-sm leading-5 text-gray-400">
                  {t('presetSlots.bambu.materials.previewDescription')}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setPreview(null)}
                disabled={loading != null}
                className="rounded-lg p-1.5 text-gray-400 hover:bg-white/10 hover:text-white disabled:opacity-40"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {changes.length > 0 && (
              <div className="mt-4 max-h-64 space-y-1.5 overflow-y-auto pr-1">
                {changes.map((change) => (
                  <div
                    key={change.slot}
                    className="grid grid-cols-1 gap-1.5 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs sm:grid-cols-[minmax(7rem,auto)_1fr_auto_1fr] sm:items-center sm:gap-2"
                  >
                    <span className="truncate font-medium text-white">{slotName(change.slot)}</span>
                    <span className="grid min-w-0 grid-cols-[1fr_auto_1fr] items-center gap-2 sm:contents">
                      <span className="flex min-w-0 items-center gap-1.5 truncate text-gray-400">
                        {change.currentColor && (
                          <span
                            className="h-3 w-3 shrink-0 rounded-full border border-white/20"
                            style={{ backgroundColor: `#${change.currentColor}` }}
                          />
                        )}
                        <span className="truncate">
                          {change.currentMaterial || t('presetSlots.bambu.materials.unknownMaterial')}
                        </span>
                      </span>
                      <span className="text-gray-600">→</span>
                      <span className="flex min-w-0 items-center gap-1.5 truncate text-purple-200">
                        <span
                          className="h-3 w-3 shrink-0 rounded-full border border-white/20"
                          style={{ backgroundColor: `#${change.targetColor}` }}
                        />
                        <span className="truncate" title={change.presetName}>{change.presetName}</span>
                      </span>
                    </span>
                  </div>
                ))}
              </div>
            )}

            {unresolved.length > 0 && (
              <div className="mt-3 space-y-1.5 rounded-xl border border-amber-400/20 bg-amber-500/10 p-3">
                {unresolved.map((item) => (
                  <p key={`${item.slot}-${item.reason}`} className="text-xs text-amber-100">
                    <span className="font-medium">{slotName(item.slot)}:</span>{' '}
                    {t(`presetSlots.bambu.materials.unresolved.${item.reason}`)}
                  </p>
                ))}
              </div>
            )}
            {!['idle', 'finished', 'failed'].includes(preview.printState ?? '') && changes.length > 0 && (
              <p className="mt-3 rounded-lg border border-amber-400/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                {t('presetSlots.bambu.materials.busy')}
              </p>
            )}
            <div className="mt-5 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setPreview(null)}
                disabled={loading != null}
                className="rounded-lg border border-white/15 px-3 py-2 text-sm text-gray-300 hover:bg-white/5 disabled:opacity-40"
              >
                {t('common.cancel')}
              </button>
              {changes.length > 0 && (
                <button
                  type="button"
                  onClick={() => void apply()}
                  disabled={!canApply || loading != null}
                  className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  {loading === 'apply' && <Loader2 className="h-4 w-4 animate-spin" />}
                  {t('presetSlots.bambu.materials.apply')}
                </button>
              )}
            </div>
          </div>
        </ModalOverlay>
      )}
    </>
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
  slotCountSummaryKey: 'presetSlots.bambu.slots',
  link: null,
  renderCreateHelp: () => <BambuCreateHelp />,
  renderActions: (context) => <BambuMaterialActions {...context} />,
  renderSetup: (context) => <BambuSetup {...context} />,
};
