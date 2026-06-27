// Единый источник валют: код, символ и языки UI, для которых валюта — дефолт.
// Всё остальное (символы, коды, дефолт по языку) выводится отсюда.
export interface CurrencyDef {
  code: string;
  symbol: string;
  languages: string[];
}

export const CURRENCIES: readonly CurrencyDef[] = [
  { code: 'RUB', symbol: '₽', languages: ['ru'] },
  { code: 'USD', symbol: '$', languages: ['en'] },
  { code: 'EUR', symbol: '€', languages: ['de', 'fr', 'es', 'it'] },
  { code: 'GBP', symbol: '£', languages: [] },
  { code: 'UAH', symbol: '₴', languages: ['uk'] },
  { code: 'KZT', symbol: '₸', languages: ['kk'] },
  { code: 'BYN', symbol: 'Br', languages: ['be'] },
  { code: 'CNY', symbol: '¥', languages: ['zh'] },
  { code: 'JPY', symbol: '¥', languages: ['ja'] },
  { code: 'PLN', symbol: 'zł', languages: ['pl'] },
];

const FALLBACK_CURRENCY = 'RUB';
const FALLBACK_LANGUAGE_CURRENCY = 'USD';

export const CURRENCY_CODES = CURRENCIES.map((c) => c.code);

const SYMBOL_BY_CODE = new Map(CURRENCIES.map((c) => [c.code, c.symbol]));

// Символ → код. Первое вхождение выигрывает (¥ → CNY, не JPY).
const CODE_BY_SYMBOL = new Map<string, string>();
for (const c of CURRENCIES) {
  if (!CODE_BY_SYMBOL.has(c.symbol)) CODE_BY_SYMBOL.set(c.symbol, c.code);
}

const CURRENCY_BY_LANGUAGE = new Map<string, string>();
for (const c of CURRENCIES) {
  for (const lang of c.languages) {
    if (!CURRENCY_BY_LANGUAGE.has(lang)) CURRENCY_BY_LANGUAGE.set(lang, c.code);
  }
}

export function currencySymbol(code: string | null | undefined): string {
  if (!code) return SYMBOL_BY_CODE.get(FALLBACK_CURRENCY)!;
  return SYMBOL_BY_CODE.get(code.toUpperCase()) || code;
}

export function formatPrice(amount: number, code: string | null | undefined): string {
  return `${Math.round(amount)} ${currencySymbol(code)}`;
}

// Старые данные хранили символ (₽/$/€); новые — код. Приводим к коду.
export function normalizeCurrency(value: string | null | undefined): string {
  if (!value) return FALLBACK_CURRENCY;
  return CODE_BY_SYMBOL.get(value) || value.toUpperCase();
}

// Дефолт валюты по языку UI (пока пользователь не выбрал свою).
export function defaultCurrencyForLanguage(language: string | null | undefined): string {
  const lang = (language || 'en').toLowerCase().split('-')[0];
  return CURRENCY_BY_LANGUAGE.get(lang) || FALLBACK_LANGUAGE_CURRENCY;
}
