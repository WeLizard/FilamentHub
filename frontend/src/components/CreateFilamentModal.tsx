/** Модальное окно для создания/редактирования материала */

import { useState, useEffect, FormEvent } from 'react';
import { X, Save, Loader2 } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { filamentsAPI, brandsAPI } from '../api/client';
import type { Filament, Brand } from '../types/api';

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
  const [brandIdValue, setBrandIdValue] = useState<number | null>(brandId || null);
  const [name, setName] = useState('');
  const [materialType, setMaterialType] = useState('PLA');
  const [colorName, setColorName] = useState('');
  const [colorHex, setColorHex] = useState('#FFFFFF');
  const [diameter, setDiameter] = useState(1.75);
  const [density, setDensity] = useState(1.24);
  const [pricePerKg, setPricePerKg] = useState(0);
  const [spoolWeight, setSpoolWeight] = useState(1000);
  const [description, setDescription] = useState('');
  const [error, setError] = useState<string | null>(null);

  const queryClient = useQueryClient();

  // Загружаем бренды для выбора (если не передан brandId)
  const { data: brandsData } = useQuery({
    queryKey: ['brands', 'for-filament'],
    queryFn: () => brandsAPI.list({ active_only: true, page: 1, size: 100 }),
    enabled: isOpen && !filament && !brandId,
  });

  // Инициализация формы при редактировании
  useEffect(() => {
    if (filament) {
      setBrandIdValue(filament.brand_id);
      setName(filament.name);
      setMaterialType(filament.material_type);
      setColorName(filament.color_name || '');
      setColorHex(filament.color_hex || '#FFFFFF');
      setDiameter(filament.diameter || 1.75);
      setDensity(filament.density || 1.24);
      setPricePerKg(filament.price_per_kg || 0);
      setSpoolWeight(filament.spool_weight || 1000);
      setDescription(filament.description || '');
    } else {
      // Сброс формы при создании нового
      setBrandIdValue(brandId || null);
      setName('');
      setMaterialType('PLA');
      setColorName('');
      setColorHex('#FFFFFF');
      setDiameter(1.75);
      setDensity(1.24);
      setPricePerKg(0);
      setSpoolWeight(1000);
      setDescription('');
    }
    setError(null);
  }, [filament, brandId, isOpen]);

  // Мутация для создания материала
  const createMutation = useMutation({
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['filaments'] });
      queryClient.invalidateQueries({ queryKey: ['brands'] });
      onClose();
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Ошибка при создании материала');
    },
  });

  // Мутация для обновления материала
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Filament> }) =>
      filamentsAPI.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['filaments'] });
      queryClient.invalidateQueries({ queryKey: ['brands'] });
      onClose();
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
      updateMutation.mutate({
        id: filament.id,
        data: {
          name,
          material_type: materialType,
          color_name: colorName || undefined,
          color_hex: colorHex || undefined,
          diameter,
          density,
          price_per_kg: pricePerKg || undefined,
          spool_weight: spoolWeight || undefined,
          description: description || undefined,
        },
      });
    } else {
      // Создание нового материала
      createMutation.mutate({
        brand_id: brandIdValue,
        name,
        material_type: materialType,
        color_name: colorName || undefined,
        color_hex: colorHex || undefined,
        diameter,
        density,
        price_per_kg: pricePerKg || undefined,
        spool_weight: spoolWeight || undefined,
        description: description || undefined,
      });
    }
  };

  if (!isOpen) return null;

  const isLoading = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 rounded-2xl p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto border border-white/20 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-white">
            {filament ? 'Редактировать материал' : 'Создать новый материал'}
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
          {/* Brand Selection (только при создании) */}
          {!filament && (
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Бренд *</label>
              <select
                value={brandIdValue || ''}
                onChange={(e) => setBrandIdValue(Number(e.target.value))}
                required
                disabled={!!brandId}
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all disabled:opacity-50"
              >
                <option value="">Выберите бренд</option>
                {brandsData?.items.map((brand: Brand) => (
                  <option key={brand.id} value={brand.id}>
                    {brand.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Name */}
          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">Название материала *</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              placeholder="Например: PLA Red"
            />
          </div>

          {/* Material Type and Color */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Тип материала *</label>
              <select
                value={materialType}
                onChange={(e) => setMaterialType(e.target.value)}
                required
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              >
                <option value="PLA">PLA</option>
                <option value="PETG">PETG</option>
                <option value="ABS">ABS</option>
                <option value="TPU">TPU</option>
                <option value="ASA">ASA</option>
                <option value="PC">PC</option>
                <option value="PA">PA (Nylon)</option>
                <option value="PVA">PVA</option>
                <option value="Other">Другое</option>
              </select>
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Цвет</label>
              <input
                type="text"
                value={colorName}
                onChange={(e) => setColorName(e.target.value)}
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                placeholder="Например: Red"
              />
            </div>
          </div>

          {/* Color Hex */}
          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">Цветовой код (HEX)</label>
            <div className="flex items-center space-x-3">
              <input
                type="color"
                value={colorHex}
                onChange={(e) => setColorHex(e.target.value)}
                className="w-16 h-12 rounded-lg border border-white/20 cursor-pointer"
              />
              <input
                type="text"
                value={colorHex}
                onChange={(e) => setColorHex(e.target.value)}
                pattern="^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$"
                className="flex-1 px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                placeholder="#FF0000"
              />
            </div>
          </div>

          {/* Diameter and Density */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Диаметр (mm) *</label>
              <select
                value={diameter}
                onChange={(e) => setDiameter(Number(e.target.value))}
                required
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
              >
                <option value={1.75}>1.75 mm</option>
                <option value={2.85}>2.85 mm</option>
                <option value={3.0}>3.0 mm</option>
              </select>
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Плотность (g/cm³)</label>
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
              <label className="block text-gray-300 mb-2 text-sm font-medium">Цена за кг (₽)</label>
              <input
                type="number"
                value={pricePerKg}
                onChange={(e) => setPricePerKg(Number(e.target.value))}
                min={0}
                step="1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                placeholder="800"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Вес катушки (g)</label>
              <input
                type="number"
                value={spoolWeight}
                onChange={(e) => setSpoolWeight(Number(e.target.value))}
                min={0}
                step="1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                placeholder="1000"
              />
            </div>
          </div>

          {/* Description */}
          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">Описание</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all resize-none"
              placeholder="Описание материала..."
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
                  <span>Сохранение...</span>
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  <span>{filament ? 'Сохранить' : 'Создать'}</span>
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};



