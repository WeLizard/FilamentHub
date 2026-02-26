/** Модальное окно для просмотра пресета (только чтение) */

import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X, CheckCircle2, XCircle } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { presetsAPI, filamentsAPI } from '../api/client';
import type { Preset, Filament } from '../types/api';
import { useHeaderVisible } from '../hooks/useHeaderVisible';
import { FilamentSummaryCard } from './FilamentSummaryCard';

// Вспомогательные компоненты для отображения значений
interface ViewFieldProps {
  label: string;
  value: string | number | null | undefined | '';
  unit?: string;
}

const ViewField: React.FC<ViewFieldProps> = ({ label, value, unit }) => {
  const hasContent = value !== null && value !== undefined && value !== '';
  const displayValue = hasContent ? value : '—';
  
  return (
    <div className="flex flex-col py-1">
      <span className="text-gray-400 text-xs mb-0.5">{label}</span>
      <span className="text-white font-medium text-sm">
        {displayValue}
        {unit && <span className="text-gray-400 ml-1 text-xs">{unit}</span>}
      </span>
    </div>
  );
};

interface ViewCheckboxProps {
  label: string;
  checked: boolean;
}

const ViewCheckbox: React.FC<ViewCheckboxProps> = ({ label, checked }) => {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col py-1">
      <span className="text-gray-400 text-xs mb-0.5">{label}</span>
      <span className="text-white font-medium text-sm flex items-center space-x-1">
        {checked ? (
          <>
            <CheckCircle2 className="w-4 h-4 text-green-400" />
            <span className="text-green-400">{t('viewPreset.yes')}</span>
          </>
        ) : (
          <>
            <XCircle className="w-4 h-4 text-red-400" />
            <span className="text-red-400">{t('viewPreset.no')}</span>
          </>
        )}
      </span>
    </div>
  );
};

interface ViewPresetModalProps {
  isOpen: boolean;
  onClose: () => void;
  preset: Preset | null; // Пресет для просмотра
}

