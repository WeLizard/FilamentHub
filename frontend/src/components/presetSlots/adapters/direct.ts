import { createElement } from 'react';
import { EdgeConnectionSetup } from '../EdgeConnectionSetup';
import type { FeedAdapter } from './types';

export const directFeedAdapter: FeedAdapter = {
  id: 'manual',
  labelKey: 'presetSlots.feedSystem.direct',
  fixedSlots: 1,
  capabilities: [],
  supportsEdge: true,
  link: null,
  renderSetup: (context) => ['manual', 'legacy'].includes(context.system.provider)
    ? createElement(EdgeConnectionSetup, { ...context, collapsible: true })
    : null,
};
