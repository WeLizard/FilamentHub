/** Утилиты для работы с аутентификацией */

const AUTH_WEB_MODE = (import.meta.env.VITE_AUTH_WEB_MODE || 'jwt').toLowerCase();

export const isCookieAuthMode = (): boolean => {
  return AUTH_WEB_MODE === 'cookie' || AUTH_WEB_MODE === 'dual';
};

export const isJwtAuthMode = (): boolean => {
  return AUTH_WEB_MODE === 'jwt' || AUTH_WEB_MODE === 'dual';
};

export const isOrcaEmbedded = (): boolean => {
  if (typeof window === 'undefined') {
    return false;
  }
  return Boolean((window as any).filamenthub || (window as any).wx?.postMessage);
};

export const shouldPersistTokensLocally = (): boolean => {
  // В cookie-only web режиме не храним токены в localStorage.
  // В Orca контексте оставляем legacy localStorage для совместимости bridge контракта.
  if (!isCookieAuthMode()) {
    return true;
  }
  return isOrcaEmbedded();
};

export const getToken = (): string | null => {
  return localStorage.getItem('access_token');
};

export const getRefreshToken = (): string | null => {
  return localStorage.getItem('refresh_token');
};

export const setToken = (token: string): void => {
  localStorage.setItem('access_token', token);
};

export const setUserId = (userId: number): void => {
  localStorage.setItem('user_id', userId.toString());
};

export const getUserId = (): number | null => {
  const userId = localStorage.getItem('user_id');
  return userId ? parseInt(userId, 10) : null;
};

export const removeUserId = (): void => {
  localStorage.removeItem('user_id');
};

export const setRefreshToken = (token: string): void => {
  localStorage.setItem('refresh_token', token);
};

export const removeToken = (): void => {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  removeUserId();
};

export const isAuthenticated = (): boolean => {
  return !!getToken();
};

export const getCookieValue = (name: string): string | null => {
  if (typeof document === 'undefined') {
    return null;
  }
  const escapedName = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = document.cookie.match(new RegExp(`(?:^|; )${escapedName}=([^;]*)`));
  if (!match) {
    return null;
  }
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
};

export const getCsrfToken = (): string | null => {
  return getCookieValue(import.meta.env.VITE_AUTH_CSRF_COOKIE_NAME || 'fh_csrf_token');
};
