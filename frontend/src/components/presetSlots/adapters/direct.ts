import type { FeedAdapter } from './types';
import { ordinaryTopologies } from './topology';

export const directFeedAdapter: FeedAdapter = {
  id: 'manual',
  onboarding: {
    connectionLabelKey: 'printerSetup.connections.moonraker',
    connectionHintKey: 'printerSetup.connections.moonrakerHint',
    methods: ['orca', 'edge'],
    orcaProbe: true,
    topologies: ordinaryTopologies,
  },
  labelKey: 'presetSlots.feedSystem.direct',
  fixedSlots: 1,
  capabilities: [],
  supportsEdge: true,
  edgeKinds: ['direct_feed'],
  link: null,
};
