import {
  configurePrusaLinkBridgeInPlugin,
  requestPrusaLinkObservationRefresh,
} from '../../../utils/pluginBridge';
import type { FeedAdapter } from './types';
import { LanBridgeSetup } from './LanBridgeSetup';
import type { LanBridgeRoute } from './LanBridgeSetup';

const MMU3_SLOTS = 5;
const XL_TOOLS = 5;
const MAX_TOOLS = 16;
// The plugin reads the printer's address and login (API key or user name and
// password) from its connection settings in OrcaSlicer.
const ROUTE: LanBridgeRoute = {
  provider: 'prusalink',
  capability: 'prusalink-lan-bridge',
  textKey: 'prusalink',
  // Looked up when used, like every other call into the plugin bridge.
  configure: (...args) => configurePrusaLinkBridgeInPlugin(...args),
  refresh: (...args) => requestPrusaLinkObservationRefresh(...args),
};

// Prusa printers over PrusaLink, the local API of the Buddy firmware (MK4/MK4S,
// MK3.5/3.9, XL, CORE One, MINI) and of Prusa-Link on a Raspberry Pi (MK3S). It
// reports the print state and, on a single-nozzle printer without an MMU, the
// material loaded. MMU3 slots and XL tools are not in the local API, so they are
// described here and assigned on the site only. The printer counts no filament.
export const prusaLinkAdapter: FeedAdapter = {
  id: 'prusalink',
  onboarding: {
    connectionProviders: ['prusalink'],
    connectionLabelKey: 'printerSetup.connections.prusalink',
    connectionHintKey: 'printerSetup.connections.prusalinkHint',
    methods: ['orca'],
    matchesModel: (model) => /^prusa(\s+research)?$/i.test(model.manufacturer?.trim() ?? ''),
    topologies: [
      { id: 'single', labelKey: 'printerSetup.feed.prusalinkSingle', kind: 'direct_feed',
        slots: () => [{ provider_index: 0, kind: 'external' }] },
      { id: 'mmu3', labelKey: 'printerSetup.feed.prusalinkMmu', kind: 'mmu',
        slots: () => Array.from({ length: MMU3_SLOTS }, (_, provider_index) => ({ provider_index, kind: 'slot' })) },
      { id: 'tools', labelKey: 'printerSetup.feed.prusalinkTools', kind: 'multi_tool',
        count: { labelKey: 'printerSetup.feed.toolCount', initial: XL_TOOLS, max: MAX_TOOLS },
        slots: (count) => Array.from({ length: count }, (_, provider_index) => ({ provider_index, kind: 'tool' })) },
    ],
  },
  labelKey: 'presetSlots.feedSystem.prusalink',
  fixedSlots: null,
  capabilities: ['read', 'presence'],
  orcaBridge: true,
  link: null,
  renderSetup: (context) => <LanBridgeSetup route={ROUTE} {...context} />,
};
