import type { CatalogImportSheet } from '../../../types/api';

export type FieldKind =
  | 'text' | 'textarea' | 'number' | 'bool' | 'select' | 'availability' | 'marketAvailability'
  | 'colorHex' | 'colors' | 'colorGroup' | 'social' | 'shop' | 'country';

/** Columns taken out of six in the editor grid: 2 = three per row, 3 = two per row, 6 = full row. */
export type FieldSpan = 2 | 3 | 6;

export interface FieldSpec {
  kind: FieldKind;
  span: FieldSpan;
  /** Raw option codes and the translation prefix that names them. */
  options?: readonly string[];
  optionsKey?: string;
}

export const FILAMENT_AVAILABILITY = ['available', 'out_of_stock', 'discontinued', 'coming_soon'] as const;
export const MARKET_AVAILABILITY = ['available', 'unavailable', 'coming_soon', 'discontinued', 'unknown'] as const;

const BOOLEAN_FIELDS = new Set([
  'enabled', 'overwrite', 'active', 'published', 'price_hidden', 'drying_required', 'transparency',
  'storage_airtight_required', 'storage_desiccant_recommended', 'storage_light_protection_required',
]);
const NUMBER_FIELD = /(?:temp|temperature|humidity|density|diameter|duration|months|hrc|flow_rate|fan_speed|retraction)/;
const TEXTAREA_FIELDS = new Set(['description', 'storage_after_opening_guidance', 'market_note']);
const FULL_ROW_FIELDS = new Set(['name', 'product_url', 'orcaslicer_settings', 'printer_ids']);

export function fieldSpec(sheet: CatalogImportSheet, field: string): FieldSpec {
  if (BOOLEAN_FIELDS.has(field)) return { kind: 'bool', span: 3 };
  if (field === 'social_media_urls') return { kind: 'social', span: 3 };
  if (field === 'shop_links') return { kind: 'shop', span: 3 };
  if (field === 'purchase_links') return { kind: 'shop', span: 6 };
  if (field === 'colors') return { kind: 'colors', span: 6 };
  if (field === 'color_hex' || field === 'logo_bg') return { kind: 'colorHex', span: 3 };
  if (field === 'color_group') return { kind: 'colorGroup', span: 3 };
  if (field === 'country') return { kind: 'country', span: 2 };
  if (field === 'availability') {
    return sheet === 'filament_markets'
      ? { kind: 'marketAvailability', span: 3, options: MARKET_AVAILABILITY, optionsKey: 'filamentMarket.availability_' }
      : { kind: 'availability', span: 3, options: FILAMENT_AVAILABILITY, optionsKey: 'createFilament.availability.' };
  }
  if (field === 'mode') {
    return {
      kind: 'select', span: 3,
      options: ['auto', 'create', 'update', ...(sheet === 'presets' ? ['fork'] : [])],
      optionsKey: 'adminCatalogImport.curation.modes.',
    };
  }
  if (field === 'color_type') {
    return {
      kind: 'select', span: 3,
      options: ['single', 'two', 'three', 'gradient', 'transition', 'thermochromic'],
      optionsKey: 'adminCatalogImport.curation.colorTypes.',
    };
  }
  if (field === 'finish') {
    return { kind: 'select', span: 3, options: ['matte', 'glossy'], optionsKey: 'adminCatalogImport.curation.visualTerms.' };
  }
  if (TEXTAREA_FIELDS.has(field)) return { kind: 'textarea', span: 6 };
  if (NUMBER_FIELD.test(field)) return { kind: 'number', span: 2 };
  return { kind: 'text', span: FULL_ROW_FIELDS.has(field) ? 6 : 3 };
}

export interface FieldGroup {
  key: string;
  fields: string[];
  collapsed?: boolean;
}

export const FILAMENT_GROUPS: FieldGroup[] = [
  { key: 'identity', fields: ['line', 'material_type', 'diameter', 'availability'] },
  { key: 'appearance', fields: ['color_name', 'color_hex', 'ral_code', 'color_group', 'color_type', 'finish', 'transparency', 'colors'] },
  { key: 'printing', fields: ['recommended_nozzle_temp_min', 'recommended_nozzle_temp_max', 'recommended_bed_temp_min', 'recommended_bed_temp_max', 'enclosure_requirement', 'chamber_temperature_c', 'bed_adhesives', 'required_nozzle_hrc', 'post_processing_chemicals'] },
  { key: 'care', collapsed: true, fields: ['drying_required', 'drying_temperature_c', 'drying_duration_hours', 'storage_temperature_min_c', 'storage_temperature_max_c', 'storage_relative_humidity_max_percent', 'storage_relative_humidity_target_percent', 'storage_airtight_required', 'storage_desiccant_recommended', 'storage_light_protection_required', 'storage_after_opening_guidance', 'unopened_shelf_life_months'] },
  { key: 'description', fields: ['description'] },
];

/** Fields drawn by the composition block instead of the plain grid. */
export const FEATURE_FIELDS = ['effects', 'additives', 'property_claims'] as const;

