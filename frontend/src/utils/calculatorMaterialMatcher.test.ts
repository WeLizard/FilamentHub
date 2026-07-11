import { describe, expect, it } from 'vitest';

import {
  findBestMaterialMatch,
  findPrioritizedMaterialMatch,
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

  it('uses the slicer HEX color to disambiguate otherwise identical materials', () => {
    const match = findBestMaterialMatch(
      [
        { id: 1, name: 'PETG', vendor: 'Acme', materialType: 'PETG', color: '#111827' },
        { id: 2, name: 'PETG', vendor: 'Acme', materialType: 'PETG', color: '#CF17D9' },
      ],
      { name: 'Generic PETG @System', vendor: 'Generic', type: 'PETG', color: '#CF17D9' },
      (item) => item,
    );

    expect(match?.item.id).toBe(2);
    expect(match?.score).toBeGreaterThanOrEqual(13);
  });

  it('recognizes a close RGB shade without treating distant colors as equivalent', () => {
    const closeScore = scoreMaterialCandidate(
      { type: 'PLA', color: '#FF5A36' },
      { name: 'Orange PLA', vendor: null, materialType: 'PLA', color: '#F95F3B' },
    );
    const distantScore = scoreMaterialCandidate(
      { type: 'PLA', color: '#FF5A36' },
      { name: 'Blue PLA', vendor: null, materialType: 'PLA', color: '#2563EB' },
    );

    expect(closeScore).toBe(9);
    expect(distantScore).toBe(6);
  });

  it('prefers a qualified user material over a stronger catalog candidate', () => {
    const match = findPrioritizedMaterialMatch(
      { name: 'PLA Basic', vendor: 'Acme', type: 'PLA' },
      [{ id: 'spool-material', name: 'PLA Basic', vendor: 'Acme', materialType: 'PLA', color: null }],
      [{ id: 'catalog', name: 'PLA Basic', vendor: 'Acme', materialType: 'PLA', color: '#000000' }],
      (item) => item,
      (item) => item,
    );

    expect(match?.source).toBe('user');
    expect(match?.match.item.id).toBe('spool-material');
  });

  it('falls back to the catalog only when user materials have no qualified match', () => {
    const match = findPrioritizedMaterialMatch(
      { name: 'PETG Pro', vendor: 'Acme', type: 'PETG' },
      [{ id: 'spool-material', name: 'PLA Basic', vendor: 'Acme', materialType: 'PLA', color: null }],
      [{ id: 'catalog', name: 'PETG Pro', vendor: 'Acme', materialType: 'PETG', color: null }],
      (item) => item,
      (item) => item,
    );

    expect(match?.source).toBe('catalog');
    expect(match?.match.item.id).toBe('catalog');
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
