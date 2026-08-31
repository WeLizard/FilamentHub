/** Страница бренда с карточкой и списком филаментов */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Building2,
  Shield,
  Package,
  Star,
  ArrowLeft,
  Search,
} from 'lucide-react';
import { brandsAPI, filamentsAPI, filamentReviewsAPI } from '../api/client';
import type { Filament } from '../types/api';
import { useReaderCountry } from '../hooks/useReaderCountry';
import { Dropdown } from '../components/Dropdown';
import { SEOHead } from '../components/SEOHead';
import { SocialIcon } from '../components/socialIcons';
import { BrandLogoFrame } from '../components/BrandLogoFrame';
import { FilamentPreview } from '../components/FilamentPreview';
import { FilamentHandlingBadges } from '../components/FilamentHandlingBadges';
import { NozzleRequirementBadge } from '../components/NozzleRequirementBadge';
import { ProductQrButton } from '../components/ProductQrButton';
import { externalUrl, externalUrlHost } from '../utils/externalUrl';
import { filamentPublicPath } from '../utils/catalogUrls';
import { hasMetaNetworkLink } from '../utils/restrictedNetworks';

interface BrandFilamentCardProps {
  filament: Filament;
  onClick: () => void;
}

const BrandFilamentCard: React.FC<BrandFilamentCardProps> = ({ filament, onClick }) => (
  <div className="flex flex-col rounded-xl border border-white/15 bg-white/[0.07] shadow-lg backdrop-blur-sm">
  <button
    type="button"
    onClick={onClick}
    className="group flex min-h-36 w-full flex-1 flex-col rounded-xl p-4 text-left transition-all hover:bg-white/10 focus:outline-none focus:ring-2 focus:ring-purple-400"
  >
    <div className="flex items-start justify-between gap-3">
      <div className="min-w-0 flex-1">
        <h3 className="line-clamp-2 text-base font-bold leading-snug text-white transition-colors group-hover:text-purple-200">
          {filament.name}
        </h3>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="rounded-full border border-purple-500/30 bg-purple-500/20 px-2 py-0.5 text-xs font-medium text-purple-200">
            {filament.material_type}
          </span>
          <NozzleRequirementBadge
            requiredHrc={filament.required_nozzle_hrc}
            compact
            size="tight"
          />
        </div>
      </div>

      <FilamentPreview
        colorHex={filament.color_hex || '#FFFFFF'}
        visualSettings={filament.visual_settings}
        size="small"
        className="shrink-0 origin-right scale-75"
      />
    </div>

    <div className="mt-auto flex min-w-0 items-end justify-between gap-3 pt-3">
      <div className="min-w-0 text-xs text-gray-300">
        <p className="truncate">{filament.color_name || filament.color_hex || '—'}</p>
        {filament.ral_code && (
          <p className="mt-0.5 font-mono text-[10px] text-gray-500">RAL {filament.ral_code}</p>
        )}
      </div>
      <FilamentHandlingBadges
        filament={filament}
        compact
        className="shrink-0 justify-end"
      />
    </div>
  </button>
  {filament.qr_code && <div className="px-4 pb-4"><ProductQrButton key={filament.id} filament={filament} /></div>}
  </div>
);

