import {
  configureProfileLanBridgeInPlugin,
  requestProfileLanObservationRefresh,
} from '../../../utils/pluginBridge';
import type { FeedAdapter } from './types';
import { LanBridgeSetup } from './LanBridgeSetup';
import type { LanBridgeRoute } from './LanBridgeSetup';

const ACE_SLOTS = 4;
const MAX_ACE_SLOTS = 16;
// The plugin reads the printer's address from its connection settings in
// OrcaSlicer and asks the printer itself for the rest in LAN mode.
const ROUTE: LanBridgeRoute = {
  provider: 'anycubic',
  capability: 'anycubic-lan-bridge',
  textKey: 'anycubic',
  // Looked up when used, like every other call into the plugin bridge.
  configure: (...args) => configureProfileLanBridgeInPlugin('anycubic', ...args),
  refresh: (...args) => requestProfileLanObservationRefresh('anycubic', ...args),
};

// Anycubic Kobra 3, S1 and X in LAN mode, read by the plugin while OrcaSlicer
// is open or by FH Edge: the printer reports the job and the slots of its ACE
// units with material, colour and what is left. It names no spool, and
// neither reader sends it anything or counts usage yet, so an assignment is
// saved on the site only.
export const anycubicAdapter: FeedAdapter = {
  id: 'anycubic',
  onboarding: {
    connectionProviders: ['anycubic'],
    connectionLabelKey: 'printerSetup.connections.anycubic',
    connectionHintKey: 'printerSetup.connections.anycubicHint',
    methods: ['orca', 'edge'],
    matchesModel: (model) => /^anycubic$/i.test(model.manufacturer?.trim() ?? ''),
    topologies: [
      { id: 'ace', labelKey: 'printerSetup.feed.anycubicAce', kind: 'mmu',
        count: { labelKey: 'printerSetup.feed.anycubicAceSlots', initial: ACE_SLOTS, max: MAX_ACE_SLOTS },
        slots: (count) => Array.from({ length: count }, (_, provider_index) => ({ provider_index, kind: 'slot' })),
        extras: [{ labelKey: 'printerSetup.feed.external', index: 255, kind: 'external', checked: true }] },
      { id: 'single', labelKey: 'printerSetup.feed.anycubicSingle', kind: 'direct_feed',
        slots: () => [{ provider_index: 255, kind: 'external' }] },
    ],
  },
  labelKey: 'presetSlots.feedSystem.anycubic',
  fixedSlots: null,
  capabilities: ['read', 'presence'],
  supportsEdge: true,
  edgeKinds: ['mmu', 'direct_feed'],
  orcaBridge: true,
  link: null,
  renderSetup: (context) => <LanBridgeSetup route={ROUTE} {...context} />,
};
