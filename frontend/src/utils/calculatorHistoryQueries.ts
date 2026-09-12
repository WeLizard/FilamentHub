export const calculatorHistoryKeys = {
  all: ['calculator-pro', 'history'] as const,
  feed: (size: number) => ['calculator-pro', 'history', 'feed', size] as const,
  summary: ['calculator-pro', 'history', 'summary'] as const,
  selectable: (size: number) => ['calculator-pro', 'history', 'selectable', size] as const,
};
