/** Модальное окно для создания/редактирования отзыва */

import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Star, CheckCircle, XCircle, AlertCircle, Settings, Shield } from 'lucide-react';
import { Printer3DIcon } from './icons/Printer3DIcon';
import { useMutation, useQueryClient, useQuery } from '@tanstack/react-query';
import { filamentReviewsAPI } from '../api/client';
import { FilamentReview, Preset } from '../types/api';
import { StarRating } from './StarRating';
import { useAuth } from '../contexts/AuthContext';
import { useHeaderVisible } from '../hooks/useHeaderVisible';

interface CreateReviewModalProps {
  filamentId: number;
  review?: FilamentReview | null; // Если передан, то редактирование
  onClose: () => void;
  onSuccess?: () => void;
}

export const CreateReviewModal: React.FC<CreateReviewModalProps> = ({
  filamentId,
  review = null,
  onClose,
  onSuccess,
}) => {
  const { t } = useTranslation();
  const isHeaderVisible = useHeaderVisible();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const isEdit = !!review;

  const [rating, setRating] = useState<number>(review?.rating || 0);
  const [success, setSuccess] = useState<boolean>(review?.success ?? true);
  const [comment, setComment] = useState<string>(review?.comment || '');
  const [printerModel, setPrinterModel] = useState<string>(review?.printer_model || '');
  const [selectedPresetId, setSelectedPresetId] = useState<number | null>(review?.preset_id || null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Загружаем доступные пресеты для этого филамента
  const { data: availablePresetsData, isLoading: isLoadingPresets, error: presetsError } = useQuery({
    queryKey: ['available-presets-for-review', filamentId],
    queryFn: () => filamentReviewsAPI.getAvailablePresets(filamentId),
    enabled: !isEdit && !!user,
    retry: false, // Не повторяем запрос при ошибке
  });

  // Автоматически выбираем официальный пресет при загрузке (если не редактирование)
  useEffect(() => {
    if (!isEdit && availablePresetsData?.items && availablePresetsData.items.length > 0 && !selectedPresetId) {
      const officialPreset = availablePresetsData.items.find(p => p.is_official);
      if (officialPreset) {
        setSelectedPresetId(officialPreset.id);
      } else if (availablePresetsData.items.length > 0) {
        // Если нет официального, выбираем первый сохраненный
        setSelectedPresetId(availablePresetsData.items[0].id);
      }
    }
  }, [availablePresetsData, isEdit, selectedPresetId]);

  // Мутация для создания/обновления отзыва
  const createMutation = useMutation({
    mutationFn: (data: {
      filament_id: number;
      preset_id?: number | null;
      success: boolean;
      rating: number;
      comment?: string | null;
      printer_model?: string | null;
    }) => {
      if (isEdit && review) {
        return filamentReviewsAPI.update(review.id, data);
      }
      return filamentReviewsAPI.create(data);
    },
    onSuccess: () => {
      // Обновляем кэш отзывов и статистики
      queryClient.invalidateQueries({ queryKey: ['filament-reviews', filamentId] });
      queryClient.invalidateQueries({ queryKey: ['filament-rating-stats', filamentId] });
      queryClient.invalidateQueries({ queryKey: ['filament', filamentId] });
      // Обновляем кэш отзывов пользователя (для профиля)
      if (user?.id) {
        queryClient.invalidateQueries({ queryKey: ['user-reviews', user.id] });
      }
      // Обновляем все запросы отзывов (на случай если есть другие страницы)
      queryClient.invalidateQueries({ queryKey: ['filament-reviews'] });
      
      if (onSuccess) {
        onSuccess();
      }
      onClose();
    },
    onError: (error: any) => {
      if (error.response?.data?.detail) {
        setErrors({ submit: error.response.data.detail });
      } else {
        setErrors({ submit: t('createReview.saveError') });
      }
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrors({});

    // Валидация
    if (rating === 0) {
      setErrors({ rating: t('createReview.selectRating') });
      return;
    }

    createMutation.mutate({
      filament_id: filamentId,
      preset_id: selectedPresetId,
      success,
      rating,
      comment: comment.trim() || null,
      printer_model: printerModel.trim() || null,
    });
  };

  if (!user) {
    return (
      <div className={`fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 ${isHeaderVisible ? 'pt-[88px]' : ''}`}>
        <div className="bg-gray-900 rounded-2xl p-8 border border-white/20 max-w-md w-full mx-4">
          <div className="text-center">
            <AlertCircle className="w-16 h-16 text-yellow-400 mx-auto mb-4" />
            <h2 className="text-2xl font-bold text-white mb-4">{t('createReview.authRequired')}</h2>
            <p className="text-gray-400 mb-6">
              {t('createReview.authRequiredMessage')}
            </p>
            <button
              onClick={onClose}
              className="px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-xl transition-colors"
            >
              {t('createReview.close')}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center z-50 p-4 ${isHeaderVisible ? 'pt-[88px]' : ''}`}>
      <div className="bg-gray-900 rounded-2xl p-8 border border-white/20 max-w-2xl w-full max-h-[90vh] overflow-y-auto">
        {/* Заголовок */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-white">
            {isEdit ? t('createReview.editTitle') : t('createReview.createTitle')}
          </h2>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-white transition-colors rounded-lg hover:bg-white/10"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Выбор пресета (только при создании, не при редактировании) */}
          {!isEdit && (
            <div>
              <label className="block text-white font-semibold mb-3">
                <Settings className="w-4 h-4 inline mr-2" />
                {t('createReview.presetSettings')} {availablePresetsData && availablePresetsData.total > 1 && <span className="text-gray-400 text-sm font-normal">({t('createReview.optional')})</span>}
              </label>
              {isLoadingPresets ? (
                <div className="text-gray-400 text-sm">{t('createReview.loadingPresets')}</div>
              ) : presetsError ? (
                <div className="bg-yellow-500/20 border border-yellow-500/30 rounded-xl p-4">
                  <p className="text-yellow-400 text-sm">
                    {t('createReview.presetsLoadError')}
                  </p>
                </div>
              ) : availablePresetsData && availablePresetsData.items.length > 0 ? (
                <div className="space-y-2">
                  {availablePresetsData.items.map((preset: Preset) => (
                    <button
                      key={preset.id}
                      type="button"
                      onClick={() => setSelectedPresetId(preset.id)}
                      className={`w-full text-left px-4 py-3 rounded-xl border transition-colors ${
                        selectedPresetId === preset.id
                          ? 'bg-purple-500/20 border-purple-500 text-white'
                          : 'bg-white/5 border-white/20 text-gray-300 hover:border-white/30'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center space-x-2">
                          {preset.is_official && (
                            <span title={t('createReview.officialPreset')}>
                              <Shield className="w-4 h-4 text-green-400" />
                            </span>
                          )}
                          <span className="font-semibold">{preset.name}</span>
                          {preset.is_saved && (
                            <span className="text-xs text-purple-400">({t('createReview.inProfile')})</span>
                          )}
                        </div>
                        {preset.rating !== null && preset.rating !== undefined && (
                          <div className="flex items-center space-x-1">
                            <Star className="w-4 h-4 text-yellow-400 fill-current" />
                            <span className="text-sm">{preset.rating.toFixed(1)}</span>
                          </div>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              ) : (
                <div className="bg-yellow-500/20 border border-yellow-500/30 rounded-xl p-4">
                  <p className="text-yellow-400 text-sm">
                    {presetsError
                      ? t('createReview.presetsLoadError')
                      : t('createReview.noPresetsAvailable')}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Рейтинг */}
          <div>
            <label className="block text-white font-semibold mb-3">
              {t('createReview.rating')} <span className="text-red-400">*</span>
            </label>
            <StarRating rating={rating} onChange={setRating} />
            {errors.rating && (
              <p className="text-red-400 text-sm mt-1">{errors.rating}</p>
            )}
          </div>

          {/* Успешность печати */}
          <div>
            <label className="block text-white font-semibold mb-3">
              {t('createReview.printResult')} <span className="text-red-400">*</span>
            </label>
            <div className="flex items-center space-x-4">
              <button
                type="button"
                onClick={() => setSuccess(true)}
                className={`flex items-center space-x-2 px-6 py-3 rounded-xl border transition-colors ${
                  success
                    ? 'bg-green-500/20 border-green-500 text-green-400'
                    : 'bg-white/5 border-white/20 text-gray-400 hover:border-white/30'
                }`}
              >
                <CheckCircle className="w-5 h-5" />
                <span className="font-semibold">{t('createReview.successful')}</span>
              </button>
              <button
                type="button"
                onClick={() => setSuccess(false)}
                className={`flex items-center space-x-2 px-6 py-3 rounded-xl border transition-colors ${
                  !success
                    ? 'bg-red-500/20 border-red-500 text-red-400'
                    : 'bg-white/5 border-white/20 text-gray-400 hover:border-white/30'
                }`}
              >
                <XCircle className="w-5 h-5" />
                <span className="font-semibold">{t('createReview.problems')}</span>
              </button>
            </div>
          </div>

          {/* Модель принтера */}
          <div>
            <label className="block text-white font-semibold mb-2">
              <Printer3DIcon className="w-4 h-4 inline mr-2" />
              {t('createReview.printerModel')}
            </label>
            <input
              type="text"
              value={printerModel}
              onChange={(e) => setPrinterModel(e.target.value)}
              placeholder={t('createReview.printerModelPlaceholder')}
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 transition-colors"
              maxLength={200}
            />
          </div>

          {/* Комментарий */}
          <div>
            <label className="block text-white font-semibold mb-2">
              {t('createReview.comment')}
            </label>
            <textarea
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              placeholder={t('createReview.commentPlaceholder')}
              rows={6}
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 transition-colors resize-none"
              maxLength={2000}
            />
            <div className="mt-1 text-sm text-gray-400 text-right">
              {comment.length} / 2000
            </div>
          </div>

          {/* Ошибки */}
          {errors.submit && (
            <div className="bg-red-500/20 border border-red-500/30 rounded-xl p-4">
              <p className="text-red-400">{errors.submit}</p>
            </div>
          )}

          {/* Кнопки */}
          <div className="flex items-center justify-end space-x-4 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-6 py-3 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-colors"
            >
              {t('createReview.cancel')}
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending || rating === 0}
              className="px-6 py-3 bg-purple-600 hover:bg-purple-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-xl transition-colors font-semibold"
            >
              {createMutation.isPending
                ? t('createReview.saving')
                : isEdit
                ? t('createReview.saveChanges')
                : t('createReview.publish')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};



