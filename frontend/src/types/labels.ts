export type LabelField =
  | "nozzle"
  | "bed"
  | "drying"
  | "abrasiveness"
  | "diameter"
  | "density"
  | "weight"
  | "chamber";

export interface LabelOptions {
  width_mm: number;
  height_mm: number;
  kind: "full" | "classic";
  color_mode: "mono" | "color";
  dpi: 203 | 300 | 600;
  locale: "ru" | "en" | "zh";
  attribution: "full" | "mark" | "none";
  qr_mark: boolean;
  brand_logo: boolean;
  fields: LabelField[];
  comment: string;
}

export interface LabelExportOptions {
  label: LabelOptions;
  format: "svg" | "png" | "pdf";
  media: "single" | "a4" | "letter";
  copies: number;
  start_position: number;
  page_margin_mm: number;
  gap_mm: number;
}

export interface LabelMetadata {
  data: {
    sku: string;
    brand: string;
    material: string;
    name: string;
    ral: string;
    fields: [LabelField, string, string][];
  };
  media_presets: { width_mm: number; height_mm: number }[];
  classic_presets_mm: number[];
  sheet_media: Record<"a4" | "letter", { width_mm: number; height_mm: number }>;
  brand_logo_available: boolean;
}

export interface LabelSheet {
  width_mm: number;
  height_mm: number;
  columns: number;
  rows: number;
  capacity: number;
  page_count: number;
}

export interface LabelPreview {
  svg: string;
  page_svg: string;
  page_width_mm: number;
  page_height_mm: number;
  capacity: number;
  sheet: LabelSheet;
  page_number: number;
  page_copies: number;
  scene: {
    dots_per_module: number;
    body_size_mm: number;
    qr: { width: number };
  };
  modules: number;
  revision: string;
  proof_required: boolean;
  printable: boolean;
}
