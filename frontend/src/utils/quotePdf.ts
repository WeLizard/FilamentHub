import { calculatorAPI } from '../api/client';
import type { SharedQuoteCreate } from '../types/api';
import { isPluginEmbed, savePdfInPlugin } from './pluginBridge';

export type QuotePdfDelivery =
  | { kind: 'downloaded' }
  | { kind: 'saved'; fileName: string }
  | { kind: 'preview'; url: string };

export class QuotePdfSaveError extends Error {}

/**
 * The browser downloads the PDF itself. The embedded page cannot, so the plugin saves
 * and opens it; a plugin too old for that keeps the in-page preview.
 */
export async function deliverQuotePdf(document: SharedQuoteCreate): Promise<QuotePdfDelivery> {
  if (!isPluginEmbed()) {
    await calculatorAPI.downloadQuotePdf(document);
    return { kind: 'downloaded' };
  }
  const blob = await calculatorAPI.getQuotePdfBlob(document);
  const saving = savePdfInPlugin(blob, `${document.title || 'quote'}.pdf`);
  if (!saving) return { kind: 'preview', url: URL.createObjectURL(blob) };
  const result = await saving;
  if (!result.ok) throw new QuotePdfSaveError(result.error ?? 'write-failed');
  return { kind: 'saved', fileName: result.fileName ?? '' };
}
