import type { SpoolFeedParams, SpoolFeedResponse, UserSpool } from '../api/client';

export const spoolQueryKeys = {
  root: ['user-spools'] as const,
  legacy: (userId: number | undefined) => [...spoolQueryKeys.root, 'legacy', userId] as const,
  feed: (userId: number | null | undefined, params: Omit<SpoolFeedParams, 'cursor'>) =>
    [...spoolQueryKeys.root, 'feed', userId, params] as const,
  detail: (userId: number | null | undefined, spoolId: number) =>
    [...spoolQueryKeys.root, 'detail', userId, spoolId] as const,
};

export function mergeSpoolFeedPages(pages: SpoolFeedResponse[] | undefined): UserSpool[] {
  const byId = new Map<number, UserSpool>();
  for (const page of pages ?? []) {
    for (const spool of page.items) byId.set(spool.id, spool);
  }
  return [...byId.values()];
}
