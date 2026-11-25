/** Страница бренда с карточкой и списком филаментов */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import {
  Building2,
  Shield,
  Package,
  Star,
  ArrowLeft,
  Search,
  Rows3,
  Layers,
  Tags,
} from 'lucide-react';
import { brandsAPI, filamentsAPI, filamentLinesAPI, filamentReviewsAPI } from '../api/client';
import type { Filament } from '../types/api';
import { useGuestCountryGuess } from '../hooks/useGuestCountryGuess';
import { useReaderCountry } from '../hooks/useReaderCountry';
import { GENERAL_MARKET, brandMarketCountry, parseMarketChoice } from '../utils/brandMarket';
import { countryName } from '../utils/countries';
import { useLoadMoreOnScroll } from '../hooks/useLoadMoreOnScroll';
import { useStoredUiChoice } from '../hooks/useStoredUiChoice';
import { useAuth } from '../contexts/AuthContext';
import { SegmentedToggle } from '../components/SegmentedToggle';
import { Dropdown } from '../components/Dropdown';
import { SEOHead } from '../components/SEOHead';
import { SocialIcon } from '../components/socialIcons';
import { BrandLogoFrame } from '../components/BrandLogoFrame';
import { OffscreenSection } from '../components/OffscreenSection';
import { FilamentPreview } from '../components/FilamentPreview';
import { FilamentHandlingBadges } from '../components/FilamentHandlingBadges';
import { NozzleRequirementBadge } from '../components/NozzleRequirementBadge';
import { ProductQrButton } from '../components/ProductQrButton';
import { externalUrl, externalUrlHost } from '../utils/externalUrl';
import { filamentPublicPath } from '../utils/catalogUrls';
import { OTHER_MATERIAL_BASE, materialBaseLabel } from '../utils/materialTypeGroups';
import { hasMetaNetworkLink } from '../utils/restrictedNetworks';

interface BrandFilamentCardProps {
  filament: Filament;
  onClick: () => void;
}

const BrandFilamentCard: React.FC<BrandFilamentCardProps> = ({ filament, onClick }) => (
  <div className="relative flex flex-col rounded-xl border border-white/15 bg-white/[0.07] shadow-lg backdrop-blur-sm">
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

    <div className={`mt-auto flex min-w-0 items-end justify-between gap-3 pt-3 ${filament.qr_code ? 'pr-12' : ''}`}>
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
  {filament.qr_code && (
    <ProductQrButton
      key={filament.id}
      filament={filament}
      iconOnly
      className="absolute bottom-4 right-4 z-10"
    />
  )}
  </div>
);

const BRAND_PAGE_SIZE = 48;
const CARD_GRID = 'grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4';
const BRAND_GROUPINGS = ['none', 'family', 'line'] as const;
type BrandGrouping = (typeof BRAND_GROUPINGS)[number];

/** The value a material is grouped under; "" for one without a family or line. */
function groupKey(filament: Filament, grouping: BrandGrouping): string {
  if (grouping === 'family') return filament.base_material_type ?? '';
  if (grouping === 'line') return filament.line_id != null ? String(filament.line_id) : '';
  return '';
}

/** Splits a page in server order into consecutive runs of one group. */
function groupRuns(items: Filament[], grouping: BrandGrouping) {
  const runs: { key: string; items: Filament[] }[] = [];
  for (const filament of items) {
    const key = groupKey(filament, grouping);
    const last = runs[runs.length - 1];
    if (last && last.key === key) last.items.push(filament);
    else runs.push({ key, items: [filament] });
  }
  return runs;
}

