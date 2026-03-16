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
  ChevronDown,
  CheckCircle2,
  Clock,
  CloudDownload,
  CloudUpload,
  FileText,
  HelpCircle,
  Link2,
  Loader2,
  Printer,
  Save,
  Settings2,
  Trash2,
  Upload,
  Weight,
  X,
} from 'lucide-react';
import { calculatorAPI, filamentsAPI, spoolsAPI, type UserSpool } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { useHeaderVisible } from '../hooks/useHeaderVisible';
import { translateApiError } from '../utils/translateApiError';
import type {
  CalculatorEstimateRequest,
  CalculatorEstimateResponse,
  CalculatorGcodeParseResponse,
  CalculatorHistoryEntry,
  CalculatorHistoryEntryCreate,
  CalculatorHistoryFilamentSnapshot,
  CalculatorParsedMaterial,
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
type CurrencyCode = '₽' | '$' | '€';

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
    const raw = window.localStorage.getItem(PRICING_PRESETS_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as PricingPreset[]) : [];
  } catch {
    return [];
  }
};

const saveCustomPricingPresets = (presets: PricingPreset[]): void => {
  window.localStorage.setItem(PRICING_PRESETS_STORAGE_KEY, JSON.stringify(presets));
};

const CALCULATOR_DEFAULTS_STORAGE_KEY = 'filamenthub_calculator_defaults_v1';
const QUOTE_PROFILE_STORAGE_KEY = 'filamenthub_calculator_quote_profile_v1';
const CURRENCY_OPTIONS: CurrencyCode[] = ['₽', '$', '€'];

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
  currency: '₽',
  quoteNumberPrefix: 'КП',
};
const DEFAULT_QUOTE_PARTY_FORM: QuotePartyFormState = {
  ...DEFAULT_QUOTE_PROFILE,
  buyerName: '',
  buyerInn: '',
  buyerAddress: '',
};

const makeCurrencyFormatter = (symbol: CurrencyCode) =>
  (value: number | null | undefined): string =>
    value == null || !Number.isFinite(value) ? '—' : `${value.toFixed(2)} ${symbol}`;

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

