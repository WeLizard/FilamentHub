import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const physicalPrinter = {
  id: 11,
  logical_id: 'printer-11',
  printer_id: null,
  name: 'Manual Voron',
  printer_profile_ids: [77],
  material_systems: [
    {
      id: 21,
      name: 'Direct feed',
      kind: 'direct_feed',
      provider: 'manual',
      capabilities: ['write'],
      active: true,
      slots: [
        {
          id: 31,
          provider_index: 0,
          label: null,
          kind: 'slot',
          active: true,
          assignment: null,
          legacy_projection: null,
        },
      ],
    },
  ],
  connectors: [],
  created_at: '2026-07-18T00:00:00Z',
  updated_at: '2026-07-18T00:00:00Z',
};

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      typeof options?.name === 'string' ? `${key}:${options.name}` : key,
    i18n: { language: 'en' },
  }),
}));

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useQuery: ({ queryKey }: { queryKey: unknown[] }) => {
    if (queryKey[0] === 'physical-printers') {
      return { data: [physicalPrinter], isLoading: false };
    }
    if (queryKey[0] === 'presets') {
      return { data: { items: [] }, isLoading: false };
    }
    return { data: [], isLoading: false };
  },
}));

vi.mock('../api/client', () => ({
  physicalPrintersAPI: { list: vi.fn(), clearSystem: vi.fn() },
  presetsAPI: { list: vi.fn(), get: vi.fn() },
  spoolsAPI: { list: vi.fn() },
}));

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1 } }),
}));

vi.mock('../components/presetSlots/GateMapGrid', () => ({
  GateMapGrid: () => <div data-testid="gate-map" />,
}));

vi.mock('../components/presetSlots/PresetAssignModal', () => ({
  PresetAssignModal: () => null,
}));

vi.mock('../components/Toast', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

describe('PresetSlotsPanel', () => {
  it('shows a manual physical printer and resolves exact linked profile ids', async () => {
    const { PresetSlotsPanel } = await import(
      '../components/presetSlots/PresetSlotsPanel'
    );

    render(
      <PresetSlotsPanel
        spools={[]}
        printerProfiles={[
          { id: 77, name: 'Voron 0.4 nozzle' },
          { id: 11, name: 'Unrelated catalog-id collision' },
        ]}
      />,
    );

    expect(screen.getByText('Manual Voron')).toBeInTheDocument();
    expect(
      screen.getByText('presetSlots.mappedPrinter:Voron 0.4 nozzle'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Unrelated catalog-id collision/)).not.toBeInTheDocument();
    expect(screen.getByTestId('gate-map')).toBeInTheDocument();
  });
});
