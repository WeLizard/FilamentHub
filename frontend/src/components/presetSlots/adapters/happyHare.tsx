import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, Check, Clock, Copy, Loader2, RefreshCw, X } from 'lucide-react';

import { devicesAPI } from '../../../api/client';
import type { UserSpool } from '../../../api/client';
import {
  isPluginEmbed,
  requestHappyHareAction,
  requestPluginCapabilities,
  subscribeToPluginCapabilities,
} from '../../../utils/pluginBridge';
import type {
  HappyHareActionResult,
  HappyHareAssignmentChange,
} from '../../../utils/pluginBridge';
import { toast } from '../../Toast';
import { ModalOverlay } from '../../ModalOverlay';
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

function spoolLabel(
  spools: UserSpool[],
  spoolId: number | null,
  unassignedLabel: string,
): string {
  if (spoolId == null) return unassignedLabel;
  const spool = spools.find((item) => item.id === spoolId);
  if (!spool) return `#${spoolId}`;
  const filament = spool.filament;
  const name = [filament?.brand_name, filament?.name].filter(Boolean).join(' ');
  return name ? `${name} · #${spoolId}` : `#${spoolId}`;
}

function AssignmentChanges({
  changes,
  spools,
}: {
  changes: HappyHareAssignmentChange[];
  spools: UserSpool[];
}) {
  const { t } = useTranslation();
  return (
    <div className="mt-3 max-h-64 space-y-1.5 overflow-y-auto pr-1">
      <div className="grid grid-cols-[auto_1fr_auto_1fr] gap-2 px-3 text-[11px] font-medium text-gray-500">
        <span />
        <span>{t('presetSlots.happyHare.refresh.currentAssignment')}</span>
        <span />
        <span>{t('presetSlots.happyHare.refresh.targetAssignment')}</span>
      </div>
      {changes.map((change) => (
        <div
          key={change.gate}
          className="grid grid-cols-[auto_1fr_auto_1fr] items-center gap-2 rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs"
        >
          <span className="font-medium text-white">
            {t('presetSlots.happyHare.refresh.gate', { gate: change.gate + 1 })}
          </span>
          <span className="truncate text-gray-400">
            {spoolLabel(
              spools,
              change.actualSpoolId,
              t('presetSlots.assignment.notAssigned'),
            )}
          </span>
          <span className="text-gray-600">→</span>
          <span className="truncate text-purple-200">
            {spoolLabel(
              spools,
              change.desiredSpoolId,
              t('presetSlots.assignment.notAssigned'),
            )}
          </span>
        </div>
      ))}
    </div>
  );
}

