/** Страница бренда с карточкой и списком филаментов */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Building2,
  Shield,
  ExternalLink,
  Package,
  Star,
  CheckCircle,
  ArrowLeft,
  Search,
  Filter,
} from 'lucide-react';
import { brandsAPI, filamentsAPI } from '../api/client';
import { FilamentPreview } from '../components/FilamentPreview';
import { Dropdown } from '../components/Dropdown';
import type { Filament } from '../types/api';

export const BrandDetailPage: React.FC = () => {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchQuery, setSearchQuery] = useState('');
  const [materialTypeFilter, setMaterialTypeFilter] = useState<string | null>(null);

  // Загружаем бренд
  const {
    data: brand,
    isLoading: isLoadingBrand,
    error: brandError,
  } = useQuery({
    queryKey: ['brand', id],
    queryFn: () => brandsAPI.get(Number(id)),
    enabled: !!id,
  });

  // Загружаем филаменты бренда
  const {
    data: filamentsData,
    isLoading: isLoadingFilaments,
    error: filamentsError,
  } = useQuery({
    queryKey: ['brand-filaments', id, searchQuery, materialTypeFilter],
    queryFn: () =>
      filamentsAPI.list({
        page: 1,
        size: 100,
        brand_id: Number(id),
        search: searchQuery || undefined,
        material_type: materialTypeFilter || undefined,
      }),
    enabled: !!id,
  });

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

  // Вычисляем статистику
  const totalFilaments = filaments.length;
  const avgRating =
    filaments.length > 0
      ? filaments.reduce((acc, f) => {
          // TODO: Получить реальный рейтинг из пресетов
          return acc + 4.5; // Заглушка
        }, 0) / filaments.length
      : 0;

  return (
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
      <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-8 border border-white/20 shadow-xl">
        <div className="flex flex-col md:flex-row items-start md:items-center gap-6">
          {/* Логотип (если есть) */}
          {brand.logo_url ? (
            <img
              src={brand.logo_url}
              alt={brand.name}
              className="w-24 h-24 object-contain rounded-xl bg-white/5 p-2"
            />
          ) : (
            <div className="w-24 h-24 flex items-center justify-center bg-purple-500/20 rounded-xl border border-purple-500/30">
              <Building2 className="w-12 h-12 text-purple-400" />
            </div>
          )}

          {/* Информация о бренде */}
          <div className="flex-1">
            <div className="flex items-center space-x-3 mb-3">
              <h1 className="text-3xl font-bold text-white">{brand.name}</h1>
              {brand.verified && (
                <span className="flex items-center space-x-1 px-3 py-1 bg-green-500/20 text-green-400 rounded-full border border-green-500/30">
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
              {avgRating > 0 && (
                <div className="flex items-center space-x-2 text-gray-300">
                  <Star className="w-5 h-5 text-yellow-400 fill-current" />
                  <span className="font-semibold text-white">{avgRating.toFixed(1)}</span>
                  <span>{t('brandDetailPage.avgRating')}</span>
                </div>
              )}
            </div>

            {/* Ссылки */}
            <div className="flex flex-wrap items-center gap-4">
              {brand.website && (
                <a
                  href={brand.website}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center space-x-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-all"
                >
                  <ExternalLink className="w-4 h-4" />
                  <span>{t('brandDetailPage.website')}</span>
                </a>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Фильтры и поиск */}
      <div className="bg-white/10 backdrop-blur-sm rounded-xl p-4 border border-white/20">
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
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredFilaments.map((filament) => (
            <div
              key={filament.id}
              onClick={() => navigate(`/filaments/${filament.id}`)}
              className="bg-white/10 backdrop-blur-sm rounded-xl p-6 border border-white/20 hover:bg-white/15 transition-all cursor-pointer group"
            >
              {/* Превью филамента */}
              <div className="flex items-center justify-center mb-4">
                <FilamentPreview
                  colorHex={filament.color_hex || '#FFFFFF'}
                  visualSettings={filament.visual_settings}
                  size="medium"
                />
              </div>

              {/* Название и тип */}
              <h3 className="text-lg font-bold text-white mb-2 group-hover:text-purple-300 transition-colors">
                {filament.name}
              </h3>
              <div className="flex items-center space-x-2 mb-4">
                <span className="px-2 py-1 bg-purple-500/20 text-purple-300 text-xs rounded-full border border-purple-500/30">
                  {filament.material_type}
                </span>
                {filament.color_name && (
                  <span className="text-sm text-gray-400">{filament.color_name}</span>
                )}
              </div>

              {/* Характеристики */}
              <div className="space-y-2 text-sm">
                {filament.diameter && (
                  <div className="flex items-center justify-between text-gray-300">
                    <span>{t('brandDetailPage.diameter')}</span>
                    <span className="text-white">{filament.diameter}mm</span>
                  </div>
                )}
                {filament.density && (
                  <div className="flex items-center justify-between text-gray-300">
                    <span>{t('brandDetailPage.density')}</span>
                    <span className="text-white">{filament.density}g/cm³</span>
                  </div>
                )}
                {filament.price_per_kg && (
                  <div className="flex items-center justify-between text-gray-300">
                    <span>{t('brandDetailPage.price')}</span>
                    <span className="text-green-400 font-semibold">
                      {Math.round(filament.price_per_kg)}{t('brandDetailPage.priceSuffix')}
                    </span>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

