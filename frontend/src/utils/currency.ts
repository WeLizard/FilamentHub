// Единый источник валют: код, символ, страны, которые в ней считают, и языки UI,
// для которых валюта — дефолт. Всё остальное выводится отсюда.
export interface CurrencyDef {
  code: string;
  symbol: string;
  countries: string[];
  languages: string[];
}

// Same order as the server's ranking, so the list does not reshuffle under the cursor
// when the catalogue arrives. Symbol order matters too: ¥ resolves to CNY, not JPY.
const EUROZONE = [
  'AD', 'AT', 'BE', 'CY', 'DE', 'EE', 'ES', 'FI', 'FR', 'GR', 'HR', 'IE', 'IT',
  'LT', 'LU', 'LV', 'MC', 'ME', 'MT', 'NL', 'PT', 'SI', 'SK', 'SM', 'VA', 'XK',
];

const BUILT_IN_CURRENCIES: readonly CurrencyDef[] = [
  { code: 'USD', symbol: '$', countries: ['US'], languages: ['en'] },
  { code: 'EUR', symbol: '€', countries: EUROZONE, languages: ['de', 'fr', 'es', 'it'] },
  { code: 'RUB', symbol: '₽', countries: ['RU'], languages: ['ru'] },
  { code: 'CNY', symbol: '¥', countries: ['CN'], languages: ['zh'] },
  { code: 'GBP', symbol: '£', countries: ['GB'], languages: [] },
  { code: 'JPY', symbol: '¥', countries: ['JP'], languages: ['ja'] },
  { code: 'UAH', symbol: '₴', countries: ['UA'], languages: ['uk'] },
  { code: 'KZT', symbol: '₸', countries: ['KZ'], languages: ['kk'] },
  { code: 'PLN', symbol: 'zł', countries: ['PL'], languages: ['pl'] },
  { code: 'BYN', symbol: 'Br', countries: ['BY'], languages: ['be'] },
];

const FALLBACK_CURRENCY = 'RUB';

// Used until the catalogue loads; the server value wins once it arrives.
const FALLBACK_ROUNDING_STEPS: Record<string, number> = {
  RUB: 10, KZT: 50, JPY: 50, HUF: 50, AMD: 50, ISK: 50,
  INR: 10, UYU: 10, KGS: 10, RSD: 20,
  CZK: 5, SEK: 5, NOK: 5, THB: 5, TWD: 5, TRY: 5, UAH: 5, PHP: 5, MXN: 5,
  VND: 2000, IDR: 2000, UZS: 1000, COP: 500, ARS: 200, CLP: 200, KRW: 200, IRR: 50000,
};
const FALLBACK_LANGUAGE_CURRENCY = 'USD';

/**
 * Currencies are reference data, not a constant: the server owns the list so adding one
 * does not need a release. The built-in set keeps the interface working before the
 * catalogue arrives and if the request fails.
 */
let catalogue: readonly CurrencyDef[] = BUILT_IN_CURRENCIES;
let symbolByCode = new Map(BUILT_IN_CURRENCIES.map((c) => [c.code, c.symbol]));
const roundingStepByCode = new Map<string, number>();

// Страна → валюта. Собирается из того же справочника: язык не является юрисдикцией,
// а вторая карта рядом рано или поздно разойдётся с первой.
function countryIndex(rows: readonly CurrencyDef[]): Map<string, string> {
  const index = new Map<string, string>();
  for (const currency of rows) {
    for (const country of currency.countries) {
      if (!index.has(country)) index.set(country, currency.code);
    }
  }
  return index;
}

let codeByCountry = countryIndex(BUILT_IN_CURRENCIES);

export function currencyCatalogue(): readonly CurrencyDef[] {
  return catalogue;
}

export function currencyCodes(): string[] {
  return catalogue.map((c) => c.code);
}

export function setCurrencyCatalogue(
  rows: Array<{
    code: string;
    symbol: string;
    rounding_step?: number;
    countries?: string[];
  }>,
): void {
  if (rows.length === 0) return;
  const byLanguage = new Map(BUILT_IN_CURRENCIES.map((c) => [c.code, c.languages]));
  const byCountry = new Map(BUILT_IN_CURRENCIES.map((c) => [c.code, c.countries]));
  catalogue = rows.map((row) => ({
    code: row.code,
    symbol: row.symbol,
    countries: row.countries ?? byCountry.get(row.code) ?? [],
    // Language hints stay a local concern; the server has no business guessing them.
    languages: byLanguage.get(row.code) ?? [],
  }));
  symbolByCode = new Map(catalogue.map((c) => [c.code, c.symbol]));
  codeByCountry = countryIndex(catalogue);
  roundingStepByCode.clear();
  rows.forEach((row) => {
    if (row.rounding_step && row.rounding_step > 0) {
      roundingStepByCode.set(row.code, row.rounding_step);
    }
  });
}


// Символ → код. Первое вхождение выигрывает (¥ → CNY, не JPY).
const CODE_BY_SYMBOL = new Map<string, string>();
for (const c of BUILT_IN_CURRENCIES) {
  if (!CODE_BY_SYMBOL.has(c.symbol)) CODE_BY_SYMBOL.set(c.symbol, c.code);
}

const CURRENCY_BY_LANGUAGE = new Map<string, string>();
for (const c of BUILT_IN_CURRENCIES) {
  for (const lang of c.languages) {
    if (!CURRENCY_BY_LANGUAGE.has(lang)) CURRENCY_BY_LANGUAGE.set(lang, c.code);
  }
}

export function currencySymbol(code: string | null | undefined): string {
  if (!code) return symbolByCode.get(FALLBACK_CURRENCY) ?? FALLBACK_CURRENCY;
  return symbolByCode.get(code.toUpperCase()) || code;
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

// Валюта рынка. Язык — не юрисдикция: русскоязычный человек в Германии платит
// в евро, поэтому страна решает, а язык остаётся запасным вариантом.
export function defaultCurrencyForCountry(
  country: string | null | undefined,
  language?: string | null,
): string {
  const known = country ? codeByCountry.get(country.toUpperCase()) : undefined;
  return known || defaultCurrencyForLanguage(language);
}

/**
 * Sensible "round the quote to" steps for a currency.
 *
 * Ten roubles is small change; ten dollars is a meaningful part of a small order.
 * The steps follow the unit's magnitude instead of being fixed at rouble-sized numbers.
 */
export function roundingStepsForCurrency(code: string | null | undefined): number[] {
  const normalized = normalizeCurrency(code);
  // The base step comes from the catalogue; the chips are that step, five and ten of it.
  const step = roundingStepByCode.get(normalized) ?? FALLBACK_ROUNDING_STEPS[normalized] ?? 1;
  return [step, step * 5, step * 10];
}

