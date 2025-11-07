/** Страница каталога материалов */

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
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
  Shield,
  TrendingUp,
  Flame,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { filamentsAPI, brandsAPI, presetsAPI, savedPresetsAPI, filamentReviewsAPI, qrAPI } from '../api/client';
import { Dropdown } from '../components/Dropdown';
import { FilamentPreview } from '../components/FilamentPreview';
import type { Filament, Preset } from '../types/api';

export const CatalogPage: React.FC = () => {
  const navigate = useNavigate();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState('');
  const [printerModel, setPrinterModel] = useState('Ender 3 Pro');
  const [materialTypeFilter, setMaterialTypeFilter] = useState<string | null>(null);
  const [brandFilter, setBrandFilter] = useState<number | null>(null);
  const [selectedFilament, setSelectedFilament] = useState<number | null>(null);
  const [showQR, setShowQR] = useState<number | null>(null);
  
  // Загружаем список сохранённых пресетов
  const { data: savedPresets } = useQuery({
    queryKey: ['saved-presets', user?.id],
    queryFn: () => savedPresetsAPI.list(),
    enabled: !!user?.id,
  });

  const savedPresetIds = new Set(savedPresets?.items.map(sp => sp.preset_id) || []);

  // Мутация для сохранения пресета
  const savePresetMutation = useMutation({
    mutationFn: (presetId: number) => {
      if (!user) {
        throw new Error('Необходимо войти в систему');
      }
      return savedPresetsAPI.save(presetId);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saved-presets'] });
      queryClient.invalidateQueries({ queryKey: ['saved-presets-details'] });
      queryClient.invalidateQueries({ queryKey: ['user-presets'] });
    },
    onError: (error: any) => {
      console.error('Ошибка сохранения пресета:', error);
      alert(error.response?.data?.detail || error.message || 'Не удалось добавить пресет в профиль');
    },
  });

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

  // Получаем топ-10 популярных (пока просто первые 10, потом будем сортировать по views_count)
  const topFilaments = filamentsData?.items.slice(0, 10) || [];

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

      {/* [ЗАГЛУШКА: Top 10 Popular - временно отключен] */}
      {/* {!searchQuery && !materialTypeFilter && !brandFilter && topFilaments.length > 0 && (
        <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
          <div className="flex items-center space-x-3 mb-6">
            <Flame className="w-8 h-8 text-orange-500" />
            <h3 className="text-2xl font-bold text-white">Топ-10 популярных материалов</h3>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4">
            {topFilaments.map((filament, index) => (
              <div
                key={filament.id}
                onClick={() => navigate(`/filaments/${filament.id}`)}
                className="bg-white/5 rounded-xl border border-white/10 hover:bg-white/10 transition-all cursor-pointer p-4 relative group"
              >
                <div className="absolute -top-2 -left-2 w-8 h-8 bg-gradient-to-r from-orange-500 to-red-500 rounded-full flex items-center justify-center text-white font-bold text-sm shadow-lg">
                  {index + 1}
                </div>
                <div className="flex items-start space-x-3 mb-3">
                  {brandsMap.get(filament.brand_id)?.verified && (
                    <Shield className="w-4 h-4 text-green-400 flex-shrink-0 mt-1" />
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="text-white font-semibold text-sm truncate">
                      {brandsMap.get(filament.brand_id)?.name || 'Unknown'}
                    </p>
                    <p className="text-gray-400 text-xs truncate">{filament.name}</p>
                    <p className="text-purple-300 text-xs">{filament.material_type}</p>
                  </div>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <div className="flex items-center space-x-1 text-yellow-400">
                    <Star className="w-3 h-3 fill-current" />
                    <span>4.8</span>
                  </div>
                  <div className="flex items-center space-x-1 text-green-400">
                    <CheckCircle className="w-3 h-3" />
                    <span>95%</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )} */}

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

          <div className="min-w-48">
            <Dropdown
              value={materialTypeFilter || ''}
              onChange={(val) => setMaterialTypeFilter(val === '' ? null : (val as string))}
              options={[
                { value: '', label: 'Все типы' },
                ...materialTypes.map((type) => ({ value: type, label: type })),
              ]}
              placeholder="Все типы"
            />
          </div>

          <div className="min-w-48">
            <Dropdown
              value={brandFilter || ''}
              onChange={(val) => setBrandFilter(val === '' ? null : Number(val))}
              options={[
                { value: '', label: 'Все бренды' },
                ...(brandsData?.items.map((brand) => ({ value: brand.id, label: brand.name })) || []),
              ]}
              placeholder="Все бренды"
            />
          </div>
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
            onSelect={(presetId) => savePresetMutation.mutate(presetId)}
            onShowQR={() => setShowQR(showQR === filament.id ? null : filament.id)}
            showQR={showQR === filament.id}
            onClick={() => navigate(`/filaments/${filament.id}`)}
            savedPresetIds={savedPresetIds}
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
  onSelect: (presetId: number) => void;
  onShowQR: () => void;
  showQR: boolean;
  onClick: () => void;
  savedPresetIds: Set<number>;
}