export const ViewPresetModal: React.FC<ViewPresetModalProps> = ({
  isOpen,
  onClose,
  preset,
}) => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<'profile' | 'cooling' | 'override' | 'retraction' | 'gcode' | 'extruder_mm' | 'compatibility' | 'notes'>('profile');
  const isHeaderVisible = useHeaderVisible();

  // Загружаем данные филамента
  const { data: editingFilament } = useQuery<Filament>({
    queryKey: ['filament', preset?.filament_id],
    queryFn: () => filamentsAPI.get(preset!.filament_id!),
    enabled: !!preset?.filament_id,
  });

  // Извлекаем значения из orcaslicer_settings
  const orcaslicerSettings = preset?.orcaslicer_settings || {};

  // Вспомогательная функция для извлечения значений из массивов (как в CreatePresetModal)
  const getValue = (key: string): any => {
    const val = orcaslicerSettings[key];
    if (Array.isArray(val)) {
      return val[0] || null;
    }
    return val || null;
  };

  const getBoolValue = (key: string): boolean => {
    const val = getValue(key);
    return val === '1' || val === 1 || val === true;
  };

  const getNumberValue = (key: string): number | null => {
    const val = getValue(key);
    if (val === null || val === undefined || val === '') return null;
    const num = typeof val === 'string' ? parseFloat(val) : Number(val);
    return isNaN(num) ? null : num;
  };

  const getStringValue = (key: string): string | null => {
    const val = getValue(key);
    return val ? String(val) : null;
  };

  const getPercentValue = (key: string): string | null => {
    const val = getValue(key);
    if (!val) return null;
    const str = String(val);
    // Убираем лишние %, если есть, и добавляем один
    const cleaned = str.replace(/%/g, '');
    return cleaned ? `${cleaned}%` : null;
  };

  const getArrayValue = (key: string): string | null => {
    const val = orcaslicerSettings[key];
    if (Array.isArray(val)) {
      return val.join(', ');
    }
    return val ? String(val) : null;
  };

  const getLayersText = (count: number | null | undefined): string | null => {
    if (count === null || count === undefined) return null;
    return t('viewPreset.layersCount', { count: Math.floor(count) });
  };

  // Основные настройки
  const extruderTemp = preset?.extruder_temp || 0;
  const bedTemp = preset?.bed_temp || 0;
  const printSpeed = preset?.print_speed || 0;
  const travelSpeed = preset?.travel_speed || 0;
  // Примечание: layer_height и first_layer_height - это параметры профилей печати (Print Profile),
  // а не профилей филамента (Preset), поэтому не отображаются здесь
  const flowRate = preset?.flow_rate || 0;
  const fanSpeed = preset?.fan_speed || 0;
  const retractionLength = preset?.retraction_length || 0;
  const retractionSpeed = preset?.retraction_speed || 0;

  // Подробные настройки из orcaslicer_settings
  const tempRangeLow = getNumberValue('nozzle_temperature_range_low');
  const tempRangeHigh = getNumberValue('nozzle_temperature_range_high');
  const nozzleTempInitialLayer = getNumberValue('nozzle_temperature_initial_layer');
  const idleTemperature = getNumberValue('idle_temperature');
  const softeningTemperature = getNumberValue('temperature_vitrification');
  const volumetricSpeed = getNumberValue('filament_max_volumetric_speed');
  const adaptiveVolumetricSpeed = getBoolValue('filament_adaptive_volumetric_speed');
  const volumetricSpeedCoefficients = getStringValue('volumetric_speed_coefficients');
  const adaptivePAModel = getArrayValue('adaptive_pressure_advance_model') || getStringValue('adaptive_pressure_advance_model');
  const filamentShrink = getPercentValue('filament_shrink');
  const filamentShrinkageCompensationZ = getPercentValue('filament_shrinkage_compensation_z');
  const defaultFilamentColour = editingFilament?.color_hex || getStringValue('default_filament_colour');
  const filamentIsSupport = getBoolValue('filament_is_support');
  const filamentSoluble = getBoolValue('filament_soluble');
  const filamentAdhesivenessCategory = getNumberValue('filament_adhesiveness_category');
  const filamentPrintable = getNumberValue('filament_printable');
  
  // Заметки
  let filamentNotes = '';
  if (orcaslicerSettings.filament_notes) {
    if (Array.isArray(orcaslicerSettings.filament_notes)) {
      filamentNotes = orcaslicerSettings.filament_notes.join('\n');
    } else if (typeof orcaslicerSettings.filament_notes === 'string') {
      filamentNotes = orcaslicerSettings.filament_notes;
    }
  }

  // Pressure Advance
  const enablePressureAdvance = getBoolValue('enable_pressure_advance');
  const pressureAdvance = getNumberValue('pressure_advance');
  const adaptivePressureAdvance = getBoolValue('adaptive_pressure_advance');
  const adaptivePAOverhangs = getBoolValue('adaptive_pressure_advance_overhangs');
  const adaptivePABridges = getNumberValue('adaptive_pressure_advance_bridges');

  // Охлаждение
  const enableChamberControl = getBoolValue('activate_chamber_temp_control');
  const chamberTemp = getNumberValue('chamber_temperature');
  const closeFanFirstXLayers = getNumberValue('close_fan_the_first_x_layers');
  const fullFanSpeedLayer = getNumberValue('full_fan_speed_layer');
  const fanCoolingLayerTime = getNumberValue('fan_cooling_layer_time');
  const fanMaxSpeedLayerTime = getNumberValue('slow_down_layer_time');
  const fanMinSpeed = getNumberValue('fan_min_speed');
  const fanMaxSpeed = getNumberValue('fan_max_speed');
  const reduceFanStopStartFreq = getBoolValue('reduce_fan_stop_start_freq');
  const slowDownForLayerCooling = getBoolValue('slow_down_for_layer_cooling');
  const dontSlowDownOuterWall = getBoolValue('dont_slow_down_outer_wall');
  const slowDownMinSpeed = getNumberValue('slow_down_min_speed');
  const enableOverhangBridgeFan = getBoolValue('enable_overhang_bridge_fan');
  const overhangFanSpeed = getNumberValue('overhang_fan_speed');
  const overhangFanThreshold = getPercentValue('overhang_fan_threshold');
  const internalBridgeFanSpeed = getNumberValue('internal_bridge_fan_speed');
  const ironingFanSpeed = getNumberValue('ironing_fan_speed');
  const supportMaterialInterfaceFanSpeed = getNumberValue('support_material_interface_fan_speed');
  const additionalCoolingFanSpeed = getNumberValue('additional_cooling_fan_speed');
  const enableExhaustFan = getBoolValue('enable_exhaust_fan') || !!getNumberValue('during_print_exhaust_fan_speed') || !!getNumberValue('complete_print_exhaust_fan_speed');
  const duringPrintExhaustFanSpeed = getNumberValue('during_print_exhaust_fan_speed');
  const completePrintExhaustFanSpeed = getNumberValue('complete_print_exhaust_fan_speed');
  const activateAirFiltration = getBoolValue('activate_air_filtration');

  // Ретракт
  const deretractionSpeed = getNumberValue('filament_deretraction_speed');
  const retractionMinimumTravel = getNumberValue('filament_retraction_minimum_travel');
  const retractBeforeWipe = getPercentValue('filament_retract_before_wipe');
  const retractWhenChangingLayer = getBoolValue('filament_retract_when_changing_layer');
  const retractRestartExtra = getNumberValue('filament_retract_restart_extra');
  const filamentZHop = getNumberValue('filament_z_hop');
  const filamentZHopTypes = getStringValue('filament_z_hop_types');
  const retractLiftAbove = getNumberValue('filament_retract_lift_above');
  const retractLiftBelow = getNumberValue('filament_retract_lift_below');
  const retractLiftEnforce = getStringValue('filament_retract_lift_enforce');
  const filamentWipe = getBoolValue('filament_wipe');
  const filamentWipeDistance = getNumberValue('filament_wipe_distance');
  const filamentFlushTemp = getNumberValue('filament_flush_temp');
  const filamentFlushVolumetricSpeed = getNumberValue('filament_flush_volumetric_speed');
  const retractionDistancesWhenCut = getStringValue('filament_retraction_distances_when_cut');
  const longRetractionsWhenCut = getStringValue('filament_long_retractions_when_cut');
  const longRetractionsWhenEC = getBoolValue('long_retractions_when_ec');
  const retractionDistancesWhenEC = getNumberValue('retraction_distances_when_ec');

  // G-code
  let filamentStartGcode = '';
  if (orcaslicerSettings.filament_start_gcode && Array.isArray(orcaslicerSettings.filament_start_gcode)) {
    filamentStartGcode = orcaslicerSettings.filament_start_gcode.join('\n');
  } else if (orcaslicerSettings.start_filament_gcode && Array.isArray(orcaslicerSettings.start_filament_gcode)) {
    filamentStartGcode = orcaslicerSettings.start_filament_gcode.join('\n');
  } else if (typeof orcaslicerSettings.filament_start_gcode === 'string') {
    filamentStartGcode = orcaslicerSettings.filament_start_gcode;
  }
  
  let filamentEndGcode = '';
  if (orcaslicerSettings.filament_end_gcode && Array.isArray(orcaslicerSettings.filament_end_gcode)) {
    filamentEndGcode = orcaslicerSettings.filament_end_gcode.join('\n');
  } else if (orcaslicerSettings.end_filament_gcode && Array.isArray(orcaslicerSettings.end_filament_gcode)) {
    filamentEndGcode = orcaslicerSettings.end_filament_gcode.join('\n');
  } else if (typeof orcaslicerSettings.filament_end_gcode === 'string') {
    filamentEndGcode = orcaslicerSettings.filament_end_gcode;
  }
  
  const filamentMultitoolRamming = getBoolValue('filament_multitool_ramming');
  const filamentMultitoolRammingVolume = getNumberValue('filament_multitool_ramming_volume');
  const filamentMultitoolRammingFlow = getNumberValue('filament_multitool_ramming_flow');
  const filamentChangeLength = getNumberValue('filament_change_length');
  const filamentCoolingInitialSpeed = getNumberValue('filament_cooling_initial_speed');
  const filamentCoolingFinalSpeed = getNumberValue('filament_cooling_final_speed');
  const filamentCoolingMoves = getNumberValue('filament_cooling_moves');
  const filamentStampingDistance = getNumberValue('filament_stamping_distance');
  const filamentStampingLoadingSpeed = getNumberValue('filament_stamping_loading_speed');
  const filamentMinimalPurgeOnWipeTower = getNumberValue('filament_minimal_purge_on_wipe_tower');
  const pelletFlowCoefficient = getNumberValue('pellet_flow_coefficient');
  const filamentLoadingSpeed = getNumberValue('filament_loading_speed');
  const filamentLoadingSpeedStart = getNumberValue('filament_loading_speed_start');
  const filamentUnloadingSpeed = getNumberValue('filament_unloading_speed');
  const filamentUnloadingSpeedStart = getNumberValue('filament_unloading_speed_start');
  const filamentToolchangeDelay = getNumberValue('filament_toolchange_delay');

  // Совместимость
  const filamentExtruderVariant = getStringValue('filament_extruder_variant');
  const requiredNozzleHRC = getNumberValue('required_nozzle_HRC') || getNumberValue('required_nozzle_hrc');
  const compatiblePrinters = getArrayValue('compatible_printers');
  const compatiblePrintersCondition = getStringValue('compatible_printers_condition');
  const compatiblePrints = getArrayValue('compatible_prints');
  const compatiblePrintsCondition = getStringValue('compatible_prints_condition');

  if (!isOpen || !preset) return null;

  return (
    <div className={`fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm ${isHeaderVisible ? 'pt-[88px]' : ''}`}>
      <div className={`bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 rounded-2xl w-full max-w-5xl overflow-hidden flex flex-col border border-white/20 shadow-2xl pointer-events-auto ${isHeaderVisible ? 'max-h-[calc(100vh-100px)]' : 'max-h-[90vh]'}`}>
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-white/10">
          <h2 className="text-2xl font-bold text-white">{t('viewPreset.title')}</h2>
          <button
            onClick={onClose}
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
              </div>
            </div>

            {editingFilament && (
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('viewPreset.filament')}</label>
                <FilamentSummaryCard filament={editingFilament} />
              </div>
            )}
          </div>

          {/* Основные настройки */}
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-white mb-3">{t('viewPreset.basicSettings')}</h3>
            
            <div className="bg-white/5 rounded-xl p-3">
              <div className="grid grid-cols-5 gap-x-3 gap-y-2.5">
                <ViewField label={t('viewPreset.nozzle')} value={extruderTemp} unit="°C" />
                <ViewField label={t('viewPreset.bed')} value={bedTemp} unit="°C" />
                <ViewField label={t('viewPreset.print')} value={printSpeed} unit="mm/s" />
                <ViewField label={t('viewPreset.travel')} value={travelSpeed} unit="mm/s" />
                <ViewField label={t('viewPreset.fan')} value={fanSpeed} unit="%" />

                <ViewField label={t('viewPreset.flow')} value={flowRate} unit="%" />
                <ViewField label={t('viewPreset.retractionLength')} value={retractionLength} unit="mm" />
                <ViewField label={t('viewPreset.retractionSpeed')} value={retractionSpeed} unit="mm/s" />
                <ViewField label={t('viewPreset.softeningTemp')} value={softeningTemperature} unit="°C" />
                <ViewField label={t('viewPreset.nozzleHardness')} value={requiredNozzleHRC} unit="HRC" />
              </div>
            </div>
          </div>

          {/* Подробные настройки */}
          <div className="mt-6">
            <h3 className="text-lg font-semibold text-white mb-4">{t('viewPreset.detailedSettings')}</h3>
            
            {/* Вкладки */}
            <div className="flex flex-wrap gap-2 mb-4 border-b border-white/20">
              <button
                type="button"
                onClick={() => setActiveTab('profile')}
                className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-all ${
                  activeTab === 'profile'
                    ? 'bg-white/10 text-white border-b-2 border-purple-500'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                {t('viewPreset.tabs.filamentProfile')}
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('cooling')}
                className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-all ${
                  activeTab === 'cooling'
                    ? 'bg-white/10 text-white border-b-2 border-purple-500'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                {t('viewPreset.tabs.cooling')}
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('override')}
                className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-all ${
                  activeTab === 'override'
                    ? 'bg-white/10 text-white border-b-2 border-purple-500'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                {t('viewPreset.tabs.override')}
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('retraction')}
                className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-all ${
                  activeTab === 'retraction'
                    ? 'bg-white/10 text-white border-b-2 border-purple-500'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                {t('viewPreset.tabs.retraction')}
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('gcode')}
                className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-all ${
                  activeTab === 'gcode'
                    ? 'bg-white/10 text-white border-b-2 border-purple-500'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                G-code
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('extruder_mm')}
                className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-all ${
                  activeTab === 'extruder_mm'
                    ? 'bg-white/10 text-white border-b-2 border-purple-500'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                {t('viewPreset.tabs.extruderMM')}
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('compatibility')}
                className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-all ${
                  activeTab === 'compatibility'
                    ? 'bg-white/10 text-white border-b-2 border-purple-500'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                {t('viewPreset.tabs.compatibility')}
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('notes')}
                className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-all ${
                  activeTab === 'notes'
                    ? 'bg-white/10 text-white border-b-2 border-purple-500'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                {t('viewPreset.tabs.notes')}
              </button>
            </div>

            {/* Содержимое вкладок */}
            <div className="p-4 bg-white/5 rounded-xl border border-white/10">
              {activeTab === 'profile' && (
                <div className="space-y-4">
                  {/* Общая информация */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">{t('viewPreset.generalInfo')}</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      {editingFilament && (
                        <>
                          <ViewField label={t('viewPreset.type')} value={editingFilament.material_type || null} />
                          <ViewField label={t('viewPreset.manufacturer')} value={editingFilament.brand_name || null} />
                          <div></div>
                        </>
                      )}
                      <ViewCheckbox label={t('viewPreset.solubleMaterial')} checked={filamentSoluble} />
                      <ViewCheckbox label={t('viewPreset.support')} checked={filamentIsSupport} />
                      <ViewField label={t('viewPreset.rammingLength')} value={filamentMultitoolRammingVolume} unit="mm" />
                      <ViewField label={t('viewPreset.shrinkCompensationXY')} value={filamentShrink} />
                      <ViewField label={t('viewPreset.shrinkCompensationZ')} value={filamentShrinkageCompensationZ} />
                      <ViewField label={t('viewPreset.softeningTempShort')} value={softeningTemperature} unit="°C" />
                      <ViewField label={t('viewPreset.idleTemp')} value={idleTemperature} unit="°C" />
                      <ViewField label={t('viewPreset.adhesionCategory')} value={filamentAdhesivenessCategory} />
                      <ViewField label={t('viewPreset.printability')} value={filamentPrintable} />
                      {defaultFilamentColour && (
                        <div className="flex flex-col py-1">
                          <span className="text-gray-400 text-xs mb-0.5">{t('viewPreset.defaultColor')}</span>
                          <div className="flex items-center space-x-2">
                            <div 
                              className="w-6 h-6 rounded border border-white/20"
                              style={{ backgroundColor: defaultFilamentColour }}
                            />
                            <span className="text-white font-medium text-sm">{defaultFilamentColour}</span>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Рекомендуемая температура сопла */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">{t('viewPreset.recommendedNozzleTemp')}</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewField label={t('viewPreset.min')} value={tempRangeLow} unit="°C" />
                      <ViewField label={t('viewPreset.max')} value={tempRangeHigh} unit="°C" />
                      <div></div>
                    </div>
                  </div>

                  {/* Коэффициент потока и Pressure Advance */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">{t('viewPreset.flowAndPA')}</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewField label={t('viewPreset.modelFlowCoef')} value={flowRate !== 100 ? (flowRate / 100).toFixed(2) : '1.00'} />
                      <ViewCheckbox label={t('viewPreset.pressureAdvance')} checked={enablePressureAdvance} />
                      {enablePressureAdvance && (
                        <>
                          <ViewField label={t('viewPreset.paCoef')} value={pressureAdvance} />
                          <ViewCheckbox label={t('viewPreset.adaptivePA')} checked={adaptivePressureAdvance} />
                          <ViewCheckbox label={t('viewPreset.paOverhangs')} checked={adaptivePAOverhangs} />
                          {adaptivePressureAdvance && adaptivePABridges !== null && (
                            <ViewField label={t('viewPreset.paBridgesCoef')} value={adaptivePABridges} />
                          )}
                        </>
                      )}
                    </div>
                    {/* Измеренные значения адаптивного Pressure advance */}
                    {adaptivePressureAdvance && adaptivePAModel && (
                      <div className="mt-3">
                        <h5 className="text-xs font-semibold text-white/60 mb-1">{t('viewPreset.adaptivePAValues')}</h5>
                        <pre className="bg-white/5 p-2 rounded-lg text-xs text-gray-300 font-mono whitespace-pre-wrap break-words">
                          {adaptivePAModel}
                        </pre>
                      </div>
                    )}
                  </div>

                  {/* Температура */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">{t('viewPreset.temperature')}</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewField label={t('viewPreset.nozzleFirstLayer')} value={nozzleTempInitialLayer} unit="°C" />
                      <ViewField label={t('viewPreset.bedFirstLayer')} value={bedTemp} unit="°C" />
                      <ViewCheckbox label={t('viewPreset.chamberControl')} checked={enableChamberControl} />
                      <ViewField label={t('viewPreset.nozzleLayers')} value={extruderTemp} unit="°C" />
                      <ViewField label={t('viewPreset.bedLayers')} value={bedTemp} unit="°C" />
                      {enableChamberControl ? (
                        <ViewField label={t('viewPreset.chamberTemp')} value={chamberTemp} unit="°C" />
                      ) : (
                        <div></div>
                      )}
                    </div>
                  </div>

                  {/* Ограничение объёмного расхода */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">{t('viewPreset.volumetricLimit')}</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewCheckbox label={t('viewPreset.adaptiveLimit')} checked={adaptiveVolumetricSpeed} />
                      <ViewField label={t('viewPreset.volumetricFlow')} value={volumetricSpeed} unit="mm³/s" />
                      <div></div>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'cooling' && (
                <div className="space-y-4">
                  <div className="grid grid-cols-3 gap-x-3 gap-y-2">
                    {closeFanFirstXLayers !== null && closeFanFirstXLayers !== undefined && (
                      <div className="flex flex-col py-1">
                        <span className="text-gray-400 text-xs mb-0.5">{t('viewPreset.disableFanFirst')}</span>
                        <span className="text-white font-medium text-sm">
                          {getLayersText(closeFanFirstXLayers)}
                        </span>
                      </div>
                    )}
                    <ViewField label={t('viewPreset.fullSpeedLayer')} value={fullFanSpeedLayer} />
                    <ViewField label={t('viewPreset.layerCoolingTime')} value={fanCoolingLayerTime} unit="s" />
                    <ViewField label={t('viewPreset.maxSpeedTime')} value={fanMaxSpeedLayerTime} unit="s" />
                    <ViewField label={t('viewPreset.minFanSpeed')} value={fanMinSpeed} unit="%" />
                    <ViewField label={t('viewPreset.maxFanSpeed')} value={fanMaxSpeed} unit="%" />
                    <ViewCheckbox label={t('viewPreset.fanAlwaysOn')} checked={reduceFanStopStartFreq} />
                    <ViewCheckbox label={t('viewPreset.slowDownForCooling')} checked={slowDownForLayerCooling} />
                    <ViewCheckbox label={t('viewPreset.dontSlowPerimeter')} checked={dontSlowDownOuterWall} />
                    {slowDownForLayerCooling && (
                      <ViewField label={t('viewPreset.minPrintSpeed')} value={slowDownMinSpeed} unit="mm/s" />
                    )}
                    <ViewCheckbox label={t('viewPreset.overhangBridgeFan')} checked={enableOverhangBridgeFan} />
                    {enableOverhangBridgeFan && (
                      <>
                        <ViewField label={t('viewPreset.overhangFan')} value={overhangFanSpeed} unit="%" />
                        <ViewField label={t('viewPreset.overhangThreshold')} value={overhangFanThreshold} />
                        {internalBridgeFanSpeed !== null && internalBridgeFanSpeed !== -1 && (
                          <ViewField label={t('viewPreset.internalBridgeFan')} value={internalBridgeFanSpeed} unit="%" />
                        )}
                        {internalBridgeFanSpeed === -1 && (
                          <div className="flex flex-col py-1">
                            <span className="text-gray-400 text-xs mb-0.5">{t('viewPreset.internalBridgeFan')}</span>
                            <span className="text-white font-medium text-sm">{t('viewPreset.default')}</span>
                          </div>
                        )}
                        <ViewField label={t('viewPreset.ironingFan')} value={ironingFanSpeed} unit="%" />
                        <ViewField label={t('viewPreset.supportInterfaceFan')} value={supportMaterialInterfaceFanSpeed} unit="%" />
                        <ViewField label={t('viewPreset.additionalFanSpeed')} value={additionalCoolingFanSpeed} unit="%" />
                      </>
                    )}
                    <ViewCheckbox label={t('viewPreset.exhaustFan')} checked={enableExhaustFan} />
                    {enableExhaustFan && (
                      <>
                        <ViewField label={t('viewPreset.fanDuringPrint')} value={duringPrintExhaustFanSpeed} unit="%" />
                        <ViewField label={t('viewPreset.fanAfterPrint')} value={completePrintExhaustFanSpeed} unit="%" />
                        <ViewCheckbox label={t('viewPreset.airFiltration')} checked={activateAirFiltration} />
                      </>
                    )}
                  </div>
                </div>
              )}

              {activeTab === 'override' && (
                <div className="space-y-4">
                  {/* Скорости и замедления */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">{t('viewPreset.speedsAndSlowdowns')}</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewCheckbox label={t('viewPreset.slowDownForCooling')} checked={slowDownForLayerCooling} />
                      <ViewCheckbox label={t('viewPreset.dontSlowPerimeter')} checked={dontSlowDownOuterWall} />
                      {slowDownForLayerCooling && (
                        <ViewField label={t('viewPreset.minPrintSpeed')} value={slowDownMinSpeed} unit="mm/s" />
                      )}
                    </div>
                  </div>

                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">{t('viewPreset.retract')}</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewField label={t('viewPreset.length')} value={retractionLength} unit="mm" />
                      <ViewField label={t('viewPreset.extractionSpeed')} value={retractionSpeed} unit="mm/s" />
                      <ViewField label={t('viewPreset.zHopHeight')} value={filamentZHop} unit="mm" />
                      <ViewField label={t('viewPreset.feedSpeed')} value={deretractionSpeed} unit="mm/s" />
                      <ViewField label={t('viewPreset.zHopType')} value={filamentZHopTypes || null} />
                      <ViewField label={t('viewPreset.onSurfaces')} value={retractLiftEnforce || null} />
                      <ViewField label={t('viewPreset.liftZAbove')} value={retractLiftAbove} unit="mm" />
                      <ViewField label={t('viewPreset.liftZBelow')} value={retractLiftBelow} unit="mm" />
                      <ViewField label={t('viewPreset.extraFeedLength')} value={retractRestartExtra} unit="mm" />
                      <ViewField label={t('viewPreset.travelThreshold')} value={retractionMinimumTravel} unit="mm" />
                      <ViewCheckbox label={t('viewPreset.retractOnLayerChange')} checked={retractWhenChangingLayer} />
                      <ViewCheckbox label={t('viewPreset.nozzleWipe')} checked={filamentWipe} />
                      {filamentWipe && (
                        <>
                          <ViewField label={t('viewPreset.wipeDistance')} value={filamentWipeDistance} unit="mm" />
                          <ViewField label={t('viewPreset.retractBeforeWipe')} value={retractBeforeWipe} />
                          <div></div>
                        </>
                      )}
                    </div>
                  </div>

                </div>
              )}

              {activeTab === 'retraction' && (
                <div className="space-y-4">
                  {/* Основные параметры ретракта */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">{t('viewPreset.basicParams')}</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewField label={t('viewPreset.length')} value={retractionLength} unit="mm" />
                      <ViewField label={t('viewPreset.extractionSpeed')} value={retractionSpeed} unit="mm/s" />
                      <ViewField label={t('viewPreset.zHopHeight')} value={filamentZHop} unit="mm" />
                      <ViewField label={t('viewPreset.feedSpeed')} value={deretractionSpeed} unit="mm/s" />
                      <ViewField label={t('viewPreset.zHopType')} value={filamentZHopTypes || null} />
                      <ViewField label={t('viewPreset.onSurfaces')} value={retractLiftEnforce || null} />
                      <ViewField label={t('viewPreset.liftZAbove')} value={retractLiftAbove} unit="mm" />
                      <ViewField label={t('viewPreset.liftZBelow')} value={retractLiftBelow} unit="mm" />
                      <ViewField label={t('viewPreset.extraFeedLength')} value={retractRestartExtra} unit="mm" />
                      <ViewField label={t('viewPreset.travelThreshold')} value={retractionMinimumTravel} unit="mm" />
                      <ViewCheckbox label={t('viewPreset.retractOnLayerChange')} checked={retractWhenChangingLayer} />
                      <ViewCheckbox label={t('viewPreset.nozzleWipe')} checked={filamentWipe} />
                      {filamentWipe && (
                        <>
                          <ViewField label={t('viewPreset.wipeDistance')} value={filamentWipeDistance} unit="mm" />
                          <ViewField label={t('viewPreset.retractBeforeWipe')} value={retractBeforeWipe} />
                          <ViewField label={t('viewPreset.flushTemp')} value={filamentFlushTemp} unit="°C" />
                          <ViewField label={t('viewPreset.flushVolumetricSpeed')} value={filamentFlushVolumetricSpeed} unit="mm³/s" />
                          <div></div>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Дополнительные параметры ретракта */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">{t('viewPreset.additionalRetractParams')}</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewField label={t('viewPreset.retractOnCut')} value={retractionDistancesWhenCut} />
                      <ViewField label={t('viewPreset.longRetractsOnCut')} value={longRetractionsWhenCut} />
                      <div></div>
                      <ViewCheckbox label={t('viewPreset.longRetractOnEC')} checked={longRetractionsWhenEC} />
                      {longRetractionsWhenEC && (
                        <>
                          <ViewField label={t('viewPreset.retractDistOnEC')} value={retractionDistancesWhenEC} unit="mm" />
                          <div></div>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Мультиматериал (многоэкструдерные принтеры) */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">{t('viewPreset.multimaterial')}</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewCheckbox label={t('viewPreset.multitoolRamming')} checked={filamentMultitoolRamming} />
                      {filamentMultitoolRamming && (
                        <>
                          <ViewField label={t('viewPreset.rammingVolume')} value={filamentMultitoolRammingVolume} unit="mm³" />
                          <ViewField label={t('viewPreset.rammingFlow')} value={filamentMultitoolRammingFlow} unit="mm³/s" />
                        </>
                      )}
                      {/* TODO: Добавить поля для начального и заменяющего экструдера, когда будут известны ключи */}
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'gcode' && (
                <div className="space-y-4">
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">{t('viewPreset.startGcode')}</h4>
                    {filamentStartGcode ? (
                      <pre className="bg-white/5 p-2 rounded-lg text-xs text-gray-300 font-mono whitespace-pre-wrap break-words mt-2">
                        {filamentStartGcode}
                      </pre>
                    ) : (
                      <p className="text-gray-400 text-xs mt-2">{t('viewPreset.none')}</p>
                    )}
                  </div>
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">{t('viewPreset.endGcode')}</h4>
                    {filamentEndGcode ? (
                      <pre className="bg-white/5 p-2 rounded-lg text-xs text-gray-300 font-mono whitespace-pre-wrap break-words mt-2">
                        {filamentEndGcode}
                      </pre>
                    ) : (
                      <p className="text-gray-400 text-xs mt-2">{t('viewPreset.none')}</p>
                    )}
                  </div>
                </div>
              )}

              {activeTab === 'extruder_mm' && (
                <div className="space-y-4">
                  {/* Параметры экструдера */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">{t('viewPreset.extruderParams')}</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewField label={t('viewPreset.extruderVariant')} value={filamentExtruderVariant} />
                      <ViewField label={t('viewPreset.requiredNozzleHRC')} value={requiredNozzleHRC} unit="HRC" />
                      <div></div>
                    </div>
                  </div>

                  {/* Параметры черновой башни */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">{t('viewPreset.wipeTowerParams')}</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewField label={t('viewPreset.minPurgeVolume')} value={filamentMinimalPurgeOnWipeTower} unit="mm³" />
                      <div></div>
                      <div></div>
                    </div>
                  </div>

                  {/* Параметры смены инструмента в одноэкструдерных мультиматериальных принтерах */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">{t('viewPreset.singleExtruderToolchange')}</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewField label={t('viewPreset.initialLoadSpeed')} value={filamentLoadingSpeedStart} unit="mm/s" />
                      <ViewField label={t('viewPreset.loadSpeed')} value={filamentLoadingSpeed} unit="mm/s" />
                      <div></div>
                      <ViewField label={t('viewPreset.initialUnloadSpeed')} value={filamentUnloadingSpeedStart} unit="mm/s" />
                      <ViewField label={t('viewPreset.unloadSpeed')} value={filamentUnloadingSpeed} unit="mm/s" />
                      <div></div>
                      <ViewField label={t('viewPreset.unloadDelay')} value={filamentToolchangeDelay} unit="s" />
                      <ViewField label={t('viewPreset.coolingMoves')} value={filamentCoolingMoves} />
                      <div></div>
                      <ViewField label={t('viewPreset.firstCoolingMoveSpeed')} value={filamentCoolingInitialSpeed} unit="mm/s" />
                      <ViewField label={t('viewPreset.lastCoolingMoveSpeed')} value={filamentCoolingFinalSpeed} unit="mm/s" />
                      <div></div>
                      <ViewField label={t('viewPreset.stampingLoadSpeed')} value={filamentStampingLoadingSpeed} unit="mm/s" />
                      <ViewField label={t('viewPreset.stampingDistance')} value={filamentStampingDistance} unit="mm" />
                      <div></div>
                    </div>
                  </div>

                  {/* Параметры смены инструмента в многоэкструдерных мультиматериальных принтерах */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">{t('viewPreset.multiExtruderToolchange')}</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewCheckbox label={t('viewPreset.enableMultitoolRamming')} checked={filamentMultitoolRamming} />
                      {filamentMultitoolRamming && (
                        <>
                          <ViewField label={t('viewPreset.multitoolRammingVolume')} value={filamentMultitoolRammingVolume} unit="mm³" />
                          <ViewField label={t('viewPreset.multitoolRammingFlow')} value={filamentMultitoolRammingFlow} unit="mm³/s" />
                        </>
                      )}
                    </div>
                  </div>

                  {/* Дополнительные параметры */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">{t('viewPreset.additionalParams')}</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewField label={t('viewPreset.filamentChangeLength')} value={filamentChangeLength} unit="mm" />
                      <ViewField label={t('viewPreset.pelletFlowCoef')} value={pelletFlowCoefficient} />
                      <div></div>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'compatibility' && (
                <div className="space-y-4">
                  {/* Принтеры */}
                  {preset.printers && preset.printers.length > 0 && (
                    <div>
                      <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">{t('viewPreset.printers')}</h4>
                      <div className="flex flex-wrap gap-2 mt-2">
                        {preset.printers.map((printer) => (
                          <span
                            key={printer.id}
                            className="px-3 py-1.5 bg-white/10 rounded-lg text-sm text-gray-300 border border-white/20"
                            title={`${printer.manufacturer} ${printer.model}`}
                          >
                            {printer.name}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                  
                  {/* Дополнительные параметры совместимости */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">{t('viewPreset.additionalParams')}</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewField label={t('viewPreset.compatiblePrinters')} value={compatiblePrinters} />
                      <ViewField label={t('viewPreset.printersCondition')} value={compatiblePrintersCondition} />
                      <div></div>
                      <ViewField label={t('viewPreset.compatiblePrints')} value={compatiblePrints} />
                      <ViewField label={t('viewPreset.printsCondition')} value={compatiblePrintsCondition} />
                      <div></div>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'notes' && (
                <div className="space-y-4">
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">{t('viewPreset.tabs.notes')}</h4>
                    {filamentNotes && filamentNotes.trim() ? (
                      <pre className="bg-white/5 p-3 rounded-lg text-xs text-gray-300 font-mono whitespace-pre-wrap break-words mt-2">
                        {filamentNotes}
                      </pre>
                    ) : (
                      <p className="text-gray-400 text-xs mt-2">{t('viewPreset.none')}</p>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex justify-end p-6 border-t border-white/10">
          <button
            onClick={onClose}
            className="px-6 py-3 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all"
          >
            {t('viewPreset.close')}
          </button>
        </div>
      </div>
    </div>
  );
};

