import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { WikiCategoryIcon, resolveWikiCategoryIcon } from './WikiCategoryIcon';

describe('WikiCategoryIcon', () => {
  it('keeps explicit custom icons available without importing the full Lucide namespace', () => {
    const { container } = render(<WikiCategoryIcon name="FilamentSpoolIcon" className="h-6 w-6" />);

    expect(container.querySelector('span')).toHaveClass('h-6', 'w-6');
  });

  it('maps legacy emoji category values and falls back safely for unknown names', () => {
    expect(resolveWikiCategoryIcon('🧵')).not.toBe(resolveWikiCategoryIcon(null));
    expect(resolveWikiCategoryIcon('UnknownFutureIcon')).toBe(resolveWikiCategoryIcon(null));
  });
});
