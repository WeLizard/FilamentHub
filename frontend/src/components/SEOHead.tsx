/** Компонент для управления SEO meta тегами, Open Graph и Twitter Cards */

import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';

interface SEOHeadProps {
  title?: string;
  description?: string;
  keywords?: string;
  image?: string;
  url?: string;
  type?: 'website' | 'article' | 'profile' | 'product';
  author?: string;
  publishedTime?: string;
  modifiedTime?: string;
  section?: string;
  tags?: string[];
  /** JSON-LD structured data */
  jsonLd?: object;
  /** Дополнительные meta теги */
  additionalMeta?: Array<{ name: string; content: string }>;
  /** Для AI агентов - разрешить индексацию */
  allowAI?: boolean;
}

const DEFAULT_IMAGE = '/logo.svg';
const BASE_URL = 'https://filamenthub.ru';

export const SEOHead: React.FC<SEOHeadProps> = ({
  title,
  description,
  keywords,
  image,
  url,
  type = 'website',
  author,
  publishedTime,
  modifiedTime,
  section,
  tags,
  jsonLd,
  additionalMeta = [],
  allowAI = true,
}) => {
  const { t, i18n } = useTranslation();
  const fullTitle = title ? `${title} | FilamentHub` : t('seo.defaultTitle');
  const fullDescription = description || t('seo.defaultDescription');
  const ogLocale = i18n.language?.startsWith('ru')
    ? 'ru_RU'
    : i18n.language?.startsWith('zh')
      ? 'zh_CN'
      : 'en_US';
  const fullImage = image ? (image.startsWith('http') ? image : `${BASE_URL}${image}`) : `${BASE_URL}${DEFAULT_IMAGE}`;
  const fullUrl = url ? (url.startsWith('http') ? url : `${BASE_URL}${url}`) : BASE_URL;

  useEffect(() => {
    // Обновляем title
    document.title = fullTitle;

    // Удаляем старые meta теги (кроме viewport и charset)
    const existingMeta = document.querySelectorAll('meta[data-seo]');
    existingMeta.forEach((meta) => meta.remove());

    // Reuse the static crawler fallback from index.html instead of leaving
    // duplicate title/description/OG tags in the document after hydration.
    const addMeta = (nameOrProperty: string, content: string, isProperty = false) => {
      const attribute = isProperty ? 'property' : 'name';
      const baseMeta = Array.from(document.head.querySelectorAll<HTMLMetaElement>(`meta[${attribute}]`))
        .find((meta) => (
          meta.getAttribute(attribute) === nameOrProperty
          && meta.dataset.seoBase === 'true'
        ));

      if (baseMeta) {
        if (baseMeta.dataset.seoOriginalContent === undefined) {
          baseMeta.dataset.seoOriginalContent = baseMeta.content;
        }
        baseMeta.content = content;
        baseMeta.dataset.seoManaged = 'true';
        return;
      }

      const meta = document.createElement('meta');
      meta.setAttribute(attribute, nameOrProperty);
      meta.setAttribute('content', content);
      meta.setAttribute('data-seo', 'true');
      document.head.appendChild(meta);
    };

    // Базовые SEO теги
    addMeta('description', fullDescription);
    if (keywords) {
      addMeta('keywords', keywords);
    }
    addMeta('author', author || 'FilamentHub');

    // Open Graph теги
    addMeta('og:title', fullTitle, true);
    addMeta('og:description', fullDescription, true);
    addMeta('og:image', fullImage, true);
    addMeta('og:url', fullUrl, true);
    addMeta('og:type', type, true);
    addMeta('og:site_name', 'FilamentHub', true);
    addMeta('og:locale', ogLocale, true);

    // Для статей
    if (type === 'article') {
      if (author) addMeta('article:author', author, true);
      if (publishedTime) addMeta('article:published_time', publishedTime, true);
      if (modifiedTime) addMeta('article:modified_time', modifiedTime, true);
      if (section) addMeta('article:section', section, true);
      if (tags && tags.length > 0) {
        tags.forEach((tag) => {
          addMeta('article:tag', tag, true);
        });
      }
    }

    // Twitter Card теги
    addMeta('twitter:card', 'summary_large_image');
    addMeta('twitter:title', fullTitle);
    addMeta('twitter:description', fullDescription);
    addMeta('twitter:image', fullImage);
    addMeta('twitter:site', '@FilamentHub'); // Если будет Twitter аккаунт

    // Для AI агентов и поисковых роботов
    if (allowAI) {
      addMeta('robots', 'index, follow, max-image-preview:large, max-snippet:-1, max-video-preview:-1');
      // Разрешаем AI индексацию (Google AI, ChatGPT, и т.д.)
      addMeta('googlebot', 'index, follow');
      addMeta('bingbot', 'index, follow');
      // Для ChatGPT и других AI агентов
      addMeta('ai:index', 'allow');
    } else {
      addMeta('robots', 'noindex, nofollow');
    }

    // Canonical URL
    const baseCanonical = document.querySelector<HTMLLinkElement>('link[rel="canonical"][data-seo-base="true"]');
    if (baseCanonical) {
      if (baseCanonical.dataset.seoOriginalHref === undefined) {
        baseCanonical.dataset.seoOriginalHref = baseCanonical.href;
      }
      baseCanonical.href = fullUrl;
      baseCanonical.dataset.seoManaged = 'true';
    } else {
      const existingCanonical = document.querySelector('link[rel="canonical"][data-seo]');
      if (existingCanonical) existingCanonical.remove();
      const canonical = document.createElement('link');
      canonical.setAttribute('rel', 'canonical');
      canonical.setAttribute('href', fullUrl);
      canonical.setAttribute('data-seo', 'true');
      document.head.appendChild(canonical);
    }

    // Дополнительные meta теги
    additionalMeta.forEach(({ name, content }) => {
      addMeta(name, content);
    });

    // JSON-LD structured data
    if (jsonLd) {
      // Удаляем старый JSON-LD
      const existingJsonLd = document.querySelector('script[type="application/ld+json"][data-seo]');
      if (existingJsonLd) {
        existingJsonLd.remove();
      }

      const script = document.createElement('script');
      script.type = 'application/ld+json';
      script.setAttribute('data-seo', 'true');
      script.textContent = JSON.stringify(jsonLd);
      document.head.appendChild(script);
    }

    // Cleanup при размонтировании
    return () => {
      const metaTags = document.querySelectorAll('meta[data-seo]');
      metaTags.forEach((meta) => meta.remove());
      const managedBaseMeta = document.querySelectorAll<HTMLMetaElement>('meta[data-seo-managed="true"]');
      managedBaseMeta.forEach((meta) => {
        if (meta.dataset.seoOriginalContent !== undefined) {
          meta.content = meta.dataset.seoOriginalContent;
        }
        delete meta.dataset.seoOriginalContent;
        delete meta.dataset.seoManaged;
      });
      const canonicalLink = document.querySelector('link[rel="canonical"][data-seo]');
      if (canonicalLink) canonicalLink.remove();
      const managedBaseCanonical = document.querySelector<HTMLLinkElement>('link[rel="canonical"][data-seo-managed="true"]');
      if (managedBaseCanonical) {
        if (managedBaseCanonical.dataset.seoOriginalHref !== undefined) {
          managedBaseCanonical.href = managedBaseCanonical.dataset.seoOriginalHref;
        }
        delete managedBaseCanonical.dataset.seoOriginalHref;
        delete managedBaseCanonical.dataset.seoManaged;
      }
      const jsonLdScript = document.querySelector('script[type="application/ld+json"][data-seo]');
      if (jsonLdScript) {
        jsonLdScript.remove();
      }
    };
  }, [
    fullTitle,
    fullDescription,
    keywords,
    fullImage,
    fullUrl,
    type,
    author,
    publishedTime,
    modifiedTime,
    section,
    tags,
    jsonLd,
    additionalMeta,
    allowAI,
    ogLocale,
  ]);

  return null; // Компонент не рендерит ничего
};

