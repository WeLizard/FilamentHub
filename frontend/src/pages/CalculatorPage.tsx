/**
 * Calculator Pro page wired to the current backend estimate API.
 * G-code parsing and history persistence remain separate future phases.
 */

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Calculator,
  CheckCircle2,
  Clock,
  DollarSign,
  Download,
  FileText,
  Loader2,
  Package,
  Save,
  Settings2,
  Trash2,
  TrendingUp,
  Upload,
  Weight,
  Zap,
} from 'lucide-react';
import { calculatorAPI, filamentsAPI } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import type { CalculatorEstimateRequest, CalculatorEstimateResponse, Filament, PricingMethod } from '../types/api';

const surfaceClass =
  'relative overflow-hidden rounded-[2rem] border border-white/10 bg-[linear-gradient(180deg,rgba(15,23,42,0.88),rgba(15,23,42,0.72))] shadow-[0_30px_90px_-50px_rgba(15,23,42,0.95)] backdrop-blur-xl';
const inputClass =
  'w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-400/60 focus:border-transparent transition-all';
const ghostButtonClass =
  'inline-flex items-center justify-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-4 py-3 text-sm font-medium text-white transition-all hover:bg-white/10';

type CalculatorTab = 'calculator' | 'history';

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
  modelingHours: number;
  modelingMinutes: number;
  modelingRatePerHour: number;
  postprocessingHours: number;
  postprocessingMinutes: number;
  postprocessingRatePerHour: number;
  printingRatePerHour: number;
  amortizationRatePerHour: number;
  quantity: number;
  overheadPercent: number;
  markupPercent: number;
  urgencyCoefficient: number;
  complexityCoefficient: number;
  volumeDiscountCoefficient: number;
  fixedCosts: number;
  minOrderPrice: number;
  roundToNearest: number;
}

const DEFAULT_FORM_STATE: CalculatorFormState = {
  selectedFilamentId: '',
  pricingMethod: 'combined',
  weightG: 531,
  supportsWeightG: 0,
  supportsLossCoefficient: 1.2,
  spoolPrice: 1200,
  spoolWeightKg: 1,
  deliveryCost: 0,
  timeHours: 13,
  timeMinutes: 40,
  timeSec: 0,
  pricePerHour: 170,
  electricityCostPerKwh: 6,
  printerPowerW: 350,
  modelingHours: 0,
  modelingMinutes: 0,
  modelingRatePerHour: 934,
  postprocessingHours: 0,
  postprocessingMinutes: 2,
  postprocessingRatePerHour: 100,
  printingRatePerHour: 170,
  amortizationRatePerHour: 16,
  quantity: 4,
  overheadPercent: 20,
  markupPercent: 30,
  urgencyCoefficient: 1.0,
  complexityCoefficient: 1.0,
  volumeDiscountCoefficient: 1.0,
  fixedCosts: 0,
  minOrderPrice: 0,
  roundToNearest: 10,
};

const formatCurrency = (value: number | null | undefined): string =>
  value == null || !Number.isFinite(value) ? '—' : `${value.toFixed(2)} ₽`;

const formatQuantity = (value: number): string => `${value}`;

const toHours = (hours: number, minutes: number, seconds: number): number =>
  hours + minutes / 60 + seconds / 3600;

const buildFilamentLabel = (filament: Filament): string =>
  [filament.brand_name, filament.name, filament.material_type].filter(Boolean).join(' · ');

const deriveSpoolDefaults = (
  filament: Filament,
): { spoolPrice: number | null; spoolWeightKg: number | null } => {
  const spoolWeightKg = filament.spool_weight ? Number((filament.spool_weight / 1000).toFixed(3)) : null;
  const spoolPrice =
    filament.price_per_kg != null
      ? Number((((filament.spool_weight ?? 1000) * filament.price_per_kg) / 1000).toFixed(2))
      : null;

  return { spoolPrice, spoolWeightKg };
};

