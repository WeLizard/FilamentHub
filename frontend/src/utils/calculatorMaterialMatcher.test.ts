import { describe, expect, it } from 'vitest';

import {
  findBestMaterialMatch,
  pickPrimaryParsedMaterial,
  scoreMaterialCandidate,
} from './calculatorMaterialMatcher';

describe('calculator material matcher', () => {
  it('ranks exact product identity as a high-confidence match', () => {
    const match = findBestMaterialMatch(
      [
        { id: 1, name: 'PLA Basic', vendor: 'Acme', materialType: 'PLA', color: 'Black' },
        { id: 2, name: 'PETG Pro', vendor: 'Acme', materialType: 'PETG', color: 'Black' },
      ],
      { name: 'PLA Basic', vendor: 'Acme', type: 'PLA', color: 'Black' },
      (item) => item,
    );

    expect(match?.item.id).toBe(1);
    expect(match?.confidence).toBe('high');
  });

  it('does not auto-select ambiguous candidates', () => {
    const match = findBestMaterialMatch(
      [
        { id: 1, name: 'Generic PLA', vendor: 'Acme', materialType: 'PLA', color: null },
        { id: 2, name: 'Generic PLA', vendor: 'Other', materialType: 'PLA', color: null },
      ],
      { name: 'Generic PLA', type: 'PLA' },
      (item) => item,
    );

    expect(match).toBeNull();
  });

  it('rejects weak type-only guesses below the threshold', () => {
    const score = scoreMaterialCandidate(
      { type: 'PLA' },
      { name: 'Unknown', vendor: null, materialType: 'PLA', color: null },
    );
    const match = findBestMaterialMatch(
      [{ id: 1, name: 'Unknown', vendor: null, materialType: 'PLA', color: null }],
      { type: 'PLA' },
      (item) => item,
    );

    expect(score).toBe(6);
    expect(match).toBeNull();
  });

  it('selects the material row that has real usage', () => {
    const material = pickPrimaryParsedMaterial({
      file_name: 'part.gcode',
      file_size_bytes: 100,
      active_material_count: 1,
      materials: [
        { name: 'Unused', weight_g: 0 },
        { name: 'Used', weight_g: 12.5 },
      ],
    });

    expect(material?.name).toBe('Used');
  });

  it('does not collapse a multi-material job into one automatic selection', () => {
    const material = pickPrimaryParsedMaterial({
      file_name: 'multi.gcode',
      file_size_bytes: 100,
      active_material_count: 2,
      materials: [{ name: 'T0' }, { name: 'T1' }],
    });

    expect(material).toBeNull();
  });
});
