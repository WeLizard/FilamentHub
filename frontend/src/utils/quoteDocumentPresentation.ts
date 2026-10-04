import logoSvg from '../../public/logo.svg?raw';
import type { QuoteWorkBreakdownEntry, QuoteWorkCaption } from './quoteDisclosure';

export const quoteLogoSvg = logoSvg
  .replace(/<\?xml[^>]*\?>/, '')
  .replace(/<defs>[\s\S]*?<\/defs>/, '')
  .replaceAll('class="b"', 'fill="#475569"');

export const quoteFooterBaseCss = `
  .document-footer { margin-top: 24px; padding-top: 8px; border-top: 1px solid #d1d5db; color: #64748b; font-size: 9px; line-height: 1.4; }
  .document-header { color: #64748b; font-size: 9px; line-height: 1.35; border-bottom: 1px solid #d1d5db; padding-bottom: 2mm; }
  .header-brand { display: inline; white-space: nowrap; color: #475569; font-weight: 600; }
  .header-brand svg { width: 14px; height: 12px; vertical-align: -2px; margin: 0 2px; }
  @media print { .document-quote-title { font-size: 18px; } }
`;

export const quoteDocumentTotalsCss = `
  .page .quote-totals { width: 55%; max-width: 360px; margin: 8px 0 12px auto; padding-top: 5px; border-top: 1px solid #64748b; break-inside: avoid; page-break-inside: avoid; }
  .page .quote-total-row { display: flex; justify-content: flex-end; gap: 12px; margin: 2px 0; text-align: right; font-size: 11px; line-height: 1.35; }
  .page .quote-total-row > :first-child { flex: 1 1 auto; color: #475569; }
  .page .quote-total-row > :last-child { flex: 0 0 auto; min-width: 88px; white-space: nowrap; }
  .page .quote-grand-total { margin-top: 4px; font-size: 14px; font-weight: 600; }
  .page .quote-grand-total > :last-child { color: #14253b; font-size: 16px; }
  .page .quote-breakdown { margin: 10px 0 14px; padding: 9px 11px; border: 1px solid #e2e8f0; border-radius: 6px; break-inside: avoid; page-break-inside: avoid; }
  .page .quote-breakdown h3 { margin: 0 0 5px; color: #475569; font-size: 11px; font-weight: 600; }
  .page .quote-breakdown-row { display: flex; justify-content: space-between; gap: 12px; font-size: 10px; line-height: 1.5; }
  .page .quote-breakdown-row span:last-child { white-space: nowrap; font-weight: 600; }
  .page .quote-breakdown-caption { display: block; margin-top: 1px; color: #64748b; font-size: 8px; font-weight: 400; line-height: 1.35; }
  .page .quote-breakdown-note { margin-top: 5px; color: #64748b; font-size: 9px; line-height: 1.4; }
`;

export interface QuoteBreakdownHtmlEntry { label: string; amount: string; caption?: string; }

type Translate = (key: string, options?: Record<string, string | number>) => string;

const formatWorkCaption = (caption: QuoteWorkCaption, t: Translate, language: string): string => {
  const number = new Intl.NumberFormat(language, { maximumFractionDigits: 2 });
  const parts: string[] = [];
  if (caption.parts) parts.push(t('profilePage.calculator.quoteBreakdownCaptionParts', { count: caption.parts }));
  const material = [
    caption.material,
    caption.weightKg ? t('profilePage.calculator.quoteBreakdownCaptionWeight', { value: number.format(caption.weightKg) }) : null,
  ].filter(Boolean).join(' ');
  if (material) parts.push(material);
  if (caption.printHours) parts.push(t('profilePage.calculator.quoteBreakdownCaptionTime', { value: number.format(caption.printHours) }));
  return parts.join(' · ');
};

/** Labels for the shared "by work" rows; the printing row carries its factual caption. */
export const workBreakdownHtmlEntries = (
  entries: QuoteWorkBreakdownEntry[],
  t: Translate,
  formatCurrency: (amount: number) => string,
  language: string,
): QuoteBreakdownHtmlEntry[] => entries.map((entry) => ({
  label: t(`profilePage.calculator.quoteBreakdown${entry.key[0].toUpperCase()}${entry.key.slice(1)}`),
  amount: formatCurrency(entry.amount),
  caption: entry.caption ? formatWorkCaption(entry.caption, t, language) || undefined : undefined,
}));

export const createQuoteBreakdownHtml = (
  title: string,
  entries: QuoteBreakdownHtmlEntry[],
  note = '',
): string => {
  if (!entries.length && !note.trim()) return '';
  const rows = entries.map((entry) => `<div class="quote-breakdown-row"><span>${escapeHtml(entry.label)}${entry.caption ? `<small class="quote-breakdown-caption">${escapeHtml(entry.caption)}</small>` : ''}</span><span>${escapeHtml(entry.amount)}</span></div>`).join('');
  return `<section class="quote-breakdown" data-quote-breakdown><h3>${escapeHtml(title)}</h3>${rows}${note.trim() ? `<p class="quote-breakdown-note">${escapeHtml(note.trim())}</p>` : ''}</section>`;
};

