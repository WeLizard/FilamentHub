/** Модальное окно для создания/редактирования пресета */

import { useState, useEffect, FormEvent, useRef } from 'react';
import { X, Save, Loader2, Check, Plus } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { presetsAPI, filamentsAPI, brandsAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import type { Preset, Filament, Brand } from '../types/api';

// Список типов материалов
const MATERIAL_TYPES = [
  'PLA', 'ABS', 'PETG', 'TPU', 'ASA', 'PC', 'Nylon', 'PEEK', 'HIPS', 'PP',
  'PLA+', 'PETG+', 'ABS+', 'Wood', 'Carbon Fiber', 'Glass Fiber', 'Metal', 'Matte', 'Silk', 'Transparent'
];

interface CreatePresetModalProps {
  isOpen: boolean;
  onClose: () => void;
  preset?: Preset | null; // Если передан, то редактирование, иначе создание
  filamentId?: number; // ID материала (если создание нового пресета)
}

export const CreatePresetModal: React.FC<CreatePresetModalProps> = ({
  isOpen,
  onClose,
  preset,
  filamentId,
}) => {
  const { user } = useAuth();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [isOfficial, setIsOfficial] = useState(false);
  const [extruderTemp, setExtruderTemp] = useState(200);
  const [bedTemp, setBedTemp] = useState(60);
  const [printSpeed, setPrintSpeed] = useState(50);
  const [travelSpeed, setTravelSpeed] = useState(150);
  const [layerHeight, setLayerHeight] = useState(0.2);
  const [flowRate, setFlowRate] = useState(100);
  const [fanSpeed, setFanSpeed] = useState(100);
  const [retractionLength, setRetractionLength] = useState(5.0);
  const [retractionSpeed, setRetractionSpeed] = useState(45.0);
  const [error, setError] = useState<string | null>(null);
  const [selectedFilamentId, setSelectedFilamentId] = useState<number | null>(filamentId || null);
  
  // Новые поля для создания нового филамента
  const [materialType, setMaterialType] = useState('PLA');
  const [brandSearch, setBrandSearch] = useState('');
  const [selectedBrandId, setSelectedBrandId] = useState<number | null>(null);
  const [filamentName, setFilamentName] = useState('');
  const [filamentColorName, setFilamentColorName] = useState('');
  const [filamentColorHex, setFilamentColorHex] = useState('#FF0000');
  const [showFilamentForm, setShowFilamentForm] = useState(false); // true = создать новый, false = выбрать существующий
  const [filamentSearch, setFilamentSearch] = useState(''); // Поиск существующего филамента
  const [showFilamentDropdown, setShowFilamentDropdown] = useState(false); // Показывать выпадающий список
  const [selectedFilament, setSelectedFilament] = useState<Filament | null>(null); // Выбранный филамент для отображения
  const [showBrandDropdown, setShowBrandDropdown] = useState(false); // Показывать выпадающий список брендов
  const [showMaterialTypeDropdown, setShowMaterialTypeDropdown] = useState(false); // Показывать выпадающий список типов
  
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

  // Загружаем филамент для редактирования
  const { data: editingFilament } = useQuery({
    queryKey: ['filament', preset?.filament_id],
    queryFn: () => filamentsAPI.get(preset!.filament_id),
    enabled: isOpen && !!preset?.filament_id, // Загружаем только при редактировании
  });

  // Загружаем материалы для выбора (если не передан filamentId И не создаем новый)
  const { data: filamentsData } = useQuery({
    queryKey: ['filaments', 'for-preset', { search: filamentSearch }],
    queryFn: () => filamentsAPI.list({ active_only: true, page: 1, size: 100, search: filamentSearch || undefined }),
    enabled: isOpen && !preset && !filamentId && !showFilamentForm, // Загружаем только если не создаем новый
  });

  // Загружаем бренды для поиска/выбора
  const { data: brandsData } = useQuery({
    queryKey: ['brands', { search: brandSearch }],
    queryFn: () => brandsAPI.list({ active_only: true, page: 1, size: 20, search: brandSearch || undefined }),
    enabled: isOpen && showFilamentForm, // Загружаем только если создаем новый филамент
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

  // Закрываем выпадающий список при клике вне его
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (filamentDropdownRef.current && !filamentDropdownRef.current.contains(event.target as Node)) {
        setShowFilamentDropdown(false);
      }
      if (brandDropdownRef.current && !brandDropdownRef.current.contains(event.target as Node)) {
        setShowBrandDropdown(false);
      }
      if (materialTypeDropdownRef.current && !materialTypeDropdownRef.current.contains(event.target as Node)) {
        setShowMaterialTypeDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Инициализация формы при редактировании
  useEffect(() => {
    if (preset) {
      setName(preset.name);
      setDescription(preset.description || '');
      setIsOfficial(preset.is_official);
      setExtruderTemp(preset.extruder_temp);
      setBedTemp(preset.bed_temp);
      setPrintSpeed(preset.print_speed);
      setTravelSpeed(preset.travel_speed || 150);
      setLayerHeight(preset.layer_height || 0.2);
      setFlowRate(preset.flow_rate || 100);
      setFanSpeed(preset.fan_speed || 100);
      setRetractionLength(preset.retraction_length || 5.0);
      setRetractionSpeed(preset.retraction_speed || 45.0);
      setSelectedFilamentId(preset.filament_id);
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
      setLayerHeight(0.2);
      setFlowRate(100);
      setFanSpeed(100);
      setRetractionLength(5.0);
      setRetractionSpeed(45.0);
      setSelectedFilamentId(filamentId || null);
      // Сброс полей создания нового материала
      setShowFilamentForm(false);
      setMaterialType('PLA');
      setBrandSearch('');
      setSelectedBrandId(null);
      setFilamentName('');
      setFilamentColorName('');
      setFilamentColorHex('#FF0000');
      setFilamentSearch('');
      setSelectedFilament(null);
      setShowBrandForm(false);
      setNewBrandName('');
      setNewBrandWebsite('');
    }
    setError(null);
  }, [preset, filamentId, isOpen]);

  // Когда загрузился филамент при редактировании, обновляем filamentSearch и selectedFilament
  useEffect(() => {
    if (editingFilament && preset) {
      setFilamentSearch(editingFilament.color_name ? `${editingFilament.name} (${editingFilament.color_name})` : editingFilament.name);
      setSelectedFilament(editingFilament);
    }
  }, [editingFilament, preset]);

  // Мутация для создания бренда
  const createBrandMutation = useMutation({
    mutationFn: (data: { name: string; slug: string; website?: string }) => brandsAPI.create(data),
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Ошибка при создании производителя');
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
      diameter?: number;
      density?: number;
      price_per_kg?: number;
      spool_weight?: number;
      description?: string;
    }) => filamentsAPI.create(data),
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Ошибка при создании материала');
    },
  });

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
      layer_height?: number;
      flow_rate?: number;
      fan_speed?: number;
      retraction_length?: number;
      retraction_speed?: number;
    }) => presetsAPI.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['presets'] });
      queryClient.invalidateQueries({ queryKey: ['filament-presets'] });
      queryClient.invalidateQueries({ queryKey: ['user-presets'] });
      onClose();
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Ошибка при создании пресета');
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
        layer_height?: number;
        flow_rate?: number;
        fan_speed?: number;
        retraction_length?: number;
        retraction_speed?: number;
      }>
    }) => presetsAPI.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['presets'] });
      queryClient.invalidateQueries({ queryKey: ['filament-presets'] });
      queryClient.invalidateQueries({ queryKey: ['user-presets'] });
      onClose();
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Ошибка при обновлении пресета');
    },
  });

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    // Если создаем новый филамент, сначала создаем его
    if (showFilamentForm && !preset) {
      // Если создаем новый бренд, сначала создаем его
      let brandId = selectedBrandId;
      
      if (showBrandForm) {
        if (!newBrandName.trim()) {
          setError('Введите название производителя');
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
          brandId = newBrand.id;
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
          brandId = newBrand.id;
        } catch (err) {
          // Ошибка уже обработана в createBrandMutation.onError
          return;
        }
      } else if (!selectedBrandId) {
        setError('Выберите производителя');
        return;
      }
      
      if (!filamentName.trim()) {
        setError('Введите название филамента');
        return;
      }

      try {
        const newFilament = await createFilamentMutation.mutateAsync({
          brand_id: brandId!,
          name: filamentName,
          material_type: materialType,
          color_name: filamentColorName || undefined,
          color_hex: filamentColorHex,
          diameter: 1.75,
          density: 1.24,
        });
        // Используем созданный филамент для пресета
        createMutation.mutate({
          filament_id: newFilament.id,
          name,
          description: description || undefined,
          is_official: isOfficial,
          extruder_temp: extruderTemp,
          bed_temp: bedTemp,
          print_speed: printSpeed,
          travel_speed: travelSpeed,
          layer_height: layerHeight,
          flow_rate: flowRate,
          fan_speed: fanSpeed,
          retraction_length: retractionLength,
          retraction_speed: retractionSpeed,
        });
      } catch (err) {
        // Ошибка уже обработана в createFilamentMutation.onError
      }
      return;
    }

    if (!selectedFilamentId) {
      setError('Выберите материал');
      return;
    }

    if (preset) {
      // Обновление существующего пресета
      updateMutation.mutate({
        id: preset.id,
        data: {
          name,
          description: description || undefined,
          extruder_temp: extruderTemp,
          bed_temp: bedTemp,
          print_speed: printSpeed,
          travel_speed: travelSpeed,
          layer_height: layerHeight,
          flow_rate: flowRate,
          fan_speed: fanSpeed,
          retraction_length: retractionLength,
          retraction_speed: retractionSpeed,
        },
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
        layer_height: layerHeight,
        flow_rate: flowRate,
        fan_speed: fanSpeed,
        retraction_length: retractionLength,
        retraction_speed: retractionSpeed,
      });
    }
  };

  if (!isOpen) return null;

  const isLoading = createMutation.isPending || updateMutation.isPending || createFilamentMutation.isPending;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 rounded-2xl p-6 w-full max-w-3xl max-h-[90vh] overflow-y-auto border border-white/20 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-white">
            {preset ? 'Редактировать пресет' : 'Создать новый пресет'}
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/10 rounded-lg transition-all text-gray-300 hover:text-white"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-4 p-3 bg-red-500/20 border border-red-500/30 rounded-lg text-red-300 text-sm">
            {error}
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Отображение филамента при редактировании */}
          {preset && editingFilament && (
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Филамент</label>
              <div className="p-4 bg-white/5 rounded-xl border border-white/10">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-lg font-bold text-white">{editingFilament.name}</h4>
                  <span className="px-3 py-1 bg-purple-600 rounded-lg text-white text-sm font-medium">
                    {editingFilament.material_type}
                  </span>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
                  {editingFilament.color_name && (
                    <div>
                      <span className="text-gray-400">Цвет:</span>
                      <span className="text-white ml-2">{editingFilament.color_name}</span>
                    </div>
                  )}
                  {editingFilament.diameter && (
                    <div>
                      <span className="text-gray-400">Диаметр:</span>
                      <span className="text-white ml-2">{editingFilament.diameter}mm</span>
                    </div>
                  )}
                  {editingFilament.density && (
                    <div>
                      <span className="text-gray-400">Плотность:</span>
                      <span className="text-white ml-2">{editingFilament.density}g/cm³</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Material Selection (только при создании) */}
          {!preset && (
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Филамент *</label>
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
                      placeholder="Например: Bestfilament PETG Красный"
                      className="flex-1 px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                    />
                    {selectedFilamentId ? (
                      <Check className="w-6 h-6 text-green-400" />
                    ) : (
                      <button
                        type="button"
                        onClick={() => setShowFilamentForm(true)}
                        className="p-3 bg-purple-600 hover:bg-purple-700 rounded-xl transition-all text-white"
                      >
                        <Plus className="w-5 h-5" />
                      </button>
                    )}
                  </div>
                  {showFilamentDropdown && filamentsData?.items && filamentsData.items.length > 0 && (
                    <div className="absolute z-10 w-full mt-2 max-h-60 overflow-y-auto bg-white/5 backdrop-blur-sm rounded-xl border border-white/10 shadow-xl">
                      {filamentsData.items.map((filament: Filament) => (
                        <button
                          key={filament.id}
                          type="button"
                          onClick={() => {
                            setSelectedFilamentId(filament.id);
                            setSelectedFilament(filament);
                            setFilamentSearch(filament.color_name ? `${filament.name} (${filament.color_name})` : filament.name);
                            setShowFilamentDropdown(false);
                          }}
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
                  
                  {/* Информация о выбранном филаменте */}
                  {selectedFilament && (
                    <div className="mt-4 p-4 bg-white/5 rounded-xl border border-white/10">
                      <div className="flex items-center justify-between mb-3">
                        <div>
                          {selectedFilament.brand_name && (
                            <span className="text-gray-300 text-sm">{selectedFilament.brand_name}</span>
                          )}
                          <h4 className="text-lg font-bold text-white">{selectedFilament.name}</h4>
                        </div>
                        <span className="px-3 py-1 bg-purple-600 rounded-lg text-white text-sm font-medium">
                          {selectedFilament.material_type}
                        </span>
                      </div>
                      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
                        {selectedFilament.color_name && (
                          <div>
                            <span className="text-gray-400">Цвет:</span>
                            <span className="text-white ml-2">{selectedFilament.color_name}</span>
                          </div>
                        )}
                        {selectedFilament.diameter && (
                          <div>
                            <span className="text-gray-400">Диаметр:</span>
                            <span className="text-white ml-2">{selectedFilament.diameter}mm</span>
                          </div>
                        )}
                        {selectedFilament.density && (
                          <div>
                            <span className="text-gray-400">Плотность:</span>
                            <span className="text-white ml-2">{selectedFilament.density}g/cm³</span>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                // Форма создания нового материала
                <div className="space-y-4 p-4 bg-white/5 rounded-xl border border-purple-500/30">
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-bold text-white">Создать новый материал</h3>
                    <button
                      type="button"
                      onClick={() => setShowFilamentForm(false)}
                      className="text-gray-400 hover:text-white text-sm"
                    >
                      Отмена
                    </button>
                  </div>
                  
                  {/* Тип материала */}
                  <div className="relative" ref={materialTypeDropdownRef}>
                    <label className="block text-gray-300 mb-2 text-sm font-medium">Тип материала *</label>
                    <div className="relative">
                      <input
                        type="text"
                        value={materialType}
                        onFocus={() => setShowMaterialTypeDropdown(true)}
                        readOnly
                        placeholder="Выберите тип материала"
                        className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all cursor-pointer"
                      />
                      {showMaterialTypeDropdown && (
                        <div className="absolute z-10 w-full mt-1 max-h-60 overflow-y-auto bg-white/5 backdrop-blur-sm rounded-xl border border-white/10 shadow-xl">
                          {MATERIAL_TYPES.map((type) => (
                            <button
                              key={type}
                              type="button"
                              onClick={() => {
                                setMaterialType(type);
                                setShowMaterialTypeDropdown(false);
                              }}
                              className="w-full px-4 py-3 text-left hover:bg-white/10 transition-all text-white border-b border-white/5 last:border-b-0"
                            >
                              {type}
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Поиск производителя */}
                  <div className="relative" ref={brandDropdownRef}>
                    <label className="block text-gray-300 mb-2 text-sm font-medium">Производитель *</label>
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
                        placeholder="Начните вводить название производителя..."
                        className="flex-1 px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all disabled:opacity-50"
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
                              className="p-3 bg-purple-600 hover:bg-purple-700 rounded-xl transition-all text-white"
                            >
                              <Plus className="w-5 h-5" />
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
                          Отмена
                        </button>
                      )}
                    </div>
                    {!showBrandForm && showBrandDropdown && brandsData?.items && brandsData.items.length > 0 && (
                      <div className="absolute z-10 w-full mt-1 max-h-48 overflow-y-auto bg-white/5 backdrop-blur-sm rounded-xl border border-white/10 shadow-xl">
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
                          onChange={(e) => setNewBrandName(e.target.value)}
                          placeholder="Название нового производителя..."
                          className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                        />
                        <input
                          type="text"
                          value={newBrandWebsite}
                          onChange={(e) => setNewBrandWebsite(e.target.value)}
                          placeholder="Сайт производителя (необязательно)"
                          className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                        />
                      </div>
                    )}
                  </div>

                  {/* Название филамента */}
                  <div>
                    <label className="block text-gray-300 mb-2 text-sm font-medium">Название филамента *</label>
                    <input
                      type="text"
                      value={filamentName}
                      onChange={(e) => setFilamentName(e.target.value)}
                      placeholder="Например: PLA+ Mate R24"
                      className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                    />
                    {similarFilamentsData?.items && similarFilamentsData.items.length > 0 && (
                      <div className="mt-2 p-3 bg-yellow-500/20 border border-yellow-500/30 rounded-lg text-yellow-300 text-sm">
                        <p className="font-medium mb-1">Похожие материалы у этого производителя:</p>
                        <ul className="list-disc list-inside space-y-1">
                          {similarFilamentsData.items.map((f: Filament) => (
                            <li key={f.id}>
                              {f.brand_name && <span className="text-gray-300">{f.brand_name} </span>}
                              {f.name}
                              {f.color_name && <span className="text-gray-400"> ({f.color_name})</span>}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>

                  {/* Цвет филамента */}
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-gray-300 mb-2 text-sm font-medium">Название цвета</label>
                      <input
                        type="text"
                        value={filamentColorName}
                        onChange={(e) => setFilamentColorName(e.target.value)}
                        placeholder="Например: Красный, Blue, Green"
                        className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                      />
                    </div>
                    <div>
                      <label className="block text-gray-300 mb-2 text-sm font-medium">Цвет HEX</label>
                      <div className="flex gap-2">
                        <input
                          type="color"
                          value={filamentColorHex}
                          onChange={(e) => setFilamentColorHex(e.target.value)}
                          className="h-12 w-20 rounded-xl cursor-pointer border border-white/20"
                        />
                        <input
                          type="text"
                          value={filamentColorHex}
                          onChange={(e) => setFilamentColorHex(e.target.value)}
                          placeholder="#FF0000"
                          className="flex-1 px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                        />
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Name */}
          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">Название пресета *</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              placeholder="Например: PLA Standard"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">Описание</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all resize-none"
              placeholder="Описание настроек..."
            />
          </div>

          {/* Is Official (только при создании И только для верифицированных производителей) */}
          {!preset && canCreateOfficial && (
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="isOfficial"
                checked={isOfficial}
                onChange={(e) => setIsOfficial(e.target.checked)}
                className="w-4 h-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
              />
              <label htmlFor="isOfficial" className="text-gray-300 text-sm">
                Официальный пресет (от производителя)
              </label>
            </div>
          )}

          {/* Temperature Settings */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">
                Температура сопла (°C) *
              </label>
              <input
                type="number"
                value={extruderTemp}
                onChange={(e) => setExtruderTemp(Number(e.target.value))}
                required
                min={150}
                max={300}
                step="1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">
                Температура стола (°C) *
              </label>
              <input
                type="number"
                value={bedTemp}
                onChange={(e) => setBedTemp(Number(e.target.value))}
                required
                min={0}
                max={120}
                step="1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              />
            </div>
          </div>

          {/* Speed Settings */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Скорость печати (mm/s) *</label>
              <input
                type="number"
                value={printSpeed}
                onChange={(e) => setPrintSpeed(Number(e.target.value))}
                required
                min={10}
                max={300}
                step="1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">
                Скорость перемещений (mm/s)
              </label>
              <input
                type="number"
                value={travelSpeed}
                onChange={(e) => setTravelSpeed(Number(e.target.value))}
                min={50}
                max={300}
                step="1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              />
            </div>
          </div>

          {/* Layer and Flow Settings */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Высота слоя (mm)</label>
              <input
                type="number"
                value={layerHeight}
                onChange={(e) => setLayerHeight(Number(e.target.value))}
                min={0.05}
                max={0.5}
                step="0.05"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Поток (%)</label>
              <input
                type="number"
                value={flowRate}
                onChange={(e) => setFlowRate(Number(e.target.value))}
                min={50}
                max={150}
                step="1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              />
            </div>
          </div>

          {/* Cooling and Retraction */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Скорость вентилятора (%)</label>
              <input
                type="number"
                value={fanSpeed}
                onChange={(e) => setFanSpeed(Number(e.target.value))}
                min={0}
                max={100}
                step="1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">
                Длина ретракции (mm)
              </label>
              <input
                type="number"
                value={retractionLength}
                onChange={(e) => setRetractionLength(Number(e.target.value))}
                min={0}
                max={10}
                step="0.1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">
                Скорость ретракции (mm/s)
              </label>
              <input
                type="number"
                value={retractionSpeed}
                onChange={(e) => setRetractionSpeed(Number(e.target.value))}
                min={10}
                max={100}
                step="1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              />
            </div>
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
                  <span>Сохранение...</span>
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  <span>{preset ? 'Сохранить' : 'Создать'}</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
