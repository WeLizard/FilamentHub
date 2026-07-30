import { describe, expect, it } from 'vitest';
import { formatRalCode, normalizeRalCode } from './ralCode';

describe('RAL Classic code helpers', () => {
  it.each([
    ['3020', '3020'],
    ['RAL 3020', '3020'],
    ['ral-3020', '3020'],
    [' RAL_3020 ', '3020'],
    ['', ''],
  ])('normalizes %s', (source, expected) => {
    expect(normalizeRalCode(source)).toBe(expected);
  });

  it('formats a normalized code without duplicating the prefix', () => {
    expect(formatRalCode('RAL 3020')).toBe('RAL 3020');
  });
});
