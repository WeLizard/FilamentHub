/** Секция каталога: пресеты, рекомендованные под принтер пользователя. */

import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Sparkles, Thermometer } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { presetsAPI } from '../api/client';
import type { PresetMatchReason } from '../types/api';
import type { PrinterSelection } from '../hooks/usePrinterSelection';

interface RecommendedForPrinterSectionProps {
  selection: PrinterSelection;
  savedPresetIds: Set<number>;
  onSavePreset: (presetId: number) => void;
}

const REASON_STYLE: Record<PresetMatchReason, string> = {
  exact_match: 'bg-green-500/20 text-green-200 border-green-500/30',
  same_model: 'bg-green-500/20 text-green-200 border-green-500/30',
  same_family: 'bg-blue-500/20 text-blue-200 border-blue-500/30',
  same_manufacturer: 'bg-white/10 text-gray-300 border-white/20',
  compatible_specs: 'bg-white/10 text-gray-300 border-white/20',
};

export const RecommendedForPrinterSection: React.FC<RecommendedForPrinterSectionProps> = ({
  selection,
  savedPresetIds,
  onSavePreset,
}) => {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();

  const profileId = selection.printerProfileId;

  const { data, isLoading, isError } = useQuery({
    queryKey: ['recommended-for-configuration', profileId, selection.physicalPrinterId],
    queryFn: () =>
      presetsAPI.getRecommendedForConfiguration({
        printer_profile_id: profileId as number,
        physical_printer_id: selection.physicalPrinterId,
      }),
    enabled: !!profileId,
    retry: false,
  });

  // Секция показывается только при выбранной конфигурации. Сам выбор
  // принтера/конфигурации живёт в PrinterConfigPicker.
  if (!user || !profileId) return null;
  // Не прячем ошибку молча: выбранная конфигурация могла стать недоступной.
  if (isError) {
    return (
      <section className="bg-white/5 border border-white/10 rounded-xl sm:rounded-2xl p-4 sm:p-5">
        <p className="text-sm text-amber-300/80">{t('recommendedForPrinter.loadError')}</p>
      </section>
    );
  }
  if (isLoading || !data || data.items.length === 0) return null;

  return (
    <section className="bg-white/5 border border-white/10 rounded-xl sm:rounded-2xl p-4 sm:p-5">
      <div className="flex items-center gap-2 mb-3 sm:mb-4">
        <Sparkles className="w-4 h-4 sm:w-5 sm:h-5 text-purple-300" />
        <h3 className="text-sm sm:text-base font-semibold text-white">
          {t('recommendedForPrinter.title', { printer: data.printer_name })}
        </h3>
      </div>

      <div className="flex gap-3 sm:gap-4 overflow-x-auto snap-x snap-mandatory pb-2 -mx-1 px-1">
        {data.items.map(({ preset, match_reason }) => {
          const isSaved = savedPresetIds.has(preset.id);
          return (
            <div
              key={preset.id}
              className="snap-start flex-shrink-0 w-[220px] sm:w-[240px] bg-white/5 border border-white/10 rounded-lg p-3 sm:p-4 flex flex-col gap-2 hover:bg-white/10 transition-colors"
            >
              <span
                className={`self-start px-2 py-0.5 text-[10px] sm:text-xs rounded-full border ${REASON_STYLE[match_reason]}`}
              >
                {t(`recommendedForPrinter.badge.${match_reason}`)}
              </span>

              <button
                type="button"
                onClick={() => preset.filament_id && navigate(`/filaments/${preset.filament_id}`)}
                disabled={!preset.filament_id}
                className="text-left text-sm font-semibold text-white hover:text-purple-300 transition-colors truncate disabled:cursor-default"
                title={preset.name}
              >
                {preset.name}
              </button>

              <div className="flex items-center gap-3 text-[11px] sm:text-xs text-gray-300">
                <span className="flex items-center gap-1">
                  <Thermometer className="w-3 h-3 text-orange-300" />
                  {Math.round(preset.extruder_temp)}°
                </span>
                <span className="flex items-center gap-1">
                  <Thermometer className="w-3 h-3 text-blue-300" />
                  {Math.round(preset.bed_temp)}°
                </span>
                {preset.rating ? (
                  <span className="text-white font-medium">★ {preset.rating.toFixed(1)}</span>
                ) : null}
              </div>

              <button
                type="button"
                onClick={() => onSavePreset(preset.id)}
                disabled={isSaved}
                className="mt-auto px-3 py-1.5 rounded-lg border border-white/20 text-xs text-white hover:bg-white/10 transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {isSaved ? t('catalogPage.addedToProfile') : `+ ${t('catalogPage.addToProfile')}`}
              </button>
            </div>
          );
        })}
      </div>
    </section>
  );
};
