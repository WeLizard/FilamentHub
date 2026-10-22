import { useTranslation } from 'react-i18next';
import type { FilamentAdditionalProperty } from '../types/api';
import { externalUrl, externalUrlHost } from '../utils/externalUrl';

interface FilamentAdditionalPropertiesProps {
  properties: FilamentAdditionalProperty[];
}

/** Compact public display for administrator-approved manufacturer facts. */
export function FilamentAdditionalProperties({ properties }: FilamentAdditionalPropertiesProps) {
  const { t } = useTranslation();
  if (properties.length === 0) return null;

  return (
    <section
      aria-labelledby="filament-additional-properties-title"
      className="rounded-xl border border-white/10 bg-white/5 p-3 md:p-4"
    >
      <h2 id="filament-additional-properties-title" className="mb-1 text-sm font-semibold text-white">
        {t('filamentDetailPage.additionalProperties')}
      </h2>
      <dl className="divide-y divide-white/10">
        {properties.map((property, index) => (
          <div key={`${property.property_name}-${index}`} className="grid gap-1 py-2 sm:grid-cols-[minmax(8rem,0.4fr)_minmax(0,1fr)] sm:gap-3">
            <dt className="break-words text-xs font-medium text-gray-400 sm:text-sm">{property.property_name}</dt>
            <dd className="min-w-0 break-words text-sm text-gray-100">
              <p className="whitespace-pre-line">{property.value_summary}</p>
              <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
                {property.kind === 'inferred' && (
                  <span className="text-gray-400">{t('filamentDetailPage.inferredFromManufacturer')}</span>
                )}
                {property.source_urls.map((rawUrl, sourceIndex) => {
                  const href = externalUrl(rawUrl);
                  if (!href) return null;
                  return (
                    <a
                      key={`${href}-${sourceIndex}`}
                      href={href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex max-w-full items-center gap-1 break-all text-cyan-300 underline decoration-cyan-300/40 underline-offset-2 hover:text-cyan-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-300"
                    >
                      <span>{t('filamentDetailPage.manufacturerSource')}</span>
                      <span className="text-gray-400">({externalUrlHost(href)})</span>
                    </a>
                  );
                })}
              </div>
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