function HappyHareRefreshAction({
  printer,
  system,
  spools,
  pluginAvailable,
}: Pick<AdapterViewContext, 'printer' | 'system' | 'spools'> & {
  pluginAvailable: boolean | null;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [loading, setLoading] = useState<'preview' | 'apply' | null>(null);
  const [preview, setPreview] = useState<HappyHareActionResult | null>(null);
  const [copied, setCopied] = useState(false);
  const [fallbackOpen, setFallbackOpen] = useState(false);
  const changes = preview?.changes ?? [];
  const busy = preview?.printState === 'printing' || preview?.printState === 'paused';
  const canApply = preview?.ok === true
    && changes.length > 0
    && preview.spoolmanSupport === 'pull'
    && !busy;
  const errorText = (code?: string | null) => (
    t(`presetSlots.happyHare.refresh.errors.${code || 'unknown'}`, {
      defaultValue: t('presetSlots.happyHare.refresh.errors.unknown'),
    })
  );

  const refreshData = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['physical-printers'] }),
      queryClient.invalidateQueries({ queryKey: ['devices'] }),
    ]);
  };

  const check = async () => {
    setLoading('preview');
    try {
      const result = await requestHappyHareAction('preview', printer.id, system.id);
      await refreshData();
      if (!result.ok) {
        setPreview(null);
        toast.error(errorText(result.code));
      } else if ((result.changes?.length ?? 0) === 0) {
        setPreview(null);
        toast.success(t('presetSlots.happyHare.refresh.inSync', {
          count: result.gateCount ?? 0,
        }));
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
      const result = await requestHappyHareAction('apply', printer.id, system.id);
      await refreshData();
      if (result.ok) {
        toast.success(t('presetSlots.happyHare.refresh.applied'));
        setPreview(null);
      } else {
        toast.error(errorText(result.code));
      }
    } catch {
      toast.error(errorText('timeout'));
    } finally {
      setLoading(null);
    }
  };

  const copyFallback = async () => {
    try {
      await navigator.clipboard.writeText('MMU_SPOOLMAN REFRESH=1');
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      toast.error(t('common.error'));
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => {
          if (pluginAvailable) void check();
          else if (pluginAvailable === false) setFallbackOpen(true);
        }}
        disabled={pluginAvailable == null || loading != null}
        title={t('presetSlots.happyHare.refresh.description')}
        className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-300/25 bg-emerald-500/10 px-2.5 py-1.5 text-xs font-medium text-emerald-100 transition hover:bg-emerald-500/20 disabled:cursor-wait disabled:opacity-40"
      >
        {loading === 'preview'
          ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
          : <RefreshCw className="h-3.5 w-3.5" />}
        {t('presetSlots.happyHare.refresh.check')}
      </button>

      {fallbackOpen && (
        <ModalOverlay onClose={() => setFallbackOpen(false)}>
          <div className="w-full max-w-lg rounded-2xl border border-white/15 bg-gray-950 p-5 text-white shadow-2xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-lg font-semibold">
                  {t('presetSlots.happyHare.refresh.title')}
                </h3>
                <p className="mt-1 text-sm leading-5 text-gray-400">
                  {t('presetSlots.happyHare.refresh.fallback')}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setFallbackOpen(false)}
                className="rounded-lg p-1.5 text-gray-400 hover:bg-white/10 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <button
              type="button"
              onClick={copyFallback}
              className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm text-gray-200 transition hover:bg-white/10"
            >
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              {t(copied
                ? 'presetSlots.pairing.copied'
                : 'presetSlots.happyHare.refresh.copyCommand')}
            </button>
          </div>
        </ModalOverlay>
      )}

      {preview?.ok && changes.length > 0 && (
        <ModalOverlay
          onClose={() => { if (!loading) setPreview(null); }}
          closeOnOverlayClick={!loading}
          closeOnEscape={!loading}
        >
          <div className="w-full max-w-2xl rounded-2xl border border-white/15 bg-gray-950 p-5 text-white shadow-2xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="text-lg font-semibold">
                  {t('presetSlots.happyHare.refresh.previewTitle')}
                </h3>
                <p className="mt-1 text-sm leading-5 text-gray-400">
                  {t('presetSlots.happyHare.refresh.previewDescription', {
                    count: changes.length,
                  })}
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
            <AssignmentChanges changes={changes} spools={spools} />
            {preview.spoolmanSupport !== 'pull' && (
              <p className="mt-3 rounded-lg border border-amber-400/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                {t('presetSlots.happyHare.refresh.pullRequired')}
              </p>
            )}
            {busy && (
              <p className="mt-3 rounded-lg border border-amber-400/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                {t('presetSlots.happyHare.refresh.busy')}
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
              <button
                type="button"
                onClick={apply}
                disabled={!canApply || loading != null}
                className="inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {loading === 'apply' && <Loader2 className="h-4 w-4 animate-spin" />}
                {t('presetSlots.happyHare.refresh.apply')}
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}
    </>
  );
}

function HappyHareSetup(context: AdapterViewContext) {
  const pluginAvailable = useHappyHarePlugin();
  if (pluginAvailable !== false || context.printer.printer_hostname) return null;
  return <PairingStep gates={context.gates} hasContact={context.printer.reports_feed} />;
}

function HappyHareActions(context: AdapterViewContext) {
  const pluginAvailable = useHappyHarePlugin();
  return (
    <HappyHareRefreshAction
      printer={context.printer}
      system={context.system}
      spools={context.spools}
      pluginAvailable={pluginAvailable}
    />
  );
}

export const happyHareAdapter: FeedAdapter = {
  id: 'happy_hare',
  labelKey: 'presetSlots.feedSystem.happy_hare',
  fixedSlots: null,
  topologyFromProvider: true,
  capabilities: ['read', 'write', 'presence', 'spool_identity', 'consumption', 'local_command'],
  link: {
    hintKey: 'presetSlots.happyHare.linkHint',
    snippet: (baseUrl, apiKey) => `[spoolman]
server: ${baseUrl}/${apiKey}
sync_rate: 5`,
  },
  renderCreateHelp: () => <HappyHareCreationGuide />,
  renderSettings: ({ printer }) => <HostnameField printer={printer} />,
  renderActions: (context) => <HappyHareActions {...context} />,
  renderSetup: (context) => <HappyHareSetup {...context} />,
};
