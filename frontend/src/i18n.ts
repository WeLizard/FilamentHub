import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';
import { getPathLocale } from './utils/siteLocale';

type SupportedLocale = 'en' | 'ru' | 'zh';

const localeLoaders: Record<SupportedLocale, () => Promise<{ default: Record<string, unknown> }>> = {
  en: () => import('./locales/en/translation.json'),
  ru: () => import('./locales/ru/translation.json'),
  zh: () => import('./locales/zh/translation.json'),
};

const normalizeLocale = (language: string): SupportedLocale => {
  const base = language.toLowerCase().split('-')[0];
  return base === 'ru' || base === 'zh' ? base : 'en';
};

const translationBackend = {
  type: 'backend' as const,
  init: () => undefined,
  read: (
    language: string,
    _namespace: string,
    callback: (error: Error | null, resources?: Record<string, unknown>) => void,
  ) => {
    localeLoaders[normalizeLocale(language)]()
      .then((module) => callback(null, module.default))
      .catch((error: unknown) => callback(error instanceof Error ? error : new Error(String(error))));
  },
};

const languageDetector = new LanguageDetector();
languageDetector.addDetector({
  name: 'siteLocalePath',
  lookup: () => getPathLocale(window.location.pathname) ?? undefined,
});

export const i18nReady = i18n
  .use(languageDetector)
  .use(translationBackend)
  .use(initReactI18next)
  .init({
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
i18n.on('languageChanged', syncHtmlLang);
void i18nReady.then(() => syncHtmlLang(i18n.language || 'en'));

export default i18n;
