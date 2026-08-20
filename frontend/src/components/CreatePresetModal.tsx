/** Модальное окно для создания/редактирования пресета */

import { useState, useEffect, FormEvent, useRef, useMemo } from 'react';
import React from 'react';
import { useTranslation } from 'react-i18next';
import { X, Save, Loader2, Check, Plus, CheckCircle, Sparkles } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { achievementsAPI, presetsAPI, filamentsAPI, brandsAPI, printersAPI } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { useAuth } from '../contexts/AuthContext';
import type {
  AchievementCode,
  AchievementOverview,
  FilamentAdditive,
  FilamentPropertyClaim,
  Preset,
  Filament,
  Brand,
  Printer,
} from '../types/api';
import { applyMaterialDefaults, sortMaterialTypes } from '../data/materialDefaults';
import { type SettingMode, isVisibleAtMode } from '../data/orcaFieldModes';
import { safeStorage } from '../utils/storage';
import { densityForMaterial, STANDARD_DIAMETERS } from '../utils/materialDensity';
import { MaterialTypeSelect } from './MaterialTypeSelect';
import { EditGCodeModal } from './EditGCodeModal';
import { CustomSelect } from './CustomSelect';
import type { FilamentVisualSettings } from '../types/api';
import { Dropdown } from './Dropdown';
import { useClickOutside } from '../hooks/useClickOutside';
import { ModalOverlay } from './ModalOverlay';
import { InfoHint } from './InfoHint';
import { ConfirmModal } from './ConfirmModal';
import { RecommendedTempsField, EMPTY_RECOMMENDED_TEMPS } from './RecommendedTempsField';
import type { RecommendedTemps } from './RecommendedTempsField';
import { NozzleHardnessField } from './NozzleHardnessField';
import { useDebounce } from '../hooks/useDebounce';
import { ColorMaterialSection } from './ColorMaterialSection';
import { FloatingHSLColorPicker } from './FloatingHSLColorPicker';
import { FilamentFeaturesEditor } from './FilamentFeaturesEditor';
import { mergeVisualEffects } from '../data/filamentFeatures';
import { currencySymbol } from '../utils/currency';
import {
  applyOrcaBooleanFromUi,
  applyOrcaLinesFromUi,
  applyOrcaUiSetting,
  cloneOrcaSettings,
  firstOrcaSetting,
  formatOrcaFlowRatio,
  isOrcaBedTemperatureSentinel,
  normalizeOrcaSettingsForUi,
  ORCA_MAX_BED_TEMPERATURE,
  ORCA_MAX_NOZZLE_TEMPERATURE,
  readOrcaNumber,
  readOrcaText,
} from '../utils/orcaPresetSettings';

import { FilamentSummaryCard } from './FilamentSummaryCard';
import { printerCatalogLabel } from '../utils/printerLabel';
import {
  FilamentHandlingEditor,
  type FilamentHandlingFormValue,
  isHandlingGuidanceComplete,
  normalizeChemicalGuidance,
  parseBedAdhesives,
} from './FilamentHandlingEditor';
import { DensityField } from './DensityField';
import { toast } from './Toast';
import { ACHIEVEMENT_CONFIG } from './Badge';
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
  brandId?: number; // ID бренда для фильтрации материалов в контексте кабинета
  allowOfficial?: boolean; // Официальный статус — отдельное право, не право на создание пресета
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

const isAchievementCode = (code: string): code is AchievementCode => (
  Object.prototype.hasOwnProperty.call(ACHIEVEMENT_CONFIG, code)
);

