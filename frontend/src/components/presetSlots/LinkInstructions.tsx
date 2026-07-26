import { useState } from 'react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Copy, X } from 'lucide-react';

import { toast } from '../Toast';
import type { FeedAdapterLink } from './adapters';

interface LinkInstructionsProps {
  link: FeedAdapterLink;
  url: string;
  onClose?: () => void;
  children?: ReactNode;
}

export function LinkInstructions({ link, url, onClose, children }: LinkInstructionsProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);
  const snippet = link.snippet(url);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(snippet);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      toast.error(t('common.error'));
    }
  };

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
      <pre className="mt-2 overflow-x-auto rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-xs text-white">{snippet}</pre>
      <div className="mt-2 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={copy}
          className="inline-flex items-center gap-1.5 rounded-lg bg-purple-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-purple-500"
        >
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          {t(copied ? 'presetSlots.pairing.copied' : 'presetSlots.pairing.copy')}
        </button>
        {children}
      </div>
    </>
  );
}
