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

export interface FilamentVisualSettings {
  color_type?: 'single' | 'two' | 'three' | 'gradient' | 'transition' | 'thermochromic';
  colors?: string[]; // До 5 цветов для градиента/перехода
  finish?: 'matte' | 'glossy';
  filler?: 'none' | 'wood' | 'carbon' | 'glitter' | 'metallic' | 'luminescent' | 'fibers' | 'stone' | 'glass' | 'pattern1' | 'pattern2' | 'pattern3' | 'pattern4' | 'pattern5' | 'pattern6' | 'pattern7' | 'pattern8' | 'pattern9' | 'pattern10' | 'pattern11' | 'pattern12';
  transparency?: boolean; // Прозрачный/непрозрачный (да/нет)
}

export interface Filament {
  id: number;
  brand_id: number;
  brand_name: string | null; // Added
  name: string;
  material_type: string;
  color_name: string | null;
  color_hex: string | null;
  visual_settings: FilamentVisualSettings | null; // Расширенные визуальные эффекты (только для сайта)
  diameter: number;
  density: number | null;
  price_per_kg: number | null;
  spool_weight: number | null;
  description: string | null;
  views_count: number | null;
  scans_count: number | null;
  qr_code: string | null; // Короткий код для QR-кода (например: "FHUB-ABC123")
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Printer {
  id: number;
  name: string;
  manufacturer: string;
  model: string;
  slug: string;
  build_volume_x: number | null;
  build_volume_y: number | null;
  build_volume_z: number | null;
  nozzle_diameter: number | null;
  max_extruder_temp: number | null;
  max_bed_temp: number | null;
  description: string | null;
  image_url: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface PrinterRequest {
  id: number;
  user_id: number;
  name: string;
  manufacturer: string;
  model: string;
  slug: string;
  description: string | null;
  build_volume_x: number | null;
  build_volume_y: number | null;
  build_volume_z: number | null;
  nozzle_diameter: number | null;
  max_extruder_temp: number | null;
  max_bed_temp: number | null;
  image_url: string | null;
  message: string | null;
  status: 'pending' | 'approved' | 'rejected';
  processed_by_id: number | null;
  processed_at: string | null;
  rejection_reason: string | null;
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
  orcaslicer_settings: Record<string, any> | null; // Расширенные параметры OrcaSlicer в формате JSON
  rating: number | null;
  success_rate: number | null; // Процент успешных печатей (0-100)
  usage_count: number;
  active: boolean;
  moderation_status: string;
  created_at: string;
  updated_at: string;
  source?: 'own' | 'saved'; // For UI: 'own' = created by user, 'saved' = added from catalog
  user_id?: number | null;
  printers?: Printer[]; // Список принтеров, для которых подходит этот пресет
  is_saved?: boolean; // Для UI: сохранен ли пресет пользователем (из available-presets эндпоинта)
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
  brand_name: string | null; // Название бренда (для админки)
  created_at: string;
  updated_at: string;
}

export interface AccountDeletionStats {
  presets_count: number;
  official_presets_count: number;
  approved_presets_count: number;
  presets_used_by_others_count: number;
  reviews_count: number;
  saved_presets_count: number;
  brand_requests_count: number;
  is_brand_representative: boolean;
  brand_other_representatives_count: number;
}

export interface Token {
  access_token: string;
  refresh_token?: string;
  token_type?: string;
}

export interface RefreshTokenRequest {
  refresh_token: string;
}

export interface RefreshTokenResponse {
  access_token: string;
  token_type: string;
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

export type BrandRequestType = 'join' | 'create';
export type BrandRequestStatus = 'pending' | 'approved' | 'rejected';

export interface BrandRequest {
  id: number;
  user_id: number;
  user_email?: string | null; // Email пользователя для админки
  request_type: BrandRequestType;
  brand_id: number | null;
  brand_name?: string | null; // Название бренда для JOIN заявок
  new_brand_name: string | null;
  new_brand_slug: string | null;
  new_brand_description: string | null;
  new_brand_website: string | null;
  message: string | null;
  company_email: string | null;
  company_website: string | null;
  social_media_urls: string[] | null;
  proof_text: string | null;
  proof_files: Array<{ path: string; name: string } | string> | null; // Поддержка старого формата (строка) и нового (объект)
  status: BrandRequestStatus;
  processed_by_id: number | null;
  processed_at: string | null;
  rejection_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface FilamentReview {
  id: number;
  filament_id: number;
  user_id: number;
  preset_id: number | null;
  preset_name: string | null;
  username: string | null;
  success: boolean;
  rating: number; // 1.0 - 5.0
  comment: string | null;
  printer_model: string | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface FilamentRatingStats {
  avg_rating: number | null;
  total_reviews: number;
  success_rate: number | null; // 0.0 - 100.0
  rating_distribution: Record<number, number>; // {1: count, 2: count, ...}
}

export interface UserSavedPreset {
  id: number;
  user_id: number;
  preset_id: number;
  saved_at: string; // ISO 8601 datetime string
}