export const TECHNICAL_KEYS: Record<CatalogImportSheet, string[]> = {
  brands: ['brand_key', 'mode', 'existing_brand', 'overwrite', 'slug'],
  filaments: ['filament_key', 'brand_key', 'mode', 'existing_filament', 'overwrite'],
  brand_markets: ['brand_key', 'overwrite'],
  filament_markets: ['filament_key', 'overwrite'],
  presets: ['preset_key', 'filament_key', 'mode', 'existing_preset', 'overwrite', 'external_id'],
};

export const SHEET_GROUPS: Record<CatalogImportSheet, FieldGroup[]> = {
  brands: [
    { key: 'identity', fields: ['website', 'logo_url', 'logo_bg', 'price_hidden'] },
    { key: 'links', fields: ['social_media_urls', 'shop_links'] },
    { key: 'description', fields: ['description'] },
  ],
  filaments: FILAMENT_GROUPS,
  brand_markets: [
    { key: 'identity', fields: ['country', 'published', 'website'] },
    { key: 'links', fields: ['social_media_urls', 'shop_links'] },
    { key: 'description', fields: ['description'] },
  ],
  filament_markets: [
    { key: 'identity', fields: ['country', 'availability', 'published', 'market_color_name', 'product_url'] },
    { key: 'links', fields: ['purchase_links'] },
    { key: 'description', fields: ['market_note'] },
  ],
  presets: [
    { key: 'identity', fields: ['description', 'extruder_temp', 'bed_temp', 'flow_rate', 'fan_speed', 'retraction_length', 'retraction_speed', 'printer_ids', 'orcaslicer_settings'] },
  ],
};

export interface BulkFieldDef {
  id: string;
  field: string;
  /** Applies to the market rows of the selected records instead of the records themselves. */
  market?: boolean;
}

const own = (field: string): BulkFieldDef => ({ id: field, field });
const market = (field: string): BulkFieldDef => ({ id: `market:${field}`, field, market: true });

export const BULK_FIELDS: Record<CatalogImportSheet, BulkFieldDef[]> = {
  brands: [own('enabled'), own('active'), market('published')],
  filaments: [
    ...['enabled', 'active', 'availability', 'line', 'diameter',
      'recommended_nozzle_temp_min', 'recommended_nozzle_temp_max', 'recommended_bed_temp_min', 'recommended_bed_temp_max',
      'drying_required', 'drying_temperature_c', 'drying_duration_hours', 'finish'].map(own),
    market('availability'), market('published'), market('market_note'),
  ],
  brand_markets: [own('enabled'), own('published')],
  filament_markets: [own('enabled'), own('availability'), own('published'), own('market_note')],
  presets: [own('enabled'), own('active')],
};

/** Market fields that are usually identical across a brand's country: edited once for the whole group. */
export const MARKET_DEFAULT_FIELDS = ['availability', 'published'] as const;

/** Where each group is shown (name is the header field of the editor). */
export const HEADER_FIELD = 'name';

/** Fields the backend accepts per sheet; the editor offers the ones a row lacks. */
export const PROPOSAL_FIELDS: Record<CatalogImportSheet, string[]> = {
  brands: [
    'enabled', 'brand_key', 'mode', 'existing_brand', 'overwrite', 'name', 'slug', 'description',
    'website', 'logo_url', 'logo_bg', 'price_hidden', 'active',
    'social_media_urls', 'shop_links',
  ],
  filaments: [
    'enabled', 'filament_key', 'brand_key', 'mode', 'existing_filament', 'overwrite', 'name', 'line',
    'material_type', 'color_name', 'color_hex', 'ral_code', 'color_group', 'color_group_source',
    'diameter', 'density', 'drying_required', 'drying_temperature_c', 'drying_duration_hours',
    'storage_temperature_min_c', 'storage_temperature_max_c',
    'storage_relative_humidity_max_percent', 'storage_relative_humidity_target_percent',
    'storage_airtight_required', 'storage_desiccant_recommended',
    'storage_light_protection_required', 'storage_after_opening_guidance',
    'unopened_shelf_life_months',
    'enclosure_requirement', 'chamber_temperature_c', 'bed_adhesives', 'recommended_nozzle_temp_min',
    'recommended_nozzle_temp_max', 'recommended_bed_temp_min', 'recommended_bed_temp_max',
    'required_nozzle_hrc',
    'availability', 'description', 'active', 'color_type', 'colors', 'finish', 'effects', 'filler', 'transparency',
    'additives', 'property_claims', 'post_processing_chemicals',
  ],
  brand_markets: [
    'enabled', 'brand_key', 'country', 'overwrite', 'website', 'description', 'social_media_urls',
    'shop_links', 'published',
  ],
  filament_markets: [
    'enabled', 'filament_key', 'country', 'overwrite', 'availability',
    'product_url', 'purchase_links', 'market_note', 'market_color_name', 'published',
  ],
  presets: [
    'enabled', 'preset_key', 'filament_key', 'mode', 'existing_preset', 'overwrite', 'name', 'description',
    'extruder_temp', 'bed_temp', 'flow_rate', 'fan_speed', 'retraction_length', 'retraction_speed',
    'printer_ids', 'orcaslicer_settings', 'external_id', 'active',
  ],
};