export const CreatePresetModal: React.FC<CreatePresetModalProps> = ({
  isOpen,
  onClose,
  preset,
  filamentId,
  brandId,
  allowOfficial,
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
  const [retractAfterWipe, setRetractAfterWipe] = useState('');
  const [retractWhenChangingLayer, setRetractWhenChangingLayer] = useState(false);
  const [retractRestartExtra, setRetractRestartExtra] = useState<number | ''>('');
  const [retractLengthToolchange, setRetractLengthToolchange] = useState<number | ''>('');
  const [retractRestartExtraToolchange, setRetractRestartExtraToolchange] = useState<number | ''>('');
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
  const [chamberMinimalTemp, setChamberMinimalTemp] = useState<number | ''>('');
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
  const [initialLayerFanSpeed, setInitialLayerFanSpeed] = useState<number | ''>('');
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
  const [activateAirFiltrationDuringPrint, setActivateAirFiltrationDuringPrint] = useState(true);
  const [activateAirFiltrationOnCompletion, setActivateAirFiltrationOnCompletion] = useState(true);
  
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
  const [filamentChangeExtrusionRoleGcode, setFilamentChangeExtrusionRoleGcode] = useState('');
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
  
  // Вкладка "Зависимости" - НЕ нужна для агрегации (не используется для расчета средних значений)
  // Но нужны для импорта из OrcaSlicer - оставляем сеттеры для загрузки данных
  const [compatiblePrinters, setCompatiblePrinters] = useState('');
  const [compatiblePrintersCondition, setCompatiblePrintersCondition] = useState('');
  const [compatiblePrints, setCompatiblePrints] = useState('');
  const [compatiblePrintsCondition, setCompatiblePrintsCondition] = useState('');
  
  // Вкладка "Заметки"
  const [filamentNotes, setFilamentNotes] = useState('');
  const [activeTab, setActiveTab] = useState<'profile' | 'cooling' | 'override' | 'advanced' | 'extruder' | 'notes'>('profile'); // Активная вкладка (как в OrcaSlicer)
  const [formDirty, setFormDirty] = useState(false);
  const [showDiscardConfirm, setShowDiscardConfirm] = useState(false);
  const requestClose = () => {
    if (formDirty) setShowDiscardConfirm(true);
    else onClose();
  };
  // Уровень сложности (как в OrcaSlicer: Simple/Advanced/Expert). Прячет продвинутые
  // вкладки/поля для новичков; классификация полей — из Orca (orcaFieldModes).
  // Выбор сохраняется — при следующем открытии не нужно переключать заново.
  const [settingMode, setSettingMode] = useState<SettingMode>(() => {
    const saved = safeStorage.get('fh_preset_setting_mode');
    return saved === 'simple' || saved === 'advanced' || saved === 'expert' ? saved : 'advanced';
  });
  useEffect(() => {
    safeStorage.set('fh_preset_setting_mode', settingMode);
    // Если активная вкладка спрятана текущим режимом — вернуться на «Профиль прутка».
    // «override» (Замещение настроек/ретракт) видно и в Simple — как в OrcaSlicer.
    if (!isVisibleAtMode('advanced', settingMode) && (activeTab === 'advanced' || activeTab === 'extruder')) {
      setActiveTab('profile');
    }
  }, [settingMode, activeTab]);
  const [error, setError] = useState<string | null>(null);
  const [duplicateFilamentSuggestion, setDuplicateFilamentSuggestion] = useState<DuplicateFilamentSuggestion | null>(null);
  const [selectedFilamentId, setSelectedFilamentId] = useState<number | null>(filamentId || null);
  
  // Новые поля для создания нового филамента
  const [materialType, setMaterialType] = useState('');
  const [brandSearch, setBrandSearch] = useState('');
  const [selectedBrandId, setSelectedBrandId] = useState<number | null>(null);
  const [filamentName, setFilamentName] = useState('');
  const [filamentColorName, setFilamentColorName] = useState('');
  const [filamentColorHex, setFilamentColorHex] = useState('#FF0000');
  const [draftHasColorEvidence, setDraftHasColorEvidence] = useState(false);
  const [filamentRalCode, setFilamentRalCode] = useState('');
  // Расширенные характеристики цвета для нового филамента
  const [filamentVisualColorType, setFilamentVisualColorType] = useState<'single' | 'two' | 'three' | 'gradient' | 'transition' | 'thermochromic'>('single');
  const [filamentVisualColors, setFilamentVisualColors] = useState<string[]>(['#FF0000']);
  const [filamentVisualFinish, setFilamentVisualFinish] = useState<'matte' | 'glossy'>('matte');
  const [filamentVisualEffects, setFilamentVisualEffects] = useState<string[]>([]);
  const [filamentAdditives, setFilamentAdditives] = useState<FilamentAdditive[]>([]);
  const resolvedFilamentVisualEffects = mergeVisualEffects(filamentVisualEffects, filamentAdditives);
  const [filamentPropertyClaims, setFilamentPropertyClaims] = useState<FilamentPropertyClaim[]>([]);
  const [filamentVisualTransparency, setFilamentVisualTransparency] = useState(false);
  const [showFilamentAdvancedVisual, setShowFilamentAdvancedVisual] = useState(false);
  // Состояния для открытия/закрытия HSL пикеров для каждого цвета в расширенных настройках
  const [openColorPickers, setOpenColorPickers] = useState<boolean[]>([]);
  const colorPickerButtonRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const [filamentDiameter, setFilamentDiameter] = useState('1.75');
  const [filamentDensity, setFilamentDensity] = useState<number | ''>('');
  const [filamentHandling, setFilamentHandling] = useState<FilamentHandlingFormValue>({
    dryingRequired: false,
    dryingTemperatureC: '',
    dryingDurationHours: '',
    enclosureRequirement: 'none',
    chamberTemperatureC: '',
    bedAdhesivesText: '',
    chemicals: [],
  });
  const [filamentPricePerKg, setFilamentPricePerKg] = useState<number | ''>('');
  const [filamentSpoolWeight, setFilamentSpoolWeight] = useState<number | ''>('');
  const [filamentPriceUnit, setFilamentPriceUnit] = useState<'per_kg' | 'per_spool'>('per_kg');
  const [filamentRecTemps, setFilamentRecTemps] = useState<RecommendedTemps>(EMPTY_RECOMMENDED_TEMPS);
  const [filamentNozzleHrc, setFilamentNozzleHrc] = useState<number | null>(null);
  const [filamentDescription, setFilamentDescription] = useState('');
  const [showFilamentForm, setShowFilamentForm] = useState(false); // true = создать новый, false = выбрать существующий
  const [filamentSearch, setFilamentSearch] = useState(''); // Поиск существующего филамента
  const [showFilamentDropdown, setShowFilamentDropdown] = useState(false); // Показывать выпадающий список
  const [selectedFilament, setSelectedFilament] = useState<Filament | null>(null); // Выбранный филамент для отображения
  const [showBrandDropdown, setShowBrandDropdown] = useState(false); // Показывать выпадающий список брендов
  const [selectedPrinterIds, setSelectedPrinterIds] = useState<number[]>([]); // Выбранные принтеры
  const [printersCache, setPrintersCache] = useState<Record<number, Printer>>({});
  const [printerSearch, setPrinterSearch] = useState('');
  const debouncedPrinterSearch = useDebounce(printerSearch, 250);
  
  // Опции диаметра (из общего источника).
  const DIAMETER_OPTIONS = STANDARD_DIAMETERS.map((d) => d.toFixed(2));
  
  // Для создания нового бренда
  const [showBrandForm, setShowBrandForm] = useState(false); // true = создать новый бренд
  const [newBrandName, setNewBrandName] = useState(''); // Название нового бренда
  const [newBrandWebsite, setNewBrandWebsite] = useState(''); // Сайт нового бренда
  
  const filamentDropdownRef = useRef<HTMLDivElement>(null);
  const brandDropdownRef = useRef<HTMLDivElement>(null);
  const draftSuggestionsAppliedRef = useRef<number | null>(null);
  const queryClient = useQueryClient();
  const achievementQueryKey = ['achievement-overview', user?.id] as const;
  useQuery({
    queryKey: achievementQueryKey,
    queryFn: achievementsAPI.getMine,
    enabled: isOpen && !!user?.id,
    staleTime: 60_000,
  });

  const refreshAchievements = async () => {
    if (!user?.id) return;
    try {
      const next = await achievementsAPI.evaluateMine();
      queryClient.setQueryData<AchievementOverview>(achievementQueryKey, {
        ...next,
        newly_earned: [],
      });
      const newlyEarned = next.newly_earned.filter(isAchievementCode);
      if (newlyEarned.length > 0) {
        toast.success(
          t('achievement.earned', {
            names: newlyEarned
              .map((code) => t(ACHIEVEMENT_CONFIG[code].labelKey))
              .join(', '),
          }),
          9000,
        );
      }
    } catch {
      // Achievement feedback must never interrupt publication.
      queryClient.invalidateQueries({ queryKey: ['achievement-overview'] });
    }
  };

  const technicalFactsBrandId = brandId ?? selectedBrandId;
  const { data: technicalFactsTerritories } = useQuery({
    queryKey: ['brand-territories', technicalFactsBrandId, user?.active_organization_id],
    queryFn: () => brandsAPI.myTerritories(technicalFactsBrandId!),
    enabled: isOpen && !!technicalFactsBrandId,
  });
  const canManageTechnicalFacts = Boolean(
    user?.role === 'admin' || (technicalFactsTerritories?.territories?.length ?? 0) > 0,
  );

  const shouldLoadFilamentsForSelection = Boolean(
    isOpen && (!preset || isDraft) && !filamentId && !showFilamentForm
  );

  // Загружаем филамент для редактирования или для предвыбранного filamentId (создание из карточки материала)
  const preselectFilamentId = preset?.filament_id ?? filamentId;
  const { data: editingFilament } = useQuery({
    queryKey: ['filament', preselectFilamentId],
    queryFn: () => filamentsAPI.get(preselectFilamentId!),
    enabled: isOpen && !!preselectFilamentId,
  });
  const { data: draftAnalysis, isLoading: draftAnalysisLoading } = useQuery({
    queryKey: ['preset-draft-analysis', preset?.id],
    queryFn: () => presetsAPI.getDraftAnalysis(preset!.id),
    enabled: isOpen && isDraft && !!preset?.id,
  });
  const trackedReviewOpenRef = useRef(false);
  useEffect(() => {
    if (!isOpen) {
      trackedReviewOpenRef.current = false;
      return;
    }
    if (!isDraft || trackedReviewOpenRef.current) return;
    trackedReviewOpenRef.current = true;
    void presetsAPI.recordDraftEvent('review_opened').catch(() => {
      // Product metrics must never interrupt review or publication.
    });
  }, [isDraft, isOpen]);
  const officialTargetBrandId = brandId
    ?? selectedFilament?.brand_id
    ?? selectedBrandId
    ?? draftAnalysis?.brand_match?.id
    ?? null;
  const { data: officialTargetBrand } = useQuery({
    queryKey: ['brand', officialTargetBrandId],
    queryFn: () => brandsAPI.get(officialTargetBrandId!),
    enabled: isOpen && officialTargetBrandId != null,
  });
  const { data: officialTargetTerritories } = useQuery({
    queryKey: [
      'brand-territories',
      officialTargetBrandId,
      user?.active_organization_id,
    ],
    queryFn: () => brandsAPI.myTerritories(officialTargetBrandId!),
    enabled: isOpen
      && officialTargetBrandId != null
      && !!user?.active_organization_id,
  });
  // Любой пользователь может создать пресет. Официальная публикация относится
  // к выбранному целевому бренду и активной Organization, а не к legacy user.brand_id.
  const canOfferOfficial = allowOfficial ?? Boolean(
    user?.role === 'admin'
    || (
      officialTargetBrand?.verified === true
      && officialTargetTerritories?.can_edit_filament_common === true
    )
  );

  useEffect(() => {
    if (isOfficial && !canOfferOfficial) {
      setIsOfficial(false);
    }
  }, [canOfferOfficial, isOfficial]);

  useEffect(() => {
    draftSuggestionsAppliedRef.current = null;
    setDraftHasColorEvidence(false);
  }, [isOpen, preset?.id]);

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
  const filamentPriceCurrency = currencySymbol(
    currentBrandData?.currency
    || brandsData?.items.find((brand: Brand) => brand.id === selectedBrandId)?.currency
    || officialTargetBrand?.currency,
  );

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

  // Инициализация формы при редактировании
  useEffect(() => {
    if (!isOpen) return; // Не выполняем инициализацию если модалка закрыта
    
    if (preset) {
      setName(preset.name);
      setDescription(preset.description || '');
      setIsOfficial(preset.is_official);
      setExtruderTemp(preset.extruder_temp);
      setBedTemp(preset.bed_temp);
      setFlowRate(preset.flow_rate ?? 100);
      setFanSpeed(preset.fan_speed ?? 100);
      setRetractionLength(preset.retraction_length ?? 5.0);
      setRetractionSpeed(preset.retraction_speed ?? 45.0);
      
      // Загружаем расширенные параметры из JSON
      if (preset.orcaslicer_settings) {
        const rawSettings = preset.orcaslicer_settings;
        const settings = normalizeOrcaSettingsForUi(rawSettings);
        const numericSetting = (key: string): number | '' => readOrcaNumber(rawSettings, key) ?? '';
        const textSetting = (key: string): string => readOrcaText(rawSettings, key);
        const percentSetting = (key: string): string => textSetting(key).replace('%', '');
        const booleanSetting = (key: string, fallback = false): boolean => {
          const rawValue = firstOrcaSetting(rawSettings, key);
          if (rawValue === undefined || rawValue === null || String(rawValue).trim().toLowerCase() === 'nil') {
            return fallback;
          }
          return ['1', 'true', 'yes'].includes(String(rawValue).trim().toLowerCase());
        };
        setTempRangeLow(numericSetting('nozzle_temperature_range_low'));
        setTempRangeHigh(numericSetting('nozzle_temperature_range_high'));
        setVolumetricSpeed(numericSetting('filament_max_volumetric_speed'));
        setFanMinSpeed(numericSetting('fan_min_speed'));
        const rawFanMaxSpeed = readOrcaNumber(rawSettings, 'fan_max_speed');
        setFanMaxSpeed(
          rawFanMaxSpeed != null && rawFanMaxSpeed <= 100 ? rawFanMaxSpeed : '',
        );
        if (preset.flow_rate == null) {
          const rawFlowRatio = readOrcaNumber(rawSettings, 'filament_flow_ratio');
          if (rawFlowRatio != null) {
            setFlowRate(rawFlowRatio <= 2 ? rawFlowRatio * 100 : rawFlowRatio);
          }
        }
        if (preset.fan_speed == null) {
          const rawFanSpeed = readOrcaNumber(rawSettings, 'fan_min_speed');
          if (rawFanSpeed != null) setFanSpeed(rawFanSpeed);
        }
        if (preset.retraction_length == null) {
          const rawRetractionLength = readOrcaNumber(rawSettings, 'filament_retraction_length');
          if (rawRetractionLength != null) setRetractionLength(rawRetractionLength);
        }
        if (preset.retraction_speed == null) {
          const rawRetractionSpeed = readOrcaNumber(rawSettings, 'filament_retraction_speed');
          if (rawRetractionSpeed != null) setRetractionSpeed(rawRetractionSpeed);
        }
        setReduceFanStopStartFreq(settings.reduce_fan_stop_start_freq?.[0] === '1' || settings.reduce_fan_stop_start_freq?.[0] === 1);
        setPressureAdvance(numericSetting('pressure_advance'));
        setEnablePressureAdvance(settings.enable_pressure_advance?.[0] === '1' || settings.enable_pressure_advance?.[0] === 1);
        setIdleTemperature(numericSetting('idle_temperature'));
        setSofteningTemperature(numericSetting('temperature_vitrification'));
        setChamberTemp(numericSetting('chamber_temperature'));
        setChamberMinimalTemp(numericSetting('chamber_minimal_temperature'));
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
        const roleChangeGcode = rawSettings.filament_change_extrusion_role_gcode;
        setFilamentChangeExtrusionRoleGcode(
          Array.isArray(roleChangeGcode)
            ? roleChangeGcode.map((line) => String(line)).join('\n')
            : textSetting('filament_change_extrusion_role_gcode'),
        );
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
          settings.bed_temperature_initial_layer?.[0] ??
          settings.hot_plate_temp_initial_layer?.[0] ??
          settings.cool_plate_temp_initial_layer?.[0] ??
          settings.eng_plate_temp_initial_layer?.[0] ??
          settings.textured_plate_temp_initial_layer?.[0] ??
          settings.supertack_plate_temp_initial_layer?.[0] ??
          settings.textured_cool_plate_temp_initial_layer?.[0] ??
          settings.customized_plate_temp_initial_layer?.[0] ??
          settings.epoxy_resin_plate_temp_initial_layer?.[0] ??
          '';
        setBedTempInitialLayer(parseNumericSetting(bedInitialLayerValue));
        setAdaptiveVolumetricSpeed(settings.filament_adaptive_volumetric_speed?.[0] === '1' || settings.filament_adaptive_volumetric_speed?.[0] === 1);
        setVolumetricSpeedCoefficients(textSetting('volumetric_speed_coefficients'));
        // Процентные значения (убираем % при загрузке)
        setFilamentShrink(percentSetting('filament_shrink'));
        setFilamentShrinkageCompensationZ(percentSetting('filament_shrinkage_compensation_z'));
        setDefaultFilamentColour(textSetting('default_filament_colour'));
        setFilamentAdhesivenessCategory(numericSetting('filament_adhesiveness_category'));
        setFilamentIsSupport(settings.filament_is_support?.[0] === '1' || settings.filament_is_support?.[0] === 1);
        setFilamentSoluble(settings.filament_soluble?.[0] === '1' || settings.filament_soluble?.[0] === 1);
        setFilamentPrintable(numericSetting('filament_printable'));
        
        // Ретракт (дополнительные параметры)
        setDeretractionSpeed(numericSetting('filament_deretraction_speed'));
        setRetractionMinimumTravel(numericSetting('filament_retraction_minimum_travel'));
        setRetractBeforeWipe(percentSetting('filament_retract_before_wipe'));
        setRetractAfterWipe(percentSetting('filament_retract_after_wipe'));
        setRetractWhenChangingLayer(settings.filament_retract_when_changing_layer?.[0] === '1' || settings.filament_retract_when_changing_layer?.[0] === 1);
        setRetractRestartExtra(numericSetting('filament_retract_restart_extra'));
        setRetractLengthToolchange(numericSetting('filament_retract_length_toolchange'));
        setRetractRestartExtraToolchange(numericSetting('filament_retract_restart_extra_toolchange'));
        
        // Lift (подъем Z)
        setFilamentZHop(numericSetting('filament_z_hop'));
        setFilamentZHopTypes(textSetting('filament_z_hop_types'));
        setRetractLiftAbove(numericSetting('filament_retract_lift_above'));
        setRetractLiftBelow(numericSetting('filament_retract_lift_below'));
        setRetractLiftEnforce(textSetting('filament_retract_lift_enforce'));
        
        // Wipe
        setFilamentWipe(settings.filament_wipe?.[0] === '1' || settings.filament_wipe?.[0] === 1);
        setFilamentWipeDistance(numericSetting('filament_wipe_distance'));
        setFilamentFlushTemp(numericSetting('filament_flush_temp'));
        setFilamentFlushVolumetricSpeed(numericSetting('filament_flush_volumetric_speed'));
        
        // Pressure Advance (дополнительные параметры)
        setAdaptivePressureAdvance(settings.adaptive_pressure_advance?.[0] === '1' || settings.adaptive_pressure_advance?.[0] === 1);
        setAdaptivePABridges(numericSetting('adaptive_pressure_advance_bridges'));
        setAdaptivePAOverhangs(settings.adaptive_pressure_advance_overhangs?.[0] === '1' || settings.adaptive_pressure_advance_overhangs?.[0] === 1);
        
        // === ВКЛАДКА "ОХЛАЖДЕНИЕ" - дополнительные параметры ===
        setFanCoolingLayerTime(numericSetting('fan_cooling_layer_time'));
        setFanMaxSpeedLayerTime(numericSetting('slow_down_layer_time')); // slow_down_layer_time используется для fanMaxSpeedLayerTime
        setFullFanSpeedLayer(numericSetting('full_fan_speed_layer'));
        setCloseFanFirstXLayers(numericSetting('close_fan_the_first_x_layers'));
        setInitialLayerFanSpeed(numericSetting('initial_layer_fan_speed'));
        setSlowDownForLayerCooling(settings.slow_down_for_layer_cooling?.[0] === '1' || settings.slow_down_for_layer_cooling?.[0] === 1);
        setEnableOverhangBridgeFan(settings.enable_overhang_bridge_fan?.[0] === '1' || settings.enable_overhang_bridge_fan?.[0] === 1);
        setOverhangFanSpeed(numericSetting('overhang_fan_speed'));
        setOverhangFanThreshold(percentSetting('overhang_fan_threshold'));
        setInternalBridgeFanSpeed(numericSetting('internal_bridge_fan_speed'));
        setIroningFanSpeed(numericSetting('ironing_fan_speed'));
        setSupportMaterialInterfaceFanSpeed(numericSetting('support_material_interface_fan_speed'));
        setAdditionalCoolingFanSpeed(numericSetting('additional_cooling_fan_speed'));
        setEnableExhaustFan(
          booleanSetting('activate_air_filtration')
          || !!settings.during_print_exhaust_fan_speed
          || !!settings.complete_print_exhaust_fan_speed,
        );
        setDuringPrintExhaustFanSpeed(numericSetting('during_print_exhaust_fan_speed'));
        setCompletePrintExhaustFanSpeed(numericSetting('complete_print_exhaust_fan_speed'));
        setActivateAirFiltrationDuringPrint(booleanSetting('activate_air_filtration_during_print', true));
        setActivateAirFiltrationOnCompletion(booleanSetting('activate_air_filtration_on_completion', true));
        
        // === ВКЛАДКА "ПЕРЕОПРЕДЕЛЕНИЕ ПАРАМЕТРОВ" ===
        setSlowDownMinSpeed(numericSetting('slow_down_min_speed'));
        setDontSlowDownOuterWall(settings.dont_slow_down_outer_wall?.[0] === '1' || settings.dont_slow_down_outer_wall?.[0] === 1);
        setRetractionDistancesWhenCut(textSetting('filament_retraction_distances_when_cut'));
        setLongRetractionsWhenCut(textSetting('filament_long_retractions_when_cut'));
        setLongRetractionsWhenEC(settings.long_retractions_when_ec?.[0] === '1' || settings.long_retractions_when_ec?.[0] === 1);
        setRetractionDistancesWhenEC(numericSetting('retraction_distances_when_ec'));
        
        // === ВКЛАДКА "ДОПОЛНИТЕЛЬНО" - дополнительные параметры ===
        setFilamentMultitoolRamming(settings.filament_multitool_ramming?.[0] === '1' || settings.filament_multitool_ramming?.[0] === 1);
        setFilamentMultitoolRammingFlow(numericSetting('filament_multitool_ramming_flow'));
        setFilamentMultitoolRammingVolume(numericSetting('filament_multitool_ramming_volume'));
        setFilamentToolchangeDelay(numericSetting('filament_toolchange_delay'));
        setFilamentLoadingSpeed(numericSetting('filament_loading_speed'));
        setFilamentLoadingSpeedStart(numericSetting('filament_loading_speed_start'));
        setFilamentUnloadingSpeed(numericSetting('filament_unloading_speed'));
        setFilamentUnloadingSpeedStart(numericSetting('filament_unloading_speed_start'));
        setFilamentChangeLength(numericSetting('filament_change_length'));
        setFilamentCoolingInitialSpeed(numericSetting('filament_cooling_initial_speed'));
        setFilamentCoolingFinalSpeed(numericSetting('filament_cooling_final_speed'));
        setFilamentCoolingMoves(numericSetting('filament_cooling_moves'));
        setFilamentStampingDistance(numericSetting('filament_stamping_distance'));
        setFilamentStampingLoadingSpeed(numericSetting('filament_stamping_loading_speed'));
        setFilamentMinimalPurgeOnWipeTower(numericSetting('filament_minimal_purge_on_wipe_tower'));
        setPelletFlowCoefficient(numericSetting('pellet_flow_coefficient'));
        
        // === ВКЛАДКА "ЭКСТРУДЕР ММ" ===
        setFilamentExtruderVariant(textSetting('filament_extruder_variant'));
        
        // === ВКЛАДКА "ЗАВИСИМОСТИ" ===
        if (settings.compatible_printers && Array.isArray(settings.compatible_printers)) {
          setCompatiblePrinters(settings.compatible_printers.join(', '));
        } else {
          setCompatiblePrinters('');
        }
        setCompatiblePrintersCondition(textSetting('compatible_printers_condition'));
        if (settings.compatible_prints && Array.isArray(settings.compatible_prints)) {
          setCompatiblePrints(settings.compatible_prints.join(', '));
        } else {
          setCompatiblePrints('');
        }
        setCompatiblePrintsCondition(textSetting('compatible_prints_condition'));

        if (isDraft && !preset.filament_id) {
          // A personal recipe is not vendor packaging evidence. Keep its
          // temperatures in the preset, but do not publish them as catalogue
          // "recommended by vendor" facts.
          setFilamentRecTemps(EMPTY_RECOMMENDED_TEMPS);
        }
        
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
        setRetractAfterWipe('');
        setRetractWhenChangingLayer(false);
        setRetractRestartExtra('');
        setRetractLengthToolchange('');
        setRetractRestartExtraToolchange('');
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
        setChamberMinimalTemp('');
        setFanCoolingLayerTime('');
        setFanMaxSpeedLayerTime('');
        setFullFanSpeedLayer('');
        setCloseFanFirstXLayers('');
        setInitialLayerFanSpeed('');
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
        setActivateAirFiltrationDuringPrint(true);
        setActivateAirFiltrationOnCompletion(true);
        setSlowDownMinSpeed('');
        setDontSlowDownOuterWall(false);
        setRetractionDistancesWhenCut('');
        setLongRetractionsWhenCut('');
        setLongRetractionsWhenEC(false);
        setRetractionDistancesWhenEC('');
        setFilamentChangeExtrusionRoleGcode('');
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
      setFlowRate(100);
      setFanSpeed(100);
      setRetractionLength(5.0);
      setRetractionSpeed(45.0);
      
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
      setRetractAfterWipe('');
      setRetractWhenChangingLayer(false);
      setRetractRestartExtra('');
      setRetractLengthToolchange('');
      setRetractRestartExtraToolchange('');
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
      setChamberMinimalTemp('');
      setEnableChamberControl(false);
      setFanMinSpeed('');
      setFanMaxSpeed('');
      setFanCoolingLayerTime('');
      setFanMaxSpeedLayerTime('');
      setFullFanSpeedLayer('');
      setCloseFanFirstXLayers('');
      setInitialLayerFanSpeed('');
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
      setActivateAirFiltrationDuringPrint(true);
      setActivateAirFiltrationOnCompletion(true);
      setSlowDownMinSpeed('');
      setDontSlowDownOuterWall(false);
      setRetractionDistancesWhenCut('');
      setLongRetractionsWhenCut('');
      setLongRetractionsWhenEC(false);
      setRetractionDistancesWhenEC('');
      setFilamentStartGcode('');
      setFilamentChangeExtrusionRoleGcode('');
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
      setBrandSearch('');
      // Если передан brandId - автоматически выбираем его при создании нового материала
      setSelectedBrandId(brandId || null);
      setFilamentName('');
      setFilamentColorName('');
      setFilamentColorHex('#FF0000');
      setFilamentRalCode('');
      setFilamentRecTemps(EMPTY_RECOMMENDED_TEMPS);
      setFilamentNozzleHrc(null);
      setFilamentDiameter('1.75');
      setFilamentDensity('');
      setFilamentHandling({
        dryingRequired: false,
        dryingTemperatureC: '',
        dryingDurationHours: '',
        enclosureRequirement: 'none',
        chamberTemperatureC: '',
        bedAdhesivesText: '',
        chemicals: [],
      });
      // Сброс расширенных визуальных эффектов
      setFilamentVisualColorType('single');
      setFilamentVisualColors(['#FF0000']);
      setFilamentVisualFinish('matte');
      setFilamentVisualEffects([]);
      setFilamentAdditives([]);
      setFilamentPropertyClaims([]);
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

  // Когда загрузился филамент (редактирование или предвыбор filamentId) — показываем его имя
  useEffect(() => {
    if (editingFilament && (preset || filamentId)) {
      setFilamentSearch(editingFilament.color_name ? `${editingFilament.name} (${editingFilament.color_name})` : editingFilament.name);
      setSelectedFilament(editingFilament);
      // Ф6: при создании пресета из карточки материала подтягиваем вендорский диапазон как дефолт
      if (!preset && filamentId) {
        applyRecommendedTempsFromFilament(editingFilament);
      }
    }
  }, [editingFilament, preset, filamentId]);

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

  // Диапазон «min–max» для подсказки (одна из границ может отсутствовать).
  const formatTempRange = (min: number | null, max: number | null): string => {
    if (min != null && max != null) return `${min}–${max}`;
    if (min != null) return `≥${min}`;
    if (max != null) return `≤${max}`;
    return '';
  };

  // Ф6: вендор задаёт рекомендованный диапазон температур на материале — пресет подтягивает
  // его как дефолт (середина диапазона), а границы сопла — в nozzle_temperature_range.
  // Вызывается после applyDefaultsByMaterialType (диапазон вендора конкретнее типовых значений)
  // и только при создании нового пресета — у существующего свои сохранённые значения.
  const applyRecommendedTempsFromFilament = (filament: Filament | null) => {
    if (!filament) return;
    const nMin = filament.recommended_nozzle_temp_min;
    const nMax = filament.recommended_nozzle_temp_max;
    const bMin = filament.recommended_bed_temp_min;
    const bMax = filament.recommended_bed_temp_max;

    if (nMin != null && nMax != null) {
      setExtruderTemp(Math.round((nMin + nMax) / 2));
      setTempRangeLow(nMin);
      setTempRangeHigh(nMax);
    } else if (nMin != null) {
      setExtruderTemp(nMin);
      setTempRangeLow(nMin);
    } else if (nMax != null) {
      setExtruderTemp(nMax);
      setTempRangeHigh(nMax);
    }

    if (bMin != null && bMax != null) {
      setBedTemp(Math.round((bMin + bMax) / 2));
    } else if (bMin != null) {
      setBedTemp(bMin);
    } else if (bMax != null) {
      setBedTemp(bMax);
    }
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
    if (!isDraft) {
      applyDefaultsByMaterialType(filament.material_type);
      applyRecommendedTempsFromFilament(fullFilament);
    }
  };

  useEffect(() => {
    if (
      !isOpen
      || !isDraft
      || !preset
      || !draftAnalysis
      || draftSuggestionsAppliedRef.current === preset.id
    ) {
      return;
    }
    draftSuggestionsAppliedRef.current = preset.id;

    const suggestion = (field: string) => draftAnalysis.suggestions[field]?.value;
    const suggestedExtruder = suggestion('extruder_temp');
    const suggestedBed = suggestion('bed_temp');
    if (typeof suggestedExtruder === 'number') setExtruderTemp(suggestedExtruder);
    if (typeof suggestedBed === 'number') setBedTemp(suggestedBed);

    const applyNewFilamentSuggestions = () => {
      setShowFilamentForm(true);
      if (draftAnalysis.brand_match) {
        setSelectedBrandId(draftAnalysis.brand_match.id);
        setBrandSearch(draftAnalysis.brand_match.name);
        setShowBrandForm(false);
      } else if (typeof suggestion('brand_name') === 'string') {
        setBrandSearch(String(suggestion('brand_name')));
        setNewBrandName(String(suggestion('brand_name')));
        setShowBrandForm(true);
      }
      if (typeof suggestion('filament_name') === 'string') {
        setFilamentName(String(suggestion('filament_name')));
      }
      if (typeof suggestion('material_type') === 'string') {
        setMaterialType(String(suggestion('material_type')));
      }
      if (typeof suggestion('color_hex') === 'string') {
        const color = String(suggestion('color_hex'));
        setFilamentColorHex(color);
        setFilamentVisualColors([color]);
        setDraftHasColorEvidence(true);
      }
      if (typeof suggestion('diameter') === 'number') {
        setFilamentDiameter(String(suggestion('diameter')));
      }
      if (typeof suggestion('density') === 'number') {
        setFilamentDensity(Number(suggestion('density')));
      }
    };

    const strongMatches = draftAnalysis.filament_matches.filter(
      (match) => match.confidence === 'exact' || match.confidence === 'strong',
    );
    if (strongMatches.length === 1) {
      const match = strongMatches[0];
      void filamentsAPI.get(match.id).then((filament) => {
        if (draftSuggestionsAppliedRef.current === preset.id) {
          selectExistingFilament(filament);
        }
      }).catch(() => {
        if (draftSuggestionsAppliedRef.current === preset.id) {
          applyNewFilamentSuggestions();
        }
      });
      return;
    }

    applyNewFilamentSuggestions();
  }, [draftAnalysis, isDraft, isOpen, preset]);

  // Мутация для создания бренда
  const createBrandMutation = useMutation({
    mutationFn: (data: { name: string; slug?: string; website?: string }) => brandsAPI.create(data),
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
      ral_code?: string | null;
      visual_settings?: FilamentVisualSettings | null;
      additives?: FilamentAdditive[];
      property_claims?: FilamentPropertyClaim[];
      diameter?: number;
      density?: number;
      drying_required?: boolean | null;
      drying_temperature_c?: number | null;
      drying_duration_hours?: number | null;
      enclosure_requirement?: import('../types/api').FilamentEnclosureRequirement | null;
      chamber_temperature_c?: number | null;
      bed_adhesives?: string[];
      post_processing_chemicals?: import('../types/api').FilamentChemicalGuidance[];
      price_per_kg?: number;
      spool_weight?: number;
      recommended_nozzle_temp_min?: number;
      recommended_nozzle_temp_max?: number;
      recommended_bed_temp_min?: number;
      recommended_bed_temp_max?: number;
      required_nozzle_hrc?: number;
      price_display_unit?: 'per_kg' | 'per_spool';
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
          const currentMaterialType = materialType.trim().toLowerCase();

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
    void presetsAPI.recordDraftEvent('duplicate_prevented').catch(() => undefined);
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
      queryClient.invalidateQueries({ queryKey: ['preset-draft-queue'] });
      queryClient.invalidateQueries({ queryKey: ['preset-stats'] });
      void refreshAchievements();
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
        flow_rate?: number;
        fan_speed?: number;
        retraction_length?: number;
        retraction_speed?: number;
        orcaslicer_settings?: Record<string, unknown> | null;
        printer_ids?: number[];
        filament_id?: number | null;
        active?: boolean;
        is_official?: boolean;
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
      queryClient.invalidateQueries({ queryKey: ['preset-draft-queue'] });
      queryClient.invalidateQueries({ queryKey: ['preset-stats'] });
      void refreshAchievements();
      // Инвалидируем кэш пресетов бренда (если редактировался из профиля бренда)
      if (brandId) {
        queryClient.invalidateQueries({ queryKey: ['brand-presets'] });
      }
      if (isDraft && updatedPreset.moderation_status === 'rejected') {
        let detail: unknown = updatedPreset.moderation_reason;
        try {
          detail = updatedPreset.moderation_reason
            ? JSON.parse(updatedPreset.moderation_reason)
            : detail;
        } catch {
          // A legacy plain-text reason is still useful to the user.
        }
        setError(translateApiError(t, detail, t('presetModal.draftNeedsFix')));
        return;
      }
      if (isDraft) {
        toast.success(
          updatedPreset.moderation_status === 'pending'
            ? t('presetModal.draftSentForReview')
            : t('presetModal.draftPublishedBenefit'),
          8000,
        );
      }
      onClose();
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      setError(translateApiError(t, err?.response?.data?.detail, t('presetModal.errors.updatePreset')));
      console.error('Failed to update preset:', err);
    },
  });

  const originalFlowRatio = readOrcaNumber(preset?.orcaslicer_settings, 'filament_flow_ratio');
  const originalFlowRate = preset?.flow_rate
    ?? (originalFlowRatio == null ? 100 : originalFlowRatio <= 2 ? originalFlowRatio * 100 : originalFlowRatio);
  const originalFanSpeed = preset?.fan_speed
    ?? readOrcaNumber(preset?.orcaslicer_settings, 'fan_min_speed')
    ?? 100;
  const originalFanMaxSpeed = readOrcaNumber(
    preset?.orcaslicer_settings,
    'fan_max_speed',
  );
  const originalRetractionLength = preset?.retraction_length
    ?? readOrcaNumber(preset?.orcaslicer_settings, 'filament_retraction_length')
    ?? 5;
  const originalRetractionSpeed = preset?.retraction_speed
    ?? readOrcaNumber(preset?.orcaslicer_settings, 'filament_retraction_speed')
    ?? 45;

  // Функция для построения JSON расширенных параметров из UI полей
  // Собирает ВСЕ параметры OrcaSlicer по всем вкладкам
  const buildOrcaslicerSettings = (filamentColorHex?: string | null): Record<string, any> | null => {
    const sourceSettings = cloneOrcaSettings(preset?.orcaslicer_settings);
    const settings: Record<string, any> = { ...sourceSettings };
    let hasSettings = Object.keys(settings).length > 0;

    // Вспомогательная функция для добавления параметра
    const addParam = (key: string, value: string | number | string[] | null | undefined) => {
      applyOrcaUiSetting(settings, sourceSettings, key, value);
    };

    // Вспомогательная функция для добавления boolean параметра
    const addBoolParam = (key: string, value: boolean) => {
      applyOrcaBooleanFromUi(settings, sourceSettings, key, value);
    };

    // Вспомогательная функция для добавления процентного значения
    const addPercentParam = (key: string, value: string) => {
      if (value && value.trim() !== '') {
        const normalized = value.trim().endsWith('%') ? value.trim() : `${value.trim()}%`;
        if (
          Object.prototype.hasOwnProperty.call(sourceSettings, key)
          && String(firstOrcaSetting(sourceSettings, key)) === normalized
        ) {
          return;
        }
        settings[key] = [normalized];
        hasSettings = true;
      } else if (
        String(firstOrcaSetting(sourceSettings, key)).trim().toLowerCase() === 'nil'
      ) {
        return;
      } else {
        delete settings[key];
      }
    };

    const addLinesParam = (key: string, value: string) => {
      applyOrcaLinesFromUi(settings, sourceSettings, key, value);
    };

    // === ВКЛАДКА "ПРОФИЛЬ ПРУТКА" ===
    
    // Температуры
    if (
      !preset
      || preset.extruder_temp !== extruderTemp
      || !Object.prototype.hasOwnProperty.call(sourceSettings, 'nozzle_temperature')
    ) {
      addParam('nozzle_temperature', extruderTemp);
    }
    addParam('nozzle_temperature_range_low', tempRangeLow);
    addParam('nozzle_temperature_range_high', tempRangeHigh);
    addParam('nozzle_temperature_initial_layer', nozzleTempInitialLayer);
    const bedKeys = [
      'bed_temperature',
      'hot_plate_temp',
      'cool_plate_temp',
      'eng_plate_temp',
      'textured_plate_temp',
      'supertack_plate_temp',
      'textured_cool_plate_temp',
      'customized_plate_temp',
      'epoxy_resin_plate_temp',
    ];
    const hasRawBedTemperature = bedKeys.some(
      (key) => firstOrcaSetting(sourceSettings, key) != null,
    );
    if (!preset || preset.bed_temp !== bedTemp || !hasRawBedTemperature) {
      bedKeys.forEach((key) => addParam(key, bedTemp));
    }
    const bedInitialTemp =
      bedTempInitialLayer !== '' && bedTempInitialLayer !== null ? bedTempInitialLayer : bedTemp;
    const originalBedInitial = [
      'bed_temperature_initial_layer',
      'hot_plate_temp_initial_layer',
      'cool_plate_temp_initial_layer',
      'eng_plate_temp_initial_layer',
      'textured_plate_temp_initial_layer',
      'supertack_plate_temp_initial_layer',
      'textured_cool_plate_temp_initial_layer',
      'customized_plate_temp_initial_layer',
      'epoxy_resin_plate_temp_initial_layer',
    ].map((key) => firstOrcaSetting(sourceSettings, key)).find((value) => value != null && value !== '');
    const preserveInheritedBedInitial = bedTempInitialLayer === ''
      && isOrcaBedTemperatureSentinel(originalBedInitial);
    if (
      !preserveInheritedBedInitial
      && (originalBedInitial == null || String(originalBedInitial) !== String(bedInitialTemp))
    ) {
      delete settings.bed_temperature_initial_layer;
      addParam('hot_plate_temp_initial_layer', bedInitialTemp);
      addParam('cool_plate_temp_initial_layer', bedInitialTemp);
      addParam('eng_plate_temp_initial_layer', bedInitialTemp);
      addParam('textured_plate_temp_initial_layer', bedInitialTemp);
      addParam('supertack_plate_temp_initial_layer', bedInitialTemp);
      addParam('textured_cool_plate_temp_initial_layer', bedInitialTemp);
      addParam('customized_plate_temp_initial_layer', bedInitialTemp);
      addParam('epoxy_resin_plate_temp_initial_layer', bedInitialTemp);
    }
    addParam('idle_temperature', idleTemperature); // Температура ожидания
    addParam('temperature_vitrification', softeningTemperature); // Температура витрификации (размягчения)
    addParam('chamber_temperature', chamberTemp);
    addParam('chamber_minimal_temperature', chamberMinimalTemp);
    addBoolParam('activate_chamber_temp_control', enableChamberControl);

    // Свойства филамента
    if (
      !preset
      || originalFlowRate !== flowRate
      || !Object.prototype.hasOwnProperty.call(sourceSettings, 'filament_flow_ratio')
    ) {
      addParam('filament_flow_ratio', formatOrcaFlowRatio(flowRate));
    }
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
      addParam('default_filament_colour', finalColor);
    }
    addParam('filament_adhesiveness_category', filamentAdhesivenessCategory);
    addBoolParam('filament_is_support', filamentIsSupport);
    addBoolParam('filament_soluble', filamentSoluble);
    addParam('filament_printable', filamentPrintable);

    // Ретракт
    if (
      !preset
      || originalRetractionLength !== retractionLength
      || !Object.prototype.hasOwnProperty.call(sourceSettings, 'filament_retraction_length')
    ) {
      addParam('filament_retraction_length', retractionLength);
    }
    if (
      !preset
      || originalRetractionSpeed !== retractionSpeed
      || !Object.prototype.hasOwnProperty.call(sourceSettings, 'filament_retraction_speed')
    ) {
      addParam('filament_retraction_speed', retractionSpeed);
    }
    addParam('filament_deretraction_speed', deretractionSpeed);
    addParam('filament_retraction_minimum_travel', retractionMinimumTravel);
    addPercentParam('filament_retract_before_wipe', retractBeforeWipe);
    addPercentParam('filament_retract_after_wipe', retractAfterWipe);
    addBoolParam('filament_retract_when_changing_layer', retractWhenChangingLayer);
    addParam('filament_retract_restart_extra', retractRestartExtra);
    addParam('filament_retract_length_toolchange', retractLengthToolchange);
    addParam('filament_retract_restart_extra_toolchange', retractRestartExtraToolchange);

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
    const hasRawFanMinSpeed = Object.prototype.hasOwnProperty.call(sourceSettings, 'fan_min_speed');
    addParam(
      'fan_min_speed',
      fanMinSpeed !== '' || hasRawFanMinSpeed ? fanMinSpeed : fanSpeed,
    );
    const preserveOutOfRangeFanMax = fanMaxSpeed === ''
      && originalFanMaxSpeed != null
      && originalFanMaxSpeed > 100;
    if (!preserveOutOfRangeFanMax) {
      addParam('fan_max_speed', fanMaxSpeed);
    }
    addParam('fan_cooling_layer_time', fanCoolingLayerTime); // Время слоя для мин. скорости (порог мин. скорости)
    // slow_down_layer_time используется для макс. скорости вентилятора (порог макс. скорости)
    // Используем fanMaxSpeedLayerTime для порога макс. скорости вентилятора, если он задан
    addParam('slow_down_layer_time', fanMaxSpeedLayerTime);
    // reduce_fan_stop_start_freq = "Keep fan always on" в OrcaSlicer (вентилятор включён всегда)
    addBoolParam('reduce_fan_stop_start_freq', reduceFanStopStartFreq);
    addParam('full_fan_speed_layer', fullFanSpeedLayer); // Полная скорость вентилятора на слое
    addParam('close_fan_the_first_x_layers', closeFanFirstXLayers); // Закрыть вентилятор на первых X слоях
    const hasInitialLayerFanSpeed = Object.prototype.hasOwnProperty.call(sourceSettings, 'initial_layer_fan_speed');
    const initialLayerFanSpeedValue = Number(closeFanFirstXLayers) > 0
      && (initialLayerFanSpeed !== '' || hasInitialLayerFanSpeed)
      ? -1
      : initialLayerFanSpeed;
    addParam('initial_layer_fan_speed', initialLayerFanSpeedValue);

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
      addParam('internal_bridge_fan_speed', internalBridgeFanSpeed !== '' ? internalBridgeFanSpeed : -1);
    } else {
      addParam('internal_bridge_fan_speed', '');
    }
    // Скорость вентилятора на связующем слое (-1 = по умолчанию)
    addParam('support_material_interface_fan_speed', supportMaterialInterfaceFanSpeed);
    // Ironing fan speed (-1 = по умолчанию)
    addParam('ironing_fan_speed', ironingFanSpeed);

    // Вспомогательный вентилятор модели
    addParam('additional_cooling_fan_speed', additionalCoolingFanSpeed);

    // Вытяжной вентилятор — структура совпадает с секцией Exhaust fan в OrcaSlicer.
    addBoolParam('activate_air_filtration', enableExhaustFan);
    if (enableExhaustFan) {
      applyOrcaBooleanFromUi(
        settings,
        sourceSettings,
        'activate_air_filtration_during_print',
        activateAirFiltrationDuringPrint,
        true,
      );
      addParam('during_print_exhaust_fan_speed', duringPrintExhaustFanSpeed);
      applyOrcaBooleanFromUi(
        settings,
        sourceSettings,
        'activate_air_filtration_on_completion',
        activateAirFiltrationOnCompletion,
        true,
      );
      addParam('complete_print_exhaust_fan_speed', completePrintExhaustFanSpeed);
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
    const startGcodeKey = Object.prototype.hasOwnProperty.call(sourceSettings, 'filament_start_gcode')
      ? 'filament_start_gcode'
      : Object.prototype.hasOwnProperty.call(sourceSettings, 'start_filament_gcode')
        ? 'start_filament_gcode'
        : 'filament_start_gcode';
    const endGcodeKey = Object.prototype.hasOwnProperty.call(sourceSettings, 'filament_end_gcode')
      ? 'filament_end_gcode'
      : Object.prototype.hasOwnProperty.call(sourceSettings, 'end_filament_gcode')
        ? 'end_filament_gcode'
        : 'filament_end_gcode';
    addLinesParam(startGcodeKey, filamentStartGcode);
    addLinesParam('filament_change_extrusion_role_gcode', filamentChangeExtrusionRoleGcode);
    addLinesParam(endGcodeKey, filamentEndGcode);
    
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

    // === ВКЛАДКА "ЗАВИСИМОСТИ" ===
    if (compatiblePrinters.trim() !== '') {
      settings.compatible_printers = compatiblePrinters.split(',').map(s => s.trim()).filter(s => s);
      hasSettings = true;
    } else {
      delete settings.compatible_printers;
    }
    addParam('compatible_printers_condition', compatiblePrintersCondition);
    if (compatiblePrints.trim() !== '') {
      settings.compatible_prints = compatiblePrints.split(',').map(s => s.trim()).filter(s => s);
      hasSettings = true;
    } else {
      delete settings.compatible_prints;
    }
    addParam('compatible_prints_condition', compatiblePrintsCondition);

    // === ВКЛАДКА "ЗАМЕТКИ" ===
    addLinesParam('filament_notes', filamentNotes);

    hasSettings = Object.keys(settings).length > 0;
    return hasSettings ? settings : null;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setDuplicateFilamentSuggestion(null);

    // Если создаем новый филамент, сначала создаем его
    // ВАЖНО: это работает и при создании пресета, и при редактировании черновика
    if (showFilamentForm) {
      if (canManageTechnicalFacts && !isHandlingGuidanceComplete(filamentHandling)) {
        setError(t('filamentHandling.requiredParametersError'));
        return;
      }

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
              slug: slug || undefined,
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
              slug: slug || undefined,
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
      const finalMaterialType = materialType;
      if (!finalMaterialType) {
        setError(t('presetModal.errors.selectMaterialType'));
        return;
      }

      // Density is persisted on this exact catalogue filament. The material
      // family map is only a suggestion for an authorized representative.
      let finalDensity: number | undefined = undefined;
      if (canManageTechnicalFacts && filamentDensity !== '') {
        finalDensity = Number(filamentDensity);
      }

      try {
        // Формируем visual_settings если есть расширенные эффекты
        const visualSettings: FilamentVisualSettings | undefined = showFilamentAdvancedVisual || resolvedFilamentVisualEffects.length > 0 || filamentVisualColorType !== 'single' || filamentVisualFinish !== 'matte' || filamentVisualTransparency
          ? {
              color_type: filamentVisualColorType,
              colors: filamentVisualColors,
              finish: filamentVisualFinish,
              filler: resolvedFilamentVisualEffects[0] || 'none',
              effects: resolvedFilamentVisualEffects,
              transparency: filamentVisualTransparency,
            }
          : undefined;

        const acceptedFilamentColor = !isDraft || draftHasColorEvidence
          ? filamentColorHex
          : undefined;
        const newFilament = await createFilamentMutation.mutateAsync({
          brand_id: finalBrandId,
          name: filamentName,
          material_type: finalMaterialType,
          color_name: filamentColorName || undefined,
          color_hex: acceptedFilamentColor,
          ral_code: filamentRalCode || undefined,
          visual_settings: visualSettings,
          additives: filamentAdditives,
          property_claims: filamentPropertyClaims,
          diameter: Number(filamentDiameter),
          density: finalDensity,
          ...(canManageTechnicalFacts ? {
            drying_required: filamentHandling.dryingRequired,
            drying_temperature_c: filamentHandling.dryingRequired && filamentHandling.dryingTemperatureC !== '' ? filamentHandling.dryingTemperatureC : null,
            drying_duration_hours: filamentHandling.dryingRequired && filamentHandling.dryingDurationHours !== '' ? filamentHandling.dryingDurationHours : null,
            enclosure_requirement: filamentHandling.enclosureRequirement,
            chamber_temperature_c: filamentHandling.enclosureRequirement === 'active' && filamentHandling.chamberTemperatureC !== '' ? filamentHandling.chamberTemperatureC : null,
            bed_adhesives: parseBedAdhesives(filamentHandling.bedAdhesivesText),
            post_processing_chemicals: normalizeChemicalGuidance(filamentHandling.chemicals),
          } : {}),
          price_per_kg: canOfferOfficial && filamentPricePerKg !== ''
            ? (filamentPriceUnit === 'per_spool' && Number(filamentSpoolWeight) > 0
                ? (Number(filamentPricePerKg) * 1000) / Number(filamentSpoolWeight)
                : Number(filamentPricePerKg))
            : undefined,
          spool_weight: canOfferOfficial && filamentSpoolWeight !== '' ? Number(filamentSpoolWeight) : undefined,
          recommended_nozzle_temp_min: isDraft ? undefined : filamentRecTemps.nozzleMin ?? undefined,
          recommended_nozzle_temp_max: isDraft ? undefined : filamentRecTemps.nozzleMax ?? undefined,
          recommended_bed_temp_min: isDraft ? undefined : filamentRecTemps.bedMin ?? undefined,
          recommended_bed_temp_max: isDraft ? undefined : filamentRecTemps.bedMax ?? undefined,
          required_nozzle_hrc: filamentNozzleHrc ?? undefined,
          price_display_unit: canOfferOfficial ? filamentPriceUnit : undefined,
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
        const orcaslicerSettings = buildOrcaslicerSettings(acceptedFilamentColor);
        
        try {
          if (preset) {
            // Редактирование заготовки: привязываем только что созданный материал
            // и активируем пресет
            const updateData: {
              name: string;
              description?: string;
              extruder_temp?: number;
              bed_temp?: number;
              flow_rate?: number;
              fan_speed?: number;
              retraction_length?: number;
              retraction_speed?: number;
              orcaslicer_settings?: Record<string, unknown> | null;
              printer_ids: number[];
              filament_id: number;
              active?: boolean;
              is_official?: boolean;
            } = {
              name,
              description: description || undefined,
              orcaslicer_settings: orcaslicerSettings,
              printer_ids: selectedPrinterIds.length > 0 ? selectedPrinterIds : [],
              filament_id: newFilament.id,
              active: isDraft ? true : undefined,
              is_official: isDraft ? isOfficial : undefined,
            };
            if (preset.extruder_temp !== extruderTemp) updateData.extruder_temp = extruderTemp;
            if (preset.bed_temp !== bedTemp) updateData.bed_temp = bedTemp;
            if (originalFlowRate !== flowRate) updateData.flow_rate = flowRate;
            if (originalFanSpeed !== fanSpeed) updateData.fan_speed = fanSpeed;
            if (originalRetractionLength !== retractionLength) updateData.retraction_length = retractionLength;
            if (originalRetractionSpeed !== retractionSpeed) updateData.retraction_speed = retractionSpeed;

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
        extruder_temp?: number;
        bed_temp?: number;
        flow_rate?: number;
        fan_speed?: number;
        retraction_length?: number;
        retraction_speed?: number;
        orcaslicer_settings?: Record<string, unknown> | null;
        printer_ids: number[];
        filament_id?: number;
        active?: boolean;
        is_official?: boolean;
      } = {
        name,
        description: description || undefined,
        orcaslicer_settings: orcaslicerSettings,
        printer_ids: selectedPrinterIds.length > 0 ? selectedPrinterIds : [],
      };
      if (preset.extruder_temp !== extruderTemp) updateData.extruder_temp = extruderTemp;
      if (preset.bed_temp !== bedTemp) updateData.bed_temp = bedTemp;
      if (originalFlowRate !== flowRate) updateData.flow_rate = flowRate;
      if (originalFanSpeed !== fanSpeed) updateData.fan_speed = fanSpeed;
      if (originalRetractionLength !== retractionLength) updateData.retraction_length = retractionLength;
      if (originalRetractionSpeed !== retractionSpeed) updateData.retraction_speed = retractionSpeed;
      
      // Если это черновик и выбран филамент - активируем пресет
      if (isDraft && selectedFilamentId) {
        updateData.filament_id = selectedFilamentId;
        updateData.active = true;
        updateData.is_official = isOfficial;
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
  const normalizedMaterialType = materialType.trim();
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
  const draftReviewFacts = draftAnalysis
    ? [
        ['brand_name', t('presetModal.review.brand')],
        ['material_type', t('presetModal.review.material')],
        ['diameter', t('presetModal.review.diameter')],
        ['color_hex', t('presetModal.review.color')],
      ]
        .map(([field, label]) => ({
          field,
          label,
          suggestion: draftAnalysis.suggestions[field],
        }))
        .filter((item) => item.suggestion?.direct)
        .slice(0, 4)
    : [];
  const draftSuggestionCount = draftAnalysis?.suggested_fields.length ?? 0;
  const draftMatchChoices = draftAnalysis?.filament_matches
    .filter((match) => match.confidence === 'exact' || match.confidence === 'strong')
    .slice(0, 3) ?? [];
  const draftDecisions = draftAnalysis
    ? [...draftAnalysis.preset_decisions, ...draftAnalysis.catalog_decisions]
    : [];

  if (!isOpen) return null;

  return (
    <ModalOverlay onClose={requestClose}>
      <div
        className="bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 rounded-2xl w-full max-w-5xl overflow-hidden flex flex-col border border-white/20 shadow-2xl max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
        onMouseDown={(e) => e.stopPropagation()}
        onChangeCapture={() => setFormDirty(true)}
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
            onClick={requestClose}
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
          {isDraft && (
            <div className="rounded-xl border border-cyan-400/25 bg-cyan-500/10 p-4">
              <div className="flex items-start gap-3">
                {draftAnalysisLoading ? (
                  <Loader2 className="mt-0.5 h-5 w-5 shrink-0 animate-spin text-cyan-300" />
                ) : (
                  <Sparkles className="mt-0.5 h-5 w-5 shrink-0 text-cyan-300" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="font-semibold text-white">{t('presetModal.review.title')}</p>
                  <p className="mt-1 text-sm leading-5 text-gray-300">
                    {t('presetModal.review.description')}
                  </p>
                  {draftAnalysis && (
                    <div className="mt-3 grid gap-2 sm:grid-cols-2">
                      <div className="rounded-lg border border-white/10 bg-black/15 px-3 py-2">
                        <div className="flex items-center justify-between gap-3 text-xs text-gray-300">
                          <span>{t('presetModal.review.presetReadiness')}</span>
                          <strong className="tabular-nums text-white">
                            {draftAnalysis.preset_readiness_percent}%
                          </strong>
                        </div>
                        <p className="mt-1 text-[11px] text-gray-400">
                          {t('presetModal.review.technicalSettingsSaved', {
                            count: draftAnalysis.technical_settings_count,
                          })}
                        </p>
                      </div>
                      <div className="rounded-lg border border-white/10 bg-black/15 px-3 py-2">
                        <div className="flex items-center justify-between gap-3 text-xs text-gray-300">
                          <span>{t('presetModal.review.catalogReadiness')}</span>
                          <strong className="tabular-nums text-white">
                            {draftAnalysis.catalog_readiness_percent}%
                          </strong>
                        </div>
                        <p className="mt-1 text-[11px] text-gray-400">
                          {draftDecisions.length > 0
                            ? t('presetModal.review.decisionsRemaining', { count: draftDecisions.length })
                            : t('presetModal.review.noDecisionsRemaining')}
                        </p>
                      </div>
                    </div>
                  )}
                  {draftDecisions.length > 0 && (
                    <div className="mt-3 rounded-lg border border-amber-300/15 bg-amber-400/[0.06] px-3 py-2">
                      <p className="text-xs font-medium text-amber-100">
                        {t('presetModal.review.importantDecisions')}
                      </p>
                      <ul className="mt-1 space-y-0.5 text-xs text-gray-300">
                        {draftDecisions.slice(0, 3).map((decision) => (
                          <li key={decision}>• {t(`presetModal.review.decisions.${decision}`)}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                  {(draftAnalysis?.similar_import_users ?? 0) >= 3 && (
                    <p className="mt-3 text-xs text-cyan-100/80">
                      {t('presetModal.review.similarImports', {
                        count: draftAnalysis?.similar_import_users ?? 0,
                      })}
                    </p>
                  )}
                  {draftReviewFacts.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {draftReviewFacts.map(({ field, label, suggestion }) => (
                        <span
                          key={field}
                          className="rounded-lg border border-cyan-300/20 bg-black/15 px-2.5 py-1 text-xs text-cyan-100"
                          title={t('presetModal.review.fromOrca')}
                        >
                          {label}: {String(suggestion.value)}
                        </span>
                      ))}
                      {draftSuggestionCount > 0 && (
                        <span className="rounded-lg border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-gray-300">
                          {t('presetModal.review.fhSuggestions', { count: draftSuggestionCount })}
                        </span>
                      )}
                    </div>
                  )}
                  {draftMatchChoices.length > 1 && !selectedFilamentId && (
                    <div className="mt-3">
                      <p className="mb-2 text-xs font-medium text-gray-300">
                        {t('presetModal.review.chooseCatalogMatch')}
                      </p>
                      <div className="grid gap-2 sm:grid-cols-2">
                        {draftMatchChoices.map((match) => (
                          <button
                            key={match.id}
                            type="button"
                            onClick={() => {
                              void filamentsAPI.get(match.id).then(selectExistingFilament);
                            }}
                            className="rounded-lg border border-white/15 bg-black/15 px-3 py-2 text-left transition-colors hover:border-cyan-300/40 hover:bg-cyan-400/10"
                          >
                            <span className="block truncate text-sm font-medium text-white">
                              {match.name}
                            </span>
                            <span className="mt-0.5 block truncate text-xs text-gray-400">
                              {[match.material_type, match.color_name].filter(Boolean).join(' · ')}
                            </span>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                  <p className="mt-2 text-xs text-gray-400">
                    {draftAnalysis?.evidence_kind === 'stored_snapshot'
                      ? t('presetModal.review.storedEvidence')
                      : t('presetModal.review.evidencePreserved')}
                  </p>
                </div>
              </div>
            </div>
          )}
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
                    <div className="flex-1">
                      <MaterialTypeSelect
                        label={`${t('presetModal.materialType')} *`}
                        value={materialType}
                        options={sortedMaterialTypes.length > 0 ? sortedMaterialTypes : MATERIAL_TYPES}
                        placeholder={t('presetModal.selectMaterialTypePlaceholder')}
                        onChange={(value) => {
                          setMaterialType(value);
                          // Type density is a suggestion only; the saved value
                          // belongs to the concrete filament being created.
                          const density = densityForMaterial(value) ?? null;
                          if (density) {
                            setFilamentDensity(density);
                          } else {
                            if (!filamentDensity) {
                              setFilamentDensity(1.24);
                            }
                          }
                        }}
                        onSelect={(value) => {
                          // Стандартные параметры пресета — только при явном выборе типа из списка.
                          applyMaterialDefaults(value, {
                            setExtruderTemp,
                            setBedTemp,
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
                      />
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
                    <p className="mt-1.5 text-xs leading-5 text-gray-400">
                      {t('presetModal.filamentNameHint')}
                    </p>
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
                    onColorHexChange={(value) => {
                      setFilamentColorHex(value);
                      setDraftHasColorEvidence(true);
                    }}
                    ralCode={filamentRalCode}
                    onRalCodeChange={setFilamentRalCode}
                    visualSettings={
                      showFilamentAdvancedVisual || resolvedFilamentVisualEffects.length > 0 || filamentVisualColorType !== 'single' || filamentVisualFinish !== 'matte' || filamentVisualTransparency
                        ? {
                            color_type: filamentVisualColorType,
                            colors: filamentVisualColors,
                            finish: filamentVisualFinish,
                            filler: resolvedFilamentVisualEffects[0] || 'none',
                            effects: resolvedFilamentVisualEffects,
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
                    <div className="mt-4 rounded-2xl border border-white/10 bg-white/[0.035] p-3">
                      <div className="grid items-start gap-3 lg:grid-cols-[minmax(18rem,1.15fr)_minmax(0,2fr)]">
                        <div className="space-y-3">
                        {/* Тип цвета */}
                        <div>
                          <div className="grid grid-cols-2 gap-2">
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
                                className={`rounded-lg border px-3 py-1.5 text-sm transition-all ${
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
                                      ref={(element) => {
                                        colorPickerButtonRefs.current[idx] = element;
                                      }}
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
                                    
                                    <FloatingHSLColorPicker
                                      anchorElement={colorPickerButtonRefs.current[idx]}
                                      color={currentColor}
                                      isOpen={isPickerOpen}
                                      onChange={(hex) => {
                                        const newColors = [...filamentVisualColors];
                                        newColors[idx] = hex;
                                        setFilamentVisualColors(newColors);
                                        // Синхронизируем основной цвет, если меняем первый цвет в расширенных настройках
                                        if (idx === 0) {
                                          isInternalColorChangeRef.current = true; // Помечаем как внутреннее изменение
                                          setFilamentColorHex(hex);
                                          setDraftHasColorEvidence(true);
                                        }
                                      }}
                                      onToggle={(isOpen) => {
                                        const newOpenStates = [...openColorPickers];
                                        newOpenStates[idx] = isOpen;
                                        setOpenColorPickers(newOpenStates);
                                      }}
                                    />
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
                                        setDraftHasColorEvidence(true);
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
                          <div className="inline-grid grid-cols-2 gap-1 rounded-xl border border-white/10 bg-black/15 p-1">
                            {(['matte', 'glossy'] as const).map((finish) => (
                              <button
                                key={finish}
                                type="button"
                                onClick={() => setFilamentVisualFinish(finish)}
                                className={`min-w-24 rounded-lg border px-3 py-1.5 text-sm transition-all ${
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
                        </div>

                        <div className="min-w-0 space-y-3">

                        {/* Прозрачность */}
                        <label className="flex cursor-pointer items-center justify-between gap-4 rounded-xl border border-white/10 bg-black/10 px-3 py-2 text-sm font-medium text-gray-200 transition-colors hover:bg-white/[0.06]">
                          <span>{t('presetModal.transparentMaterial')}</span>
                          <input
                            type="checkbox"
                            checked={filamentVisualTransparency}
                            onChange={(e) => { setFilamentVisualTransparency(e.target.checked); }}
                            className="peer sr-only"
                          />
                          <span className="relative h-6 w-11 shrink-0 rounded-full border border-white/15 bg-white/10 transition-colors after:absolute after:left-0.5 after:top-0.5 after:h-[18px] after:w-[18px] after:rounded-full after:bg-gray-300 after:shadow-sm after:transition-transform peer-checked:border-cyan-300/40 peer-checked:bg-cyan-400/25 peer-checked:after:translate-x-5 peer-checked:after:bg-cyan-100 peer-focus-visible:ring-2 peer-focus-visible:ring-cyan-300/60" />
                        </label>

                        <FilamentFeaturesEditor
                          effects={filamentVisualEffects}
                          onEffectsChange={setFilamentVisualEffects}
                          additives={filamentAdditives}
                          onAdditivesChange={setFilamentAdditives}
                          propertyClaims={filamentPropertyClaims}
                          onPropertyClaimsChange={setFilamentPropertyClaims}
                          allowCustom={canOfferOfficial}
                          compact
                        />
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Физические характеристики */}
                  <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    <Dropdown
                      label={`${t('presetModal.diameter')} *`}
                      value={filamentDiameter}
                      options={DIAMETER_OPTIONS.map(d => ({ value: d, label: `${d} mm` }))}
                      onChange={(val) => setFilamentDiameter(String(val))}
                      placeholder={t('presetModal.selectDiameter')}
                    />
                    <DensityField
                      value={filamentDensity === '' ? (densityForMaterial(materialType) ?? 1.24) : filamentDensity}
                      onChange={setFilamentDensity}
                      locked={!canManageTechnicalFacts}
                      label={t('presetModal.density')}
                    />
                  </div>

                  {canManageTechnicalFacts && (
                    <FilamentHandlingEditor
                      value={filamentHandling}
                      onChange={setFilamentHandling}
                      compact
                    />
                  )}

                  {/* Ценовые характеристики - только для производителей */}
                  {canOfferOfficial && (
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <div className="flex items-center justify-between mb-2 gap-2">
                          <label className="text-gray-300 text-sm font-medium">
                            {t(
                              filamentPriceUnit === 'per_spool'
                                ? 'presetModal.pricePerSpool'
                                : 'presetModal.pricePerKg',
                              { currency: filamentPriceCurrency },
                            )}
                          </label>
                          <div className="flex rounded-lg overflow-hidden border border-white/20 text-[11px] shrink-0">
                            <button type="button" onClick={() => setFilamentPriceUnit('per_kg')} className={`px-2 py-0.5 transition-all ${filamentPriceUnit === 'per_kg' ? 'bg-purple-600 text-white' : 'text-gray-400 hover:text-white'}`}>{t('presetModal.perKgShort')}</button>
                            <button type="button" onClick={() => setFilamentPriceUnit('per_spool')} className={`px-2 py-0.5 transition-all ${filamentPriceUnit === 'per_spool' ? 'bg-purple-600 text-white' : 'text-gray-400 hover:text-white'}`}>{t('presetModal.perSpoolShort')}</button>
                          </div>
                        </div>
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

                  {/* Рекомендованный вендором диапазон температур (спека материала) */}
                  <RecommendedTempsField value={filamentRecTemps} onChange={setFilamentRecTemps} />

                  <NozzleHardnessField
                    value={filamentNozzleHrc}
                    onChange={setFilamentNozzleHrc}
                    filler={resolvedFilamentVisualEffects[0] || 'none'}
                    effects={resolvedFilamentVisualEffects}
                    additives={filamentAdditives}
                    materialType={materialType}
                  />

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
              <label className="block text-gray-300 mb-1 text-sm font-medium">{t('presetModal.printers')}</label>
              <p className="mb-2 text-xs leading-4 text-gray-400">{t('presetModal.printersHint')}</p>
          <Dropdown
            label=""
            value=""
            options={
              printersData?.items
                .filter((p) => !selectedPrinterIds.includes(p.id))
                .map((printer: Printer) => ({
                  value: printer.id,
                  label: printerCatalogLabel(printer),
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

          {/* Сам пресет доступен всем; официальный статус выбирается отдельно. */}
          {(!preset || isDraft) && canOfferOfficial && (
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
          
          {/* Информация показывается только когда выбран официальный статус. */}
          {(!preset || isDraft) && isOfficial && (
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
                max={ORCA_MAX_NOZZLE_TEMPERATURE}
                step="1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              />
              {selectedFilament && (selectedFilament.recommended_nozzle_temp_min != null || selectedFilament.recommended_nozzle_temp_max != null) && (
                <p className="mt-1 text-xs text-gray-400">
                  {t('presetModal.vendorRecommended')}: {formatTempRange(selectedFilament.recommended_nozzle_temp_min, selectedFilament.recommended_nozzle_temp_max)} °C
                </p>
              )}
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
                max={ORCA_MAX_BED_TEMPERATURE}
                step="1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              />
              {selectedFilament && (selectedFilament.recommended_bed_temp_min != null || selectedFilament.recommended_bed_temp_max != null) && (
                <p className="mt-1 text-xs text-gray-400">
                  {t('presetModal.vendorRecommended')}: {formatTempRange(selectedFilament.recommended_bed_temp_min, selectedFilament.recommended_bed_temp_max)} °C
                </p>
              )}
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('presetModal.flowRate')} <InfoHint text={t('paramHints.flow')} /></label>
              <input
                type="number"
                value={flowRate}
                onChange={(e) => { setFlowRate(Number(e.target.value)); }}
                min={0.1}
                max={200}
                step="any"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('presetModal.fanSpeed')} <InfoHint text={t('paramHints.fanSpeed')} /></label>
              <input
                type="number"
                value={fanSpeed}
                onChange={(e) => {
                  const value = Number(e.target.value);
                  setFanSpeed(value);
                  setFanMinSpeed(value);
                }}
                min={0}
                max={100}
                step="1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              />
            </div>
          </div>

          {/* OrcaSlicer Settings Tabs (как в OrcaSlicer) */}
          <div className="mt-6">
            <div className="flex items-center justify-between mb-4 gap-3 flex-wrap">
              <h3 className="text-lg font-semibold text-white">{t('presetModal.detailedSettings')}</h3>
              {/* Уровень сложности (Simple/Advanced/Expert) — как в OrcaSlicer, выбор сохраняется */}
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-400">{t('presetModal.settingMode.label')}</span>
                <div className="inline-flex rounded-lg border border-white/20 overflow-hidden text-xs">
                  {(['simple', 'advanced', 'expert'] as SettingMode[]).map((m) => (
                    <button
                      key={m}
                      type="button"
                      onClick={() => setSettingMode(m)}
                      className={`px-3 py-1 transition-all ${settingMode === m ? 'bg-purple-600 text-white' : 'text-gray-400 hover:text-white'}`}
                    >
                      {t(`presetModal.settingMode.${m}`)}
                    </button>
                  ))}
                </div>
              </div>
            </div>

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
              {isVisibleAtMode('advanced', settingMode) && (
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
              )}
              {isVisibleAtMode('advanced', settingMode) && (
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
              )}
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
                    <div className={`flex items-center space-x-3 ${isVisibleAtMode('advanced', settingMode) ? '' : 'hidden'}`}>
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
                      <InfoHint text={t('paramHints.soluble')} />
                    </div>

                    {/* Поддержка */}
                    <div className={`flex items-center space-x-3 ${isVisibleAtMode('advanced', settingMode) ? '' : 'hidden'}`}>
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
                      <InfoHint text={t('paramHints.supportMaterial')} />
                    </div>

                    {/* Группа адгезивности (свойство материала; в Orca comDevelop → expert) */}
                    <div className={isVisibleAtMode('expert', settingMode) ? '' : 'hidden'}>
                      <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.adhesivenessCategory')} <InfoHint text={t('paramHints.adhesiveness')} /></label>
                      <input
                        type="number"
                        value={filamentAdhesivenessCategory}
                        onChange={(e) => { setFilamentAdhesivenessCategory(e.target.value === '' ? '' : Number(e.target.value)); }}
                        min={0}
                        step="1"
                        placeholder="0"
                        className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                      />
                    </div>

                    {/* Filament ramming length — MMU-параметр (advanced) */}
                    <div className={isVisibleAtMode('advanced', settingMode) ? '' : 'hidden'}>
                      <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.filamentRammingLength')} <InfoHint text={t('paramHints.multitoolRammingVolume')} /></label>
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
                    <div className={isVisibleAtMode('advanced', settingMode) ? '' : 'hidden'}>
                      <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.shrinkXY')} <InfoHint text={t('paramHints.shrinkXY')} /></label>
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
                    <div className={isVisibleAtMode('advanced', settingMode) ? '' : 'hidden'}>
                      <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.shrinkZ')} <InfoHint text={t('paramHints.shrinkZ')} /></label>
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
                      <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.softeningTemp')} <InfoHint text={t('paramHints.softeningTemp')} /></label>
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
                      <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.idleTemp')} <InfoHint text={t('paramHints.idleTemp')} /></label>
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
                <div className={isVisibleAtMode('advanced', settingMode) ? '' : 'hidden'}>
                  <h4 className="text-sm font-semibold text-white mb-3">{t('presetModal.recommendedNozzleTemp')}</h4>
                  <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="block text-gray-400 mb-1 text-xs">{t('presetModal.min')} (°C)</label>
                        <input
                          type="number"
                          value={tempRangeLow}
                          onChange={(e) => { setTempRangeLow(e.target.value === '' ? '' : Number(e.target.value)); }}
                          min={150}
                          max={ORCA_MAX_NOZZLE_TEMPERATURE}
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
                          max={ORCA_MAX_NOZZLE_TEMPERATURE}
                          step="1"
                          placeholder="260"
                          className="w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                        />
                      </div>
                    </div>
                  </div>

                {/* Коэффициент потока и Pressure Advance */}
                <div className={isVisibleAtMode('advanced', settingMode) ? '' : 'hidden'}>
                  <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.flowAndPA')}</h4>
                  
                  <div className="space-y-4">
                    {/* Коэф. потока модели */}
                    <div>
                      <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.modelFlowRatio')} <InfoHint text={t('paramHints.flow')} /></label>
                      <input
                        type="number"
                        value={parseFloat((flowRate / 100).toFixed(6))}
                        onChange={(e) => { setFlowRate(e.target.value === '' ? 100 : parseFloat((Number(e.target.value) * 100).toFixed(6))); }}
                        min={0.001}
                        max={2}
                        step="any"
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
                      <InfoHint text={t('paramHints.pressureAdvance')} />
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
                      <InfoHint text={t('paramHints.adaptivePA')} />
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
                      <InfoHint text={t('paramHints.adaptivePAOverhangs')} />
                    </div>

                    {/* Коэф. Pressure advance для мостов */}
                    {adaptivePressureAdvance && (
                      <div>
                        <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.paBridges')} <InfoHint text={t('paramHints.adaptivePABridges')} /></label>
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
                    {adaptivePressureAdvance && isVisibleAtMode('expert', settingMode) && (
                      <div>
                        <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.adaptivePAMeasured')} <InfoHint text={t('paramHints.adaptivePAMeasured')} /></label>
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
                  
                  <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] md:items-end">
                    <div>
                      <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.chamberTargetTemp')}</label>
                      <div className="relative">
                        <input
                          type="number"
                          value={chamberTemp}
                          onChange={(e) => { setChamberTemp(e.target.value === '' ? '' : Number(e.target.value)); }}
                          min={0}
                          max={100}
                          step="1"
                          placeholder="45"
                          className={`w-full pl-3 pr-10 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                        />
                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">°C</span>
                      </div>
                    </div>

                    <div>
                      <label className="block text-gray-300 mb-1 text-sm">
                        {t('presetModal.chamberMinimalTemp')}{' '}
                        <InfoHint text={t('paramHints.chamberMinimalTemp')} />
                      </label>
                      <div className="relative">
                        <input
                          type="number"
                          value={chamberMinimalTemp}
                          onChange={(e) => { setChamberMinimalTemp(e.target.value === '' ? '' : Number(e.target.value)); }}
                          min={0}
                          max={chamberTemp === '' ? 100 : chamberTemp}
                          step="1"
                          placeholder="0"
                          className="w-full rounded-lg border border-white/20 bg-white/10 py-2 pl-3 pr-10 text-sm text-white placeholder-gray-500 transition-all focus:border-transparent focus:outline-none focus:ring-2 focus:ring-purple-500"
                        />
                        <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">°C</span>
                      </div>
                    </div>

                    <div className="flex items-center space-x-3 pb-2">
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
                      <InfoHint text={t('paramHints.chamberTemp')} />
                    </div>
                  </div>
                </div>

                {/* Температура печати */}
                <div>
                  <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.printTemp')}</h4>
                  
                  <div className="grid grid-cols-2 gap-4">
                    {/* Слева: Сопло */}
                    <div>
                      <label className="block text-gray-300 mb-2 text-sm">{t('presetModal.nozzle')} <InfoHint text={t('paramHints.extruderTemp')} /></label>
                      <div className="space-y-3">
                        <div>
                          <label className="block text-gray-400 mb-1 text-xs">{t('presetModal.firstLayer')} <InfoHint text={t('paramHints.extruderTempFirst')} /></label>
                          <div className="relative">
                            <input
                              type="number"
                              value={nozzleTempInitialLayer !== '' ? nozzleTempInitialLayer : extruderTemp}
                              onChange={(e) => { setNozzleTempInitialLayer(e.target.value === '' ? '' : Number(e.target.value)); }}
                              min={150}
                              max={ORCA_MAX_NOZZLE_TEMPERATURE}
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
                      <label className="block text-gray-300 mb-2 text-sm">{t('presetModal.bed')} <InfoHint text={t('paramHints.bedTemp')} /></label>
                      <div className="space-y-3">
                        <div>
                          <label className="block text-gray-400 mb-1 text-xs">{t('presetModal.firstLayer')} <InfoHint text={t('paramHints.bedTempFirst')} /></label>
                          <div className="relative">
                          <input
                            type="number"
                            value={bedTempInitialLayer !== '' ? bedTempInitialLayer : bedTemp}
                            onChange={(e) => {
                              setBedTempInitialLayer(e.target.value === '' ? '' : Number(e.target.value));
                            }}
                            min={0}
                            max={ORCA_MAX_BED_TEMPERATURE}
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
                <div className={isVisibleAtMode('advanced', settingMode) ? '' : 'hidden'}>
                  <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.volumetricLimit')}</h4>
                  
                  <div className="space-y-3">
                    <div className={`flex items-center space-x-3 ${isVisibleAtMode('expert', settingMode) ? '' : 'hidden'}`}>
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
                      <InfoHint text={t('paramHints.adaptiveFlow')} />
                    </div>

                    <div>
                      <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.maxVolumetricSpeed')} <InfoHint text={t('paramHints.maxVolumetricSpeed')} /></label>
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
                    
                    <div className="grid gap-4 md:grid-cols-2">
                      {/* Не включать вентилятор на первых */}
                      <div>
                        <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.disableFanFirstLayers')} <InfoHint text={t('paramHints.closeFanFirstLayers')} /></label>
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

                      <div className={isVisibleAtMode('advanced', settingMode) ? '' : 'hidden'}>
                        <label className="block text-gray-300 mb-1 text-sm">
                          {t('presetModal.initialLayerFanSpeed')}{' '}
                          <InfoHint text={t('paramHints.initialLayerFanSpeed')} />
                        </label>
                        <div className="relative">
                          <input
                            type="number"
                            value={Number(closeFanFirstXLayers) > 0 ? -1 : initialLayerFanSpeed}
                            onChange={(e) => { setInitialLayerFanSpeed(e.target.value === '' ? '' : Number(e.target.value)); }}
                            min={-1}
                            max={100}
                            step="1"
                            placeholder="-1"
                            disabled={Number(closeFanFirstXLayers) > 0}
                            className="w-full rounded-lg border border-white/20 bg-white/10 py-2 pl-3 pr-8 text-sm text-white placeholder-gray-500 transition-all focus:border-transparent focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:cursor-not-allowed disabled:opacity-50"
                          />
                          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">%</span>
                        </div>
                      </div>

                      {/* Полная скорость вентилятора на слое */}
                      <div className={isVisibleAtMode('advanced', settingMode) ? '' : 'hidden'}>
                        <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.fullFanSpeedLayer')} <InfoHint text={t('paramHints.fullFanSpeedLayer')} /></label>
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
                        <label className="block text-gray-300 mb-2 text-sm font-medium">{t('presetModal.minFanThreshold')} <InfoHint text={t('paramHints.minFanThreshold')} /></label>
                        <div className="grid grid-cols-2 gap-3">
                          <div>
                            <label className="block text-gray-400 mb-1 text-xs">{t('presetModal.fanSpeedLabel')}</label>
                            <div className="relative">
                              <input
                                type="number"
                                value={fanMinSpeed}
                                onChange={(e) => {
                                  const value = e.target.value === '' ? '' : Number(e.target.value);
                                  setFanMinSpeed(value);
                                  if (value !== '') setFanSpeed(value);
                                }}
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
                        <label className="block text-gray-300 mb-2 text-sm font-medium">{t('presetModal.maxFanThreshold')} <InfoHint text={t('paramHints.maxFanThreshold')} /></label>
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
                        <InfoHint text={t('paramHints.fanAlwaysOn')} />
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
                        <InfoHint text={t('paramHints.slowForCooling')} />
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
                        <InfoHint text={t('paramHints.dontSlowOuterWall')} />
                      </div>

                      {/* Минимальная скорость печати */}
                      {slowDownForLayerCooling && isVisibleAtMode('advanced', settingMode) && (
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.minPrintSpeed')} <InfoHint text={t('paramHints.minPrintSpeed')} /></label>
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
                      <div className={`flex items-center space-x-3 ${isVisibleAtMode('advanced', settingMode) ? '' : 'hidden'}`}>
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
                        <InfoHint text={t('paramHints.overhangFan')} />
                      </div>

                      {/* Порог нависания для включения обдува */}
                      {enableOverhangBridgeFan && isVisibleAtMode('advanced', settingMode) && (
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.overhangFanThreshold')} <InfoHint text={t('paramHints.overhangThreshold')} /></label>
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
                      {enableOverhangBridgeFan && isVisibleAtMode('advanced', settingMode) && (
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.overhangBridgeFanSpeed')} <InfoHint text={t('paramHints.overhangFanSpeed')} /></label>
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
                      {enableOverhangBridgeFan && isVisibleAtMode('advanced', settingMode) && (
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.internalBridgeFanSpeed')} <InfoHint text={t('paramHints.internalBridgeFanSpeed')} /></label>
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
                      {enableOverhangBridgeFan && isVisibleAtMode('advanced', settingMode) && (
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.supportInterfaceFanSpeed')} <InfoHint text={t('paramHints.supportInterfaceFanSpeed')} /></label>
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
                      <div className={isVisibleAtMode('advanced', settingMode) ? '' : 'hidden'}>
                        <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.ironingFanSpeed')} <InfoHint text={t('paramHints.ironingFanSpeed')} /></label>
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
                    <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.auxiliaryFan')} <InfoHint text={t('paramHints.auxiliaryFan')} /></h4>
                    
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
                        <InfoHint text={t('paramHints.exhaustFan')} />
                      </div>

                      {enableExhaustFan && (
                        <>
                          <div className="grid gap-4 md:grid-cols-2">
                            <div>
                              <label className="mb-2 flex items-center gap-2 text-sm text-gray-300">
                                <input
                                  type="checkbox"
                                  checked={activateAirFiltrationDuringPrint}
                                  onChange={(e) => { setActivateAirFiltrationDuringPrint(e.target.checked); }}
                                  className="h-4 w-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
                                />
                                {t('presetModal.exhaustFanDuringPrint')}
                              </label>
                              <div className="relative">
                                <input
                                  type="number"
                                  value={duringPrintExhaustFanSpeed}
                                  onChange={(e) => { setDuringPrintExhaustFanSpeed(e.target.value === '' ? '' : Number(e.target.value)); }}
                                  min={0}
                                  max={100}
                                  step="1"
                                  placeholder="60"
                                  disabled={!activateAirFiltrationDuringPrint}
                                  className="w-full rounded-lg border border-white/20 bg-white/10 py-2 pl-3 pr-8 text-sm text-white placeholder-gray-500 transition-all focus:border-transparent focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:cursor-not-allowed disabled:opacity-50"
                                />
                                <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">%</span>
                              </div>
                            </div>

                            <div>
                              <label className="mb-2 flex items-center gap-2 text-sm text-gray-300">
                                <input
                                  type="checkbox"
                                  checked={activateAirFiltrationOnCompletion}
                                  onChange={(e) => { setActivateAirFiltrationOnCompletion(e.target.checked); }}
                                  className="h-4 w-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
                                />
                                {t('presetModal.exhaustFanAfterPrint')}
                              </label>
                              <div className="relative">
                                <input
                                  type="number"
                                  value={completePrintExhaustFanSpeed}
                                  onChange={(e) => { setCompletePrintExhaustFanSpeed(e.target.value === '' ? '' : Number(e.target.value)); }}
                                  min={0}
                                  max={100}
                                  step="1"
                                  placeholder="80"
                                  disabled={!activateAirFiltrationOnCompletion}
                                  className="w-full rounded-lg border border-white/20 bg-white/10 py-2 pl-3 pr-8 text-sm text-white placeholder-gray-500 transition-all focus:border-transparent focus:outline-none focus:ring-2 focus:ring-purple-500 disabled:cursor-not-allowed disabled:opacity-50"
                                />
                                <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">%</span>
                              </div>
                            </div>
                          </div>
                        </>
                      )}
                    </div>
                  </div>

                </div>
              )}

              {activeTab === 'override' && (
                <div className="space-y-6">
                  {/* Откат */}
                  <div>
                    <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.retraction')}</h4>
                    
                    <div className="space-y-4">
                      {/* Первая строка: Длина / Скорость извлечения */}
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.length')} <InfoHint text={t('paramHints.retractionLength')} /></label>
                          <div className="relative">
                            <input
                              type="number"
                              value={retractionLength}
                              onChange={(e) => { setRetractionLength(Number(e.target.value)); }}
                              min={0}
                              max={20}
                              step="any"
                              placeholder="0.8"
                              className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm</span>
                          </div>
                        </div>
                        <div className={isVisibleAtMode('advanced', settingMode) ? '' : 'hidden'}>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.retractionExtractSpeed')} <InfoHint text={t('paramHints.retractionSpeed')} /></label>
                          <div className="relative">
                            <input
                              type="number"
                              value={retractionSpeed}
                              onChange={(e) => { setRetractionSpeed(Number(e.target.value)); }}
                              min={0}
                              max={200}
                              step="any"
                              placeholder="30"
                              className={`w-full pl-3 pr-12 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                            />
                            <span className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400 pointer-events-none">mm/s</span>
                          </div>
                        </div>
                      </div>

                      {/* Вторая строка: Высота поднятия оси Z / Скорость заправки */}
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.zHopHeight')} <InfoHint text={t('paramHints.zHop')} /></label>
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
                        <div className={isVisibleAtMode('advanced', settingMode) ? '' : 'hidden'}>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.deretractionSpeed')} <InfoHint text={t('paramHints.deretractionSpeed')} /></label>
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

                      {/* Третья строка: Тип подъёма оси Z / На поверхностях (advanced) */}
                      <div className={`grid grid-cols-2 gap-4 ${isVisibleAtMode('advanced', settingMode) ? '' : 'hidden'}`}>
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.zHopType')} <InfoHint text={t('paramHints.zHopType')} /></label>
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
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.onSurfaces')} <InfoHint text={t('paramHints.liftEnforce')} /></label>
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

                      {/* Четвертая строка: Приподнимать ось Z только выше / Приподнимать ось Z только ниже (advanced) */}
                      <div className={`grid grid-cols-2 gap-4 ${isVisibleAtMode('advanced', settingMode) ? '' : 'hidden'}`}>
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.liftZAbove')} <InfoHint text={t('paramHints.liftAbove')} /></label>
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
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.liftZBelow')} <InfoHint text={t('paramHints.liftBelow')} /></label>
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

                      {/* Пятая строка: Доп. длина подачи / Порог перемещения (advanced) */}
                      <div className={`grid grid-cols-2 gap-4 ${isVisibleAtMode('advanced', settingMode) ? '' : 'hidden'}`}>
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.extraRestartLength')} <InfoHint text={t('paramHints.retractRestartExtra')} /></label>
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
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.retractionMinTravel')} <InfoHint text={t('paramHints.retractMinTravel')} /></label>
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

                      {/* Чекбоксы: Откат при смене слоя / Очистка сопла (advanced) */}
                      <div className={`grid grid-cols-2 gap-4 ${isVisibleAtMode('advanced', settingMode) ? '' : 'hidden'}`}>
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
                          <InfoHint text={t('paramHints.retractOnLayerChange')} />
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
                          <InfoHint text={t('paramHints.wipe')} />
                        </div>
                      </div>

                      {/* Расстояние очистки / Величина отката перед очисткой (advanced) */}
                      {filamentWipe && isVisibleAtMode('advanced', settingMode) && (
                        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                          <div>
                            <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.wipeDistance')} <InfoHint text={t('paramHints.wipeDistance')} /></label>
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
                            <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.retractBeforeWipe')} <InfoHint text={t('paramHints.retractBeforeWipe')} /></label>
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
                          <div className={isVisibleAtMode('expert', settingMode) ? '' : 'hidden'}>
                            <label className="block text-gray-300 mb-1 text-sm">
                              {t('presetModal.retractAfterWipe')}{' '}
                              <InfoHint text={t('paramHints.retractAfterWipe')} />
                            </label>
                            <div className="relative">
                              <input
                                type="number"
                                value={retractAfterWipe}
                                onChange={(e) => { setRetractAfterWipe(e.target.value); }}
                                min={0}
                                max={Math.max(0, 100 - (Number(retractBeforeWipe) || 0))}
                                step="1"
                                placeholder="0"
                                className="w-full rounded-lg border border-white/20 bg-white/10 py-2 pl-3 pr-8 text-sm text-white placeholder-gray-500 transition-all focus:border-transparent focus:outline-none focus:ring-2 focus:ring-purple-500"
                              />
                              <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">%</span>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className={isVisibleAtMode('advanced', settingMode) ? '' : 'hidden'}>
                    <h4 className="mb-3 border-b border-white/10 pb-2 text-sm font-semibold text-white">
                      {t('presetModal.retractionOnMaterialChange')}
                    </h4>
                    <div className="grid gap-4 md:grid-cols-2">
                      <div>
                        <label className="block text-gray-300 mb-1 text-sm">
                          {t('presetModal.retractLengthToolchange')}{' '}
                          <InfoHint text={t('paramHints.retractLengthToolchange')} />
                        </label>
                        <div className="relative">
                          <input
                            type="number"
                            value={retractLengthToolchange}
                            onChange={(e) => { setRetractLengthToolchange(e.target.value === '' ? '' : Number(e.target.value)); }}
                            min={0}
                            step="0.1"
                            placeholder="10"
                            className="w-full rounded-lg border border-white/20 bg-white/10 py-2 pl-3 pr-12 text-sm text-white placeholder-gray-500 transition-all focus:border-transparent focus:outline-none focus:ring-2 focus:ring-purple-500"
                          />
                          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">mm</span>
                        </div>
                      </div>
                      <div>
                        <label className="block text-gray-300 mb-1 text-sm">
                          {t('presetModal.retractRestartExtraToolchange')}{' '}
                          <InfoHint text={t('paramHints.retractRestartExtraToolchange')} />
                        </label>
                        <div className="relative">
                          <input
                            type="number"
                            value={retractRestartExtraToolchange}
                            onChange={(e) => { setRetractRestartExtraToolchange(e.target.value === '' ? '' : Number(e.target.value)); }}
                            step="0.1"
                            placeholder="0"
                            className="w-full rounded-lg border border-white/20 bg-white/10 py-2 pl-3 pr-12 text-sm text-white placeholder-gray-500 transition-all focus:border-transparent focus:outline-none focus:ring-2 focus:ring-purple-500"
                          />
                          <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs text-gray-400">mm</span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Дополнительные параметры ретракта */}
                  <div>
                    <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.additionalRetractParams')}</h4>
                    
                    <div className="space-y-4">
                      {/* Первая строка: Расстояния при обрезке / Длинные ретракты при обрезке */}
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.retractDistanceCut')} <InfoHint text={t('paramHints.retractDistanceCut')} /></label>
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
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.longRetractsCut')} <InfoHint text={t('paramHints.longRetractCut')} /></label>
                          <input
                            type="text"
                            value={longRetractionsWhenCut}
                            onChange={(e) => { setLongRetractionsWhenCut(e.target.value); }}
                            placeholder="nil"
                            className={`w-full px-3 py-2 bg-white/10 border border-white/20 rounded-lg text-white placeholder-gray-500 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all `}
                          />
                        </div>
                      </div>

                      {/* Длинные ретракты при смене экструдера (advanced) */}
                      <div className={`flex items-center space-x-3 ${isVisibleAtMode('advanced', settingMode) ? '' : 'hidden'}`}>
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
                        <InfoHint text={t('paramHints.longRetractEC')} />
                      </div>

                      {/* Расстояния ретракта при смене экструдера (advanced) */}
                      {longRetractionsWhenEC && isVisibleAtMode('advanced', settingMode) && (
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.retractDistanceEC')} <InfoHint text={t('paramHints.retractDistanceEC')} /></label>
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
                    <h4 className="mb-3 flex items-center space-x-2 border-b border-white/10 pb-2 text-sm font-semibold text-white">
                      <span className="text-gray-400">&lt; &gt;</span>
                      <span>{t('presetModal.changeExtrusionRoleGcode')}</span>
                    </h4>
                    <div
                      className="flex items-start space-x-3"
                      onClick={(e) => e.stopPropagation()}
                      onMouseDown={(e) => e.stopPropagation()}
                    >
                      <textarea
                        id="filament-change-extrusion-role-gcode"
                        value={filamentChangeExtrusionRoleGcode}
                        onChange={(e) => { setFilamentChangeExtrusionRoleGcode(e.target.value); }}
                        placeholder="; G-code for extrusion role change"
                        rows={8}
                        className="flex-1 resize-y rounded-lg border border-white/20 bg-white/10 px-3 py-2 font-mono text-sm text-white placeholder-gray-500 transition-all focus:border-transparent focus:outline-none focus:ring-2 focus:ring-purple-500"
                      />
                      <EditGCodeModal
                        isOpen={activeTab === 'advanced'}
                        onClose={() => {}}
                        onInsert={(placeholderText) => {
                          const textarea = document.getElementById('filament-change-extrusion-role-gcode') as HTMLTextAreaElement;
                          if (!textarea) return;

                          const start = textarea.selectionStart;
                          const end = textarea.selectionEnd;
                          const nextValue = `${filamentChangeExtrusionRoleGcode.substring(0, start)}${placeholderText}${filamentChangeExtrusionRoleGcode.substring(end)}`;
                          setFilamentChangeExtrusionRoleGcode(nextValue);

                          setTimeout(() => {
                            const nextCursorPosition = start + placeholderText.length;
                            textarea.setSelectionRange(nextCursorPosition, nextCursorPosition);
                            textarea.focus();
                          }, 0);
                        }}
                        title="Placeholders"
                        gcodeType="filament_change_extrusion_role_gcode"
                      />
                    </div>
                    <p className="mt-2 text-xs text-gray-500">
                      {t('presetModal.changeExtrusionRoleGcodeHint')}
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
                    </div>
                  </div>

                  {/* Параметры черновой башни */}
                  <div>
                    <h4 className="text-sm font-semibold text-white mb-3 pb-2 border-b border-white/10">{t('presetModal.wipeTowerParams')}</h4>
                    
                    <div>
                      <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.minPurgeVolume')} <InfoHint text={t('paramHints.minPurge')} /></label>
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
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.loadingSpeedStart')} <InfoHint text={t('paramHints.loadSpeedStart')} /></label>
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
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.loadingSpeed')} <InfoHint text={t('paramHints.loadSpeed')} /></label>
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
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.unloadingSpeedStart')} <InfoHint text={t('paramHints.unloadSpeedStart')} /></label>
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
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.unloadingSpeed')} <InfoHint text={t('paramHints.unloadSpeed')} /></label>
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
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.toolchangeDelay')} <InfoHint text={t('paramHints.toolchangeDelay')} /></label>
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
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.coolingMoves')} <InfoHint text={t('paramHints.coolingMoves')} /></label>
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
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.coolingInitialSpeed')} <InfoHint text={t('paramHints.coolingInitialSpeed')} /></label>
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
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.coolingFinalSpeed')} <InfoHint text={t('paramHints.coolingFinalSpeed')} /></label>
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
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.stampingLoadSpeed')} <InfoHint text={t('paramHints.stampingLoadSpeed')} /></label>
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
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.stampingDistance')} <InfoHint text={t('paramHints.stampingDistance')} /></label>
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
                        <InfoHint text={t('paramHints.multitoolRamming')} />
                      </div>

                      {/* Объём рэмминга многоинструментального принтера / Поток рэмминга многоинструментального принтера */}
                      <div className="grid grid-cols-2 gap-4">
                        <div>
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.multitoolRammingVolume')} <InfoHint text={t('paramHints.multitoolRammingVolume')} /></label>
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
                          <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.multitoolRammingFlow')} <InfoHint text={t('paramHints.multitoolRammingFlow')} /></label>
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
                        <label className="block text-gray-300 mb-1 text-sm">{t('presetModal.filamentChangeLength')} <InfoHint text={t('paramHints.filamentChangeLength')} /></label>
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
                onClick={requestClose}
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
                    {isDraft ? <Sparkles className="w-4 h-4" /> : <Save className="w-4 h-4" />}
                    <span>
                      {isDraft
                        ? t('presetModal.review.publish')
                        : preset
                          ? t('presetModal.save')
                          : t('presetModal.create')}
                    </span>
                  </>
                )}
              </button>
            </div>
          </div>
        </form>
        </div>
      </div>
      <ConfirmModal
        isOpen={showDiscardConfirm}
        onClose={() => setShowDiscardConfirm(false)}
        onConfirm={() => { setShowDiscardConfirm(false); onClose(); }}
        title={t('unsavedGuard.title')}
        message={t('unsavedGuard.message')}
        confirmText={t('unsavedGuard.confirm')}
        cancelText={t('unsavedGuard.cancel')}
      />
    </ModalOverlay>
  );
};
