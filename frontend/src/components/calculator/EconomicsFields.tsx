import { type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronDown, HelpCircle } from 'lucide-react';

export interface EconomicsValues {
  purchaseCost: number;
  lifeHours: number;
  powerWatts: number;
  maintenance: number;
  rate: number;
}

export type EconomicsField = keyof EconomicsValues;

interface EconomicsFieldsProps {
  values: EconomicsValues;
  origins?: Partial<Record<EconomicsField, string>>;
  symbol: string;
  onChange: (field: EconomicsField, value: number) => void;
  onCommit?: (field: EconomicsField, value: number) => void;
  breakdown: { depreciation: number; electricity: number; maintenance: number; cost: number };
  detailsOpen: boolean;
  onToggleDetails: () => void;
  usage?: ReactNode;
  upkeepExtra?: ReactNode;
  powerExtra?: ReactNode;
  rateChoices?: ReactNode;
  header?: ReactNode;
}

const inputClass =
  'w-full max-w-[8rem] rounded-2xl border border-white/10 bg-slate-950/60 px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-cyan-400/60';

export const EconomicsFields: React.FC<EconomicsFieldsProps> = ({
  values,
  origins = {},
  symbol,
  onChange,
  onCommit,
  breakdown,
  detailsOpen,
  onToggleDetails,
  usage,
  upkeepExtra,
  powerExtra,
  rateChoices,
  header,
}) => {
  const { t } = useTranslation();
  const margin = Math.round((values.rate - breakdown.cost) * 100) / 100;

  const tip = (text: string) => (
    <span className="group/tip relative inline-flex shrink-0 align-middle">
      <span className="text-slate-500 transition-colors group-hover/tip:text-cyan-200" aria-label={text}>
        <HelpCircle className="h-3 w-3" />
      </span>
      <span
        role="tooltip"
        className="pointer-events-none absolute left-0 top-full z-[70] mt-1.5 hidden w-56 rounded-lg border border-white/10 bg-slate-950/95 px-3 py-2 text-left text-xs leading-relaxed text-slate-200 shadow-2xl shadow-black/30 group-hover/tip:block"
      >
        {text}
      </span>
    </span>
  );

  const field = (
    name: EconomicsField,
    label: string,
    suffix: string,
    tipText?: string,
    extra?: ReactNode,
  ) => (
    <label className="block">
      <span className="mb-1 flex items-center gap-1.5 text-xs font-medium leading-4 text-slate-300">
        {label}
        {tipText ? tip(tipText) : null}
      </span>
      <div className="flex items-center gap-2">
        <input
          type="number"
          min="0"
          className={inputClass}
          value={values[name] || ''}
          placeholder="0"
          onChange={(event) => onChange(name, Math.max(0, Number(event.target.value) || 0))}
          onBlur={(event) => onCommit?.(name, Math.max(0, Number(event.target.value) || 0))}
        />
        <span className="shrink-0 text-xs text-slate-400">{suffix}</span>
      </div>
      {origins[name] ? (
        <span className="mt-1 block text-[11px] leading-4 text-slate-500">{origins[name]}</span>
      ) : null}
      {extra}
    </label>
  );

  return (
    <div className="space-y-3">
      {header}

      <div className="grid grid-cols-1 gap-x-4 gap-y-3 sm:grid-cols-2">
        {field('purchaseCost', t('printerCost.purchaseCostShort'), symbol, t('printerCost.purchaseCostTip'))}
        {field('lifeHours', t('printerCost.lifeHoursShort'), t('printerCost.hoursAbbr'), t('printerCost.lifeHoursTip'))}
        {field(
          'powerWatts',
          t('printerCost.powerShort'),
          t('printerCost.wattAbbr'),
          t('printerCost.powerTip'),
          powerExtra,
        )}
        {field(
          'maintenance',
          t('printerCost.maintenanceShort'),
          `${symbol}/${t('printerCost.hourAbbr')}`,
          t('printerCost.maintenanceTip'),
        )}
      </div>

      {upkeepExtra}
      {usage}

      <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3">
        <p className="text-sm font-semibold text-white">
          {t('printerCost.costLine', { value: breakdown.cost.toFixed(2), symbol })}
        </p>
        <button
          type="button"
          onClick={onToggleDetails}
          className="mt-1.5 flex items-center gap-1 text-xs font-semibold text-cyan-300"
        >
          {t('printerCost.howCalculated')}
          <ChevronDown className={`h-3.5 w-3.5 transition-transform ${detailsOpen ? 'rotate-180' : ''}`} />
        </button>
        {detailsOpen ? (
          <div className="mt-2.5 space-y-1.5 border-t border-white/10 pt-2.5 text-xs text-slate-300">
            {/* Each line names the fields above that produce it, so it is clear which
                input to change when a number looks wrong. */}
            <div className="flex justify-between gap-4">
              <span>
                {t('printerCost.wearLine')}
                <span className="ml-1.5 text-slate-500">{t('printerCost.wearFrom')}</span>
              </span>
              <span className="tabular-nums">{breakdown.depreciation.toFixed(2)} {symbol}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span>
                {t('printerCost.electricityLine')}
                <span className="ml-1.5 text-slate-500">{t('printerCost.electricityFrom')}</span>
              </span>
              <span className="tabular-nums">{breakdown.electricity.toFixed(2)} {symbol}</span>
            </div>
            <div className="flex justify-between gap-4">
              <span>
                {t('printerCost.maintenanceLine')}
                <span className="ml-1.5 text-slate-500">{t('printerCost.maintenanceFrom')}</span>
              </span>
              <span className="tabular-nums">{breakdown.maintenance.toFixed(2)} {symbol}</span>
            </div>
          </div>
        ) : null}
      </div>

      <div>
        <span className="mb-1 flex items-center gap-1.5 text-xs font-medium leading-4 text-slate-300">
          {t('printerCost.rateLabel')}
          {tip(t('printerCost.rateTip'))}
        </span>
        <div className="flex items-center gap-2">
          <input
            type="number"
            min="0"
            className={inputClass}
            value={values.rate || ''}
            placeholder="0"
            onChange={(event) => onChange('rate', Math.max(0, Number(event.target.value) || 0))}
            onBlur={(event) => onCommit?.('rate', Math.max(0, Number(event.target.value) || 0))}
          />
          <span className="shrink-0 text-xs text-slate-400">
            {t('printerCost.perHour', { symbol })}
          </span>
        </div>
        {rateChoices}
        {breakdown.depreciation <= 0 ? (
          <p className="mt-1.5 text-[11px] leading-4 text-slate-500">
            {t('printerCost.rateNeedsCost')}
          </p>
        ) : null}
        <p className={`mt-1.5 text-[11px] leading-4 ${margin < 0 ? 'text-amber-300' : 'text-slate-500'}`}>
          {margin < 0
            ? t('printerCost.marginNegative', { value: Math.abs(margin).toFixed(2), symbol })
            : t('printerCost.margin', { value: margin.toFixed(2), symbol })}
        </p>
      </div>
    </div>
  );
};
