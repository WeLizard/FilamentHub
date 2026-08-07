/** Даты в языке интерфейса, а не в одном заранее выбранном. */

// Берём сам i18next, а не наш настроенный модуль: помощнику нужен только
// текущий язык, и тянуть ради него react-обвязку в каждый файл, где есть дата,
// незачем. Экземпляр тот же — настраивает его приложение при запуске.
import i18n from 'i18next';

/**
 * Пояс браузер знает от системы сам, поэтому спрашивать его у человека не нужно:
 * заданный руками пояс начнёт врать в первую же поездку. От нас требуется лишь
 * не навязывать формат: китаец в китайском интерфейсе не должен читать дату
 * по-русски.
 */
const currentLocale = (): string => i18n.resolvedLanguage || i18n.language || 'en';

const asDate = (value: string | number | Date | null | undefined): Date | null => {
  if (value === null || value === undefined || value === '') {
    return null;
  }
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
};

/** Только дата. Пустое или неразобранное значение даёт пустую строку. */
export const formatDate = (
  value: string | number | Date | null | undefined,
  options?: Intl.DateTimeFormatOptions,
): string => {
  const date = asDate(value);
  return date ? date.toLocaleDateString(currentLocale(), options) : '';
};

/** Дата со временем. */
export const formatDateTime = (
  value: string | number | Date | null | undefined,
  options?: Intl.DateTimeFormatOptions,
): string => {
  const date = asDate(value);
  return date ? date.toLocaleString(currentLocale(), options) : '';
};
