import type { FeedAdapter } from './types';

export const directFeedAdapter: FeedAdapter = {
  id: 'manual',
  labelKey: 'presetSlots.feedSystem.direct',
  fixedSlots: 1,
  needsLink: false,
};
