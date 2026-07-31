import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { PhysicalPrinter } from '../api/client';

const physicalPrinter: PhysicalPrinter = {
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
      declared_slot_count: 1,
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
  has_api_key: false,
  printer_hostname: null,
  reports_feed: false,
  last_seen_at: null,
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
  it('declares only the capabilities supported by each feed adapter', async () => {
    const { feedAdapterFor } = await import(
      '../components/presetSlots/adapters'
    );

    expect(feedAdapterFor('manual').capabilities).toEqual([]);
    expect(feedAdapterFor('happy_hare').capabilities).toEqual([
      'read',
      'write',
      'presence',
      'spool_identity',
      'consumption',
    ]);
    expect(feedAdapterFor('octoprint').capabilities).toEqual([
      'read',
      'write',
      'spool_identity',
      'consumption',
    ]);

    const happyHareLink = feedAdapterFor('happy_hare').link;
    const octoprintLink = feedAdapterFor('octoprint').link;
    expect(happyHareLink?.snippet('https://fh.example/spool_compat', 'device-secret'))
      .toContain('https://fh.example/spool_compat/device-secret');
    expect(octoprintLink?.snippet('https://fh.example/spool_compat', 'device-secret'))
      .toBe('https://fh.example/spool_compat');
    expect(octoprintLink?.apiKeyHeader).toBe('X-API-Key');
    expect(feedAdapterFor('octoprint').contactMode).toBe('on_demand');
    expect(feedAdapterFor('octoprint').slotCountLabelKey)
      .toBe('presetSlots.octoprint.toolCount');

    render(<>{feedAdapterFor('happy_hare').renderCreateHelp?.()}</>);
    expect(screen.getByText('presetSlots.happyHare.guide.title')).toBeInTheDocument();
    expect(screen.getByText('spoolman_support: pull')).toBeInTheDocument();
    expect(screen.getByText('t_macro_color: gatemap')).toBeInTheDocument();

    render(<>{feedAdapterFor('octoprint').renderCreateHelp?.()}</>);
    expect(screen.getByText('presetSlots.octoprint.createDescription')).toBeInTheDocument();
  });

  it('shows a manual physical printer and resolves exact linked profile ids', async () => {
    const { PresetSlotsPanel, shouldPollForAdapterContact } = await import(
      '../components/presetSlots/PresetSlotsPanel'
    );

    expect(shouldPollForAdapterContact([
      {
        ...physicalPrinter,
        has_api_key: true,
        reports_feed: false,
      },
    ])).toBe(true);
    expect(shouldPollForAdapterContact([
      {
        ...physicalPrinter,
        has_api_key: true,
        reports_feed: true,
      },
    ])).toBe(false);

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
