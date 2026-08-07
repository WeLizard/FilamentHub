/** Что представитель ведёт по этому товару в своей стране, а что — общее. */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Globe, Lock, MapPin, Trash2 } from 'lucide-react';

import { brandsAPI, filamentsAPI } from '../api/client';
import { countryName } from '../utils/countries';
import { CURRENCIES, currencySymbol, defaultCurrencyForCountry } from '../utils/currency';
import { translateApiError } from '../utils/translateApiError';
import { PriceWithUnit } from './PriceWithUnit';
import { toast } from './Toast';
import type { CountryAvailability, Filament, FilamentCountryCell } from '../types/api';
import type { AxiosError } from 'axios';

interface FilamentMarketPanelProps {
  filament: Filament;
}

const AVAILABILITY_STATES: CountryAvailability[] = ['available', 'unavailable', 'unknown'];

export const FilamentMarketPanel: React.FC<FilamentMarketPanelProps> = ({ filament }) => {
  const { t, i18n } = useTranslation();
  const queryClient = useQueryClient();

  const [activeCountry, setActiveCountry] = useState<string | null>(null);
  const [availability, setAvailability] = useState<CountryAvailability>('unknown');
  const [price, setPrice] = useState(0);
  const [currency, setCurrency] = useState(defaultCurrencyForCountry(null, i18n.language));
  const [priceMode, setPriceMode] = useState<'per_kg' | 'per_spool'>('per_kg');
  const [productUrl, setProductUrl] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [note, setNote] = useState('');
  const [published, setPublished] = useState(false);

  const territories = useQuery({
    queryKey: ['brand-territories', filament.brand_id],
    queryFn: () => brandsAPI.myTerritories(filament.brand_id),
  });

  const mine = (territories.data?.territories ?? []).filter((item) => item.manage_filament_country);

  const cells = useQuery({
    queryKey: ['filament-country-cells', filament.id],
    queryFn: () => filamentsAPI.countryCells(filament.id),
    enabled: mine.length > 0,
  });

  const countries = mine.map((item) => item.country).filter((c): c is string => c !== null);
  const isGlobal = mine.some((item) => item.country === null);

  useEffect(() => {
    if (activeCountry === null && countries.length > 0) {
      setActiveCountry(countries[0]);
    }
  }, [countries, activeCountry]);

  const currentCell: FilamentCountryCell | undefined = (cells.data ?? []).find(
    (cell) => cell.country === activeCountry,
  );

  useEffect(() => {
    setAvailability(currentCell?.availability ?? 'unknown');
    setPrice(currentCell?.price ?? 0);
    setCurrency(currentCell?.currency ?? defaultCurrencyForCountry(activeCountry, i18n.language));
    setPriceMode(currentCell?.price_display_unit === 'per_spool' ? 'per_spool' : 'per_kg');
    setProductUrl(currentCell?.product_url ?? '');
    setDisplayName(currentCell?.market_display_name ?? '');
    setNote(currentCell?.market_note ?? '');
    setPublished(currentCell?.published ?? false);
  }, [currentCell?.id, activeCountry, i18n.language]);

  const save = useMutation({
    mutationFn: async () => {
      if (!activeCountry) return;
      // Цена и валюта уходят парой: цена без валюты окажется не в тех деньгах.
      const hasPrice = price > 0;
      const payload = {
        availability,
        price: hasPrice ? price : null,
        currency: hasPrice ? currency : null,
        price_display_unit: hasPrice ? priceMode : null,
        product_url: productUrl.trim() || null,
        market_display_name: displayName.trim() || null,
        market_note: note.trim() || null,
        published,
      };
      if (currentCell) {
        return filamentsAPI.updateCountryCell(filament.id, activeCountry, payload);
      }
      return filamentsAPI.createCountryCell(filament.id, { country: activeCountry, ...payload });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['filament-country-cells', filament.id] });
      queryClient.invalidateQueries({ queryKey: ['filament', filament.id] });
      toast.success(t('filamentMarket.saved'));
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      toast.error(
        translateApiError(t, error.response?.data?.detail, t('filamentMarket.saveFailed')),
      );
    },
  });

  const remove = useMutation({
    mutationFn: async () => {
      if (!activeCountry) return;
      return filamentsAPI.deleteCountryCell(filament.id, activeCountry);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['filament-country-cells', filament.id] });
      queryClient.invalidateQueries({ queryKey: ['filament', filament.id] });
      toast.success(t('filamentMarket.removed'));
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      toast.error(
        translateApiError(t, error.response?.data?.detail, t('filamentMarket.saveFailed')),
      );
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

      {/* Первый слой: одинаковый во всех странах. Не «поле выключено», а «это общее». */}
      <section className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
        <div className="mb-3 flex items-center gap-2">
          <Globe className="h-4 w-4 text-gray-400" />
          <h3 className="font-semibold text-white">{t('filamentMarket.commonTitle')}</h3>
          <Lock className="h-3.5 w-3.5 text-gray-500" />
        </div>
        <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-gray-400">{t('filamentMarket.commonName')}</dt>
            <dd className="text-white">{filament.name}</dd>
          </div>
          <div>
            <dt className="text-gray-400">{t('filamentMarket.commonMaterial')}</dt>
            <dd className="text-white">{filament.material_type}</dd>
          </div>
          <div>
            <dt className="text-gray-400">{t('filamentMarket.commonDiameter')}</dt>
            <dd className="text-white">
              {filament.diameter} {t('catalogPage.units.mm')}
            </dd>
          </div>
          <div>
            <dt className="text-gray-400">{t('filamentMarket.commonDensity')}</dt>
            <dd className="text-white">
              {filament.density ? `${filament.density} ${t('catalogPage.units.gcm3')}` : '—'}
            </dd>
          </div>
        </dl>
        <p className="mt-3 text-xs leading-5 text-gray-400">{t('filamentMarket.commonExplained')}</p>
      </section>

      {/* Второй слой: свой рынок. */}
      <section className="rounded-2xl border border-emerald-400/20 bg-emerald-400/[0.06] p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-semibold text-white">
            {activeCountry
              ? t('filamentMarket.yoursTitle', {
                  country: countryName(activeCountry, i18n.language),
                })
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
          <div className="space-y-4">
            <div>
              <label className="mb-1.5 block text-xs text-gray-300">
                {t('filamentMarket.availability')}
              </label>
              <div className="flex flex-wrap gap-2">
                {AVAILABILITY_STATES.map((state) => (
                  <button
                    key={state}
                    type="button"
                    onClick={() => setAvailability(state)}
                    className={`rounded-lg border px-3 py-1.5 text-xs transition ${
                      availability === state
                        ? 'border-emerald-400/60 bg-emerald-500/20 text-white'
                        : 'border-white/20 bg-white/5 text-gray-300 hover:text-white'
                    }`}
                  >
                    {t(`filamentMarket.availability_${state}`)}
                  </button>
                ))}
              </div>
              <p className="mt-1.5 text-xs leading-5 text-gray-400">
                {t('filamentMarket.availabilityExplained')}
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-[minmax(0,22rem)_9rem]">
              <PriceWithUnit
                priceMode={priceMode}
                onPriceModeChange={setPriceMode}
                value={price}
                onValueChange={setPrice}
                currencySymbol={currencySymbol(currency)}
                spoolWeight={filament.spool_weight ?? 0}
              />
              <div className="flex flex-col">
                <label className="mb-2 block text-sm font-medium text-gray-300">
                  {t('filamentMarket.currency')}
                </label>
                <select
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                  className="rounded-xl border border-white/20 bg-white/10 px-4 py-3 text-white"
                >
                  {CURRENCIES.map((item) => (
                    <option key={item.code} value={item.code} className="bg-gray-900">
                      {item.code} {item.symbol}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <p className="-mt-2 text-xs leading-5 text-gray-400">
              {t('filamentMarket.priceExplained')}
            </p>

            <div>
              <label className="mb-1.5 block text-xs text-gray-300">
                {t('filamentMarket.productUrl')}
              </label>
              <input
                type="url"
                value={productUrl}
                onChange={(e) => setProductUrl(e.target.value)}
                placeholder="https://example.ru/pla-white"
                className="w-full rounded-xl border border-white/20 bg-white/10 px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
            </div>

            <div>
              <label className="mb-1.5 block text-xs text-gray-300">
                {t('filamentMarket.displayName')}
              </label>
              <input
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                placeholder={filament.name}
                maxLength={200}
                className="w-full rounded-xl border border-white/20 bg-white/10 px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
              <p className="mt-1.5 text-xs leading-5 text-gray-400">
                {t('filamentMarket.displayNameExplained')}
              </p>
            </div>

            <div>
              <label className="mb-1.5 block text-xs text-gray-300">
                {t('filamentMarket.note')}
              </label>
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                rows={2}
                className="w-full rounded-xl border border-white/20 bg-white/10 px-4 py-2.5 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-emerald-500"
              />
            </div>

            <label className="flex items-center gap-2 text-sm text-gray-300">
              <input
                type="checkbox"
                checked={published}
                onChange={(e) => setPublished(e.target.checked)}
                className="h-4 w-4 rounded border-white/30 bg-white/10"
              />
              {t('filamentMarket.published')}
            </label>

            <div className="flex flex-wrap items-center gap-3">
              <button
                onClick={() => save.mutate()}
                disabled={save.isPending}
                className="rounded-xl bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-emerald-700 disabled:opacity-50"
              >
                {save.isPending ? t('brandRegion.saving') : t('brandRegion.save')}
              </button>
              {currentCell && (
                <button
                  onClick={() => remove.mutate()}
                  disabled={remove.isPending}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-white/20 px-4 py-2 text-sm text-gray-300 transition hover:text-white disabled:opacity-50"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  {t('filamentMarket.remove')}
                </button>
              )}
            </div>
          </div>
        ) : (
          <p className="text-sm text-gray-300">{t('brandRegion.globalHasNoCell')}</p>
        )}
      </section>
    </div>
  );
};
