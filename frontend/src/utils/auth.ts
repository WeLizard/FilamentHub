/** Утилиты для работы с аутентификацией */

export const getToken = (): string | null => {
  return localStorage.getItem('access_token');
};

export const setToken = (token: string): void => {
  localStorage.setItem('access_token', token);
};

export const removeToken = (): void => {
  localStorage.removeItem('access_token');
};

export const isAuthenticated = (): boolean => {
  return !!getToken();
};

