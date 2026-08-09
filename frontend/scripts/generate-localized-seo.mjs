import { readFile, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const distIndexPath = path.join(frontendRoot, 'dist', 'index.html');
const baseUrl = 'https://filamenthub.ru';
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
  return html.replace(pattern, `$1${escapeHtmlAttribute(title)}$2`);
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
  return html.replace(pattern, `$1${value}$2`);
}

function replaceWebsiteJsonLd(html, locale, description) {
  const pattern = /(<script\b[^>]*data-seo-base-jsonld="website"[^>]*>)[\s\S]*?(<\/script>)/;
  if (!pattern.test(html)) {
    throw new Error('Website JSON-LD marker was not found in built index');
  }
  const localizedRoot = locale === 'x-default' || locale === 'en'
    ? `${baseUrl}/`
    : `${baseUrl}/${locale}/`;
  const payload = {
    '@context': 'https://schema.org',
    '@type': 'WebSite',
    '@id': `${localizedRoot}#website`,
    url: localizedRoot,
    name: 'FilamentHub',
    alternateName: ['Filament Hub', 'ФиламентХаб', 'Филамент Хаб'],
    description,
    inLanguage: locale === 'x-default' ? 'en' : locale,
  };
  const serialized = JSON.stringify(payload, null, 2)
    .split('\n')
    .map((line) => `      ${line}`)
    .join('\n');
  return html.replace(pattern, `$1\n${serialized}\n    $2`);
}

function localizeIndex(baseHtml, locale, translation, outputLocale = locale) {
  const config = localeConfig[locale];
  const title = `${translation.catalogPage.seoTitle} | FilamentHub`;
  let html = baseHtml.replace(/<html\b[^>]*\blang="[^"]*"/, (tag) => tag.replace(/lang="[^"]*"/, `lang="${locale}"`));
  html = replaceMetaField(html, 'title', title);
  html = replaceMetaField(html, 'description', translation.catalogPage.seoDescription);
  html = replaceMetaField(html, 'keywords', translation.catalogPage.seoKeywords);
  html = replaceMetaField(html, 'imageAlt', config.imageAlt);
  html = replaceMetaField(html, 'ogLocale', config.ogLocale);
  html = replaceMetaField(html, 'canonicalUrl', `${baseUrl}__FH_CANONICAL_PATH__`);
  html = replaceTitle(html, title);
  html = replaceOgLocaleAlternates(html, config.ogLocale);
  html = replaceLinkHref(html, 'data-seo-base="true"[^>]*rel="canonical"', `${baseUrl}__FH_CANONICAL_PATH__`);
  html = replaceLinkHref(html, 'data-seo-hreflang="x-default"', `${baseUrl}__FH_BASE_PATH__`);
  for (const alternateLocale of Object.keys(localeConfig)) {
    const localizedBase = alternateLocale === 'en'
      ? baseUrl
      : `${baseUrl}/${alternateLocale}`;
    html = replaceLinkHref(
      html,
      `data-seo-hreflang="${alternateLocale}"`,
      `${localizedBase}__FH_BASE_PATH__`,
    );
  }
  html = replaceWebsiteJsonLd(html, outputLocale, translation.catalogPage.seoDescription);
  return html;
}

const baseHtml = await readFile(distIndexPath, 'utf8');
for (const locale of Object.keys(localeConfig)) {
  const translationPath = path.join(frontendRoot, 'src', 'locales', locale, 'translation.json');
  const translation = JSON.parse(await readFile(translationPath, 'utf8'));
  const localized = localizeIndex(baseHtml, locale, translation);
  await writeFile(path.join(frontendRoot, 'dist', `index.${locale}.html`), localized, 'utf8');
  if (locale === 'en') {
    const adaptiveDefault = localizeIndex(baseHtml, locale, translation, 'x-default');
    await writeFile(path.join(frontendRoot, 'dist', 'index.x-default.html'), adaptiveDefault, 'utf8');
  }
}
