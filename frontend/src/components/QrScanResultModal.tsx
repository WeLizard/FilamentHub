import { useEffect, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  CheckCircle2,
  ExternalLink,
  Library,
  Loader2,
  LogIn,
  PackagePlus,
  X,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { savedPresetsAPI, type QrScanResponse } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { ModalOverlay } from './ModalOverlay';

interface QrScanResultModalProps {
  result: QrScanResponse;
  isAuthenticated: boolean;
  onClose: () => void;
  onOpenMaterial?: () => void;
  onAddSpool?: () => void;
  onContinue?: () => void;
  continueLabel?: string;
  onRequestLogin?: () => void;
}

export function QrScanResultModal({
  result,
  isAuthenticated,
  onClose,
  onOpenMaterial,
  onAddSpool,
  onContinue,
  continueLabel,
  onRequestLogin,
}: QrScanResultModalProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [presetSaved, setPresetSaved] = useState(result.preset_saved === true);
  const [presetSyncEnabled, setPresetSyncEnabled] = useState(
    result.preset_sync_enabled,
  );
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    setPresetSaved(result.preset_saved === true);
    setPresetSyncEnabled(result.preset_sync_enabled);
    setSaveError(null);
  }, [result]);

  const saveMutation = useMutation({
    mutationFn: () => savedPresetsAPI.save(result.preset!.id, false),
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

  const filament = result.filament;
  const filamentTitle = [filament.brand_name, filament.name]
    .filter(Boolean)
    .join(' · ');

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
        className="w-full max-w-xl rounded-2xl border border-white/15 bg-slate-950 p-5 shadow-2xl shadow-black/60 sm:p-6"
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-cyan-300">
              {t('qrScanResult.recognized')}
            </p>
            <h2 id="qr-scan-result-title" className="mt-2 text-xl font-semibold text-white">
              {t('qrScanResult.title')}
            </h2>
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

        <div className="mt-5 rounded-2xl border border-cyan-400/20 bg-cyan-400/10 p-4">
          <p className="text-xs text-cyan-200">{t('qrScanResult.exactVariant')}</p>
          <p className="mt-1 text-lg font-semibold text-white">{filamentTitle}</p>
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-300">
            {filament.color_name && (
              <span className="rounded-full border border-white/10 bg-black/20 px-2.5 py-1">
                {filament.color_name}
              </span>
            )}
            <span className="rounded-full border border-white/10 bg-black/20 px-2.5 py-1">
              {filament.material_type}
            </span>
          </div>
          <p className="mt-3 text-xs leading-5 text-slate-400">
            {t('qrScanResult.productVariantHint')}
          </p>
        </div>

        <div className="mt-4 rounded-2xl border border-white/10 bg-white/[0.04] p-4">
          <div className="flex items-start gap-3">
            <Library className="mt-0.5 h-5 w-5 shrink-0 text-purple-300" />
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-white">
                {t('qrScanResult.officialPreset')}
              </p>
              {!result.preset ? (
                <p className="mt-1 text-sm text-slate-400">
                  {t('qrScanResult.noOfficialPreset')}
                </p>
              ) : (
                <>
                  <p className="mt-1 truncate text-sm text-slate-200">
                    {result.preset.name}
                  </p>
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
                      className="mt-3 inline-flex items-center gap-2 rounded-lg bg-purple-500 px-3 py-2 text-sm font-semibold text-white transition hover:bg-purple-400 disabled:opacity-50"
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

        <div className="mt-5 flex flex-wrap justify-end gap-2">
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
            <button
              type="button"
              onClick={onAddSpool}
              className="inline-flex items-center gap-2 rounded-lg bg-blue-500 px-3 py-2 text-sm font-semibold text-white transition hover:bg-blue-400"
            >
              <PackagePlus className="h-4 w-4" />
              {t('qrScanResult.addSpool')}
            </button>
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
