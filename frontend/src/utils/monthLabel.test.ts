import { describe, expect, it } from 'vitest';

import { formatMonthLabel } from './monthLabel';

describe('formatMonthLabel', () => {
  it('names the month in the interface language', () => {
    expect(formatMonthLabel('2026-07', 'en')).toBe('July 2026');
    expect(formatMonthLabel('2026-07', 'ru')).toMatch(/июль 2026/);
  });

  it('leaves an unexpected value as it came', () => {
    expect(formatMonthLabel('soon', 'en')).toBe('soon');
  });
});
