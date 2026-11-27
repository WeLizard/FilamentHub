import {
  configureFlashforgeBridgeInPlugin,
  isPluginEmbed,
  requestFlashforgeObservationRefresh,
  requestFlashforgeSlotAssignment,
} from '../../../utils/pluginBridge';
import type { FeedAdapter } from './types';
import { LanBridgeSetup } from './LanBridgeSetup';
import type { LanBridgeRoute } from './LanBridgeSetup';

const STATION_SLOTS = 4;
// The plugin reads the printer's address and check code from its connection
// settings in OrcaSlicer and its serial number from the printer on the network.
// Only a check code the profile lacks, or one the printer refused, is asked for
// here. FH Edge is the route for watching without OrcaSlicer.
const ROUTE: LanBridgeRoute = {
  provider: 'flashforge',
  capability: 'flashforge-lan-bridge',
  textKey: 'flashforge',
  // Looked up when used, like every other call into the plugin bridge.
  configure: (...args) => configureFlashforgeBridgeInPlugin(...args),
  refresh: (...args) => requestFlashforgeObservationRefresh(...args),
  secret: {
    outcomes: new Set(['check_code', 'auth']),
    maxLength: 64,
    configure: (...args) => configureFlashforgeBridgeInPlugin(...args),
  },
};

// Flashforge printers on the LAN API (port 8898): the AD5X and Creator 5 /
// 5 Pro report a four-slot material station, the Adventurer 5M / 5M Pro one
// spool with the material set on the printer. There is no spool identity and
// no measured usage: whoever watches the print (Edge always, the plugin while
// OrcaSlicer is open) counts the slicer's estimate for the job.
export const flashforgeAdapter: FeedAdapter = {
  id: 'flashforge',
  onboarding: {
    connectionProviders: ['flashforge'],
    connectionLabelKey: 'printerSetup.connections.flashforge',
    connectionHintKey: 'printerSetup.connections.flashforgeHint',
    methods: ['orca', 'edge'],
    matchesModel: (model) => /^flash\s*forge$/i.test(model.manufacturer?.trim() ?? ''),
    topologies: [
      { id: 'station', labelKey: 'printerSetup.feed.flashforgeStation', kind: 'mmu',
        slots: () => Array.from({ length: STATION_SLOTS }, (_, provider_index) => ({ provider_index, kind: 'slot' })) },
      { id: 'single', labelKey: 'printerSetup.feed.flashforgeSingle', kind: 'direct_feed',
        slots: () => [{ provider_index: 0, kind: 'external' }] },
    ],
  },
  labelKey: 'presetSlots.feedSystem.flashforge',
  fixedSlots: null,
  capabilities: ['read', 'presence'],
  supportsEdge: true,
  edgeKinds: ['mmu', 'direct_feed'],
  orcaBridge: true,
  link: null,
  // A station slot can be told the material and colour of the spool assigned
  // to it. Only the plugin does that, so only inside OrcaSlicer and only for
  // a printer linked through it; elsewhere the assignment is simply saved.
  deliverAssignment: async ({ printer, system, slot }) => {
    const linked = (printer.connectors ?? []).some(
      (item) => item.provider === 'flashforge'
        && item.transport === 'orca_plugin_lan'
        && item.material_system_id === system.id
        && item.active,
    );
    if (system.kind !== 'mmu' || !linked || !isPluginEmbed()) return null;
    const result = await requestFlashforgeSlotAssignment(printer.id, system.id, {
      materialSlotId: slot.id,
      providerIndex: slot.provider_index,
      assignmentRevision: slot.assignment_revision,
      desired: slot.assignment ? {
        presetId: slot.assignment.preset_id,
        spoolId: slot.assignment.spool_id,
        sourceTs: slot.assignment.source_ts,
      } : null,
    });
    if (result.ok) return { status: 'delivered' };
    if (result.code === 'physical_clear_unsupported') {
      return { status: 'unsupported', code: result.code };
    }
    // The slot was set; only the report of it did not reach the site.
    return { status: 'saved_only', code: result.code, physicallyApplied: result.code === 'snapshot_failed' };
  },
  renderSetup: (context) => <LanBridgeSetup route={ROUTE} {...context} />,
};
