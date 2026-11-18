import type { FeedAdapter } from './types';

const STATION_SLOTS = 4;

// Creator 5 / 5 Pro material station read through the printer's LAN API.
// The printer reports loaded filament per slot but no per-tool usage, active
// tool or spool identity, so this path claims read and presence only.
export const flashforgeAdapter: FeedAdapter = {
  id: 'flashforge',
  onboarding: {
    connectionProviders: ['flashforge'],
    connectionLabelKey: 'printerSetup.connections.flashforge',
    connectionHintKey: 'printerSetup.connections.flashforgeHint',
    methods: ['edge'],
    matchesModel: (model) => /^flash\s*forge$/i.test(model.manufacturer?.trim() ?? ''),
    topologies: [{ id: 'station', labelKey: 'printerSetup.feed.flashforgeStation', kind: 'mmu',
      slots: () => Array.from({ length: STATION_SLOTS }, (_, provider_index) => ({ provider_index, kind: 'slot' })) }],
  },
  labelKey: 'presetSlots.feedSystem.flashforge',
  fixedSlots: STATION_SLOTS,
  capabilities: ['read', 'presence'],
  supportsEdge: true,
  edgeKinds: ['mmu'],
  link: null,
};
