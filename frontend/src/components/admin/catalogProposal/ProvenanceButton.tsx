import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';

import type { CatalogCurationEvidence, CatalogQuoteCheckItem } from '../../../types/api';
import { externalUrl, externalUrlDisplay } from '../../../utils/externalUrl';

export interface FieldEvidence {
  item: CatalogCurationEvidence;
  index: number;
}

interface ProvenanceButtonProps {
  label: string;
  entries: FieldEvidence[];
  /** Server-side verdict on the quote cited for this field. */
  check?: CatalogQuoteCheckItem;
  /** Offered for image-only claims: the administrator looked at the image and accepts it. */
  onConfirmImage?: (confirmed: boolean) => void;
  readonly: boolean;
  onAdd: () => void;
  onUpdate: (index: number, changes: Partial<CatalogCurationEvidence>) => void;
  onRemove: (index: number) => void;
}

const CHECK_TONE: Record<CatalogQuoteCheckItem['status'], string> = {
  verified: 'bg-emerald-500/15 text-emerald-200',
  image_only: 'bg-cyan-500/15 text-cyan-200',
  pending: 'bg-white/10 text-gray-300',
  source_unavailable: 'bg-amber-500/15 text-amber-200',
  not_official_domain: 'bg-amber-500/15 text-amber-200',
  quote_too_short: 'bg-red-500/15 text-red-200',
  quote_not_found: 'bg-red-500/15 text-red-200',
  value_not_in_quote: 'bg-red-500/15 text-red-200',
};

const POPOVER_WIDTH = 320;
const MARGIN = 12;

