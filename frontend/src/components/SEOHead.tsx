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
  const ogLocale = i18n.language?.startsWith('ru') ? 'ru_RU' : 'en_US';
  const fullImage = image ? (image.startsWith('http') ? image : `${BASE_URL}${image}`) : `${BASE_URL}${DEFAULT_IMAGE}`;
  const fullUrl = url ? (url.startsWith('http') ? url : `${BASE_URL}${url}`) : BASE_URL;

  useEffect(() => {
    // Обновляем title
    document.title = fullTitle;

    // Удаляем старые meta теги (кроме viewport и charset)
    const existingMeta = document.querySelectorAll('meta[data-seo]');
    existingMeta.forEach((meta) => meta.remove());

    // Создаём функцию для добавления meta тега
    const addMeta = (nameOrProperty: string, content: string, isProperty = false) => {
      const meta = document.createElement('meta');
      if (isProperty) {
        meta.setAttribute('property', nameOrProperty);
      } else {
        meta.setAttribute('name', nameOrProperty);
      }
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
    const existingCanonical = document.querySelector('link[rel="canonical"][data-seo]');
    if (existingCanonical) existingCanonical.remove();
    const canonical = document.createElement('link');
    canonical.setAttribute('rel', 'canonical');
    canonical.setAttribute('href', fullUrl);
    canonical.setAttribute('data-seo', 'true');
    document.head.appendChild(canonical);

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
      const canonicalLink = document.querySelector('link[rel="canonical"][data-seo]');
      if (canonicalLink) canonicalLink.remove();
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

