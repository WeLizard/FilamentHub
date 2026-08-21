import { describe, expect, it } from 'vitest';

import { ownQrShortCode } from './qrScanner';

describe('ownQrShortCode', () => {
  it('accepts QR links from both public FilamentHub domains', () => {
    expect(ownQrShortCode('https://filamenthub.ru/qr/FH-RU01')).toBe('FH-RU01');
    expect(ownQrShortCode('https://filamenthub.club/qr/FH-CLUB01')).toBe('FH-CLUB01');
  });

  it('rejects lookalike and unrelated hosts', () => {
    expect(ownQrShortCode('https://filamenthub.club.attacker.example/qr/FH-0001')).toBeNull();
    expect(ownQrShortCode('https://example.com/qr/FH-0001')).toBeNull();
  });
});
