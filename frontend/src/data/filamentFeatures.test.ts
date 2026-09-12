import { describe, expect, it } from 'vitest';
import en from '../locales/en/translation.json';
import ru from '../locales/ru/translation.json';
import zh from '../locales/zh/translation.json';
import { ADDITIVE_CODES, deriveVisualEffectsFromAdditives, mergeVisualEffects } from './filamentFeatures';

const FUNCTIONAL_ADDITIVE_CODES = [
  'debinding_metal', 'phosphor', 'tungsten_fill', 'bismuth_fill',
  'active_foaming_agent', 'flame_retardant_additives', 'uv_stabilizers_hals',
  'impact_modifiers', 'compatibilizers', 'chain_extenders', 'nucleating_agents',
  'antioxidants_heat_stabilizers', 'antimicrobial_additives', 'laser_marking_additives',
] as const;

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

  it('keeps functional additives separate from appearance effects', () => {
    for (const code of FUNCTIONAL_ADDITIVE_CODES) {
      expect(deriveVisualEffectsFromAdditives([{ code }]), code).toEqual([]);
    }
  });

  it('offers every workbook-backed functional additive with localized labels', () => {
    for (const code of FUNCTIONAL_ADDITIVE_CODES) {
      expect(ADDITIVE_CODES).toContain(code);
      expect(ru.filamentFeatures.additives[code]).toMatch(/[А-Яа-яЁё]/u);
      expect(en.filamentFeatures.additives[code]).not.toBe(code);
      expect(zh.filamentFeatures.additives[code]).toMatch(/\p{Script=Han}/u);
    }
  });
});
