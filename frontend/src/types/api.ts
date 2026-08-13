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
  name_correction_available: boolean;
  name_corrected_at: string | null;
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

export interface BrandAnalytics {
  scope: 'global' | 'territorial';
  countries: string[];
  total_scans: number;
  historical_unattributed_scans: number;
  country_breakdown: { country: string | null; scans: number }[];
  filaments: { filament_id: number; name: string; scans: number }[];
}

export interface FilamentVisualSettings {
  color_type?: 'single' | 'two' | 'three' | 'gradient' | 'transition' | 'thermochromic';
  colors?: string[]; // До 5 цветов для градиента/перехода
  finish?: 'matte' | 'glossy';
  filler?: string; // известный набор (none/wood/carbon/...) или кастомное значение (только верифиц. бренд)
  effects?: string[]; // независимые визуальные эффекты; filler остаётся legacy primary
  transparency?: boolean; // Прозрачный/непрозрачный (да/нет)
}

export interface FilamentAdditive {
  code: string;
  content_percent?: number | null;
  content_basis?: 'weight' | 'volume' | null;
}

export interface FilamentPropertyClaim {
  code: string;
  value?: string | null;
  standard?: string | null;
  rating?: string | null;
}

export interface FilamentPresetSummary {
  id: number;
  name: string;
  is_official: boolean;
  is_weighted: boolean;
  extruder_temp: number | null;
  bed_temp: number | null;
  fan_speed: number | null;
  flow_rate: number | null;
  rating: number | null;
  success_rate: number | null;
  updated_at: string | null;
  preset_type: 'official' | 'weighted' | 'community';
}

export type FilamentAvailability = 'available' | 'out_of_stock' | 'discontinued' | 'coming_soon';

export interface Filament {
  id: number;
  slug?: string | null;
  brand_id: number;
  contributed_by_organization_id?: number | null;
  brand_name: string | null;
  brand_slug?: string | null;
  brand_verified?: boolean;
  name: string;
  material_type: string;
  color_name: string | null;
  color_hex: string | null;
  ral_code: string | null;
  visual_settings: FilamentVisualSettings | null; // Расширенные визуальные эффекты (только для сайта)
  additives?: FilamentAdditive[];
  property_claims?: FilamentPropertyClaim[];
  diameter: number;
  density: number | null;
  price_per_kg: number | null;
  spool_weight: number | null;
  empty_spool_weight_g: number | null;
  // Рекомендованные вендором диапазоны печати (спека материала), не значения профиля
  recommended_nozzle_temp_min: number | null;
  recommended_nozzle_temp_max: number | null;
  recommended_bed_temp_min: number | null;
  recommended_bed_temp_max: number | null;
  // Требуемая твёрдость сопла (HRC): абразивные наполнители требуют закалённого сопла
  required_nozzle_hrc: number | null;
  price_display_unit?: 'per_kg' | 'per_spool'; // в каком виде бренд назначил цену (основной показ)
  line_id?: number | null; // линейка (группировка вариантов-цвета)
  line_name?: string | null; // имя линейки (денормализовано)
  description: string | null;
  views_count: number | null;
  scans_count: number | null;
  qr_code: string | null;
  /** Заполнено, когда сведения подставлены из ячейки страны. */
  market_country?: string | null;
  market_availability?: CountryAvailability | null;
  market_note?: string | null;
  product_url?: string | null; // Короткий код для QR-кода (например: "FHUB-ABC123")
  active: boolean;
  availability: FilamentAvailability;
  currency?: string | null; // валюта рынка или бренда (денормализовано в ответе)
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
  status: 'created' | 'updated' | 'skipped' | 'error';
  name: string | null;
  filament_id: number | null;
  message: string | null;
}

export interface FilamentImportResult {
  created: number;
  updated: number;
  skipped: number;
  errors: number;
  rows: FilamentImportRowResult[];
}

export interface FilamentPaletteVariant {
  color_name: string;
  color_hex?: string | null;
  ral_code?: string | null;
  name?: string | null; // переопределение авто-имени «<Линейка> <Цвет>»
}

export interface FilamentPalettePayload {
  material_type: string;
  visual_settings?: FilamentVisualSettings | null;
  additives?: FilamentAdditive[];
  property_claims?: FilamentPropertyClaim[];
  diameter?: number;
  density?: number | null;
  price_per_kg?: number | null;
  spool_weight?: number | null;
  empty_spool_weight_g?: number | null;
  recommended_nozzle_temp_min?: number | null;
  recommended_nozzle_temp_max?: number | null;
  recommended_bed_temp_min?: number | null;
  recommended_bed_temp_max?: number | null;
  required_nozzle_hrc?: number | null;
  description?: string | null;
  availability?: FilamentAvailability;
  price_display_unit?: 'per_kg' | 'per_spool';
  country_cell?: {
    country: string;
    availability: CountryAvailability;
    price: number | null;
    currency: string | null;
    price_display_unit: 'per_kg' | 'per_spool' | null;
  } | null;
  variants: FilamentPaletteVariant[];
}

export interface BrandInvitePublic {
  valid: boolean;
  brand_name: string | null;
  email: string | null;
  target_type: 'new' | 'existing' | null;
  brand_id: number | null;
  active_organization_id?: number | null;
  purpose: 'platform' | 'representative' | 'territory' | 'team' | null;
  country: string | null;
  member_role: 'owner' | 'editor' | null;
  reason: string | null;
}

