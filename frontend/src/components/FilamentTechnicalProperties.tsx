import { Gauge } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { FilamentTechnicalProperty } from '../types/api';
import {
  TECHNICAL_CATEGORY_ORDER,
  TECHNICAL_PROPERTY_CATEGORIES,
  formatTechnicalValue,
  sortTechnicalProperties,
  technicalConditions,
  technicalPropertyKey,
} from '../utils/technicalProperties';

interface FilamentTechnicalPropertiesProps {
  properties: FilamentTechnicalProperty[];
  className?: string;
}

/** Data-sheet measurements grouped as manufacturers publish them. */
export function FilamentTechnicalProperties({ properties, className = '' }: FilamentTechnicalPropertiesProps) {
  const { t, i18n } = useTranslation();
  if (properties.length === 0) return null;
  const locale = i18n.language;
  const sorted = sortTechnicalProperties(properties);
  const groups = TECHNICAL_CATEGORY_ORDER
    .map(category => ({
      category,
      items: sorted.filter(item => (TECHNICAL_PROPERTY_CATEGORIES[item.code] ?? 'physical') === category),
    }))
    .filter(group => group.items.length > 0);

  return (
    <section
      aria-labelledby="filament-technical-properties-title"
      className={`rounded-xl border border-white/10 bg-white/5 p-3 md:p-4 ${className}`}
    >
      <h2 id="filament-technical-properties-title" className="mb-2 flex items-center gap-2 text-sm font-semibold text-white">
        <Gauge className="h-4 w-4 text-amber-300" />
        {t('technicalProperties.title')}
      </h2>
      <div className="grid gap-x-8 gap-y-3 md:grid-cols-2">
        {groups.map(group => (
          <div key={group.category}>
            <h3 className="mb-1 text-[11px] font-medium uppercase tracking-wide text-gray-400">
              {t(`technicalProperties.categories.${group.category}`)}
            </h3>
            <dl className="divide-y divide-white/[0.06]">
              {group.items.map(item => {
                const conditions = technicalConditions(item, t, locale);
                return (
                  <div key={technicalPropertyKey(item)} className="flex items-baseline justify-between gap-3 py-1.5">
                    <dt className="min-w-0 text-sm text-gray-300">
                      {t(`technicalProperties.codes.${item.code}`, { defaultValue: item.code.replaceAll('_', ' ') })}
                      {(conditions.length > 0 || item.standard) && (
                        <span className="block text-[11px] leading-4 text-gray-400">
                          {[...conditions, item.standard].filter(Boolean).join(' · ')}
                        </span>
                      )}
                    </dt>
                    <dd className="shrink-0 whitespace-nowrap text-sm font-medium tabular-nums text-white">
                      {formatTechnicalValue(item, locale)}
                    </dd>
                  </div>
                );
              })}
            </dl>
          </div>
        ))}
      </div>
    </section>
  );
}
