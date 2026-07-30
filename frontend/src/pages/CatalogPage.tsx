/** Страница каталога материалов */

import { useState, useEffect, useMemo, useRef } from 'react';
import { useInfiniteQuery, useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useLocation } from 'react-router-dom';
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
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { filamentsAPI, brandsAPI, savedPresetsAPI, qrAPI, printersAPI, physicalPrintersAPI } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { currencySymbol } from '../utils/currency';
import { isPluginEmbed, notifyProfileChanged } from '../utils/pluginBridge';
import { Dropdown } from '../components/Dropdown';
import { FilamentPreview } from '../components/FilamentPreview';
import { NozzleRequirementBadge } from '../components/NozzleRequirementBadge';
import { useConfiguredNozzleHrc } from '../hooks/useConfiguredNozzleHrc';
import { useDebounce } from '../hooks/useDebounce';
import { SEOHead } from '../components/SEOHead';
import type { Filament } from '../types/api';
import type { AxiosError } from 'axios';

const CATALOG_PAGE_SIZE = 24;

export const CatalogPage: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState('');
  const debouncedSearchQuery = useDebounce(searchQuery.trim(), 250);
  const [_printerModel, _setPrinterModel] = useState('Ender 3 Pro');
  const [materialTypeFilter, setMaterialTypeFilter] = useState<string | null>(null);
  const [brandFilter, setBrandFilter] = useState<number | null>(null);
  const [brandSearch, setBrandSearch] = useState('');
  const debouncedBrandSearch = useDebounce(brandSearch.trim(), 250);
  const [printerFilter, setPrinterFilter] = useState<number | null>(null);
  const [printerSearch, setPrinterSearch] = useState('');
  const configuredNozzleHrc = useConfiguredNozzleHrc();
  const [selectedFilament, _setSelectedFilament] = useState<number | null>(null);
  const [showQR, setShowQR] = useState<number | null>(null);
  
  // Загружаем список сохранённых пресетов
  const { data: savedPresets } = useQuery({
    queryKey: ['saved-presets', user?.id],
    queryFn: () => savedPresetsAPI.list(),
    enabled: !!user?.id,
  });

  const savedPresetIds = new Set(savedPresets?.items.map(sp => sp.preset_id) || []);

  // The catalog holds hundreds of models, so the list stays short and typing
  // searches the rest on the server instead of scrolling.
  const { data: catalogPrinters } = useQuery({
    queryKey: ['printers', 'catalog-filter', printerSearch],
    queryFn: () =>
      printersAPI.list({ active_only: true, size: 50, search: printerSearch || undefined }),
  });
  const { data: ownedPrinters } = useQuery({
    queryKey: ['physical-printers'],
    queryFn: physicalPrintersAPI.list,
    enabled: !!user,
  });

  const ownedPrinterIds = useMemo(
    () =>
      Array.from(
        new Set(
          (ownedPrinters ?? [])
            .map((printer) => printer.printer_id)
            .filter((id): id is number => id != null),
        ),
      ),
    [ownedPrinters],
  );

  // A person's own model is rarely on the first page of an alphabetical list,
  // so those are asked for by id rather than hoped for.
  const { data: ownedModels } = useQuery({
    queryKey: ['printers', 'owned-models', ownedPrinterIds],
    queryFn: () => printersAPI.list({ active_only: true, ids: ownedPrinterIds }),
    enabled: ownedPrinterIds.length > 0,
  });

  // A person looks for their own machine first, so those lead under a heading.
  const printerOptions = useMemo(() => {
    const owned = new Set(ownedPrinterIds);
    const byId = new Map<number, { value: number; label: string; owned: boolean }>();
    for (const printer of [...(ownedModels?.items ?? []), ...(catalogPrinters?.items ?? [])]) {
      if (!byId.has(printer.id)) {
        byId.set(printer.id, {
          value: printer.id,
          label: printer.name,
          owned: owned.has(printer.id),
        });
      }
    }
    return Array.from(byId.values())
      .sort((a, b) => Number(b.owned) - Number(a.owned) || a.label.localeCompare(b.label))
      .map(({ value, label, owned: isOwned }) => ({
        value,
        label,
        group: isOwned
          ? t('catalogPage.myPrintersGroup')
          : t('catalogPage.allPrintersGroup'),
      }));
  }, [catalogPrinters, ownedModels, ownedPrinterIds, t]);


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

  const handleSavePreset = (presetId: number) => {
    // Signed-out: route into sign-in instead of firing the save (which 401s
    // and surfaces a misleading "failed to add preset" error). Layout opens
    // AuthModal on ?auth=login.
    if (!user) {
      const params = new URLSearchParams(location.search);
      params.set('auth', 'login');
      navigate({ search: params.toString() });
      return;
    }
    savePresetMutation.mutate(presetId);
  };

  // Загружаем материалы
  const {
    data: filamentsData,
    isLoading: isLoadingFilaments,
    isFetching: isFetchingFilaments,
    isFetchingNextPage,
    isFetchNextPageError,
    fetchNextPage,
    hasNextPage,
    error: filamentsError,
  } = useInfiniteQuery({
    queryKey: [
      'filaments',
      {
        search: debouncedSearchQuery,
        material_type: materialTypeFilter,
        brand_id: brandFilter,
        printer_id: printerFilter,
      },
    ],
    queryFn: ({ pageParam }) =>
      filamentsAPI.list({
        active_only: true,
        search: debouncedSearchQuery || undefined,
        material_type: materialTypeFilter || undefined,
        brand_id: brandFilter || undefined,
        printer_id: printerFilter || undefined,
        page: pageParam,
        size: CATALOG_PAGE_SIZE,
      }),
    initialPageParam: 1,
    getNextPageParam: (lastPage) =>
      lastPage.page < lastPage.pages ? lastPage.page + 1 : undefined,
    placeholderData: (previousData) => previousData,
  });

  const printerMatchedIds = useMemo(
    () =>
      new Set(
        filamentsData?.pages.flatMap((catalogPage) => catalogPage.printer_matched_ids ?? []) ?? [],
      ),
    [filamentsData],
  );

  // Загружаем бренды для фильтра.
  const { data: brandsData } = useQuery({
    queryKey: ['brands', 'catalog-filter', debouncedBrandSearch],
    queryFn: () => brandsAPI.list({
      active_only: true,
      page: 1,
      size: 50,
      search: debouncedBrandSearch || undefined,
    }),
  });
  const { data: selectedBrand } = useQuery({
    queryKey: ['brand', brandFilter],
    queryFn: () => brandsAPI.get(brandFilter as number),
    enabled: brandFilter !== null,
  });
  const brandOptions = useMemo(() => {
    const byId = new Map<number, string>();
    if (selectedBrand) {
      byId.set(selectedBrand.id, selectedBrand.name);
    }
    for (const brand of brandsData?.items ?? []) {
      byId.set(brand.id, brand.name);
    }
    return Array.from(byId, ([value, label]) => ({ value, label }));
  }, [brandsData, selectedBrand]);

  const { data: materialTypes = [] } = useQuery({
    queryKey: ['filament-material-types'],
    queryFn: filamentsAPI.getMaterialTypes,
  });

  const filaments = useMemo(
    () => filamentsData?.pages.flatMap((catalogPage) => catalogPage.items) ?? [],
    [filamentsData],
  );
  const total = filamentsData?.pages[0]?.total ?? 0;
  const loadMoreRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const target = loadMoreRef.current;
    if (!target || !hasNextPage || typeof IntersectionObserver === 'undefined') {
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !isFetchingFilaments) {
          void fetchNextPage();
        }
      },
      { rootMargin: '400px 0px' },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [fetchNextPage, hasNextPage, isFetchingFilaments]);

  if (isLoadingFilaments) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-white text-xl">{t('catalogPage.loading')}</div>
      </div>
    );
  }

  if (filamentsError && !filamentsData) {
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

          {/* Filters - stack on mobile, row on desktop. */}
          <div className="grid gap-2 sm:gap-4 grid-cols-2 sm:grid-cols-3">
            <Dropdown
              value={materialTypeFilter || ''}
              onChange={(val) => {
                setMaterialTypeFilter(val === '' ? null : (val as string));
              }}
              options={[
                { value: '', label: t('catalogPage.allTypes') },
                ...materialTypes.map((type) => ({ value: type, label: type })),
              ]}
              placeholder={t('catalogPage.allTypes')}
            />
            <Dropdown
              value={brandFilter || ''}
              onChange={(val) => {
                setBrandFilter(val === '' ? null : Number(val));
              }}
              options={[
                { value: '', label: t('catalogPage.allBrands') },
                ...brandOptions,
              ]}
              placeholder={t('catalogPage.allBrands')}
              filterable
              filterValue={brandSearch}
              onFilterChange={setBrandSearch}
            />
            <Dropdown
              value={printerFilter ?? ''}
              onChange={(value) => {
                setPrinterFilter(value === '' ? null : Number(value));
              }}
              options={printerOptions}
              placeholder={t('catalogPage.allPrinters')}
              filterable
              filterValue={printerSearch}
              onFilterChange={setPrinterSearch}
            />
          </div>
        </div>
      </div>

      {/* Material Grid */}
      <div
        className={`grid grid-cols-1 lg:grid-cols-2 gap-6 transition-opacity ${
          isFetchingFilaments ? 'opacity-60' : 'opacity-100'
        }`}
        aria-busy={isFetchingFilaments}
      >
        {filaments.map((filament) => (
          <MaterialCard
            key={filament.id}
            filament={filament}
            isSelected={selectedFilament === filament.id}
            onSelect={handleSavePreset}
            onShowQR={() => setShowQR(showQR === filament.id ? null : filament.id)}
            showQR={showQR === filament.id}
            onClick={() => navigate(`/filaments/${filament.id}`)}
            savedPresetIds={savedPresetIds}
            configuredNozzleHrc={configuredNozzleHrc}
            fitsPrinter={printerMatchedIds.has(filament.id)}
          />
        ))}
      </div>

      {filaments.length === 0 && (
        <div className="text-center py-12">
          <Package className="w-16 h-16 text-gray-400 mx-auto mb-4" />
          <p className="text-gray-400 text-xl">{t('catalogPage.noResults')}</p>
        </div>
      )}

      {total > 0 && (
        <footer
          ref={loadMoreRef}
          className="flex flex-col items-center gap-3 rounded-xl border border-white/10 bg-white/[0.04] px-4 py-4"
        >
          <p className="text-sm text-gray-400">
            {t('catalogPage.resultsRange', {
              start: 1,
              end: filaments.length,
              total,
            })}
          </p>
          {hasNextPage && (
            <button
              type="button"
              onClick={() => void fetchNextPage()}
              disabled={isFetchingNextPage}
              className="inline-flex min-h-10 items-center justify-center rounded-xl border border-purple-400/25 bg-purple-500/10 px-5 py-2 text-sm font-medium text-purple-100 transition hover:border-purple-300/40 hover:bg-purple-500/20 disabled:cursor-wait disabled:opacity-60"
            >
              {isFetchingNextPage
                ? t('catalogPage.loadingMore')
                : t('catalogPage.loadMore')}
            </button>
          )}
          {isFetchNextPageError && (
            <p className="text-sm text-rose-300" role="alert">
              {t('catalogPage.loadMoreError')}
            </p>
          )}
          {!hasNextPage && filaments.length > CATALOG_PAGE_SIZE && (
            <p className="text-xs text-gray-500">{t('catalogPage.endOfCatalog')}</p>
          )}
        </footer>
      )}
      </div>
    </>
  );
};

