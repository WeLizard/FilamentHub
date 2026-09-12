export const DECORATIVE_VISUAL_EFFECT_CODES = [
  'metallic', 'luminescent', 'glitter',
] as const;

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