const buildEstimateRequest = (form: CalculatorFormState): CalculatorEstimateRequest => {
  const requestData: CalculatorEstimateRequest = {
    pricing_method: form.pricingMethod,
    quantity: form.quantity,
    round_to_nearest: form.roundToNearest || undefined,
  };

  if (form.pricingMethod === 'by_weight' || form.pricingMethod === 'combined') {
    requestData.weight_g = form.weightG;
    requestData.supports_weight_g = form.supportsWeightG || undefined;
    requestData.supports_loss_coefficient = form.supportsLossCoefficient || undefined;
    requestData.spool_price = form.spoolPrice;
    requestData.spool_weight_kg = form.spoolWeightKg;
    requestData.delivery_cost = form.deliveryCost || undefined;
  }

  if (form.pricingMethod === 'by_time' || form.pricingMethod === 'combined') {
    requestData.time_hours = form.timeHours;
    requestData.time_minutes = form.timeMinutes;
    requestData.time_sec = form.timeSec || undefined;
  }

  if (form.pricingMethod === 'by_time') {
    requestData.price_per_hour = form.pricePerHour;
  }

  if (form.electricityCostPerKwh && form.printerPowerW) {
    requestData.electricity_cost_per_kwh = form.electricityCostPerKwh;
    requestData.printer_power_w = form.printerPowerW;
  }

  if (form.pricingMethod === 'combined') {
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
    requestData.urgency_coefficient = form.urgencyCoefficient !== 1.0 ? form.urgencyCoefficient : undefined;
    requestData.complexity_coefficient = form.complexityCoefficient !== 1.0 ? form.complexityCoefficient : undefined;
    requestData.volume_discount_coefficient =
      form.volumeDiscountCoefficient !== 1.0 ? form.volumeDiscountCoefficient : undefined;
    requestData.fixed_costs = form.fixedCosts || undefined;
    requestData.min_order_price = form.minOrderPrice || undefined;
  }

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

export const CalculatorPage: React.FC = () => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<CalculatorTab>('calculator');
  const [form, setForm] = useState<CalculatorFormState>(DEFAULT_FORM_STATE);

  const filamentsQuery = useQuery({
    queryKey: ['calculator-pro', 'filaments'],
    queryFn: () =>
      filamentsAPI.list({
        active_only: true,
        size: 100,
      }),
    staleTime: 60_000,
  });

  const calculateMutation = useMutation({
    mutationFn: (data: CalculatorEstimateRequest) => calculatorAPI.estimate(data),
  });

  const result = calculateMutation.data ?? null;
  const selectedFilament = useMemo(
    () => filamentsQuery.data?.items.find((filament) => filament.id === form.selectedFilamentId) ?? null,
    [filamentsQuery.data?.items, form.selectedFilamentId],
  );

  useEffect(() => {
    if (!selectedFilament) {
      return;
    }

    const defaults = deriveSpoolDefaults(selectedFilament);

    setForm((prev) => ({
      ...prev,
      spoolPrice: defaults.spoolPrice ?? prev.spoolPrice,
      spoolWeightKg: defaults.spoolWeightKg ?? prev.spoolWeightKg,
    }));
  }, [selectedFilament]);

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

  const currentWorkTimeHours = useMemo(
    () => toHours(form.timeHours, form.timeMinutes, form.timeSec),
    [form.timeHours, form.timeMinutes, form.timeSec],
  );

  const summaryTotal = result ? result.cost_final || result.cost_total : null;
  const summaryTime = result?.total_time_hours ?? result?.time_hours ?? currentWorkTimeHours;

  const updateField = <K extends keyof CalculatorFormState>(field: K, value: CalculatorFormState[K]) => {
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const handleCalculate = () => {
    calculateMutation.mutate(buildEstimateRequest(form));
  };

  return (
    <div className="space-y-6">
      <section className={`${surfaceClass} p-0`}>
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.18),transparent_34%),radial-gradient(circle_at_85%_18%,rgba(251,191,36,0.16),transparent_28%),radial-gradient(circle_at_50%_120%,rgba(16,185,129,0.12),transparent_42%)]" />
        <div className="relative px-6 py-7 md:px-8 md:py-8">
          <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
            <div className="max-w-3xl">
              <div className="inline-flex items-center gap-2 rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.22em] text-cyan-200">
                Calculator Pro
              </div>
              <div className="mt-4 flex items-start gap-4">
                <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-[1.4rem] border border-white/10 bg-white/10 shadow-[inset_0_1px_0_rgba(255,255,255,0.15)]">
                  <Calculator className="h-8 w-8 text-cyan-300" />
                </div>
                <div>
                  <h1 className="text-2xl font-bold text-white md:text-4xl">{t('calculator.title')}</h1>
                  <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-300 md:text-base">
                    {t('calculator.subtitle')}
                  </p>
                </div>
              </div>
            </div>

            <div className="grid gap-3 sm:min-w-[24rem] sm:grid-cols-3">
              <MetricTile label={t('calculator.totalCost')} value={formatCurrency(summaryTotal)} />
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
              label={t('calculator.tabs.calculator')}
              onClick={() => setActiveTab('calculator')}
            />
            <TabButton
              active={activeTab === 'history'}
              icon={<Clock className="h-4 w-4" />}
              label={t('calculator.tabs.history')}
              onClick={() => setActiveTab('history')}
            />
          </div>
        </div>
      </section>

      {activeTab === 'calculator' ? (
        <CalculatorView
          form={form}
          result={result}
          selectedFilament={selectedFilament}
          filaments={filamentsQuery.data?.items ?? []}
          isFilamentsLoading={filamentsQuery.isPending}
          filamentsLoadError={filamentsQuery.isError ? t('calculator.materialsLoadError') : null}
          isCalculating={calculateMutation.isPending}
          estimateError={estimateError}
          onCalculate={handleCalculate}
          onChange={updateField}
        />
      ) : (
        <HistoryView />
      )}
    </div>
  );
};

