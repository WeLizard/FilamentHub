/** Кнопка экспорта filament presets из OrcaSlicer в FilamentHub */

import { OrcaExportButton, type OrcaExportResult } from './OrcaExportButton';

interface ExportFromOrcaSlicerButtonProps {
  onExportComplete?: (result: OrcaExportResult) => void;
}

export const ExportFromOrcaSlicerButton: React.FC<ExportFromOrcaSlicerButtonProps> = ({ onExportComplete }) => (
  <OrcaExportButton
    capability="exportFilamentPresets"
    translationPrefix="exportOrcaSlicer"
    successLabel="started"
    hideWhenUnavailable
    size="regular"
    errorContext="Filament presets"
    onExportComplete={onExportComplete}
  />
);




