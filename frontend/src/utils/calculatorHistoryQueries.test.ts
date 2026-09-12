import { describe, expect, it } from 'vitest';

import { calculatorHistoryKeys } from './calculatorHistoryQueries';

describe('calculator history query keys', () => {
  it('keeps feed, summary, and selectable cache shapes separate under one invalidation prefix', () => {
    expect(calculatorHistoryKeys.feed(20)).not.toEqual(calculatorHistoryKeys.summary);
    expect(calculatorHistoryKeys.feed(20)).not.toEqual(calculatorHistoryKeys.selectable(50));
    expect(calculatorHistoryKeys.summary.slice(0, 2)).toEqual(calculatorHistoryKeys.all);
    expect(calculatorHistoryKeys.selectable(50).slice(0, 2)).toEqual(calculatorHistoryKeys.all);
  });
});
