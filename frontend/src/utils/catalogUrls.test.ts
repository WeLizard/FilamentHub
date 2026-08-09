import { describe, expect, it } from 'vitest';
import { brandPublicPath, filamentPublicPath, filamentVariantLabel } from './catalogUrls';

describe('catalog public URLs', () => {
  it('builds a brand-scoped exact filament URL', () => {
    expect(filamentPublicPath({
      id: 5,
      slug: 'abs-black',
      brand_slug: 'hexflow',
    })).toBe('/brands/hexflow/filaments/abs-black');
  });

  it('keeps a rolling-deploy fallback for old API responses', () => {
    expect(filamentPublicPath({
      id: 5,
      slug: 'abs-black',
      brand_slug: null,
    })).toBe('/filaments/5');
  });

  it('builds the canonical brand URL', () => {
    expect(brandPublicPath({ slug: 'hexflow' })).toBe('/brands/hexflow');
  });

  it('uses the official colour name for an exact variant label, never HEX', () => {
    expect(filamentVariantLabel({ name: 'ABS', color_name: 'Чёрный' })).toBe('ABS — Чёрный');
    expect(filamentVariantLabel({ name: 'ABS Black', color_name: 'Black' })).toBe('ABS Black');
  });
});
