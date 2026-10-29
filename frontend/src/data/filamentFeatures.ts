export const DECORATIVE_VISUAL_EFFECT_CODES = [
  'metallic', 'luminescent', 'glitter', 'pearlescent', 'color_shift', 'fluorescent',
  'uv_reactive', 'photochromic', 'stone',
] as const;

export const COLOR_TYPE_CODES = [
  'single', 'two', 'three', 'four', 'gradient', 'transition', 'thermochromic',
] as const;
export type ColorTypeCode = typeof COLOR_TYPE_CODES[number];

export const FINISH_CODES = ['matte', 'satin', 'glossy', 'silk'] as const;
export type FinishCode = typeof FINISH_CODES[number];

const COLOR_COUNTS: Record<ColorTypeCode, number> = {
  single: 1, two: 2, three: 3, four: 4, gradient: 5, transition: 2, thermochromic: 2,
};

export const requiredColorCount = (type: ColorTypeCode): number => COLOR_COUNTS[type];

export const ADDITIVE_CODES = [
  'carbon_fiber', 'glass_fiber', 'aramid_fiber', 'basalt_fiber', 'natural_fiber',
  'wood', 'bamboo', 'cork', 'metal_powder', 'mineral', 'ceramic', 'glass_beads',
  'debinding_metal', 'carbon_nanotubes', 'carbon_black', 'graphene', 'phosphor',
  'tungsten_fill', 'bismuth_fill', 'hollow_spheres', 'ptfe', 'active_foaming_agent',
  'flame_retardant_additives', 'uv_stabilizers_hals', 'impact_modifiers',
  'compatibilizers', 'chain_extenders', 'nucleating_agents',
  'antioxidants_heat_stabilizers', 'antimicrobial_additives', 'laser_marking_additives',
] as const;

export const PROPERTY_CLAIM_CODES = [
  'esd', 'electrically_conductive', 'emi_shielding', 'flame_retardant',
  'uv_resistant', 'wear_resistant', 'low_friction', 'lightweight', 'foaming',
  'antimicrobial', 'food_contact', 'heat_resistant', 'chemical_resistant',
  'magnetically_detectable',
] as const;

// Stabilisers and process aids: manufacturers do not state their share, so the
// editor offers no percentage for them. Fillers and reinforcements keep it.
export const UNQUANTIFIED_ADDITIVE_CODES = new Set([
  'uv_stabilizers_hals', 'impact_modifiers', 'compatibilizers', 'chain_extenders',
  'nucleating_agents', 'antioxidants_heat_stabilizers', 'antimicrobial_additives',
  'laser_marking_additives', 'active_foaming_agent',
]);

export const ABRASIVE_ADDITIVE_CODES = new Set([
  'carbon_fiber', 'glass_fiber', 'aramid_fiber', 'basalt_fiber', 'natural_fiber',
  'metal_powder', 'mineral', 'ceramic', 'glass_beads', 'carbon_nanotubes',
  'carbon_black', 'graphene', 'wood', 'bamboo', 'stone',
]);

const ADDITIVE_VISUAL_EFFECTS: Record<string, string> = {
  carbon_fiber: 'carbon',
  glass_fiber: 'glass',
  glass_beads: 'microspheres',
  aramid_fiber: 'fibers',
  basalt_fiber: 'fibers',
  natural_fiber: 'fibers',
  wood: 'wood',
  bamboo: 'wood',
  cork: 'wood',
  metal_powder: 'metallic',
  mineral: 'stone',
  ceramic: 'stone',
  carbon_nanotubes: 'carbonaceous',
  carbon_black: 'carbonaceous',
  graphene: 'carbonaceous',
  hollow_spheres: 'microspheres',
  ptfe: 'particles',
};

export const deriveVisualEffectsFromAdditives = (additives: Array<{ code: string }>): string[] => [
  ...new Set(
    additives
      .map(item => ADDITIVE_VISUAL_EFFECTS[item.code])
      .filter((effect): effect is string => Boolean(effect)),
  ),
];

export const mergeVisualEffects = (
  selectedEffects: string[],
  additives: Array<{ code: string }>,
): string[] => [
  ...new Set([...deriveVisualEffectsFromAdditives(additives), ...selectedEffects]),
];
