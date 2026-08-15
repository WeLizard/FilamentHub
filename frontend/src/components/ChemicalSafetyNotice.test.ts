import { describe, expect, it } from 'vitest';
import { chemicalSafetyReferenceUrl } from './ChemicalSafetyNotice';

describe('chemicalSafetyReferenceUrl', () => {
  it.each([
    ['ru-RU', 'protect.gost.ru'],
    ['en-US', 'unece.org'],
    ['zh-CN', 'openstd.samr.gov.cn'],
  ])('uses the official reference selected for %s', (language, host) => {
    expect(new URL(chemicalSafetyReferenceUrl(language)).host).toBe(host);
  });

  it('falls back to the international reference for unsupported locales', () => {
    expect(new URL(chemicalSafetyReferenceUrl('de-DE')).host).toBe('unece.org');
  });
});
