/** Модальное окно для создания/редактирования пресета */

import { useState, useEffect, FormEvent, useRef, useMemo } from 'react';
import React from 'react';
import { useTranslation } from 'react-i18next';
import { X, Save, Loader2, Check, Plus, CheckCircle } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { presetsAPI, filamentsAPI, brandsAPI, printersAPI } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { useAuth } from '../contexts/AuthContext';
import type { Preset, Filament, Brand, Printer } from '../types/api';
import { applyMaterialDefaults, sortMaterialTypes } from '../data/materialDefaults';
import { EditGCodeModal } from './EditGCodeModal';
import { CustomSelect } from './CustomSelect';
import type { FilamentVisualSettings } from '../types/api';
import { Dropdown } from './Dropdown';
import { useClickOutside } from '../hooks/useClickOutside';
import { ModalOverlay } from './ModalOverlay';
import { useDebounce } from '../hooks/useDebounce';
import { ColorMaterialSection } from './ColorMaterialSection';
import { HSLColorPicker } from './HSLColorPicker';

import { FilamentSummaryCard } from './FilamentSummaryCard';
import type { AxiosError } from 'axios';

// Список стандартных типов материалов (FDM/FFF)
const MATERIAL_TYPES = [
  'PLA',
  'ABS',
  'PETG',
  'TPU',
  'ASA',
  'PC',
  'PA', // Nylon
  'PA-CF', // Nylon с углеволокном
  'PLA-CF', // PLA с углеволокном
  'PEEK',
  'HIPS',
  'PP',
  'PVA',
  'PLA+',
  'PETG+',
  'ABS+',
];

interface CreatePresetModalProps {
  isOpen: boolean;
  onClose: () => void;
  preset?: Preset | null; // Если передан, то редактирование, иначе создание
  filamentId?: number; // ID материала (если создание нового пресета)
  brandId?: number; // ID бренда (если создание из профиля бренда - автоматически is_official=true)
}

interface DuplicateFilamentSuggestion {
  id: number;
  name: string;
  brandName?: string;
  materialType?: string;
  colorName?: string;
  colorHex?: string;
}

const normalizeColorName = (value?: string | null): string => (value || '').trim().toLowerCase();
const normalizeColorHex = (value?: string | null): string => (value || '').trim().toLowerCase();

const sameColorIdentity = (
  existingColorName?: string | null,
  existingColorHex?: string | null,
  incomingColorName?: string | null,
  incomingColorHex?: string | null,
): boolean => {
  // Совпадение цвета определяем по текстовому имени.
  // HEX учитываем только если имени цвета нет с обеих сторон.
  const existingName = normalizeColorName(existingColorName);
  const incomingName = normalizeColorName(incomingColorName);
  if (existingName || incomingName) {
    return existingName === incomingName;
  }

  const existingHex = normalizeColorHex(existingColorHex);
  const incomingHex = normalizeColorHex(incomingColorHex);
  if (existingHex || incomingHex) {
    return existingHex === incomingHex;
  }

  return true;
};

const colorIdentityKey = (colorName?: string | null, colorHex?: string | null): string => {
  const normalizedName = normalizeColorName(colorName);
  if (normalizedName) {
    return `name:${normalizedName}`;
  }

  const normalizedHex = normalizeColorHex(colorHex);
  if (normalizedHex) {
    return `hex:${normalizedHex}`;
  }

  return 'none';
};

