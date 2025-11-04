/** API Client для интеграции с бэкендом */

import axios from 'axios';
import type { Brand, BrandRequest, BrandRequestStatus, Filament, FilamentVisualSettings, Preset, Printer, PrinterRequest, User, Token, RefreshTokenRequest, RefreshTokenResponse, ListResponse, AccountDeletionStats } from '../types/api';
import { getRefreshToken, setToken, removeToken } from '../utils/auth';

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

  deleteAccount: async (data: { 
    delete_reviews: boolean; 
    delete_brand_if_sole_representative: boolean; 
    password_confirm: string;
  }) => {
    await api.delete('/auth/me', {
      data,
    });
  },
};

// Brands API
export const brandsAPI = {
  list: async (params?: { page?: number; size?: number; active_only?: boolean; search?: string }) => {
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
    orcaslicer_settings?: Record<string, any> | null; // Расширенные параметры OrcaSlicer
    printer_ids?: number[]; // Список ID принтеров, для которых подходит этот пресет
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
    orcaslicer_settings?: Record<string, any> | null; // Расширенные параметры OrcaSlicer
    printer_ids?: number[]; // Список ID принтеров, для которых подходит этот пресет
    active?: boolean;
  }>) => {
    const response = await api.patch<Preset>(`/presets/${id}`, data);
    return response.data;
  },

  delete: async (id: number) => {
    await api.delete(`/presets/${id}`);
  },
};

// Saved Presets API
export const savedPresetsAPI = {
  list: async () => {
    const response = await api.get<{ items: Array<{ id: number; preset_id: number }>; total: number }>('/saved-presets/');
    return response.data;
  },

  save: async (preset_id: number) => {
    const response = await api.post<{ id: number; preset_id: number; user_id: number; saved_at: string }>('/saved-presets/', { preset_id });
    return response.data;
  },

  unsave: async (preset_id: number) => {
    await api.delete(`/saved-presets/${preset_id}`);
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

  // Printers
  createPrinter: async (data: {
    name: string;
    manufacturer: string;
    model: string;
    slug: string;
    description?: string;
    build_volume_x?: number;
    build_volume_y?: number;
    build_volume_z?: number;
    nozzle_diameter?: number;
    max_extruder_temp?: number;
    max_bed_temp?: number;
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
    description?: string;
    build_volume_x?: number;
    build_volume_y?: number;
    build_volume_z?: number;
    nozzle_diameter?: number;
    max_extruder_temp?: number;
    max_bed_temp?: number;
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
  listUsers: async (params?: { page?: number; size?: number; role?: string; active_only?: boolean }): Promise<User[]> => {
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

  unlinkUserFromBrand: async (userId: number): Promise<User> => {
    const response = await api.post<User>(`/admin/users/${userId}/unlink-brand`);
    return response.data;
  },

  // Stats
  getStats: async (): Promise<{
    users: { total: number; brands: number; admins: number };
    brands: { total: number; verified: number; pending_verification: number };
    presets: { total: number; pending_moderation: number; approved: number; rejected: number };
  }> => {
    const response = await api.get('/admin/stats');
    return response.data;
  },
};

export default api;

