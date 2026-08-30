import { bambuAdapter } from './bambu';
import { directFeedAdapter } from './direct';
import { happyHareAdapter } from './happyHare';
import { octoprintAdapter } from './octoprint';
import type { FeedAdapter } from './types';
import type { Printer } from '../../../types/api';

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

export function supportsEdgeSetup(provider: string, kind?: string): boolean {
  const adapter = provider === 'legacy' ? directFeedAdapter
    : FEED_ADAPTERS.find((item) => item.id === provider);
  // An unknown provider's display fallback is not proof of transport support.
  return adapter?.supportsEdge === true && (!kind || !adapter.edgeKinds || adapter.edgeKinds.includes(kind));
}

export function setupAdaptersFor(model?: Printer, includeOther = false): FeedAdapter[] {
  const available = FEED_ADAPTERS.filter((adapter) => adapter.onboarding);
  const matching = model ? available.filter((adapter) => adapter.onboarding?.matchesModel?.(model)) : [];
  return matching.length && !includeOther ? matching : available;
}

export type { FeedAdapter, FeedAdapterLink } from './types';
