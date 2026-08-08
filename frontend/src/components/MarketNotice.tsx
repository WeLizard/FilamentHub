/** Country-specific catalog status and product data. */

import { useTranslation } from 'react-i18next';
import { MapPin, ExternalLink } from 'lucide-react';

import { countryName } from '../utils/countries';
import { externalUrl } from '../utils/externalUrl';
import type { Filament } from '../types/api';

interface MarketNoticeProps {
  filament: Filament;
  compact?: boolean;
}

/**
 * Цена из ячейки подписывается как рекомендованная для рынка: FilamentHub не
 * магазин, и выдавать её за предложение продавца нельзя.
 */
export const MarketNotice: React.FC<MarketNoticeProps> = ({ filament, compact = false }) => {
  const { t, i18n } = useTranslation();

  if (!filament.market_country) {
    return null;
  }

  const country = countryName(filament.market_country, i18n.language);
  const status = filament.market_availability === 'unavailable'
    ? 'discontinued'
    : filament.market_availability;
  const statusText = status === 'discontinued'
    ? t('market.discontinuedIn', { country })
    : status === 'coming_soon'
      ? t('market.comingSoonIn', { country })
      : t('market.dataFor', { country });
  const link = externalUrl(filament.product_url);

  if (compact) {
    return (
      <span
        title={statusText}
        className={`inline-flex items-center gap-1 whitespace-nowrap text-xs ${
          status === 'discontinued' ? 'text-amber-300' : 'text-gray-400'
        }`}
      >
        <MapPin className="h-3 w-3 shrink-0" />
        {country}
      </span>
    );
  }

  return (
    <div className="mt-3 rounded-xl border border-white/10 bg-white/[0.04] p-3 text-sm">
      <div className="flex items-center gap-2 text-gray-300">
        <MapPin className="h-4 w-4 text-emerald-300" />
        <span>
          {statusText}
        </span>
      </div>
      {filament.market_note && (
        <p className="mt-2 text-xs leading-5 text-gray-400">{filament.market_note}</p>
      )}
      {link && (
        <a
          href={link}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-flex items-center gap-1 text-xs text-purple-300 hover:text-purple-200"
        >
          <ExternalLink className="h-3 w-3" />
          {t('filamentMarket.productUrl')}
        </a>
      )}
    </div>
  );
};
