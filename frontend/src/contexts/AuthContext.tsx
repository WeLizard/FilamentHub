/** Context для управления аутентификацией */

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { authAPI } from '../api/client';
import { getRefreshToken, getToken, isCookieAuthMode, isOrcaEmbedded, removeToken, setRefreshToken, setToken, setUserId, shouldPersistTokensLocally } from '../utils/auth';
import type { User } from '../types/api';

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  isMaintenanceMode: boolean;
  maintenanceMessage: string | null;
  login: (email: string, password: string) => Promise<void>;
  register: (data: { email: string; username: string; password: string; role: string; recaptcha_token?: string }) => Promise<void>;
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

interface AuthProviderProps {
  children: ReactNode;
}

export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isMaintenanceMode, setIsMaintenanceMode] = useState(false);
  const [maintenanceMessage, setMaintenanceMessage] = useState<string | null>(null);

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
    const loadUser = async () => {
      // Небольшая задержка — C++ инжектирует токен через RunScript в OnLoaded,
      // который может выполниться чуть позже React mount
      const token = getToken();
      const hasSessionCandidate = Boolean(token) || isCookieAuthMode();
      if (hasSessionCandidate) {
        try {
          const userData = await authAPI.me();
          setUser(userData);
          // Если успешно загрузили - сбрасываем maintenance mode
          setIsMaintenanceMode(false);
          setMaintenanceMessage(null);
        } catch (error: any) {
          // Проверяем на maintenance mode (503)
          if (error.response?.status === 503 && error.response?.data?.maintenance_mode) {
            setIsMaintenanceMode(true);
            setMaintenanceMessage(error.response?.data?.message || null);
          } else {
          // Токен/сессия невалидны или истекли
          removeToken();
          setUser(null);
          }
          // Не логируем ошибку - это нормально при первом заходе или истекшем токене
        }
      } else {
        // Нет токена - проверяем maintenance mode через публичный health endpoint
        try {
          const maintenanceStatus = await authAPI.getMaintenanceStatus();
          setIsMaintenanceMode(maintenanceStatus.maintenance_mode);
          setMaintenanceMessage(maintenanceStatus.maintenance_mode ? maintenanceStatus.message : null);
        } catch {
          // Если health endpoint недоступен, не блокируем приложение
          setIsMaintenanceMode(false);
          setMaintenanceMessage(null);
        }
        setUser(null);
      }
      setIsLoading(false);
    };

    // Задержка 100ms — даёт C++ время инжектировать токен через RunScript
    // В обычном браузере токен уже в localStorage, задержка незаметна
    const timer = setTimeout(loadUser, 100);
    return () => clearTimeout(timer);
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
          setUser(null);
        }
      }
    };
    window.addEventListener('storage', handleStorageChange);
    return () => window.removeEventListener('storage', handleStorageChange);
  }, [user]);

  const login = async (email: string, password: string) => {
    try {
      const tokenData = await authAPI.login({ email, password });
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
      setUser(userData);
      
      // Сохраняем user_id в localStorage
      if (userData.id && persistLocally) {
        setUserId(userData.id);
      }
      
      // Отправляем сообщение в OrcaSlicer если запущено там (включая refresh_token)
      if (isOrcaEmbedded() && (window as any).filamenthub?.sendLoginSuccess) {
        (window as any).filamenthub.sendLoginSuccess(tokenData.access_token, userData.id, tokenData.refresh_token);
      }
    } catch (error: any) {
      // Удаляем токен если логин не удался
      removeToken();
      throw error; // Пробрасываем ошибку дальше для обработки в компоненте
    }
  };

  const register = async (data: { email: string; username: string; password: string; role: string; recaptcha_token?: string }) => {
    try {
      // Регистрируем пользователя
      const userResponse = await authAPI.register(data);
      
      // После успешной регистрации автоматически логиним
      try {
        await login(data.email, data.password);
      } catch (loginError: any) {
        // Если автоматический логин не удался, это не критично
        // Пользователь сможет войти вручную
        // Но все равно пробрасываем ошибку регистрации, чтобы пользователь знал об успехе
        console.warn('Auto-login after registration failed:', loginError);
        // Не пробрасываем ошибку логина, т.к. регистрация прошла успешно
      }
      
      // Возвращаем успешный результат регистрации
      return;
    } catch (error: any) {
      // Пробрасываем ошибку дальше для обработки в компоненте
      throw error;
    }
  };

  const logout = async () => {
    // Серверная инвалидация токенов (best-effort — не блокируем UI при ошибке)
    try {
      const refreshToken = getRefreshToken();
      await authAPI.logout(refreshToken);
    } catch {
      // Сервер недоступен или токен уже истёк — всё равно выходим локально
    }
    removeToken();
    setUser(null);
    // Уведомляем C++ (OrcaSlicer) о logout — очистить токен в AppConfig
    try {
      if (typeof window !== 'undefined' && (window as any).wx?.postMessage) {
        (window as any).wx.postMessage(JSON.stringify({ command: 'logout' }));
      }
    } catch {
      // Не в контексте OrcaSlicer — игнорируем
    }
  };

  const refreshUser = async () => {
    if (getToken() || isCookieAuthMode()) {
      try {
        const userData = await authAPI.me();
        setUser(userData);
        // Успешно загрузили - сбрасываем maintenance mode
        setIsMaintenanceMode(false);
        setMaintenanceMessage(null);
      } catch (error: any) {
        // Проверяем на maintenance mode (503)
        if (error.response?.status === 503 && error.response?.data?.maintenance_mode) {
          setIsMaintenanceMode(true);
          setMaintenanceMessage(error.response?.data?.message || null);
        } else {
          logout();
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
    isMaintenanceMode,
    maintenanceMessage,
    login,
    register,
    logout,
    refreshUser,
    clearMaintenanceMode,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};
