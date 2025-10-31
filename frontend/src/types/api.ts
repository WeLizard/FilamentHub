/** API Types - соответствуют бэкенду */

export interface Brand {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  website: string | null;
  logo_url: string | null;
  verified: boolean;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Filament {
  id: number;
  brand_id: number;
  name: string;
  material_type: string;
  color_name: string | null;
  color_hex: string | null;
  diameter: number;
  density: number | null;
  price_per_kg: number | null;
  spool_weight: number | null;
  description: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Preset {
  id: number;
  filament_id: number;
  name: string;
  description: string | null;
  is_official: boolean;
  extruder_temp: number;
  bed_temp: number;
  print_speed: number;
  travel_speed: number | null;
  layer_height: number | null;
  first_layer_height: number | null;
  flow_rate: number | null;
  fan_speed: number | null;
  retraction_length: number | null;
  retraction_speed: number | null;
  rating: number | null;
  usage_count: number;
  active: boolean;
  moderation_status: string;
  created_at: string;
  updated_at: string;
}

export interface User {
  id: number;
  email: string;
  username: string;
  role: string;
  full_name: string | null;
  bio: string | null;
  active: boolean;
  email_verified: boolean;
  brand_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface Token {
  access_token: string;
}

export interface ListResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

/** Типы для демокода (дополнительные поля, которые будут вычисляться) */
export interface FilamentWithBrand extends Filament {
  brand?: Brand;
  rating?: number; // Вычисляется из пресетов
  successRate?: number; // Вычисляется из пресетов
  officialPreset?: Preset;
  communityPresets?: Preset[];
}

