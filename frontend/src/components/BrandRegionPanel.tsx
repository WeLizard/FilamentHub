/** Что представитель ведёт в своей стране, а что — общее для всех. */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Globe, MapPin, Lock } from 'lucide-react';

import { brandsAPI } from '../api/client';
import { countryName } from '../utils/countries';
import { translateApiError } from '../utils/translateApiError';
import { toast } from './Toast';
import type { Brand, BrandCountryCell } from '../types/api';
import type { AxiosError } from 'axios';

interface BrandRegionPanelProps {
  brand: Brand;
}

export const BrandRegionPanel: React.FC<BrandRegionPanelProps> = ({ brand }) => {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();
  const [activeCountry, setActiveCountry] = useState<string | null>(null);
  const [website, setWebsite] = useState('');

  const territories = useQuery({
    queryKey: ['brand-territories', brand.id],
    queryFn: () => brandsAPI.myTerritories(brand.id),
  });

  const cells = useQuery({
    queryKey: ['brand-country-cells', brand.id],
    queryFn: () => brandsAPI.countryCells(brand.id),
    enabled: (territories.data?.territories.length ?? 0) > 0,
  });

  const mine = territories.data?.territories ?? [];
  // Глобальная область покрывает любую страну, поэтому ей нужен выбор страны;
  // страновому представителю выбирать не из чего.
  const countries = mine.map((item) => item.country).filter((c): c is string => c !== null);
  const isGlobal = mine.some((item) => item.country === null);

  useEffect(() => {
    if (activeCountry === null && countries.length > 0) {
      setActiveCountry(countries[0]);
    }
  }, [countries, activeCountry]);

  const currentCell: BrandCountryCell | undefined = (cells.data ?? []).find(
    (cell) => cell.country === activeCountry,
  );

  useEffect(() => {
    setWebsite(currentCell?.website ?? '');
  }, [currentCell?.id, currentCell?.website]);

  const save = useMutation({
    mutationFn: async () => {
      if (!activeCountry) return;
      const payload = { website: website.trim() || null };
      if (currentCell) {
        return brandsAPI.updateCountryCell(brand.id, activeCountry, payload);
      }
      return brandsAPI.createCountryCell(brand.id, { country: activeCountry, ...payload });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['brand-country-cells', brand.id] });
      toast.success(t('brandRegion.saved'));
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      toast.error(translateApiError(t, error.response?.data?.detail, t('brandRegion.saveFailed')));
    },
  });

  if (territories.isLoading || mine.length === 0) {
    return null;
  }

  const areaLabel = isGlobal
    ? t('brandRegion.areaGlobal')
    : countries.map((code) => countryName(code, i18n.language)).join(', ');

  return (
    <div className="mt-6 space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <MapPin className="h-4 w-4 text-emerald-300" />
        <span className="text-sm text-gray-300">
          {t('brandRegion.yourArea')}: <span className="font-semibold text-white">{areaLabel}</span>
        </span>
      </div>

      {/* Первый слой: общий. Не «поле заблокировано», а «это ведёт вот кто». */}
      <section className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
        <div className="mb-3 flex items-center gap-2">
          <Globe className="h-4 w-4 text-gray-400" />
          <h3 className="font-semibold text-white">{t('brandRegion.commonTitle')}</h3>
          <Lock className="h-3.5 w-3.5 text-gray-500" />
        </div>
        <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-gray-400">{t('brandRegion.commonName')}</dt>
            <dd className="text-white">{brand.name}</dd>
          </div>
          <div>
            <dt className="text-gray-400">{t('brandRegion.commonWebsite')}</dt>
            <dd className="text-white">{brand.website || '—'}</dd>
          </div>
        </dl>
        <p className="mt-3 text-xs leading-5 text-gray-400">
          {territories.data?.common_managed_by
            ? t('brandRegion.commonManagedBy', { owner: territories.data.common_managed_by })
            : t('brandRegion.commonManagedByNobody')}
        </p>
      </section>

      {/* Второй слой: свой. Здесь можно всё. */}
      <section className="rounded-2xl border border-emerald-400/20 bg-emerald-400/[0.06] p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-semibold text-white">
            {activeCountry
              ? t('brandRegion.yoursTitle', { country: countryName(activeCountry, i18n.language) })
              : t('brandRegion.yoursTitleGlobal')}
          </h3>
          {countries.length > 1 && (
            <select
              value={activeCountry ?? ''}
              onChange={(e) => setActiveCountry(e.target.value)}
              className="rounded-lg border border-white/20 bg-white/10 px-3 py-1.5 text-sm text-white"
            >
              {countries.map((code) => (
                <option key={code} value={code} className="bg-gray-900">
                  {countryName(code, i18n.language)}
                </option>
              ))}
            </select>
          )}
        </div>

        {activeCountry ? (
          <>
            <label className="mb-1.5 block text-xs text-gray-300">
              {t('brandRegion.regionalWebsite')}
            </label>
            <input
              type="url"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
              placeholder={brand.website || 'https://example.ru'}
              className="w-full rounded-xl border border-white/20 bg-white/10 px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
            <p className="mt-1.5 text-xs leading-5 text-gray-400">{t('brandRegion.emptyMeansCommon')}</p>
            <button
              onClick={() => save.mutate()}
              disabled={save.isPending}
              className="mt-3 rounded-xl bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-emerald-700 disabled:opacity-50"
            >
              {save.isPending ? t('brandRegion.saving') : t('brandRegion.save')}
            </button>
          </>
        ) : (
          <p className="text-sm text-gray-300">{t('brandRegion.globalHasNoCell')}</p>
        )}
      </section>
    </div>
  );
};
