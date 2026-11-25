import { mkdir, readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  buildPublicPages,
  createTranslator,
  renderPageBody,
} from './public-pages.mjs';

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const distIndexPath = path.join(frontendRoot, 'dist', 'index.html');
// One canonical host per language, shared with the application (utils/siteLocale.ts).
const siteOrigins = JSON.parse(
  await readFile(path.join(frontendRoot, 'src', 'data', 'siteOrigins.json'), 'utf8'),
);
const defaultLocale = 'en';
const localizedBaseUrl = (locale) => (
  locale === defaultLocale ? siteOrigins[locale] : `${siteOrigins[locale]}/${locale}`
);
const localeConfig = {
  en: { ogLocale: 'en_US', imageAlt: 'FilamentHub — 3D printing filaments and presets' },
  ru: { ogLocale: 'ru_RU', imageAlt: 'FilamentHub — филаменты и пресеты для 3D-печати' },
  zh: { ogLocale: 'zh_CN', imageAlt: 'FilamentHub — 3D 打印耗材与预设' },
};

const escapeHtmlAttribute = (value) => String(value)
  .replaceAll('&', '&amp;')
  .replaceAll('"', '&quot;')
  .replaceAll('<', '&lt;')
  .replaceAll('>', '&gt;');

function replaceMetaField(html, field, value) {
  const pattern = new RegExp(
    `(<meta\\b[^>]*data-seo-field="${field}"[^>]*\\bcontent=")[^"]*("[^>]*>)`,
    'g',
  );
  let replacements = 0;
  const result = html.replace(pattern, (_match, prefix, suffix) => {
    replacements += 1;
    return `${prefix}${escapeHtmlAttribute(value)}${suffix}`;
  });
  if (replacements === 0) {
    throw new Error(`SEO field was not found in built index: ${field}`);
  }
  return result;
}

function replaceTitle(html, title) {
  const pattern = /(<title\b[^>]*data-seo-field="title"[^>]*>)[\s\S]*?(<\/title>)/;
  if (!pattern.test(html)) {
    throw new Error('Localized title marker was not found in built index');
  }
  return html.replace(pattern, (_match, open, close) => `${open}${escapeHtmlAttribute(title)}${close}`);
}

