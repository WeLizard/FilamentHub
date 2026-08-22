/** Кнопка экспорта filament presets из OrcaSlicer в FilamentHub */

import { OrcaExportButton, type OrcaExportResult } from './OrcaExportButton';
import { useAuth } from '../contexts/AuthContext';

interface ExportFromOrcaSlicerButtonProps {
  onExportComplete?: (result: OrcaExportResult) => void;
}

export const ExportFromOrcaSlicerButton: React.FC<ExportFromOrcaSlicerButtonProps> = ({ onExportComplete }) => {
  const { user } = useAuth();
  return (
    <OrcaExportButton
      capability="exportFilamentPresets"
      translationPrefix="exportOrcaSlicer"
      successLabel="started"
      disabled={user?.allow_filament_presets_import === false}
      hideWhenUnavailable
      size="regular"
      errorContext="Filament presets"
      onExportComplete={onExportComplete}
    />
  );
};




