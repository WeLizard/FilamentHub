import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { GateState, MaterialSlot, UserSpool } from '../../api/client';
import { GateMapGrid } from './GateMapGrid';

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
    assignment,
    legacy_projection: {
      gate_state_id: 30,
      preset_id: assignment?.preset_id ?? null,
      spool_id: assignment?.spool_id ?? null,
      source: 'hh_snapshot',
      source_ts: '2026-07-30T00:01:00Z',
      is_active: true,
      hh_material: material,
      hh_color_hex: colorHex,
      hh_status: status,
      updated_at: '2026-07-30T00:01:00Z',
    },
  };
}

describe('GateMapGrid material slots', () => {
  it('keeps the assigned spool visible when Happy Hare has no separate snapshot', () => {
    const onGateClick = vi.fn();
    const slot: MaterialSlot = {
      id: 10,
      provider_index: 0,
      label: null,
      kind: 'slot',
      active: true,
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

  it('shows a printer-reported empty state without hiding the desired spool', () => {
    const onGateClick = vi.fn();
    const observedEmptyGate: GateState = {
      ...gate,
      hh_status: 0,
      source: 'hh_snapshot',
      source_ts: '2026-07-30T00:01:00Z',
    };
    const slot = observedSlot(
      {
        id: 20,
        preset_id: null,
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
        presets={{}}
        spools={[assignedSpool]}
        onGateClick={onGateClick}
      />,
    );

    expect(screen.getByText('PLA')).toBeInTheDocument();
    expect(screen.getByText('presetSlots.hhStatus.empty')).toBeInTheDocument();
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
      source_ts: '2026-07-30T00:01:00Z',
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
    expect(screen.getAllByText('presetSlots.identifySpool').length).toBeGreaterThan(0);
  });

  it('shows a compact provider confirmation from the Spoolman-compatible path', () => {
    const slot: MaterialSlot = {
      id: 10,
      provider_index: 0,
      label: null,
      kind: 'slot',
      active: true,
      assignment: {
        id: 20,
        preset_id: null,
        spool_id: 40,
        source: 'hh_snapshot',
        source_ts: '2026-07-30T00:01:00Z',
        active: true,
      },
      legacy_projection: {
        gate_state_id: 30,
        preset_id: null,
        spool_id: 40,
        source: 'hh_snapshot',
        source_ts: '2026-07-30T00:01:00Z',
        is_active: true,
        hh_material: null,
        hh_color_hex: null,
        hh_status: null,
        updated_at: '2026-07-30T00:01:00Z',
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

    expect(screen.getByText('presetSlots.hhStatus.spool')).toBeInTheDocument();
    expect(screen.queryByText('presetSlots.observation.noData')).not.toBeInTheDocument();
  });
});
