import { describe, expect, it } from 'vitest';
import { ADDITIVE_CODES, deriveVisualEffectsFromAdditives, mergeVisualEffects } from './filamentFeatures';

describe('filament feature preview mapping', () => {
  it('derives familiar preview textures from physical composition', () => {
    expect(deriveVisualEffectsFromAdditives([
      { code: 'carbon_fiber' },
      { code: 'glass_fiber' },
      { code: 'wood' },
    ])).toEqual(['carbon', 'glass', 'wood']);
  });

  it('merges decorative details without duplicating derived effects', () => {
    expect(mergeVisualEffects(
      ['metallic', 'glitter'],
      [{ code: 'metal_powder' }],
    )).toEqual(['metallic', 'glitter']);
  });

  it('uses a fine carbonaceous rendering for nanoscale carbon additives', () => {
    expect(deriveVisualEffectsFromAdditives([
      { code: 'carbon_nanotubes' },
      { code: 'graphene' },
    ])).toEqual(['carbonaceous']);
  });

  it('has an automatic preview representation for every known filler', () => {
    for (const code of ADDITIVE_CODES) {
      expect(deriveVisualEffectsFromAdditives([{ code }]), code).not.toEqual([]);
    }
  });
});
