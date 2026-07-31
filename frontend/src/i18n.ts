import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

// Import translations
import translationEN from './locales/en/translation.json';
import translationRU from './locales/ru/translation.json';
import translationZH from './locales/zh/translation.json';
import { getPathLocale } from './utils/siteLocale';

const resources = {
  en: {
    translation: translationEN,
  },
  ru: {
    translation: translationRU,
  },
  zh: {
    translation: translationZH,
  },
};

const languageDetector = new LanguageDetector();
languageDetector.addDetector({
  name: 'siteLocalePath',
  lookup: () => getPathLocale(window.location.pathname) ?? undefined,
});

i18n
  .use(languageDetector)
  .use(initReactI18next)
  .init({
    resources,
    supportedLngs: ['en', 'ru', 'zh'],
    fallbackLng: 'en',
    nonExplicitSupportedLngs: true,
    load: 'languageOnly',
    detection: {
      // The OrcaSlicer plugin passes its host UI language as ?lng=. Outside the
      // embedded catalog, an explicit site choice still wins over the browser.
      // A locale-prefixed URL is an explicit, shareable language choice. The
      // OrcaSlicer embed keeps its host-controlled ?lng= fallback on unprefixed
      // routes. Otherwise a saved manual choice wins over browser detection.
      order: ['siteLocalePath', 'querystring', 'localStorage', 'navigator', 'htmlTag'],
      lookupQuerystring: 'lng',
      // Do NOT cache auto-detected language — that would lock the first-visit
      // detection and ignore later browser-language changes. Only an explicit
      // manual choice is persisted (by LanguageSwitcher), so until then the
      // system/browser language keeps driving the UI.
      caches: [],
    },
    debug: false,

    interpolation: {
      escapeValue: false,
    },
  });

const syncHtmlLang = (lng: string) => {
  const base = lng.split('-')[0];
  document.documentElement.lang = base === 'ru' || base === 'zh' ? base : 'en';
};
syncHtmlLang(i18n.language || 'en');
i18n.on('languageChanged', syncHtmlLang);

export default i18n;
