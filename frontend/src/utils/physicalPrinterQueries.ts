import type { InfiniteData } from '@tanstack/react-query';

import type { PhysicalPrinter, PhysicalPrinterFeedResponse } from '../api/client';

export const physicalPrinterQueryKeys = {
  root: ['physical-printers'] as const,
  legacyAll: ['physical-printers', 'legacy-all'] as const,
  feed: (userId: number | null | undefined, size: number) =>
    ['physical-printers', 'feed', userId, { size }] as const,
  lookup: (userId: number | null | undefined, printerId: number) =>
    ['physical-printers', 'lookup', userId, printerId] as const,
  topology: ['physical-printers', 'topology'] as const,
};

export function mergePhysicalPrinterPages(
  data: InfiniteData<PhysicalPrinterFeedResponse, unknown> | undefined,
): PhysicalPrinter[] {
  const byId = new Map<number, PhysicalPrinter>();
  for (const page of data?.pages ?? []) {
    for (const printer of page.items) byId.set(printer.id, printer);
  }
  return [...byId.values()];
}
