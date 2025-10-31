/** Страница каталога материалов */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Search,
  Package,
  Star,
  CheckCircle,
  MapPin,
  Settings,
  Users,
  Thermometer,
  Gauge,
  Ruler,
  QrCode,
  LucideIcon,
} from 'lucide-react';
import { filamentsAPI, brandsAPI, presetsAPI } from '../api/client';
import type { Filament, Preset } from '../types/api';

export const CatalogPage: React.FC = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [printerModel, setPrinterModel] = useState('Ender 3 Pro');
  const [materialTypeFilter, setMaterialTypeFilter] = useState<string | null>(null);
  const [brandFilter, setBrandFilter] = useState<number | null>(null);
  const [selectedFilament, setSelectedFilament] = useState<number | null>(null);
  const [showQR, setShowQR] = useState<number | null>(null);

  // Загружаем материалы
  const {
    data: filamentsData,
    isLoading: isLoadingFilaments,
    error: filamentsError,
  } = useQuery({
    queryKey: ['filaments', { material_type: materialTypeFilter, brand_id: brandFilter }],
    queryFn: () =>
      filamentsAPI.list({
        active_only: true,
        material_type: materialTypeFilter || undefined,
        brand_id: brandFilter || undefined,
        page: 1,
        size: 100,
      }),
  });

  // Загружаем бренды для фильтра и отображения
  const { data: brandsData } = useQuery({
    queryKey: ['brands'],
    queryFn: () => brandsAPI.list({ active_only: true, page: 1, size: 100 }),
  });

  // Создаем мапу брендов для быстрого доступа
  const brandsMap = new Map(brandsData?.items.map((b) => [b.id, b]) || []);

  // Фильтруем материалы по поисковому запросу
  const filteredFilaments = filamentsData?.items.filter((filament) => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      filament.name.toLowerCase().includes(query) ||
      filament.material_type.toLowerCase().includes(query) ||
      filament.color_name?.toLowerCase().includes(query)
    );
  }) || [];

  // Получаем уникальные типы материалов для фильтра
  const materialTypes = Array.from(
    new Set(filamentsData?.items.map((f) => f.material_type) || [])
  ).sort();

  if (isLoadingFilaments) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-white text-xl">Загрузка материалов...</div>
      </div>
    );
  }

  if (filamentsError) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-red-400 text-xl">Ошибка загрузки материалов</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Hero Section */}
      <div className="text-center mb-8">
        <h2 className="text-4xl font-bold text-white mb-4">
          Найдите идеальные настройки для вашего пластика
        </h2>
        <p className="text-xl text-gray-300 max-w-3xl mx-auto">
          База данных материалов с официальными пресетами от производителей и проверенными
          настройками от сообщества
        </p>
      </div>

      {/* Search Bar */}
      <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
        <div className="flex flex-col lg:flex-row gap-4">
          <div className="flex-1 relative">
            <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 text-gray-400 w-5 h-5" />
            <input
              type="text"
              placeholder="Поиск по бренду, типу или названию..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-12 pr-4 py-4 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
            />
          </div>

          <select
            value={materialTypeFilter || ''}
            onChange={(e) => setMaterialTypeFilter(e.target.value || null)}
            className="px-4 py-4 bg-white/10 border border-white/20 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all min-w-48"
          >
            <option value="">Все типы</option>
            {materialTypes.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>

          <select
            value={brandFilter || ''}
            onChange={(e) => setBrandFilter(e.target.value ? Number(e.target.value) : null)}
            className="px-4 py-4 bg-white/10 border border-white/20 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all min-w-48"
          >
            <option value="">Все бренды</option>
            {brandsData?.items.map((brand) => (
              <option key={brand.id} value={brand.id}>
                {brand.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Material Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {filteredFilaments.map((filament) => (
          <MaterialCard
            key={filament.id}
            filament={filament}
            brand={brandsMap.get(filament.brand_id)}
            isSelected={selectedFilament === filament.id}
            onSelect={() => setSelectedFilament(selectedFilament === filament.id ? null : filament.id)}
            onShowQR={() => setShowQR(showQR === filament.id ? null : filament.id)}
            showQR={showQR === filament.id}
          />
        ))}
      </div>

      {filteredFilaments.length === 0 && (
        <div className="text-center py-12">
          <Package className="w-16 h-16 text-gray-400 mx-auto mb-4" />
          <p className="text-gray-400 text-xl">Материалы не найдены</p>
        </div>
      )}
    </div>
  );
};

interface MaterialCardProps {
  filament: Filament;
  brand?: import('../types/api').Brand;
  isSelected: boolean;
  onSelect: () => void;
  onShowQR: () => void;
  showQR: boolean;
}

const MaterialCard: React.FC<MaterialCardProps> = ({
  filament,
  brand,
  isSelected,
  onSelect,
  onShowQR,
  showQR,
}) => {
  // Загружаем пресеты для каждого материала всегда
  const { data: presetsData, isLoading: isLoadingPresets } = useQuery({
    queryKey: ['filament-presets', filament.id],
    queryFn: () => filamentsAPI.getPresets(filament.id),
    enabled: true, // Всегда загружаем пресеты
  });

  // Получаем официальный пресет и пресеты сообщества
  const officialPreset = presetsData?.items.find((p) => p.is_official);
  const communityPresets = presetsData?.items.filter((p) => !p.is_official).slice(0, 3);

  // Вычисляем средний рейтинг из пресетов
  const avgRating =
    presetsData?.items && presetsData.items.length > 0
      ? presetsData.items
          .filter((p) => p.rating !== null)
          .reduce((acc, p) => acc + (p.rating || 0), 0) /
        presetsData.items.filter((p) => p.rating !== null).length
      : 4.8;

  // Вычисляем успешность (на основе usage_count и рейтинга)
  const successRate =
    presetsData?.items && presetsData.items.length > 0
      ? Math.min(
          95,
          Math.max(
            85,
            85 +
              (presetsData.items.reduce((acc, p) => acc + p.usage_count, 0) / presetsData.items.length / 10) +
              (avgRating - 4.0) * 10
          )
        )
      : 92;

  return (
    <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 hover:bg-white/15 transition-all duration-300 group shadow-xl">
      {/* Header с названием, ценой и рейтингом */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1">
          <div className="flex items-center space-x-3 mb-2">
            {brand && (
              <span className="text-purple-300 font-semibold">{brand.name}</span>
            )}
            {brand && <span className="text-gray-400">-</span>}
          </div>
          <div className="flex items-center space-x-3 mb-2">
            <h3 className="text-xl font-bold text-white group-hover:text-purple-300 transition-colors">
              {filament.name}
            </h3>
            <span className="px-2 py-1 bg-purple-500/20 text-purple-300 text-xs rounded-full border border-purple-500/30">
              {filament.material_type}
            </span>
          </div>
          <div className="flex items-center space-x-4 text-sm mb-3">
            <span className="flex items-center text-gray-300">
              <Star className="w-4 h-4 mr-1 text-yellow-400 fill-current" />
              <span className="font-semibold text-white">{avgRating.toFixed(1)}</span>
            </span>
            <span className="flex items-center text-gray-300">
              <CheckCircle className="w-4 h-4 mr-1 text-green-400" />
              <span className="font-semibold text-green-400">{Math.round(successRate)}% успеха</span>
            </span>
          </div>
        </div>
        <div className="text-right ml-4">
          <p className="text-3xl font-bold text-green-400 mb-1">
            {filament.price_per_kg ? `${Math.round(filament.price_per_kg)}₽` : '—'}
          </p>
          <p className="text-sm text-gray-400">
            {filament.spool_weight ? `${Math.round(filament.spool_weight)}g` : '—'}
          </p>
        </div>
      </div>

      {/* Описание */}
      {filament.description && (
        <p className="text-gray-300 text-sm mb-4">{filament.description}</p>
      )}

      {/* Детали материала */}
      <div className="grid grid-cols-2 gap-4 mb-4 text-sm">
        {filament.diameter && (
          <div className="flex items-center text-gray-300">
            <span className="font-medium mr-2">Диаметр:</span>
            <span className="text-white">{filament.diameter}mm</span>
          </div>
        )}
        {filament.density && (
          <div className="flex items-center text-gray-300">
            <span className="font-medium mr-2">Плотность:</span>
            <span className="text-white">{filament.density}g/cm³</span>
          </div>
        )}
      </div>

      {/* Color Indicator */}
      {filament.color_hex && (
        <div className="mb-4">
          <div className="flex items-center space-x-2">
            <span className="text-gray-300 text-sm font-medium">Цвет:</span>
            <div
              className="w-6 h-6 rounded-full border-2 border-white/30"
              style={{ backgroundColor: filament.color_hex }}
            ></div>
            <span className="text-white text-sm">{filament.color_name || '—'}</span>
          </div>
        </div>
      )}

      {/* Official Preset - показываем всегда */}
      {isLoadingPresets && (
        <div className="mb-4 p-4 bg-white/5 rounded-xl border border-white/10 text-gray-400 text-center text-sm">
          Загрузка пресетов...
        </div>
      )}

      {officialPreset && (
        <div className="mb-4 p-4 bg-gradient-to-r from-purple-500/20 to-pink-500/20 rounded-xl border border-purple-500/30">
          <div className="flex items-center justify-between mb-2">
            <h4 className="font-semibold text-white flex items-center">
              <Settings className="w-4 h-4 mr-2" />
              Официальный пресет
            </h4>
            <span className="text-purple-300 text-sm">Производитель</span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
            <div className="flex items-center space-x-2">
              <Thermometer className="w-4 h-4 text-red-400" />
              <span className="text-gray-300">Сопло: {officialPreset.extruder_temp}°C</span>
            </div>
            <div className="flex items-center space-x-2">
              <Thermometer className="w-4 h-4 text-red-400" />
              <span className="text-gray-300">Стол: {officialPreset.bed_temp}°C</span>
            </div>
            <div className="flex items-center space-x-2">
              <Gauge className="w-4 h-4 text-blue-400" />
              <span className="text-gray-300">Скорость: {officialPreset.print_speed}mm/s</span>
            </div>
            <div className="flex items-center space-x-2">
              <Ruler className="w-4 h-4 text-green-400" />
              <span className="text-gray-300">
                Слой: {officialPreset.layer_height ? `${officialPreset.layer_height}mm` : '0.2mm'}
              </span>
            </div>
            <div className="flex items-center space-x-2">
              <Gauge className="w-4 h-4 text-yellow-400" />
              <span className="text-gray-300">
                Поток: {officialPreset.flow_rate ? `${officialPreset.flow_rate}%` : '100%'}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Community Presets - показываем всегда */}
      {communityPresets && communityPresets.length > 0 && (
        <div className="mb-4">
          <h4 className="font-semibold text-white mb-2 flex items-center text-sm">
            <Users className="w-4 h-4 mr-2" />
            Популярные пресеты сообщества
          </h4>
          <div className="space-y-2">
            {communityPresets.map((preset) => (
              <div
                key={preset.id}
                className="p-3 bg-white/5 rounded-lg mb-2 last:mb-0 border border-white/10"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    {preset.moderation_status === 'approved' && (
                      <CheckCircle className="w-4 h-4 text-green-400" />
                    )}
                    <div>
                      <p className="text-white font-medium">{preset.name}</p>
                      <p className="text-gray-400 text-sm">Ender 3 Pro</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="flex items-center space-x-1 mb-1">
                      <Star className="w-3 h-3 text-yellow-400 fill-current" />
                      <span className="text-white text-sm">{preset.rating?.toFixed(1) || '4.8'}</span>
                    </div>
                    <p className="text-green-400 text-xs">
                      {Math.round(85 + ((preset.rating || 4.0) - 4.0) * 10)}% успеха
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="flex space-x-3 mt-4">
        <button
          onClick={onSelect}
          className="flex-1 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white py-3 px-6 rounded-xl transition-all duration-300 shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40"
        >
          Выбрать для OrcaSlicer
        </button>
        <button
          onClick={onShowQR}
          className="px-4 py-3 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all border border-white/20"
        >
          <QrCode className="w-5 h-5" />
        </button>
      </div>

      {/* QR Code */}
      {showQR && (
        <div className="mt-4 p-4 bg-white/5 rounded-xl border border-white/10">
          <div className="text-center">
            <div className="w-24 h-24 bg-white/20 rounded-lg mx-auto mb-2 flex items-center justify-center">
              <div className="grid grid-cols-4 gap-1">
                {[...Array(16)].map((_, i) => (
                  <div key={i} className="w-2 h-2 bg-white rounded-sm"></div>
                ))}
              </div>
            </div>
            <p className="text-gray-300 text-sm">QR-код для материала {filament.id}</p>
            <p className="text-gray-400 text-xs">Сканируйте для быстрого импорта</p>
          </div>
        </div>
      )}
    </div>
  );
};

interface PresetParamProps {
  icon: LucideIcon;
  label: string;
  value: string;
  color: string;
}

const PresetParam: React.FC<PresetParamProps> = ({ icon: Icon, label, value, color }) => (
  <div className="flex items-center space-x-2">
    <Icon className={`w-4 h-4 ${color}`} />
    <span className="text-gray-300">
      {label}: {value}
    </span>
  </div>
);

