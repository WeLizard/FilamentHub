import { Fragment, memo, useEffect, useState, type MouseEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  ChevronLeft,
  ChevronRight,
  Check,
  Droplet,
  Fan,
  Plus,
  QrCode,
  Shield,
  Thermometer,
} from 'lucide-react';

import { qrAPI } from '../api/client';
import type { Filament } from '../types/api';
import { currencySymbol } from '../utils/currency';
import {
  formatTemperatureRange,
  getFilamentCompositionFacts,
  hasNonStandardDiameter,
} from '../utils/filamentFacts';
import { formatDate } from '../utils/formatDate';
import { filamentPublicPath } from '../utils/catalogUrls';
import { isPluginEmbed } from '../utils/pluginBridge';
import { FilamentHandlingBadges } from './FilamentHandlingBadges';
import { FilamentPreview } from './FilamentPreview';
import { MarketNotice } from './MarketNotice';
import { NozzleRequirementBadge } from './NozzleRequirementBadge';

interface CatalogFilamentTableProps {
  filaments: Filament[];
  onSelect?: (presetId: number) => void;
  onShowQR?: (filamentId: number) => void;
  showQR?: number | null;
  savedPresetIds?: Set<number>;
  configuredNozzleHrc?: number | null;
  printerMatchedIds?: Set<number>;
}

const EMPTY_IDS = new Set<number>();
const TABLE_ACTION_BUTTON_CLASS = 'inline-flex size-10 shrink-0 items-center justify-center rounded-lg border transition';

