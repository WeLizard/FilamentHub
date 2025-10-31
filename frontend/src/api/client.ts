/** API Client для интеграции с бэкендом */

import axios from 'axios';
import type { Brand, Filament, Preset, User, Token, ListResponse } from '../types/api';

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

