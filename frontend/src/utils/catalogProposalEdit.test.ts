import { describe, expect, it } from 'vitest';
import {
  applyCellEdits, editsCollideKeys, fieldSpread, groupFilamentMarkets, numberFromInput, previewOutcome, settledNumber,
  type ProposalEditState,
} from './catalogProposalEdit';
import type { CatalogImportPreview } from '../types/api';

const state = (): ProposalEditState => ({
  draft: {
    filename: 'p.json',
    brands: [{ brand_key: 'maker' }],
    filaments: [
      { filament_key: 'maker:a', brand_key: 'maker', diameter: 1.75, color_group_source: 'manual' },
      { filament_key: 'maker:b', brand_key: 'maker', diameter: 1.75 },
    ],
    brand_markets: [],
    filament_markets: [
      { filament_key: 'maker:a', country: 'RU', published: true, availability: 'available' },
      { filament_key: 'maker:b', country: 'RU', published: true, availability: 'available' },
      { filament_key: 'maker:b', country: 'KZ', published: true, availability: 'unknown' },
    ],
    presets: [],
  },
  evidence: [
    { sheet: 'FilamentMarkets', key: 'maker:a:RU', field: 'availability', kind: 'direct', source_urls: ['https://example.com'] },
    { sheet: 'FilamentMarkets', key: 'maker:b:RU', field: 'availability', kind: 'inferred', source_urls: [], explanation: 'x' },
  ],
  sourceFacts: [], unmappedFacts: [],
});

describe('catalog proposal edits', () => {
  it('changes only the edited rows and keeps the others by identity', () => {
    const before = state();
    const after = applyCellEdits(before, 'filaments', [{ index: 0, field: 'diameter', value: 2.85 }]);
    expect(after.draft.filaments[0]).toEqual({ ...before.draft.filaments[0], diameter: 2.85 });
    expect(after.draft.filaments[1]).toBe(before.draft.filaments[1]);
    expect(after.draft.filament_markets).toBe(before.draft.filament_markets);
    expect(after.evidence).toBe(before.evidence);
    expect(Object.keys(after.draft.filaments[0])).toEqual(Object.keys(before.draft.filaments[0]));
  });

  it('returns the same state when nothing is edited', () => {
    const before = state();
    expect(applyCellEdits(before, 'filaments', [])).toBe(before);
  });

  it('moves evidence with a market row when its country changes, for every edited row', () => {
    const before = state();
    const after = applyCellEdits(before, 'filament_markets', [
      { index: 0, field: 'country', value: 'KG' }, { index: 1, field: 'country', value: 'KG' },
    ]);
    expect(after.evidence.map((item) => item.key)).toEqual(['maker:a:KG', 'maker:b:KG']);
    expect(after.draft.filament_markets[2]).toBe(before.draft.filament_markets[2]);
  });

  it('detects a bulk edit that would make two market keys equal', () => {
    const rows = state().draft.filament_markets;
    expect(editsCollideKeys(rows, 'filament_markets', [{ index: 1, field: 'country', value: 'DE' }])).toBe(false);
    expect(editsCollideKeys(rows, 'filament_markets', [{ index: 0, field: 'filament_key', value: 'maker:b' }])).toBe(true);
  });

  it('finds the common market value and the rows that differ from it', () => {
    const draft = state().draft;
    const [ru, kz] = groupFilamentMarkets(draft);
    expect(ru).toMatchObject({ brandKey: 'maker', country: 'RU', indices: [0, 1] });
    expect(kz.indices).toEqual([2]);
    const spread = fieldSpread(draft.filament_markets, [0, 1, 2], 'availability');
    expect(spread).toMatchObject({ value: 'available', uniform: false, exceptions: [2] });
  });

  it('keeps typed numbers as numbers and unfinished entries as text', () => {
    expect(numberFromInput('225')).toBe(225);
    expect(numberFromInput('1.')).toBe('1.');
    expect(numberFromInput('')).toBeNull();
  });

  it('keeps what was typed while it cannot be told apart from another number', () => {
    expect(numberFromInput('1.0')).toBe('1.0');
    expect(numberFromInput('1.50')).toBe('1.50');
    expect(numberFromInput('0.05')).toBe(0.05);
    expect(numberFromInput('1.04')).toBe(1.04);
    expect(numberFromInput('-5')).toBe(-5);
    expect(settledNumber('1.0')).toBe(1);
    expect(settledNumber('1.')).toBe('1.');
    expect(settledNumber('-5')).toBe(-5);
  });

  it('counts what applying would create or update from the preview rows', () => {
    const preview = {
      rows: [
        { sheet: 'Brands', status: 'create' }, { sheet: 'Filaments', status: 'create' },
        { sheet: 'Filaments', status: 'update' }, { sheet: 'FilamentMarkets', status: 'create' },
        { sheet: 'Filaments', status: 'noop' },
      ],
    } as unknown as CatalogImportPreview;
    expect(previewOutcome(preview)).toMatchObject({
      brands: { create: 1, update: 0 }, filaments: { create: 1, update: 1 }, markets: { create: 1, update: 0 },
    });
    expect(previewOutcome(null)).toBeNull();
  });
});
