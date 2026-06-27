const CURRENCY_SYMBOLS: Record<string, string> = {
  RUB: '₽',
  USD: '$',
  EUR: '€',
  GBP: '£',
  UAH: '₴',
  KZT: '₸',
  BYN: 'Br',
  CNY: '¥',
  JPY: '¥',
  PLN: 'zł',
};

export const CURRENCY_CODES = Object.keys(CURRENCY_SYMBOLS);

export function currencySymbol(code: string | null | undefined): string {
  if (!code) return '₽';
  return CURRENCY_SYMBOLS[code.toUpperCase()] || code;
}

export function formatPrice(amount: number, code: string | null | undefined): string {
  return `${Math.round(amount)} ${currencySymbol(code)}`;
}

const SYMBOL_TO_CODE: Record<string, string> = {
  '₽': 'RUB',
  $: 'USD',
  '€': 'EUR',
  '£': 'GBP',
  '₴': 'UAH',
  '₸': 'KZT',
  '¥': 'CNY',
};

// Старые данные хранили символ (₽/$/€); новые — код. Приводим к коду.
export function normalizeCurrency(value: string | null | undefined): string {
  if (!value) return 'RUB';
  return SYMBOL_TO_CODE[value] || value.toUpperCase();
}