interface CalculatorViewProps {
  form: CalculatorFormState;
  result: CalculatorEstimateResponse | null;
  selectedFilament: Filament | null;
  filaments: Filament[];
  isFilamentsLoading: boolean;
  filamentsLoadError: string | null;
  isCalculating: boolean;
  estimateError: string | null;
  onCalculate: () => void;
  onChange: <K extends keyof CalculatorFormState>(field: K, value: CalculatorFormState[K]) => void;
}

const CalculatorView: React.FC<CalculatorViewProps> = ({
  form,
  result,
  selectedFilament,
  filaments,
  isFilamentsLoading,
  filamentsLoadError,
  isCalculating,
  estimateError,
  onCalculate,
  onChange,
}) => {
  const { t } = useTranslation();

  const materialCatalogSummary =
    selectedFilament && (selectedFilament.price_per_kg != null || selectedFilament.spool_weight != null)
      ? `${selectedFilament.price_per_kg != null ? `${selectedFilament.price_per_kg.toFixed(0)} ₽/кг` : '—'} · ${
          selectedFilament.spool_weight != null ? `${selectedFilament.spool_weight.toFixed(0)} г` : '—'
        }`
      : null;

  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1.45fr)_minmax(22rem,0.92fr)]">
      <div className="space-y-5">
        <SurfaceCard className="p-6 md:p-7">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <SectionHeading icon={<Calculator className="h-5 w-5 text-cyan-300" />} title={t('profilePage.calc.pricingMethod')} />
              <p className="mt-3 max-w-xl text-sm leading-6 text-slate-300">{t('calculator.methodHint')}</p>
            </div>
            <div className="rounded-[1.3rem] border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-300">
              <span className="text-slate-400">{t('calculator.activeMethodLabel')}: </span>
              <span className="font-semibold text-white">
                {t(
                  form.pricingMethod === 'combined'
                    ? 'profilePage.calc.combined'
                    : form.pricingMethod === 'by_time'
                      ? 'profilePage.calc.byTime'
                      : 'profilePage.calc.byWeight',
                )}
              </span>
            </div>
          </div>
          <div className="mt-5 flex flex-wrap gap-3">
            {([
              { value: 'by_weight', label: t('profilePage.calc.byWeight') },
              { value: 'by_time', label: t('profilePage.calc.byTime') },
              { value: 'combined', label: t('profilePage.calc.combined') },
            ] as const).map((method) => (
              <button
                key={method.value}
                type="button"
                onClick={() => onChange('pricingMethod', method.value)}
                className={`rounded-2xl px-4 py-3 text-sm font-medium transition-all ${
                  form.pricingMethod === method.value
                    ? 'bg-cyan-300 text-slate-950 shadow-[0_18px_35px_-18px_rgba(34,211,238,0.85)]'
                    : 'border border-white/10 bg-white/5 text-slate-300 hover:bg-white/10 hover:text-white'
                }`}
              >
                {method.label}
              </button>
            ))}
          </div>
        </SurfaceCard>

        <SurfaceCard className="p-6 md:p-7">
          <SectionHeading icon={<Upload className="h-5 w-5 text-cyan-300" />} title={t('calculator.uploadGcode')} />
          <div className="mt-5 rounded-[1.6rem] border border-dashed border-cyan-400/30 bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.14),transparent_52%),linear-gradient(180deg,rgba(15,23,42,0.8),rgba(2,6,23,0.85))] p-8 md:p-10">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex items-start gap-4">
                <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-[1.25rem] border border-white/10 bg-white/5">
                  <Upload className="h-6 w-6 text-cyan-300" />
                </div>
                <div>
                  <p className="text-base font-semibold text-white">{t('calculator.gcodeSoonTitle')}</p>
                  <p className="mt-2 max-w-xl text-sm leading-6 text-slate-300">{t('calculator.gcodeSoonDescription')}</p>
                </div>
              </div>
              <div className="inline-flex items-center gap-2 self-start rounded-full border border-amber-300/20 bg-amber-400/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-200">
                <Clock className="h-3.5 w-3.5" />
                {t('downloadPage.comingSoon')}
              </div>
            </div>
          </div>
        </SurfaceCard>

        {(form.pricingMethod === 'by_weight' || form.pricingMethod === 'combined') && (
          <SurfaceCard className="p-6 md:p-7">
            <SectionHeading icon={<Weight className="h-5 w-5 text-cyan-300" />} title={t('profilePage.calc.materialParams')} />
            <div className="mt-5 space-y-5">
              <FieldBlock label={t('calculator.selectMaterial')}>
                <select
                  className={inputClass}
                  value={form.selectedFilamentId}
                  onChange={(event) => onChange('selectedFilamentId', event.target.value ? Number(event.target.value) : '')}
                >
                  <option value="">{t('calculator.chooseFromCatalog')}</option>
                  {filaments.map((filament) => (
                    <option key={filament.id} value={filament.id}>
                      {buildFilamentLabel(filament)}
                    </option>
                  ))}
                </select>
              </FieldBlock>

              {selectedFilament && materialCatalogSummary && (
                <div className="rounded-[1.35rem] border border-cyan-400/20 bg-cyan-400/10 px-4 py-3 text-sm text-cyan-100">
                  <span className="font-semibold text-white">{selectedFilament.name}</span>
                  <span className="mx-2 text-cyan-200/70">·</span>
                  {materialCatalogSummary}
                </div>
              )}

              {filamentsLoadError && (
                <div className="rounded-[1.25rem] border border-amber-400/20 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
                  {filamentsLoadError}
                </div>
              )}

              {isFilamentsLoading && (
                <div className="rounded-[1.25rem] border border-white/10 bg-white/5 px-4 py-3 text-sm text-slate-300">
                  {t('calculator.loadingMaterials')}
                </div>
              )}

              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <FieldBlock label={t('profilePage.calc.partWeight')}>
                  <InputWithSuffix
                    value={form.weightG}
                    onChange={(value) => onChange('weightG', value)}
                    placeholder="531"
                    suffix={t('calculator.grams')}
                  />
                </FieldBlock>
                <FieldBlock label={t('profilePage.calc.supportsWeight')} hint={t('profilePage.calc.supportsWeightHint')}>
                  <InputWithSuffix
                    value={form.supportsWeightG}
                    onChange={(value) => onChange('supportsWeightG', value)}
                    placeholder="0"
                    suffix={t('calculator.grams')}
                  />
                </FieldBlock>
                <FieldBlock label={t('profilePage.calc.supportsLossCoeff')} hint={t('profilePage.calc.supportsLossHint')}>
                  <NumberInput
                    value={form.supportsLossCoefficient}
                    onChange={(value) => onChange('supportsLossCoefficient', value)}
                    min="1"
                    max="2"
                    step="0.1"
                    placeholder="1.2"
                  />
                </FieldBlock>
                <FieldBlock label={t('profilePage.calc.spoolPrice')}>
                  <InputWithSuffix
                    value={form.spoolPrice}
                    onChange={(value) => onChange('spoolPrice', value)}
                    placeholder="1200"
                    suffix="₽"
                  />
                </FieldBlock>
                <FieldBlock label={t('profilePage.calc.spoolWeight')}>
                  <InputWithSuffix
                    value={form.spoolWeightKg}
                    onChange={(value) => onChange('spoolWeightKg', value)}
                    placeholder="1"
                    suffix={t('calculator.kg')}
                    step="0.1"
                  />
                </FieldBlock>
                <FieldBlock label={t('profilePage.calc.deliveryCost')}>
                  <InputWithSuffix
                    value={form.deliveryCost}
                    onChange={(value) => onChange('deliveryCost', value)}
                    placeholder="0"
                    suffix="₽"
                  />
                </FieldBlock>
              </div>
            </div>
          </SurfaceCard>
        )}

        {(form.pricingMethod === 'by_time' || form.pricingMethod === 'combined') && (
          <SurfaceCard className="p-6 md:p-7">
            <SectionHeading icon={<Clock className="h-5 w-5 text-cyan-300" />} title={t('profilePage.calc.printTime')} />
            <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-3">
              <FieldBlock label={t('profilePage.calc.hours')}>
                <NumberInput value={form.timeHours} onChange={(value) => onChange('timeHours', value)} placeholder="13" />
              </FieldBlock>
              <FieldBlock label={t('profilePage.calc.minutes')}>
                <NumberInput value={form.timeMinutes} onChange={(value) => onChange('timeMinutes', value)} placeholder="40" />
              </FieldBlock>
              <FieldBlock label={t('profilePage.calc.seconds')}>
                <NumberInput value={form.timeSec} onChange={(value) => onChange('timeSec', value)} placeholder="0" />
              </FieldBlock>
            </div>
          </SurfaceCard>
        )}

        {form.pricingMethod === 'by_time' && (
          <SurfaceCard className="p-6 md:p-7">
            <SectionHeading icon={<DollarSign className="h-5 w-5 text-cyan-300" />} title={t('profilePage.calc.hourlyRate')} />
            <div className="mt-5">
              <FieldBlock label={t('profilePage.calc.pricePerHour')}>
                <InputWithSuffix
                  value={form.pricePerHour}
                  onChange={(value) => onChange('pricePerHour', value)}
                  placeholder="170"
                  suffix={`₽/${t('calculator.hourAbbr')}`}
                />
              </FieldBlock>
            </div>
          </SurfaceCard>
        )}

        <SurfaceCard className="p-6 md:p-7">
          <SectionHeading icon={<Zap className="h-5 w-5 text-cyan-300" />} title={t('profilePage.calc.electricity')} />
          <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
            <FieldBlock label={t('profilePage.calc.electricityCost')}>
              <InputWithSuffix
                value={form.electricityCostPerKwh}
                onChange={(value) => onChange('electricityCostPerKwh', value)}
                placeholder="6"
                suffix={`₽/${t('calculator.kwhAbbr')}`}
                step="0.1"
              />
            </FieldBlock>
            <FieldBlock label={t('profilePage.calc.printerPower')}>
              <InputWithSuffix
                value={form.printerPowerW}
                onChange={(value) => onChange('printerPowerW', value)}
                placeholder="350"
                suffix={t('calculator.wattAbbr')}
              />
            </FieldBlock>
          </div>
        </SurfaceCard>

        {form.pricingMethod === 'combined' && (
          <>
            <SurfaceCard className="p-6 md:p-7">
              <SectionHeading icon={<Settings2 className="h-5 w-5 text-cyan-300" />} title={t('profilePage.calc.additionalServices')} />
              <div className="mt-5 space-y-6">
                <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                  <FieldBlock label={t('profilePage.calc.modelingHours')}>
                    <NumberInput value={form.modelingHours} onChange={(value) => onChange('modelingHours', value)} placeholder="0" />
                  </FieldBlock>
                  <FieldBlock label={t('profilePage.calc.modelingMinutes')}>
                    <NumberInput value={form.modelingMinutes} onChange={(value) => onChange('modelingMinutes', value)} placeholder="0" />
                  </FieldBlock>
                  <FieldBlock label={t('profilePage.calc.rate')}>
                    <InputWithSuffix
                      value={form.modelingRatePerHour}
                      onChange={(value) => onChange('modelingRatePerHour', value)}
                      placeholder="934"
                      suffix={`₽/${t('calculator.hourAbbr')}`}
                    />
                  </FieldBlock>
                </div>

                <FieldBlock label={t('profilePage.calc.printingRate')}>
                  <InputWithSuffix
                    value={form.printingRatePerHour}
                    onChange={(value) => onChange('printingRatePerHour', value)}
                    placeholder="170"
                    suffix={`₽/${t('calculator.hourAbbr')}`}
                  />
                </FieldBlock>

                <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
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
                  <FieldBlock label={t('profilePage.calc.rate')}>
                    <InputWithSuffix
                      value={form.postprocessingRatePerHour}
                      onChange={(value) => onChange('postprocessingRatePerHour', value)}
                      placeholder="100"
                      suffix={`₽/${t('calculator.hourAbbr')}`}
                    />
                  </FieldBlock>
                </div>

                <FieldBlock label={t('profilePage.calc.amortizationRate')}>
                  <InputWithSuffix
                    value={form.amortizationRatePerHour}
                    onChange={(value) => onChange('amortizationRatePerHour', value)}
                    placeholder="16"
                    suffix={`₽/${t('calculator.hourAbbr')}`}
                  />
                </FieldBlock>
              </div>
            </SurfaceCard>

            <SurfaceCard className="p-6 md:p-7">
              <SectionHeading icon={<TrendingUp className="h-5 w-5 text-cyan-300" />} title={t('profilePage.calc.overheadAndMarkup')} />
              <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
                <FieldBlock label={t('profilePage.calc.overheadPercent')} hint={t('profilePage.calc.overheadHint')}>
                  <InputWithSuffix
                    value={form.overheadPercent}
                    onChange={(value) => onChange('overheadPercent', value)}
                    placeholder="20"
                    suffix="%"
                    step="0.1"
                  />
                </FieldBlock>
                <FieldBlock label={t('profilePage.calc.markupPercent')} hint={t('profilePage.calc.markupHint')}>
                  <InputWithSuffix
                    value={form.markupPercent}
                    onChange={(value) => onChange('markupPercent', value)}
                    placeholder="30"
                    suffix="%"
                    step="0.1"
                  />
                </FieldBlock>
              </div>
            </SurfaceCard>

            <SurfaceCard className="p-6 md:p-7">
              <SectionHeading icon={<Settings2 className="h-5 w-5 text-cyan-300" />} title={t('profilePage.calc.adjustmentCoeffs')} />
              <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-3">
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
                <FieldBlock label={t('profilePage.calc.complexity')} hint={t('profilePage.calc.complexityHint')}>
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
            </SurfaceCard>
          </>
        )}

        <SurfaceCard className="p-6 md:p-7">
          <SectionHeading icon={<Package className="h-5 w-5 text-cyan-300" />} title={t('calculator.batchSection')} />
          <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
            <FieldBlock label={t('profilePage.calc.quantity')}>
              <NumberInput value={form.quantity} onChange={(value) => onChange('quantity', Math.max(1, value))} min="1" placeholder="4" />
            </FieldBlock>
            {form.pricingMethod === 'combined' && (
              <>
                <FieldBlock label={t('profilePage.calc.fixedCosts')} hint={t('profilePage.calc.fixedCostsHint')}>
                  <InputWithSuffix
                    value={form.fixedCosts}
                    onChange={(value) => onChange('fixedCosts', value)}
                    placeholder="0"
                    suffix="₽"
                  />
                </FieldBlock>
                <FieldBlock label={t('profilePage.calc.minOrderPrice')} hint={t('profilePage.calc.minOrderPriceHint')}>
                  <InputWithSuffix
                    value={form.minOrderPrice}
                    onChange={(value) => onChange('minOrderPrice', value)}
                    placeholder="0"
                    suffix="₽"
                  />
                </FieldBlock>
                <FieldBlock label={t('profilePage.calc.roundTo')}>
                  <InputWithSuffix
                    value={form.roundToNearest}
                    onChange={(value) => onChange('roundToNearest', value)}
                    placeholder="10"
                    suffix="₽"
                  />
                </FieldBlock>
              </>
            )}
          </div>
        </SurfaceCard>

        {estimateError && (
          <div className="rounded-[1.45rem] border border-red-400/25 bg-red-500/10 px-5 py-4 text-sm text-red-100">
            {t('profilePage.calc.error')}: {estimateError}
          </div>
        )}

        <button
          type="button"
          onClick={onCalculate}
          disabled={isCalculating}
          className="inline-flex w-full items-center justify-center gap-2 rounded-[1.6rem] bg-[linear-gradient(135deg,#0891b2,#7c3aed)] px-6 py-4 text-base font-semibold text-white shadow-[0_18px_35px_-18px_rgba(6,182,212,0.7)] transition-all hover:translate-y-[-1px] hover:shadow-[0_22px_42px_-18px_rgba(124,58,237,0.72)] disabled:cursor-not-allowed disabled:opacity-60"
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
      </div>

      <div className="xl:pt-1">
        <SurfaceCard className="p-6 md:p-7 xl:sticky xl:top-8">
          <div className="flex items-center justify-between gap-4">
            <SectionHeading icon={<Calculator className="h-5 w-5 text-cyan-300" />} title={t('calculator.resultsTitle')} compact />
            <div className="rounded-full border border-cyan-400/20 bg-cyan-400/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-cyan-200">
              {result ? t('calculator.lastEstimate') : t('calculator.readyForEstimate')}
            </div>
          </div>

          {result ? (
            <>
              <div className="mt-6 overflow-hidden rounded-[1.7rem] border border-cyan-400/20 bg-[radial-gradient(circle_at_top_left,rgba(34,211,238,0.18),transparent_45%),linear-gradient(145deg,rgba(14,116,144,0.2),rgba(76,29,149,0.26))] p-6 shadow-[inset_0_1px_0_rgba(255,255,255,0.08)]">
                <p className="text-xs uppercase tracking-[0.18em] text-slate-300">{t('calculator.totalCost')}</p>
                <p className="mt-3 text-4xl font-bold tracking-tight text-white">{formatCurrency(result.cost_final || result.cost_total)}</p>
                <p className="mt-2 text-sm text-slate-300">
                  {t('calculator.perPart')}: <span className="text-white">{formatCurrency(result.cost_first_part)}</span>
                </p>
              </div>

              <div className="mt-6 space-y-4">
                <SectionPanel title={t('profilePage.calc.costComponents')}>
                  <MetricRow label={t('profilePage.calc.material')} value={formatCurrency(result.cost_material)} />
                  <MetricRow label={t('profilePage.calc.electricityLabel')} value={formatCurrency(result.cost_electricity)} />
                  <MetricRow label={t('profilePage.calc.modeling')} value={formatCurrency(result.cost_modeling)} />
                  <MetricRow label={t('profilePage.calc.printing')} value={formatCurrency(result.cost_printing)} />
                  <MetricRow label={t('profilePage.calc.postprocessing')} value={formatCurrency(result.cost_postprocessing)} />
                  <MetricRow label={t('profilePage.calc.amortization')} value={formatCurrency(result.cost_amortization)} />
                </SectionPanel>

                {form.pricingMethod === 'combined' && (
                  <>
                    <SectionPanel title={t('profilePage.calc.intermediateCalcs')}>
                      <MetricRow label={t('profilePage.calc.directCosts')} value={formatCurrency(result.cost_direct)} />
                      <MetricRow label={t('profilePage.calc.overhead')} value={formatCurrency(result.cost_overhead)} />
                      <MetricRow label={t('profilePage.calc.costBeforeMarkup')} value={formatCurrency(result.cost_before_markup)} />
                      <MetricRow label={t('profilePage.calc.markup')} value={formatCurrency(result.cost_markup)} />
                    </SectionPanel>

                    <SectionPanel title={t('profilePage.calc.financialMetrics')}>
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
                  </>
                )}

                <SectionPanel title={t('profilePage.calc.totalSums')}>
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
                <button className={`${ghostButtonClass} w-full opacity-60`} disabled>
                  <Save className="h-4 w-4" />
                  {t('calculator.saveToHistory')}
                </button>
                <button className={`${ghostButtonClass} w-full opacity-60`} disabled>
                  <FileText className="h-4 w-4" />
                  {t('calculator.generateQuote')}
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
                  <h3 className="text-lg font-semibold text-white">{t('calculator.resultsEmptyTitle')}</h3>
                  <p className="mt-2 text-sm leading-6 text-slate-300">{t('calculator.resultsEmptyDescription')}</p>
                </div>
              </div>
            </div>
          )}
        </SurfaceCard>
      </div>
    </div>
  );
};

