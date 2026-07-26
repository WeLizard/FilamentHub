import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, Check, Copy, RefreshCw } from 'lucide-react';

import { devicesAPI } from '../../../api/client';
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

function PairingStep({ gates }: { gates: AdapterViewContext['gates'] }) {
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

export const happyHareAdapter: FeedAdapter = {
  id: 'happy_hare',
  labelKey: 'presetSlots.feedSystem.happy_hare',
  fixedSlots: null,
  link: {
    hintKey: 'presetSlots.happyHare.linkHint',
    snippet: (url) => `[spoolman]
server: ${url}
sync_rate: 5`,
  },
  renderSettings: ({ printer }) => <HostnameField printer={printer} />,
  renderSetup: ({ gates, linkConfirmed }) =>
    (linkConfirmed ? null : <PairingStep gates={gates} />),
};
