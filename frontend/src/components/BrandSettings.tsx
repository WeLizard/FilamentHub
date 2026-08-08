/** Настройки бренда: области определяются правами организации, а не её страной. */

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Loader2, Upload, X } from 'lucide-react';

import { brandsAPI } from '../api/client';
import { COUNTRY_CODES, countryName } from '../utils/countries';
import { CURRENCY_CODES, currencySymbol, defaultCurrencyForCountry } from '../utils/currency';
import { translateApiError } from '../utils/translateApiError';
import { useAuth } from '../contexts/AuthContext';
import { BrandLogoFrame } from './BrandLogoFrame';
import { FeedbackModal } from './FeedbackModal';
import { HSLColorPicker } from './HSLColorPicker';
import { SocialIcon } from './socialIcons';
import { toast } from './Toast';
import type { Brand, BrandCountryCell } from '../types/api';
import type { AxiosError } from 'axios';

interface BrandSettingsProps {
  brand: Brand;
}

type ShopLink = { platform: string; url: string };

const FIELD =
  'w-full rounded-xl border border-white/20 bg-white/10 px-4 py-3 text-white placeholder-gray-400 transition-all focus:outline-none focus:ring-2 focus:ring-purple-500';
const LABEL = 'mb-2 block text-sm font-medium text-gray-300';
const CONTEXT = 'mt-1.5 text-xs leading-5 text-gray-500';

const COMMON_SCOPE = 'common';

