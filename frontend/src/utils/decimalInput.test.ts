import { describe, expect, it } from 'vitest';

import { formatDecimalInput, parseDecimalInput } from './decimalInput';

describe('decimalInput', () => {
  it('shows calculated values with at most one decimal place', () => {
    expect(formatDecimalInput(668.188399943851)).toBe('668.2');
    expect(formatDecimalInput(1000)).toBe('1000');
  });

  it('accepts both decimal separators without truncating the fraction', () => {
    expect(parseDecimalInput('653,4')).toBe(653.4);
    expect(parseDecimalInput('653.4')).toBe(653.4);
  });

  it('rejects ambiguous or incomplete values', () => {
    expect(parseDecimalInput('653,4.2')).toBeNaN();
    expect(parseDecimalInput('')).toBeNaN();
  });
});
