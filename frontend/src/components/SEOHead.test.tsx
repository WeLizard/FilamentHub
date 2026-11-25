import { cleanup, render, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import i18n, { i18nReady } from '../i18n';
import { SEOHead } from './SEOHead';

const baseHead = `
  <meta data-seo-base="true" name="description" content="Base description" />
  <meta data-seo-base="true" property="og:title" content="Base title" />
  <meta data-seo-base="true" property="og:description" content="Base description" />
  <meta data-seo-base="true" property="og:image" content="https://filamenthub.ru/email/hero.jpg" />
  <meta data-seo-base="true" property="og:url" content="https://filamenthub.ru/" />
  <meta data-seo-base="true" property="og:type" content="website" />
  <meta data-seo-base="true" property="og:site_name" content="FilamentHub" />
  <meta data-seo-base="true" property="og:locale" content="en_US" />
  <meta data-seo-base="true" data-seo-og-alternate="true" property="og:locale:alternate" content="ru_RU" />
  <meta data-seo-base="true" data-seo-og-alternate="true" property="og:locale:alternate" content="zh_CN" />
  <link data-seo-base="true" rel="canonical" href="https://filamenthub.ru/" />
  <link data-seo-hreflang="x-default" rel="alternate" hreflang="x-default" href="https://filamenthub.ru/" />
  <link data-seo-hreflang="en" rel="alternate" hreflang="en" href="https://filamenthub.ru/" />
  <link data-seo-hreflang="ru" rel="alternate" hreflang="ru" href="https://filamenthub.ru/ru/" />
  <link data-seo-hreflang="zh" rel="alternate" hreflang="zh" href="https://filamenthub.ru/zh/" />
`;

describe('SEOHead locale metadata', () => {
  beforeEach(async () => {
    await i18nReady;
    document.head.innerHTML = baseHead;
    window.history.replaceState({}, '', '/ru/download');
    await i18n.changeLanguage('ru');
  });

  afterEach(async () => {
    cleanup();
    window.history.replaceState({}, '', '/');
    await i18n.changeLanguage('en');
  });

  it('uses self-canonical locale URLs and reciprocal hreflang links', async () => {
    render(<SEOHead title="Плагины" description="Скачать плагины" url="/download" />);

    await waitFor(() => {
      expect(document.title).toBe('Плагины | FilamentHub');
    });
    expect(document.documentElement.dataset.seoReady).toBe('true');

    expect(document.querySelector<HTMLLinkElement>('link[rel="canonical"]')?.href)
      .toBe('https://filamenthub.ru/ru/download');

    const alternates = Object.fromEntries(
      Array.from(document.querySelectorAll<HTMLLinkElement>('link[rel="alternate"][hreflang]'))
        .map((link) => [link.hreflang, link.href]),
    );
    expect(alternates).toEqual({
      'x-default': 'https://filamenthub.club/download',
      en: 'https://filamenthub.club/download',
      ru: 'https://filamenthub.ru/ru/download',
      zh: 'https://filamenthub.club/zh/download',
    });
  });

  it('names only the languages a page exists in and restores the slots afterwards', async () => {
    const { unmount } = render(
      <SEOHead
        title="Только по-русски"
        url="/wiki/articles/tolko-russkaya"
        localizedPaths={{ ru: '/wiki/articles/tolko-russkaya' }}
        contentLocale="ru"
      />,
    );

    await waitFor(() => {
      expect(document.querySelector<HTMLLinkElement>('link[rel="canonical"]')?.href)
        .toBe('https://filamenthub.ru/ru/wiki/articles/tolko-russkaya');
    });
    const alternates = () => Object.fromEntries(
      Array.from(document.querySelectorAll<HTMLLinkElement>('link[rel="alternate"][hreflang]'))
        .map((link) => [link.hreflang, link.href]),
    );
    expect(alternates()).toEqual({ ru: 'https://filamenthub.ru/ru/wiki/articles/tolko-russkaya' });

    unmount();
    expect(Object.keys(alternates()).sort()).toEqual(['en', 'ru', 'x-default', 'zh']);
  });

  it('keeps server structured data for its own page only', async () => {
    const serverScript = () => document.head.querySelector('script[data-seo-server="true"]');
    document.head.insertAdjacentHTML(
      'beforeend',
      '<script type="application/ld+json" data-seo-server="true" data-seo-path="/ru/download">{}</script>',
    );

    const { unmount } = render(<SEOHead title="Плагины" url="/download" />);
    await waitFor(() => expect(document.title).toBe('Плагины | FilamentHub'));
    expect(serverScript()).not.toBeNull();
    unmount();

    render(<SEOHead title="Плагины" url="/download" jsonLd={{ '@type': 'WebPage' }} />);
    await waitFor(() => expect(serverScript()).toBeNull());
  });

  it('keeps Open Graph locale and social preview metadata consistent', async () => {
    render(<SEOHead title="Плагины" description="Скачать плагины" url="/download" />);

    await waitFor(() => {
      expect(document.querySelector<HTMLMetaElement>('meta[property="og:locale"]')?.content).toBe('ru_RU');
    });

    const ogAlternates = Array.from(
      document.querySelectorAll<HTMLMetaElement>('meta[property="og:locale:alternate"]'),
      (meta) => meta.content,
    );
    expect(ogAlternates).toEqual(['en_US', 'zh_CN']);
    expect(document.querySelector<HTMLMetaElement>('meta[property="og:image"]')?.content)
      .toBe('https://filamenthub.ru/email/hero.jpg');
    expect(document.querySelector('meta[name="twitter:site"]')).toBeNull();
    expect(document.querySelector('meta[name="ai:index"]')).toBeNull();
  });
});
