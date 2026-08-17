import { describe, expect, it } from 'vitest';

import { expiryMs } from './useTokenRefresh';

function tokenWithExp(exp: number | undefined): string {
  const payload = btoa(JSON.stringify(exp === undefined ? {} : { exp }))
    .replace(/\+/g, '-')
    .replace(/\//g, '_');
  return `header.${payload}.signature`;
}

describe('expiryMs', () => {
  it('reads the expiry a token states', () => {
    expect(expiryMs(tokenWithExp(1_700_000_000))).toBe(1_700_000_000_000);
  });

  it('returns nothing for a token it cannot read', () => {
    // Refusing to guess matters: a wrong expiry would either refresh every ten
    // seconds forever or never refresh at all, and both are worse than leaving the
    // existing 401-and-retry path to do its job.
    expect(expiryMs('not-a-jwt')).toBeNull();
    expect(expiryMs(tokenWithExp(undefined))).toBeNull();
    expect(expiryMs('header..signature')).toBeNull();
  });
});