export function CatalogFilamentTable({
  filaments,
  onSelect,
  onShowQR,
  showQR = null,
  savedPresetIds = EMPTY_IDS,
  configuredNozzleHrc = null,
  printerMatchedIds = EMPTY_IDS,
}: CatalogFilamentTableProps) {
  const { t } = useTranslation();

  return (
    <div className="overflow-hidden rounded-2xl border border-white/15 bg-white/[0.06] shadow-xl">
      <table className="w-full table-fixed border-collapse text-left">
        <caption className="sr-only">{t('catalogPage.tableCaption')}</caption>
        <colgroup>
          <col style={{ width: '13%' }} />
          <col style={{ width: '18%' }} />
          <col style={{ width: '15%' }} />
          <col style={{ width: '15%' }} />
          <col style={{ width: '11%' }} />
          <col style={{ width: '18%' }} />
          <col style={{ width: '10%' }} />
        </colgroup>
        <thead className="bg-black/20 text-[11px] uppercase tracking-[0.12em] text-gray-400">
          <tr>
            <th scope="col" className="px-3 py-3">{t('catalogPage.tableColor')}</th>
            <th scope="col" className="px-3 py-3">{t('catalogPage.tableMaterial')}</th>
            <th scope="col" className="px-3 py-3">{t('catalogPage.tableProperties')}</th>
            <th scope="col" className="px-3 py-3">{t('catalogPage.tablePrinting')}</th>
            <th scope="col" className="px-3 py-3">{t('catalogPage.tableMarket')}</th>
            <th scope="col" className="px-3 py-3">{t('catalogPage.tablePreset')}</th>
            <th scope="col" className="px-3 py-3 text-right">{t('catalogPage.tableActions')}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-white/10">
          {filaments.map((filament) => (
            <CatalogFilamentTableRow
              key={filament.id}
              filament={filament}
              onSelect={onSelect}
              onShowQR={onShowQR}
              showQR={showQR === filament.id}
              savedPresetIds={savedPresetIds}
              configuredNozzleHrc={configuredNozzleHrc}
              fitsPrinter={printerMatchedIds.has(filament.id)}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface CatalogFilamentTableRowProps {
  filament: Filament;
  onSelect?: (presetId: number) => void;
  onShowQR?: (filamentId: number) => void;
  showQR: boolean;
  savedPresetIds: Set<number>;
  configuredNozzleHrc: number | null;
  fitsPrinter: boolean;
}

const CatalogFilamentTableRow = memo(function CatalogFilamentTableRow({
  filament,
  onSelect,
  onShowQR,
  showQR,
  savedPresetIds,
  configuredNozzleHrc,
  fitsPrinter,
}: CatalogFilamentTableRowProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [currentPresetIndex, setCurrentPresetIndex] = useState(0);
  const presetSummaries = filament.preset_summaries && filament.preset_summaries.length > 0
    ? filament.preset_summaries
    : filament.official_preset
      ? [{ ...filament.official_preset }]
      : [];
  const currentPreset = presetSummaries[currentPresetIndex] ?? null;
  const hasCarousel = presetSummaries.length > 1;
  const isPresetSaved = currentPreset ? savedPresetIds.has(currentPreset.id) : false;
  const canShowQR = Boolean(onShowQR && filament.qr_code && filament.brand_verified);
  const materialPath = filamentPublicPath(filament);
  const manufacturerNozzleRange = formatTemperatureRange(
    filament.recommended_nozzle_temp_min,
    filament.recommended_nozzle_temp_max,
  );
  const manufacturerBedRange = formatTemperatureRange(
    filament.recommended_bed_temp_min,
    filament.recommended_bed_temp_max,
  );
  const compositionLabels = getFilamentCompositionFacts(filament).map((fact) => {
    const label = t(`filamentFeatures.${fact.kind === 'additive' ? 'additives' : 'effects'}.${fact.code}`, {
      defaultValue: fact.code.replaceAll('_', ' '),
    });
    return fact.kind === 'additive' && fact.contentPercent != null
      ? `${label} ${fact.contentPercent}%`
      : label;
  });
  const propertyLabels = (filament.property_claims ?? []).map((claim) =>
    t(`filamentFeatures.claims.${claim.code}`, { defaultValue: claim.code.replaceAll('_', ' ') }),
  );

  useEffect(() => {
    setCurrentPresetIndex(0);
  }, [filament.id, presetSummaries.length]);

  const cyclePreset = (direction: 'prev' | 'next') => {
    if (!hasCarousel) return;
    setCurrentPresetIndex((current) => direction === 'prev'
      ? (current - 1 + presetSummaries.length) % presetSummaries.length
      : (current + 1) % presetSummaries.length);
  };

  const openFilament = (event: MouseEvent<HTMLTableRowElement>) => {
    const target = event.target as HTMLElement;
    if (target.closest('a, button')) return;
    navigate(materialPath);
  };

  const presetBadge = currentPreset
    ? getPresetTypeBadge(
        currentPreset.preset_type,
        currentPreset.is_official,
        currentPreset.is_weighted,
        t,
      )
    : null;

  return (
    <Fragment>
      <tr
        onClick={openFilament}
        className="cursor-pointer align-top text-sm text-gray-300 transition-colors hover:bg-white/[0.05]"
      >
        <td className="px-3 py-4">
          <div className="min-w-0">
            {(filament.color_hex || filament.visual_settings) && (
              <div className="h-6 w-[70px] overflow-visible" aria-hidden>
                <div style={{ transform: 'scale(0.45)', transformOrigin: 'top left' }}>
                  <FilamentPreview
                    colorHex={filament.color_hex || '#FFFFFF'}
                    visualSettings={filament.visual_settings}
                    size="small"
                  />
                </div>
              </div>
            )}
            <div className={`${filament.color_hex || filament.visual_settings ? 'mt-1' : ''} min-w-0 text-xs text-gray-300`}>
              <p className="truncate" title={filament.color_name || filament.color_hex || undefined}>
                {filament.color_name || filament.color_hex || '—'}
              </p>
              {filament.ral_code && (
                <p className="mt-0.5 truncate font-mono text-[10px] text-gray-500">
                  RAL {filament.ral_code}
                </p>
              )}
            </div>
          </div>
        </td>
        <th scope="row" className="px-3 py-4 font-normal">
          <Link
            to={materialPath}
            className="block font-semibold text-white transition-colors hover:text-purple-300 hover:underline"
          >
            {filament.name}
          </Link>
          {filament.brand_name && filament.brand_slug && (
            <Link
              to={`/brands/${filament.brand_slug}`}
              className={`mt-1 inline-flex items-center gap-1 text-xs font-medium hover:underline ${
                filament.brand_verified ? 'text-green-300' : 'text-purple-300'
              }`}
            >
              {filament.brand_name}
              {filament.brand_verified && <Shield className="h-3.5 w-3.5" aria-hidden />}
            </Link>
          )}
          <div className="mt-2 flex flex-wrap gap-1">
            {fitsPrinter && (
              <span className="rounded-full border border-emerald-500/30 bg-emerald-500/15 px-2 py-0.5 text-[10px] text-emerald-300">
                {t('catalogPage.fitsPrinter')}
              </span>
            )}
            {filament.availability && filament.availability !== 'available' && (
              <span className="rounded-full border border-amber-500/30 bg-amber-500/15 px-2 py-0.5 text-[10px] text-amber-300">
                {t(`createFilament.availability.${filament.availability}`)}
              </span>
            )}
          </div>
        </th>
        <td className="px-3 py-4">
          <span className="inline-flex rounded-full border border-purple-500/30 bg-purple-500/20 px-2 py-0.5 text-xs text-purple-200">
            {filament.material_type}
          </span>
          {compositionLabels.length > 0 && (
            <p className="mt-2 line-clamp-2 text-xs text-gray-400" title={compositionLabels.join(', ')}>
              {compositionLabels.join(' · ')}
            </p>
          )}
          {propertyLabels.length > 0 && (
            <p className="mt-1 line-clamp-2 text-xs text-sky-200/80" title={propertyLabels.join(', ')}>
              {propertyLabels.join(' · ')}
            </p>
          )}
          {hasNonStandardDiameter(filament.diameter) && (
            <p className="mt-2 text-xs text-gray-400">
              {t('catalogPage.diameter')}: {filament.diameter} {t('catalogPage.units.mm')}
            </p>
          )}
        </td>
        <td className="px-3 py-4">
          {(manufacturerNozzleRange || manufacturerBedRange) && (
            <div className="space-y-1 text-xs">
              {manufacturerNozzleRange && (
                <p className="flex items-center gap-1.5">
                  <Thermometer className="h-3.5 w-3.5 text-orange-300" aria-hidden />
                  {t('catalogPage.nozzle')} <strong className="font-semibold text-white">{manufacturerNozzleRange}°C</strong>
                </p>
              )}
              {manufacturerBedRange && (
                <p className="flex items-center gap-1.5">
                  <Thermometer className="h-3.5 w-3.5 text-blue-300" aria-hidden />
                  {t('catalogPage.bed')} <strong className="font-semibold text-white">{manufacturerBedRange}°C</strong>
                </p>
              )}
            </div>
          )}
          <NozzleRequirementBadge
            requiredHrc={filament.required_nozzle_hrc}
            configuredHrc={configuredNozzleHrc}
            compact
            size="tight"
            className="mt-2"
          />
          <FilamentHandlingBadges filament={filament} compact className="mt-2" />
        </td>
        <td className="px-3 py-4">
          <MarketNotice filament={filament} compact />
          <CatalogPrice filament={filament} />
        </td>
        <td className="px-3 py-4">
          {currentPreset ? (
            <div className="space-y-2">
              <div className="flex min-w-0 items-center gap-2">
                {presetBadge && (
                  <span className={`shrink-0 rounded-full border px-2 py-0.5 text-[10px] ${presetBadge.className}`}>
                    {presetBadge.label}
                  </span>
                )}
                <span className="truncate text-xs font-medium text-white" title={currentPreset.name}>
                  {currentPreset.name}
                </span>
              </div>
              <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-gray-400">
                <span>★ {currentPreset.rating != null ? currentPreset.rating.toFixed(1) : '—'}</span>
                <span>✓ {currentPreset.success_rate != null ? `${currentPreset.success_rate.toFixed(0)}%` : '—'}</span>
                <span className="inline-flex items-center gap-1"><Thermometer className="h-3 w-3 text-orange-300" aria-hidden />{formatPresetValue(currentPreset.extruder_temp, '°')}</span>
                <span className="inline-flex items-center gap-1"><Thermometer className="h-3 w-3 text-blue-300" aria-hidden />{formatPresetValue(currentPreset.bed_temp, '°')}</span>
                <span className="inline-flex items-center gap-1"><Fan className="h-3 w-3 text-sky-300" aria-hidden />{formatFanSpeed(currentPreset.fan_speed, t('catalogPage.fanNo'))}</span>
                <span className="inline-flex items-center gap-1"><Droplet className="h-3 w-3 text-emerald-300" aria-hidden />{formatPresetValue(currentPreset.flow_rate, '%')}</span>
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] text-gray-500">
                  {t('catalogPage.updatedAt')} {formatUpdatedAt(currentPreset.updated_at)}
                </span>
                {hasCarousel && (
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        cyclePreset('prev');
                      }}
                      className="rounded border border-white/15 p-1 text-gray-300 hover:bg-white/10 hover:text-white"
                      aria-label={t('catalogPage.previousPreset')}
                    >
                      <ChevronLeft className="h-3.5 w-3.5" aria-hidden />
                    </button>
                    <span className="min-w-8 text-center text-[10px] text-gray-400">
                      {currentPresetIndex + 1}/{presetSummaries.length}
                    </span>
                    <button
                      type="button"
                      onClick={(event) => {
                        event.stopPropagation();
                        cyclePreset('next');
                      }}
                      className="rounded border border-white/15 p-1 text-gray-300 hover:bg-white/10 hover:text-white"
                      aria-label={t('catalogPage.nextPreset')}
                    >
                      <ChevronRight className="h-3.5 w-3.5" aria-hidden />
                    </button>
                  </div>
                )}
              </div>
            </div>
          ) : (
            <span className="text-gray-500">—</span>
          )}
        </td>
        <td className="px-3 py-4">
          <div className="flex justify-end gap-2">
            {currentPreset && onSelect && (
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  onSelect(currentPreset.id);
                }}
                disabled={isPresetSaved}
                className={`${TABLE_ACTION_BUTTON_CLASS} border-white/20 bg-white/5 text-white hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-60`}
                aria-label={isPresetSaved
                  ? t('catalogPage.addedToProfile')
                  : isPluginEmbed()
                    ? t('catalogPage.importToOrca')
                    : t('catalogPage.addToProfile')}
                title={isPresetSaved
                  ? t('catalogPage.addedToProfile')
                  : isPluginEmbed()
                    ? t('catalogPage.importToOrca')
                    : t('catalogPage.addToProfile')}
              >
                {isPresetSaved
                  ? <Check className="h-4 w-4" aria-hidden />
                  : <Plus className="h-4 w-4" aria-hidden />}
              </button>
            )}
            {canShowQR && (
              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation();
                  onShowQR?.(filament.id);
                }}
                className={`${TABLE_ACTION_BUTTON_CLASS} border-white/20 bg-white/5 text-white hover:bg-white/10`}
                aria-label={t('catalogPage.qrCode')}
                aria-expanded={showQR}
                aria-controls={`catalog-table-qr-${filament.id}`}
                title={t('catalogPage.qrCode')}
              >
                <QrCode className="h-4 w-4" aria-hidden />
              </button>
            )}
          </div>
        </td>
      </tr>
      {canShowQR && showQR && (
        <tr id={`catalog-table-qr-${filament.id}`} className="bg-black/15">
          <td colSpan={7} className="px-4 py-4">
            <div className="flex items-center justify-center gap-4">
              <img
                src={qrAPI.getQRCodeURL(filament.id, 160)}
                alt={`QR ${filament.name}`}
                className="h-36 w-36 rounded-lg bg-white p-2"
              />
              <div className="max-w-sm text-sm text-gray-300">
                <p className="font-medium text-white">{t('catalogPage.qrCode')} {filament.qr_code}</p>
                <p className="mt-1 text-xs text-gray-400">{t('catalogPage.qrScanHint')}</p>
                <p className="mt-1 text-xs text-gray-500">
                  {t('catalogPage.qrScans')} {filament.scans_count || 0}
                </p>
              </div>
            </div>
          </td>
        </tr>
      )}
    </Fragment>
  );
});