const HistoryView: React.FC = () => {
  const { t } = useTranslation();

  return (
    <SurfaceCard className="p-6 md:p-7">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <SectionHeading icon={<Clock className="h-5 w-5 text-cyan-300" />} title={t('calculator.historyTitle')} compact />
        <div className="flex flex-col gap-2 sm:flex-row">
          <button className={`${ghostButtonClass} opacity-60`} disabled>
            <Download className="h-4 w-4" />
            {t('calculator.export')}
          </button>
          <button className="inline-flex items-center justify-center gap-2 rounded-2xl border border-red-400/25 bg-red-500/10 px-4 py-3 text-sm font-medium text-red-200 opacity-60" disabled>
            <Trash2 className="h-4 w-4" />
            {t('calculator.deleteSelected')}
          </button>
        </div>
      </div>

      <div className="mt-6 rounded-[1.8rem] border border-dashed border-white/12 bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.08),transparent_44%),linear-gradient(180deg,rgba(2,6,23,0.35),rgba(2,6,23,0.62))] px-6 py-16 text-center shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]">
        <div className="mx-auto flex h-[4.5rem] w-[4.5rem] items-center justify-center rounded-[1.6rem] border border-white/10 bg-white/5">
          <Clock className="h-9 w-9 text-slate-500" />
        </div>
        <h2 className="mt-6 text-2xl font-semibold text-white">{t('calculator.noHistory')}</h2>
        <p className="mx-auto mt-3 max-w-xl text-sm leading-6 text-slate-300">{t('calculator.noHistoryDescription')}</p>
        <button className="mt-8 inline-flex items-center justify-center rounded-[1.3rem] bg-[linear-gradient(135deg,#0891b2,#7c3aed)] px-6 py-3 text-sm font-semibold text-white opacity-60 shadow-[0_18px_35px_-18px_rgba(6,182,212,0.7)]" disabled>
          {t('calculator.createFirstCalculation')}
        </button>
      </div>
    </SurfaceCard>
  );
};

