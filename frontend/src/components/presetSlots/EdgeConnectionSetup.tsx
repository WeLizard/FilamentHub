import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Activity, Check, Clock, Copy, Loader2, ShieldCheck } from 'lucide-react';
import { printerBridgeAPI } from '../../api/client';
import { translateApiError } from '../../utils/translateApiError';
import { toast } from '../Toast';
import { ConfirmModal } from '../ConfirmModal';
import type { AdapterViewContext } from './adapters/types';

const EDGE_TRANSPORT = 'edge_agent' as const;

export function EdgeConnectionSetup({
  printer,
  system,
  collapsible = false,
}: Pick<AdapterViewContext, 'printer' | 'system'> & { collapsible?: boolean }) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [issuing, setIssuing] = useState(false);
  const [confirmRevoke, setConfirmRevoke] = useState(false);
  const [revoking, setRevoking] = useState(false);
  const [copied, setCopied] = useState(false);
  const [pairingCode, setPairingCode] = useState<string | null>(null);
  const [pairingWasPending, setPairingWasPending] = useState(false);
  const [pollDeadline, setPollDeadline] = useState(() => Date.now() + 60_000);

  const statusQuery = useQuery({
    queryKey: ['printer-bridge-status', printer.id, system.id, EDGE_TRANSPORT],
    queryFn: () => printerBridgeAPI.status(printer.id, system.id, EDGE_TRANSPORT),
    staleTime: 10_000,
    refetchOnWindowFocus: true,
    refetchInterval: (query) => {
      const status = query.state.data;
      const pairingPending = Boolean(
        status?.pairing_expires_at
          && Date.parse(status.pairing_expires_at) > Date.now(),
      );
      const awaitingFirstData = Boolean(status?.paired && !status.last_observation_at);
      return (pairingPending || awaitingFirstData) && Date.now() < pollDeadline
        ? 5_000
        : false;
    },
  });
  const status = statusQuery.data;
  const pairingPending = Boolean(
    status?.pairing_expires_at
      && Date.parse(status.pairing_expires_at) > Date.now(),
  );
  const hasReceivedData = Boolean(status?.paired && status.last_observation_at);
  const awaitingFirstData = Boolean(status?.paired && !status.last_observation_at);

  useEffect(() => {
    if (status?.last_observation_at) {
      void queryClient.invalidateQueries({ queryKey: ['physical-printers'] });
    }
  }, [status?.last_observation_at, queryClient]);

  useEffect(() => {
    if (!pairingCode) return;
    if (pairingPending) {
      setPairingWasPending(true);
    } else if (pairingWasPending) {
      setPairingCode(null);
      setCopied(false);
      setPairingWasPending(false);
    }
  }, [pairingCode, pairingPending, pairingWasPending]);

  const issuePairingCode = async () => {
    setIssuing(true);
    try {
      const issued = await printerBridgeAPI.issuePairingCode(
        printer.id,
        system.id,
        EDGE_TRANSPORT,
      );
      const expiresAt = Date.parse(issued.expires_at);
      setPollDeadline(expiresAt);
      setPairingWasPending(false);
      setPairingCode(issued.pairing_code);
      setCopied(false);
      await statusQuery.refetch();
    } catch (err: any) {
      toast.error(translateApiError(t, err?.response?.data?.detail, t('common.error')));
    } finally {
      setIssuing(false);
    }
  };

  const copyPairingCode = async () => {
    if (!pairingCode) return;
    try {
      await navigator.clipboard.writeText(pairingCode);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      toast.error(t('common.error'));
    }
  };

  const revoke = async () => {
    setRevoking(true);
    try {
      await printerBridgeAPI.revoke(printer.id, system.id, EDGE_TRANSPORT);
      setPairingCode(null);
      setConfirmRevoke(false);
      await statusQuery.refetch();
      await queryClient.invalidateQueries({ queryKey: ['physical-printers'] });
    } catch (err: any) {
      toast.error(translateApiError(t, err?.response?.data?.detail, t('common.error')));
    } finally {
      setRevoking(false);
    }
  };

  const connectionOptions = JSON.stringify({
    id: `printer-${printer.id}`,
    name: printer.name,
    adapter: 'moonraker',
    material_provider: status?.provider ?? system.provider,
    moonraker_url: 'http://PRINTER-LAN-IP:7125',
    pairing_code: pairingCode,
  }, null, 2);

  const lastContact = status?.last_seen_at
    ? new Date(status.last_seen_at).toLocaleString(i18n.language)
    : null;

  const content = (
    <div className="mb-3 rounded-lg border border-sky-400/20 bg-sky-500/[0.07] px-3 py-2">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <Activity className="h-3.5 w-3.5 shrink-0 text-sky-300" />
        <span className="text-xs font-medium text-sky-100">
          {t('presetSlots.edge.title')}
        </span>
        {statusQuery.isLoading ? (
          <span className="inline-flex items-center gap-1 text-[11px] text-gray-400">
            <Loader2 className="h-3 w-3 animate-spin" />
            {t('presetSlots.edge.checking')}
          </span>
        ) : statusQuery.isError ? (
          <span className="text-[11px] text-red-300">
            {t('presetSlots.edge.statusUnavailable')}
          </span>
        ) : hasReceivedData ? (
          <span className="inline-flex items-center gap-1 text-[11px] text-emerald-300">
            <Check className="h-3 w-3" />
            {t('presetSlots.edge.connected')}
          </span>
        ) : awaitingFirstData ? (
          <span className="inline-flex items-center gap-1 text-[11px] text-amber-200">
            <Clock className="h-3 w-3" />
            {t('presetSlots.edge.awaitingData')}
          </span>
        ) : pairingPending ? (
          <span className="inline-flex items-center gap-1 text-[11px] text-amber-200">
            <Clock className="h-3 w-3" />
            {t('presetSlots.edge.waiting')}
          </span>
        ) : (
          <span className="text-[11px] text-gray-500">
            {t('presetSlots.edge.notConnected')}
          </span>
        )}

        <button
          type="button"
          onClick={statusQuery.isError ? () => statusQuery.refetch() : issuePairingCode}
          disabled={issuing || statusQuery.isLoading}
          className="ml-auto inline-flex items-center gap-1.5 rounded-lg border border-sky-300/20 bg-sky-300/10 px-2.5 py-1 text-[11px] font-medium text-sky-100 transition hover:bg-sky-300/20 disabled:opacity-40"
        >
          {issuing && <Loader2 className="h-3 w-3 animate-spin" />}
          {t(statusQuery.isError
            ? 'presetSlots.edge.retry'
            : status?.paired
              ? 'presetSlots.edge.replaceCode'
              : 'presetSlots.edge.createCode')}
        </button>
      </div>

      <p className="mt-1 text-[11px] leading-4 text-gray-400">
        {t('presetSlots.edge.description')}
      </p>
      <a href="https://github.com/WeLizard/FilamentHub/tree/main/edge-agent#installation"
        target="_blank" rel="noopener noreferrer" className="text-xs text-sky-200 underline">
        {t('presetSlots.happyHare.installation')}
      </a>
      <button type="button" onClick={() => statusQuery.refetch()}
        disabled={statusQuery.isFetching} className="ml-3 text-xs text-sky-200 underline">
        {t('presetSlots.happyHare.refreshStatus')}
      </button>

      {status?.node_instance_id && (
        <p className="mt-2 break-all text-xs text-gray-300">
          {t('presetSlots.edge.nodeLabel')} <code>{status.node_instance_id}</code>
        </p>
      )}

      {status?.paired && (
        <button type="button" onClick={() => setConfirmRevoke(true)}
          className="mt-2 text-xs text-red-300 underline">
          {t('presetSlots.edge.disconnect')}
        </button>
      )}

      {lastContact && (
        <p className="mt-1 text-[11px] text-gray-500">
          {t('presetSlots.edge.lastContact', { date: lastContact })}
        </p>
      )}

      {pairingCode && (
        <div className="mt-2 rounded-lg border border-white/10 bg-black/20 p-2.5">
          <span className="text-[11px] font-medium text-gray-300">
            {t('presetSlots.edge.codeLabel')}
          </span>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <code className="rounded border border-white/10 bg-black/30 px-2 py-1 text-sm tracking-wide text-white">
              {pairingCode}
            </code>
            <button
              type="button"
              onClick={copyPairingCode}
              className="inline-flex items-center gap-1 rounded px-2 py-1 text-[11px] text-sky-200 hover:bg-white/10"
            >
              {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
              {t(copied
                ? 'presetSlots.edge.copied'
                : 'presetSlots.edge.copyCode')}
            </button>
          </div>
          <p className="mt-1.5 text-[11px] leading-4 text-gray-400">
            {t('presetSlots.edge.codeHint')}
          </p>
          <p className="mt-2 text-xs text-gray-300">{t('presetSlots.edge.addToNode')}</p>
          <pre className="mt-2 overflow-x-auto rounded bg-black/30 p-2 text-[11px] text-gray-200">
            {connectionOptions}
          </pre>
        </div>
      )}

      <p className="mt-2 flex items-start gap-1.5 text-[11px] leading-4 text-sky-100/65">
        <ShieldCheck className="mt-0.5 h-3 w-3 shrink-0" />
        {t('presetSlots.edge.security')}
      </p>
      <ConfirmModal isOpen={confirmRevoke} onClose={() => { if (!revoking) setConfirmRevoke(false); }}
        onConfirm={revoke} isLoading={revoking} variant="warning"
        title={t('presetSlots.edge.disconnect')} message={t('presetSlots.edge.disconnectHint')} />
    </div>
  );
  return collapsible ? (
    <details className="mb-3 rounded-lg border border-white/10 p-3">
      <summary className="cursor-pointer text-xs text-gray-200">
        {t('presetSlots.edge.connectionTitle')}
      </summary>
      <div className="mt-2">{content}</div>
    </details>
  ) : content;
}
