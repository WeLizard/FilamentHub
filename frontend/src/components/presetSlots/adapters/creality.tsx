import {
  configureCrealityBridgeInPlugin,
  requestCrealityObservationRefresh,
} from '../../../utils/pluginBridge';
import type { FeedAdapter } from './types';
import { LanBridgeSetup } from './LanBridgeSetup';
import type { LanBridgeRoute } from './LanBridgeSetup';

const CFS_SLOTS = 4;
const MAX_CFS_SLOTS = 16;
// The plugin reads the printer's address from its connection settings in
// OrcaSlicer; the stock firmware asks for nothing else.
const ROUTE: LanBridgeRoute = {
  provider: 'creality',
  capability: 'creality-lan-bridge',
  textKey: 'creality',
  // Looked up when used, like every other call into the plugin bridge.
  configure: (...args) => configureCrealityBridgeInPlugin(...args),
  refresh: (...args) => requestCrealityObservationRefresh(...args),
};

// Creality printers on stock firmware (K1 and K2 families, newer Ender-3): the
// printer lists the slots of its CFS with material, colour and what is left, and
// counts the filament a job has used. It names no spool and the plugin sends it
// nothing, so an assignment is saved on the site only.
export const crealityAdapter: FeedAdapter = {
  id: 'creality',
  onboarding: {
    connectionProviders: ['creality'],
    connectionLabelKey: 'printerSetup.connections.creality',
    connectionHintKey: 'printerSetup.connections.crealityHint',
    methods: ['orca'],
    matchesModel: (model) => /^creality$/i.test(model.manufacturer?.trim() ?? ''),
    topologies: [
      { id: 'cfs', labelKey: 'printerSetup.feed.crealityCfs', kind: 'mmu',
        count: { labelKey: 'printerSetup.feed.crealityCfsSlots', initial: CFS_SLOTS, max: MAX_CFS_SLOTS },
        slots: (count) => Array.from({ length: count }, (_, provider_index) => ({ provider_index, kind: 'slot' })),
        extras: [{ labelKey: 'printerSetup.feed.external', index: 255, kind: 'external', checked: true }] },
      { id: 'single', labelKey: 'printerSetup.feed.crealitySingle', kind: 'direct_feed',
        slots: () => [{ provider_index: 255, kind: 'external' }] },
    ],
  },
  labelKey: 'presetSlots.feedSystem.creality',
  fixedSlots: null,
  capabilities: ['read', 'presence', 'consumption'],
  orcaBridge: true,
  link: null,
  renderSetup: (context) => <LanBridgeSetup route={ROUTE} {...context} />,
};
