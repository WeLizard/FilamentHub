/** Что сказать читателю про его рынок — и о чём промолчать. */

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
 * Три состояния, но показывать можно только два.
 *
 * Ячейки нет — мы не знаем, продаётся ли товар в этой стране, и молчим: написать
 * «в вашей стране не продаётся», не имея данных, значит утверждать факт, которого
 * у нас нет. Прямое «не продаётся» показываем, потому что это чьё-то заявление.
 *
 * Цена из ячейки подписывается как рекомендованная для рынка: FilamentHub не
 * магазин, и выдавать её за предложение продавца нельзя.
 */
export const MarketNotice: React.FC<MarketNoticeProps> = ({ filament, compact = false }) => {
  const { t, i18n } = useTranslation();

  if (!filament.market_country) {
    return null;
  }

  const country = countryName(filament.market_country, i18n.language);
  const unavailable = filament.market_availability === 'unavailable';
  const link = externalUrl(filament.product_url);

  if (compact) {
    return (
      <span
        className={`inline-flex items-center gap-1 text-xs ${
          unavailable ? 'text-amber-300' : 'text-gray-400'
        }`}
      >
        <MapPin className="h-3 w-3" />
        {unavailable ? t('market.notSoldIn', { country }) : t('market.priceFor', { country })}
      </span>
    );
  }

  return (
    <div className="mt-3 rounded-xl border border-white/10 bg-white/[0.04] p-3 text-sm">
      <div className="flex items-center gap-2 text-gray-300">
        <MapPin className="h-4 w-4 text-emerald-300" />
        <span>
          {unavailable ? t('market.notSoldIn', { country }) : t('market.priceFor', { country })}
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
          {t('market.whereToBuy')}
        </a>
      )}
    </div>
  );
};
