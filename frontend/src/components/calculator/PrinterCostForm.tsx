import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Loader2 } from 'lucide-react';

import { physicalPrintersAPI, type PrinterEconomics } from '../../api/client';
import { toast } from '../Toast';
import { currencySymbol } from '../../utils/currency';
import { translateApiError } from '../../utils/translateApiError';
import { EconomicsFields, type EconomicsField, type EconomicsValues } from './EconomicsFields';
import { PowerPartsBreakdown } from './PowerPartsBreakdown';

interface PrinterCostFormProps {
  printerId: number;
  printerName: string;
  currency: string;
  /** The standard numbers this machine falls back to, field by field. */
  fallback: EconomicsValues;
  onSaved?: (economics: PrinterEconomics) => void;
  /** Where to show "saved" — the column header, away from the text below it. */
  onStatusChange?: (status: 'saving' | 'saved' | null) => void;
}

const USAGE_OPTIONS = ['occasional', 'regular', 'intensive'] as const;
type Usage = (typeof USAGE_OPTIONS)[number];

// What upkeep costs per hour, phrased the way a person can actually answer.
const UPKEEP_OPTIONS = [
  { key: 'upkeepLow', value: 2 },
  { key: 'upkeepMid', value: 5 },
  { key: 'upkeepHigh', value: 10 },
] as const;

