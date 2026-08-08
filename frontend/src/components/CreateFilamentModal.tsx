/** Модальное окно для создания/редактирования материала */

import { useState, useEffect, FormEvent, useRef, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Save, Loader2, Check, Download, QrCode } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { filamentsAPI, brandsAPI, qrAPI, filamentLinesAPI } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { MATERIAL_DENSITY } from '../utils/materialDensity';
import { ColorMaterialSection } from './ColorMaterialSection';
import { FilamentPaletteForm } from './FilamentPaletteForm';
import { FloatingHSLColorPicker } from './FloatingHSLColorPicker';
import { PriceUnitField } from './PriceUnitField';
import type { FilamentAdditive, FilamentPropertyClaim, FilamentVisualSettings } from '../types/api';
import { Dropdown } from './Dropdown';
import { sortMaterialTypes } from '../data/materialDefaults';
import { countryName } from '../utils/countries';
import { currencySymbol, defaultCurrencyForCountry } from '../utils/currency';
import type { Filament, Brand, FilamentAvailability } from '../types/api';
import { useAuth } from '../contexts/AuthContext';
import { MaterialTypeSelect, FALLBACK_TYPES } from './MaterialTypeSelect';
import { AvailabilitySelect } from './AvailabilitySelect';
import { DensityField } from './DensityField';
import { RecommendedTempsField, RecommendedTemps, EMPTY_RECOMMENDED_TEMPS } from './RecommendedTempsField';
import { NozzleHardnessField } from './NozzleHardnessField';
import { FeedbackModal } from './FeedbackModal';
import { ModalOverlay } from './ModalOverlay';
import { ConfirmModal } from './ConfirmModal';
import { InfoHint } from './InfoHint';
import { FilamentFeaturesEditor } from './FilamentFeaturesEditor';
import { deriveVisualEffectsFromAdditives, mergeVisualEffects } from '../data/filamentFeatures';
import type { AxiosError } from 'axios';

interface CreateFilamentModalProps {
  isOpen: boolean;
  onClose: () => void;
  filament?: Filament | null; // Если передан, то редактирование, иначе создание
  brandId?: number; // ID бренда (если создание нового материала)
}

