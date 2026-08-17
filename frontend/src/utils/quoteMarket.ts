export type QuoteMarket = 'ru' | 'intl' | 'cn';

export interface QuoteMarketRules {
  market: QuoteMarket;
  taxIdKey: string;
  registrationIdKey: string | null;
  showTaxCode: boolean;
  showBankDetails: boolean;
  showTaxLine: boolean;
  disclaimerKeys: { binding: string; nonBinding: string };
  dateLocale: string;
  numberPrefix: string;
  /** Как на этом рынке выглядит номер телефона. */
  phonePlaceholder: string;
  /**
   * Валюты, в которых на этом рынке обычно выставляют счёт. Первая — основная.
   * Пустой список означает «любая»: международный рынок не сводится к одной.
   */
  currencies: string[];
}

const RULES: Record<QuoteMarket, QuoteMarketRules> = {
  ru: {
    market: 'ru',
    taxIdKey: 'quoteMarket.ru.taxId',
    registrationIdKey: 'quoteMarket.ru.registrationId',
    showTaxCode: true,
    showBankDetails: true,
    showTaxLine: false,
    disclaimerKeys: {
      binding: 'quoteMarket.ru.disclaimerBinding',
      nonBinding: 'quoteMarket.ru.disclaimerNonBinding',
    },
    dateLocale: 'ru-RU',
    numberPrefix: 'КП',
    phonePlaceholder: '+7 (999) 000-00-00',
    currencies: ['RUB', 'BYN', 'KZT', 'UAH', 'AMD', 'AZN', 'GEL', 'KGS', 'MDL', 'UZS'],
  },
  intl: {
    market: 'intl',
    taxIdKey: 'quoteMarket.intl.taxId',
    registrationIdKey: 'quoteMarket.intl.registrationId',
    showTaxCode: false,
    showBankDetails: true,
    showTaxLine: true,
    disclaimerKeys: {
      binding: 'quoteMarket.intl.disclaimerBinding',
      nonBinding: 'quoteMarket.intl.disclaimerNonBinding',
    },
    dateLocale: 'en-GB',
    numberPrefix: 'QUO',
    phonePlaceholder: '+1 555 000 0000',
    currencies: [],
  },
  cn: {
    market: 'cn',
    taxIdKey: 'quoteMarket.cn.taxId',
    registrationIdKey: null,
    showTaxCode: false,
    showBankDetails: true,
    showTaxLine: true,
    disclaimerKeys: {
      binding: 'quoteMarket.cn.disclaimerBinding',
      nonBinding: 'quoteMarket.cn.disclaimerNonBinding',
    },
    dateLocale: 'zh-CN',
    numberPrefix: 'BJ',
    phonePlaceholder: '+86 138 0000 0000',
    currencies: ['CNY'],
  },
};

const CURRENCY_MARKET: Record<string, QuoteMarket> = {
  RUB: 'ru',
  BYN: 'ru',
  KZT: 'ru',
  CNY: 'cn',
};

export function resolveQuoteMarket(
  explicit: string | null | undefined,
  currency: string | null | undefined,
): QuoteMarket {
  if (explicit === 'ru' || explicit === 'intl' || explicit === 'cn') {
    return explicit;
  }
  return CURRENCY_MARKET[(currency || '').toUpperCase()] ?? 'intl';
}

export function quoteMarketRules(market: QuoteMarket): QuoteMarketRules {
  return RULES[market];
}

export const QUOTE_MARKETS: QuoteMarket[] = ['ru', 'intl', 'cn'];
