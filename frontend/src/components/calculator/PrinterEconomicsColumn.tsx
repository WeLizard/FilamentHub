import { useMemo, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Loader2 } from 'lucide-react';

import type { PhysicalPrinter } from '../../api/client';
import { Printer3DIcon } from '../icons/Printer3DIcon';
import { currencySymbol } from '../../utils/currency';
import { EconomicsFields, type EconomicsField, type EconomicsValues } from './EconomicsFields';
import { PrinterCostForm } from './PrinterCostForm';

interface PrinterEconomicsColumnProps {
  printers: PhysicalPrinter[];
  /** Whose numbers are on screen: the averaged ones, or one machine's. */
  editedPrinterId: number | '';
  onEditedPrinterChange: (printerId: number | '') => void;
  currency: string;
  electricityCostPerKwh: number;
  /** The averaged values, used by every machine that has none of its own. */
  averaged: EconomicsValues;
  onAveragedChange: (field: EconomicsField, value: number) => void;
  /** How the standard wattage is put together, from the machine's parts. */
  powerBreakdown?: ReactNode;
}

const selectClass =
  'w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-cyan-400/60';

// What upkeep costs per hour, phrased the way a person can actually answer.
const UPKEEP_OPTIONS = [
  { key: 'upkeepLow', value: 2 },
  { key: 'upkeepMid', value: 5 },
  { key: 'upkeepHigh', value: 10 },
] as const;

const roundMoney = (value: number): number => Math.round(value * 100) / 100;

const USAGE_OPTIONS = ['occasional', 'regular', 'intensive'] as const;
type Usage = (typeof USAGE_OPTIONS)[number];
// The same starting points the server suggests per machine, so the standard
// values and a machine's own are built the same way.
const USAGE_HOURS: Record<Usage, number> = {
  occasional: 3000,
  regular: 7000,
  intensive: 12000,
};

export const PrinterEconomicsColumn: React.FC<PrinterEconomicsColumnProps> = ({
  printers,
  editedPrinterId,
  onEditedPrinterChange,
  currency,
  electricityCostPerKwh,
  averaged,
  onAveragedChange,
  powerBreakdown,
}) => {
  const { t } = useTranslation();
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [usage, setUsage] = useState<Usage>('regular');
  const [status, setStatus] = useState<'saving' | 'saved' | null>(null);
  const editedPrinter = printers.find((printer) => printer.id === editedPrinterId) ?? null;

  const breakdown = useMemo(() => {
    const depreciation = averaged.lifeHours > 0 ? averaged.purchaseCost / averaged.lifeHours : 0;
    const electricity = (averaged.powerWatts / 1000) * electricityCostPerKwh;
    return {
      depreciation: roundMoney(depreciation),
      electricity: roundMoney(electricity),
      maintenance: roundMoney(averaged.maintenance),
      cost: roundMoney(depreciation + electricity + averaged.maintenance),
    };
  }, [averaged, electricityCostPerKwh]);

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

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
      <div className="flex items-center justify-between gap-3">
        <span className="flex items-center gap-2 text-sm font-semibold text-white">
          <Printer3DIcon className="text-slate-400" size={16} strokeWidth={2} />
          {t('printerCost.columnTitle')}
        </span>
        <span className="flex items-center gap-1 text-[11px] text-emerald-300">
          {status === 'saving' ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-cyan-300" />
          ) : status === 'saved' ? (
            <>
              <Check className="h-3 w-3" />
              {t('printerCost.savedShort')}
            </>
          ) : null}
        </span>
      </div>

      <select
        className={`${selectClass} mt-3`}
        value={editedPrinterId === '' ? '' : String(editedPrinterId)}
        onChange={(event) => onEditedPrinterChange(event.target.value ? Number(event.target.value) : '')}
      >
        <option value="">{t('printerCost.generalValues')}</option>
        {printers.map((printer) => (
          <option key={printer.id} value={printer.id}>
            {printer.name}
          </option>
        ))}
      </select>

      <p className="mt-2 text-xs leading-5 text-slate-500">
        {editedPrinter ? t('printerCost.machineHint') : t('printerCost.generalHint')}
      </p>

      <div className="mt-3">
        {editedPrinter ? (
          <PrinterCostForm
            key={editedPrinter.id}
            printerId={editedPrinter.id}
            printerName={editedPrinter.name}
            currency={currency}
            fallback={averaged}
            onStatusChange={setStatus}
          />
        ) : (
          <EconomicsFields
            values={averaged}
            symbol={currencySymbol(currency)}
            onChange={onAveragedChange}
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
                onClick={() => onAveragedChange('maintenance', option.value)}
                className={`rounded-full border px-3 py-1.5 text-xs transition ${
                  averaged.maintenance === option.value
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
            powerExtra={powerBreakdown}
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
                        onAveragedChange('lifeHours', USAGE_HOURS[option]);
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
                <p className="mt-1.5 text-[11px] leading-4 text-slate-500">
                  {t('printerCost.usageHint')}
                </p>
              </div>
            }
            rateChoices={
              <div className="mt-2 flex flex-wrap gap-2">
                {rateChoices.map((choice) => (
                  <button
                    key={choice.key}
                    type="button"
                    onClick={() => onAveragedChange('rate', choice.value)}
                    className={`rounded-full border px-3 py-1.5 text-xs transition ${
                      averaged.rate === choice.value
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
        )}
      </div>
    </div>
  );
};
