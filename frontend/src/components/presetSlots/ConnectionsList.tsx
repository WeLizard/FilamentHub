import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { physicalPrintersAPI } from '../../api/client';
import type { PhysicalPrinter } from '../../api/client';
import { ConfirmDeleteModal } from '../ConfirmDeleteModal';
import { toast } from '../Toast';
import { translateApiError } from '../../utils/translateApiError';
import { connectorChannel, formatLastSeen, systemContactChannels } from '../../utils/deviceLink';
import type { ContactChannel } from '../../utils/deviceLink';

const TONE: Record<ContactChannel['state'], string> = {
  live: 'bg-emerald-500/15 text-emerald-300',
  executor_only: 'bg-amber-500/15 text-amber-300',
  needs_action: 'bg-amber-500/15 text-amber-300',
  unknown: 'bg-amber-500/15 text-amber-300',
  silent: 'bg-white/10 text-gray-400',
  not_configured: 'bg-white/5 text-gray-500',
};

/** Every way FilamentHub hears from this system, each with its own state and time. */
export function ConnectionsList({ printer, systemId }: { printer: PhysicalPrinter; systemId: number }) {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [revoking, setRevoking] = useState<ContactChannel | null>(null);
  const [busy, setBusy] = useState(false);
  const channels = systemContactChannels(printer.contact_channels, systemId);
  if (channels.length === 0) return null;

  const label = (channel: ContactChannel) => {
    if (channel.kind === 'native_spoolman') return t('connections.native');
    const [provider = '', transport = ''] = channel.source.split(':');
    return t(`connections.channel.${connectorChannel({ provider, transport })}`);
  };
  const revoke = async () => {
    if (!revoking?.connector_id) return;
    setBusy(true);
    try {
      await physicalPrintersAPI.revokeConnector(printer.id, revoking.connector_id);
      await queryClient.invalidateQueries({ queryKey: ['physical-printers'] });
      setRevoking(null);
    } catch (err: any) {
      toast.error(translateApiError(t, err?.response?.data?.detail, t('common.error')));
    } finally {
      setBusy(false);
    }
  };

  return (
    <details className="mb-3 rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-xs">
      <summary className="cursor-pointer text-gray-300">{t('connections.title', { count: channels.length })}</summary>
      <ul className="mt-2 space-y-1.5">
        {channels.map((channel) => (
          <li key={`${channel.kind}:${channel.connector_id ?? 'native'}`} className="flex flex-wrap items-center gap-2">
            <span className="min-w-0 flex-1 truncate text-gray-200">{label(channel)}</span>
            <span className={`rounded-full px-2 py-0.5 text-[11px] ${TONE[channel.state]}`}>{t(`connections.state.${channel.state}`)}</span>
            <span className="text-gray-400">{channel.last_contact_at ? formatLastSeen(channel.last_contact_at, t, i18n.language) : t('deviceLink.never')}</span>
            {channel.kind === 'connector' && channel.connector_id !== null && channel.state !== 'needs_action' && (
              <button type="button" onClick={() => setRevoking(channel)}
                className="rounded px-1 py-0.5 text-gray-400 hover:bg-white/10 hover:text-white">
                {t('connections.revoke')}
              </button>
            )}
          </li>
        ))}
      </ul>
      <ConfirmDeleteModal
        isOpen={revoking !== null}
        onClose={() => setRevoking(null)}
        onConfirm={revoke}
        isLoading={busy}
        title={t('connections.revoke')}
        confirmText={t('connections.revoke')}
        message={t('connections.revokeConfirm')}
      />
    </details>
  );
}