export interface BrandInviteAdmin {
  id: number;
  token: string;
  email: string;
  brand_name: string | null;
  target_type: 'new' | 'existing';
  brand_id: number | null;
  organization_id: number | null;
  country: string | null;
  member_role: 'owner' | 'editor';
  purpose: 'platform' | 'representative' | 'territory' | 'team';
  all_brands: boolean;
  sender_profile: 'partnerships' | 'pr' | 'transactional';
  language: EmailLanguage;
  batch_id: string | null;
  send_status: 'pending' | 'sent' | 'failed';
  send_error: string | null;
  pre_verified: boolean;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  created_at: string;
  invite_url: string | null;
}

export interface BrandInviteBatchRecipientIssue {
  value: string;
  code: 'invalid_format' | 'domain_typo' | 'domain_no_mail';
  suggestion: string | null;
}

export interface BrandInviteBatchPreview {
  normalized_emails: string[];
  send_emails: string[];
  invalid: BrandInviteBatchRecipientIssue[];
  duplicates: string[];
  already_invited: string[];
  max_recipients: number;
  limit_exceeded: boolean;
  confirmation_token: string | null;
  confirmation_expires_at: string | null;
}

export interface BrandInviteBatchSendResult {
  batch_id: string;
  invites: BrandInviteAdmin[];
  skipped_existing: string[];
  replayed: boolean;
}

export interface BrandInviteAcceptResult {
  brand_id: number;
  brand_name: string;
  organization_id: number | null;
  member_role: 'owner' | 'editor' | null;
}

export type EmailThreadStatus = 'open' | 'closed';
export type EmailMessageDirection = 'inbound' | 'outbound';
export type EmailSenderProfile = 'support' | 'partnerships' | 'pr';
export type EmailLanguage = 'ru' | 'en' | 'zh';
export type EmailDeliveryStatus = 'received' | 'sending' | 'sent' | 'delivered' | 'delayed' | 'bounced' | 'complained' | 'failed';

export interface EmailAttachment {
  index: number;
  filename: string;
  content_type: string | null;
  size: number | null;
  downloadable: boolean;
  content_id: string | null; // как картинка зовётся из текста письма (src="cid:...")
  inline: boolean;
}

export interface EmailMessage {
  id: number;
  direction: EmailMessageDirection;
  sender_email: string;
  recipient_emails: string[];
  subject: string;
  text_body: string;
  html_body: string | null;
  attachment_metadata: EmailAttachment[];
  delivery_status: EmailDeliveryStatus | null;
  read_at: string | null;
  created_at: string;
}

export interface EmailThreadSummary {
  id: number;
  invite_id: number | null;
  brand_id: number | null;
  brand_name: string | null;
  participant_email: string;
  participant_name: string | null;
  subject: string;
  status: EmailThreadStatus;
  unread_count: number;
  last_message_at: string;
  latest_preview: string;
  latest_direction: EmailMessageDirection | null;
  suggested_sender_profile: EmailSenderProfile;
  language: EmailLanguage;
}

export interface EmailThreadDetail extends EmailThreadSummary {
  messages: EmailMessage[];
}

export interface EmailThreadListResponse {
  items: EmailThreadSummary[];
  total: number;
  page: number;
  size: number;
  pages: number;
  unread_total: number;
}

export type NotificationCampaignAudience = 'active' | 'all' | 'selected';
export type NotificationCampaignStatus = 'draft' | 'sent' | 'cancelled' | 'expired';

export interface NotificationCampaignRecipientPreview {
  id: number;
  email: string;
  username: string;
  full_name: string | null;
}

export interface NotificationCampaignPreview {
  campaign_id: string;
  audience: NotificationCampaignAudience;
  recipient_count: number;
  recipient_sample: NotificationCampaignRecipientPreview[];
  excluded_user_ids: number[];
  title: string;
  message: string;
  link: string | null;
  confirmation_token: string;
  confirmation_expires_at: string;
}

export interface NotificationCampaignSendResult {
  campaign_id: string;
  status: 'sent';
  recipient_count: number;
  replayed: boolean;
  sent_at: string;
}

export interface NotificationCampaignHistoryItem {
  campaign_id: string;
  audience: NotificationCampaignAudience;
  title: string;
  message: string;
  link: string | null;
  recipient_count: number;
  status: NotificationCampaignStatus;
  created_by_id: number;
  created_by_name: string;
  created_at: string;
  confirmation_expires_at: string;
  sent_at: string | null;
}

export interface NotificationCampaignHistoryResponse {
  items: NotificationCampaignHistoryItem[];
  total: number;
  page: number;
  size: number;
  pages: number;
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
  printer_profile_ids?: number[];
  configuration_links_resolved?: boolean;
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
  auto_import_local_presets?: boolean | null;
  api_key?: string | null;
  id: number;
  email: string;
  username: string;
  country?: string | null;
  role: string;
  full_name: string | null;
  avatar_url: string | null; // загруженный аватар пользователя
  active: boolean;
  email_verified: boolean;
  brand_id: number | null;
  active_organization_id: number | null;
  brand_name: string | null; // Название бренда (для админки)
  printer_id: number | null; // ID выбранного принтера из каталога
  recommend_physical_printer_id: number | null; // Выбор для рекомендаций каталога (следует за аккаунтом между устройствами)
  recommend_printer_profile_id: number | null;
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
  legal_onboarding_required: boolean;
  /** Mandatory documents whose current versions still need affirmative acceptance. */
  required_legal_acceptances?: Array<'terms' | 'personal_data_consent'>;
  legal_document_pack?: LegalPack | null;
  /** Аккаунт уже принимал более раннюю редакцию — значит это повторный показ. */
  legal_previously_accepted?: boolean;
}

