import type { FeedAdapter } from './types';

const STATION_SLOTS = 4;

// Flashforge printers on the LAN API (port 8898): the AD5X and Creator 5 /
// 5 Pro report a four-slot material station, the Adventurer 5M / 5M Pro one
// spool with the material set on the printer. There is no per-tool usage,
// active tool or spool identity, so this path claims read and presence only.
export const flashforgeAdapter: FeedAdapter = {
  id: 'flashforge',
  onboarding: {
    connectionProviders: ['flashforge'],
    connectionLabelKey: 'printerSetup.connections.flashforge',
    connectionHintKey: 'printerSetup.connections.flashforgeHint',
    methods: ['edge'],
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
  link: null,
};
