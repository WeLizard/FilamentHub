/** Модальное окно для создания print profile */

import { useState, useEffect, FormEvent } from 'react';
import { X, Save, Loader2, Layers } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { printProfilesAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import type { PrintProfile } from '../types/api';

interface CreatePrintProfileModalProps {
  isOpen: boolean;
  onClose: () => void;
  profile?: PrintProfile | null; // Если передан, то редактирование
  baseProfile?: PrintProfile | null; // Базовый профиль для клонирования
}

export const CreatePrintProfileModal: React.FC<CreatePrintProfileModalProps> = ({
  isOpen,
  onClose,
  profile,
  baseProfile,
}) => {
  const { user } = useAuth();
  const queryClient = useQueryClient();

  // Форма
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('');
  const [qualityTier, setQualityTier] = useState('');
  const [defaultNozzle, setDefaultNozzle] = useState('');
  const [layerHeight, setLayerHeight] = useState<number | ''>('');
  const [notes, setNotes] = useState('');

  // Маппинг quality tier для отображения
  const qualityTierMap: Record<string, string> = {
    superdraft: 'Extra Draft',
    draft: 'Draft',
    standard: 'Standard',
    optimal: 'Optimal',
    fine: 'Fine',
    highdetail: 'Extra Fine',
  };

  // Флаг для отслеживания, было ли имя изменено пользователем вручную
  const [nameManuallyChanged, setNameManuallyChanged] = useState(false);

  // Автогенерация имени в формате OrcaSlicer при изменении layer_height и quality_tier
  // Срабатывает только если имя не было изменено пользователем вручную
  useEffect(() => {
    if (!profile && !baseProfile && !nameManuallyChanged && layerHeight && qualityTier) {
      const layerStr = typeof layerHeight === 'number' 
        ? layerHeight.toFixed(2).replace(/\.?0+$/, '')
        : String(layerHeight);
      const qualityDisplay = qualityTierMap[qualityTier.toLowerCase()] || qualityTier.charAt(0).toUpperCase() + qualityTier.slice(1);
      const generatedName = `${layerStr}mm ${qualityDisplay} @FilamentHub`;
      setName(generatedName);
    }
  }, [layerHeight, qualityTier, profile, baseProfile, nameManuallyChanged]);

  // Сбрасываем флаг при изменении режима (редактирование/создание)
  useEffect(() => {
    if (isOpen) {
      setNameManuallyChanged(false);
    }
  }, [isOpen, profile, baseProfile]);

  // Генерируем slug из name при изменении
  useEffect(() => {
    if (!profile && !baseProfile && name) {
      const generatedSlug = name
        .toLowerCase()
        .trim()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-z0-9\s-]/g, '')
        .replace(/\s+/g, '-')
        .replace(/-+/g, '-')
        .replace(/^-|-$/g, '');
      setSlug(generatedSlug || '');
    }
  }, [name, profile, baseProfile]);

  // Заполняем форму при редактировании или клонировании
  useEffect(() => {
    if (isOpen) {
      if (profile) {
        // Редактирование
        setName(profile.name || '');
        setSlug(profile.slug || '');
        setDescription(profile.description || '');
        setCategory(profile.category || '');
        setQualityTier(profile.quality_tier || '');
        setDefaultNozzle(profile.default_nozzle || '');
        setLayerHeight(profile.layer_height_mm || '');
        setNotes(profile.notes || '');
      } else if (baseProfile) {
        // Клонирование
        setName(`${baseProfile.name} (копия)`);
        setSlug(`${baseProfile.slug}-copy`);
        setDescription(baseProfile.description || '');
        setCategory(baseProfile.category || '');
        setQualityTier(baseProfile.quality_tier || '');
        setDefaultNozzle(baseProfile.default_nozzle || '');
        setLayerHeight(baseProfile.layer_height_mm || '');
        setNotes(baseProfile.notes || '');
      } else {
        // Создание нового
        setName('');
        setSlug('');
        setDescription('');
        setCategory('');
        setQualityTier('');
        setDefaultNozzle('');
        setLayerHeight('');
        setNotes('');
      }
    }
  }, [isOpen, profile, baseProfile]);

  // Мутация для создания/обновления
  const createMutation = useMutation({
    mutationFn: (data: any) => {
      if (profile) {
        return printProfilesAPI.update(profile.id, data);
      }
      return printProfilesAPI.create(data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['print-profiles'] });
      queryClient.invalidateQueries({ queryKey: ['print-profiles', user?.id] });
      onClose();
    },
    onError: (error: any) => {
      console.error('Ошибка сохранения print profile:', error);
      alert(error?.response?.data?.detail || error?.message || 'Не удалось сохранить профиль печати');
    },
  });

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    
    if (!name.trim()) {
      alert('Введите название профиля');
      return;
    }
    
    if (!slug.trim()) {
      alert('Введите slug профиля');
      return;
    }

    const data = {
      name: name.trim(),
      slug: slug.trim(),
      description: description.trim() || null,
      category: category.trim() || null,
      quality_tier: qualityTier.trim() || null,
      default_nozzle: defaultNozzle.trim() || null,
      layer_height_mm: layerHeight ? parseFloat(layerHeight.toString()) : null,
      notes: notes.trim() || null,
      active: true,
    };

    createMutation.mutate(data);
  };

  if (!isOpen) return null;

  const qualityTiers = ['Draft', 'Standard', 'High', 'Ultra'];
  const nozzleSizes = ['0.2', '0.3', '0.4', '0.5', '0.6', '0.8', '1.0'];

  return (
    <div className="fixed inset-0 bg-black/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-gradient-to-br from-gray-900 to-gray-800 rounded-2xl shadow-2xl border border-white/20 max-w-3xl w-full max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-white/10">
          <div className="flex items-center gap-3">
            <Layers className="w-6 h-6 text-purple-400" />
            <h2 className="text-2xl font-bold text-white">
              {profile ? 'Редактировать профиль печати' : baseProfile ? 'Клонировать профиль печати' : 'Создать профиль печати'}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/10 rounded-lg text-gray-400 hover:text-white transition-all"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Название */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Название <span className="text-red-400">*</span>
              {layerHeight && qualityTier && (
                <span className="text-xs text-gray-400 ml-2">
                  (Рекомендуемый формат для OrcaSlicer: &quot;{typeof layerHeight === 'number' ? layerHeight.toFixed(2).replace(/\.?0+$/, '') : layerHeight}mm {qualityTierMap[qualityTier.toLowerCase()] || qualityTier.charAt(0).toUpperCase() + qualityTier.slice(1)} @FilamentHub&quot;)
                </span>
              )}
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setNameManuallyChanged(true); // Отмечаем, что имя изменено вручную
              }}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              placeholder={layerHeight && qualityTier 
                ? `${typeof layerHeight === 'number' ? layerHeight.toFixed(2).replace(/\.?0+$/, '') : layerHeight}mm ${qualityTierMap[qualityTier.toLowerCase()] || qualityTier.charAt(0).toUpperCase() + qualityTier.slice(1)} @FilamentHub`
                : "Например: 0.20mm Standard @Voron"}
              required
            />
            {layerHeight && qualityTier && !name.match(/@\w+$/i) && name && (
              <p className="text-xs text-amber-400 mt-1">
                💡 Рекомендуется формат для совместимости с OrcaSlicer: &quot;{typeof layerHeight === 'number' ? layerHeight.toFixed(2).replace(/\.?0+$/, '') : layerHeight}mm {qualityTierMap[qualityTier.toLowerCase()] || qualityTier.charAt(0).toUpperCase() + qualityTier.slice(1)} @FilamentHub&quot;
              </p>
            )}
          </div>

          {/* Slug */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Slug (уникальный идентификатор) <span className="text-red-400">*</span>
            </label>
            <input
              type="text"
              value={slug}
              onChange={(e) => setSlug(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 font-mono text-sm"
              placeholder="standard-0.4mm"
              required
            />
            <p className="text-xs text-gray-500 mt-1">Только латинские буквы, цифры и дефисы</p>
          </div>

          {/* Категория */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Категория
            </label>
            <input
              type="text"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              placeholder="Например: Standard, Draft, Quality"
            />
          </div>

          {/* Quality Tier */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Качество печати
            </label>
            <select
              value={qualityTier}
              onChange={(e) => setQualityTier(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-purple-500"
            >
              <option value="">Не указано</option>
              {qualityTiers.map((tier) => (
                <option key={tier} value={tier}>
                  {tier}
                </option>
              ))}
            </select>
          </div>

          {/* Default Nozzle */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Диаметр сопла по умолчанию (мм)
            </label>
            <select
              value={defaultNozzle}
              onChange={(e) => setDefaultNozzle(e.target.value)}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-purple-500"
            >
              <option value="">Не указано</option>
              {nozzleSizes.map((size) => (
                <option key={size} value={size}>
                  {size} мм
                </option>
              ))}
            </select>
          </div>

          {/* Layer Height */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Высота слоя (мм)
            </label>
            <input
              type="number"
              step="0.01"
              min="0.05"
              max="1.0"
              value={layerHeight}
              onChange={(e) => setLayerHeight(e.target.value ? parseFloat(e.target.value) : '')}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              placeholder="0.2"
            />
          </div>

          {/* Описание */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Описание
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 resize-none"
              placeholder="Краткое описание профиля..."
            />
          </div>

          {/* Заметки */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              Заметки (только для вас)
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 resize-none"
              placeholder="Личные заметки о профиле..."
            />
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 pt-4 border-t border-white/10">
            <button
              type="button"
              onClick={onClose}
              className="px-6 py-2 rounded-lg border border-white/20 text-gray-300 hover:bg-white/10 transition-all"
            >
              Отмена
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="px-6 py-2 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-lg transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {createMutation.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Сохранение...
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  {profile ? 'Сохранить изменения' : 'Создать профиль'}
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

