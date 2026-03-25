/** API Client для интеграции с бэкендом */

import axios from 'axios';
import type { Brand, BrandRequest, BrandRequestStatus, Filament, FilamentVisualSettings, FilamentReview, FilamentRatingStats, Notification, NotificationListResponse, Preset, RecommendedPreset, Printer, PrinterProfile, PrintProfile, PrinterRequest, User, Token, RefreshTokenRequest, RefreshTokenResponse, ListResponse, AccountDeletionStats, UserSavedPreset, CalculatorEstimateRequest, CalculatorEstimateResponse, CalculatorProfileResponse, CalculatorProfileUpdate, Feedback, FeedbackListResponse, FeedbackType, CompatiblePrinter, CompatibleFilament, DownloadVersion, DownloadVersionsResponse, WikiCategory, WikiCategoryListResponse, WikiArticle, WikiArticleListResponse, WikiFeedbackStats, WikiFeedbackCreate, WikiFeedback } from '../types/api';
import { getCsrfToken, getRefreshToken, isCookieAuthMode, isJwtAuthMode, isOrcaEmbedded, removeToken, setToken, shouldPersistTokensLocally } from '../utils/auth';

const API_BASE_URL = '/api/v1';
const COOKIE_AUTH_MODE = isCookieAuthMode();
const JWT_AUTH_MODE = isJwtAuthMode();
const CSRF_HEADER_NAME = import.meta.env.VITE_AUTH_CSRF_HEADER_NAME || 'X-CSRF-Token';
const canUseCookieSession = (): boolean => COOKIE_AUTH_MODE && !isOrcaEmbedded();

const api = axios.create({
  baseURL: API_BASE_URL,
  withCredentials: canUseCookieSession(),
  headers: {
    'Content-Type': 'application/json',
  },
});

/** Уведомить C++ (OrcaSlicer) о logout — очистить токен в AppConfig */
const notifyCppLogout = () => {
  try {
    if (typeof window !== 'undefined' && window.wx?.postMessage) {
      window.wx.postMessage(JSON.stringify({ command: 'logout' }));
    }
  } catch {
    // Не в контексте OrcaSlicer — игнорируем
  }
};

// Добавляем токен в запросы
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token && JWT_AUTH_MODE) {
    config.headers.Authorization = `Bearer ${token}`;
  }

  const method = (config.method || 'GET').toUpperCase();
  const hasBearer = Boolean(config.headers?.Authorization);
  if (canUseCookieSession() && !hasBearer && ['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    const csrfToken = getCsrfToken();
    if (csrfToken) {
      config.headers[CSRF_HEADER_NAME] = csrfToken;
    }
  }

  return config;
});

// Переменная для предотвращения множественных запросов refresh
let isRefreshing = false;
let failedQueue: Array<{ 
  resolve: (value?: any) => void; 
  reject: (reason?: any) => void;
  config: any;
}> = [];

const processQueue = (error: any, token: string | null = null) => {
  failedQueue.forEach((prom) => {
    if (error) {
      prom.reject(error);
    } else {
      if (token) {
        prom.config.headers.Authorization = `Bearer ${token}`;
      }
      prom.resolve(api(prom.config));
    }
  });
  
  failedQueue = [];
};