export interface UserPreferences {
  currency: string | null;
}

export interface AdminUserListResponse {
  items: User[];
  total: number;
  page: number;
  size: number;
  total_pages: number;
}

export interface AccessibleBrand {
  brand_id: number;
  brand_name: string;
  brand_slug: string;
  organization_id: number;
  organization_name: string;
  membership_role: 'owner' | 'editor' | null;
  is_active: boolean;
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
  organization_memberships_count: number;
  owned_organizations_count: number;
  sole_owner_organizations_count: number;
  ownership_transfer_required: boolean;
  representation_release_available: boolean;
  spools_count: number;
  printers_count: number;
  printer_profiles_count: number;
  print_profiles_count: number;
  calculations_count: number;
  quotes_count: number;
  customers_count: number;
  slice_reports_count: number;
}

export type BrandTeamRole = 'owner' | 'editor';

export interface BrandTeamMember {
  membership_id: number;
  user_id: number;
  username: string;
  email: string;
  role: BrandTeamRole;
  all_brands: boolean;
  brand_ids: number[];
  joined_at: string;
  is_current_user: boolean;
}

export interface BrandTeamInvite {
  id: number;
  email: string;
  role: BrandTeamRole;
  all_brands: boolean;
  brand_id: number;
  status: 'pending' | 'sent' | 'failed' | 'accepted' | 'expired' | 'revoked';
  invite_url: string;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  send_error: string | null;
}

export interface BrandRepresentative {
  grant_id: number;
  organization_id: number;
  organization_name: string;
  country: string | null;
  source: 'invitation' | 'application';
  approved_at: string | null;
}

export interface BrandRepresentativeInvite {
  id: number;
  email: string;
  country: string;
  organization_name: string | null;
  brand_id: number;
  status: 'pending' | 'sent' | 'failed' | 'accepted' | 'expired' | 'revoked';
  invite_url: string;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
  send_error: string | null;
}

export interface BrandPresence {
  organization_id: number;
  organization_name: string;
  country: string | null;
  member_count: number;
  is_current: boolean;
}

export interface BrandTeamJoinRequest {
  id: number;
  user_id: number;
  username: string;
  email: string;
  message: string | null;
  created_at: string;
}

export interface BrandTeamWorkspace {
  organization_id: number;
  organization_name: string;
  current_role: BrandTeamRole | 'admin';
  can_manage_team: boolean;
  can_transfer_ownership: boolean;
  members: BrandTeamMember[];
  pending_invites: BrandTeamInvite[];
  pending_join_requests: BrandTeamJoinRequest[];
  presence: BrandPresence[];
}

export interface Token {
  access_token: string;
  refresh_token?: string;
  token_type?: string;
  legal_onboarding_required?: boolean;
}

export type LegalPack = 'ru' | 'eu' | 'intl';
export type LegalDocumentType = 'terms' | 'personal_data_consent' | 'privacy_policy';

export interface LegalRequirements {
  legal_pack: LegalPack;
  edition_id: string;
  terms_version: string;
  personal_data_consent_version: string;
  privacy_policy_version: string;
  terms_url: string;
  personal_data_consent_url: string;
  privacy_policy_url: string;
  /** ISO date (YYYY-MM-DD) — formatted for display by the client locale. */
  legal_update_effective_date: string;
  legal_update_note: string;
}

export interface AuthMethods {
  access_region: 'ru' | 'intl' | 'unknown';
  local_login: boolean;
  local_registration: boolean;
  oauth_providers: Array<'google' | 'yandex'>;
  registration_captcha: 'recaptcha' | null;
}

interface LegalDocumentVersionsPayload {
  terms_version: string;
  personal_data_consent_version: string;
  privacy_policy_version: string;
  legal_language: string;
  legal_pack?: LegalPack;
}

export interface LegalAcceptancePayload extends LegalDocumentVersionsPayload {
  terms_accepted?: true;
  personal_data_consent?: true;
}

export interface LegalDocument {
  legal_pack: LegalPack;
  edition_id: string;
  document_type: LegalDocumentType;
  language: 'ru' | 'en' | 'zh';
  title: string;
  revision_label: string;
  markdown: string;
}

export interface RegistrationPayload extends LegalDocumentVersionsPayload {
  email: string;
  username: string;
  password: string;
  role: string;
  terms_accepted: true;
  personal_data_consent: true;
  recaptcha_token?: string;
}

export interface RefreshTokenRequest {
  refresh_token: string;
}

export interface RefreshTokenResponse {
  access_token: string;
  token_type: string;
}

export interface FilamentListResponse extends ListResponse<Filament> {
  /** Which of the listed materials have a preset for the printer asked about. */
  printer_matched_ids: number[];
}

