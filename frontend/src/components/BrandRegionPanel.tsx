/** Что представитель ведёт в своей стране на уровне самого бренда. */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Check, Pencil, X } from 'lucide-react';

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
  const [editing, setEditing] = useState<string | null>(null);
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

  const countries = (territories.data?.territories ?? [])
    .map((item) => item.country)
    .filter((code): code is string => code !== null);

  const cellFor = (country: string): BrandCountryCell | undefined =>
    (cells.data ?? []).find((cell) => cell.country === country);

  useEffect(() => {
    if (editing) {
      setWebsite(cellFor(editing)?.website ?? '');
    }
  }, [editing, cells.data]);

  const save = useMutation({
    mutationFn: async (country: string) => {
      const payload = { website: website.trim() || null };
      return cellFor(country)
        ? brandsAPI.updateCountryCell(brand.id, country, payload)
        : brandsAPI.createCountryCell(brand.id, { country, ...payload });
    },
    onSuccess: () => {
      setEditing(null);
      queryClient.invalidateQueries({ queryKey: ['brand-country-cells', brand.id] });
      toast.success(t('brandRegion.saved'));
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      toast.error(translateApiError(t, error.response?.data?.detail, t('brandRegion.saveFailed')));
    },
  });

  if (territories.isLoading || countries.length === 0) {
    return null;
  }

  return (
    <section className="rounded-2xl border border-white/10 bg-white/[0.04] p-5">
      <h4 className="font-semibold text-white">{t('brandRegion.title')}</h4>
      <p className="mt-1 text-xs leading-5 text-gray-400">{t('brandRegion.explained')}</p>

      <div className="mt-4 divide-y divide-white/10">
        {countries.map((code) => {
          const cell = cellFor(code);
          return (
            <div key={code} className="flex flex-wrap items-center gap-3 py-3">
              <span className="min-w-32 text-sm font-medium text-white">
                {countryName(code, i18n.language)}
              </span>

              {editing === code ? (
                <>
                  <input
                    type="url"
                    value={website}
                    onChange={(event) => setWebsite(event.target.value)}
                    placeholder={brand.website || 'https://example.ru'}
                    autoFocus
                    className="min-w-0 flex-1 rounded-lg border border-white/20 bg-white/10 px-3 py-1.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                  />
                  <button
                    type="button"
                    onClick={() => save.mutate(code)}
                    disabled={save.isPending}
                    className="rounded-lg bg-emerald-600 p-1.5 text-white transition hover:bg-emerald-700 disabled:opacity-50"
                    title={t('brandRegion.save')}
                  >
                    <Check className="h-4 w-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setEditing(null)}
                    className="rounded-lg border border-white/15 p-1.5 text-gray-300 transition hover:text-white"
                    title={t('brandRegion.cancel')}
                  >
                    <X className="h-4 w-4" />
                  </button>
                </>
              ) : (
                <>
                  <span className="min-w-0 flex-1 truncate text-sm text-gray-400">
                    {cell?.website || t('brandRegion.usesCommonSite')}
                  </span>
                  <button
                    type="button"
                    onClick={() => setEditing(code)}
                    className="inline-flex items-center gap-1.5 text-xs text-gray-400 transition hover:text-white"
                  >
                    <Pencil className="h-3.5 w-3.5" /> {t('brandRegion.edit')}
                  </button>
                </>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
};
