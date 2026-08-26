import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  PhysicalPrinter,
  PrinterBridgeStatus,
  PrinterConnectionBinding,
} from '../api/client';

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
          assignment_revision: 0,
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

let physicalPrintersForQuery = [physicalPrinter];
let printerBindingsForQuery: PrinterConnectionBinding[] = [];
let printerBridgeStatusForQuery: PrinterBridgeStatus = {
  configured: true,
  paired: false,
  pairing_expires_at: null,
  last_seen_at: null,
  source_instance_id: null,
};
let octoprintBridgePairedForQuery = true;
const createSystem = vi.fn();
const regenerateKey = vi.fn();
const updateOctoPrintRouting = vi.fn();

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      typeof options?.name === 'string'
        ? `${key}:${options.name}`
        : typeof options?.id === 'number'
          ? `${key}:${options.id}`
          : key,
    i18n: { language: 'en' },
  }),
}));

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
  useQuery: ({ queryKey }: { queryKey: unknown[] }) => {
    if (queryKey[0] === 'physical-printers') {
      return { data: physicalPrintersForQuery, isLoading: false };
    }
    if (queryKey[0] === 'printer-bindings') {
      return { data: printerBindingsForQuery, isLoading: false };
    }
    if (queryKey[0] === 'presets') {
      return { data: { items: [] }, isLoading: false };
    }
    if (queryKey[0] === 'octoprint-bridge-status') {
      return {
        data: {
          paired: octoprintBridgePairedForQuery,
          octoprint_version: '1.11.8',
          plugin_version: '0.1.0',
          active_slot_index: 0,
          routing: {
            mode: 'tools',
            tool_slot_map: [{ tool_index: 7, slot_index: 0 }],
            revision: 4,
            applied_revision: 3,
          },
        },
        isLoading: false,
        refetch: vi.fn(),
      };
    }
    if (queryKey[0] === 'plugin-downloads') {
      return {
        data: {
          packages: [{
            plugin: 'octoprint',
            filename: 'octoprint_filamenthub_bridge-0.1.0-py3-none-any.whl',
            version: '0.1.0',
            file_size: '32 KB',
            checksum: null,
            download_url: '/api/v1/downloads/plugins/octoprint_filamenthub_bridge-0.1.0-py3-none-any.whl',
            github_url: null,
          }],
          release_url: null,
        },
        isLoading: false,
      };
    }
    if (queryKey[0] === 'printer-bridge-status') {
      return {
        data: printerBridgeStatusForQuery,
        isLoading: false,
        refetch: vi.fn(),
      };
    }
    return { data: [], isLoading: false };
  },
}));

