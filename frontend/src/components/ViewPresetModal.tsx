/** Модальное окно для просмотра пресета (только чтение) */

import { lazy, Suspense, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { X, History, Palette } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { filamentsAPI, presetsAPI } from '../api/client';
import type { Preset, Filament } from '../types/api';
import { SETTING_MODES } from '../data/orcaFieldModes';
import { useStoredUiChoice } from '../hooks/useStoredUiChoice';
import { withFilamentCardIdentity } from '../utils/orcaPresetSettings';
import { ModalOverlay } from './ModalOverlay';
import { FilamentSummaryCard } from './FilamentSummaryCard';
import { OrcaSchemaSettingsView } from './OrcaSchemaSettingsView';
import { PresetTestedOn } from './PresetTestedOn';
import { PresetHistoryModal } from './presetVersions/PresetHistoryModal';
import { PresetColorCopyDialog } from './PresetColorCopyDialog';
import { PresetOrigin } from './PresetOrigin';
import { useAuth } from '../contexts/AuthContext';
import { canCopyForColor, colorLabel } from '../utils/presetColorCopy';

// The editor is heavy; load it only when a copy is opened from here.
const CreatePresetModal = lazy(() =>
  import('./CreatePresetModal').then((module) => ({ default: module.CreatePresetModal })),
);

interface ViewFieldProps {
  label: string;
  value: number | null;
  unit?: string;
}

const ViewField: React.FC<ViewFieldProps> = ({ label, value, unit }) => (
  <div className="flex flex-col py-1">
    <span className="text-gray-400 text-xs mb-0.5">{label}</span>
    <span className="text-white font-medium text-sm">
      {value ?? '—'}
      {value !== null && unit && <span className="text-gray-400 ml-1 text-xs">{unit}</span>}
    </span>
  </div>
);

interface ViewPresetModalProps {
  isOpen: boolean;
  onClose: () => void;
  preset: Preset | null; // Пресет для просмотра
}

export const ViewPresetModal: React.FC<ViewPresetModalProps> = ({
  isOpen,
  onClose,
  preset: requestedPreset,
}) => {
  const { t } = useTranslation();
  const { user } = useAuth();
  // The window opens with the row it was given. A restore in the history can
  // move the preset to another material, so it is read again after one.
  const { data: storedPreset } = useQuery<Preset>({
    queryKey: ['preset', requestedPreset?.id, requestedPreset?.updated_at],
    queryFn: () => presetsAPI.get(requestedPreset!.id),
    enabled: isOpen && !!requestedPreset,
    initialData: requestedPreset ?? undefined,
    staleTime: Infinity,
  });
  const preset = requestedPreset && storedPreset?.id === requestedPreset.id ? storedPreset : requestedPreset;
  const [showHistory, setShowHistory] = useState(false);
  const [showColorCopy, setShowColorCopy] = useState(false);
  const [copyToEdit, setCopyToEdit] = useState<Preset | null>(null);
  const [settingMode, setSettingMode] = useStoredUiChoice(
    'presetView.settingMode',
    user?.id,
    SETTING_MODES,
    'simple',
  );

  const canRestore = !!user && !!preset && (user.id === preset.user_id || user.role === 'admin');

  // Загружаем данные филамента
  const { data: editingFilament } = useQuery<Filament>({
    queryKey: ['filament', preset?.filament_id],
    queryFn: () => filamentsAPI.get(preset!.filament_id!),
    enabled: !!preset?.filament_id,
  });

  const orcaSettings = useMemo(
    () => (preset?.orcaslicer_settings ?? {}) as Record<string, unknown>,
    [preset?.orcaslicer_settings],
  );
  const deliveredSettings = useMemo(
    () => withFilamentCardIdentity(orcaSettings, editingFilament),
    [orcaSettings, editingFilament],
  );

  if (!isOpen || !preset) return null;

  const close = () => {
    setShowColorCopy(false);
    setCopyToEdit(null);
    onClose();
  };

  // A fresh copy opens in the editor straight away: it is the author's draft.
  if (copyToEdit) {
    return (
      <Suspense fallback={null}>
        <CreatePresetModal isOpen preset={copyToEdit} onClose={close} />
      </Suspense>
    );
  }

  return (
    <ModalOverlay onClose={close} className="!bg-black/60">
      <div className="bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 rounded-2xl w-full max-w-5xl overflow-hidden flex flex-col border border-white/20 shadow-2xl max-h-[90vh]">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-white/10">
          <h2 className="text-2xl font-bold text-white">{t('viewPreset.title')}</h2>
          <button
            onClick={close}
            className="p-2 hover:bg-white/10 rounded-lg transition-colors"
          >
            <X className="w-6 h-6 text-white" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 custom-scrollbar">
          {/* Основная информация */}
          <div className="space-y-6">
            <div className="bg-white/5 border border-white/10 rounded-2xl p-6">
              <div className="flex flex-col gap-3">
                <h3 className="text-2xl font-bold text-white">{preset.name}</h3>
                {preset.description && (
                  <p className="text-gray-300">{preset.description}</p>
                )}
                <PresetOrigin sourceId={preset.derived_from_preset_id} />
                <PresetTestedOn printers={preset.printers} />
              </div>
            </div>

            {editingFilament && (
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('viewPreset.filament')}</label>
                <FilamentSummaryCard filament={editingFilament} />
              </div>
            )}
          </div>

          <div className="mt-6">
            {Object.keys(orcaSettings).length > 0 ? (
              <OrcaSchemaSettingsView
                title={t('viewPreset.detailedSettings')}
                settings={deliveredSettings}
                mode={settingMode}
                onModeChange={setSettingMode}
              />
            ) : (
              // Сгенерированные пресеты хранят только основные параметры в колонках.
              <>
                <h3 className="text-lg font-semibold text-white mb-3">{t('viewPreset.basicSettings')}</h3>
                <div className="bg-white/5 rounded-xl p-3">
                  <div className="grid grid-cols-[repeat(auto-fill,minmax(8rem,1fr))] gap-x-3 gap-y-2.5">
                    <ViewField label={t('viewPreset.nozzle')} value={preset.extruder_temp} unit="°C" />
                    <ViewField label={t('viewPreset.bed')} value={preset.bed_temp} unit="°C" />
                    <ViewField label={t('viewPreset.fan')} value={preset.fan_speed} unit="%" />
                    <ViewField label={t('viewPreset.flow')} value={preset.flow_rate} unit="%" />
                    <ViewField label={t('viewPreset.retractionLength')} value={preset.retraction_length} unit="mm" />
                    <ViewField label={t('viewPreset.retractionSpeed')} value={preset.retraction_speed} unit="mm/s" />
                  </div>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-between items-center p-6 border-t border-white/10">
          {preset?.id ? (
            <button
              onClick={() => setShowHistory(true)}
              className="flex items-center gap-2 px-4 py-3 text-gray-400 hover:text-white transition-colors text-sm"
            >
              <History className="w-4 h-4" />
              {t('presetVersions.openButton')}
            </button>
          ) : (
            <span />
          )}
          <div className="flex flex-wrap items-center justify-end gap-3">
            {canCopyForColor(preset, user?.id) && (
              <button
                type="button"
                onClick={() => setShowColorCopy(true)}
                className="flex items-center gap-2 px-4 py-3 text-sm text-purple-200 hover:text-white hover:bg-white/10 rounded-xl transition-colors"
              >
                <Palette className="w-4 h-4" />
                {t('presetColorCopy.action')}
              </button>
            )}
            <button
              onClick={close}
              className="px-6 py-3 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all"
            >
              {t('viewPreset.close')}
            </button>
          </div>
        </div>
      </div>

      {showColorCopy && (
        <PresetColorCopyDialog
          source={preset}
          currentColor={editingFilament ? colorLabel(editingFilament) : null}
          onClose={() => setShowColorCopy(false)}
          onCopied={(copy) => {
            setShowColorCopy(false);
            setCopyToEdit(copy);
          }}
        />
      )}

      {showHistory && preset?.id && (
        <PresetHistoryModal
          presetId={preset.id}
          canRestore={canRestore}
          onClose={() => setShowHistory(false)}
        />
      )}
    </ModalOverlay>
  );
};
