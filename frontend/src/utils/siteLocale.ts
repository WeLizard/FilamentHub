import siteOrigins from '../data/siteOrigins.json';

export const SITE_LOCALES = ['en', 'ru', 'zh'] as const;

export type SiteLocale = (typeof SITE_LOCALES)[number];

// Each language has one canonical host; both hosts keep serving every language.
const SITE_ORIGINS: Record<SiteLocale, string> = siteOrigins;
const DEFAULT_LOCALE: SiteLocale = 'en';

export function siteOrigin(locale: SiteLocale): string {
  return SITE_ORIGINS[locale];
}

const LOCALE_PREFIX_PATTERN = /^\/(en|ru|zh)(?=\/|$)/i;

export function normalizeSiteLocale(value: string | null | undefined): SiteLocale | null {
  const normalized = value?.toLowerCase().split('-')[0];
  return SITE_LOCALES.includes(normalized as SiteLocale) ? normalized as SiteLocale : null;
}

export function getPathLocale(pathname: string): SiteLocale | null {
  return normalizeSiteLocale(pathname.match(LOCALE_PREFIX_PATTERN)?.[1]);
}

export function getLocaleBasename(pathname: string): string | undefined {
  const locale = getPathLocale(pathname);
  return locale ? `/${locale}` : undefined;
}

export function stripLocalePrefix(pathname: string): string {
  const stripped = pathname.replace(LOCALE_PREFIX_PATTERN, '');
  return stripped === '' ? '/' : stripped;
}

export function withLocalePrefix(path: string, locale: SiteLocale): string {
  const parsed = new URL(path, 'https://filamenthub.invalid');
  const basePath = stripLocalePrefix(parsed.pathname);
  const localizedPath = locale === 'en'
    ? basePath
    : basePath === '/' ? `/${locale}/` : `/${locale}${basePath}`;
  return `${localizedPath}${parsed.search}${parsed.hash}`;
}

export function withoutLocalePrefix(path: string): string {
  const parsed = new URL(path, 'https://filamenthub.invalid');
  return `${stripLocalePrefix(parsed.pathname)}${parsed.search}${parsed.hash}`;
}

function absoluteUrlOnOrigin(path: string, origin: string): string {
  const target = new URL(origin);
  const parsed = new URL(path, origin);
  parsed.protocol = target.protocol;
  parsed.host = target.host;
  return parsed.toString();
}

/** The language-neutral address of a page: its default-language canonical URL. */
export function absoluteSiteUrl(path: string): string {
  return absoluteUrlOnOrigin(path, siteOrigin(DEFAULT_LOCALE));
}

export function absoluteLocalizedUrl(path: string, locale: SiteLocale): string {
  return absoluteUrlOnOrigin(withLocalePrefix(path, locale), siteOrigin(locale));
}