/** Small indicator beside a field label; its popover holds the sources and the justification. */
export function ProvenanceButton({ label, entries, check, onConfirmImage, readonly, onAdd, onUpdate, onRemove }: ProvenanceButtonProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);
  const inferred = entries.some(({ item }) => item.kind === 'inferred');
  const tone = entries.length === 0 ? 'bg-gray-600' : inferred ? 'bg-amber-400' : 'bg-cyan-400';
  const kindSummary = entries.length === 0
    ? t('adminCatalogImport.curation.noEvidence')
    : t(`adminCatalogImport.curation.kind.${inferred ? 'inferred' : 'direct'}`);
  const checkStatus = check ? (check.status === 'image_only' && check.confirmed ? 'image_confirmed' : check.status) : null;
  const checkLabel = checkStatus ? t(`adminCatalogImport.curation.quoteStatus.${checkStatus}`) : null;
  const summary = checkLabel ? `${kindSummary} · ${checkLabel}` : kindSummary;

  useLayoutEffect(() => {
    if (!open || !buttonRef.current) return;
    const rect = buttonRef.current.getBoundingClientRect();
    const left = Math.min(Math.max(rect.left - 8, MARGIN), window.innerWidth - POPOVER_WIDTH - MARGIN);
    setPosition({ left: Math.max(left, MARGIN), top: rect.bottom + 6 });
  }, [open]);

  // Keep the popover inside the viewport: flip above the button, or slide up, when it would run off the bottom.
  useLayoutEffect(() => {
    if (!open || !position || !popoverRef.current || !buttonRef.current) return;
    const height = popoverRef.current.offsetHeight;
    const overflow = position.top + height + MARGIN - window.innerHeight;
    if (overflow <= 0) return;
    const above = buttonRef.current.getBoundingClientRect().top - 6 - height;
    setPosition({ left: position.left, top: Math.max(MARGIN, above >= MARGIN ? above : position.top - overflow) });
  }, [open, position, entries.length]);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent) {
        if (event.key === 'Escape') { setOpen(false); buttonRef.current?.focus(); }
        return;
      }
      const target = event.target as Node;
      if (!popoverRef.current?.contains(target) && !buttonRef.current?.contains(target)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', close);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', close);
    };
  }, [open]);

  if (readonly && entries.length === 0) return null;

  return (
    <>
      <button ref={buttonRef} type="button" aria-expanded={open} aria-haspopup="dialog"
        aria-label={`${t('adminCatalogImport.curation.provenance')}: ${label} · ${summary}`}
        title={summary}
        onClick={() => setOpen((current) => !current)}
        className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full transition hover:bg-white/10">
        <span className={`h-2 w-2 rounded-full ${tone}`} />
      </button>
      {open && createPortal(
        <div ref={popoverRef} role="dialog" aria-label={`${t('adminCatalogImport.curation.provenance')}: ${label}`}
          style={{ position: 'fixed', left: position?.left ?? MARGIN, top: position?.top ?? MARGIN, width: Math.min(POPOVER_WIDTH, window.innerWidth - 2 * MARGIN), visibility: position ? 'visible' : 'hidden' }}
          className="z-[10000] max-h-[70vh] space-y-3 overflow-y-auto rounded-xl border border-white/15 bg-gray-900 p-3 text-sm shadow-2xl">
          <p className="text-xs font-semibold text-gray-300">{label}</p>
          {entries.map(({ item, index }, position) => (
            <fieldset key={index} disabled={readonly} className="space-y-2 rounded-lg bg-white/[0.04] p-2.5">
              <div className="flex items-center justify-between gap-2">
                <select aria-label={`${t('adminCatalogImport.curation.evidenceKind')} ${position + 1}`} value={item.kind}
                  onChange={(event) => onUpdate(index, { kind: event.target.value as CatalogCurationEvidence['kind'] })}
                  className="rounded-lg border border-white/15 bg-slate-900 px-2 py-1 text-xs text-white">
                  <option value="direct">{t('adminCatalogImport.curation.kind.direct')}</option>
                  <option value="inferred">{t('adminCatalogImport.curation.kind.inferred')}</option>
                </select>
                {!readonly && <button type="button" onClick={() => onRemove(index)} className="text-xs text-red-300 hover:text-red-200">
                  {t('adminCatalogImport.curation.removeEvidence')}
                </button>}
              </div>
              {item.source_urls.map((url, sourceIndex) => {
                const safeUrl = externalUrl(url);
                return safeUrl ? <a key={sourceIndex} href={safeUrl} target="_blank" rel="noopener noreferrer"
                  className="block break-all text-xs text-cyan-200 underline decoration-cyan-400/40 underline-offset-2">{externalUrlDisplay(url)}</a> : null;
              })}
              <label className="block text-xs text-gray-400">{t('adminCatalogImport.curation.sources')}
                <textarea aria-label={`${t('adminCatalogImport.curation.sources')} ${position + 1}`} value={item.source_urls.join('\n')} rows={2}
                  onChange={(event) => onUpdate(index, { source_urls: event.target.value.split('\n') })}
                  className="mt-1 block w-full rounded-lg border border-white/15 bg-slate-950/70 p-2 text-xs text-white" />
              </label>
              <label className="block text-xs text-gray-400">
                <span className="flex items-center justify-between gap-2">
                  {t('adminCatalogImport.curation.quote')}
                  {check && <span className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${check.confirmed ? CHECK_TONE.verified : CHECK_TONE[check.status]}`}>{checkLabel}</span>}
                </span>
                <textarea aria-label={`${t('adminCatalogImport.curation.quote')} ${position + 1}`} value={item.quote ?? ''} rows={2}
                  onChange={(event) => onUpdate(index, { quote: event.target.value.trim() ? event.target.value : null })}
                  className="mt-1 block w-full rounded-lg border border-white/15 bg-slate-950/70 p-2 text-xs text-white" />
              </label>
              {check?.status === 'image_only' && onConfirmImage && !readonly && (
                <button type="button" onClick={() => onConfirmImage(!check.confirmed)}
                  className="text-xs font-medium text-cyan-200 underline decoration-cyan-300/40 underline-offset-2">
                  {t(check.confirmed ? 'adminCatalogImport.curation.imageWithdraw' : 'adminCatalogImport.curation.imageConfirm')}
                </button>
              )}
              <label className="block text-xs text-gray-400">{t('adminCatalogImport.curation.explanation')}
                <textarea aria-label={`${t('adminCatalogImport.curation.explanation')} ${position + 1}`} value={item.explanation ?? ''} rows={2}
                  onChange={(event) => onUpdate(index, { explanation: event.target.value })}
                  className="mt-1 block w-full rounded-lg border border-white/15 bg-slate-950/70 p-2 text-xs text-white" />
              </label>
            </fieldset>
          ))}
          {!readonly && entries.length === 0 && <button type="button" onClick={onAdd}
            className="text-xs font-medium text-indigo-200 underline decoration-indigo-300/40 underline-offset-2">
            {t('adminCatalogImport.curation.addEvidence')}
          </button>}
        </div>,
        document.body,
      )}
    </>
  );
}
