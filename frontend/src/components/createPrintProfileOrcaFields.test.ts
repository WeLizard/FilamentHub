import { describe, expect, it } from 'vitest';

import {
  ORCA_ADVANCED_FIELD_DEFS,
  ORCA_ADVANCED_FIELD_KEYS,
  ORCA_ADVANCED_FIELD_LABELS,
} from './createPrintProfileOrcaFields';

describe('Orca process field registry', () => {
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
