/** reCAPTCHA v3 — preload script + helper для получения свежего токена перед submit.
 *
 * Site key берётся из VITE_RECAPTCHA_SITE_KEY (.env).
 * Если ключ не задан — helper возвращает null
 * (бэкенд при пустом RECAPTCHA_SECRET_KEY тоже пропускает проверку).
 */

import { useEffect } from 'react';

const SITE_KEY = import.meta.env.VITE_RECAPTCHA_SITE_KEY as string | undefined;

declare global {
  interface Window {
    grecaptcha: {
      ready: (cb: () => void) => void;
      execute: (siteKey: string, options: { action: string }) => Promise<string>;
    };
  }
}

let scriptLoaded = false;

function loadScript(): Promise<void> {
  if (scriptLoaded || !SITE_KEY) return Promise.resolve();
  return new Promise((resolve) => {
    if (document.querySelector('script[src*="recaptcha/api.js"]')) {
      scriptLoaded = true;
      resolve();
      return;
    }
    const s = document.createElement('script');
    s.src = `https://www.google.com/recaptcha/api.js?render=${SITE_KEY}`;
    s.async = true;
    s.onload = () => {
      scriptLoaded = true;
      resolve();
    };
    document.head.appendChild(s);
  });
}

export async function getRecaptchaToken(action = 'register'): Promise<string | null> {
  if (!SITE_KEY) {
    return null;
  }

  await loadScript();

  if (!window.grecaptcha) {
    return null;
  }

  return new Promise((resolve) => {
    window.grecaptcha.ready(async () => {
      try {
        const token = await window.grecaptcha.execute(SITE_KEY, { action });
        resolve(token);
      } catch {
        resolve(null);
      }
    });
  });
}

interface RecaptchaProps {
  /** action label для reCAPTCHA analytics (по умолчанию "register") */
  action?: string;
}

export const Recaptcha: React.FC<RecaptchaProps> = () => {
  useEffect(() => {
    void loadScript();
  }, []);

  // reCAPTCHA v3 невидима — ничего не рендерим
  return null;
};
