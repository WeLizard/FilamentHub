import { useTranslation } from 'react-i18next';

import type { PrinterEconomics } from '../../api/client';
import { ModalOverlay } from '../ModalOverlay';
import { PrinterCostForm } from './PrinterCostForm';
import { loadAccountMachineDefaults } from '../../utils/calculatorDefaults';

interface PrinterCostModalProps {
  printerId: number;
  printerName: string;
  currency: string;
  onClose: () => void;
  onSaved?: (economics: PrinterEconomics) => void;
}

export const PrinterCostModal: React.FC<PrinterCostModalProps> = ({
  printerId,
  printerName,
  currency,
  onClose,
  onSaved,
}) => {
  const { t } = useTranslation();
  const accountDefaults = loadAccountMachineDefaults();

  return (
    <ModalOverlay onClose={onClose}>
      <div className="max-h-[85vh] w-full max-w-lg overflow-y-auto rounded-2xl border border-white/20 bg-gray-900 p-6">
        <div>
          <h2 className="text-lg font-semibold text-white">{t('printerCost.title')}</h2>
          <p className="mt-0.5 text-sm text-slate-400">{printerName}</p>
        </div>

        <div className="mt-4">
          <PrinterCostForm
            printerId={printerId}
            printerName={printerName}
            currency={currency}
            fallback={{
              purchaseCost: accountDefaults.printerPurchasePrice,
              lifeHours: accountDefaults.printerUsefulHours,
              powerWatts: accountDefaults.printerPowerW,
              maintenance: 0,
              rate: accountDefaults.printingRatePerHour,
            }}
            onSaved={onSaved}
          />
        </div>

        <div className="mt-5 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl bg-white/10 px-5 py-2.5 text-sm font-semibold text-white transition hover:bg-white/15"
          >
            {t('common.close')}
          </button>
        </div>
      </div>
    </ModalOverlay>
  );
};
