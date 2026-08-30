import { describe, expect, it } from 'vitest';
import type { GateState, MaterialSlot, UserSpool } from '../api/client';
import {
  compareMaterialSlot,
  MATERIAL_SLOT_OBSERVATION_FRESH_MS,
} from './materialSlotComparison';

const NOW = Date.parse('2026-07-30T00:02:00Z');

function slot(
  assignment: MaterialSlot['assignment'],
  observation: MaterialSlot['legacy_projection'],
): MaterialSlot {
  return {
    id: 10,
    provider_index: 0,
    label: null,
    kind: 'slot',
    active: true,
    assignment_revision: 0,
    assignment,
    observation: null,
    legacy_projection: observation,
  };
}

function gate(presetId: number | null, spoolId: number | null): GateState {
  return {
    id: 30,
    gate_index: 0,
    preset_id: presetId,
    spool_id: spoolId,
    hh_material: null,
    hh_color_hex: null,
    hh_status: null,
    source: 'web_manual',
    source_ts: '2026-07-30T00:00:00Z',
    is_active: true,
    updated_at: '2026-07-30T00:00:00Z',
  };
}

function assignment(spoolId: number | null, presetId: number | null = null) {
  return {
    id: 20,
    preset_id: presetId,
    spool_id: spoolId,
    source: 'web_manual',
    source_ts: '2026-07-30T00:00:00Z',
    active: true,
  };
}

function observation(status: number, material: string | null, colorHex: string | null) {
  return {
    gate_state_id: 30,
    preset_id: null,
    spool_id: null,
    source: 'hh_snapshot',
    source_ts: '2026-07-30T00:01:00Z',
    is_active: true,
    hh_material: material,
    hh_color_hex: colorHex,
    hh_status: status,
    updated_at: '2026-07-30T00:01:00Z',
  };
}

function spoolFixture(material: string, colorHex: string): UserSpool {
  return {
    id: 40,
    user_id: 1,
    filament_id: 50,
    filament: {
      id: 50,
      name: 'Test filament',
      material_type: material,
      color_name: null,
      color_hex: colorHex,
      brand_name: 'Test',
      price_per_kg: null,
      currency: null,
      required_nozzle_hrc: null,
    },
    initial_weight_g: 1000,
    used_weight_g: 100,
    remaining_weight_g: 900,
    remaining_pct: 90,
    price: null,
    currency: null,
    state: 'active',
    source: 'manual',
    lot_nr: null,
    comment: null,
    created_at: '2026-07-30T00:00:00Z',
    updated_at: '2026-07-30T00:00:00Z',
    last_used_at: null,
    extra: null,
  };
}

