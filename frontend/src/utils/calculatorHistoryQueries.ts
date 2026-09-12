export const calculatorHistoryKeys = {
  all: ['calculator-pro', 'history'] as const,
  feed: (size: number) => ['calculator-pro', 'history', 'feed', size] as const,
  summary: ['calculator-pro', 'history', 'summary'] as const,
  selectable: (size: number) => ['calculator-pro', 'history', 'selectable', size] as const,
  detail: (entryId: number) => ['calculator-pro', 'history', 'detail', entryId] as const,
};

export const shouldShowInitialHistoryError = (
  error: unknown,
  pages: readonly { items: readonly unknown[] }[] | undefined,
) => Boolean(error) && !pages?.some((page) => page.items.length > 0);
