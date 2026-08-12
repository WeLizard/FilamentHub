/** Кнопка экспорта printer profiles из OrcaSlicer в FilamentHub */

import { useAuth } from '../contexts/AuthContext';
import { OrcaExportButton, type OrcaExportResult } from './OrcaExportButton';

interface ExportPrinterProfilesButtonProps {
  onExportComplete?: (result: OrcaExportResult) => void;
}

export const ExportPrinterProfilesButton: React.FC<ExportPrinterProfilesButtonProps> = ({ onExportComplete }) => {
  const { user } = useAuth();
  // The button pulls configurations from the slicer into FilamentHub, so it
  // follows the inbound switch — the outbound one is about the other direction.
  const isExportDisabled = user?.allow_printer_profiles_import === false;

  return (
    <OrcaExportButton
      capability="exportPrinterProfiles"
      translationPrefix="exportPrinterProfiles"
      successLabel="done"
      disabled={isExportDisabled}
      errorContext="Printer profiles"
      onExportComplete={onExportComplete}
    />
  );
};

