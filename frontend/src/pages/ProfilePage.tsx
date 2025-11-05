/** Страница профиля пользователя */

import { useState, useMemo, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  User,
  Package,
  Settings,
  TrendingUp,
  Calculator,
  Play,
  Star,
  CheckCircle,
  XCircle,
  Plus,
  Download,
  Trash2,
  Thermometer,
  Gauge,
  Edit,
  Wind,
  Fan,
  Ruler,
  Factory,
  AlertTriangle,
  Loader2,
  Upload,
  Printer,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { presetsAPI, filamentsAPI, brandsAPI, savedPresetsAPI, filamentReviewsAPI } from '../api/client';
import api from '../api/client';
import { CreatePresetModal } from '../components/CreatePresetModal';
import { CreatePrinterRequestModal } from '../components/CreatePrinterRequestModal';
import { DeleteAccountModal } from '../components/DeleteAccountModal';
import { BrandProfilePage } from './BrandProfilePage';
import type { Preset } from '../types/api';

export const ProfilePage: React.FC = () => {
  const { user, refreshUser } = useAuth();
  const queryClient = useQueryClient();
  const [showBrandCabinet, setShowBrandCabinet] = useState(false); // Показывать ли кабинет производителя
  const [userTab, setUserTab] = useState<'dashboard' | 'presets' | 'history' | 'calculator'>(
    'dashboard'
  );
  const [isCreatePresetModalOpen, setIsCreatePresetModalOpen] = useState(false);
  const [isCreatePrinterRequestModalOpen, setIsCreatePrinterRequestModalOpen] = useState(false);
  const [editingPreset, setEditingPreset] = useState<Preset | null>(null);
  const [isDeleteAccountModalOpen, setIsDeleteAccountModalOpen] = useState(false);

  // Загружаем пресеты пользователя (созданные им)
  const { data: userPresetsData } = useQuery({
    queryKey: ['user-presets', user?.id],
    queryFn: () => presetsAPI.list({ active_only: true, page: 1, size: 100, user_id: user?.id }),
    enabled: !!user?.id,
  });

  // Загружаем сохранённые пресеты
  const { data: savedPresetsData } = useQuery({
    queryKey: ['saved-presets', user?.id],
    queryFn: () => savedPresetsAPI.list(),
    enabled: !!user?.id,
  });

  // Загружаем детали сохранённых пресетов
  const savedPresetIds = useMemo(() => {
    if (!savedPresetsData?.items) return [];
    // Сортируем по saved_at (новые первыми) для стабильности
    const sorted = [...savedPresetsData.items].sort((a, b) => {
      const dateA = new Date(a.saved_at).getTime();
      const dateB = new Date(b.saved_at).getTime();
      return dateB - dateA; // Новые первыми
    });
    return sorted.map(sp => sp.preset_id);
  }, [savedPresetsData]);
  
  const { data: savedPresetsDetails } = useQuery({
    queryKey: ['saved-presets-details', savedPresetIds],
    queryFn: async () => {
      // Используем Promise.allSettled для обработки ошибок
      const results = await Promise.allSettled(
        savedPresetIds.map(presetId => presetsAPI.get(presetId))
      );
      // Фильтруем успешные запросы
      const details = results
        .filter((result): result is PromiseFulfilledResult<any> => result.status === 'fulfilled')
        .map(result => result.value)
        .filter(p => p !== null && p !== undefined);
      
      // Логируем ошибки для отладки
      const errors = results.filter(result => result.status === 'rejected');
      if (errors.length > 0) {
        console.warn('Некоторые пресеты не удалось загрузить:', errors);
      }
      
      return details;
    },
    enabled: savedPresetIds.length > 0,
  });

  // Объединяем пресеты: созданные пользователем + сохранённые из каталога
  const allMyPresets = useMemo(() => {
    const created = (userPresetsData?.items || []).map(p => ({ ...p, source: 'own' as const }));
    const saved = (savedPresetsDetails || []).map(p => ({ ...p, source: 'saved' as const }));
    return [...created, ...saved];
  }, [userPresetsData, savedPresetsDetails]);

  const userPresets = allMyPresets;

  // Загружаем отзывы пользователя
  const { data: userReviewsData } = useQuery({
    queryKey: ['user-reviews', user?.id],
    queryFn: () => filamentReviewsAPI.getMyReviews({ page: 1, size: 1000, active_only: true }),
    enabled: !!user?.id,
  });

  // Вычисляем статистику из отзывов
  const reviewsStats = useMemo(() => {
    if (!userReviewsData || userReviewsData.items.length === 0) {
      return {
        successCount: 0,
        avgRating: null,
        totalReviews: 0,
      };
    }

    const reviews = userReviewsData.items;
    const successCount = reviews.filter(r => r.success).length;
    const avgRating = reviews.reduce((sum, r) => sum + r.rating, 0) / reviews.length;

    return {
      successCount,
      avgRating: avgRating.toFixed(1),
      totalReviews: reviews.length,
    };
  }, [userReviewsData]);

  // Мутация для удаления пресета (созданного пользователем)
  const deletePresetMutation = useMutation({
    mutationFn: (id: number) => presetsAPI.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['user-presets'] });
      queryClient.invalidateQueries({ queryKey: ['presets'] });
      queryClient.invalidateQueries({ queryKey: ['filament-presets'] });
    },
  });

  // Мутация для удаления сохранённого пресета
  const unsavePresetMutation = useMutation({
    mutationFn: (presetId: number) => savedPresetsAPI.unsave(presetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saved-presets'] });
      queryClient.invalidateQueries({ queryKey: ['saved-presets-details'] });
      queryClient.invalidateQueries({ queryKey: ['user-presets'] });
    },
    onError: (error: any) => {
      console.error('Ошибка удаления сохранённого пресета:', error);
      alert(error.response?.data?.detail || error.message || 'Не удалось убрать пресет из профиля');
    },
  });

  const handleDeletePreset = (preset: Preset) => {
    if (preset.source === 'saved') {
      if (confirm('Убрать пресет из профиля?')) {
        unsavePresetMutation.mutate(preset.id);
      }
    } else {
      if (confirm('Вы уверены, что хотите удалить этот пресет?')) {
        deletePresetMutation.mutate(preset.id);
      }
    }
  };

  const handleEditPreset = (preset: Preset) => {
    setEditingPreset(preset);
    setIsCreatePresetModalOpen(true);
  };

  const handleCreatePreset = () => {
    setEditingPreset(null);
    setIsCreatePresetModalOpen(true);
  };

  const handleClosePresetModal = () => {
    setIsCreatePresetModalOpen(false);
    setEditingPreset(null);
  };

  // TODO: Загрузить историю печати (когда будет эндпоинт)
  // ЗАГЛУШКА - пустой массив, история не реализована
  const userHistory: Array<{
    id: number;
    material: string;
    printer: string;
    date: string;
    success: boolean;
    rating: number;
    notes: string;
  }> = [];

  if (!user) {
    return null; // ProtectedRoute должен это обработать
  }

  // Если выбран профиль компании, показываем BrandProfilePage
  if (showBrandCabinet) {
    return (
      <div className="space-y-6">
        {/* Переключатель профилей */}
        <div className="flex justify-center mb-6">
          <div className="flex bg-white/10 rounded-lg p-1 border border-white/20">
            <button
              onClick={() => setShowBrandCabinet(false)}
              className="flex items-center space-x-2 px-6 py-2 rounded-lg transition-all text-gray-300 hover:text-white"
            >
              <User className="w-4 h-4" />
              <span>Профиль пользователя</span>
            </button>
            <button
              onClick={() => setShowBrandCabinet(true)}
              className="flex items-center space-x-2 px-6 py-2 rounded-lg transition-all bg-green-600 text-white shadow-lg shadow-green-500/25"
            >
              <Factory className="w-4 h-4" />
              <span>Профиль компании</span>
            </button>
          </div>
        </div>
        
        <BrandProfilePage onBack={() => setShowBrandCabinet(false)} />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Переключатель профилей */}
      <div className="flex justify-center mb-6">
        <div className="flex bg-white/10 rounded-lg p-1 border border-white/20">
          <button
            onClick={() => setShowBrandCabinet(false)}
            className="flex items-center space-x-2 px-6 py-2 rounded-lg transition-all bg-purple-600 text-white shadow-lg shadow-purple-500/25"
          >
            <User className="w-4 h-4" />
            <span>Профиль пользователя</span>
          </button>
          <button
            onClick={() => setShowBrandCabinet(true)}
            className="flex items-center space-x-2 px-6 py-2 rounded-lg transition-all text-gray-300 hover:text-white"
          >
            <Factory className="w-4 h-4" />
            <span>Профиль компании</span>
          </button>
        </div>
      </div>
      
      {/* Header */}
      <div className="text-center mb-8">
        <div className="flex items-center justify-center space-x-3 mb-4">
          <div className="w-16 h-16 bg-gradient-to-r from-purple-500 to-pink-500 rounded-xl flex items-center justify-center shadow-lg shadow-purple-500/25">
            <User className="w-8 h-8 text-white" />
          </div>
          <div>
            <h2 className="text-3xl font-bold text-white">Мой профиль</h2>
            <p className="text-gray-300">
              {user.full_name || user.username} • 3D печатник
            </p>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex justify-center space-x-2 mt-4">
          {[
            { id: 'dashboard', label: 'Дашборд', icon: Play },
            { id: 'presets', label: 'Мои пресеты', icon: Settings },
            { id: 'history', label: 'История', icon: TrendingUp },
            { id: 'calculator', label: 'Калькулятор', icon: Calculator },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setUserTab(tab.id as any)}
              className={`flex items-center space-x-2 px-4 py-2 rounded-lg transition-all ${
                userTab === tab.id
                  ? 'bg-purple-600 text-white shadow-lg shadow-purple-500/25'
                  : 'text-gray-300 hover:text-white hover:bg-white/10'
              }`}
            >
              <tab.icon className="w-4 h-4" />
              <span>{tab.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Dashboard Tab */}
      {userTab === 'dashboard' && (
        <div className="space-y-6">
          {/* Stats Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <StatCard
              icon={CheckCircle}
              label="Успешных печатей"
              value={reviewsStats.successCount.toString()}
              color="from-purple-500/20 to-pink-500/20"
              borderColor="border-purple-500/30"
              iconColor="text-green-400"
            />
            <StatCard
              icon={Settings}
              label="Сохраненных пресетов"
              value={userPresets.length.toString()}
              color="from-blue-500/20 to-cyan-500/20"
              borderColor="border-blue-500/30"
              iconColor="text-blue-400"
            />
            <StatCard
              icon={Package}
              label="Оставлено отзывов"
              value={reviewsStats.totalReviews.toString()}
              color="from-green-500/20 to-emerald-500/20"
              borderColor="border-green-500/30"
              iconColor="text-green-400"
            />
            <StatCard
              icon={Star}
              label="Средний рейтинг"
              value={reviewsStats.avgRating || '—'}
              color="from-yellow-500/20 to-orange-500/20"
              borderColor="border-yellow-500/30"
              iconColor="text-yellow-400"
            />
          </div>

          {/* Recent Activity */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <RecentPresets presets={userPresets.slice(0, 3)} />
            <RecentHistory history={userHistory.slice(0, 3)} />
          </div>
        </div>
      )}

      {/* Presets Tab */}
      {userTab === 'presets' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h3 className="text-2xl font-bold text-white">Мои пресеты</h3>
            <button
              onClick={handleCreatePreset}
              className="bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white px-4 py-2 rounded-xl transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40"
            >
              <Plus className="w-4 h-4 inline mr-2" />
              Новый пресет
            </button>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {userPresets.map((preset) => (
              <PresetCard
                key={preset.id}
                preset={preset}
                onEdit={handleEditPreset}
                onDelete={handleDeletePreset}
              />
            ))}
          </div>

          {userPresets.length === 0 && (
            <div className="text-center py-12">
              <Settings className="w-16 h-16 text-gray-400 mx-auto mb-4" />
              <p className="text-gray-400 text-xl">У вас пока нет сохраненных пресетов</p>
            </div>
          )}
        </div>
      )}

      {/* History Tab */}
      {userTab === 'history' && (
        <div className="space-y-6">
          <h3 className="text-2xl font-bold text-white">История печати</h3>

          <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
            {userHistory.length > 0 ? (
              <div className="space-y-4">
                {userHistory.map((item) => (
                  <HistoryItem key={item.id} item={item} />
                ))}
              </div>
            ) : (
              <div className="text-center py-12">
                <TrendingUp className="w-16 h-16 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-400 text-xl">История печати пока пуста</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Calculator Tab */}
      {userTab === 'calculator' && (
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-8">
            <h2 className="text-4xl font-bold text-white mb-4">Калькулятор стоимости печати</h2>
            <p className="text-xl text-gray-300">
              Рассчитайте точную стоимость детали с учетом региональных особенностей
            </p>
          </div>

          <CalculatorComponent />
        </div>
      )}

      {/* Create/Edit Preset Modal */}
      <CreatePresetModal
        isOpen={isCreatePresetModalOpen}
        onClose={handleClosePresetModal}
        preset={editingPreset}
      />

      {/* Create Printer Request Modal */}
      <CreatePrinterRequestModal
        isOpen={isCreatePrinterRequestModalOpen}
        onClose={() => setIsCreatePrinterRequestModalOpen(false)}
      />

      {/* Delete Account Modal */}
      <DeleteAccountModal
        isOpen={isDeleteAccountModalOpen}
        onClose={() => setIsDeleteAccountModalOpen(false)}
      />

      {/* Кнопка удаления аккаунта */}
      <div className="mt-8 pt-6 border-t border-white/20">
        <div className="max-w-2xl mx-auto">
          <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-start space-x-3 flex-1">
                <AlertTriangle className="w-5 h-5 text-red-400 flex-shrink-0 mt-0.5" />
                <div className="flex-1">
                  <h3 className="text-sm font-semibold text-red-300 mb-1">Опасная зона</h3>
                  <p className="text-xs text-red-200 mb-2">
                    Удаление аккаунта приведёт к деактивации вашего профиля. Это действие необратимо.
                  </p>
                </div>
              </div>
              <button
                onClick={() => setIsDeleteAccountModalOpen(true)}
                className="px-4 py-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded-lg transition-all border border-red-500/30 flex items-center space-x-2"
              >
                <Trash2 className="w-4 h-4" />
                <span>Удалить аккаунт</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

interface StatCardProps {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  color: string;
  borderColor: string;
  iconColor: string;
}

const StatCard: React.FC<StatCardProps> = ({ icon: Icon, label, value, color, borderColor, iconColor }) => (
  <div className={`bg-gradient-to-r ${color} p-6 rounded-2xl border ${borderColor} shadow-xl`}>
    <div className="flex items-center justify-between">
      <div>
        <p className="text-gray-300 text-sm">{label}</p>
        <p className="text-3xl font-bold text-white">{value}</p>
      </div>
      <Icon className={`w-8 h-8 ${iconColor}`} />
    </div>
  </div>
);

interface RecentPresetsProps {
  presets: Preset[];
}

const RecentPresets: React.FC<RecentPresetsProps> = ({ presets }) => (
  <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
    <h3 className="text-xl font-bold text-white mb-4 flex items-center">
      <Settings className="w-5 h-5 mr-2" />
      Последние пресеты
    </h3>
    <div className="space-y-3">
      {presets.length > 0 ? (
        presets.map((preset) => (
          <div key={preset.id} className="flex items-center justify-between p-3 bg-white/5 rounded-xl">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <p className="text-white font-medium">{preset.name}</p>
                {preset.printers && preset.printers.length > 0 && (
                  <div className="flex items-center gap-1.5 flex-wrap">
                    {preset.printers.map((printer) => (
                      <span
                        key={printer.id}
                        className="px-2 py-0.5 bg-white/10 rounded-md text-xs text-gray-300 border border-white/20"
                        title={`${printer.manufacturer} ${printer.model}`}
                      >
                        {printer.name}
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <p className="text-gray-400 text-sm">
                {preset.extruder_temp}°C / {preset.bed_temp}°C
              </p>
            </div>
            <div className="text-right">
              <p className="text-green-400 font-semibold">{preset.usage_count} использований</p>
              <p className="text-gray-400 text-sm">
                {new Date(preset.created_at).toLocaleDateString('ru-RU')}
              </p>
            </div>
          </div>
        ))
      ) : (
        <p className="text-gray-400 text-center py-4">Нет пресетов</p>
      )}
    </div>
  </div>
);

interface RecentHistoryProps {
  history: Array<{
    id: number;
    material: string;
    printer: string;
    date: string;
    success: boolean;
    rating: number;
    notes: string;
  }>;
}

const RecentHistory: React.FC<RecentHistoryProps> = ({ history }) => (
  <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
    <h3 className="text-xl font-bold text-white mb-4 flex items-center">
      <TrendingUp className="w-5 h-5 mr-2" />
      Последние отпечатки
    </h3>
    <div className="space-y-3">
      {history.length > 0 ? (
        history.map((item) => (
          <div key={item.id} className="flex items-center justify-between p-3 bg-white/5 rounded-xl">
            <div>
              <p className="text-white font-medium">{item.material}</p>
              <p className="text-gray-400 text-sm">{item.date}</p>
            </div>
            <div className="flex items-center space-x-2">
              {item.success ? (
                <CheckCircle className="w-5 h-5 text-green-400" />
              ) : (
                <XCircle className="w-5 h-5 text-red-400" />
              )}
              <span className="text-yellow-400">★{item.rating}</span>
            </div>
          </div>
        ))
      ) : (
        <p className="text-gray-400 text-center py-4">Нет истории</p>
      )}
    </div>
  </div>
);

interface PresetCardProps {
  preset: Preset;
  onEdit?: (preset: Preset) => void;
  onDelete?: (preset: Preset) => void;
}

const PresetCard: React.FC<PresetCardProps> = ({ preset, onEdit, onDelete }) => {
  const navigate = useNavigate();
  const [isDownloading, setIsDownloading] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [isInOrcaSlicer, setIsInOrcaSlicer] = useState(false);
  
  // Проверяем, запущен ли frontend внутри OrcaSlicer
  useEffect(() => {
    // Проверяем наличие window.filamenthub или window.wx
    const inOrca = typeof window !== 'undefined' && (
      (window as any).filamenthub?.importProfile ||
      (window as any).wx?.postMessage
    );
    setIsInOrcaSlicer(inOrca || false);
    
    // Если в OrcaSlicer, подписываемся на ответы от C++
    if (inOrca) {
      const handleMessage = (event: MessageEvent) => {
        try {
          const data = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
          if (data.command === 'import_profile') {
            setIsImporting(false);
            if (data.status === 'success') {
              // Показываем уведомление об успехе (можно заменить на toast)
              console.log('✅ Профиль успешно импортирован:', data.message);
            } else if (data.status === 'error') {
              // Показываем ошибку
              alert(`❌ Ошибка импорта: ${data.message || 'Неизвестная ошибка'}`);
            }
          }
        } catch (e) {
          // Игнорируем сообщения, которые не являются ответами от OrcaSlicer
        }
      };
      
      window.addEventListener('message', handleMessage);
      
      // Cleanup при размонтировании
      return () => {
        window.removeEventListener('message', handleMessage);
      };
    }
  }, []); // Пустой массив зависимостей = выполняется только при монтировании
  
  // Загружаем филамент для отображения информации
  const { data: filament } = useQuery({
    queryKey: ['filament', preset.filament_id],
    queryFn: () => filamentsAPI.get(preset.filament_id),
  });

  // Загружаем бренд
  const { data: brand } = useQuery({
    queryKey: ['brand', filament?.brand_id],
    queryFn: () => brandsAPI.get(filament!.brand_id),
    enabled: !!filament?.brand_id,
  });

  // Обработчик скачивания пресета в формате OrcaSlicer
  const handleDownload = async () => {
    if (isDownloading) return; // Предотвращаем множественные клики
    
    setIsDownloading(true);
    try {
      // Получаем JSON ответ от сервера
      const response = await api.get(`/presets/${preset.id}/export/orcaslicer.json`, {
        responseType: 'json', // Получаем JSON (axios автоматически парсит)
      });

      const jsonContent = response.data;
      
      // Получаем имя файла из заголовка Content-Disposition
      let filename = 'preset.json';
      
      // Пытаемся получить имя файла из заголовка Content-Disposition
      const contentDisposition = response.headers['content-disposition'] || response.headers['Content-Disposition'];
      
      if (contentDisposition) {
        // Парсим имя файла из заголовка
        // Формат: attachment; filename="filename.json" или attachment; filename=filename.json
        // Также поддерживаем: attachment; filename*=UTF-8''filename.json
        
        // Сначала пытаемся получить из filename*=UTF-8'' (RFC 5987)
        let matches = /filename\*=UTF-8''([^;]+)/i.exec(contentDisposition);
        if (matches && matches[1]) {
          // Декодируем имя файла из RFC 5987 формата
          filename = decodeURIComponent(matches[1]);
        } else {
          // Если нет filename*, пытаемся получить из обычного filename
          matches = /filename\s*=\s*"([^"]+)"|filename\s*=\s*([^;]+)/i.exec(contentDisposition);
          if (matches && (matches[1] || matches[2])) {
            filename = matches[1] || matches[2];
            // Убираем возможные пробелы и декодируем URL-encoded символы
            filename = filename.trim();
            try {
              filename = decodeURIComponent(filename);
            } catch (e) {
              // Если decodeURIComponent не работает, используем как есть
            }
          }
        }
      }
      
      // Если не получилось из заголовка, формируем имя из preset.name
      if (filename === 'preset.json' || !filename || filename === '') {
        // Формируем безопасное имя из preset.name (убираем только недопустимые символы для файловой системы)
        const safeName = preset.name
          .replace(/[<>:"/\\|?*]/g, '_') // Заменяем недопустимые символы
          .trim()
          .replace(/\s+/g, '_') // Заменяем пробелы на подчеркивания
          .substring(0, 100) || 'preset'; // Ограничиваем длину
        
        filename = `${safeName}.json`;
      }
      
      // Убеждаемся, что имя файла заканчивается на .json
      if (!filename.toLowerCase().endsWith('.json')) {
        filename = `${filename}.json`;
      }
      
      // Создаем blob из JSON с красивым форматированием
      const jsonString = JSON.stringify(jsonContent, null, 2);
      const blob = new Blob([jsonString], { 
        type: 'application/json;charset=utf-8' // Явно указываем кодировку для кириллицы
      });
      
      // Создаем blob URL для скачивания (не data URL, чтобы не открывался в браузере)
      const url = URL.createObjectURL(blob);
      
      // Создаем ссылку для скачивания
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      link.style.display = 'none';
      
      // Добавляем в DOM (обязательно для некоторых браузеров)
      document.body.appendChild(link);
      
      // Инициируем скачивание
      // Используем setTimeout для гарантии, что элемент добавлен в DOM
      setTimeout(() => {
        link.click();
        
        // Очищаем после задержки (чтобы скачивание успело начаться)
        setTimeout(() => {
          if (document.body.contains(link)) {
            document.body.removeChild(link);
          }
          URL.revokeObjectURL(url);
          setIsDownloading(false);
        }, 300);
      }, 0);
    } catch (error: any) {
      console.error('Ошибка скачивания пресета:', error);
      
      // Детальная обработка ошибок
      let errorMessage = 'Неизвестная ошибка';
      if (error.response) {
        // Ошибка от сервера
        const status = error.response.status;
        const data = error.response.data;
        
        if (status === 401) {
          errorMessage = 'Необходима авторизация. Пожалуйста, войдите в систему.';
        } else if (status === 404) {
          errorMessage = 'Пресет не найден.';
        } else if (status === 500) {
          const detail = data?.detail || 'Внутренняя ошибка сервера';
          errorMessage = `Ошибка сервера при экспорте: ${detail}`;
          console.error('Детали ошибки 500:', detail);
        } else {
          errorMessage = `Ошибка ${status}: ${data?.detail || data?.message || 'Ошибка запроса'}`;
        }
      } else if (error.request) {
        // Запрос был сделан, но ответа не получено
        errorMessage = 'Не удалось подключиться к серверу. Проверьте подключение.';
      } else {
        // Ошибка настройки запроса
        errorMessage = error.message || 'Ошибка при выполнении запроса';
      }
      
      alert(`Не удалось скачать пресет: ${errorMessage}`);
    } finally {
      setIsDownloading(false);
    }
  };

  return (
      <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
        <div className="flex items-center justify-between mb-4">
          <div className="flex-1">
            <div className="flex items-center space-x-2">
              <h4 className="text-xl font-bold text-white">{preset.name}</h4>
              {preset.printers && preset.printers.length > 0 && (
                <div className="flex items-center gap-1.5 flex-wrap">
                  {preset.printers.map((printer) => (
                    <span
                      key={printer.id}
                      className="px-2 py-0.5 bg-white/10 rounded-md text-xs text-gray-300 border border-white/20"
                      title={`${printer.manufacturer} ${printer.model}`}
                    >
                      {printer.name}
                    </span>
                  ))}
                </div>
              )}
              {preset.source === 'saved' && (
                <span className="px-2 py-0.5 bg-blue-600/30 rounded text-blue-300 text-xs font-medium">
                  Из каталога
                </span>
              )}
            </div>
          {filament && (
            <div 
              className="flex items-center space-x-2 mt-1 cursor-pointer hover:opacity-80 transition-opacity"
              onClick={() => navigate(`/filaments/${filament.id}`, { state: { from: 'profile' } })}
            >
              {brand && (
                <>
                  <span className={`text-sm font-medium ${brand.verified ? 'text-green-400' : 'text-gray-300'}`}>
                    {brand.name}
                  </span>
                  <span className="text-gray-500">•</span>
                </>
              )}
              <span className="text-gray-400 text-sm">{filament.name}</span>
              {filament.color_name && (
                <>
                  <span className="text-gray-500">•</span>
                  <span className="text-gray-400 text-sm">{filament.color_name}</span>
                </>
              )}
              <span className="px-2 py-0.5 bg-purple-600/30 rounded text-purple-300 text-xs font-medium">
                {filament.material_type}
              </span>
            </div>
          )}
        </div>
        <div className="flex space-x-2">
          {preset.source === 'own' && (
            <button
              onClick={() => onEdit?.(preset)}
              className="p-2 bg-white/10 hover:bg-white/20 rounded-lg text-white transition-all"
              title="Редактировать"
            >
              <Edit className="w-4 h-4" />
            </button>
          )}
          <button
            onClick={handleDownload}
            disabled={isDownloading}
            className="p-2 bg-white/10 hover:bg-white/20 rounded-lg text-white transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            title={isDownloading ? "Скачивание..." : "Скачать в формате OrcaSlicer"}
          >
            {isDownloading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Download className="w-4 h-4" />
            )}
          </button>
          <button
            onClick={() => onDelete?.(preset)}
            className="p-2 bg-white/10 hover:bg-red-500/20 rounded-lg text-white transition-all"
            title={preset.source === 'saved' ? 'Убрать из профиля' : 'Удалить'}
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mb-4 text-sm">
        <div className="flex items-center space-x-2">
          <Thermometer className="w-4 h-4 text-red-400" />
          <span className="text-gray-300">Сопло: {preset.extruder_temp}°C</span>
        </div>
        <div className="flex items-center space-x-2">
          <Thermometer className="w-4 h-4 text-red-400" />
          <span className="text-gray-300">Стол: {preset.bed_temp}°C</span>
        </div>
        <div className="flex items-center space-x-2">
          <Gauge className="w-4 h-4 text-blue-400" />
          <span className="text-gray-300">Скорость: {preset.print_speed}mm/s</span>
        </div>
        {preset.travel_speed && (
          <div className="flex items-center space-x-2">
            <Wind className="w-4 h-4 text-cyan-400" />
            <span className="text-gray-300">Перемещение: {preset.travel_speed}mm/s</span>
          </div>
        )}
        {preset.layer_height && (
          <div className="flex items-center space-x-2">
            <Ruler className="w-4 h-4 text-green-400" />
            <span className="text-gray-300">Слой: {preset.layer_height}mm</span>
          </div>
        )}
        {preset.first_layer_height && (
          <div className="flex items-center space-x-2">
            <Ruler className="w-4 h-4 text-green-300" />
            <span className="text-gray-300">Перв. слой: {preset.first_layer_height}mm</span>
          </div>
        )}
        {preset.flow_rate && (
          <div className="flex items-center space-x-2">
            <Gauge className="w-4 h-4 text-yellow-400" />
            <span className="text-gray-300">Поток: {preset.flow_rate}%</span>
          </div>
        )}
        {preset.fan_speed !== null && (
          <div className="flex items-center space-x-2">
            <Fan className="w-4 h-4 text-orange-400" />
            <span className="text-gray-300">Вентилятор: {preset.fan_speed}%</span>
          </div>
        )}
        {preset.retraction_length && (
          <div className="flex items-center space-x-2">
            <Wind className="w-4 h-4 text-purple-400" />
            <span className="text-gray-300">Ретракт: {preset.retraction_length}mm</span>
          </div>
        )}
        {preset.retraction_speed && (
          <div className="flex items-center space-x-2">
            <Gauge className="w-4 h-4 text-indigo-400" />
            <span className="text-gray-300">Ск. ретракт: {preset.retraction_speed}mm/s</span>
          </div>
        )}
        <div className="flex items-center space-x-2">
          <CheckCircle className="w-4 h-4 text-green-400" />
          <span className="text-gray-300">Использований: {preset.usage_count}</span>
        </div>
      </div>

      <div className="flex items-center justify-between text-sm">
        <div className="flex items-center space-x-3">
          <span className="text-gray-400">
            Создан: {new Date(preset.created_at).toLocaleDateString('ru-RU')}
          </span>
          {preset.created_at !== preset.updated_at && (
            <span className="text-blue-400">
              Изменён: {new Date(preset.updated_at).toLocaleDateString('ru-RU')}
            </span>
          )}
        </div>
        {preset.rating && (
          <div className="flex items-center space-x-1">
            <Star className="w-4 h-4 text-yellow-400 fill-current" />
            <span className="text-white">{preset.rating.toFixed(1)}</span>
          </div>
        )}
      </div>
    </div>
  );
};

interface HistoryItemProps {
  item: {
    id: number;
    material: string;
    printer: string;
    date: string;
    success: boolean;
    rating: number;
    notes: string;
  };
}

const HistoryItem: React.FC<HistoryItemProps> = ({ item }) => (
  <div className="flex items-center justify-between p-4 bg-white/5 rounded-xl border border-white/10">
    <div className="flex-1">
      <div className="flex items-center space-x-3 mb-2">
        {item.success ? (
          <CheckCircle className="w-5 h-5 text-green-400" />
        ) : (
          <XCircle className="w-5 h-5 text-red-400" />
        )}
        <div>
          <p className="text-white font-medium">{item.material}</p>
          <p className="text-gray-400 text-sm">{item.printer}</p>
        </div>
      </div>
      {item.notes && <p className="text-gray-300 text-sm">{item.notes}</p>}
    </div>
    <div className="text-right">
      <div className="flex items-center space-x-1 mb-1">
        <Star className="w-4 h-4 text-yellow-400 fill-current" />
        <span className="text-white">{item.rating}</span>
      </div>
      <p className="text-gray-400 text-sm">{item.date}</p>
    </div>
  </div>
);

// ЗАГЛУШКА: Калькулятор - простая математика, без G-code парсинга
const CalculatorComponent: React.FC = () => {
  const [weight, setWeight] = useState<number>(100);
  const [timeHours, setTimeHours] = useState<number>(1);
  const [pricePerKg, setPricePerKg] = useState<number>(500);
  const [electricityCost, setElectricityCost] = useState<number>(5);
  const [printerPower, setPrinterPower] = useState<number>(200);

  const calculateCost = () => {
    const filamentCost = (weight / 1000) * pricePerKg;
    const electricityCostTotal = (printerPower / 1000) * timeHours * electricityCost;
    const total = filamentCost + electricityCostTotal;

    return {
      filament: filamentCost,
      electricity: electricityCostTotal,
      total,
    };
  };

  const costs = calculateCost();

  return (
    <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-8 border border-white/20 shadow-xl">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        <div>
          <label className="block text-gray-300 mb-3 text-sm font-medium">Вес детали (г)</label>
          <input
            type="number"
            value={weight}
            onChange={(e) => setWeight(Number(e.target.value))}
            className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
            placeholder="100"
          />
        </div>
        <div>
          <label className="block text-gray-300 mb-3 text-sm font-medium">
            Стоимость электроэнергии (₽/кВт·ч)
          </label>
          <input
            type="number"
            step="0.1"
            value={electricityCost}
            onChange={(e) => setElectricityCost(Number(e.target.value))}
            className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
            placeholder="5"
          />
        </div>
        <div>
          <label className="block text-gray-300 mb-3 text-sm font-medium">
            Цена материала (₽/кг)
          </label>
          <input
            type="number"
            value={pricePerKg}
            onChange={(e) => setPricePerKg(Number(e.target.value))}
            className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
            placeholder="500"
          />
        </div>
        <div>
          <label className="block text-gray-300 mb-3 text-sm font-medium">Время печати (часы)</label>
          <input
            type="number"
            step="0.1"
            value={timeHours}
            onChange={(e) => setTimeHours(Number(e.target.value))}
            className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
            placeholder="1"
          />
        </div>
        <div>
          <label className="block text-gray-300 mb-3 text-sm font-medium">Мощность принтера (Вт)</label>
          <input
            type="number"
            value={printerPower}
            onChange={(e) => setPrinterPower(Number(e.target.value))}
            className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
            placeholder="200"
          />
        </div>
      </div>

      {/* Results */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <ResultCard
          label="Пластик"
          value={costs.filament.toFixed(2)}
          icon={Package}
          color="from-purple-500/20 to-pink-500/20"
          borderColor="border-purple-500/30"
        />
        <ResultCard
          label="Электроэнергия"
          value={costs.electricity.toFixed(2)}
          icon={Gauge}
          color="from-blue-500/20 to-cyan-500/20"
          borderColor="border-blue-500/30"
        />
        <ResultCard
          label="Итого"
          value={costs.total.toFixed(2)}
          icon={Calculator}
          color="from-green-500/20 to-emerald-500/20"
          borderColor="border-green-500/30"
          isTotal
        />
      </div>
    </div>
  );
};

interface ResultCardProps {
  label: string;
  value: string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
  borderColor: string;
  isTotal?: boolean;
}

const ResultCard: React.FC<ResultCardProps> = ({ label, value, icon: Icon, color, borderColor, isTotal }) => (
  <div className={`bg-gradient-to-r ${color} p-6 rounded-2xl border ${borderColor} shadow-xl`}>
    <div className="text-3xl font-bold mb-2" style={{ color: isTotal ? '#10b981' : '#ffffff' }}>
      {value}₽
    </div>
    <div className="text-gray-300 flex items-center">
      <Icon className="w-4 h-4 mr-2" />
      {label}
    </div>
  </div>
);

