import type { TFunction } from 'i18next';
import { describe, expect, it } from 'vitest';

import en from '../locales/en/translation.json';
import ru from '../locales/ru/translation.json';
import zh from '../locales/zh/translation.json';
import { buildQuoteDocumentHtml } from '../pages/CalculatorPage';

const translations = { ru, en, zh };
type Language = keyof typeof translations;

const translator = (language: Language): TFunction => ((key: string, options?: Record<string, unknown>) => {
  const value = key.split('.').reduce<unknown>((current, segment) => {
    if (!current || typeof current !== 'object') return undefined;
    return (current as Record<string, unknown>)[segment];
  }, translations[language]);
  return typeof value === 'string'
    ? value.replace('{{taxLabel}}', typeof options?.taxLabel === 'string' ? options.taxLabel : '')
    : key;
}) as unknown as TFunction;

const parties = (overrides: Record<string, unknown> = {}) =>
  ({
    sellerName: 'Print studio',
    sellerInn: '7701234567',
    sellerPhone: '+7 900 000-00-00',
    sellerRegistrationId: '1027700000000',
    sellerTaxCode: '770101001',
    sellerAddress: 'Moscow',
    sellerBankDetails: 'Account 123',
    quoteMarket: '',
    paymentTerms: '',
    validityDays: 14,
    disclaimerMode: 'offer',
    currency: 'RUB',
    quoteNumberPrefix: '',
    buyerName: 'Customer',
    buyerInn: '7702223333',
    buyerAddress: '',
    buyerEmail: '',
    buyerPhone: '',
    ...overrides,
  }) as unknown as Parameters<typeof buildQuoteDocumentHtml>[0]['parties'];

const render = (
  language: Language,
  partyOverrides: Record<string, unknown> = {},
  taxRatePercent = 0,
  taxDisclosure?: { kind: 'tax' | 'vat'; mode: 'included' | 'separate'; amount: number; netAmount: number } | null,
) => buildQuoteDocumentHtml({
  t: translator(language),
  language,
  items: [{
    title: 'Print enclosure',
    details: [],
    quantity: 1,
    unitPrice: 1200,
    totalPrice: 1200,
  } as unknown as Parameters<typeof buildQuoteDocumentHtml>[0]['items'][number]],
  includedItems: [],
  grandTotal: 1200,
  parties: parties(partyOverrides),
  formatCurrency: (value) => `${Number(value ?? 0).toFixed(2)}`,
  quoteNumber: '',
  taxRatePercent,
  taxDisclosure,
});

