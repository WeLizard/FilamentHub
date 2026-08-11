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
    if (queryKey[0] === 'octoprint-bridge-status') {
      return {
        data: {
          paired: true,
          octoprint_version: '1.11.8',
          plugin_version: '0.1.0',
          active_slot_index: 0,
        },
        isLoading: false,
        refetch: vi.fn(),
      };
    }
    return { data: [], isLoading: false };
  },
}));

vi.mock('../api/client', () => ({
  physicalPrintersAPI: { list: vi.fn(), clearSystem: vi.fn() },
  octoprintBridgeAPI: { status: vi.fn(), issuePairingCode: vi.fn(), revoke: vi.fn() },
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
      'presence',
      'spool_identity',
      'consumption',
    ]);

    const happyHareLink = feedAdapterFor('happy_hare').link;
    expect(happyHareLink?.snippet('https://fh.example/spool_compat', 'device-secret'))
      .toContain('https://fh.example/spool_compat/device-secret');
    expect(feedAdapterFor('octoprint').link).toBeNull();
    expect(feedAdapterFor('octoprint').contactMode).toBe('periodic');
    expect(feedAdapterFor('octoprint').slotCountLabelKey)
      .toBe('presetSlots.octoprint.slotCount');

    render(<>{feedAdapterFor('happy_hare').renderCreateHelp?.()}</>);
    expect(screen.getByText('presetSlots.happyHare.guide.title')).toBeInTheDocument();
    expect(screen.getByText('spoolman_support: pull')).toBeInTheDocument();
    expect(screen.getByText('t_macro_color: gatemap')).toBeInTheDocument();

    render(<>{feedAdapterFor('octoprint').renderCreateHelp?.()}</>);
    expect(screen.getByText('presetSlots.octoprint.createDescription')).toBeInTheDocument();

    const octoprintSystem = {
      ...physicalPrinter.material_systems[0],
      provider: 'octoprint',
    };
    render(<>{feedAdapterFor('octoprint').renderSettings?.({
      printer: { ...physicalPrinter, material_systems: [octoprintSystem] },
      system: octoprintSystem,
      gates: [],
      linkConfirmed: true,
    })}</>);
    expect(screen.getByText('presetSlots.link.label')).toBeInTheDocument();
    expect(screen.getByText('FilamentHub Bridge')).toBeInTheDocument();
    expect(screen.getByText('OctoPrint 1.11.8')).toBeInTheDocument();
    expect(screen.getByText('Bridge 0.1.0')).toBeInTheDocument();
  });

  it('waits for automatic Happy Hare v4 pairing before using the legacy fallback', async () => {
    const { feedAdapterFor } = await import(
      '../components/presetSlots/adapters'
    );
    const adapter = feedAdapterFor('happy_hare');
    const system = {
      ...physicalPrinter.material_systems[0],
      provider: 'happy_hare',
    };

    const pending = render(<>{adapter.renderSetup?.({
      printer: physicalPrinter,
      system,
      gates: [],
      linkConfirmed: false,
    })}</>);
    expect(screen.getByText('presetSlots.happyHare.autoPairingTitle')).toBeInTheDocument();
    expect(screen.queryByText('presetSlots.happyHare.pairingTitle')).not.toBeInTheDocument();
    pending.unmount();

    const paired = render(<>{adapter.renderSetup?.({
      printer: { ...physicalPrinter, printer_hostname: 'voron', reports_feed: true },
      system,
      gates: [],
      linkConfirmed: true,
    })}</>);
    expect(paired.container).toBeEmptyDOMElement();
  });

  it('keeps the one-time pairing command for Happy Hare before v4', async () => {
    const { feedAdapterFor } = await import(
      '../components/presetSlots/adapters'
    );
    const adapter = feedAdapterFor('happy_hare');
    const system = {
      ...physicalPrinter.material_systems[0],
      provider: 'happy_hare',
    };

    render(<>{adapter.renderSetup?.({
      printer: { ...physicalPrinter, reports_feed: true },
      system,
      gates: [{
        id: 41,
        gate_index: 2,
        preset_id: null,
        spool_id: 73,
        hh_material: null,
        hh_color_hex: null,
        hh_status: null,
        source: 'web_manual',
        source_ts: '2026-08-11T00:00:00Z',
        is_active: true,
        updated_at: '2026-08-11T00:00:00Z',
      }],
      linkConfirmed: true,
    })}</>);

    expect(screen.getByText('presetSlots.happyHare.pairingTitle')).toBeInTheDocument();
    expect(screen.getByText('MMU_SPOOLMAN GATE=2 SPOOLID=73')).toBeInTheDocument();
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
