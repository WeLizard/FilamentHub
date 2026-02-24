/** Модальное окно для удаления аккаунта */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { X, AlertTriangle, Trash2, Eye, Shield } from 'lucide-react';
import { authAPI } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { useAuth } from '../contexts/AuthContext';
import { useHeaderVisible } from '../hooks/useHeaderVisible';

interface DeleteAccountModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const DeleteAccountModal: React.FC<DeleteAccountModalProps> = ({ isOpen, onClose }) => {
  const { t } = useTranslation();
  const isHeaderVisible = useHeaderVisible();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [password, setPassword] = useState('');
  const [deleteReviews, setDeleteReviews] = useState(false);
  const [deleteBrandIfSole, setDeleteBrandIfSole] = useState(false);
  const [confirmText, setConfirmText] = useState('');

  const confirmWord = t('deleteAccount.confirmWord');

  // Загружаем статистику удаления
  const { data: stats, isLoading: isLoadingStats } = useQuery({
    queryKey: ['deletion-stats'],
    queryFn: () => authAPI.getDeletionStats(),
    enabled: isOpen && !!user,
  });

  // Мутация для удаления аккаунта
  const deleteAccountMutation = useMutation({
    mutationFn: (data: {
      delete_reviews: boolean;
      delete_brand_if_sole_representative: boolean;
      password_confirm: string;
    }) => authAPI.deleteAccount(data),
    onSuccess: async () => {
      // Очищаем все кеши
      await queryClient.clear();
      // Выходим из системы
      logout();
      // Перенаправляем на главную
      navigate('/');
      // Закрываем модальное окно
      onClose();
      alert(t('deleteAccount.successMessage'));
    },
    onError: (error: any) => {
      console.error('Delete account error:', error);
      alert(translateApiError(t, error.response?.data?.detail, t('deleteAccount.errorMessage')));
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (confirmText !== confirmWord) {
      alert(t('deleteAccount.enterConfirmWord'));
      return;
    }

    if (!password) {
      alert(t('deleteAccount.enterPassword'));
      return;
    }

    if (!confirm(t('deleteAccount.confirmPrompt'))) {
      return;
    }

    deleteAccountMutation.mutate({
      delete_reviews: deleteReviews,
      delete_brand_if_sole_representative: deleteBrandIfSole,
      password_confirm: password,
    });
  };

  if (!isOpen) return null;

  return (
    <div className={`fixed inset-0 z-[60] flex items-center justify-center p-4 ${isHeaderVisible ? 'pt-[88px]' : ''}`}>
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/75 backdrop-blur-sm"
        onClick={onClose}
      ></div>

      {/* Modal */}
      <div className="relative w-full max-w-2xl max-h-[90vh] bg-white/10 backdrop-blur-sm rounded-2xl border border-white/20 shadow-xl z-10 overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-white/20">
          <div className="flex items-center space-x-3">
            <div className="w-12 h-12 bg-red-500/20 rounded-xl flex items-center justify-center">
              <Trash2 className="w-6 h-6 text-red-400" />
            </div>
            <div>
              <h2 className="text-2xl font-bold text-white">{t('deleteAccount.title')}</h2>
              <p className="text-sm text-gray-400">{t('deleteAccount.subtitle')}</p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 text-gray-400 hover:text-white transition-colors"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Предупреждение */}
          <div className="bg-red-500/20 border border-red-500/50 rounded-xl p-4">
            <div className="flex items-start space-x-3">
              <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-red-300 mb-1">{t('deleteAccount.warningTitle')}</h3>
                <p className="text-xs text-red-200">
                  {t('deleteAccount.warningText')}
                </p>
              </div>
            </div>
          </div>

          {/* Статистика */}
          {isLoadingStats ? (
            <div className="text-center py-8">
              <p className="text-gray-400">{t('deleteAccount.loadingStats')}</p>
            </div>
          ) : stats && (
            <div className="bg-white/5 rounded-xl p-4 border border-white/10">
              <h3 className="text-lg font-bold text-white mb-4 flex items-center">
                <Eye className="w-5 h-5 mr-2 text-blue-400" />
                {t('deleteAccount.statsTitle')}
              </h3>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-gray-400">{t('deleteAccount.presetsCreated')}</p>
                  <p className="text-white font-semibold">{stats.presets_count}</p>
                  {stats.official_presets_count > 0 && (
                    <p className="text-xs text-green-400 mt-1">
                      {t('deleteAccount.officialCount', { count: stats.official_presets_count })}
                    </p>
                  )}
                  {stats.approved_presets_count > 0 && (
                    <p className="text-xs text-blue-400 mt-1">
                      {t('deleteAccount.approvedCount', { count: stats.approved_presets_count })}
                    </p>
                  )}
                  {stats.presets_used_by_others_count > 0 && (
                    <p className="text-xs text-yellow-400 mt-1">
                      {t('deleteAccount.usedByOthers', { count: stats.presets_used_by_others_count })}
                    </p>
                  )}
                </div>
                <div>
                  <p className="text-gray-400">{t('deleteAccount.reviewsCount')}</p>
                  <p className="text-white font-semibold">{stats.reviews_count}</p>
                </div>
                <div>
                  <p className="text-gray-400">{t('deleteAccount.savedPresets')}</p>
                  <p className="text-white font-semibold">{stats.saved_presets_count}</p>
                </div>
                <div>
                  <p className="text-gray-400">{t('deleteAccount.brandRequests')}</p>
                  <p className="text-white font-semibold">{stats.brand_requests_count}</p>
                </div>
                {stats.is_brand_representative && (
                  <div className="col-span-2">
                    <p className="text-gray-400">{t('deleteAccount.brandRepresentative')}</p>
                    <p className="text-white font-semibold">
                      {t('deleteAccount.otherReps', { count: stats.brand_other_representatives_count })}
                    </p>
                    {stats.brand_other_representatives_count === 0 && (
                      <p className="text-xs text-yellow-400 mt-1">
                        {t('deleteAccount.soleRepWarning')}
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Опции удаления */}
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Опция для отзывов */}
            <div className="bg-white/5 rounded-xl p-4 border border-white/10">
              <label className="flex items-start space-x-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={deleteReviews}
                  onChange={(e) => setDeleteReviews(e.target.checked)}
                  className="mt-1 w-4 h-4 rounded border-white/20 bg-white/10 text-red-500 focus:ring-2 focus:ring-red-500"
                />
                <div className="flex-1">
                  <p className="text-sm font-medium text-white mb-1">
                    {t('deleteAccount.deleteReviews')}
                  </p>
                  <p className="text-xs text-gray-400">
                    {t('deleteAccount.deleteReviewsHint')}
                  </p>
                </div>
              </label>
            </div>

            {/* Опция для бренда */}
            {stats?.is_brand_representative && stats.brand_other_representatives_count === 0 && (
              <div className="bg-white/5 rounded-xl p-4 border border-white/10">
                <label className="flex items-start space-x-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={deleteBrandIfSole}
                    onChange={(e) => setDeleteBrandIfSole(e.target.checked)}
                    className="mt-1 w-4 h-4 rounded border-white/20 bg-white/10 text-red-500 focus:ring-2 focus:ring-red-500"
                  />
                  <div className="flex-1">
                    <p className="text-sm font-medium text-white mb-1">
                      {t('deleteAccount.deleteBrand')}
                    </p>
                    <p className="text-xs text-gray-400">
                      {t('deleteAccount.deleteBrandHint')}
                    </p>
                  </div>
                </label>
              </div>
            )}

            {/* Пароль */}
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">
                {t('deleteAccount.confirmPassword')}
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all"
                placeholder={t('deleteAccount.passwordPlaceholder')}
              />
            </div>

            {/* Подтверждение текста */}
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">
                {t('deleteAccount.confirmTextLabel')}
              </label>
              <input
                type="text"
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                required
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-red-500 focus:border-transparent transition-all"
                placeholder={confirmWord}
              />
            </div>

            {/* Информация */}
            <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4">
              <div className="flex items-start space-x-3">
                <Shield className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
                <div className="flex-1 text-xs text-blue-200">
                  <p className="mb-1">
                    <strong>{t('deleteAccount.infoOfficialPresets')}</strong>
                  </p>
                  <p className="mb-1">
                    <strong>{t('deleteAccount.infoUsedPresets')}</strong>
                  </p>
                  <p>
                    {t('deleteAccount.infoAgreement')}{' '}
                    <a href="/user-agreement" target="_blank" className="text-blue-300 hover:text-blue-200 underline">
                      {t('deleteAccount.userAgreement')}
                    </a>
                    {' '}{t('deleteAccount.agreementSection')}
                  </p>
                </div>
              </div>
            </div>

            {/* Кнопки */}
            <div className="flex space-x-4 pt-4">
              <button
                type="button"
                onClick={onClose}
                className="flex-1 px-6 py-3 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all border border-white/20"
              >
                {t('deleteAccount.cancel')}
              </button>
              <button
                type="submit"
                disabled={deleteAccountMutation.isPending || confirmText !== confirmWord || !password}
                className="flex-1 px-6 py-3 bg-gradient-to-r from-red-600 to-red-700 hover:from-red-700 hover:to-red-800 text-white rounded-xl transition-all shadow-lg shadow-red-500/25 hover:shadow-red-500/40 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
              >
                {deleteAccountMutation.isPending ? (
                  <>
                    <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin mr-2"></div>
                    {t('deleteAccount.deleting')}
                  </>
                ) : (
                  <>
                    <Trash2 className="w-5 h-5 mr-2" />
                    {t('deleteAccount.deleteButton')}
                  </>
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};
