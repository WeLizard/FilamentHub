import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  Check,
  Clock,
  Copy,
  Loader2,
  RefreshCw,
} from 'lucide-react';

import { devicesAPI } from '../../../api/client';
import {
  isPluginEmbed,
  requestHappyHareObservationRefresh,
  requestHappyHareSlotAssignment,
  requestPluginCapabilities,
  subscribeToPluginCapabilities,
} from '../../../utils/pluginBridge';
import { toast } from '../../Toast';
import { translateApiError } from '../../../utils/translateApiError';
import type { AdapterViewContext, FeedAdapter } from './types';

function HostnameField({ printer }: { printer: AdapterViewContext['printer'] }) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (draft == null) return;
    setSaving(true);
    try {
      await devicesAPI.update(printer.id, { printer_hostname: draft.trim() || null });
      await queryClient.invalidateQueries({ queryKey: ['physical-printers'] });
      setDraft(null);
    } catch (err: any) {
      toast.error(translateApiError(t, err?.response?.data?.detail, t('common.error')));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <span className="text-xs text-gray-400">{t('presetSlots.happyHare.hostname')}</span>
      {draft != null ? (
        <span className="flex items-center gap-1.5">
          <input
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') void save(); }}
            placeholder="voron"
            autoFocus
            className="w-32 rounded border border-white/20 bg-black/30 px-2 py-0.5 text-xs text-white placeholder-gray-600 focus:border-purple-500 focus:outline-none"
          />
          <button
            type="button"
            onClick={save}
            disabled={saving}
            className="text-xs text-purple-300 hover:text-purple-200 disabled:opacity-40"
          >
            {t('common.save')}
          </button>
        </span>
      ) : (
        <button
          type="button"
          onClick={() => setDraft(printer.printer_hostname ?? '')}
          className="text-xs text-gray-200 underline decoration-dotted underline-offset-2 hover:text-white"
        >
          {printer.printer_hostname || t('presetSlots.happyHare.hostnameNotSet')}
        </button>
      )}
    </>
  );
}

