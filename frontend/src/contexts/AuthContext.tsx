/** Context для управления аутентификацией */

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { authAPI } from '../api/client';
import { setToken, setRefreshToken, removeToken, getToken, getRefreshToken } from '../utils/auth';
import type { User } from '../types/api';

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (data: { email: string; username: string; password: string; role: string }) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
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

  // Загружаем пользователя при монтировании (если есть токен)
  useEffect(() => {
    const loadUser = async () => {
      const token = getToken();
      if (token) {
        try {
          const userData = await authAPI.me();
          setUser(userData);
        } catch (error: any) {
          // Токен невалидный или истек, удаляем
          removeToken();
          setUser(null);
          // Не логируем ошибку - это нормально при первом заходе или истекшем токене
        }
      } else {
        setUser(null);
      }
      setIsLoading(false);
    };
    loadUser();
  }, []);

  const login = async (email: string, password: string) => {
    try {
      const tokenData = await authAPI.login({ email, password });
      setToken(tokenData.access_token);
      
      // Сохраняем refresh token если есть
      if (tokenData.refresh_token) {
        setRefreshToken(tokenData.refresh_token);
      }
      
      // Загружаем данные пользователя
      const userData = await authAPI.me();
      setUser(userData);
    } catch (error: any) {
      // Удаляем токен если логин не удался
      removeToken();
      throw error; // Пробрасываем ошибку дальше для обработки в компоненте
    }
  };

  const register = async (data: { email: string; username: string; password: string; role: string }) => {
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

  const logout = () => {
    removeToken();
    setUser(null);
  };

  const refreshUser = async () => {
    if (getToken()) {
      try {
        const userData = await authAPI.me();
        setUser(userData);
      } catch (error) {
        logout();
      }
    }
  };

  const value: AuthContextType = {
    user,
    isLoading,
    isAuthenticated: !!user,
    login,
    register,
    logout,
    refreshUser,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

