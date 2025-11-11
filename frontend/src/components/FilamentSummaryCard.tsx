import { Filament } from '../types/api';
import { FilamentPreview } from './FilamentPreview';

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
  } = filament;

  const detailItems: DetailItem[] = [
    { label: 'Производитель', value: brand_name },
    { label: 'Цвет', value: color_name },
    { label: 'Диаметр', value: diameter !== null && diameter !== undefined ? `${diameter} мм` : null },
    { label: 'Плотность', value: density !== null && density !== undefined ? `${density} g/cm³` : null },
    { label: 'Стоимость', value: price_per_kg !== null && price_per_kg !== undefined ? `${price_per_kg} ₽/кг` : null },
    { label: 'Вес катушки', value: spool_weight !== null && spool_weight !== undefined ? `${spool_weight} г` : null },
  ];

  return (
    <div className={`px-4 pt-4 pb-4 bg-white/5 rounded-xl border border-white/10 ${className}`}>
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="w-28 h-20 rounded-2xl border border-white/20 bg-black/15 flex items-center justify-center overflow-hidden p-2">
            <FilamentPreview
              colorHex={color_hex || '#FF0000'}
              visualSettings={visual_settings}
              size="small"
            />
          </div>
          <div>
            <h4 className="text-lg font-bold text-white leading-tight">
              {name}
            </h4>
            {color_name && (
              <p className="text-sm text-gray-300">{color_name}</p>
            )}
          </div>
        </div>
        {material_type && (
          <span className="inline-flex px-3 py-1 bg-purple-600/80 rounded-lg text-white text-sm font-medium self-start lg:self-auto">
            {material_type}
          </span>
        )}
      </div>

      <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 text-sm">
        {detailItems.map((item) => (
          item.value && (
            <div key={item.label} className="flex flex-col">
              <span className="text-gray-400 text-xs mb-0.5">{item.label}</span>
              <span className="text-white font-medium">{item.value}</span>
            </div>
          )
        ))}

        {color_hex && (
          <div className="flex flex-col">
            <span className="text-gray-400 text-xs mb-0.5">HEX цвет</span>
            <div className="flex items-center space-x-2">
              <span className="text-white font-medium text-sm">{color_hex}</span>
              <span
                className="w-5 h-5 rounded border border-white/20"
                style={{ backgroundColor: color_hex }}
              />
            </div>
          </div>
        )}
      </div>

      {showDescription && description && (
        <p className="mt-3 text-sm text-gray-300 whitespace-pre-line">{description}</p>
      )}
    </div>
  );
};