describe('new quote documents', () => {
  it('builds the document when a profile saved by an older version lacks newer fields', () => {
    const html = render('ru', {
      sellerRegistrationId: undefined,
      sellerTaxCode: undefined,
      sellerAddress: undefined,
      sellerBankDetails: undefined,
      paymentTerms: undefined,
    });

    expect(html).toContain('Print studio');
  });

  it('omits the customer block when no customer details are provided', () => {
    const html = render('ru', { buyerName: '', buyerInn: '', buyerAddress: '' });
    const document = new DOMParser().parseFromString(html, 'text/html');

    expect(document.querySelector('.quote-buyer-block')).toBeNull();
  });

  it.each(['ru', 'en', 'zh'] as const)('uses the %s interface language and shared non-offer wording', (language) => {
    const html = render(language);
    const t = translator(language);

    expect(html).toContain(`<html lang="${language}">`);
    expect(html).toContain(t('profilePage.calculator.quoteFooterNote'));
    expect(html).not.toContain(t('profilePage.calculator.quoteDisclaimerText'));
    expect(html).toMatch(/<header class="document-header">[\s\S]*?<svg[\s\S]*?<\/svg>\s*FilamentHub[\s\S]*?<\/header>/);
    expect(html).toContain(t('profilePage.calculator.quoteHeaderNoticeBefore'));
    expect(html).toContain(t('profilePage.calculator.quoteHeaderNoticeAfter').replaceAll("'", '&#39;'));
    const validityDate = new DOMParser().parseFromString(html, 'text/html').querySelector('[data-quote-validity]')?.textContent ?? '';
    if (language === 'zh') expect(validityDate).not.toMatch(/[А-Яа-яЁё]/);
    if (language === 'en') expect(validityDate).toMatch(/January|February|March|April|May|June|July|August|September|October|November|December/);
  });

  it('renders repeating header and footer margin boxes with a browser print fallback', () => {
    const html = render('en');

    expect(html).toContain('position: fixed; bottom: -15mm');
    expect(html).toContain('content: element(quoteFooter)');
    expect(html).toContain('position: running(quoteFooter)');
    expect(html.lastIndexOf('position: fixed; bottom: -15mm')).toBeLessThan(html.lastIndexOf('position: running(quoteFooter)'));
    expect(html).toContain('content: element(quoteHeader)');
    expect(html).toContain('position: running(quoteHeader)');
    expect(html.lastIndexOf('position: fixed; top: -10mm')).toBeLessThan(html.lastIndexOf('position: running(quoteHeader)'));
    expect(html).toContain('margin: 16mm 12mm 20mm');
  });

  it.each(['ru', 'en', 'zh'] as const)('never includes Russian statutory citations in %s quotes across markets', (language) => {
    for (const [quoteMarket, currency] of [['ru', 'RUB'], ['intl', 'EUR'], ['cn', 'CNY']] as const) {
      const html = render(language, { quoteMarket, currency }, 20);

      expect(html).not.toMatch(/ст\.\s*\d+|ГК РФ|Civil Code|Article\s+\d+|俄罗斯联邦民法典/i);
      expect(html).not.toContain(translator(language)('quoteMarket.ru.disclaimerNonBinding'));
      expect(html).not.toContain(translator(language)('quoteMarket.ru.disclaimerBinding'));
      expect(html).not.toContain(translator(language)('quoteMarket.intl.disclaimerNonBinding'));
      expect(html).not.toContain(translator(language)('quoteMarket.cn.disclaimerNonBinding'));
    }
  });

  it('does not infer a tax disclosure from currency or a calculator rate alone', () => {
    const html = render('ru', { currency: 'RUB' }, 20);

    expect(html).not.toContain('Налог включён');
    expect(html).not.toContain('НДС');
  });

  it('shows seller details for the Russian market', () => {
    const html = render('ru', { currency: 'RUB' });

    expect(html).toContain('ИНН: 7701234567');
    expect(html).toContain('ОГРН: 1027700000000');
    expect(html).toContain('КПП: 770101001');
  });

  it('uses the explicitly selected tax label and mode independent of market', () => {
    const html = render('en', { quoteMarket: 'ru', currency: 'RUB' }, 20, {
      kind: 'vat', mode: 'separate', amount: 200, netAmount: 1000,
    });

    expect(html).toContain('VAT from saved estimate (delivery excluded):');
    expect(html).toContain('Work subtotal before tax:');
    expect(html).toContain('1000.00');
    expect(html).toContain('200.00');
    expect(html).toContain('1200.00');
    expect(html).not.toContain('Tax included in total');
  });

  it('shows the unified code in China and omits optional registration and bank details when blank', () => {
    const html = render('en', {
      quoteMarket: 'cn',
      currency: 'CNY',
      sellerInn: '',
      sellerRegistrationId: '',
      sellerTaxCode: '',
      sellerBankDetails: '',
    });

    expect(html).not.toContain('Unified social credit code');
    expect(html).not.toContain('Company registration number');
    expect(html).not.toContain('Bank details');
  });

  it.each([
    ['en', 'intl', 'EUR', 'Includes VAT:', 'Includes VAT:'],
    ['zh', 'cn', 'CNY', '其中增值税:', '其中增值税:'],
  ] as const)('uses an explicit tax label for %s independent of currency', (language, quoteMarket, currency, taxLabel, includedLabel) => {
    const html = render(language, { quoteMarket, currency }, 20, {
      kind: 'vat', mode: 'included', amount: 200, netAmount: 1000,
    });

    expect(html).toContain(taxLabel);
    expect(html).toContain(includedLabel);
  });

  it('does not invent a tax row when no rate is set', () => {
    const html = render('en', { quoteMarket: 'intl', currency: 'EUR' });

    expect(html).not.toContain('Subtotal before tax');
    expect(html).not.toContain('Tax 0%');
    expect(html).toContain('1200.00');
    expect(html).toContain('data-quote-totals');
    expect(html).not.toMatch(/<tfoot[\s\S]*?data-quote-total-kind="total"/);
  });

  it('uses neutral international tax ID labels for English and Chinese when market is unspecified', () => {
    const en = render('en', { currency: 'RUB' });
    const zh = render('zh', { currency: 'RUB' });
    expect(en).toContain('Tax ID: 7701234567');
    expect(en).not.toContain('INN');
    expect(zh).toContain('纳税识别号: 7701234567');
    expect(zh).not.toContain('ИНН');
  });
});