describe('compareMaterialSlot', () => {
  it('compares exact identities without changing desired assignments', () => {
    const observedSlot = slot(assignment(40), null);
    observedSlot.observation = {
      source: 'happy_hare_edge', observed_at: new Date(NOW).toISOString(),
      received_at: new Date(NOW).toISOString(), present: true, active_feed: false,
      material: 'PLA', color_hex: 'FF0000', remaining_percent: null, remaining_grams: null,
      spool_id: 41, spool_identity_known: true,
    };
    const compare = () => compareMaterialSlot(observedSlot, null, spoolFixture('PLA', 'FF0000'), NOW);
    expect(compare().conflict).toBe('observed_spool_differs');
    expect(compare().desiredSpoolId).toBe(40);
    observedSlot.observation.spool_id = null;
    expect(compare().conflict).toBe('observed_spool_unknown');
    expect(compare().observationState).toBe('loaded');
    observedSlot.observation.spool_id = 40;
    expect(compare().conflict).toBeNull();
    observedSlot.observation.material = 'PETG';
    expect(compare().conflict).toBe('observed_details_differ');
  });

  it('does not treat a provider-side assignment as proof that filament is loaded', () => {
    const providerAssignment = {
      ...observation(1, null, null),
      spool_id: 40,
      hh_status: null,
    };
    const result = compareMaterialSlot(
      slot(assignment(40), providerAssignment),
      gate(null, 40),
      spoolFixture('PLA', 'FF0000'),
      NOW,
    );

    expect(result.observationState).toBe('none');
    expect(result.conflict).toBeNull();
  });

  it('does not call a cleared assignment an observed empty hardware gate', () => {
    const clearedProviderAssignment = {
      ...observation(1, null, null),
      preset_id: 60,
      spool_id: null,
      hh_status: null,
    };
    const result = compareMaterialSlot(
      slot(assignment(null, 60), clearedProviderAssignment),
      gate(60, null),
      null,
      NOW,
    );

    expect(result.observationState).toBe('none');
    expect(result.conflict).toBeNull();
  });

  it('does not present a manual assignment as provider telemetry', () => {
    const manualProjection = {
      ...observation(1, null, null),
      spool_id: 40,
      source: 'web_manual',
      hh_status: null,
    };
    const result = compareMaterialSlot(
      slot(assignment(40), manualProjection),
      gate(null, 40),
      spoolFixture('PLA', 'FF0000'),
      NOW,
    );

    expect(result.observationState).toBe('none');
  });

  it('keeps a desired assignment when the provider reports an empty slot and flags review', () => {
    const result = compareMaterialSlot(
      slot(assignment(40, 60), observation(0, null, null)),
      gate(60, 40),
      spoolFixture('PLA', 'FF0000'),
      NOW,
    );

    expect(result.desiredSpoolId).toBe(40);
    expect(result.observationState).toBe('empty');
    expect(result.conflict).toBe('assigned_but_observed_empty');
  });

  it('does not infer a spool identity from provider material and color', () => {
    const result = compareMaterialSlot(
      slot(null, observation(1, 'PLA', 'FF0000')),
      gate(null, null),
      null,
      NOW,
    );

    expect(result.desiredSpoolId).toBeNull();
    expect(result.observedMaterial).toBe('PLA');
    expect(result.conflict).toBe('observed_loaded_without_spool');
  });

  it('accepts matching supporting details without treating them as identity', () => {
    const result = compareMaterialSlot(
      slot(assignment(40), observation(1, ' pla ', '#ff0000')),
      gate(null, 40),
      spoolFixture('PLA', 'FF0000'),
      NOW,
    );

    expect(result.conflict).toBeNull();
    expect(result.desiredSpoolId).toBe(40);
  });

  it('flags differing material or color for explicit review', () => {
    const result = compareMaterialSlot(
      slot(assignment(40), observation(1, 'PETG', '00FF00')),
      gate(null, 40),
      spoolFixture('PLA', 'FF0000'),
      NOW,
    );

    expect(result.conflict).toBe('observed_details_differ');
  });

  it('ignores provider observations after their freshness window', () => {
    const result = compareMaterialSlot(
      slot(assignment(40), observation(0, null, null)),
      gate(null, 40),
      spoolFixture('PLA', 'FF0000'),
      Date.parse('2026-07-30T00:01:00Z') + MATERIAL_SLOT_OBSERVATION_FRESH_MS + 1,
    );

    expect(result.observationState).toBe('none');
    expect(result.conflict).toBeNull();
  });

  it('uses normalized Bambu observations without assigning a physical spool', () => {
    const target = slot(null, null);
    target.observation = {
      source: 'bambu_lan_mqtt',
      observed_at: '2026-07-30T00:01:00Z',
      received_at: '2026-07-30T00:01:01Z',
      present: true,
      active_feed: true,
      material: 'PLA',
      color_hex: 'FF6A13',
      remaining_percent: 65,
      remaining_grams: 428,
    };

    const result = compareMaterialSlot(target, null, null, NOW);

    expect(result.observationState).toBe('loaded');
    expect(result.observedMaterial).toBe('PLA');
    expect(result.observedColorHex).toBe('FF6A13');
    expect(result.desiredSpoolId).toBeNull();
    expect(result.conflict).toBe('observed_loaded_without_spool');
  });
});
