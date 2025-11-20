/** Страница профиля пользователя */

import { useState, useMemo, useEffect, type ReactNode } from 'react';
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
  Eye,
  DollarSign,
  Clock,
  Filter,
  RotateCcw,
  Cog,
  Layers,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { presetsAPI, filamentsAPI, brandsAPI, savedPresetsAPI, filamentReviewsAPI, calculatorAPI, printerProfilesAPI, printProfilesAPI, authAPI } from '../api/client';
import api from '../api/client';
import { CreatePresetModal } from '../components/CreatePresetModal';
import { ViewPresetModal } from '../components/ViewPresetModal';
import { CreatePrinterRequestModal } from '../components/CreatePrinterRequestModal';
import { DeleteAccountModal } from '../components/DeleteAccountModal';
import { SettingsTab } from '../components/SettingsTab';
import { ExportFromOrcaSlicerButton } from '../components/ExportFromOrcaSlicerButton';
import { ExportPrinterProfilesButton } from '../components/ExportPrinterProfilesButton';
import { ExportPrintProfilesButton } from '../components/ExportPrintProfilesButton';
import { CreatePrinterProfileModal } from '../components/CreatePrinterProfileModal';
import { CreatePrintProfileModal } from '../components/CreatePrintProfileModal';
import { PresetSyncToggle } from '../components/PresetSyncToggle';
import { BadgeList } from '../components/Badge';
import { BrandProfilePage } from './BrandProfilePage';
import type { Preset, PricingMethod, CalculatorEstimateRequest, PrinterProfile, PrintProfile } from '../types/api';