export const BrandDetailPage: React.FC = () => {
  const { t, i18n } = useTranslation();
  const { identifier } = useParams<{ identifier: string }>();
  const navigate = useNavigate();
  // The catalogue's brand view links here with the reader's search and family.
  const [searchParams, setSearchParams] = useSearchParams();
  const [searchQuery, setSearchQuery] = useState(() => searchParams.get('q') ?? '');
  const [materialTypeFilter, setMaterialTypeFilter] = useState<string | null>(
    () => searchParams.get('material') || null,
  );
  const [isBrandLogoVisible, setIsBrandLogoVisible] = useState(false);
  const readerCountry = useReaderCountry();
  const { user } = useAuth();
  // The brand's own description, links and shops follow the reader's country;
  // prices in the list below stay with the confirmed country of the profile.
  const guess = useGuestCountryGuess();
  const marketChoice = parseMarketChoice(searchParams.get('country'));
  const brandCountry = brandMarketCountry({
    choice: marketChoice,
    profileCountry: readerCountry,
    guessedCountry: guess.country,
  });
  const chooseMarket = (country: string) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      next.set('country', country);
      return next;
    }, { replace: true });
  };
  const [grouping, setGrouping] = useStoredUiChoice('brandPage.groupBy', user?.id, BRAND_GROUPINGS, 'none');

  // Загружаем бренд
  const {
    data: brand,
    isLoading: isLoadingBrand,
    error: brandError,
  } = useQuery({
    queryKey: ['brand', identifier, brandCountry],
    queryFn: () => brandsAPI.get(identifier!, undefined, brandCountry),
    enabled: !!identifier && (marketChoice !== null || guess.ready),
  });

  // Загружаем филаменты бренда
  // Grouping by line is offered only to a brand that has lines.
  const { data: brandLines = [] } = useQuery({
    queryKey: ['filament-lines', brand?.id],
    queryFn: () => filamentLinesAPI.list(brand!.id),
    enabled: !!brand?.id,
  });
  const effectiveGrouping: BrandGrouping = grouping === 'line' && brandLines.length === 0 ? 'none' : grouping;

  const {
    data: filamentsData,
    isLoading: isLoadingFilaments,
    error: filamentsError,
    isFetching: isFetchingFilaments,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ['brand-filaments', brand?.id, searchQuery, materialTypeFilter, readerCountry, effectiveGrouping],
    queryFn: ({ pageParam }) =>
      filamentsAPI.list({
        page: pageParam,
        size: BRAND_PAGE_SIZE,
        brand_id: brand!.id,
        search: searchQuery || undefined,
        material_base: materialTypeFilter || undefined,
        country: readerCountry,
        group_by: effectiveGrouping === 'none' ? undefined : effectiveGrouping,
      }),
    initialPageParam: 1,
    getNextPageParam: (lastPage) => (lastPage.page < lastPage.pages ? lastPage.page + 1 : undefined),
    enabled: !!brand?.id,
  });

  // Families and the material count describe the whole brand, not the loaded part
  // or the family picked in the filter.
  const { data: brandSummary } = useQuery({
    queryKey: ['brand-filaments', 'summary', brand?.id],
    queryFn: () => filamentsAPI.list({ brand_id: brand!.id, group_by: 'brand', size: 1 }),
    enabled: !!brand?.id,
  });

  // One request for the brand's rating instead of one per listed material.
  const { data: brandRating } = useQuery({
    queryKey: ['brand-rating', brand?.id],
    queryFn: () => filamentReviewsAPI.getBrandStats(brand!.id),
    enabled: !!brand?.id,
  });

  const loadMoreRef = useLoadMoreOnScroll<HTMLDivElement>({
    hasNextPage,
    isFetching: isFetchingFilaments,
    fetchNextPage,
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

  const filaments = (filamentsData?.pages ?? []).flatMap((page) => page.items);
  const brandGroup = brandSummary?.brand_groups?.[0];
  // Фильтр по семейству: PLA показывает и PLA+, и PLA SILK.
  const materialFamilies = Array.from(
    new Set([
      ...(brandGroup?.families ?? []).map((family) => family.base ?? OTHER_MATERIAL_BASE),
      ...(materialTypeFilter ? [materialTypeFilter] : []),
    ])
  ).sort((a, b) => Number(a === OTHER_MATERIAL_BASE) - Number(b === OTHER_MATERIAL_BASE) || a.localeCompare(b));


  // Вычисляем статистику
  const totalFilaments = brandGroup?.materials_count ?? filamentsData?.pages[0]?.total ?? 0;
  const avgRating = brandRating?.avg_rating ?? null;

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

            {(brand.available_markets?.length ?? 0) > 0 && (
              <div className="mb-4 flex flex-wrap items-center gap-2 text-sm" role="group" aria-label={t('brandDetailPage.marketLabel')}>
                <span className="text-gray-400">{t('brandDetailPage.marketLabel')}</span>
                {[GENERAL_MARKET, ...brand.available_markets!].map((market) => {
                  const selected = market === (brand.market_country ?? GENERAL_MARKET);
                  return (
                    <button
                      key={market}
                      type="button"
                      aria-pressed={selected}
                      onClick={() => chooseMarket(market)}
                      className={`rounded-full border px-3 py-1 transition-colors ${
                        selected
                          ? 'border-purple-400/60 bg-purple-500/25 text-white'
                          : 'border-white/15 bg-white/5 text-gray-300 hover:bg-white/10'
                      }`}
                    >
                      {market === GENERAL_MARKET
                        ? t('brandDetailPage.marketGeneral')
                        : countryName(market, i18n.language)}
                    </button>
                  );
                })}
              </div>
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
                ...materialFamilies.map((base) => ({
                  value: base,
                  label: materialBaseLabel(t, base === OTHER_MATERIAL_BASE ? null : base),
                })),
              ]}
              onChange={(val) => setMaterialTypeFilter(val === '' ? null : String(val))}
              placeholder={t('brandDetailPage.materialType')}
            />
          </div>
          <SegmentedToggle
            value={effectiveGrouping}
            onChange={setGrouping}
            options={[
              { value: 'none', label: t('brandDetailPage.groupNone'), icon: Rows3 },
              { value: 'family', label: t('brandDetailPage.groupFamily'), icon: Layers },
              ...(brandLines.length > 0
                ? [{ value: 'line' as const, label: t('brandDetailPage.groupLine'), icon: Tags }]
                : []),
            ]}
            ariaLabel={t('brandDetailPage.groupBy')}
            showLabels
            labelClassName="hidden lg:inline"
            className="shrink-0 self-start md:self-auto"
          />
        </div>
      </div>

      {/* Список филаментов */}
      {isLoadingFilaments ? (
        <div className="text-center py-12 text-gray-400">{t('brandDetailPage.loadingFilaments')}</div>
      ) : filamentsError ? (
        <div className="text-center py-12 text-red-400">{t('brandDetailPage.errorLoadingFilaments')}</div>
      ) : filaments.length === 0 ? (
        <div className="text-center py-12">
          <Package className="w-16 h-16 text-gray-400 mx-auto mb-4" />
          <p className="text-gray-400 text-xl">{t('brandDetailPage.noFilamentsFound')}</p>
        </div>
      ) : (
        // Pages arrive in the server's order and a page far off screen drops its
        // cards, so a large brand neither reshuffles nor weighs on the browser.
        <div className="space-y-4">
          {(filamentsData?.pages ?? []).map((materialsPage, pageIndex) => (
            <OffscreenSection
              key={materialsPage.items[0]?.id ?? pageIndex}
              className={effectiveGrouping === 'none' ? CARD_GRID : 'space-y-4'}
            >
              {effectiveGrouping === 'none'
                ? materialsPage.items.map((filament) => (
                  <BrandFilamentCard
                    key={filament.id}
                    filament={filament}
                    onClick={() => navigate(filamentPublicPath(filament))}
                  />
                ))
                : groupRuns(materialsPage.items, effectiveGrouping).map((run, runIndex) => {
                  // A group continued from the previous page gets no second header.
                  const previousPage = filamentsData?.pages[pageIndex - 1];
                  const previousItem = previousPage?.items[previousPage.items.length - 1];
                  const continues = runIndex === 0 && previousItem != null
                    && groupKey(previousItem, effectiveGrouping) === run.key;
                  const first = run.items[0];
                  const title = effectiveGrouping === 'family'
                    ? materialBaseLabel(t, first.base_material_type ?? null)
                    : first.line_name ?? t('brandDetailPage.noLine');
                  return (
                    <section key={`${run.key}:${first.id}`} className="space-y-3">
                      {!continues && (
                        <h2 className="flex items-baseline gap-2 border-b border-white/15 pb-2 pt-2 text-lg font-semibold text-white">
                          {title}
                          <span className="text-sm font-normal text-gray-400">
                            {materialsPage.group_counts?.[run.key] ?? run.items.length}
                          </span>
                        </h2>
                      )}
                      <div className={CARD_GRID}>
                        {run.items.map((filament) => (
                          <BrandFilamentCard
                            key={filament.id}
                            filament={filament}
                            onClick={() => navigate(filamentPublicPath(filament))}
                          />
                        ))}
                      </div>
                    </section>
                  );
                })}
            </OffscreenSection>
          ))}
        </div>
      )}
      {hasNextPage && (
        <div ref={loadMoreRef} className="flex justify-center">
          <button
            type="button"
            onClick={() => void fetchNextPage()}
            disabled={isFetchingNextPage}
            className="inline-flex min-h-10 items-center justify-center rounded-xl border border-purple-400/25 bg-purple-500/10 px-5 py-2 text-sm font-medium text-purple-100 transition hover:border-purple-300/40 hover:bg-purple-500/20 disabled:cursor-wait disabled:opacity-60"
          >
            {isFetchingNextPage ? t('catalogPage.loadingMore') : t('catalogPage.loadMore')}
          </button>
        </div>
      )}
    </div>
    </>
  );
};
