import { describe, expect, it } from 'vitest';
import {
  formatTemperatureRange,
  getFilamentCompositionFacts,
  hasNonStandardDiameter,
} from './filamentFacts';

describe('filament facts', () => {
  it('formats complete and partial manufacturer temperature ranges', () => {
    expect(formatTemperatureRange(200, 230)).toBe('200\u2013230');
    expect(formatTemperatureRange(210, 210)).toBe('210');
    expect(formatTemperatureRange(200, null)).toBe('\u2265200');
    expect(formatTemperatureRange(null, 80)).toBe('\u226480');
    expect(formatTemperatureRange(null, null)).toBeNull();
  });

  it('only treats a diameter different from 1.75 mm as non-standard', () => {
    expect(hasNonStandardDiameter(1.75)).toBe(false);
    expect(hasNonStandardDiameter(2.85)).toBe(true);
    expect(hasNonStandardDiameter(null)).toBe(false);
  });

  it('keeps physical additives without duplicating their derived visual effect', () => {
    expect(getFilamentCompositionFacts({
      additives: [{ code: 'carbon_fiber', content_percent: 15, content_basis: 'weight' }],
      visual_settings: { filler: 'carbon', effects: ['carbon', 'glitter'] },
    })).toEqual([
      {
        kind: 'additive',
        code: 'carbon_fiber',
        contentPercent: 15,
        contentBasis: 'weight',
      },
      { kind: 'effect', code: 'glitter' },
    ]);
  });

  it('keeps a legacy filler visible when structured additives are absent', () => {
    expect(getFilamentCompositionFacts({
      additives: [],
      visual_settings: { filler: 'wood' },
    })).toEqual([{ kind: 'effect', code: 'wood' }]);
  });
});
