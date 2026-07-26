import { directFeedAdapter } from './direct';
import { happyHareAdapter } from './happyHare';
import type { FeedAdapter } from './types';

// A new feed system joins by adding its file here; nothing in the panel changes.
export const FEED_ADAPTERS: FeedAdapter[] = [directFeedAdapter, happyHareAdapter];

export function feedAdapterFor(provider: string): FeedAdapter {
  return FEED_ADAPTERS.find((adapter) => adapter.id === provider) ?? directFeedAdapter;
}

export type { FeedAdapter } from './types';