vi.mock('../api/client', () => ({
  devicesAPI: { regenerateKey },
  physicalPrintersAPI: { list: vi.fn(), clearSystem: vi.fn(), createSystem },
  octoprintBridgeAPI: {
    status: vi.fn(),
    issuePairingCode: vi.fn(),
    updateRouting: updateOctoPrintRouting,
    revoke: vi.fn(),
  },
  downloadsAPI: { getPluginDownloads: vi.fn() },
  printerBridgeAPI: { status: vi.fn(), issuePairingCode: vi.fn() },
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
  beforeEach(() => {
    physicalPrintersForQuery = [physicalPrinter];
    printerBindingsForQuery = [];
    printerBridgeStatusForQuery = {
      configured: true,
      paired: false,
      pairing_expires_at: null,
      last_seen_at: null,
      source_instance_id: null,
    };
    octoprintBridgePairedForQuery = true;
    createSystem.mockReset();
    createSystem.mockResolvedValue({});
    regenerateKey.mockReset();
    regenerateKey.mockResolvedValue({ api_key: 'fresh-printer-key' });
    updateOctoPrintRouting.mockReset();
    updateOctoPrintRouting.mockResolvedValue({
      mode: 'tools',
      tool_slot_map: [{ tool_index: 7, slot_index: 0 }],
      revision: 5,
      applied_revision: 3,
    });
    window.localStorage.clear();
  });

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
      'local_command',
    ]);
    expect(feedAdapterFor('happy_hare').topologyFromProvider).toBe(true);
    expect(feedAdapterFor('octoprint').capabilities).toEqual([
      'read',
      'write',
      'spool_identity',
      'consumption',
    ]);

    const happyHareLink = feedAdapterFor('happy_hare').link;
    const happyHareSnippet = happyHareLink?.snippet(
      'https://fh.example/spool_compat',
      'device-secret',
    );
    expect(happyHareSnippet)
      .toContain('https://fh.example/spool_compat/device-secret');
    expect(happyHareSnippet).toContain('sync_rate: 60');
    expect(feedAdapterFor('octoprint').link).toBeNull();
    expect(feedAdapterFor('octoprint').contactMode).toBe('periodic');
    expect(feedAdapterFor('octoprint').slotCountLabelKey)
      .toBe('presetSlots.octoprint.slotCount');
    expect(feedAdapterFor('bambu').capabilities).toEqual(['read', 'write', 'presence']);
    expect(feedAdapterFor('bambu').topologyFromProvider).toBe(true);

    const bambuSystem = {
      ...physicalPrinter.material_systems[0],
      provider: 'bambu',
    };
    render(<>{feedAdapterFor('bambu').renderSetup?.({
      printer: {
        ...physicalPrinter,
        material_systems: [bambuSystem],
        connectors: [{
          id: 91,
          material_system_id: bambuSystem.id,
          provider: 'bambu',
          transport: 'orca_plugin_lan',
          capabilities: ['read', 'presence'],
          active: true,
          last_seen_at: null,
        }],
      },
      system: bambuSystem,
      gates: [],
      spools: [],
      linkConfirmed: false,
    })}</>);
    expect(screen.getByText('presetSlots.bambu.notConnected')).toBeInTheDocument();
    expect(screen.queryByText('presetSlots.bambu.changeConnection')).not.toBeInTheDocument();
    expect(screen.getByText('presetSlots.bambu.openInPlugin')).toBeInTheDocument();

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
      spools: [],
      linkConfirmed: true,
    })}</>);
    expect(screen.getByText('presetSlots.link.label')).toBeInTheDocument();
    expect(screen.getByText('FilamentHub Bridge')).toBeInTheDocument();
    expect(screen.getByText('OctoPrint 1.11.8')).toBeInTheDocument();
    expect(screen.getByText('Bridge 0.1.0')).toBeInTheDocument();
  });

  it('edits OctoPrint tool routing without changing physical slot topology', async () => {
    const { feedAdapterFor } = await import('../components/presetSlots/adapters');
    const octoprintSystem = {
      ...physicalPrinter.material_systems[0],
      provider: 'octoprint',
    };

    render(<>{feedAdapterFor('octoprint').renderSettings?.({
      printer: { ...physicalPrinter, material_systems: [octoprintSystem] },
      system: octoprintSystem,
      gates: [],
      spools: [],
      linkConfirmed: true,
    })}</>);

    expect(screen.getByText('presetSlots.octoprint.routingPending')).toBeInTheDocument();
    fireEvent.click(screen.getByTitle('presetSlots.octoprint.routingTitle'));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByLabelText('presetSlots.octoprint.toolIndex')).toHaveValue(7);
    expect(screen.getByLabelText('presetSlots.octoprint.targetSlot')).toHaveValue('0');

    fireEvent.click(screen.getByRole('button', { name: 'common.save' }));
    await waitFor(() => expect(updateOctoPrintRouting).toHaveBeenCalledWith(
      11,
      21,
      {
        mode: 'tools',
        tool_slot_map: [{ tool_index: 7, slot_index: 0 }],
        expected_revision: 4,
      },
    ));
    expect(physicalPrinter.material_systems[0].declared_slot_count).toBe(1);
  });

  it('shows OctoPrint Bridge installation instructions without external navigation', async () => {
    octoprintBridgePairedForQuery = false;
    const { feedAdapterFor } = await import('../components/presetSlots/adapters');
    const octoprintSystem = {
      ...physicalPrinter.material_systems[0],
      provider: 'octoprint',
    };

    render(<>{feedAdapterFor('octoprint').renderSetup?.({
      printer: { ...physicalPrinter, material_systems: [octoprintSystem] },
      system: octoprintSystem,
      gates: [],
      spools: [],
      linkConfirmed: false,
    })}</>);

    fireEvent.click(screen.getByRole('button', {
      name: 'presetSlots.octoprint.bridgeDocs',
    }));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('downloadPage.octoInstall1')).toBeInTheDocument();
    expect(screen.getByText('downloadPage.octoInstall2')).toBeInTheDocument();
    expect(screen.getByText('downloadPage.octoInstall3')).toBeInTheDocument();
    const download = screen.getByRole('link', {
      name: 'downloadPage.octoDownload',
    });
    expect(download).toHaveAttribute(
      'download',
      'octoprint_filamenthub_bridge-0.1.0-py3-none-any.whl',
    );
    expect(download).not.toHaveAttribute('target');
  });

  it('does not present a paired Bambu bridge as live before its first snapshot', async () => {
    const { feedAdapterFor } = await import('../components/presetSlots/adapters');
    const bambuSystem = {
      ...physicalPrinter.material_systems[0],
      provider: 'bambu',
    };
    const context = {
      printer: {
        ...physicalPrinter,
        material_systems: [bambuSystem],
        connectors: [{
          id: 91,
          material_system_id: bambuSystem.id,
          provider: 'bambu',
          transport: 'orca_plugin_lan',
          capabilities: ['read', 'presence'],
          active: true,
          last_seen_at: null,
        }],
      },
      system: bambuSystem,
      gates: [],
      spools: [],
      linkConfirmed: false,
    };
    printerBridgeStatusForQuery = {
      configured: true,
      paired: true,
      pairing_expires_at: null,
      last_seen_at: null,
      source_instance_id: 'fixture-instance',
    };

    const first = render(<>{feedAdapterFor('bambu').renderSetup?.(context)}</>);
    expect(screen.getByText('presetSlots.bambu.awaitingFirstData')).toBeInTheDocument();
    expect(screen.queryByText('presetSlots.bambu.connected')).not.toBeInTheDocument();
    first.unmount();

    printerBridgeStatusForQuery = {
      ...printerBridgeStatusForQuery,
      last_seen_at: '2026-08-14T12:00:00Z',
    };
    render(<>{feedAdapterFor('bambu').renderSetup?.(context)}</>);
    expect(screen.getByText('presetSlots.bambu.connected')).toBeInTheDocument();
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
      spools: [],
      linkConfirmed: false,
    })}</>);
    expect(screen.getByText('presetSlots.happyHare.autoPairingTitle')).toBeInTheDocument();
    expect(screen.queryByText('presetSlots.happyHare.pairingTitle')).not.toBeInTheDocument();
    pending.unmount();

    const pairedContext = {
      printer: { ...physicalPrinter, printer_hostname: 'voron', reports_feed: true },
      system,
      gates: [],
      spools: [],
      linkConfirmed: true,
    };
    const paired = render(<>
      {adapter.renderSetup?.(pairedContext)}
      {adapter.renderActions?.(pairedContext)}
    </>);
    expect(screen.getByText('presetSlots.happyHare.refresh.check')).toBeInTheDocument();
    expect(screen.queryByText('presetSlots.happyHare.refresh.title')).not.toBeInTheDocument();
    expect(screen.queryByText('presetSlots.happyHare.refresh.fallback')).not.toBeInTheDocument();
    expect(screen.queryByText('presetSlots.happyHare.refresh.copyCommand')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('presetSlots.happyHare.refresh.check'));
    expect(screen.getByText('presetSlots.happyHare.refresh.title')).toBeInTheDocument();
    expect(screen.getByText('presetSlots.happyHare.refresh.fallback')).toBeInTheDocument();
    expect(screen.getByText('presetSlots.happyHare.refresh.copyCommand')).toBeInTheDocument();
    expect(paired.container).not.toBeEmptyDOMElement();
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
      spools: [],
      linkConfirmed: true,
    })}</>);

    expect(screen.getByText('presetSlots.happyHare.pairingTitle')).toBeInTheDocument();
    expect(screen.getByText('MMU_SPOOLMAN GATE=2 SPOOLID=73')).toBeInTheDocument();
  });

  it('shows a manual physical printer and resolves exact linked profile ids', async () => {
    const {
      adapterContactPollIntervalMs,
      PresetSlotsPanel,
      shouldContinueAdapterContactPolling,
      shouldPollForAdapterContact,
    } = await import(
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
    expect(shouldContinueAdapterContactPolling([
      {
        ...physicalPrinter,
        has_api_key: true,
        reports_feed: false,
      },
    ], 70_000, 20_000)).toBe(true);
    expect(shouldContinueAdapterContactPolling([
      {
        ...physicalPrinter,
        has_api_key: true,
        reports_feed: false,
      },
    ], 70_000, 70_000)).toBe(false);
    expect(adapterContactPollIntervalMs(0)).toBe(15_000);
    expect(adapterContactPollIntervalMs(0.5)).toBe(20_000);
    expect(adapterContactPollIntervalMs(1)).toBe(25_000);

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

  it('remembers a collapsed MMU system without changing its assignments', async () => {
    physicalPrintersForQuery = [{
      ...physicalPrinter,
      material_systems: [{
        ...physicalPrinter.material_systems[0],
        name: 'Workshop MMU',
        kind: 'direct_feed',
        provider: 'happy_hare',
      }],
    }];
    const { PresetSlotsPanel } = await import(
      '../components/presetSlots/PresetSlotsPanel'
    );

    const first = render(<PresetSlotsPanel spools={[]} printerProfiles={[]} />);
    expect(screen.getByTestId('gate-map')).toBeInTheDocument();
    fireEvent.click(screen.getByTitle('presetSlots.collapseSystem'));
    expect(screen.queryByTestId('gate-map')).not.toBeInTheDocument();
    expect(window.localStorage.getItem('filamenthub:material-system:collapsed:1:21')).toBe('1');
    first.unmount();

    render(<PresetSlotsPanel spools={[]} printerProfiles={[]} />);
    expect(screen.queryByTestId('gate-map')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTitle('presetSlots.expandSystem'));
    expect(screen.getByTestId('gate-map')).toBeInTheDocument();
  });

  it('keeps a one-slot OctoPrint system collapsible through the shared persisted state', async () => {
    physicalPrintersForQuery = [{
      ...physicalPrinter,
      material_systems: [{
        ...physicalPrinter.material_systems[0],
        name: 'OctoPrint tools',
        kind: 'direct_feed',
        provider: 'octoprint',
      }],
    }];
    const { PresetSlotsPanel } = await import(
      '../components/presetSlots/PresetSlotsPanel'
    );

    const first = render(<PresetSlotsPanel spools={[]} printerProfiles={[]} />);
    fireEvent.click(screen.getByTitle('presetSlots.collapseSystem'));
    expect(screen.queryByTestId('gate-map')).not.toBeInTheDocument();
    expect(window.localStorage.getItem('filamenthub:material-system:collapsed:1:21')).toBe('1');
    first.unmount();

    render(<PresetSlotsPanel spools={[]} printerProfiles={[]} />);
    expect(screen.queryByTestId('gate-map')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTitle('presetSlots.expandSystem'));
    expect(screen.getByTestId('gate-map')).toBeInTheDocument();
  });

  it('makes same-named physical printers distinguishable before adding a material system', async () => {
    physicalPrintersForQuery = [
      {
        ...physicalPrinter,
        id: 41,
        logical_id: 'printer-41',
        name: 'Voron 2.4 350',
        printer_profile_ids: [401],
        material_systems: [],
      },
      {
        ...physicalPrinter,
        id: 42,
        logical_id: 'printer-42',
        name: 'Voron 2.4 350',
        printer_profile_ids: [402, 403],
        material_systems: [],
      },
    ];
    printerBindingsForQuery = [{
      physical_printer_id: 41,
      connection_ref: 'local-printer-41',
      provider: 'moonraker',
      display_endpoint: null,
      endpoint_shared: false,
      last_seen_at: '2026-08-13T00:00:00Z',
    }];

    const { PresetSlotsPanel } = await import(
      '../components/presetSlots/PresetSlotsPanel'
    );
    render(<PresetSlotsPanel
      spools={[]}
      printerProfiles={[
        { id: 401, name: 'Workshop Voron 0.4' },
        { id: 402, name: 'Office Voron 0.4' },
        { id: 403, name: 'Office Voron 0.6' },
      ]}
    />);

    fireEvent.click(screen.getByText('presetSlots.newSystem.add'));
    fireEvent.focus(screen.getByPlaceholderText('presetSlots.newSystem.printerPlaceholder'));

    expect(
      (screen.getByPlaceholderText(
        'presetSlots.newSystem.printerPlaceholder',
      ) as HTMLInputElement).value,
    ).toContain('presetSlots.connectionProvider.moonraker · myPrinters.localConnection');
    expect(screen.getByText(/Workshop Voron 0\.4/)).toBeInTheDocument();
    expect(screen.getByText('Office Voron 0.4 / Office Voron 0.6')).toBeInTheDocument();
    expect(screen.getByText('presetSlots.newSystem.printerHint')).toBeInTheDocument();
  });

  it('uses a next step when the selected material system requires a printer link', async () => {
    physicalPrintersForQuery = [{
      ...physicalPrinter,
      material_systems: [],
    }];
    const { PresetSlotsPanel } = await import(
      '../components/presetSlots/PresetSlotsPanel'
    );

    render(<PresetSlotsPanel spools={[]} printerProfiles={[]} />);
    fireEvent.click(screen.getByText('presetSlots.newSystem.add'));

    expect(screen.getByText('presetSlots.newSystem.create')).toBeInTheDocument();
    fireEvent.focus(screen.getByDisplayValue('presetSlots.feedSystem.direct'));
    fireEvent.click(screen.getByText('presetSlots.feedSystem.happy_hare'));

    expect(screen.getByText('presetSlots.newSystem.next')).toBeInTheDocument();
    expect(screen.queryByText('presetSlots.newSystem.create')).not.toBeInTheDocument();

    fireEvent.click(screen.getByText('presetSlots.newSystem.next'));

    await waitFor(() => {
      expect(createSystem).toHaveBeenCalledWith(11, expect.objectContaining({
        provider: 'happy_hare',
      }));
      expect(regenerateKey).toHaveBeenCalledWith(11);
    });
    expect(screen.getByText('presetSlots.newSystem.keyTitle')).toBeInTheDocument();
    expect(screen.getByText(/fresh-printer-key/)).toBeInTheDocument();
    expect(screen.getByText('presetSlots.happyHare.linkHint')).toBeInTheDocument();
    expect(screen.getByText('presetSlots.newSystem.done')).toBeInTheDocument();
  });
});
