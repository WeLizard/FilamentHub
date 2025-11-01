/** Детальная страница филамента */

import { useState } from 'react';
import { useParams, useNavigate, useLocation } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Star,
  CheckCircle,
  Settings,
  Users,
  Thermometer,
  Gauge,
  Ruler,
  QrCode,
  Shield,
  ArrowLeft,
  TrendingUp,
  MessageCircle,
  Package,
  Wind,
  ExternalLink,
  Fan,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { filamentsAPI, brandsAPI, savedPresetsAPI } from '../api/client';

export const FilamentDetailPage: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [showQR, setShowQR] = useState(false);
  const [activeTab, setActiveTab] = useState<'presets' | 'reviews'>('presets');
  
  // Определяем откуда пришли (из каталога или профиля)
  const cameFrom = location.state?.from || 'catalog';

  // Загружаем филамент
  const {
    data: filament,
    isLoading: isLoadingFilament,
    error: filamentError,
  } = useQuery({
    queryKey: ['filament', id],
    queryFn: () => filamentsAPI.get(Number(id)),
    enabled: !!id,
  });

  // Загружаем бренд
  const { data: brandData } = useQuery({
    queryKey: ['brand', filament?.brand_id],
    queryFn: () => brandsAPI.get(filament!.brand_id),
    enabled: !!filament?.brand_id,
  });

  // Загружаем все пресеты
  const { data: presetsData, isLoading: isLoadingPresets } = useQuery({
    queryKey: ['filament-presets', id],
    queryFn: () => filamentsAPI.getPresets(Number(id)),
    enabled: !!id,
  });

  // Загружаем список сохранённых пресетов
  const { data: savedPresets } = useQuery({
    queryKey: ['saved-presets', user?.id],
    queryFn: () => savedPresetsAPI.list(),
    enabled: !!user?.id,
  });

  const savedPresetIds = new Set(savedPresets?.items.map(sp => sp.preset_id) || []);

  // Мутация для сохранения пресета
  const savePresetMutation = useMutation({
    mutationFn: (presetId: number) => savedPresetsAPI.save(presetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saved-presets'] });
      queryClient.invalidateQueries({ queryKey: ['user-presets'] });
    },
  });

  // TODO: Загружаем отзывы
  // const { data: reviewsData } = useQuery({
  //   queryKey: ['filament-reviews', id],
  //   queryFn: () => filamentsAPI.getReviews(Number(id)),
  //   enabled: !!id,
  // });

  if (isLoadingFilament) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-white text-xl">Загрузка материала...</div>
      </div>
    );
  }

  if (filamentError || !filament) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-red-400 text-xl">Материал не найден</div>
      </div>
    );
  }

  // Получаем официальный пресет и пресеты сообщества
  const officialPreset = presetsData?.items.find((p) => p.is_official);
  const communityPresets = presetsData?.items.filter((p) => !p.is_official);
  
  // Проверяем, сохранён ли официальный пресет
  const isOfficialPresetSaved = officialPreset ? savedPresetIds.has(officialPreset.id) : false;

  // Вычисляем средний рейтинг из пресетов
  const avgRating =
    presetsData?.items && presetsData.items.length > 0
      ? presetsData.items
          .filter((p) => p.rating !== null)
          .reduce((acc, p) => acc + (p.rating || 0), 0) /
        presetsData.items.filter((p) => p.rating !== null).length
      : 4.8;

  // Вычисляем успешность
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
    <div className="space-y-6">
      {/* Кнопка назад */}
      <button
        onClick={() => navigate(cameFrom === 'profile' ? '/profile' : '/')}
        className="flex items-center space-x-2 text-gray-300 hover:text-white transition-colors"
      >
        <ArrowLeft className="w-5 h-5" />
        <span>{cameFrom === 'profile' ? 'Назад к профилю' : 'Назад к каталогу'}</span>
      </button>

      {/* Заголовок */}
      <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-8 border border-white/20 shadow-xl">
        <div className="flex items-start justify-between mb-6">
          <div className="flex-1">
            <div className="flex items-center space-x-3 mb-4">
              {brandData && (
                <>
                  <span
                    className={brandData.verified ? 'text-green-400 font-bold text-2xl' : 'text-purple-300 font-bold text-2xl'}
                  >
                    {brandData.name}
                  </span>
                  {brandData.verified && (
                    <Shield className="w-6 h-6 text-green-400" />
                  )}
                </>
              )}
              <h1 className="text-4xl font-bold text-white">{filament.name}</h1>
              <span className="px-3 py-1 bg-purple-500/20 text-purple-300 text-base rounded-full border border-purple-500/30">
                {filament.material_type}
              </span>
            </div>

            {/* Статистика */}
            <div className="flex items-center space-x-6 text-lg mb-4">
              <span className="flex items-center text-gray-300">
                <Star className="w-5 h-5 mr-2 text-yellow-400 fill-current" />
                <span className="font-bold text-white">{avgRating.toFixed(1)}</span>
              </span>
              <span className="flex items-center text-gray-300">
                <CheckCircle className="w-5 h-5 mr-2 text-green-400" />
                <span className="font-bold text-green-400">{Math.round(successRate)}% успеха</span>
              </span>
              <span className="flex items-center text-gray-300">
                <TrendingUp className="w-5 h-5 mr-2 text-blue-400" />
                <span className="font-bold text-white">{presetsData?.total || 0} пресетов</span>
              </span>
              <span className="flex items-center text-gray-300">
                <Package className="w-5 h-5 mr-2 text-purple-400" />
                <span className="font-bold text-white">{filament.views_count || 0} просмотров</span>
              </span>
            </div>

            {/* Описание */}
            {filament.description && (
              <p className="text-gray-300">{filament.description}</p>
            )}
          </div>

          <div className="text-right ml-8">
            {brandData?.website && (
              <a
                href={brandData.website}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center justify-end space-x-2 text-purple-400 hover:text-purple-300 transition-colors mb-2"
                title={brandData.website}
              >
                <ExternalLink className="w-5 h-5" />
                <span className="text-sm">
                  {brandData.website.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '')}
                </span>
              </a>
            )}
            <p className="text-4xl font-bold text-green-400 mb-2">
              {filament.price_per_kg ? `${Math.round(filament.price_per_kg)}₽` : '—'}
            </p>
            <p className="text-gray-400 text-lg">
              {filament.spool_weight ? `${Math.round(filament.spool_weight)}g` : '—'}
            </p>
          </div>
        </div>

        {/* Детали материала */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6 mb-6">
          {filament.diameter && (
            <div className="flex items-center space-x-3 text-gray-300">
              <Ruler className="w-5 h-5 text-purple-400" />
              <div>
                <div className="text-sm">Диаметр</div>
                <div className="text-xl font-bold text-white">{filament.diameter}mm</div>
              </div>
            </div>
          )}
          {filament.density && (
            <div className="flex items-center space-x-3 text-gray-300">
              <Package className="w-5 h-5 text-blue-400" />
              <div>
                <div className="text-sm">Плотность</div>
                <div className="text-xl font-bold text-white">{filament.density}g/cm³</div>
              </div>
            </div>
          )}
          {filament.color_hex && (
            <div className="flex items-center space-x-3 text-gray-300">
              <div
                className="w-10 h-10 rounded-full border-2 border-white/30"
                style={{ backgroundColor: filament.color_hex }}
              />
              <div>
                <div className="text-sm">Цвет</div>
                <div className="text-xl font-bold text-white">{filament.color_name || '—'}</div>
              </div>
            </div>
          )}
          <div className="flex items-center space-x-3 text-gray-300">
            <QrCode className="w-5 h-5 text-green-400" />
            <div>
              <div className="text-sm">Сканирований</div>
              <div className="text-xl font-bold text-white">{filament.scans_count || 0}</div>
            </div>
          </div>
        </div>

        {/* Кнопки действий */}
        <div className="flex space-x-4">
          {officialPreset ? (
            isOfficialPresetSaved ? (
              <button
                disabled
                className="flex-1 bg-green-600/50 text-white py-4 px-8 rounded-xl cursor-not-allowed text-lg font-semibold flex items-center justify-center"
              >
                <CheckCircle className="w-6 h-6 mr-2" />
                Добавлено
              </button>
            ) : (
              <button
                onClick={() => officialPreset && savePresetMutation.mutate(officialPreset.id)}
                className="flex-1 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white py-4 px-8 rounded-xl transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 text-lg font-semibold"
              >
                Добавить в профиль
              </button>
            )
          ) : (
            <button
              disabled
              className="flex-1 bg-gray-600/50 text-white py-4 px-8 rounded-xl cursor-not-allowed text-lg font-semibold"
            >
              Нет пресетов
            </button>
          )}
          <button
            onClick={() => setShowQR(!showQR)}
            className="px-6 py-4 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all border border-white/20"
          >
            <QrCode className="w-6 h-6" />
          </button>
        </div>

        {/* QR Code [ЗАГЛУШКА] */}
        {showQR && (
          <div className="mt-6 p-6 bg-white/5 rounded-xl border border-white/10">
            <div className="text-center">
              <div className="w-32 h-32 bg-white/20 rounded-lg mx-auto mb-3 flex items-center justify-center">
                <div className="grid grid-cols-4 gap-1">
                  {[...Array(16)].map((_, i) => (
                    <div key={i} className="w-3 h-3 bg-white rounded-sm"></div>
                  ))}
                </div>
              </div>
              <p className="text-gray-300">QR-код для материала {filament.id} [ЗАГЛУШКА]</p>
              <p className="text-gray-400 text-sm">Сканируйте для быстрого импорта</p>
            </div>
          </div>
        )}
      </div>

      {/* Табы: Пресеты / Отзывы */}
      <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
        <div className="flex space-x-4 mb-6 border-b border-white/10">
          <button
            onClick={() => setActiveTab('presets')}
            className={`pb-4 px-4 font-semibold transition-colors ${
              activeTab === 'presets'
                ? 'text-purple-400 border-b-2 border-purple-400'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            <Settings className="w-5 h-5 inline mr-2" />
            Пресеты ({presetsData?.total || 0})
          </button>
          <button
            onClick={() => setActiveTab('reviews')}
            className={`pb-4 px-4 font-semibold transition-colors ${
              activeTab === 'reviews'
                ? 'text-purple-400 border-b-2 border-purple-400'
                : 'text-gray-400 hover:text-white'
            }`}
          >
            <MessageCircle className="w-5 h-5 inline mr-2" />
            Отзывы [ЗАГЛУШКА] (0)
          </button>
        </div>

        {activeTab === 'presets' && (
          <div className="space-y-6">
            {/* Официальный пресет */}
            {isLoadingPresets && (
              <div className="text-center py-8 text-gray-400">Загрузка пресетов...</div>
            )}

            {officialPreset && (
              <div className="bg-gradient-to-r from-purple-500/20 to-pink-500/20 rounded-xl border border-purple-500/30 p-6">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-xl font-bold text-white flex items-center">
                    <Settings className="w-5 h-5 mr-2" />
                    Официальный пресет
                  </h3>
                  <span className="text-purple-300 font-semibold">Производитель</span>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
                  <div className="flex items-center space-x-2">
                    <Thermometer className="w-5 h-5 text-red-400" />
                    <div>
                      <div className="text-gray-400 text-sm">Сопло</div>
                      <div className="text-white font-semibold">{officialPreset.extruder_temp}°C</div>
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Thermometer className="w-5 h-5 text-red-400" />
                    <div>
                      <div className="text-gray-400 text-sm">Стол</div>
                      <div className="text-white font-semibold">{officialPreset.bed_temp}°C</div>
                    </div>
                  </div>
                  <div className="flex items-center space-x-2">
                    <Gauge className="w-5 h-5 text-blue-400" />
                    <div>
                      <div className="text-gray-400 text-sm">Скорость</div>
                      <div className="text-white font-semibold">{officialPreset.print_speed}mm/s</div>
                    </div>
                  </div>
                  {officialPreset.travel_speed && (
                    <div className="flex items-center space-x-2">
                      <Wind className="w-5 h-5 text-cyan-400" />
                      <div>
                        <div className="text-gray-400 text-sm">Перемещение</div>
                        <div className="text-white font-semibold">{officialPreset.travel_speed}mm/s</div>
                      </div>
                    </div>
                  )}
                  {officialPreset.layer_height && (
                    <div className="flex items-center space-x-2">
                      <Ruler className="w-5 h-5 text-green-400" />
                      <div>
                        <div className="text-gray-400 text-sm">Слой</div>
                        <div className="text-white font-semibold">{officialPreset.layer_height}mm</div>
                      </div>
                    </div>
                  )}
                  {officialPreset.first_layer_height && (
                    <div className="flex items-center space-x-2">
                      <Ruler className="w-5 h-5 text-green-300" />
                      <div>
                        <div className="text-gray-400 text-sm">Перв. слой</div>
                        <div className="text-white font-semibold">{officialPreset.first_layer_height}mm</div>
                      </div>
                    </div>
                  )}
                  {officialPreset.flow_rate && (
                    <div className="flex items-center space-x-2">
                      <Gauge className="w-5 h-5 text-yellow-400" />
                      <div>
                        <div className="text-gray-400 text-sm">Поток</div>
                        <div className="text-white font-semibold">{officialPreset.flow_rate}%</div>
                      </div>
                    </div>
                  )}
                  {officialPreset.fan_speed !== null && (
                    <div className="flex items-center space-x-2">
                      <Fan className="w-5 h-5 text-orange-400" />
                      <div>
                        <div className="text-gray-400 text-sm">Вентилятор</div>
                        <div className="text-white font-semibold">{officialPreset.fan_speed}%</div>
                      </div>
                    </div>
                  )}
                  {officialPreset.retraction_length && (
                    <div className="flex items-center space-x-2">
                      <Wind className="w-5 h-5 text-purple-400" />
                      <div>
                        <div className="text-gray-400 text-sm">Ретракт</div>
                        <div className="text-white font-semibold">{officialPreset.retraction_length}mm</div>
                      </div>
                    </div>
                  )}
                  {officialPreset.retraction_speed && (
                    <div className="flex items-center space-x-2">
                      <Gauge className="w-5 h-5 text-indigo-400" />
                      <div>
                        <div className="text-gray-400 text-sm">Ск. ретракт</div>
                        <div className="text-white font-semibold">{officialPreset.retraction_speed}mm/s</div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Пресеты сообщества */}
            {communityPresets && communityPresets.length > 0 && (
              <div>
                <h3 className="text-xl font-bold text-white mb-4 flex items-center">
                  <Users className="w-5 h-5 mr-2" />
                  Пресеты сообщества ({communityPresets.length})
                </h3>
                <div className="space-y-3">
                  {communityPresets.map((preset) => {
                    const isPresetSaved = savedPresetIds.has(preset.id);
                    return (
                      <div
                        key={preset.id}
                        className="p-4 bg-white/5 rounded-xl border border-white/10 hover:bg-white/10 transition-all"
                      >
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center space-x-3 flex-1">
                            {preset.moderation_status === 'approved' && (
                              <CheckCircle className="w-5 h-5 text-green-400" />
                            )}
                            <div className="flex-1">
                              <p className="text-white font-semibold text-lg">{preset.name}</p>
                              {preset.description && (
                                <p className="text-gray-400 text-sm">{preset.description}</p>
                              )}
                            </div>
                          </div>
                          <div className="text-right ml-4">
                            <div className="flex items-center space-x-2 mb-2">
                              <Star className="w-5 h-5 text-yellow-400 fill-current" />
                              <span className="text-white font-bold">{preset.rating?.toFixed(1) || '4.8'}</span>
                            </div>
                            <p className="text-green-400 text-sm font-semibold">
                              {Math.round(85 + ((preset.rating || 4.0) - 4.0) * 10)}% успеха
                            </p>
                            <p className="text-gray-400 text-xs">{preset.usage_count} использований</p>
                          </div>
                        </div>
                        
                        {/* Параметры пресета */}
                        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 pt-3 border-t border-white/10 mb-3">
                        <div className="flex items-center space-x-2">
                          <Thermometer className="w-4 h-4 text-red-400" />
                          <div>
                            <div className="text-gray-400 text-xs">Сопло</div>
                            <div className="text-white text-sm font-semibold">{preset.extruder_temp}°C</div>
                          </div>
                        </div>
                        <div className="flex items-center space-x-2">
                          <Thermometer className="w-4 h-4 text-red-400" />
                          <div>
                            <div className="text-gray-400 text-xs">Стол</div>
                            <div className="text-white text-sm font-semibold">{preset.bed_temp}°C</div>
                          </div>
                        </div>
                        <div className="flex items-center space-x-2">
                          <Gauge className="w-4 h-4 text-blue-400" />
                          <div>
                            <div className="text-gray-400 text-xs">Скорость</div>
                            <div className="text-white text-sm font-semibold">{preset.print_speed}mm/s</div>
                          </div>
                        </div>
                        {preset.travel_speed && (
                          <div className="flex items-center space-x-2">
                            <Wind className="w-4 h-4 text-cyan-400" />
                            <div>
                              <div className="text-gray-400 text-xs">Перемещение</div>
                              <div className="text-white text-sm font-semibold">{preset.travel_speed}mm/s</div>
                            </div>
                          </div>
                        )}
                        {preset.layer_height && (
                          <div className="flex items-center space-x-2">
                            <Ruler className="w-4 h-4 text-green-400" />
                            <div>
                              <div className="text-gray-400 text-xs">Слой</div>
                              <div className="text-white text-sm font-semibold">{preset.layer_height}mm</div>
                            </div>
                          </div>
                        )}
                        {preset.first_layer_height && (
                          <div className="flex items-center space-x-2">
                            <Ruler className="w-4 h-4 text-green-300" />
                            <div>
                              <div className="text-gray-400 text-xs">Перв. слой</div>
                              <div className="text-white text-sm font-semibold">{preset.first_layer_height}mm</div>
                            </div>
                          </div>
                        )}
                        {preset.flow_rate && (
                          <div className="flex items-center space-x-2">
                            <Gauge className="w-4 h-4 text-yellow-400" />
                            <div>
                              <div className="text-gray-400 text-xs">Поток</div>
                              <div className="text-white text-sm font-semibold">{preset.flow_rate}%</div>
                            </div>
                          </div>
                        )}
                        {preset.fan_speed !== null && (
                          <div className="flex items-center space-x-2">
                            <Fan className="w-4 h-4 text-orange-400" />
                            <div>
                              <div className="text-gray-400 text-xs">Вентилятор</div>
                              <div className="text-white text-sm font-semibold">{preset.fan_speed}%</div>
                            </div>
                          </div>
                        )}
                        {preset.retraction_length && (
                          <div className="flex items-center space-x-2">
                            <Wind className="w-4 h-4 text-purple-400" />
                            <div>
                              <div className="text-gray-400 text-xs">Ретракт</div>
                              <div className="text-white text-sm font-semibold">{preset.retraction_length}mm</div>
                            </div>
                          </div>
                        )}
                        {preset.retraction_speed && (
                          <div className="flex items-center space-x-2">
                            <Gauge className="w-4 h-4 text-indigo-400" />
                            <div>
                              <div className="text-gray-400 text-xs">Ск. ретракт</div>
                              <div className="text-white text-sm font-semibold">{preset.retraction_speed}mm/s</div>
                            </div>
                          </div>
                        )}
                        </div>
                      
                      {/* Кнопка добавления в профиль */}
                      <div className="pt-3 border-t border-white/10">
                        {isPresetSaved ? (
                          <button
                            disabled
                            className="w-full bg-green-600/50 text-white py-2 px-4 rounded-lg cursor-not-allowed flex items-center justify-center"
                          >
                            <CheckCircle className="w-5 h-5 mr-2" />
                            Добавлено
                          </button>
                        ) : (
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              savePresetMutation.mutate(preset.id);
                            }}
                            className="w-full bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white py-2 px-4 rounded-lg transition-all"
                          >
                            Добавить в профиль
                          </button>
                        )}
                      </div>
                    </div>
                  );
                  })}
                </div>
              </div>
            )}
          </div>
        )}

        {activeTab === 'reviews' && (
          <div className="text-center py-12 text-gray-400">
            <MessageCircle className="w-16 h-16 mx-auto mb-4 opacity-50" />
            <p className="text-xl">Отзывы будут доступны после реализации API</p>
          </div>
        )}
      </div>
    </div>
  );
};
