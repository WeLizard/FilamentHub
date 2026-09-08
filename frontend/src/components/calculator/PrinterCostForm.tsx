import { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';

import {
  physicalPrintersAPI,
  type PrinterEconomics,
  type PrinterEconomicsUpdate,
} from '../../api/client';
import { toast } from '../Toast';
import { currencySymbol } from '../../utils/currency';
import { translateApiError } from '../../utils/translateApiError';
import { EconomicsFields, type EconomicsField, type EconomicsValues } from './EconomicsFields';
import { PowerPartsBreakdown } from './PowerPartsBreakdown';
import { EconomicsReadinessPanel } from './EconomicsReadinessPanel';
import { enqueueEconomicsSave } from '../../utils/economicsReadiness';

interface PrinterCostFormProps {
  printerId: number;
  printerName: string;
  currency: string;
  fallback: EconomicsValues;
  onSaved?: (economics: PrinterEconomics) => void;
  onStatusChange?: (status: 'saving' | 'saved' | null) => void;
}

const USAGE_OPTIONS = ['occasional', 'regular', 'intensive'] as const;
type Usage = (typeof USAGE_OPTIONS)[number];

const UPKEEP_OPTIONS = [
  { key: 'upkeepLow', value: 2 },
  { key: 'upkeepMid', value: 5 },
  { key: 'upkeepHigh', value: 10 },
] as const;

const roundMoney = (value: number): number => Math.round(value * 100) / 100;

const sameCurrency = (left: string | null | undefined, right: string | null | undefined): boolean =>
  Boolean(
    left
    && right
    && left.trim().toUpperCase() === right.trim().toUpperCase(),
  );

export const resolveEditableMoneyValue = (
  rawValue: number | null,
  rawCurrency: string | null | undefined,
  fallbackValue: number,
  fallbackCurrency: string | null | undefined,
  appliedCurrency: string | null | undefined,
  editorCurrency: string,
): number => {
  if (
    rawValue != null
    && sameCurrency(rawCurrency, editorCurrency)
    && sameCurrency(appliedCurrency, editorCurrency)
  ) {
    return rawValue;
  }
  return sameCurrency(fallbackCurrency, editorCurrency) ? fallbackValue : 0;
};

export const calculateDepreciationPerHour = (
  purchaseCost: number,
  lifeHours: number,
  residualValue: number | null = null,
): number => lifeHours > 0
  ? Math.max(0, purchaseCost - Math.max(0, residualValue ?? 0)) / lifeHours
  : 0;

export const resolveEditableMachineRate = (
  saved: PrinterEconomics,
  editorCurrency: string,
): number => {
  if (!sameCurrency(saved.readiness?.money_currency, editorCurrency)) return 0;
  const resolvedRate = saved.readiness?.required_fields.find(
    (field) => field.key === 'machine_hour_rate',
  );
  if (
    typeof resolvedRate?.value === 'number'
    && sameCurrency(resolvedRate.source_currency, editorCurrency)
  ) {
    return resolvedRate.value;
  }
  if (
    saved.machine_hour_rate != null
    && sameCurrency(saved.economics_currency, editorCurrency)
  ) {
    return saved.machine_hour_rate;
  }
  return sameCurrency(saved.calculator_currency, editorCurrency)
    ? saved.effective_machine_hour_rate
    : 0;
};

export const printerEconomicsPatchForField = (
  field: EconomicsField,
  value: number | null,
  currency?: { stored: string | null | undefined; editor: string },
): PrinterEconomicsUpdate => {
  let patch: PrinterEconomicsUpdate;
  switch (field) {
    case 'purchaseCost':
      patch = { purchase_cost: value };
      break;
    case 'lifeHours':
      return { useful_life_hours: value == null || value <= 0 ? null : Math.round(value) };
    case 'powerWatts':
      return { average_power_watts: value == null || value <= 0 ? null : value };
    case 'maintenance':
      patch = { maintenance_cost_per_hour: value };
      break;
    case 'rate':
      patch = { machine_hour_rate: value };
      break;
  }
  if (
    currency
    && (!currency.stored || currency.stored.trim().toUpperCase() !== currency.editor.trim().toUpperCase())
  ) {
    patch.economics_currency = currency.editor;
  }
  return patch;
};

const POWER_PART_API_FIELDS = {
  hotend: 'power_hotend_w',
  bed: 'power_bed_w',
  steppers: 'power_steppers_w',
  electronics: 'power_electronics_w',
} as const;

type PowerPart = keyof typeof POWER_PART_API_FIELDS;

export const printerPowerPartPatch = (
  part: PowerPart,
  value: number | null,
): PrinterEconomicsUpdate => ({ [POWER_PART_API_FIELDS[part]]: value });

export const PrinterCostForm: React.FC<PrinterCostFormProps> = ({
  printerId,
  printerName,
  currency,
  fallback,
  onSaved,
  onStatusChange,
}) => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const [usage, setUsage] = useState<Usage>('regular');
  const [values, setValues] = useState<EconomicsValues>({
    purchaseCost: 0,
    lifeHours: 0,
    powerWatts: 0,
    maintenance: 0,
    rate: 0,
  });
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [parts, setParts] = useState({ hotend: 0, bed: 0, steppers: 0, electronics: 0 });
  const [saveError, setSaveError] = useState(false);
  const savedTimerRef = useRef<number | undefined>(undefined);
  const saveQueueRef = useRef<Promise<void>>(Promise.resolve());
  const saveSequenceRef = useRef(0);
  const mountedRef = useRef(true);

  const economicsQuery = useQuery({
    queryKey: ['printer-economics', printerId],
    queryFn: () => physicalPrintersAPI.economics(printerId),
    retry: false,
  });
  const suggestionQuery = useQuery({
    queryKey: ['printer-economics-suggestion', printerId, usage],
    queryFn: () => physicalPrintersAPI.economicsSuggestion(printerId, usage),
    retry: false,
  });

  const saved = economicsQuery.data;
  const suggestion = suggestionQuery.data;
  const economicsCurrency = currency;
  const symbol = currencySymbol(economicsCurrency);
  const calculatorMoneyMatchesEditor = sameCurrency(
    economicsCurrency,
    saved?.calculator_currency,
  );

  useEffect(() => {
    if (!saved) {
      return;
    }
    setValues({
      purchaseCost: resolveEditableMoneyValue(
        saved.purchase_cost,
        saved.economics_currency,
        fallback.purchaseCost,
        saved.calculator_currency,
        saved.readiness.money_currency,
        economicsCurrency,
      ),
      lifeHours: saved.useful_life_hours ?? fallback.lifeHours ?? suggestion?.useful_life_hours ?? 0,
      powerWatts:
        saved.average_power_watts ?? fallback.powerWatts ?? suggestion?.average_power_watts ?? 0,
      maintenance: resolveEditableMoneyValue(
        saved.maintenance_cost_per_hour,
        saved.economics_currency,
        fallback.maintenance,
        saved.calculator_currency,
        saved.readiness.money_currency,
        economicsCurrency,
      ),
      rate: resolveEditableMachineRate(saved, economicsCurrency),
    });
    // Offer what we worked out for this machine instead of four zeroes: the bed comes
    // from its own size, and a person is free to write over any of it.
    setParts({
      hotend: saved.power_hotend_w ?? suggestion?.power_hotend_w ?? 0,
      bed: saved.power_bed_w ?? suggestion?.power_bed_w ?? 0,
      steppers: saved.power_steppers_w ?? suggestion?.power_steppers_w ?? 0,
      electronics: saved.power_electronics_w ?? suggestion?.power_electronics_w ?? 0,
    });
  }, [saved, suggestion, fallback, economicsCurrency]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      window.clearTimeout(savedTimerRef.current);
    };
  }, []);

  const breakdown = useMemo(() => {
    const tariff = calculatorMoneyMatchesEditor
      ? saved?.calculator_electricity_cost_per_kwh ?? 0
      : 0;
    const depreciation = calculateDepreciationPerHour(
      values.purchaseCost,
      values.lifeHours,
      saved?.residual_value,
    );
    const electricity = (values.powerWatts / 1000) * tariff;
    return {
      depreciation: roundMoney(depreciation),
      electricity: roundMoney(electricity),
      maintenance: roundMoney(values.maintenance),
      cost: roundMoney(depreciation + electricity + values.maintenance),
    };
  }, [values, saved, calculatorMoneyMatchesEditor]);

  const rateChoices = useMemo(() => {
    if (breakdown.depreciation <= 0) {
      return [];
    }
    const base = breakdown.cost;
    const step = base < 20 ? 1 : 5;
    const round = (value: number) => Math.ceil(value / step) * step;
    const min = round(base * 1.25);
    const balanced = Math.max(round(base * 1.9), min + step);
    return [
      { key: 'min', value: min },
      { key: 'balanced', value: balanced },
      { key: 'safe', value: Math.max(round(base * 2.5), balanced + step) },
    ];
  }, [breakdown.cost]);

  const enqueueSave = (request: () => Promise<PrinterEconomics>) => {
    const sequence = ++saveSequenceRef.current;
    setSaveError(false);
    onStatusChange?.('saving');
    const queued = enqueueEconomicsSave(saveQueueRef.current, request);
    const task = queued.task;
    saveQueueRef.current = queued.tail;
    void task
      .then((economics) => {
        if (!mountedRef.current || sequence !== saveSequenceRef.current) return;
        setSaveError(false);
        queryClient.setQueryData(['printer-economics', printerId], economics);
        onSaved?.(economics);
        onStatusChange?.('saved');
        window.clearTimeout(savedTimerRef.current);
        savedTimerRef.current = window.setTimeout(() => onStatusChange?.(null), 2000);
      })
      .catch((error) => {
        if (!mountedRef.current || sequence !== saveSequenceRef.current) return;
        setSaveError(true);
        onStatusChange?.(null);
        const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
        toast.error(translateApiError(t, detail, t('printerCost.saveError')));
      });
  };

  const change = (field: EconomicsField, value: number) =>
    setValues((current) => ({ ...current, [field]: value }));

  const commit = (field: EconomicsField, value: number | null) => {
    setValues((current) => ({ ...current, [field]: value ?? 0 }));
    const patch = printerEconomicsPatchForField(field, value, {
      stored: saved?.economics_currency,
      editor: economicsCurrency,
    });
    enqueueSave(() => physicalPrintersAPI.updateEconomics(printerId, patch));
  };

  /** Persist the server's physical estimates without relabelling monetary fields. */
  const applySuggested = () => {
    if (!suggestion) return;
    enqueueSave(() => physicalPrintersAPI.applyEconomicsSuggestion(printerId, {
      usage,
      fields: [
        'average_power_watts',
        'power_hotend_w',
        'power_bed_w',
        'power_steppers_w',
        'power_electronics_w',
        'useful_life_hours',
      ],
    }));
  };

  if (economicsQuery.isLoading) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-cyan-300" />
      </div>
    );
  }

  if (economicsQuery.isError || !saved) {
    return (
      <div className="rounded-2xl border border-amber-400/20 bg-amber-500/[0.06] p-4" role="alert">
        <p className="text-sm text-amber-100">{t('printerCost.readiness.loadError')}</p>
        <button
          type="button"
          onClick={() => void economicsQuery.refetch()}
          className="mt-3 inline-flex rounded-xl border border-white/10 bg-white/[0.07] px-3 py-2 text-xs font-semibold text-white transition hover:bg-white/10"
        >
          {t('printerCost.readiness.retry')}
        </button>
      </div>
    );
  }

  return (
    <EconomicsFields
      values={values}
      symbol={symbol}
      onChange={change}
      onCommit={commit}
      breakdown={breakdown}
      detailsOpen={detailsOpen}
      onToggleDetails={() => setDetailsOpen((open) => !open)}
      upkeepExtra={
        <div>
          <span className="mb-1 block text-xs font-medium leading-4 text-slate-300">
            {t('printerCost.upkeepQuestion')}
          </span>
          <div className="flex flex-wrap gap-2">
            {UPKEEP_OPTIONS.map((option) => (
              <button
                key={option.key}
                type="button"
                onClick={() => commit('maintenance', option.value)}
                className={`rounded-full border px-3 py-1.5 text-xs transition ${
                  values.maintenance === option.value
                    ? 'border-cyan-400/50 bg-cyan-500/15 text-cyan-200'
                    : 'border-white/10 bg-slate-950/40 text-slate-400 hover:border-white/20 hover:text-slate-200'
                }`}
              >
                {t(`printerCost.${option.key}`)}
              </button>
            ))}
          </div>
          <p className="mt-1.5 text-[11px] leading-4 text-slate-500">
            {t('printerCost.upkeepHint')}
          </p>
        </div>
      }
      powerExtra={
        <PowerPartsBreakdown
          hotend={parts.hotend}
          bed={parts.bed}
          steppers={parts.steppers}
          electronics={parts.electronics}
          onChange={(part, value) => {
            const nextParts = { ...parts, [part]: value };
            setParts(nextParts);
            const total =
              nextParts.hotend + nextParts.bed + nextParts.steppers + nextParts.electronics;
            setValues((current) => ({ ...current, powerWatts: total }));
          }}
          onCommit={(part, value) => {
            const nextParts = { ...parts, [part]: value ?? 0 };
            setParts(nextParts);
            const total =
              nextParts.hotend + nextParts.bed + nextParts.steppers + nextParts.electronics;
            setValues((current) => ({ ...current, powerWatts: total }));
            enqueueSave(() => physicalPrintersAPI.updateEconomics(
              printerId,
              printerPowerPartPatch(part, value),
            ));
          }}
        />
      }
      header={
        <div className="space-y-3">
          {saveError ? (
            <p className="rounded-xl border border-amber-400/20 bg-amber-500/[0.06] px-3 py-2 text-xs text-amber-100" role="alert">
              {t('printerCost.saveError')}
            </p>
          ) : null}
          <EconomicsReadinessPanel
            entries={[{
              id: `printer-${printerId}`,
              label: printerName,
              readiness: saved.readiness,
            }]}
          />
          {suggestion ? (
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="min-w-0 flex-1 text-[11px] leading-4 text-slate-400">
                {t(`printerCost.confidence.${suggestion.confidence}`, {
                  model: suggestion.model_name ?? printerName,
                })}
              </p>
              <button
                type="button"
                onClick={applySuggested}
                className="shrink-0 rounded-full border border-white/10 bg-slate-950/40 px-3 py-1.5 text-xs text-slate-300 transition hover:border-white/20 hover:text-white"
              >
                {t('printerCost.applySuggested')}
              </button>
            </div>
          ) : null}
        </div>
      }
      usage={
        <div>
          <span className="mb-1 block text-xs font-medium leading-4 text-slate-300">
            {t('printerCost.usageQuestion')}
          </span>
          <div className="flex flex-wrap gap-2">
            {USAGE_OPTIONS.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => {
                  setUsage(option);
                }}
                className={`rounded-full border px-3 py-1.5 text-xs transition ${
                  usage === option
                    ? 'border-cyan-400/50 bg-cyan-500/15 text-cyan-200'
                    : 'border-white/10 bg-slate-950/40 text-slate-300 hover:border-white/20'
                }`}
              >
                {t(`printerCost.usage.${option}`)}
              </button>
            ))}
          </div>
          <p className="mt-1.5 text-[11px] leading-4 text-slate-500">{t('printerCost.usageHint')}</p>
        </div>
      }
      rateChoices={
        <div className="mt-2 flex flex-wrap gap-2">
          {rateChoices.map((choice) => (
            <button
              key={choice.key}
              type="button"
              onClick={() => commit('rate', choice.value)}
              className={`rounded-full border px-3 py-1.5 text-xs transition ${
                values.rate === choice.value
                  ? 'border-cyan-400/50 bg-cyan-500/15 text-cyan-200'
                  : 'border-white/10 bg-slate-950/40 text-slate-300 hover:border-white/20'
              }`}
            >
              {t(`printerCost.rateChoice.${choice.key}`)} {choice.value}
            </button>
          ))}
        </div>
      }
    />
  );
};
