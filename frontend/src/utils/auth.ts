/** Утилиты для работы с аутентификацией */

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

