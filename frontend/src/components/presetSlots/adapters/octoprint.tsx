import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  ArrowRight,
  Check,
  Copy,
  Download,
  Info,
  Link2,
  Loader2,
  Package,
  Plus,
  RefreshCw,
  Route,
  Trash2,
  Unplug,
  X,
} from 'lucide-react';

import {
  downloadsAPI,
  octoprintBridgeAPI,
  type OctoPrintBridgeStatus,
  type OctoPrintToolSlotMapping,
} from '../../../api/client';
import { ModalOverlay } from '../../ModalOverlay';
import { toast } from '../../Toast';
import { translateApiError } from '../../../utils/translateApiError';
import type { AdapterViewContext, FeedAdapter } from './types';

interface RoutingEditorProps {
  printer: AdapterViewContext['printer'];
  system: AdapterViewContext['system'];
  status: OctoPrintBridgeStatus;
  onClose: () => void;
  onRefresh: () => Promise<unknown>;
}

function RoutingEditor({ printer, system, status, onClose, onRefresh }: RoutingEditorProps) {
  const { t } = useTranslation();
  const [mode, setMode] = useState<'manual' | 'tools'>(status.routing.mode);
  const [mapping, setMapping] = useState<OctoPrintToolSlotMapping[]>(
    status.routing.tool_slot_map,
  );
  const [saving, setSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    setMode(status.routing.mode);
    setMapping(status.routing.tool_slot_map);
  }, [status.routing]);

  const slots = [...system.slots]
    .filter((slot) => slot.active)
    .sort((left, right) => left.provider_index - right.provider_index);
  const mappedTools = new Set(mapping.map((item) => item.tool_index));
  const hasDuplicateTool = mappedTools.size !== mapping.length;
  const canSave = mode === 'manual' || (mapping.length > 0 && !hasDuplicateTool);

  const addMapping = () => {
    const slot = slots[0];
    if (!slot) return;
    let toolIndex = 0;
    while (mappedTools.has(toolIndex)) toolIndex += 1;
    setMapping((current) => [
      ...current,
      { tool_index: toolIndex, slot_index: slot.provider_index },
    ]);
  };

  const updateMapping = (
    index: number,
    field: keyof OctoPrintToolSlotMapping,
    value: number,
  ) => {
    setMapping((current) => current.map((item, itemIndex) => (
      itemIndex === index ? { ...item, [field]: value } : item
    )));
  };

  const refresh = async () => {
    setRefreshing(true);
    try {
      await onRefresh();
    } finally {
      setRefreshing(false);
    }
  };

  const save = async () => {
    if (!canSave) return;
    setSaving(true);
    try {
      await octoprintBridgeAPI.updateRouting(printer.id, system.id, {
        mode,
        tool_slot_map: mode === 'tools' ? mapping : [],
        expected_revision: status.routing.revision,
      });
      await onRefresh();
      toast.success(t('presetSlots.octoprint.routingSaved'));
      onClose();
    } catch (err: any) {
      toast.error(translateApiError(t, err?.response?.data?.detail, t('common.error')));
    } finally {
      setSaving(false);
    }
  };

  return (
    <ModalOverlay onClose={onClose}>
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="octoprint-routing-title"
        className="w-full max-w-xl overflow-hidden rounded-2xl border border-cyan-300/20 bg-[#161527] text-left shadow-2xl"
      >
        <header className="flex items-center gap-3 border-b border-white/10 px-5 py-4">
          <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-cyan-400/10 text-cyan-300">
            <Route className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 id="octoprint-routing-title" className="font-semibold text-white">
              {t('presetSlots.octoprint.routingTitle')}
            </h2>
            <p className="mt-0.5 text-xs leading-4 text-gray-400">
              {t('presetSlots.octoprint.routingDescription')}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            title={t('common.close')}
            aria-label={t('common.close')}
            className="rounded-lg p-1.5 text-gray-500 transition hover:bg-white/10 hover:text-white"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="space-y-4 p-5">
          <div className="grid grid-cols-2 gap-2 rounded-xl border border-white/10 bg-black/15 p-1">
            {(['manual', 'tools'] as const).map((value) => (
              <button
                key={value}
                type="button"
                onClick={() => setMode(value)}
                className={`rounded-lg px-3 py-2 text-xs font-medium transition ${
                  mode === value
                    ? 'bg-cyan-400/15 text-cyan-100'
                    : 'text-gray-400 hover:bg-white/5 hover:text-gray-200'
                }`}
              >
                {t(`presetSlots.octoprint.routingMode.${value}`)}
              </button>
            ))}
          </div>

          {mode === 'manual' ? (
            <div className="rounded-xl border border-white/10 bg-white/[0.03] px-4 py-3 text-xs leading-5 text-gray-400">
              {t('presetSlots.octoprint.manualRoutingHint')}
            </div>
          ) : (
            <div className="space-y-2">
              {mapping.map((item, index) => {
                const slotExists = slots.some(
                  (slot) => slot.provider_index === item.slot_index,
                );
                return (
                  <div
                    key={`${item.tool_index}-${index}`}
                    className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1.5fr)_auto] items-center gap-2 rounded-xl border border-white/10 bg-white/[0.03] p-2"
                  >
                    <label className="flex min-w-0 items-center gap-1.5 text-xs text-gray-400">
                      <span>T</span>
                      <input
                        type="number"
                        min={0}
                        max={1023}
                        value={item.tool_index}
                        onChange={(event) => updateMapping(
                          index,
                          'tool_index',
                          Math.max(0, Number.parseInt(event.target.value || '0', 10)),
                        )}
                        className="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/25 px-2 py-1.5 text-sm text-white outline-none focus:border-cyan-400/50"
                        aria-label={t('presetSlots.octoprint.toolIndex')}
                      />
                    </label>
                    <ArrowRight className="h-3.5 w-3.5 text-gray-600" />
                    <select
                      value={item.slot_index}
                      onChange={(event) => updateMapping(
                        index,
                        'slot_index',
                        Number.parseInt(event.target.value, 10),
                      )}
                      className="min-w-0 rounded-lg border border-white/10 bg-[#111020] px-2 py-1.5 text-xs text-white outline-none focus:border-cyan-400/50"
                      aria-label={t('presetSlots.octoprint.targetSlot')}
                    >
                      {!slotExists && (
                        <option value={item.slot_index}>
                          {t('presetSlots.octoprint.missingSlot', { count: item.slot_index + 1 })}
                        </option>
                      )}
                      {slots.map((slot) => (
                        <option key={slot.id} value={slot.provider_index}>
                          {slot.label || t('presetSlots.octoprint.slotLabel', {
                            count: slot.provider_index + 1,
                          })}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={() => setMapping((current) => current.filter(
                        (_, itemIndex) => itemIndex !== index,
                      ))}
                      title={t('presetSlots.octoprint.removeTool')}
                      aria-label={t('presetSlots.octoprint.removeTool')}
                      className="rounded-lg p-1.5 text-gray-500 transition hover:bg-red-400/10 hover:text-red-300"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                );
              })}

              <button
                type="button"
                onClick={addMapping}
                disabled={!slots.length || mapping.length >= 256}
                className="inline-flex items-center gap-1.5 rounded-lg border border-dashed border-cyan-300/25 px-3 py-2 text-xs text-cyan-200 transition hover:bg-cyan-400/10 disabled:cursor-not-allowed disabled:opacity-40"
              >
                <Plus className="h-3.5 w-3.5" />
                {t('presetSlots.octoprint.addTool')}
              </button>

              {hasDuplicateTool && (
                <p className="text-xs text-amber-300">
                  {t('presetSlots.octoprint.duplicateTool')}
                </p>
              )}
              {!slots.length && (
                <p className="text-xs text-amber-300">
                  {t('presetSlots.octoprint.noSlots')}
                </p>
              )}
            </div>
          )}

          <p className="text-[11px] leading-4 text-gray-500">
            {t('presetSlots.octoprint.routingTopologyNote')}
          </p>
        </div>

        <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-white/10 px-5 py-4">
          <div className="flex items-center gap-2 text-[11px] text-gray-500">
            <button
              type="button"
              onClick={refresh}
              disabled={refreshing}
              className="inline-flex items-center gap-1 rounded-lg px-2 py-1.5 transition hover:bg-white/5 hover:text-gray-300 disabled:opacity-40"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`} />
              {t('presetSlots.octoprint.routingRefresh')}
            </button>
            <span>{t('presetSlots.octoprint.routingRevision', {
              count: status.routing.revision,
            })}</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg px-3 py-2 text-xs text-gray-400 transition hover:bg-white/5 hover:text-white"
            >
              {t('common.cancel')}
            </button>
            <button
              type="button"
              onClick={save}
              disabled={saving || !canSave}
              className="inline-flex items-center gap-1.5 rounded-lg bg-cyan-500 px-4 py-2 text-xs font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-40"
            >
              {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              {t('common.save')}
            </button>
          </div>
        </footer>
      </section>
    </ModalOverlay>
  );
}

function BridgeConnectionStatus({ printer, system }: AdapterViewContext) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [revoking, setRevoking] = useState(false);
  const [routingOpen, setRoutingOpen] = useState(false);

  const statusQuery = useQuery({
    queryKey: ['octoprint-bridge-status', printer.id, system.id],
    queryFn: () => octoprintBridgeAPI.status(printer.id, system.id),
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  });
  const status = statusQuery.data;

  const revoke = async () => {
    setRevoking(true);
    try {
      await octoprintBridgeAPI.revoke(printer.id, system.id);
      await Promise.all([
        statusQuery.refetch(),
        queryClient.invalidateQueries({ queryKey: ['physical-printers'] }),
      ]);
      toast.success(t('presetSlots.octoprint.disconnected'));
    } catch (err: any) {
      toast.error(translateApiError(t, err?.response?.data?.detail, t('common.error')));
    } finally {
      setRevoking(false);
    }
  };

  if (!status?.paired) return null;

  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-gray-400">
      <span className="inline-flex items-center gap-1">
        <Check className="h-3 w-3 shrink-0 text-emerald-400" />
        {t('presetSlots.link.label')}
      </span>
      <span className="text-gray-200">FilamentHub Bridge</span>
      {status.octoprint_version && (
        <span>OctoPrint {status.octoprint_version}</span>
      )}
      {status.plugin_version && (
        <span>Bridge {status.plugin_version}</span>
      )}
      {status.active_slot_index != null && (
        <span className="text-emerald-200/75">
          {t('presetSlots.octoprint.activeSlot', { count: status.active_slot_index + 1 })}
        </span>
      )}
      <button
        type="button"
        onClick={() => setRoutingOpen(true)}
        title={t('presetSlots.octoprint.routingTitle')}
        className="inline-flex items-center gap-1 rounded px-1.5 py-1 text-cyan-200/75 transition hover:bg-white/10 hover:text-cyan-100"
      >
        <Route className="h-3 w-3" />
        {status.routing.mode === 'tools'
          ? t('presetSlots.octoprint.routingSummary', {
            count: status.routing.tool_slot_map.length,
          })
          : t('presetSlots.octoprint.routingMode.manual')}
        {status.routing.applied_revision !== status.routing.revision && (
          <span className="rounded bg-amber-300/10 px-1 py-0.5 text-[9px] text-amber-200">
            {t('presetSlots.octoprint.routingPending')}
          </span>
        )}
      </button>
      <button
        type="button"
        onClick={revoke}
        disabled={revoking}
        title={t('presetSlots.octoprint.disconnect')}
        aria-label={t('presetSlots.octoprint.disconnect')}
        className="inline-flex rounded p-1 text-gray-500 transition hover:bg-white/10 hover:text-red-300 disabled:opacity-40"
      >
        {revoking ? <Loader2 className="h-3 w-3 animate-spin" /> : <Unplug className="h-3 w-3" />}
      </button>
      {routingOpen && (
        <RoutingEditor
          printer={printer}
          system={system}
          status={status}
          onClose={() => setRoutingOpen(false)}
          onRefresh={() => statusQuery.refetch()}
        />
      )}
    </div>
  );
}

function BridgeSetup({ printer, system }: AdapterViewContext) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [pairingCode, setPairingCode] = useState<string | null>(null);
  const [pairingExpiresAt, setPairingExpiresAt] = useState<string | null>(null);
  const [issuing, setIssuing] = useState(false);
  const [copied, setCopied] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);

  const statusQuery = useQuery({
    queryKey: ['octoprint-bridge-status', printer.id, system.id],
    queryFn: () => octoprintBridgeAPI.status(printer.id, system.id),
    staleTime: 10_000,
    refetchOnWindowFocus: true,
    // Fast only while the user is visibly pairing. Once paired, focus/manual
    // invalidation is enough; an idle open tab must not poll forever.
    refetchInterval: (query) => {
      const status = query.state.data;
      const expiresAtMs = pairingExpiresAt ? Date.parse(pairingExpiresAt) : Number.NaN;
      if (
        pairingCode
        && !status?.paired
        && (Number.isNaN(expiresAtMs) || Date.now() < expiresAtMs)
      ) {
        return 5_000;
      }
      return false;
    },
  });
  const status = statusQuery.data;

  const downloadsQuery = useQuery({
    queryKey: ['plugin-downloads'],
    queryFn: () => downloadsAPI.getPluginDownloads(),
    enabled: guideOpen,
    staleTime: 5 * 60_000,
  });
  const bridgeWheel = downloadsQuery.data?.packages.find(
    (item) => item.plugin === 'octoprint',
  );

  useEffect(() => {
    if (!status?.paired) return;
    setPairingCode(null);
    setPairingExpiresAt(null);
    void queryClient.invalidateQueries({ queryKey: ['physical-printers'] });
  }, [queryClient, status?.paired]);

  const issueCode = async () => {
    setIssuing(true);
    try {
      const result = await octoprintBridgeAPI.issuePairingCode(printer.id, system.id);
      setPairingCode(result.pairing_code);
      setPairingExpiresAt(result.expires_at);
      await Promise.all([
        statusQuery.refetch(),
        queryClient.invalidateQueries({ queryKey: ['physical-printers'] }),
      ]);
    } catch (err: any) {
      toast.error(translateApiError(t, err?.response?.data?.detail, t('common.error')));
    } finally {
      setIssuing(false);
    }
  };

  const copyCode = async () => {
    if (!pairingCode) return;
    try {
      await navigator.clipboard.writeText(pairingCode);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      toast.error(t('common.error'));
    }
  };

  if (statusQuery.isLoading) {
    return (
      <div className="mb-3 flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-gray-400">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        {t('presetSlots.octoprint.checking')}
      </div>
    );
  }

  if (status?.paired) return null;

  return (
    <div className="mb-3 rounded-lg border border-amber-400/25 bg-amber-500/10 px-3 py-2">
      <div className="flex flex-wrap items-center gap-2">
        <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-300" />
        <span className="text-xs font-medium text-amber-100">
          {t('presetSlots.octoprint.setupTitle')}
        </span>
        <button
          type="button"
          onClick={() => setGuideOpen(true)}
          className="inline-flex items-center gap-1 rounded px-1 py-0.5 text-[11px] text-amber-200 transition hover:bg-white/10 hover:text-amber-100"
        >
          <Info className="h-3.5 w-3.5" />
          {t('presetSlots.octoprint.bridgeDocs')}
        </button>
      </div>
      <p className="mt-1 text-[11px] leading-4 text-amber-100/70">
        {t('presetSlots.octoprint.setupDescription')}
      </p>

      {pairingCode ? (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <code className="rounded-lg border border-amber-300/20 bg-black/30 px-3 py-1.5 text-sm font-semibold tracking-wider text-white">
            {pairingCode}
          </code>
          <button
            type="button"
            onClick={copyCode}
            className="rounded-lg border border-white/10 p-1.5 text-amber-200 transition hover:bg-white/10"
            title={t('presetSlots.pairing.copy')}
          >
            {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          </button>
          {pairingExpiresAt && (
            <span className="text-[10px] text-amber-100/60">
              {t('presetSlots.octoprint.codeExpires', {
                time: new Date(pairingExpiresAt).toLocaleTimeString(i18n.language, {
                  hour: '2-digit',
                  minute: '2-digit',
                }),
              })}
            </span>
          )}
        </div>
      ) : (
        <button
          type="button"
          onClick={issueCode}
          disabled={issuing}
          className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-amber-300/15 px-3 py-1.5 text-xs font-medium text-amber-100 transition hover:bg-amber-300/25 disabled:opacity-40"
        >
          {issuing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Link2 className="h-3.5 w-3.5" />}
          {t('presetSlots.octoprint.issueCode')}
        </button>
      )}

      {guideOpen && (
        <ModalOverlay onClose={() => setGuideOpen(false)}>
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="octoprint-bridge-guide-title"
            className="w-full max-w-lg overflow-hidden rounded-2xl border border-cyan-300/20 bg-[#161527] text-left shadow-2xl"
          >
            <header className="flex items-center gap-3 border-b border-white/10 px-5 py-4">
              <span className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-cyan-400/10 text-cyan-300">
                <Package className="h-5 w-5" />
              </span>
              <div className="min-w-0 flex-1">
                <h2 id="octoprint-bridge-guide-title" className="font-semibold text-white">
                  {t('downloadPage.octoInstallTitle')}
                </h2>
                <p className="mt-0.5 text-xs leading-4 text-gray-400">
                  {t('presetSlots.octoprint.setupDescription')}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setGuideOpen(false)}
                title={t('common.close')}
                aria-label={t('common.close')}
                className="rounded-lg p-1.5 text-gray-500 transition hover:bg-white/10 hover:text-white"
              >
                <X className="h-4 w-4" />
              </button>
            </header>

            <div className="p-5">
              <ol className="space-y-3 text-sm text-gray-300">
                {(['octoInstall1', 'octoInstall2', 'octoInstall3'] as const).map((key, index) => (
                  <li key={key} className="flex gap-3">
                    <span className="font-mono text-xs text-cyan-300">
                      {String(index + 1).padStart(2, '0')}
                    </span>
                    <span>{t(`downloadPage.${key}`)}</span>
                  </li>
                ))}
              </ol>

              {bridgeWheel && (
                <a
                  href={bridgeWheel.download_url}
                  download={bridgeWheel.filename}
                  className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-cyan-500 px-4 py-2.5 text-sm font-semibold text-slate-950 transition hover:bg-cyan-400"
                >
                  <Download className="h-4 w-4" />
                  {t('downloadPage.octoDownload', { version: bridgeWheel.version })}
                </a>
              )}
            </div>
          </section>
        </ModalOverlay>
      )}
    </div>
  );
}

function CreationGuide() {
  const { t } = useTranslation();

  return (
    <div className="mt-4 flex gap-2 rounded-lg border border-sky-400/15 bg-sky-500/[0.06] px-3 py-2">
      <Info className="mt-0.5 h-3.5 w-3.5 shrink-0 text-sky-300" />
      <p className="text-[11px] leading-4 text-gray-400">
        {t('presetSlots.octoprint.createDescription')}
      </p>
    </div>
  );
}

export const octoprintAdapter: FeedAdapter = {
  id: 'octoprint',
  labelKey: 'presetSlots.feedSystem.octoprint',
  fixedSlots: null,
  alwaysCollapsible: true,
  capabilities: ['read', 'write', 'presence', 'spool_identity', 'consumption'],
  contactMode: 'periodic',
  slotCountLabelKey: 'presetSlots.octoprint.slotCount',
  slotCountSummaryKey: 'presetSlots.gates',
  link: null,
  renderCreateHelp: () => <CreationGuide />,
  renderSettings: (context) => <BridgeConnectionStatus {...context} />,
  renderSetup: (context) => <BridgeSetup {...context} />,
};
