/** API Client для интеграции с бэкендом */

import axios from 'axios';
import type { Brand, Filament, Preset, User, Token, RefreshTokenRequest, RefreshTokenResponse, ListResponse } from '../types/api';
import { getRefreshToken, setToken, setRefreshToken, removeToken } from '../utils/auth';

const API_BASE_URL = '/api/v1';

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Добавляем токен в запросы
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Переменная для предотвращения множественных запросов refresh
let isRefreshing = false;
let failedQueue: Array<{ resolve: (value?: any) => void; reject: (reason?: any) => void }> = [];

const processQueue = (error: any, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      prom.resolve(token);
    }
  });
  
  failedQueue = [];
};

// Обработка ошибок ответа
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    
    // Если токен истек или невалидный (401), пытаемся обновить
    if (error.response?.status === 401 && !originalRequest._retry) {
      if (isRefreshing) {
        // Если уже обновляем токен, ждем результата
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject });
        }).then((token) => {
          originalRequest.headers.Authorization = `Bearer ${token}`;
          return api(originalRequest);
        }).catch((err) => {
          return Promise.reject(err);
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      const refreshToken = getRefreshToken();
      
      if (!refreshToken) {
        // Нет refresh token, удаляем токены и перенаправляем
        removeToken();
        if (!window.location.pathname.includes('/auth')) {
          window.location.reload();
        }
        processQueue(error, null);
        isRefreshing = false;
        return Promise.reject(error);
      }

      try {
        // Пытаемся обновить токен
        const response = await axios.post<RefreshTokenResponse>(
          `${API_BASE_URL}/auth/refresh`,
          { refresh_token: refreshToken } as RefreshTokenRequest,
          { baseURL: '' } // Используем полный URL
        );
        
        const { access_token } = response.data;
        setToken(access_token);
        
        // Обновляем заголовок оригинального запроса
        originalRequest.headers.Authorization = `Bearer ${access_token}`;
        
        // Обрабатываем очередь запросов
        processQueue(null, access_token);
        isRefreshing = false;
        
        // Повторяем оригинальный запрос
        return api(originalRequest);
      } catch (refreshError: any) {
        // Refresh token невалидный, удаляем токены
        removeToken();
        processQueue(refreshError, null);
        isRefreshing = false;
        
        if (!window.location.pathname.includes('/auth')) {
          window.location.reload();
        }
        return Promise.reject(refreshError);
      }
    }
    
    return Promise.reject(error);
  }
);

// Auth API
export const authAPI = {
  register: async (data: { email: string; username: string; password: string; role: string }) => {
    const response = await api.post<User>('/auth/register', data);
    return response.data;
  },

  login: async (data: { email: string; password: string }) => {
    const response = await api.post<Token>('/auth/login', data);
    return response.data;
  },

  refresh: async (refreshToken: string) => {
    const response = await api.post<RefreshTokenResponse>('/auth/refresh', {
      refresh_token: refreshToken,
    } as RefreshTokenRequest);
    return response.data;
  },

  me: async () => {
    const response = await api.get<User>('/auth/me');
    return response.data;
  },

  generateApiKey: async () => {
    const response = await api.post<{ api_key: string }>('/auth/api-key');
    return response.data;
  },
};

// Brands API
export const brandsAPI = {
  list: async (params?: { page?: number; size?: number; active_only?: boolean }) => {
    const response = await api.get<ListResponse<Brand>>('/brands/', { params });
    return response.data;
  },

  get: async (id: number) => {
    const response = await api.get<Brand>(`/brands/${id}`);
    return response.data;
  },

  create: async (data: { name: string; slug: string; description?: string; website?: string; logo_url?: string }) => {
    const response = await api.post<Brand>('/brands/', data);
    return response.data;
  },
};

// Filaments API
export const filamentsAPI = {
  list: async (params?: {
    page?: number;
    size?: number;
    active_only?: boolean;
    brand_id?: number;
    material_type?: string;
  }) => {
    const response = await api.get<ListResponse<Filament>>('/filaments/', { params });
    return response.data;
  },

  get: async (id: number) => {
    const response = await api.get<Filament>(`/filaments/${id}`);
    return response.data;
  },

  getPresets: async (id: number, params?: { page?: number; size?: number; is_official?: boolean }) => {
    const response = await api.get<ListResponse<Preset>>(`/filaments/${id}/presets`, { params });
    return response.data;
  },

  create: async (data: {
    brand_id: number;
    name: string;
    material_type: string;
    color_name?: string;
    color_hex?: string;
    diameter?: number;
    density?: number;
    price_per_kg?: number;
    spool_weight?: number;
    description?: string;
  }) => {
    const response = await api.post<Filament>('/filaments/', data);
    return response.data;
  },

  update: async (id: number, data: Partial<{
    name?: string;
    material_type?: string;
    color_name?: string;
    color_hex?: string;
    diameter?: number;
    density?: number;
    price_per_kg?: number;
    spool_weight?: number;
    description?: string;
    active?: boolean;
  }>) => {
    const response = await api.patch<Filament>(`/filaments/${id}`, data);
    return response.data;
  },

  delete: async (id: number) => {
    await api.delete(`/filaments/${id}`);
  },
};

// Presets API
export const presetsAPI = {
  list: async (params?: {
    page?: number;
    size?: number;
    active_only?: boolean;
    filament_id?: number;
    is_official?: boolean;
  }) => {
    const response = await api.get<ListResponse<Preset>>('/presets/', { params });
    return response.data;
  },

  get: async (id: number) => {
    const response = await api.get<Preset>(`/presets/${id}`);
    return response.data;
  },

  recommend: async (filament_id: number) => {
    const response = await api.get(`/presets/recommend`, { params: { filament_id } });
    return response.data;
  },

  create: async (data: {
    filament_id: number;
    name: string;
    description?: string;
    is_official: boolean;
    extruder_temp: number;
    bed_temp: number;
    print_speed: number;
    travel_speed?: number;
    layer_height?: number;
    first_layer_height?: number;
    flow_rate?: number;
    fan_speed?: number;
    retraction_length?: number;
    retraction_speed?: number;
  }) => {
    const response = await api.post<Preset>('/presets/', data);
    return response.data;
  },

  update: async (id: number, data: Partial<{
    name?: string;
    description?: string;
    extruder_temp?: number;
    bed_temp?: number;
    print_speed?: number;
    travel_speed?: number;
    layer_height?: number;
    first_layer_height?: number;
    flow_rate?: number;
    fan_speed?: number;
    retraction_length?: number;
    retraction_speed?: number;
    active?: boolean;
  }>) => {
    const response = await api.patch<Preset>(`/presets/${id}`, data);
    return response.data;
  },

  delete: async (id: number) => {
    await api.delete(`/presets/${id}`);
  },
};

// Calculator API
export const calculatorAPI = {
  estimate: async (data: {
    weight_g: number;
    time_sec: number;
    price_per_kg: number;
    electricity_cost_per_kwh?: number;
    printer_power_w?: number;
  }) => {
    const response = await api.post('/calculator/estimate', data);
    return response.data;
  },
};

export default api;