/** Shared A5 quote styling used for newly generated and upgraded draft documents. */
export const quoteDocumentLayoutCss = `
  @page { size: A4; margin: 16mm 12mm 20mm; @top-center { content: element(quoteHeader); vertical-align: bottom; width: 100%; } @bottom-center { content: element(quoteFooter); vertical-align: top; width: 100%; } }
  .page h2 { color: #182437; font-size: 15px; line-height: 1.25; margin-bottom: 5px; }
  .document-quote-title { display: block; color: #475569; font-size: 14px; line-height: 1.3; margin: 2px 0 4px; }
  .page .header { display: flex; width: 100%; justify-content: space-between; align-items: flex-start; gap: 0; margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px solid #cbd5e1; box-sizing: border-box; }
  .page .header > div:first-child { flex: 0 0 50%; width: 50%; min-width: 0; padding-right: 4mm; box-sizing: border-box; overflow-wrap: anywhere; }
  .page .header-right { flex: 0 0 50%; width: 50%; max-width: 50%; min-width: 0; padding-left: 4mm; box-sizing: border-box; text-align: left; font-size: 12px; line-height: 1.45; color: #334155; overflow-wrap: anywhere; }
  .page .header-right p strong { font-size: 12px; }
  .page .party-label { margin: 0 0 3px; color: #64748b; font-size: 10px; font-weight: 600; line-height: 1.25; }
  .page .quote-buyer-block { width: 100%; max-width: 100%; box-sizing: border-box; margin-top: 10px; padding-top: 8px; border-top: 1px solid #e2e8f0; }
  .page .quote-meta-row { display: flex; justify-content: space-between; align-items: baseline; gap: 16px; border-bottom: 1px solid #e2e8f0; margin: 0 0 12px; padding: 0 0 8px; font-size: 13px; line-height: 1.4; }
  .page .quote-meta-row p { margin: 0; }
  .page .quote-meta-row p:last-child { text-align: right; }
  .page .quote-meta-row [data-quote-issue-date] { font-weight: 700; }
  .page .box { background: transparent; border: 0; border-bottom: 1px solid #e2e8f0; border-radius: 0; padding: 7px 0; margin-bottom: 10px; }
  .page .box-title { margin-bottom: 4px; color: #475569; font-size: 11px; }
  .page .box-line { font-size: 12px; }
  .page table { width: 100%; table-layout: fixed; border-collapse: collapse; margin: 15px 0 8px; }
  .page table th, .page table td { border: 0 !important; border-bottom: 1px solid #e2e8f0 !important; padding: 8px 7px; vertical-align: top; }
  .page table thead tr, .page table thead tr.bg-gray-200 { background: transparent !important; }
  .page table thead th { background: transparent !important; color: #64748b; font-size: 10px; line-height: 1.25; font-weight: 500; border-bottom: 1px solid #94a3b8 !important; }
  .page table tbody tr:last-child td { border-bottom: 0 !important; }
  .page table th:nth-child(1), .page table td:nth-child(1) { width: 4.5% !important; text-align: center !important; padding-left: 2px; padding-right: 2px; }
  .page table th:nth-child(2), .page table td:nth-child(2) { width: 53% !important; text-align: left !important; overflow-wrap: anywhere; }
  .page table th:nth-child(3), .page table td:nth-child(3) { width: 7.5% !important; text-align: right !important; white-space: nowrap; }
  .page table th:nth-child(4), .page table td:nth-child(4) { width: 17.5% !important; text-align: right !important; white-space: nowrap; }
  .page table th:nth-child(5), .page table td:nth-child(5) { width: 17.5% !important; text-align: right !important; white-space: nowrap; }
  .page table tbody td:nth-child(2) strong { display: block; font-size: 12px; line-height: 1.35; font-weight: 600; color: #1f2937; }
  .page table tbody td:nth-child(2) .text-xs { display: block; margin-top: 3px; font-size: 10px; line-height: 1.4; color: #8490a0; }
  .page .total-row td { background: #f8fafc; border-top: 1.5px solid #64748b !important; border-bottom: 0 !important; font-size: 15px; }
  .page .total-row td:last-child { color: #14253b; font-size: 17px; }
  .page .included { border-top: 1px solid #e2e8f0; padding-top: 10px; margin-bottom: 12px; }
  .page .included-title { font-size: 12px; margin-bottom: 4px; }
  .page .included ul { font-size: 12px; line-height: 1.55; }
  .page .box[style*="background: transparent"] { border-top: 1px solid #e2e8f0; border-bottom: 0; padding: 10px 0; }
  .page .box[style*="background: transparent"] .box-muted { font-size: 10px; line-height: 1.4; }
  .document-header { padding-bottom: 1mm; font-size: 8.5px; }
  .document-footer { padding-top: 2mm; }
  @media print {
    .page { width: 100%; min-height: auto; margin: 0; padding: 0; box-shadow: none; }
    /* Chromium ignores running elements and uses these fallback offsets. */
    .document-header { position: fixed; top: -10mm; left: 0; right: 0; height: 7mm; margin: 0; }
    .document-header { position: running(quoteHeader); width: 100%; height: auto; margin: 0; padding: 0 0 1mm; }
    .document-footer { position: fixed; bottom: -15mm; left: 0; right: 0; height: 12mm; margin: 0; }
    .document-footer { position: running(quoteFooter); width: 100%; height: auto; margin: 0; padding: 2mm 0 0; }
  }
`;

const escapeHtml = (value: string): string => value
  .replaceAll('&', '&amp;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;')
  .replaceAll('"', '&quot;')
  .replaceAll("'", '&#39;');

export const createQuoteHeaderHtml = (beforeBrand: string, afterBrand: string): string => `
    <header class="document-header">
      <p>${escapeHtml(beforeBrand)} <span class="header-brand">${quoteLogoSvg}FilamentHub</span> ${escapeHtml(afterBrand)}</p>
    </header>`;

export const createQuoteFooterHtml = (purposeText: string): string => `
    <footer class="document-footer"><p>${escapeHtml(purposeText)}</p></footer>`;
