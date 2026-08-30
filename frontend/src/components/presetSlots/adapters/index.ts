import { bambuAdapter } from './bambu';
import { directFeedAdapter } from './direct';
import { happyHareAdapter } from './happyHare';
import { octoprintAdapter } from './octoprint';
import type { FeedAdapter } from './types';

// A new feed system joins by adding its file here; nothing in the panel changes.
export const FEED_ADAPTERS: FeedAdapter[] = [
  directFeedAdapter,
  bambuAdapter,
  happyHareAdapter,
  octoprintAdapter,
];

export function feedAdapterFor(provider: string): FeedAdapter {
  return FEED_ADAPTERS.find((adapter) => adapter.id === provider) ?? directFeedAdapter;
}

export function supportsEdgeSetup(provider: string): boolean {
  const adapter = provider === 'legacy' ? directFeedAdapter
    : FEED_ADAPTERS.find((item) => item.id === provider);
  // An unknown provider's display fallback is not proof of transport support.
  return adapter?.supportsEdge === true;
}

export type { FeedAdapter, FeedAdapterLink } from './types';
