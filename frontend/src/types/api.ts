/** API Types - соответствуют бэкенду */

export interface Brand {
  id: number;
  name: string;
  slug: string;
  description: string | null;
  website: string | null;
  logo_url: string | null;
  logo_bg: string | null; // фон под лого (для прозрачных PNG/SVG)
  verified: boolean;
  active: boolean;
  currency: string;
  social_media_urls: string[] | null;
  shop_links: { platform: string; url: string }[] | null;
  price_hidden: boolean;
  created_at: string;
  updated_at: string;
  employees_count?: number | null; // Количество сотрудников (только при запросе)
}

export interface PopularPrinterItem {
  printer_id: number;
  name: string;
  manufacturer: string | null;
  count: number;
}

export interface BrandUsage {
  popular_printers: PopularPrinterItem[];
  spools_tracked: number;
  total_preset_usage: number;
  presets_count: number;
}

export interface FilamentVisualSettings {
  color_type?: 'single' | 'two' | 'three' | 'gradient' | 'transition' | 'thermochromic';
  colors?: string[]; // До 5 цветов для градиента/перехода
  finish?: 'matte' | 'glossy';
  filler?: string; // известный набор (none/wood/carbon/...) или кастомное значение (только верифиц. бренд)
  transparency?: boolean; // Прозрачный/непрозрачный (да/нет)
}

export interface FilamentPresetSummary {
  id: number;
  name: string;
  is_official: boolean;
  is_weighted: boolean;
  extruder_temp: number | null;
  bed_temp: number | null;
  print_speed: number | null;
  fan_speed: number | null;
  flow_rate: number | null;
  layer_height?: number | null;
  first_layer_height?: number | null;
  rating: number | null;
  success_rate: number | null;
  updated_at: string | null;
  preset_type: 'official' | 'weighted' | 'community';
}

export type FilamentAvailability = 'available' | 'out_of_stock' | 'discontinued' | 'coming_soon';

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
  empty_spool_weight_g: number | null;
  price_display_unit?: 'per_kg' | 'per_spool'; // в каком виде бренд назначил цену (основной показ)
  line_id?: number | null; // линейка (группировка вариантов-цвета)
  line_name?: string | null; // имя линейки (денормализовано)
  description: string | null;
  views_count: number | null;
  scans_count: number | null;
  qr_code: string | null; // Короткий код для QR-кода (например: "FHUB-ABC123")
  active: boolean;
  availability: FilamentAvailability;
  currency?: string; // валюта бренда (денормализовано в ответе)
  price_hidden?: boolean; // бренд скрыл цену (денормализовано)
  created_at: string;
  updated_at: string;
  presets_count?: number | null;
  official_presets_count?: number | null;
  community_presets_count?: number | null;
  official_preset?: FilamentPresetSummary | null;
  preset_summaries?: FilamentPresetSummary[];
}

export interface FilamentLine {
  id: number;
  brand_id: number;
  name: string;
  filaments_count: number;
  created_at: string;
}

export interface FilamentImportRowResult {
  row: number;
  status: 'created' | 'skipped' | 'error';
  name: string | null;
  filament_id: number | null;
  message: string | null;
}

export interface FilamentImportResult {
  created: number;
  skipped: number;
  errors: number;
  rows: FilamentImportRowResult[];
}

export interface FilamentPaletteVariant {
  color_name: string;
  color_hex?: string | null;
  name?: string | null; // переопределение авто-имени «<Линейка> <Цвет>»
}

export interface FilamentPalettePayload {
  material_type: string;
  visual_settings?: FilamentVisualSettings | null;
  diameter?: number;
  density?: number | null;
  price_per_kg?: number | null;
  spool_weight?: number | null;
  empty_spool_weight_g?: number | null;
  description?: string | null;
  availability?: FilamentAvailability;
  price_display_unit?: 'per_kg' | 'per_spool';
  variants: FilamentPaletteVariant[];
}

export interface BrandInvitePublic {
  valid: boolean;
  brand_name: string | null;
  email: string | null;
  reason: string | null;
}

