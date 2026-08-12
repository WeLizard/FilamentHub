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
const interfaceLanguage = (): string =>
  (i18n.resolvedLanguage || i18n.language || 'en').split('-')[0];

/**
 * У языка мало регионов, но разница между ними бывает опасной: `3/4/2026` в
 * Америке и `04/03/2026` в Британии — это одна дата, прочитанная как 4 марта
 * либо как 3 апреля. Интерфейс у нас на трёх языках без регионов, поэтому
 * регион берём у самого читателя: браузер перечисляет его предпочтения, и если
 * среди них есть наш язык — используем именно ту запись. Спрашивать нечего.
 */
const currentLocale = (): string => {
  const language = interfaceLanguage();
  const preferred =
    typeof navigator !== 'undefined' && Array.isArray(navigator.languages)
      ? navigator.languages.find((tag) => tag.split('-')[0] === language)
      : undefined;
  return preferred || language;
};

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

/** Короткий календарный формат для списков и карточек. */
export const formatMediumDate = (
  value: string | number | Date | null | undefined,
): string => formatDate(value, { dateStyle: 'medium' });

/** Компактные дата и время для лент сообщений и событий. */
export const formatMediumDateTime = (
  value: string | number | Date | null | undefined,
): string => formatDateTime(value, { dateStyle: 'medium', timeStyle: 'short' });
