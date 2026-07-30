import { useState } from 'react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Copy, X } from 'lucide-react';

import { toast } from '../Toast';
import type { FeedAdapterLink } from './adapters';

interface LinkInstructionsProps {
  link: FeedAdapterLink;
  baseUrl: string;
  apiKey: string;
  onClose?: () => void;
  children?: ReactNode;
}

interface CopyFieldProps {
  label: string;
  value: string;
}

function CopyField({ label, value }: CopyFieldProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const multiline = value.includes('\n');

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      toast.error(t('common.error'));
    }
  };

  return (
    <div className="group grid min-w-0 grid-cols-[7rem_minmax(0,1fr)_auto] items-center gap-2 border-t border-white/10 px-3 py-2 first:border-t-0">
      <span className="text-[10px] font-medium uppercase tracking-[0.12em] text-gray-500">
        {label}
      </span>
      <code
        className={`min-w-0 overflow-x-auto text-xs leading-5 text-gray-100 ${
          multiline ? 'whitespace-pre' : 'whitespace-nowrap'
        }`}
      >
        {value}
      </code>
      <button
        type="button"
        onClick={copy}
        title={t(copied ? 'presetSlots.pairing.copied' : 'presetSlots.pairing.copy')}
        className="rounded-md border border-white/10 bg-white/5 p-1.5 text-gray-400 transition hover:border-purple-400/30 hover:bg-purple-500/15 hover:text-purple-200"
      >
        {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
    </div>
  );
}

export function LinkInstructions({
  link,
  baseUrl,
  apiKey,
  onClose,
  children,
}: LinkInstructionsProps) {
  const { t } = useTranslation();
  const snippet = link.snippet(baseUrl, apiKey);
  const usesHeaderKey = Boolean(link.apiKeyHeader);

  return (
    <>
      <div className="flex items-start gap-3">
        <div className="flex-1 text-xs text-gray-400">
          <p>{t(link.hintKey)}</p>
          <p className="mt-1">{t('presetSlots.link.onceHint')}</p>
        </div>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            title={t('common.close')}
            className="rounded p-0.5 text-gray-500 transition hover:bg-white/10 hover:text-white"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
      {usesHeaderKey ? (
        <div className="mt-3 overflow-hidden rounded-xl border border-white/10 bg-black/25">
          <CopyField label={t('presetSlots.link.address')} value={snippet} />
          <CopyField
            label={t('presetSlots.link.apiKeyHeader')}
            value={link.apiKeyHeader!}
          />
          <CopyField label={t('presetSlots.link.apiKeyValue')} value={apiKey} />
        </div>
      ) : (
        <div className="mt-3 overflow-hidden rounded-xl border border-white/10 bg-black/25">
          <CopyField label={t('presetSlots.link.config')} value={snippet} />
        </div>
      )}
      {children && <div className="mt-2 flex flex-wrap gap-2">{children}</div>}
    </>
  );
}
