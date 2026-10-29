import type { SpoolFeedParams, SpoolFeedResponse, SpoolGroupsParams, UserSpool } from '../api/client';

export const spoolQueryKeys = {
  root: ['user-spools'] as const,
  legacy: (userId: number | undefined) => [...spoolQueryKeys.root, 'legacy', userId] as const,
  feed: (userId: number | null | undefined, params: Omit<SpoolFeedParams, 'cursor'>) =>
    [...spoolQueryKeys.root, 'feed', userId, params] as const,
  detail: (userId: number | null | undefined, spoolId: number) =>
    [...spoolQueryKeys.root, 'detail', userId, spoolId] as const,
  groups: (userId: number | null | undefined, params: Omit<SpoolGroupsParams, 'cursor'>) =>
    [...spoolQueryKeys.root, 'groups', userId, params] as const,
  collections: (userId: number | null | undefined) =>
    [...spoolQueryKeys.root, 'collections', userId] as const,
};

export const stockAlertQueryKeys = {
  rules: (userId: number | null | undefined) => ['stock-alert-rules', userId] as const,
};

export function mergeSpoolFeedPages(pages: SpoolFeedResponse[] | undefined): UserSpool[] {
  const byId = new Map<number, UserSpool>();
  for (const page of pages ?? []) {
    for (const spool of page.items) byId.set(spool.id, spool);
  }
  return [...byId.values()];
}
