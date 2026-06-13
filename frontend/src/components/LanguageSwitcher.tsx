/** Interface language switcher (ru/en).
 *
 * A manual choice here is persisted explicitly to localStorage (i18next's
 * lookup key), so it wins over auto-detection on subsequent visits. Until the
 * user picks a language, i18n falls back to browser detection (see i18n.ts:
 * caches is empty, so auto-detected values are NOT locked in).
 */

import { useTranslation } from 'react-i18next';

// Must match i18next-browser-languagedetector's lookupLocalStorage key.
const LANG_STORAGE_KEY = 'i18nextLng';

const LANGUAGES: { code: string; label: string }[] = [
  { code: 'ru', label: 'Русский' },
  { code: 'en', label: 'English' },
];

interface LanguageSwitcherProps {
  className?: string;
}

export const LanguageSwitcher: React.FC<LanguageSwitcherProps> = ({ className = '' }) => {
  const { i18n } = useTranslation();
  const current = (i18n.language || 'en').toLowerCase().split('-')[0];

  const change = (code: string) => {
    if (code === current) {
      return;
    }
    try {
      localStorage.setItem(LANG_STORAGE_KEY, code);
    } catch {
      // Private mode / storage disabled — language still switches for this session.
    }
    i18n.changeLanguage(code);
  };

  return (
    <div className={`inline-flex items-center gap-1 rounded-lg bg-white/5 border border-white/10 p-1 ${className}`}>
      {LANGUAGES.map(({ code, label }) => {
        const active = current === code;
        return (
          <button
            key={code}
            type="button"
            onClick={() => change(code)}
            aria-pressed={active}
            className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
              active
                ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white shadow'
                : 'text-gray-300 hover:text-white hover:bg-white/10'
            }`}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
};