export const ProfilePage: React.FC = () => {
  const { user, refreshUser } = useAuth();
  const queryClient = useQueryClient();
  const [showBrandCabinet, setShowBrandCabinet] = useState(false); // Показывать ли кабинет производителя
  const [userTab, setUserTab] = useState<'dashboard' | 'presets' | 'history' | 'calculator' | 'settings' | 'printer-profiles' | 'print-profiles'>(
    'dashboard'
  );
  const [isCreatePresetModalOpen, setIsCreatePresetModalOpen] = useState(false);
  const [isViewPresetModalOpen, setIsViewPresetModalOpen] = useState(false);
  const [isCreatePrinterRequestModalOpen, setIsCreatePrinterRequestModalOpen] = useState(false);
  const [editingPreset, setEditingPreset] = useState<Preset | null>(null);
  const [viewingPreset, setViewingPreset] = useState<Preset | null>(null);
  const [selectedPrinterProfile, setSelectedPrinterProfile] = useState<PrinterProfile | null>(null);
  const [selectedPrintProfile, setSelectedPrintProfile] = useState<PrintProfile | null>(null);
  const [isCreatePrinterProfileModalOpen, setIsCreatePrinterProfileModalOpen] = useState(false);
  const [isCreatePrintProfileModalOpen, setIsCreatePrintProfileModalOpen] = useState(false);
  const [editingPrinterProfile, setEditingPrinterProfile] = useState<PrinterProfile | null>(null);
  const [editingPrintProfile, setEditingPrintProfile] = useState<PrintProfile | null>(null);
  const [isDeleteAccountModalOpen, setIsDeleteAccountModalOpen] = useState(false);
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');

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

  const { data: printerProfilesData, isLoading: isLoadingPrinterProfiles } = useQuery({
    queryKey: ['printer-profiles', user?.id],
    queryFn: () =>
      printerProfilesAPI.list({
        owner_user_id: user!.id,
        page: 1,
        size: 50,
        active_only: false,
      }),
    enabled: !!user?.id,
  });

  const { data: printProfilesData, isLoading: isLoadingPrintProfiles } = useQuery({
    queryKey: ['print-profiles', user?.id],
    queryFn: () =>
      printProfilesAPI.list({
        owner_user_id: user!.id,
        page: 1,
        size: 50,
        active_only: false,
      }),
    enabled: !!user?.id,
  });

  // Объединяем пресеты: созданные пользователем + сохранённые из каталога
  // Исключаем из сохранённых те, которые уже есть в созданных (чтобы не было дублей)
  const allMyPresets = useMemo(() => {
    const created = (userPresetsData?.items || []).map(p => ({ ...p, source: 'own' as const }));
    const createdIds = new Set(created.map(p => p.id));
    const saved = (savedPresetsDetails || [])
      .filter(p => !createdIds.has(p.id)) // Исключаем пресеты, которые уже созданы пользователем
      .map(p => ({ ...p, source: 'saved' as const }));
    return [...created, ...saved];
  }, [userPresetsData, savedPresetsDetails]);

  const userPresets = allMyPresets;

  const myPrinterProfiles = useMemo(() => printerProfilesData?.items ?? [], [printerProfilesData]);
  const myPrintProfiles = useMemo(() => printProfilesData?.items ?? [], [printProfilesData]);

  const [printProfileQualityFilter, setPrintProfileQualityFilter] = useState<string | null>(null);
  const [printProfileNozzleFilter, setPrintProfileNozzleFilter] = useState<string | null>(null);
  const [printProfilePrinterFilter, setPrintProfilePrinterFilter] = useState<string | null>(null);
  const [printProfileOnlyOfficial, setPrintProfileOnlyOfficial] = useState<boolean>(false);
  const [printProfileOnlyActive, setPrintProfileOnlyActive] = useState<boolean>(false);

  const printProfileQualityOptions = useMemo(() => {
    const order = ['superdraft', 'draft', 'standard', 'optimal', 'fine', 'highdetail'];
    const unique = new Set<string>();
    myPrintProfiles.forEach(profile => {
      if (profile.quality_tier) {
        unique.add(profile.quality_tier.toLowerCase());
      }
    });
    const sorted = Array.from(unique);
    sorted.sort((a, b) => {
      const indexA = order.indexOf(a);
      const indexB = order.indexOf(b);
      const safeA = indexA === -1 ? order.length : indexA;
      const safeB = indexB === -1 ? order.length : indexB;
      if (safeA === safeB) {
        return a.localeCompare(b);
      }
      return safeA - safeB;
    });
    return sorted;
  }, [myPrintProfiles]);

  const printProfileNozzleOptions = useMemo(() => {
    const unique = new Set<string>();
    myPrintProfiles.forEach(profile => {
      if (profile.default_nozzle) {
        unique.add(profile.default_nozzle.trim());
      }
    });
    const sorted = Array.from(unique).sort((a, b) => {
      const numA = parseFloat(a);
      const numB = parseFloat(b);
      const isNumA = Number.isFinite(numA);
      const isNumB = Number.isFinite(numB);
      if (isNumA && isNumB) {
        return numA - numB;
      }
      if (isNumA) {
        return -1;
      }
      if (isNumB) {
        return 1;
      }
      return a.localeCompare(b);
    });
    return sorted;
  }, [myPrintProfiles]);

  const printProfilePrinterOptions = useMemo(() => {
    const unique = new Set<string>();
    myPrintProfiles.forEach(profile => {
      profile.printer_links?.forEach(link => {
        if (link.printer_slug) {
          unique.add(link.printer_slug);
        }
      });
    });
    return Array.from(unique).sort();
  }, [myPrintProfiles]);

  const filteredPrintProfiles = useMemo(() => {
    return myPrintProfiles.filter(profile => {
      if (printProfileOnlyOfficial && !profile.is_official) {
        return false;
      }
      if (printProfileOnlyActive && !profile.active) {
        return false;
      }
      if (printProfileQualityFilter && (profile.quality_tier || '').toLowerCase() !== printProfileQualityFilter) {
        return false;
      }
      if (printProfileNozzleFilter && profile.default_nozzle?.trim() !== printProfileNozzleFilter) {
        return false;
      }
      if (printProfilePrinterFilter) {
        const hasPrinter = profile.printer_links?.some(link => link.printer_slug === printProfilePrinterFilter);
        if (!hasPrinter) {
          return false;
        }
      }
      return true;
    });
  }, [
    myPrintProfiles,
    printProfileOnlyOfficial,
    printProfileOnlyActive,
    printProfileQualityFilter,
    printProfileNozzleFilter,
    printProfilePrinterFilter,
  ]);

  const resetPrintProfileFilters = () => {
    setPrintProfileQualityFilter(null);
    setPrintProfileNozzleFilter(null);
    setPrintProfilePrinterFilter(null);
    setPrintProfileOnlyOfficial(false);
    setPrintProfileOnlyActive(false);
  };

  useEffect(() => {
    if (printProfileQualityFilter && !printProfileQualityOptions.includes(printProfileQualityFilter)) {
      setPrintProfileQualityFilter(null);
    }
    if (printProfileNozzleFilter && !printProfileNozzleOptions.includes(printProfileNozzleFilter)) {
      setPrintProfileNozzleFilter(null);
    }
    if (printProfilePrinterFilter && !printProfilePrinterOptions.includes(printProfilePrinterFilter)) {
      setPrintProfilePrinterFilter(null);
    }
  }, [
    printProfileQualityFilter,
    printProfileNozzleFilter,
    printProfilePrinterFilter,
    printProfileQualityOptions,
    printProfileNozzleOptions,
    printProfilePrinterOptions,
  ]);

  // Загружаем отзывы пользователя
  const { data: userReviewsData } = useQuery({
    queryKey: ['user-reviews', user?.id],
    queryFn: () => filamentReviewsAPI.getMyReviews({ page: 1, size: 100, active_only: true }),
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

  // Загружаем статистику пресетов
  const { data: presetsStats } = useQuery({
    queryKey: ['presets-stats', user?.id],
    queryFn: () => authAPI.getPresetsStats(),
    enabled: !!user?.id,
  });

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

  const handleViewPreset = (preset: Preset) => {
    setViewingPreset(preset);
    setIsViewPresetModalOpen(true);
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

  const formatDateTime = (value: string) =>
    new Date(value).toLocaleString('ru-RU', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });

  const safeFileName = (value: string) =>
    (value || '')
      .trim()
      .normalize('NFKD')
      .replace(/[\u0300-\u036f]/g, '')
      .replace(/[\s/\\:]+/g, '-')
      .replace(/[^a-zA-Z0-9а-яА-ЯёЁ_.-]+/g, '-')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '')
      .toLowerCase();

  const downloadJSONFile = (payload: Record<string, any>, filename: string) => {
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const handleDownloadPrinterProfile = async (profile: PrinterProfile) => {
    try {
      const response = await api.get(`/printer-profiles/${profile.id}/export/orcaslicer.json`, {
        responseType: 'blob',
      });
      
      const blob = new Blob([response.data], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      
      const base = safeFileName(profile.slug || profile.name || `printer-profile-${profile.id}`);
      const filename = `${base || 'printer-profile'}.orca_printer.json`;
      
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error: any) {
      console.error('Ошибка скачивания printer profile:', error);
      const errorMessage = error?.response?.data?.detail || error?.message || 'Неизвестная ошибка';
      alert(`Не удалось скачать профиль принтера: ${errorMessage}`);
    }
  };

  const handleDownloadPrintProfile = async (profile: PrintProfile) => {
    try {
      const response = await api.get(`/print-profiles/${profile.id}/export/orcaslicer.json`, {
        responseType: 'blob',
      });
      
      const blob = new Blob([response.data], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      
      const base = safeFileName(profile.slug || profile.name || `print-profile-${profile.id}`);
      const filename = `${base || 'print-profile'}.orca_process.json`;
      
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error: any) {
      console.error('Ошибка скачивания print profile:', error);
      const errorMessage = error?.response?.data?.detail || error?.message || 'Неизвестная ошибка';
      alert(`Не удалось скачать профиль печати: ${errorMessage}`);
    }
  };

  const combinationsDraftCount = 0;

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
    <div className="space-y-10">
      {/* Переключатель профилей */}
      <div className="flex justify-center mb-6">
        <div className="flex bg-white/10 rounded-lg p-1 border border-white/20">
          <button
            onClick={() => setShowBrandCabinet(false)}
            className={`flex items-center space-x-2 px-6 py-2 rounded-lg transition-all ${
              !showBrandCabinet 
                ? 'bg-purple-600 text-white shadow-lg shadow-purple-500/25' 
                : 'text-gray-300 hover:text-white'
            }`}
          >
            <User className="w-4 h-4" />
            <span>Профиль пользователя</span>
          </button>
          <button
            onClick={() => setShowBrandCabinet(true)}
            className={`flex items-center space-x-2 px-6 py-2 rounded-lg transition-all ${
              showBrandCabinet 
                ? 'bg-green-600 text-white shadow-lg shadow-green-500/25' 
                : 'text-gray-300 hover:text-white'
            }`}
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
            <h2 className="text-3xl font-bold text-white mb-1">Мой профиль</h2>
            <div className="flex items-center gap-2">
              <p className="text-gray-300">
                {user.full_name || user.username} • 3D печатник
              </p>
              {user.badges && user.badges.length > 0 && (
                <BadgeList badges={user.badges as any} size="sm" />
              )}
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex justify-center space-x-2 mt-4">
          {[
            { id: 'dashboard', label: 'Дашборд', icon: Play },
            { id: 'presets', label: 'Профили филамента', icon: Settings },
            { id: 'printer-profiles', label: 'Профили принтера', icon: Printer },
            { id: 'print-profiles', label: 'Профили печати', icon: Layers },
            { id: 'history', label: 'История', icon: TrendingUp },
            { id: 'calculator', label: 'Калькулятор', icon: Calculator },
            { id: 'settings', label: 'Настройки', icon: Cog },
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
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <StatCard
              icon={CheckCircle}
              label="Успешных печатей"
              value={reviewsStats.successCount.toString()}
              color="from-purple-500/20 to-pink-500/20"
              borderColor="border-purple-500/30"
              iconColor="text-green-400"
            />
            {/* Объединённая плашка для пресетов */}
            <div className="bg-gradient-to-r from-blue-500/20 to-cyan-500/20 p-6 rounded-2xl border border-blue-500/30 shadow-xl">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-gray-300 text-sm mb-1">Пресеты</p>
                  <p className="text-3xl font-bold text-white">
                    {presetsStats?.total_presets?.toString() || userPresets.length.toString()}/{presetsStats?.synced_presets?.toString() || '0'}
                  </p>
                  <p className="text-xs text-gray-400 mt-1">всего / к синхронизации</p>
                </div>
                <Settings className="w-8 h-8 text-blue-400" />
              </div>
            </div>
            <StatCard
              icon={Star}
              label="Оставлено отзывов"
              value={reviewsStats.totalReviews.toString()}
              color="from-purple-500/20 to-pink-500/20"
              borderColor="border-purple-500/30"
              iconColor="text-purple-400"
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
            <h3 className="text-2xl font-bold text-white">Профили филамента</h3>
            <div className="flex items-center gap-3">
              {/* Кнопка экспорта из OrcaSlicer (только если запущено внутри OrcaSlicer) */}
              {typeof window !== 'undefined' && (window as any).filamenthub?.exportFilamentPresets && (
                <ExportFromOrcaSlicerButton />
              )}
              <button
                onClick={handleCreatePreset}
                className="bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white px-4 py-2 rounded-xl transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40"
              >
                <Plus className="w-4 h-4 inline mr-2" />
                Новый пресет
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {userPresets.map((preset) => (
              <PresetCard
                key={preset.id}
                preset={preset}
                onEdit={handleEditPreset}
                onView={handleViewPreset}
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

      {/* Printer Profiles Tab */}
      {userTab === 'printer-profiles' && (
        <div className="space-y-6">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-2xl font-bold text-white">Мои профили принтера</h2>
              <p className="text-sm text-gray-400">
                Настройки принтеров, которые можно синхронизировать между FilamentHub и OrcaSlicer.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <StatusBadge label={`${myPrinterProfiles.length} шт.`} variant="accent" />
              {/* Кнопка экспорта из OrcaSlicer */}
              <ExportPrinterProfilesButton />
              <button
                type="button"
                className="px-4 py-2 rounded-lg border border-white/20 text-sm text-white hover:bg-white/10 transition-all"
                onClick={() => {
                  setEditingPrinterProfile(null);
                  setIsCreatePrinterProfileModalOpen(true);
                }}
                title="Создать профиль принтера"
              >
                <Plus className="w-4 h-4 inline mr-2" />
                Добавить вручную
              </button>
            </div>
          </div>

          {isLoadingPrinterProfiles ? (
            <ProfileSectionLoader />
          ) : myPrinterProfiles.length > 0 ? (
            <div className="grid gap-6 md:grid-cols-2">
              {myPrinterProfiles.map((profile) => (
                <PrinterProfileCard
                  key={profile.id}
                  profile={profile}
                  formatDateTime={formatDateTime}
                  onView={(item) => setSelectedPrinterProfile(item)}
                  onDownload={handleDownloadPrinterProfile}
                />
              ))}
            </div>
          ) : (
            <EmptyState
              icon={Printer}
              title="Пока нет профилей принтера"
              description="Импортируйте профиль из OrcaSlicer или создайте его вручную - он появится здесь."
              actionLabel="Создать профиль принтера"
              onAction={() => {
                setEditingPrinterProfile(null);
                setIsCreatePrinterProfileModalOpen(true);
              }}
            />
          )}
        </div>
      )}

      {/* Print Profiles Tab */}
      {userTab === 'print-profiles' && (
        <div className="space-y-6">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-2xl font-bold text-white">Мои профили печати</h2>
              <p className="text-sm text-gray-400">
                Наборы настроек (Print Settings) для разных задач. Их тоже будем синхронизировать с OrcaSlicer.
              </p>
            </div>
            <div className="flex items-center gap-3">
              <StatusBadge
                label={
                  printProfileQualityFilter ||
                  printProfileNozzleFilter ||
                  printProfilePrinterFilter ||
                  printProfileOnlyOfficial ||
                  printProfileOnlyActive
                    ? `${filteredPrintProfiles.length}/${myPrintProfiles.length} шт.`
                    : `${myPrintProfiles.length} шт.`
                }
                variant="accent"
              />
              {/* Кнопка экспорта из OrcaSlicer */}
              <ExportPrintProfilesButton />
              <button
                type="button"
                onClick={() => {
                  setEditingPrintProfile(null);
                  setIsCreatePrintProfileModalOpen(true);
                }}
                className="px-4 py-2 rounded-lg border border-white/20 text-sm text-white hover:bg-white/10 transition-all"
                title="Создать профиль печати"
              >
                <Plus className="w-4 h-4 inline mr-2" />
                Добавить вручную
              </button>
            </div>
          </div>

          {isLoadingPrintProfiles ? (
            <ProfileSectionLoader />
          ) : myPrintProfiles.length > 0 ? (
            <>
              <PrintProfileFilters
                qualityOptions={printProfileQualityOptions}
                nozzleOptions={printProfileNozzleOptions}
                printerOptions={printProfilePrinterOptions}
                qualityFilter={printProfileQualityFilter}
                nozzleFilter={printProfileNozzleFilter}
                printerFilter={printProfilePrinterFilter}
                onlyOfficial={printProfileOnlyOfficial}
                onlyActive={printProfileOnlyActive}
                onQualityChange={value =>
                  setPrintProfileQualityFilter(prev => (prev === value ? null : value))
                }
                onNozzleChange={value =>
                  setPrintProfileNozzleFilter(prev => (prev === value ? null : value))
                }
                onPrinterChange={value =>
                  setPrintProfilePrinterFilter(prev => (prev === value ? null : value))
                }
                onToggleOfficial={() => setPrintProfileOnlyOfficial(prev => !prev)}
                onToggleActive={() => setPrintProfileOnlyActive(prev => !prev)}
                onReset={resetPrintProfileFilters}
              />

              {filteredPrintProfiles.length > 0 ? (
                <div className="grid gap-6 md:grid-cols-2">
                  {filteredPrintProfiles.map(profile => (
                    <PrintProfileCard
                      key={profile.id}
                      profile={profile}
                      formatDateTime={formatDateTime}
                      onView={item => setSelectedPrintProfile(item)}
                      onDownload={handleDownloadPrintProfile}
                    />
                  ))}
                </div>
              ) : (
                <EmptyState
                  icon={Filter}
                  title="Нет профилей под выбранные фильтры"
                  description="Попробуйте изменить параметры или сбросить фильтры, чтобы увидеть остальные профили."
                  actionLabel="Сбросить фильтры"
                  onAction={resetPrintProfileFilters}
                />
              )}
            </>
          ) : (
            <EmptyState
              icon={Settings}
              title="Пока нет профилей печати"
              description="Импортируйте настройки из OrcaSlicer или создайте их на базе FilamentHub, чтобы ускорить подготовку печати."
            />
          )}
        </div>
      )}

      {/* Settings Tab */}
      {userTab === 'settings' && user && (
        <SettingsTab user={user} onUserUpdate={refreshUser} />
      )}

      {/* Create/Edit Preset Modal */}
      <CreatePresetModal
        isOpen={isCreatePresetModalOpen}
        onClose={handleClosePresetModal}
        preset={editingPreset}
      />

      {/* View Preset Modal */}
      <ViewPresetModal
        isOpen={isViewPresetModalOpen}
        onClose={() => {
          setIsViewPresetModalOpen(false);
          setViewingPreset(null);
        }}
        preset={viewingPreset}
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

      {/* Create/Edit Printer Profile Modal */}
      <CreatePrinterProfileModal
        isOpen={isCreatePrinterProfileModalOpen}
        onClose={() => {
          setIsCreatePrinterProfileModalOpen(false);
          setEditingPrinterProfile(null);
        }}
        profile={editingPrinterProfile}
        onRequestPrinter={() => {
          // Закрываем текущую модалку и открываем модалку создания заявки
          setIsCreatePrinterProfileModalOpen(false);
          setIsCreatePrinterRequestModalOpen(true);
        }}
      />

      {/* Create/Edit Print Profile Modal */}
      <CreatePrintProfileModal
        isOpen={isCreatePrintProfileModalOpen}
        onClose={() => {
          setIsCreatePrintProfileModalOpen(false);
          setEditingPrintProfile(null);
        }}
        profile={editingPrintProfile}
      />

      {/* Combined Profiles Section (только на dashboard) */}
      {userTab === 'dashboard' && (
        <section className="mt-12 space-y-5">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-2xl font-bold text-white">Комбинации профилей</h2>
              <p className="text-sm text-gray-400">
                В планах — собирать связки «принтер + профиль печати + материал» и применять их в один клик.
              </p>
            </div>
            <StatusBadge label="в разработке" variant="muted" />
          </div>

          <div className="bg-white/5 border border-dashed border-white/20 rounded-2xl p-6 text-gray-200">
            <p className="text-lg text-white font-semibold mb-2">Конструктор сетапов готовится к запуску.</p>
            <p className="text-sm text-gray-300">
              После внедрения обратного импорта OrcaSlicer вы сможете сохранять готовые наборы и делиться ими с командой или друзьями.
            </p>

            <div className="mt-4 grid gap-4 md:grid-cols-3">
              <InfoSummary label="Черновиков профилей принтера" value={myPrinterProfiles.length} />
              <InfoSummary label="Черновиков профилей печати" value={myPrintProfiles.length} />
              <InfoSummary label="Доступных пресетов" value={userPresets.length} />
            </div>

            <p className="mt-4 text-xs text-gray-400 uppercase tracking-wide">
              Комбинаций пока: {combinationsDraftCount}
            </p>
          </div>
        </section>
      )}

      {/* Кнопка удаления аккаунта */}
      <div className="mt-12 pt-6 border-t border-white/20">
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

      {selectedPrinterProfile && (
        <PrinterProfileModal
          profile={selectedPrinterProfile}
          onClose={() => setSelectedPrinterProfile(null)}
          formatDateTime={formatDateTime}
        />
      )}

      {selectedPrintProfile && (
        <PrintProfileModal
          profile={selectedPrintProfile}
          onClose={() => setSelectedPrintProfile(null)}
          formatDateTime={formatDateTime}
        />
      )}
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
        <p className="text-gray-400 text-center py-4">Пока нет истории печати</p>
      )}
    </div>
  </div>
);

interface PresetCardProps {
  preset: Preset;
  onEdit?: (preset: Preset) => void;
  onView?: (preset: Preset) => void;
  onDelete?: (preset: Preset) => void;
}

const PresetCard: React.FC<PresetCardProps> = ({ preset, onEdit, onView, onDelete }) => {
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
        <div className="flex items-start justify-between mb-4 gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center flex-wrap gap-2 mb-1">
              <h4 className="text-xl font-bold text-white break-words">{preset.name}</h4>
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
                <span className="px-2 py-0.5 bg-blue-600/30 rounded text-blue-300 text-xs font-medium whitespace-nowrap">
                  Из каталога
                </span>
              )}
              {preset.is_weighted && (
                <span className="px-2 py-0.5 bg-green-600/30 rounded text-green-300 text-xs font-medium whitespace-nowrap">
                  Генеративный
                </span>
              )}
            </div>
          {filament && (
            <div className="mt-1 cursor-pointer hover:opacity-80 transition-opacity" onClick={() => navigate(`/filaments/${filament.id}`, { state: { from: 'profile' } })}>
              <div className="flex items-baseline gap-x-2">
                {brand && (
                  <span className={`text-sm font-medium ${brand.verified ? 'text-green-400' : 'text-gray-300'} break-words inline-block max-w-[calc(100%-250px)]`}>
                    {brand.name}
                  </span>
                )}
                <div className="flex items-center gap-x-2 flex-shrink-0 whitespace-nowrap">
                  {brand && <span className="text-gray-500">•</span>}
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
              </div>
            </div>
          )}
        </div>
        <div className="flex space-x-2">
          {preset.source === 'own' ? (
            <button
              onClick={() => onEdit?.(preset)}
              className="p-2 bg-white/10 hover:bg-white/20 rounded-lg text-white transition-all"
              title="Редактировать"
            >
              <Edit className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={() => onView?.(preset)}
              className="p-2 bg-white/10 hover:bg-white/20 rounded-lg text-white transition-all"
              title="Посмотреть пресет подробно"
            >
              <Eye className="w-4 h-4" />
            </button>
          )}
          {/* Переключатель синхронизации - показываем для всех пресетов */}
          <PresetSyncToggle preset={preset} size="sm" className="p-2 bg-white/10 hover:bg-white/20 rounded-lg" />
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
        {preset.flow_rate && (
          <div className="flex items-center space-x-2">
            <Gauge className="w-4 h-4 text-yellow-400" />
            <span className="text-gray-300">Поток: {preset.flow_rate}%</span>
          </div>
        )}
        {preset.fan_speed !== null && (
          <div className="flex items-center space-x-2">
            <Fan className="w-4 h-4 text-orange-400" />
            <span className="text-gray-300">Обдув: {preset.fan_speed}%</span>
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

// Калькулятор стоимости печати с поддержкой трех методов расчета
const CalculatorComponent: React.FC = () => {
  const [pricingMethod, setPricingMethod] = useState<PricingMethod>('combined');
  
  // Параметры материала
  const [weightG, setWeightG] = useState<number>(531);
  const [supportsWeightG, setSupportsWeightG] = useState<number>(0);
  const [supportsLossCoefficient, setSupportsLossCoefficient] = useState<number>(1.2);
  const [spoolPrice, setSpoolPrice] = useState<number>(1200);
  const [spoolWeightKg, setSpoolWeightKg] = useState<number>(1);
  const [deliveryCost, setDeliveryCost] = useState<number>(0);
  
  // Параметры времени печати
  const [timeHours, setTimeHours] = useState<number>(13);
  const [timeMinutes, setTimeMinutes] = useState<number>(40);
  const [timeSec, setTimeSec] = useState<number>(0);
  
  // Почасовая ставка печати (для by_time)
  const [pricePerHour, setPricePerHour] = useState<number>(170);
  
  // Электроэнергия
  const [electricityCostPerKwh, setElectricityCostPerKwh] = useState<number>(6);
  const [printerPowerW, setPrinterPowerW] = useState<number>(350);
  
  // Дополнительные услуги
  const [modelingHours, setModelingHours] = useState<number>(0);
  const [modelingMinutes, setModelingMinutes] = useState<number>(0);
  const [modelingRatePerHour, setModelingRatePerHour] = useState<number>(934);
  
  const [postprocessingHours, setPostprocessingHours] = useState<number>(0);
  const [postprocessingMinutes, setPostprocessingMinutes] = useState<number>(2);
  const [postprocessingRatePerHour, setPostprocessingRatePerHour] = useState<number>(100);
  
  const [printingRatePerHour, setPrintingRatePerHour] = useState<number>(170);
  const [amortizationRatePerHour, setAmortizationRatePerHour] = useState<number>(16);
  
  // Количество деталей
  const [quantity, setQuantity] = useState<number>(4);
  
  // Накладные расходы и наценка
  const [overheadPercent, setOverheadPercent] = useState<number>(20);
  const [markupPercent, setMarkupPercent] = useState<number>(30);
  
  // Коэффициенты корректировки
  const [urgencyCoefficient, setUrgencyCoefficient] = useState<number>(1.0);
  const [complexityCoefficient, setComplexityCoefficient] = useState<number>(1.0);
  const [volumeDiscountCoefficient, setVolumeDiscountCoefficient] = useState<number>(1.0);
  
  // Фиксированные расходы и минимальная цена
  const [fixedCosts, setFixedCosts] = useState<number>(0);
  const [minOrderPrice, setMinOrderPrice] = useState<number>(0);
  
  // Округление
  const [roundToNearest, setRoundToNearest] = useState<number>(10);

  // Мутация для расчета
  const calculateMutation = useMutation({
    mutationFn: (data: CalculatorEstimateRequest) => calculatorAPI.estimate(data),
  });

  const handleCalculate = () => {
    const requestData: CalculatorEstimateRequest = {
      pricing_method: pricingMethod,
      quantity,
      round_to_nearest: roundToNearest || undefined,
    };

    // Добавляем параметры в зависимости от метода
    if (pricingMethod === 'by_weight' || pricingMethod === 'combined') {
      requestData.weight_g = weightG;
      requestData.supports_weight_g = supportsWeightG || undefined;
      requestData.supports_loss_coefficient = supportsLossCoefficient || undefined;
      requestData.spool_price = spoolPrice;
      requestData.spool_weight_kg = spoolWeightKg;
      requestData.delivery_cost = deliveryCost;
    }

    if (pricingMethod === 'by_time' || pricingMethod === 'combined') {
      requestData.time_hours = timeHours;
      requestData.time_minutes = timeMinutes;
      requestData.time_sec = timeSec || undefined;
    }

    if (pricingMethod === 'by_time') {
      requestData.price_per_hour = pricePerHour;
    }

    if (electricityCostPerKwh && printerPowerW) {
      requestData.electricity_cost_per_kwh = electricityCostPerKwh;
      requestData.printer_power_w = printerPowerW;
    }

    if (pricingMethod === 'combined') {
      if (modelingRatePerHour) {
        requestData.modeling_hours = modelingHours;
        requestData.modeling_minutes = modelingMinutes;
        requestData.modeling_rate_per_hour = modelingRatePerHour;
      }
      if (postprocessingRatePerHour) {
        requestData.postprocessing_hours = postprocessingHours;
        requestData.postprocessing_minutes = postprocessingMinutes;
        requestData.postprocessing_rate_per_hour = postprocessingRatePerHour;
      }
      if (printingRatePerHour) {
        requestData.printing_rate_per_hour = printingRatePerHour;
      }
      if (amortizationRatePerHour) {
        requestData.amortization_rate_per_hour = amortizationRatePerHour;
      }
      
      // Накладные расходы и наценка
      requestData.overhead_percent = overheadPercent || undefined;
      requestData.markup_percent = markupPercent || undefined;
      
      // Коэффициенты корректировки
      requestData.urgency_coefficient = urgencyCoefficient !== 1.0 ? urgencyCoefficient : undefined;
      requestData.complexity_coefficient = complexityCoefficient !== 1.0 ? complexityCoefficient : undefined;
      requestData.volume_discount_coefficient = volumeDiscountCoefficient !== 1.0 ? volumeDiscountCoefficient : undefined;
      
      // Фиксированные расходы и минимальная цена
      requestData.fixed_costs = fixedCosts || undefined;
      requestData.min_order_price = minOrderPrice || undefined;
    }

    calculateMutation.mutate(requestData);
  };

  const result = calculateMutation.data;

  return (
    <div className="space-y-6">
      {/* Переключатель методов */}
      <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
        <label className="block text-gray-300 mb-4 text-sm font-medium">Метод расчета</label>
        <div className="flex flex-wrap gap-3">
          {[
            { value: 'by_weight', label: 'По граммам' },
            { value: 'by_time', label: 'По часам' },
            { value: 'combined', label: 'Комбинированный' },
          ].map((method) => (
            <button
              key={method.value}
              onClick={() => setPricingMethod(method.value as PricingMethod)}
              className={`px-4 py-2 rounded-lg transition-all ${
                pricingMethod === method.value
                  ? 'bg-purple-600 text-white shadow-lg shadow-purple-500/25'
                  : 'bg-white/10 text-gray-300 hover:text-white hover:bg-white/20'
              }`}
            >
              {method.label}
            </button>
          ))}
        </div>
      </div>

      {/* Параметры материала */}
      {(pricingMethod === 'by_weight' || pricingMethod === 'combined') && (
        <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
          <h3 className="text-xl font-bold text-white mb-4 flex items-center">
            <Package className="w-5 h-5 mr-2" />
            Параметры материала
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Вес детали (г)</label>
              <input
                type="number"
                value={weightG}
                onChange={(e) => setWeightG(Number(e.target.value) || 0)}
                className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                placeholder="531"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Вес поддержек (г)</label>
              <input
                type="number"
                value={supportsWeightG}
                onChange={(e) => setSupportsWeightG(Number(e.target.value) || 0)}
                className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                placeholder="0"
              />
              <p className="text-xs text-gray-400 mt-1">Обычно 15-30% от веса детали</p>
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Коэффициент потерь на поддержки</label>
              <input
                type="number"
                step="0.1"
                min="1.0"
                max="2.0"
                value={supportsLossCoefficient}
                onChange={(e) => setSupportsLossCoefficient(Number(e.target.value) || 1.2)}
                className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                placeholder="1.2"
              />
              <p className="text-xs text-gray-400 mt-1">Обычно 1.2-1.3</p>
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Цена катушки (₽)</label>
              <input
                type="number"
                value={spoolPrice}
                onChange={(e) => setSpoolPrice(Number(e.target.value) || 0)}
                className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                placeholder="1200"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Вес катушки (кг)</label>
              <input
                type="number"
                step="0.1"
                value={spoolWeightKg}
                onChange={(e) => setSpoolWeightKg(Number(e.target.value) || 0)}
                className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                placeholder="1"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Доставка (₽)</label>
              <input
                type="number"
                value={deliveryCost}
                onChange={(e) => setDeliveryCost(Number(e.target.value) || 0)}
                className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                placeholder="0"
              />
            </div>
          </div>
        </div>
      )}

      {/* Параметры времени печати */}
      {(pricingMethod === 'by_time' || pricingMethod === 'combined') && (
        <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
          <h3 className="text-xl font-bold text-white mb-4 flex items-center">
            <Gauge className="w-5 h-5 mr-2" />
            Время печати
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Часы</label>
              <input
                type="number"
                value={timeHours}
                onChange={(e) => setTimeHours(Number(e.target.value) || 0)}
                className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                placeholder="13"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Минуты</label>
              <input
                type="number"
                value={timeMinutes}
                onChange={(e) => setTimeMinutes(Number(e.target.value) || 0)}
                className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                placeholder="40"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Секунды</label>
              <input
                type="number"
                value={timeSec}
                onChange={(e) => setTimeSec(Number(e.target.value) || 0)}
                className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                placeholder="0"
              />
            </div>
          </div>
        </div>
      )}

      {/* Почасовая ставка (для by_time) */}
      {pricingMethod === 'by_time' && (
        <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
          <h3 className="text-xl font-bold text-white mb-4">Почасовая ставка</h3>
          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">Цена за час печати (₽/ч)</label>
            <input
              type="number"
              value={pricePerHour}
              onChange={(e) => setPricePerHour(Number(e.target.value) || 0)}
              className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              placeholder="170"
            />
          </div>
        </div>
      )}

      {/* Электроэнергия */}
      <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
        <h3 className="text-xl font-bold text-white mb-4 flex items-center">
          <Wind className="w-5 h-5 mr-2" />
          Электроэнергия
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">Стоимость 1 кВт·ч (₽)</label>
            <input
              type="number"
              step="0.1"
              value={electricityCostPerKwh}
              onChange={(e) => setElectricityCostPerKwh(Number(e.target.value) || 0)}
              className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              placeholder="6"
            />
          </div>
          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">Мощность принтера (Вт)</label>
            <input
              type="number"
              value={printerPowerW}
              onChange={(e) => setPrinterPowerW(Number(e.target.value) || 0)}
              className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              placeholder="350"
            />
          </div>
        </div>
      </div>

      {/* Дополнительные услуги (только для combined) */}
      {pricingMethod === 'combined' && (
        <>
          <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
            <h3 className="text-xl font-bold text-white mb-4 flex items-center">
              <Settings className="w-5 h-5 mr-2" />
              Дополнительные услуги
            </h3>
            <div className="space-y-4">
              {/* Моделирование */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">Моделирование (ч)</label>
                  <input
                    type="number"
                    value={modelingHours}
                    onChange={(e) => setModelingHours(Number(e.target.value) || 0)}
                    className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    placeholder="0"
                  />
                </div>
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">Моделирование (мин)</label>
                  <input
                    type="number"
                    value={modelingMinutes}
                    onChange={(e) => setModelingMinutes(Number(e.target.value) || 0)}
                    className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    placeholder="0"
                  />
                </div>
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">Ставка (₽/ч)</label>
                  <input
                    type="number"
                    value={modelingRatePerHour}
                    onChange={(e) => setModelingRatePerHour(Number(e.target.value) || 0)}
                    className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    placeholder="934"
                  />
                </div>
              </div>

              {/* Печать */}
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Ставка печати (₽/ч)</label>
                <input
                  type="number"
                  value={printingRatePerHour}
                  onChange={(e) => setPrintingRatePerHour(Number(e.target.value) || 0)}
                  className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="170"
                />
              </div>

              {/* Постобработка */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">Постобработка (ч)</label>
                  <input
                    type="number"
                    value={postprocessingHours}
                    onChange={(e) => setPostprocessingHours(Number(e.target.value) || 0)}
                    className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    placeholder="0"
                  />
                </div>
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">Постобработка (мин)</label>
                  <input
                    type="number"
                    value={postprocessingMinutes}
                    onChange={(e) => setPostprocessingMinutes(Number(e.target.value) || 0)}
                    className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    placeholder="2"
                  />
                </div>
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">Ставка (₽/ч)</label>
                  <input
                    type="number"
                    value={postprocessingRatePerHour}
                    onChange={(e) => setPostprocessingRatePerHour(Number(e.target.value) || 0)}
                    className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    placeholder="100"
                  />
                </div>
              </div>

              {/* Амортизация */}
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Ставка амортизации (₽/ч)</label>
                <input
                  type="number"
                  value={amortizationRatePerHour}
                  onChange={(e) => setAmortizationRatePerHour(Number(e.target.value) || 0)}
                  className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="16"
                />
              </div>
            </div>
          </div>
        </>
      )}

      {/* Накладные расходы и наценка (только для combined) */}
      {pricingMethod === 'combined' && (
        <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
          <h3 className="text-xl font-bold text-white mb-4 flex items-center">
            <TrendingUp className="w-5 h-5 mr-2" />
            Накладные расходы и наценка
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Накладные расходы (%)</label>
              <input
                type="number"
                step="0.1"
                min="0"
                max="100"
                value={overheadPercent}
                onChange={(e) => setOverheadPercent(Number(e.target.value) || 0)}
                className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                placeholder="20"
              />
              <p className="text-xs text-gray-400 mt-1">Обычно 20-30%</p>
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Наценка (%)</label>
              <input
                type="number"
                step="0.1"
                min="0"
                max="200"
                value={markupPercent}
                onChange={(e) => setMarkupPercent(Number(e.target.value) || 0)}
                className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                placeholder="30"
              />
              <p className="text-xs text-gray-400 mt-1">Эконом: 20-30%, Стандарт: 35-45%, Премиум: 50-70%</p>
            </div>
          </div>
        </div>
      )}

      {/* Коэффициенты корректировки (только для combined) */}
      {pricingMethod === 'combined' && (
        <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
          <h3 className="text-xl font-bold text-white mb-4 flex items-center">
            <Settings className="w-5 h-5 mr-2" />
            Коэффициенты корректировки
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Срочность</label>
              <input
                type="number"
                step="0.1"
                min="1.0"
                max="2.0"
                value={urgencyCoefficient}
                onChange={(e) => setUrgencyCoefficient(Number(e.target.value) || 1.0)}
                className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                placeholder="1.0"
              />
              <p className="text-xs text-gray-400 mt-1">1.0 = стандарт, 1.2-1.5 = срочно (+20-50%)</p>
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Сложность</label>
              <input
                type="number"
                step="0.1"
                min="1.0"
                max="3.0"
                value={complexityCoefficient}
                onChange={(e) => setComplexityCoefficient(Number(e.target.value) || 1.0)}
                className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                placeholder="1.0"
              />
              <p className="text-xs text-gray-400 mt-1">1.0 = просто, 1.2-2.5 = сложно (+15-30%)</p>
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Скидка за объем</label>
              <input
                type="number"
                step="0.01"
                min="0.85"
                max="1.0"
                value={volumeDiscountCoefficient}
                onChange={(e) => setVolumeDiscountCoefficient(Number(e.target.value) || 1.0)}
                className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                placeholder="1.0"
              />
              <p className="text-xs text-gray-400 mt-1">1.0 = без скидки, 0.85-0.95 = скидка 5-15%</p>
            </div>
          </div>
        </div>
      )}

      {/* Количество, фиксированные расходы и округление */}
      <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">Количество деталей</label>
            <input
              type="number"
              value={quantity}
              onChange={(e) => setQuantity(Number(e.target.value) || 1)}
              className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              placeholder="4"
              min="1"
            />
          </div>
          {pricingMethod === 'combined' && (
            <>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Фиксированные расходы (₽)</label>
                <input
                  type="number"
                  value={fixedCosts}
                  onChange={(e) => setFixedCosts(Number(e.target.value) || 0)}
                  className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="0"
                />
                <p className="text-xs text-gray-400 mt-1">Упаковка, доставка до ПВЗ (обычно 50-100 ₽)</p>
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Минимальная цена заказа (₽)</label>
                <input
                  type="number"
                  value={minOrderPrice}
                  onChange={(e) => setMinOrderPrice(Number(e.target.value) || 0)}
                  className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="0"
                />
                <p className="text-xs text-gray-400 mt-1">Если цена меньше, устанавливается минимум (обычно 300-500 ₽)</p>
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Округлить до (₽)</label>
                <input
                  type="number"
                  value={roundToNearest}
                  onChange={(e) => setRoundToNearest(Number(e.target.value) || 0)}
                  className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="10"
                />
              </div>
            </>
          )}
        </div>
      </div>

      {/* Кнопка расчета */}
      <div className="flex justify-center">
        <button
          onClick={handleCalculate}
          disabled={calculateMutation.isPending}
          className="px-8 py-4 bg-purple-600 hover:bg-purple-700 text-white rounded-xl font-semibold text-lg shadow-lg shadow-purple-500/25 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
        >
          {calculateMutation.isPending ? (
            <>
              <Loader2 className="w-5 h-5 animate-spin" />
              <span>Расчет...</span>
            </>
          ) : (
            <>
              <Calculator className="w-5 h-5" />
              <span>Рассчитать</span>
            </>
          )}
        </button>
      </div>

      {/* Результаты */}
      {result && (
        <div className="space-y-4">
          {/* Компоненты стоимости */}
          <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
            <h3 className="text-xl font-bold text-white mb-4">Компоненты стоимости</h3>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              {result.cost_material > 0 && (
                <ResultCard
                  label="Материал"
                  value={result.cost_material.toFixed(2)}
                  icon={Package}
                  color="from-purple-500/20 to-pink-500/20"
                  borderColor="border-purple-500/30"
                />
              )}
              {result.cost_electricity > 0 && (
                <ResultCard
                  label="Электроэнергия"
                  value={result.cost_electricity.toFixed(2)}
                  icon={Wind}
                  color="from-blue-500/20 to-cyan-500/20"
                  borderColor="border-blue-500/30"
                />
              )}
              {result.cost_modeling > 0 && (
                <ResultCard
                  label="Моделирование"
                  value={result.cost_modeling.toFixed(2)}
                  icon={Settings}
                  color="from-orange-500/20 to-red-500/20"
                  borderColor="border-orange-500/30"
                />
              )}
              {result.cost_printing > 0 && (
                <ResultCard
                  label="Печать"
                  value={result.cost_printing.toFixed(2)}
                  icon={Printer}
                  color="from-indigo-500/20 to-purple-500/20"
                  borderColor="border-indigo-500/30"
                />
              )}
              {result.cost_postprocessing > 0 && (
                <ResultCard
                  label="Постобработка"
                  value={result.cost_postprocessing.toFixed(2)}
                  icon={Fan}
                  color="from-teal-500/20 to-green-500/20"
                  borderColor="border-teal-500/30"
                />
              )}
              {result.cost_amortization > 0 && (
                <ResultCard
                  label="Амортизация"
                  value={result.cost_amortization.toFixed(2)}
                  icon={Gauge}
                  color="from-gray-500/20 to-slate-500/20"
                  borderColor="border-gray-500/30"
                />
              )}
            </div>
          </div>

          {/* Промежуточные расчеты (только для combined) */}
          {pricingMethod === 'combined' && result.cost_direct > 0 && (
            <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
              <h3 className="text-xl font-bold text-white mb-4">Промежуточные расчеты</h3>
              <div className="space-y-3">
                <div className="flex justify-between items-center py-2 border-b border-white/10">
                  <span className="text-gray-300">Прямые затраты</span>
                  <span className="text-white font-semibold">{result.cost_direct.toFixed(2)} ₽</span>
                </div>
                {result.cost_overhead > 0 && (
                  <div className="flex justify-between items-center py-2 border-b border-white/10">
                    <span className="text-gray-300">Накладные расходы</span>
                    <span className="text-white font-semibold">{result.cost_overhead.toFixed(2)} ₽</span>
                  </div>
                )}
                <div className="flex justify-between items-center py-2 border-b border-white/10">
                  <span className="text-gray-300">Стоимость до наценки</span>
                  <span className="text-white font-semibold">{result.cost_before_markup.toFixed(2)} ₽</span>
                </div>
                {result.cost_markup > 0 && (
                  <div className="flex justify-between items-center py-2 border-b border-white/10">
                    <span className="text-gray-300">Наценка</span>
                    <span className="text-white font-semibold">{result.cost_markup.toFixed(2)} ₽</span>
                  </div>
                )}
                {(result.applied_urgency_coefficient || result.applied_complexity_coefficient || result.applied_volume_discount) && (
                  <div className="pt-2 space-y-1">
                    <p className="text-sm text-gray-400">Примененные коэффициенты:</p>
                    {result.applied_urgency_coefficient && result.applied_urgency_coefficient !== 1.0 && (
                      <div className="flex justify-between items-center text-sm">
                        <span className="text-gray-300">Срочность</span>
                        <span className="text-white">×{result.applied_urgency_coefficient.toFixed(2)}</span>
                      </div>
                    )}
                    {result.applied_complexity_coefficient && result.applied_complexity_coefficient !== 1.0 && (
                      <div className="flex justify-between items-center text-sm">
                        <span className="text-gray-300">Сложность</span>
                        <span className="text-white">×{result.applied_complexity_coefficient.toFixed(2)}</span>
                      </div>
                    )}
                    {result.applied_volume_discount && result.applied_volume_discount !== 1.0 && (
                      <div className="flex justify-between items-center text-sm">
                        <span className="text-gray-300">Скидка за объем</span>
                        <span className="text-white">×{result.applied_volume_discount.toFixed(2)}</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Финансовые показатели и время (только для combined) */}
          {pricingMethod === 'combined' && (result.profit_margin !== undefined || result.total_time_hours) && (
            <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
              <h3 className="text-xl font-bold text-white mb-4 flex items-center">
                <TrendingUp className="w-5 h-5 mr-2" />
                Финансовые показатели
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {result.cost_of_goods_sold !== undefined && result.cost_of_goods_sold !== null && (
                  <div className="bg-white/5 rounded-xl p-4 border border-white/10">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-gray-300 text-sm">Себестоимость</span>
                      <DollarSign className="w-4 h-4 text-gray-400" />
                    </div>
                    <div className="text-2xl font-bold text-white">{result.cost_of_goods_sold.toFixed(2)} ₽</div>
                    <p className="text-xs text-gray-400 mt-1">Прямые затраты + накладные + фиксированные</p>
                  </div>
                )}
                {result.profit_margin !== undefined && result.profit_margin !== null && (
                  <div className="bg-green-500/10 rounded-xl p-4 border border-green-500/30">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-green-300 text-sm">Маржа (прибыль)</span>
                      <TrendingUp className="w-4 h-4 text-green-400" />
                    </div>
                    <div className="text-2xl font-bold text-green-400">
                      {result.profit_margin.toFixed(2)} ₽
                      {result.profit_margin_percent !== undefined && result.profit_margin_percent !== null && (
                        <span className="text-lg ml-2">({result.profit_margin_percent.toFixed(1)}%)</span>
                      )}
                    </div>
                    <p className="text-xs text-green-200 mt-1">Финальная цена - Себестоимость</p>
                  </div>
                )}
                {result.total_time_hours && (
                  <div className="bg-blue-500/10 rounded-xl p-4 border border-blue-500/30 md:col-span-2">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-blue-300 text-sm">Общее время работы</span>
                      <Clock className="w-4 h-4 text-blue-400" />
                    </div>
                    <div className="text-2xl font-bold text-blue-400">
                      {result.total_time_hours.toFixed(2)} ч
                      {result.total_time_hours >= 1 && (
                        <span className="text-lg ml-2">
                          ({Math.floor(result.total_time_hours)} ч {Math.round((result.total_time_hours % 1) * 60)} мин)
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-blue-200 mt-1">Печать + подготовка + постобработка</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Итоговые суммы */}
          <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
            <h3 className="text-xl font-bold text-white mb-4">Итоговые суммы</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {result.quantity > 1 && (
                <>
                  <ResultCard
                    label="Цена первой детали"
                    value={result.cost_first_part.toFixed(2)}
                    icon={Star}
                    color="from-yellow-500/20 to-orange-500/20"
                    borderColor="border-yellow-500/30"
                  />
                  <ResultCard
                    label="Цена последующих"
                    value={result.cost_subsequent_parts.toFixed(2)}
                    icon={Package}
                    color="from-blue-500/20 to-indigo-500/20"
                    borderColor="border-blue-500/30"
                  />
                </>
              )}
              <ResultCard
                label={result.quantity > 1 ? 'Общая стоимость' : 'Итого'}
                value={result.cost_final ? result.cost_final.toFixed(2) : result.cost_total.toFixed(2)}
                icon={Calculator}
                color="from-green-500/20 to-emerald-500/20"
                borderColor="border-green-500/30"
                isTotal
              />
            </div>
          </div>
        </div>
      )}

      {/* Ошибка */}
      {calculateMutation.isError && (
        <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4">
          <p className="text-red-300">
            Ошибка расчета: {calculateMutation.error instanceof Error ? calculateMutation.error.message : 'Неизвестная ошибка'}
          </p>
        </div>
      )}
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

const ProfileSectionLoader: React.FC = () => (
  <div className="flex items-center justify-center gap-3 py-12 text-gray-300">
    <Loader2 className="w-5 h-5 animate-spin" />
    <span>Загружаем профили...</span>
  </div>
);

type StatusVariant = 'default' | 'accent' | 'success' | 'warning' | 'muted';

const STATUS_BADGE_STYLES: Record<StatusVariant, string> = {
  default: 'bg-white/10 text-gray-200 border border-white/20',
  accent: 'bg-purple-500/15 text-purple-200 border border-purple-500/30',
  success: 'bg-green-500/15 text-green-200 border border-green-500/30',
  warning: 'bg-yellow-500/15 text-yellow-200 border border-yellow-500/30',
  muted: 'bg-white/5 text-gray-400 border border-white/10',
};

interface StatusBadgeProps {
  label: string;
  variant?: StatusVariant;
}

const StatusBadge: React.FC<StatusBadgeProps> = ({ label, variant = 'default' }) => (
  <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium uppercase tracking-wide ${STATUS_BADGE_STYLES[variant]}`}>
    {label}
  </span>
);

interface EmptyStateProps {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
  actionLabel?: string;
  onAction?: () => void;
}

const EmptyState: React.FC<EmptyStateProps> = ({ icon: Icon, title, description, actionLabel, onAction }) => (
  <div className="bg-white/5 border border-white/10 rounded-2xl p-10 text-center flex flex-col items-center gap-4">
    <Icon className="w-12 h-12 text-gray-400" />
    <div>
      <h3 className="text-xl font-semibold text-white">{title}</h3>
      <p className="text-sm text-gray-300 mt-1 max-w-xl">{description}</p>
    </div>
    {actionLabel && onAction && (
      <button
        type="button"
        onClick={onAction}
        className="px-4 py-2 rounded-lg bg-white/10 hover:bg-white/15 border border-white/20 text-sm text-white transition-all"
      >
        {actionLabel}
      </button>
    )}
  </div>
);

interface InfoSummaryProps {
  label: string;
  value: number | string;
}

const InfoSummary: React.FC<InfoSummaryProps> = ({ label, value }) => (
  <div className="bg-white/5 border border-white/10 rounded-xl p-4">
    <p className="text-xs uppercase tracking-wide text-gray-400">{label}</p>
    <p className="text-lg font-semibold text-white mt-1">{value}</p>
  </div>
);

interface InfoRowProps {
  label: string;
  value: ReactNode;
}

const InfoRow: React.FC<InfoRowProps> = ({ label, value }) => (
  <div>
    <p className="text-xs uppercase tracking-wide text-gray-400">{label}</p>
    <p className="text-sm text-white mt-1 break-words">{value ?? '—'}</p>
  </div>
);

interface PrinterProfileCardProps {
  profile: PrinterProfile;
  formatDateTime: (value: string) => string;
  onView: (profile: PrinterProfile) => void;
  onDownload: (profile: PrinterProfile) => void;
}

const PrinterProfileCard: React.FC<PrinterProfileCardProps> = ({ profile, formatDateTime, onView, onDownload }) => (
  <div className="bg-white/10 backdrop-blur-sm border border-white/15 rounded-2xl p-6 shadow-xl">
    <div className="flex items-start justify-between gap-3">
      <div>
        <h3 className="text-xl font-semibold text-white">{profile.name}</h3>
        <p className="text-sm text-gray-400">Slug: {profile.slug}</p>
        {profile.printer_slug && (
          <p className="text-xs text-gray-400 mt-1">Принтер: {profile.printer_name ?? profile.printer_slug}</p>
        )}
      </div>
      <div className="flex flex-wrap gap-2 justify-end">
        <StatusBadge label={profile.active ? 'Активен' : 'Отключен'} variant={profile.active ? 'success' : 'muted'} />
        {profile.is_official && <StatusBadge label="Официальный" variant="accent" />}
      </div>
    </div>
    {profile.description && (
      <p className="mt-3 text-sm text-gray-300 line-clamp-3">{profile.description}</p>
    )}
    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <InfoRow label="Привязка к принтеру" value={profile.printer_id ? `ID ${profile.printer_id}` : 'не указана'} />
      <InfoRow label="Обновлён" value={formatDateTime(profile.updated_at)} />
      <InfoRow label="Default Print Profile" value={profile.default_print_profile_slug || 'не задан'} />
      <InfoRow
        label="Диаметры сопел"
        value={profile.nozzle_diameters && profile.nozzle_diameters.length > 0 ? profile.nozzle_diameters.join(', ') : 'не указаны'}
      />
      <InfoRow
        label="Высота печати"
        value={
          typeof profile.printable_height_mm === 'number' ? `${profile.printable_height_mm.toFixed(0)} мм` : 'не указана'
        }
      />
      <InfoRow label="Стартовый G-code" value={profile.start_gcode ? 'задан' : '—'} />
      <InfoRow label="Финальный G-code" value={profile.end_gcode ? 'задан' : '—'} />
    </div>
    <div className="mt-4 flex flex-wrap gap-2">
      <button
        type="button"
        onClick={() => onView(profile)}
        className="px-4 py-2 rounded-lg border border-white/20 text-sm text-white/90 hover:bg-white/10 transition-all flex items-center gap-2"
      >
        <Eye className="w-4 h-4" />
        Смотреть JSON
      </button>
      <button
        type="button"
        onClick={() => onDownload(profile)}
        className="px-4 py-2 rounded-lg border border-white/20 text-sm text-white/90 hover:bg-white/10 transition-all flex items-center gap-2"
      >
        <Download className="w-4 h-4" />
        Скачать JSON
      </button>
    </div>
  </div>
);

interface PrintProfileCardProps {
  profile: PrintProfile;
  formatDateTime: (value: string) => string;
  onView: (profile: PrintProfile) => void;
  onDownload: (profile: PrintProfile) => void;
}

const PrintProfileCard: React.FC<PrintProfileCardProps> = ({ profile, formatDateTime, onView, onDownload }) => {
  const printersCount = profile.printer_links?.length ?? 0;
  const filamentsCount = profile.filament_links?.length ?? 0;
  const defaultNozzle = profile.default_nozzle ? `${profile.default_nozzle} мм` : 'не указано';
  const layerHeight =
    typeof profile.layer_height_mm === 'number' ? `${profile.layer_height_mm.toFixed(2)} мм` : 'не указана';

  return (
    <div className="bg-white/10 backdrop-blur-sm border border-white/15 rounded-2xl p-6 shadow-xl">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-xl font-semibold text-white">{profile.name}</h3>
          <p className="text-sm text-gray-400">Slug: {profile.slug}</p>
        </div>
        <div className="flex flex-wrap gap-2 justify-end">
          <StatusBadge label={profile.active ? 'Активен' : 'Отключен'} variant={profile.active ? 'success' : 'muted'} />
          {profile.is_official && <StatusBadge label="Официальный" variant="accent" />}
        </div>
      </div>
      {profile.description && (
        <p className="mt-3 text-sm text-gray-300 line-clamp-3">{profile.description}</p>
      )}
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <InfoRow label="Категория" value={profile.category || 'не указана'} />
        <InfoRow label="Качество" value={profile.quality_tier || 'не указано'} />
        <InfoRow label="Обновлён" value={formatDateTime(profile.updated_at)} />
        <InfoRow label="Сопло (по умолчанию)" value={defaultNozzle} />
        <InfoRow label="Высота слоя" value={layerHeight} />
        <InfoRow label="Совместимые принтеры" value={`${printersCount} шт.`} />
        <InfoRow label="Совместимые филаменты" value={`${filamentsCount} шт.`} />
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => onView(profile)}
          className="px-4 py-2 rounded-lg border border-white/20 text-sm text-white/90 hover:bg-white/10 transition-all flex items-center gap-2"
        >
          <Eye className="w-4 h-4" />
          Смотреть JSON
        </button>
        <button
          type="button"
          onClick={() => onDownload(profile)}
          className="px-4 py-2 rounded-lg border border-white/20 text-sm text-white/90 hover:bg-white/10 transition-all flex items-center gap-2"
        >
          <Download className="w-4 h-4" />
          Скачать JSON
        </button>
      </div>
    </div>
  );
};

interface FilterChipProps {
  label: string;
  active: boolean;
  onClick: () => void;
}

const FilterChip: React.FC<FilterChipProps> = ({ label, active, onClick }) => (
  <button
    type="button"
    onClick={onClick}
    className={`px-3 py-1.5 rounded-lg border transition-all text-xs sm:text-sm ${
      active
        ? 'border-purple-400 bg-purple-500/20 text-white shadow-[0_0_18px_rgba(168,85,247,0.2)]'
        : 'border-white/10 bg-white/5 text-gray-300 hover:border-purple-400 hover:text-white'
    }`}
  >
    {label}
  </button>
);

const formatQualityLabel = (value: string) => {
  const map: Record<string, string> = {
    superdraft: 'Супер Draft',
    draft: 'Draft',
    standard: 'Standard',
    optimal: 'Optimal',
    fine: 'Fine',
    highdetail: 'High Detail',
  };
  return map[value] ?? value;
};

const formatPrinterLabel = (slug: string) => slug.replace(/-/g, ' ');

interface PrintProfileFiltersProps {
  qualityOptions: string[];
  nozzleOptions: string[];
  printerOptions: string[];
  qualityFilter: string | null;
  nozzleFilter: string | null;
  printerFilter: string | null;
  onlyOfficial: boolean;
  onlyActive: boolean;
  onQualityChange: (value: string) => void;
  onNozzleChange: (value: string) => void;
  onPrinterChange: (value: string) => void;
  onToggleOfficial: () => void;
  onToggleActive: () => void;
  onReset: () => void;
}

const PrintProfileFilters: React.FC<PrintProfileFiltersProps> = ({
  qualityOptions,
  nozzleOptions,
  printerOptions,
  qualityFilter,
  nozzleFilter,
  printerFilter,
  onlyOfficial,
  onlyActive,
  onQualityChange,
  onNozzleChange,
  onPrinterChange,
  onToggleOfficial,
  onToggleActive,
  onReset,
}) => {
  const hasActiveFilters =
    !!qualityFilter || !!nozzleFilter || !!printerFilter || onlyOfficial || onlyActive;

  return (
    <div className="bg-white/5 border border-white/10 rounded-2xl p-4 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-medium uppercase tracking-wide text-gray-300">
          <Filter className="w-4 h-4" />
          Фильтры
        </div>
        <button
          type="button"
          onClick={onReset}
          disabled={!hasActiveFilters}
          className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-medium transition-all ${
            hasActiveFilters
              ? 'border-purple-400 text-purple-200 hover:bg-purple-500/10'
              : 'border-white/10 text-gray-500 cursor-not-allowed'
          }`}
        >
          <RotateCcw className="w-4 h-4" />
          Сбросить
        </button>
      </div>

      {qualityOptions.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-gray-400 uppercase tracking-wide">Класс качества</p>
          <div className="flex flex-wrap gap-2">
            {qualityOptions.map(option => (
              <FilterChip
                key={option}
                label={formatQualityLabel(option)}
                active={qualityFilter === option}
                onClick={() => onQualityChange(option)}
              />
            ))}
          </div>
        </div>
      )}

      {nozzleOptions.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-gray-400 uppercase tracking-wide">Сопло</p>
          <div className="flex flex-wrap gap-2">
            {nozzleOptions.map(option => (
              <FilterChip
                key={option}
                label={`${option} мм`}
                active={nozzleFilter === option}
                onClick={() => onNozzleChange(option)}
              />
            ))}
          </div>
        </div>
      )}

      {printerOptions.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-gray-400 uppercase tracking-wide">Принтер</p>
          <div className="flex flex-wrap gap-2">
            {printerOptions.map(option => (
              <FilterChip
                key={option}
                label={formatPrinterLabel(option)}
                active={printerFilter === option}
                onClick={() => onPrinterChange(option)}
              />
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <FilterChip
          label="Только официальные"
          active={onlyOfficial}
          onClick={onToggleOfficial}
        />
        <FilterChip label="Только активные" active={onlyActive} onClick={onToggleActive} />
      </div>
    </div>
  );
};

interface PrinterProfileModalProps {
  profile: PrinterProfile;
  onClose: () => void;
  formatDateTime: (value: string) => string;
}

const PrinterProfileModal: React.FC<PrinterProfileModalProps> = ({ profile, onClose, formatDateTime }) => {
  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-4xl max-h-[85vh] overflow-hidden rounded-2xl border border-white/20 bg-white/10 backdrop-blur-md shadow-2xl">
        <div className="flex items-start justify-between gap-4 px-6 pt-6 pb-4 border-b border-white/10">
          <div>
            <h3 className="text-2xl font-semibold text-white">{profile.name}</h3>
            <p className="text-sm text-gray-300">Slug: {profile.slug}</p>
          </div>
          <button
            type="button"
            className="text-gray-300 hover:text-white transition-colors"
            onClick={onClose}
          >
            <XCircle className="w-5 h-5" />
          </button>
        </div>
        <div className="px-6 pb-6 pt-2 space-y-6 overflow-y-auto max-h-[70vh] custom-scrollbar">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <InfoRow label="ID профиля" value={`#${profile.id}`} />
            <InfoRow label="Привязка к принтеру" value={profile.printer_id ? `ID ${profile.printer_id}` : 'не указана'} />
            <InfoRow label="Создан" value={formatDateTime(profile.created_at)} />
            <InfoRow label="Обновлён" value={formatDateTime(profile.updated_at)} />
            <InfoRow label="Тип" value={profile.is_official ? 'Официальный' : 'Пользовательский'} />
            <InfoRow label="Статус" value={profile.active ? 'Активен' : 'Отключен'} />
            <InfoRow label="Источник" value={profile.source || 'не указан'} />
            <InfoRow label="Вендор" value={profile.vendor || 'не указан'} />
            <InfoRow label="Setting ID" value={profile.setting_id || '—'} />
            <InfoRow label="External ID" value={profile.external_id || '—'} />
            <InfoRow
              label="Диаметры сопел"
              value={profile.nozzle_diameters && profile.nozzle_diameters.length > 0 ? profile.nozzle_diameters.join(', ') : 'не указаны'}
            />
            <InfoRow
              label="Высота печати"
              value={
                typeof profile.printable_height_mm === 'number' ? `${profile.printable_height_mm.toFixed(0)} мм` : 'не указана'
              }
            />
            <InfoRow label="Default Print Profile" value={profile.default_print_profile_slug || 'не задан'} />
          </div>
          {profile.description && (
            <div>
              <h4 className="text-sm font-semibold text-white mb-2">Описание</h4>
              <p className="text-sm text-gray-200 whitespace-pre-wrap">{profile.description}</p>
            </div>
          )}
          {profile.notes && (
            <div>
              <h4 className="text-sm font-semibold text-white mb-2">Заметки</h4>
              <p className="text-sm text-gray-200 whitespace-pre-wrap">{profile.notes}</p>
            </div>
          )}
          {profile.start_gcode && (
            <div>
              <h4 className="text-sm font-semibold text-white mb-2">Стартовый G-code</h4>
              <pre className="bg-black/40 border border-white/10 rounded-xl p-4 text-xs text-gray-200 overflow-auto max-h-60 whitespace-pre-wrap">
                {profile.start_gcode}
              </pre>
            </div>
          )}
          {profile.end_gcode && (
            <div>
              <h4 className="text-sm font-semibold text-white mb-2">Финальный G-code</h4>
              <pre className="bg-black/40 border border-white/10 rounded-xl p-4 text-xs text-gray-200 overflow-auto max-h-60 whitespace-pre-wrap">
                {profile.end_gcode}
              </pre>
            </div>
          )}
          <div>
            <h4 className="text-sm font-semibold text-white mb-2">Настройки OrcaSlicer</h4>
            <pre className="bg-black/40 border border-white/10 rounded-xl p-4 text-xs text-gray-200 overflow-auto max-h-72 whitespace-pre">
              {JSON.stringify(profile.orcaslicer_settings ?? {}, null, 2)}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
};

interface PrintProfileModalProps {
  profile: PrintProfile;
  onClose: () => void;
  formatDateTime: (value: string) => string;
}

const PrintProfileModal: React.FC<PrintProfileModalProps> = ({ profile, onClose, formatDateTime }) => {
  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [onClose]);

  const printersList = profile.printer_links ?? [];
  const filamentsList = profile.filament_links ?? [];
  const defaultNozzle = profile.default_nozzle ? `${profile.default_nozzle} мм` : 'не указано';
  const layerHeight =
    typeof profile.layer_height_mm === 'number' ? `${profile.layer_height_mm.toFixed(2)} мм` : 'не указана';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-4xl max-h-[85vh] overflow-hidden rounded-2xl border border-white/20 bg-white/10 backdrop-blur-md shadow-2xl">
        <div className="flex items-start justify-between gap-4 px-6 pt-6 pb-4 border-b border-white/10">
          <div>
            <h3 className="text-2xl font-semibold text-white">{profile.name}</h3>
            <p className="text-sm text-gray-300">Slug: {profile.slug}</p>
          </div>
          <button
            type="button"
            className="text-gray-300 hover:text-white transition-colors"
            onClick={onClose}
          >
            <XCircle className="w-5 h-5" />
          </button>
        </div>
        <div className="px-6 pb-6 pt-2 space-y-6 overflow-y-auto max-h-[70vh] custom-scrollbar">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <InfoRow label="ID профиля" value={`#${profile.id}`} />
            <InfoRow label="Создан" value={formatDateTime(profile.created_at)} />
            <InfoRow label="Обновлён" value={formatDateTime(profile.updated_at)} />
            <InfoRow label="Категория" value={profile.category || 'не указана'} />
            <InfoRow label="Тип" value={profile.is_official ? 'Официальный' : 'Пользовательский'} />
            <InfoRow label="Статус" value={profile.active ? 'Активен' : 'Отключен'} />
            <InfoRow label="Источник" value={profile.source || 'не указан'} />
            <InfoRow label="Вендор" value={profile.vendor || 'не указан'} />
            <InfoRow label="Setting ID" value={profile.setting_id || '—'} />
            <InfoRow label="External ID" value={profile.external_id || '—'} />
            <InfoRow label="Класс качества" value={profile.quality_tier || '—'} />
            <InfoRow label="Сопло (по умолчанию)" value={defaultNozzle} />
            <InfoRow label="Высота слоя" value={layerHeight} />
          </div>
          {profile.description && (
            <div>
              <h4 className="text-sm font-semibold text-white mb-2">Описание</h4>
              <p className="text-sm text-gray-200 whitespace-pre-wrap">{profile.description}</p>
            </div>
          )}
          {profile.notes && (
            <div>
              <h4 className="text-sm font-semibold text-white mb-2">Заметки</h4>
              <p className="text-sm text-gray-200 whitespace-pre-wrap">{profile.notes}</p>
            </div>
          )}
          {printersList.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-white mb-2">Совместимые принтеры</h4>
              <div className="flex flex-wrap gap-2">
                {printersList.map((item) => (
                  <span
                    key={`${item.printer_slug}-${item.relation_type}-${item.condition ?? 'explicit'}`}
                    className="px-2 py-1 bg-white/10 border border-white/15 rounded-lg text-xs text-gray-100"
                  >
                    {item.printer_slug}
                    {item.relation_type === 'condition' && item.condition ? ` (условие: ${item.condition})` : null}
                  </span>
                ))}
              </div>
            </div>
          )}
          {filamentsList.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-white mb-2">Совместимые филаменты</h4>
              <div className="flex flex-wrap gap-2">
                {filamentsList.map((item) => (
                  <span
                    key={`${item.filament_slug}-${item.relation_type}`}
                    className="px-2 py-1 bg-white/10 border border-white/15 rounded-lg text-xs text-gray-100"
                  >
                    {item.filament_slug}
                  </span>
                ))}
              </div>
            </div>
          )}
          <div>
            <h4 className="text-sm font-semibold text-white mb-2">Настройки OrcaSlicer</h4>
            <pre className="bg-black/40 border border-white/10 rounded-xl p-4 text-xs text-gray-200 overflow-auto max-h-72 whitespace-pre">
              {JSON.stringify(profile.orcaslicer_settings ?? {}, null, 2)}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
};