export interface OrcaSliceReport {
  id: number;
  file_name: string;
  printer_settings_id: string | null;
  print_settings_id: string | null;
  printer_model: string | null;
  physical_printer_id: number | null;
  physical_printer_name: string | null;
  printer_profile_id: number | null;
  print_profile_id: number | null;
  target_host: string | null;
  source_key: string | null;
  sliced_at: string | null;
  received_at: string;
}

export interface SpoolUsageEvent {
  id: number;
  /** printer_report · manual_adjust · reconcile_adjust · print_estimate */
  event_type: string;
  delta_weight_g: number | null;
  remaining_weight_g: number | null;
  device_name: string | null;
  job_ref: string | null;
  created_at: string;
  /** What did not add up: the weight the printer claimed, a repeat, a
   *  measurement, or a note that the record was reverted. */
  meta: Record<string, unknown> | null;
}

export interface ListResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
  pages: number;
}

export type BrandRequestType = 'join' | 'create' | 'representative';
export type BrandRequestStatus = 'pending' | 'approved' | 'rejected';

export interface BrandRequest {
  id: number;
  user_id: number;
  user_email?: string | null; // Email пользователя для админки
  request_type: BrandRequestType;
  country?: string | null;
  organization_name?: string | null;
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

export interface FeedbackMessage {
  id: number;
  author_user_id: number | null;
  author_type: 'user' | 'admin';
  message: string;
  created_at: string;
}

export interface FeedbackDetail extends Feedback {
  messages: FeedbackMessage[];
}

export interface UnreadCommunicationsCount {
  unread_emails: number;
  new_feedback: number;
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

export type PresetLibraryScope = 'unscoped' | 'targeted' | 'compatible';

export interface UserSavedPreset {
  id: number;
  user_id: number;
  preset_id: number;
  saved_at: string; // ISO 8601 datetime string
  sync: boolean; // Включена ли синхронизация с OrcaSlicer для этого пресета у этого пользователя
  scope: PresetLibraryScope; // Выводится из набора целей: 0 → unscoped, 1 → targeted, 2+ → compatible
  target_printer_profile_ids: number[]; // PrinterProfile.id целевых принтер-профилей
}

export type PricingMethod = 'by_weight' | 'by_time' | 'combined';
export type RoundingMode = 'up' | 'down' | 'nearest';

export type CalculatorMaterialPriceSource = 'spool' | 'filamenthub' | 'slicer' | 'manual';

export interface CalculatorMaterialLineRequest {
  line_id: string;
  job_key?: string | null;
  tool_index?: number | null;
  label?: string | null;
  weight_g: number;
  spool_price: number;
  spool_weight_kg: number;
  delivery_cost?: number;
  price_source: CalculatorMaterialPriceSource;
  spool_id?: number | null;
  filament_id?: number | null;
  density_g_cm3?: number | null;
  abrasiveness?: number | null;
  role_weights_g?: Partial<Record<CalculatorMaterialRole, number>>;
  role_weight_source?: CalculatorMaterialRoleSource | null;
  support_weight_g?: number | null;
  support_weight_source?: CalculatorMaterialRoleSource | null;
}

export type CalculatorMaterialRole = 'support' | 'brim' | 'prime_tower';
export type CalculatorMaterialRoleSource = 'gcode_extrusion_roles';

export interface CalculatorMaterialRoleCost {
  role: CalculatorMaterialRole;
  weight_g: number;
  cost: number;
  source: CalculatorMaterialRoleSource;
}

export interface CalculatorMaterialLineCost {
  line_id: string;
  job_key?: string | null;
  tool_index?: number | null;
  label?: string | null;
  weight_g: number;
  price_per_gram: number;
  cost: number;
  price_source: CalculatorMaterialPriceSource;
  spool_id?: number | null;
  filament_id?: number | null;
  support_weight_g?: number | null;
  support_cost?: number | null;
  non_support_weight_g?: number | null;
  non_support_cost?: number | null;
  support_weight_source?: CalculatorMaterialRoleSource | null;
  role_costs?: CalculatorMaterialRoleCost[];
  other_weight_g?: number | null;
  other_cost?: number | null;
}

export interface CalculatorPrintJobRequest {
  job_key: string;
  repeats: number;
  output_quantity_per_run: number;
  print_time_seconds: number;
  quote_mode: 'set' | 'groups';
}

export type CalculatorPreflightStatus =
  | 'ready'
  | 'ready_with_change'
  | 'ready_at_risk'
  | 'insufficient'
  | 'needs_clarification'
  | 'conflict';

export interface CalculatorPreflightLineRequest {
  line_id: string;
  job_key?: string | null;
  tool_index?: number | null;
  label?: string | null;
  weight_g: number;
  length_mm?: number | null;
  volume_cm3?: number | null;
  filament_id?: number | null;
  spool_ids: number[];
  evidence_source: 'gcode' | 'manual';
  mapping_source: 'explicit' | 'automatic' | 'unresolved';
  mapping_confidence?: 'high' | 'medium' | 'low' | null;
}

export interface CalculatorPreflightRequest {
  lines: CalculatorPreflightLineRequest[];
  print_jobs: CalculatorPrintJobRequest[];
  physical_printer_id?: number | null;
  machine_evidence: CalculatorPreflightMachineEvidence[];
  quantity: number;
  safety_buffer_percent: number;
}

export interface CalculatorPreflightMachineEvidence {
  job_key?: string | null;
  printer_profile_id?: number | null;
  printer_settings_id?: string | null;
  nozzle_diameter_mm?: number | null;
  max_nozzle_temperature_c?: number | null;
  source: 'gcode' | 'orca_plugin';
}

export interface CalculatorPreflightSpoolAllocation {
  spool_id: number;
  filament_id: number | null;
  state: string;
  remaining_before_g: number;
  reserved_elsewhere_g: number;
  planned_coverage_g: number;
  expected_consumption_g: number;
  expected_after_g: number;
  sequence_index: number | null;
  remaining_source: 'inventory_ledger';
  remaining_status: 'known' | 'stale' | 'unknown';
  remaining_evidence:
    | 'measurement'
    | 'provider_report'
    | 'manual_update'
    | 'import'
    | 'intake'
    | 'estimate';
  remaining_confidence: 'high' | 'medium' | 'low';
  remaining_updated_at: string;
  last_used_at: string | null;
  purchase_currency: string | null;
  unit_purchase_cost_per_g: number | null;
  expected_purchase_cost: number | null;
  issues: Array<
    | 'material_mismatch'
    | 'unavailable_state'
    | 'empty'
    | 'stale_remaining'
    | 'unknown_remaining'
  >;
}

export interface CalculatorPreflightSpoolSuggestion {
  spool_id: number;
  filament_id: number;
  relation: 'same_filament' | 'same_line' | 'same_material_type';
  requires_reslice: boolean;
  remaining_g: number;
  reserved_elsewhere_g: number;
  coverage_target_g: number;
  covers_target: boolean;
  remaining_status: 'known' | 'stale' | 'unknown';
  remaining_evidence:
    | 'measurement'
    | 'provider_report'
    | 'manual_update'
    | 'import'
    | 'intake'
    | 'estimate';
  remaining_confidence: 'high' | 'medium' | 'low';
  remaining_updated_at: string;
}

export interface CalculatorPreflightLineResponse {
  line_id: string;
  job_key: string | null;
  tool_index: number | null;
  label: string | null;
  filament_id: number | null;
  status: CalculatorPreflightStatus;
  evidence_source: 'gcode' | 'manual';
  mapping_source: 'explicit' | 'automatic' | 'unresolved';
  mapping_confidence: 'high' | 'medium' | 'low' | null;
  required_base_g: number;
  required_length_mm: number | null;
  required_volume_cm3: number | null;
  safety_buffer_g: number;
  required_planned_g: number;
  selected_remaining_g: number;
  expected_after_g: number;
  shortfall_base_g: number;
  shortfall_buffer_g: number;
  change_count: number;
  requires_spool_change: boolean;
  purchase_cost_by_currency: Record<string, number>;
  purchase_cost_complete: boolean;
  allocations: CalculatorPreflightSpoolAllocation[];
  spool_suggestions: CalculatorPreflightSpoolSuggestion[];
}

export interface CalculatorPreflightResponse {
  status: CalculatorPreflightStatus;
  safety_buffer_percent: number;
  required_base_g: number;
  safety_buffer_g: number;
  required_planned_g: number;
  purchase_cost_by_currency: Record<string, number>;
  purchase_cost_complete: boolean;
  printer_compatibility: CalculatorPrinterCompatibility | null;
  lines: CalculatorPreflightLineResponse[];
}

export type CalculatorPrinterCompatibilityStatus = 'compatible' | 'incompatible' | 'unknown';

export interface CalculatorPrinterCompatibilityCheck {
  kind: 'nozzle_diameter' | 'nozzle_hrc' | 'hotend_temperature';
  status: CalculatorPrinterCompatibilityStatus;
  job_key: string | null;
  line_id: string | null;
  printer_profile_id: number | null;
  printer_profile_name: string | null;
  required_value: number | null;
  available_values: number[];
  unit: 'mm' | 'HRC' | '°C';
  requirement_source: 'gcode' | 'filament_catalog';
  capability_source: 'printer_profile' | 'catalog_printer' | null;
}

export interface CalculatorPrinterCompatibility {
  physical_printer_id: number;
  physical_printer_name: string;
  status: CalculatorPrinterCompatibilityStatus;
  checks: CalculatorPrinterCompatibilityCheck[];
}

export interface CalculatorEstimateRequest {
  pricing_method?: PricingMethod;
  
