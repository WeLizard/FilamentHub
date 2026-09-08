import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type {
  OctoPrintBridgeStatus,
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
  last_observation_at: null,
  last_snapshot_sequence: null,
  last_snapshot_source_instance_id: null,
  source_instance_id: null,
  node_instance_id: null,
  provider: 'bambu',
  transport: 'orca_plugin_lan',
  capabilities: [],
};
let octoprintBridgeStatusForQuery: OctoPrintBridgeStatus = {
  configured: true,
  paired: true,
  pairing_expires_at: null,
  last_seen_at: '2026-08-28T10:40:57Z',
  reported_slot: {
    slot_index: 0,
    source: 'tool_command',
    reported_at: '2026-08-28T10:40:57Z',
  },
  instance_id: 'octoprint-fixture',
  plugin_version: '0.1.0',
  octoprint_version: '1.11.8',
  routing: {
    mode: 'tools',
    tool_slot_map: [{ tool_index: 7, slot_index: 0 }],
    revision: 4,
    applied_revision: 3,
  },
};
const createSystem = vi.fn();
const setupConnection = vi.fn();
const regenerateKey = vi.fn();
const updateOctoPrintRouting = vi.fn();

vi.mock('../hooks/usePrinterContactEvents', () => ({ usePrinterContactEvents: vi.fn() }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      typeof options?.sources === 'string'
        ? `${key}:${options.sources}`
        : typeof options?.source === 'string'
          ? `${key}:${options.source}`
          : typeof options?.name === 'string'
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
        data: octoprintBridgeStatusForQuery,
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
  physicalPrintersAPI: { list: vi.fn(), clearSystem: vi.fn(), createSystem,
    setupConnection, listBindings: vi.fn(), listInstalledCandidates: vi.fn() },
  printersAPI: { list: vi.fn() },
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
    sessionStorage.clear();
    setupConnection.mockReset();
    setupConnection.mockImplementation(async (id, payload) => {
      physicalPrintersForQuery = physicalPrintersForQuery.map((printer) => printer.id === id
        ? { ...printer, material_systems: [{ ...physicalPrinter.material_systems[0], ...payload.material_system }] }
        : printer);
      return physicalPrintersForQuery.find((printer) => printer.id === id);
    });
    physicalPrintersForQuery = [physicalPrinter];
    printerBindingsForQuery = [];
    printerBridgeStatusForQuery = {
      configured: true,
      paired: false,
      pairing_expires_at: null,
      last_seen_at: null,
      last_observation_at: null,
      last_snapshot_sequence: null,
      last_snapshot_source_instance_id: null,
      node_instance_id: null,
      source_instance_id: null,
      provider: 'bambu',
      transport: 'orca_plugin_lan',
      capabilities: [],
    };
    octoprintBridgeStatusForQuery = {
      configured: true,
      paired: true,
      pairing_expires_at: null,
      last_seen_at: '2026-08-28T10:40:57Z',
      reported_slot: {
        slot_index: 0,
        source: 'tool_command',
        reported_at: '2026-08-28T10:40:57Z',
      },
      instance_id: 'octoprint-fixture',
      plugin_version: '0.1.0',
      octoprint_version: '1.11.8',
      routing: {
        mode: 'tools',
        tool_slot_map: [{ tool_index: 7, slot_index: 0 }],
        revision: 4,
        applied_revision: 3,
      },
    };
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
    const { feedAdapterFor, supportsEdgeSetup } = await import(
      '../components/presetSlots/adapters'
    );

    expect(['manual', 'legacy', 'happy_hare'].map((provider) => supportsEdgeSetup(provider))).toEqual([true, true, true]);
    expect(['bambu', 'octoprint', 'unknown'].map((provider) => supportsEdgeSetup(provider))).toEqual([false, false, false]);
    expect(supportsEdgeSetup('manual', 'multi_tool')).toBe(false);
    expect(supportsEdgeSetup('manual', 'mmu')).toBe(false);

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
    expect(happyHareSnippet).not.toContain('sync_rate:');
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

  it('labels declared and commanded slots by their actual source', async () => {
    const { feedAdapterFor } = await import('../components/presetSlots/adapters');
    const octoprintSystem = {
      ...physicalPrinter.material_systems[0],
      provider: 'octoprint',
    };
    const context = {
      printer: { ...physicalPrinter, material_systems: [octoprintSystem] },
      system: octoprintSystem,
      gates: [],
      spools: [],
      linkConfirmed: true,
    };

    octoprintBridgeStatusForQuery = {
      ...octoprintBridgeStatusForQuery,
      reported_slot: {
        slot_index: 0,
        source: 'manual_declaration',
        reported_at: '2026-08-28T10:40:57Z',
      },
      routing: {
        mode: 'manual',
        tool_slot_map: [],
        revision: 5,
        applied_revision: 4,
      },
    };
    const pendingManualRouting = render(<>{feedAdapterFor('octoprint').renderSettings?.(context)}</>);
    expect(screen.getByText('presetSlots.octoprint.reportedSlot.manual_declaration')).toBeInTheDocument();
    pendingManualRouting.unmount();

    octoprintBridgeStatusForQuery = {
      ...octoprintBridgeStatusForQuery,
      reported_slot: {
        slot_index: 1,
        source: 'tool_command',
        reported_at: '2026-08-28T10:41:57Z',
      },
      routing: {
        mode: 'tools',
        tool_slot_map: [{ tool_index: 0, slot_index: 1 }],
        revision: 5,
        applied_revision: 5,
      },
    };
    render(<>{feedAdapterFor('octoprint').renderSettings?.(context)}</>);

    expect(screen.getByText('presetSlots.octoprint.reportedSlot.tool_command')).toBeInTheDocument();
  });

  it('shows OctoPrint Bridge installation instructions without external navigation', async () => {
    octoprintBridgeStatusForQuery = {
      ...octoprintBridgeStatusForQuery,
      paired: false,
    };
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
      last_observation_at: null,
      last_snapshot_sequence: null,
      last_snapshot_source_instance_id: null,
      node_instance_id: null,
      source_instance_id: 'fixture-instance',
      provider: 'bambu',
      transport: 'orca_plugin_lan',
      capabilities: ['read', 'presence'],
    };

    const first = render(<>{feedAdapterFor('bambu').renderSetup?.(context)}</>);
    expect(screen.getByText('presetSlots.bambu.awaitingFirstData')).toBeInTheDocument();
    expect(screen.queryByText('presetSlots.bambu.connected')).not.toBeInTheDocument();
    first.unmount();

    printerBridgeStatusForQuery = {
      ...printerBridgeStatusForQuery,
      last_observation_at: new Date().toISOString(),
    };
    render(<>{feedAdapterFor('bambu').renderSetup?.(context)}</>);
    expect(screen.getByText('presetSlots.bambu.connected')).toBeInTheDocument();
  });

  it('waits for automatic Happy Hare v4 pairing without presenting a fake local refresh', async () => {
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
    expect(screen.queryByText('presetSlots.happyHare.refreshStatus')).not.toBeInTheDocument();
    expect(screen.queryByText('presetSlots.happyHare.refresh.title')).not.toBeInTheDocument();
    expect(screen.queryByText('presetSlots.happyHare.refresh.fallback')).not.toBeInTheDocument();
    expect(screen.queryByText('presetSlots.happyHare.refresh.copyCommand')).not.toBeInTheDocument();
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
      PresetSlotsPanel,
    } = await import(
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

  it('sizes printer cards from their slots and keeps card order in the wrapping layout', async () => {
    const slotsFor = (count: number, idBase: number) => Array.from(
      { length: count },
      (_, providerIndex) => ({
        ...physicalPrinter.material_systems[0].slots[0],
        id: idBase + providerIndex,
        provider_index: providerIndex,
      }),
    );
    physicalPrintersForQuery = [{
      ...physicalPrinter,
      name: 'Five-slot Voron',
      material_systems: [{
        ...physicalPrinter.material_systems[0],
        slots: slotsFor(5, 100),
      }],
    }, {
      ...physicalPrinter,
      id: 12,
      logical_id: 'printer-12',
      name: 'Three-slot printer',
      material_systems: [{
        ...physicalPrinter.material_systems[0],
        id: 22,
        slots: slotsFor(3, 200),
      }],
    }];
    const { PresetSlotsPanel } = await import(
      '../components/presetSlots/PresetSlotsPanel'
    );

    render(<PresetSlotsPanel spools={[]} printerProfiles={[]} />);

    const fiveSlotCard = screen.getByRole('heading', { name: 'Five-slot Voron' })
      .closest('.rounded-2xl') as HTMLElement;
    const threeSlotCard = screen.getByRole('heading', { name: 'Three-slot printer' })
      .closest('.rounded-2xl') as HTMLElement;
    const fiveSlotWrapper = fiveSlotCard.parentElement as HTMLElement;
    const threeSlotWrapper = threeSlotCard.parentElement as HTMLElement;
    const layout = fiveSlotWrapper.parentElement as HTMLElement;

    expect(fiveSlotCard).toHaveClass('@container', 'min-w-0');
    expect(threeSlotCard).toHaveClass('@container', 'min-w-0');
    expect(fiveSlotWrapper).toHaveClass('min-w-[min(100%,20rem)]');
    expect(fiveSlotWrapper.style.flexBasis).toBe('39.125rem');
    expect(fiveSlotWrapper.style.flexGrow).toBe('5');
    expect(threeSlotWrapper).toHaveClass('min-w-[min(100%,20rem)]');
    expect(threeSlotWrapper.style.flexBasis).toBe('24.375rem');
    expect(threeSlotWrapper.style.flexGrow).toBe('3');
    expect(layout).toBe(threeSlotWrapper.parentElement);
    expect(layout).toHaveClass('flex', 'flex-wrap', 'items-start', 'justify-center');
    expect(Array.from(layout.querySelectorAll('h2'), (heading) => heading.textContent)).toEqual([
      'Five-slot Voron',
      'Three-slot printer',
    ]);
  });

  it('uses the shared slot count and keeps wrapped header actions aligned right', async () => {
    const slots = Array.from({ length: 4 }, (_, providerIndex) => ({
      ...physicalPrinter.material_systems[0].slots[0],
      id: 100 + providerIndex,
      provider_index: providerIndex,
      label: `AMS 1 · ${providerIndex + 1}`,
    }));
    physicalPrintersForQuery = [{
      ...physicalPrinter,
      name: 'Discovery Workshop B',
      material_systems: [{
        ...physicalPrinter.material_systems[0],
        provider: 'bambu',
        kind: 'mmu',
        slots,
      }],
    }];
    const { PresetSlotsPanel } = await import(
      '../components/presetSlots/PresetSlotsPanel'
    );

    render(<PresetSlotsPanel spools={[]} printerProfiles={[]} />);

    expect(screen.getByText('presetSlots.gates')).toBeInTheDocument();
    expect(screen.queryByText('presetSlots.bambu.slots')).not.toBeInTheDocument();
    expect(screen.getByTitle('presetSlots.collapseSystem').parentElement).toHaveClass(
      'flex-wrap',
      'justify-end',
      'justify-self-end',
    );
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

  it('keeps a one-slot manual printer collapsible through the same persisted state', async () => {
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

  it('allows normal native heartbeat jitter but still ages a silent connection', async () => {
    const { PresetSlotsPanel } = await import(
      '../components/presetSlots/PresetSlotsPanel'
    );
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-31T12:00:00Z'));
    physicalPrintersForQuery = [{
      ...physicalPrinter,
      last_seen_at: new Date(Date.now() - 144_000).toISOString(),
      material_systems: [{
        ...physicalPrinter.material_systems[0],
        provider: 'octoprint',
      }],
    }];
    try {
      const view = render(<PresetSlotsPanel spools={[]} printerProfiles={[]} />);
      expect(screen.getByText('deviceLink.active')).toBeInTheDocument();
      act(() => vi.advanceTimersByTime(60_000));
      expect(screen.getByText('deviceLink.delayed')).toBeInTheDocument();
      act(() => vi.advanceTimersByTime(120_000));
      expect(screen.getByText('deviceLink.inactive')).toBeInTheDocument();
      view.unmount();
    } finally {
      vi.useRealTimers();
    }
  });

  it('uses the freshest active material-system connector and treats multiple channels as normal', async () => {
    const { PresetSlotsPanel } = await import(
      '../components/presetSlots/PresetSlotsPanel'
    );
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-08T12:00:00Z'));
    physicalPrintersForQuery = [{
      ...physicalPrinter,
      last_seen_at: '2026-09-01T12:00:00Z',
      material_systems: [{
        ...physicalPrinter.material_systems[0],
        provider: 'octoprint',
      }],
      connectors: [
        {
          id: 1,
          material_system_id: 21,
          provider: 'octoprint',
          transport: 'orca_plugin_lan',
          capabilities: [],
          active: true,
          last_seen_at: '2026-09-01T12:00:00Z',
          topology_authority: false,
          last_topology_at: null,
        },
        {
          id: 2,
          material_system_id: 21,
          provider: 'octoprint',
          transport: 'edge_agent',
          capabilities: [],
          active: true,
          last_seen_at: '2026-09-08T11:59:30Z',
          topology_authority: true,
          last_topology_at: '2026-09-08T11:59:20Z',
        },
      ],
    }];
    try {
      const view = render(<PresetSlotsPanel spools={[]} printerProfiles={[]} />);
      expect(screen.getByText('deviceLink.active')).toBeInTheDocument();
      expect(screen.getByText(
        'presetSlots.connectionSources:presetSlots.connectionChannel.edge · presetSlots.connectionChannel.orca',
      )).toBeInTheDocument();
      expect(screen.getByText(
        'presetSlots.topologyAuthority:presetSlots.connectionChannel.edge',
      )).toBeInTheDocument();
      expect(screen.queryByText('presetSlots.sourceConflict.description')).not.toBeInTheDocument();
      view.unmount();
    } finally {
      vi.useRealTimers();
    }
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
      id: 71,
      physical_printer_id: 41,
      physical_printer_name: 'Voron 2.4 350',
      connection_ref: 'local-printer-41',
      preset_name: 'Workshop Voron 0.4',
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

    fireEvent.click(screen.getByText('printerSetup.title'));
    expect(screen.getByRole('button', { name: /Voron 2.4 350 — Workshop Voron 0.4/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Voron 2.4 350 — Office Voron 0.4 \/ Office Voron 0.6/ })).toBeInTheDocument();
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
    fireEvent.click(screen.getByText('printerSetup.title'));
    fireEvent.click(screen.getByRole('button', { name: /Manual Voron/ }));
    fireEvent.click(screen.getByText('printerSetup.feed.configure'));
    fireEvent.focus(screen.getByLabelText('printerSetup.feed.label'));
    fireEvent.click(screen.getByText('presetSlots.feedSystem.happy_hare'));
    fireEvent.click(screen.getByText('printerSetup.routes.native'));
    fireEvent.click(screen.getByText('printerSetup.connect'));
    await waitFor(() => {
      expect(setupConnection).toHaveBeenCalledWith(11, expect.objectContaining({
        material_system: expect.objectContaining({ provider: 'happy_hare' }),
      }));
    });
    expect(regenerateKey).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByText('printerSetup.issueKey'));
    await waitFor(() => expect(regenerateKey).toHaveBeenCalledWith(11));
    expect(screen.getByText(/fresh-printer-key/)).toBeInTheDocument();
    expect(screen.getByText('presetSlots.happyHare.linkHint')).toBeInTheDocument();
    expect(screen.getByText('presetSlots.newSystem.done')).toBeInTheDocument();
  });
});
