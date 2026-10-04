/**
 * Calculator Pro page wired to the current backend estimate API,
 * G-code parsing flow, and persisted calculation history.
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Calculator,
  BriefcaseBusiness,
  Boxes,
  AlertTriangle,
  ChevronDown,
  CheckCircle2,
  Check,
  Clock,
  CloudDownload,
  CloudUpload,
  FileText,
  HelpCircle,
  Link2,
  Layers3,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Settings2,
  Sparkles,
  Trash2,
  Upload,
  X,
} from 'lucide-react';
import {
  calculatorAPI,
  crmAPI,
  filamentsAPI,
  physicalPrintersAPI,
  spoolsAPI,
  type PhysicalPrinter,
  type PrinterEconomics,
  type UserSpool,
} from '../api/client';
import { SlicedJobsPanel } from '../components/calculator/SlicedJobsPanel';
import {
  PrinterCostRow,
} from '../components/calculator/PrinterCostRow';
import type { EconomicsReadinessEntry } from '../components/calculator/EconomicsReadinessPanel';
import { PrinterEconomicsColumn } from '../components/calculator/PrinterEconomicsColumn';
import { PowerPartsBreakdown } from '../components/calculator/PowerPartsBreakdown';
import { QuickPicks } from '../components/calculator/QuickPicks';
import { LayeredPrinterIcon } from '../components/icons/LayeredPrinterIcon';
import { Printer3DIcon } from '../components/icons/Printer3DIcon';
import {
  MaterialPreflightPanel,
  MaterialReadinessDetails,
  type MaterialPreflightUiLine,
} from '../components/calculator/MaterialPreflightPanel';
import { toast } from '../components/Toast';
import {
  isPluginEmbed,
  requestSliceParse,
  subscribeToPluginSliceParse,
  subscribeToPluginSliceProgress,
  type PluginSliceParseResult,
} from '../utils/pluginBridge';
import { deliverQuotePdf, QuotePdfSaveError } from '../utils/quotePdf';
import { ConfirmDeleteModal } from '../components/ConfirmDeleteModal';
import { ModalOverlay } from '../components/ModalOverlay';
import { QuotePdfPreview } from '../components/QuotePdfPreview';
import { useAuth } from '../contexts/AuthContext';
import { useHeaderVisible } from '../hooks/useHeaderVisible';
import { USER_PREFERENCES_QUERY_KEY } from '../hooks/useUserCurrency';
import { translateApiError } from '../utils/translateApiError';
import { createQuoteBreakdownHtml, createQuoteFooterHtml, createQuoteHeaderHtml, quoteDocumentLayoutCss, quoteDocumentTotalsCss, quoteFooterBaseCss, workBreakdownHtmlEntries } from '../utils/quoteDocumentPresentation';
import { QuoteDisclosureSettings } from '../components/QuoteDisclosureSettings';
import { InputWithSuffix, numberInputResetClass } from '../components/InputWithSuffix';
import {
  buildQuoteWorkBreakdown,
  getCompleteQuoteDisclosureSnapshot,
  isQuoteDisclosureBoundToLines,
  getSnapshotTaxDisclosure,
  removeEmbeddedTaxFromLines,
  replaceCustomerDeliveryLine,
  quoteLinesFingerprint,
  restoreQuoteBaseLines,
  sumQuotePositions,
  type QuoteDisclosureSnapshot,
  type QuoteWorkBreakdownEntry,
} from '../utils/quoteDisclosure';
import {
  currencySymbol,
  normalizeCurrency,
  roundingStepsForCurrency,
  currencyCodes,
  defaultCurrencyForCountry,
} from '../utils/currency';
import {
  findPrioritizedMaterialMatch,
  trustedIdentityResolution,
  pickPrimaryParsedMaterial,
  type MaterialMatchConfidence,
} from '../utils/calculatorMaterialMatcher';
import { allocateRoundedTotal, normalizeQuoteLineUnitPrice, quoteTitleFromFileName } from '../utils/calculatorQuote';
import {
  buildConfiguredCalculatorBatchSummary,
  calculatorOutputQuantityPerRun,
  canSplitCalculatorObjectGroups,
  type CalculatorQuoteMode,
} from '../utils/calculatorBatch';
import { safeStorage } from '../utils/storage';
import { quoteMarketRules, resolveQuoteMarket, QUOTE_MARKETS } from '../utils/quoteMarket';
import { CALCULATOR_DEFAULTS_STORAGE_KEY } from '../utils/calculatorDefaults';
import { normalizeFilamentColor, resolveMaterialDisplayColors } from '../utils/calculatorMaterialColors';
import { formatBytes } from '../utils/formatBytes';
import { buildGcodeExcerpt, GcodeExcerptError, type GcodeExcerpt } from '../utils/gcodeExcerpt';
import { buildGcodeToolpath } from '../utils/gcodeToolpathRunner';
import { calculatorHistoryKeys, shouldShowInitialHistoryError } from '../utils/calculatorHistoryQueries';
import {
  enqueueEconomicsSave,
  economicsReadinessResultNoteKey,
  isEconomicsFieldMissing,
  worstEconomicsReadinessStatus,
} from '../utils/economicsReadiness';
import type {
  CalculatorEstimateRequest,
  CalculatorEstimateResponse,
  CalculatorGcodeParseResponse,
  CalculatorHistoryEntry,
  CalculatorHistoryEntryCreate,
  CalculatorHistoryEntrySummary,
  CalculatorHistoryFilamentSnapshot,
  CalculatorMaterialLineRequest,
  CalculatorParsedMaterial,
  CalculatorPreflightRequest,
  CalculatorPreflightResponse,
  CalculatorProfileResponse,
  CalculatorProfileUpdate,
  CalculatorPrintJobRequest,
  CrmCustomer,
  EconomicsReadiness,
  Filament,
  OrcaSliceReport,
  PricingMethod,
  RoundingMode,
} from '../types/api';

const surfaceClass =
  'relative rounded-[2rem] border border-white/10 bg-[linear-gradient(180deg,rgba(15,23,42,0.88),rgba(15,23,42,0.72))] shadow-[0_30px_90px_-50px_rgba(15,23,42,0.95)] backdrop-blur-xl';
const inputClass =
  'w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-400/60 focus:border-transparent transition-all';
const compactNumericInputClass = `${inputClass} ${numberInputResetClass} w-full sm:max-w-[15rem]`;
const ghostButtonClass =
  'inline-flex items-center justify-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-medium text-white transition-all hover:bg-white/10';
const HISTORY_FEEDBACK_DISMISS_MS = 10_000;

type CalculatorTab = 'calculator' | 'history';
type QuoteDisclaimerMode = 'not_offer' | 'offer';
type CurrencyCode = string;

interface CalculatorPageProps {
  embedded?: boolean;
  activeTab?: CalculatorTab;
  onActiveTabChange?: (tab: CalculatorTab) => void;
  staticSettingsOpen?: boolean;
  quoteProfileOpen?: boolean;
  onStaticSettingsOpenChange?: (open: boolean) => void;
  onQuoteProfileOpenChange?: (open: boolean) => void;
}

interface QuoteProfileState {
  sellerName: string;
  sellerInn: string;
  sellerPhone: string;
  sellerRegistrationId: string;
  sellerTaxCode: string;
  sellerAddress: string;
  sellerBankDetails: string;
  quoteMarket: string;
  paymentTerms: string;
  validityDays: number;
  disclaimerMode: QuoteDisclaimerMode;
  currency: CurrencyCode;
  quoteNumberPrefix: string;
  customerDeliveryAmount: number;
  taxKind: 'tax' | 'vat';
  taxMode: 'hide' | 'included' | 'separate';
  showCostBreakdown: boolean;
  costBreakdownNote: string;
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
  scanningPrice: number;
  modelingHours: number;
  modelingMinutes: number;
  modelingRatePerHour: number;
  postprocessingHours: number;
  postprocessingMinutes: number;
  postprocessingRatePerHour: number;
  printingRatePerHour: number;
  amortizationRatePerHour: number;
  maintenanceCostPerHour: number;
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
  method: 'stable_id' | 'managed_preset' | 'attributes';
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

export interface ParsedJobState {
  key: string;
  parsed: CalculatorGcodeParseResponse;
  printerProfileId?: number | null;
}

type GcodeProcessingPhase = 'reading' | 'counting' | 'analyzing';

export interface GcodeProcessingProgress {
  phase: GcodeProcessingPhase;
  processedFiles: number;
  totalFiles: number;
  currentFileName: string | null;
  /** Share (0..1) of the current file already counted; only while `phase` is `counting`. */
  countedFraction?: number;
}

const GCODE_PHASE_LABEL_KEYS: Record<GcodeProcessingPhase, string> = {
  reading: 'gcodePhaseReading',
  counting: 'gcodePhaseCounting',
  analyzing: 'gcodePhaseAnalyzing',
};

// Each file passes through three steps: the summary is read, the parts are counted
// (the long one: every move of the file is walked), then the server analyzes it.
const COUNTING_STARTS_AT = 0.1;
const COUNTING_SHARE = 0.8;
const ANALYZING_STARTS_AT = COUNTING_STARTS_AT + COUNTING_SHARE;

export const getGcodeProcessingPercent = (
  progress: GcodeProcessingProgress | null,
): number | null => {
  if (!progress) return null;
  if (progress.totalFiles <= 0) return 0;
  const withinFile = progress.phase === 'analyzing'
    ? ANALYZING_STARTS_AT
    : progress.phase === 'counting'
      ? COUNTING_STARTS_AT + COUNTING_SHARE * Math.min(1, Math.max(0, progress.countedFraction ?? 0))
      : 0;
  const completed = progress.processedFiles + withinFile;
  return Math.min(100, Math.round((completed / progress.totalFiles) * 100));
};

export interface CalculatorJobConfig {
  jobKey: string;
  repeats: number;
  quoteMode: CalculatorQuoteMode;
  printTimeSeconds: number;
  /** Empty means the plate is charged at the order-wide machine rates. */
  physicalPrinterId: number | '';
}

const createDefaultJobConfig = (job: ParsedJobState): CalculatorJobConfig => ({
  jobKey: job.key,
  repeats: 1,
  quoteMode: (job.parsed.object_groups?.length ?? 0) === 1 ? 'groups' : 'set',
  printTimeSeconds: Math.max(0, job.parsed.print_time_seconds ?? 0),
  physicalPrinterId: '',
});

/** One match is a fact from the file; two or more machines on one preset is the person's call. */
export const singleSuggestedPrinterId = (job: ParsedJobState): number | '' => {
  const ids = job.parsed.suggested_physical_printer_ids ?? [];
  return ids.length === 1 ? ids[0] : '';
};

export const appendJobConfigs = (
  current: CalculatorJobConfig[],
  added: ParsedJobState[],
): CalculatorJobConfig[] => [...current, ...createJobConfigs(added, true)];

export const jobPrinterNote = (
  job: ParsedJobState,
  config: CalculatorJobConfig,
): 'several' | 'fromFile' | 'default' => {
  if (config.physicalPrinterId === '') {
    return (job.parsed.suggested_physical_printer_ids?.length ?? 0) > 1 ? 'several' : 'default';
  }
  return config.physicalPrinterId === singleSuggestedPrinterId(job) ? 'fromFile' : 'default';
};

const sortSuggestedPrintersFirst = (
  printers: PhysicalPrinter[],
  suggestedIds: number[],
): PhysicalPrinter[] => (suggestedIds.length === 0
  ? printers
  : [...printers].sort(
      (left, right) => Number(suggestedIds.includes(right.id)) - Number(suggestedIds.includes(left.id)),
    ));

// A lone plate has no machine of its own on screen: its printer is the order-wide one.
export const createJobConfigs = (
  jobs: ParsedJobState[],
  assignSuggestedPrinters: boolean,
): CalculatorJobConfig[] => jobs.map((job) => ({
  ...createDefaultJobConfig(job),
  physicalPrinterId: assignSuggestedPrinters ? singleSuggestedPrinterId(job) : '',
}));

