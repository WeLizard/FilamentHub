/** Детальная страница филамента */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Star,
  CheckCircle,
  Settings,
  Users,
  Thermometer,
  Gauge,
  Ruler,
  QrCode,
  Shield,
  ArrowLeft,
  TrendingUp,
  MessageCircle,
  Package,
  Wind,
  ExternalLink,
  Fan,
  Flame,
  Hammer,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { filamentsAPI, brandsAPI, savedPresetsAPI, filamentReviewsAPI, qrAPI } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { FilamentPreview } from '../components/FilamentPreview';
import { ReviewCard } from '../components/ReviewCard';
import { CreateReviewModal } from '../components/CreateReviewModal';
import { PresetSyncToggle } from '../components/PresetSyncToggle';
import { SEOHead } from '../components/SEOHead';
import { FilamentReview } from '../types/api';
import type { AxiosError } from 'axios';

export const FilamentDetailPage: React.FC = () => {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [showQR, setShowQR] = useState(false);
  const [activeTab, setActiveTab] = useState<'presets' | 'reviews'>('presets');
  const [showCreateReviewModal, setShowCreateReviewModal] = useState(false);
  const [editingReview, setEditingReview] = useState<FilamentReview | null>(null);
  const [reviewsPage, setReviewsPage] = useState(1);
  
  // Определяем откуда пришли (из каталога или профиля)
  const cameFrom = location.state?.from || 'catalog';

  // Загружаем филамент
  const {
    data: filament,
    isLoading: isLoadingFilament,
    error: filamentError,
  } = useQuery({
    queryKey: ['filament', id],
    queryFn: () => filamentsAPI.get(Number(id)),
    enabled: !!id,
  });

  // Загружаем бренд
  const { data: brandData } = useQuery({
    queryKey: ['brand', filament?.brand_id],
    queryFn: () => brandsAPI.get(filament!.brand_id),
    enabled: !!filament?.brand_id,
  });

  // Загружаем все пресеты
  const { data: presetsData, isLoading: isLoadingPresets } = useQuery({
    queryKey: ['filament-presets', id],
    queryFn: () => filamentsAPI.getPresets(Number(id)),
    enabled: !!id,
  });

  // Загружаем список сохранённых пресетов
  const { data: savedPresets } = useQuery({
    queryKey: ['saved-presets', user?.id],
    queryFn: () => savedPresetsAPI.list(),
    enabled: !!user?.id,
  });

  const savedPresetIds = new Set(savedPresets?.items.map(sp => sp.preset_id) || []);

  // Мутация для сохранения пресета
  const savePresetMutation = useMutation({
    mutationFn: (presetId: number) => {
      if (!user) {
        throw new Error(t('filamentDetailPage.loginRequired'));
      }
      return savedPresetsAPI.save(presetId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saved-presets'] });
      queryClient.invalidateQueries({ queryKey: ['saved-presets-details'] });
      queryClient.invalidateQueries({ queryKey: ['user-presets'] });
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      console.error('Error saving preset:', error);
      // Можно добавить уведомление пользователю
      alert(translateApiError(t, error.response?.data?.detail, t('filamentDetailPage.errorSavingPreset')));
    },
  });

  // Загружаем отзывы
  const { data: reviewsData, isLoading: isLoadingReviews, refetch: refetchReviews } = useQuery({
    queryKey: ['filament-reviews', id, reviewsPage],
    queryFn: () => filamentReviewsAPI.list(Number(id), { page: reviewsPage, size: 20, active_only: true }),
    enabled: !!id,
  });

  // Загружаем статистику рейтингов
  const { data: ratingStats } = useQuery({
    queryKey: ['filament-rating-stats', id],
    queryFn: () => filamentReviewsAPI.getStats(Number(id)),
    enabled: !!id,
  });

  // Мутация для удаления отзыва
  const deleteReviewMutation = useMutation({
    mutationFn: (reviewId: number) => filamentReviewsAPI.delete(reviewId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['filament-reviews', id] });
      queryClient.invalidateQueries({ queryKey: ['filament-rating-stats', id] });
    },
  });

  const handleEditReview = (review: FilamentReview) => {
    setEditingReview(review);
    setShowCreateReviewModal(true);
  };

  const handleDeleteReview = (reviewId: number) => {
    if (confirm(t('filamentDetailPage.confirmDeleteReview'))) {
      deleteReviewMutation.mutate(reviewId);
    }
  };

  if (isLoadingFilament) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-white text-xl">{t('filamentDetailPage.loadingMaterial')}</div>
      </div>
    );
  }

  if (filamentError || !filament) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-red-400 text-xl">{t('filamentDetailPage.materialNotFound')}</div>
      </div>
    );
  }

  // Получаем официальный пресет и пресеты сообщества
  const officialPreset = presetsData?.items.find((p) => p.is_official);
  const communityPresets = presetsData?.items.filter((p) => !p.is_official);
  
  // Проверяем, сохранён ли официальный пресет
  const isOfficialPresetSaved = officialPreset ? savedPresetIds.has(officialPreset.id) : false;
  // Проверяем, является ли официальный пресет созданным пользователем
  const isOfficialPresetOwn = officialPreset && user ? officialPreset.user_id === user.id : false;

  // РЕЙТИНГ ФИЛАМЕНТА: только из отзывов (FilamentReview)
  // Это оценка качества самого материала пользователями
  const filamentRating = ratingStats?.avg_rating ?? null;
  const filamentSuccessRate = ratingStats?.success_rate ?? null;
  
  // РЕЙТИНГ ПРЕСЕТА: отдельно для каждого пресета (preset.rating)
  // Это оценка качества настроек печати для конкретного пресета
  // Показывается у каждого пресета индивидуально

  const getOrcaNumber = (
    settings: Record<string, any> | null | undefined,
    key: string,
  ): number | null => {
    if (!settings) {
      return null;
    }
    const rawValue = settings[key];
    if (rawValue === undefined || rawValue === null) {
      return null;
    }
    const baseValue = Array.isArray(rawValue) ? rawValue[0] : rawValue;
    if (baseValue === undefined || baseValue === null || baseValue === '') {
      return null;
    }
    const normalized =
      typeof baseValue === 'string'
        ? baseValue.replace(',', '.').replace(/[^0-9.\-]/g, '')
        : baseValue;
    const parsed =
      typeof normalized === 'string' ? parseFloat(normalized) : Number(normalized);
    return Number.isNaN(parsed) ? null : parsed;
  };

  const officialSofteningTemperature = officialPreset
    ? getOrcaNumber(officialPreset.orcaslicer_settings, 'temperature_vitrification')
    : null;
  const officialRequiredNozzleHRC = officialPreset
    ? getOrcaNumber(officialPreset.orcaslicer_settings, 'required_nozzle_HRC') ??
      getOrcaNumber(officialPreset.orcaslicer_settings, 'required_nozzle_hrc')
    : null;

  // JSON-LD structured data для филамента
  const jsonLd = filament && brandData
    ? {
        '@context': 'https://schema.org',
        '@type': 'Product',
        name: filament.name,
        description: `${filament.material_type} filament by ${brandData.name}`,
        brand: {
          '@type': 'Brand',
          name: brandData.name,
        },
        category: `3D Printing Filament - ${filament.material_type}`,
        offers: {
          '@type': 'Offer',
          price: filament.price_per_kg?.toString() || undefined,
          priceCurrency: 'RUB',
        },
      }
    : undefined;

  return (
    <>
      {filament && (
        <SEOHead
          title={`${filament.name} - ${brandData?.name || 'FilamentHub'}`}
          description={t('filamentDetailPage.seoDescription', { materialType: filament.material_type, name: filament.name, brand: brandData?.name || '' })}
          keywords={t('filamentDetailPage.seoKeywords', { name: filament.name, materialType: filament.material_type, brand: brandData?.name || '' })}
          url={`/filaments/${filament.id}`}
          type="product"
          jsonLd={jsonLd}
          allowAI={true}
        />
      )}
      <div className="space-y-4 md:space-y-6">
        {/* Кнопка назад */}
        <button
        onClick={() => navigate(cameFrom === 'profile' ? '/profile' : '/')}
        className="flex items-center gap-2 text-gray-300 hover:text-white active:text-white transition-colors text-sm md:text-base"
      >
        <ArrowLeft className="w-4 h-4 md:w-5 md:h-5" />
        <span>{cameFrom === 'profile' ? t('filamentDetailPage.backToProfile') : t('filamentDetailPage.backToCatalog')}</span>
      </button>

      {/* Заголовок */}
      <div className="bg-white/10 backdrop-blur-sm rounded-xl md:rounded-2xl p-4 md:p-8 border border-white/20 shadow-xl">
        <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4 mb-4 md:mb-6">
          <div className="flex-1">
            <div className="flex flex-wrap items-center gap-2 md:gap-3 mb-3 md:mb-4">
              {brandData && (
                <>
                  <span
                    onClick={() => navigate(`/brands/${brandData.id}`)}
                    className={`${brandData.verified ? 'text-green-400' : 'text-purple-300'} font-bold text-lg md:text-2xl hover:underline cursor-pointer transition-colors`}
                  >
                    {brandData.name}
                  </span>
                  {brandData.verified && (
                    <Shield className="w-4 h-4 md:w-6 md:h-6 text-green-400" />
                  )}
                </>
              )}
              <h1 className="text-xl md:text-4xl font-bold text-white">{filament.name}</h1>
              <span className="px-2 py-0.5 md:px-3 md:py-1 bg-purple-500/20 text-purple-300 text-xs md:text-base rounded-full border border-purple-500/30">
                {filament.material_type}
              </span>
            </div>

            {/* Статистика материала */}
            <div className="flex flex-wrap items-center gap-3 md:gap-6 text-xs md:text-lg mb-3 md:mb-4">
              {/* Рейтинг материала (из отзывов) */}
              {filamentRating !== null && (
                <span className="flex items-center text-gray-300" title={t('filamentDetailPage.materialRatingTitle')}>
                  <Star className="w-3.5 h-3.5 md:w-5 md:h-5 mr-1 md:mr-2 text-yellow-400 fill-current" />
                  <span className="font-bold text-white">{filamentRating.toFixed(1)}</span>
                  {ratingStats && ratingStats.total_reviews > 0 && (
                    <span className="text-gray-400 text-xs md:text-sm ml-1">({ratingStats.total_reviews})</span>
                  )}
                </span>
              )}
              {/* Успешность печати (из отзывов) */}
              {filamentSuccessRate !== null && (
                <span className="flex items-center text-gray-300" title={t('filamentDetailPage.successRateTitle')}>
                  <CheckCircle className="w-3.5 h-3.5 md:w-5 md:h-5 mr-1 md:mr-2 text-green-400" />
                  <span className="font-bold text-green-400">{filamentSuccessRate.toFixed(1)}<span className="hidden md:inline">{t('filamentDetailPage.successPercent')}</span><span className="md:hidden">%</span></span>
                  {ratingStats && ratingStats.total_reviews > 0 && (
                    <span className="hidden md:inline text-gray-400 text-sm ml-1">{t('filamentDetailPage.fromReviews', { count: ratingStats.total_reviews })}</span>
                  )}
                </span>
              )}
              {/* Количество пресетов */}
              <span className="flex items-center text-gray-300" title={t('filamentDetailPage.presetsCountTitle')}>
                <TrendingUp className="w-3.5 h-3.5 md:w-5 md:h-5 mr-1 md:mr-2 text-blue-400" />
                <span className="font-bold text-white">{presetsData?.total || 0} <span className="hidden md:inline">{t('filamentDetailPage.presets')}</span></span>
              </span>
              {/* Просмотры */}
              <span className="flex items-center text-gray-300" title={t('filamentDetailPage.viewsCountTitle')}>
                <Package className="w-3.5 h-3.5 md:w-5 md:h-5 mr-1 md:mr-2 text-purple-400" />
                <span className="font-bold text-white">{filament.views_count || 0} <span className="hidden md:inline">{t('filamentDetailPage.views')}</span></span>
              </span>
              {/* Количество отзывов */}
              {ratingStats && ratingStats.total_reviews > 0 && (
                <span className="hidden md:flex items-center text-gray-300" title={t('filamentDetailPage.reviewsCountTitle')}>
                  <MessageCircle className="w-5 h-5 mr-2 text-purple-400" />
                  <span className="font-bold text-white">{ratingStats.total_reviews} {t('filamentDetailPage.reviews')}</span>
                </span>
              )}
            </div>

            {/* Описание */}
            {filament.description && (
              <p className="text-gray-300 text-sm md:text-base">{filament.description}</p>
            )}
          </div>

          <div className="flex md:flex-col items-center md:items-end gap-3 md:gap-0 md:text-right md:ml-8">
            {brandData?.website && (
              <a
                href={brandData.website}
                target="_blank"
                rel="noopener noreferrer"
                className="hidden md:inline-flex items-center justify-end space-x-2 text-purple-400 hover:text-purple-300 transition-colors mb-2"
                title={brandData.website}
              >
                <ExternalLink className="w-5 h-5" />
                <span className="text-sm">
                  {brandData.website.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '')}
                </span>
              </a>
            )}
            {filament.price_per_kg && (
              <p className="text-2xl md:text-4xl font-bold text-green-400 md:mb-2">
                {Math.round(filament.price_per_kg)}₽
              </p>
            )}
            {filament.spool_weight && (
              <p className="text-gray-400 text-sm md:text-lg">
                {Math.round(filament.spool_weight)}g
              </p>
            )}
          </div>
        </div>

        {/* Детали материала */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-6 mb-4 md:mb-6">
          {filament.diameter && (
            <div className="flex items-center gap-2 md:gap-3 text-gray-300">
              <Ruler className="w-4 h-4 md:w-5 md:h-5 text-purple-400" />
              <div>
                <div className="text-[10px] md:text-sm">{t('filamentDetailPage.diameter')}</div>
                <div className="text-base md:text-xl font-bold text-white">{filament.diameter}mm</div>
              </div>
            </div>
          )}
          {filament.density && (
            <div className="flex items-center gap-2 md:gap-3 text-gray-300">
              <Package className="w-4 h-4 md:w-5 md:h-5 text-blue-400" />
              <div>
                <div className="text-[10px] md:text-sm">{t('filamentDetailPage.density')}</div>
                <div className="text-base md:text-xl font-bold text-white">{filament.density}</div>
              </div>
            </div>
          )}
          {(filament.color_hex || filament.color_name) && (
            <div className="flex items-center gap-2 md:gap-3 text-gray-300">
              <div className="flex-shrink-0 hidden md:block" style={{ transform: 'scale(0.4)', transformOrigin: 'left center', marginRight: '-80px' }}>
                <FilamentPreview colorHex={filament.color_hex || '#FFFFFF'} visualSettings={filament.visual_settings} size="medium" />
              </div>
              <div
                className="w-6 h-6 md:hidden rounded-full border-2 border-white/20"
                style={{ backgroundColor: filament.color_hex || '#FFFFFF' }}
              />
              <div>
                <div className="text-[10px] md:text-sm">{t('filamentDetailPage.color')}</div>
                <div className="text-base md:text-xl font-bold text-white">{filament.color_name || '—'}</div>
              </div>
            </div>
          )}
          <div className="flex items-center gap-2 md:gap-3 text-gray-300">
            <QrCode className="w-4 h-4 md:w-5 md:h-5 text-green-400" />
            <div>
              <div className="text-[10px] md:text-sm">{t('filamentDetailPage.scans')}</div>
              <div className="text-base md:text-xl font-bold text-white">{filament.scans_count || 0}</div>
            </div>
          </div>
        </div>

        {/* Кнопки действий */}
        <div className="flex space-x-4">
          {officialPreset ? (
            !user ? (
              <button
                disabled
                className="flex-1 bg-gray-600/50 text-white py-4 px-8 rounded-xl cursor-not-allowed text-lg font-semibold"
                title={t('filamentDetailPage.loginRequired')}
              >
                {t('filamentDetailPage.loginToAdd')}
              </button>
            ) : isOfficialPresetOwn ? (
              <button
                disabled
                className="flex-1 bg-purple-600/50 text-white py-4 px-8 rounded-xl cursor-not-allowed text-lg font-semibold flex items-center justify-center"
              >
                <CheckCircle className="w-6 h-6 mr-2" />
                {t('filamentDetailPage.yourPreset')}
              </button>
            ) : isOfficialPresetSaved ? (
              <button
                disabled
                className="flex-1 bg-green-600/50 text-white py-4 px-8 rounded-xl cursor-not-allowed text-lg font-semibold flex items-center justify-center"
              >
                <CheckCircle className="w-6 h-6 mr-2" />
                {t('filamentDetailPage.added')}
              </button>
            ) : (
              <button
                onClick={() => officialPreset && savePresetMutation.mutate(officialPreset.id)}
                disabled={savePresetMutation.isPending}
                className="flex-1 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white py-4 px-8 rounded-xl transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 text-lg font-semibold disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {savePresetMutation.isPending ? t('filamentDetailPage.saving') : t('filamentDetailPage.addToProfile')}
              </button>
            )
          ) : (
            <button
              disabled
              className="flex-1 bg-gray-600/50 text-white py-4 px-8 rounded-xl cursor-not-allowed text-lg font-semibold"
            >
              {t('filamentDetailPage.noPresets')}
            </button>
          )}
          <button
            onClick={() => setShowQR(!showQR)}
            className="px-6 py-4 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all border border-white/20"
          >
            <QrCode className="w-6 h-6" />
          </button>
        </div>

        {/* QR Code */}
        {showQR && (
          <div className="mt-6 p-6 bg-white/5 rounded-xl border border-white/10">
            <div className="text-center">
              {filament.qr_code ? (
                <>
                  <img
                    src={qrAPI.getQRCodeURL(filament.id, 256)}
                    alt={t('filamentDetailPage.qrCodeAlt', { name: filament.name })}
                    className="w-64 h-64 mx-auto mb-4 rounded-lg bg-white p-3"
                  />
                  <p className="text-gray-300 text-base font-medium mb-1">{t('filamentDetailPage.qrCode')}: {filament.qr_code}</p>
                  <p className="text-gray-400 text-sm mb-2">{t('filamentDetailPage.scanForImport')}</p>
                  <div className="flex items-center justify-center gap-2 text-gray-500 text-xs">
                    <QrCode className="w-4 h-4" />
                    <span>{t('filamentDetailPage.scans')}: {filament.scans_count || 0}</span>
                  </div>
                  <div className="mt-4 flex gap-2 justify-center">
                    <button
                      onClick={() => qrAPI.downloadQRCode(filament.id, 300)}
                      className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg text-sm transition-all border border-white/20"
                    >
                      {t('filamentDetailPage.download')} 300px
                    </button>
                    <button
                      onClick={() => qrAPI.downloadQRCode(filament.id, 600)}
                      className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg text-sm transition-all border border-white/20"
                    >
                      {t('filamentDetailPage.download')} 600px
                    </button>
                    <button
                      onClick={() => qrAPI.downloadQRCode(filament.id, 1200)}
                      className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg text-sm transition-all border border-white/20"
                    >
                      {t('filamentDetailPage.download')} 1200px
                    </button>
                  </div>
                </>
              ) : (
                <div className="py-8">
                  <QrCode className="w-20 h-20 mx-auto mb-3 text-gray-500" />
                  <p className="text-gray-400 text-sm mb-1">
                    {t('filamentDetailPage.qrVerifiedOnly')}
                  </p>
                  {brandData && (
                    <p className="text-gray-500 text-xs">
                      {t('filamentDetailPage.brand')}: {brandData.name} {brandData.verified ? '✓' : t('filamentDetailPage.notVerified')}
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Табы: Пресеты / Отзывы */}
      <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
        <div className="flex space-x-4 mb-6 border-b border-white/10">
          <button
            onClick={() => setActiveTab('presets')}
            className={`pb-4 px-4 font-semibold transition-colors ${
              activeTab === 'presets'
                ? 'text-purple-400 border-b-2 border-purple-400'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            <Settings className="w-5 h-5 inline mr-2" />
            {t('filamentDetailPage.presetsCount', { count: presetsData?.total || 0 })}
          </button>
          <button
            onClick={() => setActiveTab('reviews')}
            className={`pb-4 px-4 font-semibold transition-colors ${
              activeTab === 'reviews'
                ? 'text-purple-400 border-b-2 border-purple-400'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            <MessageCircle className="w-5 h-5 inline mr-2" />
            {t('filamentDetailPage.reviewsCount', { count: ratingStats?.total_reviews || 0 })}
          </button>
        </div>

        {activeTab === 'presets' && (
          <div className="space-y-6">
            {/* Официальный пресет */}
            {isLoadingPresets && (
              <div className="text-center py-8 text-gray-400">{t('filamentDetailPage.loadingPresets')}</div>
            )}

            {officialPreset && (
              <div className="bg-gradient-to-r from-purple-500/20 to-pink-500/20 rounded-xl border border-purple-500/30 p-6">
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-2">
                    <h3 className="text-xl font-bold text-white flex items-center">
                      <Settings className="w-5 h-5 mr-2" />
                      {t('filamentDetailPage.officialPreset')}
                    </h3>
                  </div>
                  <div className="flex items-center gap-3">
                    {officialPreset.printers && officialPreset.printers.length > 0 && (
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {officialPreset.printers.map((printer) => (
                          <span
                            key={printer.id}
                            className="px-2 py-0.5 bg-white/10 rounded-md text-xs text-gray-300 border border-white/20"
                            title={`${printer.manufacturer} ${printer.model}`}
                          >
                            {printer.name}
                          </span>
                        ))}
                      </div>
                    )}
                    <span className="text-purple-300 font-semibold">{t('filamentDetailPage.manufacturer')}</span>
                    {/* Рейтинг и успешность официального пресета */}
                    <div className="flex items-center space-x-2">
                      {officialPreset.rating !== null && officialPreset.rating !== undefined && (
                        <div className="flex items-center space-x-1" title={t('filamentDetailPage.presetRatingTitle')}>
                          <Star className="w-4 h-4 text-yellow-400 fill-current" />
                          <span className="text-white font-semibold">{officialPreset.rating.toFixed(1)}</span>
                        </div>
                      )}
                      {officialPreset.success_rate !== null && officialPreset.success_rate !== undefined && (
                        <div className="flex items-center space-x-1" title={t('filamentDetailPage.presetSuccessTitle')}>
                          <CheckCircle className="w-4 h-4 text-green-400" />
                          <span className="text-green-400 text-sm font-semibold">{officialPreset.success_rate.toFixed(1)}%</span>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                  <div className="flex items-center space-x-2">
                    <Thermometer className="w-5 h-5 text-red-400" />
                    <div>
                      <div className="text-gray-400 text-sm">{t('filamentDetailPage.nozzle')}</div>
                      <div className="text-white font-semibold">{officialPreset.extruder_temp}°C</div>
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Thermometer className="w-5 h-5 text-red-400" />
                    <div>
                      <div className="text-gray-400 text-sm">{t('filamentDetailPage.bed')}</div>
                      <div className="text-white font-semibold">{officialPreset.bed_temp}°C</div>
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Gauge className="w-5 h-5 text-blue-400" />
                    <div>
                      <div className="text-gray-400 text-sm">{t('filamentDetailPage.speed')}</div>
                      <div className="text-white font-semibold">{officialPreset.print_speed}mm/s</div>
                    </div>
                  </div>
                  {officialPreset.travel_speed && (
                    <div className="flex items-center space-x-2">
                      <Wind className="w-5 h-5 text-cyan-400" />
                      <div>
                        <div className="text-gray-400 text-sm">{t('filamentDetailPage.travel')}</div>
                        <div className="text-white font-semibold">{officialPreset.travel_speed}mm/s</div>
                      </div>
                    </div>
                  )}
                  {officialPreset.flow_rate && (
                    <div className="flex items-center space-x-2">
                      <Gauge className="w-5 h-5 text-yellow-400" />
                      <div>
                        <div className="text-gray-400 text-sm">{t('filamentDetailPage.flowRate')}</div>
                        <div className="text-white font-semibold">{officialPreset.flow_rate}%</div>
                      </div>
                    </div>
                  )}
                  {officialPreset.fan_speed !== null && (
                    <div className="flex items-center space-x-2">
                      <Fan className="w-5 h-5 text-orange-400" />
                      <div>
                        <div className="text-gray-400 text-sm">{t('filamentDetailPage.fan')}</div>
                        <div className="text-white font-semibold">{officialPreset.fan_speed}%</div>
                      </div>
                    </div>
                  )}
                  {officialPreset.retraction_length && (
                    <div className="flex items-center space-x-2">
                      <Wind className="w-5 h-5 text-purple-400" />
                      <div>
                        <div className="text-gray-400 text-sm">{t('filamentDetailPage.retraction')}</div>
                        <div className="text-white font-semibold">{officialPreset.retraction_length}mm</div>
                      </div>
                    </div>
                  )}
                  {officialPreset.retraction_speed && (
                    <div className="flex items-center space-x-2">
                      <Gauge className="w-5 h-5 text-indigo-400" />
                      <div>
                        <div className="text-gray-400 text-sm">{t('filamentDetailPage.retractionSpeed')}</div>
                        <div className="text-white font-semibold">{officialPreset.retraction_speed}mm/s</div>
                      </div>
                    </div>
                  )}
                  {officialSofteningTemperature !== null && (
                    <div className="flex items-center space-x-2">
                      <Flame className="w-5 h-5 text-orange-400" />
                      <div>
                        <div className="text-gray-400 text-sm">{t('filamentDetailPage.softeningTemp')}</div>
                        <div className="text-white font-semibold">{officialSofteningTemperature}°C</div>
                      </div>
                    </div>
                  )}
                  {officialRequiredNozzleHRC !== null && (
                    <div className="flex items-center space-x-2">
                      <Hammer className="w-5 h-5 text-amber-400" />
                      <div>
                        <div className="text-gray-400 text-sm">{t('filamentDetailPage.nozzleHardness')}</div>
                        <div className="text-white font-semibold">{officialRequiredNozzleHRC} HRC</div>
                      </div>
                    </div>
                  )}
                </div>
                
                {/* Расширенные параметры OrcaSlicer */}
                {officialPreset.orcaslicer_settings && Object.keys(officialPreset.orcaslicer_settings).length > 0 && (
                  <div className="mt-4 pt-4 border-t border-white/10">
                    <h4 className="text-sm font-medium text-gray-300 mb-3">{t('filamentDetailPage.advancedSettings')}</h4>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                      {officialPreset.orcaslicer_settings.nozzle_temperature_range_low?.[0] && officialPreset.orcaslicer_settings.nozzle_temperature_range_high?.[0] && (
                        <div className="flex items-center space-x-2">
                          <Thermometer className="w-4 h-4 text-orange-400" />
                          <div>
                            <div className="text-gray-400 text-xs">{t('filamentDetailPage.tempRange')}</div>
                            <div className="text-white text-sm font-semibold">
                              {officialPreset.orcaslicer_settings.nozzle_temperature_range_low[0]}–{officialPreset.orcaslicer_settings.nozzle_temperature_range_high[0]}°C
                            </div>
                          </div>
                        </div>
                      )}
                      {officialPreset.orcaslicer_settings.filament_max_volumetric_speed?.[0] && (
                        <div className="flex items-center space-x-2">
                          <Gauge className="w-4 h-4 text-blue-400" />
                          <div>
                            <div className="text-gray-400 text-xs">{t('filamentDetailPage.volumetricSpeed')}</div>
                            <div className="text-white text-sm font-semibold">
                              {officialPreset.orcaslicer_settings.filament_max_volumetric_speed[0]}mm³/s
                            </div>
                          </div>
                        </div>
                      )}
                      {officialPreset.orcaslicer_settings.fan_min_speed?.[0] && officialPreset.orcaslicer_settings.fan_max_speed?.[0] && (
                        <div className="flex items-center space-x-2">
                          <Fan className="w-4 h-4 text-cyan-400" />
                          <div>
                            <div className="text-gray-400 text-xs">{t('filamentDetailPage.fan')}</div>
                            <div className="text-white text-sm font-semibold">
                              {officialPreset.orcaslicer_settings.fan_min_speed[0]}–{officialPreset.orcaslicer_settings.fan_max_speed[0]}%
                            </div>
                          </div>
                        </div>
                      )}
                      {officialPreset.orcaslicer_settings.chamber_temperature?.[0] && Number(officialPreset.orcaslicer_settings.chamber_temperature[0]) > 0 && (
                        <div className="flex items-center space-x-2">
                          <Thermometer className="w-4 h-4 text-red-400" />
                          <div>
                            <div className="text-gray-400 text-xs">{t('filamentDetailPage.chamber')}</div>
                            <div className="text-white text-sm font-semibold">
                              {officialPreset.orcaslicer_settings.chamber_temperature[0]}°C
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Пресеты сообщества */}
            {communityPresets && communityPresets.length > 0 && (
              <div>
                <h3 className="text-xl font-bold text-white mb-4 flex items-center">
                  <Users className="w-5 h-5 mr-2" />
                  {t('filamentDetailPage.communityPresets', { count: communityPresets.length })}
                </h3>
                <div className="space-y-3">
                  {communityPresets.map((preset) => {
                    const isPresetSaved = savedPresetIds.has(preset.id);
                    const isPresetOwn = user ? preset.user_id === user.id : false;
                    const presetSofteningTemperature = getOrcaNumber(
                      preset.orcaslicer_settings,
                      'temperature_vitrification',
                    );
                    const presetRequiredNozzleHRC =
                      getOrcaNumber(preset.orcaslicer_settings, 'required_nozzle_HRC') ??
                      getOrcaNumber(preset.orcaslicer_settings, 'required_nozzle_hrc');
                    return (
                      <div
                        key={preset.id}
                        className="p-4 bg-white/5 rounded-xl border border-white/10 hover:bg-white/10 transition-all"
                      >
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center space-x-3 flex-1">
                            {preset.moderation_status === 'approved' && (
                              <CheckCircle className="w-5 h-5 text-green-400" />
                            )}
                            <div className="flex-1">
                              <div className="flex items-center gap-2 mb-1">
                                <p className="text-white font-semibold text-lg">{preset.name}</p>
                              </div>
                              {preset.description && (
                                <p className="text-gray-400 text-sm">{preset.description}</p>
                              )}
                            </div>
                          </div>
                          {preset.printers && preset.printers.length > 0 && (
                            <div className="flex items-center gap-1.5 flex-wrap ml-4">
                              {preset.printers.map((printer) => (
                                <span
                                  key={printer.id}
                                  className="px-2 py-0.5 bg-white/10 rounded-md text-xs text-gray-300 border border-white/20"
                                  title={`${printer.manufacturer} ${printer.model}`}
                                >
                                  {printer.name}
                                </span>
                              ))}
                            </div>
                          )}
                          <div className="text-right ml-4">
                            {/* Переключатель синхронизации - показываем для всех пресетов пользователя (если авторизован) */}
                            {user && (
                              <div className="mb-2 flex justify-end">
                                <PresetSyncToggle preset={preset} size="sm" />
                              </div>
                            )}
                            {/* Рейтинг пресета (отдельный от рейтинга материала) */}
                            {preset.rating !== null && preset.rating !== undefined ? (
                              <div className="flex items-center space-x-2 mb-2" title={t('filamentDetailPage.presetRatingTitle')}>
                              <Star className="w-5 h-5 text-yellow-400 fill-current" />
                                <span className="text-white font-bold">{preset.rating.toFixed(1)}</span>
                            </div>
                            ) : (
                              <div className="mb-2 text-gray-500 text-sm">{t('filamentDetailPage.noRating')}</div>
                            )}
                            {/* Успешность пресета */}
                            {preset.success_rate !== null && preset.success_rate !== undefined && (
                              <div className="flex items-center space-x-1 mb-1" title={t('filamentDetailPage.presetSuccessTitle')}>
                                <CheckCircle className="w-4 h-4 text-green-400" />
                                <span className="text-green-400 text-sm font-semibold">{preset.success_rate.toFixed(1)}%</span>
                              </div>
                            )}
                            {/* Использования пресета */}
                            <p className="text-gray-400 text-xs">{preset.usage_count} {t('filamentDetailPage.usages')}</p>
                          </div>
                        </div>
                        
                        {/* Параметры пресета */}
                        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 pt-3 border-t border-white/10 mb-3">
                        <div className="flex items-center space-x-2">
                          <Thermometer className="w-4 h-4 text-red-400" />
                          <div>
                            <div className="text-gray-400 text-xs">{t('filamentDetailPage.nozzle')}</div>
                            <div className="text-white text-sm font-semibold">{preset.extruder_temp}°C</div>
                          </div>
                        </div>
                        <div className="flex items-center space-x-2">
                          <Thermometer className="w-4 h-4 text-red-400" />
                          <div>
                            <div className="text-gray-400 text-xs">{t('filamentDetailPage.bed')}</div>
                            <div className="text-white text-sm font-semibold">{preset.bed_temp}°C</div>
                          </div>
                        </div>
                        <div className="flex items-center space-x-2">
                          <Gauge className="w-4 h-4 text-blue-400" />
                          <div>
                            <div className="text-gray-400 text-xs">{t('filamentDetailPage.speed')}</div>
                            <div className="text-white text-sm font-semibold">{preset.print_speed}mm/s</div>
                          </div>
                        </div>
                        {preset.travel_speed && (
                          <div className="flex items-center space-x-2">
                            <Wind className="w-4 h-4 text-cyan-400" />
                            <div>
                              <div className="text-gray-400 text-xs">{t('filamentDetailPage.travel')}</div>
                              <div className="text-white text-sm font-semibold">{preset.travel_speed}mm/s</div>
                            </div>
                          </div>
                        )}
                        {preset.flow_rate && (
                          <div className="flex items-center space-x-2">
                            <Gauge className="w-4 h-4 text-yellow-400" />
                            <div>
                              <div className="text-gray-400 text-xs">{t('filamentDetailPage.flowRate')}</div>
                              <div className="text-white text-sm font-semibold">{preset.flow_rate}%</div>
                            </div>
                          </div>
                        )}
                        {preset.fan_speed !== null && (
                          <div className="flex items-center space-x-2">
                            <Fan className="w-4 h-4 text-orange-400" />
                            <div>
                              <div className="text-gray-400 text-xs">{t('filamentDetailPage.fan')}</div>
                              <div className="text-white text-sm font-semibold">{preset.fan_speed}%</div>
                            </div>
                          </div>
                        )}
                        {preset.retraction_length && (
                          <div className="flex items-center space-x-2">
                            <Wind className="w-4 h-4 text-purple-400" />
                            <div>
                              <div className="text-gray-400 text-xs">{t('filamentDetailPage.retraction')}</div>
                              <div className="text-white text-sm font-semibold">{preset.retraction_length}mm</div>
                            </div>
                          </div>
                        )}
                        {preset.retraction_speed && (
                          <div className="flex items-center space-x-2">
                            <Gauge className="w-4 h-4 text-indigo-400" />
                            <div>
                              <div className="text-gray-400 text-xs">{t('filamentDetailPage.retractionSpeed')}</div>
                              <div className="text-white text-sm font-semibold">{preset.retraction_speed}mm/s</div>
                            </div>
                          </div>
                        )}
                        {presetSofteningTemperature !== null && (
                          <div className="flex items-center space-x-2">
                            <Flame className="w-4 h-4 text-orange-400" />
                            <div>
                              <div className="text-gray-400 text-xs">{t('filamentDetailPage.softeningTemp')}</div>
                              <div className="text-white text-sm font-semibold">{presetSofteningTemperature}°C</div>
                            </div>
                          </div>
                        )}
                        {presetRequiredNozzleHRC !== null && (
                          <div className="flex items-center space-x-2">
                            <Hammer className="w-4 h-4 text-amber-400" />
                            <div>
                              <div className="text-gray-400 text-xs">{t('filamentDetailPage.nozzleHardness')}</div>
                              <div className="text-white text-sm font-semibold">{presetRequiredNozzleHRC} HRC</div>
                            </div>
                          </div>
                        )}
                        </div>
                      
                      {/* Расширенные параметры OrcaSlicer */}
                      {preset.orcaslicer_settings && Object.keys(preset.orcaslicer_settings).length > 0 && (
                        <div className="mt-3 pt-3 border-t border-white/10">
                          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
                            {preset.orcaslicer_settings.nozzle_temperature_range_low?.[0] && preset.orcaslicer_settings.nozzle_temperature_range_high?.[0] && (
                              <div className="flex items-center space-x-2">
                                <Thermometer className="w-4 h-4 text-orange-400" />
                                <div>
                                  <div className="text-gray-400 text-xs">{t('filamentDetailPage.tempRange')}</div>
                                  <div className="text-white text-sm font-semibold">
                                    {preset.orcaslicer_settings.nozzle_temperature_range_low[0]}–{preset.orcaslicer_settings.nozzle_temperature_range_high[0]}°C
                                  </div>
                                </div>
                              </div>
                            )}
                            {preset.orcaslicer_settings.filament_max_volumetric_speed?.[0] && (
                              <div className="flex items-center space-x-2">
                                <Gauge className="w-4 h-4 text-blue-400" />
                                <div>
                                  <div className="text-gray-400 text-xs">{t('filamentDetailPage.volumetricSpeed')}</div>
                                  <div className="text-white text-sm font-semibold">
                                    {preset.orcaslicer_settings.filament_max_volumetric_speed[0]}mm³/s
                                  </div>
                                </div>
                              </div>
                            )}
                            {preset.orcaslicer_settings.fan_min_speed?.[0] && preset.orcaslicer_settings.fan_max_speed?.[0] && (
                              <div className="flex items-center space-x-2">
                                <Fan className="w-4 h-4 text-cyan-400" />
                                <div>
                                  <div className="text-gray-400 text-xs">{t('filamentDetailPage.fan')}</div>
                                  <div className="text-white text-sm font-semibold">
                                    {preset.orcaslicer_settings.fan_min_speed[0]}–{preset.orcaslicer_settings.fan_max_speed[0]}%
                                  </div>
                                </div>
                              </div>
                            )}
                            {preset.orcaslicer_settings.chamber_temperature?.[0] && Number(preset.orcaslicer_settings.chamber_temperature[0]) > 0 && (
                              <div className="flex items-center space-x-2">
                                <Thermometer className="w-4 h-4 text-red-400" />
                                <div>
                                  <div className="text-gray-400 text-xs">{t('filamentDetailPage.chamber')}</div>
                                  <div className="text-white text-sm font-semibold">
                                    {preset.orcaslicer_settings.chamber_temperature[0]}°C
                                  </div>
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                      
                      {/* Кнопка добавления в профиль */}
                      <div className="pt-3 border-t border-white/10">
                        {!user ? (
                          <button
                            disabled
                            className="w-full bg-gray-600/50 text-white py-2 px-4 rounded-lg cursor-not-allowed flex items-center justify-center"
                            title={t('filamentDetailPage.loginRequiredTitle')}
                          >
                            {t('filamentDetailPage.loginToAdd')}
                          </button>
                        ) : isPresetOwn ? (
                          <button
                            disabled
                            className="w-full bg-purple-600/50 text-white py-2 px-4 rounded-lg cursor-not-allowed flex items-center justify-center"
                          >
                            <CheckCircle className="w-5 h-5 mr-2" />
                            {t('filamentDetailPage.yourPreset')}
                          </button>
                        ) : isPresetSaved ? (
                          <button
                            disabled
                            className="w-full bg-green-600/50 text-white py-2 px-4 rounded-lg cursor-not-allowed flex items-center justify-center"
                          >
                            <CheckCircle className="w-5 h-5 mr-2" />
                            {t('filamentDetailPage.added')}
                          </button>
                        ) : (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              savePresetMutation.mutate(preset.id);
                            }}
                            disabled={savePresetMutation.isPending}
                            className="w-full bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white py-2 px-4 rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {savePresetMutation.isPending ? t('filamentDetailPage.saving') : t('filamentDetailPage.addToProfile')}
                          </button>
                        )}
                      </div>
                    </div>
                  );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'reviews' && (
          <div className="space-y-6">
            {/* Заголовок и кнопка создания отзыва */}
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xl font-bold text-white mb-2">
                  {t('filamentDetailPage.userReviews')}
                </h3>
                {ratingStats && ratingStats.total_reviews > 0 && (
                  <div className="flex items-center space-x-4 text-sm text-gray-400">
                    {ratingStats.avg_rating && (
                      <div className="flex items-center space-x-1">
                        <Star className="w-4 h-4 text-yellow-400 fill-current" />
                        <span className="text-white font-semibold">{ratingStats.avg_rating.toFixed(1)}</span>
                        <span>{t('filamentDetailPage.outOf5')}</span>
                      </div>
                    )}
                    {ratingStats.success_rate !== null && (
                      <div className="flex items-center space-x-1">
                        <CheckCircle className="w-4 h-4 text-green-400" />
                        <span>{ratingStats.success_rate.toFixed(1)}% {t('filamentDetailPage.successfulPrints')}</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
              {user && (
                <button
                  onClick={() => {
                    setEditingReview(null);
                    setShowCreateReviewModal(true);
                  }}
                  className="px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-xl transition-colors font-semibold flex items-center space-x-2"
                >
                  <MessageCircle className="w-5 h-5" />
                  <span>{t('filamentDetailPage.leaveReview')}</span>
                </button>
              )}
            </div>

            {/* Список отзывов */}
            {isLoadingReviews ? (
              <div className="text-center py-12 text-gray-400">{t('filamentDetailPage.loadingReviews')}</div>
            ) : reviewsData && reviewsData.items.length > 0 ? (
              <>
                <div className="space-y-4">
                  {reviewsData.items.map((review) => (
                    <ReviewCard
                      key={review.id}
                      review={review}
                      isOwn={user?.id === review.user_id}
                      onEdit={handleEditReview}
                      onDelete={handleDeleteReview}
                    />
                  ))}
                </div>

                {/* Пагинация */}
                {reviewsData.pages > 1 && (
                  <div className="flex items-center justify-center space-x-2 pt-6">
                    <button
                      onClick={() => setReviewsPage((p) => Math.max(1, p - 1))}
                      disabled={reviewsPage === 1}
                      className="px-4 py-2 bg-white/10 hover:bg-white/20 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl transition-colors"
                    >
                      {t('filamentDetailPage.prev')}
                    </button>
                    <span className="text-gray-300">
                      {t('filamentDetailPage.pageOf', { page: reviewsPage, total: reviewsData.pages })}
                    </span>
                    <button
                      onClick={() => setReviewsPage((p) => Math.min(reviewsData.pages, p + 1))}
                      disabled={reviewsPage >= reviewsData.pages}
                      className="px-4 py-2 bg-white/10 hover:bg-white/20 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl transition-colors"
                    >
                      {t('filamentDetailPage.next')}
                    </button>
                  </div>
                )}
              </>
            ) : (
          <div className="text-center py-12 text-gray-400">
            <MessageCircle className="w-16 h-16 mx-auto mb-4 opacity-50" />
                <p className="text-xl mb-2">{t('filamentDetailPage.noReviews')}</p>
                {user && (
                  <p className="text-sm">
                    {t('filamentDetailPage.beFirstReviewer')}
                  </p>
                )}
          </div>
            )}
          </div>
        )}

        {/* Модальное окно создания/редактирования отзыва */}
        {showCreateReviewModal && (
          <CreateReviewModal
            filamentId={Number(id)}
            review={editingReview}
            onClose={() => {
              setShowCreateReviewModal(false);
              setEditingReview(null);
            }}
            onSuccess={() => {
              setReviewsPage(1); // Возвращаемся на первую страницу
              // Явно обновляем отзывы после создания
              refetchReviews();
            }}
          />
        )}
      </div>
      </div>
    </>
  );
};
