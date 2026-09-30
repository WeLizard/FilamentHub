import { describe, expect, it } from 'vitest';
import { printerCatalogLabel } from './printerLabel';

describe('printerCatalogLabel', () => {
  it('does not repeat the catalogue model as an alternate name', () => {
    expect(printerCatalogLabel({
      manufacturer: 'Anycubic',
      model: 'Kobra Max',
      name: 'Anycubic Kobra Max',
      source: 'system',
    })).toBe('Anycubic Kobra Max');
  });

  it('keeps a genuinely different display name', () => {
    expect(printerCatalogLabel({
      manufacturer: 'Voron',
      model: '2.4 350',
      name: 'Workshop printer',
      source: 'user',
    })).toBe('Voron 2.4 350 (Workshop printer)');
  });
  it('never reconstructs a system identity from its vendor and short label', () => {
    expect(printerCatalogLabel({
      manufacturer: 'BambuLab', model: 'P2S', name: 'Bambu Lab P2S', source: 'system',
    })).toBe('Bambu Lab P2S');
  });
});
