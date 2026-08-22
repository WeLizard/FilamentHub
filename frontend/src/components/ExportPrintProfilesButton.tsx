/** Кнопка экспорта print profiles из OrcaSlicer в FilamentHub */

import { useAuth } from '../contexts/AuthContext';
import { OrcaExportButton, type OrcaExportResult } from './OrcaExportButton';

interface ExportPrintProfilesButtonProps {
  onExportComplete?: (result: OrcaExportResult) => void;
}

export const ExportPrintProfilesButton: React.FC<ExportPrintProfilesButtonProps> = ({ onExportComplete }) => {
  const { user } = useAuth();
  const isExportDisabled = user?.allow_print_profiles_import === false;

  return (
    <OrcaExportButton
      capability="exportPrintProfiles"
      translationPrefix="exportPrintProfiles"
      successLabel="done"
      disabled={isExportDisabled}
      hideWhenUnavailable
      errorContext="Print profiles"
      onExportComplete={onExportComplete}
    />
  );
};