  // Параметры материала
  weight_g?: number | null;
  supports_weight_g?: number | null;
  supports_loss_coefficient?: number | null;
  spool_price?: number | null;
  spool_weight_kg?: number | null;
  delivery_cost?: number | null;
  material_lines?: CalculatorMaterialLineRequest[];
  print_jobs?: CalculatorPrintJobRequest[];
  
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
  cost_waste?: number;
  cost_electricity: number;
  cost_modeling: number;
  cost_printing: number;
  cost_postprocessing: number;
  cost_amortization: number;
  cost_monitoring?: number;
  cost_nozzle_wear?: number;
  cost_bed_prep: number;
  cost_tax: number;
  
  // Промежуточные расчеты
  cost_direct: number;
  cost_overhead: number;
  cost_before_markup: number;
  cost_markup: number;
  material_line_costs?: CalculatorMaterialLineCost[];
  
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
  print_runs?: number | null;
  
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

export interface CalculatorMaterialIdentityResolution {
  status: 'resolved' | 'ambiguous' | 'unresolved';
  source?:
    | 'filamenthub_filament_id'
    | 'filamenthub_preset_id'
    | 'user_preset_filament_id'
    | 'catalog_preset_filament_id'
    | null;
  stable_id: string;
  filament_id?: number | null;
  preset_id?: number | null;
  candidate_filament_ids: number[];
}

export interface CalculatorParsedMaterial {
  tool_index?: number | null;
  type?: string | null;
  name?: string | null;
  settings_id?: string | null;
  vendor?: string | null;
  color?: string | null;
  weight_g?: number | null;
  length_mm?: number | null;
  volume_cm3?: number | null;
  density_g_cm3?: number | null;
  diameter_mm?: number | null;
  slicer_filament_id?: string | null;
  identity_resolution?: CalculatorMaterialIdentityResolution | null;
  slicer_usage_cost?: number | null;
  slicer_profile_price_per_kg?: number | null;
  flow_ratio?: number | null;
  max_volumetric_speed_mm3_s?: number | null;
  prime_volume_mm3?: number | null;
  is_support_material?: boolean | null;
  used_for_model?: boolean | null;
  used_for_support?: boolean | null;
  infill_weight_g?: number | null;
  support_weight_g?: number | null;
  brim_weight_g?: number | null;
  prime_tower_weight_g?: number | null;
}

export interface CalculatorParsedObjectGroup {
  name: string;
  count: number;
  extrusion_share?: number | null;
  material_weights_g?: Record<string, number>;
}

export interface CalculatorFhubIdentity {
  kind: 'material_preset' | 'print_profile' | 'printer_profile';
  entity_id: number;
  tool_index?: number | null;
}

export interface CalculatorGcodeParseResponse {
  file_name: string;
  file_size_bytes: number;
  slicer_name?: string | null;
  slicer_version?: string | null;
  printer_settings_id?: string | null;
  print_settings_id?: string | null;
  printer_model?: string | null;
  fhub_identities?: CalculatorFhubIdentity[];
  print_time_seconds?: number | null;
  first_layer_print_time_seconds?: number | null;
  total_filament_weight_g?: number | null;
  total_filament_length_mm?: number | null;
  total_filament_volume_cm3?: number | null;
  infill_filament_weight_g?: number | null;
  support_filament_weight_g?: number | null;
  brim_filament_weight_g?: number | null;
  prime_tower_filament_weight_g?: number | null;
  object_filament_weight_g?: number | null;
  shared_filament_weight_g?: number | null;
  layer_height_mm?: number | null;
  initial_layer_height_mm?: number | null;
  sparse_infill_density_percent?: number | null;
  sparse_infill_pattern?: string | null;
  wall_loops?: number | null;
  outer_wall_line_width_mm?: number | null;
  inner_wall_line_width_mm?: number | null;
  outer_wall_speed_mm_s?: number | null;
  inner_wall_speed_mm_s?: number | null;
  sparse_infill_speed_mm_s?: number | null;
  support_speed_mm_s?: number | null;
  initial_layer_speed_mm_s?: number | null;
  prime_volume_mm3?: number | null;
  nozzle_diameter_mm?: number | null;
  nozzle_temperature_first_layer_c?: number | null;
  nozzle_temperature_other_layers_c?: number | null;
  bed_temperature_first_layer_c?: number | null;
  bed_temperature_other_layers_c?: number | null;
  object_count?: number | null;
  object_groups?: CalculatorParsedObjectGroup[];
  total_layers?: number | null;
  max_z_height_mm?: number | null;
  support_type?: string | null;
  support_threshold_angle_deg?: number | null;
  support_used?: boolean | null;
  support_filament_config_index?: number | null;
  support_interface_filament_config_index?: number | null;
  support_roles_detected?: string[];
  brim_width_mm?: number | null;
  raft_layers?: number | null;
  active_material_count?: number | null;
  is_multi_material?: boolean | null;
  toolchange_count?: number | null;
  thumbnail_data_url?: string | null;
  container_format?: 'plain_gcode' | 'gcode_3mf' | string;
  plate_index?: number | null;
  available_plate_indices?: number[];
  materials: CalculatorParsedMaterial[];
}

export interface CalculatorHistoryFilamentSnapshot {
  id?: number | null;
  name: string;
  brand_name?: string | null;
  material_type?: string | null;
  color_name?: string | null;
}

export interface CalculatorHistoryParsedJob {
  job_key: string;
  parsed_gcode: CalculatorGcodeParseResponse;
}

export interface CalculatorHistoryEntry {
  id: number;
  user_id: number;
  title: string;
  pricing_method: PricingMethod;
  request_data: CalculatorEstimateRequest;
  result_data: CalculatorEstimateResponse;
  parsed_gcode?: CalculatorGcodeParseResponse | null;
  parsed_jobs?: CalculatorHistoryParsedJob[];
  filament_snapshot?: CalculatorHistoryFilamentSnapshot | null;
  created_at: string;
  updated_at: string;
}

export interface CalculatorHistoryEntryCreate {
  title?: string | null;
  request_data: CalculatorEstimateRequest;
  result_data: CalculatorEstimateResponse;
  parsed_gcode?: CalculatorGcodeParseResponse | null;
  parsed_jobs?: CalculatorHistoryParsedJob[];
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
  printer_purchase_price: number;
  printer_useful_hours: number;
  maintenance_cost_per_hour: number;
  power_hotend_w: number;
  power_bed_w: number;
  power_steppers_w: number;
  power_electronics_w: number;
  rounding_mode: string;
  seller_name: string;
  seller_inn: string;
  seller_phone: string;
  payment_terms: string;
  seller_registration_id: string;
  seller_tax_code: string;
  seller_address: string;
  seller_bank_details: string;
  quote_market: string;
  validity_days: number;
  disclaimer_mode: string;
  currency: string;
  quote_number_prefix: string;
  updated_at: string;
}

export type CalculatorProfileUpdate = Partial<Omit<CalculatorProfileResponse, 'updated_at'>>;

export type CalculatorProfileDefaults = Omit<
  CalculatorProfileResponse,
  | 'seller_name'
  | 'seller_inn'
  | 'seller_phone'
  | 'payment_terms'
  | 'seller_registration_id'
  | 'seller_tax_code'
  | 'seller_address'
  | 'seller_bank_details'
  | 'quote_market'
  | 'validity_days'
  | 'disclaimer_mode'
  | 'currency'
  | 'quote_number_prefix'
  | 'updated_at'
>;

export interface SharedQuoteCreate {
  title?: string;
  html_content: string;
}

export interface SharedQuoteResponse {
  uuid: string;
  share_url: string;
  expires_at: string | null;
}

export type CrmQuoteStatus = 'draft' | 'sent' | 'accepted' | 'rejected' | 'expired';
export type CrmOrderStatus = 'new' | 'planned' | 'in_production' | 'ready' | 'completed' | 'cancelled';
export type CrmQuoteEventType = 'created' | 'version_created' | 'status_changed' | 'customer_changed' | 'shared';

export interface CrmCustomer {
  id: number;
  name: string;
  contact_name: string | null;
  email: string | null;
  phone: string | null;
  inn: string | null;
  address: string | null;
  note: string | null;
  archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface CrmCustomerCreate {
  name: string;
  contact_name?: string | null;
  email?: string | null;
  phone?: string | null;
  inn?: string | null;
  address?: string | null;
  note?: string | null;
}

export type CrmCustomerUpdate = Partial<CrmCustomerCreate> & { archived?: boolean };

export interface CrmQuoteLineCreate {
  title: string;
  details: string[];
  quantity: number;
  unit?: string;
  unit_price: number;
  source_data?: Record<string, unknown> | null;
}

export interface CrmQuoteLine extends Required<Omit<CrmQuoteLineCreate, 'source_data'>> {
  id: number;
  position: number;
  total_price: number;
  source_data: Record<string, unknown> | null;
}

export interface CrmQuoteVersionPayload {
  source_history_id?: number | null;
  seller_snapshot: Record<string, unknown>;
  customer_snapshot: Record<string, unknown>;
  calculation_snapshot?: Record<string, unknown> | null;
  payment_terms?: string | null;
  disclaimer_mode: 'offer' | 'not_offer';
  tax_total?: number;
  html_content?: string | null;
  lines: CrmQuoteLineCreate[];
}

export interface CrmQuoteCreate extends CrmQuoteVersionPayload {
  customer_id?: number | null;
  new_customer?: CrmCustomerCreate | null;
  number?: string | null;
  title: string;
  currency: string;
  valid_until?: string | null;
}

export interface CrmQuoteVersion {
  id: number;
  version_number: number;
  source_history_id: number | null;
  shared_quote_id: number | null;
  seller_snapshot: Record<string, unknown>;
  customer_snapshot: Record<string, unknown>;
  calculation_snapshot: Record<string, unknown> | null;
  payment_terms: string | null;
  disclaimer_mode: string;
  subtotal: number;
  tax_total: number;
  grand_total: number;
  html_content: string | null;
  lines: CrmQuoteLine[];
  created_at: string;
}

export interface CrmQuoteEvent {
  id: number;
  event_type: CrmQuoteEventType;
  from_status: string | null;
  to_status: string | null;
  details: Record<string, unknown> | null;
  created_at: string;
}

export interface CrmOrder {
  id: number;
  quote_id: number;
  customer_id: number | null;
  number: string;
  title: string;
  status: CrmOrderStatus;
  currency: string;
  total: number;
  due_date: string | null;
  note: string | null;
  material_requirements: CrmOrderMaterialRequirement[];
  spool_reservations: CrmOrderSpoolReservation[];
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  customer: CrmCustomer | null;
}

export interface CrmOrderMaterialRequirement {
  line_id: string;
  label: string | null;
  filament_id: number | null;
  required_base_g: number;
  required_planned_g: number;
  suggested_spool_ids: number[];
  suggested_allocations: Array<{ spool_id: number; weight_g: number }>;
}

export interface CrmOrderSpoolReservation {
  id: number;
  material_line_key: string;
  material_label: string | null;
  spool_id: number;
  filament_id: number | null;
  spool_label: string;
  weight_g: number;
  status: 'active' | 'released';
  created_at: string;
}

export interface CrmOrderSpoolReservationCreate {
  material_line_key: string;
  material_label?: string | null;
  spool_id: number;
  weight_g: number;
}

export interface CrmQuote {
  id: number;
  customer_id: number | null;
  number: string;
  title: string;
  status: CrmQuoteStatus;
  currency: string;
  valid_until: string | null;
  sent_at: string | null;
  accepted_at: string | null;
  rejected_at: string | null;
  created_at: string;
  updated_at: string;
  customer: CrmCustomer | null;
  current_version: CrmQuoteVersion;
  order: CrmOrder | null;
}

export interface CrmQuoteDetail extends CrmQuote {
  versions: CrmQuoteVersion[];
  events: CrmQuoteEvent[];
}

export interface CrmWorkspaceSummary {
  customers_total: number;
  quotes_draft: number;
  quotes_sent: number;
  quotes_accepted: number;
  orders_active: number;
  orders_completed: number;
  amount_awaiting_decision: Record<string, number>;
  accepted_amount: Record<string, number>;
}

export interface PluginDownload {
  plugin: 'orcaslicer' | 'octoprint' | 'print_farm';
  filename: string;
  version: string;
  file_size: string;
  checksum: string | null;
  download_url: string;
  github_url: string | null;
}

export interface PluginDownloadsResponse {
  packages: PluginDownload[];
  release_url: string | null;
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
  space_key: WikiSpaceKey;
  language: WikiLanguage;
  provenance: WikiRevisionAuthorship;
  title: string;
  slug: string;
  content_key: string;
  summary: string;
  tags: string[] | null;
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

export type WikiSpaceKey = 'guides' | 'knowledge';
export type WikiLanguage = 'ru' | 'en' | 'zh';
export type WikiRevisionStatus = 'draft' | 'pending_review' | 'published' | 'rejected' | 'withdrawn';
export type WikiRevisionAuthorship = 'editorial' | 'community';
export type WikiReviewVerdict = 'support' | 'needs_changes';

export interface WikiSpace {
  key: WikiSpaceKey;
  order: number;
  allows_community_authors: boolean;
}

export interface WikiRevisionReview {
  id: number;
  reviewer_id: number | null;
  reviewer_username: string | null;
  verdict: WikiReviewVerdict;
  comment: string | null;
  evidence_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface WikiRevision {
  id: number;
  article_id: number;
  article_category_id: number;
  article_slug: string;
  article_content_key: string;
  article_title: string;
  article_space_key: WikiSpaceKey;
  article_language: WikiLanguage;
  article_provenance: WikiRevisionAuthorship;
    revision_number: number;
    base_revision_id: number | null;
    base_title: string | null;
    base_summary: string | null;
    base_content: string | null;
    base_tags: string[] | null;
  created_by_id: number | null;
  created_by_username: string | null;
  reviewed_by_id: number | null;
  reviewed_by_username: string | null;
  status: WikiRevisionStatus;
  authorship: WikiRevisionAuthorship;
  title: string;
  summary: string;
  content: string;
  tags: string[] | null;
  edit_summary: string | null;
  review_note: string | null;
  submitted_at: string | null;
  reviewed_at: string | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
  peer_reviews: WikiRevisionReview[];
}

export interface WikiArticleTranslation {
  content_key: string;
  language: WikiLanguage;
  slug: string;
}

export interface WikiMediaAsset {
  id: string;
  url: string;
  mime_type: 'image/webp';
  width: number;
  height: number;
  size_bytes: number;
  created_at: string;
}

export interface WikiGuideProgressResponse {
  guide_ids: string[];
}

export interface WikiRevisionListResponse {
  items: WikiRevision[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface WikiPublicRevision {
  id: number;
  revision_number: number;
  base_revision_id: number | null;
  created_by_username: string | null;
  authorship: WikiRevisionAuthorship;
  title: string;
  summary: string;
  content: string;
  tags: string[] | null;
  edit_summary: string | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface WikiPublicRevisionListResponse {
  items: WikiPublicRevision[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export type OrcaPresetScope = 'filament' | 'process' | 'machine';
export type OrcaSchemaObservationStatus = 'new' | 'reviewed';

export interface OrcaSchemaObservation {
  id: number;
  scope: OrcaPresetScope;
  field_name: string;
  value_shape: string;
  status: OrcaSchemaObservationStatus;
  occurrences: number;
  registry_version: string;
  first_source: string;
  last_source: string;
  first_seen_at: string;
  last_seen_at: string;
  reviewed_at: string | null;
  reviewed_by_user_id: number | null;
}

export interface OrcaSchemaObservationListResponse {
  items: OrcaSchemaObservation[];
  total: number;
  new_count: number;
  page: number;
  size: number;
  pages: number;
  registry_version: string;
}

/** Региональная витрина бренда: одна страна — одна ячейка. */
export type CountryAvailability = 'available' | 'unavailable' | 'coming_soon' | 'discontinued' | 'unknown';

export interface FilamentCountryCell {
  id: number;
  filament_id: number;
  country: string;
  availability: CountryAvailability;
  price: number | null;
  currency: string | null;
  price_display_unit: 'per_kg' | 'per_spool' | null;
  product_url: string | null;
  purchase_links: { platform: string; url: string }[] | null;
  market_note: string | null;
  market_color_name: string | null;
  published: boolean;
  price_updated_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface BrandCountryCell {
  id: number;
  brand_id: number;
  country: string;
  website: string | null;
  description: string | null;
  social_media_urls: string[] | null;
  currency: string | null;
  shop_links: { platform: string; url: string }[] | null;
  published: boolean;
  created_at: string;
  updated_at: string;
}
