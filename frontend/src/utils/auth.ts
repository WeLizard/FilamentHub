/**
 * Authentication utilities — dual cookie/jwt strategy.
 *
 * Modes (VITE_AUTH_WEB_MODE):
 *  - "jwt"    — tokens in localStorage, Authorization header (default)
 *  - "cookie" — httpOnly cookie set by backend, CSRF token in header
 *  - "dual"   — backend sets both cookie AND returns JWT; web uses cookies,
 *               OrcaSlicer embedded WebView uses JWT (no cookie support in CEF)
 *
 * OrcaSlicer detection: window.filamenthub (C++ bridge) or window.wx.postMessage.
 * When embedded, tokens are always stored locally regardless of mode,
 * because the WebView cannot rely on browser cookie handling.
 */

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
  return Boolean(window.filamenthub || window.wx?.postMessage);
};

const canUseLocalTokenStorage = (): boolean => {
  if (!isCookieAuthMode()) {
    return true;
  }
  return isOrcaEmbedded();
};

export const shouldPersistTokensLocally = (): boolean => {
  return canUseLocalTokenStorage();
};

export const getToken = (): string | null => {
  if (!canUseLocalTokenStorage()) {
    return null;
  }
  return localStorage.getItem('access_token');
};

export const getRefreshToken = (): string | null => {
  if (!canUseLocalTokenStorage()) {
    return null;
  }
  return localStorage.getItem('refresh_token');
};

export const setToken = (token: string): void => {
  if (!canUseLocalTokenStorage()) {
    return;
  }
  localStorage.setItem('access_token', token);
};

export const setUserId = (userId: number): void => {
  if (!canUseLocalTokenStorage()) {
    return;
  }
  localStorage.setItem('user_id', userId.toString());
};

export const getUserId = (): number | null => {
  if (!canUseLocalTokenStorage()) {
    return null;
  }
  const userId = localStorage.getItem('user_id');
  return userId ? parseInt(userId, 10) : null;
};

export const removeUserId = (): void => {
  localStorage.removeItem('user_id');
};

export const setRefreshToken = (token: string): void => {
  if (!canUseLocalTokenStorage()) {
    return;
  }
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

export const clearLegacyLocalAuthStateIfNeeded = (): void => {
  if (isCookieAuthMode() && !isOrcaEmbedded()) {
    removeToken();
  }
};

export const buildAuthenticatedUploadUrl = (filePath: string): string => {
  const normalizedPath = filePath.replace(/^\/+/, '');
  const token = getToken();
  if (token) {
    return `/api/v1/uploads/${normalizedPath}?token=${encodeURIComponent(token)}`;
  }
  return `/api/v1/uploads/${normalizedPath}`;
};
