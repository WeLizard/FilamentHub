import { describe, expect, it } from 'vitest';
import { QueryClient } from '@tanstack/react-query';

import { calculatorHistoryKeys } from './calculatorHistoryQueries';

describe('calculator history query keys', () => {
  it('keeps feed, summary, and selectable cache shapes separate under one invalidation prefix', () => {
    expect(calculatorHistoryKeys.feed(20)).not.toEqual(calculatorHistoryKeys.summary);
    expect(calculatorHistoryKeys.feed(20)).not.toEqual(calculatorHistoryKeys.selectable(50));
    expect(calculatorHistoryKeys.summary.slice(0, 2)).toEqual(calculatorHistoryKeys.all);
    expect(calculatorHistoryKeys.selectable(50).slice(0, 2)).toEqual(calculatorHistoryKeys.all);
  });

  it('invalidates every calculator history shape through the shared prefix', async () => {
    const queryClient = new QueryClient();
    const historyKeys = [
      calculatorHistoryKeys.feed(20),
      calculatorHistoryKeys.summary,
      calculatorHistoryKeys.selectable(50),
    ];
    historyKeys.forEach((queryKey) => queryClient.setQueryData(queryKey, { value: queryKey }));
    queryClient.setQueryData(['unrelated'], { value: 'kept' });

    await queryClient.invalidateQueries({ queryKey: calculatorHistoryKeys.all });

    historyKeys.forEach((queryKey) => {
      expect(queryClient.getQueryState(queryKey)?.isInvalidated).toBe(true);
    });
    expect(queryClient.getQueryState(['unrelated'])?.isInvalidated).toBe(false);
  });
});
