import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

// Import translations
import translationEN from './locales/en/translation.json';
import translationRU from './locales/ru/translation.json';

const resources = {
  en: {
    translation: translationEN,
  },
  ru: {
    translation: translationRU,
  },
};

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    supportedLngs: ['en', 'ru'],
    fallbackLng: 'en',
    nonExplicitSupportedLngs: true,
    load: 'languageOnly',
    detection: {
      // Read order: an explicit user choice (written to localStorage by
      // LanguageSwitcher) wins; otherwise fall back to the browser language.
      order: ['localStorage', 'navigator', 'htmlTag'],
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
  document.documentElement.lang = base === 'ru' ? 'ru' : 'en';
};
syncHtmlLang(i18n.language || 'en');
i18n.on('languageChanged', syncHtmlLang);

export default i18n;