interface CalculatorMaterialLineState extends CalculatorMaterialLineRequest {
  selectionValue: string;
  fileName: string;
  plateIndex: number | null;
  confidence: MaterialMatchConfidence | null;
  evidenceSource: 'gcode' | 'manual';
  lengthMm: number | null;
  volumeCm3: number | null;
  mappingSource: 'explicit' | 'automatic' | 'unresolved';
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
  scanningPrice: 0,
  modelingHours: 0,
  modelingMinutes: 0,
  modelingRatePerHour: 934,
  postprocessingHours: 0,
  postprocessingMinutes: 0,
  postprocessingRatePerHour: 100,
  printingRatePerHour: 170,
  amortizationRatePerHour: 16,
  maintenanceCostPerHour: 0,
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
  'maintenanceCostPerHour',
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

const STATIC_SETTING_API_KEYS: Record<CalculatorStaticSettingKey, keyof CalculatorProfileUpdate> = {
  electricityCostPerKwh: 'electricity_cost_per_kwh',
  printerPowerW: 'printer_power_w',
  powerHotendW: 'power_hotend_w',
  powerBedW: 'power_bed_w',
  powerSteppersW: 'power_steppers_w',
  powerElectronicsW: 'power_electronics_w',
  modelingRatePerHour: 'modeling_rate_per_hour',
  postprocessingRatePerHour: 'postprocessing_rate_per_hour',
  printingRatePerHour: 'printing_rate_per_hour',
  amortizationRatePerHour: 'amortization_rate_per_hour',
  maintenanceCostPerHour: 'maintenance_cost_per_hour',
  printerPurchasePrice: 'printer_purchase_price',
  printerUsefulHours: 'printer_useful_hours',
  overheadPercent: 'overhead_percent',
  markupPercent: 'markup_percent',
  taxRatePercent: 'tax_rate_percent',
  fixedCosts: 'fixed_costs',
  bedPrepCostPerPrint: 'bed_prep_cost_per_print',
  minOrderPrice: 'min_order_price',
  roundToNearest: 'round_to_nearest',
  roundingMode: 'rounding_mode',
};

export const calculatorProfilePatchForField = <K extends CalculatorStaticSettingKey>(
  field: K,
  value: CalculatorFormState[K],
): CalculatorProfileUpdate => ({
  [STATIC_SETTING_API_KEYS[field]]:
    field === 'printerUsefulHours' ? Math.round(value as number) : value,
} as CalculatorProfileUpdate);

export const mergeCalculatorProfilePatches = (
  current: CalculatorProfileUpdate,
  next: CalculatorProfileUpdate,
): CalculatorProfileUpdate => ({ ...current, ...next });

export const isLatestCalculatorProfileRequest = (
  requestSequence: number,
  latestSequence: number,
): boolean => requestSequence === latestSequence;

export const calculatorCurrencyFromProfile = (
  profile: Pick<CalculatorProfileResponse, 'currency'>,
): CurrencyCode => normalizeCurrency(profile.currency);

export const calculatorCurrencyAfterFailedSave = (
  visibleCurrency: CurrencyCode,
  confirmedCurrency: CurrencyCode,
  requestChangedCurrency: boolean,
  requestSequence: number,
  latestSequence: number,
): CurrencyCode => (
  requestChangedCurrency && isLatestCalculatorProfileRequest(requestSequence, latestSequence)
    ? confirmedCurrency
    : visibleCurrency
);

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


const QUOTE_PROFILE_STORAGE_KEY = 'filamenthub_calculator_quote_profile_v1';

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
  sellerRegistrationId: '',
  sellerTaxCode: '',
  sellerAddress: '',
  sellerBankDetails: '',
  quoteMarket: '',
  paymentTerms: '',
  validityDays: 14,
  disclaimerMode: 'not_offer',
  currency: 'RUB',
  quoteNumberPrefix: '',
  customerDeliveryAmount: 0,
  taxKind: 'tax',
  taxMode: 'included',
  showCostBreakdown: false,
  costBreakdownNote: '',
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

const filamentColorAlpha = (color: string, alpha: string): string => `${color}${alpha}`;

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

const resolveUserSpoolPriceCurrency = (spool: UserSpool): string | null => {
  if (spool.price != null) {
    // Prices created before per-spool currency was persisted were entered under
    // the old fixed RUB label. Keep that meaning instead of relabelling them.
    return normalizeCurrency(spool.currency || spool.extra?.currency || 'RUB');
  }
  return spool.filament?.currency ? normalizeCurrency(spool.filament.currency) : null;
};

const buildSpoolLabel = (spool: UserSpool): string => {
  if (!spool.filament) {
    return `#${spool.id}`;
  }

  return `${buildFilamentLabel(spool.filament)} · ${Math.round(spool.remaining_weight_g)} g`;
};

const resolveMaterialRoleWeights = (
  line: CalculatorMaterialLineRequest,
): NonNullable<CalculatorMaterialLineRequest['role_weights_g']> => {
  const roleWeights = { ...(line.role_weights_g ?? {}) };
  if (line.support_weight_g != null && roleWeights.support == null) {
    roleWeights.support = line.support_weight_g;
  }
  return roleWeights;
};

export const isMachineRateMissing = (
  economics: PrinterEconomics | null,
  accountMachineHourRate: number,
): boolean => {
  if (!economics) {
    return accountMachineHourRate <= 0;
  }
  const readinessMissing = isEconomicsFieldMissing(economics.readiness, 'machine_hour_rate');
  if (readinessMissing != null) {
    return readinessMissing;
  }
  const rateSource = economics.sources?.rate;
  return rateSource ? rateSource === 'none' : economics.effective_machine_hour_rate <= 0;
};

export const isJobMachineRateMissing = (
  config: CalculatorJobConfig,
  orderEconomics: PrinterEconomics | null,
  accountMachineHourRate: number,
  jobEconomics: Map<number, PrinterEconomics>,
): boolean => {
  const economics = config.physicalPrinterId === ''
    ? orderEconomics
    : jobEconomics.get(config.physicalPrinterId) ?? null;
  return isMachineRateMissing(economics, accountMachineHourRate);
};

export const buildEstimateRequest = (
  form: CalculatorFormState,
  materialLines: CalculatorMaterialLineState[] = [],
  parsedJobs: ParsedJobState[] = [],
  jobConfigs: CalculatorJobConfig[] = [],
  printerEconomics: PrinterEconomics | null = null,
  calculationCurrency: string | null = null,
  jobPrinterEconomics: Map<number, PrinterEconomics> = new Map(),
): CalculatorEstimateRequest => {
  const requestData: CalculatorEstimateRequest = {
    pricing_method: 'combined',
    quantity: form.quantity,
    round_to_nearest: form.roundToNearest || undefined,
    rounding_mode: form.roundingMode,
  };

  if (materialLines.length > 0) {
    requestData.material_lines = materialLines.map((line) => {
      const roleWeights = resolveMaterialRoleWeights(line);
      const hasRoleWeights = Object.keys(roleWeights).length > 0;
      return {
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
        density_g_cm3: line.density_g_cm3 != null && line.density_g_cm3 > 0
          ? line.density_g_cm3
          : null,
        abrasiveness: line.abrasiveness != null && line.abrasiveness >= 0.5
          ? line.abrasiveness
          : undefined,
        role_weights_g: hasRoleWeights ? roleWeights : undefined,
        role_weight_source: hasRoleWeights
          ? line.role_weight_source ?? line.support_weight_source
          : undefined,
      };
    });
  } else {
    if (form.weightG > 0) {
      requestData.weight_g = form.weightG;
    }
    requestData.supports_weight_g = form.supportsWeightG || undefined;
    requestData.supports_loss_coefficient = form.supportsLossCoefficient || undefined;
    requestData.spool_price = form.spoolPrice;
    requestData.spool_weight_kg = form.spoolWeightKg;
    requestData.delivery_cost = form.deliveryCost || undefined;
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
      const jobEconomics = config.physicalPrinterId === ''
        ? null
        : jobPrinterEconomics.get(config.physicalPrinterId) ?? null;
      const jobEconomicsUsable = Boolean(
        jobEconomics
        && (
          !jobEconomics.calculator_currency
          || !calculationCurrency
          || normalizeCurrency(jobEconomics.calculator_currency) === normalizeCurrency(calculationCurrency)
        ),
      );
      return {
        job_key: job.key,
        repeats: Math.max(1, Math.floor(config.repeats)),
        output_quantity_per_run: calculatorOutputQuantityPerRun(groups, quoteMode),
        print_time_seconds: Math.max(0, config.printTimeSeconds),
        quote_mode: quoteMode,
        ...(config.physicalPrinterId !== ''
          ? { physical_printer_id: config.physicalPrinterId }
          : {}),
        // The plate's own temperatures decide how hard this machine's heaters worked.
        bed_temperature_c: job.parsed.bed_temperature_other_layers_c ?? null,
        nozzle_temperature_c: job.parsed.nozzle_temperature_other_layers_c ?? null,
        ...(jobEconomicsUsable && jobEconomics
          ? {
              printing_rate_per_hour: jobEconomics.calculator_printing_rate_per_hour,
              amortization_rate_per_hour: jobEconomics.calculator_amortization_rate_per_hour,
              power_hotend_w: jobEconomics.power_hotend_w,
              power_bed_w: jobEconomics.power_bed_w,
              power_steppers_w: jobEconomics.power_steppers_w,
              power_electronics_w: jobEconomics.power_electronics_w,
              ...(jobEconomics.calculator_printer_power_w
                ? { printer_power_w: jobEconomics.calculator_printer_power_w }
                : {}),
            }
          : {}),
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

  requestData.electricity_cost_per_kwh = form.electricityCostPerKwh;
  if (form.printerPowerW > 0) {
    requestData.printer_power_w = form.printerPowerW;
    // Parts of the order-wide machine, used when a plate names no printer of its own.
    requestData.power_hotend_w = form.powerHotendW || null;
    requestData.power_bed_w = form.powerBedW || null;
    requestData.power_steppers_w = form.powerSteppersW || null;
    requestData.power_electronics_w = form.powerElectronicsW || null;
  }

  if (form.scanningPrice > 0) {
    requestData.scanning_price = form.scanningPrice;
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

  // The rate a person sets is the whole hour their customer pays for — the same meaning
  // it has for a chosen machine. Wear and power are billed as lines of their own, so only
  // what is left above them rides on the printing rate.
  if (form.printingRatePerHour) {
    const machineCostPerHour =
      (form.amortizationRatePerHour || 0)
      + ((form.printerPowerW || 0) / 1000) * (form.electricityCostPerKwh || 0);
    requestData.printing_rate_per_hour = Math.max(
      0,
      Math.round((form.printingRatePerHour - machineCostPerHour) * 100) / 100,
    );
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

  const printerCurrencyMatches =
    !printerEconomics?.calculator_currency
    || !calculationCurrency
    || normalizeCurrency(printerEconomics.calculator_currency) === normalizeCurrency(calculationCurrency);
  if (printerEconomics && printerCurrencyMatches) {
    requestData.printer_power_w = printerEconomics.calculator_printer_power_w || undefined;
    requestData.printing_rate_per_hour = printerEconomics.calculator_printing_rate_per_hour;
    requestData.amortization_rate_per_hour = printerEconomics.calculator_amortization_rate_per_hour;
  }

  return requestData;
};

export const buildPreflightRequest = (
  estimateRequest: CalculatorEstimateRequest,
  materialLines: CalculatorMaterialLineState[],
  selectedSpool: UserSpool | null,
  selectedCatalogFilament: Filament | null,
  spoolIdsByLine: Record<string, number[]>,
  safetyBufferPercent: number,
  parsedGcode: CalculatorGcodeParseResponse | null = null,
  manualAutoMatch: AutoMaterialMatchNotice | null = null,
  parsedJobs: ParsedJobState[] = [],
  physicalPrinterId: number | '' = '',
): CalculatorPreflightRequest | null => {
  const primaryParsedMaterial = pickPrimaryParsedMaterial(parsedGcode);
  const lines = materialLines.length > 0
    ? materialLines.map((line) => {
        const selectedIds = spoolIdsByLine[line.line_id]
          ?? (line.spool_id ? [line.spool_id] : []);
        const explicitPreflightSelection = Object.prototype.hasOwnProperty.call(
          spoolIdsByLine,
          line.line_id,
        );
        return {
          line_id: line.line_id,
          job_key: line.job_key,
          tool_index: line.tool_index,
          label: line.label,
          weight_g: line.weight_g,
          length_mm: line.lengthMm,
          volume_cm3: line.volumeCm3,
          filament_id: line.filament_id,
          spool_ids: selectedIds,
          evidence_source: line.evidenceSource,
          mapping_source: explicitPreflightSelection
            ? selectedIds.length > 0 ? 'explicit' as const : 'unresolved' as const
            : line.mappingSource,
          mapping_confidence: explicitPreflightSelection ? null : line.confidence,
        };
      })
    : estimateRequest.weight_g && estimateRequest.weight_g > 0
      ? [{
          line_id: 'manual',
          job_key: null,
          tool_index: null,
          label: null,
          weight_g: estimateRequest.weight_g
            + (estimateRequest.supports_weight_g ?? 0)
              * (estimateRequest.supports_loss_coefficient ?? 1.2),
          length_mm: primaryParsedMaterial?.length_mm ?? null,
          volume_cm3: primaryParsedMaterial?.volume_cm3 ?? null,
          filament_id: selectedSpool?.filament_id ?? selectedCatalogFilament?.id ?? null,
          spool_ids: spoolIdsByLine.manual
            ?? (selectedSpool ? [selectedSpool.id] : []),
          evidence_source: parsedGcode ? 'gcode' as const : 'manual' as const,
          mapping_source: Object.prototype.hasOwnProperty.call(spoolIdsByLine, 'manual')
            ? (spoolIdsByLine.manual?.length ?? 0) > 0 ? 'explicit' as const : 'unresolved' as const
            : manualAutoMatch
              ? 'automatic' as const
              : selectedSpool || selectedCatalogFilament
                ? 'explicit' as const
                : 'unresolved' as const,
          mapping_confidence: manualAutoMatch?.confidence ?? null,
        }]
      : [];

  if (lines.length === 0) return null;
  const machineJobs = parsedJobs.length > 0
    ? parsedJobs
    : parsedGcode
      ? [{ key: null, parsed: parsedGcode, printerProfileId: null }]
      : [];
  return {
    lines,
    print_jobs: estimateRequest.print_jobs ?? [],
    physical_printer_id: physicalPrinterId === '' ? null : physicalPrinterId,
    machine_evidence: machineJobs.map((job) => {
      const temperatures = [
        job.parsed.nozzle_temperature_first_layer_c,
        job.parsed.nozzle_temperature_other_layers_c,
      ].filter((value): value is number => value != null && value > 0);
      return {
        job_key: job.key,
        printer_profile_id: job.printerProfileId ?? null,
        printer_settings_id: job.parsed.printer_settings_id ?? null,
        nozzle_diameter_mm: job.parsed.nozzle_diameter_mm ?? null,
        max_nozzle_temperature_c: temperatures.length > 0 ? Math.max(...temperatures) : null,
        source: job.printerProfileId != null ? 'orca_plugin' as const : 'gcode' as const,
      };
    }),
    quantity: estimateRequest.quantity ?? 1,
    safety_buffer_percent: safetyBufferPercent,
  };
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

const findParsedMaterialForTool = (
  parsed: CalculatorGcodeParseResponse | null | undefined,
  toolIndex: number | null | undefined,
): CalculatorParsedMaterial | null => {
  if (!parsed) return null;
  if (toolIndex != null) {
    const exact = parsed.materials.find((material) => material.tool_index === toolIndex);
    if (exact) return exact;
  }
  return pickPrimaryParsedMaterial(parsed);
};

const parsedJobKey = (parsed: CalculatorGcodeParseResponse, uploadIndex: number): string =>
  `${uploadIndex}:${parsed.file_name}:${parsed.file_size_bytes}:${parsed.plate_index ?? 0}`;

// The plugin answers with one job per plate; a plugin that predates plates sends the first only.
export const pluginSliceJobs = (result: PluginSliceParseResult): CalculatorGcodeParseResponse[] => {
  const isJob = (value: unknown): value is CalculatorGcodeParseResponse =>
    typeof value === 'object' && value !== null;
  if (Array.isArray(result.jobs)) return result.jobs.filter(isJob);
  return isJob(result.parsed) ? [result.parsed] : [];
};

// The machine the slice was made for belongs to its own jobs, not to the whole order.
export const pluginSliceJobStates = (
  jobs: CalculatorGcodeParseResponse[],
  slice: Pick<OrcaSliceReport, 'physical_printer_id' | 'printer_profile_id'>,
): ParsedJobState[] => jobs.map((parsed) => ({
  key: parsedJobKey(parsed, 0),
  parsed: slice.physical_printer_id
    ? { ...parsed, suggested_physical_printer_ids: [slice.physical_printer_id] }
    : parsed,
  printerProfileId: slice.printer_profile_id ?? null,
}));

// Long enough to outlast the plugin's own upload timeout; the plugin reports progress while it
// reads, so only a read that has stopped answering reaches it.
const SLICE_PARSE_STALL_MS = 3 * 60 * 1000;

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

    const stored: Partial<QuoteProfileState> = {
      sellerName: typeof parsed.sellerName === 'string' ? parsed.sellerName : undefined,
      sellerInn: typeof parsed.sellerInn === 'string' ? parsed.sellerInn : undefined,
      sellerPhone: typeof parsed.sellerPhone === 'string' ? parsed.sellerPhone : undefined,
      sellerRegistrationId: typeof parsed.sellerRegistrationId === 'string' ? parsed.sellerRegistrationId : undefined,
      sellerTaxCode: typeof parsed.sellerTaxCode === 'string' ? parsed.sellerTaxCode : undefined,
      sellerAddress: typeof parsed.sellerAddress === 'string' ? parsed.sellerAddress : undefined,
      sellerBankDetails: typeof parsed.sellerBankDetails === 'string' ? parsed.sellerBankDetails : undefined,
      quoteMarket: typeof parsed.quoteMarket === 'string' ? parsed.quoteMarket : undefined,
      paymentTerms: typeof parsed.paymentTerms === 'string' ? parsed.paymentTerms : undefined,
      validityDays:
        typeof parsed.validityDays === 'number' && Number.isFinite(parsed.validityDays)
          ? parsed.validityDays
          : undefined,
      disclaimerMode: 'not_offer',
      currency: parsed.currency ? normalizeCurrency(parsed.currency) : undefined,
      quoteNumberPrefix: typeof parsed.quoteNumberPrefix === 'string' ? parsed.quoteNumberPrefix : undefined,
      customerDeliveryAmount: typeof parsed.customerDeliveryAmount === 'number' ? Math.max(0, parsed.customerDeliveryAmount) : undefined,
      taxKind: parsed.taxKind === 'vat' ? 'vat' : parsed.taxKind === 'tax' ? 'tax' : undefined,
      taxMode: parsed.taxMode === 'hide' || parsed.taxMode === 'included' || parsed.taxMode === 'separate' ? parsed.taxMode : undefined,
      showCostBreakdown: typeof parsed.showCostBreakdown === 'boolean' ? parsed.showCostBreakdown : undefined,
      costBreakdownNote: typeof parsed.costBreakdownNote === 'string' ? parsed.costBreakdownNote : undefined,
    };
    // An absent key must not override the default with undefined when spread over it.
    return Object.fromEntries(
      Object.entries(stored).filter(([, value]) => value !== undefined),
    ) as Partial<QuoteProfileState>;
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
      sellerRegistrationId: data.sellerRegistrationId,
      sellerTaxCode: data.sellerTaxCode,
      sellerAddress: data.sellerAddress,
      sellerBankDetails: data.sellerBankDetails,
      quoteMarket: data.quoteMarket,
      paymentTerms: data.paymentTerms,
      validityDays: data.validityDays,
      disclaimerMode: data.disclaimerMode,
      currency: data.currency,
      quoteNumberPrefix: data.quoteNumberPrefix,
      customerDeliveryAmount: data.customerDeliveryAmount,
      taxKind: data.taxKind,
      taxMode: data.taxMode,
      showCostBreakdown: data.showCostBreakdown,
      costBreakdownNote: data.costBreakdownNote,
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
  maintenanceCostPerHour: form.maintenanceCostPerHour,
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

const profileToStaticSettings = (
  profile: CalculatorProfileResponse,
): CalculatorStaticSettings => ({
  electricityCostPerKwh: profile.electricity_cost_per_kwh,
  printerPowerW: profile.printer_power_w,
  powerHotendW: profile.power_hotend_w,
  powerBedW: profile.power_bed_w,
  powerSteppersW: profile.power_steppers_w,
  powerElectronicsW: profile.power_electronics_w,
  modelingRatePerHour: profile.modeling_rate_per_hour,
  postprocessingRatePerHour: profile.postprocessing_rate_per_hour,
  printingRatePerHour: profile.printing_rate_per_hour,
  amortizationRatePerHour: profile.amortization_rate_per_hour,
  maintenanceCostPerHour: profile.maintenance_cost_per_hour,
  printerPurchasePrice: profile.printer_purchase_price,
  printerUsefulHours: profile.printer_useful_hours,
  overheadPercent: profile.overhead_percent,
  markupPercent: profile.markup_percent,
  taxRatePercent: profile.tax_rate_percent,
  fixedCosts: profile.fixed_costs,
  bedPrepCostPerPrint: profile.bed_prep_cost_per_print,
  minOrderPrice: profile.min_order_price,
  roundToNearest: profile.round_to_nearest,
  roundingMode: profile.rounding_mode as RoundingMode,
});

export const reconcileCalculatorProfileForm = (
  current: CalculatorFormState,
  profile: CalculatorProfileResponse,
): CalculatorFormState => ({
  ...current,
  ...profileToStaticSettings(profile),
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
      maintenanceCostPerHour: numberOrFallback(parsed.maintenanceCostPerHour, fallback.maintenanceCostPerHour),
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

const translateCalculator = (t: TFunction, key: string): string =>
  t(`profilePage.calculator.${key}`);

const ALL_GCODE_FILES_FAILED = 'all_gcode_files_failed';

const isAbortError = (error: unknown): boolean => {
  const candidate = error as { code?: string; message?: string; name?: string };
  return candidate.code === 'ERR_CANCELED'
    || candidate.message === 'canceled'
    || candidate.name === 'AbortError';
};

const apiErrorCode = (error: unknown): string | null => {
  const detail = (error as { response?: { data?: { detail?: unknown } } })
    .response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail && typeof detail === 'object' && 'code' in detail) {
    return String((detail as { code: unknown }).code);
  }
  return null;
};

export const isCurrentGcodeOperation = (
  operationToken: number,
  currentToken: number,
): boolean => operationToken === currentToken;

export const runForCurrentGcodeOperation = (
  operationToken: number,
  currentToken: number,
  action: () => void,
): boolean => {
  if (!isCurrentGcodeOperation(operationToken, currentToken)) return false;
  action();
  return true;
};

const gcodeFailureKey = (error: unknown): string | null =>
  error instanceof GcodeExcerptError ? error.code : apiErrorCode(error);

interface GcodeBatchResult {
  jobs: ParsedJobState[];
  failedFiles: string[];
  /** Files whose plates are quoted by totals only: the parts could not be counted. */
  toolpathMissingFiles: string[];
}

export interface GcodeBatchRun {
  files: File[];
  signal: AbortSignal;
  buildExcerpt: (file: File, signal: AbortSignal) => Promise<GcodeExcerpt>;
  /** Counts the parts of a file in the browser; resolves with the JSON the server expects. */
  buildToolpath?: (
    file: File,
    signal: AbortSignal,
    onProgress: (fraction: number) => void,
  ) => Promise<string>;
  parseExcerpt: (
    excerpt: GcodeExcerpt,
    signal: AbortSignal,
  ) => Promise<{ jobs: CalculatorGcodeParseResponse[] }>;
  onProgress: (progress: GcodeProcessingProgress) => void;
  /** Throws a cancellation error when this run was cancelled or replaced. */
  ensureCurrent: () => void;
}

// The server refuses a toolpath it cannot accept as a whole request; the quote is still
// possible without it.
const TOOLPATH_REFUSALS = new Set(['ERR_GCODE_EXCERPT_INVALID', 'ERR_GCODE_EXCERPT_TOO_LARGE']);

/**
 * Reads the slicer summary out of each file in the browser, counts its parts there, and
 * sends only those small results for parsing; the whole file never leaves the device.
 */
export const parseGcodeFilesFromExcerpts = async ({
  files,
  signal,
  buildExcerpt,
  buildToolpath,
  parseExcerpt,
  onProgress,
  ensureCurrent,
}: GcodeBatchRun): Promise<GcodeBatchResult> => {
  const jobs: ParsedJobState[] = [];
  const failures: Array<{ fileName: string; error: unknown }> = [];
  const toolpathMissing: string[] = [];

  for (const [index, file] of files.entries()) {
    ensureCurrent();
    const report = (phase: GcodeProcessingPhase, countedFraction?: number) => onProgress({
      phase,
      processedFiles: index,
      totalFiles: files.length,
      currentFileName: file.name,
      countedFraction,
    });
    try {
      report('reading');
      let excerpt = await buildExcerpt(file, signal);
      ensureCurrent();

      let toolpathMissed = buildToolpath === undefined;
      if (buildToolpath) {
        report('counting', 0);
        try {
          const toolpath = await buildToolpath(
            file,
            signal,
            (fraction) => report('counting', fraction),
          );
          ensureCurrent();
          excerpt = { ...excerpt, toolpath };
        } catch (error) {
          ensureCurrent();
          if (isAbortError(error)) throw error;
          toolpathMissed = true;
        }
      }

      report('analyzing');
      let parsed: { jobs: CalculatorGcodeParseResponse[] };
      try {
        parsed = await parseExcerpt(excerpt, signal);
      } catch (error) {
        ensureCurrent();
        if (excerpt.toolpath === undefined || !TOOLPATH_REFUSALS.has(apiErrorCode(error) ?? '')) {
          throw error;
        }
        toolpathMissed = true;
        parsed = await parseExcerpt({ ...excerpt, toolpath: undefined }, signal);
      }
      ensureCurrent();
      if (toolpathMissed) toolpathMissing.push(file.name);
      jobs.push(...parsed.jobs.map((job) => ({
        key: parsedJobKey(job, index),
        parsed: job,
      })));
    } catch (error) {
      ensureCurrent();
      if (isAbortError(error)) throw error;
      failures.push({ fileName: file.name, error });
    }
  }

  if (jobs.length === 0) {
    // One shared reason is shown as it is (for example "no slicer summary in the
    // file"); mixed reasons collapse into the generic batch message.
    const keys = new Set(failures.map((failure) => gcodeFailureKey(failure.error)));
    if (failures.length > 0 && keys.size === 1 && !keys.has(null)) throw failures[0].error;
    throw new Error(ALL_GCODE_FILES_FAILED);
  }
  return {
    jobs,
    failedFiles: Array.from(new Set(failures.map((failure) => failure.fileName))),
    toolpathMissingFiles: Array.from(new Set(toolpathMissing)),
  };
};

export const resolveGcodeParseError = (error: unknown, t: TFunction): string | null => {
  if (!error) {
    return null;
  }

  const errorWithResponse = error as {
    response?: { data?: { detail?: unknown } };
    message?: string;
    code?: string;
    name?: string;
  };

  if (isAbortError(errorWithResponse)) {
    return null;
  }

  if (error instanceof GcodeExcerptError) {
    return translateApiError(t, { code: error.code }, t('profilePage.calc.unknownError'));
  }

  if (errorWithResponse.message === ALL_GCODE_FILES_FAILED) {
    return translateCalculator(t, 'batchParseAllFailed');
  }

  return translateApiError(
    t,
    errorWithResponse.response?.data?.detail ?? errorWithResponse.message,
    t('profilePage.calc.unknownError'),
  );
};

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

  if (parsed.toolchange_count != null && parsed.toolchange_count > 20) {
    coef += 0.3;
  } else if (parsed.toolchange_count != null && parsed.toolchange_count > 5) {
    coef += 0.15;
  } else if (parsed.is_multi_material) {
    coef += 0.1;
  }

  if (parsed.support_type && parsed.support_type.toLowerCase() !== 'none') {
    const st = parsed.support_type.toLowerCase();
    coef += st.includes('tree') || st.includes('organic') ? 0.15 : 0.1;
  }

  if (parsed.layer_height_mm != null) {
    if (parsed.layer_height_mm < 0.1) coef += 0.2;
    else if (parsed.layer_height_mm < 0.15) coef += 0.1;
  }

  if (parsed.sparse_infill_density_percent != null) {
    if (parsed.sparse_infill_density_percent > 80) coef += 0.15;
    else if (parsed.sparse_infill_density_percent > 60) coef += 0.1;
  }

  if (parsed.object_count != null) {
    if (parsed.object_count > 3) coef += 0.1;
    else if (parsed.object_count > 1) coef += 0.05;
  }

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
  printerEconomics: PrinterEconomics | null = null,
  calculationCurrency: string | null = null,
): CalculatorHistoryEntryCreate => ({
  request_data: buildEstimateRequest(
    form,
    materialLines,
    parsedJobs,
    jobConfigs,
    printerEconomics,
    calculationCurrency,
  ),
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
    scanningPrice: request.scanning_price ?? DEFAULT_FORM_STATE.scanningPrice,
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
  sourceData?: Record<string, unknown> | null;
}

const normalizeQuoteLineItems = (items: QuoteLineItem[]): QuoteLineItem[] => items.flatMap((item) => {
  const normalized = normalizeQuoteLineUnitPrice(item);
  if (!normalized) throw new Error('quoteQuantityPriceUnrepresentable');
  return normalized;
});

interface QuoteItem {
  id: string;
  lineItem: QuoteLineItem;
  includedItems: string[];
  calculationSnapshot: CalculatorHistoryEntryCreate;
}

interface BuildQuoteHtmlParams {
  t: TFunction;
  language: string;
  items: QuoteLineItem[];
  workBreakdown?: QuoteWorkBreakdownEntry[] | null;
  includedItems: string[];
  grandTotal: number;
  parties: QuotePartyFormState;
  formatCurrency: (value: number | null | undefined) => string;
  quoteNumber?: string;
  taxRatePercent?: number;
  taxDisclosure?: { kind: 'tax' | 'vat'; mode: 'hide' | 'included' | 'separate'; amount: number; netAmount: number } | null;
  taxTotal?: number;
  customerDeliveryAmount?: number;
  calculationSnapshot?: CalculatorHistoryEntryCreate | null;
  quoteSources?: CalculatorHistoryEntryCreate[];
  quoteDisclosure?: { taxKind: 'tax' | 'vat' | null; taxMode: 'hide' | 'included' | 'separate' | null; taxAmount: number; customerDelivery: number; invalidated: boolean; baseLineFingerprint?: string; showCostBreakdown?: boolean; costBreakdownNote?: string };
  taxSplitUnavailable?: boolean;
  showCostBreakdown?: boolean;
  costBreakdownNote?: string;
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
    return normalizeQuoteLineItems([{
      title: quoteTitleFromFileName(parsedGcode?.file_name ?? '', fallbackTitle),
      details,
      quantity,
      unitPrice: totalPrice / quantity,
      totalPrice,
    }]);
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

  return normalizeQuoteLineItems(drafts.map((draft, index) => ({
    title: draft.title,
    details: draft.details,
    quantity: draft.quantity,
    unitPrice: allocatedTotals[index] / draft.quantity,
    totalPrice: allocatedTotals[index],
  })));
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
  if (result.cost_modeling > 0 || (result.cost_scanning ?? 0) > 0) {
    included.push(t('profilePage.calculator.quoteIncluded.modeling'));
  }
  if (result.cost_postprocessing > 0) {
    included.push(t('profilePage.calculator.quoteIncluded.postprocessing'));
  }

  return included.length > 0 ? included : [t('profilePage.calculator.quoteIncluded.none')];
};

const buildQuoteDisclaimerLabel = (t: TFunction): string =>
  t('profilePage.calculator.quoteDisclaimerNotOffer');

export const buildQuoteDocumentHtml = ({
  t,
  language,
  items,
  workBreakdown,
  includedItems,
  grandTotal,
  parties,
  formatCurrency,
  quoteNumber,
  customerDeliveryAmount = 0,
  taxRatePercent = 0,
  taxDisclosure = null,
  quoteDisclosure = undefined,
  showCostBreakdown = false,
  costBreakdownNote = '',
}: BuildQuoteHtmlParams): string => {
  const lineItems = items;
  const issuedAt = new Date();
  const selectedQuoteMarket = parties.quoteMarket === 'ru' || parties.quoteMarket === 'intl' || parties.quoteMarket === 'cn'
    ? resolveQuoteMarket(parties.quoteMarket, null)
    : language.toLowerCase().startsWith('ru') ? 'ru' : 'intl';
  const rules = quoteMarketRules(selectedQuoteMarket);
  const sellerTaxIdLabelKey = selectedQuoteMarket === 'ru'
    ? rules.taxIdKey
    : 'profilePage.calculator.quoteSellerTaxIdGeneric';
  const sellerRegistrationLabelKey = selectedQuoteMarket === 'ru'
    ? rules.registrationIdKey
    : 'profilePage.calculator.quoteSellerRegistrationIdGeneric';
  const formatDate = (value: Date): string =>
    new Intl.DateTimeFormat(language, { dateStyle: 'long' }).format(value);
  const today = formatDate(issuedAt);
  const validityDays = Math.max(1, Math.round(parties.validityDays || DEFAULT_QUOTE_PROFILE.validityDays));
  const validUntil = formatDate(addDays(issuedAt, validityDays));

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

  const taxRows = taxDisclosure && taxDisclosure.amount > 0
    ? taxDisclosure.mode === 'included'
      ? `<div class="quote-total-row" data-quote-total-kind="included-tax"><span>${escapeHtml(t('profilePage.calculator.quoteTaxIncludedAmount', { taxLabel: t(taxDisclosure.kind === 'vat' ? 'profilePage.calculator.quoteTaxVat' : 'profilePage.calculator.quoteTaxGeneric') }).replace('{{taxLabel}}', t(taxDisclosure.kind === 'vat' ? 'profilePage.calculator.quoteTaxVat' : 'profilePage.calculator.quoteTaxGeneric')))}:</span><span>${escapeHtml(formatCurrency(taxDisclosure.amount))}</span></div>`
      : `
          <div class="quote-total-row" data-quote-total-kind="net"><span>${escapeHtml(t('profilePage.calculator.quoteSubtotal'))}:</span><span>${escapeHtml(formatCurrency(taxDisclosure.netAmount))}</span></div>
          <div class="quote-total-row" data-quote-total-kind="tax"><span>${escapeHtml(t('profilePage.calculator.quoteTaxFromEstimate', { taxLabel: t(taxDisclosure.kind === 'vat' ? 'profilePage.calculator.quoteTaxVat' : 'profilePage.calculator.quoteTaxGeneric') }).replace('{{taxLabel}}', t(taxDisclosure.kind === 'vat' ? 'profilePage.calculator.quoteTaxVat' : 'profilePage.calculator.quoteTaxGeneric')))}:</span><span>${escapeHtml(formatCurrency(taxDisclosure.amount))}</span></div>`
    : '';
  const taxDeliveryRow = '';
  const breakdownEntries = showCostBreakdown && workBreakdown?.length
    ? workBreakdownHtmlEntries(workBreakdown, t, formatCurrency, language)
    : [];
  const breakdownMarkup = breakdownEntries.length > 0
    ? createQuoteBreakdownHtml(t('profilePage.calculator.quoteBreakdownLabel'), breakdownEntries, costBreakdownNote)
    : '';

  // A profile saved by an older version can lack fields added since; absent means empty.
  const field = (value: string | undefined) => (value ?? '').trim();
  const buyerName = field(parties.buyerName);
  const buyerInn = field(parties.buyerInn);
  const buyerAddress = field(parties.buyerAddress);
  const paymentTerms = field(parties.paymentTerms);
  const sellerName = field(parties.sellerName) || '—';
  const sellerInn = field(parties.sellerInn);
  const sellerRegistrationId = field(parties.sellerRegistrationId);
  const sellerTaxCode = field(parties.sellerTaxCode);
  const sellerAddress = field(parties.sellerAddress);
  const sellerPhone = field(parties.sellerPhone);
  const sellerBankDetails = field(parties.sellerBankDetails);


  return `<!doctype html>
<html lang="${escapeHtml(language)}">
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
      h2 { font-size: 18px; font-weight: 700; margin-bottom: 4px; }
      .subtitle { font-size: 13px; color: #6b7280; }
      .date { font-size: 13px; margin-top: 8px; }
      .header { display: flex; justify-content: space-between; align-items: flex-start; gap: 20px; margin-bottom: 20px; }
      .header > div:first-child { width: 55%; }
      .header-right { width: 40%; text-align: right; font-size: 13px; line-height: 1.7; overflow-wrap: anywhere; }
      .header-right p strong { font-size: 14px; }
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
      ${quoteFooterBaseCss}
      .total-row td { font-weight: 700; font-size: 15px; background: #f9fafb; }
      @media screen {
        body { display: flex; flex-direction: column; }
        .page { order: 0; }
        .document-header { order: -1; width: 210mm; margin: 0 auto; padding: 5mm 20mm; background: white; }
        .document-footer { order: 1; width: 210mm; margin: 0 auto; padding: 5mm 20mm; background: white; }
      }
      @media print {
        @page {
          size: A4;
          margin: 24mm 14mm 32mm;
          @top-center {
            content: element(quoteHeader);
            vertical-align: bottom;
            width: 100%;
          }
          @bottom-center {
            content: element(quoteFooter);
            vertical-align: top;
            width: 100%;
          }
        }
        body { background: white; }
        .page { width: 100%; min-height: auto; margin: 0; padding: 0; box-shadow: none; }
        tr, .box, .included { break-inside: avoid; }
        /* Chromium ignores the running element declaration below and retains this header fallback. */
        .document-header { position: fixed; top: -14mm; left: 0; right: 0; height: 10mm; margin: 0; }
        .document-header { position: running(quoteHeader); width: 100%; height: auto; margin: 0; padding: 0 0 2mm; }
        /* Chromium ignores the running element declaration below and retains this footer fallback. */
        .document-footer { position: fixed; bottom: -24mm; left: 0; right: 0; height: 20mm; margin: 0; }
        .document-footer { position: running(quoteFooter); width: 100%; height: auto; margin: 0; padding: 4mm 0 0; }
      }
      ${quoteDocumentTotalsCss}
      ${quoteDocumentLayoutCss}
    </style>
  </head>
  <body>
    ${createQuoteHeaderHtml(
      t('profilePage.calculator.quoteHeaderNoticeBefore'),
      t('profilePage.calculator.quoteHeaderNoticeAfter'),
    )}
    ${createQuoteFooterHtml(t('profilePage.calculator.quoteFooterNote'))}
    <div class="page">
      <div class="header">
        <div>
          <h2>${escapeHtml(t('profilePage.calculator.quoteDocumentTitle'))}${quoteNumber ? ` ${escapeHtml(quoteNumber)}` : ''}</h2>
          <p class="subtitle">${escapeHtml(t('profilePage.calculator.quoteDocumentSubtitle'))}</p>
        </div>
        <div class="header-right">
          <div class="quote-seller-block">
          <p class="party-label">${escapeHtml(t('profilePage.calculator.quoteExecutor'))}:</p>
          <p>${escapeHtml(sellerName)}</p>
          ${sellerInn ? `<p>${escapeHtml(t(sellerTaxIdLabelKey))}: ${escapeHtml(sellerInn)}</p>` : ''}
          ${sellerRegistrationLabelKey && sellerRegistrationId
            ? `<p>${escapeHtml(t(sellerRegistrationLabelKey))}: ${escapeHtml(sellerRegistrationId)}</p>`
            : ''}
          ${rules.showTaxCode && sellerTaxCode
            ? `<p>${escapeHtml(t('quoteMarket.ru.taxCode'))}: ${escapeHtml(sellerTaxCode)}</p>`
            : ''}
          ${sellerAddress
            ? `<p>${escapeHtml(t('quoteMarket.sellerAddress'))}: ${escapeHtml(sellerAddress)}</p>`
            : ''}
          ${sellerPhone ? `<p>${escapeHtml(t('profilePage.calculator.quotePhone'))}: ${escapeHtml(sellerPhone)}</p>` : ''}
          ${rules.showBankDetails && sellerBankDetails
            ? `<p>${escapeHtml(t('quoteMarket.sellerBank'))}: ${escapeHtml(sellerBankDetails)}</p>`
            : ''}
          </div>
          ${buyerName || buyerInn || buyerAddress ? `
          <div class="quote-buyer-block">
            <p class="party-label">${escapeHtml(t('profilePage.calculator.quoteCustomer'))}:</p>
            ${buyerName ? `<p class="box-line">${escapeHtml(buyerName)}</p>` : ''}
            ${buyerInn ? `<p class="box-muted">${escapeHtml(t('profilePage.calculator.quoteInn'))}: ${escapeHtml(buyerInn)}</p>` : ''}
            ${buyerAddress ? `<p class="box-muted">${escapeHtml(t('profilePage.calculator.quoteAddress'))}: ${escapeHtml(buyerAddress)}</p>` : ''}
          </div>` : ''}
        </div>
      </div>
      <div class="quote-meta-row"><p data-quote-issue-date>${escapeHtml(today)}</p><p data-quote-validity>${escapeHtml(t('profilePage.calculator.quoteValidUntil'))}: <strong>${escapeHtml(validUntil)}</strong></p></div>

      ${paymentTerms ? `
      <div class="box">
        <p class="box-title">${escapeHtml(t('profilePage.calculator.quotePaymentTerms'))}:</p>
        <p class="box-line">${escapeHtml(paymentTerms)}</p>
      </div>` : ''}

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
      </table>
      <div class="quote-totals" data-quote-totals>
        ${taxRows}
        ${taxDeliveryRow}
        <div class="quote-total-row quote-grand-total" data-quote-total-kind="total"><span>${escapeHtml(t('profilePage.calculator.totalCost'))}:</span><strong>${escapeHtml(formatCurrency(grandTotal))}</strong></div>
      </div>

      ${breakdownMarkup}

      <div class="included">
        <p class="included-title">${escapeHtml(t('profilePage.calculator.quoteIncludedTitle'))}:</p>
        <ul>${includedMarkup}</ul>
      </div>

    </div>
  </body>
</html>`;
};

export const CalculatorPage: React.FC<CalculatorPageProps> = ({
  embedded = false,
  activeTab: controlledActiveTab,
  onActiveTabChange,
  staticSettingsOpen: controlledStaticSettingsOpen,
  quoteProfileOpen: controlledQuoteProfileOpen,
  onStaticSettingsOpenChange,
  onQuoteProfileOpenChange,
}) => {
  const { t, i18n } = useTranslation();
  const { user, refreshUser } = useAuth();
  const queryClient = useQueryClient();
  const tc = (key: string) => translateCalculator(t, key);
  const hasCalculatorAccess = user?.has_calculator_access ?? false;
  const canStartTrial = !hasCalculatorAccess && user?.subscription == null;
  const [internalActiveTab, setInternalActiveTab] = useState<CalculatorTab>('calculator');
  const [internalStaticSettingsOpen, setInternalStaticSettingsOpen] = useState(false);
  const [internalQuoteProfileOpen, setInternalQuoteProfileOpen] = useState(false);
  const activeTab = controlledActiveTab ?? internalActiveTab;
  const staticSettingsOpen = controlledStaticSettingsOpen ?? internalStaticSettingsOpen;
  const quoteProfileOpen = controlledQuoteProfileOpen ?? internalQuoteProfileOpen;
  const setActiveTab = (tab: CalculatorTab) => {
    if (controlledActiveTab === undefined) setInternalActiveTab(tab);
    onActiveTabChange?.(tab);
  };
  const setStaticSettingsOpen = (open: boolean) => {
    if (controlledStaticSettingsOpen === undefined) setInternalStaticSettingsOpen(open);
    onStaticSettingsOpenChange?.(open);
    if (open) {
      if (controlledQuoteProfileOpen === undefined) setInternalQuoteProfileOpen(false);
      onQuoteProfileOpenChange?.(false);
    }
  };
  const setQuoteProfileOpen = (open: boolean) => {
    if (controlledQuoteProfileOpen === undefined) setInternalQuoteProfileOpen(open);
    onQuoteProfileOpenChange?.(open);
    if (open) {
      if (controlledStaticSettingsOpen === undefined) setInternalStaticSettingsOpen(false);
      onStaticSettingsOpenChange?.(false);
    }
  };
  const [form, setForm] = useState<CalculatorFormState>(DEFAULT_FORM_STATE);
  const formRef = useRef(form);
  formRef.current = form;
  const [parsedGcode, setParsedGcode] = useState<CalculatorGcodeParseResponse | null>(null);
  const [parsedJobs, setParsedJobs] = useState<ParsedJobState[]>([]);
  const [jobConfigs, setJobConfigs] = useState<CalculatorJobConfig[]>([]);
  const [materialLines, setMaterialLines] = useState<CalculatorMaterialLineState[]>([]);
  const [batchParseWarning, setBatchParseWarning] = useState<string | null>(null);
  const [gcodeProcessingProgress, setGcodeProcessingProgress] =
    useState<GcodeProcessingProgress | null>(null);
  const [materialLinesError, setMaterialLinesError] = useState<string | null>(null);
  // Materials whose price nobody has confirmed, captured when the estimate was made.
  const [approximatePriceLabels, setApproximatePriceLabels] = useState<string[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [historyFeedback, setHistoryFeedback] = useState<{ kind: 'success' | 'error'; message: string } | null>(null);
  useEffect(() => {
    if (!historyFeedback) return;
    const timer = window.setTimeout(() => setHistoryFeedback(null), HISTORY_FEEDBACK_DISMISS_MS);
    return () => window.clearTimeout(timer);
  }, [historyFeedback]);
  const [quoteProfileFeedback, setQuoteProfileFeedback] = useState<{ kind: 'success' | 'error'; message: string } | null>(null);
  useEffect(() => {
    if (!quoteProfileFeedback) return;
    const timer = window.setTimeout(() => setQuoteProfileFeedback(null), HISTORY_FEEDBACK_DISMISS_MS);
    return () => window.clearTimeout(timer);
  }, [quoteProfileFeedback]);
  const [deletingHistoryEntry, setDeletingHistoryEntry] = useState<CalculatorHistoryEntrySummary | null>(null);
  const [restoringHistoryEntryId, setRestoringHistoryEntryId] = useState<number | null>(null);
  const [failedRestoreHistoryEntryId, setFailedRestoreHistoryEntryId] = useState<number | null>(null);
  const restoreHistoryAttemptRef = useRef<number | null>(null);
  const [quoteModalOpen, setQuoteModalOpen] = useState(false);
  const [quotePdfPreview, setQuotePdfPreview] = useState<{ url: string; title: string; printable?: boolean } | null>(null);
  const [quoteProfile, setQuoteProfile] = useState<QuoteProfileState>(DEFAULT_QUOTE_PROFILE);
  const [quoteParties, setQuoteParties] = useState<QuotePartyFormState>(DEFAULT_QUOTE_PARTY_FORM);
  const [selectedSpoolId, setSelectedSpoolId] = useState<number | ''>('');
  const [preflightSafetyBufferPercent, setPreflightSafetyBufferPercent] = useState(10);
  const [preflightSpoolIdsByLine, setPreflightSpoolIdsByLine] = useState<Record<string, number[]>>({});
  const [autoMaterialMatch, setAutoMaterialMatch] = useState<AutoMaterialMatchNotice | null>(null);
  const [materialPriceSource, setMaterialPriceSource] = useState<MaterialPriceSource>('manual');
  const [accountEconomicsReadiness, setAccountEconomicsReadiness] = useState<EconomicsReadiness | null>(null);
  const [accountEconomicsLoading, setAccountEconomicsLoading] = useState(false);
  const [accountEconomicsError, setAccountEconomicsError] = useState(false);
  const [accountEconomicsSaving, setAccountEconomicsSaving] = useState(false);
  const [isCloudBusy, setIsCloudBusy] = useState(false);
  const [quoteItems, setQuoteItems] = useState<QuoteItem[]>([]);
  useEffect(() => {
    const previewUrl = quotePdfPreview?.url;
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [quotePdfPreview?.url]);
  const [quoteCustomerSelection, setQuoteCustomerSelection] = useState('new');
  const [quoteCustomerDelivery, setQuoteCustomerDelivery] = useState('');
  const [quoteTaxKind, setQuoteTaxKind] = useState<'tax' | 'vat'>('tax');
  const [quoteTaxMode, setQuoteTaxMode] = useState<'hide' | 'included' | 'separate'>('hide');
  const [quoteShowBreakdown, setQuoteShowBreakdown] = useState(false);
  const [quoteBreakdownNote, setQuoteBreakdownNote] = useState('');
  const [isSharing, setIsSharing] = useState(false);
  const [shareCopied, setShareCopied] = useState(false);
  const [isPdfDownloading, setIsPdfDownloading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const skipNextFilamentDefaultsRef = useRef(false);
  const priceManuallyEditedRef = useRef(false);
  const lastAutoMatchedGcodeKeyRef = useRef<string | null>(null);
  const lastBuiltMaterialJobsKeyRef = useRef<string | null>(null);
  const quoteSequenceRef = useRef(0);
  const lastSavedHistoryPayloadRef = useRef<string | null>(null);
  const gcodeAbortControllerRef = useRef<AbortController | null>(null);
  const gcodeOperationSequenceRef = useRef(0);
  const lastGcodeFilesRef = useRef<File[]>([]);

  useEffect(() => () => {
    gcodeAbortControllerRef.current?.abort();
  }, []);

  const formatCurrency = useMemo(
    () => makeCurrencyFormatter(quoteProfile.currency || 'RUB'),
    [quoteProfile.currency],
  );

  const calcCurrencyRef = useRef(quoteProfile.currency);
  calcCurrencyRef.current = quoteProfile.currency;
  const confirmedEconomicsCurrencyRef = useRef<CurrencyCode>(quoteProfile.currency);

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
    queryFn: ({ signal }) => spoolsAPI.list(signal),
    staleTime: 30_000,
    enabled: hasCalculatorAccess,
  });

  const resolvedFilamentIds = useMemo(() => {
    const parsedSources = parsedJobs.length > 0
      ? parsedJobs.map((job) => job.parsed)
      : parsedGcode
        ? [parsedGcode]
        : [];
    return Array.from(new Set(
      parsedSources.flatMap((parsed) =>
        parsed.materials.flatMap((material) => {
          const resolution = trustedIdentityResolution(material);
          const filamentId = resolution?.status === 'resolved' ? resolution.filament_id : null;
          return filamentId != null ? [filamentId] : [];
        }),
      ),
    )).sort((left, right) => left - right);
  }, [parsedGcode, parsedJobs]);

  const baseCatalogFilaments = filamentsQuery.data?.items ?? [];
  const supplementalFilamentIds = useMemo(() => {
    const loadedIds = new Set(baseCatalogFilaments.map((filament) => filament.id));
    return resolvedFilamentIds.filter((filamentId) => !loadedIds.has(filamentId));
  }, [baseCatalogFilaments, resolvedFilamentIds]);

  const supplementalFilamentsQuery = useQuery({
    queryKey: ['calculator-pro', 'resolved-filaments', supplementalFilamentIds],
    queryFn: () => Promise.all(
      supplementalFilamentIds.map((filamentId) => filamentsAPI.get(filamentId)),
    ),
    staleTime: 60_000,
    enabled:
      hasCalculatorAccess
      && !filamentsQuery.isPending
      && supplementalFilamentIds.length > 0,
  });

  const catalogFilaments = useMemo(() => {
    const byId = new Map(baseCatalogFilaments.map((filament) => [filament.id, filament]));
    for (const filament of supplementalFilamentsQuery.data ?? []) {
      byId.set(filament.id, filament);
    }
    return Array.from(byId.values());
  }, [baseCatalogFilaments, supplementalFilamentsQuery.data]);
  const catalogFilamentsPending =
    filamentsQuery.isPending
    || (supplementalFilamentIds.length > 0 && supplementalFilamentsQuery.isPending);
  const catalogFilamentsError = filamentsQuery.isError || supplementalFilamentsQuery.isError;

  const quoteCustomersQuery = useQuery({
    queryKey: ['crm', 'customers', 'calculator'],
    queryFn: () => crmAPI.listCustomers({ size: 100 }),
    staleTime: 30_000,
    enabled: hasCalculatorAccess && quoteModalOpen,
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

  const preflightMutation = useMutation({
    mutationFn: (data: CalculatorPreflightRequest) => calculatorAPI.preflight(data),
  });

  const parseGcodeMutation = useMutation({
    mutationFn: async ({
      files,
      operationToken,
    }: {
      files: File[];
      operationToken: number;
    }) => {
      if (!isCurrentGcodeOperation(operationToken, gcodeOperationSequenceRef.current)) {
        throw new DOMException('canceled', 'AbortError');
      }
      const limitedFiles = files.slice(0, 20);
      const controller = new AbortController();
      gcodeAbortControllerRef.current?.abort();
      gcodeAbortControllerRef.current = controller;

      try {
        const { jobs, failedFiles, toolpathMissingFiles } = await parseGcodeFilesFromExcerpts({
          files: limitedFiles,
          signal: controller.signal,
          buildExcerpt: buildGcodeExcerpt,
          buildToolpath: (file, signal, onToolpathProgress) => buildGcodeToolpath(file, {
            signal,
            onProgress: onToolpathProgress,
          }),
          parseExcerpt: (excerpt, signal) => calculatorAPI.parseGcodeExcerpt(excerpt, signal),
          onProgress: (progress) => {
            if (controller.signal.aborted) return;
            runForCurrentGcodeOperation(
              operationToken,
              gcodeOperationSequenceRef.current,
              () => setGcodeProcessingProgress(progress),
            );
          },
          ensureCurrent: () => {
            if (
              controller.signal.aborted
              || !isCurrentGcodeOperation(operationToken, gcodeOperationSequenceRef.current)
            ) {
              throw new DOMException('canceled', 'AbortError');
            }
          },
        });
        return {
          jobs,
          failedFiles,
          toolpathMissingFiles,
          skippedCount: Math.max(0, files.length - limitedFiles.length),
        };
      } finally {
        if (gcodeAbortControllerRef.current === controller) {
          gcodeAbortControllerRef.current = null;
        }
      }
    },
  });

  const historyQuery = useInfiniteQuery({
    queryKey: calculatorHistoryKeys.feed(20),
    queryFn: ({ pageParam, signal }) => calculatorAPI.listHistoryFeed(
      { limit: 20, cursor: pageParam },
      signal,
    ),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor ?? undefined,
    staleTime: 30_000,
    enabled: hasCalculatorAccess,
  });
  const historyEntries = useMemo(
    () => historyQuery.data?.pages.flatMap((page) => page.items) ?? [],
    [historyQuery.data?.pages],
  );

  const saveHistoryMutation = useMutation({
    mutationFn: (payload: CalculatorHistoryEntryCreate) => calculatorAPI.saveHistory(payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['calculator-pro', 'history'] }),
        queryClient.invalidateQueries({ queryKey: ['achievement-overview'] }),
      ]);
    },
  });

  const deleteHistoryMutation = useMutation({
    mutationFn: (entryId: number) => calculatorAPI.deleteHistory(entryId),
    onSuccess: async (_result, entryId) => {
      queryClient.removeQueries({ queryKey: calculatorHistoryKeys.detail(entryId) });
      await queryClient.invalidateQueries({ queryKey: ['calculator-pro', 'history'] });
    },
  });

  const saveQuoteToWorkspaceMutation = useMutation({
    mutationFn: crmAPI.createQuote,
    onSuccess: async (quote) => {
      if (quote.customer_id) {
        setQuoteCustomerSelection(`customer:${quote.customer_id}`);
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['crm'] }),
        queryClient.invalidateQueries({ queryKey: ['calculator-pro', 'history'] }),
      ]);
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
    () => catalogFilaments.find((filament) => filament.id === form.selectedFilamentId) ?? null,
    [catalogFilaments, form.selectedFilamentId],
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
    let cancelled = false;
    setForm((prev) => ({
      ...prev,
      ...loadStoredCalculatorDefaults(),
    }));

    if (!hasCalculatorAccess) {
      setAccountEconomicsLoading(false);
      return;
    }
    setAccountEconomicsLoading(true);
    setAccountEconomicsError(false);
    void calculatorAPI
      .getProfile()
      .then((profile) => {
        if (cancelled) return;
        const profileCurrency = calculatorCurrencyFromProfile(profile);
        confirmedEconomicsCurrencyRef.current = profileCurrency;
        calcCurrencyRef.current = profileCurrency;
        setForm((prev) => ({
          ...prev,
          ...profileToStaticSettings(profile),
        }));
        setQuoteProfile((prev) => ({
          ...prev,
          currency: profileCurrency,
        }));
        setQuoteParties((prev) => ({
          ...prev,
          currency: profileCurrency,
        }));
        queryClient.setQueryData(USER_PREFERENCES_QUERY_KEY, {
          currency: profileCurrency,
        });
        setAccountEconomicsReadiness(profile.economics_readiness);
      })
      .catch(() => {
        if (!cancelled) setAccountEconomicsError(true);
      })
      .finally(() => {
        if (!cancelled) setAccountEconomicsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [hasCalculatorAccess]);

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
      const priceCurrency = resolveUserSpoolPriceCurrency(selectedSpool);
      const fallbackCurrencyOk =
        !priceCurrency || priceCurrency === calcCurrencyRef.current;

      setForm((prev) => ({
        ...prev,
        spoolPrice: fallbackCurrencyOk ? (defaults.spoolPrice ?? 0) : 0,
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
      spoolPrice: currencyMatches ? (defaults.spoolPrice ?? 0) : 0,
      spoolWeightKg: defaults.spoolWeightKg ?? prev.spoolWeightKg,
    }));
    setMaterialPriceSource(currencyMatches && defaults.spoolPrice != null ? 'filamenthub' : 'unset');
  }, [quoteProfile.currency, selectedCatalogFilament, selectedSpool]);

  useEffect(() => {
    const stored = loadStoredQuoteProfile();
    const nextProfile: QuoteProfileState = {
      ...DEFAULT_QUOTE_PROFILE,
      ...stored,
      currency: normalizeCurrency(stored.currency || defaultCurrencyForCountry(user?.country, i18n.language)),
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
    const detail = errorWithResponse.response?.data?.detail;

    if (Array.isArray(detail)) {
      return translateCalculator(t, 'estimateValidationError');
    }

    return translateApiError(
      t,
      detail ?? errorWithResponse.message,
      t('profilePage.calc.unknownError'),
    );
  }, [calculateMutation.error, t]);

  const preflightError = useMemo(() => {
    if (!preflightMutation.error) return null;
    const errorWithResponse = preflightMutation.error as {
      response?: { data?: { detail?: unknown } };
      message?: string;
    };
    return translateApiError(
      t,
      errorWithResponse.response?.data?.detail ?? errorWithResponse.message,
      tc('preflightError'),
    );
  }, [preflightMutation.error, t]);

  const parseGcodeError = useMemo(() => {
    return resolveGcodeParseError(parseGcodeMutation.error, t);
  }, [parseGcodeMutation.error, t]);

  const historyLoadError = useMemo(() => {
    if (!shouldShowInitialHistoryError(historyQuery.error, historyQuery.data?.pages)) {
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
  }, [historyQuery.data?.pages, historyQuery.error, t]);

  const currentJobCount = parsedJobs.length > 0 ? parsedJobs.length : parsedGcode ? 1 : 0;

  const updateField = <K extends keyof CalculatorFormState>(field: K, value: CalculatorFormState[K]) => {
    if (field === 'spoolPrice') {
      priceManuallyEditedRef.current = true;
      setMaterialPriceSource('manual');
    }
    if (['weightG', 'supportsWeightG', 'supportsLossCoefficient', 'quantity'].includes(field)) {
      preflightMutation.reset();
    }
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const [pickedSliceId, setPickedSliceId] = useState<number | null>(null);
  const [goneSourceKeys, setGoneSourceKeys] = useState<string[]>([]);
  const [sliceProgress, setSliceProgress] = useState<number | null>(null);
  const pendingSliceRef = useRef<OrcaSliceReport | null>(null);

  const [selectedPrinterId, setSelectedPrinterId] = useState<number | ''>('');
  const [printerPickedFrom, setPrinterPickedFrom] = useState<string | null>(null);
  const [economicsPrinterId, setEconomicsPrinterId] = useState<number | ''>('');

  useEffect(() => {
    if (selectedPrinterId !== '') {
      setEconomicsPrinterId(selectedPrinterId);
    }
  }, [selectedPrinterId]);

  const printersQuery = useQuery({
    queryKey: ['calculator', 'physical-printers'],
    queryFn: ({ signal }) => physicalPrintersAPI.list(signal),
    staleTime: 60_000,
    enabled: hasCalculatorAccess,
  });
  const printers = printersQuery.data ?? [];

  const printerEconomicsQuery = useQuery({
    queryKey: ['printer-economics', selectedPrinterId],
    queryFn: () => physicalPrintersAPI.economics(selectedPrinterId as number),
    enabled: selectedPrinterId !== '',
    retry: false,
  });
  const printerEconomics = selectedPrinterId === '' ? null : printerEconomicsQuery.data ?? null;

  const handlePrinterSelect = (printerId: number | '') => {
    preflightMutation.reset();
    setSelectedPrinterId(printerId);
    setPrinterPickedFrom(null);
  };

  // Plates can name their own machines, and each one's hour has its own price.
  const jobPrinterIds = useMemo(
    () => Array.from(new Set(
      jobConfigs
        .map((config) => config.physicalPrinterId)
        .filter((printerId): printerId is number => printerId !== ''),
    )).sort((left, right) => left - right),
    [jobConfigs],
  );

  const jobPrinterEconomicsQuery = useQuery({
    queryKey: ['calculator', 'job-printer-economics', jobPrinterIds.join(',')],
    queryFn: async () => {
      const entries = await Promise.all(
        jobPrinterIds.map(async (printerId) => [
          printerId,
          await physicalPrintersAPI.economics(printerId),
        ] as const),
      );
      return new Map<number, PrinterEconomics>(entries);
    },
    enabled: jobPrinterIds.length > 0,
    staleTime: 60_000,
  });

  const jobPrinterEconomics = jobPrinterEconomicsQuery.data ?? new Map<number, PrinterEconomics>();

  const handleSlicePick = (slice: OrcaSliceReport) => {
    if (!slice.source_key) {
      toast.error(t('slicedJobs.gone'));
      return;
    }
    // The plugin reads one slice at a time and answers without naming a request.
    if (pendingSliceRef.current) return;
    pendingSliceRef.current = slice;
    setSliceProgress(null);
    setPickedSliceId(slice.id);
    requestSliceParse(slice.source_key, slice.file_name);
  };

  const handleSelectSpool = (spoolId: number | '') => {
    setAutoMaterialMatch(null);
    skipNextFilamentDefaultsRef.current = false;
    priceManuallyEditedRef.current = false;
    setSelectedSpoolId(spoolId);
    setPreflightSpoolIdsByLine((current) => {
      const next = { ...current };
      delete next.manual;
      return next;
    });
    preflightMutation.reset();

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
    setPreflightSpoolIdsByLine((current) => {
      const next = { ...current };
      delete next.manual;
      return next;
    });
    preflightMutation.reset();
    setForm((prev) => ({
      ...prev,
      selectedFilamentId: filamentId,
    }));
  };

  const handleMaterialLineSelection = (lineId: string, selectionValue: string) => {
    setMaterialLinesError(null);
    setPreflightSpoolIdsByLine((current) => {
      const next = { ...current };
      delete next[lineId];
      return next;
    });
    preflightMutation.reset();
    setMaterialLines((currentLines) =>
      currentLines.map((line) => {
        if (line.line_id !== lineId) return line;
        if (selectionValue.startsWith('spool:')) {
          const spoolId = Number(selectionValue.slice('spool:'.length));
          const spool = availableSpools.find((item) => item.id === spoolId);
          if (!spool) return line;
          const defaults = deriveUserSpoolDefaults(spool);
          const priceCurrency = resolveUserSpoolPriceCurrency(spool);
          const currencyMatches =
            !priceCurrency || priceCurrency === calcCurrencyRef.current;
          return {
            ...line,
            selectionValue,
            spool_id: spool.id,
            filament_id: spool.filament_id,
            spool_price: currencyMatches ? (defaults.spoolPrice ?? 0) : 0,
            spool_weight_kg: defaults.spoolWeightKg ?? 1,
            price_source: spool.price != null ? 'spool' : 'filamenthub',
            mappingSource: 'explicit',
            confidence: null,
            requiresSpoolChoice: false,
            // The purchase price covers the whole spool, so without its weight the cost per
            // gram is unknown. Assuming a kilogram would quietly undercharge a 750 g spool.
            priceResolved: currencyMatches
              && defaults.spoolPrice != null
              && (spool.price == null || defaults.spoolWeightKg != null),
          };
        }
        if (selectionValue.startsWith('filament:')) {
          const filamentId = Number(selectionValue.slice('filament:'.length));
          const filament = catalogFilaments.find((item) => item.id === filamentId);
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
            mappingSource: 'explicit',
            confidence: null,
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
          mappingSource: 'unresolved',
          confidence: null,
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

  const economicsSyncRef = useRef<number | undefined>(undefined);
  const pendingEconomicsPatchRef = useRef<CalculatorProfileUpdate>({});
  const economicsRequestSequenceRef = useRef(0);
  const economicsSaveQueueRef = useRef<Promise<void>>(Promise.resolve());

  useEffect(() => () => window.clearTimeout(economicsSyncRef.current), []);

  const submitAccountEconomicsPatch = (
    payload: CalculatorProfileUpdate,
    requestSequence: number,
  ) => {
    const requestChangedCurrency = Object.prototype.hasOwnProperty.call(payload, 'currency');
    const queued = enqueueEconomicsSave(
      economicsSaveQueueRef.current,
      () => calculatorAPI.updateProfile(payload),
    );
    const task = queued.task;
    economicsSaveQueueRef.current = queued.tail;
    void task
      .then((profile) => {
        if (isLatestCalculatorProfileRequest(requestSequence, economicsRequestSequenceRef.current)) {
          const nextForm = reconcileCalculatorProfileForm(formRef.current, profile);
          const profileCurrency = calculatorCurrencyFromProfile(profile);
          formRef.current = nextForm;
          confirmedEconomicsCurrencyRef.current = profileCurrency;
          calcCurrencyRef.current = profileCurrency;
          setForm(nextForm);
          saveStoredCalculatorDefaults(extractStaticSettings(nextForm));
          setQuoteProfile((current) => ({ ...current, currency: profileCurrency }));
          setQuoteParties((current) => ({ ...current, currency: profileCurrency }));
          setAccountEconomicsReadiness(profile.economics_readiness);
          setAccountEconomicsError(false);
          queryClient.setQueryData(USER_PREFERENCES_QUERY_KEY, {
            currency: normalizeCurrency(profile.currency),
          });
        }
      })
      .catch((error) => {
        if (isLatestCalculatorProfileRequest(requestSequence, economicsRequestSequenceRef.current)) {
          const rollbackCurrency = calculatorCurrencyAfterFailedSave(
            calcCurrencyRef.current,
            confirmedEconomicsCurrencyRef.current,
            requestChangedCurrency,
            requestSequence,
            economicsRequestSequenceRef.current,
          );
          if (rollbackCurrency !== calcCurrencyRef.current) {
            calcCurrencyRef.current = rollbackCurrency;
            setQuoteProfile((current) => ({ ...current, currency: rollbackCurrency }));
            setQuoteParties((current) => ({ ...current, currency: rollbackCurrency }));
          }
          setAccountEconomicsError(true);
          toast.error(translateApiError(t, error, t('printerCost.readiness.saveError')));
        }
      })
      .finally(() => {
        if (
          isLatestCalculatorProfileRequest(requestSequence, economicsRequestSequenceRef.current)
          && Object.keys(pendingEconomicsPatchRef.current).length === 0
          && economicsSyncRef.current === undefined
        ) {
          setAccountEconomicsSaving(false);
        }
      });
  };

  const updateStaticField = <K extends CalculatorStaticSettingKey>(field: K, value: CalculatorFormState[K]) => {
    const next = { ...formRef.current, [field]: value };
    formRef.current = next;
    setForm(next);
    saveStoredCalculatorDefaults(extractStaticSettings(next));
    const requestSequence = ++economicsRequestSequenceRef.current;
    pendingEconomicsPatchRef.current = mergeCalculatorProfilePatches(
      pendingEconomicsPatchRef.current,
      calculatorProfilePatchForField(field, value),
    );
    setAccountEconomicsSaving(true);
    setAccountEconomicsError(false);
    window.clearTimeout(economicsSyncRef.current);
    economicsSyncRef.current = window.setTimeout(() => {
      economicsSyncRef.current = undefined;
      const payload = pendingEconomicsPatchRef.current;
      pendingEconomicsPatchRef.current = {};
      submitAccountEconomicsPatch(payload, requestSequence);
    }, 800);
  };

  const updateQuoteProfileField = <K extends keyof QuoteProfileState>(field: K, value: QuoteProfileState[K]) => {
    setQuoteProfile((prev) => {
      const next = { ...prev, [field]: value };
      return next;
    });
    if (field === 'currency' && hasCalculatorAccess) {
      const requestSequence = ++economicsRequestSequenceRef.current;
      setAccountEconomicsSaving(true);
      setAccountEconomicsError(false);
      window.clearTimeout(economicsSyncRef.current);
      economicsSyncRef.current = undefined;
      const pendingPayload = pendingEconomicsPatchRef.current;
      pendingEconomicsPatchRef.current = {};
      submitAccountEconomicsPatch(
        mergeCalculatorProfilePatches(pendingPayload, { currency: value as string }),
        requestSequence,
      );
    }
    setQuoteParties((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  const currentPreflightRequest = (
    spoolIdsByLine: Record<string, number[]> = preflightSpoolIdsByLine,
    safetyBufferPercent = preflightSafetyBufferPercent,
  ): CalculatorPreflightRequest | null => {
    const estimateRequest = buildEstimateRequest(
      form,
      materialLines,
      parsedJobs,
      jobConfigs,
      printerEconomics,
      quoteProfile.currency,
      jobPrinterEconomics,
    );
    return buildPreflightRequest(
      estimateRequest,
      materialLines,
      selectedSpool,
      selectedCatalogFilament,
      spoolIdsByLine,
      safetyBufferPercent,
      parsedGcode,
      autoMaterialMatch,
      parsedJobs,
      selectedPrinterId,
    );
  };

  const runPreflight = (
    spoolIdsByLine: Record<string, number[]> = preflightSpoolIdsByLine,
    safetyBufferPercent = preflightSafetyBufferPercent,
  ) => {
    const payload = currentPreflightRequest(spoolIdsByLine, safetyBufferPercent);
    if (payload) preflightMutation.mutate(payload);
  };

  // Readiness is part of the answer, not an extra button. The key is the set of material
  // lines, so editing a price or a spool does not fire another server round-trip.
  const autoPreflightLinesKeyRef = useRef<string | null>(null);
  const autoPreflightRunsRef = useRef(0);
  useEffect(() => {
    if (parsedJobs.length === 0 || materialLines.length === 0) return;
    // A failed check must not retry in a loop, and a pending one is already on its way.
    if (preflightMutation.isPending || preflightMutation.error) return;
    const linesKey = materialLines
      .map((line) => `${line.line_id}:${line.spool_id ?? ''}`)
      .join('|');
    // Other actions drop the whole result; without this the status vanishes from every
    // row at once and the person is left guessing.
    const staleResult = preflightMutation.data == null;
    if (!staleResult && autoPreflightLinesKeyRef.current === linesKey) return;
    if (autoPreflightLinesKeyRef.current === linesKey) {
      // Same materials, result keeps disappearing: something else resets it. Re-running
      // forever would put every open tab on the server, so stop after a few tries and
      // leave the manual refresh.
      if (autoPreflightRunsRef.current >= 3) return;
      autoPreflightRunsRef.current += 1;
    } else {
      autoPreflightRunsRef.current = 1;
    }
    autoPreflightLinesKeyRef.current = linesKey;
    runPreflight();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    materialLines,
    parsedJobs,
    preflightMutation.data,
    preflightMutation.isPending,
    preflightMutation.error,
  ]);

  const handlePreflightSpoolIdsChange = (lineId: string, spoolIds: number[]) => {
    const next = { ...preflightSpoolIdsByLine, [lineId]: spoolIds };
    setPreflightSpoolIdsByLine(next);
    // Dropping the spool the row was priced from would leave the picker naming a spool the
    // print no longer uses. Move it to the one that stays instead of letting them diverge.
    setMaterialLines((currentLines) =>
      currentLines.map((line) => {
        if (line.line_id !== lineId) return line;
        if (line.spool_id == null || spoolIds.includes(line.spool_id)) return line;
        const nextSpool = spoolIds
          .map((spoolId) => availableSpools.find((item) => item.id === spoolId))
          .find((spool): spool is UserSpool => spool != null);
        if (!nextSpool) return line;
        const defaults = deriveUserSpoolDefaults(nextSpool);
        const priceCurrency = resolveUserSpoolPriceCurrency(nextSpool);
        const currencyMatches = !priceCurrency || priceCurrency === calcCurrencyRef.current;
        return {
          ...line,
          selectionValue: `spool:${nextSpool.id}`,
          spool_id: nextSpool.id,
          filament_id: nextSpool.filament_id,
          spool_price: currencyMatches ? (defaults.spoolPrice ?? 0) : 0,
          spool_weight_kg: defaults.spoolWeightKg ?? 1,
          price_source: nextSpool.price != null ? 'spool' : 'filamenthub',
          priceResolved: currencyMatches
            && defaults.spoolPrice != null
            && (nextSpool.price == null || defaults.spoolWeightKg != null),
        };
      }),
    );
    runPreflight(next);
  };

  const handlePreflightBufferChange = (value: number) => {
    setPreflightSafetyBufferPercent(value);
    preflightMutation.reset();
  };

  const handleCalculate = () => {
    // A missing price cannot be calculated. An unconfirmed one can: it only stops the
    // total from being presented as final. Refusing both would wall off everyone whose
    // only price came out of the slicer.
    if (materialLines.some((line) => line.spool_price <= 0 || line.spool_weight_kg <= 0)) {
      setMaterialLinesError(tc('materialLinesIncomplete'));
      return;
    }
    setMaterialLinesError(null);
    setApproximatePriceLabels(
      materialLines
        .filter((line) => !line.priceResolved)
        .map((line) => line.label?.trim() || line.line_id),
    );
    const estimateRequest = buildEstimateRequest(
      form,
      materialLines,
      parsedJobs,
      jobConfigs,
      printerEconomics,
      quoteProfile.currency,
      jobPrinterEconomics,
    );
    calculateMutation.mutate(estimateRequest);
    const preflightRequest = buildPreflightRequest(
      estimateRequest,
      materialLines,
      selectedSpool,
      selectedCatalogFilament,
      preflightSpoolIdsByLine,
      preflightSafetyBufferPercent,
      parsedGcode,
      autoMaterialMatch,
      parsedJobs,
      selectedPrinterId,
    );
    if (preflightRequest) preflightMutation.mutate(preflightRequest);
  };

  const applyParsedJobs = (
    jobs: ParsedJobState[],
    warning: string | null,
    mode: 'replace' | 'append' = 'replace',
  ) => {
    calculateMutation.reset();
    preflightMutation.reset();
    priceManuallyEditedRef.current = false;
    lastAutoMatchedGcodeKeyRef.current = null;
    lastBuiltMaterialJobsKeyRef.current = null;
    setAutoMaterialMatch(null);
    setMaterialLinesError(null);
    setApproximatePriceLabels([]);
    setBatchParseWarning(warning);

    if (mode === 'append' && parsedJobs.length > 0) {
      // A second file joins the same order instead of throwing the first one away:
      // work already done on the existing plates must survive.
      const existingKeys = new Set(parsedJobs.map((job) => job.key));
      const added = jobs.filter((job) => !existingKeys.has(job.key));
      if (added.length === 0) return;
      setParsedJobs([...parsedJobs, ...added]);
      setJobConfigs((current) => appendJobConfigs(current, added));
      return;
    }

    setPreflightSpoolIdsByLine({});
    setSelectedSpoolId('');
    setMaterialPriceSource('unset');
    setParsedJobs(jobs);
    setJobConfigs(createJobConfigs(jobs, jobs.length > 1));
    setParsedGcode(jobs[0]?.parsed ?? null);
    // The file already names the machine it was sliced for. Asking again is asking
    // the person to repeat what the slicer wrote down.
    const filePrinterId = jobs.length === 1 ? singleSuggestedPrinterId(jobs[0]) : '';
    if (filePrinterId !== '' && selectedPrinterId === '') {
      setSelectedPrinterId(filePrinterId);
      setPrinterPickedFrom(tc('printerPickedFromGcode'));
    }
    setForm((prev) => ({
      ...applyParsedJobsToForm(prev, jobs),
      selectedFilamentId: '',
      spoolPrice: 0,
    }));
  };

  const handleRemoveParsedJob = (jobKey: string) => {
    const remaining = parsedJobs.filter((job) => job.key !== jobKey);
    calculateMutation.reset();
    preflightMutation.reset();
    lastBuiltMaterialJobsKeyRef.current = null;
    setParsedJobs(remaining);
    setJobConfigs((current) => current.filter((config) => config.jobKey !== jobKey));
    setMaterialLines((current) => current.filter((line) => line.job_key !== jobKey));
    setParsedGcode(remaining[0]?.parsed ?? null);
    if (remaining.length === 0) {
      setBatchParseWarning(null);
      setPreflightSpoolIdsByLine({});
    }
  };

  const handleGcodeFiles = async (files: File[]) => {
    const operationToken = gcodeOperationSequenceRef.current + 1;
    gcodeOperationSequenceRef.current = operationToken;
    gcodeAbortControllerRef.current?.abort();
    lastGcodeFilesRef.current = files;
    parseGcodeMutation.reset();
    try {
      const batch = await parseGcodeMutation.mutateAsync({ files, operationToken });
      if (!isCurrentGcodeOperation(operationToken, gcodeOperationSequenceRef.current)) return;
      const notices = [
        batch.failedFiles.length > 0 || batch.skippedCount > 0
          ? tc('batchParsePartial')
              .replace('{{failed}}', String(batch.failedFiles.length))
              .replace('{{skipped}}', String(batch.skippedCount))
          : null,
        batch.toolpathMissingFiles.length > 0
          ? tc('gcodeToolpathUnavailable').replace('{{files}}', batch.toolpathMissingFiles.join(', '))
          : null,
      ].filter((notice): notice is string => notice !== null);
      applyParsedJobs(
        batch.jobs,
        notices.length > 0 ? notices.join(' ') : null,
        parsedJobs.length > 0 ? 'append' : 'replace',
      );
      lastGcodeFilesRef.current = [];
    } catch {
      // Mutation state owns the localized error and keeps the current calculator
      // inputs intact so the same in-memory files can be retried directly.
    } finally {
      runForCurrentGcodeOperation(
        operationToken,
        gcodeOperationSequenceRef.current,
        () => setGcodeProcessingProgress(null),
      );
    }
  };

  const cancelGcodeProcessing = () => {
    gcodeOperationSequenceRef.current += 1;
    gcodeAbortControllerRef.current?.abort();
    setGcodeProcessingProgress(null);
  };

  const retryGcodeProcessing = () => {
    if (lastGcodeFilesRef.current.length > 0) {
      void handleGcodeFiles(lastGcodeFilesRef.current);
    }
  };

  const applyParsedJobsRef = useRef(applyParsedJobs);
  useEffect(() => {
    applyParsedJobsRef.current = applyParsedJobs;
  });

  useEffect(() => {
    if (!isPluginEmbed()) {
      return;
    }
    const stopProgress = subscribeToPluginSliceProgress((progress) => {
      if (pendingSliceRef.current?.source_key === progress.sourceKey) {
        setSliceProgress(progress.fraction);
      }
    });
    const stopResult = subscribeToPluginSliceParse((result) => {
      const slice = pendingSliceRef.current;
      // An answer nobody is waiting for, e.g. to a page that was reloaded meanwhile.
      if (!slice || (result.sourceKey && result.sourceKey !== slice.source_key)) {
        return;
      }
      pendingSliceRef.current = null;
      setPickedSliceId(null);
      setSliceProgress(null);
      if (result.error === 'gone') {
        if (slice.source_key) {
          setGoneSourceKeys((current) => [...current, slice.source_key as string]);
        }
        toast.error(t('slicedJobs.gone'));
        return;
      }
      const parsedJobs = pluginSliceJobs(result);
      if (parsedJobs.length === 0) {
        const fallback = translateCalculator(t, 'sliceParseFailed');
        toast.error(result.code ? translateApiError(t, { code: result.code }, fallback) : fallback);
        return;
      }
      // A slice joins the order like a dropped file does: an order can mix plates
      // sliced for different machines.
      applyParsedJobsRef.current(pluginSliceJobStates(parsedJobs, slice), null, 'append');
      toast.success(t('slicedJobs.taken', { name: slice.file_name }));
    });
    return () => {
      stopProgress();
      stopResult();
    };
  }, [t]);

  // The plugin always answers; this only frees the list if it never does (plugin reloaded mid-read).
  useEffect(() => {
    if (pickedSliceId === null) {
      return;
    }
    const timer = window.setTimeout(() => {
      pendingSliceRef.current = null;
      setPickedSliceId(null);
      setSliceProgress(null);
      toast.error(translateCalculator(t, 'sliceParseFailed'));
    }, SLICE_PARSE_STALL_MS);
    return () => window.clearTimeout(timer);
  }, [pickedSliceId, sliceProgress, t]);

  const handleJobSelect = (jobKey: string) => {
    const job = parsedJobs.find((candidate) => candidate.key === jobKey);
    if (job) setParsedGcode(job.parsed);
  };

  const handleJobConfigChange = (
    jobKey: string,
    patch: Partial<Omit<CalculatorJobConfig, 'jobKey'>>,
  ) => {
    preflightMutation.reset();
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

  const saveCurrentResultToHistory = async (): Promise<boolean> => {
    if (!result) return false;

    setHistoryFeedback(null);
    let payload: CalculatorHistoryEntryCreate;
    try {
      payload = buildHistoryPayload(
        form,
        result,
        parsedGcode,
        selectedMaterial,
        materialLines,
        parsedJobs,
        jobConfigs,
        printerEconomics,
        quoteProfile.currency,
      );
    } catch (error) {
      setHistoryFeedback({
        kind: 'error',
        message: error instanceof Error && error.message === 'quoteQuantityPriceUnrepresentable'
          ? tc('quoteQuantityPriceUnrepresentable')
          : tc('historySaveError'),
      });
      return false;
    }

    const fingerprint = JSON.stringify(payload);
    if (lastSavedHistoryPayloadRef.current === fingerprint) return true;

    try {
      await saveHistoryMutation.mutateAsync(payload);
      lastSavedHistoryPayloadRef.current = fingerprint;
      return true;
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
      return false;
    }
  };

  const handleSaveToHistory = async () => {
    const saved = await saveCurrentResultToHistory();
    if (saved) {
      setHistoryFeedback({ kind: 'success', message: tc('historySaved') });
      setActiveTab('history');
    }
  };

  const applyRestoredHistory = (entry: CalculatorHistoryEntry) => {
    const restoredJobs: ParsedJobState[] = entry.parsed_jobs?.length
      ? entry.parsed_jobs.map((job) => ({ key: job.job_key, parsed: job.parsed_gcode }))
      : entry.parsed_gcode
        ? [{ key: parsedJobKey(entry.parsed_gcode, 0), parsed: entry.parsed_gcode }]
        : [];
    const restoredJobsByKey = new Map(restoredJobs.map((job) => [job.key, job.parsed]));
    skipNextFilamentDefaultsRef.current = true;
    preflightMutation.reset();
    setPreflightSpoolIdsByLine({});
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
            physicalPrinterId: saved.physical_printer_id ?? '',
          }
        : {
            ...createDefaultJobConfig(job),
            repeats: legacyRepeats,
          };
    }));
    setMaterialLines(
      (entry.request_data.material_lines ?? []).map((line) => {
        const parsedJob = line.job_key
          ? restoredJobsByKey.get(line.job_key) ?? entry.parsed_gcode
          : entry.parsed_gcode;
        const parsedMaterial = findParsedMaterialForTool(parsedJob, line.tool_index);
        return {
          ...line,
          selectionValue: line.spool_id
            ? `spool:${line.spool_id}`
            : line.filament_id
              ? `filament:${line.filament_id}`
              : 'manual',
          fileName: parsedJob?.file_name
            ?? line.job_key
            ?? tc('manualMaterialLine'),
          plateIndex: parsedJob?.plate_index ?? null,
          confidence: null,
          evidenceSource: parsedJob ? 'gcode' : 'manual',
          lengthMm: parsedMaterial?.length_mm ?? null,
          volumeCm3: parsedMaterial?.volume_cm3 ?? null,
          mappingSource: line.spool_id || line.filament_id ? 'explicit' : 'unresolved',
          requiresSpoolChoice: false,
          priceResolved: true,
        };
      }),
    );
    setActiveTab('calculator');
    setHistoryFeedback({ kind: 'success', message: tc('historyRestored') });
  };

  const handleRestoreHistory = async (entry: CalculatorHistoryEntrySummary) => {
    if (restoreHistoryAttemptRef.current !== null) return;
    restoreHistoryAttemptRef.current = entry.id;
    setRestoringHistoryEntryId(entry.id);
    setFailedRestoreHistoryEntryId(null);
    setHistoryFeedback(null);
    try {
      const fullEntry = await queryClient.fetchQuery({
        queryKey: calculatorHistoryKeys.detail(entry.id),
        queryFn: ({ signal }) => calculatorAPI.getHistory(entry.id, signal),
        staleTime: 30_000,
      });
      if (restoreHistoryAttemptRef.current === entry.id) applyRestoredHistory(fullEntry);
    } catch (error) {
      if (restoreHistoryAttemptRef.current !== entry.id) return;
      const errorWithResponse = error as { response?: { data?: { detail?: unknown } }; message?: string };
      setFailedRestoreHistoryEntryId(entry.id);
      setHistoryFeedback({
        kind: 'error',
        message: translateApiError(
          t,
          errorWithResponse.response?.data?.detail ?? errorWithResponse.message,
          tc('historyLoadError'),
        ),
      });
    } finally {
      if (restoreHistoryAttemptRef.current === entry.id) {
        restoreHistoryAttemptRef.current = null;
        setRestoringHistoryEntryId(null);
      }
    }
  };

  const handleDeleteHistory = (entry: CalculatorHistoryEntrySummary) => {
    setDeletingHistoryEntry(entry);
  };

  const performDeleteHistory = async (entry: CalculatorHistoryEntrySummary) => {
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

  const handlePrintQuote = async () => {
    if (!result && quoteItems.length === 0) return;

    let quoteHtml: string;
    let quoteNumber = '';
    try {
      const prefix = quoteProfile.quoteNumberPrefix
        || quoteMarketRules(resolveQuoteMarket(quoteProfile.quoteMarket, quoteProfile.currency)).numberPrefix;
      quoteSequenceRef.current += 1;
      const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '');
      quoteNumber = `${prefix}-${dateStr}-${String(quoteSequenceRef.current).padStart(2, '0')}`;
      quoteHtml = buildQuoteDocumentHtml(buildQuoteHtmlParams(quoteNumber));
    } catch (error) {
      setHistoryFeedback({ kind: 'error', message: error instanceof Error && error.message === 'quoteQuantityPriceUnrepresentable' ? tc('quoteQuantityPriceUnrepresentable') : tc('quotePdfError') });
      return;
    }

    const url = URL.createObjectURL(new Blob([quoteHtml], { type: 'text/html;charset=utf-8' }));
    setQuotePdfPreview({ url, title: quoteNumber, printable: true });
  };

  const handleShareQuote = async () => {
    if ((!result && quoteItems.length === 0) || !user) return;
    setIsSharing(true);
    try {
      quoteSequenceRef.current += 1;
      const prefix =
      quoteProfile.quoteNumberPrefix
      || quoteMarketRules(resolveQuoteMarket(quoteProfile.quoteMarket, quoteProfile.currency)).numberPrefix;
      const seq = quoteSequenceRef.current;
      const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '');
      const quoteNumber = `${prefix}-${dateStr}-${String(seq).padStart(2, '0')}`;

      const quoteHtml = buildQuoteDocumentHtml(buildQuoteHtmlParams(quoteNumber));

      const resp = await calculatorAPI.shareQuote({
        title: quoteNumber,
        html_content: quoteHtml,
      });

      await navigator.clipboard.writeText(resp.share_url);
      setShareCopied(true);
      window.setTimeout(() => setShareCopied(false), 2500);
      setHistoryFeedback({ kind: 'success', message: tc('quoteShareCopied') });
    } catch (err) {
      const errorWithResponse = err as { response?: { data?: { detail?: unknown } }; message?: string };
      setHistoryFeedback({
        kind: 'error',
        message: translateApiError(
          t,
          errorWithResponse.response?.data?.detail ?? errorWithResponse.message,
          errorWithResponse.message === 'quoteQuantityPriceUnrepresentable' ? tc('quoteQuantityPriceUnrepresentable') : tc('quoteShareError'),
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
      const prefix =
      quoteProfile.quoteNumberPrefix
      || quoteMarketRules(resolveQuoteMarket(quoteProfile.quoteMarket, quoteProfile.currency)).numberPrefix;
      const seq = quoteSequenceRef.current;
      const dateStr = new Date().toISOString().slice(0, 10).replace(/-/g, '');
      const quoteNumber = `${prefix}-${dateStr}-${String(seq).padStart(2, '0')}`;

      const quoteHtml = buildQuoteDocumentHtml(buildQuoteHtmlParams(quoteNumber));

      const delivery = await deliverQuotePdf({ title: quoteNumber, html_content: quoteHtml });
      if (delivery.kind === 'preview') {
        setQuotePdfPreview({ url: delivery.url, title: quoteNumber });
      } else {
        setHistoryFeedback({
          kind: 'success',
          message: delivery.kind === 'saved' ? t('profilePage.calculator.quotePdfSaved', { fileName: delivery.fileName }) : tc('quotePdfDownloaded'),
        });
      }
    } catch (err) {
      if (err instanceof QuotePdfSaveError) {
        setHistoryFeedback({ kind: 'error', message: tc('quotePdfSaveFailed') });
        return;
      }
      const errorWithResponse = err as { response?: { data?: { detail?: unknown } }; message?: string };
      setHistoryFeedback({
        kind: 'error',
        message: translateApiError(
          t,
          errorWithResponse.response?.data?.detail ?? errorWithResponse.message,
          errorWithResponse.message === 'quoteQuantityPriceUnrepresentable' ? tc('quoteQuantityPriceUnrepresentable') : tc('quotePdfError'),
        ),
      });
    } finally {
      setIsPdfDownloading(false);
    }
  };

  const handleAddToQuote = async () => {
    if (!result) return;
    let lineItems: QuoteLineItem[];
    try {
      lineItems = buildQuoteLineItems(
        t,
        form,
        result,
        parsedGcode,
        selectedMaterial,
        parsedJobs,
        materialLines,
        jobConfigs,
      );
    } catch (error) {
      setHistoryFeedback({ kind: 'error', message: error instanceof Error && error.message === 'quoteQuantityPriceUnrepresentable' ? tc('quoteQuantityPriceUnrepresentable') : tc('quoteSaveWorkspaceError') });
      return;
    }
    const included = buildQuoteIncludedItems(t, result);
    const calculationSnapshot = buildHistoryPayload(
      form, result, parsedGcode, selectedMaterial, materialLines, parsedJobs, jobConfigs, printerEconomics, quoteProfile.currency,
    );
    const newItems = lineItems.map((lineItem) => ({
      id: crypto.randomUUID(),
      lineItem,
      includedItems: included,
      calculationSnapshot,
    }));
    setQuoteItems((prev) => [...prev, ...newItems]);
    const historySaved = await saveCurrentResultToHistory();
    setHistoryFeedback({
      kind: historySaved ? 'success' : 'error',
      message: historySaved ? tc('addedToQuoteAndHistory') : tc('addedToQuoteHistoryError'),
    });
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

  const getQuoteDisclosureContext = () => {
    const currentSnapshot = result
      ? buildHistoryPayload(form, result, parsedGcode, selectedMaterial, materialLines, parsedJobs, jobConfigs, printerEconomics, quoteProfile.currency)
      : null;
    const snapshots = quoteItems.length > 0
      ? quoteItems.map((item) => item.calculationSnapshot)
      : currentSnapshot ? [currentSnapshot] : [];
    const uniqueSources = [...new Map(snapshots.map((snapshot) => [JSON.stringify(snapshot), snapshot])).values()];
    const snapshot = uniqueSources.length === 1 ? uniqueSources[0] : null;
    const baseTotal = quoteItems.length > 0
      ? quoteItems.reduce((sum, item) => sum + item.lineItem.totalPrice, 0)
      : Number(result?.cost_final ?? result?.cost_total ?? 0);
    const complete = getCompleteQuoteDisclosureSnapshot(snapshot as unknown as QuoteDisclosureSnapshot | null);
    const disclosureLines = quoteItems.length > 0
      ? quoteItems.map((item) => item.lineItem)
      : result
        ? buildQuoteLineItems(t, form, result, parsedGcode, selectedMaterial, parsedJobs, materialLines, jobConfigs)
        : [];
    const eligible = Boolean(complete) && Math.round(Number(complete?.result.cost_final) * 100) === Math.round(baseTotal * 100)
      && isQuoteDisclosureBoundToLines(snapshot as unknown as QuoteDisclosureSnapshot | null, disclosureLines.map((line) => ({
        quantity: line.quantity, unit: 'pcs', unitPrice: line.unitPrice,
      })), quoteLinesFingerprint(disclosureLines.map((line) => ({ quantity: line.quantity, unit: 'pcs', unitPrice: line.unitPrice }))));
    return {
      snapshot,
      uniqueSources,
      baseTotal,
      fullSnapshot: eligible ? complete : null,
      sourceEligible: eligible,
      disclosureLines,
    };
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
      grandTotal = items.reduce((sum, item) => sum + item.totalPrice, 0);
    } else {
      items = [];
      includedItems = [];
      grandTotal = 0;
    }

    const context = getQuoteDisclosureContext();
    const sourceSnapshot = context.snapshot as unknown as QuoteDisclosureSnapshot | null;
    const baseTotal = grandTotal;
    const sameSavedCalculation = context.sourceEligible;
    let taxDisclosure: BuildQuoteHtmlParams['taxDisclosure'] = null;
    let taxTotal = 0;
    let savedTaxAmount = 0;
    let taxSplitUnavailable = false;
    if (sameSavedCalculation && sourceSnapshot) {
      const tax = getSnapshotTaxDisclosure(sourceSnapshot, baseTotal);
      if (tax.available && tax.taxAmount && tax.netAmount !== null) {
        savedTaxAmount = tax.taxAmount;
        if (quoteTaxMode === 'included') {
          taxDisclosure = { kind: quoteTaxKind, mode: quoteTaxMode, amount: tax.taxAmount, netAmount: tax.netAmount };
        } else if (quoteTaxMode === 'separate') {
          const netLines = removeEmbeddedTaxFromLines(items, tax.taxAmount);
          if (netLines) {
            items = netLines.map((line) => ({ ...line, sourceData: line.sourceData ?? null }));
            taxDisclosure = { kind: quoteTaxKind, mode: quoteTaxMode, amount: tax.taxAmount, netAmount: tax.netAmount };
            taxTotal = tax.taxAmount;
          } else taxSplitUnavailable = true;
        }
      }
    }
    const delivery = Math.round((Number(quoteCustomerDelivery) || 0) * 100 + Number.EPSILON) / 100;
    const withDelivery = replaceCustomerDeliveryLine(items, delivery, t('profilePage.calculator.quoteDelivery'));
    if (withDelivery) items = withDelivery.map((line) => ({ ...line, sourceData: line.sourceData ?? null }));
    const workBreakdown = quoteShowBreakdown && sameSavedCalculation
      ? buildQuoteWorkBreakdown({ snapshot: sourceSnapshot, positionsTotal: sumQuotePositions(items), positionsIncludeTax: taxTotal <= 0, customerDelivery: delivery })
      : null;
    return {
      t,
      language: i18n.language,
      items,
      workBreakdown,
      includedItems,
      grandTotal: baseTotal + delivery,
      parties: quoteParties,
      formatCurrency,
      quoteNumber,
      taxRatePercent: form.taxRatePercent,
      taxDisclosure,
      taxTotal,
      customerDeliveryAmount: delivery,
      calculationSnapshot: sameSavedCalculation ? context.snapshot : null,
      quoteSources: context.uniqueSources,
      quoteDisclosure: {
        taxKind: savedTaxAmount > 0 ? quoteTaxKind : null,
        taxMode: savedTaxAmount > 0 ? quoteTaxMode : null,
        taxAmount: savedTaxAmount,
        customerDelivery: delivery,
        showCostBreakdown: quoteShowBreakdown,
        costBreakdownNote: quoteBreakdownNote,
        invalidated: false,
        baseLineFingerprint: quoteLinesFingerprint(restoreQuoteBaseLines(items).map((line) => ({
          quantity: line.quantity, unit: 'pcs', unitPrice: line.unitPrice,
        }))),
      },
      showCostBreakdown: quoteShowBreakdown,
      costBreakdownNote: quoteBreakdownNote,
      taxSplitUnavailable,
    };
  };

  const handleQuoteCustomerSelection = (selection: string) => {
    setQuoteCustomerSelection(selection);
    if (!selection.startsWith('customer:')) return;
    const customerId = Number(selection.slice('customer:'.length));
    const customer = quoteCustomersQuery.data?.items.find((item) => item.id === customerId);
    if (!customer) return;
    setQuoteParties((prev) => ({
      ...prev,
      buyerName: customer.name,
      buyerInn: customer.inn ?? '',
      buyerAddress: customer.address ?? '',
    }));
  };

  const handleSaveQuoteToWorkspace = async () => {
    if ((!result && quoteItems.length === 0) || !user) return;
    let quoteParams: BuildQuoteHtmlParams;
    try {
      quoteParams = buildQuoteHtmlParams('{{CRM_QUOTE_NUMBER}}');
    } catch (error) {
      setHistoryFeedback({ kind: 'error', message: error instanceof Error && error.message === 'quoteQuantityPriceUnrepresentable' ? tc('quoteQuantityPriceUnrepresentable') : tc('quoteSaveWorkspaceError') });
      return;
    }
    if (quoteParams.items.length === 0) return;
    if (quoteParams.taxSplitUnavailable) {
      setHistoryFeedback({ kind: 'error', message: tc('quoteTaxSplitUnrepresentable') });
      return;
    }

    const selectedCustomerId = quoteCustomerSelection.startsWith('customer:')
      ? Number(quoteCustomerSelection.slice('customer:'.length))
      : null;
    const shouldCreateCustomer = quoteCustomerSelection === 'new' && Boolean(quoteParties.buyerName.trim());
    const calculationSnapshot = quoteParams.calculationSnapshot
      ? {
          ...quoteParams.calculationSnapshot,
          ...(quoteParams.quoteSources && quoteParams.quoteSources.length > 1 ? { quote_sources: quoteParams.quoteSources } : {}),
          quote_disclosure: quoteParams.quoteDisclosure,
        }
      : quoteParams.quoteSources?.length
        ? { quote_sources: quoteParams.quoteSources, quote_disclosure: quoteParams.quoteDisclosure }
        : { quote_disclosure: quoteParams.quoteDisclosure };
    const preflightRequest = currentPreflightRequest();

    try {
      await saveQuoteToWorkspaceMutation.mutateAsync({
        title: quoteParams.items[0]?.title || tc('quoteDefaultItemTitle'),
        currency: quoteProfile.currency,
        valid_until: addDays(
          new Date(),
          Math.max(1, Math.round(quoteParties.validityDays || DEFAULT_QUOTE_PROFILE.validityDays)),
        ).toISOString().slice(0, 10),
        customer_id: selectedCustomerId,
        new_customer: shouldCreateCustomer
          ? {
              name: quoteParties.buyerName.trim(),
              inn: quoteParties.buyerInn.trim() || null,
              address: quoteParties.buyerAddress.trim() || null,
            }
          : null,
        seller_snapshot: {
          name: quoteParties.sellerName,
          inn: quoteParties.sellerInn,
          phone: quoteParties.sellerPhone,
        },
        customer_snapshot: {
          name: quoteParties.buyerName,
          inn: quoteParties.buyerInn,
          address: quoteParties.buyerAddress,
        },
        calculation_snapshot: calculationSnapshot
          ? {
              ...calculationSnapshot,
              operational_preflight: preflightRequest
                ? {
                    request: preflightRequest,
                    result: preflightMutation.data ?? null,
                  }
                : null,
            }
          : null,
        payment_terms: quoteParties.paymentTerms,
        disclaimer_mode: 'not_offer',
        tax_total: quoteParams.taxTotal ?? 0,
        html_content: buildQuoteDocumentHtml(quoteParams),
        lines: quoteParams.items.map((item, index) => ({
          title: item.title,
          details: item.details,
          quantity: item.quantity,
          unit: 'pcs',
          unit_price: item.unitPrice,
          source_data: { ...(item.sourceData ?? {}), position: index + 1, source: estimateSource },
        })),
      });
      setHistoryFeedback({ kind: 'success', message: tc('quoteSavedToWorkspace') });
      setQuoteModalOpen(false);
    } catch (error) {
      const errorWithResponse = error as { response?: { data?: { detail?: unknown } }; message?: string };
      setHistoryFeedback({
        kind: 'error',
        message: translateApiError(
          t,
          errorWithResponse.response?.data?.detail ?? errorWithResponse.message,
          tc('quoteSaveWorkspaceError'),
        ),
      });
    }
  };

  const handleOpenQuote = () => {
    setQuoteCustomerDelivery(quoteProfile.customerDeliveryAmount > 0 ? String(quoteProfile.customerDeliveryAmount) : '');
    setQuoteTaxKind(quoteProfile.taxKind);
    setQuoteTaxMode(quoteProfile.taxMode);
    setQuoteShowBreakdown(quoteProfile.showCostBreakdown);
    setQuoteBreakdownNote(quoteProfile.costBreakdownNote);
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
        calculationSnapshot: buildHistoryPayload(
          form, result, parsedGcode, selectedMaterial, materialLines, parsedJobs, jobConfigs, printerEconomics, quoteProfile.currency,
        ),
      })));
    }
    setQuoteModalOpen(true);
  };

  const handleCloudSave = async () => {
    setIsCloudBusy(true);
    try {
      const profile = await calculatorAPI.updateProfile({
        seller_name: quoteProfile.sellerName,
        seller_inn: quoteProfile.sellerInn,
        seller_phone: quoteProfile.sellerPhone,
        seller_registration_id: quoteProfile.sellerRegistrationId,
        seller_tax_code: quoteProfile.sellerTaxCode,
        seller_address: quoteProfile.sellerAddress,
        seller_bank_details: quoteProfile.sellerBankDetails,
        quote_market: quoteProfile.quoteMarket,
        payment_terms: quoteProfile.paymentTerms,
        validity_days: quoteProfile.validityDays,
        disclaimer_mode: 'not_offer',
        currency: quoteProfile.currency,
        quote_number_prefix: quoteProfile.quoteNumberPrefix,
      });
      queryClient.setQueryData(USER_PREFERENCES_QUERY_KEY, {
        currency: normalizeCurrency(profile.currency),
      });
      setQuoteProfileFeedback({ kind: 'success', message: tc('cloudSaveSuccess') });
    } catch (error) {
      setQuoteProfileFeedback({
        kind: 'error',
        message: translateApiError(t, error, tc('cloudSaveError')),
      });
    } finally {
      setIsCloudBusy(false);
    }
  };

  const handleCloudLoad = async () => {
    setIsCloudBusy(true);
    try {
      const profile = await calculatorAPI.getProfile();
      setQuoteProfile((prev) => ({
        ...prev,
        sellerName: profile.seller_name,
        sellerInn: profile.seller_inn,
        sellerPhone: profile.seller_phone,
        sellerRegistrationId: profile.seller_registration_id,
        sellerTaxCode: profile.seller_tax_code,
        sellerAddress: profile.seller_address,
        sellerBankDetails: profile.seller_bank_details,
        quoteMarket: profile.quote_market,
        paymentTerms: profile.payment_terms,
        validityDays: profile.validity_days,
        disclaimerMode: 'not_offer',
        currency: normalizeCurrency(profile.currency),
        quoteNumberPrefix: profile.quote_number_prefix,
      }));
      saveStoredQuoteProfile({
        sellerName: profile.seller_name,
        sellerInn: profile.seller_inn,
        sellerPhone: profile.seller_phone,
        sellerRegistrationId: profile.seller_registration_id,
        sellerTaxCode: profile.seller_tax_code,
        sellerAddress: profile.seller_address,
        sellerBankDetails: profile.seller_bank_details,
        quoteMarket: profile.quote_market,
        paymentTerms: profile.payment_terms,
        validityDays: profile.validity_days,
        disclaimerMode: 'not_offer',
        currency: normalizeCurrency(profile.currency),
        quoteNumberPrefix: profile.quote_number_prefix,
        customerDeliveryAmount: quoteProfile.customerDeliveryAmount,
        taxKind: quoteProfile.taxKind,
        taxMode: quoteProfile.taxMode,
        showCostBreakdown: quoteProfile.showCostBreakdown,
        costBreakdownNote: quoteProfile.costBreakdownNote,
      });
      setQuoteProfileFeedback({ kind: 'success', message: tc('cloudLoadSuccess') });
    } catch (error) {
      setQuoteProfileFeedback({
        kind: 'error',
        message: translateApiError(t, error, tc('cloudLoadError')),
      });
    } finally {
      setIsCloudBusy(false);
    }
  };

  const handlePlatformDefaultsReset = async () => {
    setIsCloudBusy(true);
    try {
      const profile = await calculatorAPI.resetProfileDefaults();
      const staticSettings = profileToStaticSettings(profile);
      setForm((prev) => ({ ...prev, ...staticSettings }));
      saveStoredCalculatorDefaults(staticSettings);
      toast.success(tc('platformDefaultsApplied'));
    } catch (error) {
      toast.error(translateApiError(t, error, tc('platformDefaultsError')));
    } finally {
      setIsCloudBusy(false);
    }
  };

  useEffect(() => {
    if (parsedJobs.length === 0 || catalogFilamentsPending || spoolsQuery.isPending) {
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
        color: spool.filament.color_hex || spool.filament.color_name,
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
      const parsedMaterials: CalculatorParsedMaterial[] = usedMaterials.length > 0
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
          catalogFilaments,
          (candidate) => candidate,
          (filament) => ({
            filamentId: filament.id,
            name: filament.name,
            vendor: filament.brand_name,
            materialType: filament.material_type,
            color: filament.color_hex || filament.color_name,
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
          evidenceSource: 'gcode',
          lengthMm: material.length_mm ?? null,
          volumeCm3: material.volume_cm3 ?? null,
          mappingSource: 'unresolved',
          requiresSpoolChoice: false,
          priceResolved: false,
          role_weights_g: {
            ...(material.support_weight_g != null
              ? { support: material.support_weight_g }
              : {}),
            ...(material.brim_weight_g != null
              ? { brim: material.brim_weight_g }
              : {}),
            ...(material.prime_tower_weight_g != null
              ? { prime_tower: material.prime_tower_weight_g }
              : {}),
          },
          role_weight_source: material.support_weight_g != null
            || material.brim_weight_g != null
            || material.prime_tower_weight_g != null
            ? 'gcode_extrusion_roles'
            : null,
        };

        if (match?.source === 'user') {
          const candidate = match.match.item;
          baseLine.filament_id = candidate.filamentId;
          baseLine.mappingSource = 'automatic';
          const catalogFilament = catalogFilaments.find(
            (filament) => filament.id === candidate.filamentId,
          );
          // The filament is identified exactly, so a spool of that same filament is not a
          // guess. One spool is bound outright; several mean the person picks which one
          // the remaining weight comes off.
          const ownSpools = availableSpools.filter(
            (item) => item.filament_id === candidate.filamentId,
          );
          const ownSpool = ownSpools.length === 1 ? ownSpools[0] : null;
          if (ownSpool) {
            const defaults = deriveUserSpoolDefaults(ownSpool);
            const priceCurrency = resolveUserSpoolPriceCurrency(ownSpool);
            const currencyMatches = !priceCurrency || priceCurrency === calcCurrencyRef.current;
            baseLine.selectionValue = `spool:${ownSpool.id}`;
            baseLine.spool_id = ownSpool.id;
            baseLine.spool_price = currencyMatches ? (defaults.spoolPrice ?? 0) : 0;
            baseLine.spool_weight_kg = defaults.spoolWeightKg ?? 1;
            baseLine.price_source = ownSpool.price != null ? 'spool' : 'filamenthub';
            baseLine.priceResolved = currencyMatches
              && defaults.spoolPrice != null
              && (ownSpool.price == null || defaults.spoolWeightKg != null);
          } else if (ownSpools.length > 1) {
            baseLine.requiresSpoolChoice = true;
            if (catalogFilament) {
              baseLine.selectionValue = `filament:${catalogFilament.id}`;
            }
          } else if (catalogFilament) {
            const defaults = deriveCatalogFilamentDefaults(catalogFilament);
            const brandCurrency = catalogFilament.currency
              ? normalizeCurrency(catalogFilament.currency)
              : null;
            const currencyMatches =
              !brandCurrency || brandCurrency === calcCurrencyRef.current;
            baseLine.selectionValue = `filament:${catalogFilament.id}`;
            baseLine.spool_price = currencyMatches ? (defaults.spoolPrice ?? 0) : 0;
            baseLine.spool_weight_kg = defaults.spoolWeightKg ?? 1;
            baseLine.price_source = 'filamenthub';
            baseLine.priceResolved = currencyMatches && defaults.spoolPrice != null;
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
          baseLine.mappingSource = 'automatic';
          baseLine.priceResolved = currencyMatches && defaults.spoolPrice != null;
        } else if ((material.slicer_profile_price_per_kg ?? 0) > 0) {
          // Slicer profiles carry whatever placeholder their author left there — 20 per
          // kilogram is common. Offer it as a starting number, but never let it pass for a
          // confirmed price: it goes straight into what the customer is charged.
          baseLine.spool_price = material.slicer_profile_price_per_kg!;
          baseLine.spool_weight_kg = 1;
          baseLine.price_source = 'slicer';
          baseLine.priceResolved = false;
        }
        nextLines.push(baseLine);
      });
    }

    lastBuiltMaterialJobsKeyRef.current = jobsKey;
    setMaterialLines(nextLines);
  }, [
    availableSpools,
    catalogFilaments,
    catalogFilamentsPending,
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
      catalogFilamentsPending ||
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
        color: spool.filament.color_hex || spool.filament.color_name,
        spoolIds: [],
      };
      candidate.spoolIds.push(spool.id);
      spoolCandidatesByFilamentId.set(candidate.filamentId, candidate);
    }

    const prioritizedMatch = findPrioritizedMaterialMatch(
      primaryMaterial,
      Array.from(spoolCandidatesByFilamentId.values()),
      catalogFilaments,
      (candidate) => candidate,
      (filament) => ({
        filamentId: filament.id,
        name: filament.name,
        vendor: filament.brand_name,
        materialType: filament.material_type,
        color: filament.color_hex || filament.color_name,
      }),
    );

    if (prioritizedMatch?.source === 'user') {
      const spoolMatch = prioritizedMatch.match;
      priceManuallyEditedRef.current = false;
      setSelectedSpoolId('');
      setForm((prev) => ({
        ...prev,
        selectedFilamentId: spoolMatch.item.filamentId,
      }));
      setAutoMaterialMatch({
        confidence: spoolMatch.confidence,
        method: spoolMatch.method,
        source: 'spool',
        requiresSpoolChoice: true,
      });
      return;
    }

    if (prioritizedMatch?.source === 'catalog') {
      const catalogMatch = prioritizedMatch.match;
      priceManuallyEditedRef.current = false;
      setSelectedSpoolId('');
      setForm((prev) => ({ ...prev, selectedFilamentId: catalogMatch.item.id }));
      setAutoMaterialMatch({
        confidence: catalogMatch.confidence,
        method: catalogMatch.method,
        source: 'catalog',
      });
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
    catalogFilaments,
    catalogFilamentsPending,
    parsedGcode,
    spoolsQuery.isPending,
  ]);

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

  const preflightUiLines: MaterialPreflightUiLine[] = materialLines.length > 0
    ? materialLines.map((line) => ({
        lineId: line.line_id,
        label: line.label || (line.tool_index != null ? `T${line.tool_index}` : tc('unknownMaterial')),
        toolIndex: line.tool_index ?? null,
        filamentId: line.filament_id ?? null,
        selectedSpoolIds: preflightSpoolIdsByLine[line.line_id]
          ?? (line.spool_id ? [line.spool_id] : []),
      }))
    : form.weightG > 0
      ? [{
          lineId: 'manual',
          label: selectedSpool?.filament
            ? buildFilamentLabel(selectedSpool.filament)
            : selectedCatalogFilament
              ? buildFilamentLabel(selectedCatalogFilament)
              : tc('manualMaterialLine'),
          toolIndex: null,
          filamentId: selectedSpool?.filament_id ?? selectedCatalogFilament?.id ?? null,
          selectedSpoolIds: preflightSpoolIdsByLine.manual
            ?? (selectedSpool ? [selectedSpool.id] : []),
        }]
      : [];

  const quoteDisclosureContext = getQuoteDisclosureContext();
  const quoteTaxAvailable = quoteDisclosureContext.sourceEligible
    && getSnapshotTaxDisclosure(quoteDisclosureContext.snapshot as unknown as QuoteDisclosureSnapshot | null, quoteDisclosureContext.baseTotal).available;
  const quoteTaxSnapshot = quoteDisclosureContext.snapshot as unknown as QuoteDisclosureSnapshot | null;
  const taxPreview = quoteTaxAvailable ? getSnapshotTaxDisclosure(quoteTaxSnapshot, quoteDisclosureContext.baseTotal) : null;
  const quoteByWorkAvailable = quoteDisclosureContext.sourceEligible;
  const quoteTaxSeparateAvailable = Boolean(taxPreview?.available && taxPreview.taxAmount
    && removeEmbeddedTaxFromLines(quoteDisclosureContext.disclosureLines, taxPreview.taxAmount));

  return (
    <div className="space-y-6">
      {trialDaysLeft !== null && (
        <div className="inline-flex w-fit items-center gap-1.5 rounded-full border border-cyan-400/20 bg-cyan-500/10 px-3 py-1 text-xs text-cyan-200">
          <Clock className="h-3.5 w-3.5 shrink-0" />
          <span>{t('profilePage.calculator.trialBanner', { days: trialDaysLeft })}</span>
        </div>
      )}
      {!embedded && <section className="relative overflow-hidden rounded-[2rem] bg-[linear-gradient(180deg,rgba(15,23,42,0.88),rgba(15,23,42,0.72))] shadow-[0_30px_90px_-50px_rgba(15,23,42,0.95)] backdrop-blur-xl ring-1 ring-white/5">
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
              <MetricTile
                label={tc('workspaceSavedEstimates')}
                value={historyQuery.isPending ? '—' : String(historyQuery.data?.pages[0]?.total ?? 0)}
              />
              <MetricTile label={tc('workspaceQuoteDraft')} value={String(quoteItems.length)} />
              <MetricTile label={tc('workspaceCurrentJobs')} value={String(currentJobCount)} />
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
      </section>}

      {embedded && historyFeedback ? (
        <div
          className={`rounded-[1.25rem] border px-4 py-3 text-sm ${
            historyFeedback.kind === 'success'
              ? 'border-emerald-400/25 bg-emerald-500/10 text-emerald-100'
              : 'border-red-400/25 bg-red-500/10 text-red-100'
          }`}
        >
          {historyFeedback.message}
        </div>
      ) : null}

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
          preflightLines={preflightUiLines}
          preflightResult={preflightMutation.data ?? null}
          preflightSafetyBufferPercent={preflightSafetyBufferPercent}
          preflightError={preflightError}
          isPreflightLoading={preflightMutation.isPending}
          batchParseWarning={batchParseWarning}
          materialLinesError={materialLinesError}
          approximatePriceLabels={approximatePriceLabels}
          dragActive={dragActive}
          filaments={catalogFilaments}
          isFilamentsLoading={catalogFilamentsPending}
          filamentsLoadError={catalogFilamentsError ? tc('materialsLoadError') : null}
          spools={availableSpools}
          isSpoolsLoading={spoolsQuery.isPending}
          spoolsLoadError={spoolsQuery.isError ? tc('spoolsLoadError') : null}
          isParsingGcode={parseGcodeMutation.isPending}
          gcodeProcessingProgress={gcodeProcessingProgress}
          parseGcodeError={parseGcodeError}
          onCancelGcodeProcessing={cancelGcodeProcessing}
          onRetryGcodeProcessing={retryGcodeProcessing}
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
          onSlicePick={handleSlicePick}
          pickingSliceId={pickedSliceId}
          pickingSliceProgress={sliceProgress}
          goneSourceKeys={goneSourceKeys}
          printers={printers}
          selectedPrinterId={selectedPrinterId}
          printerEconomics={printerEconomics}
          jobPrinterEconomics={jobPrinterEconomics}
          accountEconomicsReadiness={accountEconomicsReadiness}
          economicsReadinessLoading={
            accountEconomicsLoading
            || printerEconomicsQuery.isLoading
            || jobPrinterEconomicsQuery.isLoading
            || accountEconomicsSaving
          }
          economicsReadinessError={
            accountEconomicsError
            || printerEconomicsQuery.isError
            || jobPrinterEconomicsQuery.isError
          }
          printerPickedFrom={printerPickedFrom}
          onPrinterSelect={handlePrinterSelect}
          economicsPrinterId={economicsPrinterId}
          onEconomicsPrinterChange={setEconomicsPrinterId}
          insidePlugin={isPluginEmbed()}
          onJobSelect={handleJobSelect}
          onJobRemove={handleRemoveParsedJob}
          onJobConfigChange={handleJobConfigChange}
          onMaterialLineSelection={handleMaterialLineSelection}
          onMaterialLinePriceChange={handleMaterialLinePriceChange}
          onMaterialLineSpoolWeightChange={handleMaterialLineSpoolWeightChange}
          onPreflightSafetyBufferChange={handlePreflightBufferChange}
          onPreflightSpoolIdsChange={handlePreflightSpoolIdsChange}
          onPreflightRefresh={() => runPreflight()}
          onDragStateChange={setDragActive}
          quoteProfile={quoteProfile}
          embedded={embedded}
          staticSettingsOpen={staticSettingsOpen}
          quoteProfileOpen={quoteProfileOpen}
          onStaticSettingsOpenChange={setStaticSettingsOpen}
          onQuoteProfileOpenChange={setQuoteProfileOpen}
          onQuoteProfileChange={updateQuoteProfileField}
          onOpenQuote={handleOpenQuote}
          onAddToQuote={handleAddToQuote}
          quoteItemCount={quoteItems.length}
          onSaveToHistory={handleSaveToHistory}
          onCloudSave={handleCloudSave}
          onCloudLoad={handleCloudLoad}
          quoteProfileFeedback={quoteProfileFeedback}
          onPlatformDefaultsReset={handlePlatformDefaultsReset}
          isCloudBusy={isCloudBusy}
          formatCurrency={formatCurrency}
        />
      ) : (
        <HistoryView
          entries={historyEntries}
          historyLoadError={historyLoadError}
          historyLoadMoreError={historyQuery.isFetchNextPageError ? tc('historyLoadMoreError') : null}
          isDeletingHistory={deleteHistoryMutation.isPending}
          restoringEntryId={restoringHistoryEntryId}
          failedRestoreEntryId={failedRestoreHistoryEntryId}
          isLoading={historyQuery.isPending}
          isLoadingMore={historyQuery.isFetchingNextPage}
          hasMore={historyQuery.hasNextPage}
          total={historyQuery.data?.pages[0]?.total ?? 0}
          onRetryLoad={() => void historyQuery.refetch()}
          onLoadMore={() => void historyQuery.fetchNextPage()}
          onDeleteEntry={handleDeleteHistory}
          onRestoreEntry={handleRestoreHistory}
          formatCurrency={formatCurrency}
        />
      )}

      <QuoteModal
        isOpen={quoteModalOpen}
        embedded={embedded}
        source={estimateSource}
        quoteParties={quoteParties}
        result={result}
        quoteItems={quoteItems}
        customers={quoteCustomersQuery.data?.items ?? []}
        customersLoading={quoteCustomersQuery.isPending}
        customerSelection={quoteCustomerSelection}
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
        onCustomerSelection={handleQuoteCustomerSelection}
        onSaveToWorkspace={() => void handleSaveQuoteToWorkspace()}
        onPrint={handlePrintQuote}
        onShare={handleShareQuote}
        onDownloadPdf={handleDownloadPdf}
        isSharing={isSharing}
        shareCopied={shareCopied}
        isPdfDownloading={isPdfDownloading}
        isSavingToWorkspace={saveQuoteToWorkspaceMutation.isPending}
        isLoggedIn={!!user}
        formatCurrency={formatCurrency}
        customerDelivery={quoteCustomerDelivery}
        onCustomerDeliveryChange={setQuoteCustomerDelivery}
        byWorkAvailable={quoteByWorkAvailable}
        currencySymbol={currencySymbol(quoteProfile.currency)}
        taxDisclosureAvailable={quoteTaxAvailable}
        taxSeparateAvailable={quoteTaxSeparateAvailable}
        taxKind={quoteTaxKind}
        onTaxKindChange={setQuoteTaxKind}
        taxMode={quoteTaxMode}
        onTaxModeChange={setQuoteTaxMode}
        showCostBreakdown={quoteShowBreakdown}
        onShowCostBreakdownChange={setQuoteShowBreakdown}
        costBreakdownNote={quoteBreakdownNote}
        onCostBreakdownNoteChange={setQuoteBreakdownNote}
      />

      {quotePdfPreview && <QuotePdfPreview url={quotePdfPreview.url} title={quotePdfPreview.title} printable={quotePdfPreview.printable} onClose={() => setQuotePdfPreview(null)} />}

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
  embedded: boolean;
  staticSettingsOpen: boolean;
  quoteProfileOpen: boolean;
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
  preflightLines: MaterialPreflightUiLine[];
  preflightResult: CalculatorPreflightResponse | null;
  preflightSafetyBufferPercent: number;
  preflightError: string | null;
  isPreflightLoading: boolean;
  batchParseWarning: string | null;
  materialLinesError: string | null;
  approximatePriceLabels: string[];
  dragActive: boolean;
  filaments: Filament[];
  isFilamentsLoading: boolean;
  filamentsLoadError: string | null;
  spools: UserSpool[];
  isSpoolsLoading: boolean;
  spoolsLoadError: string | null;
  isParsingGcode: boolean;
  gcodeProcessingProgress: GcodeProcessingProgress | null;
  parseGcodeError: string | null;
  onCancelGcodeProcessing: () => void;
  onRetryGcodeProcessing: () => void;
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
  onStaticSettingsOpenChange: (open: boolean) => void;
  onQuoteProfileOpenChange: (open: boolean) => void;
  onFileSelect: (files: FileList | null) => Promise<void>;
  onSlicePick: (slice: OrcaSliceReport) => void;
  pickingSliceId: number | null;
  pickingSliceProgress: number | null;
  goneSourceKeys: string[];
  printers: PhysicalPrinter[];
  selectedPrinterId: number | '';
  printerEconomics: PrinterEconomics | null;
  jobPrinterEconomics: Map<number, PrinterEconomics>;
  accountEconomicsReadiness: EconomicsReadiness | null;
  economicsReadinessLoading: boolean;
  economicsReadinessError: boolean;
  printerPickedFrom: string | null;
  onPrinterSelect: (printerId: number | '') => void;
  economicsPrinterId: number | '';
  onEconomicsPrinterChange: (printerId: number | '') => void;
  /** The slice list needs the plugin's bridge to reach a file at all. */
  insidePlugin: boolean;
  onJobSelect: (jobKey: string) => void;
  onJobRemove: (jobKey: string) => void;
  onJobConfigChange: (
    jobKey: string,
    patch: Partial<Omit<CalculatorJobConfig, 'jobKey'>>,
  ) => void;
  onMaterialLineSelection: (lineId: string, selectionValue: string) => void;
  onMaterialLinePriceChange: (lineId: string, value: number) => void;
  onMaterialLineSpoolWeightChange: (lineId: string, value: number) => void;
  onPreflightSafetyBufferChange: (value: number) => void;
  onPreflightSpoolIdsChange: (lineId: string, spoolIds: number[]) => void;
  onPreflightRefresh: () => void;
  onDragStateChange: (active: boolean) => void;
  onOpenQuote: () => void;
  onAddToQuote: () => void;
  quoteItemCount: number;
  onSaveToHistory: () => Promise<void>;
  onCloudSave: () => Promise<void>;
  onCloudLoad: () => Promise<void>;
  quoteProfileFeedback: { kind: 'success' | 'error'; message: string } | null;
  onPlatformDefaultsReset: () => Promise<void>;
  isCloudBusy: boolean;
  formatCurrency: (value: number | null | undefined) => string;
}

const CalculatorView: React.FC<CalculatorViewProps> = ({
  embedded,
  staticSettingsOpen,
  quoteProfileOpen,
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
  preflightLines,
  preflightResult,
  preflightSafetyBufferPercent,
  preflightError,
  isPreflightLoading,
  batchParseWarning,
  materialLinesError,
  approximatePriceLabels,
  dragActive,
  filaments,
  isFilamentsLoading,
  filamentsLoadError,
  spools,
  isSpoolsLoading,
  spoolsLoadError,
  isParsingGcode,
  gcodeProcessingProgress,
  parseGcodeError,
  onCancelGcodeProcessing,
  onRetryGcodeProcessing,
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
  onStaticSettingsOpenChange,
  onQuoteProfileOpenChange,
  onFileSelect,
  onSlicePick,
  pickingSliceId,
  pickingSliceProgress,
  goneSourceKeys,
  printers,
  selectedPrinterId,
  printerEconomics,
  jobPrinterEconomics,
  accountEconomicsReadiness,
  economicsReadinessLoading,
  economicsReadinessError,
  printerPickedFrom,
  onPrinterSelect,
  economicsPrinterId,
  onEconomicsPrinterChange,
  insidePlugin,
  onJobSelect,
  onJobRemove,
  onJobConfigChange,
  onMaterialLineSelection,
  onMaterialLinePriceChange,
  onMaterialLineSpoolWeightChange,
  onPreflightSafetyBufferChange,
  onPreflightSpoolIdsChange,
  onPreflightRefresh,
  onDragStateChange,
  onOpenQuote,
  onAddToQuote,
  quoteItemCount,
  onSaveToHistory,
  onCloudSave,
  onCloudLoad,
  quoteProfileFeedback,
  onPlatformDefaultsReset,
  isCloudBusy,
  formatCurrency,
}) => {
  const { t, i18n } = useTranslation();
  const tc = (key: string) => translateCalculator(t, key);
  const gcodeProgressPercent = getGcodeProcessingPercent(gcodeProcessingProgress) ?? 0;
  const gcodeProcessingLabel = gcodeProcessingProgress
    ? tc(GCODE_PHASE_LABEL_KEYS[gcodeProcessingProgress.phase])
        .replace('{{current}}', String(gcodeProcessingProgress.processedFiles))
        .replace('{{total}}', String(gcodeProcessingProgress.totalFiles))
    : '';
  const gcodeProcessingDetail = (() => {
    if (!gcodeProcessingProgress) return '';
    if (gcodeProcessingProgress.phase === 'reading') {
      return tc('gcodeReadingDetail').replace('{{file}}', gcodeProcessingProgress.currentFileName ?? '');
    }
    if (gcodeProcessingProgress.phase === 'counting') {
      return tc('gcodeCountingDetail')
        .replace('{{file}}', gcodeProcessingProgress.currentFileName ?? '')
        .replace(
          '{{percent}}',
          String(Math.round((gcodeProcessingProgress.countedFraction ?? 0) * 100)),
        );
    }
    return tc('gcodeAnalysisDetail')
      .replace('{{current}}', String(gcodeProcessingProgress.processedFiles))
      .replace('{{total}}', String(gcodeProcessingProgress.totalFiles));
  })();
  const [advancedSettingsOpen, setAdvancedSettingsOpen] = useState(false);
  const [postprocessChecked, setPostprocessChecked] = useState<Record<string, boolean>>({});
  const [customPresets, setCustomPresets] = useState<PricingPreset[]>(() => loadCustomPricingPresets());
  const [presetNameInput, setPresetNameInput] = useState('');
  const [openObjectJobKeys, setOpenObjectJobKeys] = useState<Set<string>>(new Set());
  const [openMaterialRowIds, setOpenMaterialRowIds] = useState<Set<string>>(new Set());
  const resultsRef = useRef<HTMLDivElement | null>(null);
  const scrollToResultAfterEstimateRef = useRef(false);

  // A row that still needs a price opens by itself so the missing input is reachable
  // without hunting for it in a long list.
  useEffect(() => {
    setOpenMaterialRowIds((current) => {
      const availableIds = new Set(materialLines.map((line) => line.line_id));
      return new Set([...current].filter((lineId) => availableIds.has(lineId)));
    });
  }, [materialLines]);

  useEffect(() => {
    if (!scrollToResultAfterEstimateRef.current || (!result && !estimateError)) return;
    scrollToResultAfterEstimateRef.current = false;
    resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [estimateError, result]);

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
    ? autoMaterialMatch.method === 'stable_id'
      ? tc('materialIdentityExact')
      : autoMaterialMatch.method === 'managed_preset'
        ? tc('materialIdentityManagedPreset')
        : {
          high: tc('materialMatchConfidenceHigh'),
          medium: tc('materialMatchConfidenceMedium'),
          low: tc('materialMatchConfidenceLow'),
        }[autoMaterialMatch.confidence]
    : null;
  const selectedSpoolPriceCurrency = selectedSpool
    ? resolveUserSpoolPriceCurrency(selectedSpool)
    : null;
  const catalogBrandCurrency = !selectedSpool && selectedCatalogFilament?.currency
    ? normalizeCurrency(selectedCatalogFilament.currency)
    : null;
  const catalogPriceMismatch =
    selectedSpool
    && selectedSpool.price != null
    && selectedSpoolPriceCurrency
    && selectedSpoolPriceCurrency !== quoteProfile.currency
      ? {
          brandSymbol: currencySymbol(selectedSpoolPriceCurrency),
          reference: selectedSpool.price,
        }
      : catalogBrandCurrency && catalogBrandCurrency !== quoteProfile.currency && selectedCatalogFilament
      ? {
          brandSymbol: currencySymbol(catalogBrandCurrency),
          reference: deriveCatalogFilamentDefaults(selectedCatalogFilament).spoolPrice,
        }
      : null;
  const materialSummary =
    selectedSpool
      ? [
          selectedSpool.price != null
            ? makeCurrencyFormatter(selectedSpoolPriceCurrency || quoteProfile.currency)(selectedSpool.price)
            : tc('materialPriceUnknown'),
          `${Math.round(selectedSpool.initial_weight_g)} ${tc('grams')}`,
          `${Math.round(selectedSpool.remaining_weight_g)} ${tc('grams')} ${tc('remainingShort')}`,
        ].join(' · ')
      : selectedCatalogFilament &&
          (selectedCatalogFilament.price_per_kg != null || selectedCatalogFilament.spool_weight != null)
        ? `${selectedCatalogFilament.price_per_kg != null ? `${selectedCatalogFilament.price_per_kg.toFixed(0)} ${currencySymbol(catalogBrandCurrency || quoteProfile.currency)}/${tc('kg')}` : '—'} · ${
            selectedCatalogFilament.spool_weight != null
              ? `${selectedCatalogFilament.spool_weight.toFixed(0)} ${tc('grams')}`
              : '—'
          }`
        : null;
  const activeQuoteRules = quoteMarketRules(
    resolveQuoteMarket(quoteProfile.quoteMarket, quoteProfile.currency),
  );

  const roundingSteps = roundingStepsForCurrency(quoteProfile.currency);
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
  const activeJobKey = activeParsedJobKey ?? displayJobs[0]?.key;
  const visibleJobs = displayJobs.length > 1
    ? displayJobs.filter((job) => job.key === activeJobKey)
    : displayJobs;
  const hasParsedJobs = displayJobs.length > 0;
  const isBatchMode = displayJobs.length > 1;
  const hasManualCalculationData = !hasParsedJobs
    && form.weightG > 0
    && toHours(form.timeHours, form.timeMinutes, form.timeSec) > 0;
  const showCalculateAction = hasParsedJobs || hasManualCalculationData;
  // Enough to compute, which is not the same as enough to quote: an unconfirmed price
  // still gives a number, and the total says so rather than the button refusing.
  const materialsReadyForCalculation = !hasParsedJobs || (
    materialLines.length > 0
    && materialLines.every((line) => (
      line.weight_g > 0
      && line.spool_weight_kg > 0
      && line.spool_price > 0
    ))
  );
  const calculateActionEnabled = showCalculateAction
    && materialsReadyForCalculation
    && !isParsingGcode
    && !isCalculating;
  const machineRateMissing = isMachineRateMissing(printerEconomics, form.printingRatePerHour);
  const orderMachineRateMissing = machineRateMissing
    && (!hasParsedJobs || jobConfigs.some((config) => config.physicalPrinterId === ''));

  const economicsReadinessEntries = (() => {
    const entries = new Map<string, EconomicsReadinessEntry>();
    const printerName = (printerId: number) => printers.find((printer) => printer.id === printerId)?.name
      ?? `#${printerId}`;
    const addAccount = () => entries.set('account', {
      id: 'account',
      label: t('printerCost.generalValues'),
      readiness: accountEconomicsReadiness,
    });
    const addPrinter = (printerId: number) => {
      const economics = jobPrinterEconomics.get(printerId)
        ?? (selectedPrinterId === printerId ? printerEconomics : null);
      entries.set(`printer-${printerId}`, {
        id: `printer-${printerId}`,
        label: printerName(printerId),
        readiness: economics?.readiness ?? null,
      });
    };

    if (hasParsedJobs) {
      const configsByJob = new Map(jobConfigs.map((config) => [config.jobKey, config]));
      displayJobs.forEach((job) => {
        const printerId = (configsByJob.get(job.key) ?? createDefaultJobConfig(job)).physicalPrinterId;
        if (printerId !== '') addPrinter(printerId);
        else if (selectedPrinterId !== '') addPrinter(selectedPrinterId);
        else addAccount();
      });
    } else if (selectedPrinterId !== '') {
      addPrinter(selectedPrinterId);
    } else {
      addAccount();
    }
    return [...entries.values()];
  })();
  const economicsReadinessUnavailable = economicsReadinessError
    || (!economicsReadinessLoading && economicsReadinessEntries.some((entry) => !entry.readiness));
  const overallEconomicsReadinessStatus = worstEconomicsReadinessStatus(
    economicsReadinessEntries.map((entry) => entry.readiness),
  );
  const economicsResultNoteKey = economicsReadinessResultNoteKey(
    overallEconomicsReadinessStatus,
    economicsReadinessUnavailable,
  );
  const approximateNotes = result
    ? [
        ...approximatePriceLabels,
        ...(economicsResultNoteKey ? [t(economicsResultNoteKey)] : []),
      ]
    : [];
  const focusMachineEconomics = () => {
    onStaticSettingsOpenChange(true);
    // The panel is closed at this point, so its anchor exists only after the re-render.
    window.setTimeout(() => {
      document
        .getElementById('calculator-machine-economics')
        ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 0);
  };
  const handleCalculateAction = () => {
    if (!calculateActionEnabled) return;
    scrollToResultAfterEstimateRef.current = true;
    onCalculate();
  };
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
  const jobsWithRaft = new Set(
    displayJobs
      .filter((job) => job.parsed.raft_layers != null && job.parsed.raft_layers > 0)
      .map((job) => job.key),
  );
  const formatBatchWeight = (weightG: number) =>
    weightG >= 1000 ? `${(weightG / 1000).toFixed(2)} ${tc('kg')}` : `${weightG.toFixed(2)} ${tc('grams')}`;
  const renderMaterialLine = (line: CalculatorMaterialLineState) => {
    const owningJob = displayJobs.find((job) => job.key === line.job_key);
    const parsedMaterial = owningJob?.parsed.materials.find(
      (material) => material.tool_index === line.tool_index,
    );
    const selectedSpoolForLine = line.selectionValue.startsWith('spool:')
      ? spools.find((spool) => spool.id === Number(line.selectionValue.slice('spool:'.length)))
      : null;
    const selectedFilamentForLine = line.selectionValue.startsWith('filament:')
      ? filaments.find((filament) => filament.id === Number(line.selectionValue.slice('filament:'.length)))
      : null;
    const selectedMaterialForLine = selectedSpoolForLine?.filament || selectedFilamentForLine;
    const materialName = selectedMaterialForLine?.name
      || parsedMaterial?.type
      || parsedMaterial?.name
      || line.label
      || (line.tool_index != null ? `T${line.tool_index}` : tc('unknownMaterial'));
    const materialColors = resolveMaterialDisplayColors(
      parsedMaterial?.color,
      selectedMaterialForLine?.color_hex,
    );
    const selectedMaterialColor = materialColors.primary;
    const materialTypeInName = Boolean(
      selectedMaterialForLine?.material_type
      && materialName.toLowerCase().includes(selectedMaterialForLine.material_type.toLowerCase()),
    );
    const selectedMaterialDetails = selectedMaterialForLine
      ? [
          selectedMaterialForLine.brand_name,
          materialTypeInName ? null : selectedMaterialForLine.material_type,
          selectedMaterialForLine.color_name || selectedMaterialColor,
        ].filter(Boolean).join(' · ')
      : null;
    const technicalLabel = line.label && line.label !== materialName ? line.label : null;
    const rowOpen = openMaterialRowIds.has(line.line_id);
    const preflightUiLine = preflightLines.find((item) => item.lineId === line.line_id) ?? null;
    const lineReadiness = preflightResult?.lines.find((item) => item.line_id === line.line_id) ?? null;
    const identityResolution = trustedIdentityResolution(parsedMaterial);
    const roleWeights = resolveMaterialRoleWeights(line);
    const roleWeightSource = line.role_weight_source ?? line.support_weight_source;
    const supportWeightG = roleWeightSource === 'gcode_extrusion_roles'
      ? roleWeights.support
      : null;
    const brimWeightG = roleWeightSource === 'gcode_extrusion_roles'
      ? roleWeights.brim
      : null;
    const primeTowerWeightG = roleWeightSource === 'gcode_extrusion_roles'
      ? roleWeights.prime_tower
      : null;
    const supportWeightLabel = owningJob?.parsed.raft_layers != null
      && owningJob.parsed.raft_layers > 0
      ? tc('materialSupportAndRaftWeight')
      : tc('materialSupportWeight');
    const identityBadge =
      identityResolution?.status === 'resolved'
      && identityResolution.filament_id != null
      && identityResolution.filament_id === line.filament_id
        ? {
            label: identityResolution.source === 'filamenthub_managed_name'
              ? tc('materialIdentityManagedPreset')
              : tc('materialIdentityExact'),
            tone: 'text-emerald-300/80',
          }
        : identityResolution?.status === 'ambiguous'
          ? { label: tc('materialIdentityAmbiguous'), tone: 'text-amber-300/90' }
          : line.mappingSource === 'automatic'
            ? { label: tc('materialMatchedByAttributes'), tone: 'text-cyan-300/80' }
            : identityResolution?.status === 'unresolved'
              ? { label: tc('materialIdentityUnresolved'), tone: 'text-amber-300/80' }
              : null;

    return (
    <div
      key={line.line_id}
      className="min-w-0 py-3"
      title={technicalLabel ?? undefined}
    >
      <button
        type="button"
        aria-expanded={rowOpen}
        onClick={() => setOpenMaterialRowIds((current) => {
          const next = new Set(current);
          if (next.has(line.line_id)) next.delete(line.line_id);
          else next.add(line.line_id);
          return next;
        })}
        className="flex min-h-11 w-full min-w-0 items-start justify-between gap-3 text-left"
      >
        <div className="flex min-w-0 items-start gap-2">
          {/* The slot keeps its width while the check is being recalculated, otherwise the
              whole row shifts sideways every time a spool changes. */}
          <span
            title={lineReadiness ? t(`profilePage.calculator.preflightStatus.${lineReadiness.status}`) : undefined}
            className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center ${
              !lineReadiness
                ? 'text-transparent'
                : lineReadiness.status === 'ready' || lineReadiness.status === 'ready_with_change'
                  ? 'text-emerald-300'
                  : 'text-amber-300'
            }`}
          >
            {lineReadiness && (lineReadiness.status === 'ready' || lineReadiness.status === 'ready_with_change')
              ? <CheckCircle2 className="h-4 w-4" />
              : lineReadiness
                ? <AlertTriangle className="h-4 w-4" />
                : null}
          </span>
          <div className="min-w-0">
          <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5">
            {selectedMaterialColor ? (
              <span className="relative mr-0.5 inline-flex h-4 w-4 shrink-0" title={
                materialColors.differs
                  ? `${tc('colorFromGcode')}: ${selectedMaterialColor} · ${tc('colorAssigned')}: ${selectedMaterialForLine?.color_name || materialColors.assigned}`
                  : selectedMaterialForLine?.color_name || selectedMaterialColor
              }>
                <span
                  data-testid="calculator-selected-material-color"
                  className="h-4 w-4 rounded-full border border-white/35 shadow-[0_0_0_3px_rgba(255,255,255,0.04)]"
                  style={{ backgroundColor: selectedMaterialColor }}
                />
                {materialColors.assigned ? (
                  <span
                    data-testid="calculator-assigned-material-color"
                    className="absolute -bottom-1 -right-1 h-2.5 w-2.5 rounded-full border border-slate-950 ring-1 ring-white/35"
                    style={{ backgroundColor: materialColors.assigned }}
                  />
                ) : null}
              </span>
            ) : null}
            <p data-testid="calculator-selected-material" className="truncate text-sm font-semibold text-white">
              {materialName}
            </p>
            <p className="shrink-0 text-xs font-medium tabular-nums text-cyan-100">
              {line.weight_g.toFixed(2)} {tc('grams')}
            </p>
            {roleWeightSource === 'gcode_extrusion_roles' ? (
              <span className="shrink-0 text-[10px] leading-4 text-slate-500">
                {[
                  supportWeightG != null && supportWeightG > 0
                    ? `${supportWeightLabel} ${supportWeightG.toFixed(2)}`
                    : null,
                  brimWeightG != null && brimWeightG > 0
                    ? `${tc('materialBrimWeight')} ${brimWeightG.toFixed(2)}`
                    : null,
                  primeTowerWeightG != null && primeTowerWeightG > 0
                    ? `${tc('materialPrimeTowerWeight')} ${primeTowerWeightG.toFixed(2)}`
                    : null,
                ].filter(Boolean).join(' · ')}
              </span>
            ) : null}
          </div>
          <div className="mt-1 flex min-w-0 flex-wrap items-center gap-x-2 gap-y-0.5 text-[10px]">
            {line.tool_index != null ? (
              <span className="shrink-0 font-semibold uppercase tracking-[0.14em] text-slate-500">T{line.tool_index}</span>
            ) : null}
            {selectedMaterialDetails ? (
              <span className="min-w-0 truncate text-slate-400" title={selectedMaterialDetails}>
                {selectedMaterialDetails}
              </span>
            ) : null}
            {identityBadge ? (
              <span
                className={`shrink-0 font-medium ${identityBadge.tone}`}
                title={identityResolution?.stable_id}
              >
                {identityBadge.label}
              </span>
            ) : null}
          </div>
          </div>
        </div>
        <span className="flex shrink-0 items-start gap-2">
          <span className="text-right">
            <span className={`block text-sm font-semibold tabular-nums ${line.priceResolved ? 'text-white' : 'text-amber-300/80'}`}>
              {line.spool_weight_kg > 0 && (line.priceResolved || line.spool_price > 0)
                ? formatCurrency((line.weight_g / 1000) * (line.spool_price / line.spool_weight_kg))
                : tc('materialLineNeedsPrice')}
            </span>
            {line.priceResolved || line.spool_price > 0 ? (
              <span className={`mt-0.5 block text-[10px] leading-4 ${line.priceResolved ? 'text-slate-500' : 'text-amber-300/70'}`}>
                {formatCurrency(line.spool_price)} / {line.spool_weight_kg} {tc('kg')} · {tc(`materialLineSource.${line.price_source}`)}
                {line.priceResolved ? '' : ` · ${tc('materialLineConfirmPrice')}`}
              </span>
            ) : null}
          </span>
          <ChevronDown className={`mt-0.5 h-4 w-4 shrink-0 text-slate-500 transition-transform ${rowOpen ? 'rotate-180' : ''}`} />
        </span>
      </button>
      {rowOpen ? (
      <div className="mt-3 space-y-3 rounded-xl border border-white/15 bg-black/25 p-3">
        <div className="flex flex-wrap items-end gap-3">
        <select
          className={`${inputClass} min-h-11 min-w-0 py-1.5 text-xs sm:max-w-[24rem]`}
          value={line.selectionValue}
          onChange={(event) => {
            const selectionValue = event.target.value;
            onMaterialLineSelection(line.line_id, selectionValue);
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
        <div className={`grid w-full min-w-0 grid-cols-1 gap-2 [&_input]:min-h-11 sm:w-[21rem] sm:grid-cols-2 ${compactFieldsClass}`}>
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
              value={Number((line.spool_weight_kg * 1000).toFixed(0))}
              onChange={(value) => onMaterialLineSpoolWeightChange(line.line_id, value / 1000)}
              placeholder="1000"
              suffix={tc('grams')}
              step="50"
            />
          </FieldBlock>
        </div>
        </div>
        {preflightUiLine ? (
          <MaterialReadinessDetails
            line={preflightUiLine}
            readiness={lineReadiness}
            spools={spools}
            formatSpoolLabel={buildSpoolLabel}
            onSpoolIdsChange={onPreflightSpoolIdsChange}
            onReplaceSpool={(lineId, spoolId) => onMaterialLineSelection(lineId, `spool:${spoolId}`)}
          />
        ) : null}
      </div>
      ) : null}
    </div>
    );
  };

  return (
    <div className={`flex flex-col gap-5 ${showCalculateAction ? 'pb-20' : ''}`}>
      <div className="order-1 min-w-0 space-y-5">
        {(!embedded || staticSettingsOpen || quoteProfileOpen) && <SurfaceCard className="p-4 md:p-5">
          {!embedded && <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <SectionHeading icon={<Settings2 className="h-5 w-5 text-cyan-300" />} title={tc('staticSettingsTitle')} compact />
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => onStaticSettingsOpenChange(!staticSettingsOpen)}
                aria-expanded={staticSettingsOpen}
                className={ghostButtonClass}
              >
                <Settings2 className="h-4 w-4" />
                {tc('staticEconomicsTitle')}
                <ChevronDown className={`h-4 w-4 transition-transform ${staticSettingsOpen ? 'rotate-180' : ''}`} />
              </button>
              <button
                type="button"
                onClick={() => onQuoteProfileOpenChange(!quoteProfileOpen)}
                aria-expanded={quoteProfileOpen}
                className={ghostButtonClass}
              >
                <FileText className="h-4 w-4" />
                {tc('quoteProfileTitle')}
                <ChevronDown className={`h-4 w-4 transition-transform ${quoteProfileOpen ? 'rotate-180' : ''}`} />
              </button>
            </div>
          </div>}

          {staticSettingsOpen || quoteProfileOpen ? (
            <div className={`${embedded ? '' : 'mt-4 border-t border-white/10 pt-4'} space-y-4`}>
              {staticSettingsOpen ? (
                <div>
                  <p className="text-sm font-semibold text-white">{tc('staticEconomicsTitle')}</p>
                  <p className="mt-1 text-xs leading-5 text-slate-400">
                    {`${t('profilePage.calc.printingRate')}: ${form.printingRatePerHour} ${currencySymbol(quoteProfile.currency)}/${tc('hourAbbr')} · ${t('profilePage.calc.taxRatePercent')}: ${form.taxRatePercent}% · ${t('profilePage.calc.roundTo')}: ${form.roundToNearest} ${currencySymbol(quoteProfile.currency)} · ${roundingModeLabel}`}
                  </p>
                </div>
              ) : null}

              {staticSettingsOpen ? (
                <div className="mt-3 grid gap-4 xl:grid-cols-[1.75fr_1fr] xl:items-start">
                <div className="space-y-3">
                <div>
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">{tc('economicsGroupHourly')}</p>
                  <div className={`grid grid-cols-2 gap-x-3 gap-y-3 sm:grid-cols-3 ${compactFieldsClass}`}>
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
                        label={t('profilePage.calc.modeling')}
                        tooltipText={tc('defaultModelingRateTooltip')}
                      />
                    }
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
                  >
                    <InputWithSuffix
                      value={form.postprocessingRatePerHour}
                      onChange={(value) => onStaticChange('postprocessingRatePerHour', value)}
                      placeholder="100"
                      suffix={`${currencySymbol(quoteProfile.currency)}/${tc('hourAbbr')}`}
                    />
                  </FieldBlock>
                  </div>
                </div>
                <div>
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">{tc('economicsGroupPerOrder')}</p>
                  <div className={`grid grid-cols-2 gap-x-3 gap-y-3 sm:grid-cols-3 ${compactFieldsClass}`}>
                  <FieldBlock
                    label={
                      <TooltipLabel
                        label={t('profilePage.calc.bedPrepCost')}
                        tooltipText={t('profilePage.calc.bedPrepCostHint')}
                      />
                    }
                  >
                    <InputWithSuffix
                      value={form.bedPrepCostPerPrint}
                      onChange={(value) => onStaticChange('bedPrepCostPerPrint', value)}
                      placeholder="0"
                      suffix={currencySymbol(quoteProfile.currency)}
                    />
                  </FieldBlock>
                  <FieldBlock
                    label={
                      <TooltipLabel
                        label={t('profilePage.calc.fixedCosts')}
                        tooltipText={t('profilePage.calc.fixedCostsHint')}
                      />
                    }
                  >
                    <InputWithSuffix
                      value={form.fixedCosts}
                      onChange={(value) => onStaticChange('fixedCosts', value)}
                      placeholder="0"
                      suffix={currencySymbol(quoteProfile.currency)}
                    />
                  </FieldBlock>
                  <FieldBlock
                    label={
                      <TooltipLabel
                        label={t('profilePage.calc.minOrderPrice')}
                        tooltipText={t('profilePage.calc.minOrderPriceHint')}
                      />
                    }
                  >
                    <InputWithSuffix
                      value={form.minOrderPrice}
                      onChange={(value) => onStaticChange('minOrderPrice', value)}
                      placeholder="0"
                      suffix={currencySymbol(quoteProfile.currency)}
                    />
                  </FieldBlock>
                  </div>
                </div>
                <div>
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">{tc('economicsGroupMargins')}</p>
                  <div className={`grid grid-cols-2 gap-x-3 gap-y-3 sm:grid-cols-3 ${compactFieldsClass}`}>
                  <FieldBlock
                    label={
                      <TooltipLabel
                        label={t('profilePage.calc.overheadPercent')}
                        tooltipText={tc('defaultOverheadTooltip')}
                      />
                    }
                  >
                    <InputWithSuffix
                      value={form.overheadPercent}
                      onChange={(value) => onStaticChange('overheadPercent', value)}
                      placeholder="20"
                      suffix="%"
                      step="0.1"
                    />
                    <QuickPicks
                      options={[
                      { label: tc('overheadLow'), value: 10 },
                      { label: tc('overheadMid'), value: 20 },
                      { label: tc('overheadHigh'), value: 30 },
                    ]}
                      value={form.overheadPercent}
                      onPick={(value) => onStaticChange('overheadPercent', value)}
                      caption={tc('overheadCaption')}
                      hint={false}
                    />
                  </FieldBlock>
                  <FieldBlock
                    label={
                      <TooltipLabel
                        label={t('profilePage.calc.markupPercent')}
                        tooltipText={tc('defaultMarkupTooltip')}
                      />
                    }
                  >
                    <InputWithSuffix
                      value={form.markupPercent}
                      onChange={(value) => onStaticChange('markupPercent', value)}
                      placeholder="30"
                      suffix="%"
                      step="0.1"
                    />
                    <QuickPicks
                      options={[
                      { label: tc('markupLow'), value: 20 },
                      { label: tc('markupMid'), value: 40 },
                      { label: tc('markupHigh'), value: 70 },
                    ]}
                      value={form.markupPercent}
                      onPick={(value) => onStaticChange('markupPercent', value)}
                      caption={tc('markupCaption')}
                      hint={false}
                    />
                  </FieldBlock>
                  <FieldBlock
                    label={
                      <TooltipLabel
                        label={t('profilePage.calc.taxRatePercent')}
                        tooltipText={t('profilePage.calc.taxRateHint')}
                      />
                    }
                  >
                    <InputWithSuffix
                      value={form.taxRatePercent}
                      onChange={(value) => onStaticChange('taxRatePercent', value)}
                      placeholder="0"
                      suffix="%"
                      step="0.1"
                    />
                    <QuickPicks
                      options={[
                      { label: '0%', value: 0 },
                      { label: '4%', value: 4 },
                      { label: '6%', value: 6 },
                      { label: '20%', value: 20 },
                    ]}
                      value={form.taxRatePercent}
                      onPick={(value) => onStaticChange('taxRatePercent', value)}
                      caption={tc('taxCaption')}
                      hint={false}
                    />
                  </FieldBlock>
                  </div>
                </div>
                <div>
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">{tc('economicsGroupRounding')}</p>
                  <div className={compactFieldsClass}>
                  <FieldBlock label={t('profilePage.calc.roundTo')}>
                    <div className="flex flex-wrap items-center gap-2">
                      <InputWithSuffix
                        value={form.roundToNearest}
                        onChange={(value) => onStaticChange('roundToNearest', value)}
                        placeholder="10"
                        suffix={currencySymbol(quoteProfile.currency)}
                      />
                      <select
                        className={`${inputClass} w-full sm:w-auto sm:min-w-[8rem]`}
                        value={form.roundingMode}
                        aria-label={t('profilePage.calc.roundingMode')}
                        onChange={(event) => onStaticChange('roundingMode', event.target.value as RoundingMode)}
                      >
                        <option value="up">{t('profilePage.calc.roundingModeUp')}</option>
                        <option value="nearest">{t('profilePage.calc.roundingModeNearest')}</option>
                        <option value="down">{t('profilePage.calc.roundingModeDown')}</option>
                      </select>
                    </div>
                    <QuickPicks
                      options={[
                        { label: tc('roundNone'), value: 0 },
                        ...roundingSteps.map((step) => ({ label: String(step), value: step })),
                      ]}
                      value={form.roundToNearest}
                      onPick={(value) => onStaticChange('roundToNearest', value)}
                      caption={tc('roundCaption')}
                      hint={false}
                    />
                  </FieldBlock>
                  </div>
                </div>
                </div>
                <PrinterEconomicsColumn
                  printers={printers}
                  editedPrinterId={economicsPrinterId}
                  onEditedPrinterChange={onEconomicsPrinterChange}
                  currency={quoteProfile.currency}
                  electricityCostPerKwh={form.electricityCostPerKwh}
                  averaged={{
                    purchaseCost: form.printerPurchasePrice,
                    lifeHours: form.printerUsefulHours,
                    powerWatts: form.printerPowerW,
                    maintenance: form.maintenanceCostPerHour,
                    rate: form.printingRatePerHour,
                  }}
                  powerBreakdown={
                    <PowerPartsBreakdown
                      hotend={form.powerHotendW}
                      bed={form.powerBedW}
                      steppers={form.powerSteppersW}
                      electronics={form.powerElectronicsW}
                      onChange={(part, value) => {
                        const map = {
                          hotend: 'powerHotendW',
                          bed: 'powerBedW',
                          steppers: 'powerSteppersW',
                          electronics: 'powerElectronicsW',
                        } as const;
                        onStaticChange(map[part], value);
                        const totals = {
                          hotend: form.powerHotendW,
                          bed: form.powerBedW,
                          steppers: form.powerSteppersW,
                          electronics: form.powerElectronicsW,
                          [part]: value,
                        };
                        const total =
                          totals.hotend + totals.bed + totals.steppers + totals.electronics;
                        if (total > 0) onStaticChange('printerPowerW', total);
                      }}
                    />
                  }
                  onAveragedChange={(field, value) => {
                    const mapping = {
                      purchaseCost: 'printerPurchasePrice',
                      lifeHours: 'printerUsefulHours',
                      powerWatts: 'printerPowerW',
                      maintenance: 'maintenanceCostPerHour',
                      rate: 'printingRatePerHour',
                    } as const;
                    onStaticChange(mapping[field], value);
                    if (field === 'purchaseCost' || field === 'lifeHours' || field === 'maintenance') {
                      const price = field === 'purchaseCost' ? value : form.printerPurchasePrice;
                      const hours = field === 'lifeHours' ? value : form.printerUsefulHours;
                      const upkeep = field === 'maintenance' ? value : form.maintenanceCostPerHour;
                      const perHour = hours > 0 ? price / hours : 0;
                      onStaticChange(
                        'amortizationRatePerHour',
                        Math.round((perHour + upkeep) * 100) / 100,
                      );
                    }
                  }}
                />
                </div>
              ) : null}

              {staticSettingsOpen ? (
                <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                  <button
                    type="button"
                    onClick={onPlatformDefaultsReset}
                    disabled={isCloudBusy}
                    className={ghostButtonClass}
                  >
                    {isCloudBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
                    {tc('platformDefaultsReset')}
                  </button>
                  <p className="text-[11px] leading-4 text-slate-500">{tc('economicsAutosaveHint')}</p>
                </div>
              ) : null}

              {quoteProfileOpen ? (
                <div className={staticSettingsOpen ? 'border-t border-white/10 pt-4' : ''}>
                  <p className="text-sm font-semibold text-white">{tc('quoteProfileTitle')}</p>
                  <p className="mt-1 text-xs leading-5 text-slate-400">
                    {(quoteProfile.sellerName || tc('quoteProfileSummaryEmpty')) +
                      ` · ${tc('quoteValidityDaysShort')}: ${quoteProfile.validityDays} ${tc('dayAbbr')}`}
                  </p>
                <div className="mt-4 rounded-2xl border border-white/10 bg-white/[0.03] p-3">
                  <p className="text-xs font-semibold text-slate-200">{t('quoteMarket.title')}</p>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => onQuoteProfileChange('quoteMarket', '')}
                      className={`rounded-full border px-3 py-1.5 text-xs transition ${
                        quoteProfile.quoteMarket === ''
                          ? 'border-cyan-400/50 bg-cyan-500/15 text-cyan-200'
                          : 'border-white/10 bg-slate-950/40 text-slate-300 hover:border-white/20'
                      }`}
                    >
                      {t('quoteMarket.auto')}
                    </button>
                    {QUOTE_MARKETS.map((market) => (
                      <button
                        key={market}
                        type="button"
                        onClick={() => {
                          onQuoteProfileChange('quoteMarket', market);
                          // Picking a market is a deliberate act, so the currency may
                          // follow it — but only when the current one does not belong
                          // to that market anyway. A shop in Kazakhstan choosing
                          // "Russia and CIS" keeps its tenge.
                          const { currencies } = quoteMarketRules(market);
                          const current = normalizeCurrency(quoteProfile.currency);
                          if (currencies.length > 0 && !currencies.includes(current)) {
                            onQuoteProfileChange('currency', currencies[0]);
                          }
                        }}
                        className={`rounded-full border px-3 py-1.5 text-xs transition ${
                          quoteProfile.quoteMarket === market
                            ? 'border-cyan-400/50 bg-cyan-500/15 text-cyan-200'
                            : 'border-white/10 bg-slate-950/40 text-slate-300 hover:border-white/20'
                        }`}
                      >
                        {t(`quoteMarket.markets.${market}`)}
                      </button>
                    ))}
                  </div>
                  <p className="mt-2 text-[11px] leading-4 text-slate-500">{t('quoteMarket.hint')}</p>
                </div>

                <div className="mt-3">
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">{tc('quoteGroupSupplier')}</p>
                  <div className={`grid grid-cols-2 gap-x-3 gap-y-3 sm:grid-cols-3 xl:grid-cols-4 ${compactFieldsClass}`}>
                  <FieldBlock label={tc('quoteSellerName')}>
                    <TextInput
                      value={quoteProfile.sellerName}
                      onChange={(value) => onQuoteProfileChange('sellerName', value)}
                      placeholder={tc('quoteSellerNamePlaceholder')}
                    />
                  </FieldBlock>
                  <FieldBlock label={t(activeQuoteRules.taxIdKey)}>
                    <TextInput
                      value={quoteProfile.sellerInn}
                      onChange={(value) => onQuoteProfileChange('sellerInn', value)}
                      placeholder=""
                    />
                  </FieldBlock>
                  {activeQuoteRules.registrationIdKey ? (
                    <FieldBlock label={t(activeQuoteRules.registrationIdKey)}>
                      <TextInput
                        value={quoteProfile.sellerRegistrationId}
                        onChange={(value) => onQuoteProfileChange('sellerRegistrationId', value)}
                        placeholder=""
                      />
                    </FieldBlock>
                  ) : null}
                  {activeQuoteRules.showTaxCode ? (
                    <FieldBlock label={t('quoteMarket.ru.taxCode')}>
                      <TextInput
                        value={quoteProfile.sellerTaxCode}
                        onChange={(value) => onQuoteProfileChange('sellerTaxCode', value)}
                        placeholder=""
                      />
                    </FieldBlock>
                  ) : null}
                  <FieldBlock label={t('quoteMarket.sellerAddress')}>
                    <TextInput
                      value={quoteProfile.sellerAddress}
                      onChange={(value) => onQuoteProfileChange('sellerAddress', value)}
                      placeholder=""
                    />
                  </FieldBlock>
                  {activeQuoteRules.showBankDetails ? (
                    <FieldBlock label={t('quoteMarket.sellerBank')}>
                      <TextInput
                        value={quoteProfile.sellerBankDetails}
                        onChange={(value) => onQuoteProfileChange('sellerBankDetails', value)}
                        placeholder=""
                      />
                    </FieldBlock>
                  ) : null}
                  <FieldBlock label={tc('quoteSellerPhone')}>
                    <TextInput
                      value={quoteProfile.sellerPhone}
                      onChange={(value) => onQuoteProfileChange('sellerPhone', value)}
                      placeholder={quoteMarketRules(
                        resolveQuoteMarket(quoteProfile.quoteMarket, quoteProfile.currency),
                      ).phonePlaceholder}
                    />
                  </FieldBlock>
                  </div>
                </div>
                <div className="mt-3">
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">{tc('quoteGroupDocument')}</p>
                  <div className={`grid grid-cols-2 gap-x-3 gap-y-3 sm:grid-cols-3 xl:grid-cols-4 ${compactFieldsClass}`}>
                  <FieldBlock label={tc('quoteValidityDays')} hint={tc('quoteValidityDaysHint')}>
                    <NumberInput
                      value={quoteProfile.validityDays}
                      onChange={(value) => onQuoteProfileChange('validityDays', Math.max(1, value))}
                      min="1"
                      placeholder="14"
                    />
                  </FieldBlock>
                  <div className="md:col-span-2">
                    <FieldBlock label={tc('quoteLegalStatus')} hint={tc('quoteDisclaimerHint')}>
                      <p className="text-sm text-slate-200">{tc('quoteDisclaimerNotOffer')}</p>
                    </FieldBlock>
                  </div>
                  <FieldBlock label={tc('quoteNumberPrefix')} hint={tc('quoteNumberPrefixHint')}>
                    <TextInput
                      value={quoteProfile.quoteNumberPrefix}
                      placeholder={activeQuoteRules.numberPrefix}
                      onChange={(value) => onQuoteProfileChange('quoteNumberPrefix', value)}
                    />
                  </FieldBlock>
                  </div>
                </div>
                <div className="mt-3">
                  <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">{tc('quoteGroupMoney')}</p>
                  <div className={`grid grid-cols-2 gap-x-3 gap-y-3 sm:grid-cols-3 xl:grid-cols-4 ${compactFieldsClass}`}>
                  <FieldBlock label={tc('quoteCurrency')}>
                    <select
                      className={`${inputClass} w-full sm:max-w-[18rem]`}
                      value={quoteProfile.currency}
                      onChange={(event) =>
                        onQuoteProfileChange('currency', event.target.value as CurrencyCode)
                      }
                    >
                      {currencyCodes().map((c: CurrencyCode) => (
                        <option key={c} value={c}>{c} ({currencySymbol(c)})</option>
                      ))}
                    </select>
                  </FieldBlock>
                  <div className="col-span-2 sm:col-span-3 xl:col-span-4">
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
                <div className="mt-3 rounded-2xl border border-cyan-400/15 bg-cyan-400/[0.04] p-3">
                  <QuoteDisclosureSettings
                    byWork={quoteProfile.showCostBreakdown}
                    onByWorkChange={(value) => onQuoteProfileChange('showCostBreakdown', value)}
                    note={quoteProfile.costBreakdownNote}
                    onNoteChange={(value) => onQuoteProfileChange('costBreakdownNote', value)}
                    taxKind={quoteProfile.taxKind}
                    onTaxKindChange={(value) => onQuoteProfileChange('taxKind', value)}
                    taxMode={quoteProfile.taxMode}
                    onTaxModeChange={(value) => onQuoteProfileChange('taxMode', value)}
                    delivery={quoteProfile.customerDeliveryAmount}
                    onDeliveryChange={(value) => onQuoteProfileChange('customerDeliveryAmount', value)}
                    currencySymbol={currencySymbol(quoteProfile.currency)}
                  >
                    <p className="text-[11px] leading-4 text-slate-500">{tc('quoteProfileDisclosureHint')}</p>
                  </QuoteDisclosureSettings>
                </div>
                <div className="mt-4 rounded-2xl border border-white/10 bg-white/[0.03] p-3">
                  <p className="text-xs leading-5 text-slate-400">{tc('quoteCloudHint')}</p>
                  <div className="mt-2 flex flex-wrap gap-2">
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
                  {quoteProfileFeedback ? (
                    <div
                      role={quoteProfileFeedback.kind === 'error' ? 'alert' : 'status'}
                      className={`mt-3 rounded-xl border px-3 py-2 text-xs leading-5 ${
                        quoteProfileFeedback.kind === 'success'
                          ? 'border-emerald-400/25 bg-emerald-500/10 text-emerald-100'
                          : 'border-red-400/25 bg-red-500/10 text-red-100'
                      }`}
                    >
                      {quoteProfileFeedback.message}
                    </div>
                  ) : null}
                </div>
                </div>
              ) : null}
            </div>
          ) : null}
        </SurfaceCard>}

        <SurfaceCard className="p-5 md:p-6">
          <SectionHeading icon={<LayeredPrinterIcon className="h-5 w-5 text-cyan-300" />} title={tc('workspaceTitle')} />

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
              {/* Without a file this panel is an offer, not a step: numbering it
                  first would start the count on the thing the person skipped. */}
              <WorkspacePanel
                step={hasParsedJobs ? '1' : undefined}
                title={tc('workspaceSourceTitle')}
              >
                <div className={insidePlugin ? 'grid gap-4 lg:grid-cols-2' : ''}>
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
                  className={`block w-full cursor-pointer rounded-2xl border border-dashed p-4 text-left transition-all ${
                    dragActive
                      ? 'border-cyan-300/80 bg-cyan-400/12 shadow-[0_25px_50px_-35px_rgba(34,211,238,0.65)]'
                      : 'border-cyan-400/30 bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.14),transparent_52%),linear-gradient(180deg,rgba(15,23,42,0.8),rgba(2,6,23,0.85))] hover:border-cyan-300/50'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/5">
                      {isParsingGcode ? <Loader2 className="h-4 w-4 animate-spin text-cyan-300" /> : <Upload className="h-4 w-4 text-cyan-300" />}
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-white">
                        {isParsingGcode ? gcodeProcessingLabel : tc('gcodeDropTitle')}
                      </p>
                      <p className="mt-0.5 text-[10px] uppercase tracking-[0.14em] text-slate-500">{tc('supportedFormats')}</p>
                    </div>
                  </div>
                  {isParsingGcode && gcodeProcessingProgress ? (
                    <div className="mt-3" role="status" aria-live="polite">
                      <div className="h-1.5 overflow-hidden rounded-full bg-slate-800">
                        <div
                          className="h-full rounded-full bg-cyan-400 transition-[width] duration-200"
                          style={{ width: `${gcodeProgressPercent}%` }}
                        />
                      </div>
                      <p className="mt-1.5 text-xs text-slate-400">{gcodeProcessingDetail}</p>
                      <button
                        type="button"
                        className="mt-2 inline-flex min-h-9 items-center rounded-xl border border-slate-600 px-3 text-xs font-semibold text-slate-200 transition hover:border-slate-400 hover:text-white"
                        onClick={(event) => {
                          event.preventDefault();
                          event.stopPropagation();
                          onCancelGcodeProcessing();
                        }}
                      >
                        {tc('gcodeCancel')}
                      </button>
                    </div>
                  ) : null}
                </label>

                {insidePlugin && (
                  <SlicedJobsPanel
                    onPick={onSlicePick}
                    pickingId={pickingSliceId}
                    pickingProgress={pickingSliceProgress}
                    goneSourceKeys={goneSourceKeys}
                  />
                )}
                </div>

                {parseGcodeError && (
                  <div className="flex flex-wrap items-center justify-between gap-3 rounded-[1.25rem] border border-red-400/25 bg-red-500/10 px-4 py-3 text-sm text-red-100">
                    <span>{parseGcodeError}</span>
                    <button
                      type="button"
                      className="inline-flex min-h-9 items-center rounded-xl border border-red-300/35 px-3 text-xs font-semibold text-red-50 transition hover:border-red-200"
                      onClick={onRetryGcodeProcessing}
                    >
                      {tc('gcodeRetry')}
                    </button>
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
                    {isBatchMode || batchSummary.printRunCount > 1 ? (
                    <div className="mt-5 grid grid-cols-2 gap-3 md:grid-cols-4">
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
                        icon={<Printer3DIcon className="h-4 w-4" />}
                        label={tc('partyRuns')}
                        value={String(batchSummary.printRunCount)}
                      />
                      <BatchMetric
                        icon={<Layers3 className="h-4 w-4" />}
                        label={tc('partyMaterial')}
                        value={formatBatchWeight(batchSummary.partyWeightG)}
                      />
                    </div>
                    ) : null}
                  </div>
                </div>
              ) : null}

              <div
                className={
                  hasParsedJobs
                    ? 'space-y-5'
                    : 'grid gap-5 xl:grid-cols-2 xl:items-start'
                }
              >
              <WorkspacePanel
                step={hasParsedJobs ? '2' : '1'}
                title={hasParsedJobs ? tc('orderCompositionTitle') : tc('workspaceMaterialTitle')}
              >
                {hasParsedJobs ? (
                  <div className="mb-4">
                    <PrinterCostRow
                      printers={printers}
                      selectedPrinterId={selectedPrinterId}
                      onSelect={onPrinterSelect}
                      pickedFromLabel={printerPickedFrom}
                      rateMissing={orderMachineRateMissing}
                      onFixRate={focusMachineEconomics}
                      readinessEntries={economicsReadinessEntries}
                      readinessLoading={economicsReadinessLoading}
                      readinessError={economicsReadinessUnavailable}
                    />
                  </div>
                ) : null}
                {/* Several plates stack into a wall of cards; one job at a time keeps the
                    screen readable and gives each its own place for a printer later. */}
                {hasParsedJobs && displayJobs.length > 1 ? (
                  <div className="mb-4 flex flex-wrap gap-2">
                    {displayJobs.map((job, jobIndex) => {
                      const isActive = job.key === activeJobKey;
                      return (
                        <button
                          key={`job-tab-${job.key}`}
                          type="button"
                          aria-pressed={isActive}
                          onClick={() => onJobSelect(job.key)}
                          className={`min-w-0 rounded-xl border px-3 py-2 text-left transition ${
                            isActive
                              ? 'border-cyan-400/40 bg-cyan-400/10 text-white'
                              : 'border-white/10 bg-white/[0.04] text-slate-300 hover:border-white/20 hover:text-white'
                          }`}
                        >
                          <span className="block max-w-[14rem] truncate text-xs font-medium">
                            {quoteTitleFromFileName(job.parsed.file_name, `${tc('jobFallbackTitle')} ${jobIndex + 1}`)}
                          </span>
                          <span className="mt-0.5 block text-[10px] text-slate-500">
                            {formatHoursShort(
                              (getJobConfig(job).printTimeSeconds) / 3600,
                              t('profilePage.calc.h'),
                              t('profilePage.calc.min'),
                            )}
                            {' · '}
                            {formatBatchWeight(job.parsed.total_filament_weight_g ?? 0)}
                          </span>
                        </button>
                      );
                    })}
                  </div>
                ) : null}
                {hasParsedJobs ? (
                  <div className="grid min-w-0 grid-cols-1 gap-4">
                    {visibleJobs.map((job, jobIndex) => {
                      const jobLines = materialLines.filter((line) => line.job_key === job.key);
                      const jobLinesByWeight = [...jobLines].sort((a, b) => b.weight_g - a.weight_g);
                      const jobRoleTotals = jobLines.reduce(
                        (totals, line) => {
                          if ((line.role_weight_source ?? line.support_weight_source) !== 'gcode_extrusion_roles') {
                            return totals;
                          }
                          const roles = resolveMaterialRoleWeights(line);
                          return {
                            support: totals.support + (roles.support ?? 0),
                            brim: totals.brim + (roles.brim ?? 0),
                            primeTower: totals.primeTower + (roles.prime_tower ?? 0),
                          };
                        },
                        { support: 0, brim: 0, primeTower: 0 },
                      );
                      const jobTotalWeightG = job.parsed.total_filament_weight_g ?? 0;
                      const jobServiceWeightG = jobRoleTotals.support + jobRoleTotals.brim + jobRoleTotals.primeTower;
                      const servicePercent = jobTotalWeightG > 0
                        ? Math.round((jobServiceWeightG / jobTotalWeightG) * 100)
                        : 0;
                      const objectCount = Math.max(1, job.parsed.object_count ?? 1);
                      const objectGroups = job.parsed.object_groups ?? [];
                      const config = getJobConfig(job);
                      const jobRateMissing = isJobMachineRateMissing(
                        config,
                        printerEconomics,
                        form.printingRatePerHour,
                        jobPrinterEconomics,
                      );
                      const canSplitGroups = canSplitCalculatorObjectGroups(objectGroups);
                      const objectsOpen = config.quoteMode === 'groups' || openObjectJobKeys.has(job.key);
                      const quoteMode = config.quoteMode === 'groups'
                        && objectGroups.length > 1
                        && !canSplitGroups
                        ? 'set'
                        : config.quoteMode;
                      const outputPerRun = calculatorOutputQuantityPerRun(objectGroups, quoteMode);
                      const timeParts = splitSeconds(config.printTimeSeconds);
                      const suggestedPrinterIds = job.parsed.suggested_physical_printer_ids ?? [];
                      const printerNote = jobPrinterNote(job, config);
                      return (
                        <article
                          key={job.key}
                          className={`min-w-0 overflow-hidden rounded-[1.35rem] border bg-black/20 ${
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
                              {job.parsed.thumbnail_data_url ? (
                                <img
                                  src={job.parsed.thumbnail_data_url}
                                  alt={tc('parsedPreviewAlt')}
                                  className="h-20 w-20 shrink-0 rounded-xl border border-white/10 bg-slate-950/60 object-contain"
                                />
                              ) : null}
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
                                  {job.parsed.plate_index != null ? (
                                    <span>{tc('parsedPlateOption').replace('{{index}}', String(job.parsed.plate_index))}</span>
                                  ) : null}
                                </span>
                              </span>
                            </button>

                            <div className="ml-auto flex shrink-0 items-start gap-3">
                            <label className="flex shrink-0 items-center gap-3 rounded-xl border border-white/[0.08] bg-white/[0.04] px-3 py-2">
                              <span className="border-r border-white/10 pr-3 text-right text-[11px] leading-4 text-slate-400">
                                <span className="block tabular-nums">
                                  {tc('plateObjectsTotal')}: <strong className="font-medium text-slate-200">{objectCount * config.repeats}</strong>
                                </span>
                                <span className="mt-0.5 block tabular-nums">
                                  {tc('plateQuoteQuantity')}: <strong className="font-medium text-slate-200">{outputPerRun * config.repeats}</strong>
                                </span>
                              </span>
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
                            {displayJobs.length > 1 ? (
                              <button
                                type="button"
                                onClick={() => onJobRemove(job.key)}
                                className="shrink-0 self-start rounded-lg border border-white/10 px-2.5 py-1.5 text-xs font-medium text-slate-400 transition hover:border-red-400/30 hover:text-red-200"
                              >
                                {tc('removeJob')}
                              </button>
                            ) : null}
                            </div>
                          </div>

                          {/* The machine sits with the plate it prints: an hour on each one
                              costs its own money, and plates in an order can differ. */}
                          {displayJobs.length > 1 ? (
                            <label className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-white/[0.07] px-4 py-2.5">
                              <span className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                                {t('printerCost.rowLabel')}
                              </span>
                              <select
                                className={`${inputClass} w-auto min-w-[12rem] py-1.5 text-xs`}
                                value={config.physicalPrinterId === '' ? '' : String(config.physicalPrinterId)}
                                onChange={(event) => onJobConfigChange(job.key, {
                                  physicalPrinterId: event.target.value ? Number(event.target.value) : '',
                                })}
                              >
                                <option value="">{tc('jobPrinterFromOrder')}</option>
                                {sortSuggestedPrintersFirst(printers, suggestedPrinterIds).map((printer) => (
                                  <option key={`job-printer-${job.key}-${printer.id}`} value={printer.id}>
                                    {printer.name}
                                  </option>
                                ))}
                              </select>
                              {printerNote === 'several' ? (
                                <span className="text-[11px] text-cyan-300/90">{tc('jobPrinterSeveralFit')}</span>
                              ) : printerNote === 'fromFile' ? (
                                <span className="text-[11px] text-cyan-300/90">{tc('printerPickedFromGcode')}</span>
                              ) : (
                                <span className="text-[11px] text-slate-500">{tc('jobPrinterHint')}</span>
                              )}
                              {jobRateMissing ? (
                                <span className="basis-full text-[11px] leading-4 text-amber-300/90">
                                  {tc('jobPrinterRateMissing')}
                                </span>
                              ) : null}
                            </label>
                          ) : null}

                          {objectCount > 1 ? (
                            <div className="border-t border-white/[0.07] p-4">
                              <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                                <div>
                                  <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500">{tc('jobObjects')}</p>
                                  <p className="mt-1 text-xs leading-5 text-slate-400">
                                    {objectGroups.length > 1 ? tc('jobObjectsHint') : tc('jobObjectsSingleHint')}
                                  </p>
                                  {quoteMode === 'set' && objectGroups.length > 0 ? (
                                    <button
                                      type="button"
                                      aria-expanded={objectsOpen}
                                      onClick={() => setOpenObjectJobKeys((current) => {
                                        const next = new Set(current);
                                        if (next.has(job.key)) next.delete(job.key);
                                        else next.add(job.key);
                                        return next;
                                      })}
                                      className="mt-1.5 inline-flex items-center gap-1.5 text-xs font-medium text-cyan-200 transition-colors hover:text-white"
                                    >
                                      {objectsOpen
                                        ? tc('jobObjectsHide')
                                        : tc('jobObjectsShow').replace('{{count}}', String(objectGroups.length))}
                                      <ChevronDown className={`h-3.5 w-3.5 transition-transform ${objectsOpen ? 'rotate-180' : ''}`} />
                                    </button>
                                  ) : null}
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

                              {objectsOpen && objectGroups.length > 0 ? (
                                <div className="mt-3 grid min-w-0 gap-x-6 rounded-2xl border border-white/20 bg-white/10 px-3 py-1 lg:grid-cols-2 2xl:grid-cols-3">
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
                                        const compactLabel = parsedMaterial?.type
                                          || parsedMaterial?.name
                                          || matchingLine?.label
                                          || `T${numericToolIndex}`;
                                        const usageSpool = matchingLine?.selectionValue.startsWith('spool:')
                                          ? spools.find((spool) => spool.id === Number(matchingLine.selectionValue.slice('spool:'.length)))
                                          : null;
                                        const usageFilament = matchingLine?.selectionValue.startsWith('filament:')
                                          ? filaments.find((filament) => filament.id === Number(matchingLine.selectionValue.slice('filament:'.length)))
                                          : null;
                                        const displayColors = resolveMaterialDisplayColors(
                                          parsedMaterial?.color,
                                          usageSpool?.filament?.color_hex || usageFilament?.color_hex,
                                        );
                                        return {
                                          toolIndex: numericToolIndex,
                                          technicalLabel: matchingLine?.label
                                            || (parsedMaterial
                                              ? buildParsedMaterialLabel(parsedMaterial, `T${numericToolIndex}`)
                                              : `T${numericToolIndex}`),
                                          compactLabel,
                                          color: displayColors.primary,
                                          assignedColor: displayColors.assigned,
                                          weightG,
                                        };
                                      });
                                    return (
                                      <div
                                        key={`${job.key}-${group.name}-${groupIndex}`}
                                        className="min-w-0 border-b border-white/10 py-2 last:border-b-0"
                                      >
                                        <div className="flex min-w-0 items-baseline gap-x-2">
                                          <p className="min-w-0 truncate text-sm font-medium text-slate-100">{group.name || tc('jobObjectFallback')}</p>
                                          <span className="shrink-0 text-xs tabular-nums text-slate-400">× {group.count}</span>
                                          {config.repeats > 1 ? (
                                            <span className="shrink-0 text-xs tabular-nums text-slate-500">
                                              {tc('groupPartyLabel')}: {group.count * config.repeats}
                                            </span>
                                          ) : null}
                                          {groupMaterialUsages.length > 0 ? (
                                            <span className="ml-auto shrink-0 text-xs font-medium tabular-nums text-slate-300">
                                              {groupMaterialUsages
                                                .reduce((total, usage) => total + usage.weightG, 0)
                                                .toFixed(2)} {tc('grams')}
                                            </span>
                                          ) : null}
                                        </div>
                                        <div className="mt-1 min-w-0">
                                          {groupMaterialUsages.length > 0 ? (
                                            <div className="flex flex-wrap gap-1.5">
                                              {groupMaterialUsages.map((usage) => (
                                                 <span
                                                   key={`${job.key}-${group.name}-t${usage.toolIndex}`}
                                                   title={`T${usage.toolIndex} · ${usage.technicalLabel}`}
                                                   data-testid="calculator-group-material"
                                                   className="inline-flex items-center gap-1.5 rounded-md border border-cyan-400/15 bg-cyan-400/[0.06] px-1.5 py-0.5 text-[10px] text-cyan-100/85"
                                                   style={usage.color ? {
                                                     borderColor: filamentColorAlpha(usage.color, '66'),
                                                     backgroundColor: filamentColorAlpha(usage.color, '1f'),
                                                   } : undefined}
                                                 >
                                                   {usage.color ? (
                                                     <span className="relative inline-flex h-2.5 w-2.5 shrink-0">
                                                       <span
                                                         className="h-2.5 w-2.5 rounded-full border border-white/30"
                                                         style={{ backgroundColor: usage.color }}
                                                       />
                                                       {usage.assignedColor ? (
                                                         <span
                                                           className="absolute -bottom-0.5 -right-0.5 h-1.5 w-1.5 rounded-full border border-slate-900"
                                                           style={{ backgroundColor: usage.assignedColor }}
                                                         />
                                                       ) : null}
                                                     </span>
                                                   ) : null}
                                                   {usage.compactLabel} · {usage.weightG.toFixed(2)} {tc('grams')}
                                                 </span>
                                              ))}
                                            </div>
                                          ) : groupWeightG > 0 ? (
                                            <p className="text-[11px] text-slate-500">
                                              {tc('groupModelMaterialEstimate').replace('{{weight}}', groupWeightG.toFixed(2))}
                                            </p>
                                          ) : null}
                                        </div>
                                      </div>
                                    );
                                  })}
                                </div>
                              ) : objectGroups.length === 0 ? (
                                <p className="mt-3 text-xs leading-5 text-amber-200/80">
                                  {tc('objectGroupsUnavailable').replace('{{count}}', String(objectCount))}
                                </p>
                              ) : null}

                              {objectGroups.length > 1 && !canSplitGroups ? (
                                <p className="mt-3 text-xs leading-5 text-amber-200/80">{tc('groupSplitUnavailable')}</p>
                              ) : objectsOpen && objectGroups.length > 1 ? (
                                <p className="mt-3 text-xs leading-5 text-slate-500">
                                  {quoteMode === 'groups' ? tc('groupSplitActiveHint') : tc('groupSetActiveHint')}
                                </p>
                              ) : null}
                            </div>
                          ) : null}

                          <details className="group/time border-t border-white/[0.07]">
                            <summary className="flex min-h-11 cursor-pointer list-none flex-col items-start gap-1.5 px-4 py-2 marker:hidden sm:flex-row sm:items-center sm:gap-3">
                              {/* On desktop the width keeps the control in place whether the run
                                  is "2 ч 5 мин" or "14 ч 42 мин". */}
                              <span className="w-full min-w-0 break-words text-xs text-slate-400 sm:w-[13rem] sm:shrink-0">
                                {tc('plateTime')}: <strong className="font-medium text-slate-200">{formatHoursShort(config.printTimeSeconds / 3600, t('profilePage.calc.h'), t('profilePage.calc.min'))}</strong>
                              </span>
                              <span className="inline-flex min-w-0 items-center gap-1.5 text-xs font-medium text-cyan-200">
                                <span className="min-w-0 break-words">{tc('adjustPlateTime')}</span>
                                <ChevronDown className="h-3.5 w-3.5 shrink-0 transition-transform group-open/time:rotate-180" />
                              </span>
                            </summary>
                            <div className={`grid w-full min-w-0 grid-cols-1 gap-2 border-t border-white/[0.06] px-4 py-3 [&_input]:min-h-11 sm:w-[19rem] sm:grid-cols-3 ${compactFieldsClass}`}>
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
                              <div className="min-w-0 divide-y divide-white/10 rounded-2xl border border-white/20 bg-white/10 px-4">
                                {jobLinesByWeight.map(renderMaterialLine)}
                              </div>
                            ) : (
                              <p className="text-xs leading-5 text-slate-400">
                                {isFilamentsLoading || isSpoolsLoading ? tc('loadingMaterials') : tc('jobMaterialsUnavailable')}
                              </p>
                            )}

                            {jobServiceWeightG > 0 && jobTotalWeightG > 0 ? (
                              <div className="mt-3 rounded-2xl border border-white/20 bg-white/10 px-4 py-3">
                                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-xs">
                                  <span className="font-medium text-slate-200">{tc('serviceUsageTitle')}</span>
                                  <span className="font-medium tabular-nums text-amber-200">
                                    {jobServiceWeightG.toFixed(0)} / {jobTotalWeightG.toFixed(0)} {tc('grams')} — {servicePercent}%
                                  </span>
                                </div>
                                <div className="mt-2 flex h-1.5 overflow-hidden rounded-full bg-white/10">
                                  <span className="bg-emerald-400" style={{ width: `${((jobTotalWeightG - jobServiceWeightG) / jobTotalWeightG) * 100}%` }} />
                                  <span className="bg-orange-400" style={{ width: `${(jobRoleTotals.primeTower / jobTotalWeightG) * 100}%` }} />
                                  <span className="bg-violet-400" style={{ width: `${(jobRoleTotals.support / jobTotalWeightG) * 100}%` }} />
                                  <span className="bg-sky-400" style={{ width: `${(jobRoleTotals.brim / jobTotalWeightG) * 100}%` }} />
                                </div>
                                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500">
                                  <span className="inline-flex items-center gap-1.5 font-medium text-emerald-200">
                                    <span className="h-2 w-2 rounded-full bg-emerald-400" />
                                    {tc('serviceUsageInPart')}: {(jobTotalWeightG - jobServiceWeightG).toFixed(0)} {tc('grams')}
                                  </span>
                                  <span className="inline-flex items-center gap-1.5">
                                    <span className="h-2 w-2 rounded-full bg-orange-400" />
                                    {tc('materialPrimeTowerWeight')}: {jobRoleTotals.primeTower.toFixed(0)} {tc('grams')}
                                  </span>
                                  <span className="inline-flex items-center gap-1.5">
                                    <span className="h-2 w-2 rounded-full bg-violet-400" />
                                    {tc('materialSupportWeight')}: {jobRoleTotals.support.toFixed(0)} {tc('grams')}
                                  </span>
                                  <span className="inline-flex items-center gap-1.5">
                                    <span className="h-2 w-2 rounded-full bg-sky-400" />
                                    {tc('materialBrimWeight')}: {jobRoleTotals.brim.toFixed(0)} {tc('grams')}
                                  </span>
                                </div>
                                {jobServiceWeightG > jobTotalWeightG - jobServiceWeightG ? (
                                  <p className="mt-2 text-[11px] leading-4 text-slate-500">{tc('serviceUsageResliceHint')}</p>
                                ) : null}
                              </div>
                            ) : null}
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
                        } else if (value.startsWith('filament:')) {
                          onCatalogFilamentSelect(Number(value.slice('filament:'.length)));
                        } else {
                          onSpoolSelect('');
                          onCatalogFilamentSelect('');
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
                  {/* Two fields do not need a disclosure with a summary of themselves:
                      the summary said what the fields already show, and the toggle was
                      a control whose only outcome was hiding a required price. */}
                  <div className="rounded-[1.25rem] border border-white/[0.08] bg-black/15 p-3">
                    <p className="text-xs font-medium text-slate-200">{tc('materialCostBasis')}</p>
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
                  </div>
                </div>
                ) : null}
                {preflightLines.length > 0 ? (
                  <MaterialPreflightPanel
                    lines={preflightLines}
                    spools={spools}
                    result={preflightResult}
                    safetyBufferPercent={preflightSafetyBufferPercent}
                    isLoading={isPreflightLoading}
                    error={preflightError}
                    canRun={!isSpoolsLoading}
                    formatSpoolLabel={buildSpoolLabel}
                    onSafetyBufferChange={onPreflightSafetyBufferChange}
                    onSpoolIdsChange={onPreflightSpoolIdsChange}
                    onRefresh={onPreflightRefresh}
                  />
                ) : null}
              </WorkspacePanel>

            {!hasParsedJobs ? (
            <WorkspacePanel
              step={hasParsedJobs ? '3' : '2'}
              title={tc('workspaceProductionTitle')}
            >
              {/* Seconds are not typed by hand: nobody estimates a batch to the second,
                  and the field cost a stop on the way through the form. A sliced file
                  still brings them, where they are measured. */}
              {!hasParsedJobs ? (
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                  <FieldBlock label={t('profilePage.calc.quantity')}>
                    <NumberInput value={form.quantity} onChange={(value) => onChange('quantity', Math.max(1, value))} min="1" placeholder="1" />
                  </FieldBlock>
                  <FieldBlock label={t('profilePage.calc.hours')}>
                    <NumberInput value={form.timeHours} onChange={(value) => onChange('timeHours', value)} placeholder="0" />
                  </FieldBlock>
                  <FieldBlock label={t('profilePage.calc.minutes')}>
                    <NumberInput value={form.timeMinutes} onChange={(value) => onChange('timeMinutes', value)} placeholder="0" />
                  </FieldBlock>
                </div>
              ) : null}
              <PrinterCostRow
                printers={printers}
                selectedPrinterId={selectedPrinterId}
                onSelect={onPrinterSelect}
                pickedFromLabel={printerPickedFrom}
                rateMissing={orderMachineRateMissing}
                onFixRate={focusMachineEconomics}
                readinessEntries={economicsReadinessEntries}
                readinessLoading={economicsReadinessLoading}
                readinessError={economicsReadinessUnavailable}
              />
            </WorkspacePanel>
            ) : null}
            </div>
            </div>

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
                        {/* With one job the picker below already names the file; two copies of
                            the same name is noise. */}
                        {parsedJobs.length > 1 ? null : (
                          <p className="text-sm font-semibold text-white">{parsedGcode.file_name}</p>
                        )}
                        {parsedJobs.length > 1 ? (
                          <label className="flex max-w-xs items-center gap-3 text-xs text-slate-300">
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
                            {tc('fileSize')}: {formatBytes(parsedGcode.file_size_bytes, i18n.language) || '—'}
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

                    </div>
                  </div>

                  <div className={`grid grid-cols-1 items-start gap-4 ${showParsedMaterialsSection ? 'lg:grid-cols-3' : 'lg:grid-cols-2'}`}>
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
                          label={
                            parsedGcode.raft_layers != null && parsedGcode.raft_layers > 0
                              ? tc('parsedSupportAndRaftWeight')
                              : tc('parsedSupportWeight')
                          }
                          value={`${parsedGcode.support_filament_weight_g.toFixed(2)} ${tc('grams')}`}
                        />
                      ) : null}
                      {parsedGcode.brim_filament_weight_g != null
                        && parsedGcode.brim_filament_weight_g > 0 ? (
                        <CompactMetric
                          label={tc('parsedBrimWeight')}
                          value={`${parsedGcode.brim_filament_weight_g.toFixed(2)} ${tc('grams')}`}
                        />
                      ) : null}
                      {parsedGcode.prime_tower_filament_weight_g != null
                        && parsedGcode.prime_tower_filament_weight_g > 0 ? (
                        <CompactMetric
                          label={tc('parsedPrimeTowerWeight')}
                          value={`${parsedGcode.prime_tower_filament_weight_g.toFixed(2)} ${tc('grams')}`}
                        />
                      ) : null}
                      {parsedGcode.support_used && parsedGcode.support_filament_weight_g == null ? (
                        <p className="rounded-xl border border-amber-400/15 bg-amber-400/[0.07] px-3 py-2 text-xs leading-5 text-amber-100/85">
                          {tc('supportBreakdownUnavailable')}
                        </p>
                      ) : null}
                      <CompactMetric
                        label={tc('parsedLength')}
                        value={
                          parsedGcode.total_filament_length_mm != null
                            ? `${(parsedGcode.total_filament_length_mm / 1000).toFixed(2)} ${tc('unitMeters')}`
                            : '—'
                        }
                      />
                      <CompactMetric
                        label={tc('parsedVolume')}
                        value={
                          parsedGcode.total_filament_volume_cm3 != null
                            ? `${parsedGcode.total_filament_volume_cm3.toFixed(2)} ${tc('unitCm3')}`
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
                      {parsedGcode.object_filament_weight_g != null ? (
                        <CompactMetric
                          label={tc('parsedObjectScopeWeight')}
                          value={`${parsedGcode.object_filament_weight_g.toFixed(2)} ${tc('grams')}`}
                        />
                      ) : null}
                      {parsedGcode.shared_filament_weight_g != null
                        && parsedGcode.shared_filament_weight_g > 0 ? (
                        <CompactMetric
                          label={tc('parsedSharedWeight')}
                          value={`${parsedGcode.shared_filament_weight_g.toFixed(2)} ${tc('grams')}`}
                        />
                      ) : null}
                      <CompactMetric
                        label={tc('parsedMaxHeight')}
                        value={parsedGcode.max_z_height_mm != null ? `${parsedGcode.max_z_height_mm} ${tc('unitMm')}` : '—'}
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
                          <div className="mt-3 flex flex-col gap-1.5">
                            {parsedGcode.materials.map((material, index) => {
                              const materialColor = normalizeFilamentColor(material.color);
                              return (
                              <div
                                key={`${material.name ?? material.type ?? 'material'}-${index}`}
                                title={buildParsedMaterialLabel(material, tc('unknownMaterial'))}
                                className="flex w-full min-w-0 items-center gap-2 rounded-lg border border-cyan-400/20 bg-cyan-400/10 px-2 py-1 text-[10px] leading-4 text-cyan-100"
                                style={materialColor ? {
                                  borderColor: filamentColorAlpha(materialColor, '66'),
                                  backgroundColor: filamentColorAlpha(materialColor, '1f'),
                                } : undefined}
                              >
                                {materialColor ? (
                                  <span
                                    className="h-2.5 w-2.5 shrink-0 rounded-full border border-white/30"
                                    style={{ backgroundColor: materialColor }}
                                    title={`${tc('colorFromGcode')}: ${materialColor}`}
                                  />
                                ) : null}
                                <span className="min-w-0 flex-1 truncate font-medium text-white">
                                  {buildParsedMaterialLabel(material, tc('unknownMaterial'))}
                                </span>
                                {material.weight_g != null ? (
                                  <span className="shrink-0 whitespace-nowrap tabular-nums">
                                    {material.weight_g.toFixed(2)} {tc('grams')}
                                  </span>
                                ) : null}
                              </div>
                              );
                            })}
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
                    <div className="md:col-span-2 space-y-3 rounded-2xl border border-white/10 bg-white/[0.03] p-3">
                      <div>
                        <p className="text-xs font-semibold text-slate-200">{tc('modelPrepTitle')}</p>
                        <p className="mt-0.5 text-xs leading-5 text-slate-400">{tc('modelPrepHint')}</p>
                      </div>
                      <div>
                        <FieldBlock label={tc('scanningTitle')} hint={tc('scanningHint')}>
                          <div className="max-w-[12rem]">
                            <InputWithSuffix
                              value={form.scanningPrice}
                              onChange={(value) => onChange('scanningPrice', value)}
                              placeholder="0"
                              suffix={currencySymbol(quoteProfile.currency)}
                            />
                          </div>
                        </FieldBlock>
                      </div>
                      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                        <FieldBlock label={t('profilePage.calc.modelingHours')}>
                          <NumberInput value={form.modelingHours} onChange={(value) => onChange('modelingHours', value)} placeholder="0" />
                        </FieldBlock>
                        <FieldBlock label={t('profilePage.calc.modelingMinutes')}>
                          <NumberInput value={form.modelingMinutes} onChange={(value) => onChange('modelingMinutes', value)} placeholder="0" />
                        </FieldBlock>
                      </div>
                    </div>
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

      </div>

      {result || estimateError ? (
      <div ref={resultsRef} data-testid="calculator-result" className="order-2 min-w-0 scroll-mt-6">
        <SurfaceCard className="p-5 md:p-6">
          <div className="flex items-center justify-between gap-4">
            <SectionHeading icon={<Calculator className="h-5 w-5 text-cyan-300" />} title={tc('resultsTitle')} compact />
            <div className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-cyan-200">
              {result ? tc('lastEstimate') : tc('estimateFailed')}
            </div>
          </div>

          {result ? (
            <>
              <div className="mt-5 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-[1.3fr_repeat(3,minmax(0,0.72fr))]">
              <div className="overflow-hidden rounded-[1.45rem] border border-cyan-400/20 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.18),transparent_45%),linear-gradient(145deg,rgba(14,116,144,0.2),rgba(76,29,149,0.26))] p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-300">{tc('customerPriceTitle')}</p>
                <p className="mt-3 text-4xl font-bold tracking-tight text-white">{formatCurrency(result.cost_final || result.cost_total)}</p>
                {/* Shown only once a number exists: the point is not to advertise a
                    feature but to say what the number they are looking at is worth. */}
                {!hasParsedJobs ? (
                  <p className="mt-3 flex items-start gap-1.5 rounded-xl border border-cyan-400/20 bg-cyan-400/[0.07] px-3 py-2 text-xs leading-5 text-cyan-100/90">
                    <Sparkles className="mt-0.5 h-3.5 w-3.5 shrink-0 text-cyan-300" />
                    <span>{tc('manualEstimateHint')}</span>
                  </p>
                ) : null}
                {approximateNotes.length > 0 ? (
                  <p className="mt-2 flex items-start gap-1.5 text-xs leading-4 text-amber-300/90">
                    <AlertTriangle className="mt-px h-3.5 w-3.5 shrink-0" />
                    <span>
                      {tc('resultApproximate')}
                      <span className="text-amber-200/70"> · {approximateNotes.join(', ')}</span>
                    </span>
                  </p>
                ) : null}
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

              <div className="contents">
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
              </div>

              <details className="group/results mt-4 rounded-[1.25rem] border border-white/[0.08] bg-black/15">
                <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 marker:hidden">
                  <span className="text-sm font-medium text-slate-200">{tc('detailedResults')}</span>
                  <ChevronDown className="h-4 w-4 text-cyan-200 transition-transform group-open/results:rotate-180" />
                </summary>
              <div className="grid grid-cols-1 gap-4 border-t border-white/[0.07] p-4 md:grid-cols-2 2xl:grid-cols-4">
                <SectionPanel title={tc('resultsCostStructureTitle')}>
                  <MetricRow label={t('profilePage.calc.material')} value={formatCurrency(result.cost_material)} />
                  {result.material_line_costs?.length ? (
                    <div className="mx-3 mb-2 rounded-xl border border-white/[0.06] bg-black/15 px-3 py-2">
                      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
                        {tc('materialCostBreakdown')}
                      </p>
                      <div className="space-y-1.5">
                        {result.material_line_costs.map((line) => {
                          const roleCosts = line.role_costs?.length
                            ? line.role_costs
                            : line.support_weight_source === 'gcode_extrusion_roles'
                              && line.support_weight_g != null
                              && line.support_cost != null
                              ? [{
                                  role: 'support' as const,
                                  weight_g: line.support_weight_g,
                                  cost: line.support_cost,
                                  source: line.support_weight_source,
                                }]
                              : [];
                          const visibleRoleCosts = roleCosts.filter((roleCost) => roleCost.weight_g > 0);
                          const otherWeightG = line.other_weight_g
                            ?? (roleCosts.length > 0 ? line.non_support_weight_g : null);
                          const otherCost = line.other_cost
                            ?? (roleCosts.length > 0 ? line.non_support_cost : null);
                          return (
                            <div key={line.line_id} className="text-xs">
                              <div className="flex min-w-0 items-baseline gap-2">
                                {/* The job name only tells them apart when there are several;
                                    on a single plate it just repeats before every material. */}
                                {isBatchMode && line.job_key && jobTitleByKey.has(line.job_key) ? (
                                  <span className="shrink-0 text-slate-500">{jobTitleByKey.get(line.job_key)}</span>
                                ) : null}
                                <span
                                  className="min-w-0 flex-1 truncate text-slate-200"
                                  title={line.label ?? undefined}
                                >
                                  {line.label || (line.tool_index != null ? `T${line.tool_index}` : tc('unknownMaterial'))}
                                </span>
                                <span className="shrink-0 whitespace-nowrap tabular-nums text-slate-400">
                                  {line.weight_g.toFixed(2)} {tc('grams')}
                                </span>
                                <span className="w-20 shrink-0 text-right font-medium tabular-nums text-white">{formatCurrency(line.cost)}</span>
                              </div>
                              {visibleRoleCosts.length > 0
                                && otherWeightG != null
                                && otherCost != null ? (
                                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 pl-2 text-[11px] text-slate-500">
                                  {visibleRoleCosts.map((roleCost) => (
                                    <span key={roleCost.role}>
                                      {roleCost.role === 'support'
                                        ? jobsWithRaft.has(line.job_key ?? '')
                                          ? tc('materialSupportAndRaftCost')
                                          : tc('materialSupportCost')
                                        : roleCost.role === 'brim'
                                          ? tc('materialBrimCost')
                                          : tc('materialPrimeTowerCost')}: {roleCost.weight_g.toFixed(2)} {tc('grams')} · {formatCurrency(roleCost.cost)}
                                    </span>
                                  ))}
                                  <span>
                                    {tc('materialNonSupportCost')}: {otherWeightG.toFixed(2)} {tc('grams')} · {formatCurrency(otherCost)}
                                  </span>
                                </div>
                              ) : null}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ) : null}
                  <MetricRow label={t('profilePage.calc.electricityLabel')} value={formatCurrency(result.cost_electricity)} />
                  {(result.cost_scanning ?? 0) > 0 ? (
                    <MetricRow label={t('profilePage.calculator.scanningTitle')} value={formatCurrency(result.cost_scanning ?? 0)} />
                  ) : null}
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
              </details>

              <div className="mt-6 grid grid-cols-1 gap-3 md:grid-cols-3">
                <button
                  type="button"
                  onClick={onAddToQuote}
                  disabled={isSavingHistory}
                  title={tc('quoteDraftActionHint')}
                  className={`${ghostButtonClass} w-full disabled:cursor-wait disabled:opacity-60`}
                >
                  <Plus className="h-4 w-4" />
                  {tc('addToQuote')}
                </button>
                <button
                  type="button"
                  onClick={onOpenQuote}
                  title={tc('quoteOpenActionHint')}
                  className="relative inline-flex w-full items-center justify-center gap-2 rounded-2xl border border-cyan-400/20 bg-cyan-400/10 px-4 py-3 text-sm font-medium text-cyan-100 transition-all hover:bg-cyan-400/20 hover:text-white"
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
          ) : estimateError ? (
            <div className="mt-5 rounded-[1.35rem] border border-red-400/25 bg-red-500/10 px-5 py-4 text-sm text-red-100">
              {t('profilePage.calc.error')}: {estimateError}
            </div>
          ) : null}
        </SurfaceCard>
      </div>
      ) : null}

      {/* Rendered outside <main>: it sits in its own stacking context, so a floating
          button inside it always slides under the footer no matter how high its z-index. */}
      {showCalculateAction ? createPortal(
        <div className={`fixed z-[70] max-w-[calc(100vw-2.5rem)] ${insidePlugin ? 'bottom-24 right-6' : 'bottom-5 right-5 lg:bottom-8 lg:right-8'}`}>
          <button
            type="button"
            data-testid="calculator-floating-action"
            onClick={handleCalculateAction}
            disabled={!calculateActionEnabled}
            className="inline-flex min-h-14 items-center justify-center gap-3 rounded-2xl border border-cyan-200/20 bg-[linear-gradient(135deg,rgba(8,145,178,0.96),rgba(124,58,237,0.96))] px-5 py-3 text-sm font-semibold text-white shadow-[0_22px_55px_-20px_rgba(34,211,238,0.85)] backdrop-blur-xl transition-all hover:-translate-y-0.5 hover:shadow-[0_26px_60px_-20px_rgba(124,58,237,0.9)] disabled:cursor-not-allowed disabled:border-amber-300/15 disabled:bg-[linear-gradient(135deg,rgba(51,65,85,0.96),rgba(30,41,59,0.96))] disabled:text-slate-300 disabled:shadow-none"
          >
            {isCalculating ? <Loader2 className="h-5 w-5 animate-spin" /> : <Calculator className="h-5 w-5" />}
            <span>
              {isCalculating
                ? t('profilePage.calc.calculating')
                : materialsReadyForCalculation
                  ? tc('calculateOrder')
                  : tc('completeMaterialsAction')}
            </span>
          </button>
        </div>,
        document.body,
      ) : null}
    </div>
  );
};

interface HistoryViewProps {
  entries: CalculatorHistoryEntrySummary[];
  historyLoadError: string | null;
  historyLoadMoreError: string | null;
  isDeletingHistory: boolean;
  restoringEntryId: number | null;
  failedRestoreEntryId: number | null;
  isLoading: boolean;
  isLoadingMore: boolean;
  hasMore: boolean;
  total: number;
  onRetryLoad: () => void;
  onLoadMore: () => void;
  onDeleteEntry: (entry: CalculatorHistoryEntrySummary) => void;
  onRestoreEntry: (entry: CalculatorHistoryEntrySummary) => void;
  formatCurrency: (value: number | null | undefined) => string;
}

export const HistoryView: React.FC<HistoryViewProps> = ({
  entries,
  historyLoadError,
  historyLoadMoreError,
  isDeletingHistory,
  restoringEntryId,
  failedRestoreEntryId,
  isLoading,
  isLoadingMore,
  hasMore,
  total,
  onRetryLoad,
  onLoadMore,
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
        <div className="mt-6 rounded-[1.25rem] border border-red-400/25 bg-red-500/10 px-4 py-3 text-sm text-red-100" role="alert">
          <p>{historyLoadError}</p>
          <button
            type="button"
            onClick={onRetryLoad}
            className="mt-3 inline-flex items-center rounded-xl border border-red-300/25 px-3 py-2 text-sm font-medium transition hover:bg-red-300/10"
          >
            {t('common.retry')}
          </button>
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
            const filamentLabel =
              entry.filament_snapshot != null
                ? [entry.filament_snapshot.brand_name, entry.filament_snapshot.name].filter(Boolean).join(' · ')
                : null;
            const isRestoring = restoringEntryId === entry.id;

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
                      <HistoryTag label={tc('totalCost')} value={formatCurrency(entry.total_cost)} />
                      <HistoryTag label={t('profilePage.calc.quantity')} value={String(entry.quantity)} />
                      <HistoryTag
                        label={tc('sourceLabel')}
                        value={entry.source === 'gcode' ? tc('sourceGcode') : tc('sourceManual')}
                      />
                      {entry.gcode_file ? <HistoryTag label={tc('parsedFile')} value={entry.gcode_file} /> : null}
                      {filamentLabel ? <HistoryTag label={tc('materialLabel')} value={filamentLabel} /> : null}
                    </div>
                  </div>

                  <div className="flex flex-col gap-2 sm:flex-row">
                    <button
                      type="button"
                      onClick={() => void onRestoreEntry(entry)}
                      disabled={restoringEntryId !== null}
                      className={`${ghostButtonClass} disabled:cursor-not-allowed disabled:opacity-60`}
                    >
                      {isRestoring ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
                      {failedRestoreEntryId === entry.id ? t('common.retry') : tc('restoreHistoryEntry')}
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
          {historyLoadMoreError ? (
            <p className="text-sm text-red-200">{historyLoadMoreError}</p>
          ) : null}
          {hasMore ? (
            <button
              type="button"
              onClick={onLoadMore}
              disabled={isLoadingMore}
              className={`${ghostButtonClass} disabled:cursor-not-allowed disabled:opacity-60`}
            >
              {isLoadingMore ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {isLoadingMore ? tc('historyLoadingMore') : tc('historyLoadMore')}
            </button>
          ) : null}
        </div>
      )}
    </SurfaceCard>
  );
};

interface QuoteModalProps {
  isOpen: boolean;
  embedded?: boolean;
  source: 'manual' | 'gcode';
  quoteParties: QuotePartyFormState;
  result: CalculatorEstimateResponse | null;
  quoteItems: QuoteItem[];
  customers: CrmCustomer[];
  customersLoading: boolean;
  customerSelection: string;
  onRemoveFromQuote: (id: string) => void;
  onRenameQuoteItem: (id: string, title: string) => void;
  onClearQuoteItems: () => void;
  onClose: () => void;
  onPartyChange: <K extends keyof QuotePartyFormState>(field: K, value: QuotePartyFormState[K]) => void;
  onCustomerSelection: (selection: string) => void;
  onSaveToWorkspace: () => void;
  onPrint: () => void;
  onShare: () => void;
  onDownloadPdf: () => void;
  isSharing: boolean;
  shareCopied: boolean;
  isPdfDownloading: boolean;
  isSavingToWorkspace: boolean;
  isLoggedIn: boolean;
  formatCurrency: (value: number | null | undefined) => string;
  customerDelivery: string;
  onCustomerDeliveryChange: (value: string) => void;
  byWorkAvailable: boolean;
  currencySymbol: string;
  taxDisclosureAvailable: boolean;
  taxSeparateAvailable: boolean;
  taxKind: 'tax' | 'vat';
  onTaxKindChange: (kind: 'tax' | 'vat') => void;
  taxMode: 'hide' | 'included' | 'separate';
  onTaxModeChange: (mode: 'hide' | 'included' | 'separate') => void;
  showCostBreakdown: boolean;
  onShowCostBreakdownChange: (value: boolean) => void;
  costBreakdownNote: string;
  onCostBreakdownNoteChange: (value: string) => void;
}

const QuoteModal: React.FC<QuoteModalProps> = ({
  isOpen,
  embedded = false,
  source,
  quoteParties,
  result,
  quoteItems,
  customers,
  customersLoading,
  customerSelection,
  onRemoveFromQuote,
  onRenameQuoteItem,
  onClearQuoteItems,
  onClose,
  onPartyChange,
  onCustomerSelection,
  onSaveToWorkspace,
  onPrint,
  onShare,
  onDownloadPdf,
  isSharing,
  shareCopied,
  isPdfDownloading,
  isSavingToWorkspace,
  isLoggedIn,
  formatCurrency,
  customerDelivery,
  onCustomerDeliveryChange,
  byWorkAvailable,
  currencySymbol,
  taxDisclosureAvailable,
  taxSeparateAvailable,
  taxKind,
  onTaxKindChange,
  taxMode,
  onTaxModeChange,
  showCostBreakdown,
  onShowCostBreakdownChange,
  costBreakdownNote,
  onCostBreakdownNoteChange,
}) => {
  const { t } = useTranslation();
  const insidePluginEmbed = isPluginEmbed();
  const tc = (key: string) => translateCalculator(t, key);
  const isHeaderVisible = useHeaderVisible();

  if (!isOpen || (!result && quoteItems.length === 0)) {
    return null;
  }

  const hasItems = quoteItems.length > 0;
  const displayTotal = hasItems
    ? quoteItems.reduce((sum, qi) => sum + qi.lineItem.totalPrice, 0)
    : result?.cost_total ?? 0;
  const customerDeliveryValue = Math.max(0, Number(customerDelivery) || 0);

  return (
    <ModalOverlay
      onClose={onClose}
      className={`!bg-slate-950/75 !backdrop-blur-md ${isHeaderVisible ? 'pt-[88px]' : ''}`}
      contentClassName="flex min-h-full items-center justify-center p-4 md:p-6"
    >
      <div
        className="w-full max-w-4xl overflow-hidden rounded-[2rem] border border-white/10 bg-[linear-gradient(180deg,rgba(15,23,42,0.95),rgba(15,23,42,0.9))] shadow-[0_40px_120px_-60px_rgba(15,23,42,1)]"
        onClick={(event) => event.stopPropagation()}
      >
          <div className="flex items-start justify-between gap-3 border-b border-white/10 px-5 py-3.5 md:px-6 md:py-4">
            <div className="min-w-0">
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/20 bg-cyan-400/10 px-2.5 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-cyan-200">
                {source === 'gcode' ? tc('sourceGcode') : tc('sourceManual')}
              </div>
              <h2 className="mt-1.5 text-xl font-semibold text-white md:text-2xl">{tc('quoteBuilderTitle')}</h2>
              <p className="mt-1 max-w-2xl text-sm leading-5 text-slate-300">{tc('quoteBuilderDescription')}</p>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-white/5 text-slate-300 transition-all hover:bg-white/10 hover:text-white"
            >
              <X className="h-5 w-5" />
            </button>
          </div>

          <div className="grid grid-cols-1 gap-6 px-6 py-6 md:px-7 lg:grid-cols-[minmax(0,1.1fr)_minmax(20rem,0.9fr)]">
            <div className="space-y-6">
              <div className="rounded-[1.5rem] border border-white/10 bg-white/5 p-5">
                <div className="flex items-center gap-3">
                  <div className="flex h-11 w-12 shrink-0 items-center justify-center rounded-[1rem] border border-white/10 bg-white/5">
                    <Printer3DIcon className="h-5 w-5 text-cyan-300" />
                  </div>
                  <div>
                    <p className="text-base font-semibold text-white">{tc('quoteSellerSection')}</p>
                    <p className="mt-1 text-sm text-slate-400">{tc('quoteSellerDescription')}</p>
                  </div>
                </div>

                <div className="mt-5">
                  <FieldBlock label={tc('quoteCustomerSelect')} hint={tc('quoteCustomerSelectHint')}>
                    <select
                      className={inputClass}
                      value={customerSelection}
                      disabled={customersLoading}
                      onChange={(event) => onCustomerSelection(event.target.value)}
                    >
                      <option value="new">{tc('quoteCustomerNew')}</option>
                      <option value="none">{tc('quoteCustomerNone')}</option>
                      {customers.map((customer) => (
                        <option key={customer.id} value={`customer:${customer.id}`}>
                          {customer.name}{customer.inn ? ` · ${customer.inn}` : ''}
                        </option>
                      ))}
                    </select>
                  </FieldBlock>
                </div>

                <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-2">
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
                      placeholder={quoteMarketRules(
                        resolveQuoteMarket(quoteParties.quoteMarket, quoteParties.currency),
                      ).phonePlaceholder}
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
                    <p className="text-sm text-slate-200">{tc('quoteDisclaimerNotOffer')}</p>
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
              <div className="rounded-[1.5rem] border border-white/10 bg-white/5 p-5">
                <QuoteDisclosureSettings
                  byWork={showCostBreakdown}
                  onByWorkChange={onShowCostBreakdownChange}
                  byWorkAvailable={byWorkAvailable}
                  note={costBreakdownNote}
                  onNoteChange={onCostBreakdownNoteChange}
                  taxKind={taxKind}
                  onTaxKindChange={onTaxKindChange}
                  taxMode={taxMode}
                  onTaxModeChange={onTaxModeChange}
                  taxAvailable={taxDisclosureAvailable}
                  taxSeparateAvailable={taxSeparateAvailable}
                  delivery={customerDeliveryValue}
                  onDeliveryChange={(value) => onCustomerDeliveryChange(value > 0 ? String(value) : '')}
                  currencySymbol={currencySymbol}
                />
              </div>
              <div className="rounded-[1.5rem] border border-cyan-400/20 bg-cyan-400/10 p-5">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-cyan-200">{tc('quoteSummaryTitle')}</p>
                <p className="mt-3 text-3xl font-semibold tracking-tight text-white">{formatCurrency(displayTotal + customerDeliveryValue)}</p>
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
                      {buildQuoteDisclaimerLabel(t)}
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
                  onClick={onSaveToWorkspace}
                  disabled={isSavingToWorkspace}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-[1.4rem] bg-[linear-gradient(135deg,#f59e0b,#0891b2)] px-5 py-4 text-sm font-semibold text-white shadow-[0_18px_35px_-18px_rgba(245,158,11,0.62)] transition-all hover:translate-y-[-1px] disabled:cursor-wait disabled:opacity-55"
                >
                  {isSavingToWorkspace ? <Loader2 className="h-4 w-4 animate-spin" /> : <BriefcaseBusiness className="h-4 w-4" />}
                  {tc('quoteSaveWorkspaceAction')}
                </button>
                {!insidePluginEmbed && <button
                  type="button"
                  onClick={onPrint}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-[1.4rem] bg-[linear-gradient(135deg,#0891b2,#7c3aed)] px-5 py-4 text-sm font-semibold text-white shadow-[0_18px_35px_-18px_rgba(6,182,212,0.7)] transition-all hover:translate-y-[-1px] hover:shadow-[0_22px_42px_-18px_rgba(124,58,237,0.72)]"
                >
                  <FileText className="h-4 w-4" />
                  {tc('quotePrintAction')}
                </button>}
                {isLoggedIn && (
                  <button
                    type="button"
                    onClick={onDownloadPdf}
                    disabled={isPdfDownloading}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-[1.4rem] border border-cyan-400/20 bg-cyan-400/10 px-5 py-4 text-sm font-semibold text-cyan-200 transition-all hover:bg-cyan-400/20 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isPdfDownloading ? <Loader2 className="h-4 w-4 animate-spin" /> : <CloudDownload className="h-4 w-4" />}
                    {tc(insidePluginEmbed ? 'quoteSavePdfAction' : 'quoteDownloadPdfAction')}
                  </button>
                )}
                {isLoggedIn && (
                  <button
                    type="button"
                    onClick={onShare}
                    disabled={isSharing}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-[1.4rem] border border-cyan-400/20 bg-cyan-400/10 px-5 py-4 text-sm font-semibold text-cyan-200 transition-all hover:bg-cyan-400/20 hover:text-white disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isSharing ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : shareCopied ? (
                      <Check className="h-4 w-4" />
                    ) : (
                      <Link2 className="h-4 w-4" />
                    )}
                    {shareCopied ? tc('quoteShareCopied') : tc('quoteShareAction')}
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
    </ModalOverlay>
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

const compactFieldsClass = [
  '[&_label>span:first-child]:min-h-0',
  '[&_label>span:first-child]:mb-1',
  '[&_label>span:first-child]:text-xs',
  '[&_label>span:first-child]:leading-4',
  '[&_input]:py-2',
  '[&_select]:py-2',
  '[&_label>div>div:first-child]:max-w-[13rem]',
  '[&_select]:max-w-[13rem]',
].join(' ');

const WorkspacePanel: React.FC<{
  /** Omitted for a panel that is an offer rather than a step to be taken. */
  step?: string;
  title: string;
  description?: string;
  children: ReactNode;
}> = ({ step, title, description, children }) => (
  <div className="rounded-[1.55rem] border border-white/10 bg-white/5 p-5 shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
    <div className="flex items-start gap-3">
      {step ? <StepBadge step={step} /> : null}
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
