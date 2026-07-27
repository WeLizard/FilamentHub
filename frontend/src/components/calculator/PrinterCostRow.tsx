import { useTranslation } from 'react-i18next';

import type { PhysicalPrinter, PrinterEconomics } from '../../api/client';
import { Printer3DIcon } from '../icons/Printer3DIcon';
import { currencySymbol } from '../../utils/currency';

interface PrinterCostRowProps {
  printers: PhysicalPrinter[];
  selectedPrinterId: number | '';
  onSelect: (printerId: number | '') => void;
  economics: PrinterEconomics | null;
  currency: string;
  pickedFromLabel?: string | null;
}

const selectClass =
  'w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-white focus:outline-none focus:ring-2 focus:ring-cyan-400/60 sm:max-w-[18rem]';

export const PrinterCostRow: React.FC<PrinterCostRowProps> = ({
  printers,
  selectedPrinterId,
  onSelect,
  economics,
  currency,
  pickedFromLabel = null,
}) => {
  const { t } = useTranslation();
  const symbol = currencySymbol(currency);

  return (
    <div
      id="calculator-printer-row"
      className="rounded-[1.35rem] border border-white/10 bg-white/[0.04] p-4"
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
          : economics?.configured
            ? t('printerCost.rowConfigured', {
                rate: `${economics.effective_machine_hour_rate.toFixed(2)} ${symbol}`,
              })
            : t('printerCost.notConfiguredHint')}
        {pickedFromLabel ? ` · ${pickedFromLabel}` : ''}
      </p>
    </div>
  );
};
