/** Context для управления аутентификацией */

import React, { createContext, useContext, useState, useEffect, useRef, ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { AUTH_SESSION_EXPIRED_EVENT, authAPI, beginAuthSessionTransition, withAuthSessionLock } from '../api/client';
import { getRefreshToken, getToken, hasSessionCandidate, isOrcaEmbedded, removeToken, setRefreshToken, setToken, setUserId, shouldPersistTokensLocally } from '../utils/auth';
import { isPluginEmbed, reportLogoutToPlugin, reportPluginSessionToPlugin, subscribeToPluginAuthRestore, subscribeToPluginLogout } from '../utils/pluginBridge';
import type { LegalAcceptancePayload, RegistrationPayload, Token, User } from '../types/api';

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  unauthenticatedReason: 'session_expired' | null;
  isMaintenanceMode: boolean;
  maintenanceMessage: string | null;
  login: (email: string, password: string) => Promise<void>;
  loginWithToken: (accessToken: string, refreshToken?: string | null) => Promise<User>;
  register: (data: RegistrationPayload) => Promise<void>;
  acceptLegalDocuments: (data: LegalAcceptancePayload) => Promise<User>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  clearMaintenanceMode: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};

const PLUGIN_SESSION_RETRY_MS = 60_000;
const PLUGIN_SESSION_REFRESH_MARGIN_SECONDS = 60;