const normalizeMaterialText = (value: string | null | undefined): string =>
  (value ?? '')
    .toLowerCase()
    .replace(/[\[\](){}"'`@.,;:/\\|+-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

const MATERIAL_NOISE_TOKENS = new Set([
  'generic',
  'system',
  'copy',
  'copied',
  'копировать',
  'копия',
  'filamenthub',
]);

const materialTokens = (value: string | null | undefined): string[] =>
  normalizeMaterialText(value)
    .split(' ')
    .map((token) => token.trim())
    .filter((token) => token.length > 1 && !MATERIAL_NOISE_TOKENS.has(token));

const countSharedTokens = (left: string[], right: string[]): number => {
  if (left.length === 0 || right.length === 0) {
    return 0;
  }

  const rightSet = new Set(right);
  return left.reduce((count, token) => count + (rightSet.has(token) ? 1 : 0), 0);
};

const scoreMaterialCandidate = (
  parsed: CalculatorParsedMaterial,
  candidate: {
    name: string | null | undefined;
    vendor: string | null | undefined;
    materialType: string | null | undefined;
    color: string | null | undefined;
  },
): number => {
  let score = 0;

  const parsedType = normalizeMaterialText(parsed.type);
  const candidateType = normalizeMaterialText(candidate.materialType);
  const parsedVendor = normalizeMaterialText(parsed.vendor);
  const candidateVendor = normalizeMaterialText(candidate.vendor);
  const parsedName = normalizeMaterialText(parsed.name);
  const candidateName = normalizeMaterialText(candidate.name);
  const parsedColor = normalizeMaterialText(parsed.color);
  const candidateColor = normalizeMaterialText(candidate.color);

  if (parsedType && candidateType) {
    if (parsedType === candidateType) {
      score += 6;
    } else {
      const sharedTypeTokens = countSharedTokens(materialTokens(parsed.type), materialTokens(candidate.materialType));
      score += Math.min(sharedTypeTokens * 2, 4);
    }
  }

  if (parsedVendor && candidateVendor) {
    if (parsedVendor === candidateVendor) {
      score += 4;
    } else {
      const sharedVendorTokens = countSharedTokens(materialTokens(parsed.vendor), materialTokens(candidate.vendor));
      score += Math.min(sharedVendorTokens * 2, 3);
    }
  }

  if (parsedName && candidateName) {
    if (parsedName === candidateName) {
      score += 8;
    } else if (parsedName.includes(candidateName) || candidateName.includes(parsedName)) {
      score += 6;
    } else {
      const sharedNameTokens = countSharedTokens(materialTokens(parsed.name), materialTokens(candidate.name));
      score += Math.min(sharedNameTokens * 2, 6);
    }
  }

  if (parsedColor && candidateColor && parsedColor === candidateColor) {
    score += 1;
  }

  return score;
};

const pickPrimaryParsedMaterial = (parsed: CalculatorGcodeParseResponse | null): CalculatorParsedMaterial | null => {
  if (!parsed) {
    return null;
  }

  if (parsed.active_material_count != null && parsed.active_material_count > 1) {
    return null;
  }

  const weightedMaterial =
    parsed.materials.find((material) => (material.weight_g ?? 0) > 0 || (material.length_mm ?? 0) > 0) ??
    parsed.materials[0];

  return weightedMaterial ?? null;
};

const findBestMatch = <T,>(
  items: T[],
  getScore: (item: T) => number,
): T | null => {
  const ranked = items
    .map((item) => ({ item, score: getScore(item) }))
    .filter((entry) => entry.score >= 8)
    .sort((left, right) => right.score - left.score);

  if (ranked.length === 0) {
    return null;
  }

  const [best, second] = ranked;
  if (second && best.score - second.score < 2) {
    return null;
  }

  return best.item;
};

const buildEstimateRequest = (form: CalculatorFormState): CalculatorEstimateRequest => {
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
    const raw = window.localStorage.getItem(QUOTE_PROFILE_STORAGE_KEY);
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
      currency: CURRENCY_OPTIONS.includes(parsed.currency) ? parsed.currency : undefined,
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

  window.localStorage.setItem(
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
    const raw = window.localStorage.getItem(CALCULATOR_DEFAULTS_STORAGE_KEY);
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

  window.localStorage.setItem(CALCULATOR_DEFAULTS_STORAGE_KEY, JSON.stringify(data));
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
): CalculatorHistoryEntryCreate => ({
  request_data: buildEstimateRequest(form),
  result_data: result,
  parsed_gcode: parsedGcode
    ? {
        ...parsedGcode,
        thumbnail_data_url: null,
      }
    : null,
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

interface BuildQuoteHtmlParams {
  t: TFunction;
  form: CalculatorFormState;
  result: CalculatorEstimateResponse;
  parsedGcode: CalculatorGcodeParseResponse | null;
  selectedFilament: MaterialSelectionSnapshot | null;
  parties: QuotePartyFormState;
  formatCurrency: (value: number | null | undefined) => string;
  quoteNumber?: string;
}

const buildQuoteLineItems = (
  t: TFunction,
  form: CalculatorFormState,
  result: CalculatorEstimateResponse,
  parsedGcode: CalculatorGcodeParseResponse | null,
  selectedFilament: MaterialSelectionSnapshot | null,
): QuoteLineItem[] => {
  const itemTitle = parsedGcode?.file_name || t('profilePage.calculator.quoteDefaultItemTitle');
  const details = [
    selectedFilament ? buildFilamentLabel(selectedFilament) : null,
    parsedGcode?.slicer_name ? `${t('profilePage.calculator.quoteSlicer')}: ${[parsedGcode.slicer_name, parsedGcode.slicer_version].filter(Boolean).join(' ')}` : null,
    form.weightG > 0 ? `${t('profilePage.calculator.quoteWeight')}: ${form.weightG.toFixed(2)} ${t('profilePage.calculator.grams')}` : null,
    toHours(form.timeHours, form.timeMinutes, form.timeSec) > 0
      ? `${t('profilePage.calculator.quotePrintTime')}: ${formatHoursShort(
          toHours(form.timeHours, form.timeMinutes, form.timeSec),
          t('profilePage.calc.h'),
          t('profilePage.calc.min'),
        )}`
      : null,
  ].filter(Boolean) as string[];

  const quantity = Math.max(1, result.quantity);
  const unitPrice = quantity > 0 ? result.cost_total / quantity : result.cost_total;

  return [
    {
      title: itemTitle,
      details,
      quantity,
      unitPrice,
      totalPrice: result.cost_total,
    },
  ];
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
  form,
  result,
  parsedGcode,
  selectedFilament,
  parties,
  formatCurrency,
  quoteNumber,
}: BuildQuoteHtmlParams): string => {
  const lineItems = buildQuoteLineItems(t, form, result, parsedGcode, selectedFilament);
  const includedItems = buildQuoteIncludedItems(t, result);
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

  const costBreakdownRows = [
    { label: t('profilePage.calc.material'), value: result.cost_material },
    { label: t('profilePage.calc.electricityLabel'), value: result.cost_electricity },
    { label: t('profilePage.calc.modeling'), value: result.cost_modeling },
    { label: t('profilePage.calc.printing'), value: result.cost_printing },
    { label: t('profilePage.calc.postprocessing'), value: result.cost_postprocessing },
    { label: t('profilePage.calc.amortization'), value: result.cost_amortization },
    ...(result.cost_bed_prep > 0 ? [{ label: t('profilePage.calc.bedPrep'), value: result.cost_bed_prep }] : []),
    ...(result.cost_tax > 0 ? [{ label: t('profilePage.calc.taxAmount'), value: result.cost_tax }] : []),
  ].filter((row) => row.value > 0);

  const breakdownRows = costBreakdownRows
    .map(
      (row) => `
          <tr>
            <td class="p-2 border border-gray-300 text-sm">${escapeHtml(row.label)}</td>
            <td class="p-2 border border-gray-300 text-sm text-right">${escapeHtml(formatCurrency(row.value))}</td>
          </tr>`,
    )
    .join('');

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
      .border-gray-300 { border-color: #d1d5db; }
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
      .breakdown { margin-bottom: 24px; }
      .breakdown-title { font-weight: 700; margin-bottom: 8px; font-size: 14px; }
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
            <td class="p-2 border border-gray-400 text-sm text-right">${escapeHtml(formatCurrency(result.cost_total))}</td>
          </tr>
        </tfoot>
      </table>

      ${costBreakdownRows.length > 0 ? `
      <div class="breakdown">
        <p class="breakdown-title">${escapeHtml(t('profilePage.calc.totalSums'))}:</p>
        <table>
          <tbody>
            ${breakdownRows}
            <tr class="total-row">
              <td class="p-2 border border-gray-300 text-sm">${escapeHtml(t('profilePage.calculator.totalCost'))}</td>
              <td class="p-2 border border-gray-300 text-sm text-right">${escapeHtml(formatCurrency(result.cost_total))}</td>
            </tr>
          </tbody>
        </table>
      </div>` : ''}

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
  const { t } = useTranslation();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const tc = (key: string) => translateCalculator(t, key);
  const [activeTab, setActiveTab] = useState<CalculatorTab>('calculator');
  const [form, setForm] = useState<CalculatorFormState>(DEFAULT_FORM_STATE);
  const [parsedGcode, setParsedGcode] = useState<CalculatorGcodeParseResponse | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [historyFeedback, setHistoryFeedback] = useState<{ kind: 'success' | 'error'; message: string } | null>(null);
  const [quoteModalOpen, setQuoteModalOpen] = useState(false);
  const [quoteProfile, setQuoteProfile] = useState<QuoteProfileState>(DEFAULT_QUOTE_PROFILE);
  const [quoteParties, setQuoteParties] = useState<QuotePartyFormState>(DEFAULT_QUOTE_PARTY_FORM);
  const [selectedSpoolId, setSelectedSpoolId] = useState<number | ''>('');
  const [isCloudBusy, setIsCloudBusy] = useState(false);
  const [isSharing, setIsSharing] = useState(false);
  const [isPdfDownloading, setIsPdfDownloading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const skipNextFilamentDefaultsRef = useRef(false);
  const lastAutoMatchedGcodeKeyRef = useRef<string | null>(null);
  const quoteSequenceRef = useRef(0);

  const formatCurrency = useMemo(
    () => makeCurrencyFormatter(quoteProfile.currency || '₽'),
    [quoteProfile.currency],
  );

  const filamentsQuery = useQuery({
    queryKey: ['calculator-pro', 'filaments'],
    queryFn: () =>
      filamentsAPI.list({
        active_only: true,
        size: 100,
      }),
    staleTime: 60_000,
  });

  const spoolsQuery = useQuery({
    queryKey: ['calculator-pro', 'spools'],
    queryFn: spoolsAPI.list,
    staleTime: 30_000,
  });

  const calculateMutation = useMutation({
    mutationFn: (data: CalculatorEstimateRequest) => calculatorAPI.estimate(data),
  });

  const parseGcodeMutation = useMutation({
    mutationFn: (file: File) => calculatorAPI.parseGcode(file),
  });

  const historyQuery = useQuery({
    queryKey: ['calculator-pro', 'history'],
    queryFn: () => calculatorAPI.listHistory({ page: 1, size: 50 }),
    staleTime: 30_000,
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

      const defaults = deriveUserSpoolDefaults(selectedSpool);

      setForm((prev) => ({
        ...prev,
        spoolPrice: defaults.spoolPrice ?? prev.spoolPrice,
        spoolWeightKg: defaults.spoolWeightKg ?? prev.spoolWeightKg,
      }));
      return;
    }

    if (!selectedCatalogFilament) {
      return;
    }

    if (skipNextFilamentDefaultsRef.current) {
      skipNextFilamentDefaultsRef.current = false;
      return;
    }

    const defaults = deriveCatalogFilamentDefaults(selectedCatalogFilament);

    setForm((prev) => ({
      ...prev,
      spoolPrice: defaults.spoolPrice ?? prev.spoolPrice,
      spoolWeightKg: defaults.spoolWeightKg ?? prev.spoolWeightKg,
    }));
  }, [selectedCatalogFilament, selectedSpool]);

  useEffect(() => {
    const stored = loadStoredQuoteProfile();
    const nextProfile: QuoteProfileState = {
      ...DEFAULT_QUOTE_PROFILE,
      ...stored,
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

  const summaryTotal = result ? result.cost_final || result.cost_total : null;
  const summaryTime = result?.total_time_hours ?? result?.time_hours ?? currentWorkTimeHours;

  const updateField = <K extends keyof CalculatorFormState>(field: K, value: CalculatorFormState[K]) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleSelectSpool = (spoolId: number | '') => {
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
    setSelectedSpoolId('');
    setForm((prev) => ({
      ...prev,
      selectedFilamentId: filamentId,
    }));
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
    calculateMutation.mutate(buildEstimateRequest(form));
  };

  const handleGcodeFile = async (file: File) => {
    const parsed = await parseGcodeMutation.mutateAsync(file);
    lastAutoMatchedGcodeKeyRef.current = null;
    setParsedGcode(parsed);
    setForm((prev) => applyParsedGcodeToForm(prev, parsed));
  };

  const handleFileSelection = async (files: FileList | null) => {
    const file = files?.[0];
    if (!file) {
      return;
    }

    await handleGcodeFile(file);
  };

  const handleSaveToHistory = async () => {
    if (!result) {
      return;
    }

    setHistoryFeedback(null);

    try {
      await saveHistoryMutation.mutateAsync(buildHistoryPayload(form, result, parsedGcode, selectedMaterial));
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
    skipNextFilamentDefaultsRef.current = true;
    setSelectedSpoolId('');
    lastAutoMatchedGcodeKeyRef.current = entry.parsed_gcode
      ? `${entry.parsed_gcode.file_name}:${entry.parsed_gcode.file_size_bytes}`
      : null;
    setForm(buildFormFromHistoryEntry(entry));
    setParsedGcode(entry.parsed_gcode ?? null);
    setActiveTab('calculator');
    setHistoryFeedback({ kind: 'success', message: tc('historyRestored') });
  };

  const handleDeleteHistory = async (entry: CalculatorHistoryEntry) => {
    if (!window.confirm(tc('historyDeleteConfirm'))) {
      return;
    }

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
    if (!result) {
      return;
    }

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

    const quoteHtml = buildQuoteDocumentHtml({
      t,
      form,
      result,
      parsedGcode,
      selectedFilament: selectedMaterial,
      parties: quoteParties,
      formatCurrency,
      quoteNumber,
    });

    quoteWindow.document.open();
    quoteWindow.document.write(quoteHtml);
    quoteWindow.document.close();
    quoteWindow.focus();
    setTimeout(() => {
      quoteWindow.print();
    }, 250);
  };

  const handleShareQuote = async () => {
    if (!result || !user) return;
    setIsSharing(true);
    try {
      quoteSequenceRef.current += 1;
      const prefix = quoteProfile.quoteNumberPrefix || 'КП';
      const seq = quoteSequenceRef.current;
      const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '');
      const quoteNumber = `${prefix}-${dateStr}-${String(seq).padStart(2, '0')}`;

      const quoteHtml = buildQuoteDocumentHtml({
        t,
        form,
        result,
        parsedGcode,
        selectedFilament: selectedMaterial,
        parties: quoteParties,
        formatCurrency,
        quoteNumber,
      });

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
    if (!result || !user) return;
    setIsPdfDownloading(true);
    try {
      quoteSequenceRef.current += 1;
      const prefix = quoteProfile.quoteNumberPrefix || 'КП';
      const seq = quoteSequenceRef.current;
      const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '');
      const quoteNumber = `${prefix}-${dateStr}-${String(seq).padStart(2, '0')}`;

      const quoteHtml = buildQuoteDocumentHtml({
        t,
        form,
        result,
        parsedGcode,
        selectedFilament: selectedMaterial,
        parties: quoteParties,
        formatCurrency,
        quoteNumber,
      });

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

  const handleOpenQuote = () => {
    setQuoteParties((prev) => ({
      ...prev,
      ...quoteProfile,
    }));
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
        currency: (CURRENCY_OPTIONS.includes(profile.currency as CurrencyCode) ? profile.currency : '₽') as CurrencyCode,
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
        currency: (CURRENCY_OPTIONS.includes(profile.currency as CurrencyCode) ? profile.currency : '₽') as CurrencyCode,
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
    const currentParsedKey = parsedGcode ? `${parsedGcode.file_name}:${parsedGcode.file_size_bytes}` : null;
    if (!parsedGcode || !currentParsedKey || lastAutoMatchedGcodeKeyRef.current === currentParsedKey) {
      return;
    }

    const primaryMaterial = pickPrimaryParsedMaterial(parsedGcode);
    lastAutoMatchedGcodeKeyRef.current = currentParsedKey;

    if (!primaryMaterial) {
      return;
    }

    const matchedSpool = findBestMatch(availableSpools, (spool) =>
      scoreMaterialCandidate(primaryMaterial, {
        name: spool.filament?.name,
        vendor: spool.filament?.brand_name,
        materialType: spool.filament?.material_type,
        color: spool.filament?.color_name,
      }),
    );

    if (matchedSpool) {
      setSelectedSpoolId(matchedSpool.id);
      setForm((prev) => ({
        ...prev,
        selectedFilamentId: matchedSpool.filament_id ?? prev.selectedFilamentId,
      }));
      return;
    }

    const matchedFilament = findBestMatch(filamentsQuery.data?.items ?? [], (filament) =>
      scoreMaterialCandidate(primaryMaterial, {
        name: filament.name,
        vendor: filament.brand_name,
        materialType: filament.material_type,
        color: filament.color_name,
      }),
    );

    if (matchedFilament) {
      setSelectedSpoolId('');
      setForm((prev) => ({
        ...prev,
        selectedFilamentId: matchedFilament.id,
      }));
    }
  }, [availableSpools, filamentsQuery.data?.items, parsedGcode]);

  return (
    <div className="space-y-6">
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
              <MetricTile label={t('profilePage.calc.quantity')} value={formatQuantity(form.quantity)} />
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
          parsedGcode={parsedGcode}
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
          onDragStateChange={setDragActive}
          quoteProfile={quoteProfile}
          onQuoteProfileChange={updateQuoteProfileField}
          onOpenQuote={handleOpenQuote}
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
  parsedGcode: CalculatorGcodeParseResponse | null;
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
  onDragStateChange: (active: boolean) => void;
  onOpenQuote: () => void;
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
  parsedGcode,
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
  onDragStateChange,
  onOpenQuote,
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

  const materialSourceLabel = selectedSpool
    ? tc('materialSourceSpool')
    : selectedFilament
      ? tc('materialSourceCatalog')
      : tc('materialSourceManual');
  const materialSummary =
    selectedSpool
      ? [
          selectedSpool.price != null ? formatCurrency(selectedSpool.price) : tc('materialPriceUnknown'),
          `${Math.round(selectedSpool.initial_weight_g)} ${tc('grams')}`,
          `${Math.round(selectedSpool.remaining_weight_g)} ${tc('grams')} ${tc('remainingShort')}`,
        ].join(' · ')
      : selectedCatalogFilament &&
          (selectedCatalogFilament.price_per_kg != null || selectedCatalogFilament.spool_weight != null)
        ? `${selectedCatalogFilament.price_per_kg != null ? `${selectedCatalogFilament.price_per_kg.toFixed(0)} ${quoteProfile.currency}/${tc('kg')}` : '—'} · ${
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
                    {`${t('profilePage.calc.printingRate')}: ${form.printingRatePerHour} ${quoteProfile.currency}/${tc('hourAbbr')} · ${t('profilePage.calc.taxRatePercent')}: ${form.taxRatePercent}% · ${t('profilePage.calc.roundTo')}: ${form.roundToNearest} ${quoteProfile.currency} · ${roundingModeLabel}`}
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
                      suffix={`${quoteProfile.currency}/${tc('kwhAbbr')}`}
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
                      suffix={`${quoteProfile.currency}/${tc('hourAbbr')}`}
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
                      suffix={`${quoteProfile.currency}/${tc('hourAbbr')}`}
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
                      suffix={`${quoteProfile.currency}/${tc('hourAbbr')}`}
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
                        ? `${tc('autoCalc')}: ${(form.printerPurchasePrice / form.printerUsefulHours).toFixed(2)} ${quoteProfile.currency}/${tc('hourAbbr')}`
                        : undefined
                    }
                  >
                    <InputWithSuffix
                      value={form.amortizationRatePerHour}
                      onChange={(value) => onStaticChange('amortizationRatePerHour', value)}
                      placeholder="16"
                      suffix={`${quoteProfile.currency}/${tc('hourAbbr')}`}
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
                      suffix={quoteProfile.currency}
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
                      suffix={quoteProfile.currency}
                    />
                  </FieldBlock>
                  <FieldBlock label={t('profilePage.calc.bedPrepCost')} hint={t('profilePage.calc.bedPrepCostHint')}>
                    <InputWithSuffix
                      value={form.bedPrepCostPerPrint}
                      onChange={(value) => onStaticChange('bedPrepCostPerPrint', value)}
                      placeholder="0"
                      suffix={quoteProfile.currency}
                    />
                  </FieldBlock>
                  <FieldBlock label={t('profilePage.calc.minOrderPrice')} hint={t('profilePage.calc.minOrderPriceHint')}>
                    <InputWithSuffix
                      value={form.minOrderPrice}
                      onChange={(value) => onStaticChange('minOrderPrice', value)}
                      placeholder="0"
                      suffix={quoteProfile.currency}
                    />
                  </FieldBlock>
                  <FieldBlock label={t('profilePage.calc.roundTo')}>
                    <InputWithSuffix
                      value={form.roundToNearest}
                      onChange={(value) => onStaticChange('roundToNearest', value)}
                      placeholder="10"
                      suffix={quoteProfile.currency}
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
                        <option key={c} value={c}>{c}</option>
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
              ref={fileInputRef}
              type="file"
              accept=".gcode,.txt,.gz"
              className="hidden"
              onChange={async (event) => {
                await onFileSelect(event.target.files);
                event.currentTarget.value = '';
              }}
            />

            <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
              <WorkspacePanel
                step="1"
                title={tc('workspaceSourceTitle')}
              >
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
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
                  className={`w-full cursor-pointer rounded-[1.5rem] border border-dashed p-6 text-left transition-all ${
                    dragActive
                      ? 'border-cyan-300/80 bg-cyan-400/12 shadow-[0_25px_50px_-35px_rgba(34,211,238,0.65)]'
                      : 'border-cyan-400/30 bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.14),transparent_52%),linear-gradient(180deg,rgba(15,23,42,0.8),rgba(2,6,23,0.85))] hover:border-cyan-300/50'
                  }`}
                >
                  <div className="flex items-start gap-4">
                    <div className="flex items-start gap-4">
                      <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-[1.1rem] border border-white/10 bg-white/5">
                        {isParsingGcode ? <Loader2 className="h-5 w-5 animate-spin text-cyan-300" /> : <Upload className="h-5 w-5 text-cyan-300" />}
                      </div>
                      <div>
                        <p className="text-base font-semibold text-white">
                          {isParsingGcode ? tc('uploadingGcode') : tc('gcodeDropTitle')}
                        </p>
                        <p className="mt-2 text-xs uppercase tracking-[0.16em] text-slate-400">{tc('supportedFormats')}</p>
                      </div>
                    </div>
                  </div>
                </button>

                {parseGcodeError && (
                  <div className="rounded-[1.25rem] border border-red-400/25 bg-red-500/10 px-4 py-3 text-sm text-red-100">
                    {parseGcodeError}
                  </div>
                )}
              </WorkspacePanel>

              <WorkspacePanel
                step="2"
                title={tc('workspaceMaterialTitle')}
              >
                <FieldBlock label={tc('selectSpool')}>
                  <select
                    className={inputClass}
                    value={selectedSpool?.id ?? ''}
                    onChange={(event) => onSpoolSelect(event.target.value ? Number(event.target.value) : '')}
                  >
                    <option value="">{tc('chooseFromMyFilaments')}</option>
                    {spools.map((spool) => (
                      <option key={spool.id} value={spool.id}>
                        {buildSpoolLabel(spool)}
                      </option>
                    ))}
                  </select>
                </FieldBlock>

                <FieldBlock label={tc('selectMaterial')}>
                  <select
                    className={inputClass}
                    value={form.selectedFilamentId}
                    onChange={(event) =>
                      onCatalogFilamentSelect(event.target.value ? Number(event.target.value) : '')
                    }
                  >
                    <option value="">{tc('chooseFromCatalog')}</option>
                    {filaments.map((filament) => (
                      <option key={filament.id} value={filament.id}>
                        {buildFilamentLabel(filament)}
                      </option>
                    ))}
                  </select>
                </FieldBlock>

                <StatusPill tone={selectedSpool ? 'success' : 'neutral'}>{materialSourceLabel}</StatusPill>

                {selectedFilament && materialSummary && (
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

                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  <FieldBlock label={t('profilePage.calc.partWeight')}>
                    <InputWithSuffix
                      value={form.weightG}
                      onChange={(value) => onChange('weightG', value)}
                      placeholder="531"
                      suffix={tc('grams')}
                    />
                  </FieldBlock>
                  <FieldBlock label={t('profilePage.calc.spoolPrice')}>
                    <InputWithSuffix
                      value={form.spoolPrice}
                      onChange={(value) => onChange('spoolPrice', value)}
                      placeholder="1200"
                      suffix={quoteProfile.currency}
                    />
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
              </WorkspacePanel>
            </div>

            <WorkspacePanel
              step="3"
              title={tc('workspaceProductionTitle')}
            >
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-5">
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

            {parsedGcode && (
              <WorkspacePanel
                step="4"
                title={tc('workspaceGcodeSummaryTitle')}
              >
                <div className="space-y-4">
                  <div className="rounded-[1.3rem] border border-white/10 bg-white/5 p-4">
                    <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                      <div className="min-w-0">
                        <p className="text-sm font-semibold text-white">{parsedGcode.file_name}</p>
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
                      <CompactMetric
                        label={tc('parsedLength')}
                        value={
                          parsedGcode.total_filament_length_mm != null
                            ? `${(parsedGcode.total_filament_length_mm / 1000).toFixed(2)} m`
                            : '—'
                        }
                      />
                      <CompactMetric
                        label={tc('parsedLayers')}
                        value={parsedGcode.total_layers != null ? String(parsedGcode.total_layers) : '—'}
                      />
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
              </WorkspacePanel>
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
                      suffix={quoteProfile.currency}
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
                  {tc('perPart')}: <span className="text-white">{formatCurrency(result.cost_first_part)}</span>
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
                  <MetricRow label={t('profilePage.calc.firstPartPrice')} value={formatCurrency(result.cost_first_part)} strong />
                  <MetricRow label={t('profilePage.calc.subsequentPrice')} value={formatCurrency(result.cost_subsequent_parts)} />
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
                  onClick={onOpenQuote}
                  className={`${ghostButtonClass} w-full`}
                >
                  <FileText className="h-4 w-4" />
                  {tc('openQuoteBuilder')}
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
  onDeleteEntry: (entry: CalculatorHistoryEntry) => Promise<void>;
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

  if (!isOpen || !result) {
    return null;
  }

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
                <p className="mt-3 text-3xl font-semibold tracking-tight text-white">{formatCurrency(result.cost_total)}</p>
                <div className="mt-5 space-y-3 text-sm text-slate-200">
                  <div className="flex items-center justify-between gap-4">
                    <span className="text-slate-300">{t('profilePage.calc.quantity')}</span>
                    <span className="font-medium text-white">{result.quantity}</span>
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <span className="text-slate-300">{tc('perPart')}</span>
                    <span className="font-medium text-white">{formatCurrency(result.cost_first_part)}</span>
                  </div>
                  <div className="flex items-center justify-between gap-4">
                    <span className="text-slate-300">{t('profilePage.calc.totalWorkTime')}</span>
                    <span className="font-medium text-white">
                      {formatHoursShort(result.total_time_hours ?? result.time_hours, t('profilePage.calc.h'), t('profilePage.calc.min'))}
                    </span>
                  </div>
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

              <div className="rounded-[1.5rem] border border-white/10 bg-white/5 p-5">
                <p className="text-base font-semibold text-white">{tc('quotePreviewChecklist')}</p>
                <ul className="mt-4 space-y-2 text-sm leading-6 text-slate-300">
                  <li>{tc('quoteChecklistLineItems')}</li>
                  <li>{tc('quoteChecklistCosts')}</li>
                  <li>{tc('quoteChecklistParties')}</li>
                  <li>{tc('quoteChecklistPrint')}</li>
                </ul>
              </div>

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

const StatusPill: React.FC<{ children: ReactNode; tone?: 'neutral' | 'success' }> = ({ children, tone = 'neutral' }) => (
  <div
    className={`rounded-full border px-3 py-1.5 text-xs font-medium ${
      tone === 'success'
        ? 'border-emerald-400/20 bg-emerald-500/10 text-emerald-100'
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
  <label className="block">
    <span className="mb-1.5 block text-sm font-medium text-slate-300">{label}</span>
    {children}
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
  <div className="relative w-full sm:max-w-[15rem]">
    <input
      type="number"
      className={`${inputClass} ${numberInputResetClass} w-full pr-24`}
      value={value || ''}
      placeholder={placeholder}
      step={step}
      onChange={(event) => onChange(Number(event.target.value) || 0)}
    />
    <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 rounded-xl border border-white/[0.08] bg-white/[0.06] px-2.5 py-1 text-xs font-medium text-slate-300">
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