interface MaterialCardProps {
  filament: Filament;
  isSelected: boolean;
  onSelect: (presetId: number) => void;
  onShowQR: () => void;
  showQR: boolean;
  onClick: () => void;
  savedPresetIds: Set<number>;
  configuredNozzleHrc: number | null;
  fitsPrinter?: boolean;
}

const MaterialCard: React.FC<MaterialCardProps> = ({
  filament,
  isSelected,
  onSelect,
  onShowQR,
  showQR,
  onClick,
  savedPresetIds,
  configuredNozzleHrc,
  fitsPrinter = false,
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
  const brand = filament.brand_name && filament.brand_slug
    ? {
        name: filament.brand_name,
        slug: filament.brand_slug,
        verified: filament.brand_verified,
      }
    : null;

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
                    navigate(`/brands/${brand.slug}`);
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
              {fitsPrinter && (
                <span className="px-2 py-0.5 sm:py-1 bg-emerald-500/15 text-emerald-300 text-xs rounded-full border border-emerald-500/30">
                  {t('catalogPage.fitsPrinter')}
                </span>
              )}
              {filament.availability && filament.availability !== 'available' && (
                <span className="px-2 py-0.5 sm:py-1 bg-amber-500/20 text-amber-300 text-xs rounded-full border border-amber-500/30">
                  {t(`createFilament.availability.${filament.availability}`)}
                </span>
              )}
              <NozzleRequirementBadge
                requiredHrc={filament.required_nozzle_hrc}
                configuredHrc={configuredNozzleHrc}
                compact
              />

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
        {filament.ral_code && (
          <div className="rounded-full border border-white/10 bg-white/5 px-2 py-0.5 font-mono text-[10px] font-semibold text-gray-200 sm:px-3 sm:py-1 sm:text-xs">
            RAL {filament.ral_code}
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
              <button
                onClick={handleSavePreset}
                className="px-3 sm:px-4 py-1.5 sm:py-2 rounded-lg border border-white/20 text-xs sm:text-sm text-white hover:bg-white/10 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
                disabled={isPresetSaved}
              >
                {isPresetSaved ? '✓' : '+'}
                <span className="hidden sm:inline ml-1">
                  {isPresetSaved
                    ? t('catalogPage.addedToProfile')
                    : isPluginEmbed()
                      ? t('catalogPage.importToOrca')
                      : t('catalogPage.addToProfile')}
                </span>
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

