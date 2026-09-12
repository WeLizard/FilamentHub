import { describe, expect, it } from 'vitest';

import type { SpoolFeedResponse, UserSpool } from '../api/client';
import { mergeSpoolFeedPages, spoolQueryKeys } from './spoolQueries';

const spool = (id: number): UserSpool => ({
  id,
  user_id: 7,
  filament_id: 42,
  filament: { id: 42, name: 'Same product', material_type: 'PLA', color_name: null,
    color_hex: null, brand_name: null, price_per_kg: null, currency: null,
    required_nozzle_hrc: null, qr_code: 'same-product-qr' },
  initial_weight_g: 1000,
  used_weight_g: 0,
  remaining_weight_g: 1000,
  remaining_pct: 100,
  price: null,
  currency: null,
  state: 'shelf',
  source: 'qr',
  lot_nr: null,
  comment: null,
  created_at: '2026-09-12T12:00:00Z',
  updated_at: '2026-09-12T12:00:00Z',
  last_used_at: null,
  extra: null,
});

const page = (items: UserSpool[]): SpoolFeedResponse => ({
  items,
  next_cursor: null,
  summary: {
    total: items.length,
    state_counts: { active: 0, shelf: items.length, archived: 0, empty: 0 },
    available_remaining_weight_g: null,
  },
});

describe('spool feed cache helpers', () => {
  it('keeps two physical spools for the same product QR and merges only repeated IDs', () => {
    expect(mergeSpoolFeedPages([page([spool(1), spool(2)]), page([spool(2)])]).map((item) => item.id))
      .toEqual([1, 2]);
  });

  it('keeps feed and detail cache shapes distinct under one invalidation root', () => {
    expect(spoolQueryKeys.feed(7, { limit: 24, state: 'shelf' })).not.toEqual(
      spoolQueryKeys.detail(7, 24),
    );
    expect(spoolQueryKeys.feed(7, { limit: 24, state: 'shelf' }).slice(0, 1))
      .toEqual(spoolQueryKeys.root);
  });
});
