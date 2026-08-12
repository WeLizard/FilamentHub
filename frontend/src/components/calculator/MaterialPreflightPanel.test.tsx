import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';

import type { UserSpool } from '../../api/client';
import type { CalculatorPreflightResponse } from '../../types/api';
import { MaterialPreflightPanel } from './MaterialPreflightPanel';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) => (
      values ? `${key}:${JSON.stringify(values)}` : key
    ),
  }),
}));

vi.mock('react-router-dom', () => ({
  Link: ({ children, to }: { children: ReactNode; to: string }) => (
    <a href={to}>{children}</a>
  ),
}));

const spool = (id: number, filamentId: number): UserSpool => ({
  id,
  user_id: 1,
  filament_id: filamentId,
  filament: {
    id: filamentId,
    name: `Material ${filamentId}`,
    material_type: 'ABS',
    color_name: null,
    color_hex: null,
    brand_name: 'Brand',
    price_per_kg: null,
    currency: null,
    required_nozzle_hrc: null,
  },
  initial_weight_g: 200,
  used_weight_g: 0,
  remaining_weight_g: 200,
  remaining_pct: 100,
  price: null,
  currency: null,
  state: 'shelf',
  source: 'manual',
  lot_nr: null,
  comment: null,
  created_at: '2026-08-09T12:00:00Z',
  updated_at: '2026-08-09T12:00:00Z',
  last_used_at: null,
  extra: null,
});

const result: CalculatorPreflightResponse = {
  status: 'insufficient',
  safety_buffer_percent: 10,
  required_base_g: 100,
  safety_buffer_g: 10,
  required_planned_g: 110,
  purchase_cost_by_currency: {},
  purchase_cost_complete: false,
  printer_compatibility: null,
  lines: [
    {
      line_id: 'tool-0',
      job_key: null,
      tool_index: 0,
      label: 'ABS Black',
      filament_id: 10,
      status: 'insufficient',
      evidence_source: 'gcode',
      mapping_source: 'automatic',
      mapping_confidence: 'high',
      required_base_g: 100,
      required_length_mm: null,
      required_volume_cm3: null,
      safety_buffer_g: 10,
      required_planned_g: 110,
      selected_remaining_g: 20,
      expected_after_g: 0,
      shortfall_base_g: 80,
      shortfall_buffer_g: 10,
      change_count: 0,
      requires_spool_change: false,
      purchase_cost_by_currency: {},
      purchase_cost_complete: false,
      allocations: [],
      spool_suggestions: [
        {
          spool_id: 2,
          filament_id: 10,
          relation: 'same_filament',
          requires_reslice: false,
          remaining_g: 40,
          reserved_elsewhere_g: 0,
          coverage_target_g: 90,
          covers_target: false,
          remaining_status: 'known',
          remaining_evidence: 'intake',
          remaining_confidence: 'low',
          remaining_updated_at: '2026-08-09T12:00:00Z',
        },
        {
          spool_id: 3,
          filament_id: 11,
          relation: 'same_line',
          requires_reslice: true,
          remaining_g: 200,
          reserved_elsewhere_g: 0,
          coverage_target_g: 110,
          covers_target: true,
          remaining_status: 'known',
          remaining_evidence: 'intake',
          remaining_confidence: 'low',
          remaining_updated_at: '2026-08-09T12:00:00Z',
        },
      ],
    },
  ],
};

describe('MaterialPreflightPanel alternatives', () => {
  it('adds an exact spool but keeps a reslice candidate informational', () => {
    const onSpoolIdsChange = vi.fn();
    render(
      <MaterialPreflightPanel
        lines={[{
          lineId: 'tool-0',
          label: 'ABS Black',
          toolIndex: 0,
          filamentId: 10,
          selectedSpoolIds: [1],
        }]}
        spools={[spool(1, 10), spool(2, 10), spool(3, 11)]}
        result={result}
        safetyBufferPercent={10}
        isLoading={false}
        error={null}
        canRun
        formatSpoolLabel={(item) => `Spool ${item.id}`}
        onSafetyBufferChange={vi.fn()}
        onSpoolIdsChange={onSpoolIdsChange}
        onRefresh={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Spool 2/ }));
    expect(onSpoolIdsChange).toHaveBeenCalledWith('tool-0', [1, 2]);

    const replacement = screen.getByText('Spool 3');
    expect(replacement.closest('button')).toBeNull();
    expect(screen.getByText('profilePage.calculator.preflightReplacementWarning')).toBeTruthy();
  });

  it('shows an incompatible printer check as advisory evidence', () => {
    render(
      <MaterialPreflightPanel
        lines={[]}
        spools={[]}
        result={{
          ...result,
          printer_compatibility: {
            physical_printer_id: 7,
            physical_printer_name: 'Workshop Voron',
            status: 'incompatible',
            checks: [{
              kind: 'nozzle_hrc',
              status: 'incompatible',
              job_key: null,
              line_id: 'tool-0',
              printer_profile_id: 12,
              printer_profile_name: 'Voron 0.4 brass',
              required_value: 50,
              available_values: [2],
              unit: 'HRC',
              requirement_source: 'filament_catalog',
              capability_source: 'printer_profile',
            }],
          },
        }}
        safetyBufferPercent={10}
        isLoading={false}
        error={null}
        canRun
        formatSpoolLabel={(item) => `Spool ${item.id}`}
        onSafetyBufferChange={vi.fn()}
        onSpoolIdsChange={vi.fn()}
        onRefresh={vi.fn()}
      />,
    );

    expect(screen.getByText(/Workshop Voron/)).toBeTruthy();
    expect(screen.getByText('profilePage.calculator.printerCompatibilityKind.nozzle_hrc')).toBeTruthy();
    expect(screen.getByText(/50 HRC/)).toBeTruthy();
  });
});
