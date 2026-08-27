import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Boxes,
  CheckCircle2,
  ExternalLink,
  Library,
  Loader2,
  LogIn,
  MapPin,
  PackagePlus,
  Printer,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import {
  physicalPrintersAPI,
  savedPresetsAPI,
  spoolsAPI,
  type QrScanResponse,
  type UserSpool,
} from '../api/client';
import { useConfigurationPresetRecommendation } from '../hooks/useConfigurationPresetRecommendation';
import { getSpoolCurrentLocation } from '../utils/spoolLocation';
import { translateApiError } from '../utils/translateApiError';
import { ModalOverlay } from './ModalOverlay';
import {
  PresetRecommendationEvidence,
  PrinterConfigurationSelect,
} from './ConfigurationPresetRecommendation';

interface QrScanResultModalProps {
  result: QrScanResponse;
  userId: number | null;
  onClose: () => void;
  onOpenMaterial?: () => void;
  onAddSpool?: (placement: 'shelf' | 'printer') => void;
  onOpenSpools?: () => void;
  onContinue?: () => void;
  continueLabel?: string;
  onRequestLogin?: () => void;
}

export function QrScanResultModal({
  result,
  userId,
  onClose,
  onOpenMaterial,
  onAddSpool,
  onOpenSpools,
  onContinue,
  continueLabel,
  onRequestLogin,
}: QrScanResultModalProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const filament = result.filament;
  const isAuthenticated = userId !== null;
  const configurationRecommendation = useConfigurationPresetRecommendation(
    userId,
    filament.id,
  );
  const hasConfiguration = configurationRecommendation.selectedKey !== '';
  const recommendationResolved = hasConfiguration
    && !configurationRecommendation.isLoadingRecommendation
    && !configurationRecommendation.isRecommendationError;
  const recommendedItem = hasConfiguration
    ? configurationRecommendation.recommendation
    : null;
  const selectedPreset = recommendationResolved
    ? recommendedItem?.preset ?? null
    : result.preset;
  const [presetSaved, setPresetSaved] = useState(result.preset_saved === true);
  const [presetSyncEnabled, setPresetSyncEnabled] = useState(
    result.preset_sync_enabled,
  );
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    setPresetSaved(
      recommendedItem?.saved
        ?? (selectedPreset?.id === result.preset?.id && result.preset_saved === true),
    );
    setPresetSyncEnabled(
      recommendedItem?.sync_enabled
        ?? (selectedPreset?.id === result.preset?.id ? result.preset_sync_enabled : null),
    );
    setSaveError(null);
  }, [recommendedItem, result, selectedPreset?.id]);

  const saveMutation = useMutation({
    mutationFn: () => savedPresetsAPI.save(selectedPreset!.id, false),
    onSuccess: (savedPreset) => {
      setPresetSaved(true);
      setPresetSyncEnabled(savedPreset.sync);
      setSaveError(null);
      queryClient.invalidateQueries({ queryKey: ['saved-presets'] });
      queryClient.invalidateQueries({ queryKey: ['presets-stats'] });
      queryClient.invalidateQueries({ queryKey: ['my-presets'] });
    },
    onError: (error: any) => {
      setSaveError(
        translateApiError(
          t,
          error?.response?.data?.detail,
          t('qrScanResult.saveError'),
        ),
      );
    },
  });

  const inventoryQuery = useQuery({
    queryKey: ['spools', 'filament', userId, filament.id],
    queryFn: () => spoolsAPI.listForFilament(filament.id),
    enabled: isAuthenticated,
    staleTime: 30_000,
  });
  const printerLocationsQuery = useQuery({
    queryKey: ['qr-inventory-locations', userId],
    queryFn: physicalPrintersAPI.list,
    enabled: isAuthenticated,
    staleTime: 30_000,
  });
  const matchingSpools = (inventoryQuery.data ?? []).filter(
    (spool) => spool.filament_id === filament.id,
  );
  const availableSpools = matchingSpools.filter(
    (spool) => spool.state === 'active' || spool.state === 'shelf',
  );
  const archivedCount = matchingSpools.filter(
    (spool) => spool.state === 'archived',
  ).length;
  const emptyCount = matchingSpools.filter((spool) => spool.state === 'empty').length;
  const visibleSpools = availableSpools.slice(0, 3);
  const hiddenAvailableCount = availableSpools.length - visibleSpools.length;
  const totalRemaining = availableSpools.reduce(
    (total, spool) => total + Math.max(0, spool.remaining_weight_g),
    0,
  );

  const assignedLocation = (spoolId: number) => {
    for (const printer of printerLocationsQuery.data ?? []) {
      for (const system of printer.material_systems) {
        const slot = system.slots.find(
          (candidate) =>
            candidate.assignment?.active === true
            && candidate.assignment.spool_id === spoolId,
        );
        if (slot) {
          return {
            printer: printer.name,
            slot: slot.label || slot.provider_index + 1,
          };
        }
      }
    }
    return null;
  };

  const spoolLocation = (spool: UserSpool) => {
    const canonicalLocation = assignedLocation(spool.id);
    if (canonicalLocation) {
      return t('qrScanResult.inventoryLocationPrinter', canonicalLocation);
    }
    const currentLocation = getSpoolCurrentLocation(spool.extra);
    if (currentLocation) {
      return t('qrScanResult.inventoryLocationPrinter', {
        printer: currentLocation.printer,
        slot: currentLocation.gate + 1,
      });
    }
    return t(`profilePage.spoolState.${spool.state}`);
  };

  const filamentTitle = [filament.brand_name, filament.name]
    .filter(Boolean)
    .join(' · ');
  const selectedPresetType = recommendedItem
    ? (selectedPreset?.is_official ? 'official' : 'community')
    : result.preset_type ?? (selectedPreset?.is_official ? 'official' : 'community');

  return (
    <ModalOverlay
      onClose={onClose}
      closeOnOverlayClick={!saveMutation.isPending}
      closeOnEscape={!saveMutation.isPending}
      className="!bg-black/65"
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="qr-scan-result-title"
        className="max-h-[calc(100vh-2rem)] w-full max-w-xl overflow-y-auto rounded-2xl border border-white/15 bg-slate-950 p-4 shadow-2xl shadow-black/60 sm:p-5"
      >
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 id="qr-scan-result-title" className="truncate text-xl font-semibold text-white">
              {filamentTitle}
            </h2>
            <div className="mt-2 flex flex-wrap gap-1.5 text-xs text-slate-300">
              {filament.color_name && (
                <span className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5">
                  {filament.color_name}
                </span>
              )}
              <span className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5">
                {filament.material_type}
              </span>
            </div>
            <p className="mt-2 text-xs text-slate-500">
              {t('qrScanResult.productVariantHint')}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={saveMutation.isPending}
            aria-label={t('qrScanResult.close')}
            className="rounded-lg border border-white/10 p-2 text-slate-400 transition hover:bg-white/10 hover:text-white disabled:opacity-50"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="mt-3 rounded-xl border border-blue-400/15 bg-blue-400/[0.06] p-3.5">
          <div className="flex items-start gap-3">
            <Boxes className="mt-0.5 h-5 w-5 shrink-0 text-blue-300" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-white">
                {t('qrScanResult.inventoryTitle')}
              </p>
              {!isAuthenticated ? (
                <p className="mt-1 text-sm text-slate-400">
                  {t('qrScanResult.inventoryLoginHint')}
                </p>
              ) : inventoryQuery.isPending ? (
                <p className="mt-2 flex items-center gap-2 text-sm text-slate-400">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {t('qrScanResult.inventoryLoading')}
                </p>
              ) : inventoryQuery.isError ? (
                <p className="mt-2 rounded-lg border border-amber-400/25 bg-amber-400/10 px-3 py-2 text-xs text-amber-100">
                  {t('qrScanResult.inventoryLoadError')}
                </p>
              ) : (
                <>
                  <p className="mt-1 text-sm text-slate-300">
                    {matchingSpools.length === 0
                      ? t('qrScanResult.inventoryNone')
                      : availableSpools.length === 0
                        ? t('qrScanResult.inventoryNoAvailable')
                        : availableSpools.length === 1
                          ? t('qrScanResult.inventoryOne')
                          : t('qrScanResult.inventoryMany', {
                              count: availableSpools.length,
                            })}
                  </p>
                  {availableSpools.length > 0 && (
                    <p className="mt-1 text-xs text-blue-200">
                      {t('qrScanResult.inventoryRemainingTotal', {
                        weight: Math.round(totalRemaining),
                      })}
                    </p>
                  )}
                  {visibleSpools.length > 0 && (
                    <div className="mt-2.5 space-y-1.5">
                      {visibleSpools.map((spool) => (
                        <div
                          key={spool.id}
                          data-testid={`qr-inventory-spool-${spool.id}`}
                          className="rounded-lg border border-white/10 bg-black/15 px-3 py-2"
                        >
                          <div className="flex items-center justify-between gap-3 text-xs">
                            <span className="font-medium text-slate-200">
                              {t('qrScanResult.inventorySpoolLabel', { id: spool.id })}
                            </span>
                            <span className="shrink-0 text-blue-200">
                              {t('qrScanResult.inventoryRemaining', {
                                weight: Math.round(spool.remaining_weight_g),
                              })}
                            </span>
                          </div>
                          <p className="mt-1 flex items-center gap-1.5 text-xs text-slate-400">
                            <MapPin className="h-3.5 w-3.5 shrink-0" />
                            <span className="truncate">{spoolLocation(spool)}</span>
                          </p>
                        </div>
                      ))}
                    </div>
                  )}
                  {(archivedCount > 0 || emptyCount > 0) && (
                    <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-400">
                      {archivedCount > 0 && (
                        <span>{t('qrScanResult.inventoryArchived', { count: archivedCount })}</span>
                      )}
                      {emptyCount > 0 && (
                        <span>{t('qrScanResult.inventoryEmpty', { count: emptyCount })}</span>
                      )}
                    </div>
                  )}
                  {hiddenAvailableCount > 0 && (
                    <p className="mt-2 text-xs text-slate-400">
                      {t('qrScanResult.inventoryMore', { count: hiddenAvailableCount })}
                    </p>
                  )}
                  {matchingSpools.length > 0 && onOpenSpools && (
                    <button
                      type="button"
                      onClick={onOpenSpools}
                      className="mt-3 inline-flex items-center gap-2 text-sm text-blue-300 transition hover:text-blue-200"
                    >
                      <ExternalLink className="h-4 w-4" />
                      {t('qrScanResult.openSpools')}
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        </div>

        <div className="mt-3 rounded-xl border border-white/10 bg-white/[0.04] p-3.5">
          <div className="flex items-start gap-3">
            <Library className="mt-0.5 h-5 w-5 shrink-0 text-purple-300" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-white">
                {t('qrScanResult.presetTitle')}
              </p>
              {isAuthenticated && (
                <div className="mt-2">
                  <PrinterConfigurationSelect
                    options={configurationRecommendation.options}
                    selectedKey={configurationRecommendation.selectedKey}
                    onChange={configurationRecommendation.select}
                    isLoading={configurationRecommendation.isLoadingOptions}
                    isError={configurationRecommendation.isOptionsError}
                    compact
                  />
                </div>
              )}
              {hasConfiguration && configurationRecommendation.isLoadingRecommendation ? (
                <p className="mt-2 flex items-center gap-2 text-sm text-slate-400">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {t('filamentDetailPage.loadingPresets')}
                </p>
              ) : !selectedPreset ? (
                <p className="mt-1 text-sm text-slate-400">
                  {t('qrScanResult.noPreset')}
                </p>
              ) : (
                <>
                  <div className="mt-1 flex min-w-0 flex-wrap items-center gap-2">
                    <p className="min-w-0 truncate text-sm text-slate-200">
                      {selectedPreset.name}
                    </p>
                    <span className="shrink-0 rounded-full border border-purple-400/20 bg-purple-400/10 px-2 py-0.5 text-[11px] text-purple-200">
                      {selectedPresetType === 'official'
                        ? t('qrScanResult.presetSourceOfficial')
                        : t('qrScanResult.presetSourceCommunity')}
                    </span>
                  </div>
                  {recommendedItem && configurationRecommendation.printerName && (
                    <PresetRecommendationEvidence
                      recommendation={recommendedItem}
                      printerName={configurationRecommendation.printerName}
                    />
                  )}
                  {presetSaved ? (
                    <div className="mt-2 flex items-start gap-2 text-sm text-emerald-300">
                      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
                      <div>
                        <p>{t('qrScanResult.presetSaved')}</p>
                        <p className="mt-0.5 text-xs text-slate-400">
                          {presetSyncEnabled
                            ? t('qrScanResult.syncOn')
                            : t('qrScanResult.syncOff')}
                        </p>
                      </div>
                    </div>
                  ) : isAuthenticated ? (
                    <button
                      type="button"
                      onClick={() => saveMutation.mutate()}
                      disabled={saveMutation.isPending}
                      className="mt-2 inline-flex items-center gap-2 rounded-lg bg-purple-500 px-3 py-1.5 text-sm font-semibold text-white transition hover:bg-purple-400 disabled:opacity-50"
                    >
                      {saveMutation.isPending ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Library className="h-4 w-4" />
                      )}
                      {saveMutation.isPending
                        ? t('qrScanResult.savingPreset')
                        : t('qrScanResult.savePreset')}
                    </button>
                  ) : (
                    <p className="mt-2 text-sm text-slate-400">
                      {t('qrScanResult.loginHint')}
                    </p>
                  )}
                </>
              )}
              {saveError && (
                <p className="mt-2 rounded-lg border border-red-400/25 bg-red-400/10 px-3 py-2 text-xs text-red-200">
                  {saveError}
                </p>
              )}
            </div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap justify-end gap-2">
          {!isAuthenticated && onRequestLogin && (
            <button
              type="button"
              onClick={onRequestLogin}
              className="mr-auto inline-flex items-center gap-2 rounded-lg border border-white/15 px-3 py-2 text-sm text-slate-200 transition hover:bg-white/10"
            >
              <LogIn className="h-4 w-4" />
              {t('qrScanResult.login')}
            </button>
          )}
          {onOpenMaterial && (
            <button
              type="button"
              onClick={onOpenMaterial}
              className="inline-flex items-center gap-2 rounded-lg border border-white/15 px-3 py-2 text-sm text-slate-200 transition hover:bg-white/10"
            >
              <ExternalLink className="h-4 w-4" />
              {t('qrScanResult.openMaterial')}
            </button>
          )}
          {isAuthenticated && onAddSpool && (
            <>
              <button
                type="button"
                onClick={() => onAddSpool('shelf')}
                className="inline-flex items-center gap-2 rounded-lg border border-blue-400/30 px-3 py-2 text-sm font-semibold text-blue-200 transition hover:bg-blue-400/10"
              >
                <PackagePlus className="h-4 w-4" />
                {t('qrScanResult.addToShelf')}
              </button>
              <button
                type="button"
                onClick={() => onAddSpool('printer')}
                className="inline-flex items-center gap-2 rounded-lg bg-blue-500 px-3 py-2 text-sm font-semibold text-white transition hover:bg-blue-400"
              >
                <Printer className="h-4 w-4" />
                {t('qrScanResult.installInPrinter')}
              </button>
            </>
          )}
          {onContinue && (
            <button
              type="button"
              onClick={onContinue}
              className="inline-flex items-center gap-2 rounded-lg bg-cyan-500 px-3 py-2 text-sm font-semibold text-slate-950 transition hover:bg-cyan-300"
            >
              <PackagePlus className="h-4 w-4" />
              {continueLabel ?? t('qrScanResult.continue')}
            </button>
          )}
        </div>
      </section>
    </ModalOverlay>
  );
}
