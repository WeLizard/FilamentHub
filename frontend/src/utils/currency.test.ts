import { describe, expect, it } from 'vitest';

import { defaultCurrencyForCountry, defaultCurrencyForLanguage } from './currency';

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
