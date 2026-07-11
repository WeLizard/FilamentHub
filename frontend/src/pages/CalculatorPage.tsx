/**
 * Calculator Pro page wired to the current backend estimate API,
 * G-code parsing flow, and persisted calculation history.
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Calculator,
  Boxes,
  ChevronDown,
  CheckCircle2,
  Clock,
  CloudDownload,
  CloudUpload,
  FileText,
  HelpCircle,
  Link2,
  Layers3,
  Loader2,
  Plus,
  Printer,
  Save,
  Settings2,
  Sparkles,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import { calculatorAPI, filamentsAPI, spoolsAPI, type UserSpool } from '../api/client';
import { ConfirmDeleteModal } from '../components/ConfirmDeleteModal';
import { useAuth } from '../contexts/AuthContext';
import { useHeaderVisible } from '../hooks/useHeaderVisible';
import { translateApiError } from '../utils/translateApiError';
import { currencySymbol, normalizeCurrency, CURRENCY_CODES, defaultCurrencyForLanguage } from '../utils/currency';
import {
  findPrioritizedMaterialMatch,
  pickPrimaryParsedMaterial,
  type MaterialMatchConfidence,
} from '../utils/calculatorMaterialMatcher';
import { allocateRoundedTotal, quoteTitleFromFileName } from '../utils/calculatorQuote';
import {
  buildConfiguredCalculatorBatchSummary,
  calculatorOutputQuantityPerRun,
  canSplitCalculatorObjectGroups,
  type CalculatorQuoteMode,
} from '../utils/calculatorBatch';
import { safeStorage } from '../utils/storage';
import type {
  CalculatorEstimateRequest,
  CalculatorEstimateResponse,
  CalculatorGcodeParseResponse,
  CalculatorHistoryEntry,
  CalculatorHistoryEntryCreate,
  CalculatorHistoryFilamentSnapshot,
  CalculatorMaterialLineRequest,
  CalculatorParsedMaterial,
  CalculatorPrintJobRequest,
  Filament,
  PricingMethod,
  RoundingMode,
} from '../types/api';

const surfaceClass =
  'relative rounded-[2rem] border border-white/10 bg-[linear-gradient(180deg,rgba(15,23,42,0.88),rgba(15,23,42,0.72))] shadow-[0_30px_90px_-50px_rgba(15,23,42,0.95)] backdrop-blur-xl';
const inputClass =
  'w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-400/60 focus:border-transparent transition-all';
const numberInputResetClass =
  '[appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none';
const compactNumericInputClass = `${inputClass} ${numberInputResetClass} w-full sm:max-w-[15rem]`;
const ghostButtonClass =
  'inline-flex items-center justify-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-medium text-white transition-all hover:bg-white/10';

type CalculatorTab = 'calculator' | 'history';
type QuoteDisclaimerMode = 'not_offer' | 'offer';
type CurrencyCode = string;

interface QuoteProfileState {
  sellerName: string;
  sellerInn: string;
  sellerPhone: string;
  paymentTerms: string;
  validityDays: number;
  disclaimerMode: QuoteDisclaimerMode;
  currency: CurrencyCode;
  quoteNumberPrefix: string;
}

interface CalculatorFormState {
  selectedFilamentId: number | '';
  pricingMethod: PricingMethod;
  weightG: number;
  supportsWeightG: number;
  supportsLossCoefficient: number;
  spoolPrice: number;
  spoolWeightKg: number;
  deliveryCost: number;
  timeHours: number;
  timeMinutes: number;
  timeSec: number;
  pricePerHour: number;
  electricityCostPerKwh: number;
  printerPowerW: number;
  powerHotendW: number;
  powerBedW: number;
  powerSteppersW: number;
  powerElectronicsW: number;
  modelingHours: number;
  modelingMinutes: number;
  modelingRatePerHour: number;
  postprocessingHours: number;
  postprocessingMinutes: number;
  postprocessingRatePerHour: number;
  printingRatePerHour: number;
  amortizationRatePerHour: number;
  printerPurchasePrice: number;
  printerUsefulHours: number;
  quantity: number;
  overheadPercent: number;
  markupPercent: number;
  taxRatePercent: number;
  urgencyCoefficient: number;
  complexityCoefficient: number;
  volumeDiscountCoefficient: number;
  fixedCosts: number;
  bedPrepCostPerPrint: number;
  minOrderPrice: number;
  roundToNearest: number;
  roundingMode: RoundingMode;
}

interface QuotePartyFormState extends QuoteProfileState {
  buyerName: string;
  buyerInn: string;
  buyerAddress: string;
}

interface MaterialSelectionSnapshot {
  id: number | null;
  name: string;
  brand_name: string | null;
  material_type: string | null;
  color_name: string | null;
}

interface AutoMaterialMatchNotice {
  confidence: MaterialMatchConfidence;
  source: 'catalog' | 'spool';
  requiresSpoolChoice?: boolean;
}

type MaterialPriceSource = 'manual' | 'spool' | 'filamenthub' | 'slicer' | 'unset';

interface AutoMaterialMatchCandidate {
  filamentId: number;
  name: string | null;
  vendor: string | null;
  materialType: string | null;
  color: string | null;
  spoolIds: number[];
}

interface ParsedJobState {
  key: string;
  parsed: CalculatorGcodeParseResponse;
}

export interface CalculatorJobConfig {
  jobKey: string;
  repeats: number;
  quoteMode: CalculatorQuoteMode;
  printTimeSeconds: number;
}

const createDefaultJobConfig = (job: ParsedJobState): CalculatorJobConfig => ({
  jobKey: job.key,
  repeats: 1,
  quoteMode: (job.parsed.object_groups?.length ?? 0) === 1 ? 'groups' : 'set',
  printTimeSeconds: Math.max(0, job.parsed.print_time_seconds ?? 0),
});

interface CalculatorMaterialLineState extends CalculatorMaterialLineRequest {
  selectionValue: string;
  fileName: string;
  plateIndex: number | null;
  confidence: MaterialMatchConfidence | null;
  requiresSpoolChoice: boolean;
  priceResolved: boolean;
}

const DEFAULT_FORM_STATE: CalculatorFormState = {
  selectedFilamentId: '',
  pricingMethod: 'combined',
  weightG: 0,
  supportsWeightG: 0,
  supportsLossCoefficient: 1.2,
  spoolPrice: 0,
  spoolWeightKg: 1,
  deliveryCost: 0,
  timeHours: 0,
  timeMinutes: 0,
  timeSec: 0,
  pricePerHour: 170,
  electricityCostPerKwh: 6,
  printerPowerW: 350,
  powerHotendW: 0,
  powerBedW: 0,
  powerSteppersW: 0,
  powerElectronicsW: 0,
  modelingHours: 0,
  modelingMinutes: 0,
  modelingRatePerHour: 934,
  postprocessingHours: 0,
  postprocessingMinutes: 0,
  postprocessingRatePerHour: 100,
  printingRatePerHour: 170,
  amortizationRatePerHour: 16,
  printerPurchasePrice: 0,
  printerUsefulHours: 0,
  quantity: 1,
  overheadPercent: 20,
  markupPercent: 30,
  taxRatePercent: 0,
  urgencyCoefficient: 1.0,
  complexityCoefficient: 1.0,
  volumeDiscountCoefficient: 1.0,
  fixedCosts: 0,
  bedPrepCostPerPrint: 0,
  minOrderPrice: 0,
  roundToNearest: 10,
  roundingMode: 'up',
};

const CALCULATOR_STATIC_FIELDS = [
  'electricityCostPerKwh',
  'printerPowerW',
  'powerHotendW',
  'powerBedW',
  'powerSteppersW',
  'powerElectronicsW',
  'modelingRatePerHour',
  'postprocessingRatePerHour',
  'printingRatePerHour',
  'amortizationRatePerHour',
  'printerPurchasePrice',
  'printerUsefulHours',
  'overheadPercent',
  'markupPercent',
  'taxRatePercent',
  'fixedCosts',
  'bedPrepCostPerPrint',
  'minOrderPrice',
  'roundToNearest',
  'roundingMode',
] as const;

type CalculatorStaticSettingKey = (typeof CALCULATOR_STATIC_FIELDS)[number];
type CalculatorStaticSettings = Pick<CalculatorFormState, CalculatorStaticSettingKey>;

interface PricingPreset {
  name: string;
  urgencyCoefficient: number;
  complexityCoefficient: number;
  volumeDiscountCoefficient: number;
  isBuiltin?: boolean;
}

const BUILTIN_PRICING_PRESETS: PricingPreset[] = [
  { name: 'standard', urgencyCoefficient: 1.0, complexityCoefficient: 1.0, volumeDiscountCoefficient: 1.0, isBuiltin: true },
  { name: 'urgent', urgencyCoefficient: 1.5, complexityCoefficient: 1.0, volumeDiscountCoefficient: 1.0, isBuiltin: true },
  { name: 'complex', urgencyCoefficient: 1.0, complexityCoefficient: 1.5, volumeDiscountCoefficient: 1.0, isBuiltin: true },
  { name: 'bulk', urgencyCoefficient: 1.0, complexityCoefficient: 1.0, volumeDiscountCoefficient: 0.9, isBuiltin: true },
];

const PRICING_PRESETS_STORAGE_KEY = 'filamenthub_pricing_presets_v1';

const loadCustomPricingPresets = (): PricingPreset[] => {
  try {
    const raw = safeStorage.get(PRICING_PRESETS_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as PricingPreset[]) : [];
  } catch {
    return [];
  }
};

const saveCustomPricingPresets = (presets: PricingPreset[]): void => {
  safeStorage.set(PRICING_PRESETS_STORAGE_KEY, JSON.stringify(presets));
};

const CALCULATOR_DEFAULTS_STORAGE_KEY = 'filamenthub_calculator_defaults_v1';
const QUOTE_PROFILE_STORAGE_KEY = 'filamenthub_calculator_quote_profile_v1';
const CURRENCY_OPTIONS: CurrencyCode[] = CURRENCY_CODES;

interface PostprocessOperation {
  id: string;
  i18nKey: string;
  defaultMinutes: number;
}

const POSTPROCESS_OPERATIONS: PostprocessOperation[] = [
  { id: 'remove_supports', i18nKey: 'postprocess.removeSupports', defaultMinutes: 10 },
  { id: 'sanding_rough', i18nKey: 'postprocess.sandingRough', defaultMinutes: 15 },
  { id: 'sanding_fine', i18nKey: 'postprocess.sandingFine', defaultMinutes: 20 },
  { id: 'priming', i18nKey: 'postprocess.priming', defaultMinutes: 15 },
  { id: 'painting', i18nKey: 'postprocess.painting', defaultMinutes: 30 },
  { id: 'gluing', i18nKey: 'postprocess.gluing', defaultMinutes: 10 },
  { id: 'assembly', i18nKey: 'postprocess.assembly', defaultMinutes: 15 },
  { id: 'threading', i18nKey: 'postprocess.threading', defaultMinutes: 10 },
  { id: 'heat_treatment', i18nKey: 'postprocess.heatTreatment', defaultMinutes: 60 },
  { id: 'acetone_smoothing', i18nKey: 'postprocess.acetoneSmoothing', defaultMinutes: 20 },
];

const DEFAULT_QUOTE_PROFILE: QuoteProfileState = {
  sellerName: '',
  sellerInn: '',
  sellerPhone: '',
  paymentTerms: '',
  validityDays: 14,
  disclaimerMode: 'not_offer',
  currency: 'RUB',
  quoteNumberPrefix: 'КП',
};
const DEFAULT_QUOTE_PARTY_FORM: QuotePartyFormState = {
  ...DEFAULT_QUOTE_PROFILE,
  buyerName: '',
  buyerInn: '',
  buyerAddress: '',
};

const makeCurrencyFormatter = (code: CurrencyCode) =>
  (value: number | null | undefined): string =>
    value == null || !Number.isFinite(value) ? '—' : `${value.toFixed(2)} ${currencySymbol(code)}`;

const formatQuantity = (value: number): string => `${value}`;

const toHours = (hours: number, minutes: number, seconds: number): number =>
  hours + minutes / 60 + seconds / 3600;

const buildFilamentLabel = (filament: Pick<MaterialSelectionSnapshot, 'brand_name' | 'name' | 'material_type'>): string =>
  [filament.brand_name, filament.name, filament.material_type].filter(Boolean).join(' · ');

const deriveCatalogFilamentDefaults = (
  filament: Filament,
): { spoolPrice: number | null; spoolWeightKg: number | null } => {
  const spoolWeightKg = filament.spool_weight ? Number((filament.spool_weight / 1000).toFixed(3)) : null;
  const spoolPrice =
    filament.price_per_kg != null
      ? Number((((filament.spool_weight ?? 1000) * filament.price_per_kg) / 1000).toFixed(2))
      : null;

  return { spoolPrice, spoolWeightKg };
};

const deriveUserSpoolDefaults = (
  spool: UserSpool,
): { spoolPrice: number | null; spoolWeightKg: number | null } => {
  const spoolWeightKg =
    spool.initial_weight_g > 0 ? Number((spool.initial_weight_g / 1000).toFixed(3)) : null;
  const spoolPrice =
    spool.price != null
      ? Number(spool.price.toFixed(2))
      : spool.filament?.price_per_kg != null
        ? Number(((spool.initial_weight_g * spool.filament.price_per_kg) / 1000).toFixed(2))
        : null;

  return { spoolPrice, spoolWeightKg };
};

const buildSpoolLabel = (spool: UserSpool): string => {
  if (!spool.filament) {
    return `#${spool.id}`;
  }

  return `${buildFilamentLabel(spool.filament)} · ${Math.round(spool.remaining_weight_g)} g`;
};

const buildEstimateRequest = (
  form: CalculatorFormState,
  materialLines: CalculatorMaterialLineState[] = [],
  parsedJobs: ParsedJobState[] = [],
  jobConfigs: CalculatorJobConfig[] = [],
): CalculatorEstimateRequest => {
  const requestData: CalculatorEstimateRequest = {
    pricing_method: 'combined',
    quantity: form.quantity,
    round_to_nearest: form.roundToNearest || undefined,
    rounding_mode: form.roundingMode,
  };

  requestData.weight_g = form.weightG;
  requestData.supports_weight_g = form.supportsWeightG || undefined;
  requestData.supports_loss_coefficient = form.supportsLossCoefficient || undefined;
  requestData.spool_price = form.spoolPrice;
  requestData.spool_weight_kg = form.spoolWeightKg;
  requestData.delivery_cost = form.deliveryCost || undefined;
  if (materialLines.length > 0) {
    requestData.material_lines = materialLines.map((line) => ({
      line_id: line.line_id,
      job_key: line.job_key,
      tool_index: line.tool_index,
      label: line.label,
      weight_g: line.weight_g,
      spool_price: line.spool_price,
      spool_weight_kg: line.spool_weight_kg,
      delivery_cost: line.delivery_cost,
      price_source: line.price_source,
      spool_id: line.spool_id,
      filament_id: line.filament_id,
      density_g_cm3: line.density_g_cm3,
      abrasiveness: line.abrasiveness,
    }));
  }
  if (parsedJobs.length > 0) {
    const configsByJob = new Map(jobConfigs.map((config) => [config.jobKey, config]));
    requestData.print_jobs = parsedJobs.map<CalculatorPrintJobRequest>((job) => {
      const config = configsByJob.get(job.key) ?? createDefaultJobConfig(job);
      const groups = job.parsed.object_groups ?? [];
      const quoteMode = config.quoteMode === 'groups'
        && groups.length > 1
        && !canSplitCalculatorObjectGroups(groups)
        ? 'set'
        : config.quoteMode;
      return {
        job_key: job.key,
        repeats: Math.max(1, Math.floor(config.repeats)),
        output_quantity_per_run: calculatorOutputQuantityPerRun(groups, quoteMode),
        print_time_seconds: Math.max(0, config.printTimeSeconds),
        quote_mode: quoteMode,
      };
    });
    requestData.quantity = requestData.print_jobs.reduce(
      (sum, job) => sum + job.output_quantity_per_run * job.repeats,
      0,
    );
  }
  requestData.time_hours = form.timeHours;
  requestData.time_minutes = form.timeMinutes;
  requestData.time_sec = form.timeSec || undefined;

  if (form.electricityCostPerKwh && form.printerPowerW) {
    requestData.electricity_cost_per_kwh = form.electricityCostPerKwh;
    requestData.printer_power_w = form.printerPowerW;
  }

  if (form.modelingRatePerHour) {
    requestData.modeling_hours = form.modelingHours;
    requestData.modeling_minutes = form.modelingMinutes;
    requestData.modeling_rate_per_hour = form.modelingRatePerHour;
  }

  if (form.postprocessingRatePerHour) {
    requestData.postprocessing_hours = form.postprocessingHours;
    requestData.postprocessing_minutes = form.postprocessingMinutes;
    requestData.postprocessing_rate_per_hour = form.postprocessingRatePerHour;
  }

  if (form.printingRatePerHour) {
    requestData.printing_rate_per_hour = form.printingRatePerHour;
  }

  if (form.amortizationRatePerHour) {
    requestData.amortization_rate_per_hour = form.amortizationRatePerHour;
  }

  requestData.overhead_percent = form.overheadPercent || undefined;
  requestData.markup_percent = form.markupPercent || undefined;
  requestData.tax_rate_percent = form.taxRatePercent || undefined;
  requestData.urgency_coefficient = form.urgencyCoefficient !== 1.0 ? form.urgencyCoefficient : undefined;
  requestData.complexity_coefficient = form.complexityCoefficient !== 1.0 ? form.complexityCoefficient : undefined;
  requestData.volume_discount_coefficient =
    form.volumeDiscountCoefficient !== 1.0 ? form.volumeDiscountCoefficient : undefined;
  requestData.fixed_costs = form.fixedCosts || undefined;
  requestData.bed_prep_cost_per_print = form.bedPrepCostPerPrint || undefined;
  requestData.min_order_price = form.minOrderPrice || undefined;

  return requestData;
};

const resolveParsedMaterialWeight = (
  material: CalculatorParsedMaterial,
  fallbackWeightG?: number | null,
): number => {
  if ((material.weight_g ?? 0) > 0) return material.weight_g!;
  if ((material.volume_cm3 ?? 0) > 0 && (material.density_g_cm3 ?? 0) > 0) {
    return Number((material.volume_cm3! * material.density_g_cm3!).toFixed(3));
  }
  if (
    (material.length_mm ?? 0) > 0
    && (material.diameter_mm ?? 0) > 0
    && (material.density_g_cm3 ?? 0) > 0
  ) {
    const radiusMm = material.diameter_mm! / 2;
    const volumeCm3 = (Math.PI * radiusMm * radiusMm * material.length_mm!) / 1000;
    return Number((volumeCm3 * material.density_g_cm3!).toFixed(3));
  }
  return fallbackWeightG && fallbackWeightG > 0 ? fallbackWeightG : 0;
};

const parsedJobKey = (parsed: CalculatorGcodeParseResponse, uploadIndex: number): string =>
  `${uploadIndex}:${parsed.file_name}:${parsed.file_size_bytes}:${parsed.plate_index ?? 0}`;

const formatHoursShort = (value: number | null | undefined, hourLabel: string, minLabel: string): string => {
  if (value == null || !Number.isFinite(value) || value <= 0) {
    return '—';
  }

  const wholeHours = Math.floor(value);
  const wholeMinutes = Math.round((value % 1) * 60);

  if (wholeHours === 0) {
    return `${wholeMinutes} ${minLabel}`;
  }

  if (wholeMinutes === 0) {
    return `${wholeHours} ${hourLabel}`;
  }

  return `${wholeHours} ${hourLabel} ${wholeMinutes} ${minLabel}`;
};

const escapeHtml = (value: string): string =>
  value
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');

const loadStoredQuoteProfile = (): Partial<QuoteProfileState> => {
  if (typeof window === 'undefined') {
    return {};
  }

  try {
    const raw = safeStorage.get(QUOTE_PROFILE_STORAGE_KEY);
    if (!raw) {
      return {};
    }

    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') {
      return {};
    }

    return {
      sellerName: typeof parsed.sellerName === 'string' ? parsed.sellerName : undefined,
      sellerInn: typeof parsed.sellerInn === 'string' ? parsed.sellerInn : undefined,
      sellerPhone: typeof parsed.sellerPhone === 'string' ? parsed.sellerPhone : undefined,
      paymentTerms: typeof parsed.paymentTerms === 'string' ? parsed.paymentTerms : undefined,
      validityDays:
        typeof parsed.validityDays === 'number' && Number.isFinite(parsed.validityDays)
          ? parsed.validityDays
          : undefined,
      disclaimerMode: parsed.disclaimerMode === 'offer' || parsed.disclaimerMode === 'not_offer'
        ? parsed.disclaimerMode
        : undefined,
      currency: parsed.currency ? normalizeCurrency(parsed.currency) : undefined,
      quoteNumberPrefix: typeof parsed.quoteNumberPrefix === 'string' ? parsed.quoteNumberPrefix : undefined,
    };
  } catch {
    return {};
  }
};

const saveStoredQuoteProfile = (data: QuoteProfileState): void => {
  if (typeof window === 'undefined') {
    return;
  }

  safeStorage.set(
    QUOTE_PROFILE_STORAGE_KEY,
    JSON.stringify({
      sellerName: data.sellerName,
      sellerInn: data.sellerInn,
      sellerPhone: data.sellerPhone,
      paymentTerms: data.paymentTerms,
      validityDays: data.validityDays,
      disclaimerMode: data.disclaimerMode,
      currency: data.currency,
      quoteNumberPrefix: data.quoteNumberPrefix,
    }),
  );
};

const addDays = (value: Date, days: number): Date => {
  const next = new Date(value);
  next.setDate(next.getDate() + days);
  return next;
};

const extractStaticSettings = (form: CalculatorFormState): CalculatorStaticSettings => ({
  electricityCostPerKwh: form.electricityCostPerKwh,
  printerPowerW: form.printerPowerW,
  powerHotendW: form.powerHotendW,
  powerBedW: form.powerBedW,
  powerSteppersW: form.powerSteppersW,
  powerElectronicsW: form.powerElectronicsW,
  modelingRatePerHour: form.modelingRatePerHour,
  postprocessingRatePerHour: form.postprocessingRatePerHour,
  printingRatePerHour: form.printingRatePerHour,
  amortizationRatePerHour: form.amortizationRatePerHour,
  printerPurchasePrice: form.printerPurchasePrice,
  printerUsefulHours: form.printerUsefulHours,
  overheadPercent: form.overheadPercent,
  markupPercent: form.markupPercent,
  taxRatePercent: form.taxRatePercent,
  fixedCosts: form.fixedCosts,
  bedPrepCostPerPrint: form.bedPrepCostPerPrint,
  minOrderPrice: form.minOrderPrice,
  roundToNearest: form.roundToNearest,
  roundingMode: form.roundingMode,
});

const loadStoredCalculatorDefaults = (): CalculatorStaticSettings => {
  const fallback = extractStaticSettings(DEFAULT_FORM_STATE);

  if (typeof window === 'undefined') {
    return fallback;
  }

  try {
    const raw = safeStorage.get(CALCULATOR_DEFAULTS_STORAGE_KEY);
    if (!raw) {
      return fallback;
    }

    const parsed = JSON.parse(raw) as Partial<Record<CalculatorStaticSettingKey, unknown>>;
    const numberOrFallback = (value: unknown, defaultValue: number): number =>
      typeof value === 'number' && Number.isFinite(value) ? value : defaultValue;

    return {
      electricityCostPerKwh: numberOrFallback(parsed.electricityCostPerKwh, fallback.electricityCostPerKwh),
      printerPowerW: numberOrFallback(parsed.printerPowerW, fallback.printerPowerW),
      powerHotendW: numberOrFallback(parsed.powerHotendW, fallback.powerHotendW),
      powerBedW: numberOrFallback(parsed.powerBedW, fallback.powerBedW),
      powerSteppersW: numberOrFallback(parsed.powerSteppersW, fallback.powerSteppersW),
      powerElectronicsW: numberOrFallback(parsed.powerElectronicsW, fallback.powerElectronicsW),
      modelingRatePerHour: numberOrFallback(parsed.modelingRatePerHour, fallback.modelingRatePerHour),
      postprocessingRatePerHour: numberOrFallback(parsed.postprocessingRatePerHour, fallback.postprocessingRatePerHour),
      printingRatePerHour: numberOrFallback(parsed.printingRatePerHour, fallback.printingRatePerHour),
      amortizationRatePerHour: numberOrFallback(parsed.amortizationRatePerHour, fallback.amortizationRatePerHour),
      printerPurchasePrice: numberOrFallback(parsed.printerPurchasePrice, fallback.printerPurchasePrice),
      printerUsefulHours: numberOrFallback(parsed.printerUsefulHours, fallback.printerUsefulHours),
      overheadPercent: numberOrFallback(parsed.overheadPercent, fallback.overheadPercent),
      markupPercent: numberOrFallback(parsed.markupPercent, fallback.markupPercent),
      taxRatePercent: numberOrFallback(parsed.taxRatePercent, fallback.taxRatePercent),
      fixedCosts: numberOrFallback(parsed.fixedCosts, fallback.fixedCosts),
      bedPrepCostPerPrint: numberOrFallback(parsed.bedPrepCostPerPrint, fallback.bedPrepCostPerPrint),
      minOrderPrice: numberOrFallback(parsed.minOrderPrice, fallback.minOrderPrice),
      roundToNearest: numberOrFallback(parsed.roundToNearest, fallback.roundToNearest),
      roundingMode:
        parsed.roundingMode === 'up' || parsed.roundingMode === 'nearest' || parsed.roundingMode === 'down'
          ? parsed.roundingMode
          : fallback.roundingMode,
    };
  } catch {
    return fallback;
  }
};

const saveStoredCalculatorDefaults = (data: CalculatorStaticSettings): void => {
  if (typeof window === 'undefined') {
    return;
  }

  safeStorage.set(CALCULATOR_DEFAULTS_STORAGE_KEY, JSON.stringify(data));
};

const splitSeconds = (totalSeconds: number): { hours: number; minutes: number; seconds: number } => {
  const safeSeconds = Math.max(0, Math.round(totalSeconds));
  return {
    hours: Math.floor(safeSeconds / 3600),
    minutes: Math.floor((safeSeconds % 3600) / 60),
    seconds: safeSeconds % 60,
  };
};

const formatFileSize = (bytes: number): string => {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return '—';
  }

  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }

  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
};

const translateCalculator = (t: TFunction, key: string): string =>
  t(`profilePage.calculator.${key}`);

const buildParsedMaterialLabel = (material: CalculatorParsedMaterial, fallbackLabel: string): string =>
  [material.vendor, material.name, material.type].filter(Boolean).join(' · ') || fallbackLabel;

const formatParsedTemperaturePair = (
  nozzleTemperature: number | null | undefined,
  bedTemperature: number | null | undefined,
): string | null => {
  if (nozzleTemperature == null && bedTemperature == null) {
    return null;
  }

  const nozzleLabel = nozzleTemperature != null ? `${nozzleTemperature}°C` : '—';
  const bedLabel = bedTemperature != null ? `${bedTemperature}°C` : '—';
  return `${nozzleLabel} / ${bedLabel}`;
};

const suggestComplexityCoefficient = (parsed: CalculatorGcodeParseResponse): number => {
  let coef = 1.0;

  // Multi-material / toolchanges
  if (parsed.toolchange_count != null && parsed.toolchange_count > 20) {
    coef += 0.3;
  } else if (parsed.toolchange_count != null && parsed.toolchange_count > 5) {
    coef += 0.15;
  } else if (parsed.is_multi_material) {
    coef += 0.1;
  }

  // Supports (tree/organic more complex than normal)
  if (parsed.support_type && parsed.support_type.toLowerCase() !== 'none') {
    const st = parsed.support_type.toLowerCase();
    coef += st.includes('tree') || st.includes('organic') ? 0.15 : 0.1;
  }

  // Fine layers
  if (parsed.layer_height_mm != null) {
    if (parsed.layer_height_mm < 0.1) coef += 0.2;
    else if (parsed.layer_height_mm < 0.15) coef += 0.1;
  }

  // High infill density
  if (parsed.sparse_infill_density_percent != null) {
    if (parsed.sparse_infill_density_percent > 80) coef += 0.15;
    else if (parsed.sparse_infill_density_percent > 60) coef += 0.1;
  }

  // Multiple objects on plate
  if (parsed.object_count != null) {
    if (parsed.object_count > 3) coef += 0.1;
    else if (parsed.object_count > 1) coef += 0.05;
  }

  // Many wall loops
  if (parsed.wall_loops != null) {
    if (parsed.wall_loops > 6) coef += 0.15;
    else if (parsed.wall_loops > 4) coef += 0.1;
  }

  return Math.min(2.5, Math.round(coef * 100) / 100);
};

const applyParsedGcodeToForm = (
  current: CalculatorFormState,
  parsed: CalculatorGcodeParseResponse,
): CalculatorFormState => {
  const nextForm: CalculatorFormState = { ...current };

  if (parsed.total_filament_weight_g != null && Number.isFinite(parsed.total_filament_weight_g)) {
    nextForm.weightG = Number(parsed.total_filament_weight_g.toFixed(2));
  }

  if (parsed.print_time_seconds != null && Number.isFinite(parsed.print_time_seconds)) {
    const duration = splitSeconds(parsed.print_time_seconds);
    nextForm.timeHours = duration.hours;
    nextForm.timeMinutes = duration.minutes;
    nextForm.timeSec = duration.seconds;
  }

  // Auto-suggest complexity coefficient from G-code metadata
  const suggestedComplexity = suggestComplexityCoefficient(parsed);
  if (suggestedComplexity > 1.0) {
    nextForm.complexityCoefficient = suggestedComplexity;
  }

  return nextForm;
};

const applyParsedJobsToForm = (
  current: CalculatorFormState,
  jobs: ParsedJobState[],
): CalculatorFormState => {
  if (jobs.length === 0) return current;

  const next = jobs.reduce(
    (accumulator, job) => applyParsedGcodeToForm(accumulator, job.parsed),
    { ...current },
  );
  const totalWeightG = jobs.reduce(
    (sum, job) => sum + (job.parsed.total_filament_weight_g ?? 0),
    0,
  );
  const totalSeconds = jobs.reduce(
    (sum, job) => sum + (job.parsed.print_time_seconds ?? 0),
    0,
  );
  if (totalWeightG > 0) next.weightG = Number(totalWeightG.toFixed(3));
  if (totalSeconds > 0) {
    next.timeHours = Math.floor(totalSeconds / 3600);
    next.timeMinutes = Math.floor((totalSeconds % 3600) / 60);
    next.timeSec = totalSeconds % 60;
  }
  next.complexityCoefficient = Math.max(
    current.complexityCoefficient,
    ...jobs.map((job) => suggestComplexityCoefficient(job.parsed)),
  );
  return next;
};

const buildHistoryFilamentSnapshot = (
  filament: MaterialSelectionSnapshot | null,
): CalculatorHistoryFilamentSnapshot | null => {
  if (!filament) {
    return null;
  }

  return {
    id: filament.id,
    name: filament.name,
    brand_name: filament.brand_name,
    material_type: filament.material_type,
    color_name: filament.color_name,
  };
};

const buildHistoryPayload = (
  form: CalculatorFormState,
  result: CalculatorEstimateResponse,
  parsedGcode: CalculatorGcodeParseResponse | null,
  selectedFilament: MaterialSelectionSnapshot | null,
  materialLines: CalculatorMaterialLineState[] = [],
  parsedJobs: ParsedJobState[] = [],
  jobConfigs: CalculatorJobConfig[] = [],
): CalculatorHistoryEntryCreate => ({
  request_data: buildEstimateRequest(form, materialLines, parsedJobs, jobConfigs),
  result_data: result,
  parsed_gcode: parsedGcode
    ? {
        ...parsedGcode,
        thumbnail_data_url: null,
      }
    : null,
  parsed_jobs: parsedJobs.map((job) => ({
    job_key: job.key,
    parsed_gcode: {
      ...job.parsed,
      thumbnail_data_url: null,
    },
  })),
  filament_snapshot: buildHistoryFilamentSnapshot(selectedFilament),
});

const buildFormFromHistoryEntry = (entry: CalculatorHistoryEntry): CalculatorFormState => {
  const request = entry.request_data;

  return {
    ...DEFAULT_FORM_STATE,
    selectedFilamentId: entry.filament_snapshot?.id ?? '',
    pricingMethod: request.pricing_method ?? DEFAULT_FORM_STATE.pricingMethod,
    weightG: request.weight_g ?? DEFAULT_FORM_STATE.weightG,
    supportsWeightG: request.supports_weight_g ?? DEFAULT_FORM_STATE.supportsWeightG,
    supportsLossCoefficient: request.supports_loss_coefficient ?? DEFAULT_FORM_STATE.supportsLossCoefficient,
    spoolPrice: request.spool_price ?? DEFAULT_FORM_STATE.spoolPrice,
    spoolWeightKg: request.spool_weight_kg ?? DEFAULT_FORM_STATE.spoolWeightKg,
    deliveryCost: request.delivery_cost ?? DEFAULT_FORM_STATE.deliveryCost,
    timeHours: request.time_hours ?? DEFAULT_FORM_STATE.timeHours,
    timeMinutes: request.time_minutes ?? DEFAULT_FORM_STATE.timeMinutes,
    timeSec: request.time_sec ?? DEFAULT_FORM_STATE.timeSec,
    pricePerHour: request.price_per_hour ?? DEFAULT_FORM_STATE.pricePerHour,
    electricityCostPerKwh: request.electricity_cost_per_kwh ?? DEFAULT_FORM_STATE.electricityCostPerKwh,
    printerPowerW: request.printer_power_w ?? DEFAULT_FORM_STATE.printerPowerW,
    modelingHours: request.modeling_hours ?? DEFAULT_FORM_STATE.modelingHours,
    modelingMinutes: request.modeling_minutes ?? DEFAULT_FORM_STATE.modelingMinutes,
    modelingRatePerHour: request.modeling_rate_per_hour ?? DEFAULT_FORM_STATE.modelingRatePerHour,
    postprocessingHours: request.postprocessing_hours ?? DEFAULT_FORM_STATE.postprocessingHours,
    postprocessingMinutes: request.postprocessing_minutes ?? DEFAULT_FORM_STATE.postprocessingMinutes,
    postprocessingRatePerHour: request.postprocessing_rate_per_hour ?? DEFAULT_FORM_STATE.postprocessingRatePerHour,
    printingRatePerHour: request.printing_rate_per_hour ?? DEFAULT_FORM_STATE.printingRatePerHour,
    amortizationRatePerHour: request.amortization_rate_per_hour ?? DEFAULT_FORM_STATE.amortizationRatePerHour,
    quantity: request.quantity ?? DEFAULT_FORM_STATE.quantity,
    overheadPercent: request.overhead_percent ?? DEFAULT_FORM_STATE.overheadPercent,
    markupPercent: request.markup_percent ?? DEFAULT_FORM_STATE.markupPercent,
    taxRatePercent: request.tax_rate_percent ?? DEFAULT_FORM_STATE.taxRatePercent,
    urgencyCoefficient: request.urgency_coefficient ?? DEFAULT_FORM_STATE.urgencyCoefficient,
    complexityCoefficient: request.complexity_coefficient ?? DEFAULT_FORM_STATE.complexityCoefficient,
    volumeDiscountCoefficient:
      request.volume_discount_coefficient ?? DEFAULT_FORM_STATE.volumeDiscountCoefficient,
    fixedCosts: request.fixed_costs ?? DEFAULT_FORM_STATE.fixedCosts,
    bedPrepCostPerPrint: request.bed_prep_cost_per_print ?? DEFAULT_FORM_STATE.bedPrepCostPerPrint,
    minOrderPrice: request.min_order_price ?? DEFAULT_FORM_STATE.minOrderPrice,
    roundToNearest: request.round_to_nearest ?? DEFAULT_FORM_STATE.roundToNearest,
    roundingMode: request.rounding_mode ?? DEFAULT_FORM_STATE.roundingMode,
  };
};

const formatHistoryDate = (isoDate: string): string =>
  new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(new Date(isoDate));

interface QuoteLineItem {
  title: string;
  details: string[];
  quantity: number;
  unitPrice: number;
  totalPrice: number;
}

interface QuoteItem {
  id: string;
  lineItem: QuoteLineItem;
  includedItems: string[];
}

interface BuildQuoteHtmlParams {
  t: TFunction;
  items: QuoteLineItem[];
  includedItems: string[];
  grandTotal: number;
  parties: QuotePartyFormState;
  formatCurrency: (value: number | null | undefined) => string;
  quoteNumber?: string;
}

export const buildQuoteLineItems = (
  t: TFunction,
  form: CalculatorFormState,
  result: CalculatorEstimateResponse,
  parsedGcode: CalculatorGcodeParseResponse | null,
  selectedFilament: MaterialSelectionSnapshot | null,
  parsedJobs: ParsedJobState[] = [],
  materialLines: CalculatorMaterialLineState[] = [],
  jobConfigs: CalculatorJobConfig[] = [],
): QuoteLineItem[] => {
  const quantity = Math.max(1, result.quantity);
  const fallbackTitle = t('profilePage.calculator.quoteDefaultItemTitle');
  const jobs = parsedJobs.length > 0
    ? parsedJobs
    : parsedGcode
      ? [{ key: 'single-job', parsed: parsedGcode }]
      : [];

  if (jobs.length === 0) {
    const details = [
      selectedFilament ? buildFilamentLabel(selectedFilament) : null,
      form.weightG > 0
        ? `${t('profilePage.calculator.quoteWeight')}: ${form.weightG.toFixed(2)} ${t('profilePage.calculator.grams')}`
        : null,
      toHours(form.timeHours, form.timeMinutes, form.timeSec) > 0
        ? `${t('profilePage.calculator.quotePrintTime')}: ${formatHoursShort(
            toHours(form.timeHours, form.timeMinutes, form.timeSec),
            t('profilePage.calc.h'),
            t('profilePage.calc.min'),
          )}`
        : null,
    ].filter(Boolean) as string[];
    const totalPrice = result.cost_final || result.cost_total;
    return [{
      title: quoteTitleFromFileName(parsedGcode?.file_name ?? '', fallbackTitle),
      details,
      quantity,
      unitPrice: totalPrice / quantity,
      totalPrice,
    }];
  }

  const configsByJob = new Map(jobConfigs.map((config) => [config.jobKey, config]));
  const getConfig = (job: ParsedJobState): CalculatorJobConfig => configsByJob.get(job.key) ?? {
    ...createDefaultJobConfig(job),
    repeats: quantity,
  };
  const totalPrintSeconds = jobs.reduce((sum, job) => {
    const config = getConfig(job);
    return sum + config.printTimeSeconds * config.repeats;
  }, 0);
  const totalWeightG = jobs.reduce((sum, job) => {
    const config = getConfig(job);
    return sum + (job.parsed.total_filament_weight_g ?? 0) * config.repeats;
  }, 0);
  const timeDrivenCost =
    result.cost_electricity
    + result.cost_printing
    + result.cost_amortization
    + (result.cost_monitoring ?? 0);
  const weightDrivenCost = (result.cost_waste ?? 0) + (result.cost_nozzle_wear ?? 0);
  const materialCostsByJob = new Map<string, number>();
  for (const lineCost of result.material_line_costs ?? []) {
    if (!lineCost.job_key) continue;
    materialCostsByJob.set(
      lineCost.job_key,
      (materialCostsByJob.get(lineCost.job_key) ?? 0) + lineCost.cost,
    );
  }

  const drafts = jobs.flatMap((job, index) => {
    const parsed = job.parsed;
    const config = getConfig(job);
    const groups = parsed.object_groups ?? [];
    const homogeneousObjectGroup = groups.length === 1 ? groups[0] : null;
    const canSplitMixedGroups = canSplitCalculatorObjectGroups(groups);
    const splitByGroups = Boolean(
      homogeneousObjectGroup
      || (config.quoteMode === 'groups' && canSplitMixedGroups),
    );
    const materialNames = Array.from(new Set(
      parsed.materials
        .filter((material) => (material.weight_g ?? 0) > 0 || parsed.materials.length === 1)
        .map((material) => {
          const materialName = material.type || material.name || material.settings_id;
          if (!materialName) return null;
          const vendor = material.vendor && material.vendor.toLocaleLowerCase() !== 'generic'
            ? material.vendor
            : null;
          return [vendor, materialName].filter(Boolean).join(' ');
        })
        .filter((value): value is string => Boolean(value)),
    ));
    if (materialNames.length === 0) {
      materialNames.push(...Array.from(new Set(
        materialLines
          .filter((line) => line.job_key === job.key && Boolean(line.label))
          .map((line) => line.label!),
      )));
    }

    const jobWeightG = (parsed.total_filament_weight_g ?? 0) * config.repeats;
    const jobPrintSeconds = config.printTimeSeconds * config.repeats;
    const commonDetails = [
      materialNames.length > 0 ? materialNames.join(' / ') : null,
      jobWeightG > 0
        ? `${t('profilePage.calculator.quoteWeight')}: ${jobWeightG.toFixed(2)} ${t('profilePage.calculator.grams')}`
        : null,
      jobPrintSeconds > 0
        ? `${t('profilePage.calculator.quotePrintTime')}: ${formatHoursShort(
            jobPrintSeconds / 3600,
            t('profilePage.calc.h'),
            t('profilePage.calc.min'),
          )}`
        : null,
    ].filter(Boolean) as string[];
    const materialCost = materialCostsByJob.get(job.key)
      ?? (jobs.length === 1 ? result.cost_material : 0);
    const score = materialCost
      + (totalPrintSeconds > 0 ? timeDrivenCost * (jobPrintSeconds / totalPrintSeconds) : 0)
      + (totalWeightG > 0 ? weightDrivenCost * (jobWeightG / totalWeightG) : 0);
    const plateSuffix = parsed.plate_index != null
      ? ` · ${t('profilePage.calculator.parsedPlateOption', { index: parsed.plate_index })}`
      : '';
    const defaultTitle = homogeneousObjectGroup && homogeneousObjectGroup.count > 1
      ? homogeneousObjectGroup.name
      : `${quoteTitleFromFileName(parsed.file_name, `${fallbackTitle} ${index + 1}`)}${plateSuffix}`;

    if (!splitByGroups) {
      return [{
        title: defaultTitle,
        details: commonDetails,
        quantity: config.repeats,
        score,
      }];
    }

    const rawShares = groups.map((group) => (
      groups.length === 1 ? 1 : Math.max(0, group.extrusion_share ?? 0)
    ));
    const shareTotal = rawShares.reduce((sum, share) => sum + share, 0) || 1;
    return groups.map((group, groupIndex) => {
      const share = rawShares[groupIndex] / shareTotal;
      const groupWeightG = jobWeightG * share;
      const groupMaterialNames = Object.keys(group.material_weights_g ?? {})
        .map(Number)
        .map((toolIndex) => {
          const parsedMaterial = parsed.materials.find((material) => material.tool_index === toolIndex);
          if (!parsedMaterial) return null;
          const materialName = parsedMaterial.type || parsedMaterial.name || parsedMaterial.settings_id;
          if (!materialName) return null;
          const vendor = parsedMaterial.vendor && parsedMaterial.vendor.toLocaleLowerCase() !== 'generic'
            ? parsedMaterial.vendor
            : null;
          return [vendor, materialName].filter(Boolean).join(' ');
        })
        .filter((value): value is string => Boolean(value));
      const details = groups.length === 1
        ? commonDetails
        : [
            groupMaterialNames.length > 0
              ? Array.from(new Set(groupMaterialNames)).join(' / ')
              : materialNames.length > 0
                ? materialNames.join(' / ')
                : null,
            groupWeightG > 0
              ? `${t('profilePage.calculator.quoteWeight')}: ${groupWeightG.toFixed(2)} ${t('profilePage.calculator.grams')}`
              : null,
          ].filter(Boolean) as string[];
      return {
        title: group.name || defaultTitle,
        details,
        quantity: Math.max(1, group.count) * config.repeats,
        score: score * share,
      };
    });
  });

  const allocatedTotals = allocateRoundedTotal(
    result.cost_final || result.cost_total,
    drafts.map((draft) => draft.score),
  );

  return drafts.map((draft, index) => ({
    title: draft.title,
    details: draft.details,
    quantity: draft.quantity,
    unitPrice: allocatedTotals[index] / draft.quantity,
    totalPrice: allocatedTotals[index],
  }));
};

const buildQuoteIncludedItems = (t: TFunction, result: CalculatorEstimateResponse): string[] => {
  const included: string[] = [];

  if (result.cost_material > 0) {
    included.push(t('profilePage.calculator.quoteIncluded.materials'));
  }
  if (result.cost_electricity > 0 || result.cost_amortization > 0) {
    included.push(t('profilePage.calculator.quoteIncluded.equipment'));
  }
  if (result.cost_printing > 0) {
    included.push(t('profilePage.calculator.quoteIncluded.printing'));
  }
  if (result.cost_modeling > 0) {
    included.push(t('profilePage.calculator.quoteIncluded.modeling'));
  }
  if (result.cost_postprocessing > 0) {
    included.push(t('profilePage.calculator.quoteIncluded.postprocessing'));
  }

  return included.length > 0 ? included : [t('profilePage.calculator.quoteIncluded.none')];
};

const buildQuoteDisclaimerLabel = (t: TFunction, mode: QuoteDisclaimerMode): string =>
  mode === 'offer' ? t('profilePage.calculator.quoteDisclaimerOffer') : t('profilePage.calculator.quoteDisclaimerNotOffer');

const buildQuoteDocumentHtml = ({
  t,
  items,
  includedItems,
  grandTotal,
  parties,
  formatCurrency,
  quoteNumber,
}: BuildQuoteHtmlParams): string => {
  const lineItems = items;
  const issuedAt = new Date();
  const today = new Intl.DateTimeFormat('ru-RU', { dateStyle: 'long' }).format(issuedAt);
  const validityDays = Math.max(1, Math.round(parties.validityDays || DEFAULT_QUOTE_PROFILE.validityDays));
  const validUntil = new Intl.DateTimeFormat('ru-RU', { dateStyle: 'long' }).format(addDays(issuedAt, validityDays));
  const disclaimerLabel = buildQuoteDisclaimerLabel(t, parties.disclaimerMode || DEFAULT_QUOTE_PROFILE.disclaimerMode);
  const buyerFallback = t('profilePage.calculator.quoteBuyerFallback');

  const tableRows = lineItems
    .map(
      (item, index) => `
          <tr>
            <td class="p-2 border border-gray-400 text-sm text-center">${index + 1}</td>
            <td class="p-2 border border-gray-400 text-sm">
              <strong>${escapeHtml(item.title)}</strong>
              ${item.details.length > 0 ? `<div class="text-xs text-gray-500 mt-1">${escapeHtml(item.details.join(' · '))}</div>` : ''}
            </td>
            <td class="p-2 border border-gray-400 text-sm text-center">${item.quantity}</td>
            <td class="p-2 border border-gray-400 text-sm text-right">${escapeHtml(formatCurrency(item.unitPrice))}</td>
            <td class="p-2 border border-gray-400 text-sm text-right">${escapeHtml(formatCurrency(item.totalPrice))}</td>
          </tr>`,
    )
    .join('');

  const includedMarkup = includedItems.map((item) => `<li>${escapeHtml(item)}</li>`).join('');

  const buyerName = parties.buyerName.trim() || buyerFallback;
  const buyerInn = parties.buyerInn.trim();
  const buyerAddress = parties.buyerAddress.trim();
  const paymentTerms = parties.paymentTerms.trim();
  const sellerName = parties.sellerName.trim() || '—';


  return `<!doctype html>
<html lang="ru">
  <head>
    <meta charset="utf-8" />
    <title>${escapeHtml(t('profilePage.calculator.quoteDocumentTitle'))}${quoteNumber ? ` ${escapeHtml(quoteNumber)}` : ''}</title>
    <style>
      * { margin: 0; padding: 0; box-sizing: border-box; }
      body { font-family: "Segoe UI", Arial, sans-serif; color: #1f2937; background: #f3f4f6; }
      .page {
        width: 210mm; min-height: 297mm;
        margin: 0 auto; padding: 20mm;
        background: #fff;
      }
      h2 { font-size: 22px; font-weight: 700; margin-bottom: 4px; }
      .subtitle { font-size: 13px; color: #6b7280; }
      .date { font-size: 13px; margin-top: 8px; }
      .header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 28px; }
      .header-right { text-align: right; font-size: 13px; line-height: 1.7; }
      .header-right p strong { font-size: 14px; }
      .header-right .status { font-size: 11px; color: #9ca3af; margin-top: 6px; }
      .box { border: 1px solid #d1d5db; border-radius: 8px; padding: 14px 16px; background: #f9fafb; margin-bottom: 20px; }
      .box-title { font-weight: 700; margin-bottom: 8px; font-size: 14px; }
      .box-line { font-size: 13px; line-height: 1.6; color: #374151; }
      .box-muted { font-size: 12px; color: #6b7280; }
      table { width: 100%; border-collapse: collapse; margin-bottom: 24px; }
      .p-2 { padding: 8px 10px; }
      .border { border: 1px solid; }
      .border-gray-400 { border-color: #9ca3af; }
      .text-sm { font-size: 13px; }
      .text-xs { font-size: 11px; }
      .text-right { text-align: right; }
      .text-center { text-align: center; }
      .text-gray-500 { color: #6b7280; }
      .mt-1 { margin-top: 4px; }
      .bg-gray-200 { background: #e5e7eb; }
      .font-bold { font-weight: 700; }
      .included { margin-bottom: 24px; }
      .included-title { font-weight: 700; margin-bottom: 8px; font-size: 14px; }
      .included ul { padding-left: 20px; font-size: 13px; color: #4b5563; line-height: 1.8; }
      .signatures { display: flex; justify-content: space-between; margin-top: 48px; }
      .sig-block { width: 38%; }
      .sig-block p { font-size: 13px; margin-bottom: 32px; }
      .sig-line { border-bottom: 1px solid #1f2937; padding-bottom: 4px; font-size: 13px; }
      .sig-hint { font-size: 10px; color: #9ca3af; margin-top: 4px; }
      .footer-note { margin-top: 32px; text-align: center; font-size: 10px; color: #d1d5db; }
      .total-row td { font-weight: 700; font-size: 15px; background: #f9fafb; }
      @media print {
        body { background: white; }
        .page { width: 100%; min-height: auto; margin: 0; padding: 15mm; box-shadow: none; }
      }
    </style>
  </head>
  <body>
    <div class="page">
      <div class="header">
        <div>
          <h2>${escapeHtml(t('profilePage.calculator.quoteDocumentTitle'))}${quoteNumber ? ` ${escapeHtml(quoteNumber)}` : ''}</h2>
          <p class="subtitle">${escapeHtml(t('profilePage.calculator.quoteDocumentSubtitle'))}</p>
          <p class="date">${escapeHtml(today)}</p>
        </div>
        <div class="header-right">
          <p><strong>${escapeHtml(t('profilePage.calculator.quoteExecutor'))}:</strong></p>
          <p>${escapeHtml(sellerName)}</p>
          <p>${escapeHtml(t('profilePage.calculator.quoteInn'))}: ${escapeHtml(parties.sellerInn.trim() || '—')}</p>
          <p>${escapeHtml(t('profilePage.calculator.quotePhone'))}: ${escapeHtml(parties.sellerPhone.trim() || '—')}</p>
          <p class="status">${escapeHtml(t('profilePage.calculator.quoteTaxStatus'))}</p>
        </div>
      </div>

      <div class="box">
        <p class="box-title">${escapeHtml(t('profilePage.calculator.quoteCustomer'))}:</p>
        <p class="box-line">${escapeHtml(buyerName)}</p>
        ${buyerInn ? `<p class="box-muted">${escapeHtml(t('profilePage.calculator.quoteInn'))}: ${escapeHtml(buyerInn)}</p>` : ''}
        ${buyerAddress ? `<p class="box-muted">${escapeHtml(t('profilePage.calculator.quoteAddress'))}: ${escapeHtml(buyerAddress)}</p>` : ''}
      </div>

      ${paymentTerms ? `
      <div class="box">
        <p class="box-title">${escapeHtml(t('profilePage.calculator.quotePaymentTerms'))}:</p>
        <p class="box-line">${escapeHtml(paymentTerms)}</p>
      </div>` : ''}

      <div class="box" style="margin-bottom: 24px;">
        <p class="box-line">${escapeHtml(t('profilePage.calculator.quoteValidUntil'))}: <strong>${escapeHtml(validUntil)}</strong></p>
      </div>

      <table>
        <thead>
          <tr class="bg-gray-200">
            <th class="p-2 border border-gray-400 text-sm" style="width:36px;">№</th>
            <th class="p-2 border border-gray-400 text-sm">${escapeHtml(t('profilePage.calculator.quoteTable.item'))}</th>
            <th class="p-2 border border-gray-400 text-sm text-center" style="width:70px;">${escapeHtml(t('profilePage.calculator.quoteTable.quantity'))}</th>
            <th class="p-2 border border-gray-400 text-sm text-right" style="width:130px;">${escapeHtml(t('profilePage.calculator.quoteTable.unitPrice'))}</th>
            <th class="p-2 border border-gray-400 text-sm text-right" style="width:130px;">${escapeHtml(t('profilePage.calculator.quoteTable.total'))}</th>
          </tr>
        </thead>
        <tbody>
          ${tableRows}
        </tbody>
        <tfoot>
          <tr class="total-row">
            <td colspan="4" class="p-2 border border-gray-400 text-sm text-right">${escapeHtml(t('profilePage.calculator.totalCost'))}:</td>
            <td class="p-2 border border-gray-400 text-sm text-right">${escapeHtml(formatCurrency(grandTotal))}</td>
          </tr>
        </tfoot>
      </table>


      <div class="included">
        <p class="included-title">${escapeHtml(t('profilePage.calculator.quoteIncludedTitle'))}:</p>
        <ul>${includedMarkup}</ul>
      </div>

      <div class="box" style="background: transparent; border-color: #e5e7eb;">
        <p class="box-muted">${escapeHtml(t('profilePage.calculator.quoteLegalStatus'))}: ${escapeHtml(disclaimerLabel)}</p>
      </div>

      <div class="signatures">
        <div class="sig-block">
          <p>${escapeHtml(t('profilePage.calculator.quoteExecutor'))}:</p>
          <p class="sig-line">${escapeHtml(sellerName)}</p>
          <p class="sig-hint">(${escapeHtml(t('profilePage.calculator.quoteSignatureHint'))})</p>
        </div>
        <div class="sig-block" style="text-align: right;">
          <p>${escapeHtml(t('profilePage.calculator.quoteCustomer'))}:</p>
          <p class="sig-line"></p>
          <p class="sig-hint">(${escapeHtml(t('profilePage.calculator.quoteSignatureHint'))})</p>
        </div>
      </div>

      <p class="footer-note">${escapeHtml(t('profilePage.calculator.quoteFooterNote'))}</p>
    </div>
  </body>
</html>`;
};

export const CalculatorPage: React.FC = () => {
  const { t, i18n } = useTranslation();
  const { user, refreshUser } = useAuth();
  const queryClient = useQueryClient();
  const tc = (key: string) => translateCalculator(t, key);
  const hasCalculatorAccess = user?.has_calculator_access ?? false;
  const canStartTrial = !hasCalculatorAccess && user?.subscription == null;
  const [activeTab, setActiveTab] = useState<CalculatorTab>('calculator');
  const [form, setForm] = useState<CalculatorFormState>(DEFAULT_FORM_STATE);
  const [parsedGcode, setParsedGcode] = useState<CalculatorGcodeParseResponse | null>(null);
  const [parsedJobs, setParsedJobs] = useState<ParsedJobState[]>([]);
  const [jobConfigs, setJobConfigs] = useState<CalculatorJobConfig[]>([]);
  const [materialLines, setMaterialLines] = useState<CalculatorMaterialLineState[]>([]);
  const [batchParseWarning, setBatchParseWarning] = useState<string | null>(null);
  const [materialLinesError, setMaterialLinesError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [historyFeedback, setHistoryFeedback] = useState<{ kind: 'success' | 'error'; message: string } | null>(null);
  const [deletingHistoryEntry, setDeletingHistoryEntry] = useState<CalculatorHistoryEntry | null>(null);
  const [quoteModalOpen, setQuoteModalOpen] = useState(false);
  const [quoteProfile, setQuoteProfile] = useState<QuoteProfileState>(DEFAULT_QUOTE_PROFILE);
  const [quoteParties, setQuoteParties] = useState<QuotePartyFormState>(DEFAULT_QUOTE_PARTY_FORM);
  const [selectedSpoolId, setSelectedSpoolId] = useState<number | ''>('');
  const [autoMaterialMatch, setAutoMaterialMatch] = useState<AutoMaterialMatchNotice | null>(null);
  const [materialPriceSource, setMaterialPriceSource] = useState<MaterialPriceSource>('manual');
  const [isCloudBusy, setIsCloudBusy] = useState(false);
  const [quoteItems, setQuoteItems] = useState<QuoteItem[]>([]);
  const [isSharing, setIsSharing] = useState(false);
  const [isPdfDownloading, setIsPdfDownloading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const skipNextFilamentDefaultsRef = useRef(false);
  const priceManuallyEditedRef = useRef(false);
  const lastAutoMatchedGcodeKeyRef = useRef<string | null>(null);
  const lastBuiltMaterialJobsKeyRef = useRef<string | null>(null);
  const quoteSequenceRef = useRef(0);

  const formatCurrency = useMemo(
    () => makeCurrencyFormatter(quoteProfile.currency || 'RUB'),
    [quoteProfile.currency],
  );

  // Всегда актуальная валюта калькулятора — чтобы эффект автоподстановки не тянул
  // её в зависимости (иначе смена валюты затирала бы введённую цену).
  const calcCurrencyRef = useRef(quoteProfile.currency);
  calcCurrencyRef.current = quoteProfile.currency;

  const filamentsQuery = useQuery({
    queryKey: ['calculator-pro', 'filaments'],
    queryFn: () =>
      filamentsAPI.list({
        active_only: true,
        size: 100,
      }),
    staleTime: 60_000,
    enabled: hasCalculatorAccess,
  });

  const spoolsQuery = useQuery({
    queryKey: ['calculator-pro', 'spools'],
    queryFn: spoolsAPI.list,
    staleTime: 30_000,
    enabled: hasCalculatorAccess,
  });

  const startTrialMutation = useMutation({
    mutationFn: calculatorAPI.startTrial,
    onSuccess: async () => {
      await refreshUser();
    },
  });

  const calculateMutation = useMutation({
    mutationFn: (data: CalculatorEstimateRequest) => calculatorAPI.estimate(data),
  });

  const parseGcodeMutation = useMutation({
    mutationFn: async (files: File[]) => {
      const limitedFiles = files.slice(0, 20);
      const settled = await Promise.allSettled(
        limitedFiles.map(async (file, uploadIndex) => {
          const first = await calculatorAPI.parseGcode(file);
          const plateIndices = first.available_plate_indices ?? [];
          const remainingPlateIndices = plateIndices.filter(
            (plateIndex) => plateIndex !== first.plate_index,
          );
          const remaining = await Promise.all(
            remainingPlateIndices.map((plateIndex) => calculatorAPI.parseGcode(file, plateIndex)),
          );
          return [first, ...remaining]
            .sort((left, right) => (left.plate_index ?? 0) - (right.plate_index ?? 0))
            .map((parsed) => ({ key: parsedJobKey(parsed, uploadIndex), parsed }));
        }),
      );
      const jobs = settled.flatMap((result) => (result.status === 'fulfilled' ? result.value : []));
      const failedFiles = settled.flatMap((result, index) =>
        result.status === 'rejected' ? [limitedFiles[index]?.name ?? `#${index + 1}`] : [],
      );
      if (jobs.length === 0) {
        throw new Error('all_gcode_files_failed');
      }
      return {
        jobs,
        failedFiles,
        skippedCount: Math.max(0, files.length - limitedFiles.length),
      };
    },
  });

  const historyQuery = useQuery({
    queryKey: ['calculator-pro', 'history'],
    queryFn: () => calculatorAPI.listHistory({ page: 1, size: 50 }),
    staleTime: 30_000,
    enabled: hasCalculatorAccess,
  });

  const saveHistoryMutation = useMutation({
    mutationFn: (payload: CalculatorHistoryEntryCreate) => calculatorAPI.saveHistory(payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['calculator-pro', 'history'] });
    },
  });

  const deleteHistoryMutation = useMutation({
    mutationFn: (entryId: number) => calculatorAPI.deleteHistory(entryId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['calculator-pro', 'history'] });
    },
  });

  const result = calculateMutation.data ?? null;
  const estimateSource: 'manual' | 'gcode' = parsedGcode ? 'gcode' : 'manual';
  const availableSpools = useMemo(
    () =>
      (spoolsQuery.data ?? []).filter(
        (spool) => spool.filament && spool.state !== 'archived' && spool.state !== 'empty',
      ),
    [spoolsQuery.data],
  );
  const selectedSpool = useMemo(
    () => availableSpools.find((spool) => spool.id === selectedSpoolId) ?? null,
    [availableSpools, selectedSpoolId],
  );
  const selectedCatalogFilament = useMemo(
    () => filamentsQuery.data?.items.find((filament) => filament.id === form.selectedFilamentId) ?? null,
    [filamentsQuery.data?.items, form.selectedFilamentId],
  );
  const selectedMaterial = useMemo<MaterialSelectionSnapshot | null>(() => {
    if (selectedSpool?.filament) {
      return {
        id: selectedSpool.filament_id,
        name: selectedSpool.filament.name,
        brand_name: selectedSpool.filament.brand_name,
        material_type: selectedSpool.filament.material_type,
        color_name: selectedSpool.filament.color_name,
      };
    }

    if (selectedCatalogFilament) {
      return {
        id: selectedCatalogFilament.id,
        name: selectedCatalogFilament.name,
        brand_name: selectedCatalogFilament.brand_name,
        material_type: selectedCatalogFilament.material_type,
        color_name: selectedCatalogFilament.color_name,
      };
    }

    return null;
  }, [selectedSpool, selectedCatalogFilament]);

  useEffect(() => {
    setForm((prev) => ({
      ...prev,
      ...loadStoredCalculatorDefaults(),
    }));
  }, []);

  useEffect(() => {
    if (selectedSpool) {
      if (skipNextFilamentDefaultsRef.current) {
        skipNextFilamentDefaultsRef.current = false;
        return;
      }
      if (priceManuallyEditedRef.current) {
        return;
      }

      const defaults = deriveUserSpoolDefaults(selectedSpool);
      // Если у катушки нет своей цены, deriveUserSpoolDefaults берёт цену бренда
      // (в валюте бренда). Не подставляем её, если она не совпадает с валютой
      // калькулятора — пользователь укажет свою (как и для каталога).
      const usesBrandFallback =
        selectedSpool.price == null && selectedSpool.filament?.price_per_kg != null;
      const spoolBrandCurrency = selectedSpool.filament?.currency
        ? normalizeCurrency(selectedSpool.filament.currency)
        : null;
      const fallbackCurrencyOk =
        !usesBrandFallback || !spoolBrandCurrency || spoolBrandCurrency === calcCurrencyRef.current;

      setForm((prev) => ({
        ...prev,
        spoolPrice: fallbackCurrencyOk ? (defaults.spoolPrice ?? prev.spoolPrice) : prev.spoolPrice,
        spoolWeightKg: defaults.spoolWeightKg ?? prev.spoolWeightKg,
      }));
      if (fallbackCurrencyOk && defaults.spoolPrice != null) {
        setMaterialPriceSource(selectedSpool.price != null ? 'spool' : 'filamenthub');
      } else {
        setMaterialPriceSource('unset');
      }
      return;
    }

    if (!selectedCatalogFilament) {
      return;
    }

    if (skipNextFilamentDefaultsRef.current) {
      skipNextFilamentDefaultsRef.current = false;
      return;
    }
    if (priceManuallyEditedRef.current) {
      return;
    }

    const defaults = deriveCatalogFilamentDefaults(selectedCatalogFilament);
    const brandCurrency = selectedCatalogFilament.currency
      ? normalizeCurrency(selectedCatalogFilament.currency)
      : null;
    const currencyMatches = !brandCurrency || brandCurrency === calcCurrencyRef.current;

    setForm((prev) => ({
      ...prev,
      // Каталожная цена — в валюте бренда. Подставляем её только если валюта совпадает
      // с валютой калькулятора, иначе оставляем пользователю ввести свою (без смешивания валют).
      spoolPrice: currencyMatches ? (defaults.spoolPrice ?? prev.spoolPrice) : prev.spoolPrice,
      spoolWeightKg: defaults.spoolWeightKg ?? prev.spoolWeightKg,
    }));
    setMaterialPriceSource(currencyMatches && defaults.spoolPrice != null ? 'filamenthub' : 'unset');
  }, [selectedCatalogFilament, selectedSpool]);

  useEffect(() => {
    const stored = loadStoredQuoteProfile();
    const nextProfile: QuoteProfileState = {
      ...DEFAULT_QUOTE_PROFILE,
      ...stored,
      // Пока пользователь не выбрал валюту — дефолт по языку UI.
      currency: normalizeCurrency(stored.currency || defaultCurrencyForLanguage(i18n.language)),
      sellerName:
        typeof stored.sellerName === 'string' && stored.sellerName.trim()
          ? stored.sellerName
          : user?.full_name?.trim() || user?.username || DEFAULT_QUOTE_PROFILE.sellerName,
    };
    setQuoteProfile(nextProfile);
    setQuoteParties((prev) => ({
      ...prev,
      ...nextProfile,
    }));
  }, [user?.full_name, user?.username]);

  useEffect(() => {
    saveStoredQuoteProfile(quoteProfile);
  }, [quoteProfile]);

  const estimateError = useMemo(() => {
    if (!calculateMutation.error) {
      return null;
    }

    const errorWithResponse = calculateMutation.error as {
      response?: { data?: { detail?: unknown } };
      message?: string;
    };

    return translateApiError(
      t,
      errorWithResponse.response?.data?.detail ?? errorWithResponse.message,
      t('profilePage.calc.unknownError'),
    );
  }, [calculateMutation.error, t]);

  const parseGcodeError = useMemo(() => {
    if (!parseGcodeMutation.error) {
      return null;
    }

    const errorWithResponse = parseGcodeMutation.error as {
      response?: { data?: { detail?: unknown } };
      message?: string;
    };

    return translateApiError(
      t,
      errorWithResponse.response?.data?.detail ?? errorWithResponse.message,
      t('profilePage.calc.unknownError'),
    );
  }, [parseGcodeMutation.error, t]);

  const historyLoadError = useMemo(() => {
    if (!historyQuery.error) {
      return null;
    }

    const errorWithResponse = historyQuery.error as {
      response?: { data?: { detail?: unknown } };
      message?: string;
    };

    return translateApiError(
      t,
      errorWithResponse.response?.data?.detail ?? errorWithResponse.message,
      tc('historyLoadError'),
    );
  }, [historyQuery.error, t]);

  const currentWorkTimeHours = useMemo(
    () => toHours(form.timeHours, form.timeMinutes, form.timeSec),
    [form.timeHours, form.timeMinutes, form.timeSec],
  );
  const headerJobs = parsedJobs.length > 0
    ? parsedJobs
    : parsedGcode
      ? [{ key: 'single-job', parsed: parsedGcode }]
      : [];
  const headerConfigsByJob = new Map(jobConfigs.map((config) => [config.jobKey, config]));
  const headerBatchSummary = buildConfiguredCalculatorBatchSummary(
    headerJobs.map((job) => {
      const config = headerConfigsByJob.get(job.key) ?? {
        ...createDefaultJobConfig(job),
        repeats: form.quantity,
      };
      const groups = job.parsed.object_groups ?? [];
      const quoteMode = config.quoteMode === 'groups'
        && groups.length > 1
        && !canSplitCalculatorObjectGroups(groups)
        ? 'set'
        : config.quoteMode;
      return {
        repeats: config.repeats,
        outputQuantityPerRun: calculatorOutputQuantityPerRun(groups, quoteMode),
        objectCount: job.parsed.object_count,
        printTimeSeconds: config.printTimeSeconds,
        weightG: job.parsed.total_filament_weight_g,
      };
    }),
  );

  const summaryTotal = result ? result.cost_final || result.cost_total : null;
  const summaryTime = result?.total_time_hours
    ?? result?.time_hours
    ?? (headerBatchSummary.jobCount > 0
      ? headerBatchSummary.partyPrintTimeSeconds / 3600
      : currentWorkTimeHours * Math.max(1, form.quantity));
  const summaryQuantity = headerBatchSummary.jobCount > 0
    ? headerBatchSummary.quoteQuantity
    : form.quantity;

  const updateField = <K extends keyof CalculatorFormState>(field: K, value: CalculatorFormState[K]) => {
    if (field === 'spoolPrice') {
      priceManuallyEditedRef.current = true;
      setMaterialPriceSource('manual');
    }
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSelectSpool = (spoolId: number | '') => {
    setAutoMaterialMatch(null);
    skipNextFilamentDefaultsRef.current = false;
    priceManuallyEditedRef.current = false;
    setSelectedSpoolId(spoolId);

    if (!spoolId) {
      return;
    }

    const matchedSpool = availableSpools.find((spool) => spool.id === spoolId);
    setForm((prev) => ({
      ...prev,
      selectedFilamentId: matchedSpool?.filament_id ?? prev.selectedFilamentId,
    }));
  };

  const handleSelectCatalogFilament = (filamentId: number | '') => {
    setAutoMaterialMatch(null);
    skipNextFilamentDefaultsRef.current = false;
    priceManuallyEditedRef.current = false;
    setSelectedSpoolId('');
    setForm((prev) => ({
      ...prev,
      selectedFilamentId: filamentId,
    }));
  };

  const handleMaterialLineSelection = (lineId: string, selectionValue: string) => {
    setMaterialLinesError(null);
    setMaterialLines((currentLines) =>
      currentLines.map((line) => {
        if (line.line_id !== lineId) return line;
        if (selectionValue.startsWith('spool:')) {
          const spoolId = Number(selectionValue.slice('spool:'.length));
          const spool = availableSpools.find((item) => item.id === spoolId);
          if (!spool) return line;
          const defaults = deriveUserSpoolDefaults(spool);
          const brandCurrency = spool.filament?.currency
            ? normalizeCurrency(spool.filament.currency)
            : null;
          const currencyMatches =
            spool.price != null || !brandCurrency || brandCurrency === calcCurrencyRef.current;
          return {
            ...line,
            selectionValue,
            spool_id: spool.id,
            filament_id: spool.filament_id,
            spool_price: currencyMatches ? (defaults.spoolPrice ?? 0) : 0,
            spool_weight_kg: defaults.spoolWeightKg ?? 1,
            price_source: spool.price != null ? 'spool' : 'filamenthub',
            requiresSpoolChoice: false,
            priceResolved: currencyMatches && defaults.spoolPrice != null,
          };
        }
        if (selectionValue.startsWith('filament:')) {
          const filamentId = Number(selectionValue.slice('filament:'.length));
          const filament = filamentsQuery.data?.items.find((item) => item.id === filamentId);
          if (!filament) return line;
          const defaults = deriveCatalogFilamentDefaults(filament);
          const brandCurrency = filament.currency ? normalizeCurrency(filament.currency) : null;
          const currencyMatches = !brandCurrency || brandCurrency === calcCurrencyRef.current;
          return {
            ...line,
            selectionValue,
            spool_id: null,
            filament_id: filament.id,
            spool_price: currencyMatches ? (defaults.spoolPrice ?? 0) : 0,
            spool_weight_kg: defaults.spoolWeightKg ?? 1,
            price_source: 'filamenthub',
            requiresSpoolChoice: false,
            priceResolved: currencyMatches && defaults.spoolPrice != null,
          };
        }
        return {
          ...line,
          selectionValue: selectionValue || 'manual',
          spool_id: null,
          filament_id: null,
          price_source: 'manual',
          requiresSpoolChoice: false,
          priceResolved: selectionValue === 'manual' && line.priceResolved,
        };
      }),
    );
  };

  const handleMaterialLinePriceChange = (lineId: string, value: number) => {
    setMaterialLinesError(null);
    setMaterialLines((currentLines) =>
      currentLines.map((line) =>
        line.line_id === lineId
          ? {
              ...line,
              spool_price: value,
              price_source: 'manual',
              priceResolved: Number.isFinite(value) && value >= 0,
            }
          : line,
      ),
    );
  };

  const handleMaterialLineSpoolWeightChange = (lineId: string, value: number) => {
    setMaterialLinesError(null);
    setMaterialLines((currentLines) =>
      currentLines.map((line) =>
        line.line_id === lineId
          ? { ...line, spool_weight_kg: value, priceResolved: line.priceResolved && value > 0 }
          : line,
      ),
    );
  };

  const updateStaticField = <K extends CalculatorStaticSettingKey>(field: K, value: CalculatorFormState[K]) => {
    setForm((prev) => {
      const next = { ...prev, [field]: value };
      saveStoredCalculatorDefaults(extractStaticSettings(next));
      return next;
    });
  };

  const updateQuoteProfileField = <K extends keyof QuoteProfileState>(field: K, value: QuoteProfileState[K]) => {
    setQuoteProfile((prev) => {
      const next = { ...prev, [field]: value };
      return next;
    });
    setQuoteParties((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleCalculate = () => {
    if (materialLines.some((line) => !line.priceResolved || line.spool_weight_kg <= 0)) {
      setMaterialLinesError(tc('materialLinesIncomplete'));
      return;
    }
    setMaterialLinesError(null);
    calculateMutation.mutate(buildEstimateRequest(form, materialLines, parsedJobs, jobConfigs));
  };

  const handleGcodeFiles = async (files: File[]) => {
    const batch = await parseGcodeMutation.mutateAsync(files);
    const firstJob = batch.jobs[0];
    priceManuallyEditedRef.current = false;
    lastAutoMatchedGcodeKeyRef.current = null;
    lastBuiltMaterialJobsKeyRef.current = null;
    setSelectedSpoolId('');
    setAutoMaterialMatch(null);
    setMaterialPriceSource('unset');
    setMaterialLinesError(null);
    setParsedJobs(batch.jobs);
    setJobConfigs(batch.jobs.map(createDefaultJobConfig));
    setParsedGcode(firstJob?.parsed ?? null);
    setBatchParseWarning(
      batch.failedFiles.length > 0 || batch.skippedCount > 0
        ? tc('batchParsePartial')
            .replace('{{failed}}', String(batch.failedFiles.length))
            .replace('{{skipped}}', String(batch.skippedCount))
        : null,
    );
    setForm((prev) => ({
      ...applyParsedJobsToForm(prev, batch.jobs),
      selectedFilamentId: '',
      spoolPrice: 0,
    }));
  };

  const handleJobSelect = (jobKey: string) => {
    const job = parsedJobs.find((candidate) => candidate.key === jobKey);
    if (job) setParsedGcode(job.parsed);
  };

  const handleJobConfigChange = (
    jobKey: string,
    patch: Partial<Omit<CalculatorJobConfig, 'jobKey'>>,
  ) => {
    setJobConfigs((current) => current.map((config) => (
      config.jobKey === jobKey
        ? {
            ...config,
            ...patch,
            repeats: Math.max(1, Math.floor(patch.repeats ?? config.repeats)),
            printTimeSeconds: Math.max(0, patch.printTimeSeconds ?? config.printTimeSeconds),
          }
        : config
    )));
  };

  const handleFileSelection = async (files: FileList | null) => {
    const selectedFiles = Array.from(files ?? []);
    if (selectedFiles.length === 0) {
      return;
    }

    await handleGcodeFiles(selectedFiles);
  };

  const handleSaveToHistory = async () => {
    if (!result) {
      return;
    }

    setHistoryFeedback(null);

    try {
      await saveHistoryMutation.mutateAsync(
        buildHistoryPayload(
          form,
          result,
          parsedGcode,
          selectedMaterial,
          materialLines,
          parsedJobs,
          jobConfigs,
        ),
      );
      setHistoryFeedback({ kind: 'success', message: tc('historySaved') });
      setActiveTab('history');
    } catch (error) {
      const errorWithResponse = error as {
        response?: { data?: { detail?: unknown } };
        message?: string;
      };
      setHistoryFeedback({
        kind: 'error',
        message: translateApiError(
          t,
          errorWithResponse.response?.data?.detail ?? errorWithResponse.message,
          tc('historySaveError'),
        ),
      });
    }
  };

  const handleRestoreHistory = (entry: CalculatorHistoryEntry) => {
    const restoredJobs: ParsedJobState[] = entry.parsed_jobs?.length
      ? entry.parsed_jobs.map((job) => ({ key: job.job_key, parsed: job.parsed_gcode }))
      : entry.parsed_gcode
        ? [{ key: parsedJobKey(entry.parsed_gcode, 0), parsed: entry.parsed_gcode }]
        : [];
    const restoredJobsByKey = new Map(restoredJobs.map((job) => [job.key, job.parsed]));
    skipNextFilamentDefaultsRef.current = true;
    setSelectedSpoolId('');
    lastAutoMatchedGcodeKeyRef.current = entry.parsed_gcode
      ? `${entry.parsed_gcode.file_name}:${entry.parsed_gcode.file_size_bytes}:${entry.parsed_gcode.plate_index ?? 0}`
      : null;
    setForm(buildFormFromHistoryEntry(entry));
    priceManuallyEditedRef.current = true;
    setMaterialPriceSource('manual');
    lastBuiltMaterialJobsKeyRef.current = restoredJobs.map((job) => job.key).join('|') || null;
    setParsedGcode(restoredJobs[0]?.parsed ?? entry.parsed_gcode ?? null);
    setParsedJobs(restoredJobs);
    const restoredPrintJobs = new Map(
      (entry.request_data.print_jobs ?? []).map((job) => [job.job_key, job]),
    );
    const legacyRepeats = Math.max(1, Math.floor(entry.request_data.quantity ?? 1));
    setJobConfigs(restoredJobs.map((job) => {
      const saved = restoredPrintJobs.get(job.key);
      return saved
        ? {
            jobKey: job.key,
            repeats: saved.repeats,
            quoteMode: saved.quote_mode ?? createDefaultJobConfig(job).quoteMode,
            printTimeSeconds: saved.print_time_seconds,
          }
        : {
            ...createDefaultJobConfig(job),
            repeats: legacyRepeats,
          };
    }));
    setMaterialLines(
      (entry.request_data.material_lines ?? []).map((line) => ({
        ...line,
        selectionValue: line.spool_id
          ? `spool:${line.spool_id}`
          : line.filament_id
            ? `filament:${line.filament_id}`
            : 'manual',
        fileName: (line.job_key ? restoredJobsByKey.get(line.job_key)?.file_name : null)
          ?? entry.parsed_gcode?.file_name
          ?? line.job_key
          ?? tc('manualMaterialLine'),
        plateIndex: (line.job_key ? restoredJobsByKey.get(line.job_key)?.plate_index : null)
          ?? entry.parsed_gcode?.plate_index
          ?? null,
        confidence: null,
        requiresSpoolChoice: false,
        priceResolved: true,
      })),
    );
    setActiveTab('calculator');
    setHistoryFeedback({ kind: 'success', message: tc('historyRestored') });
  };

  const handleDeleteHistory = (entry: CalculatorHistoryEntry) => {
    setDeletingHistoryEntry(entry);
  };

  const performDeleteHistory = async (entry: CalculatorHistoryEntry) => {
    setDeletingHistoryEntry(null);
    setHistoryFeedback(null);

    try {
      await deleteHistoryMutation.mutateAsync(entry.id);
      setHistoryFeedback({ kind: 'success', message: tc('historyDeleted') });
    } catch (error) {
      const errorWithResponse = error as {
        response?: { data?: { detail?: unknown } };
        message?: string;
      };
      setHistoryFeedback({
        kind: 'error',
        message: translateApiError(
          t,
          errorWithResponse.response?.data?.detail ?? errorWithResponse.message,
          tc('historyDeleteError'),
        ),
      });
    }
  };

  const handlePrintQuote = () => {
    if (!result && quoteItems.length === 0) return;

    const quoteWindow = window.open('', '_blank');
    if (!quoteWindow) {
      setHistoryFeedback({ kind: 'error', message: tc('quotePopupBlocked') });
      return;
    }

    quoteSequenceRef.current += 1;
    const prefix = quoteProfile.quoteNumberPrefix || 'КП';
    const seq = quoteSequenceRef.current;
    const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '');
    const quoteNumber = `${prefix}-${dateStr}-${String(seq).padStart(2, '0')}`;

    const quoteHtml = buildQuoteDocumentHtml(buildQuoteHtmlParams(quoteNumber));

    quoteWindow.document.open();
    quoteWindow.document.write(quoteHtml);
    quoteWindow.document.close();
    quoteWindow.focus();
    setTimeout(() => {
      quoteWindow.print();
    }, 250);
  };

  const handleShareQuote = async () => {
    if ((!result && quoteItems.length === 0) || !user) return;
    setIsSharing(true);
    try {
      quoteSequenceRef.current += 1;
      const prefix = quoteProfile.quoteNumberPrefix || 'КП';
      const seq = quoteSequenceRef.current;
      const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '');
      const quoteNumber = `${prefix}-${dateStr}-${String(seq).padStart(2, '0')}`;

      const quoteHtml = buildQuoteDocumentHtml(buildQuoteHtmlParams(quoteNumber));

      const resp = await calculatorAPI.shareQuote({
        title: quoteNumber,
        html_content: quoteHtml,
      });

      await navigator.clipboard.writeText(resp.share_url);
      setHistoryFeedback({ kind: 'success', message: tc('quoteShareCopied') });
    } catch (err) {
      const errorWithResponse = err as { response?: { data?: { detail?: unknown } }; message?: string };
      setHistoryFeedback({
        kind: 'error',
        message: translateApiError(
          t,
          errorWithResponse.response?.data?.detail ?? errorWithResponse.message,
          tc('quoteShareError'),
        ),
      });
    } finally {
      setIsSharing(false);
    }
  };

  const handleDownloadPdf = async () => {
    if ((!result && quoteItems.length === 0) || !user) return;
    setIsPdfDownloading(true);
    try {
      quoteSequenceRef.current += 1;
      const prefix = quoteProfile.quoteNumberPrefix || 'КП';
      const seq = quoteSequenceRef.current;
      const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '');
      const quoteNumber = `${prefix}-${dateStr}-${String(seq).padStart(2, '0')}`;

      const quoteHtml = buildQuoteDocumentHtml(buildQuoteHtmlParams(quoteNumber));

      await calculatorAPI.downloadQuotePdf({
        title: quoteNumber,
        html_content: quoteHtml,
      });
      setHistoryFeedback({ kind: 'success', message: tc('quotePdfDownloaded') });
    } catch (err) {
      const errorWithResponse = err as { response?: { data?: { detail?: unknown } }; message?: string };
      setHistoryFeedback({
        kind: 'error',
        message: translateApiError(
          t,
          errorWithResponse.response?.data?.detail ?? errorWithResponse.message,
          tc('quotePdfError'),
        ),
      });
    } finally {
      setIsPdfDownloading(false);
    }
  };

  const handleAddToQuote = () => {
    if (!result) return;
    const lineItems = buildQuoteLineItems(
      t,
      form,
      result,
      parsedGcode,
      selectedMaterial,
      parsedJobs,
      materialLines,
      jobConfigs,
    );
    const included = buildQuoteIncludedItems(t, result);
    const newItems = lineItems.map((lineItem) => ({
      id: crypto.randomUUID(),
      lineItem,
      includedItems: included,
    }));
    setQuoteItems((prev) => [...prev, ...newItems]);
    setHistoryFeedback({ kind: 'success', message: tc('addedToQuote') });
  };

  const handleRemoveFromQuote = (id: string) => {
    setQuoteItems((prev) => prev.filter((item) => item.id !== id));
  };

  const handleRenameQuoteItem = (id: string, title: string) => {
    setQuoteItems((prev) => prev.map((item) => (
      item.id === id
        ? { ...item, lineItem: { ...item.lineItem, title } }
        : item
    )));
  };

  const buildQuoteHtmlParams = (quoteNumber: string): BuildQuoteHtmlParams => {
    let items: QuoteLineItem[];
    let includedItems: string[];
    let grandTotal: number;

    if (quoteItems.length > 0) {
      items = quoteItems.map((qi) => qi.lineItem);
      includedItems = [...new Set(quoteItems.flatMap((qi) => qi.includedItems))];
      grandTotal = items.reduce((sum, item) => sum + item.totalPrice, 0);
    } else if (result) {
      items = buildQuoteLineItems(
        t,
        form,
        result,
        parsedGcode,
        selectedMaterial,
        parsedJobs,
        materialLines,
        jobConfigs,
      );
      includedItems = buildQuoteIncludedItems(t, result);
      grandTotal = result.cost_final || result.cost_total;
    } else {
      items = [];
      includedItems = [];
      grandTotal = 0;
    }

    return { t, items, includedItems, grandTotal, parties: quoteParties, formatCurrency, quoteNumber };
  };

  const handleOpenQuote = () => {
    setQuoteParties((prev) => ({
      ...prev,
      ...quoteProfile,
    }));
    if (quoteItems.length === 0 && result) {
      const included = buildQuoteIncludedItems(t, result);
      setQuoteItems(buildQuoteLineItems(
        t,
        form,
        result,
        parsedGcode,
        selectedMaterial,
        parsedJobs,
        materialLines,
        jobConfigs,
      ).map((lineItem) => ({
        id: crypto.randomUUID(),
        lineItem,
        includedItems: included,
      })));
    }
    setQuoteModalOpen(true);
  };

  const handleCloudSave = async () => {
    setIsCloudBusy(true);
    try {
      const staticSettings = extractStaticSettings(form);
      await calculatorAPI.updateProfile({
        electricity_cost_per_kwh: staticSettings.electricityCostPerKwh,
        printer_power_w: staticSettings.printerPowerW,
        modeling_rate_per_hour: staticSettings.modelingRatePerHour,
        postprocessing_rate_per_hour: staticSettings.postprocessingRatePerHour,
        printing_rate_per_hour: staticSettings.printingRatePerHour,
        amortization_rate_per_hour: staticSettings.amortizationRatePerHour,
        overhead_percent: staticSettings.overheadPercent,
        markup_percent: staticSettings.markupPercent,
        tax_rate_percent: staticSettings.taxRatePercent,
        fixed_costs: staticSettings.fixedCosts,
        bed_prep_cost_per_print: staticSettings.bedPrepCostPerPrint,
        min_order_price: staticSettings.minOrderPrice,
        round_to_nearest: staticSettings.roundToNearest,
        rounding_mode: staticSettings.roundingMode,
        seller_name: quoteProfile.sellerName,
        seller_inn: quoteProfile.sellerInn,
        seller_phone: quoteProfile.sellerPhone,
        payment_terms: quoteProfile.paymentTerms,
        validity_days: quoteProfile.validityDays,
        disclaimer_mode: quoteProfile.disclaimerMode,
        currency: quoteProfile.currency,
        quote_number_prefix: quoteProfile.quoteNumberPrefix,
      });
      setHistoryFeedback({ kind: 'success', message: tc('cloudSaveSuccess') });
    } catch {
      setHistoryFeedback({ kind: 'error', message: tc('cloudSaveError') });
    } finally {
      setIsCloudBusy(false);
    }
  };

  const handleCloudLoad = async () => {
    setIsCloudBusy(true);
    try {
      const profile = await calculatorAPI.getProfile();
      setForm((prev) => ({
        ...prev,
        electricityCostPerKwh: profile.electricity_cost_per_kwh,
        printerPowerW: profile.printer_power_w,
        modelingRatePerHour: profile.modeling_rate_per_hour,
        postprocessingRatePerHour: profile.postprocessing_rate_per_hour,
        printingRatePerHour: profile.printing_rate_per_hour,
        amortizationRatePerHour: profile.amortization_rate_per_hour,
        overheadPercent: profile.overhead_percent,
        markupPercent: profile.markup_percent,
        taxRatePercent: profile.tax_rate_percent,
        fixedCosts: profile.fixed_costs,
        bedPrepCostPerPrint: profile.bed_prep_cost_per_print,
        minOrderPrice: profile.min_order_price,
        roundToNearest: profile.round_to_nearest,
        roundingMode: profile.rounding_mode as RoundingMode,
      }));
      setQuoteProfile((prev) => ({
        ...prev,
        sellerName: profile.seller_name,
        sellerInn: profile.seller_inn,
        sellerPhone: profile.seller_phone,
        paymentTerms: profile.payment_terms,
        validityDays: profile.validity_days,
        disclaimerMode: profile.disclaimer_mode as QuoteDisclaimerMode,
        currency: normalizeCurrency(profile.currency),
        quoteNumberPrefix: profile.quote_number_prefix,
      }));
      saveStoredCalculatorDefaults({
        electricityCostPerKwh: profile.electricity_cost_per_kwh,
        printerPowerW: profile.printer_power_w,
        powerHotendW: form.powerHotendW,
        powerBedW: form.powerBedW,
        powerSteppersW: form.powerSteppersW,
        powerElectronicsW: form.powerElectronicsW,
        modelingRatePerHour: profile.modeling_rate_per_hour,
        postprocessingRatePerHour: profile.postprocessing_rate_per_hour,
        printingRatePerHour: profile.printing_rate_per_hour,
        amortizationRatePerHour: profile.amortization_rate_per_hour,
        printerPurchasePrice: form.printerPurchasePrice,
        printerUsefulHours: form.printerUsefulHours,
        overheadPercent: profile.overhead_percent,
        markupPercent: profile.markup_percent,
        taxRatePercent: profile.tax_rate_percent,
        fixedCosts: profile.fixed_costs,
        bedPrepCostPerPrint: profile.bed_prep_cost_per_print,
        minOrderPrice: profile.min_order_price,
        roundToNearest: profile.round_to_nearest,
        roundingMode: profile.rounding_mode as RoundingMode,
      });
      saveStoredQuoteProfile({
        sellerName: profile.seller_name,
        sellerInn: profile.seller_inn,
        sellerPhone: profile.seller_phone,
        paymentTerms: profile.payment_terms,
        validityDays: profile.validity_days,
        disclaimerMode: profile.disclaimer_mode as QuoteDisclaimerMode,
        currency: normalizeCurrency(profile.currency),
        quoteNumberPrefix: profile.quote_number_prefix,
      });
      setHistoryFeedback({ kind: 'success', message: tc('cloudLoadSuccess') });
    } catch {
      setHistoryFeedback({ kind: 'error', message: tc('cloudLoadError') });
    } finally {
      setIsCloudBusy(false);
    }
  };

  useEffect(() => {
    if (parsedJobs.length === 0 || filamentsQuery.isPending || spoolsQuery.isPending) {
      return;
    }
    const jobsKey = parsedJobs.map((job) => job.key).join('|');
    if (lastBuiltMaterialJobsKeyRef.current === jobsKey) {
      return;
    }

    const spoolCandidatesByFilamentId = new Map<number, AutoMaterialMatchCandidate>();
    for (const spool of availableSpools) {
      if (!spool.filament_id || !spool.filament) continue;
      const candidate = spoolCandidatesByFilamentId.get(spool.filament_id) ?? {
        filamentId: spool.filament_id,
        name: spool.filament.name,
        vendor: spool.filament.brand_name,
        materialType: spool.filament.material_type,
        color: spool.filament.color_name,
        spoolIds: [],
      };
      candidate.spoolIds.push(spool.id);
      spoolCandidatesByFilamentId.set(candidate.filamentId, candidate);
    }

    const nextLines: CalculatorMaterialLineState[] = [];
    for (const job of parsedJobs) {
      const usedMaterials = job.parsed.materials.filter(
        (material) => resolveParsedMaterialWeight(material) > 0,
      );
      const parsedMaterials = usedMaterials.length > 0
        ? usedMaterials
        : job.parsed.total_filament_weight_g
          ? [{ weight_g: job.parsed.total_filament_weight_g }]
          : [];

      parsedMaterials.forEach((material, materialIndex) => {
        const weightG = resolveParsedMaterialWeight(
          material,
          parsedMaterials.length === 1 ? job.parsed.total_filament_weight_g : null,
        );
        if (weightG <= 0) return;

        const toolIndex = material.tool_index ?? materialIndex;
        const match = findPrioritizedMaterialMatch(
          material,
          Array.from(spoolCandidatesByFilamentId.values()),
          filamentsQuery.data?.items ?? [],
          (candidate) => candidate,
          (filament) => ({
            name: filament.name,
            vendor: filament.brand_name,
            materialType: filament.material_type,
            color: filament.color_name,
          }),
        );
        const baseLine: CalculatorMaterialLineState = {
          line_id: `${job.key}:t${toolIndex}`,
          job_key: job.key,
          tool_index: toolIndex,
          label: buildParsedMaterialLabel(material, tc('unknownMaterial')),
          weight_g: weightG,
          spool_price: 0,
          spool_weight_kg: 1,
          delivery_cost: 0,
          price_source: 'manual',
          spool_id: null,
          filament_id: null,
          density_g_cm3: material.density_g_cm3 ?? null,
          selectionValue: 'manual',
          fileName: job.parsed.file_name,
          plateIndex: job.parsed.plate_index ?? null,
          confidence: match?.match.confidence ?? null,
          requiresSpoolChoice: false,
          priceResolved: false,
        };

        if (match?.source === 'user') {
          const candidate = match.match.item;
          if (candidate.spoolIds.length === 1) {
            const spool = availableSpools.find((item) => item.id === candidate.spoolIds[0]);
            if (spool) {
              const defaults = deriveUserSpoolDefaults(spool);
              const brandCurrency = spool.filament?.currency
                ? normalizeCurrency(spool.filament.currency)
                : null;
              const currencyMatches =
                spool.price != null || !brandCurrency || brandCurrency === calcCurrencyRef.current;
              baseLine.selectionValue = `spool:${spool.id}`;
              baseLine.spool_id = spool.id;
              baseLine.filament_id = spool.filament_id;
              baseLine.spool_price = currencyMatches ? (defaults.spoolPrice ?? 0) : 0;
              baseLine.spool_weight_kg = defaults.spoolWeightKg ?? 1;
              baseLine.price_source = spool.price != null ? 'spool' : 'filamenthub';
              baseLine.priceResolved = currencyMatches && defaults.spoolPrice != null;
            }
          } else {
            baseLine.selectionValue = '';
            baseLine.filament_id = candidate.filamentId;
            baseLine.requiresSpoolChoice = true;
          }
        } else if (match?.source === 'catalog') {
          const filament = match.match.item;
          const defaults = deriveCatalogFilamentDefaults(filament);
          const brandCurrency = filament.currency ? normalizeCurrency(filament.currency) : null;
          const currencyMatches = !brandCurrency || brandCurrency === calcCurrencyRef.current;
          baseLine.selectionValue = `filament:${filament.id}`;
          baseLine.filament_id = filament.id;
          baseLine.spool_price = currencyMatches ? (defaults.spoolPrice ?? 0) : 0;
          baseLine.spool_weight_kg = defaults.spoolWeightKg ?? 1;
          baseLine.price_source = 'filamenthub';
          baseLine.priceResolved = currencyMatches && defaults.spoolPrice != null;
        } else if ((material.slicer_profile_price_per_kg ?? 0) > 0) {
          baseLine.spool_price = material.slicer_profile_price_per_kg!;
          baseLine.spool_weight_kg = 1;
          baseLine.price_source = 'slicer';
          baseLine.priceResolved = true;
        }
        nextLines.push(baseLine);
      });
    }

    lastBuiltMaterialJobsKeyRef.current = jobsKey;
    setMaterialLines(nextLines);
  }, [
    availableSpools,
    filamentsQuery.data?.items,
    filamentsQuery.isPending,
    parsedJobs,
    spoolsQuery.isPending,
  ]);

  useEffect(() => {
    if (parsedJobs.length > 0) {
      return;
    }
    const currentParsedKey = parsedGcode
      ? `${parsedGcode.file_name}:${parsedGcode.file_size_bytes}:${parsedGcode.plate_index ?? 0}`
      : null;
    if (
      !parsedGcode ||
      !currentParsedKey ||
      lastAutoMatchedGcodeKeyRef.current === currentParsedKey ||
      filamentsQuery.isPending ||
      spoolsQuery.isPending
    ) {
      return;
    }

    const primaryMaterial = pickPrimaryParsedMaterial(parsedGcode);
    lastAutoMatchedGcodeKeyRef.current = currentParsedKey;
    setAutoMaterialMatch(null);

    if (!primaryMaterial) {
      return;
    }

    const spoolCandidatesByFilamentId = new Map<number, AutoMaterialMatchCandidate>();
    for (const spool of availableSpools) {
      if (!spool.filament_id || !spool.filament) continue;
      const candidate = spoolCandidatesByFilamentId.get(spool.filament_id) ?? {
        filamentId: spool.filament_id,
        name: spool.filament.name,
        vendor: spool.filament.brand_name,
        materialType: spool.filament.material_type,
        color: spool.filament.color_name,
        spoolIds: [],
      };
      candidate.spoolIds.push(spool.id);
      spoolCandidatesByFilamentId.set(candidate.filamentId, candidate);
    }

    const prioritizedMatch = findPrioritizedMaterialMatch(
      primaryMaterial,
      Array.from(spoolCandidatesByFilamentId.values()),
      filamentsQuery.data?.items ?? [],
      (candidate) => candidate,
      (filament) => ({
        name: filament.name,
        vendor: filament.brand_name,
        materialType: filament.material_type,
        color: filament.color_name,
      }),
    );

    if (prioritizedMatch?.source === 'user') {
      const spoolMatch = prioritizedMatch.match;
      priceManuallyEditedRef.current = false;
      const exactSpoolId = spoolMatch.item.spoolIds.length === 1 ? spoolMatch.item.spoolIds[0] : '';
      if (!exactSpoolId) {
        // The material identity is clear, but choosing an arbitrary physical
        // spool would silently pick the wrong purchase price or remaining stock.
        skipNextFilamentDefaultsRef.current = true;
        setMaterialPriceSource('unset');
      }
      setSelectedSpoolId(exactSpoolId);
      setForm((prev) => ({
        ...prev,
        selectedFilamentId: spoolMatch.item.filamentId,
        ...(!exactSpoolId ? { spoolPrice: 0 } : {}),
      }));
      setAutoMaterialMatch({
        confidence: spoolMatch.confidence,
        source: 'spool',
        requiresSpoolChoice: !exactSpoolId,
      });
      return;
    }

    if (prioritizedMatch?.source === 'catalog') {
      const catalogMatch = prioritizedMatch.match;
      priceManuallyEditedRef.current = false;
      setSelectedSpoolId('');
      setForm((prev) => ({ ...prev, selectedFilamentId: catalogMatch.item.id }));
      setAutoMaterialMatch({ confidence: catalogMatch.confidence, source: 'catalog' });
      return;
    }

    if ((primaryMaterial.slicer_profile_price_per_kg ?? 0) > 0) {
      priceManuallyEditedRef.current = false;
      setSelectedSpoolId('');
      setForm((prev) => ({
        ...prev,
        selectedFilamentId: '',
        spoolPrice: primaryMaterial.slicer_profile_price_per_kg ?? prev.spoolPrice,
        spoolWeightKg: 1,
      }));
      setMaterialPriceSource('slicer');
    }
  }, [
    availableSpools,
    filamentsQuery.data?.items,
    filamentsQuery.isPending,
    parsedGcode,
    spoolsQuery.isPending,
  ]);

  // Калькулятор — Pro-функция. Триал запускается только явным действием пользователя.
  if (!hasCalculatorAccess) {
    const trialError = startTrialMutation.error as {
      response?: { data?: { detail?: unknown } };
    } | null;

    return (
      <div className="mx-auto max-w-2xl">
        <div className={`${surfaceClass} p-8 text-center md:p-12`}>
          <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-cyan-500/15 text-cyan-300">
            <Calculator className="h-8 w-8" />
          </div>
          <h1 className="mb-3 text-2xl font-bold text-white">{tc('proLockedTitle')}</h1>
          <p className="mb-6 text-slate-300">{tc('proLockedDescription')}</p>
          {canStartTrial ? (
            <div className="space-y-4">
              <p className="text-sm text-slate-400">{tc('trialActivationHint')}</p>
              <button
                type="button"
                onClick={() => startTrialMutation.mutate()}
                disabled={startTrialMutation.isPending}
                className="inline-flex items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-cyan-500 to-blue-600 px-6 py-3 font-semibold text-white shadow-lg shadow-cyan-500/20 transition hover:from-cyan-400 hover:to-blue-500 disabled:cursor-wait disabled:opacity-60"
              >
                {startTrialMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="h-4 w-4" />
                )}
                {startTrialMutation.isPending ? tc('trialActivating') : tc('trialActivateAction')}
              </button>
              {startTrialMutation.isError && (
                <p className="text-sm text-red-300">
                  {translateApiError(
                    t,
                    trialError?.response?.data?.detail,
                    tc('trialActivationError'),
                  )}
                </p>
              )}
            </div>
          ) : (
            <p className="text-sm text-slate-400">{tc('proLockedHint')}</p>
          )}
        </div>
      </div>
    );
  }

  const trialEndsAt = user?.subscription?.status === 'trialing' ? user?.subscription?.trial_ends_at ?? null : null;
  const trialDaysLeft = trialEndsAt
    ? Math.max(0, Math.ceil((new Date(trialEndsAt).getTime() - Date.now()) / 86_400_000))
    : null;

  return (
    <div className="space-y-6">
      {trialDaysLeft !== null && (
        <div className="inline-flex w-fit items-center gap-1.5 rounded-full border border-cyan-400/20 bg-cyan-500/10 px-3 py-1 text-xs text-cyan-200">
          <Clock className="h-3.5 w-3.5 shrink-0" />
          <span>{t('profilePage.calculator.trialBanner', { days: trialDaysLeft })}</span>
        </div>
      )}
      <section className="relative overflow-hidden rounded-[2rem] bg-[linear-gradient(180deg,rgba(15,23,42,0.88),rgba(15,23,42,0.72))] shadow-[0_30px_90px_-50px_rgba(15,23,42,0.95)] backdrop-blur-xl ring-1 ring-white/5">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.18),transparent_34%),radial-gradient(circle_at_85%_18%,rgba(251,191,36,0.16),transparent_28%),radial-gradient(circle_at_50%_120%,rgba(16,185,129,0.12),transparent_42%)]" />
        <div className="relative px-6 py-7 md:px-8 md:py-8">
          <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
            <div className="max-w-3xl">
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-cyan-200">
                {tc('proBadge')}
              </div>
              <div className="mt-4 flex items-start gap-4">
                <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-[1.4rem] border border-white/10 bg-white/10 shadow-[inset_0_1px_0_rgba(255,255,255,0.15)]">
                  <Calculator className="h-8 w-8 text-cyan-300" />
                </div>
                <div>
                  <h1 className="text-2xl font-bold text-white md:text-4xl">{tc('title')}</h1>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300 md:text-base">
                    {tc('subtitle')}
                  </p>
                </div>
              </div>
            </div>

            <div className="grid gap-3 sm:min-w-[24rem] sm:grid-cols-3">
              <MetricTile label={tc('totalCost')} value={formatCurrency(summaryTotal)} />
              <MetricTile
                label={t('profilePage.calc.totalWorkTime')}
                value={formatHoursShort(summaryTime, t('profilePage.calc.h'), t('profilePage.calc.min'))}
              />
              <MetricTile label={t('profilePage.calc.quantity')} value={formatQuantity(summaryQuantity)} />
            </div>
          </div>

          <div className="mt-6 inline-flex flex-wrap gap-2 rounded-[1.4rem] border border-white/10 bg-black/20 p-1.5">
            <TabButton
              active={activeTab === 'calculator'}
              icon={<Calculator className="h-4 w-4" />}
              label={tc('tabs.calculator')}
              onClick={() => setActiveTab('calculator')}
            />
            <TabButton
              active={activeTab === 'history'}
              icon={<Clock className="h-4 w-4" />}
              label={tc('tabs.history')}
              onClick={() => setActiveTab('history')}
            />
          </div>

          {historyFeedback ? (
            <div
              className={`mt-5 rounded-[1.25rem] border px-4 py-3 text-sm ${
                historyFeedback.kind === 'success'
                  ? 'border-emerald-400/25 bg-emerald-500/10 text-emerald-100'
                  : 'border-red-400/25 bg-red-500/10 text-red-100'
              }`}
            >
              {historyFeedback.message}
            </div>
          ) : null}
        </div>
      </section>

      {activeTab === 'calculator' ? (
        <CalculatorView
          form={form}
          result={result}
          selectedFilament={selectedMaterial}
          selectedCatalogFilament={selectedCatalogFilament}
          selectedSpool={selectedSpool}
          autoMaterialMatch={autoMaterialMatch}
          materialPriceSource={materialPriceSource}
          parsedGcode={parsedGcode}
          parsedJobs={parsedJobs}
          jobConfigs={jobConfigs}
          materialLines={materialLines}
          batchParseWarning={batchParseWarning}
          materialLinesError={materialLinesError}
          dragActive={dragActive}
          filaments={filamentsQuery.data?.items ?? []}
          isFilamentsLoading={filamentsQuery.isPending}
          filamentsLoadError={filamentsQuery.isError ? tc('materialsLoadError') : null}
          spools={availableSpools}
          isSpoolsLoading={spoolsQuery.isPending}
          spoolsLoadError={spoolsQuery.isError ? tc('spoolsLoadError') : null}
          isParsingGcode={parseGcodeMutation.isPending}
          parseGcodeError={parseGcodeError}
          isCalculating={calculateMutation.isPending}
          estimateError={estimateError}
          canSaveHistory={Boolean(result)}
          fileInputRef={fileInputRef}
          isSavingHistory={saveHistoryMutation.isPending}
          onCalculate={handleCalculate}
          onChange={updateField}
          onStaticChange={updateStaticField}
          onSpoolSelect={handleSelectSpool}
          onCatalogFilamentSelect={handleSelectCatalogFilament}
          onFileSelect={handleFileSelection}
          onJobSelect={handleJobSelect}
          onJobConfigChange={handleJobConfigChange}
          onMaterialLineSelection={handleMaterialLineSelection}
          onMaterialLinePriceChange={handleMaterialLinePriceChange}
          onMaterialLineSpoolWeightChange={handleMaterialLineSpoolWeightChange}
          onDragStateChange={setDragActive}
          quoteProfile={quoteProfile}
          onQuoteProfileChange={updateQuoteProfileField}
          onOpenQuote={handleOpenQuote}
          onAddToQuote={handleAddToQuote}
          quoteItemCount={quoteItems.length}
          onSaveToHistory={handleSaveToHistory}
          onCloudSave={handleCloudSave}
          onCloudLoad={handleCloudLoad}
          isCloudBusy={isCloudBusy}
          formatCurrency={formatCurrency}
        />
      ) : (
        <HistoryView
          entries={historyQuery.data?.items ?? []}
          historyLoadError={historyLoadError}
          isDeletingHistory={deleteHistoryMutation.isPending}
          isLoading={historyQuery.isPending}
          total={historyQuery.data?.total ?? 0}
          onDeleteEntry={handleDeleteHistory}
          onRestoreEntry={handleRestoreHistory}
          formatCurrency={formatCurrency}
        />
      )}

      <QuoteModal
        isOpen={quoteModalOpen}
        source={estimateSource}
        quoteParties={quoteParties}
        result={result}
        quoteItems={quoteItems}
        onRemoveFromQuote={handleRemoveFromQuote}
        onRenameQuoteItem={handleRenameQuoteItem}
        onClearQuoteItems={() => setQuoteItems([])}
        onClose={() => setQuoteModalOpen(false)}
        onPartyChange={(field, value) => {
          setQuoteParties((prev) => ({
            ...prev,
            [field]: value,
          }));
        }}
        onPrint={handlePrintQuote}
        onShare={handleShareQuote}
        onDownloadPdf={handleDownloadPdf}
        isSharing={isSharing}
        isPdfDownloading={isPdfDownloading}
        isLoggedIn={!!user}
        formatCurrency={formatCurrency}
      />

      <ConfirmDeleteModal
        isOpen={deletingHistoryEntry !== null}
        onClose={() => setDeletingHistoryEntry(null)}
        onConfirm={() => {
          if (deletingHistoryEntry) void performDeleteHistory(deletingHistoryEntry);
        }}
        message={tc('historyDeleteConfirm')}
        isLoading={deleteHistoryMutation.isPending}
      />
    </div>
  );
};

interface CalculatorViewProps {
  form: CalculatorFormState;
  quoteProfile: QuoteProfileState;
  result: CalculatorEstimateResponse | null;
  selectedFilament: MaterialSelectionSnapshot | null;
  selectedCatalogFilament: Filament | null;
  selectedSpool: UserSpool | null;
  autoMaterialMatch: AutoMaterialMatchNotice | null;
  materialPriceSource: MaterialPriceSource;
  parsedGcode: CalculatorGcodeParseResponse | null;
  parsedJobs: ParsedJobState[];
  jobConfigs: CalculatorJobConfig[];
  materialLines: CalculatorMaterialLineState[];
  batchParseWarning: string | null;
  materialLinesError: string | null;
  dragActive: boolean;
  filaments: Filament[];
  isFilamentsLoading: boolean;
  filamentsLoadError: string | null;
  spools: UserSpool[];
  isSpoolsLoading: boolean;
  spoolsLoadError: string | null;
  isParsingGcode: boolean;
  parseGcodeError: string | null;
  isCalculating: boolean;
  estimateError: string | null;
  canSaveHistory: boolean;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  isSavingHistory: boolean;
  onCalculate: () => void;
  onChange: <K extends keyof CalculatorFormState>(field: K, value: CalculatorFormState[K]) => void;
  onStaticChange: <K extends CalculatorStaticSettingKey>(field: K, value: CalculatorFormState[K]) => void;
  onSpoolSelect: (spoolId: number | '') => void;
  onCatalogFilamentSelect: (filamentId: number | '') => void;
  onQuoteProfileChange: <K extends keyof QuoteProfileState>(field: K, value: QuoteProfileState[K]) => void;
  onFileSelect: (files: FileList | null) => Promise<void>;
  onJobSelect: (jobKey: string) => void;
  onJobConfigChange: (
    jobKey: string,
    patch: Partial<Omit<CalculatorJobConfig, 'jobKey'>>,
  ) => void;
  onMaterialLineSelection: (lineId: string, selectionValue: string) => void;
  onMaterialLinePriceChange: (lineId: string, value: number) => void;
  onMaterialLineSpoolWeightChange: (lineId: string, value: number) => void;
  onDragStateChange: (active: boolean) => void;
  onOpenQuote: () => void;
  onAddToQuote: () => void;
  quoteItemCount: number;
  onSaveToHistory: () => Promise<void>;
  onCloudSave: () => Promise<void>;
  onCloudLoad: () => Promise<void>;
  isCloudBusy: boolean;
  formatCurrency: (value: number | null | undefined) => string;
}

const CalculatorView: React.FC<CalculatorViewProps> = ({
  form,
  quoteProfile,
  result,
  selectedFilament,
  selectedCatalogFilament,
  selectedSpool,
  autoMaterialMatch,
  materialPriceSource,
  parsedGcode,
  parsedJobs,
  jobConfigs,
  materialLines,
  batchParseWarning,
  materialLinesError,
  dragActive,
  filaments,
  isFilamentsLoading,
  filamentsLoadError,
  spools,
  isSpoolsLoading,
  spoolsLoadError,
  isParsingGcode,
  parseGcodeError,
  isCalculating,
  estimateError,
  canSaveHistory,
  fileInputRef,
  isSavingHistory,
  onCalculate,
  onChange,
  onStaticChange,
  onSpoolSelect,
  onCatalogFilamentSelect,
  onQuoteProfileChange,
  onFileSelect,
  onJobSelect,
  onJobConfigChange,
  onMaterialLineSelection,
  onMaterialLinePriceChange,
  onMaterialLineSpoolWeightChange,
  onDragStateChange,
  onOpenQuote,
  onAddToQuote,
  quoteItemCount,
  onSaveToHistory,
  onCloudSave,
  onCloudLoad,
  isCloudBusy,
  formatCurrency,
}) => {
  const { t } = useTranslation();
  const tc = (key: string) => translateCalculator(t, key);
  const [staticSettingsOpen, setStaticSettingsOpen] = useState(false);
  const [quoteProfileOpen, setQuoteProfileOpen] = useState(false);
  const [advancedSettingsOpen, setAdvancedSettingsOpen] = useState(false);
  const [postprocessChecked, setPostprocessChecked] = useState<Record<string, boolean>>({});
  const [customPresets, setCustomPresets] = useState<PricingPreset[]>(() => loadCustomPricingPresets());
  const [presetNameInput, setPresetNameInput] = useState('');
  const [expandedMaterialLineIds, setExpandedMaterialLineIds] = useState<Set<string>>(new Set());
  const [singleMaterialCostOpen, setSingleMaterialCostOpen] = useState(true);

  useEffect(() => {
    setExpandedMaterialLineIds((current) => {
      const availableIds = new Set(materialLines.map((line) => line.line_id));
      const next = new Set([...current].filter((lineId) => availableIds.has(lineId)));
      materialLines.forEach((line) => {
        if (!line.priceResolved) next.add(line.line_id);
      });
      return next;
    });
  }, [materialLines]);

  const materialSourceLabel = {
    spool: tc('materialSourceSpool'),
    filamenthub: tc('materialSourceCatalog'),
    slicer: tc('materialSourceSlicer'),
    manual: tc('materialSourceManual'),
    unset: tc('materialSourceUnset'),
  }[materialPriceSource];
  const unifiedMaterialSelectionValue = selectedSpool
    ? `spool:${selectedSpool.id}`
    : selectedCatalogFilament
      ? `filament:${selectedCatalogFilament.id}`
      : 'manual';
  const activeParsedJobKey = parsedJobs.find(
    (job) =>
      job.parsed.file_name === parsedGcode?.file_name
      && job.parsed.plate_index === parsedGcode?.plate_index,
  )?.key;
  const materialMatchConfidenceLabel = autoMaterialMatch
    ? {
        high: tc('materialMatchConfidenceHigh'),
        medium: tc('materialMatchConfidenceMedium'),
        low: tc('materialMatchConfidenceLow'),
      }[autoMaterialMatch.confidence]
    : null;
  // Каталожная цена бренда в другой валюте: её не подставили в форму, просим указать свою.
  const catalogBrandCurrency = !selectedSpool && selectedCatalogFilament?.currency
    ? normalizeCurrency(selectedCatalogFilament.currency)
    : null;
  const catalogPriceMismatch =
    catalogBrandCurrency && catalogBrandCurrency !== quoteProfile.currency && selectedCatalogFilament
      ? {
          brandSymbol: currencySymbol(catalogBrandCurrency),
          reference: deriveCatalogFilamentDefaults(selectedCatalogFilament).spoolPrice,
        }
      : null;
  const materialSummary =
    selectedSpool
      ? [
          selectedSpool.price != null ? formatCurrency(selectedSpool.price) : tc('materialPriceUnknown'),
          `${Math.round(selectedSpool.initial_weight_g)} ${tc('grams')}`,
          `${Math.round(selectedSpool.remaining_weight_g)} ${tc('grams')} ${tc('remainingShort')}`,
        ].join(' · ')
      : selectedCatalogFilament &&
          (selectedCatalogFilament.price_per_kg != null || selectedCatalogFilament.spool_weight != null)
        ? `${selectedCatalogFilament.price_per_kg != null ? `${selectedCatalogFilament.price_per_kg.toFixed(0)} ${currencySymbol(quoteProfile.currency)}/${tc('kg')}` : '—'} · ${
            selectedCatalogFilament.spool_weight != null
              ? `${selectedCatalogFilament.spool_weight.toFixed(0)} ${tc('grams')}`
              : '—'
          }`
        : null;
  const roundingModeLabel =
    form.roundingMode === 'down'
      ? t('profilePage.calc.roundingModeDown')
      : form.roundingMode === 'nearest'
        ? t('profilePage.calc.roundingModeNearest')
        : t('profilePage.calc.roundingModeUp');
  const parsedSupportsSummary = parsedGcode
    ? [
        parsedGcode.support_used == null
          ? null
          : parsedGcode.support_used
            ? tc('parsedYes')
            : tc('parsedNo'),
        parsedGcode.support_type,
        parsedGcode.support_threshold_angle_deg != null ? `${parsedGcode.support_threshold_angle_deg}°` : null,
      ]
        .filter(Boolean)
        .join(' · ') || tc('parsedNone')
    : null;
  const parsedAdhesionSummary = parsedGcode
    ? [
        parsedGcode.brim_width_mm != null && parsedGcode.brim_width_mm > 0
          ? `${tc('parsedBrim')} ${parsedGcode.brim_width_mm} mm`
          : null,
        parsedGcode.raft_layers != null && parsedGcode.raft_layers > 0
          ? `${tc('parsedRaft')} ${parsedGcode.raft_layers}`
          : null,
      ]
        .filter(Boolean)
        .join(' · ') || tc('parsedNone')
    : null;
  const primaryParsedMaterial = pickPrimaryParsedMaterial(parsedGcode);
  const parsedNozzleSummary =
    parsedGcode?.nozzle_diameter_mm != null ? `${parsedGcode.nozzle_diameter_mm} mm` : null;
  const firstLayerTemperatureSummary = formatParsedTemperaturePair(
    parsedGcode?.nozzle_temperature_first_layer_c,
    parsedGcode?.bed_temperature_first_layer_c,
  );
  const otherLayerTemperatureSummary = formatParsedTemperaturePair(
    parsedGcode?.nozzle_temperature_other_layers_c,
    parsedGcode?.bed_temperature_other_layers_c,
  );
  const parsedTemperaturesSummary = [
    firstLayerTemperatureSummary ? `${tc('parsedFirstLayerShort')} ${firstLayerTemperatureSummary}` : null,
    otherLayerTemperatureSummary && otherLayerTemperatureSummary !== firstLayerTemperatureSummary
      ? `${tc('parsedOtherLayersShort')} ${otherLayerTemperatureSummary}`
      : null,
  ]
    .filter(Boolean)
    .join(' · ');
  const showParsedMaterialsSection = Boolean(
    parsedGcode
      && (
        parsedGcode.materials.length > 1
        || (parsedGcode.active_material_count != null && parsedGcode.active_material_count > 1)
        || (parsedGcode.toolchange_count != null && parsedGcode.toolchange_count > 0)
        || parsedGcode.is_multi_material
      ),
  );
  const displayJobs: ParsedJobState[] = parsedJobs.length > 0
    ? parsedJobs
    : parsedGcode
      ? [{ key: 'single-job', parsed: parsedGcode }]
      : [];
  const hasParsedJobs = displayJobs.length > 0;
  const isBatchMode = displayJobs.length > 1;
  const jobConfigsByKey = new Map(jobConfigs.map((config) => [config.jobKey, config]));
  const getJobConfig = (job: ParsedJobState): CalculatorJobConfig => jobConfigsByKey.get(job.key)
    ?? createDefaultJobConfig(job);
  const batchSummary = buildConfiguredCalculatorBatchSummary(
    displayJobs.map((job) => {
      const config = getJobConfig(job);
      const groups = job.parsed.object_groups ?? [];
      const quoteMode = config.quoteMode === 'groups'
        && groups.length > 1
        && !canSplitCalculatorObjectGroups(groups)
        ? 'set'
        : config.quoteMode;
      return {
        repeats: config.repeats,
        outputQuantityPerRun: calculatorOutputQuantityPerRun(groups, quoteMode),
        printTimeSeconds: config.printTimeSeconds,
        weightG: job.parsed.total_filament_weight_g,
        objectCount: job.parsed.object_count,
      };
    }),
  );
  const objectGroupCount = displayJobs.reduce(
    (sum, job) => sum + Math.max(1, job.parsed.object_groups?.length ?? 0),
    0,
  );
  const jobTitleByKey = new Map(displayJobs.map((job, index) => [
    job.key,
    quoteTitleFromFileName(job.parsed.file_name, `${tc('jobFallbackTitle')} ${index + 1}`),
  ]));
  const formatBatchWeight = (weightG: number) =>
    weightG >= 1000 ? `${(weightG / 1000).toFixed(2)} ${tc('kg')}` : `${weightG.toFixed(2)} ${tc('grams')}`;
  const renderMaterialLine = (line: CalculatorMaterialLineState) => (
    <div key={line.line_id} className="rounded-[1.15rem] border border-white/[0.08] bg-black/15 p-3.5">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-white">{line.label}</p>
          <p className="mt-1 text-xs text-slate-400">
            {line.tool_index != null ? `T${line.tool_index} · ` : ''}
            {line.weight_g.toFixed(2)} {tc('grams')}
          </p>
        </div>
        <StatusPill tone={line.priceResolved ? 'success' : 'warning'}>
          {line.priceResolved ? tc(`materialLineSource.${line.price_source}`) : tc('materialLineNeedsPrice')}
        </StatusPill>
      </div>
      <div className="space-y-3">
        <select
          className={`${inputClass} py-2.5 text-sm`}
          value={line.selectionValue}
          onChange={(event) => {
            const selectionValue = event.target.value;
            onMaterialLineSelection(line.line_id, selectionValue);
            setExpandedMaterialLineIds((current) => {
              const next = new Set(current);
              if (!selectionValue || selectionValue === 'manual') next.add(line.line_id);
              else next.delete(line.line_id);
              return next;
            });
          }}
        >
          {line.requiresSpoolChoice ? <option value="">{tc('chooseExactSpool')}</option> : null}
          <option value="manual">{tc('materialManualOption')}</option>
          <optgroup label={tc('chooseFromMyFilaments')}>
            {spools.map((spool) => (
              <option key={`line-spool-${line.line_id}-${spool.id}`} value={`spool:${spool.id}`}>
                {buildSpoolLabel(spool)}
              </option>
            ))}
          </optgroup>
          <optgroup label={tc('chooseFromCatalog')}>
            {filaments.map((filament) => (
              <option key={`line-filament-${line.line_id}-${filament.id}`} value={`filament:${filament.id}`}>
                {buildFilamentLabel(filament)}
              </option>
            ))}
          </optgroup>
        </select>
        <div className="flex min-h-9 flex-wrap items-center justify-between gap-3 rounded-xl border border-white/[0.06] bg-white/[0.035] px-3 py-2">
          <p className="text-xs text-slate-300">
            {line.priceResolved
              ? `${formatCurrency(line.spool_price)} · ${line.spool_weight_kg} ${tc('kg')}`
              : tc('materialLineNeedsPrice')}
          </p>
          <button
            type="button"
            className="inline-flex items-center gap-1.5 text-xs font-medium text-cyan-200 transition-colors hover:text-white"
            onClick={() => setExpandedMaterialLineIds((current) => {
              const next = new Set(current);
              if (next.has(line.line_id)) next.delete(line.line_id);
              else next.add(line.line_id);
              return next;
            })}
          >
            {expandedMaterialLineIds.has(line.line_id) ? tc('hideMaterialCost') : tc('editMaterialCost')}
            <ChevronDown className={`h-3.5 w-3.5 transition-transform ${expandedMaterialLineIds.has(line.line_id) ? 'rotate-180' : ''}`} />
          </button>
        </div>
        {expandedMaterialLineIds.has(line.line_id) ? (
          <div className="grid grid-cols-1 gap-3 border-t border-white/[0.06] pt-3 sm:grid-cols-2">
            <FieldBlock label={tc('spoolPrice')}>
              <InputWithSuffix
                value={line.spool_price}
                onChange={(value) => onMaterialLinePriceChange(line.line_id, value)}
                placeholder="1200"
                suffix={currencySymbol(quoteProfile.currency)}
              />
            </FieldBlock>
            <FieldBlock label={tc('spoolWeight')}>
              <InputWithSuffix
                value={line.spool_weight_kg}
                onChange={(value) => onMaterialLineSpoolWeightChange(line.line_id, value)}
                placeholder="1"
                suffix={tc('kg')}
                step="0.1"
              />
            </FieldBlock>
          </div>
        ) : null}
      </div>
    </div>
  );

  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(22rem,0.92fr)]">
      <div className="space-y-5">
        <SurfaceCard className="p-4 md:p-5">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <SectionHeading icon={<Settings2 className="h-5 w-5 text-cyan-300" />} title={tc('staticSettingsTitle')} compact />
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setStaticSettingsOpen((prev) => !prev)}
                className={ghostButtonClass}
              >
                <Settings2 className="h-4 w-4" />
                {tc('staticEconomicsTitle')}
                <ChevronDown className={`h-4 w-4 transition-transform ${staticSettingsOpen ? 'rotate-180' : ''}`} />
              </button>
              <button
                type="button"
                onClick={() => setQuoteProfileOpen((prev) => !prev)}
                className={ghostButtonClass}
              >
                <FileText className="h-4 w-4" />
                {tc('quoteProfileTitle')}
                <ChevronDown className={`h-4 w-4 transition-transform ${quoteProfileOpen ? 'rotate-180' : ''}`} />
              </button>
            </div>
          </div>

          {staticSettingsOpen || quoteProfileOpen ? (
            <div className="mt-4 space-y-4 border-t border-white/10 pt-4">
              {staticSettingsOpen ? (
                <div>
                  <p className="text-sm font-semibold text-white">{tc('staticEconomicsTitle')}</p>
                  <p className="mt-1 text-xs leading-5 text-slate-400">
                    {`${t('profilePage.calc.printingRate')}: ${form.printingRatePerHour} ${currencySymbol(quoteProfile.currency)}/${tc('hourAbbr')} · ${t('profilePage.calc.taxRatePercent')}: ${form.taxRatePercent}% · ${t('profilePage.calc.roundTo')}: ${form.roundToNearest} ${currencySymbol(quoteProfile.currency)} · ${roundingModeLabel}`}
                  </p>
                </div>
              ) : null}

              {staticSettingsOpen ? (
                <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                  <FieldBlock
                    label={
                      <TooltipLabel
                        label={t('profilePage.calc.electricityCost')}
                        tooltipText={tc('defaultElectricityCostTooltip')}
                      />
                    }
                  >
                    <InputWithSuffix
                      value={form.electricityCostPerKwh}
                      onChange={(value) => onStaticChange('electricityCostPerKwh', value)}
                      placeholder="6"
                      suffix={`${currencySymbol(quoteProfile.currency)}/${tc('kwhAbbr')}`}
                      step="0.1"
                    />
                  </FieldBlock>
                  <FieldBlock
                    label={
                      <TooltipLabel
                        label={t('profilePage.calc.printerPower')}
                        tooltipText={tc('defaultPrinterPowerTooltip')}
                      />
                    }
                    hint={
                      form.powerHotendW + form.powerBedW + form.powerSteppersW + form.powerElectronicsW > 0
                        ? `${tc('autoCalc')}: ${form.powerHotendW + form.powerBedW + form.powerSteppersW + form.powerElectronicsW} ${tc('wattAbbr')}`
                        : undefined
                    }
                  >
                    <InputWithSuffix
                      value={form.printerPowerW}
                      onChange={(value) => onStaticChange('printerPowerW', value)}
                      placeholder="350"
                      suffix={tc('wattAbbr')}
                    />
                  </FieldBlock>
                  <FieldBlock label={tc('powerHotend')} hint={tc('powerHotendHint')}>
                    <InputWithSuffix
                      value={form.powerHotendW}
                      onChange={(value) => {
                        onStaticChange('powerHotendW', value);
                        const total = value + form.powerBedW + form.powerSteppersW + form.powerElectronicsW;
                        if (total > 0) onStaticChange('printerPowerW', total);
                      }}
                      placeholder="0"
                      suffix={tc('wattAbbr')}
                    />
                  </FieldBlock>
                  <FieldBlock label={tc('powerBed')} hint={tc('powerBedHint')}>
                    <InputWithSuffix
                      value={form.powerBedW}
                      onChange={(value) => {
                        onStaticChange('powerBedW', value);
                        const total = form.powerHotendW + value + form.powerSteppersW + form.powerElectronicsW;
                        if (total > 0) onStaticChange('printerPowerW', total);
                      }}
                      placeholder="0"
                      suffix={tc('wattAbbr')}
                    />
                  </FieldBlock>
                  <FieldBlock label={tc('powerSteppers')} hint={tc('powerSteppersHint')}>
                    <InputWithSuffix
                      value={form.powerSteppersW}
                      onChange={(value) => {
                        onStaticChange('powerSteppersW', value);
                        const total = form.powerHotendW + form.powerBedW + value + form.powerElectronicsW;
                        if (total > 0) onStaticChange('printerPowerW', total);
                      }}
                      placeholder="0"
                      suffix={tc('wattAbbr')}
                    />
                  </FieldBlock>
                  <FieldBlock label={tc('powerElectronics')} hint={tc('powerElectronicsHint')}>
                    <InputWithSuffix
                      value={form.powerElectronicsW}
                      onChange={(value) => {
                        onStaticChange('powerElectronicsW', value);
                        const total = form.powerHotendW + form.powerBedW + form.powerSteppersW + value;
                        if (total > 0) onStaticChange('printerPowerW', total);
                      }}
                      placeholder="0"
                      suffix={tc('wattAbbr')}
                    />
                  </FieldBlock>
                  <FieldBlock
                    label={
                      <TooltipLabel
                        label={t('profilePage.calc.printingRate')}
                        tooltipText={tc('defaultPrintingRateTooltip')}
                      />
                    }
                  >
                    <InputWithSuffix
                      value={form.printingRatePerHour}
                      onChange={(value) => onStaticChange('printingRatePerHour', value)}
                      placeholder="170"
                      suffix={`${currencySymbol(quoteProfile.currency)}/${tc('hourAbbr')}`}
                    />
                  </FieldBlock>
                  <FieldBlock
                    label={
                      <TooltipLabel
                        label={t('profilePage.calc.modeling')}
                        tooltipText={tc('defaultModelingRateTooltip')}
                      />
                    }
                    hint={t('profilePage.calc.rate')}
                  >
                    <InputWithSuffix
                      value={form.modelingRatePerHour}
                      onChange={(value) => onStaticChange('modelingRatePerHour', value)}
                      placeholder="934"
                      suffix={`${currencySymbol(quoteProfile.currency)}/${tc('hourAbbr')}`}
                    />
                  </FieldBlock>
                  <FieldBlock
                    label={
                      <TooltipLabel
                        label={t('profilePage.calc.postprocessing')}
                        tooltipText={tc('defaultPostprocessingRateTooltip')}
                      />
                    }
                    hint={t('profilePage.calc.rate')}
                  >
                    <InputWithSuffix
                      value={form.postprocessingRatePerHour}
                      onChange={(value) => onStaticChange('postprocessingRatePerHour', value)}
                      placeholder="100"
                      suffix={`${currencySymbol(quoteProfile.currency)}/${tc('hourAbbr')}`}
                    />
                  </FieldBlock>
                  <FieldBlock
                    label={
                      <TooltipLabel
                        label={t('profilePage.calc.amortizationRate')}
                        tooltipText={tc('defaultAmortizationRateTooltip')}
                      />
                    }
                    hint={
                      form.printerPurchasePrice > 0 && form.printerUsefulHours > 0
                        ? `${tc('autoCalc')}: ${(form.printerPurchasePrice / form.printerUsefulHours).toFixed(2)} ${currencySymbol(quoteProfile.currency)}/${tc('hourAbbr')}`
                        : undefined
                    }
                  >
                    <InputWithSuffix
                      value={form.amortizationRatePerHour}
                      onChange={(value) => onStaticChange('amortizationRatePerHour', value)}
                      placeholder="16"
                      suffix={`${currencySymbol(quoteProfile.currency)}/${tc('hourAbbr')}`}
                    />
                  </FieldBlock>
                  <FieldBlock label={tc('printerPurchasePrice')} hint={tc('printerPurchasePriceHint')}>
                    <InputWithSuffix
                      value={form.printerPurchasePrice}
                      onChange={(value) => {
                        onStaticChange('printerPurchasePrice', value);
                        if (value > 0 && form.printerUsefulHours > 0) {
                          onStaticChange('amortizationRatePerHour', Math.round((value / form.printerUsefulHours) * 100) / 100);
                        }
                      }}
                      placeholder="0"
                      suffix={currencySymbol(quoteProfile.currency)}
                    />
                  </FieldBlock>
                  <FieldBlock label={tc('printerUsefulHours')} hint={tc('printerUsefulHoursHint')}>
                    <InputWithSuffix
                      value={form.printerUsefulHours}
                      onChange={(value) => {
                        onStaticChange('printerUsefulHours', value);
                        if (form.printerPurchasePrice > 0 && value > 0) {
                          onStaticChange('amortizationRatePerHour', Math.round((form.printerPurchasePrice / value) * 100) / 100);
                        }
                      }}
                      placeholder="0"
                      suffix={tc('hoursAbbr')}
                    />
                  </FieldBlock>
                  <FieldBlock
                    label={
                      <TooltipLabel
                        label={t('profilePage.calc.overheadPercent')}
                        tooltipText={tc('defaultOverheadTooltip')}
                      />
                    }
                    hint={t('profilePage.calc.overheadHint')}
                  >
                    <InputWithSuffix
                      value={form.overheadPercent}
                      onChange={(value) => onStaticChange('overheadPercent', value)}
                      placeholder="20"
                      suffix="%"
                      step="0.1"
                    />
                  </FieldBlock>
                  <FieldBlock
                    label={
                      <TooltipLabel
                        label={t('profilePage.calc.markupPercent')}
                        tooltipText={tc('defaultMarkupTooltip')}
                      />
                    }
                    hint={t('profilePage.calc.markupHint')}
                  >
                    <InputWithSuffix
                      value={form.markupPercent}
                      onChange={(value) => onStaticChange('markupPercent', value)}
                      placeholder="30"
                      suffix="%"
                      step="0.1"
                    />
                  </FieldBlock>
                  <FieldBlock label={t('profilePage.calc.taxRatePercent')} hint={t('profilePage.calc.taxRateHint')}>
                    <InputWithSuffix
                      value={form.taxRatePercent}
                      onChange={(value) => onStaticChange('taxRatePercent', value)}
                      placeholder="0"
                      suffix="%"
                      step="0.1"
                    />
                  </FieldBlock>
                  <FieldBlock label={t('profilePage.calc.fixedCosts')} hint={t('profilePage.calc.fixedCostsHint')}>
                    <InputWithSuffix
                      value={form.fixedCosts}
                      onChange={(value) => onStaticChange('fixedCosts', value)}
                      placeholder="0"
                      suffix={currencySymbol(quoteProfile.currency)}
                    />
                  </FieldBlock>
                  <FieldBlock label={t('profilePage.calc.bedPrepCost')} hint={t('profilePage.calc.bedPrepCostHint')}>
                    <InputWithSuffix
                      value={form.bedPrepCostPerPrint}
                      onChange={(value) => onStaticChange('bedPrepCostPerPrint', value)}
                      placeholder="0"
                      suffix={currencySymbol(quoteProfile.currency)}
                    />
                  </FieldBlock>
                  <FieldBlock label={t('profilePage.calc.minOrderPrice')} hint={t('profilePage.calc.minOrderPriceHint')}>
                    <InputWithSuffix
                      value={form.minOrderPrice}
                      onChange={(value) => onStaticChange('minOrderPrice', value)}
                      placeholder="0"
                      suffix={currencySymbol(quoteProfile.currency)}
                    />
                  </FieldBlock>
                  <FieldBlock label={t('profilePage.calc.roundTo')}>
                    <InputWithSuffix
                      value={form.roundToNearest}
                      onChange={(value) => onStaticChange('roundToNearest', value)}
                      placeholder="10"
                      suffix={currencySymbol(quoteProfile.currency)}
                    />
                  </FieldBlock>
                  <FieldBlock label={t('profilePage.calc.roundingMode')}>
                    <select
                      className={`${inputClass} w-full sm:max-w-[15rem]`}
                      value={form.roundingMode}
                      onChange={(event) => onStaticChange('roundingMode', event.target.value as RoundingMode)}
                    >
                      <option value="up">{t('profilePage.calc.roundingModeUp')}</option>
                      <option value="nearest">{t('profilePage.calc.roundingModeNearest')}</option>
                      <option value="down">{t('profilePage.calc.roundingModeDown')}</option>
                    </select>
                  </FieldBlock>
                </div>
              ) : null}

              {quoteProfileOpen ? (
                <div className={staticSettingsOpen ? 'border-t border-white/10 pt-4' : ''}>
                  <p className="text-sm font-semibold text-white">{tc('quoteProfileTitle')}</p>
                  <p className="mt-1 text-xs leading-5 text-slate-400">
                    {(quoteProfile.sellerName || tc('quoteProfileSummaryEmpty')) +
                      ` · ${tc('quoteValidityDaysShort')}: ${quoteProfile.validityDays} ${tc('dayAbbr')}`}
                  </p>
                <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                  <FieldBlock label={tc('quoteSellerName')}>
                    <TextInput
                      value={quoteProfile.sellerName}
                      onChange={(value) => onQuoteProfileChange('sellerName', value)}
                      placeholder={tc('quoteSellerNamePlaceholder')}
                    />
                  </FieldBlock>
                  <FieldBlock label={tc('quoteSellerInn')}>
                    <TextInput
                      value={quoteProfile.sellerInn}
                      onChange={(value) => onQuoteProfileChange('sellerInn', value)}
                      placeholder="123456789012"
                    />
                  </FieldBlock>
                  <FieldBlock label={tc('quoteSellerPhone')}>
                    <TextInput
                      value={quoteProfile.sellerPhone}
                      onChange={(value) => onQuoteProfileChange('sellerPhone', value)}
                      placeholder="+7 (999) 000-00-00"
                    />
                  </FieldBlock>
                  <FieldBlock label={tc('quoteValidityDays')} hint={tc('quoteValidityDaysHint')}>
                    <NumberInput
                      value={quoteProfile.validityDays}
                      onChange={(value) => onQuoteProfileChange('validityDays', Math.max(1, value))}
                      min="1"
                      placeholder="14"
                    />
                  </FieldBlock>
                  <FieldBlock label={tc('quoteLegalStatus')} hint={tc('quoteDisclaimerHint')}>
                    <select
                      className={`${inputClass} w-full sm:max-w-[18rem]`}
                      value={quoteProfile.disclaimerMode}
                      onChange={(event) =>
                        onQuoteProfileChange('disclaimerMode', event.target.value as QuoteDisclaimerMode)
                      }
                    >
                      <option value="not_offer">{tc('quoteDisclaimerNotOffer')}</option>
                      <option value="offer">{tc('quoteDisclaimerOffer')}</option>
                    </select>
                  </FieldBlock>
                  <FieldBlock label={tc('quoteCurrency')}>
                    <select
                      className={`${inputClass} w-full sm:max-w-[18rem]`}
                      value={quoteProfile.currency}
                      onChange={(event) =>
                        onQuoteProfileChange('currency', event.target.value as CurrencyCode)
                      }
                    >
                      {CURRENCY_OPTIONS.map((c) => (
                        <option key={c} value={c}>{c} ({currencySymbol(c)})</option>
                      ))}
                    </select>
                  </FieldBlock>
                  <FieldBlock label={tc('quoteNumberPrefix')} hint={tc('quoteNumberPrefixHint')}>
                    <TextInput
                      value={quoteProfile.quoteNumberPrefix}
                      onChange={(value) => onQuoteProfileChange('quoteNumberPrefix', value)}
                      placeholder="КП"
                    />
                  </FieldBlock>
                  <div className="md:col-span-2 xl:col-span-3">
                    <FieldBlock label={tc('quotePaymentTerms')}>
                      <TextareaInput
                        value={quoteProfile.paymentTerms}
                        onChange={(value) => onQuoteProfileChange('paymentTerms', value)}
                        placeholder={tc('quotePaymentTermsPlaceholder')}
                      />
                    </FieldBlock>
                  </div>
                </div>
                </div>
              ) : null}

              <div className="mt-4 flex flex-wrap gap-2 border-t border-white/10 pt-4">
                <button
                  type="button"
                  onClick={onCloudSave}
                  disabled={isCloudBusy}
                  className={ghostButtonClass}
                >
                  {isCloudBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudUpload className="h-4 w-4" />}
                  {tc('cloudSave')}
                </button>
                <button
                  type="button"
                  onClick={onCloudLoad}
                  disabled={isCloudBusy}
                  className={ghostButtonClass}
                >
                  {isCloudBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudDownload className="h-4 w-4" />}
                  {tc('cloudLoad')}
                </button>
              </div>
            </div>
          ) : null}
        </SurfaceCard>

        <SurfaceCard className="p-5 md:p-6">
          <SectionHeading icon={<Printer className="h-5 w-5 text-cyan-300" />} title={tc('workspaceTitle')} />

          <div className="mt-5 space-y-5">
            <input
              id="calculator-gcode-upload"
              ref={fileInputRef}
              type="file"
              multiple
              accept=".gcode,.gcode.3mf,.txt,.gz"
              className="sr-only"
              onChange={async (event) => {
                const input = event.currentTarget;
                await onFileSelect(input.files);
                input.value = '';
              }}
            />

            <div className="space-y-5">
              <WorkspacePanel
                step="1"
                title={tc('workspaceSourceTitle')}
              >
                <label
                  htmlFor="calculator-gcode-upload"
                  role="button"
                  tabIndex={0}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      fileInputRef.current?.click();
                    }
                  }}
                  onDragEnter={(event) => {
                    event.preventDefault();
                    onDragStateChange(true);
                  }}
                  onDragOver={(event) => {
                    event.preventDefault();
                    onDragStateChange(true);
                  }}
                  onDragLeave={(event) => {
                    event.preventDefault();
                    onDragStateChange(false);
                  }}
                  onDrop={async (event) => {
                    event.preventDefault();
                    onDragStateChange(false);
                    await onFileSelect(event.dataTransfer.files);
                  }}
                  className={`block min-h-[9.5rem] w-full cursor-pointer rounded-[1.5rem] border border-dashed p-7 text-left transition-all md:p-8 ${
                    dragActive
                      ? 'border-cyan-300/80 bg-cyan-400/12 shadow-[0_25px_50px_-35px_rgba(34,211,238,0.65)]'
                      : 'border-cyan-400/30 bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.14),transparent_52%),linear-gradient(180deg,rgba(15,23,42,0.8),rgba(2,6,23,0.85))] hover:border-cyan-300/50'
                  }`}
                >
                  <div className="flex min-h-[5.5rem] items-center gap-5">
                    <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-[1.2rem] border border-white/10 bg-white/5">
                      {isParsingGcode ? <Loader2 className="h-6 w-6 animate-spin text-cyan-300" /> : <Upload className="h-6 w-6 text-cyan-300" />}
                    </div>
                    <div>
                      <p className="text-base font-semibold text-white">
                        {isParsingGcode ? tc('uploadingGcode') : tc('gcodeDropTitle')}
                      </p>
                      <p className="mt-2 text-xs uppercase tracking-[0.16em] text-slate-400">{tc('supportedFormats')}</p>
                    </div>
                  </div>
                </label>

                {parseGcodeError && (
                  <div className="rounded-[1.25rem] border border-red-400/25 bg-red-500/10 px-4 py-3 text-sm text-red-100">
                    {parseGcodeError}
                  </div>
                )}
                {batchParseWarning && (
                  <div className="rounded-[1.25rem] border border-amber-400/25 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
                    {batchParseWarning}
                  </div>
                )}
              </WorkspacePanel>

              {hasParsedJobs ? (
                <div className="overflow-hidden rounded-[1.55rem] border border-cyan-400/20 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.14),transparent_42%),linear-gradient(145deg,rgba(15,23,42,0.96),rgba(2,6,23,0.92))] shadow-[0_28px_70px_-45px_rgba(34,211,238,0.55)]">
                  <div className="p-5 md:p-6">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusPill tone="success">
                          {isBatchMode
                            ? tc('batchJobsTitle').replace('{{count}}', String(batchSummary.jobCount))
                            : tc('singleJobTitle')}
                        </StatusPill>
                        <span className="text-xs text-slate-400">
                          {tc('batchStructure')
                            .replace('{{groups}}', String(objectGroupCount))
                            .replace('{{objects}}', String(batchSummary.physicalObjectCount))}
                        </span>
                      </div>
                      <span className="text-xs text-slate-500">{tc('perPlateControlHint')}</span>
                    </div>
                    <div className="mt-5 grid grid-cols-2 gap-3">
                      <BatchMetric
                        icon={<Boxes className="h-4 w-4" />}
                        label={tc('quoteQuantity')}
                        value={String(batchSummary.quoteQuantity)}
                        accent
                      />
                      <BatchMetric
                        icon={<Clock className="h-4 w-4" />}
                        label={tc('partyTime')}
                        value={formatHoursShort(batchSummary.partyPrintTimeSeconds / 3600, t('profilePage.calc.h'), t('profilePage.calc.min'))}
                        accent
                      />
                      <BatchMetric
                        icon={<Printer className="h-4 w-4" />}
                        label={tc('partyRuns')}
                        value={String(batchSummary.printRunCount)}
                      />
                      <BatchMetric
                        icon={<Layers3 className="h-4 w-4" />}
                        label={tc('partyMaterial')}
                        value={formatBatchWeight(batchSummary.partyWeightG)}
                      />
                    </div>
                  </div>
                </div>
              ) : null}

              <WorkspacePanel
                step="2"
                title={hasParsedJobs ? tc('orderCompositionTitle') : tc('workspaceMaterialTitle')}
              >
                {hasParsedJobs ? (
                  <div className={`grid grid-cols-1 gap-4 ${isBatchMode ? '2xl:grid-cols-2' : ''}`}>
                    {displayJobs.map((job, jobIndex) => {
                      const jobLines = materialLines.filter((line) => line.job_key === job.key);
                      const objectCount = Math.max(1, job.parsed.object_count ?? 1);
                      const objectGroups = job.parsed.object_groups ?? [];
                      const config = getJobConfig(job);
                      const canSplitGroups = canSplitCalculatorObjectGroups(objectGroups);
                      const quoteMode = config.quoteMode === 'groups'
                        && objectGroups.length > 1
                        && !canSplitGroups
                        ? 'set'
                        : config.quoteMode;
                      const outputPerRun = calculatorOutputQuantityPerRun(objectGroups, quoteMode);
                      const timeParts = splitSeconds(config.printTimeSeconds);
                      return (
                        <article
                          key={job.key}
                          className={`overflow-hidden rounded-[1.35rem] border bg-black/20 ${
                            job.key === activeParsedJobKey || (!activeParsedJobKey && jobIndex === 0)
                              ? 'border-cyan-400/25'
                              : 'border-white/10'
                          }`}
                        >
                          <div className="flex flex-col gap-4 p-4 sm:flex-row sm:items-start sm:justify-between">
                            <button
                              type="button"
                              onClick={() => onJobSelect(job.key)}
                              className="flex min-w-0 items-start gap-3 text-left"
                            >
                              {isBatchMode ? (
                                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/[0.05] text-xs font-semibold text-slate-300">
                                  {jobIndex + 1}
                                </span>
                              ) : null}
                              <span className="min-w-0">
                                <span className="block truncate text-sm font-semibold text-white">
                                  {quoteTitleFromFileName(job.parsed.file_name, tc('jobFallbackTitle'))}
                                </span>
                                <span className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-400">
                                  <span>{formatHoursShort(config.printTimeSeconds / 3600, t('profilePage.calc.h'), t('profilePage.calc.min'))}</span>
                                  <span>{formatBatchWeight(job.parsed.total_filament_weight_g ?? 0)}</span>
                                  <span>{tc('jobObjectCount').replace('{{count}}', String(objectCount))}</span>
                                  {job.parsed.plate_index != null ? (
                                    <span>{tc('parsedPlateOption').replace('{{index}}', String(job.parsed.plate_index))}</span>
                                  ) : null}
                                </span>
                              </span>
                            </button>

                            <label className="flex shrink-0 items-center justify-between gap-3 rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 py-2 sm:w-[10.5rem]">
                              <span>
                                <span className="block text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">{tc('plateRepeats')}</span>
                                <span className="mt-0.5 block text-[11px] text-slate-400">{tc('plateRepeatsShort')}</span>
                              </span>
                              <input
                                type="number"
                                min="1"
                                max="1000"
                                className={`${numberInputResetClass} w-14 rounded-lg border border-white/10 bg-slate-950/70 px-2 py-1.5 text-center text-base font-semibold text-white focus:outline-none focus:ring-2 focus:ring-cyan-400/50`}
                                value={config.repeats}
                                onChange={(event) => onJobConfigChange(job.key, {
                                  repeats: Math.max(1, Number(event.target.value) || 1),
                                })}
                              />
                            </label>
                          </div>

                          <div className="grid grid-cols-3 border-t border-white/[0.07] bg-white/[0.02]">
                            <JobFact label={tc('plateRunsTotal')} value={String(config.repeats)} />
                            <JobFact label={tc('plateObjectsTotal')} value={String(objectCount * config.repeats)} />
                            <JobFact label={tc('plateQuoteQuantity')} value={String(outputPerRun * config.repeats)} />
                          </div>

                          {objectCount > 1 ? (
                            <div className="border-t border-white/[0.07] p-4">
                              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                                <div>
                                  <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">{tc('jobObjects')}</p>
                                  <p className="mt-1 text-xs leading-5 text-slate-400">{tc('jobObjectsHint')}</p>
                                </div>
                                {objectGroups.length > 1 ? (
                                  <div className="inline-flex rounded-xl border border-white/[0.08] bg-black/20 p-1">
                                    <button
                                      type="button"
                                      aria-pressed={quoteMode === 'set'}
                                      onClick={() => onJobConfigChange(job.key, { quoteMode: 'set' })}
                                      className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${quoteMode === 'set' ? 'bg-white/10 text-white' : 'text-slate-400 hover:text-white'}`}
                                    >
                                      {tc('quoteAsSet')}
                                    </button>
                                    <button
                                      type="button"
                                      aria-pressed={quoteMode === 'groups'}
                                      disabled={!canSplitGroups}
                                      onClick={() => onJobConfigChange(job.key, { quoteMode: 'groups' })}
                                      className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${quoteMode === 'groups' ? 'bg-cyan-400/15 text-cyan-100' : 'text-slate-400 hover:text-white'} disabled:cursor-not-allowed disabled:opacity-35`}
                                    >
                                      {tc('quoteByGroups')}
                                    </button>
                                  </div>
                                ) : null}
                              </div>

                              {objectGroups.length > 0 ? (
                                <div className="mt-3 space-y-2">
                                  {objectGroups.map((group, groupIndex) => {
                                    const groupWeightG = (job.parsed.total_filament_weight_g ?? 0)
                                      * Math.max(0, group.extrusion_share ?? 0);
                                    const groupMaterialUsages = Object.entries(group.material_weights_g ?? {})
                                      .filter(([, weightG]) => weightG > 0)
                                      .map(([toolIndex, weightG]) => {
                                        const numericToolIndex = Number(toolIndex);
                                        const matchingLine = jobLines.find((line) => line.tool_index === numericToolIndex);
                                        const parsedMaterial = job.parsed.materials.find(
                                          (material) => material.tool_index === numericToolIndex,
                                        );
                                        return {
                                          toolIndex: numericToolIndex,
                                          label: matchingLine?.label
                                            || (parsedMaterial
                                              ? buildParsedMaterialLabel(parsedMaterial, `T${numericToolIndex}`)
                                              : `T${numericToolIndex}`),
                                          weightG,
                                        };
                                      });
                                    return (
                                      <div
                                        key={`${job.key}-${group.name}-${groupIndex}`}
                                        className="grid gap-3 rounded-xl border border-white/[0.07] bg-white/[0.035] px-3 py-2.5 sm:grid-cols-[minmax(0,1fr)_auto_auto] sm:items-center"
                                      >
                                        <div className="min-w-0">
                                          <p className="truncate text-sm font-medium text-slate-100">{group.name || tc('jobObjectFallback')}</p>
                                          {groupMaterialUsages.length > 0 ? (
                                            <div className="mt-1 flex flex-wrap gap-1.5">
                                              {groupMaterialUsages.map((usage) => (
                                                <span
                                                  key={`${job.key}-${group.name}-t${usage.toolIndex}`}
                                                  className="rounded-md border border-cyan-400/15 bg-cyan-400/[0.06] px-1.5 py-0.5 text-[10px] text-cyan-100/85"
                                                >
                                                  {usage.label} · {usage.weightG.toFixed(2)} {tc('grams')}
                                                </span>
                                              ))}
                                            </div>
                                          ) : groupWeightG > 0 ? (
                                            <p className="mt-0.5 text-[11px] text-slate-500">
                                              {tc('groupModelMaterialEstimate').replace('{{weight}}', groupWeightG.toFixed(2))}
                                            </p>
                                          ) : null}
                                        </div>
                                        <span className="text-xs text-slate-400">
                                          {tc('groupPerPlate').replace('{{count}}', String(group.count))}
                                        </span>
                                        <span className="rounded-lg border border-white/[0.08] bg-black/20 px-2.5 py-1 text-xs font-semibold text-white">
                                          {tc('groupPartyTotal').replace('{{count}}', String(group.count * config.repeats))}
                                        </span>
                                      </div>
                                    );
                                  })}
                                </div>
                              ) : (
                                <p className="mt-3 text-xs leading-5 text-amber-200/80">
                                  {tc('objectGroupsUnavailable').replace('{{count}}', String(objectCount))}
                                </p>
                              )}

                              {objectGroups.length > 1 && !canSplitGroups ? (
                                <p className="mt-3 text-xs leading-5 text-amber-200/80">{tc('groupSplitUnavailable')}</p>
                              ) : objectGroups.length > 1 ? (
                                <p className="mt-3 text-xs leading-5 text-slate-500">
                                  {quoteMode === 'groups' ? tc('groupSplitActiveHint') : tc('groupSetActiveHint')}
                                </p>
                              ) : null}
                            </div>
                          ) : null}

                          <details className="group/time border-t border-white/[0.07]">
                            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 marker:hidden">
                              <span className="text-xs text-slate-400">
                                {tc('plateTime')}: <strong className="font-medium text-slate-200">{formatHoursShort(config.printTimeSeconds / 3600, t('profilePage.calc.h'), t('profilePage.calc.min'))}</strong>
                              </span>
                              <span className="inline-flex items-center gap-1.5 text-xs font-medium text-cyan-200">
                                {tc('adjustPlateTime')}
                                <ChevronDown className="h-3.5 w-3.5 transition-transform group-open/time:rotate-180" />
                              </span>
                            </summary>
                            <div className="grid grid-cols-3 gap-3 border-t border-white/[0.06] px-4 py-4">
                              <FieldBlock label={t('profilePage.calc.hours')}>
                                <NumberInput
                                  value={timeParts.hours}
                                  onChange={(value) => onJobConfigChange(job.key, {
                                    printTimeSeconds: value * 3600 + timeParts.minutes * 60 + timeParts.seconds,
                                  })}
                                  min="0"
                                  placeholder="0"
                                />
                              </FieldBlock>
                              <FieldBlock label={t('profilePage.calc.minutes')}>
                                <NumberInput
                                  value={timeParts.minutes}
                                  onChange={(value) => onJobConfigChange(job.key, {
                                    printTimeSeconds: timeParts.hours * 3600 + Math.min(59, value) * 60 + timeParts.seconds,
                                  })}
                                  min="0"
                                  max="59"
                                  placeholder="0"
                                />
                              </FieldBlock>
                              <FieldBlock label={t('profilePage.calc.seconds')}>
                                <NumberInput
                                  value={timeParts.seconds}
                                  onChange={(value) => onJobConfigChange(job.key, {
                                    printTimeSeconds: timeParts.hours * 3600 + timeParts.minutes * 60 + Math.min(59, value),
                                  })}
                                  min="0"
                                  max="59"
                                  placeholder="0"
                                />
                              </FieldBlock>
                            </div>
                          </details>

                          <div className="border-t border-white/[0.07] p-4">
                            <p className="mb-3 text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">{tc('jobMaterials')}</p>
                            {jobLines.length > 0 ? (
                              <div className="space-y-3">{jobLines.map(renderMaterialLine)}</div>
                            ) : (
                              <p className="text-xs leading-5 text-slate-400">
                                {isFilamentsLoading || isSpoolsLoading ? tc('loadingMaterials') : tc('jobMaterialsUnavailable')}
                              </p>
                            )}
                          </div>
                        </article>
                      );
                    })}
                  </div>
                ) : (
                  <FieldBlock label={tc('selectMaterialSource')}>
                    <select
                      className={inputClass}
                      value={unifiedMaterialSelectionValue}
                      onChange={(event) => {
                        const value = event.target.value;
                        if (value.startsWith('spool:')) {
                          onSpoolSelect(Number(value.slice('spool:'.length)));
                          setSingleMaterialCostOpen(false);
                        } else if (value.startsWith('filament:')) {
                          onCatalogFilamentSelect(Number(value.slice('filament:'.length)));
                          setSingleMaterialCostOpen(false);
                        } else {
                          onSpoolSelect('');
                          onCatalogFilamentSelect('');
                          setSingleMaterialCostOpen(true);
                        }
                      }}
                    >
                      <option value="manual">{tc('materialManualOption')}</option>
                      <optgroup label={tc('chooseFromMyFilaments')}>
                        {spools.map((spool) => (
                          <option key={`spool-${spool.id}`} value={`spool:${spool.id}`}>
                            {buildSpoolLabel(spool)}
                          </option>
                        ))}
                      </optgroup>
                      <optgroup label={tc('chooseFromCatalog')}>
                        {filaments.map((filament) => (
                          <option key={`filament-${filament.id}`} value={`filament:${filament.id}`}>
                            {buildFilamentLabel(filament)}
                          </option>
                        ))}
                      </optgroup>
                    </select>
                  </FieldBlock>
                )}

                {!hasParsedJobs && autoMaterialMatch && materialMatchConfidenceLabel && (
                  <div className="rounded-[1.25rem] border border-emerald-400/25 bg-emerald-500/10 px-4 py-3 text-sm text-emerald-100">
                    <div className="flex items-center gap-2 font-semibold text-white">
                      <CheckCircle2 className="h-4 w-4 text-emerald-300" />
                      <span>{tc('materialAutoMatched')}</span>
                      <span className="rounded-full bg-emerald-400/15 px-2 py-0.5 text-xs text-emerald-200">
                        {materialMatchConfidenceLabel}
                      </span>
                    </div>
                    <p className="mt-1 text-xs leading-5 text-emerald-100/75">
                      {autoMaterialMatch.source === 'spool'
                        ? autoMaterialMatch.requiresSpoolChoice
                          ? tc('materialAutoMatchedSpoolChoiceHint')
                          : tc('materialAutoMatchedSpoolHint')
                        : tc('materialAutoMatchedCatalogHint')}
                    </p>
                  </div>
                )}

                {!hasParsedJobs ? (
                  <StatusPill tone={materialPriceSource === 'spool' ? 'success' : 'neutral'}>{materialSourceLabel}</StatusPill>
                ) : null}

                {!hasParsedJobs && selectedFilament && materialSummary && (
                  <div className="rounded-[1.25rem] border border-cyan-400/20 bg-cyan-400/10 px-4 py-3 text-sm text-cyan-100">
                    <span className="font-semibold text-white">{selectedFilament.name}</span>
                    <span className="mx-2 text-cyan-200/70">·</span>
                    {materialSummary}
                  </div>
                )}

                {spoolsLoadError && (
                  <div className="rounded-[1.25rem] border border-amber-400/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
                    {spoolsLoadError}
                  </div>
                )}

                {filamentsLoadError && (
                  <div className="rounded-[1.25rem] border border-amber-400/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
                    {filamentsLoadError}
                  </div>
                )}

                {isSpoolsLoading && (
                  <div className="rounded-[1.25rem] border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-300">
                    {tc('loadingSpools')}
                  </div>
                )}

                {isFilamentsLoading && (
                  <div className="rounded-[1.25rem] border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-300">
                    {tc('loadingMaterials')}
                  </div>
                )}

                {materialLinesError ? (
                  <div className="rounded-[1.25rem] border border-red-400/25 bg-red-500/10 px-4 py-3 text-sm text-red-100">
                    {materialLinesError}
                  </div>
                ) : null}

                {!hasParsedJobs ? (
                <div className="space-y-3">
                  <FieldBlock label={t('profilePage.calc.partWeight')}>
                    <InputWithSuffix
                      value={form.weightG}
                      onChange={(value) => onChange('weightG', value)}
                      placeholder="531"
                      suffix={tc('grams')}
                    />
                  </FieldBlock>
                  <div className="rounded-[1.25rem] border border-white/[0.08] bg-black/15 p-3">
                    <div className="flex min-h-10 flex-wrap items-center justify-between gap-3">
                      <div>
                        <p className="text-xs font-medium text-slate-200">{tc('materialCostBasis')}</p>
                        <p className="mt-1 text-xs text-slate-400">
                          {form.spoolPrice > 0
                            ? `${formatCurrency(form.spoolPrice)} · ${form.spoolWeightKg} ${tc('kg')}`
                            : tc('materialLineNeedsPrice')}
                        </p>
                      </div>
                      <button
                        type="button"
                        className="inline-flex items-center gap-1.5 text-xs font-medium text-cyan-200 transition-colors hover:text-white"
                        onClick={() => setSingleMaterialCostOpen((current) => !current)}
                      >
                        {singleMaterialCostOpen ? tc('hideMaterialCost') : tc('editMaterialCost')}
                        <ChevronDown className={`h-3.5 w-3.5 transition-transform ${singleMaterialCostOpen ? 'rotate-180' : ''}`} />
                      </button>
                    </div>
                    {singleMaterialCostOpen ? (
                      <div className="mt-3 grid grid-cols-1 gap-3 border-t border-white/[0.06] pt-3 sm:grid-cols-2">
                        <FieldBlock label={t('profilePage.calc.spoolPrice')}>
                          <InputWithSuffix
                            value={form.spoolPrice}
                            onChange={(value) => onChange('spoolPrice', value)}
                            placeholder="1200"
                            suffix={currencySymbol(quoteProfile.currency)}
                          />
                          {catalogPriceMismatch && (
                            <p className="mt-1 text-[11px] leading-snug text-amber-300/90">
                              {t('profilePage.calc.priceCurrencyMismatch')}
                              {catalogPriceMismatch.reference != null && (
                                <> {t('profilePage.calc.priceCurrencyMismatchRef', {
                                  price: Math.round(catalogPriceMismatch.reference),
                                  symbol: catalogPriceMismatch.brandSymbol,
                                })}</>
                              )}
                            </p>
                          )}
                        </FieldBlock>
                        <FieldBlock label={t('profilePage.calc.spoolWeight')}>
                          <InputWithSuffix
                            value={form.spoolWeightKg}
                            onChange={(value) => onChange('spoolWeightKg', value)}
                            placeholder="1"
                            suffix={tc('kg')}
                            step="0.1"
                          />
                        </FieldBlock>
                      </div>
                    ) : null}
                  </div>
                </div>
                ) : null}
              </WorkspacePanel>
            </div>

            {!hasParsedJobs ? (
              <WorkspacePanel
                step="3"
                title={tc('workspaceProductionTitle')}
              >
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
                  <FieldBlock label={t('profilePage.calc.quantity')}>
                    <NumberInput value={form.quantity} onChange={(value) => onChange('quantity', Math.max(1, value))} min="1" placeholder="1" />
                  </FieldBlock>
                  <FieldBlock label={t('profilePage.calc.hours')}>
                    <NumberInput value={form.timeHours} onChange={(value) => onChange('timeHours', value)} placeholder="0" />
                  </FieldBlock>
                <FieldBlock label={t('profilePage.calc.minutes')}>
                  <NumberInput value={form.timeMinutes} onChange={(value) => onChange('timeMinutes', value)} placeholder="0" />
                </FieldBlock>
                  <FieldBlock label={t('profilePage.calc.seconds')}>
                    <NumberInput value={form.timeSec} onChange={(value) => onChange('timeSec', value)} placeholder="0" />
                  </FieldBlock>
                </div>
              </WorkspacePanel>
            ) : null}

            {parsedGcode && (
              <details className="group rounded-[1.35rem] border border-white/[0.08] bg-black/15">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-4 marker:hidden">
                  <span>
                    <span className="block text-sm font-semibold text-slate-200">{tc('technicalDetailsTitle')}</span>
                    <span className="mt-1 block text-xs leading-5 text-slate-500">{tc('technicalDetailsHint')}</span>
                  </span>
                  <ChevronDown className="h-4 w-4 shrink-0 text-slate-400 transition-transform group-open:rotate-180" />
                </summary>
                <div className="space-y-4 border-t border-white/[0.07] p-4">
                  <div className="rounded-[1.3rem] border border-white/10 bg-white/5 p-4">
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-white">{parsedGcode.file_name}</p>
                        {parsedJobs.length > 1 ? (
                          <label className="mt-3 flex max-w-xs items-center gap-3 text-xs text-slate-300">
                            <span className="shrink-0">{tc('parsedJob')}</span>
                            <select
                              className={`${inputClass} py-2 text-sm`}
                              value={activeParsedJobKey ?? ''}
                              disabled={isParsingGcode}
                              onChange={(event) => onJobSelect(event.target.value)}
                            >
                              {parsedJobs.map((job) => (
                                <option key={job.key} value={job.key}>
                                  {job.parsed.file_name}
                                  {job.parsed.plate_index != null
                                    ? ` · ${tc('parsedPlateOption').replace('{{index}}', String(job.parsed.plate_index))}`
                                    : ''}
                                </option>
                              ))}
                            </select>
                          </label>
                        ) : null}
                        <div className="mt-3 flex flex-wrap gap-2">
                          <StatusPill tone="neutral">
                            {tc('parsedSlicer')}: {[parsedGcode.slicer_name, parsedGcode.slicer_version].filter(Boolean).join(' ') || tc('notDetected')}
                          </StatusPill>
                          <StatusPill tone="neutral">
                            {tc('fileSize')}: {formatFileSize(parsedGcode.file_size_bytes)}
                          </StatusPill>
                          {primaryParsedMaterial ? (
                            <StatusPill tone="neutral">
                              {tc('parsedMaterial')}: {buildParsedMaterialLabel(primaryParsedMaterial, tc('unknownMaterial'))}
                              {primaryParsedMaterial.weight_g != null ? ` · ${primaryParsedMaterial.weight_g.toFixed(2)} ${tc('grams')}` : ''}
                            </StatusPill>
                          ) : null}
                          {parsedNozzleSummary ? (
                            <StatusPill tone="neutral">
                              {tc('parsedNozzle')}: {parsedNozzleSummary}
                            </StatusPill>
                          ) : null}
                        </div>
                      </div>

                      {parsedGcode.thumbnail_data_url ? (
                        <div className="w-full max-w-[12rem] overflow-hidden rounded-[1rem] border border-white/10 bg-slate-950/60">
                          <img
                            src={parsedGcode.thumbnail_data_url}
                            alt={tc('parsedPreviewAlt')}
                            className="block h-auto w-full object-contain"
                          />
                        </div>
                      ) : null}
                    </div>
                  </div>

                  <div className={`grid grid-cols-1 gap-4 ${showParsedMaterialsSection ? 'lg:grid-cols-3' : 'lg:grid-cols-2'}`}>
                    <CompactSummarySection title={tc('parsedGroupPrint')}>
                      <CompactMetric
                        label={tc('parsedPrintTime')}
                        value={
                          parsedGcode.print_time_seconds != null
                            ? formatHoursShort(parsedGcode.print_time_seconds / 3600, t('profilePage.calc.h'), t('profilePage.calc.min'))
                            : '—'
                        }
                      />
                      <CompactMetric
                        label={tc('parsedWeight')}
                        value={
                          parsedGcode.total_filament_weight_g != null
                            ? `${parsedGcode.total_filament_weight_g.toFixed(2)} ${tc('grams')}`
                            : '—'
                        }
                      />
                      {parsedGcode.infill_filament_weight_g != null ? (
                        <CompactMetric
                          label={tc('parsedInfillWeight')}
                          value={`${parsedGcode.infill_filament_weight_g.toFixed(2)} ${tc('grams')}`}
                        />
                      ) : null}
                      {parsedGcode.support_filament_weight_g != null ? (
                        <CompactMetric
                          label={tc('parsedSupportWeight')}
                          value={`${parsedGcode.support_filament_weight_g.toFixed(2)} ${tc('grams')}`}
                        />
                      ) : null}
                      <CompactMetric
                        label={tc('parsedLength')}
                        value={
                          parsedGcode.total_filament_length_mm != null
                            ? `${(parsedGcode.total_filament_length_mm / 1000).toFixed(2)} m`
                            : '—'
                        }
                      />
                      <CompactMetric
                        label={tc('parsedVolume')}
                        value={
                          parsedGcode.total_filament_volume_cm3 != null
                            ? `${parsedGcode.total_filament_volume_cm3.toFixed(2)} cm³`
                            : '—'
                        }
                      />
                      <CompactMetric
                        label={tc('parsedLayers')}
                        value={parsedGcode.total_layers != null ? String(parsedGcode.total_layers) : '—'}
                      />
                      {parsedGcode.object_count != null ? (
                        <CompactMetric
                          label={tc('parsedObjectCount')}
                          value={String(parsedGcode.object_count)}
                        />
                      ) : null}
                      <CompactMetric
                        label={tc('parsedMaxHeight')}
                        value={parsedGcode.max_z_height_mm != null ? `${parsedGcode.max_z_height_mm} mm` : '—'}
                      />
                    </CompactSummarySection>

                    <CompactSummarySection title={tc('parsedGroupProcess')}>
                      <CompactMetric
                        label={tc('parsedLayerHeight')}
                        value={parsedGcode.layer_height_mm != null ? `${parsedGcode.layer_height_mm} mm` : '—'}
                      />
                      {parsedTemperaturesSummary ? (
                        <CompactMetric
                          label={tc('parsedTemperatures')}
                          value={parsedTemperaturesSummary}
                        />
                      ) : null}
                      <CompactMetric
                        label={tc('parsedInfill')}
                        value={
                          parsedGcode.sparse_infill_density_percent != null
                            ? `${parsedGcode.sparse_infill_density_percent}%${
                                parsedGcode.sparse_infill_pattern ? ` · ${parsedGcode.sparse_infill_pattern}` : ''
                              }`
                            : '—'
                        }
                      />
                      <CompactMetric label={tc('parsedSupports')} value={parsedSupportsSummary ?? '—'} />
                      <CompactMetric label={tc('parsedAdhesion')} value={parsedAdhesionSummary ?? '—'} />
                    </CompactSummarySection>

                    {showParsedMaterialsSection ? (
                      <CompactSummarySection title={tc('parsedGroupMaterials')}>
                        <CompactMetric
                          label={tc('parsedActiveMaterials')}
                          value={
                            parsedGcode.active_material_count != null
                              ? String(parsedGcode.active_material_count)
                              : parsedGcode.materials.length > 0
                                ? String(parsedGcode.materials.length)
                                : '—'
                          }
                        />
                        <CompactMetric
                          label={tc('parsedToolchanges')}
                          value={parsedGcode.toolchange_count != null ? String(parsedGcode.toolchange_count) : '—'}
                        />
                        <CompactMetric
                          label={tc('parsedMultiMaterial')}
                          value={
                            parsedGcode.is_multi_material == null
                              ? '—'
                              : parsedGcode.is_multi_material
                                ? tc('parsedYes')
                                : tc('parsedNo')
                          }
                        />

                        {parsedGcode.materials.length > 1 ? (
                          <div className="mt-4 flex flex-wrap gap-2">
                            {parsedGcode.materials.map((material, index) => (
                              <div
                                key={`${material.name ?? material.type ?? 'material'}-${index}`}
                                className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-2 text-xs text-cyan-100"
                              >
                                <span className="font-semibold text-white">
                                  {buildParsedMaterialLabel(material, tc('unknownMaterial'))}
                                </span>
                                {material.weight_g != null ? ` · ${material.weight_g.toFixed(2)} ${tc('grams')}` : ''}
                              </div>
                            ))}
                          </div>
                        ) : null}
                      </CompactSummarySection>
                    ) : null}
                  </div>
                </div>
              </details>
            )}
          </div>
        </SurfaceCard>

        <SurfaceCard className="p-5 md:p-6">
          <button
            type="button"
            onClick={() => setAdvancedSettingsOpen((prev) => !prev)}
            className="flex w-full flex-col gap-4 text-left md:flex-row md:items-start md:justify-between"
          >
            <div>
              <SectionHeading icon={<Settings2 className="h-5 w-5 text-cyan-300" />} title={tc('advancedInputsTitle')} compact />
            </div>
            <div className={`${ghostButtonClass} shrink-0 self-start`}>
              {advancedSettingsOpen ? tc('hideAdvancedInputs') : tc('showAdvancedInputs')}
              <ChevronDown className={`h-4 w-4 transition-transform ${advancedSettingsOpen ? 'rotate-180' : ''}`} />
            </div>
          </button>

          {advancedSettingsOpen ? (
            <div className="mt-5 space-y-5 border-t border-white/10 pt-5">
              <div>
                <p className="text-sm font-semibold text-white">{tc('advancedMaterialTitle')}</p>
                <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
                  <FieldBlock label={t('profilePage.calc.supportsWeight')} hint={t('profilePage.calc.supportsWeightHint')}>
                    <InputWithSuffix
                      value={form.supportsWeightG}
                      onChange={(value) => onChange('supportsWeightG', value)}
                      placeholder="0"
                      suffix={tc('grams')}
                    />
                  </FieldBlock>
                  <FieldBlock label={t('profilePage.calc.supportsLossCoeff')} hint={t('profilePage.calc.supportsLossHint')}>
                    <NumberInput
                      value={form.supportsLossCoefficient}
                      onChange={(value) => onChange('supportsLossCoefficient', value)}
                      min="1"
                      max="3"
                      step="0.1"
                      placeholder="1.2"
                    />
                  </FieldBlock>
                  <FieldBlock label={t('profilePage.calc.deliveryCost')}>
                    <InputWithSuffix
                      value={form.deliveryCost}
                      onChange={(value) => onChange('deliveryCost', value)}
                      placeholder="0"
                      suffix={currencySymbol(quoteProfile.currency)}
                    />
                  </FieldBlock>
                </div>
              </div>

              <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
                <div>
                  <p className="text-sm font-semibold text-white">{t('profilePage.calc.additionalServices')}</p>
                  <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
                    <FieldBlock label={t('profilePage.calc.modelingHours')}>
                      <NumberInput value={form.modelingHours} onChange={(value) => onChange('modelingHours', value)} placeholder="0" />
                    </FieldBlock>
                    <FieldBlock label={t('profilePage.calc.modelingMinutes')}>
                      <NumberInput value={form.modelingMinutes} onChange={(value) => onChange('modelingMinutes', value)} placeholder="0" />
                    </FieldBlock>
                    <FieldBlock label={t('profilePage.calc.postprocessingHours')}>
                      <NumberInput
                        value={form.postprocessingHours}
                        onChange={(value) => onChange('postprocessingHours', value)}
                        placeholder="0"
                      />
                    </FieldBlock>
                    <FieldBlock label={t('profilePage.calc.postprocessingMinutes')}>
                      <NumberInput
                        value={form.postprocessingMinutes}
                        onChange={(value) => onChange('postprocessingMinutes', value)}
                        placeholder="2"
                      />
                    </FieldBlock>
                  </div>
                  <div className="mt-3">
                    <p className="mb-2 text-xs font-medium text-slate-400">{tc('postprocessChecklistTitle')}</p>
                    <div className="flex flex-wrap gap-2">
                      {POSTPROCESS_OPERATIONS.map((op) => {
                        const checked = postprocessChecked[op.id] ?? false;
                        return (
                          <button
                            key={op.id}
                            type="button"
                            className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                              checked
                                ? 'border-cyan-400/40 bg-cyan-400/20 text-cyan-200'
                                : 'border-white/10 bg-white/5 text-slate-400 hover:border-white/20 hover:text-slate-300'
                            }`}
                            onClick={() => {
                              const next = !checked;
                              const updated = { ...postprocessChecked, [op.id]: next };
                              setPostprocessChecked(updated);
                              const totalMinutes = POSTPROCESS_OPERATIONS.reduce(
                                (sum, o) => sum + (updated[o.id] ? o.defaultMinutes : 0),
                                0,
                              );
                              onChange('postprocessingHours', Math.floor(totalMinutes / 60));
                              onChange('postprocessingMinutes', totalMinutes % 60);
                            }}
                          >
                            {tc(op.i18nKey)} · {op.defaultMinutes} {t('profilePage.calc.min')}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>

                <div>
                  <p className="text-sm font-semibold text-white">{t('profilePage.calc.adjustmentCoeffs')}</p>
                  <div className="mt-2 mb-3">
                    <p className="mb-2 text-xs font-medium text-slate-400">{tc('pricingPresetsTitle')}</p>
                    <div className="flex flex-wrap gap-2">
                      {[...BUILTIN_PRICING_PRESETS, ...customPresets].map((preset) => {
                        const isActive =
                          form.urgencyCoefficient === preset.urgencyCoefficient &&
                          form.complexityCoefficient === preset.complexityCoefficient &&
                          form.volumeDiscountCoefficient === preset.volumeDiscountCoefficient;
                        return (
                          <button
                            key={preset.name}
                            type="button"
                            className={`rounded-full border px-3 py-1 text-xs transition-colors ${
                              isActive
                                ? 'border-cyan-400/40 bg-cyan-400/20 text-cyan-200'
                                : 'border-white/10 bg-white/5 text-slate-400 hover:border-white/20 hover:text-slate-300'
                            }`}
                            onClick={() => {
                              onChange('urgencyCoefficient', preset.urgencyCoefficient);
                              onChange('complexityCoefficient', preset.complexityCoefficient);
                              onChange('volumeDiscountCoefficient', preset.volumeDiscountCoefficient);
                            }}
                          >
                            {preset.isBuiltin ? tc(`preset.${preset.name}`) : preset.name}
                          </button>
                        );
                      })}
                    </div>
                    <div className="mt-2 flex items-center gap-2">
                      <input
                        type="text"
                        value={presetNameInput}
                        onChange={(e) => setPresetNameInput(e.target.value)}
                        placeholder={tc('presetNamePlaceholder')}
                        className="h-7 w-36 rounded-lg border border-white/10 bg-white/5 px-2 text-xs text-white placeholder:text-slate-500 focus:border-cyan-400/40 focus:outline-none"
                      />
                      <button
                        type="button"
                        disabled={!presetNameInput.trim()}
                        className="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-slate-400 transition-colors hover:border-cyan-400/30 hover:text-cyan-300 disabled:opacity-40 disabled:cursor-not-allowed"
                        onClick={() => {
                          const name = presetNameInput.trim();
                          if (!name) return;
                          const newPreset: PricingPreset = {
                            name,
                            urgencyCoefficient: form.urgencyCoefficient,
                            complexityCoefficient: form.complexityCoefficient,
                            volumeDiscountCoefficient: form.volumeDiscountCoefficient,
                          };
                          const updated = [...customPresets.filter((p) => p.name !== name), newPreset];
                          setCustomPresets(updated);
                          saveCustomPricingPresets(updated);
                          setPresetNameInput('');
                        }}
                      >
                        {tc('presetSave')}
                      </button>
                      {customPresets.length > 0 ? (
                        <button
                          type="button"
                          className="rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-xs text-red-400 transition-colors hover:border-red-400/30"
                          onClick={() => {
                            const activeName = customPresets.find(
                              (p) =>
                                form.urgencyCoefficient === p.urgencyCoefficient &&
                                form.complexityCoefficient === p.complexityCoefficient &&
                                form.volumeDiscountCoefficient === p.volumeDiscountCoefficient,
                            )?.name;
                            if (activeName) {
                              const updated = customPresets.filter((p) => p.name !== activeName);
                              setCustomPresets(updated);
                              saveCustomPricingPresets(updated);
                            }
                          }}
                        >
                          {tc('presetDelete')}
                        </button>
                      ) : null}
                    </div>
                  </div>
                  <div className="mt-4 grid grid-cols-1 gap-4">
                    <FieldBlock label={t('profilePage.calc.urgency')} hint={t('profilePage.calc.urgencyHint')}>
                      <NumberInput
                        value={form.urgencyCoefficient}
                        onChange={(value) => onChange('urgencyCoefficient', value)}
                        min="1"
                        max="2"
                        step="0.1"
                        placeholder="1.0"
                      />
                    </FieldBlock>
                    <FieldBlock
                      label={t('profilePage.calc.complexity')}
                      hint={
                        parsedGcode && form.complexityCoefficient > 1.0
                          ? `${t('profilePage.calc.complexityHint')} · ${tc('autoFromGcode')}`
                          : t('profilePage.calc.complexityHint')
                      }
                    >
                      <NumberInput
                        value={form.complexityCoefficient}
                        onChange={(value) => onChange('complexityCoefficient', value)}
                        min="1"
                        max="3"
                        step="0.1"
                        placeholder="1.0"
                      />
                    </FieldBlock>
                    <FieldBlock label={t('profilePage.calc.volumeDiscount')} hint={t('profilePage.calc.volumeDiscountHint')}>
                      <NumberInput
                        value={form.volumeDiscountCoefficient}
                        onChange={(value) => onChange('volumeDiscountCoefficient', value)}
                        min="0.85"
                        max="1"
                        step="0.01"
                        placeholder="1.0"
                      />
                    </FieldBlock>
                  </div>
                </div>
              </div>
            </div>
          ) : null}
        </SurfaceCard>

        {estimateError && (
          <div className="rounded-[1.45rem] border border-red-400/25 bg-red-500/10 px-5 py-4 text-sm text-red-100">
            {t('profilePage.calc.error')}: {estimateError}
          </div>
        )}

      </div>

      <div className="xl:pt-1">
        <SurfaceCard className="p-5 md:p-6 xl:sticky xl:top-8">
          <div className="flex items-center justify-between gap-4">
            <SectionHeading icon={<Calculator className="h-5 w-5 text-cyan-300" />} title={tc('resultsTitle')} compact />
            <div className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-cyan-200">
              {result ? tc('lastEstimate') : tc('readyForEstimate')}
            </div>
          </div>

          <button
            type="button"
            onClick={onCalculate}
            disabled={isCalculating}
            className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-[1.6rem] bg-[linear-gradient(135deg,#0891b2,#7c3aed)] px-6 py-4 text-base font-semibold text-white shadow-[0_18px_35px_-18px_rgba(6,182,212,0.7)] transition-all hover:translate-y-[-1px] hover:shadow-[0_22px_42px_-18px_rgba(124,58,237,0.72)] disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isCalculating ? (
              <>
                <Loader2 className="h-5 w-5 animate-spin" />
                {t('profilePage.calc.calculating')}
              </>
            ) : (
              <>
                <Calculator className="h-5 w-5" />
                {t('profilePage.calc.calculate')}
              </>
            )}
          </button>

          {result ? (
            <>
              <div className="mt-6 overflow-hidden rounded-[1.7rem] border border-cyan-400/20 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.18),transparent_45%),linear-gradient(145deg,rgba(14,116,144,0.2),rgba(76,29,149,0.26))] p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-300">{tc('customerPriceTitle')}</p>
                <p className="mt-3 text-4xl font-bold tracking-tight text-white">{formatCurrency(result.cost_final || result.cost_total)}</p>
                <p className="mt-2 text-sm text-slate-300">
                  {hasParsedJobs ? (
                    <>
                      {tc('resultQuoteQuantity')}: <span className="text-white">{result.quantity}</span>
                      <span className="mx-2 text-slate-500">·</span>
                      {tc('partyRuns')}: <span className="text-white">{result.print_runs ?? batchSummary.printRunCount}</span>
                    </>
                  ) : (
                    <>{tc('perPart')}: <span className="text-white">{formatCurrency(result.cost_first_part)}</span></>
                  )}
                </p>
              </div>

              <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-3">
                <MetricTile label={tc('summaryCostOfGoods')} value={formatCurrency(result.cost_of_goods_sold)} />
                <MetricTile
                  label={tc('summaryProfit')}
                  value={
                    result.profit_margin_percent != null
                      ? `${formatCurrency(result.profit_margin)} · ${result.profit_margin_percent.toFixed(1)}%`
                      : formatCurrency(result.profit_margin)
                  }
                />
                <MetricTile
                  label={tc('summaryWorkTime')}
                  value={formatHoursShort(result.total_time_hours, t('profilePage.calc.h'), t('profilePage.calc.min'))}
                />
              </div>

              <div className="mt-6 space-y-4">
                <SectionPanel title={tc('resultsCostStructureTitle')}>
                  <MetricRow label={t('profilePage.calc.material')} value={formatCurrency(result.cost_material)} />
                  {result.material_line_costs?.length ? (
                    <div className="mx-3 mb-2 rounded-xl border border-white/[0.06] bg-black/15 px-3 py-2">
                      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                        {tc('materialCostBreakdown')}
                      </p>
                      <div className="space-y-1.5">
                        {result.material_line_costs.map((line) => (
                          <div key={line.line_id} className="flex items-start justify-between gap-3 text-xs">
                            <span className="min-w-0 text-slate-400">
                              {line.job_key && jobTitleByKey.has(line.job_key) ? (
                                <span className="mr-1.5 text-slate-500">{jobTitleByKey.get(line.job_key)} ·</span>
                              ) : null}
                              <span className="text-slate-200">{line.label || (line.tool_index != null ? `T${line.tool_index}` : tc('unknownMaterial'))}</span>
                              <span className="ml-1.5 whitespace-nowrap">{line.weight_g.toFixed(2)} {tc('grams')}</span>
                            </span>
                            <span className="shrink-0 font-medium text-white">{formatCurrency(line.cost)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                  <MetricRow label={t('profilePage.calc.electricityLabel')} value={formatCurrency(result.cost_electricity)} />
                  <MetricRow label={t('profilePage.calc.modeling')} value={formatCurrency(result.cost_modeling)} />
                  <MetricRow label={t('profilePage.calc.printing')} value={formatCurrency(result.cost_printing)} />
                  <MetricRow label={t('profilePage.calc.postprocessing')} value={formatCurrency(result.cost_postprocessing)} />
                  <MetricRow label={t('profilePage.calc.amortization')} value={formatCurrency(result.cost_amortization)} />
                  {result.cost_bed_prep > 0 ? (
                    <MetricRow label={t('profilePage.calc.bedPrep')} value={formatCurrency(result.cost_bed_prep)} />
                  ) : null}
                  {result.cost_tax > 0 ? (
                    <MetricRow label={t('profilePage.calc.taxAmount')} value={formatCurrency(result.cost_tax)} />
                  ) : null}
                </SectionPanel>

                <SectionPanel title={tc('resultsCommercialModelTitle')}>
                  <MetricRow label={t('profilePage.calc.directCosts')} value={formatCurrency(result.cost_direct)} />
                  <MetricRow label={t('profilePage.calc.overhead')} value={formatCurrency(result.cost_overhead)} />
                  <MetricRow label={t('profilePage.calc.costBeforeMarkup')} value={formatCurrency(result.cost_before_markup)} />
                  <MetricRow label={t('profilePage.calc.markup')} value={formatCurrency(result.cost_markup)} />
                </SectionPanel>

                <SectionPanel title={tc('resultsMarginTitle')}>
                  <MetricRow label={t('profilePage.calc.costOfGoods')} value={formatCurrency(result.cost_of_goods_sold)} />
                  <MetricRow
                    label={t('profilePage.calc.profitMargin')}
                    value={
                      result.profit_margin_percent != null
                        ? `${formatCurrency(result.profit_margin)} · ${result.profit_margin_percent.toFixed(2)}%`
                        : formatCurrency(result.profit_margin)
                    }
                  />
                  <MetricRow
                    label={t('profilePage.calc.totalWorkTime')}
                    value={formatHoursShort(result.total_time_hours, t('profilePage.calc.h'), t('profilePage.calc.min'))}
                  />
                </SectionPanel>

                <SectionPanel title={tc('resultsBatchTitle')}>
                  {hasParsedJobs ? (
                    <>
                      <MetricRow label={tc('resultQuoteQuantity')} value={String(result.quantity)} strong />
                      <MetricRow label={tc('partyRuns')} value={String(result.print_runs ?? batchSummary.printRunCount)} />
                    </>
                  ) : (
                    <>
                      <MetricRow label={t('profilePage.calc.firstPartPrice')} value={formatCurrency(result.cost_first_part)} strong />
                      <MetricRow label={t('profilePage.calc.subsequentPrice')} value={formatCurrency(result.cost_subsequent_parts)} />
                    </>
                  )}
                  <MetricRow
                    label={result.quantity > 1 ? t('profilePage.calc.totalCost') : t('profilePage.calc.total')}
                    value={formatCurrency(result.cost_total)}
                    strong
                  />
                </SectionPanel>
              </div>

              <div className="mt-6 space-y-3">
                <button
                  type="button"
                  onClick={onAddToQuote}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-cyan-400/20 bg-cyan-400/10 px-4 py-3 text-sm font-medium text-cyan-200 transition-all hover:bg-cyan-400/20 hover:text-white"
                >
                  <Plus className="h-4 w-4" />
                  {tc('addToQuote')}
                </button>
                <button
                  type="button"
                  onClick={onOpenQuote}
                  className={`${ghostButtonClass} w-full relative`}
                >
                  <FileText className="h-4 w-4" />
                  {tc('openQuoteBuilder')}
                  {quoteItemCount > 0 && (
                    <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-cyan-500 px-1.5 text-[10px] font-bold text-white">
                      {quoteItemCount}
                    </span>
                  )}
                </button>
                <button
                  type="button"
                  onClick={() => void onSaveToHistory()}
                  disabled={!canSaveHistory || isSavingHistory}
                  className={`${ghostButtonClass} w-full disabled:cursor-not-allowed disabled:opacity-60`}
                >
                  {isSavingHistory ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  {isSavingHistory ? tc('savingToHistory') : tc('saveToHistory')}
                </button>
              </div>
            </>
          ) : (
            <div className="mt-6 rounded-[1.6rem] border border-dashed border-white/12 bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.08),transparent_44%),linear-gradient(180deg,rgba(2,6,23,0.35),rgba(2,6,23,0.62))] px-5 py-8 text-left shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
              <div className="flex items-start gap-4">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-[1.1rem] border border-white/10 bg-white/5">
                  <CheckCircle2 className="h-6 w-6 text-cyan-300" />
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-white">{tc('resultsEmptyTitle')}</h3>
                  <p className="mt-2 text-sm leading-6 text-slate-300">{tc('resultsEmptyDescription')}</p>
                </div>
              </div>
            </div>
          )}
        </SurfaceCard>
      </div>
    </div>
  );
};

interface HistoryViewProps {
  entries: CalculatorHistoryEntry[];
  historyLoadError: string | null;
  isDeletingHistory: boolean;
  isLoading: boolean;
  total: number;
  onDeleteEntry: (entry: CalculatorHistoryEntry) => void;
  onRestoreEntry: (entry: CalculatorHistoryEntry) => void;
  formatCurrency: (value: number | null | undefined) => string;
}

const HistoryView: React.FC<HistoryViewProps> = ({
  entries,
  historyLoadError,
  isDeletingHistory,
  isLoading,
  total,
  onDeleteEntry,
  onRestoreEntry,
  formatCurrency,
}) => {
  const { t } = useTranslation();
  const tc = (key: string) => translateCalculator(t, key);

  return (
    <SurfaceCard className="p-6 md:p-7">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <SectionHeading icon={<Clock className="h-5 w-5 text-cyan-300" />} title={tc('historyTitle')} compact />
        <div className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-300">
          {total} {tc('historyEntriesCount')}
        </div>
      </div>

      {historyLoadError ? (
        <div className="mt-6 rounded-[1.25rem] border border-red-400/25 bg-red-500/10 px-4 py-3 text-sm text-red-100">
          {historyLoadError}
        </div>
      ) : null}

      {isLoading ? (
        <div className="mt-6 flex items-center justify-center rounded-[1.8rem] border border-white/10 bg-white/5 px-6 py-16">
          <div className="inline-flex items-center gap-3 text-sm text-slate-300">
            <Loader2 className="h-5 w-5 animate-spin text-cyan-300" />
            {tc('historyLoading')}
          </div>
        </div>
      ) : entries.length === 0 ? (
        <div className="mt-6 rounded-[1.8rem] border border-dashed border-white/12 bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.08),transparent_44%),linear-gradient(180deg,rgba(2,6,23,0.35),rgba(2,6,23,0.62))] px-6 py-16 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
          <div className="mx-auto flex h-[4.5rem] w-[4.5rem] items-center justify-center rounded-[1.6rem] border border-white/10 bg-white/5">
            <Clock className="h-9 w-9 text-slate-500" />
          </div>
          <h2 className="mt-6 text-2xl font-semibold text-white">{tc('noHistory')}</h2>
          <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-slate-300">{tc('noHistoryDescription')}</p>
        </div>
      ) : (
        <div className="mt-6 space-y-4">
          {entries.map((entry) => {
            const totalCost = entry.result_data.cost_final || entry.result_data.cost_total;
            const filamentLabel =
              entry.filament_snapshot != null
                ? [entry.filament_snapshot.brand_name, entry.filament_snapshot.name].filter(Boolean).join(' · ')
                : null;
            const gcodeFile = entry.parsed_gcode?.file_name ?? null;

            return (
              <div
                key={entry.id}
                className="rounded-[1.55rem] border border-white/10 bg-white/5 p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]"
              >
                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                  <div className="space-y-3">
                    <div>
                      <p className="text-lg font-semibold text-white">{entry.title}</p>
                      <p className="mt-1 text-sm text-slate-400">{formatHistoryDate(entry.created_at)}</p>
                    </div>

                    <div className="flex flex-wrap gap-2">
                      <HistoryTag label={tc('totalCost')} value={formatCurrency(totalCost)} />
                      <HistoryTag label={t('profilePage.calc.quantity')} value={String(entry.result_data.quantity)} />
                      <HistoryTag
                        label={tc('sourceLabel')}
                        value={entry.parsed_gcode ? tc('sourceGcode') : tc('sourceManual')}
                      />
                      {gcodeFile ? <HistoryTag label={tc('parsedFile')} value={gcodeFile} /> : null}
                      {filamentLabel ? <HistoryTag label={tc('materialLabel')} value={filamentLabel} /> : null}
                    </div>
                  </div>

                  <div className="flex flex-col gap-2 sm:flex-row">
                    <button
                      type="button"
                      onClick={() => onRestoreEntry(entry)}
                      className={ghostButtonClass}
                    >
                      <CheckCircle2 className="h-4 w-4" />
                      {tc('restoreHistoryEntry')}
                    </button>
                    <button
                      type="button"
                      onClick={() => void onDeleteEntry(entry)}
                      disabled={isDeletingHistory}
                      className="inline-flex items-center justify-center gap-2 rounded-2xl border border-red-400/25 bg-red-500/10 px-4 py-3 text-sm font-medium text-red-200 transition-all hover:bg-red-500/20 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {isDeletingHistory ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                      {tc('deleteHistoryEntry')}
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </SurfaceCard>
  );
};

interface QuoteModalProps {
  isOpen: boolean;
  source: 'manual' | 'gcode';
  quoteParties: QuotePartyFormState;
  result: CalculatorEstimateResponse | null;
  quoteItems: QuoteItem[];
  onRemoveFromQuote: (id: string) => void;
  onRenameQuoteItem: (id: string, title: string) => void;
  onClearQuoteItems: () => void;
  onClose: () => void;
  onPartyChange: <K extends keyof QuotePartyFormState>(field: K, value: QuotePartyFormState[K]) => void;
  onPrint: () => void;
  onShare: () => void;
  onDownloadPdf: () => void;
  isSharing: boolean;
  isPdfDownloading: boolean;
  isLoggedIn: boolean;
  formatCurrency: (value: number | null | undefined) => string;
}

const QuoteModal: React.FC<QuoteModalProps> = ({
  isOpen,
  source,
  quoteParties,
  result,
  quoteItems,
  onRemoveFromQuote,
  onRenameQuoteItem,
  onClearQuoteItems,
  onClose,
  onPartyChange,
  onPrint,
  onShare,
  onDownloadPdf,
  isSharing,
  isPdfDownloading,
  isLoggedIn,
  formatCurrency,
}) => {
  const { t } = useTranslation();
  const tc = (key: string) => translateCalculator(t, key);
  const isHeaderVisible = useHeaderVisible();

  if (!isOpen || (!result && quoteItems.length === 0)) {
    return null;
  }

  const hasItems = quoteItems.length > 0;
  const displayTotal = hasItems
    ? quoteItems.reduce((sum, qi) => sum + qi.lineItem.totalPrice, 0)
    : result?.cost_total ?? 0;

  return createPortal(
    <div
      className={`fixed inset-0 z-50 overflow-y-auto bg-slate-950/75 backdrop-blur-md ${isHeaderVisible ? 'pt-[88px]' : ''}`}
      onClick={(event) => {
        if (event.target === event.currentTarget) {
          onClose();
        }
      }}
    >
      <div className="flex min-h-full items-center justify-center p-4 md:p-6">
        <div
          className="w-full max-w-4xl overflow-hidden rounded-[2rem] border border-white/10 bg-[linear-gradient(180deg,rgba(15,23,42,0.95),rgba(15,23,42,0.9))] shadow-[0_40px_120px_-60px_rgba(15,23,42,1)]"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="flex items-center justify-between gap-4 border-b border-white/10 px-6 py-5 md:px-7">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-cyan-200">
                {source === 'gcode' ? tc('sourceGcode') : tc('sourceManual')}
              </div>
              <h2 className="mt-3 text-xl font-semibold text-white md:text-2xl">{tc('quoteBuilderTitle')}</h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300">{tc('quoteBuilderDescription')}</p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-11 w-11 items-center justify-center rounded-2xl border border-white/10 bg-white/5 text-slate-300 transition-all hover:bg-white/10 hover:text-white"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="grid grid-cols-1 gap-6 px-6 py-6 md:px-7 lg:grid-cols-[minmax(0,1.1fr)_minmax(20rem,0.9fr)]">
            <div className="space-y-6">
              <div className="rounded-[1.5rem] border border-white/10 bg-white/5 p-5">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-[1rem] border border-white/10 bg-white/5">
                    <Printer className="h-5 w-5 text-cyan-300" />
                  </div>
                  <div>
                    <p className="text-base font-semibold text-white">{tc('quoteSellerSection')}</p>
                    <p className="mt-1 text-sm text-slate-400">{tc('quoteSellerDescription')}</p>
                  </div>
                </div>

                <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
                  <FieldBlock label={tc('quoteSellerName')}>
                    <TextInput
                      value={quoteParties.sellerName}
                      onChange={(value) => onPartyChange('sellerName', value)}
                      placeholder={tc('quoteSellerNamePlaceholder')}
                    />
                  </FieldBlock>
                  <FieldBlock label={tc('quoteSellerInn')}>
                    <TextInput
                      value={quoteParties.sellerInn}
                      onChange={(value) => onPartyChange('sellerInn', value)}
                      placeholder="123456789012"
                    />
                  </FieldBlock>
                  <FieldBlock label={tc('quoteSellerPhone')}>
                    <TextInput
                      value={quoteParties.sellerPhone}
                      onChange={(value) => onPartyChange('sellerPhone', value)}
                      placeholder="+7 (999) 000-00-00"
                    />
                  </FieldBlock>
                  <FieldBlock label={tc('quoteValidityDays')} hint={tc('quoteValidityDaysHint')}>
                    <NumberInput
                      value={quoteParties.validityDays}
                      onChange={(value) => onPartyChange('validityDays', Math.max(1, value))}
                      min="1"
                      placeholder="14"
                    />
                  </FieldBlock>
                  <FieldBlock label={tc('quoteLegalStatus')} hint={tc('quoteDisclaimerHint')}>
                    <select
                      className={`${inputClass} w-full sm:max-w-[18rem]`}
                      value={quoteParties.disclaimerMode}
                      onChange={(event) => onPartyChange('disclaimerMode', event.target.value as QuoteDisclaimerMode)}
                    >
                      <option value="not_offer">{tc('quoteDisclaimerNotOffer')}</option>
                      <option value="offer">{tc('quoteDisclaimerOffer')}</option>
                    </select>
                  </FieldBlock>
                  <div className="md:col-span-2">
                    <FieldBlock label={tc('quotePaymentTerms')}>
                      <TextareaInput
                        value={quoteParties.paymentTerms}
                        onChange={(value) => onPartyChange('paymentTerms', value)}
                        placeholder={tc('quotePaymentTermsPlaceholder')}
                      />
                    </FieldBlock>
                  </div>
                </div>
              </div>

              <div className="rounded-[1.5rem] border border-white/10 bg-white/5 p-5">
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-[1rem] border border-white/10 bg-white/5">
                    <FileText className="h-5 w-5 text-cyan-300" />
                  </div>
                  <div>
                    <p className="text-base font-semibold text-white">{tc('quoteBuyerSection')}</p>
                    <p className="mt-1 text-sm text-slate-400">{tc('quoteBuyerDescription')}</p>
                  </div>
                </div>

                <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
                  <FieldBlock label={tc('quoteBuyerName')}>
                    <TextInput
                      value={quoteParties.buyerName}
                      onChange={(value) => onPartyChange('buyerName', value)}
                      placeholder={tc('quoteBuyerNamePlaceholder')}
                    />
                  </FieldBlock>
                  <FieldBlock label={tc('quoteBuyerInn')}>
                    <TextInput
                      value={quoteParties.buyerInn}
                      onChange={(value) => onPartyChange('buyerInn', value)}
                      placeholder="1234567890"
                    />
                  </FieldBlock>
                  <div className="md:col-span-2">
                    <FieldBlock label={tc('quoteBuyerAddress')}>
                      <TextareaInput
                        value={quoteParties.buyerAddress}
                        onChange={(value) => onPartyChange('buyerAddress', value)}
                        placeholder={tc('quoteBuyerAddressPlaceholder')}
                      />
                    </FieldBlock>
                  </div>
                </div>
              </div>
            </div>

            <div className="space-y-5">
              <div className="rounded-[1.5rem] border border-cyan-400/20 bg-cyan-400/10 p-5">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-200">{tc('quoteSummaryTitle')}</p>
                <p className="mt-3 text-3xl font-semibold tracking-tight text-white">{formatCurrency(displayTotal)}</p>
                <div className="mt-5 space-y-3 text-sm text-slate-200">
                  {hasItems && (
                    <div className="flex items-center justify-between gap-4">
                      <span className="text-slate-300">{tc('quoteItemsCount')}</span>
                      <span className="font-medium text-white">{quoteItems.length}</span>
                    </div>
                  )}
                  {!hasItems && result && (
                    <>
                      <div className="flex items-center justify-between gap-4">
                        <span className="text-slate-300">{t('profilePage.calc.quantity')}</span>
                        <span className="font-medium text-white">{result.quantity}</span>
                      </div>
                      <div className="flex items-center justify-between gap-4">
                        <span className="text-slate-300">{tc('perPart')}</span>
                        <span className="font-medium text-white">{formatCurrency(result.cost_first_part)}</span>
                      </div>
                    </>
                  )}
                  <div className="flex items-center justify-between gap-4">
                    <span className="text-slate-300">{tc('quoteValidUntil')}</span>
                    <span className="font-medium text-white">
                      {new Intl.DateTimeFormat(undefined, { dateStyle: 'medium' }).format(
                        addDays(new Date(), Math.max(1, Math.round(quoteParties.validityDays || DEFAULT_QUOTE_PROFILE.validityDays))),
                      )}
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <span className="text-slate-300">{tc('quoteLegalStatus')}</span>
                    <span className="text-right font-medium text-white">
                      {buildQuoteDisclaimerLabel(t, quoteParties.disclaimerMode || DEFAULT_QUOTE_PROFILE.disclaimerMode)}
                    </span>
                  </div>
                </div>
              </div>

              {hasItems && (
                <div className="rounded-[1.5rem] border border-white/10 bg-white/5 p-5">
                  <div className="flex items-center justify-between">
                    <p className="text-base font-semibold text-white">{tc('quoteItemsList')}</p>
                    <button
                      type="button"
                      onClick={onClearQuoteItems}
                      className="text-xs text-slate-400 transition-colors hover:text-red-400"
                    >
                      {tc('quoteClearAll')}
                    </button>
                  </div>
                  <ul className="mt-4 space-y-3">
                    {quoteItems.map((qi, idx) => (
                      <li key={qi.id} className="flex items-start justify-between gap-3 rounded-xl border border-white/5 bg-white/5 px-4 py-3">
                        <div className="min-w-0 flex-1">
                          <label className="flex items-center gap-2 text-xs text-slate-400">
                            <span className="shrink-0">{idx + 1}.</span>
                            <span className="sr-only">{tc('quoteItemName')}</span>
                            <input
                              value={qi.lineItem.title}
                              onChange={(event) => onRenameQuoteItem(qi.id, event.target.value)}
                              className="min-w-0 flex-1 rounded-xl border border-white/10 bg-slate-950/50 px-3 py-2 text-sm font-medium text-white outline-none transition focus:border-cyan-400/50 focus:ring-2 focus:ring-cyan-400/20"
                              placeholder={tc('quoteItemNamePlaceholder')}
                            />
                          </label>
                          {qi.lineItem.details.length > 0 && (
                            <p className="mt-1 truncate text-xs text-slate-400">{qi.lineItem.details.join(' · ')}</p>
                          )}
                          <p className="mt-1 text-xs text-slate-300">
                            {qi.lineItem.quantity} × {formatCurrency(qi.lineItem.unitPrice)} = {formatCurrency(qi.lineItem.totalPrice)}
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => onRemoveFromQuote(qi.id)}
                          className="mt-0.5 shrink-0 text-slate-500 transition-colors hover:text-red-400"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {!hasItems && (
                <div className="rounded-[1.5rem] border border-white/10 bg-white/5 p-5">
                  <p className="text-base font-semibold text-white">{tc('quotePreviewChecklist')}</p>
                  <ul className="mt-4 space-y-2 text-sm leading-6 text-slate-300">
                    <li>{tc('quoteChecklistLineItems')}</li>
                    <li>{tc('quoteChecklistCosts')}</li>
                    <li>{tc('quoteChecklistParties')}</li>
                    <li>{tc('quoteChecklistPrint')}</li>
                  </ul>
                </div>
              )}

              <div className="space-y-3">
                <button
                  type="button"
                  onClick={onPrint}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-[1.4rem] bg-[linear-gradient(135deg,#0891b2,#7c3aed)] px-5 py-4 text-sm font-semibold text-white shadow-[0_18px_35px_-18px_rgba(6,182,212,0.7)] transition-all hover:translate-y-[-1px] hover:shadow-[0_22px_42px_-18px_rgba(124,58,237,0.72)]"
                >
                  <FileText className="h-4 w-4" />
                  {tc('quotePrintAction')}
                </button>
                {isLoggedIn && (
                  <button
                    type="button"
                    onClick={onDownloadPdf}
                    disabled={isPdfDownloading}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-[1.4rem] border border-cyan-400/20 bg-cyan-400/10 px-5 py-4 text-sm font-semibold text-cyan-200 transition-all hover:bg-cyan-400/20 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isPdfDownloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudDownload className="h-4 w-4" />}
                    {tc('quoteDownloadPdfAction')}
                  </button>
                )}
                {isLoggedIn && (
                  <button
                    type="button"
                    onClick={onShare}
                    disabled={isSharing}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-[1.4rem] border border-cyan-400/20 bg-cyan-400/10 px-5 py-4 text-sm font-semibold text-cyan-200 transition-all hover:bg-cyan-400/20 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isSharing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Link2 className="h-4 w-4" />}
                    {tc('quoteShareAction')}
                  </button>
                )}
                <button
                  type="button"
                  onClick={onClose}
                  className={`${ghostButtonClass} w-full`}
                >
                  {tc('quoteClose')}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
};

const SurfaceCard: React.FC<{ children: ReactNode; className?: string }> = ({ children, className = '' }) => (
  <section className={`${surfaceClass} ${className}`}>
    <div className="pointer-events-none absolute inset-0 overflow-hidden rounded-[inherit]">
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.06),transparent_40%)]" />
    </div>
    <div className="relative">{children}</div>
  </section>
);

const HelpTooltip: React.FC<{ text: string }> = ({ text }) => (
  <span className="group/tooltip relative inline-flex shrink-0 align-middle">
    <button
      type="button"
      className="inline-flex h-4 w-4 items-center justify-center rounded-full text-slate-500 transition-colors hover:text-cyan-200 focus:outline-none focus:text-cyan-200"
      aria-label={text}
      title={text}
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
      }}
    >
      <HelpCircle className="h-3.5 w-3.5" />
    </button>
    <span
      role="tooltip"
      className="pointer-events-none absolute left-0 top-full z-[70] mt-2 hidden w-64 rounded-lg border border-white/10 bg-slate-950/95 px-3 py-2 text-left text-xs leading-relaxed text-slate-200 shadow-2xl shadow-black/30 group-hover/tooltip:block group-focus-within/tooltip:block"
    >
      {text}
    </span>
  </span>
);

const TooltipLabel: React.FC<{ label: string; tooltipText?: string }> = ({ label, tooltipText }) => (
  <span className="inline-flex items-center gap-1.5">
    <span>{label}</span>
    {tooltipText ? <HelpTooltip text={tooltipText} /> : null}
  </span>
);

const StepBadge: React.FC<{ step: string }> = ({ step }) => (
  <div className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-cyan-400/20 bg-cyan-400/10 text-xs font-semibold text-cyan-200">
    {step}
  </div>
);

const WorkspacePanel: React.FC<{
  step: string;
  title: string;
  description?: string;
  children: ReactNode;
}> = ({ step, title, description, children }) => (
  <div className="rounded-[1.55rem] border border-white/10 bg-white/5 p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
    <div className="flex items-start gap-3">
      <StepBadge step={step} />
      <div>
        <p className="text-base font-semibold text-white">{title}</p>
        {description ? <p className="mt-1 text-sm leading-6 text-slate-300">{description}</p> : null}
      </div>
    </div>
    <div className="mt-4 space-y-4">{children}</div>
  </div>
);

const StatusPill: React.FC<{ children: ReactNode; tone?: 'neutral' | 'success' | 'warning' }> = ({ children, tone = 'neutral' }) => (
  <div
    className={`rounded-full border px-3 py-1.5 text-xs font-medium ${
      tone === 'success'
        ? 'border-emerald-400/20 bg-emerald-500/10 text-emerald-100'
        : tone === 'warning'
          ? 'border-amber-400/20 bg-amber-500/10 text-amber-100'
          : 'border-white/10 bg-black/20 text-slate-300'
    }`}
  >
    {children}
  </div>
);

const SectionHeading: React.FC<{ icon: ReactNode; title: string; compact?: boolean }> = ({
  icon,
  title,
  compact = false,
}) => (
  <div className="flex items-center gap-3">
    <div
      className={`flex items-center justify-center rounded-[1.1rem] border border-white/10 bg-white/[0.06] ${
        compact ? 'h-10 w-10' : 'h-11 w-11'
      }`}
    >
      {icon}
    </div>
    <h2 className={`${compact ? 'text-lg' : 'text-xl'} font-semibold text-white`}>{title}</h2>
  </div>
);

const FieldBlock: React.FC<{ label: ReactNode; children: ReactNode; hint?: string | null }> = ({ label, children, hint }) => (
  <label className="flex h-full flex-col">
    <span className="mb-1.5 flex min-h-10 items-end text-sm font-medium leading-5 text-slate-300">{label}</span>
    <div>{children}</div>
    {hint ? <span className="mt-1.5 block text-xs leading-5 text-slate-400">{hint}</span> : null}
  </label>
);

const NumberInput: React.FC<{
  value: number;
  onChange: (value: number) => void;
  placeholder: string;
  min?: string;
  max?: string;
  step?: string;
}> = ({ value, onChange, placeholder, min, max, step }) => (
  <input
    type="number"
    className={compactNumericInputClass}
    value={value || ''}
    min={min}
    max={max}
    step={step}
    placeholder={placeholder}
    onChange={(event) => onChange(Number(event.target.value) || 0)}
  />
);

const TextInput: React.FC<{
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}> = ({ value, onChange, placeholder }) => (
  <input
    type="text"
    className={inputClass}
    value={value}
    placeholder={placeholder}
    onChange={(event) => onChange(event.target.value)}
  />
);

const TextareaInput: React.FC<{
  value: string;
  onChange: (value: string) => void;
  placeholder: string;
}> = ({ value, onChange, placeholder }) => (
  <textarea
    className={`${inputClass} min-h-28 resize-y`}
    value={value}
    placeholder={placeholder}
    onChange={(event) => onChange(event.target.value)}
  />
);

const InputWithSuffix: React.FC<{
  value: number;
  onChange: (value: number) => void;
  placeholder: string;
  suffix: string;
  step?: string;
}> = ({ value, onChange, placeholder, suffix, step }) => (
  <div className="flex w-full items-center gap-2 rounded-2xl border border-white/10 bg-slate-950/60 pr-3 transition-all focus-within:border-transparent focus-within:ring-2 focus-within:ring-cyan-400/60 sm:max-w-[15rem]">
    <input
      type="number"
      className={`${numberInputResetClass} w-full min-w-0 bg-transparent px-4 py-3 text-white placeholder:text-slate-500 focus:outline-none`}
      value={value || ''}
      placeholder={placeholder}
      step={step}
      onChange={(event) => onChange(Number(event.target.value) || 0)}
    />
    <span className="pointer-events-none shrink-0 rounded-xl border border-white/[0.08] bg-white/[0.06] px-2.5 py-1 text-xs font-medium text-slate-300">
      {suffix}
    </span>
  </div>
);

const MetricTile: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="rounded-[1.45rem] bg-white/[0.04] px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)] ring-1 ring-white/5">
    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">{label}</p>
    <p className="mt-2 text-2xl font-semibold tracking-tight text-white">{value}</p>
  </div>
);

const BatchMetric: React.FC<{
  icon: ReactNode;
  label: string;
  value: string;
  accent?: boolean;
}> = ({ icon, label, value, accent = false }) => (
  <div className={`rounded-[1.15rem] border px-3.5 py-3 ${
    accent
      ? 'border-cyan-400/20 bg-cyan-400/[0.08]'
      : 'border-white/[0.08] bg-white/[0.035]'
  }`}>
    <div className={`flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.14em] ${accent ? 'text-cyan-200' : 'text-slate-500'}`}>
      {icon}
      <span>{label}</span>
    </div>
    <p className={`mt-2 font-semibold tracking-tight text-white ${accent ? 'text-xl md:text-2xl' : 'text-lg'}`}>{value}</p>
  </div>
);

const JobFact: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="border-r border-white/[0.07] px-3 py-2.5 last:border-r-0">
    <p className="text-[9px] font-semibold uppercase tracking-[0.13em] text-slate-500">{label}</p>
    <p className="mt-1 text-sm font-semibold text-slate-100">{value}</p>
  </div>
);

const CompactSummarySection: React.FC<{ title: string; children: ReactNode }> = ({ title, children }) => (
  <div className="rounded-[1.3rem] border border-white/10 bg-white/5 p-4">
    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">{title}</p>
    <div className="mt-3 space-y-2">{children}</div>
  </div>
);

const CompactMetric: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="flex items-start justify-between gap-4 text-sm">
    <span className="text-slate-400">{label}</span>
    <span className="text-right font-medium text-white">{value}</span>
  </div>
);

const MetricRow: React.FC<{ label: string; value: string; strong?: boolean }> = ({ label, value, strong = false }) => (
  <div className="flex items-center justify-between gap-4 px-4 py-3 text-sm">
    <span className={strong ? 'font-medium text-slate-200' : 'text-slate-400'}>{label}</span>
    <span className={strong ? 'font-semibold text-white' : 'font-medium text-white'}>{value}</span>
  </div>
);

const SectionPanel: React.FC<{ title: string; children: ReactNode }> = ({ title, children }) => (
  <div className="overflow-hidden rounded-[1.45rem] border border-white/[0.08] bg-black/20">
    <div className="border-b border-white/10 px-4 py-3">
      <p className="text-sm font-semibold text-white">{title}</p>
    </div>
    <div className="divide-y divide-white/10">{children}</div>
  </div>
);

const TabButton: React.FC<{
  active: boolean;
  icon: ReactNode;
  label: string;
  onClick: () => void;
}> = ({ active, icon, label, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className={`inline-flex items-center gap-2 rounded-[1.1rem] px-4 py-2.5 text-sm font-medium transition-all ${
      active
        ? 'bg-white text-slate-950 shadow-[0_12px_28px_-18px_rgba(255,255,255,0.9)]'
        : 'text-slate-300 hover:bg-white/[0.08] hover:text-white'
    }`}
  >
    {icon}
    <span>{label}</span>
  </button>
);

const HistoryTag: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="rounded-full border border-white/10 bg-black/20 px-3 py-2 text-xs text-slate-300">
    <span className="text-slate-400">{label}: </span>
    <span className="font-medium text-white">{value}</span>
  </div>
);