function CatalogPrice({ filament }: { filament: Filament }) {
  const { t } = useTranslation();

  if (filament.price_hidden || (!filament.price_per_kg && !filament.spool_weight)) {
    return null;
  }

  if (filament.price_display_unit === 'per_spool' && filament.price_per_kg) {
    return (
      <div className="mt-2 text-xs">
        <p className="font-medium text-gray-200">
          {filament.price_per_kg} {currencySymbol(filament.currency)}/{t('catalogPage.units.spool')}
        </p>
        {filament.spool_weight && (
          <p className="mt-0.5 text-[10px] text-gray-500">
            {Math.round(filament.spool_weight)} {t('catalogPage.units.g')}
          </p>
        )}
      </div>
    );
  }

  if (filament.price_per_kg && filament.spool_weight && filament.spool_weight !== 1000) {
    return (
      <div className="mt-2 text-xs">
        <p className="font-medium text-gray-200">
          {Math.round((filament.price_per_kg * filament.spool_weight) / 1000)} {currencySymbol(filament.currency)}
          <span className="text-gray-400">/{Math.round(filament.spool_weight)} {t('catalogPage.units.g')}</span>
        </p>
        <p className="mt-0.5 text-[10px] text-gray-500">
          ≈ {Math.round(filament.price_per_kg)} {currencySymbol(filament.currency)}/{t('catalogPage.units.kg')}
        </p>
      </div>
    );
  }

  if (filament.price_per_kg) {
    return (
      <p className="mt-2 text-xs font-medium text-gray-200">
        {Math.round(filament.price_per_kg)} {currencySymbol(filament.currency)}/{t('catalogPage.units.kg')}
      </p>
    );
  }

  return (
    <p className="mt-2 text-xs text-gray-400">
      {Math.round(filament.spool_weight!)} {t('catalogPage.units.g')}
    </p>
  );
}

function formatPresetValue(value: number | null | undefined, suffix: string) {
  return value == null ? '—' : `${Math.round(value)}${suffix}`;
}

function formatFanSpeed(value: number | null | undefined, offLabel: string) {
  if (value == null) return offLabel;
  const rounded = Math.round(value);
  return rounded > 0 ? `${rounded}%` : offLabel;
}

function formatUpdatedAt(value: string | null | undefined) {
  if (!value) return '—';
  try {
    return formatDate(value);
  } catch {
    return '—';
  }
}

function getPresetTypeBadge(
  presetType: string | undefined,
  isOfficial: boolean,
  isWeighted: boolean,
  t: (key: string) => string,
) {
  if (presetType === 'official' || isOfficial) {
    return {
      label: t('catalogPage.badgeOfficial'),
      className: 'border-green-500/30 bg-green-500/20 text-green-200',
    };
  }
  if (presetType === 'weighted' || isWeighted) {
    return {
      label: t('catalogPage.badgeWeighted'),
      className: 'border-yellow-500/30 bg-yellow-500/20 text-yellow-200',
    };
  }
  return {
    label: t('catalogPage.badgeCommunity'),
    className: 'border-blue-500/30 bg-blue-500/20 text-blue-200',
  };
}
