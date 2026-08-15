import { describe, expect, it } from 'vitest';
import { printerCatalogLabel } from './printerLabel';

describe('printerCatalogLabel', () => {
  it('does not repeat the catalogue model as an alternate name', () => {
    expect(printerCatalogLabel({
      manufacturer: 'Anycubic',
      model: 'Kobra Max',
      name: 'Anycubic Kobra Max',
    })).toBe('Anycubic Kobra Max');
  });

  it('keeps a genuinely different display name', () => {
    expect(printerCatalogLabel({
      manufacturer: 'Voron',
      model: '2.4 350',
      name: 'Workshop printer',
    })).toBe('Voron 2.4 350 (Workshop printer)');
  });
});
