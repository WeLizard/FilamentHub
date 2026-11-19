import { describe, expect, it } from 'vitest';

import {
  ORCA_ADVANCED_FIELD_DEFS,
  ORCA_ADVANCED_FIELD_KEYS,
  ORCA_ADVANCED_FIELD_LABELS,
  isOrcaStructuredFieldEnabled,
  isOrcaStructuredFieldValueValid,
} from './createPrintProfileOrcaFields';

describe('Orca process field registry', () => {
  const field = (key: string) => ORCA_ADVANCED_FIELD_DEFS.find((item) => item.key === key)!;

  it('places all six reviewed fields in their Orca sections once', () => {
    const expected = [
      ['wipe_inward', 'boolean', 'quality', 'seam'],
      ['wipe_inward_distance', 'floatOrPercent', 'quality', 'seam'],
      ['unsupported_wall_last', 'boolean', 'quality', 'overhangs'],
      ['wipe_tower_sparse_layers_combination', 'boolean', 'multimaterial', 'primeTower'],
      ['toolchange_cyclic_order', 'string', 'multimaterial', 'advanced'],
      ['toolchange_cyclic_first_layer', 'boolean', 'multimaterial', 'advanced'],
    ];
    for (const [key, kind, tab, section] of expected) {
      expect(ORCA_ADVANCED_FIELD_DEFS.filter((item) => item.key === key)).toHaveLength(1);
      expect(field(key)).toMatchObject({ kind, tab, section });
      expect(ORCA_ADVANCED_FIELD_LABELS[key]).toBeDefined();
    }
    const keys = ORCA_ADVANCED_FIELD_DEFS.map((item) => item.key);
    expect(keys.indexOf('wipe_inward_distance')).toBe(keys.indexOf('wipe_inward') + 1);
    expect(keys.indexOf('unsupported_wall_last')).toBe(keys.indexOf('detect_overhang_wall') + 1);
  });

  it('disables dependent fields only for known incompatible parent settings', () => {
    expect(isOrcaStructuredFieldEnabled(field('wipe_inward_distance'), { wipe_inward: '0' })).toBe(false);
    expect(isOrcaStructuredFieldEnabled(field('wipe_inward_distance'), { wipe_inward: '1' })).toBe(true);
    expect(isOrcaStructuredFieldEnabled(field('unsupported_wall_last'), { detect_overhang_wall: '0' })).toBe(false);
    expect(isOrcaStructuredFieldEnabled(field('toolchange_cyclic_order'), { toolchange_ordering: 'default' })).toBe(false);
    expect(isOrcaStructuredFieldEnabled(field('toolchange_cyclic_first_layer'), { toolchange_ordering: 'cyclic' })).toBe(true);
    const tower = field('wipe_tower_sparse_layers_combination');
    expect(isOrcaStructuredFieldEnabled(tower, { enable_prime_tower: '0' })).toBe(false);
    expect(isOrcaStructuredFieldEnabled(tower, { enable_prime_tower: '1', wipe_tower_no_sparse_layers: '1' })).toBe(false);
    expect(isOrcaStructuredFieldEnabled(tower, { enable_prime_tower: '1', wipe_tower_no_sparse_layers: '0' })).toBe(true);
    expect(isOrcaStructuredFieldEnabled(tower, {})).toBe(true);
  });

  it('gates the November 2026 Orca process fields like Orca does', () => {
    const keys = ORCA_ADVANCED_FIELD_DEFS.map((item) => item.key);
    expect(keys.slice(keys.indexOf('adaptive_infill_mode'), keys.indexOf('adaptive_infill_mode') + 4)).toEqual([
      'adaptive_infill_mode', 'adaptive_infill_interior_density', 'adaptive_infill_gradient', 'gyroid_optimized',
    ]);
    for (const key of ['adaptive_infill_mode', 'adaptive_infill_interior_density', 'adaptive_infill_gradient', 'infill_complete_top', 'high_precision_gcode', 'exclude_object_tolerance']) {
      expect(ORCA_ADVANCED_FIELD_LABELS[key]).toBeDefined();
    }
    const mode = field('adaptive_infill_mode');
    expect(isOrcaStructuredFieldEnabled(mode, { sparse_infill_pattern: 'tpmsd' })).toBe(true);
    expect(isOrcaStructuredFieldEnabled(mode, { sparse_infill_pattern: 'grid' })).toBe(false);
    expect(isOrcaStructuredFieldEnabled(mode, {})).toBe(true);
    const density = field('adaptive_infill_interior_density');
    expect(isOrcaStructuredFieldEnabled(density, { sparse_infill_pattern: 'gyroid', adaptive_infill_mode: 'disabled' })).toBe(false);
    expect(isOrcaStructuredFieldEnabled(density, { sparse_infill_pattern: 'gyroid', adaptive_infill_mode: 'lobes' })).toBe(true);
    expect(isOrcaStructuredFieldEnabled(field('gyroid_optimized'), { sparse_infill_pattern: 'gyroid', adaptive_infill_mode: 'lobes' })).toBe(false);
    expect(isOrcaStructuredFieldEnabled(field('infill_complete_top'), { sparse_infill_pattern: '3dhoneycomb' })).toBe(true);
    expect(isOrcaStructuredFieldEnabled(field('infill_complete_top'), { sparse_infill_pattern: 'gyroid' })).toBe(false);
    expect(isOrcaStructuredFieldEnabled(field('exclude_object_tolerance'), { exclude_object: '0' })).toBe(false);
    for (const key of ['leading_brim_length', 'extra_brim_width', 'belt_purge_tower_width', 'imex_parallel_mode']) {
      expect(ORCA_ADVANCED_FIELD_KEYS.has(key)).toBe(false);
    }
  });

  it('validates edited distances and cyclic sequences without supplying defaults', () => {
    for (const value of ['', '0', '0.20', '50%', '100%']) {
      expect(isOrcaStructuredFieldValueValid(field('wipe_inward_distance'), value)).toBe(true);
    }
    for (const value of ['-1', 'NaN', '50%%', '101%', '2mm']) {
      expect(isOrcaStructuredFieldValueValid(field('wipe_inward_distance'), value)).toBe(false);
    }
    for (const value of ['', '3,2,1,4', '1, 2']) {
      expect(isOrcaStructuredFieldValueValid(field('toolchange_cyclic_order'), value)).toBe(true);
    }
    for (const value of ['0,1', '1.5', '2,,3', '1,']) {
      expect(isOrcaStructuredFieldValueValid(field('toolchange_cyclic_order'), value)).toBe(false);
    }
  });
  it('exposes mixed-color sublayers as a structured quality boolean', () => {
    expect(
      ORCA_ADVANCED_FIELD_DEFS.filter(
        (field) => field.key === 'enable_mixed_color_sublayer',
      ),
    ).toEqual([
      {
        key: 'enable_mixed_color_sublayer',
        kind: 'boolean',
        tab: 'quality',
        section: 'layerHeight',
      },
    ]);
    expect(ORCA_ADVANCED_FIELD_LABELS.enable_mixed_color_sublayer).toEqual({
      en: 'Mixed color sublayer',
      ru: 'Подслои смешивания цветов',
    });
  });

  it('keeps Orca preset metadata out of the structured process editor', () => {
    expect(ORCA_ADVANCED_FIELD_KEYS.has('is_custom_defined')).toBe(false);
  });
});
