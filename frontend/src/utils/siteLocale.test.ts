import { describe, expect, it } from 'vitest';
import {
  absoluteLocalizedUrl,
  absoluteSiteUrl,
  getLocaleBasename,
  getPathLocale,
  normalizeSiteLocale,
  stripLocalePrefix,
  withLocalePrefix,
  withoutLocalePrefix,
} from './siteLocale';

describe('siteLocale', () => {
  it('recognizes only supported locale path prefixes', () => {
    expect(getPathLocale('/ru/filaments/12')).toBe('ru');
    expect(getPathLocale('/en')).toBe('en');
    expect(getPathLocale('/zh/')).toBe('zh');
    expect(getPathLocale('/filaments/12')).toBeNull();
    expect(getPathLocale('/english/catalog')).toBeNull();
    expect(normalizeSiteLocale('ru-RU')).toBe('ru');
    expect(normalizeSiteLocale('de-DE')).toBeNull();
  });

  it('builds the router basename without changing the application route', () => {
    expect(getLocaleBasename('/ru/filaments/12')).toBe('/ru');
    expect(stripLocalePrefix('/ru/filaments/12')).toBe('/filaments/12');
    expect(stripLocalePrefix('/en')).toBe('/');
    expect(getLocaleBasename('/filaments/12')).toBeUndefined();
  });

  it('creates stable localized paths and preserves query and hash state', () => {
    expect(withLocalePrefix('/catalog?material=PLA#results', 'zh'))
      .toBe('/zh/catalog?material=PLA#results');
    expect(withLocalePrefix('/ru/download', 'en')).toBe('/en/download');
    expect(withLocalePrefix('/', 'ru')).toBe('/ru/');
    expect(withoutLocalePrefix('/zh/wiki/materials?tab=all')).toBe('/wiki/materials?tab=all');
  });

  it('keeps canonical URLs on the production origin', () => {
    expect(absoluteSiteUrl('/download')).toBe('https://filamenthub.ru/download');
    expect(absoluteLocalizedUrl('/download', 'ru')).toBe('https://filamenthub.ru/ru/download');
  });
});
