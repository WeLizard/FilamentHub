import i18n from '../i18n';
import { normalizeSiteLocale, type SiteLocale } from './siteLocale';

/** Interface language to attach to a request whose visible result is an email. */
export function currentRequestLanguage(): SiteLocale {
  return normalizeSiteLocale(i18n.resolvedLanguage || i18n.language) ?? 'en';
}