const SurfaceCard: React.FC<{ children: ReactNode; className?: string }> = ({ children, className = '' }) => (
  <section className={`${surfaceClass} ${className}`}>
    <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top,rgba(255,255,255,0.06),transparent_40%)]" />
    <div className="relative">{children}</div>
  </section>
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

const FieldBlock: React.FC<{ label: string; children: ReactNode; hint?: string | null }> = ({ label, children, hint }) => (
  <label className="block">
    <span className="mb-2 block text-sm font-medium text-slate-300">{label}</span>
    {children}
    {hint ? <span className="mt-2 block text-xs leading-5 text-slate-400">{hint}</span> : null}
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
    className={inputClass}
    value={value}
    min={min}
    max={max}
    step={step}
    placeholder={placeholder}
    onChange={(event) => onChange(Number(event.target.value) || 0)}
  />
);

const InputWithSuffix: React.FC<{
  value: number;
  onChange: (value: number) => void;
  placeholder: string;
  suffix: string;
  step?: string;
}> = ({ value, onChange, placeholder, suffix, step }) => (
  <div className="relative">
    <input
      type="number"
      className={`${inputClass} pr-20`}
      value={value}
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
  <div className="rounded-[1.45rem] border border-white/10 bg-white/5 px-4 py-3 shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]">
    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">{label}</p>
    <p className="mt-2 text-2xl font-semibold tracking-tight text-white">{value}</p>
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