export interface BrandInviteAdmin {
  id: number;
  token: string;
  email: string;
  brand_name: string | null;
  pre_verified: boolean;
  expires_at: string;
  accepted_at: string | null;
  created_at: string;
  invite_url: string | null;
}

export interface BrandInviteAcceptResult {
  brand_id: number;
  brand_name: string;
}

export interface Printer {
  id: number;
  name: string;
  manufacturer: string;
  model: string;
  slug: string;
  model_id: string | null;
  family: string | null;
  technology: string | null;
  source: string;
  vendor: string | null;
  build_volume_x: number | null;
  build_volume_y: number | null;
  build_volume_z: number | null;
  nozzle_diameter: number | null;
  nozzle_options: number[] | null;
  max_extruder_temp: number | null;
  max_bed_temp: number | null;
  description: string | null;
  image_url: string | null;
  default_materials: string[] | null;
  extra_metadata: Record<string, any> | null;
  active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CompatiblePrinter {
  id: number;
  slug: string;
  name: string;
  manufacturer: string | null;
  relation_source: string; // 'via_preset', 'via_print_profile', etc.
  confidence_score: number; // 0.0-1.0
}

export interface CompatibleFilament {
  id: number;
  slug: string;
  name: string;
  material_type: string;
  brand_name: string | null;
  relation_source: string; // 'via_preset', 'via_print_profile', etc.
  confidence_score: number; // 0.0-1.0
}

export interface PrinterProfile {
  id: number;
  printer_id: number | null;
  owner_user_id: number | null;
  name: string;
  slug: string;
  description: string | null;
  is_official: boolean;
  active: boolean;
  source: string;
  vendor: string | null;
  external_id: string | null;
  setting_id: string | null;
  nozzle_diameters: number[] | null;
  printable_area: Record<string, number> | string[] | null;
  printable_height_mm: number | null;
  default_print_profile_slug: string | null;
  orcaslicer_settings: Record<string, any>;
  extra_metadata: Record<string, any> | null;
  start_gcode: string | null;
  end_gcode: string | null;
  notes: string | null;
  printer_slug: string | null;
  printer_name: string | null;
  printer_manufacturer: string | null;
  printer_model: string | null;
  created_at: string;
  updated_at: string;
}

export interface PrintProfilePrinterLink {
  printer_id: number | null;
  printer_slug: string;
  relation_type: string;
  condition?: string | null;
}

export interface PrintProfileFilamentLink {
  filament_id: number | null;
  filament_slug: string;
  relation_type: string;
}

export interface PrintProfile {
  id: number;
  owner_user_id: number | null;
  name: string;
  slug: string;
  description: string | null;
  category: string | null;
  is_official: boolean;
  active: boolean;
  source: string;
  vendor: string | null;
  external_id: string | null;
  setting_id: string | null;
  quality_tier: string | null;
  default_nozzle: string | null;
  layer_height_mm: number | null;
  compatible_printers: string[] | null;
  compatible_filaments: string[] | null;
  orcaslicer_settings: Record<string, any>;
  extra_metadata: Record<string, any> | null;
  notes: string | null;
  printer_links: PrintProfilePrinterLink[];
  filament_links: PrintProfileFilamentLink[];
  created_at: string;
  updated_at: string;
}

export interface PrinterRequest {
  id: number;
  user_id: number;
  user_email: string | null; // Email пользователя для админки
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
  proof_files: string[] | null; // JSON массив путей к загруженным файлам
  status: 'pending' | 'approved' | 'rejected';
  processed_by_id: number | null;
  processed_at: string | null;
  rejection_reason: string | null;
  created_at: string;
  updated_at: string;
}

export interface Preset {
  id: number;
  filament_id: number | null;
  name: string;
  description: string | null;
  is_official: boolean;
  is_weighted: boolean; // Динамический взвешенный пресет, автоматически пересчитывается системой
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
  moderation_reason?: string | null;
  // УДАЛЕНО: sync_enabled - теперь управляется через user_saved_presets.sync
  external_id?: string | null; // ID пресета в OrcaSlicer (для маппинга)
  source?: string | null; // Источник пресета ("orcaslicer", "user", "system", etc.) или 'own' | 'saved' для UI
  created_at: string;
  updated_at: string;
  user_id?: number | null;
  printers?: Printer[]; // Список принтеров, для которых подходит этот пресет
  is_saved?: boolean; // Для UI: сохранен ли пресет пользователем (из available-presets эндпоинта)
}

export type PresetMatchReason =
  | 'exact_match'
  | 'same_model'
  | 'same_family'
  | 'same_manufacturer'
  | 'compatible_specs';

export interface RecommendedPresetItem {
  preset: Preset;
  match_score: number; // базовый уровень совпадения + бонусы (0..1.2)
  match_reason: PresetMatchReason;
}

export interface RecommendedForPrinterResponse {
  printer_id: number;
  printer_name: string;
  items: RecommendedPresetItem[];
}

export interface RecommendedPreset {
  filament_id: number;
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
  presets_count: number; // Количество пресетов, использованных для расчета
  avg_rating: number | null;
}

export interface User {
  // Sync settings (разрешения на импорт/экспорт профилей)
  allow_filament_presets_import?: boolean;
  allow_filament_presets_export?: boolean;
  allow_printer_profiles_import?: boolean;
  allow_printer_profiles_export?: boolean;
  allow_print_profiles_import?: boolean;
  allow_print_profiles_export?: boolean;
  api_key?: string | null;
  id: number;
  email: string;
  username: string;
  role: string;
  full_name: string | null;
  bio: string | null;
  avatar_url: string | null; // загруженный аватар пользователя
  active: boolean;
  email_verified: boolean;
  brand_id: number | null;
  brand_name: string | null; // Название бренда (для админки)
  printer_id: number | null; // ID выбранного принтера из каталога
  badges: string[] | null; // Бейджи пользователя (founder, beta_tester, contributor, verified, early_adopter, supporter)
  // Calculator Pro entitlement. New users activate a one-time trial explicitly.
  has_calculator_access?: boolean;
  subscription?: {
    status: string; // trialing | active | past_due | canceled | expired
    trial_ends_at: string | null;
    current_period_end: string | null;
    cancel_at_period_end: boolean;
    is_comp: boolean;
  } | null;
  oauth_provider: string | null; // OAuth provider (google, yandex) или null
  has_password: boolean; // false для OAuth-пользователей без пароля
  created_at: string;
  updated_at: string;
  last_login: string | null; // Дата последнего входа
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
  user_badges: string[] | null; // Бейджи пользователя
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

export type NotificationType = 'preset_updated' | 'preset_deleted' | 'preset_locally_deleted' | 'brand_verified' | 'brand_request_approved' | 'brand_request_rejected' | 'admin_message';

export type FeedbackType = 'bug' | 'feature' | 'question' | 'other';
export type FeedbackStatus = 'open' | 'in_progress' | 'resolved' | 'closed';

export interface Feedback {
  id: number;
  user_id: number | null;
  type: FeedbackType;
  subject: string;
  message: string;
  email: string | null;
  source: string | null; // wiki_article, preset, catalog, general
  source_url: string | null; // URL страницы, откуда отправили
  source_id: number | null; // ID связанного объекта
  status: FeedbackStatus;
  admin_response: string | null;
  admin_response_at: string | null;
  responded_by: number | null;
  created_at: string;
  updated_at: string;
}

export interface FeedbackListResponse {
  items: Feedback[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

export interface Notification {
  id: number;
  user_id: number;
  type: NotificationType;
  title: string;
  message: string;
  link: string | null;
  extra_data: Record<string, any> | null;
  read: boolean;
  read_at: string | null;
  created_at: string;
}

export interface NotificationListResponse {
  items: Notification[];
  total: number;
  page: number;
  size: number;
  pages: number;
  unread_count: number;
}

export interface UserSavedPreset {
  id: number;
  user_id: number;
  preset_id: number;
  saved_at: string; // ISO 8601 datetime string
  sync: boolean; // Включена ли синхронизация с OrcaSlicer для этого пресета у этого пользователя
}

export type PricingMethod = 'by_weight' | 'by_time' | 'combined';
export type RoundingMode = 'up' | 'down' | 'nearest';

export interface CalculatorEstimateRequest {
  pricing_method?: PricingMethod;
  
  // Параметры материала
  weight_g?: number | null;
  supports_weight_g?: number | null;
  supports_loss_coefficient?: number | null;
  spool_price?: number | null;
  spool_weight_kg?: number | null;
  delivery_cost?: number | null;
  
  // Параметры времени печати
  time_sec?: number | null;
  time_hours?: number | null;
  time_minutes?: number | null;
  
  // Почасовая ставка печати (для метода by_time)
  price_per_hour?: number | null;
  
  // Электроэнергия
  electricity_cost_per_kwh?: number | null;
  printer_power_w?: number | null;
  
  // Дополнительные услуги
  modeling_hours?: number | null;
  modeling_minutes?: number | null;
  modeling_rate_per_hour?: number | null;
  
  postprocessing_hours?: number | null;
  postprocessing_minutes?: number | null;
  postprocessing_rate_per_hour?: number | null;
  
  printing_rate_per_hour?: number | null;
  amortization_rate_per_hour?: number | null;
  
  // Количество деталей
  quantity?: number;
  parts_per_print?: number | null;
  
  // Накладные расходы и наценка
  overhead_percent?: number | null;
  markup_percent?: number | null;
  tax_rate_percent?: number | null;
  
  // Коэффициенты корректировки
  urgency_coefficient?: number | null;
  complexity_coefficient?: number | null;
  volume_discount_coefficient?: number | null;
  
  // Фиксированные расходы
  fixed_costs?: number | null;

  // Подготовка стола
  bed_prep_cost_per_print?: number | null;

  // Минимальная цена заказа
  min_order_price?: number | null;
  
  // Округление
  round_to_nearest?: number | null;
  rounding_mode?: RoundingMode;
}

export interface CalculatorEstimateResponse {
  // Компоненты стоимости
  cost_material: number;
  cost_electricity: number;
  cost_modeling: number;
  cost_printing: number;
  cost_postprocessing: number;
  cost_amortization: number;
  cost_bed_prep: number;
  cost_tax: number;
  
  // Промежуточные расчеты
  cost_direct: number;
  cost_overhead: number;
  cost_before_markup: number;
  cost_markup: number;
  
  // Итоговые суммы
  cost_first_part: number;
  cost_subsequent_parts: number;
  cost_total: number;
  cost_final: number;
  
  // Статистика
  weight_kg: number | null;
  time_hours: number | null;
  total_time_hours?: number | null;
  quantity: number;
  
  // Финансовые показатели (только для combined)
  cost_of_goods_sold?: number | null;
  profit_margin?: number | null;
  profit_margin_percent?: number | null;
  
  // Метод расчета
  pricing_method: PricingMethod;
  
  // Примененные коэффициенты
  applied_urgency_coefficient?: number | null;
  applied_complexity_coefficient?: number | null;
  applied_volume_discount?: number | null;
  applied_tax_rate_percent?: number | null;
}

export interface CalculatorParsedMaterial {
  type?: string | null;
  name?: string | null;
  vendor?: string | null;
  color?: string | null;
  weight_g?: number | null;
  length_mm?: number | null;
}

export interface CalculatorGcodeParseResponse {
  file_name: string;
  file_size_bytes: number;
  slicer_name?: string | null;
  slicer_version?: string | null;
  print_time_seconds?: number | null;
  total_filament_weight_g?: number | null;
  total_filament_length_mm?: number | null;
  layer_height_mm?: number | null;
  initial_layer_height_mm?: number | null;
  sparse_infill_density_percent?: number | null;
  sparse_infill_pattern?: string | null;
  wall_loops?: number | null;
  nozzle_diameter_mm?: number | null;
  nozzle_temperature_first_layer_c?: number | null;
  nozzle_temperature_other_layers_c?: number | null;
  bed_temperature_first_layer_c?: number | null;
  bed_temperature_other_layers_c?: number | null;
  object_count?: number | null;
  total_layers?: number | null;
  max_z_height_mm?: number | null;
  support_type?: string | null;
  support_threshold_angle_deg?: number | null;
  brim_width_mm?: number | null;
  raft_layers?: number | null;
  active_material_count?: number | null;
  is_multi_material?: boolean | null;
  toolchange_count?: number | null;
  thumbnail_data_url?: string | null;
  materials: CalculatorParsedMaterial[];
}

export interface CalculatorHistoryFilamentSnapshot {
  id?: number | null;
  name: string;
  brand_name?: string | null;
  material_type?: string | null;
  color_name?: string | null;
}

export interface CalculatorHistoryEntry {
  id: number;
  user_id: number;
  title: string;
  pricing_method: PricingMethod;
  request_data: CalculatorEstimateRequest;
  result_data: CalculatorEstimateResponse;
  parsed_gcode?: CalculatorGcodeParseResponse | null;
  filament_snapshot?: CalculatorHistoryFilamentSnapshot | null;
  created_at: string;
  updated_at: string;
}

export interface CalculatorHistoryEntryCreate {
  title?: string | null;
  request_data: CalculatorEstimateRequest;
  result_data: CalculatorEstimateResponse;
  parsed_gcode?: CalculatorGcodeParseResponse | null;
  filament_snapshot?: CalculatorHistoryFilamentSnapshot | null;
}

export interface CalculatorHistoryListResponse {
  items: CalculatorHistoryEntry[];
  total: number;
}

export interface CalculatorProfileResponse {
  electricity_cost_per_kwh: number;
  printer_power_w: number;
  modeling_rate_per_hour: number;
  postprocessing_rate_per_hour: number;
  printing_rate_per_hour: number;
  amortization_rate_per_hour: number;
  overhead_percent: number;
  markup_percent: number;
  tax_rate_percent: number;
  fixed_costs: number;
  bed_prep_cost_per_print: number;
  min_order_price: number;
  round_to_nearest: number;
  rounding_mode: string;
  seller_name: string;
  seller_inn: string;
  seller_phone: string;
  payment_terms: string;
  validity_days: number;
  disclaimer_mode: string;
  currency: string;
  quote_number_prefix: string;
  updated_at: string;
}

export type CalculatorProfileUpdate = Partial<Omit<CalculatorProfileResponse, 'updated_at'>>;

export interface SharedQuoteCreate {
  title?: string;
  html_content: string;
}

export interface SharedQuoteResponse {
  uuid: string;
  share_url: string;
  expires_at: string | null;
}

export interface DownloadVersion {
  platform: 'windows' | 'macos' | 'linux';
  architecture: 'x64' | 'arm64';
  version: string;
  download_url: string | null;
  file_size: string | null;
  checksum: string | null;
  available: boolean;
  download_type?: 'installer' | 'portable' | 'github';
  github_url?: string | null;
}

export interface DownloadVersionsResponse {
  versions: DownloadVersion[];
  latest_version: string;
}

// ============================================================================
// Wiki Types
// ============================================================================

export interface WikiCategory {
  id: number;
  name: string;
  slug: string;
  description: string;
  icon: string | null;
  order: number;
  created_at: string;
  updated_at: string;
  articles_count: number;
}

export interface WikiCategoryListResponse {
  items: WikiCategory[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface WikiArticleSummary {
  id: number;
  category_id: number;
  title: string;
  slug: string;
  summary: string;
  tags: string[];
  author: string | null;
  published: boolean;
  views: number;
  order: number;
  created_at: string;
  updated_at: string;
}

export interface WikiArticle extends WikiArticleSummary {
  content: string;
  category_name: string | null;
}

export interface WikiArticleListResponse {
  items: WikiArticleSummary[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// Wiki Feedback types
export type WikiFeedbackType = 'helpful' | 'feedback';

export interface WikiFeedbackStats {
  helpful_count: number;
  feedback_count: number;
  user_marked_helpful: boolean;
}

export interface WikiFeedbackCreate {
  feedback_type: WikiFeedbackType;
  comment?: string | null;
}

export interface WikiFeedback {
  id: number;
  article_id: number;
  user_id: number | null;
  feedback_type: WikiFeedbackType;
  comment: string | null;
  created_at: string;
  username: string | null;
}