export const CreateFilamentModal: React.FC<CreateFilamentModalProps> = ({
  isOpen,
  onClose,
  filament,
  brandId,
}) => {
  const { t, i18n } = useTranslation();
  const [brandIdValue, setBrandIdValue] = useState<number | null>(brandId || null);
  const [formMode, setFormMode] = useState<'single' | 'palette'>('single');
  const [formDirty, setFormDirty] = useState(false);
  const [showDiscardConfirm, setShowDiscardConfirm] = useState(false);
  const requestClose = () => {
    if (formDirty) setShowDiscardConfirm(true);
    else onClose();
  };
  const [name, setName] = useState('');
  const [materialType, setMaterialType] = useState('');
  const [customMaterialType, setCustomMaterialType] = useState('');
  const [colorName, setColorName] = useState('');
  const [colorHex, setColorHex] = useState('#808080');
  const [ralCode, setRalCode] = useState('');
  // Расширенные характеристики цвета
  const [visualColorType, setVisualColorType] = useState<'single' | 'two' | 'three' | 'gradient' | 'transition' | 'thermochromic'>('single');
  const [visualColors, setVisualColors] = useState<string[]>(['#808080']);
  const [visualFinish, setVisualFinish] = useState<'matte' | 'glossy'>('matte');
  const [visualEffects, setVisualEffects] = useState<string[]>([]);
  const [additives, setAdditives] = useState<FilamentAdditive[]>([]);
  const [propertyClaims, setPropertyClaims] = useState<FilamentPropertyClaim[]>([]);
  const [lineId, setLineId] = useState<number | ''>('');
  const [newLineName, setNewLineName] = useState('');
  const [visualTransparency, setVisualTransparency] = useState(false);
  const [showAdvancedVisual, setShowAdvancedVisual] = useState(false); // Collapsible секция
  const [openColorPickers, setOpenColorPickers] = useState<boolean[]>([]);
  const colorPickerButtonRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const [diameter, setDiameter] = useState(1.75);
  const [density, setDensity] = useState(1.24);
  const [priceMode, setPriceMode] = useState<'per_kg' | 'per_spool'>('per_kg');

  // Общую цену задаёт только тот, у кого область — весь мир.
  const territoriesQuery = useQuery({
    queryKey: ['brand-territories', brandIdValue],
    queryFn: () => brandsAPI.myTerritories(brandIdValue!),
    enabled: !!brandIdValue,
  });
  // Область организации: если она страновая, форма правит её ячейку.
  const scopeCountry = (territoriesQuery.data?.territories ?? [])
    .map((item) => item.country)
    .find((code): code is string => code !== null);

  const countryCell = useQuery({
    queryKey: ['filament-country-cells', filament?.id],
    queryFn: () => filamentsAPI.countryCells(filament!.id),
    enabled: !!filament?.id && !!scopeCountry,
  });

  useEffect(() => {
    if (!scopeCountry || !countryCell.data) return;
    const cell = countryCell.data.find((item) => item.country === scopeCountry);
    if (!cell) return;
    // Пусто в ячейке означает «как у всех», поэтому общее остаётся видимым.
    if (cell.market_color_name) setColorName(cell.market_color_name);
    if (cell.price) {
      if (cell.price_display_unit === 'per_spool') {
        setPriceMode('per_spool');
        setPricePerSpool(cell.price);
      } else {
        setPriceMode('per_kg');
        setPricePerKg(cell.price);
      }
    }
  }, [scopeCountry, countryCell.data]);

  const saveCountryCell = useMutation({
    mutationFn: async (payload: Record<string, unknown> & { country: string }) => {
      const exists = (countryCell.data ?? []).some((cell) => cell.country === payload.country);
      const { country, ...rest } = payload;
      return exists
        ? filamentsAPI.updateCountryCell(filament!.id, country, { ...rest, published: true })
        : filamentsAPI.createCountryCell(filament!.id, { country, ...rest, published: true });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['brand-filaments'] });
      queryClient.invalidateQueries({ queryKey: ['filament-country-cells', filament?.id] });
      onClose();
    },
  });

  const [pricePerKg, setPricePerKg] = useState(0);
  const [pricePerSpool, setPricePerSpool] = useState(0);
  const [spoolWeight, setSpoolWeight] = useState(1000);
  const [emptySpoolWeight, setEmptySpoolWeight] = useState<number | null>(null);
  const [recTemps, setRecTemps] = useState<RecommendedTemps>(EMPTY_RECOMMENDED_TEMPS);
  const [nozzleHrc, setNozzleHrc] = useState<number | null>(null);
  const [description, setDescription] = useState('');
  const [availability, setAvailability] = useState<FilamentAvailability>('available');
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [createdFilament, setCreatedFilament] = useState<Filament | null>(null); // Для отображения QR-кода после создания

  const queryClient = useQueryClient();
  const { user } = useAuth();
  const [typoOpen, setTypoOpen] = useState(false);

  
  // Ref для отслеживания внутренних изменений цвета (из расширенных настроек)
  const isInternalColorChangeRef = useRef(false);

  // Синхронизация colorHex с visualColors[0] при изменении цвета через пикер/HEX инпут
  useEffect(() => {
    // Пропускаем синхронизацию, если изменение было из расширенных настроек
    if (isInternalColorChangeRef.current) {
      isInternalColorChangeRef.current = false;
      return;
    }

    // Только если цвет изменился и это не пустая строка, и первый цвет в массиве отличается
    if (colorHex && colorHex !== '' && visualColors.length > 0) {
      // Синхронизируем только если первый цвет отличается (чтобы избежать бесконечных обновлений)
      if (visualColors[0] !== colorHex) {
        setVisualColors(prev => {
          const newColors = [...prev];
          newColors[0] = colorHex;
          return newColors;
        });
      }
    }
  }, [colorHex, visualColors]);

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
          setOpenColorPickers(new Array(Math.max(openColorPickers.length, 5)).fill(false));
        }
      }
    };

    document.addEventListener('mousedown', handleClickOutside, true);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside, true);
    };
  }, [openColorPickers]);

  // Загружаем бренды для выбора (если не передан brandId) или для отображения названия
  const { data: brandsData } = useQuery({
    queryKey: ['brands', 'for-filament'],
    queryFn: () => brandsAPI.list({ active_only: true, page: 1, size: 100 }),
    enabled: isOpen,
  });

  // Custom material features are available to administrators and verified brands.
  const canUseCustomFeatures = user?.role === 'admin' || Boolean(
    brandsData?.items.find((b: Brand) => b.id === brandIdValue)?.verified,
  );

  // Линейки бренда (для группировки вариантов-цвета).
  const { data: linesData } = useQuery({
    queryKey: ['filament-lines', brandIdValue],
    queryFn: () => filamentLinesAPI.list(brandIdValue!),
    enabled: isOpen && !!brandIdValue,
  });

  const createLineMutation = useMutation({
    mutationFn: (name: string) => filamentLinesAPI.create(brandIdValue!, name),
    onSuccess: (line) => {
      queryClient.invalidateQueries({ queryKey: ['filament-lines', brandIdValue] });
      setLineId(line.id);
      setNewLineName('');
    },
  });
  const resolvedVisualEffects = mergeVisualEffects(visualEffects, additives);
  // Old clients still read one primary effect from ``filler``.
  const effectiveFiller = resolvedVisualEffects[0] || 'none';
  const hasVisualSettings = showAdvancedVisual
    || resolvedVisualEffects.length > 0
    || visualColorType !== 'single'
    || visualFinish !== 'matte'
    || visualTransparency;
  const currentVisualSettings: FilamentVisualSettings | undefined = hasVisualSettings
    ? {
        color_type: visualColorType,
        colors: visualColors,
        finish: visualFinish,
        filler: effectiveFiller,
        effects: resolvedVisualEffects,
        transparency: visualTransparency,
      }
    : undefined;

  // Загружаем уникальные типы материалов из БД
  const { data: materialTypes = [] } = useQuery({
    queryKey: ['filaments', 'material-types'],
    queryFn: () => filamentsAPI.getMaterialTypes(),
    enabled: isOpen,
  });

  // Базовые типы вперёд, подробные варианты — следом (ничего не удаляя)
  const sortedMaterialTypes = useMemo(() => sortMaterialTypes(materialTypes), [materialTypes]);

  // Инициализация формы при редактировании
  useEffect(() => {
    if (!isOpen) return; // Не выполняем инициализацию, если модалка закрыта
    
    if (filament) {
      setBrandIdValue(filament.brand_id);
      setName(filament.name);
      // Проверяем, есть ли тип материала в списке из БД
      const isInList = materialTypes.includes(filament.material_type);
      if (isInList) {
        setMaterialType(filament.material_type);
        setCustomMaterialType('');
      } else {
        setMaterialType('Other');
        setCustomMaterialType(filament.material_type);
      }
      setColorName(filament.color_name || '');
      setColorHex(filament.color_hex || '#FFFFFF');
      setRalCode(filament.ral_code || '');
      const nextAdditives = filament.additives || [];
      // Инициализация расширенных визуальных эффектов
      if (filament.visual_settings) {
        const vs = filament.visual_settings;
        const storedEffects = vs.effects?.length
          ? vs.effects
          : (vs.filler && vs.filler !== 'none' ? [vs.filler] : []);
        const derivedEffectSet = new Set(deriveVisualEffectsFromAdditives(nextAdditives));
        setVisualColorType(vs.color_type || 'single');
        setVisualColors(vs.colors || [filament.color_hex || '#FFFFFF']);
        setVisualFinish(vs.finish || 'matte');
        setVisualEffects(storedEffects.filter(effect => !derivedEffectSet.has(effect)));
        setVisualTransparency(vs.transparency ?? false);
        setShowAdvancedVisual(true);
      } else {
        setVisualColorType('single');
        setVisualColors([filament.color_hex || '#FFFFFF']);
        setVisualFinish('matte');
        setVisualEffects([]);
        setVisualTransparency(false);
        setShowAdvancedVisual(false);
      }
      setAdditives(nextAdditives);
      setPropertyClaims(filament.property_claims || []);
      setOpenColorPickers([]);
      setDiameter(filament.diameter || 1.75);
      setDensity(filament.density || 1.24);
      const initialPricePerKg = filament.price_per_kg || 0;
      const initialSpoolWeight = filament.spool_weight || 1000;
      setPricePerKg(initialPricePerKg);
      setSpoolWeight(initialSpoolWeight);
      setEmptySpoolWeight(filament.empty_spool_weight_g ?? null);
      setRecTemps({
        nozzleMin: filament.recommended_nozzle_temp_min ?? null,
        nozzleMax: filament.recommended_nozzle_temp_max ?? null,
        bedMin: filament.recommended_bed_temp_min ?? null,
        bedMax: filament.recommended_bed_temp_max ?? null,
      });
      setNozzleHrc(filament.required_nozzle_hrc ?? null);
      // Вычисляем цену за катушку из цены за кг
      setPricePerSpool(initialPricePerKg > 0 && initialSpoolWeight > 0 ? (initialPricePerKg * initialSpoolWeight) / 1000 : 0);
      setPriceMode(filament.price_display_unit === 'per_spool' ? 'per_spool' : 'per_kg');
      setDescription(filament.description || '');
      setAvailability(filament.availability || 'available');
      setLineId(filament.line_id ?? '');
    } else {
      // Сброс формы при создании нового
      // Если пользователь является сотрудником бренда, автоматически устанавливаем его brand_id
      const newBrandId = brandId || user?.brand_id || null;
      // Устанавливаем только если значение изменилось, чтобы избежать бесконечного цикла
      setBrandIdValue((prev) => prev !== newBrandId ? newBrandId : prev);
      setName('');
      setMaterialType('');
      setCustomMaterialType('');
      setColorName('');
      setColorHex('#808080');
      setRalCode('');
      // Сброс расширенных визуальных эффектов
      setVisualColorType('single');
      setVisualColors(['#808080']);
      setVisualFinish('matte');
      setVisualEffects([]);
      setAdditives([]);
      setPropertyClaims([]);
      setVisualTransparency(false);
      setShowAdvancedVisual(false);
      setOpenColorPickers([]);
      setDiameter(1.75);
      setDensity(1.24);
      setPricePerKg(0);
      setPricePerSpool(0);
      setSpoolWeight(1000);
      setEmptySpoolWeight(null);
      setRecTemps(EMPTY_RECOMMENDED_TEMPS);
      setPriceMode('per_kg');
      setDescription('');
      setAvailability('available');
      setLineId('');
      setNewLineName('');
    }
    setError(null);
    setSuccessMessage(null);
    setCreatedFilament(null); // Сбрасываем QR-код при закрытии
  }, [filament?.id, brandId, isOpen, user?.brand_id]); // Убрал materialTypes и filament целиком, используем только filament.id

  // Автоопределение плотности по типу материала (только при создании нового)
  useEffect(() => {
    if (filament) return; // При редактировании не трогаем
    const mt = materialType === 'Other' ? customMaterialType.trim() : materialType;
    const d = MATERIAL_DENSITY[mt] ?? MATERIAL_DENSITY[mt.toUpperCase()];
    if (d) setDensity(d);
  }, [materialType, customMaterialType, filament]);

  // Автоматический пересчет при изменении цены за кг (режим "за кг") или веса катушки
  useEffect(() => {
    if (priceMode === 'per_kg' && spoolWeight > 0 && pricePerKg > 0) {
      const calculatedPricePerSpool = (pricePerKg * spoolWeight) / 1000;
      // Обновляем только если значение изменилось (с небольшой погрешностью)
      if (Math.abs(calculatedPricePerSpool - pricePerSpool) > 0.01) {
        setPricePerSpool(calculatedPricePerSpool);
      }
    } else if (priceMode === 'per_kg' && pricePerKg === 0 && pricePerSpool !== 0) {
      setPricePerSpool(0);
    }
  }, [priceMode, pricePerKg, spoolWeight]);

  // Автоматический пересчет при изменении цены за катушку (режим "за катушку") или веса катушки
  useEffect(() => {
    if (priceMode === 'per_spool' && spoolWeight > 0 && pricePerSpool > 0) {
      const calculatedPricePerKg = (pricePerSpool / spoolWeight) * 1000;
      // Обновляем только если значение изменилось (с небольшой погрешностью)
      if (Math.abs(calculatedPricePerKg - pricePerKg) > 0.01) {
        setPricePerKg(calculatedPricePerKg);
      }
    } else if (priceMode === 'per_spool' && pricePerSpool === 0 && pricePerKg !== 0) {
      setPricePerKg(0);
    }
  }, [priceMode, pricePerSpool, spoolWeight]);

  // Мутация для создания материала
  const createMutation = useMutation({
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
      price_per_kg?: number;
      spool_weight?: number;
      empty_spool_weight_g?: number;
      recommended_nozzle_temp_min?: number;
      recommended_nozzle_temp_max?: number;
      recommended_bed_temp_min?: number;
      recommended_bed_temp_max?: number;
      required_nozzle_hrc?: number;
      description?: string;
      availability?: FilamentAvailability;
      price_display_unit?: 'per_kg' | 'per_spool';
      line_id?: number | null;
    }) => filamentsAPI.create(data),
    onSuccess: (data: Filament) => {
      queryClient.invalidateQueries({ queryKey: ['filaments'] });
      queryClient.invalidateQueries({ queryKey: ['filaments', 'material-types'] });
      queryClient.invalidateQueries({ queryKey: ['brands'] });
      queryClient.invalidateQueries({ queryKey: ['brand-filaments'] });
      setSuccessMessage(t('createFilament.createSuccess'));
      
      // Если есть QR-код И создание НЕ из профиля бренда - показываем его
      // Для брендов QR-код показывается через отдельную кнопку в списке материалов
      if (data.qr_code && !brandId) {
        setCreatedFilament(data);
      }
      
      setTimeout(() => {
        if (!data.qr_code || brandId) {
          onClose();
        }
        setSuccessMessage(null);
      }, 1500);
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      setError(translateApiError(t, err.response?.data?.detail, t('createFilament.createError')));
    },
  });

  // Мутация для обновления материала
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { 
      id: number; 
      data: Partial<{
        name?: string;
        material_type?: string;
        color_name?: string;
        color_hex?: string;
        ral_code?: string | null;
        visual_settings?: FilamentVisualSettings | null;
        additives?: FilamentAdditive[];
        property_claims?: FilamentPropertyClaim[];
        diameter?: number;
        density?: number;
        price_per_kg?: number;
        spool_weight?: number;
        empty_spool_weight_g?: number;
        recommended_nozzle_temp_min?: number;
        recommended_nozzle_temp_max?: number;
        recommended_bed_temp_min?: number;
        recommended_bed_temp_max?: number;
        required_nozzle_hrc?: number;
        description?: string;
        active?: boolean;
        availability?: FilamentAvailability;
        price_display_unit?: 'per_kg' | 'per_spool';
        line_id?: number | null;
      }>
    }) => filamentsAPI.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['filaments'] });
      queryClient.invalidateQueries({ queryKey: ['filaments', 'material-types'] });
      queryClient.invalidateQueries({ queryKey: ['brands'] });
      queryClient.invalidateQueries({ queryKey: ['brand-filaments'] });
      setSuccessMessage(t('createFilament.updateSuccess'));
      setTimeout(() => {
        onClose();
        setSuccessMessage(null);
      }, 1500);
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      setError(translateApiError(t, err.response?.data?.detail, t('createFilament.updateError')));
    },
  });

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!brandIdValue) {
      setError(t('createFilament.selectBrandError'));
      return;
    }

    // price_per_kg is stored canonically; when the brand priced per spool we
    // derive it here. price_display_unit keeps the brand's chosen unit so the
    // card shows that price as primary and the other unit as a hint.
    const priceKg =
      priceMode === 'per_spool'
        ? pricePerSpool > 0 && spoolWeight > 0
          ? (pricePerSpool * 1000) / spoolWeight
          : 0
        : pricePerKg;

    if (filament) {
      // Обновление существующего материала
      const finalMaterialType = materialType === 'Other' ? customMaterialType.trim() : materialType;
      if (!finalMaterialType) {
        setError(t('createFilament.enterMaterialTypeError'));
        return;
      }
      // Формируем visual_settings если есть расширенные эффекты
      const visualSettings: FilamentVisualSettings | undefined = showAdvancedVisual || resolvedVisualEffects.length > 0 || visualColorType !== 'single' || visualFinish !== 'matte' || visualTransparency
        ? {
            color_type: visualColorType,
            colors: visualColors,
            finish: visualFinish,
            filler: effectiveFiller,
            effects: resolvedVisualEffects,
            transparency: visualTransparency,
          }
        : undefined;
      
      updateMutation.mutate({
        id: filament.id,
        data: {
          name,
          material_type: finalMaterialType,
          color_name: colorName || undefined,
          color_hex: colorHex || undefined,
          ral_code: ralCode || null,
          visual_settings: visualSettings,
          additives,
          property_claims: propertyClaims,
          diameter,
          density,
          price_per_kg: priceKg || undefined,
          spool_weight: spoolWeight || undefined,
          empty_spool_weight_g: emptySpoolWeight ?? undefined,
          recommended_nozzle_temp_min: recTemps.nozzleMin ?? undefined,
          recommended_nozzle_temp_max: recTemps.nozzleMax ?? undefined,
          recommended_bed_temp_min: recTemps.bedMin ?? undefined,
          recommended_bed_temp_max: recTemps.bedMax ?? undefined,
          required_nozzle_hrc: nozzleHrc ?? undefined,
          description: description || undefined,
          availability,
          price_display_unit: priceMode,
          line_id: lineId === '' ? null : lineId,
        },
      });
    } else {
      // Создание нового материала
      const finalMaterialType = materialType === 'Other' ? customMaterialType.trim() : materialType;
      if (!finalMaterialType) {
        setError(t('createFilament.enterMaterialTypeError'));
        return;
      }
      // Формируем visual_settings если есть расширенные эффекты
      const visualSettings: FilamentVisualSettings | undefined = showAdvancedVisual || resolvedVisualEffects.length > 0 || visualColorType !== 'single' || visualFinish !== 'matte' || visualTransparency
        ? {
            color_type: visualColorType,
            colors: visualColors,
            finish: visualFinish,
            filler: effectiveFiller,
            effects: resolvedVisualEffects,
            transparency: visualTransparency,
          }
        : undefined;
      
      createMutation.mutate({
        brand_id: brandIdValue,
        name,
        material_type: finalMaterialType,
        color_name: colorName || undefined,
        color_hex: colorHex || undefined,
        ral_code: ralCode || undefined,
        visual_settings: visualSettings,
        additives,
        property_claims: propertyClaims,
        diameter,
        density,
        price_per_kg: priceKg || undefined,
        spool_weight: spoolWeight || undefined,
        empty_spool_weight_g: emptySpoolWeight ?? undefined,
        recommended_nozzle_temp_min: recTemps.nozzleMin ?? undefined,
        recommended_nozzle_temp_max: recTemps.nozzleMax ?? undefined,
        recommended_bed_temp_min: recTemps.bedMin ?? undefined,
        recommended_bed_temp_max: recTemps.bedMax ?? undefined,
        required_nozzle_hrc: nozzleHrc ?? undefined,
        description: description || undefined,
        availability,
        price_display_unit: priceMode,
        line_id: lineId === '' ? null : lineId,
      });
    }
  };

  const isLoading =
    createMutation.isPending || updateMutation.isPending || saveCountryCell.isPending;

  const myCell = (countryCell.data ?? []).find((cell) => cell.country === scopeCountry);
  // Общий слой правит тот, чей это вклад. Чужой показывается, но не редактируется.
  const ownsRecord =
    !filament ||
    !scopeCountry ||
    filament.contributed_by_organization_id === user?.active_organization_id;
  const filamentCurrency = scopeCountry
    ? myCell?.currency || defaultCurrencyForCountry(scopeCountry)
    : filament?.currency ??
      brandsData?.items.find((b: Brand) => b.id === brandIdValue)?.currency;
  const priceCurrencySymbol = currencySymbol(filamentCurrency);

  if (!isOpen) return null;

  return (
    <>
    <FeedbackModal
      isOpen={typoOpen}
      onClose={() => setTypoOpen(false)}
      initialType="other"
      initialSubject={t('createFilament.typoSubject', { name: filament?.name ?? '' })}
    />
    <ModalOverlay onClose={requestClose} closeOnOverlayClick={false}>
      <div
        className="bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 rounded-2xl w-full max-w-5xl max-h-[90vh] overflow-hidden flex flex-col border border-white/20 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        onMouseDown={(e) => e.stopPropagation()}
        onChangeCapture={() => setFormDirty(true)}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-white/10">
          <div className="flex min-w-0 flex-wrap items-center gap-3">
            <h2 className="text-2xl font-bold text-white">
              {filament ? t('createFilament.editTitle') : t('createFilament.createTitle')}
            </h2>
            {scopeCountry && (
              <span className="rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-xs text-emerald-300">
                {countryName(scopeCountry, i18n.language)}
              </span>
            )}
          </div>
          <button
            onClick={requestClose}
            className="p-2 hover:bg-white/10 rounded-lg transition-all text-gray-300 hover:text-white"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Success Message */}
          {successMessage && (
            <div className="mb-4 p-3 bg-green-500/20 border border-green-500/30 rounded-lg text-green-300 text-sm flex items-center space-x-2">
              <Check className="w-4 h-4" />
              <span>{successMessage}</span>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="mb-4 p-3 bg-red-500/20 border border-red-500/30 rounded-lg text-red-300 text-sm">
              {error}
            </div>
          )}

          {/* Form or QR Code */}
          {createdFilament && createdFilament.qr_code ? (
            // QR Code Success Section
            <div className="p-6 bg-gradient-to-br from-green-500/20 to-emerald-500/20 border border-green-500/30 rounded-xl">
              <div className="flex items-center space-x-2 mb-4">
                <QrCode className="w-6 h-6 text-green-400" />
                <h3 className="text-xl font-bold text-white">{t('createFilament.qrCodeCreated')}</h3>
              </div>
              
              <div className="flex flex-col items-center space-y-4">
                {/* QR Code */}
                <div className="p-4 bg-white rounded-xl">
                  <img
                    src={qrAPI.getQRCodeURL(createdFilament.id, 256)}
                    alt={`QR Code ${createdFilament.qr_code}`}
                    className="w-64 h-64"
                  />
                </div>
                
                {/* QR Code Info */}
                <div className="text-center">
                  <p className="text-gray-300 text-sm mb-2">{t('createFilament.code')}:</p>
                  <p className="text-white font-mono text-lg font-bold">{createdFilament.qr_code}</p>
                </div>
                
                {/* Download Buttons */}
                <div className="flex flex-wrap gap-3 justify-center">
                  <button
                    onClick={() => qrAPI.downloadQRCode(createdFilament.id, 300)}
                    className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-all flex items-center space-x-2"
                  >
                    <Download className="w-4 h-4" />
                    <span>300x300</span>
                  </button>
                  <button
                    onClick={() => qrAPI.downloadQRCode(createdFilament.id, 600)}
                    className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-all flex items-center space-x-2"
                  >
                    <Download className="w-4 h-4" />
                    <span>600x600</span>
                  </button>
                  <button
                    onClick={() => qrAPI.downloadQRCode(createdFilament.id, 1200)}
                    className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-all flex items-center space-x-2"
                  >
                    <Download className="w-4 h-4" />
                    <span>1200x1200</span>
                  </button>
                </div>
                
                {/* Close Button */}
                <button
                  onClick={() => {
                    setCreatedFilament(null);
                    onClose();
                  }}
                  className="px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-xl transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40"
                >
                  {t('createFilament.close')}
                </button>
              </div>
            </div>
          ) : (
            <>
              {!filament && brandIdValue && (
                <div className="flex gap-2 mb-5">
                  <button
                    type="button"
                    onClick={() => setFormMode('single')}
                    className={`flex-1 px-4 py-2 rounded-xl text-sm font-medium transition-all ${formMode === 'single' ? 'bg-purple-600 text-white' : 'bg-white/10 text-gray-300 hover:bg-white/20'}`}
                  >
                    {t('createFilament.modeSingle')}
                  </button>
                  <button
                    type="button"
                    onClick={() => setFormMode('palette')}
                    className={`flex-1 px-4 py-2 rounded-xl text-sm font-medium transition-all ${formMode === 'palette' ? 'bg-purple-600 text-white' : 'bg-white/10 text-gray-300 hover:bg-white/20'}`}
                  >
                    {t('createFilament.modePalette')}
                  </button>
                </div>
              )}
              {formMode === 'palette' && !filament && brandIdValue ? (
                <FilamentPaletteForm
                  brandId={brandIdValue}
                  onClose={onClose}
                  priceCurrencySymbol={priceCurrencySymbol}
                  allowCustomFeatures={canUseCustomFeatures}
                />
              ) : (
            // Form
            <form onSubmit={handleSubmit} className="space-y-6">
          {scopeCountry && !ownsRecord && (
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-3">
              <p className="text-xs leading-5 text-gray-400">
                {t('createFilament.commonOwnedByOther')}
              </p>
              <button
                type="button"
                onClick={() => setTypoOpen(true)}
                className="whitespace-nowrap rounded-lg border border-white/15 bg-white/5 px-3 py-1.5 text-sm text-cyan-300 transition hover:bg-white/10"
              >
                {t('createFilament.reportTypo')}
              </button>
            </div>
          )}
          <fieldset disabled={Boolean(scopeCountry && !ownsRecord)} className="space-y-6 disabled:opacity-60">
          {/* Name and Material Type in one row */}
          <div className="flex items-end gap-4">
            <div className="flex-1">
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('createFilament.nameLabel')} *</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                placeholder={t('createFilament.namePlaceholder')}
              />
            </div>
            <div className="flex-1">
              <MaterialTypeSelect
                label={`${t('createFilament.materialTypeLabel')} *`}
                value={materialType === 'Other' ? customMaterialType : materialType}
                onChange={(v) => {
                  const allTypes = sortedMaterialTypes.length > 0 ? sortedMaterialTypes : FALLBACK_TYPES;
                  if (allTypes.includes(v)) {
                    setMaterialType(v);
                    setCustomMaterialType('');
                  } else {
                    setMaterialType('Other');
                    setCustomMaterialType(v);
                  }
                }}
                options={sortedMaterialTypes}
                required
              />
            </div>
            {/* Brand Selection (только при создании без brandId и если пользователь не сотрудник бренда) */}
            {!filament && !brandId && !user?.brand_id && (
              <div className="flex-[2]">
                <Dropdown
                  label={`${t('createFilament.brandLabel')} *`}
                  value={brandIdValue || ''}
                  options={[
                    { value: '', label: t('createFilament.selectBrand') },
                    ...(brandsData?.items.map((brand: Brand) => ({
                      value: brand.id,
                      label: brand.name,
                    })) || []),
                  ]}
                  onChange={(val) => setBrandIdValue(val === '' ? null : Number(val))}
                  placeholder={t('createFilament.selectBrand')}
                />
              </div>
            )}
          </div>

          {/* Линейка (группировка вариантов-цвета) */}
          {brandIdValue && (
            <div>
              <label className="block text-gray-300 mb-1 text-sm font-medium">{t('createFilament.lineLabel')}</label>
              <p className="text-gray-500 text-xs mb-2">{t('createFilament.lineHint')}</p>
              <div className="flex gap-2">
                <div className="flex-1">
                  <Dropdown
                    value={lineId === '' ? '' : String(lineId)}
                    onChange={(val) => setLineId(val === '' ? '' : Number(val))}
                    options={[
                      { value: '', label: t('createFilament.lineNone') },
                      ...((linesData ?? []).map((l) => ({ value: String(l.id), label: l.name }))),
                    ]}
                    placeholder={t('createFilament.lineNone')}
                  />
                </div>
                <input
                  type="text"
                  value={newLineName}
                  onChange={(e) => setNewLineName(e.target.value)}
                  placeholder={t('createFilament.lineNewPlaceholder')}
                  maxLength={200}
                  className="flex-1 px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white text-sm placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                />
                <button
                  type="button"
                  disabled={!newLineName.trim() || createLineMutation.isPending}
                  onClick={() => createLineMutation.mutate(newLineName.trim())}
                  className="px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-gray-300 hover:text-white hover:bg-white/20 transition-all text-sm whitespace-nowrap disabled:opacity-50"
                >
                  {t('createFilament.lineCreate')}
                </button>
              </div>
            </div>
          )}

          {/* Color Section - в одну линию как в CreatePresetModal */}
          <ColorMaterialSection
            mode="edit"
            colorName={colorName}
            onColorNameChange={setColorName}
            colorHex={colorHex}
            onColorHexChange={setColorHex}
            ralCode={ralCode}
            onRalCodeChange={setRalCode}
            visualSettings={currentVisualSettings}
            previewSize="medium"
            rightButton={
              <button
                type="button"
                onClick={() => setShowAdvancedVisual(!showAdvancedVisual)}
                className="h-12 px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-gray-300 hover:text-white hover:bg-white/20 transition-all flex items-center gap-2"
                title={t('createFilament.advancedColorSettings')}
              >
                <span className="text-sm font-medium">{t('createFilament.advancedColorSettings')}</span>
                <span className="text-xs">{showAdvancedVisual ? '▼' : '▶'}</span>
              </button>
            }
          />

          {/* Расширенные характеристики цвета (collapsible) */}
          {showAdvancedVisual && (
            <div className="mt-4 overflow-visible rounded-2xl border border-white/10 bg-white/[0.035] p-3">
              <div className="grid items-start gap-3 lg:grid-cols-[minmax(18rem,1.15fr)_minmax(0,2fr)]">
                <aside className="space-y-3 md:sticky md:top-0">
                {/* Тип цвета */}
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-300">{t('createFilament.colorTypeLabel')}</label>
                  <div className="grid grid-cols-2 gap-2">
                    {(['single', 'two', 'three', 'gradient', 'transition', 'thermochromic'] as const).map((type) => (
                      <button
                        key={type}
                        type="button"
                        onClick={() => {
                          setVisualColorType(type);
                          const requiredColors = type === 'single' ? 1 : type === 'two' ? 2 : type === 'three' ? 3 : type === 'transition' || type === 'thermochromic' ? 2 : 5;
                          setVisualColors((prevColors) => {
                            const base = colorHex || prevColors[0] || '#FFFFFF';
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
                          // Сбрасываем состояние открытых пикеров при смене типа
                          setOpenColorPickers([]);
                        }}
                        className={`rounded-lg border px-3 py-1.5 text-sm transition-all ${
                          visualColorType === type
                            ? 'bg-purple-600 border-purple-400 text-white'
                            : 'bg-white/10 border-white/20 text-gray-300 hover:bg-white/20'
                        }`}
                      >
                        {type === 'single' ? t('createFilament.colorType.single') :
                         type === 'two' ? t('createFilament.colorType.two') :
                         type === 'three' ? t('createFilament.colorType.three') :
                         type === 'gradient' ? t('createFilament.colorType.gradient') :
                         type === 'transition' ? (
                          <span title={t('createFilament.colorType.transitionHint')}>
                            {t('createFilament.colorType.transition')}
                          </span>
                        ) :
                         type === 'thermochromic' ? (
                          <span title={t('createFilament.colorType.thermochromicHint')}>
                            {t('createFilament.colorType.thermochromic')}
                          </span>
                        ) : null}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Цвета (до 5) */}
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-gray-300">
                    {t('createFilament.colors')} ({visualColorType === 'single' ? 1 : visualColorType === 'two' ? 2 : visualColorType === 'three' ? 3 : visualColorType === 'transition' || visualColorType === 'thermochromic' ? 2 : 5})
                  </label>
                  <div className="grid grid-cols-5 gap-2">
                    {Array.from({ length: visualColorType === 'single' ? 1 : visualColorType === 'two' ? 2 : visualColorType === 'three' ? 3 : visualColorType === 'transition' || visualColorType === 'thermochromic' ? 2 : 5 }).map((_, idx) => {
                      const currentColor = visualColors[idx] || '#FF0000';
                      const isPickerOpen = openColorPickers[idx] || false;
                      
                      return (
                          <div key={idx} className="flex flex-col gap-1.5">
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
                              className="relative h-10 w-full cursor-pointer overflow-visible rounded-lg border border-white/20 transition-opacity hover:opacity-80"
                              style={{ backgroundColor: currentColor }}
                              title={t('createFilament.clickToPickColor')}
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
                                const newColors = [...visualColors];
                                newColors[idx] = hex;
                                setVisualColors(newColors);
                                // Синхронизируем основной цвет, если меняем первый цвет в расширенных настройках
                                if (idx === 0) {
                                  isInternalColorChangeRef.current = true; // Помечаем как внутреннее изменение
                                  setColorHex(hex);
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
                              const newColors = [...visualColors];
                              newColors[idx] = hex;
                              setVisualColors(newColors);
                              if (idx === 0) {
                                isInternalColorChangeRef.current = true;
                                setColorHex(hex);
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
                  <label className="mb-1.5 block text-sm font-medium text-gray-300">{t('createFilament.surfaceTypeLabel')}</label>
                  <div className="inline-grid grid-cols-2 gap-1 rounded-xl border border-white/10 bg-black/15 p-1">
                    {(['matte', 'glossy'] as const).map((finish) => (
                      <button
                        key={finish}
                        type="button"
                        onClick={() => setVisualFinish(finish)}
                        className={`min-w-24 rounded-lg border px-3 py-1.5 text-sm transition-all ${
                          visualFinish === finish
                            ? 'bg-purple-600 border-purple-400 text-white'
                            : 'bg-white/10 border-white/20 text-gray-300 hover:bg-white/20'
                        }`}
                      >
                        {finish === 'matte' ? t('createFilament.surface.matte') : t('createFilament.surface.glossy')}
                      </button>
                    ))}
                  </div>
                </div>
                </aside>

                <section className="min-w-0 space-y-3">
                  <label className="flex cursor-pointer items-center justify-between gap-4 rounded-xl border border-white/10 bg-black/10 px-3 py-2 text-sm font-medium text-gray-200 transition-colors hover:bg-white/[0.06]">
                    <span>{t('createFilament.transparentMaterial')}</span>
                    <input
                      type="checkbox"
                      checked={visualTransparency}
                      onChange={(e) => setVisualTransparency(e.target.checked)}
                      className="peer sr-only"
                    />
                    <span className="relative h-6 w-11 shrink-0 rounded-full border border-white/15 bg-white/10 transition-colors after:absolute after:left-0.5 after:top-0.5 after:h-[18px] after:w-[18px] after:rounded-full after:bg-gray-300 after:shadow-sm after:transition-transform peer-checked:border-cyan-300/40 peer-checked:bg-cyan-400/25 peer-checked:after:translate-x-5 peer-checked:after:bg-cyan-100 peer-focus-visible:ring-2 peer-focus-visible:ring-cyan-300/60" />
                  </label>

                  <FilamentFeaturesEditor
                    effects={visualEffects}
                    onEffectsChange={setVisualEffects}
                    additives={additives}
                    onAdditivesChange={setAdditives}
                    propertyClaims={propertyClaims}
                    onPropertyClaimsChange={setPropertyClaims}
                    allowCustom={canUseCustomFeatures}
                    compact
                  />
                </section>
              </div>
            </div>
          )}

          {/* Diameter and Density */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Dropdown
              label={<>{t('createFilament.diameterLabel')} * <InfoHint text={t('paramHints.diameter')} /></>}
              value={diameter}
              options={[
                { value: 1.75, label: '1.75 mm' },
                { value: 2.85, label: '2.85 mm' },
                { value: 3.0, label: '3.0 mm' },
              ]}
              onChange={(val) => setDiameter(Number(val))}
              placeholder={t('createFilament.selectDiameter')}
            />
            <DensityField value={density} onChange={setDensity} />
          </div>

          {/* Цена относится к рынку: у страновой организации она уходит в её
              ячейку, у глобальной — в общий слой. Поле одно и то же. */}
          <PriceUnitField
            priceMode={priceMode}
            onPriceModeChange={setPriceMode}
            pricePerKg={pricePerKg}
            onPricePerKgChange={setPricePerKg}
            pricePerSpool={pricePerSpool}
            onPricePerSpoolChange={setPricePerSpool}
            spoolWeight={spoolWeight}
            onSpoolWeightChange={setSpoolWeight}
            emptySpoolWeight={emptySpoolWeight}
            onEmptySpoolWeightChange={setEmptySpoolWeight}
            currencySymbol={priceCurrencySymbol}
          />

          <RecommendedTempsField value={recTemps} onChange={setRecTemps} />

          <NozzleHardnessField
            value={nozzleHrc}
            onChange={setNozzleHrc}
            filler={effectiveFiller}
            effects={resolvedVisualEffects}
            additives={additives}
            materialType={materialType === 'custom' ? customMaterialType : materialType}
          />

          <AvailabilitySelect
            value={availability}
            onChange={setAvailability}
            includeDiscontinued={!!filament}
          />

          {/* Description */}
          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">{t('createFilament.descriptionLabel')}</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all resize-none"
              placeholder={t('createFilament.descriptionPlaceholder')}
            />
          </div>
          </fieldset>

          {/* Actions */}
          <div className="flex justify-end space-x-3 pt-4 border-t border-white/10">
            <button
              type="button"
              onClick={requestClose}
              disabled={isLoading}
              className="px-6 py-3 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all disabled:opacity-50"
            >
              {t('createFilament.cancel')}
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-xl transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 disabled:opacity-50 flex items-center space-x-2"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>{t('createFilament.saving')}</span>
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  <span>{filament ? t('createFilament.save') : t('createFilament.create')}</span>
                </>
              )}
            </button>
          </div>
        </form>
              )}
            </>
          )}
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
    </>
  );
};



