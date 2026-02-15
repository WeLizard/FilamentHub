/** reCAPTCHA v3 — невидимая капча с серверной проверкой.
 *
 * Site key берётся из VITE_RECAPTCHA_SITE_KEY (.env).
 * Если ключ не задан — компонент не рендерится и onToken не вызывается
 * (бэкенд при пустом RECAPTCHA_SECRET_KEY тоже пропускает проверку).
 */

import { useCallback, useEffect, useRef } from 'react';

const SITE_KEY = import.meta.env.VITE_RECAPTCHA_SITE_KEY as string | undefined;

declare global {
  interface Window {
    grecaptcha: {
      ready: (cb: () => void) => void;
      execute: (siteKey: string, options: { action: string }) => Promise<string>;
    };
  }
}

interface RecaptchaProps {
  /** Вызывается с токеном reCAPTCHA, который нужно отправить на сервер */
  onToken: (token: string) => void;
  /** action label для reCAPTCHA analytics (по умолчанию "register") */
  action?: string;
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

export const Recaptcha: React.FC<RecaptchaProps> = ({ onToken, action = 'register' }) => {
  const called = useRef(false);

  const execute = useCallback(async () => {
    if (!SITE_KEY || called.current) return;
    called.current = true;
    await loadScript();
    window.grecaptcha.ready(async () => {
      try {
        const token = await window.grecaptcha.execute(SITE_KEY, { action });
        onToken(token);
      } catch {
        // Если не удалось — просто не отправляем токен, сервер решит
      }
    });
  }, [onToken, action]);

  useEffect(() => {
    execute();
  }, [execute]);

  // reCAPTCHA v3 невидима — ничего не рендерим
  return null;
};
