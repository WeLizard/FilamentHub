/** Модальное окно для просмотра пресета (только чтение) */

import { useState, useEffect } from 'react';
import { X, CheckCircle2, XCircle } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';
import { presetsAPI, filamentsAPI } from '../api/client';
import type { Preset, Filament } from '../types/api';
import { useHeaderVisible } from '../hooks/useHeaderVisible';

// Вспомогательные компоненты для отображения значений
interface ViewFieldProps {
  label: string;
  value: string | number | null | undefined | '';
  unit?: string;
}

const ViewField: React.FC<ViewFieldProps> = ({ label, value, unit }) => {
  // Показываем все значения, включая 0 (по требованию пользователя)
  if (value === null || value === undefined || value === '') {
    return null;
  }
  
  return (
    <div className="flex flex-col py-1">
      <span className="text-gray-400 text-xs mb-0.5">{label}</span>
      <span className="text-white font-medium text-sm">
        {value}
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
  return (
    <div className="flex flex-col py-1">
      <span className="text-gray-400 text-xs mb-0.5">{label}</span>
      <span className="text-white font-medium text-sm flex items-center space-x-1">
        {checked ? (
          <>
            <CheckCircle2 className="w-4 h-4 text-green-400" />
            <span className="text-green-400">Да</span>
          </>
        ) : (
          <>
            <XCircle className="w-4 h-4 text-red-400" />
            <span className="text-red-400">Нет</span>
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
  const [activeTab, setActiveTab] = useState<'profile' | 'cooling' | 'override' | 'retraction' | 'gcode' | 'extruder_mm' | 'compatibility' | 'notes'>('profile');
  const isHeaderVisible = useHeaderVisible();

  // Загружаем данные филамента
  const { data: editingFilament } = useQuery<Filament>({
    queryKey: ['filament', preset?.filament_id],
    queryFn: () => filamentsAPI.get(preset!.filament_id),
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

  // Функция для правильного склонения "слой/слоя/слоёв"
  const getLayersText = (count: number | null | undefined): string | null => {
    if (count === null || count === undefined) return null;
    const num = Math.floor(count);
    if (num === 1) return '1 слой';
    if (num >= 2 && num <= 4) return `${num} слоя`;
    return `${num} слоёв`;
  };

  // Основные настройки
  const extruderTemp = preset?.extruder_temp || 0;
  const bedTemp = preset?.bed_temp || 0;
  const printSpeed = preset?.print_speed || 0;
  const travelSpeed = preset?.travel_speed || 0;
  const layerHeight = preset?.layer_height || 0;
  const firstLayerHeight = preset?.first_layer_height || null;
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
  const defaultFilamentColour = getStringValue('default_filament_colour');
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

  // Ретракция
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
    <div className={`fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm ${isHeaderVisible ? 'pt-[88px]' : ''}`}>
      <div className="bg-gradient-to-br from-gray-900 via-purple-900/20 to-gray-900 rounded-2xl shadow-2xl border border-white/10 w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-white/10">
          <h2 className="text-2xl font-bold text-white">Просмотр пресета</h2>
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
          <div className="mb-6">
            <h3 className="text-xl font-semibold text-white mb-4">{preset.name}</h3>
            {preset.description && (
              <p className="text-gray-300 mb-4">{preset.description}</p>
            )}
          </div>

          {/* Основные настройки */}
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-white mb-3">Основные настройки</h3>
            
            <div className="bg-white/5 rounded-xl p-3">
              <div className="grid grid-cols-5 gap-x-3 gap-y-2.5">
                <ViewField label="Сопло" value={extruderTemp} unit="°C" />
                <ViewField label="Стол" value={bedTemp} unit="°C" />
                <ViewField label="Печать" value={printSpeed} unit="mm/s" />
                <ViewField label="Перемещение" value={travelSpeed} unit="mm/s" />
                <ViewField label="Обдув" value={fanSpeed} unit="%" />
                
                <ViewField label="Высота слоя" value={layerHeight} unit="mm" />
                <ViewField label="Высота первого слоя" value={firstLayerHeight} unit="mm" />
                <ViewField label="Поток" value={flowRate} unit="%" />
                <ViewField label="Длина ретракта" value={retractionLength} unit="mm" />
                <ViewField label="Скорость ретракта" value={retractionSpeed} unit="mm/s" />
              </div>
            </div>
          </div>

          {/* Подробные настройки */}
          <div className="mt-6">
            <h3 className="text-lg font-semibold text-white mb-4">Подробные настройки</h3>
            
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
                Профиль прутка
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
                Охлаждение
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
                Переопределение параметров
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
                Ретракты
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
                Экструдер ММ
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
                Совместимость
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
                Заметки
              </button>
            </div>

            {/* Содержимое вкладок */}
            <div className="p-4 bg-white/5 rounded-xl border border-white/10">
              {activeTab === 'profile' && (
                <div className="space-y-4">
                  {/* Общая информация */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">Общая информация</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      {editingFilament && (
                        <>
                          <ViewField label="Тип" value={editingFilament.material_type || null} />
                          <ViewField label="Производитель" value={editingFilament.brand_name || null} />
                          <div></div>
                        </>
                      )}
                      <ViewCheckbox label="Растворимый материал" checked={filamentSoluble} />
                      <ViewCheckbox label="Поддержка" checked={filamentIsSupport} />
                      <ViewField label="Ramming length" value={filamentMultitoolRammingVolume} unit="mm" />
                      <ViewField label="Компенсация усадки по XY" value={filamentShrink} />
                      <ViewField label="Компенсация усадки по Z" value={filamentShrinkageCompensationZ} />
                      <ViewField label="Темп. размягчения" value={softeningTemperature} unit="°C" />
                      <ViewField label="Темп. ожидания" value={idleTemperature} unit="°C" />
                      <ViewField label="Категория адгезии" value={filamentAdhesivenessCategory} />
                      <ViewField label="Печатаемость" value={filamentPrintable} />
                      {defaultFilamentColour && (
                        <div className="flex flex-col py-1">
                          <span className="text-gray-400 text-xs mb-0.5">Цвет по умолчанию</span>
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
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">Рекомендуемая температура сопла</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewField label="Мин." value={tempRangeLow} unit="°C" />
                      <ViewField label="Макс." value={tempRangeHigh} unit="°C" />
                      <div></div>
                    </div>
                  </div>

                  {/* Коэффициент потока и Pressure Advance */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">Коэффициент потока и Pressure Advance</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewField label="Коэф. потока модели" value={flowRate !== 100 ? (flowRate / 100).toFixed(2) : '1.00'} />
                      <ViewCheckbox label="Pressure advance" checked={enablePressureAdvance} />
                      {enablePressureAdvance && (
                        <>
                          <ViewField label="Коэф. PA" value={pressureAdvance} />
                          <ViewCheckbox label="Адаптивный PA" checked={adaptivePressureAdvance} />
                          <ViewCheckbox label="PA на нависаниях" checked={adaptivePAOverhangs} />
                          {adaptivePressureAdvance && adaptivePABridges !== null && (
                            <ViewField label="Коэф. PA для мостов" value={adaptivePABridges} />
                          )}
                        </>
                      )}
                    </div>
                    {/* Измеренные значения адаптивного Pressure advance */}
                    {adaptivePressureAdvance && adaptivePAModel && (
                      <div className="mt-3">
                        <h5 className="text-xs font-semibold text-white/60 mb-1">Измеренные значения адаптивного Pressure advance (beta)</h5>
                        <pre className="bg-white/5 p-2 rounded-lg text-xs text-gray-300 font-mono whitespace-pre-wrap break-words">
                          {adaptivePAModel}
                        </pre>
                      </div>
                    )}
                  </div>

                  {/* Температура */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">Температура</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      {/* 1 строка */}
                      <ViewField label="Сопло 1-й слой" value={nozzleTempInitialLayer} unit="°C" />
                      <ViewField label="Стол 1-й слой" value={bedTemp} unit="°C" />
                      <ViewCheckbox label="Контроль камеры" checked={enableChamberControl} />
                      {/* 2 строка */}
                      <ViewField label="Сопло слои" value={extruderTemp} unit="°C" />
                      <ViewField label="Стол слои" value={bedTemp} unit="°C" />
                      {enableChamberControl ? (
                        <ViewField label="Темп. камеры" value={chamberTemp} unit="°C" />
                      ) : (
                        <div></div>
                      )}
                    </div>
                  </div>

                  {/* Ограничение объёмного расхода */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">Ограничение объёмного расхода</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewCheckbox label="Адаптивное ограничение" checked={adaptiveVolumetricSpeed} />
                      <ViewField label="Объёмный расход" value={volumetricSpeed} unit="mm³/s" />
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
                        <span className="text-gray-400 text-xs mb-0.5">Не включать вентилятор первые</span>
                        <span className="text-white font-medium text-sm">
                          {getLayersText(closeFanFirstXLayers)}
                        </span>
                      </div>
                    )}
                    <ViewField label="Слой полной скорости" value={fullFanSpeedLayer} />
                    <ViewField label="Время охлаждения слоя" value={fanCoolingLayerTime} unit="s" />
                    <ViewField label="Время макс. скорости" value={fanMaxSpeedLayerTime} unit="s" />
                    <ViewField label="Мин. скорость вентилятора" value={fanMinSpeed} unit="%" />
                    <ViewField label="Макс. скорость вентилятора" value={fanMaxSpeed} unit="%" />
                    <ViewCheckbox label="Вентилятор всегда включён" checked={reduceFanStopStartFreq} />
                    <ViewCheckbox label="Замедлять для охлаждения" checked={slowDownForLayerCooling} />
                    <ViewCheckbox label="Не замедлять периметр" checked={dontSlowDownOuterWall} />
                    {slowDownForLayerCooling && (
                      <ViewField label="Мин. скорость печати" value={slowDownMinSpeed} unit="mm/s" />
                    )}
                    <ViewCheckbox label="Обдув нависаний и мостов" checked={enableOverhangBridgeFan} />
                    {enableOverhangBridgeFan && (
                      <>
                        <ViewField label="Вент. нависаний" value={overhangFanSpeed} unit="%" />
                        <ViewField label="Порог нависаний" value={overhangFanThreshold} />
                        {internalBridgeFanSpeed !== null && internalBridgeFanSpeed !== -1 && (
                          <ViewField label="Вент. внутренних мостов" value={internalBridgeFanSpeed} unit="%" />
                        )}
                        {internalBridgeFanSpeed === -1 && (
                          <div className="flex flex-col py-1">
                            <span className="text-gray-400 text-xs mb-0.5">Вент. внутренних мостов</span>
                            <span className="text-white font-medium text-sm">По умолчанию</span>
                          </div>
                        )}
                        <ViewField label="Вент. при глажке" value={ironingFanSpeed} unit="%" />
                        <ViewField label="Вент. интерфейса поддержки" value={supportMaterialInterfaceFanSpeed} unit="%" />
                        <ViewField label="Доп. скорость вентилятора" value={additionalCoolingFanSpeed} unit="%" />
                      </>
                    )}
                    <ViewCheckbox label="Вытяжной вентилятор" checked={enableExhaustFan} />
                    {enableExhaustFan && (
                      <>
                        <ViewField label="Вент. во время печати" value={duringPrintExhaustFanSpeed} unit="%" />
                        <ViewField label="Вент. после печати" value={completePrintExhaustFanSpeed} unit="%" />
                        <ViewCheckbox label="Фильтрация воздуха" checked={activateAirFiltration} />
                      </>
                    )}
                  </div>
                </div>
              )}

              {activeTab === 'override' && (
                <div className="space-y-4">
                  {/* Скорости и замедления */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">Скорости и замедления</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewCheckbox label="Замедлять для охлаждения" checked={slowDownForLayerCooling} />
                      <ViewCheckbox label="Не замедлять периметр" checked={dontSlowDownOuterWall} />
                      {slowDownForLayerCooling && (
                        <ViewField label="Мин. скорость печати" value={slowDownMinSpeed} unit="mm/s" />
                      )}
                    </div>
                  </div>

                  {/* Откат */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">Откат</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewField label="Длина" value={retractionLength} unit="mm" />
                      <ViewField label="Скорость извлечения" value={retractionSpeed} unit="mm/s" />
                      <ViewField label="Высота поднятия Z" value={filamentZHop} unit="mm" />
                      <ViewField label="Скорость заправки" value={deretractionSpeed} unit="mm/s" />
                      <ViewField label="Тип подъёма Z" value={filamentZHopTypes || null} />
                      <ViewField label="На поверхностях" value={retractLiftEnforce || null} />
                      <ViewField label="Поднимать Z выше" value={retractLiftAbove} unit="mm" />
                      <ViewField label="Поднимать Z ниже" value={retractLiftBelow} unit="mm" />
                      <ViewField label="Доп. длина подачи" value={retractRestartExtra} unit="mm" />
                      <ViewField label="Порог перемещения" value={retractionMinimumTravel} unit="mm" />
                      <ViewCheckbox label="Откат при смене слоя" checked={retractWhenChangingLayer} />
                      <ViewCheckbox label="Очистка сопла" checked={filamentWipe} />
                      {filamentWipe && (
                        <>
                          <ViewField label="Расстояние очистки" value={filamentWipeDistance} unit="mm" />
                          <ViewField label="Откат перед очисткой" value={retractBeforeWipe} />
                          <div></div>
                        </>
                      )}
                    </div>
                  </div>

                </div>
              )}

              {activeTab === 'retraction' && (
                <div className="space-y-4">
                  {/* Основные параметры ретракции */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">Основные параметры</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewField label="Длина" value={retractionLength} unit="mm" />
                      <ViewField label="Скорость извлечения" value={retractionSpeed} unit="mm/s" />
                      <ViewField label="Высота поднятия Z" value={filamentZHop} unit="mm" />
                      <ViewField label="Скорость заправки" value={deretractionSpeed} unit="mm/s" />
                      <ViewField label="Тип подъёма Z" value={filamentZHopTypes || null} />
                      <ViewField label="На поверхностях" value={retractLiftEnforce || null} />
                      <ViewField label="Поднимать Z выше" value={retractLiftAbove} unit="mm" />
                      <ViewField label="Поднимать Z ниже" value={retractLiftBelow} unit="mm" />
                      <ViewField label="Доп. длина подачи" value={retractRestartExtra} unit="mm" />
                      <ViewField label="Порог перемещения" value={retractionMinimumTravel} unit="mm" />
                      <ViewCheckbox label="Откат при смене слоя" checked={retractWhenChangingLayer} />
                      <ViewCheckbox label="Очистка сопла" checked={filamentWipe} />
                      {filamentWipe && (
                        <>
                          <ViewField label="Расстояние очистки" value={filamentWipeDistance} unit="mm" />
                          <ViewField label="Откат перед очисткой" value={retractBeforeWipe} />
                          <ViewField label="Темп. промывки" value={filamentFlushTemp} unit="°C" />
                          <ViewField label="Объёмный расход промывки" value={filamentFlushVolumetricSpeed} unit="mm³/s" />
                          <div></div>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Дополнительные параметры ретракции */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">Дополнительные параметры ретракции</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewField label="Ретракция при обрезке" value={retractionDistancesWhenCut} />
                      <ViewField label="Длинные ретракции при обрезке" value={longRetractionsWhenCut} />
                      <div></div>
                      <ViewCheckbox label="Длинный ретракт при смене экстр." checked={longRetractionsWhenEC} />
                      {longRetractionsWhenEC && (
                        <>
                          <ViewField label="Расстояния ретракции при смене экструдера" value={retractionDistancesWhenEC} unit="mm" />
                          <div></div>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Мультиматериал (многоэкструдерные принтеры) */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">Мультиматериал (многоэкструдерные принтеры)</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewCheckbox label="Рэмминг мультитул" checked={filamentMultitoolRamming} />
                      {filamentMultitoolRamming && (
                        <>
                          <ViewField label="Объём рэмминга" value={filamentMultitoolRammingVolume} unit="mm³" />
                          <ViewField label="Поток рэмминга" value={filamentMultitoolRammingFlow} unit="mm³/s" />
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
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">Стартовый G-код прутка</h4>
                    {filamentStartGcode ? (
                      <pre className="bg-white/5 p-2 rounded-lg text-xs text-gray-300 font-mono whitespace-pre-wrap break-words mt-2">
                        {filamentStartGcode}
                      </pre>
                    ) : (
                      <p className="text-gray-400 text-xs mt-2">нет</p>
                    )}
                  </div>
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">Завершающий G-код прутка</h4>
                    {filamentEndGcode ? (
                      <pre className="bg-white/5 p-2 rounded-lg text-xs text-gray-300 font-mono whitespace-pre-wrap break-words mt-2">
                        {filamentEndGcode}
                      </pre>
                    ) : (
                      <p className="text-gray-400 text-xs mt-2">нет</p>
                    )}
                  </div>
                </div>
              )}

              {activeTab === 'extruder_mm' && (
                <div className="space-y-4">
                  {/* Параметры экструдера */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">Параметры экструдера</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewField label="Вариант экструдера" value={filamentExtruderVariant} />
                      <ViewField label="Требуемая твердость сопла HRC" value={requiredNozzleHRC} unit="HRC" />
                      <div></div>
                    </div>
                  </div>

                  {/* Параметры черновой башни */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">Параметры черновой башни</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewField label="Мин. объём сброса на черновой башне" value={filamentMinimalPurgeOnWipeTower} unit="mm³" />
                      <div></div>
                      <div></div>
                    </div>
                  </div>

                  {/* Параметры смены инструмента в одноэкструдерных мультиматериальных принтерах */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">Параметры смены инструмента в одноэкструдерных мультиматериальных принтерах</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewField label="Начальная скорость загрузки" value={filamentLoadingSpeedStart} unit="mm/s" />
                      <ViewField label="Скорость загрузки" value={filamentLoadingSpeed} unit="mm/s" />
                      <div></div>
                      <ViewField label="Начальная скорость выгрузки" value={filamentUnloadingSpeedStart} unit="mm/s" />
                      <ViewField label="Скорость выгрузки" value={filamentUnloadingSpeed} unit="mm/s" />
                      <div></div>
                      <ViewField label="Задержка после выгрузки" value={filamentToolchangeDelay} unit="s" />
                      <ViewField label="Количество охлаждающих движений" value={filamentCoolingMoves} />
                      <div></div>
                      <ViewField label="Скорость первого охлаждающего движения" value={filamentCoolingInitialSpeed} unit="mm/s" />
                      <ViewField label="Скорость последнего охлаждающего движения" value={filamentCoolingFinalSpeed} unit="mm/s" />
                      <div></div>
                      <ViewField label="Скорость загрузки при утрамбовке" value={filamentStampingLoadingSpeed} unit="mm/s" />
                      <ViewField label="Расстояние утрамбовки" value={filamentStampingDistance} unit="mm" />
                      <div></div>
                    </div>
                  </div>

                  {/* Параметры смены инструмента в многоэкструдерных мультиматериальных принтерах */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">Параметры смены инструмента в многоэкструдерных мультиматериальных принтерах</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewCheckbox label="Включить рэмминг для многоинструментального принтера" checked={filamentMultitoolRamming} />
                      {filamentMultitoolRamming && (
                        <>
                          <ViewField label="Объём рэмминга многоинструментального принтера" value={filamentMultitoolRammingVolume} unit="mm³" />
                          <ViewField label="Поток рэмминга многоинструментального принтера" value={filamentMultitoolRammingFlow} unit="mm³/s" />
                        </>
                      )}
                    </div>
                  </div>

                  {/* Дополнительные параметры */}
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">Дополнительные параметры</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewField label="Длина смены филамента" value={filamentChangeLength} unit="mm" />
                      <ViewField label="Коэффициент потока пеллет" value={pelletFlowCoefficient} />
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
                      <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">Принтеры</h4>
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
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">Дополнительные параметры</h4>
                    <div className="grid grid-cols-3 gap-x-3 gap-y-2 mt-2">
                      <ViewField label="Совместимые принтеры" value={compatiblePrinters} />
                      <ViewField label="Условие принтеров" value={compatiblePrintersCondition} />
                      <div></div>
                      <ViewField label="Совместимые печати" value={compatiblePrints} />
                      <ViewField label="Условие печатей" value={compatiblePrintsCondition} />
                      <div></div>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'notes' && (
                <div className="space-y-4">
                  <div>
                    <h4 className="text-xs font-semibold text-white/70 mb-2 pb-1 border-b border-white/10">Заметки</h4>
                    {filamentNotes && filamentNotes.trim() ? (
                      <pre className="bg-white/5 p-3 rounded-lg text-xs text-gray-300 font-mono whitespace-pre-wrap break-words mt-2">
                        {filamentNotes}
                      </pre>
                    ) : (
                      <p className="text-gray-400 text-xs mt-2">нет</p>
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
            Закрыть
          </button>
        </div>
      </div>
    </div>
  );
};