function PairingStep({
  gates,
  hasContact,
}: {
  gates: AdapterViewContext['gates'];
  hasContact: boolean;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [copied, setCopied] = useState(false);

  const gate = gates.find((item) => item.spool_id != null) ?? null;
  const command = gate?.spool_id != null
    ? `MMU_SPOOLMAN GATE=${gate.gate_index} SPOOLID=${gate.spool_id}`
    : null;

  const copy = async () => {
    if (!command) return;
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      toast.error(t('common.error'));
    }
  };

  if (!hasContact) {
    return (
      <div className="mb-3 rounded-lg border border-purple-400/25 bg-purple-500/10 px-3 py-2">
        <div className="flex items-center gap-2">
          <Clock className="h-3.5 w-3.5 shrink-0 text-purple-300" />
          <span className="text-xs font-medium text-purple-100">
            {t('presetSlots.happyHare.autoPairingTitle')}
          </span>
        </div>
        <p className="mt-1 text-[11px] leading-4 text-purple-100/70">
          {t('presetSlots.happyHare.autoPairingDescription')}
        </p>
      </div>
    );
  }

  return (
    <div className="mb-3 rounded-lg border border-amber-400/25 bg-amber-500/10 px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-300" />
        <span className="text-xs font-medium text-amber-100">
          {t('presetSlots.happyHare.pairingTitle')}
        </span>
        {command ? (
          <>
            <code className="rounded border border-white/10 bg-black/30 px-2 py-0.5 text-[11px] text-white">
              {command}
            </code>
            <button
              type="button"
              onClick={copy}
              title={t('presetSlots.pairing.copy')}
              className="rounded p-1 text-amber-200 transition hover:bg-white/10 hover:text-amber-100"
            >
              {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            </button>
            <button
              type="button"
              onClick={() => queryClient.invalidateQueries({ queryKey: ['physical-printers'] })}
              title={t('presetSlots.pairing.check')}
              className="rounded p-1 text-amber-200 transition hover:bg-white/10 hover:text-amber-100"
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </button>
          </>
        ) : (
          <span className="text-xs text-amber-200/80">{t('presetSlots.happyHare.pairingWaiting')}</span>
        )}
      </div>
      <p className="mt-1 text-[11px] leading-4 text-amber-100/70">
        {t('presetSlots.happyHare.pairingDescription')}
      </p>
    </div>
  );
}

function HappyHareCreationGuide() {
  const { t } = useTranslation();

  return (
    <div className="mt-4 rounded-xl border border-purple-400/20 bg-purple-500/[0.07] p-4">
      <p className="text-sm font-semibold text-purple-100">
        {t('presetSlots.happyHare.guide.title')}
      </p>
      <p className="mt-1 text-xs leading-5 text-gray-400">
        {t('presetSlots.happyHare.guide.description')}
      </p>
      <div className="mt-3 grid gap-2 md:grid-cols-2">
        <div className="rounded-lg border border-white/10 bg-black/15 p-3">
          <code className="text-xs font-semibold text-emerald-300">spoolman_support: pull</code>
          <p className="mt-1 text-[11px] leading-4 text-gray-400">
            {t('presetSlots.happyHare.guide.pull')}
          </p>
        </div>
        <div className="rounded-lg border border-white/10 bg-black/15 p-3">
          <code className="text-xs font-semibold text-emerald-300">t_macro_color: gatemap</code>
          <p className="mt-1 text-[11px] leading-4 text-gray-400">
            {t('presetSlots.happyHare.guide.gatemap')}
          </p>
        </div>
      </div>
      <details className="mt-3 text-xs text-gray-400">
        <summary className="cursor-pointer select-none text-purple-200 hover:text-purple-100">
          {t('presetSlots.happyHare.guide.modes')}
        </summary>
        <div className="mt-2 grid gap-3 md:grid-cols-2">
          <div>
            <p className="font-medium text-gray-300">spoolman_support</p>
            <ul className="mt-1 space-y-1 leading-4">
              <li>{t('presetSlots.happyHare.guide.spoolmanOff')}</li>
              <li>{t('presetSlots.happyHare.guide.spoolmanReadonly')}</li>
              <li>{t('presetSlots.happyHare.guide.spoolmanPush')}</li>
              <li className="text-emerald-300">{t('presetSlots.happyHare.guide.spoolmanPull')}</li>
            </ul>
          </div>
          <div>
            <p className="font-medium text-gray-300">t_macro_color</p>
            <ul className="mt-1 space-y-1 leading-4">
              <li>{t('presetSlots.happyHare.guide.colorSlicer')}</li>
              <li className="text-emerald-300">{t('presetSlots.happyHare.guide.colorGatemap')}</li>
              <li>{t('presetSlots.happyHare.guide.colorAllgates')}</li>
              <li>{t('presetSlots.happyHare.guide.colorOff')}</li>
            </ul>
          </div>
        </div>
      </details>
      <p className="mt-3 text-[11px] leading-4 text-purple-200/80">
        {t('presetSlots.happyHare.guide.next')}
      </p>
    </div>
  );
}

function useHappyHarePlugin(): boolean | null {
  const embedded = isPluginEmbed();
  const [available, setAvailable] = useState<boolean | null>(embedded ? null : false);

  useEffect(() => {
    if (!embedded) {
      setAvailable(false);
      return undefined;
    }
    const unsubscribe = subscribeToPluginCapabilities((capabilities) => {
      setAvailable(capabilities.has('happy-hare-moonraker'));
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

function useHappyHareMaterialRefresh(): boolean | null {
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

function HappyHareRefreshAction({
  printer,
  system,
  pluginAvailable,
}: Pick<AdapterViewContext, 'printer' | 'system'> & {
  pluginAvailable: boolean | null;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [loading, setLoading] = useState(false);
  const feedbackKey = `happy-hare-${printer.id}-${system.id}`;
  const errorText = (code?: string | null) => t(
    code === 'inventory_not_connected'
      ? 'presetSlots.happyHare.inventoryError'
      : `presetSlots.happyHare.refresh.errors.${code || 'unknown'}`,
    { defaultValue: t('presetSlots.happyHare.refresh.errors.unknown') },
  );

  const refreshData = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['physical-printers'] }),
      queryClient.invalidateQueries({ queryKey: ['devices'] }),
      queryClient.invalidateQueries({ queryKey: ['spools'] }),
      queryClient.invalidateQueries({ queryKey: ['user-spools'] }),
    ]);
  };

  const refresh = async () => {
    setLoading(true);
    try {
      const result = await requestHappyHareObservationRefresh(printer.id, system.id);
      await refreshData();
      if (result.ok && result.observationUploaded) {
        toast.success(t('presetSlots.happyHare.refresh.refreshed'), undefined, feedbackKey);
      } else {
        toast.error(errorText(result.code), undefined, feedbackKey);
      }
    } catch {
      toast.error(errorText('timeout'), undefined, feedbackKey);
    } finally {
      setLoading(false);
    }
  };

  if (pluginAvailable === false) return null;
  return (
    <button
      type="button"
      onClick={() => void refresh()}
      disabled={pluginAvailable == null || loading}
      title={t('presetSlots.happyHare.refresh.description')}
      className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-300/25 bg-emerald-500/10 px-2.5 py-1.5 text-xs font-medium text-emerald-100 transition hover:bg-emerald-500/20 disabled:cursor-wait disabled:opacity-40"
    >
      {loading
        ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
        : <RefreshCw className="h-3.5 w-3.5" />}
      {t('presetSlots.happyHare.refresh.check')}
    </button>
  );
}
function HappyHareSetup(context: AdapterViewContext) {
  const { t } = useTranslation();
  const pluginAvailable = useHappyHarePlugin();
  const needsLegacyPairing = pluginAvailable === false && !context.printer.printer_hostname;
  return (
    <>
      <details open={pluginAvailable === false && context.system.slots.length === 0}
        className="mb-3 rounded-lg border border-white/10 p-3">
        <summary className="cursor-pointer text-xs text-gray-200">
          {t('presetSlots.happyHare.connectionTitle')}
        </summary>
        <p className="my-2 text-xs text-gray-400">{t('presetSlots.happyHare.connectionGuide')}</p>
        <a href="https://moggieuk.github.io/Happy-Hare-Doc/Feature-Spoolman/#filamenthub"
          target="_blank" rel="noopener noreferrer" className="text-xs text-sky-200 underline">
          {t('presetSlots.happyHare.documentation')}
        </a>
      </details>
      {needsLegacyPairing && (
        <PairingStep gates={context.gates} hasContact={context.printer.reports_feed} />
      )}
    </>
  );
}

function HappyHareActions(context: AdapterViewContext) {
  const pluginAvailable = useHappyHareMaterialRefresh();
  return (
    <HappyHareRefreshAction
      printer={context.printer}
      system={context.system}
      pluginAvailable={pluginAvailable}
    />
  );
}

export const happyHareAdapter: FeedAdapter = {
  id: 'happy_hare',
  onboarding: {
    connectionProvider: 'manual',
    connectionLabelKey: 'printerSetup.connections.moonraker',
    connectionHintKey: 'printerSetup.connections.happyHareHint',
    methods: ['native', 'orca', 'edge'],
    orcaProbe: true,
    topologies: [{ id: 'gates', labelKey: 'presetSlots.feedSystem.happy_hare', kind: 'mmu',
      count: { labelKey: 'printerSetup.feed.gateCount', initial: 4, max: 256 },
      slots: (count) => Array.from({ length: count }, (_, provider_index) => ({ provider_index, kind: 'gate' })),
      extras: [{ labelKey: 'printerSetup.feed.bypass', index: 1023, kind: 'bypass' }] }],
  },
  labelKey: 'presetSlots.feedSystem.happy_hare',
  fixedSlots: null,
  topologyFromProvider: true,
  supportsEdge: true,
  capabilities: ['read', 'write', 'presence', 'spool_identity', 'consumption', 'local_command'],
  link: {
    hintKey: 'presetSlots.happyHare.linkHint',
    snippet: (baseUrl, apiKey) => `[spoolman]
server: ${baseUrl}/${apiKey}`,
  },
  deliverAssignment: async ({ printer, system, slot }) => {
    const result = await requestHappyHareSlotAssignment(printer.id, system.id, {
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
  renderCreateHelp: () => <HappyHareCreationGuide />,
  renderSettings: ({ printer }) => <HostnameField printer={printer} />,
  renderActions: (context) => <HappyHareActions {...context} />,
  renderSetup: (context) => <HappyHareSetup {...context} />,
};
