import { describe, expect, it } from 'vitest';

import { defaultCurrencyForCountry, defaultCurrencyForLanguage, splitTotalPrice } from './currency';

describe('defaultCurrencyForCountry', () => {
  it('lets the market decide, not the interface language', () => {
    // Русскоязычный человек в Германии платит в евро: язык не является
    // юрисдикцией, и подставлять ему рубли неверно.
    expect(defaultCurrencyForCountry('DE', 'ru')).toBe('EUR');
    expect(defaultCurrencyForCountry('RU', 'en')).toBe('RUB');
  });

  it('falls back to the language only while the country is unknown', () => {
    expect(defaultCurrencyForCountry(null, 'ru')).toBe(defaultCurrencyForLanguage('ru'));
    expect(defaultCurrencyForCountry(undefined, 'zh')).toBe('CNY');
  });

  it('keeps an unfamiliar country from silently borrowing the language currency', () => {
    // Страна вне списка — это незнание, а не повод выдать рубли за местные
    // деньги; язык здесь остаётся единственной догадкой, и она честно видна.
    expect(defaultCurrencyForCountry('BR', 'en')).toBe('USD');
  });
});

describe('splitTotalPrice', () => {
  it('gives the leftover minor units to the first spools', () => {
    expect(splitTotalPrice(100, 3, 'RUB')).toEqual([
      { amount: 33.34, count: 1 },
      { amount: 33.33, count: 2 },
    ]);
  });

  it('splits yen in whole units', () => {
    expect(splitTotalPrice(1000, 3, 'JPY')).toEqual([
      { amount: 334, count: 1 },
      { amount: 333, count: 2 },
    ]);
  });

  it('keeps an even split as one share and zero as zero', () => {
    expect(splitTotalPrice(90, 3, 'USD')).toEqual([{ amount: 30, count: 3 }]);
    expect(splitTotalPrice(0, 4, 'EUR')).toEqual([{ amount: 0, count: 4 }]);
  });
});
