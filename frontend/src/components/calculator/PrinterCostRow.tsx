import { useTranslation } from 'react-i18next';
import { AlertTriangle } from 'lucide-react';

import type { PhysicalPrinter } from '../../api/client';
import { Printer3DIcon } from '../icons/Printer3DIcon';
import {
  EconomicsReadinessPanel,
  type EconomicsReadinessEntry,
} from './EconomicsReadinessPanel';

interface PrinterCostRowProps {
  printers: PhysicalPrinter[];
  selectedPrinterId: number | '';
  onSelect: (printerId: number | '') => void;
  pickedFromLabel?: string | null;
  rateMissing?: boolean;
  onFixRate?: () => void;
  readinessEntries?: EconomicsReadinessEntry[];
  readinessLoading?: boolean;
  readinessError?: boolean;
}

const selectClass =
  'w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-white focus:outline-none focus:ring-2 focus:ring-cyan-400/60 sm:max-w-[18rem]';

export const PrinterCostRow: React.FC<PrinterCostRowProps> = ({
  printers,
  selectedPrinterId,
  onSelect,
  pickedFromLabel = null,
  rateMissing = false,
  onFixRate,
  readinessEntries = [],
  readinessLoading = false,
  readinessError = false,
}) => {
  const { t } = useTranslation();
  return (
    <div
      id="calculator-printer-row"
      className="rounded-2xl border border-white/20 bg-white/10 p-4"
    >
      <div className="flex flex-wrap items-center gap-3">
        <span className="flex items-center gap-2 text-sm font-medium text-slate-300">
          <Printer3DIcon className="text-slate-400" size={16} strokeWidth={2} />
          {t('printerCost.rowLabel')}
        </span>
        <select
          className={selectClass}
          value={selectedPrinterId === '' ? '' : String(selectedPrinterId)}
          onChange={(event) => onSelect(event.target.value ? Number(event.target.value) : '')}
        >
          <option value="">{t('printerCost.noPrinter')}</option>
          {printers.map((printer) => (
            <option key={printer.id} value={printer.id}>
              {printer.name}
            </option>
          ))}
        </select>
      </div>

      <p className="mt-2 text-xs leading-5 text-slate-500">
        {selectedPrinterId === ''
          ? t('printerCost.noPrinterHint')
          : t('printerCost.machineSelectedHint')}
        {pickedFromLabel ? ` · ${pickedFromLabel}` : ''}
      </p>

      <div className="mt-3">
        <EconomicsReadinessPanel
          entries={readinessEntries}
          isLoading={readinessLoading}
          error={readinessError}
          onConfigure={onFixRate}
        />
      </div>

      {rateMissing && readinessEntries.length === 0 && !readinessLoading ? (
        <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs leading-5 text-amber-300/90">
          <span className="flex items-start gap-1.5">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            {t('printerCost.rateMissing')}
          </span>
          {onFixRate ? (
            <button
              type="button"
              onClick={onFixRate}
              className="font-semibold text-amber-200 underline underline-offset-2 transition hover:text-amber-100"
            >
              {t('printerCost.rateMissingAction')}
            </button>
          ) : null}
        </p>
      ) : null}
    </div>
  );
};