// Обработка ошибок ответа
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    // Network error — no response received (internet down, server unreachable, DNS failure)
    if (!error.response) {
      const isTimeout = error.code === 'ECONNABORTED' || error.code === 'ERR_CANCELED';
      const code = isTimeout ? 'ERR_REQUEST_TIMEOUT' : 'ERR_NETWORK';
      // Inject structured error so translateApiError can handle it uniformly
      error.response = {
        status: 0,
        statusText: 'Network Error',
        headers: {},
        config: error.config,
        data: { detail: { code } },
      };
      return Promise.reject(error);
    }

    // Проверяем на maintenance mode (503)
    if (error.response?.status === 503 && error.response?.data?.maintenance_mode) {
      // Dispatch custom event для AuthContext
      window.dispatchEvent(new CustomEvent('maintenanceMode', {
        detail: {
          enabled: true,
          message: error.response?.data?.message || 'Site is temporarily unavailable. Maintenance in progress.',
        },
      }));
    }
    
    const originalRequest = error.config;
    
    // Если токен истек или невалидный (401), пытаемся обновить
    // НО: не обрабатываем ошибки авторизации (login/register) - они должны обрабатываться в компонентах
    const isAuthEndpoint = originalRequest?.url?.includes('/auth/login') ||
                            originalRequest?.url?.includes('/auth/register') ||
                            originalRequest?.url?.includes('/auth/refresh') ||
                            originalRequest?.url?.includes('/auth/oauth/');
    
    // Для /auth/me: если токена нет, это нормально (пользователь не авторизован)
    // Не показываем ошибку в консоли и не пытаемся обновить токен
    const isMeEndpoint = originalRequest?.url?.includes('/auth/me');
    const hasToken = Boolean(localStorage.getItem('access_token'));
    const cookieSessionAvailable = canUseCookieSession();
    
    if (isMeEndpoint && !hasToken && !cookieSessionAvailable) {
      // Токена нет - это нормально, просто возвращаем ошибку без логирования
      return Promise.reject(error);
    }
    
    const shouldTryRefreshForMe = isMeEndpoint && (hasToken || cookieSessionAvailable);

    // Не обрабатываем повторно запросы, которые уже были повторены
    if (error.response?.status === 401 && !originalRequest._retry && !isAuthEndpoint && (!isMeEndpoint || shouldTryRefreshForMe)) {
      if (isRefreshing) {
        // Если уже обновляем токен, ждем результата
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject, config: originalRequest });
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      const refreshToken = getRefreshToken();
      
      if (!refreshToken && !cookieSessionAvailable) {
        // Нет refresh token, удаляем токены и перенаправляем
        // Только если это не запрос авторизации и не админ панель
        removeToken();
        // Уведомляем C++ о logout (401 без refresh token)
        notifyCppLogout();
        const isAdminPage = window.location.pathname.includes('/admin');
        if (!isMeEndpoint && !window.location.pathname.includes('/auth') && !isAdminPage) {
          window.location.reload();
        }
        processQueue(error, null);
        isRefreshing = false;
        return Promise.reject(error);
      }

      try {
        // Пытаемся обновить токен
        const refreshPayload = refreshToken
          ? ({ refresh_token: refreshToken } as RefreshTokenRequest)
          : undefined;

        const response = await axios.post<RefreshTokenResponse>(
          `${API_BASE_URL}/auth/refresh`,
          refreshPayload,
          {
            baseURL: '', // Используем полный URL
            withCredentials: cookieSessionAvailable,
            headers: cookieSessionAvailable
              ? (() => {
                  const csrfToken = getCsrfToken();
                  return csrfToken ? { [CSRF_HEADER_NAME]: csrfToken } : {};
                })()
              : undefined,
          }
        );
        
        const { access_token } = response.data;
        
        if (!access_token) {
          throw new Error('No access token received from refresh endpoint');
        }

        if (JWT_AUTH_MODE && shouldPersistTokensLocally()) {
          setToken(access_token);
          // Обновляем заголовок оригинального запроса
          originalRequest.headers.Authorization = `Bearer ${access_token}`;
        } else if (originalRequest.headers?.Authorization) {
          delete originalRequest.headers.Authorization;
        }
        
        // Обрабатываем очередь запросов
        processQueue(null, JWT_AUTH_MODE && shouldPersistTokensLocally() ? access_token : null);
        isRefreshing = false;
        
        // Повторяем оригинальный запрос
        return api(originalRequest);
      } catch (refreshError: any) {
        // Refresh token невалидный, удаляем токены
        removeToken();
        // Уведомляем C++ о logout (refresh failed)
        notifyCppLogout();
        processQueue(refreshError, null);
        isRefreshing = false;
        
        // Не перезагружаем страницу если мы в админке или на странице авторизации
        // И не делаем reload для /auth/me, иначе возникает вечный цикл на гостевой сессии.
        const isAdminPage = window.location.pathname.includes('/admin');
        if (!isMeEndpoint && !window.location.pathname.includes('/auth') && !isAdminPage) {
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
  register: async (data: { email: string; username: string; password: string; role: string; recaptcha_token?: string }) => {
    const response = await api.post<User>('/auth/register', data);
    return response.data;
  },

  login: async (data: { email: string; password: string }) => {
    const response = await api.post<Token>('/auth/login', data);
    return response.data;
  },

  refresh: async (refreshToken?: string | null) => {
    const payload = refreshToken
      ? ({ refresh_token: refreshToken } as RefreshTokenRequest)
      : undefined;
    const response = await api.post<RefreshTokenResponse>('/auth/refresh', payload);
    return response.data;
  },

  logout: async (refreshToken?: string | null) => {
    await api.post('/auth/logout', refreshToken ? { refresh_token: refreshToken } : undefined);
  },

  getOAuthUrl: async (provider: string) => {
    const response = await api.get<{ url: string; state: string }>(`/auth/oauth/${provider}/url`);
    return response.data;
  },

  oauthCallback: async (provider: string, code: string, state: string) => {
    const response = await api.post<Token>(`/auth/oauth/${provider}/callback`, { code, state });
    return response.data;
  },

  me: async () => {
    const response = await api.get<User>('/auth/me');
    return response.data;
  },

  getMaintenanceStatus: async (): Promise<{ maintenance_mode: boolean; message: string | null }> => {
    const response = await axios.get<{ maintenance_mode?: boolean; maintenance_message?: string | null }>(
      '/health',
      { baseURL: '' }
    );
    return {
      maintenance_mode: Boolean(response.data.maintenance_mode),
      message: response.data.maintenance_message ?? null,
    };
  },

  updateProfile: async (data: Partial<{ email: string; username: string; full_name: string | null; bio: string | null; password: string; brand_id: number | null }>) => {
    const response = await api.patch<User>('/auth/me', data);
    return response.data;
  },

  generateApiKey: async () => {
    const response = await api.post<{ api_key: string }>('/auth/api-key');
    return response.data;
  },

  getDeletionStats: async (): Promise<AccountDeletionStats> => {
    const response = await api.get<AccountDeletionStats>('/auth/deletion-stats');
    return response.data;
  },

  getPresetsStats: async (): Promise<{ total_presets: number; synced_presets: number }> => {
    const response = await api.get<{ total_presets: number; synced_presets: number }>('/auth/me/presets-stats');
    return response.data;
  },

  deleteAccount: async (data: { 
    delete_reviews: boolean; 
    delete_brand_if_sole_representative: boolean; 
    password_confirm: string;
  }) => {
    await api.delete('/auth/me', {
      data,
    });
  },

  forgotPassword: async (email: string) => {
    const response = await api.post<{ message: string }>('/auth/forgot-password', { email });
    return response.data;
  },

  resetPassword: async (token: string, newPassword: string) => {
    const response = await api.post<{ message: string }>('/auth/reset-password', {
      token,
      new_password: newPassword,
    });
    return response.data;
  },

  updateSettings: async (data: {
    allow_filament_presets_import?: boolean;
    allow_filament_presets_export?: boolean;
    allow_printer_profiles_import?: boolean;
    allow_printer_profiles_export?: boolean;
    allow_print_profiles_import?: boolean;
    allow_print_profiles_export?: boolean;
  }) => {
    const response = await api.patch<User>('/auth/me/settings', data);
    return response.data;
  },

  updatePassword: async (data: {
    current_password?: string;
    new_password: string;
  }) => {
    const response = await api.patch<User>('/auth/me/password', data);
    return response.data;
  },

  updateEmail: async (data: {
    new_email: string;
  }) => {
    const response = await api.patch<{ message: string }>('/auth/me/email', data);
    return response.data;
  },

  confirmEmailChange: async (token: string) => {
    const response = await api.post<{ message: string }>(`/auth/confirm-email-change?token=${encodeURIComponent(token)}`);
    return response.data;
  },

  updateUsername: async (data: {
    new_username: string;
  }) => {
    const response = await api.patch<User>('/auth/me/username', data);
    return response.data;
  },
};

// Brands API
export const brandsAPI = {
  list: async (params?: { page?: number; size?: number; active_only?: boolean; search?: string }) => {
    const response = await api.get<ListResponse<Brand>>('/brands/', { params });
    return response.data;
  },

  get: async (id: number, includeEmployeesCount?: boolean) => {
    const response = await api.get<Brand>(`/brands/${id}`, { 
      params: includeEmployeesCount ? { include_employees_count: true } : undefined 
    });
    return response.data;
  },

  create: async (data: { name: string; slug: string; description?: string; website?: string; logo_url?: string }) => {
    const response = await api.post<Brand>('/brands/', data);
    return response.data;
  },

  update: async (id: number, data: { description?: string | null; website?: string | null; logo_url?: string | null }) => {
    const response = await api.patch<Brand>(`/brands/${id}`, data);
    return response.data;
  },

  uploadLogo: async (id: number, file: File): Promise<Brand> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post<Brand>(`/brands/${id}/logo`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },
};

// Filaments API
export const filamentsAPI = {
  getMaterialTypes: async (): Promise<string[]> => {
    const response = await api.get<string[]>('/filaments/material-types');
    return response.data;
  },
  list: async (params?: {
    page?: number;
    size?: number;
    active_only?: boolean;
    brand_id?: number;
    material_type?: string;
    search?: string;
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
    visual_settings?: FilamentVisualSettings | null;
    color_name?: string;
    color_hex?: string;
    diameter?: number;
    density?: number;
    price_per_kg?: number;
    spool_weight?: number;
    empty_spool_weight_g?: number;
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
    visual_settings?: FilamentVisualSettings | null;
    diameter?: number;
    density?: number;
    price_per_kg?: number;
    spool_weight?: number;
    empty_spool_weight_g?: number;
    description?: string;
    active?: boolean;
  }>) => {
    const response = await api.patch<Filament>(`/filaments/${id}`, data);
    return response.data;
  },

  delete: async (id: number) => {
    await api.delete(`/filaments/${id}`);
  },

  // Получить совместимые принтеры для филамента
  getCompatiblePrinters: async (id: number, minConfidence: number = 0.5) => {
    const response = await api.get<CompatiblePrinter[]>(`/filaments/${id}/compatible-printers`, {
      params: { min_confidence: minConfidence },
    });
    return response.data;
  },

  // Reviews
  getReviews: async (id: number, params?: { page?: number; size?: number; active_only?: boolean }) => {
    const response = await api.get<ListResponse<FilamentReview>>(`/filament-reviews/filament/${id}`, { params });
    return response.data;
  },

  getRatingStats: async (id: number) => {
    const response = await api.get<FilamentRatingStats>(`/filament-reviews/filament/${id}/stats`);
    return response.data;
  },
};

// Filament Reviews API
export const filamentReviewsAPI = {
  list: async (filamentId: number, params?: {
    page?: number;
    size?: number;
    active_only?: boolean;
    order_by?: 'created_at' | 'rating' | 'updated_at';
    order_desc?: boolean;
  }) => {
    const response = await api.get<ListResponse<FilamentReview>>(`/filament-reviews/filament/${filamentId}`, { params });
    return response.data;
  },

  get: async (reviewId: number) => {
    const response = await api.get<FilamentReview>(`/filament-reviews/${reviewId}`);
    return response.data;
  },

  getAvailablePresets: async (filamentId: number) => {
    const response = await api.get<{ items: Preset[]; total: number }>(`/filament-reviews/available-presets/${filamentId}`);
    return response.data;
  },

  create: async (data: {
    filament_id: number;
    preset_id?: number | null;
    success: boolean;
    rating: number; // 1.0 - 5.0
    comment?: string | null;
    printer_model?: string | null;
  }) => {
    const response = await api.post<FilamentReview>('/filament-reviews/', data);
    return response.data;
  },

  update: async (reviewId: number, data: Partial<{
    success?: boolean;
    rating?: number;
    comment?: string | null;
    printer_model?: string | null;
    active?: boolean;
  }>) => {
    const response = await api.patch<FilamentReview>(`/filament-reviews/${reviewId}`, data);
    return response.data;
  },

  delete: async (reviewId: number) => {
    await api.delete(`/filament-reviews/${reviewId}`);
  },

  getStats: async (filamentId: number) => {
    const response = await api.get<FilamentRatingStats>(`/filament-reviews/filament/${filamentId}/stats`);
    return response.data;
  },

  getMyReviews: async (params?: {
    page?: number;
    size?: number;
    active_only?: boolean;
  }) => {
    const response = await api.get<ListResponse<FilamentReview>>('/filament-reviews/my', { params });
    return response.data;
  },
};

// QR Code API
export const qrAPI = {
  // Получить QR-код изображение (URL)
  getQRCodeURL: (filamentId: number, size: number = 300): string => {
    return `${API_BASE_URL}/qr/filaments/${filamentId}/qr-code?size=${size}`;
  },

  // Скачать QR-код для печати
  downloadQRCode: async (filamentId: number, size: number = 600): Promise<void> => {
    const response = await api.get(`/qr/filaments/${filamentId}/qr-code/download`, {
      params: { size },
      responseType: 'blob',
    });
    
    // Создаем временную ссылку для скачивания
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `qr-code-${filamentId}-${size}x${size}.png`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },

  // Регистрация сканирования QR-кода
  scan: async (shortCode: string): Promise<{
    filament: Filament;
    preset_added: boolean;
    preset: Preset | null;
  }> => {
    const response = await api.post(`/qr/${shortCode}/scan`);
    return response.data;
  },

  // Получить пресет по QR-коду
  getPreset: async (shortCode: string): Promise<any> => {
    const response = await api.get(`/qr/${shortCode}/preset`);
    return response.data;
  },
};

// Presets API
export const presetsAPI = {
  list: async (params?: {
    page?: number;
    size?: number;
    active_only?: boolean;
    filament_id?: number;
    printer_id?: number;
    is_official?: boolean;
    user_id?: number;
    search?: string;
    ids?: string;
  }) => {
    const response = await api.get<ListResponse<Preset>>('/presets/', { params });
    return response.data;
  },

  get: async (id: number) => {
    const response = await api.get<Preset>(`/presets/${id}`);
    return response.data;
  },

  getRecommended: async (filament_id: number) => {
    const response = await api.get<RecommendedPreset>(`/presets/recommended/${filament_id}`);
    return response.data;
  },

  update: async (id: number, data: Partial<{
    name?: string;
    description?: string;
    is_official?: boolean;
    filament_id?: number | null; // Может быть null для черновиков
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
    orcaslicer_settings?: any;
    rating?: number;
    active?: boolean;
    // УДАЛЕНО: sync_enabled - теперь управляется через user_saved_presets.sync
  }>) => {
    const response = await api.patch<Preset>(`/presets/${id}`, data);
    return response.data;
  },

  create: async (data: {
    filament_id?: number | null; // Может быть null для черновиков
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
    orcaslicer_settings?: Record<string, any> | null; // Расширенные параметры OrcaSlicer
    printer_ids?: number[]; // Список ID принтеров, для которых подходит этот пресет
  }) => {
    const response = await api.post<Preset>('/presets/', data);
    return response.data;
  },

  delete: async (id: number) => {
    await api.delete(`/presets/${id}`);
  },

  activate: async (id: number, filament_id: number) => {
    const response = await api.post<Preset>(`/presets/${id}/activate`, { filament_id });
    return response.data;
  },
};

// Saved Presets API
export const savedPresetsAPI = {
  list: async () => {
    const response = await api.get<{ items: UserSavedPreset[]; total: number }>('/saved-presets/');
    return response.data;
  },

  save: async (preset_id: number) => {
    const response = await api.post<UserSavedPreset>('/saved-presets/', { preset_id });
    return response.data;
  },

  unsave: async (preset_id: number) => {
    await api.delete(`/saved-presets/${preset_id}`);
  },

  toggleSync: async (preset_id: number, sync: boolean) => {
    const response = await api.patch<UserSavedPreset>(`/saved-presets/${preset_id}/sync?sync=${sync}`);
    return response.data;
  },
};

// Printer Profiles API
type CreatePrinterProfilePayload = {
  name: string;
  slug: string;
  description?: string | null;
  printer_id?: number | null;
  owner_user_id?: number | null;
  vendor?: string | null;
  is_official?: boolean;
  active?: boolean;
  printable_area?: Record<string, number> | string[] | null;
  printable_height_mm?: number | null;
  nozzle_diameters?: number[] | null;
  orcaslicer_settings?: Record<string, any> | null;
  extra_metadata?: Record<string, any> | null;
  start_gcode?: string | null;
  end_gcode?: string | null;
  notes?: string | null;
};

export const printerProfilesAPI = {
  list: async (params?: {
    page?: number;
    size?: number;
    active_only?: boolean;
    is_official?: boolean;
    printer_id?: number;
    owner_user_id?: number;
    search?: string;
  }) => {
    const response = await api.get<ListResponse<PrinterProfile>>('/printer-profiles/', { params });
    return response.data;
  },

  get: async (id: number) => {
    const response = await api.get<PrinterProfile>(`/printer-profiles/${id}`);
    return response.data;
  },

  create: async (data: CreatePrinterProfilePayload) => {
    const response = await api.post<PrinterProfile>('/printer-profiles/', data);
    return response.data;
  },

  update: async (id: number, data: Partial<CreatePrinterProfilePayload>) => {
    const response = await api.patch<PrinterProfile>(`/printer-profiles/${id}`, data);
    return response.data;
  },

  delete: async (id: number) => {
    await api.delete(`/printer-profiles/${id}`);
  },
};

// Print Profiles API
type CreatePrintProfilePayload = {
  name: string;
  slug: string;
  description?: string | null;
  category?: string | null;
  owner_user_id?: number | null;
  is_official?: boolean;
  active?: boolean;
  source?: string;
  vendor?: string | null;
  setting_id?: string | null;
  quality_tier?: string | null;
  default_nozzle?: string | null;
  layer_height_mm?: number | null;
  compatible_printers?: string[] | null;
  compatible_filaments?: string[] | null;
  orcaslicer_settings?: Record<string, any>;
  extra_metadata?: Record<string, any> | null;
  notes?: string | null;
};

export const printProfilesAPI = {
  list: async (params?: {
    page?: number;
    size?: number;
    active_only?: boolean;
    is_official?: boolean;
    owner_user_id?: number;
    search?: string;
    category?: string;
  }) => {
    const response = await api.get<ListResponse<PrintProfile>>('/print-profiles/', { params });
    return response.data;
  },

  get: async (id: number) => {
    const response = await api.get<PrintProfile>(`/print-profiles/${id}`);
    return response.data;
  },

  create: async (data: CreatePrintProfilePayload) => {
    const response = await api.post<PrintProfile>('/print-profiles/', data);
    return response.data;
  },

  update: async (id: number, data: Partial<CreatePrintProfilePayload>) => {
    const response = await api.patch<PrintProfile>(`/print-profiles/${id}`, data);
    return response.data;
  },

  delete: async (id: number) => {
    await api.delete(`/print-profiles/${id}`);
  },
};

// Printers API
export const printersAPI = {
  list: async (params?: {
    page?: number;
    size?: number;
    active_only?: boolean;
    manufacturer?: string;
    search?: string;
  }) => {
    const response = await api.get<ListResponse<Printer>>('/printers/', { params });
    return response.data;
  },

  get: async (id: number) => {
    const response = await api.get<Printer>(`/printers/${id}`);
    return response.data;
  },

  // Получить совместимые филаменты для принтера
  getCompatibleFilaments: async (id: number, minConfidence: number = 0.5) => {
    const response = await api.get<CompatibleFilament[]>(`/printers/${id}/compatible-filaments`, {
      params: { min_confidence: minConfidence },
    });
    return response.data;
  },
};

// Calculator API
// Brand Requests API
export const brandRequestsAPI = {
  create: async (data: {
    request_type: 'join' | 'create';
    brand_id?: number;
    new_brand_name?: string;
    new_brand_slug?: string;
    new_brand_description?: string;
    new_brand_website?: string;
    message?: string;
    company_email?: string;
    company_website?: string;
    social_media_urls?: string[];
    proof_text: string;
    proof_files?: string[];
  }) => {
    const response = await api.post<BrandRequest>('/brand-requests/', data);
    return response.data;
  },

  getMy: async () => {
    const response = await api.get<BrandRequest[]>('/brand-requests/my');
    return response.data;
  },

  get: async (id: number) => {
    const response = await api.get<BrandRequest>(`/brand-requests/${id}`);
    return response.data;
  },

  cancel: async (id: number) => {
    await api.delete(`/brand-requests/${id}`);
  },

  uploadFile: async (requestId: number, file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post<BrandRequest>(`/brand-requests/${requestId}/upload`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  deleteFile: async (requestId: number, filePath: string) => {
    const response = await api.delete<BrandRequest>(`/brand-requests/${requestId}/files/${encodeURIComponent(filePath)}`);
    return response.data;
  },
};

export const calculatorAPI = {
  estimate: async (data: CalculatorEstimateRequest) => {
    const response = await api.post<CalculatorEstimateResponse>('/calculator/estimate', data);
    return response.data;
  },

  parseGcode: async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post<import('../types/api').CalculatorGcodeParseResponse>('/calculator/parse-gcode', formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    });
    return response.data;
  },

  listHistory: async (params?: { page?: number; size?: number }) => {
    const response = await api.get<import('../types/api').CalculatorHistoryListResponse>('/calculator/history', { params });
    return response.data;
  },

  saveHistory: async (data: import('../types/api').CalculatorHistoryEntryCreate) => {
    const response = await api.post<import('../types/api').CalculatorHistoryEntry>('/calculator/history', data);
    return response.data;
  },

  deleteHistory: async (entryId: number) => {
    await api.delete(`/calculator/history/${entryId}`);
  },

  getProfile: async () => {
    const response = await api.get<CalculatorProfileResponse>('/calculator/profile');
    return response.data;
  },

  updateProfile: async (data: CalculatorProfileUpdate) => {
    const response = await api.put<CalculatorProfileResponse>('/calculator/profile', data);
    return response.data;
  },

  shareQuote: async (data: import('../types/api').SharedQuoteCreate) => {
    const response = await api.post<import('../types/api').SharedQuoteResponse>('/calculator/quote/share', data);
    return response.data;
  },

  downloadQuotePdf: async (data: import('../types/api').SharedQuoteCreate) => {
    const response = await api.post('/calculator/quote/pdf', data, {
      responseType: 'blob',
    });
    const url = window.URL.createObjectURL(response.data as Blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${data.title || 'quote'}.pdf`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  },
};

// ==================== Admin API ====================

export const adminAPI = {
  // Brand Requests
  listBrandRequests: async (params?: { page?: number; size?: number; status?: BrandRequestStatus }): Promise<ListResponse<BrandRequest>> => {
    const response = await api.get<ListResponse<BrandRequest>>('/admin/brand-requests', { params });
    return response.data;
  },
  
  getBrandRequest: async (id: number): Promise<BrandRequest> => {
    const response = await api.get<BrandRequest>(`/admin/brand-requests/${id}`);
    return response.data;
  },
  
  deleteBrandRequest: async (id: number): Promise<void> => {
    await api.delete(`/admin/brand-requests/${id}`);
  },
  
  updateBrandRequest: async (id: number, data: { status: BrandRequestStatus; rejection_reason?: string }): Promise<BrandRequest> => {
    const response = await api.patch<BrandRequest>(`/admin/brand-requests/${id}`, data);
    return response.data;
  },

  // Brands
  listBrands: async (params?: { 
    page?: number; 
    size?: number; 
    verified?: boolean | null;
    active_only?: boolean;
    search?: string;
  }): Promise<{ items: Brand[]; total: number; page: number; size: number; pages: number }> => {
    const response = await api.get<{ items: Brand[]; total: number; page: number; size: number; pages: number }>('/admin/brands', { params });
    return response.data;
  },

  updateBrand: async (id: number, data: {
    name?: string;
    slug?: string;
    description?: string | null;
    website?: string | null;
    logo_url?: string | null;
    verified?: boolean;
    active?: boolean;
  }): Promise<Brand> => {
    const response = await api.patch<Brand>(`/admin/brands/${id}`, data);
    return response.data;
  },

  uploadBrandLogo: async (brandId: number, file: File): Promise<Brand> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post<Brand>(`/admin/brands/${brandId}/logo`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return response.data;
  },

  // Printers
  createPrinter: async (data: {
    name: string;
    manufacturer: string;
    model: string;
    slug: string;
    model_id?: string;
    family?: string;
    technology?: string;
    vendor?: string;
    description?: string;
    build_volume_x?: number;
    build_volume_y?: number;
    build_volume_z?: number;
    nozzle_diameter?: number;
    nozzle_options?: number[];
    max_extruder_temp?: number;
    max_bed_temp?: number;
    default_materials?: string[];
    extra_metadata?: Record<string, any>;
    image_url?: string;
  }): Promise<Printer> => {
    const response = await api.post<Printer>('/admin/printers', data);
    return response.data;
  },

  updatePrinter: async (id: number, data: {
    name?: string;
    manufacturer?: string;
    model?: string;
    slug?: string;
    model_id?: string;
    family?: string;
    technology?: string;
    vendor?: string;
    description?: string;
    build_volume_x?: number;
    build_volume_y?: number;
    build_volume_z?: number;
    nozzle_diameter?: number;
    nozzle_options?: number[];
    max_extruder_temp?: number;
    max_bed_temp?: number;
    default_materials?: string[];
    extra_metadata?: Record<string, any>;
    image_url?: string;
    active?: boolean;
  }): Promise<Printer> => {
    const response = await api.patch<Printer>(`/admin/printers/${id}`, data);
    return response.data;
  },

  deletePrinter: async (id: number): Promise<void> => {
    await api.delete(`/admin/printers/${id}`);
  },

  // Printer Requests
  listPrinterRequests: async (params?: { 
    page?: number; 
    size?: number; 
    status?: 'pending' | 'approved' | 'rejected';
  }): Promise<{ items: PrinterRequest[]; total: number }> => {
    const response = await api.get<{ items: PrinterRequest[]; total: number }>('/admin/printer-requests', { params });
    return response.data;
  },

  getPrinterRequest: async (id: number): Promise<PrinterRequest> => {
    const response = await api.get<PrinterRequest>(`/admin/printer-requests/${id}`);
    return response.data;
  },

  updatePrinterRequest: async (id: number, data: { 
    status: 'pending' | 'approved' | 'rejected'; 
    rejection_reason?: string;
  }): Promise<PrinterRequest> => {
    const response = await api.patch<PrinterRequest>(`/admin/printer-requests/${id}`, data);
    return response.data;
  },

  verifyBrand: async (brandId: number): Promise<Brand> => {
    const response = await api.post<Brand>(`/admin/brands/${brandId}/verify`);
    return response.data;
  },
  
  unverifyBrand: async (brandId: number): Promise<Brand> => {
    const response = await api.post<Brand>(`/admin/brands/${brandId}/unverify`);
    return response.data;
  },

  // Presets
  listPendingPresets: async (params?: { page?: number; size?: number }): Promise<Preset[]> => {
    const response = await api.get<Preset[]>('/admin/presets/pending', { params });
    return response.data;
  },
  
  approvePreset: async (presetId: number): Promise<Preset> => {
    const response = await api.post<Preset>(`/admin/presets/${presetId}/approve`);
    return response.data;
  },
  
  rejectPreset: async (presetId: number, reason: string): Promise<Preset> => {
    const response = await api.post<Preset>(`/admin/presets/${presetId}/reject`, null, {
      params: { reason },
    });
    return response.data;
  },

  // Users
  listUsers: async (params?: { page?: number; size?: number; role?: string; active_only?: boolean; with_brand?: boolean }): Promise<User[]> => {
    const response = await api.get<User[]>('/admin/users', { params });
    return response.data;
  },
  
  activateUser: async (userId: number): Promise<User> => {
    const response = await api.post<User>(`/admin/users/${userId}/activate`);
    return response.data;
  },
  
  deactivateUser: async (userId: number): Promise<User> => {
    const response = await api.post<User>(`/admin/users/${userId}/deactivate`);
    return response.data;
  },
  
  promoteToAdmin: async (userId: number): Promise<User> => {
    const response = await api.post<User>(`/admin/users/${userId}/promote-admin`);
    return response.data;
  },

  demoteToUser: async (userId: number): Promise<User> => {
    const response = await api.post<User>(`/admin/users/${userId}/demote-to-user`);
    return response.data;
  },

  linkUserToBrand: async (userId: number, brandId: number): Promise<User> => {
    const response = await api.post<User>(`/admin/users/${userId}/link-brand?brand_id=${brandId}`, {});
    return response.data;
  },

  unlinkUserFromBrand: async (userId: number): Promise<User> => {
    const response = await api.post<User>(`/admin/users/${userId}/unlink-brand`);
    return response.data;
  },

  updateUserBadges: async (userId: number, badges: string[]): Promise<User> => {
    const response = await api.patch<User>(`/admin/users/${userId}/badges`, badges);
    return response.data;
  },

  // Notifications
  sendNotification: async (data: {
    user_ids: number[];
    title: string;
    message: string;
    link?: string | null;
  }): Promise<{ success: boolean; message: string; count: number; sent_to: number[] }> => {
    const response = await api.post('/admin/notifications/send', data);
    return response.data;
  },

  // Stats
  getStats: async (): Promise<{
    users: {
      total: number; brands: number; admins: number;
      registered_24h: number; registered_7d: number; registered_30d: number;
      active_24h: number; active_7d: number;
    };
    brands: { total: number; verified: number; pending_verification: number };
    presets: { total: number; pending_moderation: number; approved: number; rejected: number };
    content: {
      filaments: number; printers: number; printer_profiles: number;
      reviews_total: number; reviews_7d: number; wiki_articles: number;
    };
    hardware: {
      devices: number; spools: number;
      gate_slots: number; gate_slots_assigned: number;
      sync_devices: number; sync_devices_active_7d: number;
    };
    notifications: { unread: number };
  }> => {
    const response = await api.get('/admin/stats');
    return response.data;
  },

  getSetting: async (key: string): Promise<{ key: string; value: string | null }> => {
    const response = await api.get(`/admin/settings/${key}`);
    return response.data;
  },

  setSetting: async (key: string, value: string): Promise<{ key: string; value: string }> => {
    const response = await api.put(`/admin/settings/${key}`, { value });
    return response.data;
  },

  getDockerStats: async (): Promise<{
    containers: Array<{
      name: string; cpu: string; mem_usage: string; mem_perc: string;
      net_io: string; block_io: string; pids: string;
      restart_count: number; status: string;
    }>;
    error?: string;
  }> => {
    const response = await api.get('/admin/docker-stats');
    return response.data;
  },

  // Database Management
  getMigrationHistory: async (): Promise<{
    current_revision: string | null;
    heads: string[];
    migrations: Array<{
      revision: string;
      down_revision: string | null;
      branch_labels: string | null;
      is_head: boolean;
      is_applied: boolean;
      applied_at: string | null;
      description: string | null;
    }>;
  }> => {
    const response = await api.get('/admin/database/migrations');
    return response.data;
  },

  checkDatabaseIntegrity: async (): Promise<{
    is_valid: boolean;
    missing_tables: string[];
    message: string;
  }> => {
    const response = await api.get('/admin/database/integrity');
    return response.data;
  },

  recreateTables: async (): Promise<{
    success: boolean;
    message: string;
    created_tables: string[];
  }> => {
    const response = await api.post('/admin/database/recreate-tables');
    return response.data;
  },

  applyMigration: async (data: { revision: string }): Promise<{
    success: boolean;
    message: string;
    current_revision: string | null;
    validation_errors?: string[] | null;
  }> => {
    const response = await api.post('/admin/database/migrations/apply', data, {
      timeout: 180000, // 3 минуты для применения миграций
    });
    return response.data;
  },

  downgradeMigration: async (data: { revision: string }): Promise<{
    success: boolean;
    message: string;
    current_revision: string | null;
  }> => {
    const response = await api.post('/admin/database/migrations/downgrade', data, {
      timeout: 180000, // 3 минуты для отката миграций
    });
    return response.data;
  },

  getDatabaseStats: async (): Promise<{
    database_name: string;
    database_size: string;
    database_size_bytes: number;
    table_stats: Array<{
      schema: string;
      table: string;
      size: string;
      size_bytes: number;
      column_count: number;
      row_count: number;
    }>;
  }> => {
    const response = await api.get('/admin/database/stats');
    return response.data;
  },

  exportDatabase: async (data: {
    format: string;
    include_data: boolean;
    tables?: string[];
  }): Promise<{
    success: boolean;
    filename: string | null;
    download_url: string | null;
    size: number | null;
    message: string;
  }> => {
    const response = await api.post('/admin/database/export', data);
    return response.data;
  },

  listDatabaseDumps: async (): Promise<{
    dumps: Array<{
      filename: string;
      size: number;
      created_at: string;
      modified_at: string;
      format: string;
    }>;
  }> => {
    const response = await api.get('/admin/database/dumps');
    return response.data;
  },

  deleteDatabaseDump: async (filename: string): Promise<{
    success: boolean;
    message: string;
  }> => {
    const response = await api.delete(`/admin/database/dumps/${filename}`);
    return response.data;
  },

  importDatabase: async (
    file: File,
    format: string,
    clean: boolean,
    create?: boolean
  ): Promise<{
    success: boolean;
    message: string;
  }> => {
    const formData = new FormData();
    formData.append('file', file);
    const response = await api.post('/admin/database/import', formData, {
      params: {
        format,
        clean,
        create: create || false,
      },
      headers: {
        'Content-Type': 'multipart/form-data',
      },
      timeout: 600000, // 10 минут таймаут для больших файлов
    });
    return response.data;
  },

  getTableStructure: async (tableName: string, schemaName: string = 'public'): Promise<{
    table_name: string;
    schema_name: string;
    columns: Array<{
      column_name: string;
      data_type: string;
      is_nullable: boolean;
      column_default: string | null;
      character_maximum_length: number | null;
    }>;
    indexes: Array<{ name: string; definition: string }>;
    constraints: Array<{ name: string; type: string }>;
  }> => {
    const response = await api.get(`/admin/database/tables/${tableName}/structure`, {
      params: { schema_name: schemaName },
    });
    return response.data;
  },

  getTableData: async (
    tableName: string,
    params?: {
      schema_name?: string;
      page?: number;
      size?: number;
      order_by?: string;
      order_desc?: boolean;
      search?: string;
    }
  ): Promise<{
    table_name: string;
    schema_name: string;
    columns: string[];
    rows: Array<Record<string, any>>;
    total: number;
    page: number;
    size: number;
    pages: number;
    primary_key_columns: string[];
  }> => {
    const response = await api.get(`/admin/database/tables/${tableName}/data`, { params });
    return response.data;
  },

  updateTableData: async (
    tableName: string,
    data: {
      primary_key: Record<string, any>;
      data: Record<string, any>;
    },
    schemaName?: string
  ): Promise<{ success: boolean; message: string }> => {
    const response = await api.patch(`/admin/database/tables/${tableName}/data`, data, {
      params: { schema_name: schemaName || 'public' },
    });
    return response.data;
  },

  deleteTableData: async (
    tableName: string,
    primaryKey: Record<string, any>,
    schemaName?: string
  ): Promise<{ success: boolean; message: string }> => {
    const response = await api.delete(`/admin/database/tables/${tableName}/data`, {
      data: primaryKey,
      params: { schema_name: schemaName || 'public' },
    });
    return response.data;
  },

  // Wiki Sync & Export
  syncWiki: async (): Promise<{
    success: boolean;
    message: string;
    created: number;
    updated: number;
    skipped: number;
    errors: number;
    details: Array<{
      file: string;
      status: string;
      title?: string;
      slug?: string;
      category?: string;
      reason?: string;
    }>;
  }> => {
    const response = await api.post('/admin/wiki/sync');
    return response.data;
  },

  exportWiki: async (): Promise<{
    success: boolean;
    message: string;
    exported: number;
    errors: number;
    details: Array<{
      file: string;
      status: string;
      title?: string;
      reason?: string;
    }>;
  }> => {
    const response = await api.post('/admin/wiki/export');
    return response.data;
  },

  exportArticle: async (id: number): Promise<void> => {
    const response = await api.get(`/admin/wiki/export/${id}`, {
      responseType: 'blob',
    });
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    const contentDisposition = response.headers['content-disposition'];
    const filename = contentDisposition
      ? contentDisposition.split('filename=')[1]?.replace(/"/g, '')
      : `article-${id}.md`;
    link.setAttribute('download', filename);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
};

// Notifications API
export const notificationsAPI = {
  // Получить список уведомлений
  list: async (params?: { page?: number; size?: number; unread_only?: boolean }): Promise<NotificationListResponse> => {
    const response = await api.get('/notifications/', { params });
    return response.data;
  },

  // Получить количество непрочитанных уведомлений
  getUnreadCount: async (): Promise<{ unread_count: number }> => {
    const response = await api.get('/notifications/unread-count');
    return response.data;
  },

  // Отметить уведомление как прочитанное
  markAsRead: async (notificationId: number): Promise<Notification> => {
    const response = await api.patch(`/notifications/${notificationId}/read`);
    return response.data;
  },

  // Отметить все уведомления как прочитанные
  markAllAsRead: async (): Promise<{ marked_count: number }> => {
    const response = await api.post('/notifications/mark-all-read');
    return response.data;
  },

  // Удалить уведомление
  delete: async (notificationId: number): Promise<{ message: string }> => {
    const response = await api.delete(`/notifications/${notificationId}`);
    return response.data;
  },

  deleteAll: async (readOnly?: boolean): Promise<{ deleted_count: number; message: string }> => {
    const response = await api.delete('/notifications/all', {
      params: readOnly ? { read_only: true } : undefined,
    });
    return response.data;
  },
};

// OrcaSlicer Deleted Presets API
export const orcaslicerDeletedPresetsAPI = {
  // Сообщить об удалённых пресетах
  reportDeletedPresets: async (data: {
    deleted_presets: Array<{
      preset_id: number;
      preset_name: string;
      bundle_preset_name?: string | null;
    }>;
  }): Promise<{
    message: string;
    notification_id?: number | null;
    preset_count?: number | null;
    created_count?: number | null;
    saved_count?: number | null;
    rule?: string | null;
  }> => {
    const response = await api.post('/orcaslicer/deleted-presets', data);
    return response.data;
  },

  // Обработать действие пользователя для удалённого пресета
  handleAction: async (
    notificationId: number,
    data: {
      action: 'restore' | 'delete' | 'skip';
      preset_ids?: number[] | null;
      apply_to_all?: boolean;
      save_rule?: boolean;
    }
  ): Promise<{
    message: string;
    action: string;
    processed_count: number;
    total_count: number;
  }> => {
    const response = await api.post(`/orcaslicer/deleted-presets/${notificationId}/action`, data);
    return response.data;
  },

  // Автоматически обработать удалённые уведомления
  autoProcess: async (): Promise<{
    message: string;
    processed_count: number;
    notifications_processed: number;
  }> => {
    const response = await api.post('/orcaslicer/deleted-presets/auto-process');
    return response.data;
  },
};

// Feedback API
export const feedbackAPI = {
  // Создать обратную связь (требуется авторизация)
  create: async (data: {
    type: FeedbackType;
    subject: string;
    message: string;
    email?: string | null;
    // Source context
    source?: string | null;
    source_url?: string | null;
    source_id?: number | null;
  }): Promise<Feedback> => {
    const response = await api.post<Feedback>('/feedback/', data);
    return response.data;
  },

  // Получить список своей обратной связи
  listMy: async (params?: { page?: number; size?: number }): Promise<FeedbackListResponse> => {
    const response = await api.get<FeedbackListResponse>('/feedback/my/list', { params });
    return response.data;
  },
};

// Admin Feedback API (только для админов)
export const adminFeedbackAPI = {
  // Получить список всей обратной связи
  list: async (params?: {
    page?: number;
    size?: number;
    status?: string;
    type?: FeedbackType;
    source?: string;
  }): Promise<FeedbackListResponse> => {
    const response = await api.get<FeedbackListResponse>('/feedback/', { params });
    return response.data;
  },

  // Получить обратную связь по ID
  get: async (feedbackId: number): Promise<Feedback> => {
    const response = await api.get<Feedback>(`/feedback/${feedbackId}`);
    return response.data;
  },

  // Обновить обратную связь (ответить, изменить статус)
  update: async (feedbackId: number, data: {
    status?: string;
    admin_response?: string | null;
  }): Promise<Feedback> => {
    const response = await api.patch<Feedback>(`/feedback/${feedbackId}`, data);
    return response.data;
  },

  // Удалить обратную связь
  delete: async (feedbackId: number): Promise<{ success: boolean }> => {
    const response = await api.delete(`/feedback/${feedbackId}`);
    return response.data;
  },
};

// Admin Notifications API (только для админов)
export const adminNotificationsAPI = {
  // Массовая рассылка уведомлений
  broadcast: async (data: {
    title: string;
    message: string;
    link?: string | null;
    active_only?: boolean;
  }): Promise<{ success: boolean; message: string; count: number }> => {
    const response = await api.post('/admin/notifications/broadcast', {
      title: data.title,
      message: data.message,
      link: data.link || null,
      active_only: data.active_only !== false,
    });
    return response.data;
  },
};

// Downloads API
export const downloadsAPI = {
  getOrcaSlicerDownloads: async (platform?: 'windows' | 'macos' | 'linux'): Promise<DownloadVersionsResponse> => {
    const params = platform ? { platform } : {};
    const response = await api.get('/downloads/orcaslicer', { params });
    return response.data;
  },

  getOrcaSlicerDownload: async (
    platform: 'windows' | 'macos' | 'linux',
    architecture: 'x64' | 'arm64'
  ): Promise<DownloadVersion> => {
    const response = await api.get(`/downloads/orcaslicer/${platform}/${architecture}`);
    return response.data;
  },
};

// Wiki API
export const wikiAPI = {
  // Categories
  listCategories: async (params?: { page?: number; page_size?: number }): Promise<WikiCategoryListResponse> => {
    const response = await api.get('/wiki/categories', { params });
    return response.data;
  },
  
  getCategory: async (slug: string): Promise<WikiCategory> => {
    const response = await api.get(`/wiki/categories/${slug}`);
    return response.data;
  },
  
  // Articles
  listArticles: async (params?: {
    page?: number;
    page_size?: number;
    category_slug?: string;
    search?: string;
    published_only?: boolean;
  }): Promise<WikiArticleListResponse> => {
    const response = await api.get('/wiki/articles', { params });
    return response.data;
  },
  
  getArticle: async (slug: string): Promise<WikiArticle> => {
    const response = await api.get(`/wiki/articles/${slug}`);
    return response.data;
  },
  
  searchArticles: async (q: string, params?: { page?: number; page_size?: number }): Promise<WikiArticleListResponse> => {
    const response = await api.get('/wiki/search', { params: { q, ...params } });
    return response.data;
  },

  // Feedback
  getFeedbackStats: async (articleSlug: string): Promise<WikiFeedbackStats> => {
    const response = await api.get(`/wiki/articles/${articleSlug}/feedback/stats`);
    return response.data;
  },

  createFeedback: async (articleSlug: string, data: WikiFeedbackCreate): Promise<WikiFeedback> => {
    const response = await api.post(`/wiki/articles/${articleSlug}/feedback`, data);
    return response.data;
  },

  removeHelpfulMark: async (articleSlug: string): Promise<void> => {
    await api.delete(`/wiki/articles/${articleSlug}/feedback/helpful`);
  },

  listFeedback: async (articleSlug: string, params?: { page?: number; page_size?: number }): Promise<WikiFeedback[]> => {
    const response = await api.get(`/wiki/articles/${articleSlug}/feedback`, { params });
    return response.data;
  },

  // Admin CRUD
  createArticle: async (data: {
    category_id: number;
    title: string;
    slug: string;
    summary: string;
    content: string;
    tags?: string[] | null;
    author?: string | null;
    published?: boolean;
    order?: number;
  }): Promise<WikiArticle> => {
    const response = await api.post<WikiArticle>('/wiki/articles', data);
    return response.data;
  },

  updateArticle: async (id: number, data: {
    category_id?: number;
    title?: string;
    slug?: string;
    summary?: string;
    content?: string;
    tags?: string[] | null;
    author?: string | null;
    published?: boolean;
    order?: number;
  }): Promise<WikiArticle> => {
    const response = await api.patch<WikiArticle>(`/wiki/articles/${id}`, data);
    return response.data;
  },

  deleteArticle: async (id: number): Promise<void> => {
    await api.delete(`/wiki/articles/${id}`);
  },

  createCategory: async (data: {
    name: string;
    slug: string;
    description: string;
    icon?: string | null;
    order?: number;
  }): Promise<WikiCategory> => {
    const response = await api.post<WikiCategory>('/wiki/categories', data);
    return response.data;
  },

  updateCategory: async (id: number, data: {
    name?: string;
    slug?: string;
    description?: string;
    icon?: string | null;
    order?: number;
  }): Promise<WikiCategory> => {
    const response = await api.patch<WikiCategory>(`/wiki/categories/${id}`, data);
    return response.data;
  },

  deleteCategory: async (id: number): Promise<void> => {
    await api.delete(`/wiki/categories/${id}`);
  },
};

// ── Spools API ───────────────────────────────────────────────────────────────

export type SpoolState = 'active' | 'shelf' | 'archived' | 'empty';

export interface SpoolFilamentInfo {
  id: number;
  name: string;
  material_type: string;
  color_name: string | null;
  color_hex: string | null;
  brand_name: string | null;
  price_per_kg: number | null;
}

export interface UserSpool {
  id: number;
  user_id: number;
  filament_id: number | null;
  filament: SpoolFilamentInfo | null;
  initial_weight_g: number;
  used_weight_g: number;
  remaining_weight_g: number;
  remaining_pct: number;
  price: number | null;
  state: SpoolState;
  source: string;
  lot_nr: string | null;
  comment: string | null;
  created_at: string;
  updated_at: string;
  last_used_at: string | null;
  extra: Record<string, string> | null;
}

export interface SpoolCreatePayload {
  filament_id?: number | null;
  initial_weight_g: number;
  used_weight_g?: number;
  price?: number | null;
  state?: SpoolState;
  source?: string;
  lot_nr?: string | null;
  comment?: string | null;
}

export interface SpoolUpdatePayload {
  filament_id?: number | null;
  initial_weight_g?: number;
  used_weight_g?: number;
  price?: number | null;
  state?: SpoolState;
  lot_nr?: string | null;
  comment?: string | null;
}

export const spoolsAPI = {
  list: async (): Promise<UserSpool[]> => {
    const response = await api.get<UserSpool[]>('/spools');
    return response.data;
  },

  create: async (payload: SpoolCreatePayload): Promise<UserSpool> => {
    const response = await api.post<UserSpool>('/spools', payload);
    return response.data;
  },

  update: async (id: number, payload: SpoolUpdatePayload): Promise<UserSpool> => {
    const response = await api.patch<UserSpool>(`/spools/${id}`, payload);
    return response.data;
  },

  use: async (id: number, delta_weight_g: number): Promise<UserSpool> => {
    const response = await api.post<UserSpool>(`/spools/${id}/use`, { delta_weight_g });
    return response.data;
  },

  delete: async (id: number): Promise<void> => {
    await api.delete(`/spools/${id}`);
  },
};

// ── Devices API ──────────────────────────────────────────────────────────────

export interface UserPrinterDevice {
  id: number;
  user_id: number;
  printer_id: number | null;
  name: string;
  device_fingerprint: string;
  supports_hh: boolean;
  gate_count: number | null;
  printer_hostname: string | null;
  has_api_key: boolean;
  last_seen_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface DeviceCreateWithKeyResponse {
  device: UserPrinterDevice;
  api_key: string;
}

export interface DeviceRegenerateKeyResponse {
  api_key: string;
}

/** gate_status from Happy Hare: -1=unknown, 0=empty, 1=spool, 2=buffer */
export interface GateState {
  id: number;
  gate_index: number;
  preset_id: number | null;
  spool_id: number | null;
  hh_material: string | null;
  hh_color_hex: string | null;
  hh_status: number | null;
  source: 'hh_snapshot' | 'manual_orca' | 'web_manual';
  source_ts: string;
  is_active: boolean;
  updated_at: string;
}

export interface DeviceStateResponse {
  device: UserPrinterDevice;
  gates: GateState[];
}

export interface DeviceRegisterPayload {
  device_fingerprint: string;
  name: string;
  printer_id?: number | null;
  supports_hh?: boolean;
  gate_count?: number | null;
}

export interface SlotAssignPayload {
  preset_id?: number | null;
  spool_id?: number | null;
}

export interface DeviceUpdatePayload {
  name?: string | null;
  gate_count?: number | null;
  supports_hh?: boolean | null;
  printer_hostname?: string | null;
}

export const devicesAPI = {
  list: async (): Promise<UserPrinterDevice[]> => {
    const response = await api.get<UserPrinterDevice[]>('/devices');
    return response.data;
  },

  register: async (payload: DeviceRegisterPayload): Promise<UserPrinterDevice> => {
    const response = await api.post<UserPrinterDevice>('/devices/register-or-update', payload);
    return response.data;
  },

  update: async (id: number, payload: DeviceUpdatePayload): Promise<UserPrinterDevice> => {
    const response = await api.patch<UserPrinterDevice>(`/devices/${id}`, payload);
    return response.data;
  },

  getState: async (id: number): Promise<DeviceStateResponse> => {
    const response = await api.get<DeviceStateResponse>(`/devices/${id}/state`);
    return response.data;
  },

  createWithKey: async (name: string, printerId?: number): Promise<DeviceCreateWithKeyResponse> => {
    const response = await api.post<DeviceCreateWithKeyResponse>('/devices/create-with-key', {
      name,
      ...(printerId ? { printer_id: printerId } : {}),
    });
    return response.data;
  },

  regenerateKey: async (id: number): Promise<DeviceRegenerateKeyResponse> => {
    const response = await api.post<DeviceRegenerateKeyResponse>(`/devices/${id}/regenerate-key`);
    return response.data;
  },

  remove: async (id: number): Promise<void> => {
    await api.delete(`/devices/${id}`);
  },
};

export const presetSlotsAPI = {
  list: async (device_id: number): Promise<GateState[]> => {
    const response = await api.get<GateState[]>('/preset-slots', { params: { device_id } });
    return response.data;
  },

  assign: async (device_id: number, gate_index: number, payload: SlotAssignPayload): Promise<GateState> => {
    const response = await api.patch<GateState>(`/preset-slots/${device_id}/${gate_index}`, payload);
    return response.data;
  },

  clear: async (device_id: number): Promise<{ cleared: number }> => {
    const response = await api.post<{ cleared: number }>(`/preset-slots/${device_id}/clear`);
    return response.data;
  },
};

export default api;
