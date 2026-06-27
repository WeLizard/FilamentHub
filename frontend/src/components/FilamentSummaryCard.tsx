import { useTranslation } from 'react-i18next';
import { Filament } from '../types/api';
import { FilamentPreview } from './FilamentPreview';
import { currencySymbol } from '../utils/currency';

interface FilamentSummaryCardProps {
  filament: Filament;
  className?: string;
  showDescription?: boolean;
}

interface DetailItem {
  label: string;
  value: string | null;
  unit?: string;
}

export const FilamentSummaryCard: React.FC<FilamentSummaryCardProps> = ({
  filament,
  className = '',
  showDescription = true,
}) => {
  const { t } = useTranslation();
  const {
    name,
    color_name,
    color_hex,
    material_type,
    brand_name,
    diameter,
    density,
    price_per_kg,
    spool_weight,
    description,
    visual_settings,
    currency,
  } = filament;

  const detailItems: DetailItem[] = [
    { label: t('filamentSummary.diameter'), value: diameter !== null && diameter !== undefined ? `${diameter} ${t('filamentSummary.mm')}` : null },
    { label: t('filamentSummary.density'), value: density !== null && density !== undefined ? `${density} ${t('filamentSummary.g')}/${t('filamentSummary.cm3')}` : null },
    { label: t('filamentSummary.cost'), value: price_per_kg !== null && price_per_kg !== undefined ? `${price_per_kg} ${currencySymbol(currency)}/${t('filamentSummary.kg')}` : null },
    { label: t('filamentSummary.spoolWeight'), value: spool_weight !== null && spool_weight !== undefined ? `${spool_weight} ${t('filamentSummary.g')}` : null },
  ];

  return (
    <div className={`px-4 pt-4 pb-4 bg-white/5 rounded-xl border border-white/10 ${className}`}>
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="flex items-center justify-center p-1">
            <FilamentPreview
              colorHex={color_hex || '#FF0000'}
              visualSettings={visual_settings}
              size="small"
            />
          </div>
          <div className="flex flex-col gap-0.5">
            <h4 className="text-lg font-bold text-white leading-tight">
              {name}
            </h4>
            {(color_name || color_hex) && (
              <p className="text-sm text-gray-300">
                {color_name ?? t('filamentSummary.noColor')}
                {color_hex && ' | '}
                {color_hex}
              </p>
            )}
          </div>
        </div>
        {brand_name && (
          <span className="text-base text-gray-200 font-semibold self-start lg:self-center">
            {brand_name}
          </span>
        )}
        {material_type && (
          <span className="inline-flex px-3 py-1 bg-purple-600/80 rounded-lg text-white text-sm font-medium self-start lg:self-auto">
            {material_type}
          </span>
        )}
      </div>

      <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm justify-center text-center">
        {detailItems.map(
          (item) =>
            item.value && (
              <span key={item.label} className="text-gray-300">
                <span className="text-gray-400">{item.label}:</span> {item.value}
              </span>
            ),
        )}
      </div>

      {showDescription && description && (
        <p className="mt-4 text-sm text-gray-300 whitespace-pre-line">{description}</p>
      )}
    </div>
  );
};


