/** Модальное окно для создания/редактирования пресета */

import { useState, useEffect, FormEvent } from 'react';
import { X, Save, Loader2 } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { presetsAPI, filamentsAPI } from '../api/client';
import type { Preset, Filament } from '../types/api';

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

  const queryClient = useQueryClient();

  // Загружаем материалы для выбора (если не передан filamentId)
  const { data: filamentsData } = useQuery({
    queryKey: ['filaments', 'for-preset'],
    queryFn: () => filamentsAPI.list({ active_only: true, page: 1, size: 100 }),
    enabled: isOpen && !preset && !filamentId, // Загружаем только если нужно показать выбор материала
  });

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
    }
    setError(null);
  }, [preset, filamentId, isOpen]);

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
    mutationFn: ({ id, data }: { id: number; data: Partial<Preset> }) =>
      presetsAPI.update(id, data),
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
      // Создание нового пресета
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

  const isLoading = createMutation.isPending || updateMutation.isPending;

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
          {/* Material Selection (только при создании) */}
          {!preset && (
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Материал *</label>
              <select
                value={selectedFilamentId || ''}
                onChange={(e) => setSelectedFilamentId(Number(e.target.value))}
                required
                disabled={!!filamentId}
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all disabled:opacity-50"
              >
                <option value="">Выберите материал</option>
                {filamentsData?.items.map((filament: Filament) => (
                  <option key={filament.id} value={filament.id}>
                    {filament.name} ({filament.material_type})
                  </option>
                ))}
              </select>
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

          {/* Is Official (только при создании) */}
          {!preset && (
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

