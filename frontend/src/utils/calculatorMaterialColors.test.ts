import { describe, expect, it } from 'vitest';

import { normalizeFilamentColor, resolveMaterialDisplayColors } from './calculatorMaterialColors';

describe('calculator material color provenance', () => {
  it('keeps the G-code color primary when an automatic assignment has another color', () => {
    expect(resolveMaterialDisplayColors('#FF0000', '#000000')).toEqual({
      primary: '#FF0000',
      assigned: '#000000',
      differs: true,
    });
  });

  it('falls back to the assigned material when the slicer did not provide a color', () => {
    expect(resolveMaterialDisplayColors(null, 'cf17d9')).toEqual({
      primary: '#CF17D9',
      assigned: null,
      differs: false,
    });
  });

  it('normalizes Orca RGBA colors to browser-safe RGB hex', () => {
    expect(normalizeFilamentColor('#32c2a9ff')).toBe('#32C2A9');
  });
});
