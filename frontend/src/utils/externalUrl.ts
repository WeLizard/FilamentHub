/**
 * Links people type into brand and shop fields.
 *
 * A value without a scheme is a relative path to the browser, so "example.com"
 * on /brands/x quietly becomes /brands/example.com instead of leaving the site.
 * Anything that is not http(s) is dropped rather than repaired: these fields are
 * edited by brand owners, and a "javascript:" value would otherwise become code
 * running on a page every visitor can open.
 */

const SAFE_PROTOCOLS = new Set(['http:', 'https:']);

export function externalUrl(value: string | null | undefined): string | null {
  const raw = value?.trim();
  if (!raw) return null;

  // Bare "example.com" and "//example.com" both mean the same thing to a person.
  const candidate = /^[a-z][a-z0-9+.-]*:/i.test(raw)
    ? raw
    : `https://${raw.replace(/^\/+/, '')}`;

  try {
    const parsed = new URL(candidate);
    return SAFE_PROTOCOLS.has(parsed.protocol) && parsed.hostname ? parsed.toString() : null;
  } catch {
    return null;
  }
}

/** Host without "www.", for showing a link without its full address. */
export function externalUrlHost(value: string | null | undefined): string {
  const normalized = externalUrl(value);
  if (!normalized) return value?.trim() || '';
  try {
    return new URL(normalized).hostname.replace(/^www\./, '');
  } catch {
    return value?.trim() || '';
  }
}
