/** Страница каталога материалов */

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Search,
  Package,
  Thermometer,
  Ruler,
  QrCode,
  Shield,
  ChevronLeft,
  ChevronRight,
  Droplet,
  Palette,
  Fan,
  Printer,
  Download,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { filamentsAPI, brandsAPI, savedPresetsAPI, qrAPI } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { currencySymbol } from '../utils/currency';
import { isPluginEmbed, importPresetToPlugin, notifyProfileChanged } from '../utils/pluginBridge';
import { Dropdown } from '../components/Dropdown';
import { FilamentPreview } from '../components/FilamentPreview';
import { RecommendedForPrinterSection } from '../components/RecommendedForPrinterSection';
import { SEOHead } from '../components/SEOHead';
import type { Filament } from '../types/api';
import type { AxiosError } from 'axios';

export const CatalogPage: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState('');
  const [_printerModel, _setPrinterModel] = useState('Ender 3 Pro');
  const [materialTypeFilter, setMaterialTypeFilter] = useState<string | null>(null);
  const [brandFilter, setBrandFilter] = useState<number | null>(null);
  const [selectedFilament, _setSelectedFilament] = useState<number | null>(null);
  const [showQR, setShowQR] = useState<number | null>(null);
  
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
        throw new Error(t('catalogPage.errorLoginRequired'));
      }
      return savedPresetsAPI.save(presetId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saved-presets'] });
      queryClient.invalidateQueries({ queryKey: ['saved-presets-details'] });
      queryClient.invalidateQueries({ queryKey: ['user-presets'] });
      // Refresh the plugin toolbar count and auto-sync the new preset into the slicer.
      queryClient.invalidateQueries({ queryKey: ['presets-stats'] });
      notifyProfileChanged();
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      console.error('Error saving preset:', error);
      alert(translateApiError(t, error.response?.data?.detail, t('catalogPage.errorSavePreset')));
    },
  });

  // Загружаем материалы
  const {
    data: filamentsData,
    isLoading: isLoadingFilaments,
    error: filamentsError,
  } = useQuery({
    queryKey: ['filaments', { material_type: materialTypeFilter, brand_id: brandFilter }],
    queryFn: () =>
      filamentsAPI.list({
        active_only: true,
        material_type: materialTypeFilter || undefined,
        brand_id: brandFilter || undefined,
        page: 1,
        size: 100,
      }),
  });

  // Загружаем бренды для фильтра и отображения
  const { data: brandsData } = useQuery({
    queryKey: ['brands'],
    queryFn: () => brandsAPI.list({ active_only: true, page: 1, size: 100 }),
  });

  // Создаем мапу брендов для быстрого доступа
  const brandsMap = new Map(brandsData?.items.map((b) => [b.id, b]) || []);

  // Фильтруем материалы по поисковому запросу
  const filteredFilaments = filamentsData?.items.filter((filament) => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      filament.name.toLowerCase().includes(query) ||
      filament.material_type.toLowerCase().includes(query) ||
      filament.color_name?.toLowerCase().includes(query)
    );
  }) || [];

  // Получаем уникальные типы материалов для фильтра
  const materialTypes = Array.from(
    new Set(filamentsData?.items.map((f) => f.material_type) || [])
  ).sort();

  if (isLoadingFilaments) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-white text-xl">{t('catalogPage.loading')}</div>
      </div>
    );
  }

  if (filamentsError) {
    // В embed-режиме (WebView плагина, DevTools нет) показываем техдетали ошибки.
    const axiosError = filamentsError as AxiosError<{ detail?: unknown }>;
    let responseDetail = '';
    try {
      responseDetail = JSON.stringify(axiosError.response?.data ?? null);
    } catch {
      responseDetail = String(axiosError.response?.data);
    }
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] gap-4 px-4">
        <div className="text-red-400 text-xl">{t('catalogPage.error')}</div>
        {isPluginEmbed() && (
          <pre className="max-w-full overflow-x-auto whitespace-pre-wrap break-all text-xs font-mono text-red-300 bg-black/40 border border-red-500/40 rounded-lg p-3">
            {[
              `message: ${axiosError.message}`,
              `code: ${axiosError.code ?? '-'}`,
              `status: ${axiosError.response?.status ?? '-'}`,
              `url: ${axiosError.config?.baseURL ?? ''}${axiosError.config?.url ?? '-'}`,
              `response: ${responseDetail}`,
            ].join('\n')}
          </pre>
        )}
      </div>
    );
  }

  return (
    <>
      <SEOHead
        title={t('catalogPage.seoTitle')}
        description={t('catalogPage.seoDescription')}
        keywords={t('catalogPage.seoKeywords')}
        url="/"
        type="website"
        allowAI={true}
      />
      <div className="space-y-6">
        {/* Hero Section — показываем только гостю; залогиненному сразу каталог.
            Подзаголовок скрыт на мобиле, отступы компактнее (не съедать экран). */}
        {!user && (
          <div className="text-center mb-4 sm:mb-6">
            <h2 className="text-xl sm:text-3xl md:text-4xl font-bold text-white mb-2 sm:mb-3 px-2">
              {t('catalogPage.heroTitle')}
            </h2>
            <p className="hidden sm:block text-base sm:text-lg md:text-xl text-gray-300 max-w-3xl mx-auto px-2">
              {t('catalogPage.heroSubtitle')}
            </p>
          </div>
        )}

      {/* Search Bar */}
      <div className="bg-white/10 backdrop-blur-sm rounded-xl sm:rounded-2xl p-4 sm:p-6 border border-white/20 shadow-xl">
        <div className="flex flex-col gap-3 sm:gap-4">
          {/* Search Input */}
          <div className="relative">
            <Search className="absolute left-3 sm:left-4 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
            <input
              type="text"
              placeholder={t('catalogPage.searchPlaceholder')}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 sm:pl-12 pr-4 py-3 sm:py-4 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all text-sm sm:text-base"
            />
          </div>

          {/* Filters - stack on mobile, row on desktop.
              Третьей кнопкой — компактный CTA выбора принтера (только залогиненным без printer_id). */}
          <div className={`grid gap-2 sm:gap-4 ${user && !user.printer_id ? 'grid-cols-2 sm:grid-cols-3' : 'grid-cols-2'}`}>
            <Dropdown
              value={materialTypeFilter || ''}
              onChange={(val) => setMaterialTypeFilter(val === '' ? null : (val as string))}
              options={[
                { value: '', label: t('catalogPage.allTypes') },
                ...materialTypes.map((type) => ({ value: type, label: type })),
              ]}
              placeholder={t('catalogPage.allTypes')}
            />
            <Dropdown
              value={brandFilter || ''}
              onChange={(val) => setBrandFilter(val === '' ? null : Number(val))}
              options={[
                { value: '', label: t('catalogPage.allBrands') },
                ...(brandsData?.items.map((brand) => ({ value: brand.id, label: brand.name })) || []),
              ]}
              placeholder={t('catalogPage.allBrands')}
            />
            {user && !user.printer_id && (
              <button
                type="button"
                onClick={() => navigate('/profile', { state: { tab: 'settings' } })}
                title={t('recommendedForPrinter.ctaText')}
                className="flex items-center justify-center gap-2 px-3 sm:px-4 py-3 rounded-xl bg-white/10 border border-white/20 text-sm text-gray-200 hover:bg-white/15 hover:text-white transition-all"
              >
                <Printer className="w-4 h-4 text-purple-300 flex-shrink-0" />
                <span className="truncate">{t('recommendedForPrinter.ctaTitle')}</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Рекомендации под принтер пользователя (над основным гридом) */}
      <RecommendedForPrinterSection
        savedPresetIds={savedPresetIds}
        onSavePreset={(presetId) => savePresetMutation.mutate(presetId)}
      />

      {/* Material Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {filteredFilaments.map((filament) => (
          <MaterialCard
            key={filament.id}
            filament={filament}
            brand={brandsMap.get(filament.brand_id)}
            isSelected={selectedFilament === filament.id}
            onSelect={(presetId) => savePresetMutation.mutate(presetId)}
            onShowQR={() => setShowQR(showQR === filament.id ? null : filament.id)}
            showQR={showQR === filament.id}
            onClick={() => navigate(`/filaments/${filament.id}`)}
            savedPresetIds={savedPresetIds}
          />
        ))}
      </div>

      {filteredFilaments.length === 0 && (
        <div className="text-center py-12">
          <Package className="w-16 h-16 text-gray-400 mx-auto mb-4" />
          <p className="text-gray-400 text-xl">{t('catalogPage.noResults')}</p>
        </div>
      )}
      </div>
    </>
  );
};

interface MaterialCardProps {
  filament: Filament;
  brand?: import('../types/api').Brand;
  isSelected: boolean;
  onSelect: (presetId: number) => void;
  onShowQR: () => void;
  showQR: boolean;
  onClick: () => void;
  savedPresetIds: Set<number>;
}

const MaterialCard: React.FC<MaterialCardProps> = ({
  filament,
  brand,
  isSelected,
  onSelect,
  onShowQR,
  showQR,
  onClick,
  savedPresetIds,
}) => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [currentPresetIndex, setCurrentPresetIndex] = useState(0);
  const presetSummaries = filament.preset_summaries && filament.preset_summaries.length > 0
    ? filament.preset_summaries
    : filament.official_preset
      ? [{ ...filament.official_preset }]
      : [];
  const hasCarousel = presetSummaries.length > 1;
  const currentPreset = presetSummaries[currentPresetIndex] ?? null;
  const isPresetSaved = currentPreset ? savedPresetIds.has(currentPreset.id) : false;

  useEffect(() => {
    setCurrentPresetIndex(0);
  }, [filament.id]);
  
  // УБРАЛИ загрузку пресетов и статистики в каталоге для оптимизации
  // Детальная информация загружается только на странице материала
  // Это решает проблему с сотнями запросов при загрузке каталога

  const handleCardClick = (e: React.MouseEvent) => {
    // Не открываем детальную страницу, если кликнули на кнопку или внутри кнопки
    const target = e.target as HTMLElement;
    if (target.closest('button')) {
      return;
    }
    onClick();
  };

  const canShowQR = Boolean(filament.qr_code && brand?.verified);

  const formatPresetValue = (value: number | null | undefined, suffix: string) => {
    if (value === null || value === undefined) return '—';
    return `${Math.round(value)}${suffix}`;
  };

  const formatFanSpeed = (value: number | null | undefined) => {
    if (value === null || value === undefined) return t('catalogPage.fanNo');
    const rounded = Math.round(value);
    return rounded > 0 ? `${rounded}%` : t('catalogPage.fanNo');
  };

  const formatFlowRate = (value: number | null | undefined) => {
    if (value === null || value === undefined) return '—';
    return `${Math.round(value)}%`;
  };

  const formatUpdatedAt = (value: string | null | undefined) => {
    if (!value) return '—';
    try {
      return new Date(value).toLocaleDateString('ru-RU');
    } catch {
      return '—';
    }
  };

  const getPresetTypeBadge = (presetType: string | undefined, isOfficial: boolean, isWeighted: boolean) => {
    if (presetType === 'official' || isOfficial) {
      return { label: t('catalogPage.badgeOfficial'), className: 'bg-green-500/20 text-green-200 border-green-500/30' };
    }
    if (presetType === 'weighted' || isWeighted) {
      return { label: t('catalogPage.badgeWeighted'), className: 'bg-yellow-500/20 text-yellow-200 border-yellow-500/30' };
    }
    return { label: t('catalogPage.badgeCommunity'), className: 'bg-blue-500/20 text-blue-200 border-blue-500/30' };
  };

  const handleSavePreset = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (currentPreset) {
      onSelect(currentPreset.id);
    }
  };

  const handleCyclePreset = (direction: 'prev' | 'next') => {
    if (!hasCarousel) return;
    const total = presetSummaries.length;
    setCurrentPresetIndex((prev) => {
      if (direction === 'prev') {
        return (prev - 1 + total) % total;
      }
      return (prev + 1) % total;
    });
  };

  const presetBadge = currentPreset ? getPresetTypeBadge(currentPreset.preset_type, currentPreset.is_official, currentPreset.is_weighted) : null;

  return (
    <div 
      onClick={handleCardClick}
      className="bg-white/10 backdrop-blur-sm rounded-xl sm:rounded-2xl p-4 sm:p-6 border border-white/20 hover:bg-white/15 transition-all duration-300 group shadow-xl cursor-pointer"
    >
      {/* Header с названием, ценой и рейтингом */}
      <div className="flex items-start justify-between mb-3 sm:mb-4">
        <div className="flex-1 min-w-0">
          {/* Mobile: Stack brand/name vertically, Desktop: inline */}
          <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3 mb-2">
            <div className="flex items-center gap-2 flex-wrap">
            {brand && (
              <>
                <span
                  onClick={(e) => {
                    e.stopPropagation();
                    navigate(`/brands/${brand.id}`);
                  }}
                    className={`${brand.verified ? "text-green-400" : "text-purple-300"} font-semibold hover:underline cursor-pointer transition-colors text-sm sm:text-base`}
                >
                  {brand.name}
                </span>
                {brand.verified && (
                    <Shield className="w-3.5 h-3.5 sm:w-4 sm:h-4 text-green-400"/>
                )}
              </>
            )}
            </div>
            <h3 className="min-w-0 text-lg sm:text-xl font-bold text-white group-hover:text-purple-300 transition-colors truncate">
              {filament.name}
            </h3>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <span className="px-2 py-0.5 sm:py-1 bg-purple-500/20 text-purple-300 text-xs rounded-full border border-purple-500/30">
                {filament.material_type}
              </span>
              {filament.availability && filament.availability !== 'available' && (
                <span className="px-2 py-0.5 sm:py-1 bg-amber-500/20 text-amber-300 text-xs rounded-full border border-amber-500/30">
                  {t(`createFilament.availability.${filament.availability}`)}
                </span>
              )}
              {(filament.color_hex || filament.visual_settings) && (
              <span className="inline-flex items-center justify-center w-16 sm:w-24">
                <div style={{ transform: 'scale(0.35)', transformOrigin: 'center center' }} className="sm:hidden">
                  <FilamentPreview
                    colorHex={filament.color_hex || '#FFFFFF'}
                    visualSettings={filament.visual_settings}
                    size="medium"
                  />
                </div>
                <div style={{ transform: 'scale(0.45)', transformOrigin: 'center center' }} className="hidden sm:block">
                    <FilamentPreview
                      colorHex={filament.color_hex || '#FFFFFF'}
                      visualSettings={filament.visual_settings}
                      size="medium"
                    />
                  </div>
                </span>
              )}
            </div>
        </div>
        {filament.price_hidden ? null : (filament.price_per_kg || filament.spool_weight) ? (
          <div className="text-right ml-2 sm:ml-4 flex-shrink-0">
            {filament.price_per_kg && filament.spool_weight && filament.spool_weight !== 1000 ? (
              <>
                <p className="text-xs sm:text-sm font-medium text-gray-300">
                  {Math.round((filament.price_per_kg * filament.spool_weight) / 1000)} {currencySymbol(filament.currency)}<span className="text-gray-400">/{Math.round(filament.spool_weight)} {t('catalogPage.units.g')}</span>
                </p>
                <p className="text-[10px] sm:text-xs text-gray-500">
                  ≈ {Math.round(filament.price_per_kg)} {currencySymbol(filament.currency)}/{t('catalogPage.units.kg')}
                </p>
              </>
            ) : filament.price_per_kg ? (
              <p className="text-xs sm:text-sm font-medium text-gray-300">
                {Math.round(filament.price_per_kg)} {currencySymbol(filament.currency)}<span className="text-gray-400">/{t('catalogPage.units.kg')}</span>
              </p>
            ) : (
              <p className="text-xs sm:text-sm text-gray-400">{Math.round(filament.spool_weight!)} {t('catalogPage.units.g')}</p>
            )}
          </div>
        ) : null}
      </div>

      {/* Детали материала в компактном виде */}
      <div className="mb-3 sm:mb-4 flex flex-wrap items-center gap-2 sm:gap-4 text-xs text-gray-300">
        {filament.diameter && (
          <div className="flex items-center gap-1 bg-white/5 border border-white/10 rounded-full px-2 sm:px-3 py-0.5 sm:py-1">
            <Ruler className="w-3 h-3 sm:w-3.5 sm:h-3.5 text-purple-300" />
            <span className="hidden sm:inline uppercase tracking-wide text-[11px]">{t('catalogPage.diameter')}</span>
            <span className="text-white font-semibold text-[10px] sm:text-xs">{filament.diameter} {t('catalogPage.units.mm')}</span>
          </div>
        )}
        {filament.density && (
          <div className="flex items-center gap-1 bg-white/5 border border-white/10 rounded-full px-2 sm:px-3 py-0.5 sm:py-1">
            <Droplet className="w-3 h-3 sm:w-3.5 sm:h-3.5 text-blue-300" />
            <span className="hidden sm:inline uppercase tracking-wide text-[11px]">{t('catalogPage.density')}</span>
            <span className="text-white font-semibold text-[10px] sm:text-xs">{filament.density} {t('catalogPage.units.gcm3')}</span>
          </div>
        )}
        {filament.color_name && (
          <div className="flex items-center gap-1 sm:gap-2 bg-white/5 border border-white/10 rounded-full px-2 sm:px-3 py-0.5 sm:py-1">
            <Palette className="w-3 h-3 sm:w-3.5 sm:h-3.5 text-amber-300" />
            <span className="text-white font-semibold text-[10px] sm:text-xs truncate max-w-[80px] sm:max-w-[220px]">{filament.color_name}</span>
          </div>
        )}
      </div>

      {/* Пресеты и детальная информация загружаются только на странице материала для оптимизации */}
      {currentPreset && (
        <div className="mt-4 sm:mt-6 bg-white/5 border border-white/10 rounded-lg sm:rounded-xl p-3 sm:p-5 space-y-3 sm:space-y-4">
          {/* Header: Badge, Name, Date */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 sm:gap-3">
            <div className="flex items-center gap-2 text-xs sm:text-sm text-gray-300 flex-wrap">
              {presetBadge && (
                <span className={`px-2 py-0.5 sm:py-1 text-[10px] sm:text-xs rounded-full border ${presetBadge.className}`}>
                  {presetBadge.label}
                </span>
              )}
              <h4 className="text-sm sm:text-base font-semibold text-white truncate max-w-[150px] sm:max-w-[280px]">{currentPreset.name}</h4>
              <span className="text-gray-400 text-[10px] sm:text-xs hidden sm:inline">· {t('catalogPage.updatedAt')} {formatUpdatedAt(currentPreset.updated_at)}</span>
            </div>
            <div className="flex items-center gap-2 sm:gap-3 text-[10px] sm:text-sm text-gray-300">
              <span>
                <span className="text-white font-semibold">
                  ★ {currentPreset.rating ? currentPreset.rating.toFixed(1) : '—'}
                </span>
              </span>
              <span>
                <span className="text-white font-semibold">
                  ✓ {currentPreset.success_rate ? `${currentPreset.success_rate.toFixed(0)}%` : '—'}
                </span>
              </span>
            </div>
          </div>

          {/* Params Grid + Actions */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div className="grid grid-cols-4 gap-2 sm:gap-3 text-[10px] sm:text-xs">
              <div className="text-center flex flex-col items-center">
                <Thermometer className="w-3 h-3 sm:w-3.5 sm:h-3.5 text-orange-300 mb-0.5" />
                <div className="text-white font-semibold">
                  {formatPresetValue(currentPreset.extruder_temp, '°')}
                </div>
              </div>
              <div className="text-center flex flex-col items-center">
                <Thermometer className="w-3 h-3 sm:w-3.5 sm:h-3.5 text-blue-300 mb-0.5" />
                <div className="text-white font-semibold">
                  {formatPresetValue(currentPreset.bed_temp, '°')}
                </div>
              </div>
              <div className="text-center flex flex-col items-center">
                <Fan className="w-3 h-3 sm:w-3.5 sm:h-3.5 text-sky-300 mb-0.5" />
                <div className="text-white font-semibold">
                  {formatFanSpeed(currentPreset.fan_speed)}
                </div>
              </div>
              <div className="text-center flex flex-col items-center">
                <Droplet className="w-3 h-3 sm:w-3.5 sm:h-3.5 text-emerald-300 mb-0.5" />
                <div className="text-white font-semibold">
                  {formatFlowRate(currentPreset.flow_rate)}
                </div>
              </div>
            </div>
            <div className="flex items-center justify-between sm:justify-end gap-2">
              {hasCarousel && (
                <div className="flex items-center gap-1 sm:gap-2">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleCyclePreset('prev');
                    }}
                    className="p-1.5 sm:p-2 rounded-full border border-white/20 text-white hover:bg-white/10 transition-colors"
                  >
                    <ChevronLeft className="w-3 h-3 sm:w-4 sm:h-4" />
                  </button>
                  <span className="text-[10px] sm:text-xs text-gray-400 min-w-[40px] text-center">
                    {currentPresetIndex + 1}/{presetSummaries.length}
                  </span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleCyclePreset('next');
                    }}
                    className="p-1.5 sm:p-2 rounded-full border border-white/20 text-white hover:bg-white/10 transition-colors"
                  >
                    <ChevronRight className="w-3 h-3 sm:w-4 sm:h-4" />
                  </button>
                </div>
              )}
              {isPluginEmbed() && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    importPresetToPlugin(currentPreset.id);
                  }}
                  title={t('catalogPage.importToOrcaTitle')}
                  className="px-3 sm:px-4 py-1.5 sm:py-2 rounded-lg border border-purple-400/40 bg-purple-500/20 text-xs sm:text-sm text-purple-100 hover:bg-purple-500/30 transition-colors"
                >
                  <Download className="w-3.5 h-3.5 inline sm:mr-1" />
                  <span className="hidden sm:inline">{t('catalogPage.importToOrca')}</span>
                </button>
              )}
              <button
                onClick={handleSavePreset}
                className="px-3 sm:px-4 py-1.5 sm:py-2 rounded-lg border border-white/20 text-xs sm:text-sm text-white hover:bg-white/10 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                disabled={isPresetSaved}
              >
                {isPresetSaved ? '✓' : '+'}
                <span className="hidden sm:inline ml-1">{isPresetSaved ? t('catalogPage.addedToProfile') : t('catalogPage.addToProfile')}</span>
              </button>
            </div>
          </div>
        </div>
      )}
      
      {/* Actions */}
      <div className="flex space-x-3 mt-4">
        {canShowQR && (
          <button
            onClick={onShowQR}
            className="px-4 py-3 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all border border-white/20"
          >
            <QrCode className="w-5 h-5" />
          </button>
        )}
      </div>

      {/* QR Code */}
      {canShowQR && showQR && (
        <div className="mt-4 p-4 bg-white/5 rounded-xl border border-white/10">
          <div className="text-center">
            <img
              src={qrAPI.getQRCodeURL(filament.id, 200)}
              alt={`QR ${filament.name}`}
              className="w-48 h-48 mx-auto mb-3 rounded-lg bg-white p-2"
            />
            <p className="text-gray-300 text-sm font-medium mb-1">{t('catalogPage.qrCode')} {filament.qr_code}</p>
            <p className="text-gray-400 text-xs">{t('catalogPage.qrScanHint')}</p>
            <p className="text-gray-500 text-xs mt-1">
              {t('catalogPage.qrScans')} {filament.scans_count || 0}
            </p>
          </div>
        </div>
      )}
    </div>
  );
};

