import { describe, expect, it } from 'vitest';

import { quoteMarketRules, resolveQuoteMarket } from '../utils/quoteMarket';

describe('which market a quote follows', () => {
  it('follows the currency when nothing was chosen', () => {
    expect(resolveQuoteMarket('', 'RUB')).toBe('ru');
    expect(resolveQuoteMarket('', 'KZT')).toBe('ru');
    expect(resolveQuoteMarket('', 'CNY')).toBe('cn');
    expect(resolveQuoteMarket('', 'EUR')).toBe('intl');
    expect(resolveQuoteMarket('', 'USD')).toBe('intl');
  });

  it('lets a person overrule the currency', () => {
    expect(resolveQuoteMarket('intl', 'RUB')).toBe('intl');
    expect(resolveQuoteMarket('ru', 'EUR')).toBe('ru');
  });

  it('falls back to the international layout on nonsense', () => {
    expect(resolveQuoteMarket(null, null)).toBe('intl');
    expect(resolveQuoteMarket('mars', 'XYZ')).toBe('intl');
  });
});

describe('what each market shows', () => {
  it('asks for the details Russia expects', () => {
    const rules = quoteMarketRules('ru');

    expect(rules.showTaxCode).toBe(true);
    expect(rules.registrationIdKey).toBeTruthy();
    expect(rules.showTaxLine).toBe(false);
    expect(rules.numberPrefix).toBe('КП');
  });

  it('asks for a registration number and shows tax separately abroad', () => {
    const rules = quoteMarketRules('intl');

    expect(rules.showTaxCode).toBe(false);
    expect(rules.registrationIdKey).toBeTruthy();
    expect(rules.showTaxLine).toBe(true);
  });

  it('uses the one unified code in China', () => {
    const rules = quoteMarketRules('cn');

    expect(rules.registrationIdKey).toBeNull();
    expect(rules.showTaxCode).toBe(false);
    expect(rules.showTaxLine).toBe(true);
  });
});

describe('splitting a gross total into net and tax', () => {
  const split = (gross: number, ratePercent: number) => {
    const tax = gross - gross / (1 + ratePercent / 100);
    return { net: gross - tax, tax };
  };

  it('adds back up to what the customer pays', () => {
    const { net, tax } = split(1200, 20);

    expect(net + tax).toBeCloseTo(1200, 6);
    expect(net).toBeCloseTo(1000, 6);
    expect(tax).toBeCloseTo(200, 6);
  });

  it('handles a rate that is not a round number', () => {
    const { net, tax } = split(1130, 13);

    expect(net + tax).toBeCloseTo(1130, 6);
    expect(net).toBeCloseTo(1000, 6);
  });

  it('leaves the total alone when there is no tax', () => {
    const { net, tax } = split(500, 0);

    expect(net).toBe(500);
    expect(tax).toBe(0);
  });
});
