import { useTranslation } from 'react-i18next';
import { SETTING_MODES, type SettingMode } from '../data/orcaFieldModes';

interface SettingModeSelectorProps {
  mode: SettingMode;
  onChange: (mode: SettingMode) => void;
}

/** Simple / Advanced / Expert switch mirroring OrcaSlicer's setting levels. */
export const SettingModeSelector: React.FC<SettingModeSelectorProps> = ({ mode, onChange }) => {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-gray-400">{t('presetModal.settingMode.label')}</span>
      <div className="inline-flex rounded-lg border border-white/20 overflow-hidden text-xs">
        {SETTING_MODES.map((m) => (
          <button
            key={m}
            type="button"
            aria-pressed={mode === m}
            onClick={() => onChange(m)}
            className={`px-3 py-1 transition-all ${mode === m ? 'bg-purple-600 text-white' : 'text-gray-400 hover:text-white'}`}
          >
            {t(`presetModal.settingMode.${m}`)}
          </button>
        ))}
      </div>
    </div>
  );
};