export const BrandDetailPage: React.FC = () => {
  const { t, i18n } = useTranslation();
  const { identifier } = useParams<{ identifier: string }>();
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState('');
  const [materialTypeFilter, setMaterialTypeFilter] = useState<string | null>(null);
  const [isBrandLogoVisible, setIsBrandLogoVisible] = useState(false);
  const readerCountry = useReaderCountry();

  // Загружаем бренд
  const {
    data: brand,
    isLoading: isLoadingBrand,
    error: brandError,
  } = useQuery({
    queryKey: ['brand', identifier, readerCountry],
    queryFn: () => brandsAPI.get(identifier!, undefined, readerCountry),
    enabled: !!identifier,
  });

  // Загружаем филаменты бренда
  const {
    data: filamentsData,
    isLoading: isLoadingFilaments,
    error: filamentsError,
  } = useQuery({
    queryKey: ['brand-filaments', brand?.id, searchQuery, materialTypeFilter, readerCountry],
    queryFn: () =>
      filamentsAPI.list({
        page: 1,
        size: 100,
        brand_id: brand!.id,
        search: searchQuery || undefined,
        material_type: materialTypeFilter || undefined,
        country: readerCountry,
      }),
    enabled: !!brand?.id,
  });

  // Загружаем рейтинги для всех филаментов бренда (хук должен быть ДО early returns)
  const filamentIds = (filamentsData?.items || []).map((f) => f.id);
  const { data: ratingsData } = useQuery({
    queryKey: ['brand-ratings', brand?.id, filamentIds],
    queryFn: async () => {
      const stats = await Promise.all(
        filamentIds.map((fid) => filamentReviewsAPI.getStats(fid).catch(() => null))
      );
      return stats;
    },
    enabled: filamentIds.length > 0,
  });

  useEffect(() => {
    setIsBrandLogoVisible(Boolean(brand?.logo_url));
  }, [brand?.logo_url]);

  useEffect(() => {
    if (brand && identifier !== brand.slug) {
      navigate(`/brands/${brand.slug}`, { replace: true });
    }
  }, [brand, identifier, navigate]);

  if (isLoadingBrand) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-gray-400 text-xl">{t('brandDetailPage.loading')}</div>
      </div>
    );
  }

  if (brandError || !brand) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-red-400 text-xl">{t('brandDetailPage.notFound')}</div>
      </div>
    );
  }

  const filaments = filamentsData?.items || [];
  const materialTypes = Array.from(
    new Set(filaments.map((f) => f.material_type).filter(Boolean))
  ).sort();

  // Фильтруем филаменты по материалу
  const filteredFilaments = filaments.filter((f) => {
    if (materialTypeFilter && f.material_type !== materialTypeFilter) {
      return false;
    }
    return true;
  });
  const orderedFilaments = [
    ...filteredFilaments.filter((filament) => filament.line_id != null),
    ...filteredFilaments.filter((filament) => filament.line_id == null),
  ];

  // Вычисляем статистику
  const totalFilaments = filaments.length;
  const ratingsWithData = (ratingsData || []).filter(
    (s) => s && s.avg_rating !== null && s.avg_rating !== undefined && s.total_reviews > 0
  );
  const avgRating =
    ratingsWithData.length > 0
      ? ratingsWithData.reduce((acc, s) => acc + (s!.avg_rating || 0), 0) / ratingsWithData.length
      : null;

  const seoDescription = brand.description
    ? brand.description.slice(0, 160)
    : t('brandDetailPage.seoDescription', { name: brand.name, count: totalFilaments });
  const websiteUrl = externalUrl(brand.website);
  // The ban notice is a Russian legal requirement, so it follows the Russian
  // interface rather than the visitor's location.
  const showMetaNotice = i18n.language.startsWith('ru') && hasMetaNetworkLink([
    brand.website,
    ...(brand.social_media_urls ?? []),
    ...(brand.shop_links?.map((shop) => shop.url) ?? []),
  ]);

  return (
    <>
      <SEOHead
        title={brand.name}
        description={seoDescription}
        image={brand.logo_url || undefined}
        url={`/brands/${brand.slug}`}
        type="website"
      />
      <div className="space-y-6">
      {/* Кнопка назад */}
      <button
        onClick={() => navigate(-1)}
        className="flex items-center space-x-2 text-gray-300 hover:text-white transition-colors"
      >
        <ArrowLeft className="w-5 h-5" />
        <span>{t('brandDetailPage.back')}</span>
      </button>

      {/* Карточка бренда */}
      <div className="glass-panel rounded-2xl p-8 border border-white/20 shadow-xl">
        <div className="flex flex-col md:flex-row items-start md:items-center gap-6">
          {/* Логотип (если есть) */}
          <BrandLogoFrame
            src={isBrandLogoVisible ? brand.logo_url : null}
            alt={brand.name}
            backgroundColor={brand.logo_bg}
            size="hero"
            fallback={<Building2 className="h-12 w-12 text-purple-400" />}
            fallbackBackgroundClassName="bg-purple-500/20"
            onError={() => setIsBrandLogoVisible(false)}
          />

          {/* Информация о бренде */}
          <div className="flex-1">
            <div className="flex items-center space-x-3 mb-3">
              <h1 className="text-3xl font-bold text-white">{brand.name}</h1>
              {brand.verified && (
                <span
                  className="flex items-center space-x-1 px-3 py-1 bg-green-500/20 text-green-400 rounded-full border border-green-500/30"
                  title={t('brandDetailPage.verifiedMeaning')}
                >
                  <Shield className="w-4 h-4" />
                  <span className="text-sm font-semibold">{t('brandDetailPage.verified')}</span>
                </span>
              )}
            </div>

            {brand.description && (
              <p className="text-gray-300 mb-4 max-w-2xl">{brand.description}</p>
            )}

            {/* Статистика */}
            <div className="flex flex-wrap items-center gap-6 mb-4">
              <div className="flex items-center space-x-2 text-gray-300">
                <Package className="w-5 h-5 text-purple-400" />
                <span className="font-semibold text-white">{totalFilaments}</span>
                <span>{t('brandDetailPage.filaments')}</span>
              </div>
              {avgRating !== null && (
                <div className="flex items-center space-x-2 text-gray-300">
                  <Star className="w-5 h-5 text-yellow-400 fill-current" />
                  <span className="font-semibold text-white">{avgRating.toFixed(1)}</span>
                  <span>{t('brandDetailPage.avgRating')}</span>
                </div>
              )}
            </div>

            {/* Ссылки — иконки соцсетей/маркетплейсов */}
            <div className="flex flex-wrap items-center gap-2">
              {websiteUrl && (
                <a
                  href={websiteUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  title={t('brandDetailPage.website')}
                  className="flex items-center gap-2 h-10 px-3 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-all"
                >
                  <SocialIcon url={websiteUrl} className="w-5 h-5 flex-shrink-0" />
                  <span className="text-sm truncate max-w-[200px]">{externalUrlHost(brand.website)}</span>
                </a>
              )}
              {brand.shop_links?.map((shop, i) => {
                const shopUrl = externalUrl(shop.url);
                return shopUrl ? (
                  <a
                    key={`shop-${i}`}
                    href={shopUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    title={shop.platform || t('brandDetailPage.shop')}
                    className="w-10 h-10 flex items-center justify-center bg-white/10 hover:bg-white/20 text-white rounded-lg transition-all"
                  >
                    <SocialIcon url={shopUrl} kind="shop" className="w-5 h-5" />
                  </a>
                ) : null;
              })}
              {brand.social_media_urls?.map((url, i) => {
                const socialUrl = externalUrl(url);
                return socialUrl ? (
                  <a
                    key={`social-${i}`}
                    href={socialUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    title={externalUrlHost(url)}
                    className="w-10 h-10 flex items-center justify-center bg-white/10 hover:bg-white/20 text-white rounded-lg transition-all"
                  >
                    <SocialIcon url={socialUrl} className="w-5 h-5" />
                  </a>
                ) : null;
              })}
            </div>

            {showMetaNotice && (
              <p className="mt-2 text-[11px] leading-4 text-gray-500">
                {t('brandDetailPage.metaRestrictedNotice')}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Фильтры и поиск */}
      <div className="glass-panel rounded-xl p-4 border border-white/20">
        <div className="flex flex-col md:flex-row gap-4">
          {/* Поиск */}
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('brandDetailPage.searchPlaceholder')}
              className="w-full pl-10 pr-4 py-3 bg-white/5 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
          </div>

          {/* Фильтр по типу материала */}
          <div className="w-full md:w-64 relative z-10">
            <Dropdown
              label=""
              value={materialTypeFilter || ''}
              options={[
                { value: '', label: t('brandDetailPage.allMaterials') },
                ...materialTypes.map((type) => ({ value: type, label: type })),
              ]}
              onChange={(val) => setMaterialTypeFilter(val === '' ? null : String(val))}
              placeholder={t('brandDetailPage.materialType')}
            />
          </div>
        </div>
      </div>

      {/* Список филаментов */}
      {isLoadingFilaments ? (
        <div className="text-center py-12 text-gray-400">{t('brandDetailPage.loadingFilaments')}</div>
      ) : filamentsError ? (
        <div className="text-center py-12 text-red-400">{t('brandDetailPage.errorLoadingFilaments')}</div>
      ) : filteredFilaments.length === 0 ? (
        <div className="text-center py-12">
          <Package className="w-16 h-16 text-gray-400 mx-auto mb-4" />
          <p className="text-gray-400 text-xl">{t('brandDetailPage.noFilamentsFound')}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {orderedFilaments.map((filament) => (
            <BrandFilamentCard
              key={filament.id}
              filament={filament}
              onClick={() => navigate(filamentPublicPath(filament))}
            />
          ))}
        </div>
      )}
    </div>
    </>
  );
};