const MaterialCard: React.FC<MaterialCardProps> = ({
  filament,
  brand,
  isSelected,
  onSelect,
  onShowQR,
  showQR,
  onClick,
  savedPresetIds,
}) => {
  const navigate = useNavigate();
  
  // УБРАЛИ загрузку пресетов и статистики в каталоге для оптимизации
  // Детальная информация загружается только на странице материала
  // Это решает проблему с сотнями запросов при загрузке каталога

  const handleCardClick = (e: React.MouseEvent) => {
    // Не открываем детальную страницу, если кликнули на кнопку или внутри кнопки
    const target = e.target as HTMLElement;
    if (target.closest('button')) {
      return;
    }
    onClick();
  };

  return (
    <div 
      onClick={handleCardClick}
      className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 hover:bg-white/15 transition-all duration-300 group shadow-xl cursor-pointer"
    >
      {/* Header с названием, ценой и рейтингом */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1">
          <div className="flex items-center space-x-3 mb-2">
            {brand && (
              <>
                <span
                  onClick={(e) => {
                    e.stopPropagation();
                    navigate(`/brands/${brand.id}`);
                  }}
                  className={`${brand.verified ? "text-green-400" : "text-purple-300"} font-semibold hover:underline cursor-pointer transition-colors`}
                >
                  {brand.name}
                </span>
                {brand.verified && (
                  <Shield className="w-4 h-4 text-green-400"/>
                )}
              </>
            )}
            <h3 className="text-xl font-bold text-white group-hover:text-purple-300 transition-colors">
              {filament.name}
            </h3>
            <span className="px-2 py-1 bg-purple-500/20 text-purple-300 text-xs rounded-full border border-purple-500/30">
              {filament.material_type}
            </span>
          </div>
          {/* Рейтинг материала - убран из каталога для оптимизации, показывается на детальной странице */}
        </div>
        {(filament.price_per_kg || filament.spool_weight) && (
          <div className="text-right ml-4">
            {filament.price_per_kg && (
              <p className="text-3xl font-bold text-green-400 mb-1">
                {Math.round(filament.price_per_kg)}₽
              </p>
            )}
            {filament.spool_weight && (
              <p className="text-sm text-gray-400">
                {Math.round(filament.spool_weight)}g
              </p>
            )}
          </div>
        )}
      </div>

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
      {(filament.color_hex || filament.color_name) && (
        <div className="mb-4">
          <div className="flex items-center space-x-2">
            <span className="text-gray-300 text-sm font-medium">Цвет:</span>
            <div style={{ transform: 'scale(0.4)', transformOrigin: 'left center', marginRight: '-80px' }}>
              <FilamentPreview
                colorHex={filament.color_hex || '#FFFFFF'}
                visualSettings={filament.visual_settings}
                size="medium"
              />
            </div>
            {filament.color_name && (
              <span className="text-white text-sm">{filament.color_name}</span>
            )}
          </div>
        </div>
      )}

      {/* Пресеты и детальная информация загружаются только на странице материала для оптимизации */}
      
      {/* Actions */}
      <div className="flex space-x-3 mt-4">
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
            {filament.qr_code ? (
              <>
                <img
                  src={qrAPI.getQRCodeURL(filament.id, 200)}
                  alt={`QR-код для ${filament.name}`}
                  className="w-48 h-48 mx-auto mb-3 rounded-lg bg-white p-2"
                />
                <p className="text-gray-300 text-sm font-medium mb-1">QR-код: {filament.qr_code}</p>
                <p className="text-gray-400 text-xs">Сканируйте для быстрого импорта настроек</p>
                <p className="text-gray-500 text-xs mt-1">
                  Сканирований: {filament.scans_count || 0}
                </p>
              </>
            ) : (
              <div className="py-8">
                <QrCode className="w-16 h-16 mx-auto mb-3 text-gray-500" />
                <p className="text-gray-400 text-sm">
                  QR-код доступен только для верифицированных брендов
                </p>
              </div>
            )}
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