const roundMoney = (value: number): number => Math.round(value * 100) / 100;

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
  const symbol = currencySymbol(currency);

  const [usage, setUsage] = useState<Usage>('regular');
  const [values, setValues] = useState<EconomicsValues>({
    purchaseCost: 0,
    lifeHours: 0,
    powerWatts: 0,
    maintenance: 0,
    rate: 0,
  });
  const [detailsOpen, setDetailsOpen] = useState(false);
  // The parts that add up to this machine's wattage. Stored with the machine:
  // two printers of one model rarely carry the same heaters and board.
  const [parts, setParts] = useState({ hotend: 0, bed: 0, steppers: 0, electronics: 0 });
  const savedTimerRef = useRef<number | undefined>(undefined);

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

  // The machine's own number wins; then the averaged one; then what we can tell
  // from the machine itself. A field is never empty and never a mystery.
  useEffect(() => {
    if (!saved) {
      return;
    }
    setValues({
      purchaseCost: saved.purchase_cost ?? fallback.purchaseCost,
      lifeHours: saved.useful_life_hours ?? fallback.lifeHours ?? suggestion?.useful_life_hours ?? 0,
      powerWatts:
        saved.average_power_watts ?? fallback.powerWatts ?? suggestion?.average_power_watts ?? 0,
      maintenance:
        saved.maintenance_cost_per_hour
        ?? fallback.maintenance
        ?? suggestion?.maintenance_cost_per_hour
        ?? 0,
      rate: saved.machine_hour_rate ?? fallback.rate,
    });
    setParts({
      hotend: saved.power_hotend_w ?? 0,
      bed: saved.power_bed_w ?? 0,
      steppers: saved.power_steppers_w ?? 0,
      electronics: saved.power_electronics_w ?? 0,
    });
  }, [saved, suggestion, fallback]);

  useEffect(() => () => window.clearTimeout(savedTimerRef.current), []);

  const origins = useMemo(() => {
    if (!saved) {
      return {};
    }
    const label = (own: unknown, isEstimate = false): string =>
      own != null
        ? t('printerCost.originOwn')
        : isEstimate
          ? t('printerCost.originEstimate')
          : t('printerCost.originAverage');
    return {
      purchaseCost: label(saved.purchase_cost),
      lifeHours: label(saved.useful_life_hours, fallback.lifeHours <= 0),
      powerWatts: label(saved.average_power_watts, fallback.powerWatts <= 0),
      maintenance: label(saved.maintenance_cost_per_hour, fallback.maintenance <= 0),
      rate: label(saved.machine_hour_rate),
    } as Partial<Record<EconomicsField, string>>;
  }, [saved, fallback, t]);

  const breakdown = useMemo(() => {
    const tariff = saved?.calculator_electricity_cost_per_kwh ?? 0;
    const depreciation = values.lifeHours > 0 ? values.purchaseCost / values.lifeHours : 0;
    const electricity = (values.powerWatts / 1000) * tariff;
    return {
      depreciation: roundMoney(depreciation),
      electricity: roundMoney(electricity),
      maintenance: roundMoney(values.maintenance),
      cost: roundMoney(depreciation + electricity + values.maintenance),
    };
  }, [values, saved]);

  const rateChoices = useMemo(() => {
    if (breakdown.depreciation <= 0) {
      return [];
    }
    const base = breakdown.cost;
    const step = base < 20 ? 1 : 5;
    const round = (value: number) => Math.ceil(value / step) * step;
    // Three distinct numbers even when the cost is tiny: identical chips would
    // read as a bug rather than a choice.
    const min = round(base * 1.25);
    const balanced = Math.max(round(base * 1.9), min + step);
    return [
      { key: 'min', value: min },
      { key: 'balanced', value: balanced },
      { key: 'safe', value: Math.max(round(base * 2.5), balanced + step) },
    ];
  }, [breakdown.cost]);

  const saveMutation = useMutation({
    onMutate: () => onStatusChange?.('saving'),
    mutationFn: ({
      next,
      nextParts,
    }: {
      next: EconomicsValues;
      nextParts?: typeof parts;
    }) =>
      physicalPrintersAPI.updateEconomics(printerId, {
        purchase_cost: next.purchaseCost > 0 ? next.purchaseCost : null,
        useful_life_hours: next.lifeHours > 0 ? Math.round(next.lifeHours) : null,
        average_power_watts: next.powerWatts > 0 ? next.powerWatts : null,
        power_hotend_w: (nextParts ?? parts).hotend || null,
        power_bed_w: (nextParts ?? parts).bed || null,
        power_steppers_w: (nextParts ?? parts).steppers || null,
        power_electronics_w: (nextParts ?? parts).electronics || null,
        maintenance_cost_per_hour: next.maintenance > 0 ? next.maintenance : null,
        machine_hour_rate: next.rate > 0 ? next.rate : null,
        economics_currency: currency,
      }),
    onSuccess: async (economics) => {
      onStatusChange?.('saved');
      window.clearTimeout(savedTimerRef.current);
      savedTimerRef.current = window.setTimeout(() => onStatusChange?.(null), 2000);
      await queryClient.invalidateQueries({ queryKey: ['printer-economics', printerId] });
      onSaved?.(economics);
    },
    onError: (error) => {
      const detail = (error as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
      toast.error(translateApiError(t, detail, t('printerCost.saveError')));
    },
  });

  const change = (field: EconomicsField, value: number) =>
    setValues((current) => ({ ...current, [field]: value }));

  // Saved when a field is left, the way the rest of the calculator remembers
  // what a person types.
  const commit = (field: EconomicsField, value: number) => {
    const next = { ...values, [field]: value };
    setValues(next);
    saveMutation.mutate({ next });
  };

  if (economicsQuery.isLoading) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-cyan-300" />
      </div>
    );
  }

  return (
    <EconomicsFields
      values={values}
      origins={origins}
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
            const next = total > 0 ? { ...values, powerWatts: total } : values;
            setValues(next);
            saveMutation.mutate({ next, nextParts });
          }}
        />
      }
      header={
        suggestion ? (
          <p className="text-[11px] leading-4 text-slate-500">
            {t(`printerCost.confidence.${suggestion.confidence}`, {
              model: suggestion.model_name ?? printerName,
            })}
          </p>
        ) : null
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
                  const hours = suggestionQuery.data?.useful_life_hours;
                  if (hours) {
                    commit('lifeHours', hours);
                  }
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
