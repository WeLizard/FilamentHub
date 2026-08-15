import { Archive, ArchiveX, Droplets } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { Filament } from '../types/api';

interface FilamentHandlingBadgesProps {
  filament: Pick<Filament,
    | 'drying_required'
    | 'drying_temperature_c'
    | 'drying_duration_hours'
    | 'enclosure_requirement'
    | 'chamber_temperature_c'
  >;
  compact?: boolean;
  className?: string;
}

export function FilamentHandlingBadges({
  filament,
  compact = false,
  className = '',
}: FilamentHandlingBadgesProps) {
  const { t } = useTranslation();
  const enclosure = filament.enclosure_requirement;

  if (!filament.drying_required && !enclosure) {
    return null;
  }

  const badgeClass = compact
    ? 'gap-1 px-2 py-0.5 text-[10px] sm:text-xs'
    : 'gap-1.5 px-3 py-1 text-xs';

  return (
    <div className={`flex flex-wrap items-center gap-2 ${className}`}>
      {filament.drying_required && (
        <span className={`inline-flex items-center rounded-full border border-sky-400/30 bg-sky-500/15 font-medium text-sky-200 ${badgeClass}`}>
          <Droplets className="h-3.5 w-3.5" />
          {filament.drying_temperature_c != null && filament.drying_duration_hours != null
            ? t('filamentHandling.dryingRequiredWithParameters', {
                temperature: filament.drying_temperature_c,
                duration: filament.drying_duration_hours,
              })
            : t('filamentHandling.dryingRequired')}
        </span>
      )}
      {enclosure && (
        <span className={`inline-flex items-center rounded-full border font-medium ${enclosure === 'none'
          ? 'border-emerald-400/30 bg-emerald-500/15 text-emerald-100'
          : 'border-amber-400/30 bg-amber-500/15 text-amber-100'} ${badgeClass}`}>
          {enclosure === 'none'
            ? <ArchiveX className="h-3.5 w-3.5" />
            : <Archive className="h-3.5 w-3.5" />}
          {enclosure === 'active' && filament.chamber_temperature_c != null
            ? t('filamentHandling.activeEnclosureWithTemperature', {
                temperature: filament.chamber_temperature_c,
              })
            : t(`filamentHandling.enclosure.${enclosure}`)}
        </span>
      )}
    </div>
  );
}
