import { FlaskConical, Sparkles } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { Filament } from '../types/api';
import { FilamentHandlingBadges } from './FilamentHandlingBadges';
import { ChemicalSafetyNotice } from './ChemicalSafetyNotice';

interface FilamentHandlingDetailsProps {
  filament: Filament;
  className?: string;
}

export function FilamentHandlingDetails({ filament, className = '' }: FilamentHandlingDetailsProps) {
  const { t } = useTranslation();
  const adhesives = filament.bed_adhesives ?? [];
  const chemicals = filament.post_processing_chemicals ?? [];
  const hasRequirements = Boolean(filament.drying_required || filament.enclosure_requirement);

  if (!hasRequirements && adhesives.length === 0 && chemicals.length === 0) {
    return null;
  }

  return (
    <section className={`rounded-2xl border border-white/10 bg-white/[0.05] p-5 ${className}`}>
      <h2 className="text-lg font-semibold text-white">{t('filamentHandling.title')}</h2>
      <FilamentHandlingBadges filament={filament} className="mt-3" />

      {adhesives.length > 0 && (
        <div className="mt-4 flex gap-3">
          <Sparkles className="mt-0.5 h-5 w-5 shrink-0 text-violet-300" />
          <div>
            <h3 className="text-sm font-medium text-gray-200">{t('filamentHandling.bedAdhesives')}</h3>
            <p className="mt-1 text-sm leading-6 text-gray-300">{adhesives.join(' · ')}</p>
          </div>
        </div>
      )}

      {chemicals.length > 0 && (
        <div className="mt-4">
          <div className="flex items-center gap-2">
            <FlaskConical className="h-5 w-5 text-cyan-300" />
            <h3 className="text-sm font-medium text-gray-200">{t('filamentHandling.chemicals')}</h3>
          </div>
          <div className="mt-2 grid gap-2 md:grid-cols-2">
            {chemicals.map((chemical, index) => (
              <div
                key={`${chemical.name}-${index}`}
                className={`rounded-xl border p-3 ${chemical.hazardous
                  ? 'border-rose-400/30 bg-rose-500/10'
                  : 'border-white/10 bg-black/10'}`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-white">{chemical.name}</span>
                  {chemical.hazardous && (
                    <span className="rounded-full border border-rose-400/30 bg-rose-500/15 px-2 py-0.5 text-[10px] font-medium text-rose-200">
                      {t('filamentHandling.hazardous')}
                    </span>
                  )}
                </div>
                {chemical.purpose && <p className="mt-1 text-sm text-gray-300">{chemical.purpose}</p>}
                {chemical.safety_note && (
                  <p className="mt-2 text-xs leading-5 text-amber-100">{chemical.safety_note}</p>
                )}
              </div>
            ))}
          </div>
          <ChemicalSafetyNotice />
        </div>
      )}
    </section>
  );
}
