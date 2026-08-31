import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { GateState, MaterialSlot, UserSpool } from '../../api/client';
import { GateMapGrid } from './GateMapGrid';

const FRESH_SOURCE_TS = new Date().toISOString();

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string) => key,
  }),
}));

const gate: GateState = {
  id: 30,
  gate_index: 0,
  preset_id: null,
  spool_id: 40,
  hh_material: null,
  hh_color_hex: null,
  hh_status: null,
  source: 'web_manual',
  source_ts: '2026-07-30T00:00:00Z',
  is_active: true,
  updated_at: '2026-07-30T00:00:00Z',
};

const assignedSpool: UserSpool = {
  id: 40,
  user_id: 1,
  filament_id: 50,
  filament: {
    id: 50,
    name: 'Signal Red',
    material_type: 'PLA',
    color_name: 'Red',
    color_hex: 'FF0000',
    brand_name: 'Example',
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

function observedSlot(
  assignment: MaterialSlot['assignment'],
  status: number,
  material: string | null,
  colorHex: string | null,
): MaterialSlot {
  return {
    id: 10,
    provider_index: 0,
    label: null,
    kind: 'slot',
    active: true,
    assignment_revision: 0,
    assignment,
    legacy_projection: {
      gate_state_id: 30,
      preset_id: assignment?.preset_id ?? null,
      spool_id: assignment?.spool_id ?? null,
      source: 'hh_snapshot',
      source_ts: FRESH_SOURCE_TS,
      is_active: true,
      hh_material: material,
      hh_color_hex: colorHex,
      hh_status: status,
      updated_at: FRESH_SOURCE_TS,
    },
  };
}

describe('GateMapGrid material slots', () => {
  it('shows Happy Hare bypass as a named observed route instead of gate 1023', () => {
    const onGateClick = vi.fn();
    const bypass: MaterialSlot = {
      id: 99,
      provider_index: 1023,
      label: null,
      kind: 'bypass',
      active: true,
      assignment_revision: 0,
      assignment: null,
      observation: {
        source: 'happy_hare_moonraker',
        observed_at: FRESH_SOURCE_TS,
        received_at: FRESH_SOURCE_TS,
        present: true,
        active_feed: true,
        material: null,
        color_hex: null,
        remaining_percent: null,
        remaining_grams: null,
      },
      legacy_projection: null,
    };

    render(
      <GateMapGrid
        slots={[bypass]}
        gates={[]}
        presets={{}}
        spools={[]}
        onGateClick={onGateClick}
      />,
    );

    expect(screen.getByText('presetSlots.route.bypass')).toBeInTheDocument();
    expect(screen.getByText('presetSlots.route.bypassSelectedLoaded')).toBeInTheDocument();
    expect(screen.queryByText('1023')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('presetSlots.route.bypass'));
    expect(onGateClick).toHaveBeenCalledWith(null, bypass);
  });

  it('keeps the assigned spool visible when Happy Hare has no separate snapshot', () => {
    const onGateClick = vi.fn();
    const slot: MaterialSlot = {
      id: 10,
      provider_index: 0,
      label: null,
      kind: 'slot',
      active: true,
      assignment_revision: 0,
      assignment: {
        id: 20,
        preset_id: null,
        spool_id: 40,
        source: 'web_manual',
        source_ts: '2026-07-30T00:00:00Z',
        active: true,
      },
      legacy_projection: {
        gate_state_id: 30,
        preset_id: null,
        spool_id: 40,
        source: 'web_manual',
        source_ts: '2026-07-30T00:00:00Z',
        is_active: true,
        hh_material: null,
        hh_color_hex: null,
        hh_status: null,
        updated_at: '2026-07-30T00:00:00Z',
      },
    };

    render(
      <GateMapGrid
        slots={[slot]}
        gates={[gate]}
        presets={{}}
        spools={[assignedSpool]}
        onGateClick={onGateClick}
      />,
    );

    expect(screen.getByText('PLA')).toBeInTheDocument();
    expect(screen.getByText('Example Signal Red')).toBeInTheDocument();
    expect(screen.queryByText('Happy Hare')).not.toBeInTheDocument();
    expect(screen.queryByText('presetSlots.observation.noData')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('PLA'));
    expect(onGateClick).toHaveBeenCalledWith(gate, slot);
  });

  it('shows provider-neutral tag evidence without turning it into desired state', () => {
    const slot: MaterialSlot = {
      id: 11,
      provider_index: 0,
      label: 'Gate 0',
      kind: 'gate',
      active: true,
      assignment_revision: 0,
      assignment: null,
      legacy_projection: null,
      observation: {
        source: 'edge_happy_hare',
        observed_at: FRESH_SOURCE_TS,
        received_at: FRESH_SOURCE_TS,
        present: true,
        active_feed: false,
        spool_id: null,
        spool_identity_known: false,
        tag_uid: 'DEADBEEF',
        tag_technology: 'unknown',
        tag_format: null,
        tag_match_status: 'unlinked',
        material: null,
        color_hex: null,
        remaining_percent: null,
        remaining_grams: null,
      },
    };

    render(
      <GateMapGrid
        slots={[slot]}
        gates={[]}
        presets={{}}
        spools={[]}
        onGateClick={vi.fn()}
      />,
    );

    expect(screen.getByText(/spoolTags\.observation\.unlinked/).closest('[title]')).toHaveAttribute(
      'title',
      'DEADBEEF',
    );
    expect(slot.assignment).toBeNull();
  });

  it('shows a printer-reported empty state without hiding the desired spool', () => {
    const onGateClick = vi.fn();
    const observedEmptyGate: GateState = {
      ...gate,
      hh_status: 0,
      source: 'hh_snapshot',
      source_ts: FRESH_SOURCE_TS,
    };
    const slot = observedSlot(
      {
        id: 20,
        preset_id: 77,
        spool_id: 40,
        source: 'web_manual',
        source_ts: '2026-07-30T00:00:00Z',
        active: true,
      },
      0,
      null,
      null,
    );

    render(
      <GateMapGrid
        slots={[slot]}
        gates={[observedEmptyGate]}
        presets={{
          77: {
            id: 77,
            name: 'Voron PETG 0.20',
            extruder_temp: 240,
            bed_temp: 80,
          },
        }}
        spools={[assignedSpool]}
        onGateClick={onGateClick}
      />,
    );

    expect(screen.getByText('presetSlots.hhStatus.empty')).toBeInTheDocument();
    expect(screen.getByText('presetSlots.hhStatus.empty').closest('[title]')).toHaveAttribute(
      'title',
      'presetSlots.observation.conflict.assigned_but_observed_empty presetSlots.hhStatus.emptyTooltip',
    );
    expect(screen.getByText('Example Signal Red')).toBeInTheDocument();
    expect(screen.getByText('Voron PETG 0.20')).toBeInTheDocument();
    fireEvent.click(screen.getByText('presetSlots.hhStatus.empty'));
    expect(onGateClick).toHaveBeenCalledWith(observedEmptyGate, slot);
  });

  it('offers spool identification for material reported without a known spool', () => {
    const unassignedGate: GateState = {
      ...gate,
      spool_id: null,
      hh_material: 'PETG',
      hh_color_hex: '00FF00',
      hh_status: 1,
      source: 'hh_snapshot',
      source_ts: FRESH_SOURCE_TS,
    };
    const slot = observedSlot(null, 1, 'PETG', '00FF00');

    render(
      <GateMapGrid
        slots={[slot]}
        gates={[unassignedGate]}
        presets={{}}
        spools={[]}
        onGateClick={vi.fn()}
      />,
    );

    expect(screen.getByText('PETG')).toBeInTheDocument();
    expect(screen.getByText('presetSlots.assignment.unknownSpool')).toBeInTheDocument();
    expect(screen.queryByText('presetSlots.observation.action.observed_loaded_without_spool'))
      .not.toBeInTheDocument();
    expect(screen.queryByText('presetSlots.assignment.notAssigned')).not.toBeInTheDocument();
    expect(screen.queryByText('presetSlots.identifySpool')).not.toBeInTheDocument();
    expect(screen.queryByText('presetSlots.hhStatus.spool')).not.toBeInTheDocument();
  });

  it('shows user-facing availability without exposing the internal Happy Hare buffer state', () => {
    const bufferedGate: GateState = {
      ...gate,
      spool_id: null,
      hh_material: 'PLA',
      hh_status: 2,
      source: 'hh_snapshot',
      source_ts: FRESH_SOURCE_TS,
    };
    const view = render(
      <GateMapGrid
        slots={[observedSlot(null, 2, 'PLA', null)]}
        gates={[bufferedGate]}
        presets={{}}
        spools={[]}
        onGateClick={vi.fn()}
      />,
    );

    expect(screen.getByText('PLA')).toBeInTheDocument();
    expect(screen.queryByText('presetSlots.hhStatus.buffer')).not.toBeInTheDocument();
    expect(screen.getByText('PLA').closest('[title]')).toHaveAttribute(
      'title',
      'presetSlots.observation.conflict.observed_loaded_without_spool presetSlots.hhStatus.bufferTooltip',
    );

    view.rerender(
      <GateMapGrid
        slots={[observedSlot(null, 2, null, null)]}
        gates={[{ ...bufferedGate, hh_material: null }]}
        presets={{}}
        spools={[]}
        onGateClick={vi.fn()}
      />,
    );
    expect(screen.getByText('presetSlots.hhStatus.loaded')).toBeInTheDocument();
  });

  it('does not invent provider telemetry from a Spoolman-compatible assignment', () => {
    const slot: MaterialSlot = {
      id: 10,
      provider_index: 0,
      label: null,
      kind: 'slot',
      active: true,
      assignment_revision: 0,
      assignment: {
        id: 20,
        preset_id: null,
        spool_id: 40,
        source: 'hh_snapshot',
        source_ts: FRESH_SOURCE_TS,
        active: true,
      },
      legacy_projection: {
        gate_state_id: 30,
        preset_id: null,
        spool_id: 40,
        source: 'hh_snapshot',
        source_ts: FRESH_SOURCE_TS,
        is_active: true,
        hh_material: null,
        hh_color_hex: null,
        hh_status: null,
        updated_at: FRESH_SOURCE_TS,
      },
    };

    render(
      <GateMapGrid
        slots={[slot]}
        gates={[{ ...gate, source: 'hh_snapshot' }]}
        presets={{}}
        spools={[assignedSpool]}
        onGateClick={vi.fn()}
      />,
    );

    expect(screen.queryByText('presetSlots.hhStatus.spool')).not.toBeInTheDocument();
    expect(screen.queryByText('presetSlots.observation.noData')).not.toBeInTheDocument();
  });
});
