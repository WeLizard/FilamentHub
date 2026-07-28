import type { TFunction } from 'i18next';
import { describe, expect, it } from 'vitest';

import { buildQuoteDocumentHtml } from '../pages/CalculatorPage';

const LABELS: Record<string, string> = {
  'quoteMarket.ru.taxId': 'ИНН',
  'quoteMarket.ru.registrationId': 'ОГРН',
  'quoteMarket.ru.taxCode': 'КПП',
  'quoteMarket.intl.taxId': 'VAT number',
  'quoteMarket.intl.registrationId': 'Company registration number',
  'quoteMarket.cn.taxId': 'Unified social credit code',
  'quoteMarket.sellerAddress': 'Registered address',
  'quoteMarket.sellerBank': 'Bank details',
  'quoteMarket.netAmount': 'Net amount',
  'quoteMarket.taxLine': 'VAT',
  'quoteMarket.taxIncluded': 'Tax included in the total',
  'quoteMarket.ru.disclaimerNonBinding': 'Не является публичной офертой',
  'quoteMarket.intl.disclaimerNonBinding': 'Not a contract until signed',
  'quoteMarket.cn.disclaimerNonBinding': '仅供参考',
};

const t = ((key: string) => LABELS[key] ?? key) as unknown as TFunction;

const parties = (overrides: Record<string, unknown> = {}) =>
  ({
    sellerName: 'ООО «Ромашка»',
    sellerInn: '7701234567',
    sellerPhone: '+7 900 000-00-00',
    sellerRegistrationId: '1027700000000',
    sellerTaxCode: '770101001',
    sellerAddress: 'Москва, ул. Ленина, 1',
    sellerBankDetails: 'р/с 40702810000000000001',
    quoteMarket: '',
    paymentTerms: '',
    validityDays: 14,
    disclaimerMode: 'not_offer',
    currency: 'RUB',
    quoteNumberPrefix: '',
    buyerName: 'ООО «Заказчик»',
    buyerInn: '',
    buyerAddress: '',
    buyerEmail: '',
    buyerPhone: '',
    ...overrides,
  }) as unknown as Parameters<typeof buildQuoteDocumentHtml>[0]['parties'];

const render = (partyOverrides: Record<string, unknown>, taxRatePercent = 0) =>
  buildQuoteDocumentHtml({
    t,
    items: [
      {
        title: 'Печать корпуса',
        details: [],
        quantity: 1,
        unitPrice: 1200,
        totalPrice: 1200,
      } as unknown as Parameters<typeof buildQuoteDocumentHtml>[0]['items'][number],
    ],
    includedItems: [],
    grandTotal: 1200,
    parties: parties(partyOverrides),
    formatCurrency: (value) => `${Number(value ?? 0).toFixed(2)} ₽`,
    quoteNumber: '',
    taxRatePercent,
  });

describe('the quote document per market', () => {
  it('names the Russian details and keeps tax inside the price', () => {
    const html = render({ currency: 'RUB' }, 20);

    expect(html).toContain('ИНН');
    expect(html).toContain('ОГРН');
    expect(html).toContain('КПП');
    expect(html).toContain('Tax included in the total');
    expect(html).not.toContain('Net amount');
  });

  it('shows VAT as its own line abroad', () => {
    const html = render({ quoteMarket: 'intl', currency: 'EUR' }, 20);

    expect(html).toContain('VAT number');
    expect(html).toContain('Company registration number');
    expect(html).toContain('Net amount');
    expect(html).toContain('1000.00');
    expect(html).toContain('200.00');
    expect(html).not.toContain('КПП');
  });

  it('uses the single unified code in China', () => {
    const html = render({ quoteMarket: 'cn', currency: 'CNY' }, 13);

    expect(html).toContain('Unified social credit code');
    expect(html).not.toContain('Company registration number');
    expect(html).not.toContain('КПП');
    expect(html).toContain('Net amount');
  });

  it('does not invent a tax line when no rate is set', () => {
    const html = render({ quoteMarket: 'intl', currency: 'EUR' }, 0);

    expect(html).not.toContain('Net amount');
    expect(html).toContain('1200.00');
  });

  it('leaves out details a person has not filled in', () => {
    const html = render(
      { quoteMarket: 'intl', currency: 'EUR', sellerRegistrationId: '', sellerBankDetails: '' },
      0,
    );

    expect(html).not.toContain('Company registration number');
    expect(html).not.toContain('Bank details');
  });
});
