/** Модальное окно для создания/редактирования материала */

import { useState, useEffect, FormEvent, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Save, Loader2, Check, Download, QrCode } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { filamentsAPI, brandsAPI, qrAPI } from '../api/client';
import { ColorMaterialSection } from './ColorMaterialSection';
import { HSLColorPicker } from './HSLColorPicker';
import type { FilamentVisualSettings } from '../types/api';
import { Dropdown } from './Dropdown';
import type { Filament, Brand } from '../types/api';
import { useAuth } from '../contexts/AuthContext';
import { useClickOutside } from '../hooks/useClickOutside';
import { useHeaderVisible } from '../hooks/useHeaderVisible';

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
  const { t } = useTranslation();
  const [brandIdValue, setBrandIdValue] = useState<number | null>(brandId || null);
  const [name, setName] = useState('');
  const [materialType, setMaterialType] = useState('PLA');
  const [customMaterialType, setCustomMaterialType] = useState('');
  const [showMaterialTypeDropdown, setShowMaterialTypeDropdown] = useState(false);
  const materialTypeDropdownRef = useRef<HTMLDivElement>(null);
  const [colorName, setColorName] = useState('');
  const [colorHex, setColorHex] = useState('#FFFFFF');
  // Расширенные характеристики цвета
  const [visualColorType, setVisualColorType] = useState<'single' | 'two' | 'three' | 'gradient' | 'transition' | 'thermochromic'>('single');
  const [visualColors, setVisualColors] = useState<string[]>(['#FFFFFF']);
  const [visualFinish, setVisualFinish] = useState<'matte' | 'glossy'>('matte');
  const [visualFiller, setVisualFiller] = useState<'none' | 'wood' | 'carbon' | 'glitter' | 'metallic' | 'luminescent' | 'fibers' | 'stone' | 'glass' | 'pattern1' | 'pattern2' | 'pattern3' | 'pattern4' | 'pattern5' | 'pattern6' | 'pattern7' | 'pattern8' | 'pattern9' | 'pattern10' | 'pattern11' | 'pattern12'>('none');
  const [visualTransparency, setVisualTransparency] = useState(false);
  const [showAdvancedVisual, setShowAdvancedVisual] = useState(false); // Collapsible секция
  const [openColorPickers, setOpenColorPickers] = useState<boolean[]>([]);
  const [diameter, setDiameter] = useState(1.75);
  const [density, setDensity] = useState(1.24);
  const [priceMode, setPriceMode] = useState<'per_kg' | 'per_spool'>('per_kg');
  const [pricePerKg, setPricePerKg] = useState(0);
  const [pricePerSpool, setPricePerSpool] = useState(0);
  const [spoolWeight, setSpoolWeight] = useState(1000);
  const [description, setDescription] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [createdFilament, setCreatedFilament] = useState<Filament | null>(null); // Для отображения QR-кода после создания

  const queryClient = useQueryClient();
  const { user } = useAuth();

  // Закрываем выпадающий список типов материалов при клике вне его
  useClickOutside({
    ref: materialTypeDropdownRef,
    isOpen: showMaterialTypeDropdown,
    onClose: () => setShowMaterialTypeDropdown(false),
  });
  
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

  // Загружаем уникальные типы материалов из БД
  const { data: materialTypes = [] } = useQuery({
    queryKey: ['filaments', 'material-types'],
    queryFn: () => filamentsAPI.getMaterialTypes(),
    enabled: isOpen,
  });

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
      // Инициализация расширенных визуальных эффектов
      if ((filament as any).visual_settings) {
        const vs = (filament as any).visual_settings;
        setVisualColorType(vs.color_type || 'single');
        setVisualColors(vs.colors || [filament.color_hex || '#FFFFFF']);
        setVisualFinish(vs.finish || 'matte');
        setVisualFiller(vs.filler || 'none');
        setVisualTransparency(vs.transparency ?? false);
        setShowAdvancedVisual(true);
      } else {
        setVisualColorType('single');
        setVisualColors([filament.color_hex || '#FFFFFF']);
        setVisualFinish('matte');
        setVisualFiller('none');
      setVisualTransparency(false);
      setShowAdvancedVisual(false);
      }
      setOpenColorPickers([]);
      setDiameter(filament.diameter || 1.75);
      setDensity(filament.density || 1.24);
      const initialPricePerKg = filament.price_per_kg || 0;
      const initialSpoolWeight = filament.spool_weight || 1000;
      setPricePerKg(initialPricePerKg);
      setSpoolWeight(initialSpoolWeight);
      // Вычисляем цену за катушку из цены за кг
      setPricePerSpool(initialPricePerKg > 0 && initialSpoolWeight > 0 ? (initialPricePerKg * initialSpoolWeight) / 1000 : 0);
      setPriceMode('per_kg'); // По умолчанию показываем за кг
      setDescription(filament.description || '');
    } else {
      // Сброс формы при создании нового
      // Если пользователь является сотрудником бренда, автоматически устанавливаем его brand_id
      const newBrandId = brandId || user?.brand_id || null;
      // Устанавливаем только если значение изменилось, чтобы избежать бесконечного цикла
      setBrandIdValue((prev) => prev !== newBrandId ? newBrandId : prev);
      setName('');
      setMaterialType('PLA');
      setCustomMaterialType('');
      setColorName('');
      setColorHex('#FFFFFF');
      // Сброс расширенных визуальных эффектов
      setVisualColorType('single');
      setVisualColors(['#FFFFFF']);
      setVisualFinish('matte');
      setVisualFiller('none');
      setVisualTransparency(false);
      setShowAdvancedVisual(false);
      setOpenColorPickers([]);
      setShowMaterialTypeDropdown(false);
      setDiameter(1.75);
      setDensity(1.24);
      setPricePerKg(0);
      setPricePerSpool(0);
      setSpoolWeight(1000);
      setPriceMode('per_kg');
      setDescription('');
    }
    setError(null);
    setSuccessMessage(null);
    setCreatedFilament(null); // Сбрасываем QR-код при закрытии
  }, [filament?.id, brandId, isOpen, user?.brand_id]); // Убрал materialTypes и filament целиком, используем только filament.id

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
      visual_settings?: FilamentVisualSettings | null;
      diameter?: number;
      density?: number;
      price_per_kg?: number;
      spool_weight?: number;
      description?: string;
    }) => filamentsAPI.create(data),
    onSuccess: (data: Filament) => {
      queryClient.invalidateQueries({ queryKey: ['filaments'] });
      queryClient.invalidateQueries({ queryKey: ['filaments', 'material-types'] });
      queryClient.invalidateQueries({ queryKey: ['brands'] });
      queryClient.invalidateQueries({ queryKey: ['brand-filaments'] });
      setSuccessMessage('Материал успешно создан!');
      
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
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Ошибка при создании материала');
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
        visual_settings?: FilamentVisualSettings | null;
        diameter?: number;
        density?: number;
        price_per_kg?: number;
        spool_weight?: number;
        description?: string;
        active?: boolean;
      }>
    }) => filamentsAPI.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['filaments'] });
      queryClient.invalidateQueries({ queryKey: ['filaments', 'material-types'] });
      queryClient.invalidateQueries({ queryKey: ['brands'] });
      queryClient.invalidateQueries({ queryKey: ['brand-filaments'] });
      setSuccessMessage('Материал успешно обновлён!');
      setTimeout(() => {
        onClose();
        setSuccessMessage(null);
      }, 1500);
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Ошибка при обновлении материала');
    },
  });

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!brandIdValue) {
      setError('Выберите бренд');
      return;
    }

    if (filament) {
      // Обновление существующего материала
      const finalMaterialType = materialType === 'Other' ? customMaterialType.trim() : materialType;
      if (!finalMaterialType) {
        setError('Введите тип материала');
        return;
      }
      // Формируем visual_settings если есть расширенные эффекты
      const visualSettings: FilamentVisualSettings | undefined = showAdvancedVisual || visualFiller !== 'none' || visualColorType !== 'single' || visualFinish !== 'matte' || visualTransparency
        ? {
            color_type: visualColorType,
            colors: visualColors,
            finish: visualFinish,
            filler: visualFiller,
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
          visual_settings: visualSettings,
          diameter,
          density,
          price_per_kg: pricePerKg || undefined,
          spool_weight: spoolWeight || undefined,
          description: description || undefined,
        },
      });
    } else {
      // Создание нового материала
      const finalMaterialType = materialType === 'Other' ? customMaterialType.trim() : materialType;
      if (!finalMaterialType) {
        setError('Введите тип материала');
        return;
      }
      // Формируем visual_settings если есть расширенные эффекты
      const visualSettings: FilamentVisualSettings | undefined = showAdvancedVisual || visualFiller !== 'none' || visualColorType !== 'single' || visualFinish !== 'matte' || visualTransparency
        ? {
            color_type: visualColorType,
            colors: visualColors,
            finish: visualFinish,
            filler: visualFiller,
            transparency: visualTransparency,
          }
        : undefined;
      
      createMutation.mutate({
        brand_id: brandIdValue,
        name,
        material_type: finalMaterialType,
        color_name: colorName || undefined,
        color_hex: colorHex || undefined,
        visual_settings: visualSettings,
        diameter,
        density,
        price_per_kg: pricePerKg || undefined,
        spool_weight: spoolWeight || undefined,
        description: description || undefined,
      });
    }
  };

  // Хуки должны вызываться до условного возврата
  const isHeaderVisible = useHeaderVisible();
  const isLoading = createMutation.isPending || updateMutation.isPending;

  if (!isOpen) return null;

  return (
    <div className={`fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm ${isHeaderVisible ? 'pt-[88px]' : ''}`}>
      <div 
        className={`bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 rounded-2xl w-full max-w-5xl overflow-hidden flex flex-col border border-white/20 shadow-2xl ${isHeaderVisible ? 'max-h-[calc(100vh-60px)]' : 'max-h-[calc(100vh-10px)]'}`}
        onClick={(e) => e.stopPropagation()}
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-white/10">
          <h2 className="text-2xl font-bold text-white">
            {filament ? t('createFilament.editTitle') : t('createFilament.createTitle')}
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
                <h3 className="text-xl font-bold text-white">QR-код создан автоматически!</h3>
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
                  Закрыть
                </button>
              </div>
            </div>
          ) : (
            // Form
            <form onSubmit={handleSubmit} className="space-y-6">
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
              {/* Если brandId передан - используем input с выпадающим списком (как в CreatePresetModal) */}
              {brandId ? (
                <div className="relative" ref={materialTypeDropdownRef}>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{t('createFilament.materialTypeLabel')} *</label>
                  <div className="relative">
                    <input
                      type="text"
                      value={materialType === 'Other' ? customMaterialType : materialType}
                      onChange={(e) => {
                        const value = e.target.value;
                        setMaterialType(value);
                        // Показываем выпадающий список если начали вводить
                        if (value.length > 0) {
                          setShowMaterialTypeDropdown(true);
                        }
                        // Если значение не из списка - используем как кастомный тип
                        const allTypes = materialTypes.length > 0
                          ? materialTypes
                          : ['PLA', 'PETG', 'ABS', 'TPU', 'ASA', 'PC', 'PA', 'PVA'];
                        if (!allTypes.includes(value)) {
                          setMaterialType('Other');
                          setCustomMaterialType(value);
                        } else {
                          setCustomMaterialType('');
                        }
                      }}
                      onFocus={() => {
                        setShowMaterialTypeDropdown(true);
                      }}
                      placeholder={t('createFilament.selectOrEnterMaterial')}
                      required
                      className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                    />
                    {showMaterialTypeDropdown && (
                      <div 
                        className="absolute z-10 w-full mt-1 max-h-60 overflow-y-auto bg-white/5 backdrop-blur-sm rounded-xl border border-white/10 shadow-xl"
                        onClick={(e) => e.stopPropagation()}
                      >
                        {(() => {
                          // Фильтруем типы по введенному тексту
                          const allTypes = materialTypes.length > 0 
                            ? materialTypes
                            : ['PLA', 'PETG', 'ABS', 'TPU', 'ASA', 'PC', 'PA', 'PVA'];
                          const filteredTypes = allTypes.filter(type => 
                            type.toLowerCase().includes((materialType === 'Other' ? customMaterialType : materialType).toLowerCase())
                          );
                          
                          return filteredTypes.length > 0 ? (
                            filteredTypes.map((type) => (
                              <button
                                key={type}
                                type="button"
                                onClick={() => {
                                  setMaterialType(type);
                                  setCustomMaterialType('');
                                  setShowMaterialTypeDropdown(false);
                                }}
                                className="w-full px-4 py-3 text-left hover:bg-white/10 transition-all text-white border-b border-white/5 last:border-b-0"
                              >
                                {type}
                              </button>
                            ))
                          ) : (
                            <div className="px-4 py-3 text-gray-400 text-sm">
                              Типы не найдены. Введите новый тип материала вручную.
                            </div>
                          );
                        })()}
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <>
                  <Dropdown
                    label={`${t('createFilament.materialTypeLabel')} *`}
                    value={materialType}
                    options={[
                      ...(materialTypes.length > 0
                        ? materialTypes.map((type) => ({ value: type, label: type }))
                        : [
                            { value: 'PLA', label: 'PLA' },
                            { value: 'PETG', label: 'PETG' },
                            { value: 'ABS', label: 'ABS' },
                            { value: 'TPU', label: 'TPU' },
                            { value: 'ASA', label: 'ASA' },
                            { value: 'PC', label: 'PC' },
                            { value: 'PA', label: 'PA (Nylon)' },
                            { value: 'PVA', label: 'PVA' },
                          ]),
                      { value: 'Other', label: 'Другой...' },
                    ]}
                    onChange={(val) => {
                      const value = String(val);
                      setMaterialType(value);
                      if (value !== 'Other') {
                        setCustomMaterialType('');
                      }
                    }}
                    placeholder={t('createFilament.selectMaterial')}
                  />
                  {materialType === 'Other' && (
                    <input
                      type="text"
                      value={customMaterialType}
                      onChange={(e) => setCustomMaterialType(e.target.value)}
                      placeholder={t('createFilament.enterMaterialType')}
                      required={materialType === 'Other'}
                      className="mt-2 w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                    />
                  )}
                </>
              )}
            </div>
            {/* Brand Selection (только при создании без brandId и если пользователь не сотрудник бренда) */}
            {!filament && !brandId && !user?.brand_id && (
              <div className="flex-[2]">
                <Dropdown
                  label={`${t('createFilament.brandLabel')} *`}
                  value={brandIdValue || ''}
                  options={[
                    { value: '', label: 'Выберите бренд' },
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

          {/* Color Section - в одну линию как в CreatePresetModal */}
          <ColorMaterialSection
            mode="edit"
            colorName={colorName}
            onColorNameChange={setColorName}
            colorHex={colorHex}
            onColorHexChange={setColorHex}
            visualSettings={
              showAdvancedVisual || visualFiller !== 'none' || visualColorType !== 'single' || visualFinish !== 'matte' || visualTransparency
                ? {
                    color_type: visualColorType,
                    colors: visualColors,
                    finish: visualFinish,
                    filler: visualFiller,
                    transparency: visualTransparency,
                  }
                : undefined
            }
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
            <div className="border border-white/10 rounded-xl p-4 bg-white/5 mt-4">
              <div className="space-y-4">
                {/* Тип цвета */}
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{t('createFilament.colorTypeLabel')}</label>
                  <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
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
                        className={`px-4 py-2 rounded-lg border transition-all ${
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
                  <label className="block text-gray-300 mb-2 text-sm font-medium">
                    Цвета ({visualColorType === 'single' ? 1 : visualColorType === 'two' ? 2 : visualColorType === 'three' ? 3 : visualColorType === 'transition' || visualColorType === 'thermochromic' ? 2 : 5})
                  </label>
                  <div className="grid grid-cols-5 gap-2">
                    {Array.from({ length: visualColorType === 'single' ? 1 : visualColorType === 'two' ? 2 : visualColorType === 'three' ? 3 : visualColorType === 'transition' || visualColorType === 'thermochromic' ? 2 : 5 }).map((_, idx) => {
                      const currentColor = visualColors[idx] || '#FF0000';
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
                              className="w-full h-12 rounded-lg border border-white/20 cursor-pointer hover:opacity-80 transition-opacity relative overflow-visible"
                              style={{ backgroundColor: currentColor }}
                              title={t('createFilament.clickToPickColor')}
                            >
                              <div className="absolute inset-0 flex items-center justify-center text-white text-xs font-medium drop-shadow-lg">
                                {currentColor}
                              </div>
                            </button>
                            
                            {/* HSL Color Picker - появляется над кнопкой */}
                            {isPickerOpen && (
                              <div className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-[100]">
                                <HSLColorPicker
                                  color={currentColor}
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
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Финиш */}
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{t('createFilament.surfaceTypeLabel')}</label>
                  <div className="flex gap-2">
                    {(['matte', 'glossy'] as const).map((finish) => (
                      <button
                        key={finish}
                        type="button"
                        onClick={() => setVisualFinish(finish)}
                        className={`flex-1 px-4 py-2 rounded-lg border transition-all ${
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

                {/* Наполнитель */}
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{t('createFilament.fillerLabel')}</label>
                  <Dropdown
                    value={visualFiller}
                    onChange={(val) => setVisualFiller(val as typeof visualFiller)}
                    options={[
                      { value: 'none', label: t('createFilament.filler.none') },
                      { value: 'wood', label: t('createFilament.filler.wood') },
                      { value: 'carbon', label: t('createFilament.filler.carbon') },
                      { value: 'glass', label: t('createFilament.filler.glass') },
                      { value: 'metallic', label: t('createFilament.filler.metallic') },
                      { value: 'luminescent', label: t('createFilament.filler.luminescent') },
                      { value: 'glitter', label: t('createFilament.filler.glitter') },
                      { value: 'fibers', label: t('createFilament.filler.fibers') },
                      { value: 'stone', label: t('createFilament.filler.stone') },
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
                    placeholder={t('createFilament.selectFiller')}
                  />
                </div>

                {/* Прозрачность */}
                <div>
                  <label className="flex items-center space-x-2 text-gray-300 mb-2 text-sm font-medium">
                    <input
                      type="checkbox"
                      checked={visualTransparency}
                      onChange={(e) => setVisualTransparency(e.target.checked)}
                      className="w-4 h-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
                    />
                    <span>{t('createFilament.transparentMaterial')}</span>
                  </label>
                </div>
              </div>
            </div>
          )}

          {/* Diameter and Density */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Dropdown
              label={`${t('createFilament.diameterLabel')} *`}
              value={diameter}
              options={[
                { value: 1.75, label: '1.75 mm' },
                { value: 2.85, label: '2.85 mm' },
                { value: 3.0, label: '3.0 mm' },
              ]}
              onChange={(val) => setDiameter(Number(val))}
              placeholder={t('createFilament.selectDiameter')}
            />
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('createFilament.densityLabel')}</label>
              <input
                type="number"
                value={density}
                onChange={(e) => setDensity(Number(e.target.value))}
                min={0.5}
                max={2.0}
                step="0.01"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                placeholder="1.24"
              />
            </div>
          </div>

          {/* Price and Weight */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-gray-300 text-sm font-medium">
                  {priceMode === 'per_kg' ? 'Цена за кг (₽)' : 'Цена за катушку (₽)'}
                </label>
                {/* Price Mode Toggle */}
                <div className="flex items-center bg-white/10 rounded-lg p-1 border border-white/20">
                  <button
                    type="button"
                    onClick={() => setPriceMode('per_kg')}
                    className={`px-2 py-1 text-xs rounded transition-all ${
                      priceMode === 'per_kg'
                        ? 'bg-purple-600 text-white'
                        : 'text-gray-400 hover:text-white'
                    }`}
                    title={t('createFilament.pricePerKg')}
                  >
                    {t('createFilament.pricePerKg')}
                  </button>
                  <button
                    type="button"
                    onClick={() => setPriceMode('per_spool')}
                    className={`px-2 py-1 text-xs rounded transition-all ${
                      priceMode === 'per_spool'
                        ? 'bg-purple-600 text-white'
                        : 'text-gray-400 hover:text-white'
                    }`}
                    title={t('createFilament.pricePerSpool')}
                  >
                    {t('createFilament.pricePerSpool')}
                  </button>
                </div>
              </div>
              <input
                type="number"
                value={priceMode === 'per_kg' ? (pricePerKg || '') : (pricePerSpool || '')}
                onChange={(e) => {
                  const value = e.target.value === '' ? 0 : Number(e.target.value);
                  if (priceMode === 'per_kg') {
                    setPricePerKg(value);
                  } else {
                    setPricePerSpool(value);
                  }
                }}
                min={0}
                step="0.01"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                placeholder={priceMode === 'per_kg' ? "800" : "800"}
              />
              {/* Показываем пересчитанное значение */}
              {priceMode === 'per_kg' && pricePerKg > 0 && spoolWeight > 0 && (
                <p className="text-xs text-gray-400 mt-1">
                  ≈ {((pricePerKg * spoolWeight) / 1000).toFixed(2)} ₽ за катушку
                </p>
              )}
              {priceMode === 'per_spool' && pricePerSpool > 0 && spoolWeight > 0 && (
                <p className="text-xs text-gray-400 mt-1">
                  ≈ {((pricePerSpool / spoolWeight) * 1000).toFixed(2)} ₽ за кг
                </p>
              )}
            </div>
            <div className="flex flex-col">
              <div className="h-[34px] mb-2 flex items-end">
                <label className="block text-gray-300 text-sm font-medium">{t('createFilament.spoolWeightLabel')}</label>
              </div>
              <input
                type="number"
                value={spoolWeight || ''}
                onChange={(e) => setSpoolWeight(e.target.value === '' ? 0 : Number(e.target.value))}
                min={0}
                step="1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                placeholder="1000"
              />
            </div>
          </div>

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

          {/* Actions */}
          <div className="flex justify-end space-x-3 pt-4 border-t border-white/10">
            <button
              type="button"
              onClick={onClose}
              disabled={isLoading}
              className="px-6 py-3 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all disabled:opacity-50"
            >
              Отмена
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
        </div>
      </div>
    </div>
  );
};