function LinkRow({
  icon,
  children,
  onRemove,
}: {
  icon: React.ReactNode;
  children: React.ReactNode;
  onRemove: () => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/5 text-gray-300">
        {icon}
      </span>
      {children}
      <button
        type="button"
        onClick={onRemove}
        className="rounded-xl bg-white/10 px-3 py-3 text-gray-300 transition-all hover:bg-red-500/20"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

export const BrandSettings: React.FC<BrandSettingsProps> = ({ brand }) => {
  const { t, i18n } = useTranslation();
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const territories = useQuery({
    queryKey: ['brand-territories', brand.id, user?.active_organization_id],
    queryFn: () => brandsAPI.myTerritories(brand.id),
  });
  const cells = useQuery({
    queryKey: ['brand-country-cells', brand.id, user?.active_organization_id],
    queryFn: () => brandsAPI.countryCells(brand.id),
  });

  const canEditCommon = Boolean(territories.data?.can_edit_common || territories.data?.is_admin);
  const grants = territories.data?.territories ?? [];
  const hasGlobalGrant =
    grants.some((item) => item.country === null) || Boolean(territories.data?.is_admin);

  // Область — это право организации на бренд, а не сорт пользователя. Глобальное
  // право покрывает любую страну, поэтому там список стран открыт.
  const countries = useMemo(() => {
    const own = grants.map((item) => item.country).filter((code): code is string => code !== null);
    if (!hasGlobalGrant) return own;
    return Array.from(new Set([...own, ...(cells.data ?? []).map((cell) => cell.country)]));
  }, [grants, cells.data, hasGlobalGrant]);
  const scopeOptions = hasGlobalGrant
    ? [COMMON_SCOPE, ...countries]
    : [...countries, COMMON_SCOPE];

  const [scope, setScope] = useState<string>(COMMON_SCOPE);
  const cell: BrandCountryCell | undefined = (cells.data ?? []).find(
    (item) => item.country === scope,
  );
  // Common data follows the global capability. Territorial workspaces use the
  // same rows after choosing their country, but do not mutate the shared layer.
  const canEditField = (_value: unknown) => {
    if (scope !== COMMON_SCOPE) return true;
    return canEditCommon;
  };
  const canUploadLogo = canEditCommon || (!brand.logo_url && grants.length > 0);

  const [description, setDescription] = useState('');
  const [brandName, setBrandName] = useState(brand.name);
  const [website, setWebsite] = useState('');
  const [socials, setSocials] = useState<string[] | null>(null);
  const [shops, setShops] = useState<ShopLink[] | null>(null);
  const [marketCurrency, setMarketCurrency] = useState('');
  const [logoBg, setLogoBg] = useState(brand.logo_bg || '');
  const [bgPickerOpen, setBgPickerOpen] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [justSaved, setJustSaved] = useState(false);
  const [nameRequestOpen, setNameRequestOpen] = useState(false);

  useEffect(() => {
    if (hasGlobalGrant) {
      setScope((current) => (
        current === COMMON_SCOPE || countries.includes(current) ? current : COMMON_SCOPE
      ));
      return;
    }
    setScope((current) => (
      countries.includes(current) ? current : countries[0] ?? COMMON_SCOPE
    ));
  }, [countries, hasGlobalGrant, user?.active_organization_id]);

  useEffect(() => {
    if (scope === COMMON_SCOPE) {
      setDescription(brand.description || '');
      setWebsite(brand.website || '');
      setSocials(brand.social_media_urls || []);
      setShops(brand.shop_links || []);
      return;
    }
    setDescription(cell?.description || '');
    setWebsite(cell?.website || '');
    // null означает «не задано, наследуется»; пустой список — уже своё решение.
    setSocials(cell?.social_media_urls ?? null);
    setShops(cell?.shop_links ?? null);
    setMarketCurrency(cell?.currency ?? defaultCurrencyForCountry(scope));
  }, [scope, cell?.id, brand.id, brand.updated_at]);

  useEffect(() => {
    setBrandName(brand.name);
    setLogoBg(brand.logo_bg || '');
  }, [brand.name, brand.logo_bg]);

  const fail = (error: unknown, fallback: string) =>
    toast.error(
      translateApiError(
        t,
        (error as AxiosError<{ detail: unknown }>).response?.data?.detail,
        t(fallback),
      ),
    );

  const save = useMutation({
    mutationFn: async () => {
      if (scope === COMMON_SCOPE) {
        return brandsAPI.update(brand.id, {
          ...(brand.name_correction_available && brandName.trim() !== brand.name
            ? { name: brandName.trim() }
            : {}),
          description: description.trim() || null,
          website: website.trim() || null,
          logo_bg: logoBg.trim() || null,
          social_media_urls: (socials ?? []).filter((url) => url.trim()),
          shop_links: (shops ?? []).filter((link) => link.url.trim()),
        });
      }
      const payload = {
        description: description.trim() || null,
        website: website.trim() || null,
        social_media_urls: socials === null ? null : socials.filter((url) => url.trim()),
        shop_links: shops === null ? null : shops.filter((link) => link.url.trim()),
        currency: marketCurrency || null,
        published: true,
      };
      return cell
        ? brandsAPI.updateCountryCell(brand.id, scope, payload)
        : brandsAPI.createCountryCell(brand.id, { country: scope, ...payload });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['brand'] });
      queryClient.invalidateQueries({ queryKey: ['brand-country-cells', brand.id] });
      toast.success(t('brandSettings.saved'));
      setJustSaved(true);
      window.setTimeout(() => setJustSaved(false), 2500);
    },
    onError: (error) => fail(error, 'brandSettings.saveFailed'),
  });

  const removeLogo = useMutation({
    mutationFn: () => brandsAPI.update(brand.id, { logo_url: null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['brand'] });
      toast.success(t('brandSettings.saved'));
    },
    onError: (error) => fail(error, 'brandSettings.saveFailed'),
  });

  const uploadLogo = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setUploading(true);
    try {
      await brandsAPI.uploadLogo(brand.id, file);
      queryClient.invalidateQueries({ queryKey: ['brand'] });
      toast.success(t('brandSettings.logoUpdated'));
    } catch (error) {
      fail(error, 'brandSettings.saveFailed');
    } finally {
      setUploading(false);
      event.target.value = '';
    }
  };

  if (territories.isLoading) return null;

  const shown = (value: string | null | undefined) =>
    value && value.trim() ? value : t('brandSettings.notSet');
  const shownList = (values: string[] | null | undefined) =>
    values && values.length > 0 ? values.join(', ') : t('brandSettings.notSet');

  return (
    <div className="space-y-5">
      <FeedbackModal
        isOpen={nameRequestOpen}
        onClose={() => setNameRequestOpen(false)}
        initialType="other"
        initialSubject={t('brandSettings.nameRequestSubject', { brand: brand.name })}
      />
      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <section className="rounded-2xl border border-white/10 bg-white/[0.04] p-5 sm:p-6">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-start">
          {brand.logo_url && (
            <BrandLogoFrame
              src={brand.logo_url}
              alt={brand.name}
              backgroundColor={logoBg}
              size="settings"
            />
          )}

          <div className="min-w-0 flex-1">
            {brand.name_correction_available && canEditCommon ? (
              <div className="rounded-xl border border-cyan-400/20 bg-cyan-400/5 p-4">
                <label className={LABEL}>{t('brandProfile.officialNameLabel')}</label>
                <input
                  type="text"
                  value={brandName}
                  maxLength={100}
                  onChange={(event) => setBrandName(event.target.value)}
                  className={FIELD}
                />
                <p className={CONTEXT}>{t('brandProfile.officialNameHint')}</p>
              </div>
            ) : (
              <>
                <h4 className="truncate text-xl font-semibold text-white">{brand.name}</h4>
                <p className={CONTEXT}>
                  {t('brandSettings.nameThroughAdmin')}{' '}
                  <button
                    type="button"
                    onClick={() => setNameRequestOpen(true)}
                    className="text-cyan-300 underline-offset-2 transition hover:text-cyan-200 hover:underline"
                  >
                    {t('brandSettings.requestNameChange')}
                  </button>
                </p>
              </>
            )}

            {canUploadLogo && (
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <label className="inline-flex cursor-pointer items-center justify-center gap-2 rounded-xl border border-white/20 bg-white/10 px-4 py-2.5 text-gray-300 transition-all hover:bg-white/20 hover:text-white">
                  {uploading ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Upload className="h-4 w-4" />
                  )}
                  <span className="text-sm">{t('brandProfile.uploadLogo')}</span>
                  <input type="file" accept="image/*" className="hidden" onChange={uploadLogo} />
                </label>
                {brand.logo_url && canEditCommon && (
                  <button
                    type="button"
                    onClick={() => removeLogo.mutate()}
                    disabled={removeLogo.isPending}
                    className="rounded-xl border border-white/15 px-4 py-2.5 text-sm text-gray-400 transition-all hover:border-red-400/30 hover:bg-red-500/10 hover:text-red-200 disabled:opacity-50"
                  >
                    {t('brandProfile.removeLogo')}
                  </button>
                )}
              </div>
            )}
          </div>
        </div>

        {canEditCommon && brand.logo_url && (
          <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-white/10 pt-4">
            <div>
              <p className="text-sm font-medium text-gray-300">{t('brandProfile.logoBgLabel')}</p>
              <p className="mt-0.5 text-xs text-gray-500">{t('brandProfile.logoBgHint')}</p>
            </div>
            <div className="flex items-center gap-3">
              <HSLColorPicker
                color={logoBg || '#ffffff'}
                onChange={setLogoBg}
                isOpen={bgPickerOpen}
                onToggle={setBgPickerOpen}
                showTrigger
                triggerClassName="h-10 w-10 cursor-pointer rounded-lg border border-white/20 shadow-inner"
                flyoutOffset="-mb-7"
              />
              <span className="min-w-16 font-mono text-xs text-gray-400">
                {logoBg || t('brandProfile.logoBgDefault')}
              </span>
              {logoBg && (
                <button
                  type="button"
                  onClick={() => setLogoBg('')}
                  className="rounded-lg px-3 py-2 text-sm text-gray-400 transition hover:bg-white/10 hover:text-white"
                >
                  {t('brandProfile.logoBgReset')}
                </button>
              )}
            </div>
          </div>
        )}
        </section>

        <div className="min-w-0 space-y-3">
          <div className="flex w-fit max-w-full flex-wrap items-center gap-1 rounded-xl border border-white/10 bg-white/[0.04] p-1.5">
            <span className="px-2 text-sm text-gray-400">{t('brandSettings.scope')}</span>
            {scopeOptions.map((code) => (
              <button
                key={code}
                type="button"
                onClick={() => setScope(code)}
                className={`rounded-lg px-4 py-2 text-sm transition-all ${
                  scope === code
                    ? 'bg-purple-600 text-white shadow-lg shadow-purple-500/25'
                    : 'text-gray-300 hover:bg-white/10 hover:text-white'
                }`}
              >
                {code === COMMON_SCOPE ? t('brandSettings.common') : countryName(code, i18n.language)}
              </button>
            ))}
            {hasGlobalGrant && (
              <select
                value=""
                onChange={(event) => event.target.value && setScope(event.target.value)}
                className="rounded-lg border border-white/20 bg-white/10 px-3 py-2 text-sm text-white"
              >
                <option value="" className="bg-gray-900">
                  {t('brandSettings.addCountry')}
                </option>
                {COUNTRY_CODES.filter((code) => !countries.includes(code)).map((code) => (
                  <option key={code} value={code} className="bg-gray-900">
                    {countryName(code, i18n.language)}
                  </option>
                ))}
              </select>
            )}
          </div>

          <section
            className={`rounded-2xl border p-5 ${
              scope === COMMON_SCOPE
                ? 'border-white/10 bg-white/[0.04]'
                : 'border-emerald-400/20 bg-emerald-400/[0.06]'
            }`}
          >
        <h4 className="font-semibold text-white">
          {scope === COMMON_SCOPE
            ? t('brandSettings.commonTitle')
            : t('brandSettings.countryTitle', { country: countryName(scope, i18n.language) })}
        </h4>

        <div className="mt-4 space-y-5">
            <div>
              <label className={LABEL}>{t('brandProfile.websiteLabel')}</label>
              {canEditField(brand.website) ? (
                <input
                  type="url"
                  value={website}
                  onChange={(event) => setWebsite(event.target.value)}
                  placeholder="https://example.com"
                  className={FIELD}
                />
              ) : (
                <p className="text-sm text-white">{shown(brand.website)}</p>
              )}
              {scope !== COMMON_SCOPE && (
                <p className={CONTEXT}>
                  {t('brandSettings.inherited', { value: shown(brand.website) })}
                </p>
              )}
            </div>

            {scope !== COMMON_SCOPE && (
              <div>
                <label className={LABEL}>{t('brandSettings.marketCurrency')}</label>
                <select
                  value={marketCurrency}
                  onChange={(event) => setMarketCurrency(event.target.value)}
                  className={`${FIELD} sm:max-w-xs`}
                >
                  {CURRENCY_CODES.map((code) => (
                    <option key={code} value={code} className="bg-gray-900">
                      {code} · {currencySymbol(code)}
                    </option>
                  ))}
                </select>
                <p className={CONTEXT}>{t('brandSettings.marketCurrencyHint')}</p>
              </div>
            )}

            <div>
              <label className={LABEL}>{t('brandProfile.descriptionLabel')}</label>
              {canEditField(brand.description) ? (
                <textarea
                  value={description}
                  rows={3}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder={t('brandProfile.descriptionPlaceholder')}
                  className={FIELD}
                />
              ) : (
                <p className="whitespace-pre-line text-sm text-white">{shown(brand.description)}</p>
              )}
              {scope !== COMMON_SCOPE && (
                <p className={CONTEXT}>
                  {t('brandSettings.inherited', { value: shown(brand.description) })}
                </p>
              )}
            </div>

            <div>
              <label className={LABEL}>{t('brandProfile.socialMediaLabel')}</label>
              {!canEditField(brand.social_media_urls) ? (
                <p className="text-sm text-white">{shownList(brand.social_media_urls)}</p>
              ) : scope !== COMMON_SCOPE && socials === null ? (
                <>
                  <p className="text-sm text-gray-400">{shownList(brand.social_media_urls)}</p>
                  <button
                    type="button"
                    onClick={() => setSocials(brand.social_media_urls ?? [])}
                    className="mt-2 text-sm text-emerald-300 hover:text-emerald-200"
                  >
                    {t('brandSettings.setOwnList')}
                  </button>
                  <p className={CONTEXT}>{t('brandSettings.listReplaces')}</p>
                </>
              ) : (
                <div className="space-y-2">
                  {(socials ?? []).map((url, index) => (
                    <LinkRow
                      key={index}
                      icon={<SocialIcon url={url} className="h-4 w-4" />}
                      onRemove={() => setSocials((socials ?? []).filter((_, i) => i !== index))}
                    >
                      <input
                        type="url"
                        value={url}
                        onChange={(event) =>
                          setSocials(
                            (socials ?? []).map((item, i) =>
                              i === index ? event.target.value : item,
                            ),
                          )
                        }
                        placeholder="https://..."
                        className={FIELD}
                      />
                    </LinkRow>
                  ))}
                  <button
                    type="button"
                    onClick={() => setSocials([...(socials ?? []), ''])}
                    className="text-sm text-purple-300 hover:text-purple-200"
                  >
                    + {t('brandProfile.addLink')}
                  </button>
                </div>
              )}
            </div>

            <div>
              <label className={LABEL}>{t('brandProfile.shopLinksLabel')}</label>
              {!canEditField(brand.shop_links) ? (
                <p className="text-sm text-white">
                  {shownList((brand.shop_links ?? []).map((link) => link.url))}
                </p>
              ) : scope !== COMMON_SCOPE && shops === null ? (
                <>
                  <p className="text-sm text-gray-400">
                    {shownList((brand.shop_links ?? []).map((link) => link.url))}
                  </p>
                  <button
                    type="button"
                    onClick={() => setShops(brand.shop_links ?? [])}
                    className="mt-2 text-sm text-emerald-300 hover:text-emerald-200"
                  >
                    {t('brandSettings.setOwnList')}
                  </button>
                  <p className={CONTEXT}>{t('brandSettings.listReplaces')}</p>
                </>
              ) : (
                <div className="space-y-2">
                  {(shops ?? []).map((link, index) => (
                    <LinkRow
                      key={index}
                      icon={<SocialIcon url={link.url} className="h-4 w-4" kind="shop" />}
                      onRemove={() => setShops((shops ?? []).filter((_, i) => i !== index))}
                    >
                      <input
                        type="text"
                        value={link.platform}
                        onChange={(event) =>
                          setShops(
                            (shops ?? []).map((item, i) =>
                              i === index ? { ...item, platform: event.target.value } : item,
                            ),
                          )
                        }
                        placeholder={t('brandProfile.shopPlatformPlaceholder')}
                        className="w-28 shrink-0 rounded-xl border border-white/20 bg-white/10 px-3 py-3 text-white placeholder-gray-400"
                      />
                      <input
                        type="url"
                        value={link.url}
                        onChange={(event) =>
                          setShops(
                            (shops ?? []).map((item, i) =>
                              i === index ? { ...item, url: event.target.value } : item,
                            ),
                          )
                        }
                        placeholder="https://..."
                        className={FIELD}
                      />
                    </LinkRow>
                  ))}
                  <button
                    type="button"
                    onClick={() => setShops([...(shops ?? []), { platform: '', url: '' }])}
                    className="text-sm text-purple-300 hover:text-purple-200"
                  >
                    + {t('brandProfile.addShop')}
                  </button>
                </div>
              )}
            </div>

            {(scope !== COMMON_SCOPE || canEditCommon) && (
            <div className="flex flex-wrap items-center gap-3">
              <button
                onClick={() => save.mutate()}
                disabled={save.isPending || (scope === COMMON_SCOPE && brand.name_correction_available && !brandName.trim())}
                className={`rounded-xl px-5 py-2.5 text-sm font-medium text-white transition disabled:opacity-50 ${
                  scope === COMMON_SCOPE
                    ? 'bg-purple-600 hover:bg-purple-700'
                    : 'bg-emerald-600 hover:bg-emerald-700'
                }`}
              >
                {save.isPending
                  ? t('brandSettings.saving')
                  : justSaved
                    ? t('brandSettings.saved')
                    : t('brandSettings.save')}
              </button>
              {scope !== COMMON_SCOPE && (
                <span className="text-xs text-gray-400">
                  {t('brandSettings.savePublishes', {
                    country: countryName(scope, i18n.language),
                  })}
                </span>
              )}
            </div>
            )}
        </div>
          </section>
        </div>
      </div>
    </div>
  );
};
