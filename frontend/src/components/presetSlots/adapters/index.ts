import { bambuAdapter } from './bambu';
import { directFeedAdapter } from './direct';
import { happyHareAdapter } from './happyHare';
import { octoprintAdapter } from './octoprint';
import type { FeedAdapter, FeedTopologyChoice } from './types';
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
  const available = FEED_ADAPTERS.filter((adapter) => adapter.onboarding && !adapter.onboarding.connectionProvider);
  const matching = model ? available.filter((adapter) => adapter.onboarding?.matchesModel?.(model)) : [];
  return matching.length && !includeOther ? matching : available;
}

export function connectionAdapterFor(provider: string): FeedAdapter {
  const adapter = feedAdapterFor(provider);
  return feedAdapterFor(adapter.onboarding?.connectionProvider ?? adapter.id);
}

export function adapterForConnection(provider: string | null): FeedAdapter | undefined {
  return FEED_ADAPTERS.find((adapter) => provider && adapter.onboarding?.connectionProviders?.includes(provider));
}

export function setupTopologiesFor(provider: string, includeRelated = true): FeedTopologyChoice[] {
  const adapter = feedAdapterFor(provider);
  const connection = connectionAdapterFor(provider);
  const adapters = includeRelated
    ? FEED_ADAPTERS.filter((item) => connectionAdapterFor(item.id).id === connection.id)
    : [adapter];
  return adapters.flatMap((item) => (item.onboarding?.topologies ?? []).map((choice) => ({
    ...choice, id: `${item.id}:${choice.id}`, provider: item.id,
  })));
}

export type { FeedAdapter, FeedAdapterLink } from './types';
