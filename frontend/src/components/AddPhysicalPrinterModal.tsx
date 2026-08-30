import { PrinterSetupWizard } from './PrinterSetupWizard';
import type { PrinterSetupWizardProps } from './PrinterSetupWizard';

export function AddPhysicalPrinterModal({
  isOpen, ...props
}: PrinterSetupWizardProps & { isOpen: boolean }) {
  return isOpen ? <PrinterSetupWizard {...props} /> : null;
}
