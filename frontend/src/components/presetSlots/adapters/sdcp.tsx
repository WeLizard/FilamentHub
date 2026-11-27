import {
  configureProfileLanBridgeInPlugin,
  requestProfileLanObservationRefresh,
} from '../../../utils/pluginBridge';
import { CANVAS_TOPOLOGIES, centauriGeneration } from './canvas';
import type { FeedAdapter } from './types';
import { LanBridgeSetup } from './LanBridgeSetup';
import type { LanBridgeRoute } from './LanBridgeSetup';

// The plugin reads the printer's address from its connection settings in OrcaSlicer.
const ROUTE: LanBridgeRoute = {
  provider: 'sdcp',
  capability: 'sdcp-lan-bridge',
  textKey: 'sdcp',
  // Looked up when used, like every other call into the plugin bridge.
  configure: (...args) => configureProfileLanBridgeInPlugin('sdcp', ...args),
  refresh: (...args) => requestProfileLanObservationRefresh('sdcp', ...args),
};

// Printers on the open SDCP protocol; the Elegoo Centauri Carbon is the one
// known so far, and any other brand that speaks it connects the same way. The
// printer tells the print state and, with CANVAS on firmware 1.2 or later, its
// slots with material and colour. It counts no filament used and names no
// spool, and nothing is sent to it, so an assignment is saved on the site
// only, whether the plugin or FH Edge reads it. Elegoo's Klipper printers
// (Neptune 4) connect through Moonraker.
export const sdcpAdapter: FeedAdapter = {
  id: 'sdcp',
  onboarding: {
    connectionProviders: ['sdcp'],
    connectionLabelKey: 'printerSetup.connections.sdcp',
    connectionHintKey: 'printerSetup.connections.sdcpHint',
    methods: ['orca', 'edge'],
    matchesModel: (model) => centauriGeneration(model) === 1,
    topologies: CANVAS_TOPOLOGIES,
  },
  labelKey: 'presetSlots.feedSystem.sdcp',
  fixedSlots: null,
  capabilities: ['read', 'presence'],
  supportsEdge: true,
  edgeKinds: ['mmu', 'direct_feed'],
  orcaBridge: true,
  link: null,
  renderSetup: (context) => <LanBridgeSetup route={ROUTE} {...context} />,
};