function replaceOgLocaleAlternates(html, currentLocale) {
  const alternates = Object.values(localeConfig)
    .map(({ ogLocale }) => ogLocale)
    .filter((ogLocale) => ogLocale !== currentLocale);
  let index = 0;
  const result = html.replace(
    /(<meta\b[^>]*data-seo-og-alternate="true"[^>]*\bcontent=")[^"]*("[^>]*>)/g,
    (_match, prefix, suffix) => `${prefix}${alternates[index++]}${suffix}`,
  );
  if (index !== alternates.length) {
    throw new Error(`Expected ${alternates.length} Open Graph locale alternate slots, found ${index}`);
  }
  return result;
}

function replaceLinkHref(html, marker, value) {
  const pattern = new RegExp(
    `(<link\\b[^>]*${marker}[^>]*\\bhref=")[^"]*("[^>]*>)`,
  );
  if (!pattern.test(html)) {
    throw new Error(`SEO link marker was not found in built index: ${marker}`);
  }
  return html.replace(pattern, (_match, prefix, suffix) => `${prefix}${value}${suffix}`);
}

function replaceWebsiteJsonLd(html, locale, description) {
  const pattern = /(<script\b[^>]*data-seo-base-jsonld="website"[^>]*>)[\s\S]*?(<\/script>)/;
  if (!pattern.test(html)) {
    throw new Error('Website JSON-LD marker was not found in built index');
  }
  const localizedRoot = `${localizedBaseUrl(locale === 'x-default' ? defaultLocale : locale)}/`;
  const payload = {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    '@id': `${localizedRoot}#website`,
    url: localizedRoot,
    name: 'FilamentHub',
    alternateName: ['Filament Hub', 'ФиламентХаб', 'Филамент Хаб'],
    description,
    inLanguage: locale === 'x-default' ? 'en' : locale,
    publisher: { '@id': `${localizedBaseUrl(defaultLocale)}/#organization` },
  };
  const serialized = JSON.stringify(payload, null, 2)
    .split('\n')
    .map((line) => `      ${line}`)
    .join('\n');
  return html.replace(pattern, (_match, open, close) => `${open}\n${serialized}\n    ${close}`);
}

// React replaces the content of #root on its first render, so static text put
// there is what a reader without JavaScript sees and nothing a visitor keeps.
function injectStaticBody(html, body) {
  const marker = '<div id="root"></div>';
  if (!html.includes(marker)) {
    throw new Error('Application root marker was not found in built index');
  }
  return html.replace(marker, () => `<div id="root">${body}</div>`);
}

function localizeIndex(baseHtml, locale, translation, outputLocale = locale, page = null) {
  const config = localeConfig[locale];
  const title = `${page?.title ?? translation.catalogPage.seoTitle} | FilamentHub`;
  const description = page?.description ?? translation.catalogPage.seoDescription;
  let html = baseHtml.replace(/<html\b[^>]*\blang="[^"]*"/, (tag) => tag.replace(/lang="[^"]*"/, `lang="${locale}"`));
  html = replaceMetaField(html, 'title', title);
  html = replaceMetaField(html, 'description', description);
  html = replaceMetaField(html, 'keywords', translation.catalogPage.seoKeywords);
  html = replaceMetaField(html, 'imageAlt', config.imageAlt);
  html = replaceMetaField(html, 'ogLocale', config.ogLocale);
  const origin = siteOrigins[locale];
  html = replaceMetaField(html, 'canonicalUrl', `${origin}__FH_CANONICAL_PATH__`);
  html = replaceMetaField(html, 'image', `${origin}/email/hero.jpg`);
  html = replaceTitle(html, title);
  html = replaceOgLocaleAlternates(html, config.ogLocale);
  html = replaceLinkHref(html, 'data-seo-base="true"[^>]*rel="canonical"', `${origin}__FH_CANONICAL_PATH__`);
  html = replaceLinkHref(html, 'data-seo-hreflang="x-default"', `${localizedBaseUrl(defaultLocale)}__FH_BASE_PATH__`);
  for (const alternateLocale of Object.keys(localeConfig)) {
    html = replaceLinkHref(
      html,
      `data-seo-hreflang="${alternateLocale}"`,
      `${localizedBaseUrl(alternateLocale)}__FH_BASE_PATH__`,
    );
  }
  html = replaceWebsiteJsonLd(html, outputLocale, translation.catalogPage.seoDescription);
  if (page) {
    const prefix = localeHrefPrefix(outputLocale);
    const localizeHref = (href) => (href === '/' ? `${prefix}/` : `${prefix}${href}`);
    html = injectStaticBody(html, renderPageBody(page, localizeHref));
  }
  return html;
}

// dist/_pages/<variant><path>/index.html is the static form of a public page;
// nginx serves it for that path and falls back to the plain shell without it.
async function writePublicPages(baseHtml, locale, translation, pages, variant) {
  for (const page of pages) {
    const directory = path.join(frontendRoot, 'dist', '_pages', variant, page.path);
    await mkdir(directory, { recursive: true });
    await writeFile(
      path.join(directory, 'index.html'),
      localizeIndex(baseHtml, locale, translation, variant, page),
      'utf8',
    );
  }
}

const localeHrefPrefix = (variant) => (
  variant === 'x-default' || variant === defaultLocale ? '' : `/${variant}`
);

const readJson = async (...segments) => JSON.parse(
  await readFile(path.join(frontendRoot, 'src', ...segments), 'utf8'),
);

const baseHtml = await readFile(distIndexPath, 'utf8');
const capabilities = await readJson('data', 'capabilities.json');
for (const locale of Object.keys(localeConfig)) {
  const translation = await readJson('locales', locale, 'translation.json');
  const features = await readJson('locales', locale, 'features.json');
  const t = createTranslator(translation, features);
  const pages = buildPublicPages(t, capabilities);
  const localized = localizeIndex(baseHtml, locale, translation);
  await writeFile(path.join(frontendRoot, 'dist', `index.${locale}.html`), localized, 'utf8');
  await writePublicPages(baseHtml, locale, translation, pages, locale);
  if (locale === defaultLocale) {
    const adaptiveDefault = localizeIndex(baseHtml, locale, translation, 'x-default');
    await writeFile(path.join(frontendRoot, 'dist', 'index.x-default.html'), adaptiveDefault, 'utf8');
    await writePublicPages(baseHtml, locale, translation, pages, 'x-default');
  }
}