async function authorizePluginSession(isCurrent: () => boolean): Promise<number | null> {
  if (!isPluginEmbed()) {
    return null;
  }
  try {
    const pluginSession = await authAPI.createPluginSession();
    if (!isCurrent()) return null;
    reportPluginSessionToPlugin(pluginSession.plugin_token);
    return pluginSession.expires_in;
  } catch {
    // The account session remains valid. Retry separately without logging the
    // user out or letting a stale plugin capability block the embedded site.
    return null;
  }
}

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const queryClient = useQueryClient();
  const epoch = useRef(0);
  const mounted = useRef(true);
  const currentUser = useRef<User | null>(null);
  const queriesNeedRefetch = useRef(false);
  const [user, setUser] = useState<User | null>(null);
  const [unauthenticatedReason, setUnauthenticatedReason] = useState<'session_expired' | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isMaintenanceMode, setIsMaintenanceMode] = useState(false);
  const [maintenanceMessage, setMaintenanceMessage] = useState<string | null>(null);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; epoch.current += 1; };
  }, []);

  const clearAccountQueries = () => {
    void queryClient.cancelQueries();
    // Reset observed queries so public views keep their subscriptions. Refetch
    // only after the new identity has updated private queries' enabled guards.
    queryClient.getQueryCache().getAll().forEach((query) => query.reset());
    queryClient.removeQueries({ predicate: (query) => query.getObserversCount() === 0 });
    queryClient.getMutationCache().clear();
    queriesNeedRefetch.current = true;
  };
  const updateUser = (nextUser: User | null) => {
    if (currentUser.current?.id !== nextUser?.id) {
      if (currentUser.current && nextUser) {
        epoch.current += 1;
        beginAuthSessionTransition();
      }
      clearAccountQueries();
    }
    currentUser.current = nextUser;
    if (nextUser) setUnauthenticatedReason(null);
    setUser(nextUser);
  };
  const beginIdentityChange = () => {
    epoch.current += 1;
    beginAuthSessionTransition();
    updateUser(null);
    setIsLoading(false);
    return epoch.current;
  };
  const requireCurrent = (operation: number) => {
    if (!mounted.current || operation !== epoch.current) throw new Error('Authentication operation was superseded');
  };

  const markSessionExpired = () => {
    beginIdentityChange();
    setUnauthenticatedReason('session_expired');
  };

  useEffect(() => {
    const onSessionExpired = (event: Event) => {
      const hadSessionCandidate = (event as CustomEvent<{ hadSessionCandidate: boolean }>).detail?.hadSessionCandidate;
      if (!hadSessionCandidate && !currentUser.current) return;
      markSessionExpired();
    };
    window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, onSessionExpired);
    return () => window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, onSessionExpired);
  }, []);

  useEffect(() => {
    if (queriesNeedRefetch.current) {
      queriesNeedRefetch.current = false;
      void queryClient.refetchQueries({ type: 'active' });
    }
  }, [queryClient, user?.id]);

  // Слушаем глобальное событие maintenance mode от API interceptor
  useEffect(() => {
    const handleMaintenanceMode = (event: CustomEvent<{ enabled: boolean; message: string }>) => {
      if (event.detail.enabled) {
        setIsMaintenanceMode(true);
        setMaintenanceMessage(event.detail.message);
      }
    };

    window.addEventListener('maintenanceMode', handleMaintenanceMode as EventListener);
    return () => {
      window.removeEventListener('maintenanceMode', handleMaintenanceMode as EventListener);
    };
  }, []);

  // Загружаем пользователя при монтировании (если есть токен)
  // Используем небольшую задержку чтобы C++ успел инжектировать токен в localStorage
  useEffect(() => {
    let cancelled = false;
    const operation = epoch.current;
    const isCurrent = () => !cancelled && operation === epoch.current;
    const loadUser = async () => {
      const embeddedOrca = isOrcaEmbedded();
      const waitForEmbeddedToken = async (): Promise<string | null> => {
        if (!embeddedOrca) {
          return getToken();
        }

        const initialToken = getToken();
        if (initialToken) {
          return initialToken;
        }

        const deadline = Date.now() + 2500;
        while (Date.now() < deadline && isCurrent()) {
          await new Promise((resolve) => setTimeout(resolve, 100));
          const token = getToken();
          if (token) {
            return token;
          }
        }

        return null;
      };

      // Небольшая задержка — C++ инжектирует токен через RunScript в OnLoaded,
      // который может выполниться чуть позже React mount
      const token = await waitForEmbeddedToken();
      if (!isCurrent()) return;
      if (token || hasSessionCandidate()) {
        try {
          const userData = await authAPI.me();
          if (!isCurrent()) return;
          updateUser(userData);
          // Если успешно загрузили - сбрасываем maintenance mode
          setIsMaintenanceMode(false);
          setMaintenanceMessage(null);
        } catch (error: any) {
          if (!isCurrent()) return;
          // Проверяем на maintenance mode (503)
          if (error.response?.status === 503 && error.response?.data?.maintenance_mode) {
            setIsMaintenanceMode(true);
            setMaintenanceMessage(error.response?.data?.message || null);
          } else if (error.response?.status === 401) {
            // Токен/сессия невалидны или истекли
            removeToken();
            markSessionExpired();
          } else {
            console.error('Account session check failed', { status: error.response?.status });
          }
        }
      } else {
        // Нет токена - проверяем maintenance mode через публичный health endpoint
        try {
          const maintenanceStatus = await authAPI.getMaintenanceStatus();
          if (!isCurrent()) return;
          setIsMaintenanceMode(maintenanceStatus.maintenance_mode);
          setMaintenanceMessage(maintenanceStatus.maintenance_mode ? maintenanceStatus.message : null);
        } catch {
          if (!isCurrent()) return;
          // Если health endpoint недоступен, не блокируем приложение
          setIsMaintenanceMode(false);
          setMaintenanceMessage(null);
        }
        updateUser(null);
      }
      setIsLoading(false);
    };

    // Задержка 100ms — даёт C++ время инжектировать токен через RunScript
    // В обычном браузере токен уже в localStorage, задержка незаметна
    const timer = setTimeout(loadUser, 100);
    return () => { cancelled = true; clearTimeout(timer); };
  }, []);

  // Слушаем изменения localStorage (C++ может инжектировать токен после загрузки)
  useEffect(() => {
    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === 'access_token') {
        if (e.newValue && !user) {
          // Токен появился (C++ инжектировал) — загружаем пользователя
          refreshUser();
        } else if (!e.newValue && user) {
          // Токен удалён — logout
          beginIdentityChange();
        }
      }
    };
    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, [user]);

  // Выход по кнопке в тулбаре шелла плагина (рядом с ником)
  useEffect(() => {
    if (!isPluginEmbed()) {
      return;
    }
    return subscribeToPluginLogout(() => {
      logout();
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Внешний OAuth (Google/Yandex) идёт в системном браузере; шелл возвращает
  // account-сессию в iframe через auth-restore. Входим ею как при обычном логине.
  useEffect(() => {
    if (!isPluginEmbed()) {
      return;
    }
    return subscribeToPluginAuthRestore(({ accessToken, refreshToken }) => {
      void loginWithToken(accessToken, refreshToken);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Plugin capabilities are deliberately short-lived and cannot authenticate
  // against regular account endpoints. Mint one whenever an authenticated
  // embed session appears (including cookie-restored sessions after a plugin
  // update), then refresh it before expiry while the window stays open.
  useEffect(() => {
    if (!user || user.legal_onboarding_required || !isPluginEmbed()) {
      return;
    }

    let cancelled = false;
    const operation = epoch.current;
    let refreshTimer: ReturnType<typeof setTimeout> | undefined;

    const refreshPluginSession = async () => {
      const expiresIn = await authorizePluginSession(() => !cancelled && operation === epoch.current);
      if (cancelled || operation !== epoch.current) {
        return;
      }
      const delay = expiresIn
        ? Math.max(
            PLUGIN_SESSION_RETRY_MS,
            (expiresIn - PLUGIN_SESSION_REFRESH_MARGIN_SECONDS) * 1000,
          )
        : PLUGIN_SESSION_RETRY_MS;
      refreshTimer = setTimeout(refreshPluginSession, delay);
    };

    void refreshPluginSession();
    return () => {
      cancelled = true;
      if (refreshTimer !== undefined) {
        clearTimeout(refreshTimer);
      }
    };
  }, [user?.id, user?.legal_onboarding_required]);

  // Вход и регистрация заканчиваются одинаково: сервер выдал сессию, дальше её
  // нужно сохранить и представиться. Общее место, чтобы не разошлись.
  const establishSession = async (tokenData: Token, operation: number) => {
    requireCurrent(operation);
    const persistLocally = shouldPersistTokensLocally();
    if (persistLocally) {
      setToken(tokenData.access_token);
    }

    // Сохраняем refresh token если есть
    if (tokenData.refresh_token && persistLocally) {
      setRefreshToken(tokenData.refresh_token);
    }

    // Загружаем данные пользователя
    const userData = await authAPI.me();
    requireCurrent(operation);
    updateUser(userData);

    // Сохраняем user_id в localStorage
    if (userData.id && persistLocally) {
      setUserId(userData.id);
    }

    // Отправляем сообщение в OrcaSlicer если запущено там (включая refresh_token)
    if (isOrcaEmbedded() && window.filamenthub?.sendLoginSuccess) {
      window.filamenthub.sendLoginSuccess(tokenData.access_token, userData.id, tokenData.refresh_token ?? '');
    }
  };

  const login = async (email: string, password: string) => {
    const operation = beginIdentityChange();
    try {
      await establishSession(await authAPI.login({ email, password }), operation);
    } catch (error: any) {
      // Удаляем токен если логин не удался
      if (operation === epoch.current) removeToken();
      throw error; // Пробрасываем ошибку дальше для обработки в компоненте
    }
  };

  const loginWithToken = async (accessToken: string, refreshToken?: string | null) => {
    const operation = beginIdentityChange();
    try {
      const persistLocally = shouldPersistTokensLocally();
      // Wait for a pending logout before restoring externally supplied credentials.
      // Do not hold the lock during /me, which may itself need session refresh.
      await withAuthSessionLock(async () => {
        requireCurrent(operation);
        if (persistLocally) setToken(accessToken);
        if (refreshToken && persistLocally) setRefreshToken(refreshToken);
      });
      requireCurrent(operation);
      const userData = await authAPI.me();
      requireCurrent(operation);
      updateUser(userData);
      if (userData.id && persistLocally) {
        setUserId(userData.id);
      }
      return userData;
    } catch (error: any) {
      if (operation === epoch.current) removeToken();
      throw error;
    }
  };

  const register = async (data: RegistrationPayload) => {
    const operation = beginIdentityChange();
    try {
      // Регистрация сразу отдаёт сессию: отдельный вход следом заставлял сервер
      // второй раз проверять тот же пароль.
      const tokenData = await authAPI.register(data);

      try {
        await establishSession(tokenData, operation);
      } catch (sessionError: any) {
        if (operation !== epoch.current) throw sessionError;
        console.warn('Session after registration failed', { status: sessionError.response?.status });
        removeToken();
        const error = new Error('Registration succeeded but the session could not be opened') as Error & {
          registrationSucceeded: true;
          cause?: unknown;
        };
        error.registrationSucceeded = true;
        error.cause = sessionError;
        throw error;
      }

      return;
    } catch (error: any) {
      // Пробрасываем ошибку дальше для обработки в компоненте
      throw error;
    }
  };

  const acceptLegalDocuments = async (data: LegalAcceptancePayload): Promise<User> => {
    const operation = epoch.current;
    const userData = await authAPI.acceptLegalDocuments(data);
    requireCurrent(operation);
    updateUser(userData);
    return userData;
  };

  const logout = async () => {
    setUnauthenticatedReason(null);
    const operation = beginIdentityChange();
    // Серверная инвалидация токенов (best-effort — не блокируем UI при ошибке)
    try {
      const refreshToken = getRefreshToken();
      await authAPI.logout(refreshToken);
    } catch {
      // Сервер недоступен или токен уже истёк — всё равно выходим локально
    }
    if (operation !== epoch.current) return;
    removeToken();
    // Уведомляем C++ (OrcaSlicer) о logout — очистить токен в AppConfig
    try {
      if (typeof window !== 'undefined' && window.wx?.postMessage) {
        window.wx.postMessage(JSON.stringify({ command: 'logout' }));
      }
    } catch {
      // Не в контексте OrcaSlicer — игнорируем
    }
    // В iframe плагина — плагин удаляет сохранённые токены
    reportLogoutToPlugin();
  };

  const refreshUser = async () => {
    const operation = epoch.current;
    if (hasSessionCandidate()) {
      try {
        const userData = await authAPI.me();
        if (operation !== epoch.current) return;
        updateUser(userData);
        // Успешно загрузили - сбрасываем maintenance mode
        setIsMaintenanceMode(false);
        setMaintenanceMessage(null);
      } catch (error: any) {
        if (operation !== epoch.current) return;
        // Проверяем на maintenance mode (503)
        if (error.response?.status === 503 && error.response?.data?.maintenance_mode) {
          setIsMaintenanceMode(true);
          setMaintenanceMessage(error.response?.data?.message || null);
        } else if (error.response?.status === 401) {
          markSessionExpired();
          removeToken();
        } else {
          console.error('Account session check failed', { status: error.response?.status });
        }
      }
    }
  };

  const clearMaintenanceMode = () => {
    setIsMaintenanceMode(false);
    setMaintenanceMessage(null);
  };

  const value: AuthContextType = {
    user,
    isLoading,
    isAuthenticated: !!user,
    unauthenticatedReason,
    isMaintenanceMode,
    maintenanceMessage,
    login,
    loginWithToken,
    register,
    acceptLegalDocuments,
    logout,
    refreshUser,
    clearMaintenanceMode,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
