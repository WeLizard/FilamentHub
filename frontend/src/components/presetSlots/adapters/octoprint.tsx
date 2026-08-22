import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  Check,
  Copy,
  Download,
  Info,
  Link2,
  Loader2,
  Package,
  Unplug,
  X,
} from 'lucide-react';

import { downloadsAPI, octoprintBridgeAPI } from '../../../api/client';
import { ModalOverlay } from '../../ModalOverlay';
import { toast } from '../../Toast';
import { translateApiError } from '../../../utils/translateApiError';
import type { AdapterViewContext, FeedAdapter } from './types';

function BridgeConnectionStatus({ printer, system }: AdapterViewContext) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [revoking, setRevoking] = useState(false);

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
        onClick={revoke}
        disabled={revoking}
        title={t('presetSlots.octoprint.disconnect')}
        aria-label={t('presetSlots.octoprint.disconnect')}
        className="inline-flex rounded p-1 text-gray-500 transition hover:bg-white/10 hover:text-red-300 disabled:opacity-40"
      >
        {revoking ? <Loader2 className="h-3 w-3 animate-spin" /> : <Unplug className="h-3 w-3" />}
      </button>
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
  capabilities: ['read', 'write', 'presence', 'spool_identity', 'consumption'],
  contactMode: 'periodic',
  slotCountLabelKey: 'presetSlots.octoprint.slotCount',
  slotCountSummaryKey: 'presetSlots.gates',
  link: null,
  renderCreateHelp: () => <CreationGuide />,
  renderSettings: (context) => <BridgeConnectionStatus {...context} />,
  renderSetup: (context) => <BridgeSetup {...context} />,
};
