import { calculatorAPI } from '../api/client';
import type { SharedQuoteCreate } from '../types/api';
import { isPluginEmbed } from './pluginBridge';

export type QuotePdfDelivery =
  | { kind: 'downloaded' }
  | { kind: 'preview'; url: string; printable: true };

/**
 * The browser downloads the PDF itself. The embedded page cannot, and the plugin
 * neither saves files nor opens programs, so it shows the printable HTML document
 * in the in-page preview; Print there can save a PDF on every platform.
 */
export async function deliverQuotePdf(document: SharedQuoteCreate): Promise<QuotePdfDelivery> {
  if (!isPluginEmbed()) {
    await calculatorAPI.downloadQuotePdf(document);
    return { kind: 'downloaded' };
  }
  const html = new Blob([document.html_content], { type: 'text/html;charset=utf-8' });
  return { kind: 'preview', url: URL.createObjectURL(html), printable: true };
}
