import { QueryClient } from '@tanstack/react-query';
import { describe, expect, it } from 'vitest';

import type { PhysicalPrinter, PhysicalPrinterFeedResponse } from '../api/client';
import {
  mergePhysicalPrinterPages,
  physicalPrinterQueryKeys,
} from './physicalPrinterQueries';

const printer = (id: number) => ({ id, name: `Printer ${id}` }) as PhysicalPrinter;

describe('physical printer query shapes', () => {
  it('merges pages by physical-printer id and preserves page order', () => {
    const page = (
      items: PhysicalPrinter[],
      next_cursor: string | null,
    ): PhysicalPrinterFeedResponse => ({
      items,
      next_cursor,
      has_more: next_cursor !== null,
      total: 3,
    });
    expect(mergePhysicalPrinterPages({
      pages: [page([printer(1), printer(2)], 'next'), page([printer(2), printer(3)], null)],
      pageParams: [undefined, 'next'],
    }).map((item) => item.id)).toEqual([1, 2, 3]);
  });

  it('keeps cache shapes distinct and invalidates all of them by root prefix', async () => {
    const client = new QueryClient();
    const keys = [
      physicalPrinterQueryKeys.legacyAll,
      physicalPrinterQueryKeys.feed(7, 12),
      physicalPrinterQueryKeys.lookup(7, 41),
      physicalPrinterQueryKeys.topology,
    ];
    keys.forEach((key, index) => client.setQueryData(key, index));

    expect(new Set(keys.map((key) => JSON.stringify(key))).size).toBe(keys.length);
    await client.invalidateQueries({
      queryKey: physicalPrinterQueryKeys.root,
      refetchType: 'none',
    });
    for (const key of keys) expect(client.getQueryState(key)?.isInvalidated).toBe(true);
  });
});
