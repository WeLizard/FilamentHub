/** Как бренд выглядит на рынке представителя. Общее остаётся общим. */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { X } from 'lucide-react';

import { brandsAPI } from '../api/client';
import { countryName } from '../utils/countries';
import { translateApiError } from '../utils/translateApiError';
import { SocialIcon } from './socialIcons';
import { toast } from './Toast';
import type { Brand, BrandCountryCell } from '../types/api';
import type { AxiosError } from 'axios';

interface BrandRegionPanelProps {
  brand: Brand;
}

const FIELD =
  'w-full rounded-xl border border-white/20 bg-white/10 px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500';

export const BrandRegionPanel: React.FC<BrandRegionPanelProps> = ({ brand }) => {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();

  const [activeCountry, setActiveCountry] = useState<string | null>(null);
  const [website, setWebsite] = useState('');
  const [description, setDescription] = useState('');
  const [socials, setSocials] = useState<string[]>([]);
  const [shops, setShops] = useState<{ platform: string; url: string }[]>([]);

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
    setDescription(currentCell?.description ?? '');
    setSocials(currentCell?.social_media_urls ?? []);
    setShops(currentCell?.shop_links ?? []);
  }, [currentCell?.id, activeCountry]);

  const save = useMutation({
    mutationFn: async () => {
      if (!activeCountry) return;
      const socialList = socials.map((url) => url.trim()).filter(Boolean);
      const shopList = shops.filter((link) => link.url.trim());
      const payload = {
        website: website.trim() || null,
        description: description.trim() || null,
        social_media_urls: socialList.length > 0 ? socialList : null,
        shop_links: shopList.length > 0 ? shopList : null,
        published: true,
      };
      return currentCell
        ? brandsAPI.updateCountryCell(brand.id, activeCountry, payload)
        : brandsAPI.createCountryCell(brand.id, { country: activeCountry, ...payload });
    },
    onSuccess: () => {
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
    <section className="rounded-2xl border border-emerald-400/20 bg-emerald-400/[0.06] p-5">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-3">
        <h4 className="font-semibold text-white">
          {activeCountry
            ? t('brandRegion.title', { country: countryName(activeCountry, i18n.language) })
            : t('brandRegion.titleGeneric')}
        </h4>
        {countries.length > 1 && (
          <select
            value={activeCountry ?? ''}
            onChange={(event) => setActiveCountry(event.target.value)}
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
      <p className="mb-4 text-xs leading-5 text-gray-400">{t('brandRegion.explained')}</p>

      <div className="space-y-4">
        <div>
          <label className="mb-1.5 block text-sm font-medium text-gray-300">
            {t('brandRegion.website')}
          </label>
          <input
            type="url"
            value={website}
            onChange={(event) => setWebsite(event.target.value)}
            placeholder={brand.website || 'https://example.kz'}
            className={FIELD}
          />
        </div>

        <div>
          <label className="mb-1.5 block text-sm font-medium text-gray-300">
            {t('brandRegion.description')}
          </label>
          <textarea
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={3}
            placeholder={brand.description || ''}
            className={FIELD}
          />
        </div>

        <div>
          <label className="mb-2 block text-sm font-medium text-gray-300">
            {t('brandRegion.socials')}
          </label>
          <div className="space-y-2">
            {socials.map((url, index) => (
              <div key={index} className="flex items-center gap-2">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-gray-300">
                  <SocialIcon url={url} className="h-4 w-4" />
                </span>
                <input
                  type="url"
                  value={url}
                  onChange={(event) =>
                    setSocials(socials.map((item, i) => (i === index ? event.target.value : item)))
                  }
                  placeholder="https://..."
                  className={FIELD}
                />
                <button
                  type="button"
                  onClick={() => setSocials(socials.filter((_, i) => i !== index))}
                  className="rounded-xl bg-white/10 px-3 py-2.5 text-gray-300 transition-all hover:bg-red-500/20"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ))}
            <button
              type="button"
              onClick={() => setSocials([...socials, ''])}
              className="text-sm text-emerald-300 hover:text-emerald-200"
            >
              + {t('brandProfile.addLink')}
            </button>
          </div>
        </div>

        <div>
          <label className="mb-2 block text-sm font-medium text-gray-300">
            {t('brandRegion.shops')}
          </label>
          <div className="space-y-2">
            {shops.map((link, index) => (
              <div key={index} className="flex items-center gap-2">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-gray-300">
                  <SocialIcon url={link.url} className="h-4 w-4" kind="shop" />
                </span>
                <input
                  type="text"
                  value={link.platform}
                  onChange={(event) =>
                    setShops(
                      shops.map((item, i) =>
                        i === index ? { ...item, platform: event.target.value } : item,
                      ),
                    )
                  }
                  placeholder={t('brandProfile.shopPlatformPlaceholder')}
                  className="w-28 shrink-0 rounded-xl border border-white/20 bg-white/10 px-3 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500"
                />
                <input
                  type="url"
                  value={link.url}
                  onChange={(event) =>
                    setShops(
                      shops.map((item, i) =>
                        i === index ? { ...item, url: event.target.value } : item,
                      ),
                    )
                  }
                  placeholder="https://..."
                  className={FIELD}
                />
                <button
                  type="button"
                  onClick={() => setShops(shops.filter((_, i) => i !== index))}
                  className="rounded-xl bg-white/10 px-3 py-2.5 text-gray-300 transition-all hover:bg-red-500/20"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ))}
            <button
              type="button"
              onClick={() => setShops([...shops, { platform: '', url: '' }])}
              className="text-sm text-emerald-300 hover:text-emerald-200"
            >
              + {t('brandProfile.addShop')}
            </button>
          </div>
        </div>

        <button
          onClick={() => save.mutate()}
          disabled={save.isPending}
          className="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-emerald-700 disabled:opacity-50"
        >
          {save.isPending ? t('brandRegion.saving') : t('brandRegion.save')}
        </button>
      </div>
    </section>
  );
};