export const CreatePresetModal: React.FC<CreatePresetModalProps> = ({
  isOpen,
  onClose,
  preset,
  filamentId,
  brandId,
}) => {
  const { user } = useAuth();
  const { t } = useTranslation();

  // Определяем, является ли пресет черновиком (заготовкой)
  // Черновик = пресет без привязки к филаменту ИЛИ неактивный пресет без @fh в имени
  const isDraft = Boolean(
    preset && (!preset.filament_id || (!preset.active && !preset.name?.includes('@fh')))
  );
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [isOfficial, setIsOfficial] = useState(false);
  const [extruderTemp, setExtruderTemp] = useState(200);
  const [bedTemp, setBedTemp] = useState(60);
  const [printSpeed, setPrintSpeed] = useState(50);
  const [travelSpeed, setTravelSpeed] = useState(150);
  const [flowRate, setFlowRate] = useState(100);
  const [fanSpeed, setFanSpeed] = useState(100);
  const [retractionLength, setRetractionLength] = useState(5.0);
  const [retractionSpeed, setRetractionSpeed] = useState(45.0);
  
  // Расширенные параметры OrcaSlicer (UI-friendly)
  // Вкладка "Профиль прутка"
  const [tempRangeLow, setTempRangeLow] = useState<number | ''>('');
  const [tempRangeHigh, setTempRangeHigh] = useState<number | ''>('');
  const [nozzleTempInitialLayer, setNozzleTempInitialLayer] = useState<number | ''>('');
  const [bedTempInitialLayer, setBedTempInitialLayer] = useState<number | ''>('');
  const [idleTemperature, setIdleTemperature] = useState<number | ''>(''); // Температура ожидания
  const [softeningTemperature, setSofteningTemperature] = useState<number | ''>(''); // Температура размягчения
  const [volumetricSpeed, setVolumetricSpeed] = useState<number | ''>('');
  const [adaptiveVolumetricSpeed, setAdaptiveVolumetricSpeed] = useState(false);
  const [volumetricSpeedCoefficients, setVolumetricSpeedCoefficients] = useState('');
  const [filamentShrink, setFilamentShrink] = useState('');
  const [filamentShrinkageCompensationZ, setFilamentShrinkageCompensationZ] = useState('');
  const [defaultFilamentColour, setDefaultFilamentColour] = useState('');
  // filamentAdhesivenessCategory и filamentPrintable - НЕ нужны для агрегации (не указаны производителями)
  // Но нужны для импорта из OrcaSlicer - оставляем сеттеры для загрузки данных
  const [filamentAdhesivenessCategory, setFilamentAdhesivenessCategory] = useState<number | ''>('');
  const [filamentIsSupport, setFilamentIsSupport] = useState(false);
  const [filamentSoluble, setFilamentSoluble] = useState(false);
  const [filamentPrintable, setFilamentPrintable] = useState<number | ''>('');
  const [deretractionSpeed, setDeretractionSpeed] = useState<number | ''>('');
  const [retractionMinimumTravel, setRetractionMinimumTravel] = useState<number | ''>('');
  const [retractBeforeWipe, setRetractBeforeWipe] = useState('');
  const [retractWhenChangingLayer, setRetractWhenChangingLayer] = useState(false);
  const [retractRestartExtra, setRetractRestartExtra] = useState<number | ''>('');
  const [filamentZHop, setFilamentZHop] = useState<number | ''>('');
  const [filamentZHopTypes, setFilamentZHopTypes] = useState('');
  const [retractLiftAbove, setRetractLiftAbove] = useState<number | ''>('');
  const [retractLiftBelow, setRetractLiftBelow] = useState<number | ''>('');
  const [retractLiftEnforce, setRetractLiftEnforce] = useState('');
  const [filamentWipe, setFilamentWipe] = useState(false);
  const [filamentWipeDistance, setFilamentWipeDistance] = useState<number | ''>('');
  // filamentFlushTemp и filamentFlushVolumetricSpeed - НЕ нужны для агрегации (для Wipe, специфично для пользователей)
  // Но нужны для импорта из OrcaSlicer - оставляем сеттеры для загрузки данных
  const [filamentFlushTemp, setFilamentFlushTemp] = useState<number | ''>('');
  const [filamentFlushVolumetricSpeed, setFilamentFlushVolumetricSpeed] = useState<number | ''>('');
  const [pressureAdvance, setPressureAdvance] = useState<number | ''>('');
  const [enablePressureAdvance, setEnablePressureAdvance] = useState(false);
  const [adaptivePressureAdvance, setAdaptivePressureAdvance] = useState(false);
  const [adaptivePABridges, setAdaptivePABridges] = useState<number | ''>('');
  const [adaptivePAOverhangs, setAdaptivePAOverhangs] = useState(false);
  const [chamberTemp, setChamberTemp] = useState<number | ''>('');
  const [enableChamberControl, setEnableChamberControl] = useState(false);
  
  // Вкладка "Охлаждение"
  const [fanMinSpeed, setFanMinSpeed] = useState<number | ''>('');
  const [fanMaxSpeed, setFanMaxSpeed] = useState<number | ''>('');
  const [fanCoolingLayerTime, setFanCoolingLayerTime] = useState<number | ''>(''); // Время слоя для мин. скорости
  const [fanMaxSpeedLayerTime, setFanMaxSpeedLayerTime] = useState<number | ''>(''); // Время слоя для макс. скорости
  // fanAlwaysOn удален - теперь используется reduceFanStopStartFreq (это и есть "Keep fan always on" в OrcaSlicer)
  const [overhangFanSpeed, setOverhangFanSpeed] = useState<number | ''>('');
  const [overhangFanThreshold, setOverhangFanThreshold] = useState('');
  const [closeFanFirstXLayers, setCloseFanFirstXLayers] = useState<number | ''>('');
  const [fullFanSpeedLayer, setFullFanSpeedLayer] = useState<number | ''>('');
  const [reduceFanStopStartFreq, setReduceFanStopStartFreq] = useState(false);
  const [additionalCoolingFanSpeed, setAdditionalCoolingFanSpeed] = useState<number | ''>('');
  const [enableOverhangBridgeFan, setEnableOverhangBridgeFan] = useState(false);
  const [internalBridgeFanSpeed, setInternalBridgeFanSpeed] = useState<number | ''>('');
  const [ironingFanSpeed, setIroningFanSpeed] = useState<number | ''>('');
  const [supportMaterialInterfaceFanSpeed, setSupportMaterialInterfaceFanSpeed] = useState<number | ''>('');
  const [enableExhaustFan, setEnableExhaustFan] = useState(false); // Вкл. вытяжной вентилятор
  const [completePrintExhaustFanSpeed, setCompletePrintExhaustFanSpeed] = useState<number | ''>('');
  const [duringPrintExhaustFanSpeed, setDuringPrintExhaustFanSpeed] = useState<number | ''>('');
  const [activateAirFiltration, setActivateAirFiltration] = useState(false);
  
  // Вкладка "Переопределение параметров"
  const [slowDownForLayerCooling, setSlowDownForLayerCooling] = useState(false);
  // slowDownLayerTime - дубликат fanMaxSpeedLayerTime, используем только fanMaxSpeedLayerTime
  const [slowDownMinSpeed, setSlowDownMinSpeed] = useState<number | ''>('');
  const [dontSlowDownOuterWall, setDontSlowDownOuterWall] = useState(false);
  const [retractionDistancesWhenCut, setRetractionDistancesWhenCut] = useState('');
  const [longRetractionsWhenCut, setLongRetractionsWhenCut] = useState('');
  const [longRetractionsWhenEC, setLongRetractionsWhenEC] = useState(false);
  const [retractionDistancesWhenEC, setRetractionDistancesWhenEC] = useState<number | ''>('');
  
  // Вкладка "Дополнительно"
  const [filamentStartGcode, setFilamentStartGcode] = useState(''); // Стартовый G-код прутка
  const [filamentEndGcode, setFilamentEndGcode] = useState(''); // Завершающий G-код прутка
  const [filamentMultitoolRamming, setFilamentMultitoolRamming] = useState(false);
  const [filamentMultitoolRammingFlow, setFilamentMultitoolRammingFlow] = useState<number | ''>('');
  const [filamentMultitoolRammingVolume, setFilamentMultitoolRammingVolume] = useState<number | ''>('');
  // filamentRammingParameters - сложный параметр, не для агрегации, не переносим в UI
  const [filamentToolchangeDelay, setFilamentToolchangeDelay] = useState<number | ''>('');
  const [filamentLoadingSpeed, setFilamentLoadingSpeed] = useState<number | ''>('');
  const [filamentLoadingSpeedStart, setFilamentLoadingSpeedStart] = useState<number | ''>('');
  const [filamentUnloadingSpeed, setFilamentUnloadingSpeed] = useState<number | ''>('');
  const [filamentUnloadingSpeedStart, setFilamentUnloadingSpeedStart] = useState<number | ''>('');
  const [filamentChangeLength, setFilamentChangeLength] = useState<number | ''>('');
  const [filamentCoolingInitialSpeed, setFilamentCoolingInitialSpeed] = useState<number | ''>('');
  const [filamentCoolingFinalSpeed, setFilamentCoolingFinalSpeed] = useState<number | ''>('');
  const [filamentCoolingMoves, setFilamentCoolingMoves] = useState<number | ''>('');
  const [filamentStampingDistance, setFilamentStampingDistance] = useState<number | ''>('');
  const [filamentStampingLoadingSpeed, setFilamentStampingLoadingSpeed] = useState<number | ''>('');
  const [filamentMinimalPurgeOnWipeTower, setFilamentMinimalPurgeOnWipeTower] = useState<number | ''>('');
  const [pelletFlowCoefficient, setPelletFlowCoefficient] = useState<number | ''>('');
  
  // Вкладка "Экструдер мм"
  const [filamentExtruderVariant, setFilamentExtruderVariant] = useState('');
  const [requiredNozzleHRC, setRequiredNozzleHRC] = useState<number | ''>('');
  
  // Вкладка "Зависимости" - НЕ нужна для агрегации (не используется для расчета средних значений)
  // Но нужны для импорта из OrcaSlicer - оставляем сеттеры для загрузки данных
  const [compatiblePrinters, setCompatiblePrinters] = useState('');
  const [compatiblePrintersCondition, setCompatiblePrintersCondition] = useState('');
  const [compatiblePrints, setCompatiblePrints] = useState('');
  const [compatiblePrintsCondition, setCompatiblePrintsCondition] = useState('');
  
  // Вкладка "Заметки"
  const [filamentNotes, setFilamentNotes] = useState('');
  const [activeTab, setActiveTab] = useState<'profile' | 'cooling' | 'override' | 'advanced' | 'extruder' | 'notes'>('profile'); // Активная вкладка (как в OrcaSlicer)
  const [error, setError] = useState<string | null>(null);
  const [duplicateFilamentSuggestion, setDuplicateFilamentSuggestion] = useState<DuplicateFilamentSuggestion | null>(null);
  const [selectedFilamentId, setSelectedFilamentId] = useState<number | null>(filamentId || null);
  
  // Новые поля для создания нового филамента
  const [materialType, setMaterialType] = useState('');
  const [customMaterialType, setCustomMaterialType] = useState(''); // Пользовательский тип материала
  const [useCustomMaterial, setUseCustomMaterial] = useState(false); // Использовать ли пользовательский материал
  const [brandSearch, setBrandSearch] = useState('');
  const [selectedBrandId, setSelectedBrandId] = useState<number | null>(null);
  const [filamentName, setFilamentName] = useState('');
  const [filamentColorName, setFilamentColorName] = useState('');
  const [filamentColorHex, setFilamentColorHex] = useState('#FF0000');
  // Расширенные характеристики цвета для нового филамента
  const [filamentVisualColorType, setFilamentVisualColorType] = useState<'single' | 'two' | 'three' | 'gradient' | 'transition' | 'thermochromic'>('single');
  const [filamentVisualColors, setFilamentVisualColors] = useState<string[]>(['#FF0000']);
  const [filamentVisualFinish, setFilamentVisualFinish] = useState<'matte' | 'glossy'>('matte');
  const [filamentVisualFiller, setFilamentVisualFiller] = useState<'none' | 'wood' | 'carbon' | 'glitter' | 'metallic' | 'luminescent' | 'fibers' | 'stone' | 'glass' | 'pattern1' | 'pattern2' | 'pattern3' | 'pattern4' | 'pattern5' | 'pattern6' | 'pattern7' | 'pattern8' | 'pattern9' | 'pattern10' | 'pattern11' | 'pattern12'>('none');
  const [filamentVisualTransparency, setFilamentVisualTransparency] = useState(false);
  const [showFilamentAdvancedVisual, setShowFilamentAdvancedVisual] = useState(false);
  // Состояния для открытия/закрытия HSL пикеров для каждого цвета в расширенных настройках
  const [openColorPickers, setOpenColorPickers] = useState<boolean[]>([]);
  const [filamentDiameter, setFilamentDiameter] = useState('1.75');
  const [filamentDensity, setFilamentDensity] = useState<number | ''>('');
  const [canEditDensity, setCanEditDensity] = useState(false); // Можно ли редактировать плотность (только для неизвестных типов)
  const [filamentPricePerKg, setFilamentPricePerKg] = useState<number | ''>('');
  const [filamentSpoolWeight, setFilamentSpoolWeight] = useState<number | ''>('');
  const [filamentDescription, setFilamentDescription] = useState('');
  const [showFilamentForm, setShowFilamentForm] = useState(false); // true = создать новый, false = выбрать существующий
  const [filamentSearch, setFilamentSearch] = useState(''); // Поиск существующего филамента
  const [showFilamentDropdown, setShowFilamentDropdown] = useState(false); // Показывать выпадающий список
  const [selectedFilament, setSelectedFilament] = useState<Filament | null>(null); // Выбранный филамент для отображения
  const [showBrandDropdown, setShowBrandDropdown] = useState(false); // Показывать выпадающий список брендов
  const [showMaterialTypeDropdown, setShowMaterialTypeDropdown] = useState(false); // Показывать выпадающий список типов
  const [selectedPrinterIds, setSelectedPrinterIds] = useState<number[]>([]); // Выбранные принтеры
  const [printersCache, setPrintersCache] = useState<Record<number, Printer>>({});
  const [printerSearch, setPrinterSearch] = useState('');
  const debouncedPrinterSearch = useDebounce(printerSearch, 250);
  
  // Маппинг плотности по типам материалов (г/см³)
  const MATERIAL_DENSITY_MAP: Record<string, number> = {
    'PLA': 1.24,
    'ABS': 1.04,
    'PETG': 1.27,
    'TPU': 1.20,
    'ASA': 1.05,
    'PC': 1.20,
    'PA': 1.14,
    'PVA': 1.23,
    'HIPS': 1.04,
    'PP': 0.90,
    'PEEK': 1.32,
    'PEI': 1.27,
    'PLA+': 1.24,
    'PETG+': 1.27,
    'PLA-CF': 1.30,
    'PA-CF': 1.18,
    'ABS-CF': 1.10,
    'PETG-CF': 1.32,
    'ASA-CF': 1.10,
  };
  
  // Опции диаметра
  const DIAMETER_OPTIONS = ['1.75', '2.85', '3.00'];
  
  // Для создания нового бренда
  const [showBrandForm, setShowBrandForm] = useState(false); // true = создать новый бренд
  const [newBrandName, setNewBrandName] = useState(''); // Название нового бренда
  const [newBrandWebsite, setNewBrandWebsite] = useState(''); // Сайт нового бренда
  
  const filamentDropdownRef = useRef<HTMLDivElement>(null);
  const brandDropdownRef = useRef<HTMLDivElement>(null);
  const materialTypeDropdownRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();
  
  // Определяем, может ли пользователь создавать официальные пресеты
  const canCreateOfficial = user?.role === 'brand'; // TODO: добавить проверку verified бренда
  const shouldLoadFilamentsForSelection = Boolean(
    isOpen && (!preset || isDraft) && !filamentId && !showFilamentForm
  );

  // Загружаем филамент для редактирования
  const { data: editingFilament } = useQuery({
    queryKey: ['filament', preset?.filament_id],
    queryFn: () => filamentsAPI.get(preset!.filament_id!),
    enabled: isOpen && !!preset?.filament_id, // Загружаем только при редактировании
  });

  // Загружаем материалы для выбора (если не передан filamentId И не создаем новый)
  const { data: filamentsData, error: filamentsError } = useQuery({
    queryKey: ['filaments', 'for-preset', { search: filamentSearch, brandId }],
    queryFn: () => filamentsAPI.list({ 
      active_only: true, 
      page: 1, 
      size: 100, 
      search: filamentSearch || undefined,
      brand_id: brandId || undefined, // Фильтруем по бренду если передан brandId
    }),
    enabled: shouldLoadFilamentsForSelection,
  });

  // Загружаем информацию о бренде если передан brandId
  const { data: currentBrandData } = useQuery({
    queryKey: ['brand', brandId],
    queryFn: () => brandsAPI.get(brandId!),
    enabled: isOpen && !!brandId && showFilamentForm, // Загружаем только если создаем новый материал и передан brandId
  });

  // Загружаем бренды для поиска/выбора (только если НЕ передан brandId)
  const { data: brandsData } = useQuery({
    queryKey: ['brands', { search: brandSearch }],
    queryFn: () => brandsAPI.list({ active_only: true, page: 1, size: 20, search: brandSearch || undefined }),
    enabled: isOpen && showFilamentForm && !brandId, // Загружаем только если создаем новый филамент И НЕ передан brandId
  });

  // Загружаем материалы выбранного бренда для подсказок
  const { data: similarFilamentsData } = useQuery({
    queryKey: ['filaments', 'similar', { brand_id: selectedBrandId, search: filamentName }],
    queryFn: () => filamentsAPI.list({ 
      active_only: true, 
      brand_id: selectedBrandId || undefined,
      search: filamentName || undefined,
      page: 1, 
      size: 10 
    }),
    enabled: isOpen && showFilamentForm && !!selectedBrandId && filamentName.length > 0,
  });

  const uniqueSimilarFilaments = useMemo(() => {
    const items = similarFilamentsData?.items ?? [];
    const seen = new Set<string>();
    const uniqueItems: Filament[] = [];

    for (const filament of items) {
      const key = [
        filament.brand_id,
        filament.name.trim().toLowerCase(),
        filament.material_type.trim().toLowerCase(),
        colorIdentityKey(filament.color_name, filament.color_hex),
      ].join('|');

      if (seen.has(key)) {
        continue;
      }

      seen.add(key);
      uniqueItems.push(filament);
    }

    return uniqueItems;
  }, [similarFilamentsData?.items]);

  // Загружаем уникальные типы материалов из БД (для формы создания нового материала)
  const { data: materialTypes = [] } = useQuery({
    queryKey: ['filaments', 'material-types'],
    queryFn: () => filamentsAPI.getMaterialTypes(),
    enabled: isOpen && showFilamentForm, // Загружаем только если создаем новый материал
  });

  // Базовые типы вперёд, подробные варианты — следом (ничего не удаляя)
  const sortedMaterialTypes = useMemo(() => sortMaterialTypes(materialTypes), [materialTypes]);

  // Загружаем принтеры для выбора
  const { data: printersData } = useQuery({
    queryKey: ['printers', 'for-preset', { search: debouncedPrinterSearch }],
    queryFn: () => printersAPI.list({
      active_only: true,
      page: 1,
      size: 20,
      search: debouncedPrinterSearch || undefined,
    }),
    enabled: isOpen,
  });

  useEffect(() => {
    if (printersData?.items) {
      setPrintersCache((prev) => {
        const next = { ...prev };
        printersData.items.forEach((printer) => {
          next[printer.id] = printer;
        });
        return next;
      });
    }
  }, [printersData]);

  // Закрываем выпадающий список при клике вне его
  // Универсальные хуки для закрытия выпадающих списков при клике вне
  useClickOutside({
    ref: filamentDropdownRef,
    isOpen: showFilamentDropdown,
    onClose: () => setShowFilamentDropdown(false),
  });
  useClickOutside({
    ref: brandDropdownRef,
    isOpen: showBrandDropdown,
    onClose: () => setShowBrandDropdown(false),
  });
  useClickOutside({
    ref: materialTypeDropdownRef,
    isOpen: showMaterialTypeDropdown,
    onClose: () => setShowMaterialTypeDropdown(false),
  });

  // Инициализация формы при редактировании
  useEffect(() => {
    if (!isOpen) return; // Не выполняем инициализацию если модалка закрыта
    
    if (preset) {
      setName(preset.name);
      setDescription(preset.description || '');
      setIsOfficial(preset.is_official);
      setExtruderTemp(preset.extruder_temp);
      setBedTemp(preset.bed_temp);
      setPrintSpeed(preset.print_speed);
      setTravelSpeed(preset.travel_speed || 150);
      setFlowRate(preset.flow_rate || 100);
      setFanSpeed(preset.fan_speed || 100);
      setRetractionLength(preset.retraction_length || 5.0);
      setRetractionSpeed(preset.retraction_speed || 45.0);
      
      // Загружаем расширенные параметры из JSON
      if (preset.orcaslicer_settings) {
        const settings = preset.orcaslicer_settings;
        setTempRangeLow(settings.nozzle_temperature_range_low?.[0] ? Number(settings.nozzle_temperature_range_low[0]) : '');
        setTempRangeHigh(settings.nozzle_temperature_range_high?.[0] ? Number(settings.nozzle_temperature_range_high[0]) : '');
        setVolumetricSpeed(settings.filament_max_volumetric_speed?.[0] ? Number(settings.filament_max_volumetric_speed[0]) : '');
        setFanMinSpeed(settings.fan_min_speed?.[0] ? Number(settings.fan_min_speed[0]) : '');
        setFanMaxSpeed(settings.fan_max_speed?.[0] ? Number(settings.fan_max_speed[0]) : '');
        setReduceFanStopStartFreq(settings.reduce_fan_stop_start_freq?.[0] === '1' || settings.reduce_fan_stop_start_freq?.[0] === 1);
        setPressureAdvance(settings.pressure_advance?.[0] ? Number(settings.pressure_advance[0]) : '');
        setEnablePressureAdvance(settings.enable_pressure_advance?.[0] === '1' || settings.enable_pressure_advance?.[0] === 1);
        setIdleTemperature(settings.idle_temperature?.[0] ? Number(settings.idle_temperature[0]) : '');
        setSofteningTemperature(settings.temperature_vitrification?.[0] ? Number(settings.temperature_vitrification[0]) : '');
        setChamberTemp(settings.chamber_temperature?.[0] ? Number(settings.chamber_temperature[0]) : '');
        setEnableChamberControl(settings.activate_chamber_temp_control?.[0] === '1' || settings.activate_chamber_temp_control?.[0] === 1);
        
        // G-code
        if (settings.filament_start_gcode && Array.isArray(settings.filament_start_gcode)) {
          setFilamentStartGcode(settings.filament_start_gcode.join('\n'));
        } else if (settings.start_filament_gcode && Array.isArray(settings.start_filament_gcode)) {
          // Поддержка старого названия для обратной совместимости
          setFilamentStartGcode(settings.start_filament_gcode.join('\n'));
        } else {
          setFilamentStartGcode('');
        }
        if (settings.filament_end_gcode && Array.isArray(settings.filament_end_gcode)) {
          setFilamentEndGcode(settings.filament_end_gcode.join('\n'));
        } else if (settings.end_filament_gcode && Array.isArray(settings.end_filament_gcode)) {
          // Поддержка старого названия для обратной совместимости
          setFilamentEndGcode(settings.end_filament_gcode.join('\n'));
        } else {
          setFilamentEndGcode('');
        }
        
        // Заметки
        if (settings.filament_notes) {
          // filament_notes может быть строкой или массивом строк
          if (Array.isArray(settings.filament_notes)) {
            setFilamentNotes(settings.filament_notes.join('\n'));
          } else if (typeof settings.filament_notes === 'string') {
            setFilamentNotes(settings.filament_notes);
          } else {
            setFilamentNotes('');
          }
        } else {
          setFilamentNotes('');
        }
        
        // === ВКЛАДКА "ПРОФИЛЬ ПРУТКА" - дополнительные параметры ===
        const parseNumericSetting = (raw: unknown): number | '' => {
          if (raw === undefined || raw === null) {
            return '';
          }
          const rawStr = String(raw).trim();
          if (rawStr === '' || rawStr.toLowerCase() === 'nil') {
            return '';
          }
          const parsed = Number(rawStr);
          return Number.isNaN(parsed) ? '' : parsed;
        };
        setNozzleTempInitialLayer(parseNumericSetting(settings.nozzle_temperature_initial_layer?.[0]));
        const bedInitialLayerValue =
          settings.hot_plate_temp_initial_layer?.[0] ??
          settings.cool_plate_temp_initial_layer?.[0] ??
          settings.eng_plate_temp_initial_layer?.[0] ??
          settings.textured_plate_temp_initial_layer?.[0] ??
          '';
        setBedTempInitialLayer(parseNumericSetting(bedInitialLayerValue));
        setBedTempInitialLayer(settings.bed_temperature_initial_layer?.[0] ? Number(settings.bed_temperature_initial_layer[0]) : '');
        setAdaptiveVolumetricSpeed(settings.filament_adaptive_volumetric_speed?.[0] === '1' || settings.filament_adaptive_volumetric_speed?.[0] === 1);
        setVolumetricSpeedCoefficients(settings.volumetric_speed_coefficients?.[0] ? String(settings.volumetric_speed_coefficients[0]) : '');
        // Процентные значения (убираем % при загрузке)
        const shrink = settings.filament_shrink?.[0];
        setFilamentShrink(typeof shrink === 'string' ? shrink.replace('%', '') : shrink ? String(shrink).replace('%', '') : '');
        const shrinkZ = settings.filament_shrinkage_compensation_z?.[0];
        setFilamentShrinkageCompensationZ(typeof shrinkZ === 'string' ? shrinkZ.replace('%', '') : shrinkZ ? String(shrinkZ).replace('%', '') : '');
        setDefaultFilamentColour(settings.default_filament_colour?.[0] ? String(settings.default_filament_colour[0]) : '');
        setFilamentAdhesivenessCategory(settings.filament_adhesiveness_category?.[0] ? Number(settings.filament_adhesiveness_category[0]) : '');
        setFilamentIsSupport(settings.filament_is_support?.[0] === '1' || settings.filament_is_support?.[0] === 1);
        setFilamentSoluble(settings.filament_soluble?.[0] === '1' || settings.filament_soluble?.[0] === 1);
        setFilamentPrintable(settings.filament_printable?.[0] ? Number(settings.filament_printable[0]) : '');
        
        // Ретракт (дополнительные параметры)
        setDeretractionSpeed(settings.filament_deretraction_speed?.[0] ? Number(settings.filament_deretraction_speed[0]) : '');
        setRetractionMinimumTravel(settings.filament_retraction_minimum_travel?.[0] ? Number(settings.filament_retraction_minimum_travel[0]) : '');
        const retractBeforeWipeVal = settings.filament_retract_before_wipe?.[0];
        setRetractBeforeWipe(typeof retractBeforeWipeVal === 'string' ? retractBeforeWipeVal.replace('%', '') : retractBeforeWipeVal ? String(retractBeforeWipeVal).replace('%', '') : '');
        setRetractWhenChangingLayer(settings.filament_retract_when_changing_layer?.[0] === '1' || settings.filament_retract_when_changing_layer?.[0] === 1);
        setRetractRestartExtra(settings.filament_retract_restart_extra?.[0] ? Number(settings.filament_retract_restart_extra[0]) : '');
        
        // Lift (подъем Z)
        setFilamentZHop(settings.filament_z_hop?.[0] ? Number(settings.filament_z_hop[0]) : '');
        setFilamentZHopTypes(settings.filament_z_hop_types?.[0] ? String(settings.filament_z_hop_types[0]) : '');
        setRetractLiftAbove(settings.filament_retract_lift_above?.[0] ? Number(settings.filament_retract_lift_above[0]) : '');
        setRetractLiftBelow(settings.filament_retract_lift_below?.[0] ? Number(settings.filament_retract_lift_below[0]) : '');
        setRetractLiftEnforce(settings.filament_retract_lift_enforce?.[0] ? String(settings.filament_retract_lift_enforce[0]) : '');
        
        // Wipe
        setFilamentWipe(settings.filament_wipe?.[0] === '1' || settings.filament_wipe?.[0] === 1);
        setFilamentWipeDistance(settings.filament_wipe_distance?.[0] ? Number(settings.filament_wipe_distance[0]) : '');
        setFilamentFlushTemp(settings.filament_flush_temp?.[0] ? Number(settings.filament_flush_temp[0]) : '');
        setFilamentFlushVolumetricSpeed(settings.filament_flush_volumetric_speed?.[0] ? Number(settings.filament_flush_volumetric_speed[0]) : '');
        
        // Pressure Advance (дополнительные параметры)
        setAdaptivePressureAdvance(settings.adaptive_pressure_advance?.[0] === '1' || settings.adaptive_pressure_advance?.[0] === 1);
        setAdaptivePABridges(settings.adaptive_pressure_advance_bridges?.[0] ? Number(settings.adaptive_pressure_advance_bridges[0]) : '');
        setAdaptivePAOverhangs(settings.adaptive_pressure_advance_overhangs?.[0] === '1' || settings.adaptive_pressure_advance_overhangs?.[0] === 1);
        
        // === ВКЛАДКА "ОХЛАЖДЕНИЕ" - дополнительные параметры ===
        setFanCoolingLayerTime(settings.fan_cooling_layer_time?.[0] ? Number(settings.fan_cooling_layer_time[0]) : '');
        setFanMaxSpeedLayerTime(settings.slow_down_layer_time?.[0] ? Number(settings.slow_down_layer_time[0]) : ''); // slow_down_layer_time используется для fanMaxSpeedLayerTime
        setFullFanSpeedLayer(settings.full_fan_speed_layer?.[0] ? Number(settings.full_fan_speed_layer[0]) : '');
        setCloseFanFirstXLayers(settings.close_fan_the_first_x_layers?.[0] ? Number(settings.close_fan_the_first_x_layers[0]) : '');
        setSlowDownForLayerCooling(settings.slow_down_for_layer_cooling?.[0] === '1' || settings.slow_down_for_layer_cooling?.[0] === 1);
        setEnableOverhangBridgeFan(settings.enable_overhang_bridge_fan?.[0] === '1' || settings.enable_overhang_bridge_fan?.[0] === 1);
        setOverhangFanSpeed(settings.overhang_fan_speed?.[0] ? Number(settings.overhang_fan_speed[0]) : '');
        const overhangThreshold = settings.overhang_fan_threshold?.[0];
        setOverhangFanThreshold(typeof overhangThreshold === 'string' ? overhangThreshold.replace('%', '') : overhangThreshold ? String(overhangThreshold).replace('%', '') : '');
        setInternalBridgeFanSpeed(settings.internal_bridge_fan_speed?.[0] ? Number(settings.internal_bridge_fan_speed[0]) : '');
        setIroningFanSpeed(settings.ironing_fan_speed?.[0] ? Number(settings.ironing_fan_speed[0]) : '');
        setSupportMaterialInterfaceFanSpeed(settings.support_material_interface_fan_speed?.[0] ? Number(settings.support_material_interface_fan_speed[0]) : '');
        setAdditionalCoolingFanSpeed(settings.additional_cooling_fan_speed?.[0] ? Number(settings.additional_cooling_fan_speed[0]) : '');
        setEnableExhaustFan(settings.enable_exhaust_fan?.[0] === '1' || settings.enable_exhaust_fan?.[0] === 1 || !!settings.during_print_exhaust_fan_speed || !!settings.complete_print_exhaust_fan_speed);
        setDuringPrintExhaustFanSpeed(settings.during_print_exhaust_fan_speed?.[0] ? Number(settings.during_print_exhaust_fan_speed[0]) : '');
        setCompletePrintExhaustFanSpeed(settings.complete_print_exhaust_fan_speed?.[0] ? Number(settings.complete_print_exhaust_fan_speed[0]) : '');
        setActivateAirFiltration(settings.activate_air_filtration?.[0] === '1' || settings.activate_air_filtration?.[0] === 1);
        
        // === ВКЛАДКА "ПЕРЕОПРЕДЕЛЕНИЕ ПАРАМЕТРОВ" ===
        setSlowDownMinSpeed(settings.slow_down_min_speed?.[0] ? Number(settings.slow_down_min_speed[0]) : '');
        setDontSlowDownOuterWall(settings.dont_slow_down_outer_wall?.[0] === '1' || settings.dont_slow_down_outer_wall?.[0] === 1);
        setRetractionDistancesWhenCut(settings.filament_retraction_distances_when_cut?.[0] ? String(settings.filament_retraction_distances_when_cut[0]) : '');
        setLongRetractionsWhenCut(settings.filament_long_retractions_when_cut?.[0] ? String(settings.filament_long_retractions_when_cut[0]) : '');
        setLongRetractionsWhenEC(settings.long_retractions_when_ec?.[0] === '1' || settings.long_retractions_when_ec?.[0] === 1);
        setRetractionDistancesWhenEC(settings.retraction_distances_when_ec?.[0] ? Number(settings.retraction_distances_when_ec[0]) : '');
        
        // === ВКЛАДКА "ДОПОЛНИТЕЛЬНО" - дополнительные параметры ===
        setFilamentMultitoolRamming(settings.filament_multitool_ramming?.[0] === '1' || settings.filament_multitool_ramming?.[0] === 1);
        setFilamentMultitoolRammingFlow(settings.filament_multitool_ramming_flow?.[0] ? Number(settings.filament_multitool_ramming_flow[0]) : '');
        setFilamentMultitoolRammingVolume(settings.filament_multitool_ramming_volume?.[0] ? Number(settings.filament_multitool_ramming_volume[0]) : '');
        setFilamentToolchangeDelay(settings.filament_toolchange_delay?.[0] ? Number(settings.filament_toolchange_delay[0]) : '');
        setFilamentLoadingSpeed(settings.filament_loading_speed?.[0] ? Number(settings.filament_loading_speed[0]) : '');
        setFilamentLoadingSpeedStart(settings.filament_loading_speed_start?.[0] ? Number(settings.filament_loading_speed_start[0]) : '');
        setFilamentUnloadingSpeed(settings.filament_unloading_speed?.[0] ? Number(settings.filament_unloading_speed[0]) : '');
        setFilamentUnloadingSpeedStart(settings.filament_unloading_speed_start?.[0] ? Number(settings.filament_unloading_speed_start[0]) : '');
        setFilamentChangeLength(settings.filament_change_length?.[0] ? Number(settings.filament_change_length[0]) : '');
        setFilamentCoolingInitialSpeed(settings.filament_cooling_initial_speed?.[0] ? Number(settings.filament_cooling_initial_speed[0]) : '');
        setFilamentCoolingFinalSpeed(settings.filament_cooling_final_speed?.[0] ? Number(settings.filament_cooling_final_speed[0]) : '');
        setFilamentCoolingMoves(settings.filament_cooling_moves?.[0] ? Number(settings.filament_cooling_moves[0]) : '');
        setFilamentStampingDistance(settings.filament_stamping_distance?.[0] ? Number(settings.filament_stamping_distance[0]) : '');
        setFilamentStampingLoadingSpeed(settings.filament_stamping_loading_speed?.[0] ? Number(settings.filament_stamping_loading_speed[0]) : '');
        setFilamentMinimalPurgeOnWipeTower(settings.filament_minimal_purge_on_wipe_tower?.[0] ? Number(settings.filament_minimal_purge_on_wipe_tower[0]) : '');
        setPelletFlowCoefficient(settings.pellet_flow_coefficient?.[0] ? Number(settings.pellet_flow_coefficient[0]) : '');
        
        // === ВКЛАДКА "ЭКСТРУДЕР ММ" ===
        setFilamentExtruderVariant(settings.filament_extruder_variant?.[0] ? String(settings.filament_extruder_variant[0]) : '');
        setRequiredNozzleHRC(settings.required_nozzle_HRC?.[0] ? Number(settings.required_nozzle_HRC[0]) : '');
        
        // === ВКЛАДКА "ЗАВИСИМОСТИ" ===
        if (settings.compatible_printers && Array.isArray(settings.compatible_printers)) {
          setCompatiblePrinters(settings.compatible_printers.join(', '));
        } else {
          setCompatiblePrinters('');
        }
        setCompatiblePrintersCondition(settings.compatible_printers_condition?.[0] ? String(settings.compatible_printers_condition[0]) : '');
        if (settings.compatible_prints && Array.isArray(settings.compatible_prints)) {
          setCompatiblePrints(settings.compatible_prints.join(', '));
        } else {
          setCompatiblePrints('');
        }
        setCompatiblePrintsCondition(settings.compatible_prints_condition?.[0] ? String(settings.compatible_prints_condition[0]) : '');
        
        // showAdvancedSettings - устаревшая переменная, больше не используется (используем вкладки)
      } else {
        // Если нет orcaslicer_settings, сбрасываем все расширенные параметры
        setFilamentNotes('');
        setNozzleTempInitialLayer('');
        setAdaptiveVolumetricSpeed(false);
        setVolumetricSpeedCoefficients('');
        setFilamentShrink('');
        setFilamentShrinkageCompensationZ('');
        setDefaultFilamentColour('');
        setFilamentAdhesivenessCategory('');
        setFilamentIsSupport(false);
        setFilamentSoluble(false);
        setFilamentPrintable('');
        setDeretractionSpeed('');
        setRetractionMinimumTravel('');
        setRetractBeforeWipe('');
        setRetractWhenChangingLayer(false);
        setRetractRestartExtra('');
        setFilamentZHop('');
        setFilamentZHopTypes('');
        setRetractLiftAbove('');
        setRetractLiftBelow('');
        setRetractLiftEnforce('');
        setFilamentWipe(false);
        setFilamentWipeDistance('');
        setFilamentFlushTemp('');
        setFilamentFlushVolumetricSpeed('');
        setAdaptivePressureAdvance(false);
        setAdaptivePABridges('');
        setAdaptivePAOverhangs(false);
        setFanCoolingLayerTime('');
        setFanMaxSpeedLayerTime('');
        setFullFanSpeedLayer('');
        setCloseFanFirstXLayers('');
        setSlowDownForLayerCooling(false);
        setEnableOverhangBridgeFan(false);
        setOverhangFanSpeed('');
        setOverhangFanThreshold('');
        setInternalBridgeFanSpeed('');
        setIroningFanSpeed('');
        setSupportMaterialInterfaceFanSpeed('');
        setAdditionalCoolingFanSpeed('');
        setEnableExhaustFan(false);
        setDuringPrintExhaustFanSpeed('');
        setCompletePrintExhaustFanSpeed('');
        setActivateAirFiltration(false);
        setSlowDownMinSpeed('');
        setDontSlowDownOuterWall(false);
        setRetractionDistancesWhenCut('');
        setLongRetractionsWhenCut('');
        setLongRetractionsWhenEC(false);
        setRetractionDistancesWhenEC('');
        setFilamentMultitoolRamming(false);
        setFilamentMultitoolRammingFlow('');
        setFilamentMultitoolRammingVolume('');
        setFilamentToolchangeDelay('');
        setFilamentLoadingSpeed('');
        setFilamentLoadingSpeedStart('');
        setFilamentUnloadingSpeed('');
        setFilamentUnloadingSpeedStart('');
        setFilamentChangeLength('');
        setFilamentCoolingInitialSpeed('');
        setFilamentCoolingFinalSpeed('');
        setFilamentCoolingMoves('');
        setFilamentStampingDistance('');
        setFilamentStampingLoadingSpeed('');
        setFilamentMinimalPurgeOnWipeTower('');
        setPelletFlowCoefficient('');
        setFilamentExtruderVariant('');
        setRequiredNozzleHRC('');
        setCompatiblePrinters('');
        setCompatiblePrintersCondition('');
        setCompatiblePrints('');
        setCompatiblePrintsCondition('');
      }
      setSelectedFilamentId(preset.filament_id);
      // Инициализируем выбранные принтеры
      const presetPrinters = preset.printers?.map(p => p.id) || [];
      setSelectedPrinterIds(presetPrinters);
      if (preset.printers && preset.printers.length > 0) {
        setPrintersCache((prev) => {
          const next = { ...prev };
          preset.printers?.forEach((printer) => {
            next[printer.id] = printer;
          });
          return next;
        });
      }
      setPrinterSearch('');
      // При редактировании отключаем форму создания нового материала
      setShowFilamentForm(false);
    } else {
      // Сброс формы при создании нового
      setName('');
      setDescription('');
      setIsOfficial(false);
      setExtruderTemp(200);
      setBedTemp(60);
      setPrintSpeed(50);
      setTravelSpeed(150);
      setFlowRate(100);
      setFanSpeed(100);
      setRetractionLength(5.0);
      setRetractionSpeed(45.0);
      
      // Если создаем из профиля бренда - автоматически делаем официальным
      if (brandId) {
        setIsOfficial(true);
      }
      
      // Сброс расширенных параметров (все вкладки)
      setTempRangeLow('');
      setTempRangeHigh('');
      setNozzleTempInitialLayer('');
      setBedTempInitialLayer('');
      setIdleTemperature('');
      setSofteningTemperature('');
      setVolumetricSpeed('');
      setAdaptiveVolumetricSpeed(false);
      setVolumetricSpeedCoefficients('');
      setFilamentShrink('');
      setFilamentShrinkageCompensationZ('');
      setDefaultFilamentColour('');
      setFilamentAdhesivenessCategory('');
      setFilamentIsSupport(false);
      setFilamentSoluble(false);
      setFilamentPrintable('');
      setDeretractionSpeed('');
      setRetractionMinimumTravel('');
      setRetractBeforeWipe('');
      setRetractWhenChangingLayer(false);
      setRetractRestartExtra('');
      setFilamentZHop('');
      setFilamentZHopTypes('');
      setRetractLiftAbove('');
      setRetractLiftBelow('');
      setRetractLiftEnforce('');
      setFilamentWipe(false);
      setFilamentWipeDistance('');
      setFilamentFlushTemp('');
      setFilamentFlushVolumetricSpeed('');
      setPressureAdvance('');
      setEnablePressureAdvance(false);
      setAdaptivePressureAdvance(false);
      setAdaptivePABridges('');
      setAdaptivePAOverhangs(false);
      setChamberTemp('');
      setEnableChamberControl(false);
      setFanMinSpeed('');
      setFanMaxSpeed('');
      setFanCoolingLayerTime('');
      setFanMaxSpeedLayerTime('');
      setFullFanSpeedLayer('');
      setCloseFanFirstXLayers('');
      setReduceFanStopStartFreq(false);
      setSlowDownForLayerCooling(false);
      setEnableOverhangBridgeFan(false);
      setOverhangFanSpeed('');
      setOverhangFanThreshold('');
      setInternalBridgeFanSpeed('');
      setIroningFanSpeed('');
      setSupportMaterialInterfaceFanSpeed('');
      setAdditionalCoolingFanSpeed('');
      setEnableExhaustFan(false);
      setDuringPrintExhaustFanSpeed('');
      setCompletePrintExhaustFanSpeed('');
      setActivateAirFiltration(false);
      setSlowDownMinSpeed('');
      setDontSlowDownOuterWall(false);
      setRetractionDistancesWhenCut('');
      setLongRetractionsWhenCut('');
      setLongRetractionsWhenEC(false);
      setRetractionDistancesWhenEC('');
      setFilamentStartGcode('');
      setFilamentEndGcode('');
      setFilamentMultitoolRamming(false);
      setFilamentMultitoolRammingFlow('');
      setFilamentMultitoolRammingVolume('');
      setFilamentToolchangeDelay('');
      setFilamentLoadingSpeed('');
      setFilamentLoadingSpeedStart('');
      setFilamentUnloadingSpeed('');
      setFilamentUnloadingSpeedStart('');
      setFilamentChangeLength('');
      setFilamentCoolingInitialSpeed('');
      setFilamentCoolingFinalSpeed('');
      setFilamentCoolingMoves('');
      setFilamentStampingDistance('');
      setFilamentStampingLoadingSpeed('');
      setFilamentMinimalPurgeOnWipeTower('');
      setPelletFlowCoefficient('');
      setFilamentExtruderVariant('');
      setRequiredNozzleHRC('');
      setCompatiblePrinters('');
      setCompatiblePrintersCondition('');
      setCompatiblePrints('');
      setCompatiblePrintsCondition('');
      setPrintersCache({});
      setPrinterSearch('');
      setFilamentNotes(''); // Сброс заметок при создании нового пресета
      // showAdvancedSettings - устаревшая переменная, больше не используется (используем вкладки)
      
      setSelectedFilamentId(filamentId || null);
      // Сброс выбранных принтеров
      setSelectedPrinterIds([]);
      // Сброс полей создания нового материала
      setShowFilamentForm(false);
      setMaterialType('');
      setCustomMaterialType('');
      setUseCustomMaterial(false);
      setBrandSearch('');
      // Если передан brandId - автоматически выбираем его при создании нового материала
      setSelectedBrandId(brandId || null);
      setFilamentName('');
      setFilamentColorName('');
      setFilamentColorHex('#FF0000');
      // Сброс расширенных визуальных эффектов
      setFilamentVisualColorType('single');
      setFilamentVisualColors(['#FF0000']);
      setFilamentVisualFinish('matte');
      setFilamentVisualFiller('none');
      setFilamentVisualTransparency(false);
      setShowFilamentAdvancedVisual(false);
      setFilamentSearch('');
      setSelectedFilament(null);
      setShowBrandForm(false);
      setNewBrandName('');
      setNewBrandWebsite('');
    }
    setError(null);
    setDuplicateFilamentSuggestion(null);
  }, [preset, filamentId, brandId, isOpen]);

  // Когда загрузился филамент при редактировании, обновляем filamentSearch и selectedFilament
  useEffect(() => {
    if (editingFilament && preset) {
      setFilamentSearch(editingFilament.color_name ? `${editingFilament.name} (${editingFilament.color_name})` : editingFilament.name);
      setSelectedFilament(editingFilament);
    }
  }, [editingFilament, preset]);

  // Флаг для отслеживания изменений из расширенных настроек (чтобы избежать циклов)
  const isInternalColorChangeRef = useRef(false);

  // Закрываем все цветовые пикеры при клике вне их области
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      // Проверяем, есть ли открытые пикеры
      const hasOpenPickers = openColorPickers.some(isOpen => isOpen);
      if (hasOpenPickers) {
        const target = event.target as HTMLElement;
        
        // Проверяем, что клик был не на пикер или его элементы (overlay закрывает сам)
        const isClickOnPickerFlyout = target.closest('.hsl-color-picker-flyout');
        const isClickOnOverlay = target.closest('.fixed.inset-0.z-40.bg-black\\/50');
        const isClickOnColorButton = target.closest('button[style*="backgroundColor"]') || 
                                      target.closest('.flex.flex-col.gap-2')?.querySelector('button[style*="backgroundColor"]');
        
        // Если клик на overlay - он сам закроет пикер
        if (isClickOnOverlay) {
          return;
        }
        
        // Если клик не на flyout пикера и не на кнопку цвета - закрываем все пикеры
        if (!isClickOnPickerFlyout && !isClickOnColorButton) {
          setOpenColorPickers([]);
        }
      }
    };

    document.addEventListener('mousedown', handleClickOutside, true);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside, true);
    };
  }, [openColorPickers]);

  // Синхронизация filamentColorHex с filamentVisualColors[0] при изменении цвета через пикер/HEX инпут
  // Обновляем первый цвет в массиве, чтобы превью филамента отображало актуальный цвет
  useEffect(() => {
    // Пропускаем синхронизацию, если изменение было из расширенных настроек
    if (isInternalColorChangeRef.current) {
      isInternalColorChangeRef.current = false;
      return;
    }

    // Только если цвет изменился и это не пустая строка, и первый цвет в массиве отличается
    if (filamentColorHex && filamentColorHex !== '' && filamentVisualColors.length > 0) {
      // Синхронизируем только если первый цвет отличается (чтобы избежать бесконечных обновлений)
      if (filamentVisualColors[0] !== filamentColorHex) {
        // Для single color type - обновляем первый цвет
        // Для других типов - тоже обновляем первый, чтобы основной цвет соответствовал
        setFilamentVisualColors(prev => {
          const newColors = [...prev];
          newColors[0] = filamentColorHex;
          return newColors;
        });
      }
    }
  }, [filamentColorHex, filamentVisualColors]); // Добавили filamentVisualColors для отслеживания изменений

  const applyDefaultsByMaterialType = (materialTypeValue?: string | null) => {
    if (!materialTypeValue) {
      return;
    }

    applyMaterialDefaults(materialTypeValue, {
      setExtruderTemp,
      setBedTemp,
      setPrintSpeed,
      setTravelSpeed,
      setFlowRate,
      setFanSpeed,
      setRetractionLength,
      setRetractionSpeed,
      setTempRangeLow,
      setTempRangeHigh,
      setNozzleTempInitialLayer,
      setBedTempInitialLayer,
      setIdleTemperature,
      setChamberTemp,
      setEnableChamberControl,
      setVolumetricSpeed,
      setAdaptiveVolumetricSpeed,
      setFilamentShrink,
      setFilamentShrinkageCompensationZ,
      setFilamentIsSupport,
      setFilamentSoluble,
      setFanMinSpeed,
      setFanMaxSpeed,
      setOverhangFanSpeed,
      setCloseFanFirstXLayers,
      setPressureAdvance,
      setEnablePressureAdvance,
      setAdaptivePressureAdvance,
    });
  };

  const selectExistingFilament = (filament: {
    id: number;
    name: string;
    color_name?: string | null;
    color_hex?: string | null;
    material_type?: string | null;
    brand_name?: string | null;
  }) => {
    const matchedFromDropdown = filamentsData?.items?.find((item) => item.id === filament.id);
    const matchedFromSimilar = uniqueSimilarFilaments.find((item) => item.id === filament.id);
    const fullFilament = matchedFromDropdown || matchedFromSimilar || null;

    setSelectedFilamentId(filament.id);
    setSelectedFilament(fullFilament);
    setDuplicateFilamentSuggestion(null);
    setFilamentSearch(filament.color_name ? `${filament.name} (${filament.color_name})` : filament.name);
    setShowFilamentDropdown(false);
    setShowFilamentForm(false);
    setError(null);
    applyDefaultsByMaterialType(filament.material_type);
  };

  // Мутация для создания бренда
  const createBrandMutation = useMutation({
    mutationFn: (data: { name: string; slug: string; website?: string }) => brandsAPI.create(data),
    onError: (err: AxiosError<{ detail: unknown }>) => {
      setError(translateApiError(t, err?.response?.data?.detail, t('presetModal.errors.createBrand')));
      console.error('Failed to create brand:', err);
    },
  });
  
  // Мутация для создания филамента
  const createFilamentMutation = useMutation({
    mutationFn: (data: {
      brand_id: number;
      name: string;
      material_type: string;
      color_name?: string;
      color_hex?: string;
      visual_settings?: FilamentVisualSettings | null;
      diameter?: number;
      density?: number;
      price_per_kg?: number;
      spool_weight?: number;
      description?: string;
    }) => filamentsAPI.create(data),
    onSuccess: () => {
      // Инвалидируем кэш типов материалов, чтобы список обновился
      queryClient.invalidateQueries({ queryKey: ['filaments', 'material-types'] });
      // Инвалидируем кэш филаментов, чтобы новый материал появился в каталоге
      queryClient.invalidateQueries({ queryKey: ['filaments'] });
      setDuplicateFilamentSuggestion(null);
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      const detail = err?.response?.data?.detail;
      const isDuplicateFilamentError =
        (detail && typeof detail === 'object' && (detail as Record<string, unknown>).code === 'ERR_FILAMENT_ALREADY_EXISTS') ||
        detail === 'ERR_FILAMENT_ALREADY_EXISTS';

      if (isDuplicateFilamentError) {
        let suggestion: DuplicateFilamentSuggestion | null = null;

        if (detail && typeof detail === 'object') {
          const params = (detail as Record<string, unknown>).params as Record<string, unknown> || {};
          const duplicateId = Number(params.filament_id);
          if (Number.isFinite(duplicateId) && duplicateId > 0) {
            suggestion = {
              id: duplicateId,
              name: String(params.filament_name || filamentName || ''),
              brandName: params.brand_name ? String(params.brand_name) : undefined,
              materialType: params.material_type ? String(params.material_type) : undefined,
              colorName: params.color_name ? String(params.color_name) : undefined,
              colorHex: params.color_hex ? String(params.color_hex) : undefined,
            };
          }
        }

        // Fallback: если сервер вернул только код без params,
        // берём первое совпадение из подсказок бренда.
        if (!suggestion && uniqueSimilarFilaments.length) {
          const normalizedFilamentName = filamentName.trim().toLowerCase();
          const currentMaterialType = (useCustomMaterial ? customMaterialType : materialType).trim().toLowerCase();

          const matched = uniqueSimilarFilaments.find((candidate) => {
            const candidateName = candidate.name?.trim().toLowerCase() || '';
            const candidateMaterialType = candidate.material_type?.trim().toLowerCase() || '';

            return (
              candidateName === normalizedFilamentName &&
              (!currentMaterialType || candidateMaterialType === currentMaterialType) &&
              sameColorIdentity(
                candidate.color_name,
                candidate.color_hex,
                filamentColorName,
                filamentColorHex,
              )
            );
          });

          if (matched) {
            suggestion = {
              id: matched.id,
              name: matched.name,
              brandName: matched.brand_name || undefined,
              materialType: matched.material_type || undefined,
              colorName: matched.color_name || undefined,
              colorHex: matched.color_hex || undefined,
            };
          }
        }

        setDuplicateFilamentSuggestion(suggestion);
      } else {
        setDuplicateFilamentSuggestion(null);
      }
      if (isDuplicateFilamentError) {
        setError(
          translateApiError(
            t,
            err?.response?.data?.detail,
            t('apiErrors.ERR_FILAMENT_ALREADY_EXISTS', {
              defaultValue: 'Такой материал уже существует. Выберите существующий.',
            }),
          ),
        );
      } else {
        setError(translateApiError(t, err?.response?.data?.detail, t('presetModal.errors.createFilament')));
      }
      if (!isDuplicateFilamentError) {
        console.error('Failed to create filament:', err);
      }
    },
  });

  const useExistingFilamentFromSuggestion = (suggestion: DuplicateFilamentSuggestion) => {
    selectExistingFilament({
      id: suggestion.id,
      name: suggestion.name,
      color_name: suggestion.colorName,
      color_hex: suggestion.colorHex,
      material_type: suggestion.materialType,
      brand_name: suggestion.brandName,
    });
  };

  // Мутация для создания пресета
  const createMutation = useMutation({
    mutationFn: (data: {
      filament_id: number;
      name: string;
      description?: string;
      is_official: boolean;
      extruder_temp: number;
      bed_temp: number;
      print_speed: number;
      travel_speed?: number;
      flow_rate?: number;
      fan_speed?: number;
      retraction_length?: number;
      retraction_speed?: number;
      orcaslicer_settings?: Record<string, any> | null;
      printer_ids?: number[];
    }) => presetsAPI.create(data),
    onSuccess: (createdPreset) => {
      queryClient.invalidateQueries({ queryKey: ['presets'] });
      if (createdPreset?.filament_id) {
        queryClient.invalidateQueries({ queryKey: ['filament-presets', createdPreset.filament_id] });
      } else {
        queryClient.invalidateQueries({ queryKey: ['filament-presets'] });
      }
      queryClient.invalidateQueries({ queryKey: ['user-presets'] });
      // Инвалидируем кэш пресетов бренда (если создавался из профиля бренда)
      if (brandId) {
        queryClient.invalidateQueries({ queryKey: ['brand-presets'] });
      }
      // Инвалидируем кэш филаментов (если создавался новый материал)
      queryClient.invalidateQueries({ queryKey: ['filaments'] });
      onClose();
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      setError(translateApiError(t, err?.response?.data?.detail, t('presetModal.errors.createPreset')));
      console.error('Failed to create preset:', err);
    },
  });

  // Мутация для обновления пресета
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { 
      id: number; 
      data: Partial<{
        name?: string;
        description?: string;
        extruder_temp?: number;
        bed_temp?: number;
        print_speed?: number;
        travel_speed?: number;
        flow_rate?: number;
        fan_speed?: number;
        retraction_length?: number;
        retraction_speed?: number;
        orcaslicer_settings?: Record<string, unknown> | null;
        printer_ids?: number[];
        filament_id?: number | null;
        active?: boolean;
      }>
    }) => presetsAPI.update(id, data),
    onSuccess: (updatedPreset) => {
      queryClient.invalidateQueries({ queryKey: ['presets'] });
      if (updatedPreset?.filament_id) {
        queryClient.invalidateQueries({ queryKey: ['filament-presets', updatedPreset.filament_id] });
      } else if (preset?.filament_id) {
        queryClient.invalidateQueries({ queryKey: ['filament-presets', preset.filament_id] });
      } else {
        queryClient.invalidateQueries({ queryKey: ['filament-presets'] });
      }
      queryClient.invalidateQueries({ queryKey: ['user-presets'] });
      // Инвалидируем кэш пресетов бренда (если редактировался из профиля бренда)
      if (brandId) {
        queryClient.invalidateQueries({ queryKey: ['brand-presets'] });
      }
      onClose();
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      setError(translateApiError(t, err?.response?.data?.detail, t('presetModal.errors.updatePreset')));
      console.error('Failed to update preset:', err);
    },
  });

  // Функция для построения JSON расширенных параметров из UI полей
  // Собирает ВСЕ параметры OrcaSlicer по всем вкладкам
  const buildOrcaslicerSettings = (filamentColorHex?: string | null): Record<string, any> | null => {
    const settings: Record<string, any> = {};
    let hasSettings = false;

    // Вспомогательная функция для добавления параметра
    const addParam = (key: string, value: string | number | string[] | null | undefined) => {
      if (value !== '' && value !== null && value !== undefined) {
        settings[key] = Array.isArray(value) ? value : [String(value)];
        hasSettings = true;
      }
    };

    // Вспомогательная функция для добавления boolean параметра
    const addBoolParam = (key: string, value: boolean) => {
      if (value) {
        settings[key] = ['1'];
        hasSettings = true;
      }
    };

    // Вспомогательная функция для добавления процентного значения
    const addPercentParam = (key: string, value: string) => {
      if (value && value.trim() !== '') {
        settings[key] = [value.trim().endsWith('%') ? value.trim() : `${value.trim()}%`];
        hasSettings = true;
      }
    };

    // === ВКЛАДКА "ПРОФИЛЬ ПРУТКА" ===
    
    // Температуры
    addParam('nozzle_temperature_range_low', tempRangeLow);
    addParam('nozzle_temperature_range_high', tempRangeHigh);
    addParam('nozzle_temperature_initial_layer', nozzleTempInitialLayer);
    const bedInitialTemp =
      bedTempInitialLayer !== '' && bedTempInitialLayer !== null ? bedTempInitialLayer : bedTemp;
    addParam('hot_plate_temp_initial_layer', bedInitialTemp);
    addParam('cool_plate_temp_initial_layer', bedInitialTemp);
    addParam('eng_plate_temp_initial_layer', bedInitialTemp);
    addParam('textured_plate_temp_initial_layer', bedInitialTemp);
    addParam('idle_temperature', idleTemperature); // Температура ожидания
    addParam('temperature_vitrification', softeningTemperature); // Температура витрификации (размягчения)
    addParam('chamber_temperature', chamberTemp);
    addBoolParam('activate_chamber_temp_control', enableChamberControl);

    // Свойства филамента
    addParam('filament_max_volumetric_speed', volumetricSpeed);
    addBoolParam('filament_adaptive_volumetric_speed', adaptiveVolumetricSpeed);
    addParam('volumetric_speed_coefficients', volumetricSpeedCoefficients);
    addPercentParam('filament_shrink', filamentShrink);
    addPercentParam('filament_shrinkage_compensation_z', filamentShrinkageCompensationZ);
    // Цвет по умолчанию - используем из defaultFilamentColour или из данных филамента
    // При создании нового филамента - синхронизируется с filamentColorHex
    // При редактировании/выборе существующего - используется цвет филамента если defaultFilamentColour не задан
    const finalColor = defaultFilamentColour || filamentColorHex;
    if (finalColor && finalColor.trim() !== '' && finalColor !== '#000000') {
      settings.default_filament_colour = [finalColor];
      hasSettings = true;
    }
    addParam('filament_adhesiveness_category', filamentAdhesivenessCategory);
    addBoolParam('filament_is_support', filamentIsSupport);
    addBoolParam('filament_soluble', filamentSoluble);
    addParam('filament_printable', filamentPrintable);

    // Ретракт
    addParam('filament_deretraction_speed', deretractionSpeed);
    addParam('filament_retraction_minimum_travel', retractionMinimumTravel);
    addPercentParam('filament_retract_before_wipe', retractBeforeWipe);
    addBoolParam('filament_retract_when_changing_layer', retractWhenChangingLayer);
    addParam('filament_retract_restart_extra', retractRestartExtra);

    // Lift (подъем Z)
    addParam('filament_z_hop', filamentZHop);
    addParam('filament_z_hop_types', filamentZHopTypes);
    addParam('filament_retract_lift_above', retractLiftAbove);
    addParam('filament_retract_lift_below', retractLiftBelow);
    addParam('filament_retract_lift_enforce', retractLiftEnforce);

    // Wipe
    addBoolParam('filament_wipe', filamentWipe);
    addParam('filament_wipe_distance', filamentWipeDistance);
    addParam('filament_flush_temp', filamentFlushTemp);
    addParam('filament_flush_volumetric_speed', filamentFlushVolumetricSpeed);

    // Pressure Advance
    addParam('pressure_advance', pressureAdvance);
    addBoolParam('enable_pressure_advance', enablePressureAdvance);
    addBoolParam('adaptive_pressure_advance', adaptivePressureAdvance);
    addParam('adaptive_pressure_advance_bridges', adaptivePABridges);
    addBoolParam('adaptive_pressure_advance_overhangs', adaptivePAOverhangs);

    // === ВКЛАДКА "ОХЛАЖДЕНИЕ" ===
    
    // Обдув модели
    addParam('fan_min_speed', fanMinSpeed);
    addParam('fan_max_speed', fanMaxSpeed);
    addParam('fan_cooling_layer_time', fanCoolingLayerTime); // Время слоя для мин. скорости (порог мин. скорости)
    // slow_down_layer_time используется для макс. скорости вентилятора (порог макс. скорости)
    // Используем fanMaxSpeedLayerTime для порога макс. скорости вентилятора, если он задан
    if (fanMaxSpeedLayerTime !== '') {
      addParam('slow_down_layer_time', fanMaxSpeedLayerTime);
    }
    // reduce_fan_stop_start_freq = "Keep fan always on" в OrcaSlicer (вентилятор включён всегда)
    addBoolParam('reduce_fan_stop_start_freq', reduceFanStopStartFreq);
    addParam('full_fan_speed_layer', fullFanSpeedLayer); // Полная скорость вентилятора на слое
    addParam('close_fan_the_first_x_layers', closeFanFirstXLayers); // Закрыть вентилятор на первых X слоях

    // Замедление для охлаждения (связано с вентилятором)
    addBoolParam('slow_down_for_layer_cooling', slowDownForLayerCooling);
    // slow_down_min_speed добавляется ниже в разделе "Переопределение параметров"
    // dont_slow_down_outer_wall добавляется ниже в разделе "Переопределение параметров"

    // Принудительный обдув нависаний и мостов
    addBoolParam('enable_overhang_bridge_fan', enableOverhangBridgeFan);
    if (enableOverhangBridgeFan || overhangFanSpeed !== '' || overhangFanThreshold !== '') {
      addParam('overhang_fan_speed', overhangFanSpeed);
      addPercentParam('overhang_fan_threshold', overhangFanThreshold);
    }
    // Скорость вентилятора для внутренних мостов (-1 = по умолчанию)
    if (internalBridgeFanSpeed !== '' || enableOverhangBridgeFan) {
      settings.internal_bridge_fan_speed = internalBridgeFanSpeed !== '' ? [String(internalBridgeFanSpeed)] : ['-1'];
      hasSettings = true;
    }
    // Скорость вентилятора на связующем слое (-1 = по умолчанию)
    if (supportMaterialInterfaceFanSpeed !== '') {
      settings.support_material_interface_fan_speed = [String(supportMaterialInterfaceFanSpeed)];
      hasSettings = true;
    }
    // Ironing fan speed (-1 = по умолчанию)
    if (ironingFanSpeed !== '') {
      settings.ironing_fan_speed = [String(ironingFanSpeed)];
      hasSettings = true;
    }

    // Вспомогательный вентилятор модели
    addParam('additional_cooling_fan_speed', additionalCoolingFanSpeed);

    // Вытяжной вентилятор
    // enable_exhaust_fan - возможно есть в OrcaSlicer, но может называться по-другому
    // Пока не добавляем, так как не уверены в точном имени параметра
    // Но если enableExhaustFan включен, добавляем скорости
    if (enableExhaustFan || duringPrintExhaustFanSpeed !== '' || completePrintExhaustFanSpeed !== '') {
      addParam('during_print_exhaust_fan_speed', duringPrintExhaustFanSpeed);
      addParam('complete_print_exhaust_fan_speed', completePrintExhaustFanSpeed);
      addBoolParam('activate_air_filtration', activateAirFiltration);
    }

    // === ВКЛАДКА "ПЕРЕОПРЕДЕЛЕНИЕ ПАРАМЕТРОВ" ===
    
    // Скорости и замедления
    // slow_down_for_layer_cooling уже добавлено выше в разделе "Охлаждение"
    // slow_down_layer_time уже добавлено выше (используется как fanMaxSpeedLayerTime для порога макс. скорости вентилятора)
    // slowDownLayerTime удален - используем только fanMaxSpeedLayerTime (добавлен выше в разделе "Охлаждение")
    addParam('slow_down_min_speed', slowDownMinSpeed); // Минимальная скорость печати при замедлении
    addBoolParam('dont_slow_down_outer_wall', dontSlowDownOuterWall);

    // Дополнительные параметры ретракта
    addParam('filament_retraction_distances_when_cut', retractionDistancesWhenCut);
    addParam('filament_long_retractions_when_cut', longRetractionsWhenCut);
    addBoolParam('long_retractions_when_ec', longRetractionsWhenEC);
    addParam('retraction_distances_when_ec', retractionDistancesWhenEC);

    // === ВКЛАДКА "ДОПОЛНИТЕЛЬНО" ===
    
    // G-code
    if (filamentStartGcode && filamentStartGcode.trim() !== '') {
      // OrcaSlicer использует массив строк для G-code, каждая строка - отдельный элемент
      // Преобразуем многострочный текст в массив строк
      const startGcodeLines = filamentStartGcode.split('\n').filter(line => line.trim() !== '');
      if (startGcodeLines.length > 0) {
        settings.filament_start_gcode = startGcodeLines;
        hasSettings = true;
      }
    }
    if (filamentEndGcode && filamentEndGcode.trim() !== '') {
      // Преобразуем многострочный текст в массив строк
      const endGcodeLines = filamentEndGcode.split('\n').filter(line => line.trim() !== '');
      if (endGcodeLines.length > 0) {
        settings.filament_end_gcode = endGcodeLines;
        hasSettings = true;
      }
    }
    
    // Мультитул
    addBoolParam('filament_multitool_ramming', filamentMultitoolRamming);
    addParam('filament_multitool_ramming_flow', filamentMultitoolRammingFlow);
    addParam('filament_multitool_ramming_volume', filamentMultitoolRammingVolume);
    // filament_ramming_parameters - не переносим в UI (сложный параметр, настраивается через OrcaSlicer)
    addParam('filament_toolchange_delay', filamentToolchangeDelay);

    // Загрузка/выгрузка
    addParam('filament_loading_speed', filamentLoadingSpeed);
    addParam('filament_loading_speed_start', filamentLoadingSpeedStart);
    addParam('filament_unloading_speed', filamentUnloadingSpeed);
    addParam('filament_unloading_speed_start', filamentUnloadingSpeedStart);
    addParam('filament_change_length', filamentChangeLength);

    // Охлаждение при загрузке
    addParam('filament_cooling_initial_speed', filamentCoolingInitialSpeed);
    addParam('filament_cooling_final_speed', filamentCoolingFinalSpeed);
    addParam('filament_cooling_moves', filamentCoolingMoves);

    // Stamping
    addParam('filament_stamping_distance', filamentStampingDistance);
    addParam('filament_stamping_loading_speed', filamentStampingLoadingSpeed);

    // Дополнительные параметры
    addParam('filament_minimal_purge_on_wipe_tower', filamentMinimalPurgeOnWipeTower);
    addParam('pellet_flow_coefficient', pelletFlowCoefficient);

    // === ВКЛАДКА "ЭКСТРУДЕР ММ" ===
    addParam('filament_extruder_variant', filamentExtruderVariant);
    addParam('required_nozzle_HRC', requiredNozzleHRC);

    // === ВКЛАДКА "ЗАВИСИМОСТИ" ===
    if (compatiblePrinters.trim() !== '') {
      settings.compatible_printers = compatiblePrinters.split(',').map(s => s.trim()).filter(s => s);
      hasSettings = true;
    }
    addParam('compatible_printers_condition', compatiblePrintersCondition);
    if (compatiblePrints.trim() !== '') {
      settings.compatible_prints = compatiblePrints.split(',').map(s => s.trim()).filter(s => s);
      hasSettings = true;
    }
    addParam('compatible_prints_condition', compatiblePrintsCondition);

    // === ВКЛАДКА "ЗАМЕТКИ" ===
    addParam('filament_notes', filamentNotes);

    return hasSettings ? settings : null;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setDuplicateFilamentSuggestion(null);

    // Если создаем новый филамент, сначала создаем его
    // ВАЖНО: это работает и при создании пресета, и при редактировании черновика
    if (showFilamentForm) {
      // Если передан brandId из пропсов - используем его (бренд создает материал для себя)
      let finalBrandId: number;
      
      if (brandId) {
        // Если передан brandId - используем его, не позволяем создавать новый бренд
        finalBrandId = brandId;
      } else {
        // Обычная логика для пользователей без привязки к бренду
        let brandIdFromSelection = selectedBrandId;
        
        if (showBrandForm) {
          if (!newBrandName.trim()) {
            setError(t('presetModal.errors.enterBrandName'));
            return;
          }
          
          try {
            // Создаём slug из названия
            const slug = newBrandName.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
            const newBrand = await createBrandMutation.mutateAsync({
              name: newBrandName.trim(),
              slug: slug,
              website: newBrandWebsite.trim() || undefined,
            });
            brandIdFromSelection = newBrand.id;
          } catch (err) {
            // Ошибка уже обработана в createBrandMutation.onError
            return;
          }
        } else if (!selectedBrandId && brandSearch.trim()) {
          // Если введен текст, но не выбран бренд - создаем новый
          try {
            const slug = brandSearch.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');
            const newBrand = await createBrandMutation.mutateAsync({
              name: brandSearch.trim(),
              slug: slug,
            });
            brandIdFromSelection = newBrand.id;
          } catch (err) {
            // Ошибка уже обработана в createBrandMutation.onError
            return;
          }
        } else if (!selectedBrandId) {
          setError(t('presetModal.errors.selectBrand'));
          return;
        }
        
        finalBrandId = brandIdFromSelection!;
      }
      
      if (!filamentName.trim()) {
        setError(t('presetModal.errors.enterFilamentName'));
        return;
      }

      // Проверяем тип материала
      const finalMaterialType = useCustomMaterial ? customMaterialType.trim() : materialType;
      if (!finalMaterialType) {
        setError(t('presetModal.errors.selectMaterialType'));
        return;
      }

      // Определяем плотность: если тип известный - берем из мапа, иначе из поля ввода
      let finalDensity: number | undefined = undefined;
      const knownDensity = MATERIAL_DENSITY_MAP[finalMaterialType.toUpperCase()] || MATERIAL_DENSITY_MAP[finalMaterialType];
      if (knownDensity) {
        finalDensity = knownDensity;
      } else if (filamentDensity !== '') {
        finalDensity = Number(filamentDensity);
      }

      try {
        // Формируем visual_settings если есть расширенные эффекты
        const visualSettings: FilamentVisualSettings | undefined = showFilamentAdvancedVisual || filamentVisualFiller !== 'none' || filamentVisualColorType !== 'single' || filamentVisualFinish !== 'matte' || filamentVisualTransparency
          ? {
              color_type: filamentVisualColorType,
              colors: filamentVisualColors,
              finish: filamentVisualFinish,
              filler: filamentVisualFiller,
              transparency: filamentVisualTransparency,
            }
          : undefined;

        const newFilament = await createFilamentMutation.mutateAsync({
          brand_id: finalBrandId,
          name: filamentName,
          material_type: finalMaterialType,
          color_name: filamentColorName || undefined,
          color_hex: filamentColorHex,
          visual_settings: visualSettings,
          diameter: Number(filamentDiameter),
          density: finalDensity,
          price_per_kg: canCreateOfficial && filamentPricePerKg !== '' ? Number(filamentPricePerKg) : undefined,
          spool_weight: canCreateOfficial && filamentSpoolWeight !== '' ? Number(filamentSpoolWeight) : undefined,
          description: filamentDescription.trim() || undefined,
        });
        // Валидация обязательных полей пресета
        if (!name.trim()) {
          setError(t('presetModal.errors.enterPresetName'));
          return;
        }

        // Используем созданный филамент для пресета
        // Формируем JSON расширенных параметров из UI полей
        // Передаём цвет филамента для синхронизации с default_filament_colour
        const orcaslicerSettings = buildOrcaslicerSettings(filamentColorHex);
        
        try {
          if (preset) {
            // Редактирование заготовки: привязываем только что созданный материал
            // и активируем пресет
            const updateData: {
              name: string;
              description?: string;
              extruder_temp: number;
              bed_temp: number;
              print_speed: number;
              travel_speed: number;
              flow_rate: number;
              fan_speed: number;
              retraction_length: number;
              retraction_speed: number;
              orcaslicer_settings?: Record<string, unknown> | null;
              printer_ids: number[];
              filament_id: number;
              active?: boolean;
            } = {
              name,
              description: description || undefined,
              extruder_temp: extruderTemp,
              bed_temp: bedTemp,
              print_speed: printSpeed,
              travel_speed: travelSpeed,
              flow_rate: flowRate,
              fan_speed: fanSpeed,
              retraction_length: retractionLength,
              retraction_speed: retractionSpeed,
              orcaslicer_settings: orcaslicerSettings,
              printer_ids: selectedPrinterIds.length > 0 ? selectedPrinterIds : [],
              filament_id: newFilament.id,
              active: isDraft ? true : undefined,
            };

            await updateMutation.mutateAsync({
              id: preset.id,
              data: updateData,
            });
          } else {
            await createMutation.mutateAsync({
              filament_id: newFilament.id,
              name,
              description: description || undefined,
              is_official: isOfficial,
              extruder_temp: extruderTemp,
              bed_temp: bedTemp,
              print_speed: printSpeed,
              travel_speed: travelSpeed,
              flow_rate: flowRate,
              fan_speed: fanSpeed,
              retraction_length: retractionLength,
              retraction_speed: retractionSpeed,
              orcaslicer_settings: orcaslicerSettings,
              printer_ids: selectedPrinterIds.length > 0 ? selectedPrinterIds : undefined,
            });
          }
        } catch (err) {
          // Ошибка уже обработана в createMutation.onError / updateMutation.onError
        }
      } catch (err) {
        // Ошибка уже обработана в createFilamentMutation.onError
      }
      return;
    }

    if (!selectedFilamentId) {
      setError(
        showFilamentForm
          ? t('presetModal.errors.finishOrCancelFilamentCreation')
          : t('presetModal.errors.selectFilament')
      );
      return;
    }

    // Валидация обязательных полей
    if (!name.trim()) {
      setError(t('presetModal.errors.enterPresetName'));
      return;
    }

    // Формируем JSON расширенных параметров из UI полей
    // Определяем цвет филамента для синхронизации с default_filament_colour
    const filamentColor = preset && editingFilament 
      ? editingFilament.color_hex 
      : selectedFilament?.color_hex 
      ? selectedFilament.color_hex 
      : showFilamentForm 
      ? filamentColorHex 
      : null;
    const orcaslicerSettings = buildOrcaslicerSettings(filamentColor);

    if (preset) {
      // Обновление существующего пресета
      // Для черновиков (заготовок) также передаём filament_id и активируем пресет
      const updateData: {
        name: string;
        description?: string;
        extruder_temp: number;
        bed_temp: number;
        print_speed: number;
        travel_speed: number;
        flow_rate: number;
        fan_speed: number;
        retraction_length: number;
        retraction_speed: number;
        orcaslicer_settings?: Record<string, unknown> | null;
        printer_ids: number[];
        filament_id?: number;
        active?: boolean;
      } = {
        name,
        description: description || undefined,
        extruder_temp: extruderTemp,
        bed_temp: bedTemp,
        print_speed: printSpeed,
        travel_speed: travelSpeed,
        flow_rate: flowRate,
        fan_speed: fanSpeed,
        retraction_length: retractionLength,
        retraction_speed: retractionSpeed,
        orcaslicer_settings: orcaslicerSettings,
        printer_ids: selectedPrinterIds.length > 0 ? selectedPrinterIds : [],
      };
      
      // Если это черновик и выбран филамент - активируем пресет
      if (isDraft && selectedFilamentId) {
        updateData.filament_id = selectedFilamentId;
        updateData.active = true;
      }
      
      updateMutation.mutate({
        id: preset.id,
        data: updateData,
      });
    } else {
      // Создание нового пресета для существующего филамента
      createMutation.mutate({
        filament_id: selectedFilamentId,
        name,
        description: description || undefined,
        is_official: isOfficial,
        extruder_temp: extruderTemp,
        bed_temp: bedTemp,
        print_speed: printSpeed,
        travel_speed: travelSpeed,
        flow_rate: flowRate,
        fan_speed: fanSpeed,
        retraction_length: retractionLength,
        retraction_speed: retractionSpeed,
        orcaslicer_settings: orcaslicerSettings,
        printer_ids: selectedPrinterIds.length > 0 ? selectedPrinterIds : undefined,
      });
    }
  };

  const isLoading =
    createMutation.isPending ||
    updateMutation.isPending ||
    createFilamentMutation.isPending ||
    createBrandMutation.isPending;
  const normalizedMaterialType = useCustomMaterial ? customMaterialType.trim() : materialType.trim();
  const hasBrandSelection = brandId
    ? true
    : showBrandForm
      ? newBrandName.trim().length > 0
      : Boolean(selectedBrandId || brandSearch.trim());
  const canSubmitFromFilamentForm =
    hasBrandSelection && filamentName.trim().length > 0 && normalizedMaterialType.length > 0;
  const canSubmit = name.trim().length > 0 && (showFilamentForm ? canSubmitFromFilamentForm : Boolean(selectedFilamentId));
  const isSubmitDisabled = isLoading || !canSubmit;
  const submitBlockReason = !isLoading && isSubmitDisabled
    ? !name.trim()
      ? t('presetModal.hints.enterPresetNameToContinue')
      : showFilamentForm
        ? !normalizedMaterialType
          ? t('presetModal.hints.selectMaterialTypeToContinue')
          : !hasBrandSelection
            ? t('presetModal.hints.selectBrandToContinue')
            : !filamentName.trim()
              ? t('presetModal.hints.enterFilamentNameToContinue')
              : null
        : !selectedFilamentId
          ? t('presetModal.hints.selectFilamentToContinue')
          : null
    : null;

  if (!isOpen) return null;

  return (
    <ModalOverlay onClose={onClose}>
      <div
        className="bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 rounded-2xl w-full max-w-5xl overflow-hidden flex flex-col border border-white/20 shadow-2xl max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-white/10">
          <h2 className="text-2xl font-bold text-white">
            {preset
              ? (isDraft ? t('presetModal.titleDraft') : t('presetModal.titleEdit'))
              : t('presetModal.titleCreate')
            }
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/10 rounded-lg transition-all text-gray-300 hover:text-white"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Error */}
          {error && (
            <div className="mb-4 p-3 bg-red-500/20 border border-red-500/30 rounded-lg text-red-300 text-sm">
              {error}
            </div>
          )}
          {duplicateFilamentSuggestion && (
            <div className="mb-4 p-3 bg-yellow-500/20 border border-yellow-500/30 rounded-lg text-yellow-200 text-sm">
              <p className="font-medium">
                {t('presetModal.duplicateFilamentFound', { defaultValue: 'Такой материал уже существует' })}
              </p>
              <p className="mt-1 text-yellow-100">
                {(duplicateFilamentSuggestion.brandName ? `${duplicateFilamentSuggestion.brandName} ` : '')}
                {duplicateFilamentSuggestion.name}
                {duplicateFilamentSuggestion.colorName ? ` (${duplicateFilamentSuggestion.colorName})` : ''}
              </p>
              <button
                type="button"
                onClick={() => useExistingFilamentFromSuggestion(duplicateFilamentSuggestion)}
                className="mt-3 px-3 py-2 bg-yellow-500/30 hover:bg-yellow-500/40 border border-yellow-400/40 rounded-lg text-yellow-100 transition-all"
              >
                {t('presetModal.useExistingFilament', { defaultValue: 'Выбрать существующий материал' })}
              </button>
            </div>
          )}

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-6">
          {/* Отображение филамента при редактировании (только если не черновик) */}
          {preset && editingFilament && !isDraft && (
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('presetModal.filament')}</label>
              <FilamentSummaryCard filament={editingFilament} />
            </div>
          )}

          {/* Material Selection (при создании ИЛИ при редактировании черновика) */}
          {(!preset || isDraft) && (
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('presetModal.filament')} *</label>
              {!showFilamentForm ? (
                // Выбор существующего филамента
                <div className="relative" ref={filamentDropdownRef}>
                  <div className="flex items-center space-x-2">
                    <input
                      type="text"
                      value={filamentSearch}
                      onChange={(e) => {
                        setFilamentSearch(e.target.value);
                        setShowFilamentDropdown(true);
                        // Если очищаем поле - сбрасываем выбор
                        if (e.target.value === '') {
                          setSelectedFilamentId(null);
                          setSelectedFilament(null);
                        }
                      }}
                      onFocus={() => setShowFilamentDropdown(true)}
                      placeholder={t('presetModal.filamentSearchPlaceholder')}
                      className="flex-1 px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 placeholder:text-center focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                    />
                    {selectedFilamentId ? (
                      <Check className="w-6 h-6 text-green-400" />
                    ) : (
                      <button
                        type="button"
                        onClick={() => {
                          setShowFilamentForm(true);
                          setDuplicateFilamentSuggestion(null);
                        }}
                        className="px-3 py-3 bg-purple-600 hover:bg-purple-700 rounded-xl transition-all text-white flex items-center gap-2 whitespace-nowrap"
                        title={t('presetModal.createNewFilament')}
                        aria-label={t('presetModal.createNewFilament')}
                      >
                        <Plus className="w-5 h-5" />
                        <span className="text-sm font-medium">{t('presetModal.createNewFilament')}</span>
                      </button>
                    )}
                  </div>
                  {showFilamentDropdown && filamentsData?.items && filamentsData.items.length > 0 && (
                    <div 
                      className="absolute z-10 w-full mt-2 max-h-60 overflow-y-auto bg-white/5 backdrop-blur-sm rounded-xl border border-white/10 shadow-xl"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {filamentsData.items.map((filament: Filament) => (
                        <button
                          key={filament.id}
                          type="button"
                          onClick={() => selectExistingFilament(filament)}
                          className="w-full px-4 py-3 text-left hover:bg-white/10 transition-all text-white border-b border-white/5 last:border-b-0"
                        >
                          <div className="flex items-center justify-between">
                            <div>
                              <div className="font-medium">
                                {filament.brand_name && <span className="text-gray-300">{filament.brand_name} </span>}
                                {filament.name}
                              </div>
                              {filament.color_name && <div className="text-gray-400 text-sm">{filament.color_name}</div>}
                            </div>
                            <span className="text-purple-300 text-sm font-medium">{filament.material_type}</span>
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                  
                  {/* Сообщение об ошибке загрузки материалов */}
                  {filamentsError && (
                    <div className="mt-2 p-3 bg-red-500/20 border border-red-500/30 rounded-xl text-red-300 text-sm">
                      {t('presetModal.filamentsLoadError')}: {filamentsError instanceof Error ? filamentsError.message : t('presetModal.unknownError')}
                    </div>
                  )}
                  
                  {/* Сообщение если нет материалов */}
                  {brandId && filamentsData && filamentsData.items.length === 0 && !filamentsError && (
                    <div className="mt-2 p-3 bg-yellow-500/20 border border-yellow-500/30 rounded-xl text-yellow-300 text-sm">
                      {t('presetModal.noFilamentsForBrand')}
                    </div>
                  )}
                  
                  {/* Информация о выбранном филаменте */}
                  {selectedFilament && (
                    <div className="mt-4">
                      <FilamentSummaryCard filament={selectedFilament} />
                    </div>
                  )}
                  {!selectedFilamentId && (
                    <p className="mt-2 text-xs text-gray-400">{t('presetModal.hints.createFilamentIfMissing')}</p>
                  )}
                </div>
              ) : (
                // Форма создания нового материала
                <div className="space-y-4 p-4 bg-white/5 rounded-xl border border-purple-500/30">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-bold text-white">{t('presetModal.createNewFilament')}</h3>
                    <button
                      type="button"
                      onClick={() => {
                        setShowFilamentForm(false);
                        setDuplicateFilamentSuggestion(null);
                      }}
                      className="text-gray-400 hover:text-white text-sm"
                    >
                      {t('presetModal.cancel')}
                    </button>
                  </div>
                  
                  {/* Тип материала и Производитель в одной строке */}
                  <div className="flex items-start gap-4">
                    {/* Тип материала */}
                    <div className="relative flex-1" ref={materialTypeDropdownRef}>
                      <label className="block text-gray-300 mb-2 text-sm font-medium">{t('presetModal.materialType')} *</label>
                    <div className="relative">
                      <div className="flex gap-2">
                        <input
                          type="text"
                          value={useCustomMaterial ? customMaterialType : materialType}
                          onChange={(e) => {
                            if (useCustomMaterial) {
                              setCustomMaterialType(e.target.value);
                            } else {
                              const value = e.target.value;
                              setMaterialType(value);
                              // Показываем выпадающий список если начали вводить
                              if (value.length > 0) {
                                setShowMaterialTypeDropdown(true);
                              }
                              // Проверяем плотность для введенного типа
                              const density = MATERIAL_DENSITY_MAP[value.toUpperCase()] || MATERIAL_DENSITY_MAP[value] || null;
                              if (density) {
                                setFilamentDensity(density);
                                setCanEditDensity(false);
                              } else {
                                setCanEditDensity(true);
                                if (!filamentDensity) {
                                  setFilamentDensity(1.24);
                                }
                              }
                            }
                          }}
                          onFocus={() => {
                            if (!useCustomMaterial) {
                              setShowMaterialTypeDropdown(true);
                            }
                          }}
                          placeholder={useCustomMaterial ? t('presetModal.enterMaterialTypePlaceholder') : t('presetModal.selectMaterialTypePlaceholder')}
                          className="flex-1 px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 placeholder:text-center focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                        />
                        {useCustomMaterial && (
                          <button
                            type="button"
                            onClick={() => {
                              setUseCustomMaterial(false);
                              setCustomMaterialType('');
                              setMaterialType('');
                            }}
                            className="px-4 py-3 bg-white/10 hover:bg-white/20 border border-white/20 rounded-xl text-gray-300 hover:text-white transition-all text-sm flex-shrink-0"
                          >
                            {t('presetModal.cancel')}
                          </button>
                        )}
                      </div>
                      {showMaterialTypeDropdown && !useCustomMaterial && (
                        <div 
                          className="absolute z-10 w-full mt-1 max-h-60 overflow-y-auto bg-white/5 backdrop-blur-sm rounded-xl border border-white/10 shadow-xl"
                          onClick={(e) => e.stopPropagation()}
                        >
                          {(() => {
                            const baseTypes = sortedMaterialTypes.length > 0 ? sortedMaterialTypes : MATERIAL_TYPES;
                            const query = materialType.toLowerCase();
                            // Если значение точно совпадает с типом — показываем весь список (выбор, а не поиск)
                            const isExact = baseTypes.some((type) => type.toLowerCase() === query);
                            const filteredTypes = isExact
                              ? baseTypes
                              : baseTypes.filter((type) => type.toLowerCase().includes(query));

                            return filteredTypes.length > 0 ? (
                              filteredTypes.map((type) => (
                                <button
                                  key={type}
                                  type="button"
                                  onClick={() => {
                                    setMaterialType(type);
                                    setShowMaterialTypeDropdown(false);
                                    
                                    // Автоматически определяем плотность по типу материала
                                    const density = MATERIAL_DENSITY_MAP[type.toUpperCase()] || MATERIAL_DENSITY_MAP[type] || null;
                                    if (density) {
                                      setFilamentDensity(density);
                                      setCanEditDensity(false); // Тип известный - плотность определяется автоматически
                                    } else {
                                      // Тип неизвестный - можно редактировать плотность вручную
                                      setCanEditDensity(true);
                                      if (!filamentDensity) {
                                        setFilamentDensity(1.24); // Дефолтное значение если пусто
                                      }
                                    }
                                    
                                    // Применяем стандартные значения для выбранного типа материала
                                    applyMaterialDefaults(type, {
                                      setExtruderTemp,
                                      setBedTemp,
                                      setPrintSpeed,
                                      setTravelSpeed,
                                      setFlowRate,
                                      setFanSpeed,
                                      setRetractionLength,
                                      setRetractionSpeed,
                                      setTempRangeLow,
                                      setTempRangeHigh,
                                      setNozzleTempInitialLayer,
                                      setBedTempInitialLayer,
                                      setIdleTemperature,
                                      setChamberTemp,
                                      setEnableChamberControl,
                                      setVolumetricSpeed,
                                      setAdaptiveVolumetricSpeed,
                                      setFilamentShrink,
                                      setFilamentShrinkageCompensationZ,
                                      setFilamentIsSupport,
                                      setFilamentSoluble,
                                      setFanMinSpeed,
                                      setFanMaxSpeed,
                                      setOverhangFanSpeed,
                                      setCloseFanFirstXLayers,
                                      setPressureAdvance,
                                      setEnablePressureAdvance,
                                      setAdaptivePressureAdvance,
                                    });
                                  }}
                                  className="w-full px-4 py-3 text-left hover:bg-white/10 transition-all text-white border-b border-white/5 last:border-b-0"
                                >
                                  {type}
                                </button>
                              ))
                            ) : (
                              <div className="px-4 py-3 text-gray-400 text-sm">
                                {t('presetModal.typesNotFound')}
                              </div>
                            );
                          })()}
                          <div className="border-t border-white/10 mt-1">
                            <button
                              type="button"
                              onClick={() => {
                                setUseCustomMaterial(true);
                                setShowMaterialTypeDropdown(false);
                                setCustomMaterialType('');
                                setCanEditDensity(true); // Кастомный тип - можно редактировать плотность
                                if (!filamentDensity) {
                                  setFilamentDensity(1.24); // Дефолтное значение
                                }
                              }}
                              className="w-full px-4 py-3 text-left hover:bg-white/10 transition-all text-purple-300 font-medium"
                            >
                              + {t('presetModal.otherMaterial')}
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                    {/* Подсказка - всегда занимает одинаковое место */}
                    <div className="min-h-[20px] mt-1">
                      {useCustomMaterial ? (
                        <p className="text-xs text-gray-500">
                          {t('presetModal.customMaterialTypeHint')}
                        </p>
                      ) : (
                        <p className="text-xs text-gray-500 invisible pointer-events-none" aria-hidden="true">
                          {t('presetModal.customMaterialTypeHint')}
                        </p>
                      )}
                    </div>
                    </div>
                    
                    {/* Поиск производителя */}
                    <div className="relative flex-[2]" ref={brandDropdownRef}>
                      <label className="block text-gray-300 mb-2 text-sm font-medium">{t('presetModal.brand')} *</label>
                      {brandId && currentBrandData ? (
                        // Если передан brandId - показываем как read-only поле
                        <div className="flex items-center space-x-2">
                          <input
                            type="text"
                            value={currentBrandData.name}
                            disabled
                            className="flex-1 px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 opacity-60 cursor-not-allowed"
                          />
                          <Check className="w-6 h-6 text-green-400" />
                        </div>
                      ) : (
                        // Обычное поле для выбора/создания бренда
                        <>
                          <div className="flex items-center space-x-2">
                            <input
                              type="text"
                              value={brandSearch}
                              onChange={(e) => {
                                setBrandSearch(e.target.value);
                                setShowBrandDropdown(true);
                                setSelectedBrandId(null); // Сбрасываем выбор при изменении текста
                              }}
                              onFocus={() => setShowBrandDropdown(true)}
                              disabled={showBrandForm}
                              placeholder={t('presetModal.brandSearchPlaceholder')}
                              className="flex-1 px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 placeholder:text-center focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all disabled:opacity-50"
                            />
                            {!showBrandForm ? (
                              <>
                                {selectedBrandId ? (
                                  <Check className="w-6 h-6 text-green-400" />
                                ) : (
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setShowBrandForm(true);
                                      setNewBrandName('');
                                      setNewBrandWebsite('');
                                    }}
                                    className="px-3 py-3 bg-purple-600 hover:bg-purple-700 rounded-xl transition-all text-white flex items-center gap-2 whitespace-nowrap"
                                    title={t('presetModal.newBrandButton')}
                                    aria-label={t('presetModal.newBrandButton')}
                                  >
                                    <Plus className="w-5 h-5" />
                                    <span className="text-sm font-medium">{t('presetModal.newBrandButton')}</span>
                                  </button>
                                )}
                              </>
                            ) : (
                              <button
                                type="button"
                                onClick={() => {
                                  setShowBrandForm(false);
                                  setNewBrandName('');
                                  setNewBrandWebsite('');
                                }}
                                className="px-4 py-3 bg-red-600/50 hover:bg-red-600 rounded-xl transition-all text-white"
                              >
                                {t('presetModal.cancel')}
                              </button>
                            )}
                          </div>
                          {!showBrandForm && !selectedBrandId && (
                            <p className="mt-2 text-xs text-gray-400">{t('presetModal.hints.createBrandIfMissing')}</p>
                          )}
                          {!showBrandForm && showBrandDropdown && brandsData?.items && brandsData.items.length > 0 && (
                            <div 
                              className="absolute z-10 w-full mt-1 max-h-48 overflow-y-auto bg-white/5 backdrop-blur-sm rounded-xl border border-white/10 shadow-xl"
                              onClick={(e) => e.stopPropagation()}
                            >
                              {brandsData.items.map((brand: Brand) => (
                                <button
                                  key={brand.id}
                                  type="button"
                                  onClick={() => {
                                    setSelectedBrandId(brand.id);
                                    setBrandSearch(brand.name);
                                    setShowBrandDropdown(false);
                                  }}
                                  className="w-full px-4 py-2 text-left hover:bg-white/10 transition-all text-white border-b border-white/5 last:border-b-0"
                                >
                                  {brand.name}
                                </button>
                              ))}
                            </div>
                          )}
                          {showBrandForm && (
                            <div className="mt-2 space-y-3">
                              <input
                                type="text"
                                value={newBrandName}
                                onChange={(e) => { setNewBrandName(e.target.value); }}
                                placeholder={t('presetModal.newBrandNamePlaceholder')}
                          className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 placeholder:text-center focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                        />
                        <input
                          type="text"
                          value={newBrandWebsite}
                          onChange={(e) => { setNewBrandWebsite(e.target.value); }}
                          placeholder={t('presetModal.brandWebsitePlaceholder')}
                          className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 placeholder:text-center focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                        />
                      </div>
                    )}
                        </>
                      )}
                    </div>
                  </div>

                  {/* Название филамента */}
                  <div>
                    <label className="block text-gray-300 mb-2 text-sm font-medium">{t('presetModal.filamentName')} *</label>
                    <input
                      type="text"
                      value={filamentName}
                      onChange={(e) => { setFilamentName(e.target.value); }}
                      placeholder={t('presetModal.filamentNamePlaceholder')}
                      className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 placeholder:text-center focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                    />
                    {uniqueSimilarFilaments.length > 0 && (
                      <div className="mt-2 p-3 bg-yellow-500/20 border border-yellow-500/30 rounded-lg text-yellow-300 text-sm">
                        <p className="font-medium mb-1">{t('presetModal.similarFilaments')}:</p>
                        <ul className="space-y-2">
                          {uniqueSimilarFilaments.map((f: Filament) => (
                            <li key={f.id} className="flex items-center justify-between gap-3">
                              <div className="min-w-0">
                                {f.brand_name && <span className="text-gray-300">{f.brand_name} </span>}
                                <span className="break-words">{f.name}</span>
                                {f.color_name && <span className="text-gray-400"> ({f.color_name})</span>}
                              </div>
                              <button
                                type="button"
                                onClick={() => selectExistingFilament(f)}
                                className="shrink-0 px-2 py-1 rounded-md border border-yellow-300/40 bg-yellow-300/10 hover:bg-yellow-300/20 text-yellow-200 text-xs font-medium transition-all"
                              >
                                {t('presetModal.useExistingFilament', { defaultValue: 'Выбрать существующий материал' })}
                              </button>
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>

                  {/* Цвет филамента */}
                  <ColorMaterialSection
                    mode="edit"
                    colorName={filamentColorName}
                    onColorNameChange={setFilamentColorName}
                    colorHex={filamentColorHex}
                    onColorHexChange={setFilamentColorHex}
                    visualSettings={
                      showFilamentAdvancedVisual || filamentVisualFiller !== 'none' || filamentVisualColorType !== 'single' || filamentVisualFinish !== 'matte' || filamentVisualTransparency
                        ? {
                            color_type: filamentVisualColorType,
                            colors: filamentVisualColors,
                            finish: filamentVisualFinish,
                            filler: filamentVisualFiller,
                            transparency: filamentVisualTransparency,
                          }
                        : undefined
                    }
                    previewSize="medium"
                    rightButton={
                      <button
                        type="button"
                        onClick={() => setShowFilamentAdvancedVisual(!showFilamentAdvancedVisual)}
                        className="h-12 px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-gray-300 hover:text-white hover:bg-white/20 transition-all flex items-center gap-2"
                        title={t('presetModal.advancedColorSettings')}
                      >
                        <span className="text-sm font-medium">{t('presetModal.advancedColorSettings')}</span>
                        <span className="text-xs">{showFilamentAdvancedVisual ? '▼' : '▶'}</span>
                      </button>
                    }
                  />

                  {/* Расширенные характеристики цвета (collapsible) - меню остается здесь */}
                  {showFilamentAdvancedVisual && (
                    <div className="border border-white/10 rounded-xl p-4 bg-white/5 mt-4">
                      <div className="space-y-4">
                        {/* Тип цвета */}
                        <div>
                          <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
                            {(['single', 'two', 'three', 'gradient', 'transition', 'thermochromic'] as const).map((type) => (
                              <button
                                key={type}
                                type="button"
                                onClick={() => {
                                  setFilamentVisualColorType(type);
                                  const requiredColors = type === 'single' ? 1 : type === 'two' ? 2 : type === 'three' ? 3 : type === 'transition' || type === 'thermochromic' ? 2 : 5;
                                  setFilamentVisualColors((prevColors) => {
                                    const base = filamentColorHex || prevColors[0] || '#FF0000';
                                    const nextColors = [...prevColors];

                                    if (nextColors.length === 0) {
                                      nextColors.push(base);
                                    }

                                    if (nextColors.length < requiredColors) {
                                      const seed = nextColors[0] || base;
                                      while (nextColors.length < requiredColors) {
                                        nextColors.push(seed);
                                      }
                                    }

                                    nextColors[0] = base;

                                    return nextColors;
                                  });
                                  setOpenColorPickers([]);
                                }}
                                className={`px-4 py-2 rounded-lg border transition-all ${
                                  filamentVisualColorType === type
                                    ? 'bg-purple-600 border-purple-400 text-white'
                                    : 'bg-white/10 border-white/20 text-gray-300 hover:bg-white/20'
                                }`}
                              >
                                {type === 'single' && t('presetModal.colorSingle')}
                                {type === 'two' && t('presetModal.colorTwo')}
                                {type === 'three' && t('presetModal.colorThree')}
                                {type === 'gradient' && t('presetModal.colorGradient')}
                                {type === 'transition' && (
                                  <span title={t('presetModal.colorTransitionHint')}>
                                    {t('presetModal.colorTransition')}
                                  </span>
                                )}
                                {type === 'thermochromic' && (
                                  <span title={t('presetModal.colorThermochromicHint')}>
                                    {t('presetModal.colorThermochromic')}
                                  </span>
                                )}
                              </button>
                            ))}
                          </div>
                        </div>

                        {/* Цвета (до 5) */}
                        <div>
                          <label className="block text-gray-300 mb-2 text-sm font-medium">
                            {t('presetModal.colors')} ({filamentVisualColorType === 'single' ? 1 : filamentVisualColorType === 'two' ? 2 : filamentVisualColorType === 'three' ? 3 : filamentVisualColorType === 'transition' || filamentVisualColorType === 'thermochromic' ? 2 : 5})
                          </label>
                          <div className="grid grid-cols-5 gap-2">
                            {Array.from({ length: filamentVisualColorType === 'single' ? 1 : filamentVisualColorType === 'two' ? 2 : filamentVisualColorType === 'three' ? 3 : filamentVisualColorType === 'transition' || filamentVisualColorType === 'thermochromic' ? 2 : 5 }).map((_, idx) => {
                              const currentColor = filamentVisualColors[idx] || '#FF0000';
                              const isPickerOpen = openColorPickers[idx] || false;
                              
                              return (
                                <div key={idx} className="flex flex-col gap-2">
                                  {/* Кнопка с цветным квадратом для открытия HSL пикера */}
                                  <div className="relative">
                                    <button
                                      type="button"
                                      onClick={(e) => {
                                        e.stopPropagation(); // Предотвращаем всплытие события
                                        // Закрываем все другие пикеры перед открытием этого
                                        const newOpenStates = new Array(Math.max(openColorPickers.length, 5)).fill(false);
                                        newOpenStates[idx] = !openColorPickers[idx];
                                        setOpenColorPickers(newOpenStates);
                                      }}
                                      className="w-full h-12 rounded-lg border border-white/20 cursor-pointer hover:opacity-80 transition-opacity relative overflow-hidden"
                                      style={{ backgroundColor: currentColor }}
                                      title={t('presetModal.clickToSelectColor')}
                                    >
                                      <div className="absolute inset-0 flex items-center justify-center text-white text-xs font-medium drop-shadow-lg">
                                        {currentColor}
                                      </div>
                                    </button>
                                    
                                    {/* HSL Color Picker - появляется над кнопкой */}
                                    {isPickerOpen && (
                                      <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50">
                                        <HSLColorPicker
                                          color={currentColor}
                                          onChange={(hex) => {
                                            const newColors = [...filamentVisualColors];
                                            newColors[idx] = hex;
                                            setFilamentVisualColors(newColors);
                                            // Синхронизируем основной цвет, если меняем первый цвет в расширенных настройках
                                            if (idx === 0) {
                                              isInternalColorChangeRef.current = true; // Помечаем как внутреннее изменение
                                              setFilamentColorHex(hex);
                                            }
                                          }}
                                          isOpen={isPickerOpen}
                                          onToggle={(isOpen) => {
                                            const newOpenStates = [...openColorPickers];
                                            newOpenStates[idx] = isOpen;
                                            setOpenColorPickers(newOpenStates);
                                          }}
                                        />
                                      </div>
                                    )}
                                  </div>
                                  {/* HEX-инпут под значком — дублирует цвет, двусторонняя привязка */}
                                  <input
                                    type="text"
                                    value={currentColor}
                                    onChange={(e) => {
                                      const hex = e.target.value;
                                      const newColors = [...filamentVisualColors];
                                      newColors[idx] = hex;
                                      setFilamentVisualColors(newColors);
                                      if (idx === 0) {
                                        isInternalColorChangeRef.current = true;
                                        setFilamentColorHex(hex);
                                      }
                                    }}
                                    placeholder="#FF0000"
                                    className="w-full px-2 py-1 bg-white/10 border border-white/20 rounded-lg text-white text-xs text-center font-mono placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                                  />
                                </div>
                              );
                            })}
                          </div>
                        </div>

                        {/* Финиш */}
                        <div>
                          <label className="block text-gray-300 mb-2 text-sm font-medium">{t('presetModal.surfaceType')}</label>
                          <div className="flex gap-2">
                            {(['matte', 'glossy'] as const).map((finish) => (
                              <button
                                key={finish}
                                type="button"
                                onClick={() => setFilamentVisualFinish(finish)}
                                className={`flex-1 px-4 py-2 rounded-lg border transition-all ${
                                  filamentVisualFinish === finish
                                    ? 'bg-purple-600 border-purple-400 text-white'
                                    : 'bg-white/10 border-white/20 text-gray-300 hover:bg-white/20'
                                }`}
                              >
                                {finish === 'matte' ? t('presetModal.matte') : t('presetModal.glossy')}
                              </button>
                            ))}
                          </div>
                        </div>

                        {/* Наполнитель */}
                        <div>
                          <label className="block text-gray-300 mb-2 text-sm font-medium">{t('presetModal.filler')}</label>
                          <Dropdown
                            value={filamentVisualFiller}
                            onChange={(val) => setFilamentVisualFiller(val as typeof filamentVisualFiller)}
                            options={[
                              { value: 'none', label: t('presetModal.fillerNone') },
                              { value: 'wood', label: t('presetModal.fillerWood') },
                              { value: 'carbon', label: t('presetModal.fillerCarbon') },
                              { value: 'glass', label: t('presetModal.fillerGlass') },
                              { value: 'metallic', label: t('presetModal.fillerMetallic') },
                              { value: 'luminescent', label: t('presetModal.fillerLuminescent') },
                              { value: 'glitter', label: t('presetModal.fillerGlitter') },
                              { value: 'fibers', label: t('presetModal.fillerFibers') },
                              { value: 'stone', label: t('presetModal.fillerStone') },
                              // Паттерны временно отключены (не удалены, чтобы сохранить совместимость с существующими данными)
                              // { value: 'pattern1', label: 'Паттерн 1' },
                              // { value: 'pattern2', label: 'Паттерн 2' },
                              // { value: 'pattern3', label: 'Паттерн 3' },
                              // { value: 'pattern4', label: 'Паттерн 4' },
                              // { value: 'pattern5', label: 'Паттерн 5' },
                              // { value: 'pattern6', label: 'Паттерн 6' },
                              // { value: 'pattern7', label: 'Паттерн 7' },
                              // { value: 'pattern8', label: 'Паттерн 8' },
                              // { value: 'pattern9', label: 'Паттерн 9' },
                              // { value: 'pattern10', label: 'Паттерн 10' },
                              // { value: 'pattern11', label: 'Паттерн 11' },
                              // { value: 'pattern12', label: 'Паттерн 12' },
                            ]}
                            placeholder={t('presetModal.selectFiller')}
                          />
                        </div>

                        {/* Прозрачность */}
                        <div>
                          <label className="flex items-center space-x-2 text-gray-300 mb-2 text-sm font-medium">
                            <input
                              type="checkbox"
                              checked={filamentVisualTransparency}
                              onChange={(e) => { setFilamentVisualTransparency(e.target.checked); }}
                              className="w-4 h-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
                            />
                            <span>{t('presetModal.transparentMaterial')}</span>
                          </label>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Физические характеристики */}
                  <div className="grid grid-cols-2 gap-4">
                    <Dropdown
                      label={`${t('presetModal.diameter')} *`}
                      value={filamentDiameter}
                      options={DIAMETER_OPTIONS.map(d => ({ value: d, label: `${d} mm` }))}
                      onChange={(val) => setFilamentDiameter(String(val))}
                      placeholder={t('presetModal.selectDiameter')}
                    />
                    <div>
                      <label className="block text-gray-300 mb-2 text-sm font-medium">
                        {t('presetModal.density')}
                        {!canEditDensity && (
                          <span className="ml-2 text-xs text-gray-500">({t('presetModal.auto')})</span>
                        )}
                      </label>
                      <input
                        type="number"
                        value={filamentDensity}
                        onChange={(e) => { setFilamentDensity(e.target.value === '' ? '' : Number(e.target.value)); }}
                        placeholder={canEditDensity ? t('presetModal.densityPlaceholder') : t('presetModal.densityAuto')}
                        disabled={!canEditDensity}
                        min={0.5}
                        max={3.0}
                        step="0.01"
                        className={`w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 placeholder:text-center focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all ${
                          !canEditDensity ? 'opacity-50 cursor-not-allowed' : ''
                        }`}
                      />
                      {!canEditDensity && filamentDensity && (
                        <p className="mt-1 text-xs text-gray-500">
                          {t('presetModal.densityFor')} {useCustomMaterial ? customMaterialType : materialType}: {filamentDensity} g/cm³
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Ценовые характеристики - только для производителей */}
                  {canCreateOfficial && (
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-gray-300 mb-2 text-sm font-medium">{t('presetModal.pricePerKg')}</label>
                        <input
                          type="number"
                          value={filamentPricePerKg}
                          onChange={(e) => { setFilamentPricePerKg(e.target.value === '' ? '' : Number(e.target.value)); }}
                          placeholder={t('presetModal.placeholders.examplePrice')}
                          min={0}
                          step="10"
                          className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 placeholder:text-center focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                        />
                      </div>
                      <div>
                        <label className="block text-gray-300 mb-2 text-sm font-medium">{t('presetModal.spoolWeight')}</label>
                        <input
                          type="number"
                          value={filamentSpoolWeight}
                          onChange={(e) => { setFilamentSpoolWeight(e.target.value === '' ? '' : Number(e.target.value)); }}
                          placeholder={t('presetModal.placeholders.exampleWeight')}
                          min={0}
                          step="50"
                          className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 placeholder:text-center focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                        />
                      </div>
                    </div>
                  )}

                  {/* Описание филамента */}
                  <div>
                    <label className="block text-gray-300 mb-2 text-sm font-medium">{t('presetModal.filamentDescription')}</label>
                    <textarea
                      value={filamentDescription}
                      onChange={(e) => { setFilamentDescription(e.target.value); }}
                      rows={3}
                      placeholder={t('presetModal.filamentDescriptionPlaceholder')}
                      className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 placeholder:text-center focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all resize-none"
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Name and Printers */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('presetModal.presetName')} *</label>
              <input
                type="text"
                value={name}
                onChange={(e) => { setName(e.target.value); }}
                required
                className={`w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 placeholder:text-center focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                placeholder={t('presetModal.presetNamePlaceholder')}
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('presetModal.printers')}</label>
          <Dropdown
            label=""
            value=""
            options={
              printersData?.items
                .filter((p) => !selectedPrinterIds.includes(p.id))
                .map((printer: Printer) => ({
                  value: printer.id,
                  label: `${printer.manufacturer} ${printer.model} (${printer.name})`,
                })) || []
            }
            onChange={(val) => {
              if (val && typeof val === 'number' && !selectedPrinterIds.includes(val)) {
                const selectedPrinter =
                  printersData?.items.find((p) => p.id === val) || printersCache[val];
                if (selectedPrinter) {
                  setPrintersCache((prev) => ({ ...prev, [selectedPrinter.id]: selectedPrinter }));
                }
                setSelectedPrinterIds([...selectedPrinterIds, val]);
                setPrinterSearch('');
              }
            }}
            placeholder={t('presetModal.addPrinter')}
            filterable
            filterValue={printerSearch}
            onFilterChange={setPrinterSearch}
            emptyMessage={t('presetModal.printerNotFound')}
          />
          {selectedPrinterIds.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              {selectedPrinterIds.slice(0, 3).map((printerId) => {
                const printer =
                  printersCache[printerId] ||
                  printersData?.items.find((p) => p.id === printerId);
                if (!printer) {
                  return null;
                }
                return (
                  <span
                    key={printerId}
                    className="px-3 py-1.5 bg-purple-600/30 text-white rounded-lg text-sm flex items-center gap-2 border border-purple-500/30"
                  >
                    {printer.name}
                    <button
                      type="button"
                      onClick={() => setSelectedPrinterIds(selectedPrinterIds.filter((id) => id !== printerId))}
                      className="hover:text-red-400 transition-colors"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </span>
                );
              })}
              {selectedPrinterIds.length > 3 && (
                <span className="px-3 py-1.5 bg-white/10 text-gray-300 rounded-lg text-sm border border-white/20">
                  + {t('presetModal.moreCount', { count: selectedPrinterIds.length - 3 })}
                </span>
              )}
            </div>
          )}
              {printerSearch && printersData?.items.length === 0 && (
                <p className="text-gray-400 text-xs mt-2">{t('presetModal.printersNotFoundInDb')}</p>
              )}
            </div>
          </div>

          {/* Description */}
          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">{t('presetModal.description')}</label>
            <textarea
              value={description}
              onChange={(e) => { setDescription(e.target.value); }}
              rows={3}
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all resize-none"
              placeholder={t('presetModal.descriptionPlaceholder')}
            />
          </div>

          {/* Is Official (только при создании И только для верифицированных производителей) */}
          {/* Не показываем если передан brandId - в этом случае пресет всегда официальный */}
          {!preset && canCreateOfficial && !brandId && (
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="isOfficial"
                checked={isOfficial}
                onChange={(e) => { setIsOfficial(e.target.checked); }}
                className="w-4 h-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
              />
              <label htmlFor="isOfficial" className="text-gray-300 text-sm">
                {t('presetModal.officialPreset')}
              </label>
            </div>
          )}
          
          {/* Информация о том, что создается официальный пресет из профиля бренда */}
          {!preset && brandId && (
            <div className="flex items-center space-x-2 p-3 bg-green-500/20 border border-green-500/30 rounded-xl">
              <CheckCircle className="w-5 h-5 text-green-400" />
              <span className="text-green-300 text-sm">
                {t('presetModal.officialPresetInfo')}
              </span>
            </div>
          )}

          {/* Основные настройки */}
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">
                {t('presetModal.nozzleTemp')} *
              </label>
              <input
                type="number"
                value={extruderTemp}
                onChange={(e) => { setExtruderTemp(Number(e.target.value)); }}
                required
                min={150}
                max={300}
                step="1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">
                {t('presetModal.bedTemp')} *
              </label>
              <input
                type="number"
                value={bedTemp}
                onChange={(e) => { setBedTemp(Number(e.target.value)); }}
                required
                min={0}
                max={120}
                step="1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('presetModal.printSpeed')} *</label>
              <input
                type="number"
                value={printSpeed}
                onChange={(e) => { setPrintSpeed(Number(e.target.value)); }}
                required
                min={10}
                max={300}
                step="1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">
                {t('presetModal.travelSpeed')}
              </label>
              <input
                type="number"
                value={travelSpeed}
                onChange={(e) => { setTravelSpeed(Number(e.target.value)); }}
                min={50}
                max={300}
                step="1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('presetModal.flowRate')}</label>
              <input
                type="number"
                value={flowRate}
                onChange={(e) => { setFlowRate(Number(e.target.value)); }}
                min={50}
                max={150}
                step="0.1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('presetModal.fanSpeed')}</label>
              <input
                type="number"
                value={fanSpeed}
                onChange={(e) => { setFanSpeed(Number(e.target.value)); }}
                min={0}
                max={100}
                step="1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">
                {t('presetModal.retractionLength')}
              </label>
              <input
                type="number"
                value={retractionLength}
                onChange={(e) => { setRetractionLength(Number(e.target.value)); }}
                min={0}
                max={10}
                step="0.1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">
                {t('presetModal.retractionSpeed')}
              </label>
              <input
                type="number"
                value={retractionSpeed}
                onChange={(e) => { setRetractionSpeed(Number(e.target.value)); }}
                min={10}
                max={100}
                step="1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              />
            </div>
          </div>

          {/* OrcaSlicer Settings Tabs (как в OrcaSlicer) */}
          <div className="mt-6">
            <h3 className="text-lg font-semibold text-white mb-4">{t('presetModal.detailedSettings')}</h3>
            
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
                {t('presetModal.tabs.profile')}
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
                {t('presetModal.tabs.cooling')}
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
                {t('presetModal.tabs.override')}
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('advanced')}
                className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-all ${
                  activeTab === 'advanced'
                    ? 'bg-white/10 text-white border-b-2 border-purple-500'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                {t('presetModal.tabs.advanced')}
              </button>
              <button
                type="button"
                onClick={() => setActiveTab('extruder')}
                className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-all ${
                  activeTab === 'extruder'
                    ? 'bg-white/10 text-white border-b-2 border-purple-500'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                {t('presetModal.tabs.extruder')}
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
                {t('presetModal.tabs.notes')}
              </button>
            </div>

            {/* Содержимое вкладок */}
            <div className="p-4 bg-white/5 rounded-xl border border-white/10">
              {activeTab === 'profile' && (
              <div className="space-y-6">
                {/* Общая информация */}
                <div>
                  <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.generalInfo')}</h4>
                  
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {/* Тип материала - показываем информацию о типе из данных филамента */}
                    {((preset && editingFilament) || selectedFilament) && (
                      <div>
                        <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.type')}</label>
                        <div className="px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white text-sm">
                          {(preset && editingFilament) ? editingFilament.material_type : selectedFilament?.material_type || t('presetModal.notSelected')}
                        </div>
                        <p className="text-xs text-gray-500 mt-1">{t('presetModal.fromFilamentData')}</p>
                      </div>
                    )}

                    {/* Производитель - показываем информацию о производителе из данных филамента */}
                    {((preset && editingFilament) || selectedFilament) && (
                      <div>
                        <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.brandLabel')}</label>
                        <div className="px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-white text-sm">
                          {(preset && editingFilament) ? editingFilament.brand_name : selectedFilament?.brand_name || t('presetModal.notSelected')}
                        </div>
                        <p className="text-xs text-gray-500 mt-1">{t('presetModal.fromFilamentData')}</p>
                      </div>
                    )}

                    {/* Растворимый материал */}
                    <div className="flex items-center space-x-3">
                      <input
                        type="checkbox"
                        id="filamentSoluble"
                        checked={filamentSoluble}
                        onChange={(e) => { setFilamentSoluble(e.target.checked); }}
                        className="w-4 h-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
                      />
                      <label htmlFor="filamentSoluble" className="text-gray-300 text-sm">
                        {t('presetModal.solubleMaterial')}
                      </label>
                    </div>

                    {/* Поддержка */}
                    <div className="flex items-center space-x-3">
                      <input
                        type="checkbox"
                        id="filamentIsSupport"
                        checked={filamentIsSupport}
                        onChange={(e) => { setFilamentIsSupport(e.target.checked); }}
                        className="w-4 h-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
                      />
                      <label htmlFor="filamentIsSupport" className="text-gray-300 text-sm">
                        {t('presetModal.supportMaterial')}
                      </label>
                    </div>

                    {/* Filament ramming length - это параметр мультитула, будет в вкладке "Дополнительно" */}
                    {/* Но в OrcaSlicer он показывается в "Профиль прутка", оставляем здесь */}
                    <div>
                      <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.filamentRammingLength')}</label>
                      <div className="relative">
                        <input
                          type="number"
                          value={filamentMultitoolRammingVolume !== '' ? filamentMultitoolRammingVolume : ''}
                          onChange={(e) => { setFilamentMultitoolRammingVolume(e.target.value === '' ? '' : Number(e.target.value)); }}
                          min={0}
                          step="1"
                          placeholder="10"
                          className="w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                        />
                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm</span>
                      </div>
                    </div>

                    {/* Цвет по умолчанию - показываем только если редактируем существующий пресет и есть цвет в филаменте */}
                    {preset && editingFilament && editingFilament.color_hex && (
                      <div>
                        <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.defaultColor')}</label>
                        <div className="flex items-center space-x-3">
                          <div
                            className="w-10 h-10 rounded-lg border-2 border-white/30 shadow-md flex-shrink-0"
                            style={{ backgroundColor: defaultFilamentColour || editingFilament.color_hex || '#000000' }}
                          />
                          <input
                            type="text"
                            value={defaultFilamentColour || editingFilament.color_hex || ''}
                            readOnly
                            disabled
                            placeholder={editingFilament.color_hex || '#000000'}
                            className="flex-1 px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-gray-400 text-sm cursor-not-allowed"
                          />
                        </div>
                        <p className="text-xs text-gray-500 mt-1">
                          {t('presetModal.usedFromFilament')}: {editingFilament.color_name || t('presetModal.noName')}
                        </p>
                      </div>
                    )}
                    
                    {/* При создании нового филамента - цвет задаётся в форме создания филамента выше */}
                    {!preset && showFilamentForm && (
                      <div>
                        <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.defaultColor')}</label>
                        <div className="flex items-center space-x-3">
                          <div
                            className="w-10 h-10 rounded-lg border-2 border-white/30 shadow-md flex-shrink-0"
                            style={{ backgroundColor: defaultFilamentColour || filamentColorHex || '#000000' }}
                          />
                          <input
                            type="text"
                            value={defaultFilamentColour || filamentColorHex || ''}
                            readOnly
                            disabled
                            placeholder={filamentColorHex || '#000000'}
                            className="flex-1 px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-gray-400 text-sm cursor-not-allowed"
                          />
                        </div>
                        <p className="text-xs text-gray-500 mt-1">
                          {t('presetModal.syncWithFilamentColor')}
                        </p>
                      </div>
                    )}
                    
                    {/* При выборе существующего филамента - показываем только информацию */}
                    {!preset && !showFilamentForm && selectedFilament && selectedFilament.color_hex && (
                      <div>
                        <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.defaultColor')}</label>
                        <div className="flex items-center space-x-3">
                          <div
                            className="w-10 h-10 rounded-lg border-2 border-white/30 shadow-md flex-shrink-0"
                            style={{ backgroundColor: selectedFilament.color_hex }}
                          />
                          <input
                            type="text"
                            value={defaultFilamentColour || selectedFilament.color_hex || ''}
                            readOnly
                            disabled
                            placeholder={selectedFilament.color_hex || '#000000'}
                            className="flex-1 px-3 py-2 bg-white/5 border border-white/10 rounded-lg text-gray-400 text-sm cursor-not-allowed"
                          />
                        </div>
                        <p className="text-xs text-gray-500 mt-1">
                          {t('presetModal.fromFilamentData')}: {selectedFilament.color_name || t('presetModal.noName')}
                        </p>
                      </div>
                    )}

                    {/* Компенсация усадки по XY */}
                    <div>
                      <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.shrinkXY')}</label>
                      <div className="relative">
                        <input
                          type="text"
                          value={filamentShrink || ''}
                          onChange={(e) => { setFilamentShrink(e.target.value); }}
                          placeholder="99.8"
                          className="w-full pl-3 pr-8 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                        />
                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">%</span>
                      </div>
                    </div>

                    {/* Компенсация усадки по Z */}
                    <div>
                      <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.shrinkZ')}</label>
                      <div className="relative">
                        <input
                          type="text"
                          value={filamentShrinkageCompensationZ || ''}
                          onChange={(e) => { setFilamentShrinkageCompensationZ(e.target.value); }}
                          placeholder="100"
                          className="w-full pl-3 pr-8 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                        />
                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">%</span>
                      </div>
                    </div>

                    {/* Температура размягчения */}
                    <div>
                      <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.softeningTemp')}</label>
                      <div className="relative">
                        <input
                          type="number"
                          value={softeningTemperature !== '' ? softeningTemperature : ''}
                          onChange={(e) => { setSofteningTemperature(e.target.value === '' ? '' : Number(e.target.value)); }}
                          min={0}
                          max={255}
                          step="1"
                          placeholder="110"
                          className="w-full pl-3 pr-10 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                        />
                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">°C</span>
                      </div>
                    </div>

                    {/* Температура ожидания */}
                    <div>
                      <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.idleTemp')}</label>
                      <div className="relative">
                        <input
                          type="number"
                          value={idleTemperature !== '' ? idleTemperature : ''}
                          onChange={(e) => { setIdleTemperature(e.target.value === '' ? '' : Number(e.target.value)); }}
                          min={0}
                          max={255}
                          step="1"
                          placeholder="2"
                          className="w-full pl-3 pr-10 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                        />
                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">°C</span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Рекомендуемая температура сопла */}
                <div>
                  <h4 className="text-sm font-semibold text-white mb-3">{t('presetModal.recommendedNozzleTemp')}</h4>
                  <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-gray-400 mb-1 text-xs">{t('presetModal.min')} (°C)</label>
                        <input
                          type="number"
                          value={tempRangeLow}
                          onChange={(e) => { setTempRangeLow(e.target.value === '' ? '' : Number(e.target.value)); }}
                          min={150}
                          max={300}
                          step="1"
                          placeholder="220"
                          className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                        />
                      </div>
                      <div>
                        <label className="block text-gray-400 mb-1 text-xs">{t('presetModal.max')} (°C)</label>
                        <input
                          type="number"
                          value={tempRangeHigh}
                          onChange={(e) => { setTempRangeHigh(e.target.value === '' ? '' : Number(e.target.value)); }}
                          min={150}
                          max={300}
                          step="1"
                          placeholder="260"
                          className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                        />
                      </div>
                    </div>
                  </div>

                {/* Коэффициент потока и Pressure Advance */}
                <div>
                  <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.flowAndPA')}</h4>
                  
                  <div className="space-y-4">
                    {/* Коэф. потока модели */}
                    <div>
                      <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.modelFlowRatio')}</label>
                      <input
                        type="number"
                        value={flowRate !== 100 ? parseFloat((flowRate / 100).toFixed(3)) : 0.95}
                        onChange={(e) => { setFlowRate(e.target.value === '' ? 100 : parseFloat((Number(e.target.value) * 100).toFixed(1))); }}
                        min={0.5}
                        max={1.5}
                        step="0.001"
                        placeholder="0.95"
                        className={`w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                      />
                    </div>

                    {/* Включить Pressure advance */}
                    <div className="flex items-center space-x-3">
                      <input
                        type="checkbox"
                        id="enablePA"
                        checked={enablePressureAdvance}
                        onChange={(e) => { setEnablePressureAdvance(e.target.checked); }}
                        className="w-4 h-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
                      />
                      <label htmlFor="enablePA" className="text-gray-300 text-sm">
                        {t('presetModal.enablePA')}
                      </label>
                    </div>

                    {/* Коэф. Pressure advance */}
                    {enablePressureAdvance && (
                      <div>
                        <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.paCoefficient')}</label>
                        <input
                          type="number"
                          value={pressureAdvance}
                          onChange={(e) => { setPressureAdvance(e.target.value === '' ? '' : Number(e.target.value)); }}
                          min={0}
                          max={1}
                          step="0.001"
                          placeholder="0.038"
                          className={`w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                        />
                      </div>
                    )}

                    {/* Включить адаптивное Pressure advance (beta) */}
                    <div className="flex items-center space-x-3">
                      <input
                        type="checkbox"
                        id="adaptivePA"
                        checked={adaptivePressureAdvance}
                        onChange={(e) => { setAdaptivePressureAdvance(e.target.checked); }}
                        className="w-4 h-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
                      />
                      <label htmlFor="adaptivePA" className="text-gray-300 text-sm">
                        {t('presetModal.enableAdaptivePA')}
                      </label>
                    </div>

                    {/* Включить адаптивное Pressure advance на нависаниях (beta) */}
                    <div className="flex items-center space-x-3">
                      <input
                        type="checkbox"
                        id="adaptivePAOverhangs"
                        checked={adaptivePAOverhangs}
                        onChange={(e) => { setAdaptivePAOverhangs(e.target.checked); }}
                        className="w-4 h-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
                      />
                      <label htmlFor="adaptivePAOverhangs" className="text-gray-300 text-sm">
                        {t('presetModal.enableAdaptivePAOverhangs')}
                      </label>
                    </div>

                    {/* Коэф. Pressure advance для мостов */}
                    {adaptivePressureAdvance && (
                      <div>
                        <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.paBridges')}</label>
                        <input
                          type="number"
                          value={adaptivePABridges}
                          onChange={(e) => { setAdaptivePABridges(e.target.value ? Number(e.target.value) : ''); }}
                          min={0}
                          max={2}
                          step="0.1"
                          placeholder="1"
                          className={`w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                        />
                      </div>
                    )}

                    {/* Измеренные значения адаптивного Pressure advance (beta) */}
                    {adaptivePressureAdvance && (
                      <div>
                        <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.adaptivePAMeasured')}</label>
                        <textarea
                          value={volumetricSpeedCoefficients || ''}
                          onChange={(e) => { setVolumetricSpeedCoefficients(e.target.value); }}
                          placeholder="0,0,00,0,0"
                          rows={3}
                          className={`w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all resize-none `}
                        />
                      </div>
                    )}
                  </div>
                </div>

                {/* Температура в термокамере при печати */}
                <div>
                  <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.chamberTempSection')}</h4>
                  
                  <div className="flex items-center space-x-3">
                    <div className="flex-1">
                      <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.chamberTemp')}</label>
                      <div className="relative">
                        <input
                          type="number"
                          value={chamberTemp}
                          onChange={(e) => { setChamberTemp(e.target.value === '' ? '' : Number(e.target.value)); }}
                          min={0}
                          max={100}
                          step="1"
                          placeholder="1"
                          className={`w-full pl-3 pr-10 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                        />
                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">°C</span>
                      </div>
                    </div>

                    <div className="flex items-center space-x-3 mt-6">
                      <input
                        type="checkbox"
                        id="enableChamber"
                        checked={enableChamberControl}
                        onChange={(e) => { setEnableChamberControl(e.target.checked); }}
                        className="w-4 h-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
                      />
                      <label htmlFor="enableChamber" className="text-gray-300 text-sm whitespace-nowrap">
                        {t('presetModal.enableTempControl')}
                      </label>
                    </div>
                  </div>
                </div>

                {/* Температура печати */}
                <div>
                  <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.printTemp')}</h4>
                  
                  <div className="grid grid-cols-2 gap-4">
                    {/* Слева: Сопло */}
                    <div>
                      <label className="block text-gray-300 mb-2 text-sm">{t('presetModal.nozzle')}</label>
                      <div className="space-y-3">
                        <div>
                          <label className="block text-gray-400 mb-1 text-xs">{t('presetModal.firstLayer')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={nozzleTempInitialLayer !== '' ? nozzleTempInitialLayer : extruderTemp}
                              onChange={(e) => { setNozzleTempInitialLayer(e.target.value === '' ? '' : Number(e.target.value)); }}
                              min={150}
                              max={300}
                              step="1"
                              placeholder="250"
                              className={`w-full pl-3 pr-10 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">°C</span>
                          </div>
                        </div>
                        <div>
                          <label className="block text-gray-400 mb-1 text-xs">{t('presetModal.subsequentLayers')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={extruderTemp}
                              onChange={(e) => { setExtruderTemp(Number(e.target.value)); }}
                              min={150}
                              max={300}
                              step="1"
                              placeholder="250"
                              className={`w-full pl-3 pr-10 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">°C</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    {/* Справа: Стол */}
                    <div>
                      <label className="block text-gray-300 mb-2 text-sm">{t('presetModal.bed')}</label>
                      <div className="space-y-3">
                        <div>
                          <label className="block text-gray-400 mb-1 text-xs">{t('presetModal.firstLayer')}</label>
                          <div className="relative">
                          <input
                            type="number"
                            value={bedTempInitialLayer !== '' ? bedTempInitialLayer : bedTemp}
                            onChange={(e) => {
                              setBedTempInitialLayer(e.target.value === '' ? '' : Number(e.target.value));
                            }}
                            min={0}
                            max={120}
                            step="1"
                            placeholder="90"
                            className={`w-full pl-3 pr-10 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                          />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">°C</span>
                          </div>
                        </div>
                        <div>
                          <label className="block text-gray-400 mb-1 text-xs">{t('presetModal.subsequentLayers')}</label>
                          <div className="relative">
                          <input
                            type="number"
                            value={bedTemp}
                            onChange={(e) => { setBedTemp(Number(e.target.value)); }}
                            min={0}
                            max={120}
                            step="1"
                            placeholder="90"
                            className={`w-full pl-3 pr-10 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                          />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">°C</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Ограничение объёмного расхода */}
                <div>
                  <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.volumetricLimit')}</h4>
                  
                  <div className="space-y-3">
                    <div className="flex items-center space-x-3">
                      <input
                        type="checkbox"
                        id="adaptiveVolumetricSpeed"
                        checked={adaptiveVolumetricSpeed}
                        onChange={(e) => { setAdaptiveVolumetricSpeed(e.target.checked); }}
                        className="w-4 h-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
                      />
                      <label htmlFor="adaptiveVolumetricSpeed" className="text-gray-300 text-sm">
                        {t('presetModal.adaptiveVolumetricSpeed')}
                      </label>
                    </div>

                    <div>
                      <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.maxVolumetricSpeed')}</label>
                      <div className="relative">
                        <input
                          type="number"
                          value={volumetricSpeed}
                          onChange={(e) => { setVolumetricSpeed(e.target.value === '' ? '' : Number(e.target.value)); }}
                          min={1}
                          max={100}
                          step="0.1"
                          placeholder="12"
                          className={`w-full pl-3 pr-16 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                        />
                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm³/s</span>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
              )}

              {activeTab === 'cooling' && (
                <div className="space-y-6">
                  {/* Обдув определенного слоя */}
                  <div>
                    <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.layerFanControl')}</h4>
                    
                    <div className="space-y-4">
                      {/* Не включать вентилятор на первых */}
                      <div>
                        <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.disableFanFirstLayers')}</label>
                        <div className="relative">
                          <input
                            type="number"
                            value={closeFanFirstXLayers}
                            onChange={(e) => { setCloseFanFirstXLayers(e.target.value === '' ? '' : Number(e.target.value)); }}
                            min={0}
                            step="1"
                            placeholder="3"
                            className={`w-full pl-3 pr-16 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                          />
                          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">{t('presetModal.layers')}</span>
                        </div>
                      </div>

                      {/* Полная скорость вентилятора на слое */}
                      <div>
                        <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.fullFanSpeedLayer')}</label>
                        <div className="relative">
                          <input
                            type="number"
                            value={fullFanSpeedLayer}
                            onChange={(e) => { setFullFanSpeedLayer(e.target.value === '' ? '' : Number(e.target.value)); }}
                            min={0}
                            step="1"
                            placeholder="0"
                            className={`w-full pl-3 pr-16 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                          />
                          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">{t('presetModal.layer')}</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Обдув модели */}
                  <div>
                    <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.partCooling')}</h4>
                    
                    <div className="space-y-4">
                      {/* Порог мин. скорости вентилятора */}
                      <div>
                        <label className="block text-gray-300 mb-2 text-sm font-medium">{t('presetModal.minFanThreshold')}</label>
                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <label className="block text-gray-400 mb-1 text-xs">{t('presetModal.fanSpeedLabel')}</label>
                            <div className="relative">
                              <input
                                type="number"
                                value={fanMinSpeed}
                                onChange={(e) => { setFanMinSpeed(e.target.value === '' ? '' : Number(e.target.value)); }}
                                min={0}
                                max={100}
                                step="1"
                                placeholder="10"
                                className={`w-full pl-3 pr-8 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                              />
                              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">%</span>
                            </div>
                          </div>
                          <div>
                            <label className="block text-gray-400 mb-1 text-xs">{t('presetModal.layerTime')}</label>
                            <div className="relative">
                              <input
                                type="number"
                                value={fanCoolingLayerTime}
                                onChange={(e) => { setFanCoolingLayerTime(e.target.value === '' ? '' : Number(e.target.value)); }}
                                min={0}
                                step="1"
                                placeholder="30"
                                className={`w-full pl-3 pr-8 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                              />
                              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">{t('presetModal.units.sec')}</span>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Порог макс. скорости вентилятора */}
                      <div>
                        <label className="block text-gray-300 mb-2 text-sm font-medium">{t('presetModal.maxFanThreshold')}</label>
                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <label className="block text-gray-400 mb-1 text-xs">{t('presetModal.fanSpeedLabel')}</label>
                            <div className="relative">
                              <input
                                type="number"
                                value={fanMaxSpeed}
                                onChange={(e) => { setFanMaxSpeed(e.target.value === '' ? '' : Number(e.target.value)); }}
                                min={0}
                                max={100}
                                step="1"
                                placeholder="80"
                                className={`w-full pl-3 pr-8 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                              />
                              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">%</span>
                            </div>
                          </div>
                          <div>
                            <label className="block text-gray-400 mb-1 text-xs">{t('presetModal.layerTime')}</label>
                            <div className="relative">
                                <input
                                type="number"
                                value={fanMaxSpeedLayerTime}
                                onChange={(e) => { setFanMaxSpeedLayerTime(e.target.value === '' ? '' : Number(e.target.value)); }}
                                min={0}
                                step="1"
                                placeholder="3"
                                className={`w-full pl-3 pr-8 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                              />
                              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">{t('presetModal.units.sec')}</span>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Обдув включён всегда (reduce_fan_stop_start_freq в OrcaSlicer) */}
                      <div className="flex items-center space-x-3">
                        <input
                          type="checkbox"
                          id="reduceFanStopStartFreq"
                          checked={reduceFanStopStartFreq}
                          onChange={(e) => { setReduceFanStopStartFreq(e.target.checked); }}
                          className="w-4 h-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
                        />
                        <label htmlFor="reduceFanStopStartFreq" className="text-gray-300 text-sm">
                          {t('presetModal.fanAlwaysOn')}
                        </label>
                      </div>

                      {/* Замедлять печать для лучшего охлаждения слоёв */}
                      <div className="flex items-center space-x-3">
                        <input
                          type="checkbox"
                          id="slowDownForLayerCooling"
                          checked={slowDownForLayerCooling}
                          onChange={(e) => { setSlowDownForLayerCooling(e.target.checked); }}
                          className="w-4 h-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
                        />
                        <label htmlFor="slowDownForLayerCooling" className="text-gray-300 text-sm">
                          {t('presetModal.slowDownForCooling')}
                        </label>
                      </div>

                      {/* Не замедляться на внешнем периметре */}
                      <div className="flex items-center space-x-3">
                        <input
                          type="checkbox"
                          id="dontSlowDownOuterWall"
                          checked={dontSlowDownOuterWall}
                          onChange={(e) => { setDontSlowDownOuterWall(e.target.checked); }}
                          className="w-4 h-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
                        />
                        <label htmlFor="dontSlowDownOuterWall" className="text-gray-300 text-sm">
                          {t('presetModal.dontSlowOuterWall')}
                        </label>
                      </div>

                      {/* Минимальная скорость печати */}
                      {slowDownForLayerCooling && (
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.minPrintSpeed')}</label>
                          <input
                            type="number"
                            value={slowDownMinSpeed}
                            onChange={(e) => { setSlowDownMinSpeed(e.target.value === '' ? '' : Number(e.target.value)); }}
                            min={0}
                            step="1"
                            placeholder="10"
                            className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                          />
                          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm/s</span>
                        </div>
                      )}

                      {/* Принудительный обдув нависаний и мостов */}
                      <div className="flex items-center space-x-3">
                        <input
                          type="checkbox"
                          id="enableOverhangBridgeFan"
                          checked={enableOverhangBridgeFan}
                          onChange={(e) => { setEnableOverhangBridgeFan(e.target.checked); }}
                          className="w-4 h-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
                        />
                        <label htmlFor="enableOverhangBridgeFan" className="text-gray-300 text-sm">
                          {t('presetModal.forceOverhangBridgeFan')}
                        </label>
                      </div>

                      {/* Порог нависания для включения обдува */}
                      {enableOverhangBridgeFan && (
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.overhangFanThreshold')}</label>
                          <div className="relative">
                            <input
                              type="text"
                              value={overhangFanThreshold}
                              onChange={(e) => { setOverhangFanThreshold(e.target.value); }}
                              placeholder="25"
                              className={`w-full pl-3 pr-8 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">%</span>
                          </div>
                        </div>
                      )}

                      {/* Скорость вентилятора для нависаний и внешних мостов */}
                      {enableOverhangBridgeFan && (
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.overhangBridgeFanSpeed')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={overhangFanSpeed}
                              onChange={(e) => { setOverhangFanSpeed(e.target.value === '' ? '' : Number(e.target.value)); }}
                              min={-1}
                              max={100}
                              step="1"
                              placeholder="80"
                              className={`w-full pl-3 pr-8 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">%</span>
                          </div>
                          <p className="text-xs text-gray-500 mt-1">{t('presetModal.minusOneDefault')}</p>
                        </div>
                      )}

                      {/* Скорость вентилятора для внутренних мостов */}
                      {enableOverhangBridgeFan && (
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.internalBridgeFanSpeed')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={internalBridgeFanSpeed}
                              onChange={(e) => { setInternalBridgeFanSpeed(e.target.value === '' ? '' : Number(e.target.value)); }}
                              min={-1}
                              max={100}
                              step="1"
                              placeholder="-1"
                              className={`w-full pl-3 pr-8 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">%</span>
                          </div>
                          <p className="text-xs text-gray-500 mt-1">{t('presetModal.minusOneDefault')}</p>
                        </div>
                      )}

                      {/* Скорость вентилятора на связующем слое */}
                      {enableOverhangBridgeFan && (
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.supportInterfaceFanSpeed')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={supportMaterialInterfaceFanSpeed}
                              onChange={(e) => { setSupportMaterialInterfaceFanSpeed(e.target.value === '' ? '' : Number(e.target.value)); }}
                              min={-1}
                              max={100}
                              step="1"
                              placeholder="-1"
                              className={`w-full pl-3 pr-8 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">%</span>
                          </div>
                          <p className="text-xs text-gray-500 mt-1">{t('presetModal.minusOneDefault')}</p>
                        </div>
                      )}

                      {/* Ironing fan speed */}
                      <div>
                        <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.ironingFanSpeed')}</label>
                        <div className="relative">
                          <input
                            type="number"
                            value={ironingFanSpeed}
                            onChange={(e) => { setIroningFanSpeed(e.target.value === '' ? '' : Number(e.target.value)); }}
                            min={-1}
                            max={100}
                            step="1"
                            placeholder="-1"
                            className={`w-full pl-3 pr-8 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                          />
                          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">%</span>
                        </div>
                        <p className="text-xs text-gray-500 mt-1">{t('presetModal.defaultMinusOne')}</p>
                      </div>
                    </div>
                  </div>

                  {/* Вспомогательный вентилятор модели */}
                  <div>
                    <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.auxiliaryFan')}</h4>
                    
                    <div>
                      <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.fanSpeedLabel')}</label>
                      <div className="relative">
                        <input
                          type="number"
                          value={additionalCoolingFanSpeed}
                          onChange={(e) => { setAdditionalCoolingFanSpeed(e.target.value === '' ? '' : Number(e.target.value)); }}
                          min={0}
                          max={100}
                          step="1"
                          placeholder="0"
                          className={`w-full pl-3 pr-8 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                        />
                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">%</span>
                      </div>
                    </div>
                  </div>

                  {/* Вытяжной вентилятор */}
                  <div>
                    <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.exhaustFan')}</h4>
                    
                    <div className="space-y-3">
                      <div className="flex items-center space-x-3">
                        <input
                          type="checkbox"
                          id="enableExhaustFan"
                          checked={enableExhaustFan}
                          onChange={(e) => { setEnableExhaustFan(e.target.checked); }}
                          className="w-4 h-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
                        />
                        <label htmlFor="enableExhaustFan" className="text-gray-300 text-sm">
                          {t('presetModal.enableExhaustFan')}
                        </label>
                      </div>

                      {enableExhaustFan && (
                        <>
                          <div>
                            <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.exhaustFanDuringPrint')}</label>
                            <div className="relative">
                              <input
                                type="number"
                                value={duringPrintExhaustFanSpeed}
                                onChange={(e) => { setDuringPrintExhaustFanSpeed(e.target.value === '' ? '' : Number(e.target.value)); }}
                                min={0}
                                max={100}
                                step="1"
                                placeholder="70"
                                className={`w-full pl-3 pr-8 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                              />
                              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">%</span>
                            </div>
                          </div>

                          <div>
                            <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.exhaustFanAfterPrint')}</label>
                            <div className="relative">
                              <input
                                type="number"
                                value={completePrintExhaustFanSpeed}
                                onChange={(e) => { setCompletePrintExhaustFanSpeed(e.target.value === '' ? '' : Number(e.target.value)); }}
                                min={0}
                                max={100}
                                step="1"
                                placeholder="70"
                                className={`w-full pl-3 pr-8 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                              />
                              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">%</span>
                            </div>
                          </div>

                          <div className="flex items-center space-x-3">
                            <input
                              type="checkbox"
                              id="activateAirFiltration"
                              checked={activateAirFiltration}
                              onChange={(e) => { setActivateAirFiltration(e.target.checked); }}
                              className="w-4 h-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
                            />
                            <label htmlFor="activateAirFiltration" className="text-gray-300 text-sm">
                              {t('presetModal.activateAirFilter')}
                            </label>
                          </div>
                        </>
                      )}
                    </div>
                  </div>

                </div>
              )}

              {activeTab === 'override' && (
                <div className="space-y-6">
                  {/* Скорости и замедления */}
                  <div>
                    <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.speedsAndSlowdowns')}</h4>
                    
                    <div className="space-y-4">
                      {/* Замедлять печать для лучшего охлаждения слоёв */}
                      <div className="flex items-center space-x-3">
                        <input
                          type="checkbox"
                          id="slowDownForLayerCoolingOverride"
                          checked={slowDownForLayerCooling}
                          onChange={(e) => { setSlowDownForLayerCooling(e.target.checked); }}
                          className="w-4 h-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
                        />
                        <label htmlFor="slowDownForLayerCoolingOverride" className="text-gray-300 text-sm">
                          {t('presetModal.slowDownForCooling')}
                        </label>
                      </div>

                      {/* Не замедляться на внешнем периметре */}
                      <div className="flex items-center space-x-3">
                        <input
                          type="checkbox"
                          id="dontSlowDownOuterWallOverride"
                          checked={dontSlowDownOuterWall}
                          onChange={(e) => { setDontSlowDownOuterWall(e.target.checked); }}
                          className="w-4 h-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
                        />
                        <label htmlFor="dontSlowDownOuterWallOverride" className="text-gray-300 text-sm">
                          {t('presetModal.dontSlowOuterWall')}
                        </label>
                      </div>

                      {/* Минимальная скорость печати */}
                      {slowDownForLayerCooling && (
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.minPrintSpeed')}</label>
                          <input
                            type="number"
                            value={slowDownMinSpeed}
                            onChange={(e) => { setSlowDownMinSpeed(e.target.value === '' ? '' : Number(e.target.value)); }}
                            min={0}
                            step="1"
                            placeholder="10"
                            className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                          />
                          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm/s</span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Откат */}
                  <div>
                    <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.retraction')}</h4>
                    
                    <div className="space-y-4">
                      {/* Первая строка: Длина / Скорость извлечения */}
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.length')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={retractionLength}
                              onChange={(e) => { setRetractionLength(Number(e.target.value)); }}
                              min={0}
                              max={10}
                              step="0.1"
                              placeholder="0.8"
                              className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm</span>
                          </div>
                          <p className="text-xs text-gray-500 mt-1">{t('presetModal.syncsWithBase')}</p>
                        </div>
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.retractionExtractSpeed')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={retractionSpeed}
                              onChange={(e) => { setRetractionSpeed(Number(e.target.value)); }}
                              min={0}
                              max={100}
                              step="1"
                              placeholder="30"
                              className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm/s</span>
                          </div>
                          <p className="text-xs text-gray-500 mt-1">{t('presetModal.syncsWithBase')}</p>
                        </div>
                      </div>

                      {/* Вторая строка: Высота поднятия оси Z / Скорость заправки */}
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.zHopHeight')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={filamentZHop}
                              onChange={(e) => { setFilamentZHop(e.target.value === '' ? '' : Number(e.target.value)); }}
                              min={0}
                              max={5}
                              step="0.1"
                              placeholder="0.4"
                              className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm</span>
                          </div>
                        </div>
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.deretractionSpeed')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={deretractionSpeed}
                              onChange={(e) => { setDeretractionSpeed(e.target.value === '' ? '' : Number(e.target.value)); }}
                              min={0}
                              max={100}
                              step="1"
                              placeholder="30"
                              className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm/s</span>
                          </div>
                        </div>
                      </div>

                      {/* Третья строка: Тип подъёма оси Z / На поверхностях */}
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.zHopType')}</label>
                          <CustomSelect
                            value={filamentZHopTypes || null}
                            onChange={(value: string | number | null) => {  setFilamentZHopTypes(value as string || ''); }}
                            options={[
                              { value: '', label: t('presetModal.default') },
                              { value: 'Normal', label: t('presetModal.zHopNormal') },
                              { value: 'Spiral', label: t('presetModal.zHopSpiral') },
                              { value: 'AutoLift', label: t('presetModal.zHopAutoLift') },
                            ]}
                            placeholder={t('presetModal.default')}
                          />
                        </div>
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.onSurfaces')}</label>
                          <CustomSelect
                            value={retractLiftEnforce || null}
                            onChange={(value: string | number | null) => {  setRetractLiftEnforce(value as string || ''); }}
                            options={[
                              { value: '', label: t('presetModal.default') },
                              { value: 'All', label: t('presetModal.allTop') },
                              { value: 'TopOnly', label: t('presetModal.topOnly') },
                              { value: 'None', label: t('presetModal.none') },
                            ]}
                            placeholder={t('presetModal.default')}
                          />
                        </div>
                      </div>

                      {/* Четвертая строка: Приподнимать ось Z только выше / Приподнимать ось Z только ниже */}
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.liftZAbove')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={retractLiftAbove}
                              onChange={(e) => { setRetractLiftAbove(e.target.value === '' ? '' : Number(e.target.value)); }}
                              min={0}
                              step="0.1"
                              placeholder="0"
                              className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm</span>
                          </div>
                        </div>
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.liftZBelow')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={retractLiftBelow}
                              onChange={(e) => { setRetractLiftBelow(e.target.value === '' ? '' : Number(e.target.value)); }}
                              min={0}
                              step="0.1"
                              placeholder="0"
                              className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm</span>
                          </div>
                        </div>
                      </div>

                      {/* Пятая строка: Доп. длина подачи / Порог перемещения */}
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.extraRestartLength')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={retractRestartExtra}
                              onChange={(e) => { setRetractRestartExtra(e.target.value === '' ? '' : Number(e.target.value)); }}
                              min={0}
                              step="0.1"
                              placeholder="0"
                              className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm</span>
                          </div>
                        </div>
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.retractionMinTravel')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={retractionMinimumTravel}
                              onChange={(e) => { setRetractionMinimumTravel(e.target.value === '' ? '' : Number(e.target.value)); }}
                              min={0}
                              step="0.1"
                              placeholder="1"
                              className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm</span>
                          </div>
                        </div>
                      </div>

                      {/* Чекбоксы: Откат при смене слоя / Очистка сопла */}
                      <div className="grid grid-cols-2 gap-4">
                        <div className="flex items-center space-x-3">
                          <input
                            type="checkbox"
                            id="retractWhenChangingLayerOverride"
                            checked={retractWhenChangingLayer}
                            onChange={(e) => { setRetractWhenChangingLayer(e.target.checked); }}
                            className="w-4 h-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
                          />
                          <label htmlFor="retractWhenChangingLayerOverride" className="text-gray-300 text-sm">
                            {t('presetModal.retractOnLayerChange')}
                          </label>
                        </div>
                        <div className="flex items-center space-x-3">
                          <input
                            type="checkbox"
                            id="filamentWipeOverride"
                            checked={filamentWipe}
                            onChange={(e) => { setFilamentWipe(e.target.checked); }}
                            className="w-4 h-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
                          />
                          <label htmlFor="filamentWipeOverride" className="text-gray-300 text-sm">
                            {t('presetModal.wipeOnRetract')}
                          </label>
                        </div>
                      </div>

                      {/* Расстояние очистки / Величина отката перед очисткой */}
                      {filamentWipe && (
                        <div className="grid grid-cols-2 gap-4">
                          <div>
                            <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.wipeDistance')}</label>
                            <div className="relative">
                              <input
                                type="number"
                                value={filamentWipeDistance}
                                onChange={(e) => { setFilamentWipeDistance(e.target.value === '' ? '' : Number(e.target.value)); }}
                                min={0}
                                step="0.1"
                                placeholder="1"
                                className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                              />
                              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm</span>
                            </div>
                          </div>
                          <div>
                            <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.retractBeforeWipe')}</label>
                            <div className="relative">
                              <input
                                type="text"
                                value={retractBeforeWipe}
                                onChange={(e) => { setRetractBeforeWipe(e.target.value); }}
                                placeholder="70"
                                className={`w-full pl-3 pr-8 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                              />
                              <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">%</span>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Дополнительные параметры ретракта */}
                  <div>
                    <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.additionalRetractParams')}</h4>
                    
                    <div className="space-y-4">
                      {/* Первая строка: Расстояния при обрезке / Длинные ретракты при обрезке */}
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.retractDistanceCut')}</label>
                          <input
                            type="text"
                            value={retractionDistancesWhenCut}
                            onChange={(e) => { setRetractionDistancesWhenCut(e.target.value); }}
                            placeholder="0,0,0"
                            className={`w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                          />
                          <p className="text-xs text-gray-500 mt-1">{t('presetModal.commaSeparatedValues')}</p>
                        </div>
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.longRetractsCut')}</label>
                          <input
                            type="text"
                            value={longRetractionsWhenCut}
                            onChange={(e) => { setLongRetractionsWhenCut(e.target.value); }}
                            placeholder="nil"
                            className={`w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                          />
                        </div>
                      </div>

                      {/* Длинные ретракты при смене экструдера */}
                      <div className="flex items-center space-x-3">
                        <input
                          type="checkbox"
                          id="longRetractionsWhenEC"
                          checked={longRetractionsWhenEC}
                          onChange={(e) => { setLongRetractionsWhenEC(e.target.checked); }}
                          className="w-4 h-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
                        />
                        <label htmlFor="longRetractionsWhenEC" className="text-gray-300 text-sm">
                          {t('presetModal.longRetractsEC')}
                        </label>
                      </div>

                      {/* Расстояния ретракта при смене экструдера */}
                      {longRetractionsWhenEC && (
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.retractDistanceEC')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={retractionDistancesWhenEC}
                              onChange={(e) => { setRetractionDistancesWhenEC(e.target.value === '' ? '' : Number(e.target.value)); }}
                              min={0}
                              step="0.1"
                              placeholder="0"
                              className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm</span>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'advanced' && (
                <div className="space-y-6">
                  {/* G-code */}
                  <div>
                    <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10 flex items-center space-x-2">
                      <span className="text-gray-400">&lt; &gt;</span>
                      <span>{t('presetModal.startGcode')}</span>
                    </h4>
                    
                    <div 
                      className="flex items-start space-x-3"
                      onClick={(e) => e.stopPropagation()}
                      onMouseDown={(e) => e.stopPropagation()}
                    >
                      <textarea
                        id="filament-start-gcode"
                        value={filamentStartGcode}
                        onChange={(e) => { setFilamentStartGcode(e.target.value); }}
                        placeholder="; Filament gcode"
                        rows={12}
                        className={`flex-1 px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all resize-none `}
                        style={{ fontFamily: 'monospace' }}
                        onClick={(e) => e.stopPropagation()}
                        onMouseDown={(e) => e.stopPropagation()}
                      />
                      <EditGCodeModal
                        isOpen={activeTab === 'advanced'}
                        onClose={() => {}}
                        onInsert={(placeholderText) => {
                          const textarea = document.getElementById('filament-start-gcode') as HTMLTextAreaElement;
                          if (textarea) {
                            const start = textarea.selectionStart;
                            const end = textarea.selectionEnd;
                            const text = filamentStartGcode;
                            const before = text.substring(0, start);
                            const after = text.substring(end);
                            const newValue = before + placeholderText + after;
                            setFilamentStartGcode(newValue);
                            
                            setTimeout(() => {
                              const newCursorPos = start + placeholderText.length;
                              textarea.setSelectionRange(newCursorPos, newCursorPos);
                              textarea.focus();
                            }, 0);
                          }
                        }}
                        title="Placeholders"
                        gcodeType="filament_start_gcode"
                      />
                    </div>
                    <p className="text-xs text-gray-500 mt-2">
                      {t('presetModal.startGcodeHint')}
                    </p>
                  </div>

                  <div>
                    <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10 flex items-center space-x-2">
                      <span className="text-gray-400">&lt; &gt;</span>
                      <span>{t('presetModal.endGcode')}</span>
                    </h4>
                    
                    <div 
                      className="flex items-start space-x-3"
                      onClick={(e) => e.stopPropagation()}
                      onMouseDown={(e) => e.stopPropagation()}
                    >
                      <textarea
                        id="filament-end-gcode"
                        value={filamentEndGcode}
                        onChange={(e) => { setFilamentEndGcode(e.target.value); }}
                        placeholder="; filament end gcode"
                        rows={12}
                        className={`flex-1 px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all resize-none `}
                        style={{ fontFamily: 'monospace' }}
                        onClick={(e) => e.stopPropagation()}
                        onMouseDown={(e) => e.stopPropagation()}
                      />
                      <EditGCodeModal
                        isOpen={activeTab === 'advanced'}
                        onClose={() => {}}
                        onInsert={(placeholderText) => {
                          const textarea = document.getElementById('filament-end-gcode') as HTMLTextAreaElement;
                          if (textarea) {
                            const start = textarea.selectionStart;
                            const end = textarea.selectionEnd;
                            const text = filamentEndGcode;
                            const before = text.substring(0, start);
                            const after = text.substring(end);
                            const newValue = before + placeholderText + after;
                            setFilamentEndGcode(newValue);
                            
                            setTimeout(() => {
                              const newCursorPos = start + placeholderText.length;
                              textarea.setSelectionRange(newCursorPos, newCursorPos);
                              textarea.focus();
                            }, 0);
                          }
                        }}
                        title="Placeholders"
                        gcodeType="filament_end_gcode"
                      />
                    </div>
                    <p className="text-xs text-gray-500 mt-2">
                      {t('presetModal.endGcodeHint')}
                    </p>
                  </div>

                </div>
              )}

              {activeTab === 'extruder' && (
                <div className="space-y-6">
                  {/* Параметры экструдера */}
                  <div>
                    <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.extruderParams')}</h4>
                    
                    <div className="grid grid-cols-2 gap-4">
                      {/* Вариант экструдера */}
                      <div>
                        <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.extruderVariant')}</label>
                        <input
                          type="text"
                          value={filamentExtruderVariant}
                          onChange={(e) => { setFilamentExtruderVariant(e.target.value); }}
                          placeholder="Direct Drive Standard"
                          className={`w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                        />
                        <p className="text-xs text-gray-500 mt-1">{t('presetModal.extruderVariantHint')}</p>
                      </div>

                      {/* Требуемая твердость сопла HRC */}
                      <div>
                        <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.nozzleHRC')}</label>
                        <div className="relative">
                          <input
                            type="number"
                            value={requiredNozzleHRC}
                            onChange={(e) => { setRequiredNozzleHRC(e.target.value === '' ? '' : Number(e.target.value)); }}
                            min={0}
                            max={100}
                            step="1"
                            placeholder="3"
                            className={`w-full pl-3 pr-10 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                          />
                          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">HRC</span>
                        </div>
                        <p className="text-xs text-gray-500 mt-1">{t('presetModal.nozzleHRCHint')}</p>
                      </div>
                    </div>
                  </div>

                  {/* Параметры черновой башни */}
                  <div>
                    <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.wipeTowerParams')}</h4>
                    
                    <div>
                      <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.minPurgeVolume')}</label>
                      <div className="relative">
                        <input
                          type="number"
                          value={filamentMinimalPurgeOnWipeTower}
                          onChange={(e) => { setFilamentMinimalPurgeOnWipeTower(e.target.value === '' ? '' : Number(e.target.value)); }}
                          min={0}
                          step="0.1"
                          placeholder="15"
                          className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                        />
                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm³</span>
                      </div>
                    </div>
                  </div>

                  {/* Параметры смены инструмента в одноэкструдерных мультиматериальных принтерах */}
                  <div>
                    <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.singleExtruderToolchange')}</h4>
                    
                    <div className="space-y-4">
                      {/* Первая строка: Начальная скорость загрузки / Скорость загрузки */}
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.loadingSpeedStart')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={filamentLoadingSpeedStart}
                              onChange={(e) => { setFilamentLoadingSpeedStart(e.target.value === '' ? '' : Number(e.target.value)); }}
                              min={0}
                              step="1"
                              placeholder="3"
                              className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm/s</span>
                          </div>
                        </div>

                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.loadingSpeed')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={filamentLoadingSpeed}
                              onChange={(e) => { setFilamentLoadingSpeed(e.target.value === '' ? '' : Number(e.target.value)); }}
                              min={0}
                              step="1"
                              placeholder="28"
                              className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm/s</span>
                          </div>
                        </div>
                      </div>

                      {/* Вторая строка: Начальная скорость выгрузки / Скорость выгрузки */}
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.unloadingSpeedStart')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={filamentUnloadingSpeedStart}
                              onChange={(e) => { setFilamentUnloadingSpeedStart(e.target.value === '' ? '' : Number(e.target.value)); }}
                              min={0}
                              step="1"
                              placeholder="100"
                              className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm/s</span>
                          </div>
                        </div>

                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.unloadingSpeed')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={filamentUnloadingSpeed}
                              onChange={(e) => { setFilamentUnloadingSpeed(e.target.value === '' ? '' : Number(e.target.value)); }}
                              min={0}
                              step="1"
                              placeholder="90"
                              className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm/s</span>
                          </div>
                        </div>
                      </div>

                      {/* Третья строка: Задержка после выгрузки / Количество охлаждающих движений */}
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.toolchangeDelay')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={filamentToolchangeDelay}
                              onChange={(e) => { setFilamentToolchangeDelay(e.target.value === '' ? '' : Number(e.target.value)); }}
                              min={0}
                              step="0.1"
                              placeholder="0"
                              className={`w-full pl-3 pr-8 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">s</span>
                          </div>
                        </div>

                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.coolingMoves')}</label>
                          <input
                            type="number"
                            value={filamentCoolingMoves}
                            onChange={(e) => { setFilamentCoolingMoves(e.target.value === '' ? '' : Number(e.target.value)); }}
                            min={0}
                            step="1"
                            placeholder="4"
                            className={`w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                          />
                        </div>
                      </div>

                      {/* Четвертая строка: Скорость первого охлаждающего движения / Скорость последнего охлаждающего движения */}
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.coolingInitialSpeed')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={filamentCoolingInitialSpeed}
                              onChange={(e) => { setFilamentCoolingInitialSpeed(e.target.value === '' ? '' : Number(e.target.value)); }}
                              min={0}
                              step="0.1"
                              placeholder="2.2"
                              className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm/s</span>
                          </div>
                        </div>

                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.coolingFinalSpeed')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={filamentCoolingFinalSpeed}
                              onChange={(e) => { setFilamentCoolingFinalSpeed(e.target.value === '' ? '' : Number(e.target.value)); }}
                              min={0}
                              step="0.1"
                              placeholder="3.4"
                              className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm/s</span>
                          </div>
                        </div>
                      </div>

                      {/* Пятая строка: Скорость загрузки при утрамбовке / Расстояние утрамбовки */}
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.stampingLoadSpeed')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={filamentStampingLoadingSpeed}
                              onChange={(e) => { setFilamentStampingLoadingSpeed(e.target.value === '' ? '' : Number(e.target.value)); }}
                              min={0}
                              step="1"
                              placeholder="0"
                              className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm/s</span>
                          </div>
                        </div>

                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.stampingDistance')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={filamentStampingDistance}
                              onChange={(e) => { setFilamentStampingDistance(e.target.value === '' ? '' : Number(e.target.value)); }}
                              min={0}
                              step="0.1"
                              placeholder="0"
                              className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Параметры смены инструмента в многоэкструдерных мультиматериальных принтерах */}
                  <div>
                    <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.multiExtruderToolchange')}</h4>
                    
                    <div className="space-y-4">
                      {/* Включить рэмминг для многоинструментального принтера */}
                      <div className="flex items-center space-x-3">
                        <input
                          type="checkbox"
                          id="filamentMultitoolRammingExtruder"
                          checked={filamentMultitoolRamming}
                          onChange={(e) => { setFilamentMultitoolRamming(e.target.checked); }}
                          className="w-4 h-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
                        />
                        <label htmlFor="filamentMultitoolRammingExtruder" className="text-gray-300 text-sm">
                          {t('presetModal.enableMultitoolRamming')}
                        </label>
                      </div>

                      {/* Объём рэмминга многоинструментального принтера / Поток рэмминга многоинструментального принтера */}
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.multitoolRammingVolume')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={filamentMultitoolRammingVolume}
                              onChange={(e) => { setFilamentMultitoolRammingVolume(e.target.value === '' ? '' : Number(e.target.value)); }}
                              min={0}
                              step="0.1"
                              placeholder="10"
                              className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm³</span>
                          </div>
                        </div>

                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.multitoolRammingFlow')}</label>
                          <div className="relative">
                            <input
                              type="number"
                              value={filamentMultitoolRammingFlow}
                              onChange={(e) => { setFilamentMultitoolRammingFlow(e.target.value === '' ? '' : Number(e.target.value)); }}
                              min={0}
                              step="0.1"
                              placeholder="10"
                              className={`w-full pl-3 pr-16 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm³/s</span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Дополнительные параметры */}
                  <div>
                    <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.additionalParams')}</h4>
                    
                    <div className="grid grid-cols-2 gap-4">
                      {/* Длина смены филамента */}
                      <div>
                        <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.filamentChangeLength')}</label>
                        <div className="relative">
                          <input
                            type="number"
                            value={filamentChangeLength}
                            onChange={(e) => { setFilamentChangeLength(e.target.value === '' ? '' : Number(e.target.value)); }}
                            min={0}
                            step="0.1"
                            placeholder="0"
                            className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                          />
                          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm</span>
                        </div>
                      </div>

                      {/* Коэффициент потока пеллет */}
                      <div>
                        <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.pelletFlowCoeff')}</label>
                        <input
                          type="number"
                          value={pelletFlowCoefficient}
                          onChange={(e) => { setPelletFlowCoefficient(e.target.value === '' ? '' : Number(e.target.value)); }}
                          min={0}
                          step="0.01"
                          placeholder="1.0"
                          className={`w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                        />
                        <p className="text-xs text-gray-500 mt-1">{t('presetModal.pelletFlowHint')}</p>
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {activeTab === 'notes' && (
                <div className="space-y-4">
                  <div>
                    <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.notes')}</h4>
                    <textarea
                      value={filamentNotes}
                      onChange={(e) => { setFilamentNotes(e.target.value); }}
                      placeholder={t('presetModal.notesPlaceholder')}
                      rows={10}
                      className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all resize-none"
                    />
                    <p className="text-xs text-gray-500 mt-2">{t('presetModal.notesHint')}</p>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Actions */}
          <div className="flex flex-col gap-3 pt-4 border-t border-white/10 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-h-[1rem]">
              {submitBlockReason && (
                <p className="text-xs text-amber-300">{submitBlockReason}</p>
              )}
            </div>
            <div className="flex items-center space-x-3 self-end sm:self-auto">
              <button
                type="button"
                onClick={onClose}
                disabled={isLoading}
                className="px-6 py-3 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all disabled:opacity-50"
              >
                {t('presetModal.cancel')}
              </button>
              <button
                type="submit"
                disabled={isSubmitDisabled}
                className="px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-xl transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
              >
                {isLoading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>{t('presetModal.saving')}</span>
                  </>
                ) : (
                  <>
                    <Save className="w-4 h-4" />
                    <span>{preset ? t('presetModal.save') : t('presetModal.create')}</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </form>
        </div>
      </div>
    </ModalOverlay>
  );
};
