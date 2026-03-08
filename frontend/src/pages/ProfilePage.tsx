/** Страница профиля пользователя */

import { useState, useMemo, useEffect, useRef, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
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
  XCircle,
  Plus,
  Download,
  Trash2,
  Thermometer,
  Gauge,
  MoveHorizontal,
  Edit,
  Wind,
  Fan,
  Ruler,
  Factory,
  AlertTriangle,
  Loader2,
  Upload,
  Eye,
  DollarSign,
  Clock,
  Filter,
  RotateCcw,
  Cog,
  Layers,
  ChevronDown,
  ChevronUp,
  CheckCircle,
  Copy,
  HelpCircle,
  X,
  BookOpen,
  Zap,
  Shield,
  RefreshCw,
  QrCode,
  Camera,
  Lock,
} from 'lucide-react';
import { Printer3DIcon } from '../components/icons/Printer3DIcon';
import { useAuth } from '../contexts/AuthContext';
import { useHeaderVisible } from '../hooks/useHeaderVisible';
import { presetsAPI, filamentsAPI, brandsAPI, savedPresetsAPI, filamentReviewsAPI, calculatorAPI, printerProfilesAPI, printProfilesAPI, authAPI, spoolsAPI, qrAPI, devicesAPI, presetSlotsAPI } from '../api/client';
import type { UserSpool, SpoolState, UserPrinterDevice } from '../api/client';
import { SpoolIcon } from '../components/icons/SpoolIcon';
import api from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { CreatePresetModal } from '../components/CreatePresetModal';
import { ViewPresetModal } from '../components/ViewPresetModal';
import { CreatePrinterRequestModal } from '../components/CreatePrinterRequestModal';
import { SettingsTab } from '../components/SettingsTab';
import { ExportFromOrcaSlicerButton } from '../components/ExportFromOrcaSlicerButton';
import { ExportPrinterProfilesButton } from '../components/ExportPrinterProfilesButton';
import { CreatePrinterProfileModal } from '../components/CreatePrinterProfileModal';
import { CreatePrintProfileModal } from '../components/CreatePrintProfileModal';
import { PresetSyncToggle } from '../components/PresetSyncToggle';
import { BadgeList } from '../components/Badge';
import { PresetSlotsPanel } from '../components/presetSlots/PresetSlotsPanel';
import { BrandProfilePage } from './BrandProfilePage';
import { CalculatorPage } from './CalculatorPage';
import type { Preset, PricingMethod, CalculatorEstimateRequest, PrinterProfile, PrintProfile, Filament } from '../types/api';

export const ProfilePage: React.FC = () => {
  const { user, refreshUser } = useAuth();
  const queryClient = useQueryClient();
  const { t } = useTranslation();
  const isHeaderVisible = useHeaderVisible();
  const [showBrandCabinet, setShowBrandCabinet] = useState(false); // Показывать ли кабинет производителя
  const [userTab, setUserTab] = useState<'dashboard' | 'presets' | 'spools' | 'calculator' | 'calculator-pro' | 'settings' | 'printer-profiles'>(
    'dashboard'
  );
  const [isAddSpoolOpen, setIsAddSpoolOpen] = useState(false);
  const [showHelpModal, setShowHelpModal] = useState(false);
  const [isCreatePresetModalOpen, setIsCreatePresetModalOpen] = useState(false);
  const [isViewPresetModalOpen, setIsViewPresetModalOpen] = useState(false);
  const [isCreatePrinterRequestModalOpen, setIsCreatePrinterRequestModalOpen] = useState(false);
  const [editingPreset, setEditingPreset] = useState<Preset | null>(null);
  const [viewingPreset, setViewingPreset] = useState<Preset | null>(null);
  const [selectedPrinterProfile, setSelectedPrinterProfile] = useState<PrinterProfile | null>(null);
  const [selectedPrintProfile, setSelectedPrintProfile] = useState<PrintProfile | null>(null);
  const [expandedPrinterId, setExpandedPrinterId] = useState<number | string | null>(null); // ID или slug принтера, для которого показываем профили
  const [expandedPrinterProfileId, setExpandedPrinterProfileId] = useState<number | null>(null); // ID профиля принтера, для которого показываем профили печати
  const [isCreatePrinterProfileModalOpen, setIsCreatePrinterProfileModalOpen] = useState(false);
  const [isCreatePrintProfileModalOpen, setIsCreatePrintProfileModalOpen] = useState(false);
  const [editingPrinterProfile, setEditingPrinterProfile] = useState<PrinterProfile | null>(null);
  const [editingPrintProfile, setEditingPrintProfile] = useState<PrintProfile | null>(null);
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('grid');
  const [presetFilter, setPresetFilter] = useState<'all' | 'own' | 'saved' | 'drafts'>('all');

  // Загружаем все пресеты пользователя (активные + черновики)
  const { data: userPresetsData } = useQuery({
    queryKey: ['user-presets', user?.id],
    queryFn: () => presetsAPI.list({ active_only: false, page: 1, size: 100, user_id: user?.id }),
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
      // Batch fetch all saved presets in one API call
      const response = await presetsAPI.list({
        ids: savedPresetIds.join(','),
        active_only: false,
        size: 100,
      });
      return response.items || [];
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

  const filteredPresets = useMemo(() => {
    switch (presetFilter) {
      case 'own':
        return allMyPresets.filter(p => p.source === 'own' && p.active);
      case 'saved':
        return allMyPresets.filter(p => p.source === 'saved');
      case 'drafts':
        return allMyPresets.filter(p => p.source === 'own' && (!p.active || p.moderation_status === 'pending'));
      default:
        return allMyPresets;
    }
  }, [allMyPresets, presetFilter]);

  const userPresets = filteredPresets;

  const myPrinterProfiles = useMemo(() => printerProfilesData?.items ?? [], [printerProfilesData]);
  const myPrintProfiles = useMemo(() => printProfilesData?.items ?? [], [printProfilesData]);

  // Lookup map для PrintProfile по slug -> name (для отображения вместо slug)
  const printProfileNameBySlug = useMemo(() => {
    const map = new Map<string, string>();
    myPrintProfiles.forEach((profile) => {
      if (profile.slug && profile.name) {
        map.set(profile.slug, profile.name);
      }
    });
    return map;
  }, [myPrintProfiles]);

  // Lookup map для PrinterProfile по slug -> name (для отображения вместо slug)
  const printerProfileNameBySlug = useMemo(() => {
    const map = new Map<string, string>();
    myPrinterProfiles.forEach((profile) => {
      if (profile.slug && profile.name) {
        map.set(profile.slug, profile.name);
      }
    });
    return map;
  }, [myPrinterProfiles]);

  // Группируем профили принтера по принтерам (по printer_id)
  const printersWithProfiles = useMemo(() => {
    const printerMap = new Map<number, {
      id: number;
      slug: string | null;
      name: string;
      manufacturer: string | null;
      model: string | null;
      profiles: PrinterProfile[];
    }>();

    myPrinterProfiles.forEach((profile) => {
      // Группируем только по printer_id (реальные принтеры из базы)
      if (!profile.printer_id) {
        return; // Пропускаем профили без привязанного принтера
      }
      
      if (!printerMap.has(profile.printer_id)) {
        // Формируем название принтера:
        // 1. Приоритет: printer_name (имя из OrcaSlicer профиля, например "B2Bee", "Voron 2.4 350")
        // 2. Если printer_name пустой или выглядит как placeholder, используем manufacturer + model
        // 3. Fallback: printer_slug или "Принтер {id}"
        let displayName = '';
        
        // Сначала проверяем printer_name - это наиболее точное имя для пользовательских принтеров
        if (profile.printer_name && !profile.printer_name.startsWith('Printer ') && !profile.printer_name.startsWith('Принтер ')) {
          displayName = profile.printer_name;
        } else if (profile.printer_manufacturer && profile.printer_model) {
          // Если есть manufacturer и model, используем их (для официальных принтеров)
          displayName = `${profile.printer_manufacturer} ${profile.printer_model}`;
        } else {
          // Fallback
          displayName = profile.printer_name || profile.printer_slug || `Printer ${profile.printer_id}`;
        }
        
        printerMap.set(profile.printer_id, {
          id: profile.printer_id,
          slug: profile.printer_slug,
          name: displayName,
          manufacturer: profile.printer_manufacturer,
          model: profile.printer_model,
          profiles: [],
        });
      }
      
      printerMap.get(profile.printer_id)!.profiles.push(profile);
    });

    return Array.from(printerMap.values()).sort((a, b) => {
      // Сортируем сначала по производителю, затем по модели
      const manufacturerA = a.manufacturer || '';
      const manufacturerB = b.manufacturer || '';
      if (manufacturerA !== manufacturerB) {
        return manufacturerA.localeCompare(manufacturerB);
      }
      const modelA = a.model || '';
      const modelB = b.model || '';
      return modelA.localeCompare(modelB);
    });
  }, [myPrinterProfiles]);

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
      console.error('Failed to delete saved preset:', error);
      alert(translateApiError(t, error.response?.data?.detail, t('profilePage.unsaveError')));
    },
  });

  const handleDeletePreset = (preset: Preset) => {
    if (preset.source === 'saved') {
      if (confirm(t('profilePage.confirmUnsave'))) {
        unsavePresetMutation.mutate(preset.id);
      }
    } else {
      if (confirm(t('profilePage.confirmDelete'))) {
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

  const { data: spoolsData = [], refetch: refetchSpools } = useQuery({
    queryKey: ['user-spools', user?.id],
    queryFn: () => spoolsAPI.list(),
    enabled: !!user?.id,
  });

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
      console.error('Error downloading printer profile:', error);
      alert(`${t('profilePage.downloadPrinterProfileError')}: ${translateApiError(t, error?.response?.data?.detail, t('profilePage.unknownError'))}`);
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
      console.error('Error downloading print profile:', error);
      alert(`${t('profilePage.downloadPrintProfileError')}: ${translateApiError(t, error?.response?.data?.detail, t('profilePage.unknownError'))}`);
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
              <span>{t('profilePage.userProfile')}</span>
            </button>
            <button
              onClick={() => setShowBrandCabinet(true)}
              className="flex items-center space-x-2 px-6 py-2 rounded-lg transition-all bg-green-600 text-white shadow-lg shadow-green-500/25"
            >
              <Factory className="w-4 h-4" />
              <span>{t('profilePage.companyProfile')}</span>
            </button>
          </div>
        </div>
        
        <BrandProfilePage onBack={() => setShowBrandCabinet(false)} />
      </div>
    );
  }

  return (
    <div className="space-y-6 md:space-y-10">
      {/* Переключатель профилей */}
      <div className="flex justify-center mb-4 md:mb-6">
        <div className="flex bg-white/10 rounded-lg p-1 border border-white/20">
          <button
            onClick={() => setShowBrandCabinet(false)}
            className={`flex items-center gap-1.5 md:gap-2 px-3 md:px-6 py-1.5 md:py-2 rounded-lg transition-all text-xs md:text-base ${
              !showBrandCabinet 
                ? 'bg-purple-600 text-white shadow-lg shadow-purple-500/25' 
                : 'text-gray-300 hover:text-white'
            }`}
          >
            <User className="w-3.5 h-3.5 md:w-4 md:h-4" />
            <span className="hidden sm:inline">{t('profilePage.user')}</span>
            <span className="sm:hidden">{t('profilePage.profile')}</span>
          </button>
          <button
            onClick={() => setShowBrandCabinet(true)}
            className={`flex items-center gap-1.5 md:gap-2 px-3 md:px-6 py-1.5 md:py-2 rounded-lg transition-all text-xs md:text-base ${
              showBrandCabinet 
                ? 'bg-green-600 text-white shadow-lg shadow-green-500/25' 
                : 'text-gray-300 hover:text-white'
            }`}
          >
            <Factory className="w-3.5 h-3.5 md:w-4 md:h-4" />
            <span className="hidden sm:inline">{t('profilePage.company')}</span>
            <span className="sm:hidden">{t('profilePage.brand')}</span>
          </button>
        </div>
      </div>
      
      {/* Header */}
      <div className="text-center mb-4 md:mb-8">
        <div className="flex items-center justify-center gap-2 md:gap-3 mb-3 md:mb-4">
          <div className="w-12 h-12 md:w-16 md:h-16 bg-gradient-to-r from-purple-500 to-pink-500 rounded-lg md:rounded-xl flex items-center justify-center shadow-lg shadow-purple-500/25">
            <User className="w-6 h-6 md:w-8 md:h-8 text-white" />
          </div>
          <div className="text-left">
            <h2 className="text-xl md:text-3xl font-bold text-white mb-0.5 md:mb-1">{t('profilePage.myProfile')}</h2>
            <div className="flex flex-wrap items-center gap-1 md:gap-2">
              <p className="text-gray-300 text-xs md:text-base">
                {user.full_name || user.username}<span className="hidden md:inline"> • {t('profilePage.printer3d')}</span>
              </p>
              {user.badges && user.badges.length > 0 && (
                <BadgeList badges={user.badges as any} size="sm" />
              )}
            </div>
          </div>
        </div>

        {/* Tabs - горизонтальный скролл на мобильных */}
        <div className="overflow-x-auto -mx-4 px-4 md:mx-0 md:px-0 scrollbar-hide">
          <div className="flex justify-start md:justify-center gap-1.5 md:gap-2 mt-3 md:mt-4 min-w-max">
            {[
              { id: 'dashboard', label: t('profilePage.tabs.dashboard'), shortLabel: t('profilePage.tabs.dashboardShort'), icon: Play },
              { id: 'presets', label: t('profilePage.tabs.presets'), shortLabel: t('profilePage.tabs.presetsShort'), icon: Settings },
              { id: 'printer-profiles', label: t('profilePage.tabs.printers'), shortLabel: t('profilePage.tabs.printersShort'), icon: Printer3DIcon },
              { id: 'spools', label: t('profilePage.tabs.spools'), shortLabel: t('profilePage.tabs.spoolsShort'), icon: Package },
              { id: 'calculator', label: t('profilePage.tabs.calculator'), shortLabel: t('profilePage.tabs.calculatorShort'), icon: Calculator },
              { 
                id: 'calculator-pro', 
                label: t('profilePage.tabs.calculatorPro'), 
                shortLabel: t('profilePage.tabs.calculatorProShort'), 
                icon: Calculator,
                premium: true,
              },
              { id: 'settings', label: t('profilePage.tabs.settings'), shortLabel: t('profilePage.tabs.settingsShort'), icon: Cog },
            ].map((tab) => {
              const isPremiumTab = tab.premium === true;
              const isLocked = isPremiumTab && !user?.is_premium;
              
              return (
                <button
                  key={tab.id}
                  onClick={() => !isLocked && setUserTab(tab.id as any)}
                  disabled={isLocked}
                  className={`flex items-center gap-1.5 md:gap-2 px-2.5 md:px-4 py-1.5 md:py-2 rounded-lg transition-all text-xs md:text-sm whitespace-nowrap ${
                    userTab === tab.id
                      ? 'bg-purple-600 text-white shadow-lg shadow-purple-500/25'
                      : isLocked
                      ? 'text-gray-500 cursor-not-allowed'
                      : 'text-gray-300 hover:text-white hover:bg-white/10 active:bg-white/15'
                  } ${isLocked ? 'opacity-60' : ''}`}
                  title={isLocked ? t('profilePage.premiumRequired') : undefined}
                >
                  <tab.icon className="w-3.5 h-3.5 md:w-4 md:h-4" />
                  <span className="hidden md:inline">{tab.label}</span>
                  <span className="md:hidden">{tab.shortLabel}</span>
                  {isLocked && <Lock className="w-3 h-3 md:w-3.5 md:h-3.5 ml-1" />}
                </button>
              );
            })}
            <button
              onClick={() => setShowHelpModal(true)}
              className="flex items-center gap-1.5 px-2 md:px-3 py-1.5 md:py-2 rounded-lg transition-all text-xs md:text-sm text-gray-400 hover:text-white hover:bg-white/10 active:bg-white/15"
              title={t('profilePage.help.title')}
            >
              <HelpCircle className="w-3.5 h-3.5 md:w-4 md:h-4" />
              <span className="hidden lg:inline">{t('profilePage.help.button')}</span>
            </button>
          </div>
        </div>
      </div>

      {/* Dashboard Tab */}
      {userTab === 'dashboard' && (
        <div className="space-y-4 md:space-y-6">
          {/* Stats Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-6">
            <StatCard
              icon={CheckCircle}
              label={t('profilePage.stats.successfulPrints')}
              value={reviewsStats.successCount.toString()}
              color="from-purple-500/20 to-pink-500/20"
              borderColor="border-purple-500/30"
              iconColor="text-green-400"
            />
            {/* Объединённая плашка для пресетов */}
            <div className="bg-gradient-to-r from-blue-500/20 to-cyan-500/20 p-3 md:p-6 rounded-xl md:rounded-2xl border border-blue-500/30 shadow-xl">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-gray-300 text-[10px] md:text-sm mb-0.5 md:mb-1">{t('profilePage.stats.presets')}</p>
                  <p className="text-xl md:text-3xl font-bold text-white">
                    {presetsStats?.total_presets?.toString() || userPresets.length.toString()}/{presetsStats?.synced_presets?.toString() || '0'}
                  </p>
                  <p className="text-[10px] md:text-xs text-gray-400 mt-0.5 md:mt-1">
                    <span className="md:hidden">{t('profilePage.stats.totalSyncShort')}</span>
                    <span className="hidden md:inline">{t('profilePage.stats.totalSync')}</span>
                  </p>
                </div>
                <Settings className="w-5 h-5 md:w-8 md:h-8 text-blue-400" />
              </div>
            </div>
            <StatCard
              icon={Star}
              label={t('profilePage.stats.reviewsLeft')}
              value={reviewsStats.totalReviews.toString()}
              color="from-purple-500/20 to-pink-500/20"
              borderColor="border-purple-500/30"
              iconColor="text-purple-400"
            />
            <StatCard
              icon={Star}
              label={t('profilePage.stats.avgRating')}
              value={reviewsStats.avgRating || '—'}
              color="from-yellow-500/20 to-orange-500/20"
              borderColor="border-yellow-500/30"
              iconColor="text-yellow-400"
            />
          </div>

          {/* Recent Activity */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <RecentPresets presets={userPresets.slice(0, 3)} />
            <RecentSpools spools={spoolsData.slice(0, 3)} onViewAll={() => setUserTab('spools')} />
          </div>
        </div>
      )}

      {/* Presets Tab */}
      {userTab === 'presets' && (
        <div className="space-y-4 md:space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <h3 className="text-lg md:text-2xl font-bold text-white">{t('profilePage.filamentProfiles')}</h3>
            <div className="flex items-center gap-2 md:gap-3">
              {typeof window !== 'undefined' && (window as any).filamenthub?.exportFilamentPresets && (
                <ExportFromOrcaSlicerButton />
              )}
              <button
                onClick={handleCreatePreset}
                className="flex-1 sm:flex-none bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 active:from-purple-800 active:to-pink-800 text-white px-3 md:px-4 py-2 rounded-lg md:rounded-xl transition-all shadow-lg shadow-purple-500/25 text-sm md:text-base"
              >
                <Plus className="w-4 h-4 inline mr-1.5 md:mr-2" />
                <span className="hidden sm:inline">{t('profilePage.newPreset')}</span>
                <span className="sm:hidden">{t('profilePage.add')}</span>
              </button>
            </div>
          </div>

          {/* Filter chips */}
          {allMyPresets.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {([
                { key: 'all' as const, label: t('profilePage.presetFilterAll'), count: allMyPresets.length },
                { key: 'own' as const, label: t('profilePage.presetFilterOwn'), count: allMyPresets.filter(p => p.source === 'own' && p.active).length },
                { key: 'saved' as const, label: t('profilePage.presetFilterSaved'), count: allMyPresets.filter(p => p.source === 'saved').length },
                { key: 'drafts' as const, label: t('profilePage.presetFilterDrafts'), count: allMyPresets.filter(p => p.source === 'own' && (!p.active || p.moderation_status === 'pending')).length },
              ]).filter(f => f.key === 'all' || f.count > 0).map(f => (
                <button
                  key={f.key}
                  onClick={() => setPresetFilter(f.key)}
                  className={`px-3 py-1.5 rounded-lg text-sm transition-all ${
                    presetFilter === f.key
                      ? 'bg-purple-600 text-white shadow-lg shadow-purple-500/25'
                      : 'bg-white/5 text-gray-400 hover:bg-white/10 hover:text-white border border-white/10'
                  }`}
                >
                  {f.label}
                  <span className={`ml-1.5 text-xs ${presetFilter === f.key ? 'text-purple-200' : 'text-gray-500'}`}>
                    {f.count}
                  </span>
                </button>
              ))}
            </div>
          )}

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 md:gap-6">
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
            <div className="text-center py-8 md:py-12">
              <Settings className="w-12 h-12 md:w-16 md:h-16 text-gray-400 mx-auto mb-3 md:mb-4" />
              <p className="text-gray-400 text-base md:text-xl">
                <span className="md:hidden">{t('profilePage.noPresetsShort')}</span>
                <span className="hidden md:inline">{t('profilePage.noPresetsLong')}</span>
              </p>
            </div>
          )}
        </div>
      )}

      {/* Spools Tab */}
      {userTab === 'spools' && (
        <SpoolsTab
          spools={spoolsData}
          printerBindings={printersWithProfiles.map((printer) => ({ id: printer.id, name: printer.name }))}
          onRefetch={refetchSpools}
          isAddOpen={isAddSpoolOpen}
          setIsAddOpen={setIsAddSpoolOpen}
        />
      )}

      {/* Calculator Tab */}
      {userTab === 'calculator' && (
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-4 md:mb-8">
            <h2 className="text-xl md:text-4xl font-bold text-white mb-2 md:mb-4">{t('profilePage.calculatorTitle')}</h2>
            <p className="text-sm md:text-xl text-gray-300">
              <span className="md:hidden">{t('profilePage.calculatorSubtitleShort')}</span>
              <span className="hidden md:inline">{t('profilePage.calculatorSubtitleLong')}</span>
            </p>
          </div>

          <CalculatorComponent />
        </div>
      )}

      {/* Calculator Pro Tab (Premium) */}
      {userTab === 'calculator-pro' && (
        <div className="max-w-7xl mx-auto">
          {user?.is_premium ? (
            <CalculatorPage />
          ) : (
            <div className="flex flex-col items-center justify-center py-20">
              <div className="p-6 bg-purple-600/20 rounded-full mb-6">
                <Lock className="w-16 h-16 text-purple-400" />
              </div>
              <h2 className="text-3xl font-bold text-white mb-4">
                {t('profilePage.premiumRequired')}
              </h2>
              <p className="text-gray-400 mb-8 text-center max-w-md">
                {t('profilePage.premiumCalculatorDesc')}
              </p>
              <button className="px-8 py-4 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 text-white font-bold rounded-xl shadow-lg shadow-purple-500/25 transition-all">
                {t('profilePage.getPremium')}
              </button>
            </div>
          )}
        </div>
      )}

      {/* Printer Profiles Tab */}
      {userTab === 'printer-profiles' && (
        <div className="space-y-6">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-2xl font-bold text-white">{t('profilePage.myPrinters')}</h2>
              <p className="text-sm text-gray-400">
                {t('profilePage.myPrintersDescription')}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <StatusBadge label={t('profilePage.printersCount', { count: printersWithProfiles.length })} variant="accent" />
              {/* Кнопка экспорта из OrcaSlicer */}
              <ExportPrinterProfilesButton />
              <button
                type="button"
                className="px-4 py-2 rounded-lg border border-white/20 text-sm text-white hover:bg-white/10 transition-all"
                onClick={() => {
                  setEditingPrinterProfile(null);
                  setIsCreatePrinterProfileModalOpen(true);
                }}
                title={t('profilePage.createPrinterProfile')}
              >
                <Plus className="w-4 h-4 inline mr-2" />
                {t('profilePage.addProfile')}
              </button>
            </div>
          </div>

          {isLoadingPrinterProfiles ? (
            <ProfileSectionLoader />
          ) : printersWithProfiles.length > 0 ? (
            <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              {printersWithProfiles.map((printer) => {
                const isPrinterExpanded = expandedPrinterId === printer.id;
                
                return (
                  <div key={printer.id} className="bg-white/10 backdrop-blur-sm border border-white/15 rounded-2xl p-6 shadow-xl">
                    {/* Заголовок принтера */}
                    <div className="flex items-start justify-between gap-3 mb-4">
                      <div className="flex-1">
                        <div className="flex items-center gap-3 mb-2">
                          <Printer3DIcon className="w-6 h-6 text-purple-400 flex-shrink-0" />
                          <div>
                            {printer.manufacturer && (
                              <p className="text-xs text-gray-400">{printer.manufacturer}</p>
                            )}
                            <h3 className="text-lg font-semibold text-white">{printer.model || printer.name}</h3>
                          </div>
                        </div>
                        {printer.slug && (
                          <p className="text-xs text-gray-500">Slug: {printer.slug}</p>
                        )}
                      </div>
                      <StatusBadge label={t('profilePage.profilesCount', { count: printer.profiles.length })} variant="accent" />
                    </div>

                    {/* Профили принтера */}
                    <div className="space-y-2 mt-4 pt-4 border-t border-white/10">
                      {printer.profiles.map((profile) => {
                          // Фильтруем профили печати для этого профиля принтера
                          const printProfilesForPrinterProfile = profile.printer_slug
                            ? myPrintProfiles.filter((pp) => {
                                const hasPrinterLink = pp.printer_links?.some(
                                  (link) => link.printer_slug === profile.printer_slug
                                );
                                const hasCompatiblePrinter = pp.compatible_printers?.includes(profile.printer_slug || '');
                                return hasPrinterLink || hasCompatiblePrinter;
                              })
                            : [];

                          const isProfileExpanded = expandedPrinterProfileId === profile.id;

                          return (
                            <div key={profile.id} className="bg-white/5 rounded-xl border border-white/10 p-3">
                              {/* Заголовок профиля принтера */}
                              <div className="flex items-start justify-between gap-3 mb-2">
                                <div className="flex-1">
                                  <div className="flex items-center gap-2 mb-1">
                                    <Settings className="w-4 h-4 text-blue-400 flex-shrink-0" />
                                    <h4 className="text-sm font-semibold text-white">{profile.name}</h4>
                                  </div>
                                  {profile.nozzle_diameters && profile.nozzle_diameters.length > 0 && (
                                    <p className="text-xs text-gray-400 ml-6">
                                      {t('profilePage.nozzles')}: {profile.nozzle_diameters.join(', ')} {t('profilePage.mm')}
                                    </p>
                                  )}
                                </div>
                                {printProfilesForPrinterProfile.length > 0 && (
                                  <StatusBadge label={t('profilePage.printProfilesCount', { count: printProfilesForPrinterProfile.length })} variant="accent" />
                                )}
                              </div>
                              
                              {/* Кнопка раскрытия деталей */}
                              <button
                                type="button"
                                onClick={() => setExpandedPrinterProfileId(isProfileExpanded ? null : profile.id)}
                                className="w-full mt-2 px-3 py-1.5 rounded-lg border border-white/20 text-xs text-gray-400 hover:text-white hover:bg-white/10 transition-all flex items-center justify-center gap-2"
                              >
                                {isProfileExpanded ? (
                                  <>
                                    <ChevronUp className="w-3 h-3" />
                                    {t('profilePage.hideDetails')}
                                  </>
                                ) : (
                                  <>
                                    <ChevronDown className="w-3 h-3" />
                                    {t('profilePage.showDetails')}
                                  </>
                                )}
                              </button>

                              {/* Детали профиля принтера и профили печати */}
                              {isProfileExpanded && (
                                <div className="mt-3 pt-3 space-y-3 border-t border-white/10 px-2">
                                  {/* Краткая информация о профиле принтера */}
                                  <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 text-xs">
                                    <div>
                                      <span className="text-gray-400">{t('profilePage.updated')}:</span>{' '}
                                      <span className="text-white">{formatDateTime(profile.updated_at)}</span>
                                    </div>
                                    {profile.default_print_profile_slug && (
                                      <div>
                                        <span className="text-gray-400">Default Profile:</span>{' '}
                                        <span className="text-white" title={profile.default_print_profile_slug}>
                                          {printProfileNameBySlug.get(profile.default_print_profile_slug) || profile.default_print_profile_slug}
                                        </span>
                                      </div>
                                    )}
                                    {typeof profile.printable_height_mm === 'number' && (
                                      <div>
                                        <span className="text-gray-400">{t('profilePage.height')}:</span>{' '}
                                        <span className="text-white">{profile.printable_height_mm.toFixed(0)} {t('profilePage.mm')}</span>
                                      </div>
                                    )}
                                  </div>

                                  {/* Кнопки действий профиля принтера */}
                                  <div className="flex flex-wrap gap-2">
                                    <button
                                      type="button"
                                      onClick={() => setSelectedPrinterProfile(profile)}
                                      className="px-3 py-1.5 rounded-lg border border-white/20 text-xs text-white/90 hover:bg-white/10 transition-all flex items-center gap-1.5"
                                    >
                                      <Eye className="w-3 h-3" />
                                      {t('profilePage.view')}
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => handleDownloadPrinterProfile(profile)}
                                      className="px-3 py-1.5 rounded-lg border border-white/20 text-xs text-white/90 hover:bg-white/10 transition-all flex items-center gap-1.5"
                                    >
                                      <Download className="w-3 h-3" />
                                      {t('profilePage.downloadJson')}
                                    </button>
                                  </div>

                                  {/* Профили печати для этого профиля принтера */}
                                  {printProfilesForPrinterProfile.length > 0 && (
                                    <div className="pt-2 border-t border-white/10">
                                      <p className="text-xs text-gray-400 mb-2">{t('profilePage.printProfilesLabel')}:</p>
                                      <div className="space-y-2">
                                        {printProfilesForPrinterProfile.map((printProfile) => (
                                          <div
                                            key={printProfile.id}
                                            className="bg-white/5 rounded-lg p-3 border border-white/10"
                                          >
                                            <div className="flex items-start justify-between gap-3">
                                              <div className="flex-1">
                                                <h5 className="text-xs font-semibold text-white">{printProfile.name}</h5>
                                                {printProfile.quality_tier && (
                                                  <p className="text-xs text-gray-400 mt-0.5">
                                                    {t('profilePage.quality')}: {printProfile.quality_tier}
                                                  </p>
                                                )}
                                                {printProfile.layer_height_mm && (
                                                  <p className="text-xs text-gray-400">
                                                    {t('profilePage.layerHeight')}: {printProfile.layer_height_mm.toFixed(2)} {t('profilePage.mm')}
                                                  </p>
                                                )}
                                              </div>
                                              <div className="flex items-center gap-2">
                                                {printProfile.is_official && (
                                                  <StatusBadge label={t('profilePage.badge.system')} variant="accent" />
                                                )}
                                                <StatusBadge
                                                  label={printProfile.active ? t('profilePage.badge.active') : t('profilePage.badge.disabled')}
                                                  variant={printProfile.active ? 'success' : 'muted'}
                                                />
                                              </div>
                                            </div>
                                            {printProfile.description && (
                                              <p className="mt-1.5 text-xs text-gray-300 line-clamp-2">
                                                {printProfile.description}
                                              </p>
                                            )}
                                            <div className="mt-2 flex flex-wrap gap-2">
                                              <button
                                                type="button"
                                                onClick={() => setSelectedPrintProfile(printProfile)}
                                                className="px-2 py-1 rounded border border-white/20 text-xs text-white/90 hover:bg-white/10 transition-all flex items-center gap-1"
                                              >
                                                <Eye className="w-3 h-3" />
                                                {t('profilePage.view')}
                                              </button>
                                              <button
                                                type="button"
                                                onClick={() => handleDownloadPrintProfile(printProfile)}
                                                className="px-2 py-1 rounded border border-white/20 text-xs text-white/90 hover:bg-white/10 transition-all flex items-center gap-1"
                                              >
                                                <Download className="w-3 h-3" />
                                                {t('profilePage.download')}
                                              </button>
                                            </div>
                                          </div>
                                        ))}
                                      </div>
                                    </div>
                                  )}

                                  {/* Кнопка добавления профиля печати */}
                                  <button
                                    type="button"
                                    onClick={() => {
                                      setEditingPrintProfile(null);
                                      setIsCreatePrintProfileModalOpen(true);
                                    }}
                                    className="w-full px-3 py-2 rounded-lg border border-dashed border-white/20 text-xs text-gray-400 hover:text-white hover:border-white/40 transition-all flex items-center justify-center gap-2"
                                  >
                                    <Plus className="w-3 h-3" />
                                    {t('profilePage.addPrintProfile')}
                                  </button>
                                </div>
                              )}
                            </div>
                          );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <EmptyState
              icon={Printer3DIcon}
              title={t('profilePage.noPrinters')}
              description={t('profilePage.noPrintersDesc')}
              actionLabel={t('profilePage.createPrinterProfile')}
              onAction={() => {
                setEditingPrinterProfile(null);
                setIsCreatePrinterProfileModalOpen(true);
              }}
            />
          )}
        </div>
      )}

      {/* Print Profiles Tab */}
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

      {/* Help Modal */}
      {showHelpModal && (
        <div className={`fixed inset-0 z-[100] ${isHeaderVisible ? 'pt-[88px]' : ''}`}>
          <div className="fixed inset-0 bg-black/50 backdrop-blur-sm" onClick={() => setShowHelpModal(false)} />
          <div className="fixed inset-0 flex items-center justify-center pointer-events-none" style={{ top: isHeaderVisible ? '88px' : '0' }}>
          <div className={`bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 rounded-2xl w-full max-w-4xl overflow-hidden flex flex-col border border-white/20 shadow-2xl pointer-events-auto mx-4 ${isHeaderVisible ? 'max-h-[calc(100vh-100px)]' : 'max-h-[90vh]'}`} onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between p-5 border-b border-white/10">
              <div className="flex items-center gap-3">
                <div className="p-2 bg-purple-600/20 rounded-xl">
                  <BookOpen className="w-5 h-5 text-purple-400" />
                </div>
                <h2 className="text-lg font-bold text-white">{t('profilePage.help.title')}</h2>
              </div>
              <button onClick={() => setShowHelpModal(false)} className="p-2 hover:bg-white/10 rounded-lg transition-colors">
                <X className="w-5 h-5 text-gray-400" />
              </button>
            </div>
            <div className="overflow-y-auto p-5 space-y-4" style={{ maxHeight: 'calc(85vh - 70px)' }}>

              <HelpSection icon={Package} title={t('profilePage.help.presetsTitle')}>
                <p>{t('profilePage.help.presetsDesc')}</p>
                <p className="mt-2 text-gray-400 text-sm">{t('profilePage.help.presetsHow')}</p>
                <ul className="list-disc list-inside space-y-1 text-gray-400 text-sm mt-2">
                  <li>{t('profilePage.help.presetsStep1')}</li>
                  <li>{t('profilePage.help.presetsStep2')}</li>
                  <li>{t('profilePage.help.presetsStep3')}</li>
                  <li>{t('profilePage.help.presetsStep4')}</li>
                </ul>
                <p className="mt-2 text-gray-400 text-sm">{t('profilePage.help.presetsNote')}</p>
              </HelpSection>

              <HelpSection icon={Printer3DIcon} title={t('profilePage.help.printersTitle')}>
                <p>{t('profilePage.help.printersDesc')}</p>
                <ul className="list-disc list-inside space-y-1 text-gray-400 text-sm mt-2">
                  <li>{t('profilePage.help.printersStep1')}</li>
                  <li>{t('profilePage.help.printersStep2')}</li>
                  <li>{t('profilePage.help.printersStep3')}</li>
                </ul>
                <p className="mt-2 text-gray-400 text-sm">{t('profilePage.help.printersNote')}</p>
              </HelpSection>

              <HelpSection icon={Calculator} title={t('profilePage.help.calculatorTitle')}>
                <p>{t('profilePage.help.calculatorDesc')}</p>
                <ul className="list-disc list-inside space-y-1 text-gray-400 text-sm mt-2">
                  <li>{t('profilePage.help.calculatorStep1')}</li>
                  <li>{t('profilePage.help.calculatorStep2')}</li>
                  <li>{t('profilePage.help.calculatorStep3')}</li>
                </ul>
              </HelpSection>

              <HelpSection icon={RefreshCw} title={t('profilePage.help.syncTitle')}>
                <p>{t('profilePage.help.syncDesc')}</p>
                <ul className="list-disc list-inside space-y-1 text-gray-400 text-sm mt-2">
                  <li>{t('profilePage.help.syncStep1')}</li>
                  <li>{t('profilePage.help.syncStep2')}</li>
                  <li>{t('profilePage.help.syncStep3')}</li>
                </ul>
                <p className="mt-2 text-gray-400 text-sm">{t('profilePage.help.syncNote')}</p>
              </HelpSection>

              <HelpSection icon={Shield} title={t('profilePage.help.brandTitle')}>
                <p>{t('profilePage.help.brandDesc')}</p>
                <ul className="list-disc list-inside space-y-1 text-gray-400 text-sm mt-2">
                  <li>{t('profilePage.help.brandStep1')}</li>
                  <li>{t('profilePage.help.brandStep2')}</li>
                  <li>{t('profilePage.help.brandStep3')}</li>
                </ul>
              </HelpSection>

              <HelpSection icon={Settings} title={t('profilePage.help.settingsTitle')}>
                <p>{t('profilePage.help.settingsDesc')}</p>
                <ul className="list-disc list-inside space-y-1 text-gray-400 text-sm mt-2">
                  <li>{t('profilePage.help.settingsStep1')}</li>
                  <li>{t('profilePage.help.settingsStep2')}</li>
                  <li>{t('profilePage.help.settingsStep3')}</li>
                </ul>
              </HelpSection>

              <HelpSection icon={Layers} title={t('profilePage.help.hhTitle')}>
                <p>{t('profilePage.help.hhDesc')}</p>

                <p className="mt-3 text-gray-400 text-sm font-medium">{t('profilePage.help.hhConnectHow')}</p>
                <ul className="list-disc list-inside space-y-1 text-gray-400 text-sm mt-1">
                  <li>{t('profilePage.help.hhConnectStep1')}</li>
                  <li>{t('profilePage.help.hhConnectStep2')}</li>
                  <li>{t('profilePage.help.hhConnectStep3')}</li>
                </ul>

                <p className="mt-3 text-gray-400 text-sm font-medium">{t('profilePage.help.hhSpoolmanTitle')}</p>
                <ul className="space-y-1 text-sm mt-1 ml-2">
                  <li className="text-gray-500">{t('profilePage.help.hhSpoolmanOff')}</li>
                  <li className="text-gray-500">{t('profilePage.help.hhSpoolmanReadonly')}</li>
                  <li className="text-gray-500">{t('profilePage.help.hhSpoolmanPush')}</li>
                  <li className="text-green-400 font-medium">{t('profilePage.help.hhSpoolmanPull')}</li>
                </ul>

                <p className="mt-3 text-gray-400 text-sm font-medium">{t('profilePage.help.hhColorTitle')}</p>
                <ul className="space-y-1 text-sm mt-1 ml-2">
                  <li className="text-gray-500">{t('profilePage.help.hhColorSlicer')}</li>
                  <li className="text-green-400 font-medium">{t('profilePage.help.hhColorGatemap')}</li>
                  <li className="text-gray-500">{t('profilePage.help.hhColorAllgates')}</li>
                  <li className="text-gray-500">{t('profilePage.help.hhColorOff')}</li>
                </ul>

                <p className="mt-3 text-purple-300 text-sm">{t('profilePage.help.hhWorkflow')}</p>
              </HelpSection>

              <HelpSection icon={Zap} title={t('profilePage.help.tipsTitle')}>
                <ul className="list-disc list-inside space-y-1 text-gray-400 text-sm">
                  <li>{t('profilePage.help.tip1')}</li>
                  <li>{t('profilePage.help.tip2')}</li>
                  <li>{t('profilePage.help.tip3')}</li>
                  <li>{t('profilePage.help.tip4')}</li>
                  <li>{t('profilePage.help.tip5')}</li>
                </ul>
              </HelpSection>

            </div>
          </div>
          </div>
        </div>
      )}

      {/* Combined Profiles Section (только на dashboard) */}
      {userTab === 'dashboard' && (
        <section className="mt-12 space-y-5">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div>
              <h2 className="text-2xl font-bold text-white">{t('profilePage.combos.title')}</h2>
              <p className="text-sm text-gray-400">
                {t('profilePage.combos.description')}
              </p>
            </div>
            <StatusBadge label={t('profilePage.combos.inDevelopment')} variant="muted" />
          </div>

          <div className="bg-white/5 border border-dashed border-white/20 rounded-2xl p-6 text-gray-200">
            <p className="text-lg text-white font-semibold mb-2">{t('profilePage.combos.comingSoon')}</p>
            <p className="text-sm text-gray-300">
              {t('profilePage.combos.comingSoonDesc')}
            </p>

            <div className="mt-4 grid gap-4 md:grid-cols-3">
              <InfoSummary label={t('profilePage.combos.printerProfileDrafts')} value={myPrinterProfiles.length} />
              <InfoSummary label={t('profilePage.combos.printProfileDrafts')} value={myPrintProfiles.length} />
              <InfoSummary label={t('profilePage.combos.availablePresets')} value={userPresets.length} />
            </div>

            <p className="mt-4 text-xs text-gray-400 uppercase tracking-wide">
              {t('profilePage.combos.combinationsCount')}: {combinationsDraftCount}
            </p>
          </div>
        </section>
      )}


      {selectedPrinterProfile && (
        <PrinterProfileModal
          profile={selectedPrinterProfile}
          onClose={() => setSelectedPrinterProfile(null)}
          formatDateTime={formatDateTime}
          printProfileNameBySlug={printProfileNameBySlug}
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
  <div className={`bg-gradient-to-r ${color} p-3 md:p-6 rounded-xl md:rounded-2xl border ${borderColor} shadow-xl`}>
    <div className="flex items-center justify-between">
      <div>
        <p className="text-gray-300 text-[10px] md:text-sm mb-0.5">{label}</p>
        <p className="text-xl md:text-3xl font-bold text-white">{value}</p>
      </div>
      <Icon className={`w-5 h-5 md:w-8 md:h-8 ${iconColor}`} />
    </div>
  </div>
);

interface RecentPresetsProps {
  presets: Preset[];
}

const RecentPresets: React.FC<RecentPresetsProps> = ({ presets }) => {
  const { t } = useTranslation();
  return (
  <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
    <h3 className="text-xl font-bold text-white mb-4 flex items-center">
      <Settings className="w-5 h-5 mr-2" />
      {t('profilePage.recentPresets')}
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
              <p className="text-green-400 font-semibold">{preset.usage_count} {t('profilePage.usages')}</p>
              <p className="text-gray-400 text-sm">
                {new Date(preset.created_at).toLocaleDateString('ru-RU')}
              </p>
            </div>
          </div>
        ))
      ) : (
        <p className="text-gray-400 text-center py-4">{t('profilePage.noPresets')}</p>
      )}
    </div>
  </div>
  );
};

// ── Spool helpers ────────────────────────────────────────────────────────────

const SPOOL_STATE_COLORS: Record<string, string> = {
  active: 'bg-green-500/20 text-green-300 border-green-500/30',
  shelf: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  archived: 'bg-gray-500/20 text-gray-300 border-gray-500/30',
  empty: 'bg-red-500/20 text-red-300 border-red-500/30',
};

interface SpoolCardProps {
  spool: UserSpool;
  isBusy?: boolean;
  onEdit?: () => void;
  onUse?: () => void;
  onDelete?: () => void;
  onStateChange?: (state: SpoolState) => void;
}

const SpoolCard: React.FC<SpoolCardProps> = ({ spool, isBusy = false, onEdit, onUse, onDelete, onStateChange }) => {
  const { t } = useTranslation();
  const pct = Math.max(0, Math.min(100, spool.remaining_pct));
  const stateKey = `profilePage.spoolState.${spool.state}` as const;
  const iconColor = spool.filament?.color_hex
    ? `#${spool.filament.color_hex.replace('#', '')}`
    : '#9333ea';
  const pctToneClass = pct <= 10 ? 'text-red-300' : pct <= 30 ? 'text-yellow-300' : 'text-green-300';

  return (
    <div className="bg-white/10 backdrop-blur-sm border border-white/15 rounded-2xl p-4 shadow-xl flex gap-4 items-stretch">
      {/* Spool icon — the visual centrepiece */}
      <div className="flex-shrink-0 self-stretch flex items-center justify-center w-[112px]">
        <SpoolIcon
          pct={pct}
          color={iconColor}
          remainingWeightG={spool.remaining_weight_g}
          showMetrics
          size={112}
          viewBox="8 12 78 72"
        />
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0 flex flex-col gap-1.5">
        {/* Name + state badge */}
        <div className="flex items-start justify-between gap-2">
          <p className="text-white font-semibold text-sm leading-tight truncate">
            {spool.filament ? spool.filament.name : t('profilePage.spoolNoFilament')}
          </p>
          <span className={`text-xs px-2 py-0.5 rounded-full border flex-shrink-0 ${SPOOL_STATE_COLORS[spool.state] ?? ''}`}>
            {t(stateKey)}
          </span>
        </div>

        {/* Brand · material */}
        {spool.filament && (
          <p className="text-gray-400 text-xs truncate">
            {spool.filament.brand_name && `${spool.filament.brand_name} · `}
            {spool.filament.material_type}
          </p>
        )}

        {/* Weight stats */}
        <div className="flex items-center gap-3 text-xs mt-0.5">
          <span className={`font-medium ${pctToneClass}`}>
            {spool.remaining_weight_g.toFixed(0)} г
            <span className="text-gray-400 font-normal ml-1">({pct.toFixed(0)}%)</span>
          </span>
          <span className="text-gray-500">
            {t('profilePage.spoolUsed')}: {spool.used_weight_g.toFixed(0)} г
            {' / '}
            {spool.initial_weight_g.toFixed(0)} г
          </span>
        </div>

        <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
          <div
            className="h-full rounded-full transition-all duration-500"
            style={{ width: `${pct}%`, backgroundColor: iconColor }}
          />
        </div>

        {/* Price per spool */}
        {(spool.price != null || spool.filament?.price_per_kg != null) && (
          <p className="text-gray-400 text-xs">
            <span className="text-gray-500">{t('profilePage.spoolPrice')}: </span>
            <span className="font-medium">
              {spool.price != null
                ? `${spool.price.toFixed(0)} ₽`
                : `${((spool.filament!.price_per_kg! * spool.initial_weight_g) / 1000).toFixed(0)} ₽`}
            </span>
            {spool.price == null && spool.filament?.price_per_kg != null && (
              <span className="text-gray-600 ml-1">
                ({spool.filament.price_per_kg.toFixed(0)} ₽/кг, рек.)
              </span>
            )}
          </p>
        )}

        {/* Lot / comment */}
        {(spool.lot_nr || spool.comment) && (
          <p className="text-gray-500 text-xs truncate">
            {spool.lot_nr && <span className="mr-2">№ {spool.lot_nr}</span>}
            {spool.comment}
          </p>
        )}

        {/* MMU gate badge */}
        {(() => {
          const printerNameRaw = spool.extra?.printer_name;
          const gateRaw = spool.extra?.mmu_gate_map;
          if (!printerNameRaw || gateRaw == null) return null;
          try {
            const printerName = JSON.parse(printerNameRaw) as string;
            const gate = typeof gateRaw === 'string' ? JSON.parse(gateRaw) : Number(gateRaw);
            if (!printerName || typeof gate !== 'number' || !Number.isFinite(gate) || gate < 0) return null;
            return (
              <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-purple-500/20 border border-purple-500/30 text-purple-300 w-fit">
                <span className="font-mono">MMU</span>
                <span className="text-purple-400">{printerName}</span>
                <span>#{gate}</span>
              </span>
            );
          } catch {
            return null;
          }
        })()}

        <div className="grid grid-cols-2 gap-2 pt-1">
          <button
            type="button"
            onClick={onEdit}
            disabled={!onEdit || isBusy}
            className="inline-flex items-center justify-center gap-1 rounded-lg border border-white/20 bg-white/5 px-2 py-1 text-[11px] text-gray-200 hover:bg-white/10 disabled:opacity-50"
          >
            <Edit className="h-3 w-3" />
            <span>{t('profilePage.spoolActions.edit')}</span>
          </button>
          <button
            type="button"
            onClick={onUse}
            disabled={!onUse || isBusy || spool.remaining_weight_g <= 0}
            className="inline-flex items-center justify-center gap-1 rounded-lg border border-white/20 bg-white/5 px-2 py-1 text-[11px] text-gray-200 hover:bg-white/10 disabled:opacity-50"
          >
            <Gauge className="h-3 w-3" />
            <span>{t('profilePage.spoolActions.use')}</span>
          </button>
          <select
            value={spool.state}
            onChange={(e) => onStateChange?.(e.target.value as SpoolState)}
            disabled={!onStateChange || isBusy}
            className="w-full rounded-lg border border-white/20 bg-white/5 px-2 py-1 text-[11px] text-gray-200 focus:border-purple-500 focus:outline-none disabled:opacity-50"
          >
            {(['active', 'shelf', 'archived', 'empty'] as const).map(s => (
              <option key={s} value={s}>{t(`profilePage.spoolState.${s}`)}</option>
            ))}
          </select>
          <button
            type="button"
            onClick={onDelete}
            disabled={!onDelete || isBusy}
            className="inline-flex items-center justify-center gap-1 rounded-lg border border-red-500/30 bg-red-500/10 px-2 py-1 text-[11px] text-red-200 hover:bg-red-500/20 disabled:opacity-50"
          >
            <Trash2 className="h-3 w-3" />
            <span>{t('profilePage.spoolActions.delete')}</span>
          </button>
        </div>
      </div>
    </div>
  );
};

interface SpoolFormProps {
  mode: 'create' | 'edit';
  spool?: UserSpool;
  onSaved: () => void;
  onCancel: () => void;
}

const SpoolForm: React.FC<SpoolFormProps> = ({ mode, spool, onSaved, onCancel }) => {
  const { user } = useAuth();
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [filamentId, setFilamentId] = useState<string>(spool?.filament_id ? String(spool.filament_id) : '');
  const [initialWeight, setInitialWeight] = useState<string>(spool ? String(spool.initial_weight_g) : '1000');
  const [usedWeight, setUsedWeight] = useState<string>(spool ? String(spool.used_weight_g) : '0');
  const [state, setState] = useState<SpoolState>(spool?.state ?? 'active');
  const [price, setPrice] = useState<string>(spool?.price != null ? String(spool.price) : '');
  const [lotNr, setLotNr] = useState<string>(spool?.lot_nr ?? '');
  const [comment, setComment] = useState<string>(spool?.comment ?? '');
  const [isQrPanelOpen, setIsQrPanelOpen] = useState(false);
  const [qrInput, setQrInput] = useState('');
  const [qrBusy, setQrBusy] = useState(false);
  const [qrError, setQrError] = useState<string | null>(null);
  const [qrSuccess, setQrSuccess] = useState<string | null>(null);
  const [scannedFilament, setScannedFilament] = useState<Filament | null>(null);
  const [isCameraOpen, setIsCameraOpen] = useState(false);
  const [isCameraBusy, setIsCameraBusy] = useState(false);
  const [isCameraReady, setIsCameraReady] = useState(false);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const cameraStreamRef = useRef<MediaStream | null>(null);
  const cameraFrameRef = useRef<number | null>(null);
  const cameraDetectorRef = useRef<{ detect: (source: any) => Promise<Array<{ rawValue?: string }>> } | null>(null);
  const isCameraScanningRef = useRef(false);
  const [errorText, setErrorText] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [gateStep, setGateStep] = useState(false);
  const [createdSpool, setCreatedSpool] = useState<UserSpool | null>(null);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>('');
  const [selectedGate, setSelectedGate] = useState<string>('');
  const [assigning, setAssigning] = useState(false);

  const { data: filamentsData } = useQuery({
    queryKey: ['spool-form-filaments'],
    queryFn: () => filamentsAPI.list({ page: 1, size: 100, active_only: true }),
  });

  const { data: presetFilamentIds = [] } = useQuery({
    queryKey: ['spool-form-user-preset-filaments', user?.id],
    queryFn: async () => {
      const response = await presetsAPI.list({
        active_only: false,
        page: 1,
        size: 100,
        user_id: user?.id,
      });
      const uniqueIds = new Set<number>();
      response.items.forEach((preset) => {
        if (preset.filament_id) {
          uniqueIds.add(preset.filament_id);
        }
      });
      return Array.from(uniqueIds);
    },
    enabled: !!user?.id,
  });

  const { data: allDevices = [] } = useQuery<UserPrinterDevice[]>({
    queryKey: ['spool-form-devices'],
    queryFn: () => devicesAPI.list(),
    enabled: mode === 'create',
  });

  const hhDevices = useMemo(
    () => allDevices.filter((d) => d.supports_hh),
    [allDevices],
  );

  const filamentOptions = useMemo(() => {
    const allowedIds = new Set(presetFilamentIds);
    const list = [...(filamentsData?.items ?? [])].filter((item) => allowedIds.has(item.id));
    if (scannedFilament && !list.some((item) => item.id === scannedFilament.id)) {
      list.unshift(scannedFilament);
    }
    if (spool?.filament && !list.some((item) => item.id === spool.filament!.id)) {
      list.unshift({
        id: spool.filament.id,
        brand_id: 0,
        brand_name: spool.filament.brand_name,
        name: spool.filament.name,
        material_type: spool.filament.material_type,
        color_name: spool.filament.color_name,
        color_hex: spool.filament.color_hex,
        visual_settings: null,
        diameter: 1.75,
        density: null,
        price_per_kg: null,
        spool_weight: null,
        empty_spool_weight_g: null,
        description: null,
        views_count: null,
        scans_count: null,
        qr_code: null,
        active: true,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      });
    }
    return list;
  }, [filamentsData?.items, presetFilamentIds, scannedFilament, spool?.filament]);

  useEffect(() => {
    if (!spool) {
      return;
    }
    setFilamentId(spool.filament_id ? String(spool.filament_id) : '');
    setInitialWeight(String(spool.initial_weight_g));
    setUsedWeight(String(spool.used_weight_g));
    setState(spool.state);
    setPrice(spool.price != null ? String(spool.price) : '');
    setLotNr(spool.lot_nr ?? '');
    setComment(spool.comment ?? '');
    setIsQrPanelOpen(false);
    setQrInput('');
    setQrError(null);
    setQrSuccess(null);
    setScannedFilament(null);
    setIsCameraOpen(false);
    setIsCameraBusy(false);
    setIsCameraReady(false);
    setErrorText(null);
  }, [spool]);

  const stopCameraScan = () => {
    isCameraScanningRef.current = false;
    if (cameraFrameRef.current !== null) {
      cancelAnimationFrame(cameraFrameRef.current);
      cameraFrameRef.current = null;
    }
    cameraDetectorRef.current = null;
    if (cameraStreamRef.current) {
      cameraStreamRef.current.getTracks().forEach((track) => track.stop());
      cameraStreamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setIsCameraReady(false);
    setIsCameraOpen(false);
  };

  useEffect(() => {
    if (!isQrPanelOpen) {
      stopCameraScan();
    }
  }, [isQrPanelOpen]);

  useEffect(() => {
    return () => {
      stopCameraScan();
    };
  }, []);

  const extractQrShortCode = (rawValue: string): string | null => {
    const normalized = rawValue.trim();
    if (!normalized) {
      return null;
    }

    // Поддерживаем полный URL вида https://.../qr/<SHORT_CODE>
    if (normalized.startsWith('http://') || normalized.startsWith('https://')) {
      try {
        const parsed = new URL(normalized);
        const segments = parsed.pathname.split('/').filter(Boolean);
        const qrIndex = segments.findIndex((segment) => segment.toLowerCase() === 'qr');
        if (qrIndex !== -1 && segments[qrIndex + 1]) {
          return segments[qrIndex + 1];
        }
      } catch {
        // Если URL невалидный — пробуем как обычный short code.
      }
    }

    const match = normalized.match(/[A-Za-z0-9_-]{4,100}/);
    return match ? match[0] : null;
  };

  const resolveQrCode = async (rawCode: string) => {
    const shortCode = extractQrShortCode(rawCode);
    if (!shortCode) {
      setQrError(t('profilePage.spoolAddModal.scanQrInvalid'));
      return;
    }

    setQrBusy(true);
    setQrError(null);
    setQrSuccess(null);
    try {
      const response = await qrAPI.scan(shortCode);
      if (!response?.filament) {
        setQrError(t('profilePage.spoolAddModal.scanQrNoFilament'));
        return;
      }

      setScannedFilament(response.filament);
      setFilamentId(String(response.filament.id));
      setQrInput('');
      setIsQrPanelOpen(false);
      setQrSuccess(
        response.preset_added
          ? t('profilePage.spoolAddModal.scanQrSuccessWithPreset')
          : t('profilePage.spoolAddModal.scanQrSuccess')
      );
    } catch (error: any) {
      setQrError(translateApiError(t, error?.response?.data?.detail));
    } finally {
      setQrBusy(false);
    }
  };

  const startCameraScan = async () => {
    setQrError(null);
    setQrSuccess(null);

    if (!navigator.mediaDevices?.getUserMedia) {
      setQrError(t('profilePage.spoolAddModal.scanQrCameraNotSupported'));
      return;
    }

    const BarcodeDetectorCtor = (window as any).BarcodeDetector as
      | (new (options?: { formats?: string[] }) => { detect: (source: any) => Promise<Array<{ rawValue?: string }>> })
      | undefined;

    if (!BarcodeDetectorCtor) {
      setQrError(t('profilePage.spoolAddModal.scanQrCameraNotSupported'));
      return;
    }

    setIsCameraBusy(true);
    setIsCameraOpen(true);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' } },
        audio: false,
      });
      cameraStreamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }

      cameraDetectorRef.current = new BarcodeDetectorCtor({ formats: ['qr_code'] });
      isCameraScanningRef.current = true;
      setIsCameraReady(true);

      const scanFrame = async () => {
        if (!isCameraScanningRef.current) {
          return;
        }

        const video = videoRef.current;
        const detector = cameraDetectorRef.current;

        if (!video || !detector || video.readyState < 2) {
          cameraFrameRef.current = requestAnimationFrame(() => {
            void scanFrame();
          });
          return;
        }

        try {
          const barcodes = await detector.detect(video);
          if (!isCameraScanningRef.current) {
            return;
          }
          const rawValue = barcodes.find((item) => item.rawValue)?.rawValue;
          if (rawValue) {
            stopCameraScan();
            await resolveQrCode(rawValue);
            return;
          }
        } catch {
          // Игнорируем временные ошибки декодирования и продолжаем цикл.
        }

        cameraFrameRef.current = requestAnimationFrame(() => {
          void scanFrame();
        });
      };

      cameraFrameRef.current = requestAnimationFrame(() => {
        void scanFrame();
      });
    } catch (error: any) {
      stopCameraScan();
      if (error?.name === 'NotAllowedError' || error?.name === 'PermissionDeniedError') {
        setQrError(t('profilePage.spoolAddModal.scanQrCameraPermissionDenied'));
      } else {
        setQrError(translateApiError(t, error?.response?.data?.detail));
      }
    } finally {
      setIsCameraBusy(false);
    }
  };

  const handlePasteQrFromClipboard = async () => {
    setQrError(null);
    try {
      if (!navigator.clipboard?.readText) {
        setQrError(t('profilePage.spoolAddModal.scanQrPasteFailed'));
        return;
      }
      const text = await navigator.clipboard.readText();
      if (!text.trim()) {
        setQrError(t('profilePage.spoolAddModal.scanQrInvalid'));
        return;
      }
      setQrInput(text);
      await resolveQrCode(text);
    } catch {
      setQrError(t('profilePage.spoolAddModal.scanQrPasteFailed'));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorText(null);
    const parsedInitial = parseFloat(initialWeight);
    const parsedUsed = parseFloat(usedWeight || '0');

    if (!Number.isFinite(parsedInitial) || parsedInitial <= 0) {
      setErrorText(t('profilePage.spoolActions.invalidInitialWeight'));
      return;
    }
    if (!Number.isFinite(parsedUsed) || parsedUsed < 0) {
      setErrorText(t('profilePage.spoolActions.invalidUsedWeight'));
      return;
    }
    if (parsedUsed > parsedInitial) {
      setErrorText(t('profilePage.spoolActions.usedGreaterThanInitial'));
      return;
    }

    setSaving(true);
    try {
      const parsedPrice = price !== '' ? parseFloat(price) : null;
      const payload = {
        filament_id: filamentId ? Number(filamentId) : null,
        initial_weight_g: parsedInitial,
        used_weight_g: parsedUsed,
        price: parsedPrice != null && Number.isFinite(parsedPrice) ? parsedPrice : null,
        state,
        lot_nr: lotNr || null,
        comment: comment || null,
      };
      if (mode === 'edit' && spool) {
        await spoolsAPI.update(spool.id, payload);
        queryClient.invalidateQueries({ queryKey: ['user-spools'] });
        onSaved();
      } else {
        const newSpool = await spoolsAPI.create(payload);
        queryClient.invalidateQueries({ queryKey: ['user-spools'] });
        if (hhDevices.length > 0) {
          setCreatedSpool(newSpool);
          if (hhDevices.length === 1) setSelectedDeviceId(String(hhDevices[0].id));
          setGateStep(true);
        } else {
          onSaved();
        }
      }
    } catch (error: any) {
      setErrorText(translateApiError(t, error?.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const handleAssignToGate = async () => {
    if (!createdSpool || !selectedDeviceId || selectedGate === '') return;
    setAssigning(true);
    setErrorText(null);
    try {
      await presetSlotsAPI.assign(Number(selectedDeviceId), Number(selectedGate), { spool_id: createdSpool.id });
      queryClient.invalidateQueries({ queryKey: ['user-spools'] });
      onSaved();
    } catch (err: any) {
      setErrorText(translateApiError(t, err?.response?.data?.detail));
      setAssigning(false);
    }
  };

  const inputCls = 'w-full bg-white/5 border border-white/20 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-purple-500 placeholder-gray-500';
  const labelCls = 'block text-xs text-gray-400 mb-1';

  if (gateStep && createdSpool) {
    const selectedDevice = hhDevices.find((d) => d.id === Number(selectedDeviceId));
    const gateCount = selectedDevice?.gate_count ?? null;
    return (
      <div className="bg-white/10 backdrop-blur-sm border border-white/20 rounded-2xl p-4 md:p-5 space-y-4 max-w-2xl mx-auto">
        <div className="flex items-center gap-2">
          <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0" />
          <h3 className="text-white font-semibold text-base">{t('profilePage.spoolGateStep.title')}</h3>
        </div>
        <p className="text-gray-400 text-sm">{t('profilePage.spoolGateStep.hint')}</p>

        <div className="space-y-3">
          {hhDevices.length > 1 && (
            <div>
              <label className={labelCls}>{t('profilePage.spoolGateStep.deviceLabel')}</label>
              <select
                value={selectedDeviceId}
                onChange={(e) => { setSelectedDeviceId(e.target.value); setSelectedGate(''); }}
                className={inputCls}
              >
                <option value="">{t('profilePage.spoolGateStep.selectDevice')}</option>
                {hhDevices.map((d) => (
                  <option key={d.id} value={d.id}>{d.name}</option>
                ))}
              </select>
            </div>
          )}

          {selectedDeviceId && gateCount !== null && gateCount > 0 && (
            <div>
              <label className={labelCls}>{t('profilePage.spoolGateStep.gateLabel')}</label>
              <div className="flex flex-wrap gap-2">
                {Array.from({ length: gateCount }, (_, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => setSelectedGate(String(i))}
                    className={`w-10 h-10 rounded-lg border text-sm font-mono font-semibold transition-colors ${
                      selectedGate === String(i)
                        ? 'border-purple-500 bg-purple-500/30 text-purple-200'
                        : 'border-white/20 bg-white/5 text-gray-300 hover:bg-white/10'
                    }`}
                  >
                    {i}
                  </button>
                ))}
              </div>
            </div>
          )}

          {selectedDeviceId && gateCount === null && (
            <div>
              <label className={labelCls}>{t('profilePage.spoolGateStep.gateLabel')}</label>
              <input
                type="number"
                min={0}
                max={99}
                value={selectedGate}
                onChange={(e) => setSelectedGate(e.target.value)}
                placeholder="0"
                className={`w-24 ${inputCls}`}
              />
            </div>
          )}
        </div>

        {errorText && <p className="text-red-400 text-xs">{errorText}</p>}

        <div className="flex gap-2 pt-1">
          <button
            type="button"
            onClick={handleAssignToGate}
            disabled={assigning || !selectedDeviceId || selectedGate === ''}
            className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-sm font-medium disabled:opacity-50 transition-colors"
          >
            {assigning && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            {t('profilePage.spoolGateStep.assign')}
          </button>
          <button
            type="button"
            onClick={onSaved}
            className="px-4 py-2 rounded-lg border border-white/20 text-gray-300 text-sm hover:bg-white/10 transition-colors"
          >
            {t('profilePage.spoolGateStep.skip')}
          </button>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="bg-white/10 backdrop-blur-sm border border-white/20 rounded-2xl p-4 md:p-5 space-y-4 max-w-2xl mx-auto">
      <h3 className="text-white font-semibold text-base">
        {mode === 'edit' ? t('profilePage.spoolEditModal.title') : t('profilePage.spoolAddModal.title')}
      </h3>

      <div>
        <div className="flex items-center justify-between gap-2 mb-1">
          <label className={`${labelCls} mb-0`}>{t('profilePage.spoolAddModal.filamentLabel')}</label>
          <button
            type="button"
            onClick={() => setIsQrPanelOpen((prev) => !prev)}
            className="inline-flex items-center gap-1.5 text-xs px-2 py-1 rounded-md border border-white/20 text-gray-300 hover:bg-white/10 transition-colors"
          >
            <QrCode className="w-3.5 h-3.5" />
            <span>{t('profilePage.spoolAddModal.scanQr')}</span>
          </button>
        </div>

        {isQrPanelOpen && (
          <div className="mb-3 p-3 bg-white/5 border border-white/10 rounded-lg space-y-2">
            <p className="text-xs text-gray-400">{t('profilePage.spoolAddModal.scanQrHint')}</p>
            <input
              type="text"
              value={qrInput}
              onChange={(e) => setQrInput(e.target.value)}
              placeholder={t('profilePage.spoolAddModal.scanQrPlaceholder')}
              className={inputCls}
              disabled={qrBusy}
            />
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => resolveQrCode(qrInput)}
                disabled={qrBusy}
                className="inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-md bg-purple-600/80 hover:bg-purple-600 text-white text-xs font-medium transition-colors disabled:opacity-60"
              >
                {qrBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <QrCode className="w-3.5 h-3.5" />}
                <span>{t('profilePage.spoolAddModal.scanQrApply')}</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  if (isCameraOpen) {
                    stopCameraScan();
                    return;
                  }
                  void startCameraScan();
                }}
                disabled={isCameraBusy}
                className="px-3 py-2 rounded-md border border-white/20 text-gray-300 text-xs hover:bg-white/10 transition-colors disabled:opacity-60 inline-flex items-center gap-1.5"
              >
                {isCameraBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Camera className="w-3.5 h-3.5" />}
                <span>{isCameraOpen ? t('profilePage.spoolAddModal.scanQrCameraStop') : t('profilePage.spoolAddModal.scanQrCameraStart')}</span>
              </button>
              <button
                type="button"
                onClick={handlePasteQrFromClipboard}
                disabled={qrBusy}
                className="px-3 py-2 rounded-md border border-white/20 text-gray-300 text-xs hover:bg-white/10 transition-colors disabled:opacity-60"
              >
                {t('profilePage.spoolAddModal.scanQrPaste')}
              </button>
            </div>

            {isCameraOpen && (
              <div className="mt-2 rounded-lg overflow-hidden border border-white/15 bg-black/30">
                <video ref={videoRef} className="w-full max-h-64 object-cover" playsInline muted autoPlay />
                <div className="px-3 py-2 text-xs text-gray-300 border-t border-white/10">
                  <p>{isCameraReady ? t('profilePage.spoolAddModal.scanQrCameraHint') : t('profilePage.spoolAddModal.scanQrCameraStarting')}</p>
                </div>
              </div>
            )}
          </div>
        )}

        <select
          value={filamentId}
          onChange={(e) => setFilamentId(e.target.value)}
          className={inputCls}
        >
          <option value="">{t('profilePage.spoolAddModal.filamentPlaceholder')}</option>
          {filamentOptions.map((filament) => (
            <option key={filament.id} value={filament.id}>
              {[filament.brand_name, filament.name, filament.color_name].filter(Boolean).join(' · ') || filament.name}
            </option>
          ))}
        </select>
        {filamentOptions.length === 0 && (
          <p className="mt-1 text-xs text-gray-500">{t('profilePage.spoolAddModal.noPresetFilaments')}</p>
        )}
        {qrError && (
          <p className="mt-2 text-xs text-red-300 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">{qrError}</p>
        )}
        {qrSuccess && (
          <p className="mt-2 text-xs text-green-300 bg-green-500/10 border border-green-500/30 rounded-lg px-3 py-2">{qrSuccess}</p>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className={labelCls}>{t('profilePage.spoolAddModal.initialWeight')}</label>
          <input type="number" min="1" max="10000" step="1" value={initialWeight}
            onChange={e => setInitialWeight(e.target.value)} className={inputCls} required />
        </div>
        <div>
          <label className={labelCls}>{t('profilePage.spoolAddModal.usedWeight')}</label>
          <input type="number" min="0" max="10000" step="1" value={usedWeight}
            onChange={e => setUsedWeight(e.target.value)} className={inputCls} />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className={labelCls}>{t('profilePage.spoolAddModal.state')}</label>
          <select value={state} onChange={e => setState(e.target.value as SpoolState)} className={inputCls}>
            {(['active', 'shelf', 'archived', 'empty'] as const).map(s => (
              <option key={s} value={s}>{t(`profilePage.spoolState.${s}`)}</option>
            ))}
          </select>
        </div>

        <div>
          <label className={labelCls}>{t('profilePage.spoolAddModal.price')}</label>
          <input type="number" min="0" step="1" value={price}
            onChange={e => setPrice(e.target.value)}
            placeholder={t('profilePage.spoolAddModal.pricePlaceholder')} className={inputCls} />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className={labelCls}>{t('profilePage.spoolAddModal.lotNr')}</label>
          <input type="text" value={lotNr} onChange={e => setLotNr(e.target.value)}
            placeholder={t('profilePage.spoolAddModal.optional')} className={inputCls} />
        </div>
      </div>

      <div>
        <label className={labelCls}>{t('profilePage.spoolAddModal.comment')}</label>
        <input type="text" value={comment} onChange={e => setComment(e.target.value)}
          placeholder="необязательно" className={inputCls} />
      </div>

      {errorText && (
        <p className="text-xs text-red-300 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">{errorText}</p>
      )}

      <div className="flex gap-2 pt-1">
        <button type="submit" disabled={saving}
          className="flex-1 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white py-2 rounded-lg text-sm font-medium transition-all disabled:opacity-60">
          {saving ? (
            <Loader2 className="w-4 h-4 animate-spin mx-auto" />
          ) : mode === 'edit' ? t('profilePage.spoolEditModal.submit') : t('profilePage.spoolAddModal.submit')}
        </button>
        <button type="button" onClick={onCancel}
          className="px-4 py-2 rounded-lg border border-white/20 text-sm text-gray-300 hover:bg-white/10 transition-all">
          {t('profilePage.spoolAddModal.cancel')}
        </button>
      </div>
    </form>
  );
};

interface UseSpoolFormProps {
  spool: UserSpool;
  onSaved: () => void;
  onCancel: () => void;
}

const UseSpoolForm: React.FC<UseSpoolFormProps> = ({ spool, onSaved, onCancel }) => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [deltaWeight, setDeltaWeight] = useState<string>('10');
  const [errorText, setErrorText] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorText(null);
    const parsedDelta = parseFloat(deltaWeight);

    if (!Number.isFinite(parsedDelta) || parsedDelta <= 0) {
      setErrorText(t('profilePage.spoolUseModal.invalidDelta'));
      return;
    }
    if (parsedDelta > spool.remaining_weight_g) {
      setErrorText(t('profilePage.spoolUseModal.exceedsRemaining'));
      return;
    }

    setSaving(true);
    try {
      await spoolsAPI.use(spool.id, parsedDelta);
      queryClient.invalidateQueries({ queryKey: ['user-spools'] });
      onSaved();
    } catch (error: any) {
      setErrorText(translateApiError(t, error?.response?.data?.detail));
    } finally {
      setSaving(false);
    }
  };

  const inputCls = 'w-full bg-white/5 border border-white/20 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-purple-500 placeholder-gray-500';
  const labelCls = 'block text-xs text-gray-400 mb-1';

  return (
    <form onSubmit={handleSubmit} className="bg-white/10 backdrop-blur-sm border border-white/20 rounded-2xl p-4 md:p-5 space-y-4 max-w-xl mx-auto">
      <h3 className="text-white font-semibold text-base">{t('profilePage.spoolUseModal.title')}</h3>
      <p className="text-xs text-gray-400">
        {spool.filament?.name ?? t('profilePage.spoolNoFilament')} · {t('profilePage.spoolRemaining')}: {spool.remaining_weight_g.toFixed(0)} г
      </p>
      <div>
        <label className={labelCls}>{t('profilePage.spoolUseModal.deltaLabel')}</label>
        <input
          type="number"
          min="1"
          max={Math.max(1, Math.floor(spool.remaining_weight_g))}
          step="0.1"
          value={deltaWeight}
          onChange={e => setDeltaWeight(e.target.value)}
          className={inputCls}
          required
        />
      </div>

      {errorText && (
        <p className="text-xs text-red-300 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">{errorText}</p>
      )}

      <div className="flex gap-2 pt-1">
        <button type="submit" disabled={saving}
          className="flex-1 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white py-2 rounded-lg text-sm font-medium transition-all disabled:opacity-60">
          {saving ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : t('profilePage.spoolUseModal.submit')}
        </button>
        <button type="button" onClick={onCancel}
          className="px-4 py-2 rounded-lg border border-white/20 text-sm text-gray-300 hover:bg-white/10 transition-all">
          {t('profilePage.spoolUseModal.cancel')}
        </button>
      </div>
    </form>
  );
};

interface SpoolsTabProps {
  spools: UserSpool[];
  printerBindings: Array<{ id: number; name: string }>;
  onRefetch: () => void;
  isAddOpen: boolean;
  setIsAddOpen: (v: boolean) => void;
}

const SpoolsTab: React.FC<SpoolsTabProps> = ({
  spools,
  printerBindings,
  onRefetch,
  isAddOpen,
  setIsAddOpen,
}) => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [spoolTab, setSpoolTab] = useState<'shelf' | 'active' | 'archived'>('shelf');
  const [editingSpool, setEditingSpool] = useState<UserSpool | null>(null);
  const [usingSpool, setUsingSpool] = useState<UserSpool | null>(null);
  const [busySpoolId, setBusySpoolId] = useState<number | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [setupError, setSetupError] = useState<string | null>(null);
  const [isSetupOpen, setIsSetupOpen] = useState(false);
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const [newDeviceName, setNewDeviceName] = useState('');
  const [isCreatingDevice, setIsCreatingDevice] = useState(false);
  const [showNewDeviceForm, setShowNewDeviceForm] = useState(false);
  const [revealedKeys, setRevealedKeys] = useState<Record<number, string>>({});
  const [copiedDeviceId, setCopiedDeviceId] = useState<number | null>(null);
  const [editingHostname, setEditingHostname] = useState<Record<number, string>>({});
  const [savingHostname, setSavingHostname] = useState<number | null>(null);

  const { data: devices = [], refetch: refetchDevices } = useQuery({
    queryKey: ['devices'],
    queryFn: devicesAPI.list,
    staleTime: 60_000,
  });

  const spoolCompatBaseUrl = useMemo(() => {
    if (typeof window === 'undefined' || !window.location?.origin) {
      return 'https://filamenthub.ru/api/v1/spool_compat';
    }
    return `${window.location.origin}/api/v1/spool_compat`;
  }, []);

  const handleCopyConfig = async (apiKey: string, deviceId: number) => {
    const endpoint = `${spoolCompatBaseUrl}/${apiKey}`;
    const snippet = `[spoolman]\nserver: ${endpoint}\nsync_rate: 5`;
    setSetupError(null);
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(snippet);
      } else {
        const textarea = document.createElement('textarea');
        textarea.value = snippet;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        document.execCommand('copy');
        textarea.remove();
      }
      setCopiedDeviceId(deviceId);
      setTimeout(() => {
        setCopiedDeviceId((prev) => (prev === deviceId ? null : prev));
      }, 1800);
    } catch {
      setSetupError(t('profilePage.deviceSetup.copyFailed'));
    }
  };

  const handleCreateDevice = async () => {
    const name = newDeviceName.trim();
    if (!name) return;
    setSetupError(null);
    setIsCreatingDevice(true);
    try {
      const result = await devicesAPI.createWithKey(name);
      setRevealedKeys((prev) => ({ ...prev, [result.device.id]: result.api_key }));
      setNewDeviceName('');
      setShowNewDeviceForm(false);
      queryClient.invalidateQueries({ queryKey: ['devices'] });
      await refetchDevices();
    } catch (error: any) {
      setSetupError(translateApiError(t, error?.response?.data?.detail));
    } finally {
      setIsCreatingDevice(false);
    }
  };

  const handleRegenerateKey = async (deviceId: number) => {
    if (!window.confirm(t('profilePage.deviceSetup.regenerateConfirm'))) return;
    setSetupError(null);
    try {
      const result = await devicesAPI.regenerateKey(deviceId);
      setRevealedKeys((prev) => ({ ...prev, [deviceId]: result.api_key }));
      queryClient.invalidateQueries({ queryKey: ['devices'] });
    } catch (error: any) {
      setSetupError(translateApiError(t, error?.response?.data?.detail));
    }
  };

  const handleSaveHostname = async (deviceId: number) => {
    const hostname = (editingHostname[deviceId] ?? '').trim();
    setSavingHostname(deviceId);
    setSetupError(null);
    try {
      await devicesAPI.update(deviceId, { printer_hostname: hostname || null });
      setEditingHostname((prev) => {
        const next = { ...prev };
        delete next[deviceId];
        return next;
      });
      queryClient.invalidateQueries({ queryKey: ['devices'] });
      await refetchDevices();
    } catch (error: any) {
      setSetupError(translateApiError(t, error?.response?.data?.detail));
    } finally {
      setSavingHostname(null);
    }
  };

  const handleDeleteDevice = async (deviceId: number) => {
    if (!window.confirm(t('profilePage.deviceSetup.deleteConfirm'))) return;
    setSetupError(null);
    try {
      await devicesAPI.remove(deviceId);
      setRevealedKeys((prev) => {
        const next = { ...prev };
        delete next[deviceId];
        return next;
      });
      queryClient.invalidateQueries({ queryKey: ['devices'] });
      await refetchDevices();
    } catch (error: any) {
      setSetupError(translateApiError(t, error?.response?.data?.detail));
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm(t('profilePage.spoolActions.deleteConfirm'))) {
      return;
    }
    setActionError(null);
    setBusySpoolId(id);
    try {
      await spoolsAPI.delete(id);
      queryClient.invalidateQueries({ queryKey: ['user-spools'] });
      onRefetch();
    } catch (error: any) {
      setActionError(translateApiError(t, error?.response?.data?.detail));
    } finally {
      setBusySpoolId(null);
    }
  };

  const handleStateChange = async (id: number, state: SpoolState) => {
    setActionError(null);
    setBusySpoolId(id);
    try {
      await spoolsAPI.update(id, { state });
      queryClient.invalidateQueries({ queryKey: ['user-spools'] });
      onRefetch();
    } catch (error: any) {
      setActionError(translateApiError(t, error?.response?.data?.detail));
    } finally {
      setBusySpoolId(null);
    }
  };

  const spoolTabCounts = useMemo(
    () => ({
      shelf: spools.filter((spool) => spool.state === 'shelf').length,
      active: spools.filter((spool) => spool.state === 'active').length,
      archived: spools.filter((spool) => spool.state === 'archived' || spool.state === 'empty').length,
    }),
    [spools],
  );

  const filteredSpools = useMemo(() => {
    if (spoolTab === 'shelf') {
      return spools.filter((spool) => spool.state === 'shelf');
    }
    if (spoolTab === 'active') {
      return spools.filter((spool) => spool.state === 'active');
    }
    return spools.filter((spool) => spool.state === 'archived' || spool.state === 'empty');
  }, [spools, spoolTab]);

  const spoolTabs: Array<{ key: 'shelf' | 'active' | 'archived'; label: string; count: number }> = [
    { key: 'shelf', label: t('profilePage.spoolTabs.shelf'), count: spoolTabCounts.shelf },
    { key: 'active', label: t('profilePage.spoolTabs.active'), count: spoolTabCounts.active },
    { key: 'archived', label: t('profilePage.spoolTabs.archived'), count: spoolTabCounts.archived },
  ];

  return (
    <div className="space-y-4 md:space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-lg md:text-2xl font-bold text-white">{t('profilePage.spoolsTitle')}</h3>
          <button
            type="button"
            onClick={() => setIsHelpOpen((prev) => !prev)}
            className={`flex items-center justify-center w-6 h-6 rounded-full border transition-colors ${
              isHelpOpen
                ? 'border-purple-500 bg-purple-500/20 text-purple-300'
                : 'border-white/20 text-gray-400 hover:border-white/40 hover:text-gray-200'
            }`}
            title={t('profilePage.spoolHelp.toggle')}
          >
            <HelpCircle className="w-3.5 h-3.5" />
          </button>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsSetupOpen((prev) => !prev)}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border border-white/20 text-gray-200 hover:bg-white/10 transition-colors text-sm"
            title={isSetupOpen ? t('profilePage.spoolSetup.hide') : t('profilePage.spoolSetup.show')}
          >
            <Cog className="w-4 h-4" />
            <span className="hidden sm:inline">
              {isSetupOpen ? t('profilePage.spoolSetup.hide') : t('profilePage.spoolSetup.show')}
            </span>
          </button>
          <button
            onClick={() => {
              setEditingSpool(null);
              setUsingSpool(null);
              setIsAddOpen(true);
            }}
            className="flex items-center gap-1.5 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white px-3 md:px-4 py-2 rounded-lg text-sm transition-all shadow-lg shadow-purple-500/25"
          >
            <Plus className="w-4 h-4" />
            <span>{t('profilePage.spoolsAdd')}</span>
          </button>
        </div>
      </div>

      {isHelpOpen && (
        <div className="bg-blue-500/10 border border-blue-500/20 rounded-2xl p-4 text-sm text-gray-300 space-y-2">
          <p className="font-semibold text-white">{t('profilePage.spoolHelp.title')}</p>
          <ul className="space-y-1 list-disc list-inside text-gray-400">
            <li>{t('profilePage.spoolHelp.line1')}</li>
            <li>{t('profilePage.spoolHelp.line2')}</li>
            <li>{t('profilePage.spoolHelp.line3')}</li>
            <li>{t('profilePage.spoolHelp.line4')}</li>
          </ul>
        </div>
      )}

      {isSetupOpen && (
        <div className="bg-white/10 backdrop-blur-sm border border-white/20 rounded-2xl p-4 md:p-5 space-y-4">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div>
              <h4 className="text-white font-semibold text-base md:text-lg">{t('profilePage.deviceSetup.title')}</h4>
              <p className="text-gray-300 text-sm mt-1">{t('profilePage.deviceSetup.description')}</p>
            </div>
            <button
              onClick={() => setShowNewDeviceForm(true)}
              disabled={showNewDeviceForm}
              className="inline-flex items-center justify-center gap-2 px-3 py-2 rounded-lg bg-purple-600/80 hover:bg-purple-600 text-white text-sm font-medium transition-colors disabled:opacity-60"
            >
              <Plus className="w-4 h-4" />
              <span>{t('profilePage.deviceSetup.addPrinter')}</span>
            </button>
          </div>

          {showNewDeviceForm && (
            <div className="bg-black/20 border border-white/10 rounded-lg p-3 space-y-3">
              <p className="text-xs text-gray-400">{t('profilePage.deviceSetup.nameLabel')}</p>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={newDeviceName}
                  onChange={(e) => setNewDeviceName(e.target.value)}
                  placeholder={t('profilePage.deviceSetup.namePlaceholder')}
                  maxLength={200}
                  className="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-white placeholder-gray-600 focus:border-purple-500 focus:outline-none"
                  onKeyDown={(e) => { if (e.key === 'Enter') handleCreateDevice(); }}
                />
                <button
                  onClick={handleCreateDevice}
                  disabled={isCreatingDevice || !newDeviceName.trim()}
                  className="inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg bg-purple-600 text-white text-sm font-medium transition-colors hover:bg-purple-500 disabled:opacity-50"
                >
                  {isCreatingDevice && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  {t('profilePage.deviceSetup.create')}
                </button>
                <button
                  onClick={() => { setShowNewDeviceForm(false); setNewDeviceName(''); }}
                  className="px-3 py-1.5 rounded-lg border border-white/10 text-gray-400 text-sm hover:bg-white/10"
                >
                  {t('common.cancel')}
                </button>
              </div>
            </div>
          )}

          {devices.length === 0 && !showNewDeviceForm && (
            <div className="text-center py-6 text-gray-500 text-sm">
              {t('profilePage.deviceSetup.noDevices')}
            </div>
          )}

          {devices.map((device) => {
            const apiKey = revealedKeys[device.id];
            const endpoint = apiKey ? `${spoolCompatBaseUrl}/${apiKey}` : null;
            const configSnippet = endpoint ? `[spoolman]\nserver: ${endpoint}\nsync_rate: 5` : null;
            const isConnected = device.last_seen_at != null;
            return (
              <div key={device.id} className="bg-black/20 border border-white/10 rounded-lg p-3 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-white font-medium text-sm">{device.name}</span>
                    {isConnected ? (
                      <span className="flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-300">
                        <Zap className="w-3 h-3" />
                        {device.gate_count != null
                          ? t('profilePage.deviceSetup.connectedGates', { count: device.gate_count })
                          : t('profilePage.deviceSetup.connected')}
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[11px] font-medium text-amber-300">
                        <Clock className="w-3 h-3" />
                        {t('profilePage.deviceSetup.awaitingConnection')}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-1.5">
                    <button
                      onClick={() => handleRegenerateKey(device.id)}
                      className="p-1.5 rounded-md text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
                      title={t('profilePage.deviceSetup.regenerateKey')}
                    >
                      <RefreshCw className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => handleDeleteDevice(device.id)}
                      className="p-1.5 rounded-md text-gray-400 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                      title={t('profilePage.deviceSetup.deleteDevice')}
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-400">{t('profilePage.deviceSetup.hostnameLabel')}:</span>
                  {editingHostname[device.id] !== undefined ? (
                    <div className="flex items-center gap-1.5">
                      <input
                        type="text"
                        value={editingHostname[device.id]}
                        onChange={(e) => setEditingHostname((prev) => ({ ...prev, [device.id]: e.target.value }))}
                        onKeyDown={(e) => { if (e.key === 'Enter') handleSaveHostname(device.id); }}
                        className="bg-black/30 border border-white/20 rounded px-2 py-0.5 text-xs text-white w-32 focus:border-blue-500 focus:outline-none"
                        placeholder="voron"
                        autoFocus
                      />
                      <button
                        onClick={() => handleSaveHostname(device.id)}
                        disabled={savingHostname === device.id}
                        className="text-xs text-blue-400 hover:text-blue-300"
                      >
                        {savingHostname === device.id ? '...' : '✓'}
                      </button>
                      <button
                        onClick={() => setEditingHostname((prev) => { const n = { ...prev }; delete n[device.id]; return n; })}
                        className="text-xs text-gray-500 hover:text-gray-300"
                      >✕</button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setEditingHostname((prev) => ({ ...prev, [device.id]: device.printer_hostname ?? '' }))}
                      className="text-xs text-gray-300 hover:text-white transition-colors"
                    >
                      {device.printer_hostname || <span className="text-amber-400 italic">{t('profilePage.deviceSetup.hostnameNotSet')}</span>}
                    </button>
                  )}
                </div>

                {apiKey && configSnippet ? (
                  <>
                    <p className="text-xs text-gray-400">{t('profilePage.deviceSetup.configLabel')}</p>
                    <pre className="text-xs md:text-sm text-gray-100 bg-black/30 rounded-md px-3 py-2 overflow-x-auto">{configSnippet}</pre>
                    <button
                      onClick={() => handleCopyConfig(apiKey, device.id)}
                      className="inline-flex items-center justify-center gap-2 px-3 py-1.5 rounded-md border border-white/15 text-gray-200 hover:bg-white/10 transition-colors text-sm"
                    >
                      {copiedDeviceId === device.id ? <CheckCircle className="w-4 h-4 text-green-400" /> : <Copy className="w-4 h-4" />}
                      <span>{copiedDeviceId === device.id ? t('profilePage.deviceSetup.copied') : t('profilePage.deviceSetup.copyConfig')}</span>
                    </button>
                    <p className="text-[11px] text-amber-300/80">{t('profilePage.deviceSetup.keyShownOnce')}</p>
                  </>
                ) : (
                  <p className="text-xs text-gray-500">
                    {device.has_api_key
                      ? t('profilePage.deviceSetup.keyHidden')
                      : t('profilePage.deviceSetup.noKey')}
                  </p>
                )}
              </div>
            );
          })}

          <div className="text-xs text-gray-400 space-y-1">
            <p>{t('profilePage.deviceSetup.note')}</p>
          </div>

          {setupError && (
            <p className="text-xs text-red-300 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">{setupError}</p>
          )}
        </div>
      )}

      <div className="space-y-4 md:space-y-6">
        {isAddOpen && (
          <SpoolForm
            mode="create"
            onSaved={() => {
              setIsAddOpen(false);
              onRefetch();
            }}
            onCancel={() => setIsAddOpen(false)}
          />
        )}

        {editingSpool && (
          <SpoolForm
            mode="edit"
            spool={editingSpool}
            onSaved={() => {
              setEditingSpool(null);
              onRefetch();
            }}
            onCancel={() => setEditingSpool(null)}
          />
        )}

        {usingSpool && (
          <UseSpoolForm
            spool={usingSpool}
            onSaved={() => {
              setUsingSpool(null);
              onRefetch();
            }}
            onCancel={() => setUsingSpool(null)}
          />
        )}

        {actionError && (
          <p className="text-xs text-red-300 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">{actionError}</p>
        )}

        <div className="flex flex-wrap gap-2">
          {spoolTabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setSpoolTab(tab.key)}
              className={[
                'inline-flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm transition-colors',
                spoolTab === tab.key
                  ? 'border-purple-400/70 bg-purple-500/20 text-white'
                  : 'border-white/15 bg-white/5 text-gray-300 hover:bg-white/10',
              ].join(' ')}
            >
              <span>{tab.label}</span>
              <span className="inline-flex min-w-[20px] items-center justify-center rounded-full bg-black/20 px-1.5 text-xs">
                {tab.count}
              </span>
            </button>
          ))}
        </div>

        {spoolTab === 'active' ? (
          <div className="space-y-4 md:space-y-5">
            <div className="bg-white/10 backdrop-blur-sm border border-white/20 rounded-2xl p-4 md:p-5">
              <PresetSlotsPanel compact spools={spools} printerBindings={printerBindings} />
            </div>

            <div className="space-y-3">
              <h4 className="text-base md:text-lg font-semibold text-white">{t('profilePage.spoolTabs.active')}</h4>
              {filteredSpools.length === 0 ? (
                <div className="text-center py-10 border border-white/10 rounded-2xl bg-white/5">
                  <Package className="w-10 h-10 text-gray-500 mx-auto mb-3" />
                  <p className="text-gray-400 text-sm md:text-base">{t('profilePage.spoolsActiveEmpty')}</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {filteredSpools.map((spool) => (
                    <SpoolCard
                      key={spool.id}
                      spool={spool}
                      isBusy={busySpoolId === spool.id}
                      onEdit={() => {
                        setIsAddOpen(false);
                        setUsingSpool(null);
                        setEditingSpool(spool);
                      }}
                      onUse={() => {
                        setIsAddOpen(false);
                        setEditingSpool(null);
                        setUsingSpool(spool);
                      }}
                      onDelete={() => handleDelete(spool.id)}
                      onStateChange={(state) => handleStateChange(spool.id, state)}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        ) : spools.length === 0 && !isAddOpen ? (
          <div className="text-center py-12 md:py-16">
            <Package className="w-14 h-14 md:w-20 md:h-20 text-gray-500 mx-auto mb-4" />
            <p className="text-gray-400 text-base md:text-lg">{t('profilePage.spoolsEmpty')}</p>
          </div>
        ) : filteredSpools.length === 0 ? (
          <div className="text-center py-10 border border-white/10 rounded-2xl bg-white/5">
            <Package className="w-10 h-10 text-gray-500 mx-auto mb-3" />
            <p className="text-gray-400 text-sm md:text-base">
              {t('profilePage.spoolsEmptyInTab', { tab: t(`profilePage.spoolTabs.${spoolTab}`) })}
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filteredSpools.map(spool => (
              <SpoolCard
                key={spool.id}
                spool={spool}
                isBusy={busySpoolId === spool.id}
                onEdit={() => {
                  setIsAddOpen(false);
                  setUsingSpool(null);
                  setEditingSpool(spool);
                }}
                onUse={() => {
                  setIsAddOpen(false);
                  setEditingSpool(null);
                  setUsingSpool(spool);
                }}
                onDelete={() => handleDelete(spool.id)}
                onStateChange={(state) => handleStateChange(spool.id, state)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

interface RecentSpoolsProps {
  spools: UserSpool[];
  onViewAll: () => void;
}

const RecentSpools: React.FC<RecentSpoolsProps> = ({ spools, onViewAll }) => {
  const { t } = useTranslation();
  return (
    <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-xl font-bold text-white flex items-center gap-2">
          <Package className="w-5 h-5" />
          {t('profilePage.recentSpools')}
        </h3>
        <button onClick={onViewAll} className="text-xs text-purple-400 hover:text-purple-300 transition-colors">
          {t('profilePage.spoolsTitle')} →
        </button>
      </div>
      <div className="space-y-1.5">
        {spools.length > 0 ? (
          spools.map(spool => {
            const iconColor = spool.filament?.color_hex
              ? `#${spool.filament.color_hex.replace('#', '')}`
              : '#9333ea';
            return (
              <div key={spool.id} className="flex items-center gap-2.5 p-2 bg-white/5 rounded-xl">
                <SpoolIcon pct={spool.remaining_pct} color={iconColor} size={38} />
                <div className="flex-1 min-w-0">
                  <p className="text-white text-xs font-medium truncate leading-tight">
                    {spool.filament?.name ?? t('profilePage.spoolNoFilament')}
                  </p>
                  {spool.filament && (
                    <p className="text-gray-500 text-xs truncate leading-tight">
                      {spool.filament.material_type}
                    </p>
                  )}
                </div>
                <div className="text-right flex-shrink-0">
                  <p className="text-white text-xs font-medium">{spool.remaining_weight_g.toFixed(0)}г</p>
                  <p className="text-gray-500 text-xs">{spool.remaining_pct.toFixed(0)}%</p>
                </div>
              </div>
            );
          })
        ) : (
          <p className="text-gray-400 text-center py-4 text-sm">{t('profilePage.noSpools')}</p>
        )}
      </div>
    </div>
  );
};

const HelpSection: React.FC<{ icon: React.ElementType; title: string; children: ReactNode }> = ({ icon: Icon, title, children }) => (
  <div className="bg-white/5 border border-white/10 rounded-xl p-4">
    <div className="flex items-center gap-2 mb-2">
      <Icon className="w-4 h-4 text-purple-400 flex-shrink-0" />
      <h3 className="text-sm font-semibold text-white">{title}</h3>
    </div>
    <div className="text-sm text-gray-300 leading-relaxed">{children}</div>
  </div>
);

interface PresetCardProps {
  preset: Preset;
  onEdit?: (preset: Preset) => void;
  onView?: (preset: Preset) => void;
  onDelete?: (preset: Preset) => void;
}

const PresetCard: React.FC<PresetCardProps> = ({ preset, onEdit, onView, onDelete }) => {
  const { t } = useTranslation();
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
              // Профиль успешно импортирован
            } else if (data.status === 'error') {
              // Показываем ошибку
              alert(`${t('profilePage.importError')}: ${data.message || t('profilePage.unknownError')}`);
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
    queryFn: () => filamentsAPI.get(preset.filament_id!),
    enabled: !!preset.filament_id,
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
      console.error('Error downloading preset:', error);

      let errorMessage = t('profilePage.unknownError');
      if (error.response) {
        const status = error.response.status;
        const data = error.response.data;

        if (status === 401) {
          errorMessage = t('profilePage.errors.authRequired');
        } else if (status === 404) {
          errorMessage = t('profilePage.errors.presetNotFound');
        } else if (status === 500) {
          const detail = data?.detail || t('profilePage.errors.internalError');
          errorMessage = `${t('profilePage.errors.serverExportError')}: ${detail}`;
          console.error('Error 500 details:', detail);
        } else {
          errorMessage = `${t('profilePage.errors.errorCode', { code: status })}: ${data?.detail || data?.message || t('profilePage.errors.requestError')}`;
        }
      } else if (error.request) {
        errorMessage = t('profilePage.errors.connectionError');
      } else {
        errorMessage = error.message || t('profilePage.errors.requestError');
      }

      alert(`${t('profilePage.downloadPresetError')}: ${errorMessage}`);
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
                  {t('profilePage.fromCatalog')}
                </span>
              )}
              {!preset.active && preset.source === 'own' && !preset.name?.includes('@FilamentHub') && (
                <span className="px-2 py-0.5 bg-orange-600/30 rounded text-orange-300 text-xs font-medium whitespace-nowrap">
                  {t('profilePage.draft')}
                </span>
              )}
              {preset.is_weighted && (
                <span className="px-2 py-0.5 bg-green-600/30 rounded text-green-300 text-xs font-medium whitespace-nowrap">
                  {t('profilePage.generative')}
                </span>
              )}
            </div>
          {filament && (
            <div className="mt-1 cursor-pointer hover:opacity-80 transition-opacity" onClick={() => navigate(`/filaments/${filament.id}`, { state: { from: 'profile' } })}>
              <div className="min-w-0 space-y-1">
                {brand && (
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      className={`text-sm font-medium ${brand.verified ? 'text-green-400' : 'text-gray-300'} truncate max-w-[45%]`}
                      title={brand.name}
                    >
                      {brand.name}
                    </span>
                    <span className="text-gray-500 flex-shrink-0">•</span>
                    <span className="text-gray-400 text-sm truncate flex-1 min-w-0" title={filament.name}>
                      {filament.name}
                    </span>
                  </div>
                )}
                {!brand && (
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-gray-400 text-sm truncate flex-1 min-w-0" title={filament.name}>
                      {filament.name}
                    </span>
                  </div>
                )}
                <div className="flex items-center gap-2 flex-wrap">
                  {filament.color_name && (
                    <span className="text-gray-400 text-sm truncate max-w-full" title={filament.color_name}>
                      {filament.color_name}
                    </span>
                  )}
                  <span className="px-2 py-0.5 bg-purple-600/30 rounded text-purple-300 text-xs font-medium flex-shrink-0">
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
              title={t('profilePage.edit')}
            >
              <Edit className="w-4 h-4" />
            </button>
          ) : (
            <button
              onClick={() => onView?.(preset)}
              className="p-2 bg-white/10 hover:bg-white/20 rounded-lg text-white transition-all"
              title={t('profilePage.viewPreset')}
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
            title={isDownloading ? t('profilePage.downloading') : t('profilePage.downloadOrcaSlicer')}
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
            title={preset.source === 'saved' ? t('profilePage.removeFromProfile') : t('profilePage.delete')}
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 mb-4 text-sm">
        <div className="flex items-start space-x-2 min-w-0">
          <Thermometer className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
          <span className="text-gray-300 leading-tight break-words">{t('profilePage.preset.nozzle')}: {preset.extruder_temp}°C</span>
        </div>
        <div className="flex items-start space-x-2 min-w-0">
          <Thermometer className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
          <span className="text-gray-300 leading-tight break-words">{t('profilePage.preset.bed')}: {preset.bed_temp}°C</span>
        </div>
        <div className="flex items-start space-x-2 min-w-0">
          <Gauge className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
          <span className="text-gray-300 leading-tight break-words">{t('profilePage.preset.speed')}: {preset.print_speed}mm/s</span>
        </div>
        {preset.travel_speed && (
          <div className="flex items-start space-x-2 min-w-0">
            <MoveHorizontal className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
            <span className="text-gray-300 leading-tight break-words">{t('profilePage.preset.travel')}: {preset.travel_speed}mm/s</span>
          </div>
        )}
        {preset.flow_rate && (
          <div className="flex items-start space-x-2 min-w-0">
            <Gauge className="w-4 h-4 text-yellow-400 shrink-0 mt-0.5" />
            <span className="text-gray-300 leading-tight break-words">{t('profilePage.preset.flow')}: {preset.flow_rate}%</span>
          </div>
        )}
        {preset.fan_speed !== null && (
          <div className="flex items-start space-x-2 min-w-0">
            <Fan className="w-4 h-4 text-orange-400 shrink-0 mt-0.5" />
            <span className="text-gray-300 leading-tight break-words">{t('profilePage.preset.fan')}: {preset.fan_speed}%</span>
          </div>
        )}
        {preset.retraction_length && (
          <div className="flex items-start space-x-2 min-w-0">
            <Wind className="w-4 h-4 text-purple-400 shrink-0 mt-0.5" />
            <span className="text-gray-300 leading-tight break-words">{t('profilePage.preset.retract')}: {preset.retraction_length}mm</span>
          </div>
        )}
        {preset.retraction_speed && (
          <div className="flex items-start space-x-2 min-w-0">
            <Gauge className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
            <span className="text-gray-300 leading-tight break-words">{t('profilePage.preset.retractSpeed')}: {preset.retraction_speed}mm/s</span>
          </div>
        )}
        <div className="flex items-start space-x-2 min-w-0">
          <CheckCircle className="w-4 h-4 text-green-400 shrink-0 mt-0.5" />
          <span className="text-gray-300 leading-tight break-words">{t('profilePage.preset.usageCount')}: {preset.usage_count}</span>
        </div>
      </div>

      <div className="flex items-center justify-between text-xs sm:text-sm gap-3">
        {preset.rating ? (
          <div className="flex items-center space-x-1">
            <Star className="w-4 h-4 text-yellow-400 fill-current" />
            <span className="text-white">{preset.rating.toFixed(1)}</span>
          </div>
        ) : (
          <span />
        )}
        <div className="ml-auto flex items-center gap-3 whitespace-nowrap">
          <span className="text-gray-400">
            {t('profilePage.created')}: {new Date(preset.created_at).toLocaleDateString()}
          </span>
          {preset.created_at !== preset.updated_at && (
            <span className="text-blue-400">
              {t('profilePage.modified')}: {new Date(preset.updated_at).toLocaleDateString()}
            </span>
          )}
        </div>
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
  const { t } = useTranslation();
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
        <label className="block text-gray-300 mb-4 text-sm font-medium">{t('profilePage.calc.pricingMethod')}</label>
        <div className="flex flex-wrap gap-3">
          {[
            { value: 'by_weight', label: t('profilePage.calc.byWeight') },
            { value: 'by_time', label: t('profilePage.calc.byTime') },
            { value: 'combined', label: t('profilePage.calc.combined') },
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
            {t('profilePage.calc.materialParams')}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.partWeight')}</label>
              <input
                type="number"
                value={weightG}
                onChange={(e) => setWeightG(Number(e.target.value) || 0)}
                className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                placeholder="531"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.supportsWeight')}</label>
              <input
                type="number"
                value={supportsWeightG}
                onChange={(e) => setSupportsWeightG(Number(e.target.value) || 0)}
                className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                placeholder="0"
              />
              <p className="text-xs text-gray-400 mt-1">{t('profilePage.calc.supportsWeightHint')}</p>
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.supportsLossCoeff')}</label>
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
              <p className="text-xs text-gray-400 mt-1">{t('profilePage.calc.supportsLossHint')}</p>
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.spoolPrice')}</label>
              <input
                type="number"
                value={spoolPrice}
                onChange={(e) => setSpoolPrice(Number(e.target.value) || 0)}
                className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                placeholder="1200"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.spoolWeight')}</label>
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
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.deliveryCost')}</label>
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
            {t('profilePage.calc.printTime')}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.hours')}</label>
              <input
                type="number"
                value={timeHours}
                onChange={(e) => setTimeHours(Number(e.target.value) || 0)}
                className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                placeholder="13"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.minutes')}</label>
              <input
                type="number"
                value={timeMinutes}
                onChange={(e) => setTimeMinutes(Number(e.target.value) || 0)}
                className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                placeholder="40"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.seconds')}</label>
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
          <h3 className="text-xl font-bold text-white mb-4">{t('profilePage.calc.hourlyRate')}</h3>
          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.pricePerHour')}</label>
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
          {t('profilePage.calc.electricity')}
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.electricityCost')}</label>
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
            <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.printerPower')}</label>
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
              {t('profilePage.calc.additionalServices')}
            </h3>
            <div className="space-y-4">
              {/* Моделирование */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.modelingHours')}</label>
                  <input
                    type="number"
                    value={modelingHours}
                    onChange={(e) => setModelingHours(Number(e.target.value) || 0)}
                    className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    placeholder="0"
                  />
                </div>
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.modelingMinutes')}</label>
                  <input
                    type="number"
                    value={modelingMinutes}
                    onChange={(e) => setModelingMinutes(Number(e.target.value) || 0)}
                    className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    placeholder="0"
                  />
                </div>
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.rate')}</label>
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
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.printingRate')}</label>
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
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.postprocessingHours')}</label>
                  <input
                    type="number"
                    value={postprocessingHours}
                    onChange={(e) => setPostprocessingHours(Number(e.target.value) || 0)}
                    className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    placeholder="0"
                  />
                </div>
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.postprocessingMinutes')}</label>
                  <input
                    type="number"
                    value={postprocessingMinutes}
                    onChange={(e) => setPostprocessingMinutes(Number(e.target.value) || 0)}
                    className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    placeholder="2"
                  />
                </div>
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.rate')}</label>
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
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.amortizationRate')}</label>
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
            {t('profilePage.calc.overheadAndMarkup')}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.overheadPercent')}</label>
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
              <p className="text-xs text-gray-400 mt-1">{t('profilePage.calc.overheadHint')}</p>
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.markupPercent')}</label>
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
              <p className="text-xs text-gray-400 mt-1">{t('profilePage.calc.markupHint')}</p>
            </div>
          </div>
        </div>
      )}

      {/* Коэффициенты корректировки (только для combined) */}
      {pricingMethod === 'combined' && (
        <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
          <h3 className="text-xl font-bold text-white mb-4 flex items-center">
            <Settings className="w-5 h-5 mr-2" />
            {t('profilePage.calc.adjustmentCoeffs')}
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.urgency')}</label>
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
              <p className="text-xs text-gray-400 mt-1">{t('profilePage.calc.urgencyHint')}</p>
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.complexity')}</label>
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
              <p className="text-xs text-gray-400 mt-1">{t('profilePage.calc.complexityHint')}</p>
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.volumeDiscount')}</label>
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
              <p className="text-xs text-gray-400 mt-1">{t('profilePage.calc.volumeDiscountHint')}</p>
            </div>
          </div>
        </div>
      )}

      {/* Количество, фиксированные расходы и округление */}
      <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.quantity')}</label>
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
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.fixedCosts')}</label>
                <input
                  type="number"
                  value={fixedCosts}
                  onChange={(e) => setFixedCosts(Number(e.target.value) || 0)}
                  className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="0"
                />
                <p className="text-xs text-gray-400 mt-1">{t('profilePage.calc.fixedCostsHint')}</p>
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.minOrderPrice')}</label>
                <input
                  type="number"
                  value={minOrderPrice}
                  onChange={(e) => setMinOrderPrice(Number(e.target.value) || 0)}
                  className="w-full px-4 py-2 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  placeholder="0"
                />
                <p className="text-xs text-gray-400 mt-1">{t('profilePage.calc.minOrderPriceHint')}</p>
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('profilePage.calc.roundTo')}</label>
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
              <span>{t('profilePage.calc.calculating')}</span>
            </>
          ) : (
            <>
              <Calculator className="w-5 h-5" />
              <span>{t('profilePage.calc.calculate')}</span>
            </>
          )}
        </button>
      </div>

      {/* Результаты */}
      {result && (
        <div className="space-y-4">
          {/* Компоненты стоимости */}
          <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
            <h3 className="text-xl font-bold text-white mb-4">{t('profilePage.calc.costComponents')}</h3>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
              {result.cost_material > 0 && (
                <ResultCard
                  label={t('profilePage.calc.material')}
                  value={result.cost_material.toFixed(2)}
                  icon={Package}
                  color="from-purple-500/20 to-pink-500/20"
                  borderColor="border-purple-500/30"
                />
              )}
              {result.cost_electricity > 0 && (
                <ResultCard
                  label={t('profilePage.calc.electricityLabel')}
                  value={result.cost_electricity.toFixed(2)}
                  icon={Wind}
                  color="from-blue-500/20 to-cyan-500/20"
                  borderColor="border-blue-500/30"
                />
              )}
              {result.cost_modeling > 0 && (
                <ResultCard
                  label={t('profilePage.calc.modeling')}
                  value={result.cost_modeling.toFixed(2)}
                  icon={Settings}
                  color="from-orange-500/20 to-red-500/20"
                  borderColor="border-orange-500/30"
                />
              )}
              {result.cost_printing > 0 && (
                <ResultCard
                  label={t('profilePage.calc.printing')}
                  value={result.cost_printing.toFixed(2)}
                  icon={Printer3DIcon}
                  color="from-indigo-500/20 to-purple-500/20"
                  borderColor="border-indigo-500/30"
                />
              )}
              {result.cost_postprocessing > 0 && (
                <ResultCard
                  label={t('profilePage.calc.postprocessing')}
                  value={result.cost_postprocessing.toFixed(2)}
                  icon={Fan}
                  color="from-teal-500/20 to-green-500/20"
                  borderColor="border-teal-500/30"
                />
              )}
              {result.cost_amortization > 0 && (
                <ResultCard
                  label={t('profilePage.calc.amortization')}
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
              <h3 className="text-xl font-bold text-white mb-4">{t('profilePage.calc.intermediateCalcs')}</h3>
              <div className="space-y-3">
                <div className="flex justify-between items-center py-2 border-b border-white/10">
                  <span className="text-gray-300">{t('profilePage.calc.directCosts')}</span>
                  <span className="text-white font-semibold">{result.cost_direct.toFixed(2)} ₽</span>
                </div>
                {result.cost_overhead > 0 && (
                  <div className="flex justify-between items-center py-2 border-b border-white/10">
                    <span className="text-gray-300">{t('profilePage.calc.overhead')}</span>
                    <span className="text-white font-semibold">{result.cost_overhead.toFixed(2)} ₽</span>
                  </div>
                )}
                <div className="flex justify-between items-center py-2 border-b border-white/10">
                  <span className="text-gray-300">{t('profilePage.calc.costBeforeMarkup')}</span>
                  <span className="text-white font-semibold">{result.cost_before_markup.toFixed(2)} ₽</span>
                </div>
                {result.cost_markup > 0 && (
                  <div className="flex justify-between items-center py-2 border-b border-white/10">
                    <span className="text-gray-300">{t('profilePage.calc.markup')}</span>
                    <span className="text-white font-semibold">{result.cost_markup.toFixed(2)} ₽</span>
                  </div>
                )}
                {(result.applied_urgency_coefficient || result.applied_complexity_coefficient || result.applied_volume_discount) && (
                  <div className="pt-2 space-y-1">
                    <p className="text-sm text-gray-400">{t('profilePage.calc.appliedCoeffs')}:</p>
                    {result.applied_urgency_coefficient && result.applied_urgency_coefficient !== 1.0 && (
                      <div className="flex justify-between items-center text-sm">
                        <span className="text-gray-300">{t('profilePage.calc.urgency')}</span>
                        <span className="text-white">×{result.applied_urgency_coefficient.toFixed(2)}</span>
                      </div>
                    )}
                    {result.applied_complexity_coefficient && result.applied_complexity_coefficient !== 1.0 && (
                      <div className="flex justify-between items-center text-sm">
                        <span className="text-gray-300">{t('profilePage.calc.complexity')}</span>
                        <span className="text-white">×{result.applied_complexity_coefficient.toFixed(2)}</span>
                      </div>
                    )}
                    {result.applied_volume_discount && result.applied_volume_discount !== 1.0 && (
                      <div className="flex justify-between items-center text-sm">
                        <span className="text-gray-300">{t('profilePage.calc.volumeDiscount')}</span>
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
                {t('profilePage.calc.financialMetrics')}
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {result.cost_of_goods_sold !== undefined && result.cost_of_goods_sold !== null && (
                  <div className="bg-white/5 rounded-xl p-4 border border-white/10">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-gray-300 text-sm">{t('profilePage.calc.costOfGoods')}</span>
                      <DollarSign className="w-4 h-4 text-gray-400" />
                    </div>
                    <div className="text-2xl font-bold text-white">{result.cost_of_goods_sold.toFixed(2)} ₽</div>
                    <p className="text-xs text-gray-400 mt-1">{t('profilePage.calc.costOfGoodsHint')}</p>
                  </div>
                )}
                {result.profit_margin !== undefined && result.profit_margin !== null && (
                  <div className="bg-green-500/10 rounded-xl p-4 border border-green-500/30">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-green-300 text-sm">{t('profilePage.calc.profitMargin')}</span>
                      <TrendingUp className="w-4 h-4 text-green-400" />
                    </div>
                    <div className="text-2xl font-bold text-green-400">
                      {result.profit_margin.toFixed(2)} ₽
                      {result.profit_margin_percent !== undefined && result.profit_margin_percent !== null && (
                        <span className="text-lg ml-2">({result.profit_margin_percent.toFixed(1)}%)</span>
                      )}
                    </div>
                    <p className="text-xs text-green-200 mt-1">{t('profilePage.calc.profitMarginHint')}</p>
                  </div>
                )}
                {result.total_time_hours && (
                  <div className="bg-blue-500/10 rounded-xl p-4 border border-blue-500/30 md:col-span-2">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-blue-300 text-sm">{t('profilePage.calc.totalWorkTime')}</span>
                      <Clock className="w-4 h-4 text-blue-400" />
                    </div>
                    <div className="text-2xl font-bold text-blue-400">
                      {result.total_time_hours.toFixed(2)} {t('profilePage.calc.h')}
                      {result.total_time_hours >= 1 && (
                        <span className="text-lg ml-2">
                          ({Math.floor(result.total_time_hours)} {t('profilePage.calc.h')} {Math.round((result.total_time_hours % 1) * 60)} {t('profilePage.calc.min')})
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-blue-200 mt-1">{t('profilePage.calc.totalWorkTimeHint')}</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Итоговые суммы */}
          <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
            <h3 className="text-xl font-bold text-white mb-4">{t('profilePage.calc.totalSums')}</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {result.quantity > 1 && (
                <>
                  <ResultCard
                    label={t('profilePage.calc.firstPartPrice')}
                    value={result.cost_first_part.toFixed(2)}
                    icon={Star}
                    color="from-yellow-500/20 to-orange-500/20"
                    borderColor="border-yellow-500/30"
                  />
                  <ResultCard
                    label={t('profilePage.calc.subsequentPrice')}
                    value={result.cost_subsequent_parts.toFixed(2)}
                    icon={Package}
                    color="from-blue-500/20 to-indigo-500/20"
                    borderColor="border-blue-500/30"
                  />
                </>
              )}
              <ResultCard
                label={result.quantity > 1 ? t('profilePage.calc.totalCost') : t('profilePage.calc.total')}
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
            {t('profilePage.calc.error')}: {calculateMutation.error instanceof Error ? calculateMutation.error.message : t('profilePage.calc.unknownError')}
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

const ProfileSectionLoader: React.FC = () => {
  const { t } = useTranslation();
  return (
  <div className="flex items-center justify-center gap-3 py-12 text-gray-300">
    <Loader2 className="w-5 h-5 animate-spin" />
    <span>{t('profilePage.loadingProfiles')}</span>
  </div>
  );
};

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
  printProfiles?: PrintProfile[];
  isExpanded?: boolean;
  onExpand?: () => void;
  formatDateTime: (value: string) => string;
  onView: (profile: PrinterProfile) => void;
  onDownload: (profile: PrinterProfile) => void;
  onViewPrintProfile?: (profile: PrintProfile) => void;
  onDownloadPrintProfile?: (profile: PrintProfile) => void;
  onCreatePrintProfile?: () => void;
  printProfileNameBySlug?: Map<string, string>;
}

const PrinterProfileCard: React.FC<PrinterProfileCardProps> = ({
  profile,
  printProfiles = [],
  isExpanded = false,
  onExpand,
  formatDateTime,
  onView,
  onDownload,
  onViewPrintProfile,
  onDownloadPrintProfile,
  onCreatePrintProfile,
  printProfileNameBySlug,
}) => {
  const { t } = useTranslation();
  const printProfilesCount = printProfiles.length;
  
  return (
  <div className="bg-white/10 backdrop-blur-sm border border-white/15 rounded-2xl p-6 shadow-xl">
    <div className="flex items-start justify-between gap-3">
      <div>
        <h3 className="text-xl font-semibold text-white">{profile.name}</h3>
        <p className="text-sm text-gray-400">Slug: {profile.slug}</p>
        {profile.printer_slug && (
          <p className="text-xs text-gray-400 mt-1">{t('profilePage.printer')}: {profile.printer_name ?? profile.printer_slug}</p>
        )}
      </div>
      <div className="flex flex-wrap gap-2 justify-end">
        <StatusBadge label={profile.active ? t('profilePage.badge.active') : t('profilePage.badge.disabled')} variant={profile.active ? 'success' : 'muted'} />
        {profile.is_official && <StatusBadge label={t('profilePage.badge.official')} variant="accent" />}
        {printProfilesCount > 0 && (
          <StatusBadge label={t('profilePage.printProfilesCount', { count: printProfilesCount })} variant="accent" />
        )}
      </div>
    </div>
    {profile.description && (
      <p className="mt-3 text-sm text-gray-300 line-clamp-3">{profile.description}</p>
    )}
    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <InfoRow label={t('profilePage.printerBinding')} value={profile.printer_id ? `ID ${profile.printer_id}` : t('profilePage.notSpecifiedF')} />
      <InfoRow label={t('profilePage.updated')} value={formatDateTime(profile.updated_at)} />
      <InfoRow
        label={t('profilePage.defaultPrintProfile')}
        value={profile.default_print_profile_slug
          ? (printProfileNameBySlug?.get(profile.default_print_profile_slug) || profile.default_print_profile_slug)
          : t('profilePage.notSetM')}
      />
      <InfoRow
        label={t('profilePage.nozzleDiameters')}
        value={profile.nozzle_diameters && profile.nozzle_diameters.length > 0 ? profile.nozzle_diameters.join(', ') : t('profilePage.notSpecifiedPl')}
      />
      <InfoRow
        label={t('profilePage.printHeight')}
        value={
          typeof profile.printable_height_mm === 'number' ? `${profile.printable_height_mm.toFixed(0)} ${t('profilePage.mm')}` : t('profilePage.notSpecifiedF')}
      />
      <InfoRow label={t('profilePage.startGcode')} value={profile.start_gcode ? t('profilePage.set') : '—'} />
      <InfoRow label={t('profilePage.endGcode')} value={profile.end_gcode ? t('profilePage.set') : '—'} />
    </div>
    
    {/* Профили печати для этого принтера */}
    {printProfilesCount > 0 && onExpand && (
      <div className="mt-4 pt-4 border-t border-white/10">
        <button
          type="button"
          onClick={onExpand}
          className="w-full flex items-center justify-between px-4 py-2 rounded-lg border border-white/20 text-sm text-white/90 hover:bg-white/10 transition-all"
        >
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4" />
            <span>{t('profilePage.printProfilesLabel')} ({printProfilesCount})</span>
          </div>
          {isExpanded ? (
            <ChevronUp className="w-4 h-4" />
          ) : (
            <ChevronDown className="w-4 h-4" />
          )}
        </button>
        
        {isExpanded && (
          <div className="mt-4 space-y-3">
            {printProfiles.map((printProfile) => (
              <div
                key={printProfile.id}
                className="bg-white/5 rounded-lg p-4 border border-white/10"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1">
                    <h4 className="text-sm font-semibold text-white">{printProfile.name}</h4>
                    {printProfile.quality_tier && (
                      <p className="text-xs text-gray-400 mt-1">{t('profilePage.quality')}: {printProfile.quality_tier}</p>
                    )}
                    {printProfile.layer_height_mm && (
                      <p className="text-xs text-gray-400">{t('profilePage.layerHeight')}: {printProfile.layer_height_mm.toFixed(2)} {t('profilePage.mm')}</p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {printProfile.is_official && (
                      <StatusBadge label={t('profilePage.badge.system')} variant="accent" />
                    )}
                    <StatusBadge 
                      label={printProfile.active ? t('profilePage.badge.active') : t('profilePage.badge.disabled')} 
                      variant={printProfile.active ? 'success' : 'muted'}
                    />
                  </div>
                </div>
                {printProfile.description && (
                  <p className="mt-2 text-xs text-gray-300 line-clamp-2">{printProfile.description}</p>
                )}
                <div className="mt-3 flex flex-wrap gap-2">
                  {onViewPrintProfile && (
                    <button
                      type="button"
                      onClick={() => onViewPrintProfile(printProfile)}
                      className="px-3 py-1.5 rounded-lg border border-white/20 text-xs text-white/90 hover:bg-white/10 transition-all flex items-center gap-1.5"
                    >
                      <Eye className="w-3 h-3" />
                      {t('profilePage.view')}
                    </button>
                  )}
                  {onDownloadPrintProfile && (
                    <button
                      type="button"
                      onClick={() => onDownloadPrintProfile(printProfile)}
                      className="px-3 py-1.5 rounded-lg border border-white/20 text-xs text-white/90 hover:bg-white/10 transition-all flex items-center gap-1.5"
                    >
                      <Download className="w-3 h-3" />
                      {t('profilePage.download')}
                    </button>
                  )}
                </div>
              </div>
            ))}
            {onCreatePrintProfile && (
              <button
                type="button"
                onClick={onCreatePrintProfile}
                className="w-full px-4 py-2 rounded-lg border border-dashed border-white/20 text-sm text-gray-400 hover:text-white hover:border-white/40 transition-all flex items-center justify-center gap-2"
              >
                <Plus className="w-4 h-4" />
                {t('profilePage.addPrintProfile')}
              </button>
            )}
          </div>
        )}
      </div>
    )}
    
    {printProfilesCount === 0 && onCreatePrintProfile && (
      <div className="mt-4 pt-4 border-t border-white/10">
        <button
          type="button"
          onClick={onCreatePrintProfile}
          className="w-full px-4 py-2 rounded-lg border border-dashed border-white/20 text-sm text-gray-400 hover:text-white hover:border-white/40 transition-all flex items-center justify-center gap-2"
        >
          <Plus className="w-4 h-4" />
          Добавить профиль печати
        </button>
      </div>
    )}
    
    <div className="mt-4 flex flex-wrap gap-2">
      <button
        type="button"
        onClick={() => onView(profile)}
        className="px-4 py-2 rounded-lg border border-white/20 text-sm text-white/90 hover:bg-white/10 transition-all flex items-center gap-2"
      >
        <Eye className="w-4 h-4" />
        {t('profilePage.viewJson')}
      </button>
      <button
        type="button"
        onClick={() => onDownload(profile)}
        className="px-4 py-2 rounded-lg border border-white/20 text-sm text-white/90 hover:bg-white/10 transition-all flex items-center gap-2"
      >
        <Download className="w-4 h-4" />
        {t('profilePage.downloadJson')}
      </button>
    </div>
  </div>
  );
};

interface PrintProfileCardProps {
  profile: PrintProfile;
  formatDateTime: (value: string) => string;
  onView: (profile: PrintProfile) => void;
  onDownload: (profile: PrintProfile) => void;
}

const PrintProfileCard: React.FC<PrintProfileCardProps> = ({ profile, formatDateTime, onView, onDownload }) => {
  const { t } = useTranslation();
  const printersCount = profile.printer_links?.length ?? 0;
  const filamentsCount = profile.filament_links?.length ?? 0;
  const defaultNozzle = profile.default_nozzle ? `${profile.default_nozzle} ${t('profilePage.mm')}` : t('profilePage.notSpecifiedN');
  const layerHeight =
    typeof profile.layer_height_mm === 'number' ? `${profile.layer_height_mm.toFixed(2)} ${t('profilePage.mm')}` : t('profilePage.notSpecifiedF');

  return (
    <div className="bg-white/10 backdrop-blur-sm border border-white/15 rounded-2xl p-6 shadow-xl">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-xl font-semibold text-white">{profile.name}</h3>
          <p className="text-sm text-gray-400">Slug: {profile.slug}</p>
        </div>
        <div className="flex flex-wrap gap-2 justify-end">
          <StatusBadge label={profile.active ? t('profilePage.badge.active') : t('profilePage.badge.disabled')} variant={profile.active ? 'success' : 'muted'} />
          {profile.is_official && <StatusBadge label={t('profilePage.badge.official')} variant="accent" />}
        </div>
      </div>
      {profile.description && (
        <p className="mt-3 text-sm text-gray-300 line-clamp-3">{profile.description}</p>
      )}
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        <InfoRow label={t('profilePage.category')} value={profile.category || t('profilePage.notSpecifiedF')} />
        <InfoRow label={t('profilePage.quality')} value={profile.quality_tier || t('profilePage.notSpecifiedN')} />
        <InfoRow label={t('profilePage.updated')} value={formatDateTime(profile.updated_at)} />
        <InfoRow label={t('profilePage.defaultNozzle')} value={defaultNozzle} />
        <InfoRow label={t('profilePage.layerHeight')} value={layerHeight} />
        <InfoRow label={t('profilePage.compatiblePrinters')} value={`${printersCount}`} />
        <InfoRow label={t('profilePage.compatibleFilaments')} value={`${filamentsCount}`} />
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => onView(profile)}
          className="px-4 py-2 rounded-lg border border-white/20 text-sm text-white/90 hover:bg-white/10 transition-all flex items-center gap-2"
        >
          <Eye className="w-4 h-4" />
          {t('profilePage.viewJson')}
        </button>
        <button
          type="button"
          onClick={() => onDownload(profile)}
          className="px-4 py-2 rounded-lg border border-white/20 text-sm text-white/90 hover:bg-white/10 transition-all flex items-center gap-2"
        >
          <Download className="w-4 h-4" />
          {t('profilePage.downloadJson')}
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
    superdraft: 'Super Draft',
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
  const { t } = useTranslation();
  const hasActiveFilters =
    !!qualityFilter || !!nozzleFilter || !!printerFilter || onlyOfficial || onlyActive;

  return (
    <div className="bg-white/5 border border-white/10 rounded-2xl p-4 space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-medium uppercase tracking-wide text-gray-300">
          <Filter className="w-4 h-4" />
          {t('profilePage.filters')}
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
          {t('profilePage.reset')}
        </button>
      </div>

      {qualityOptions.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-gray-400 uppercase tracking-wide">{t('profilePage.qualityClass')}</p>
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
          <p className="text-xs text-gray-400 uppercase tracking-wide">{t('profilePage.nozzle')}</p>
          <div className="flex flex-wrap gap-2">
            {nozzleOptions.map(option => (
              <FilterChip
                key={option}
                label={`${option} ${t('profilePage.mm')}`}
                active={nozzleFilter === option}
                onClick={() => onNozzleChange(option)}
              />
            ))}
          </div>
        </div>
      )}

      {printerOptions.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs text-gray-400 uppercase tracking-wide">{t('profilePage.printer')}</p>
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
          label={t('profilePage.officialOnly')}
          active={onlyOfficial}
          onClick={onToggleOfficial}
        />
        <FilterChip label={t('profilePage.activeOnly')} active={onlyActive} onClick={onToggleActive} />
      </div>
    </div>
  );
};

interface PrinterProfileModalProps {
  profile: PrinterProfile;
  onClose: () => void;
  formatDateTime: (value: string) => string;
  printProfileNameBySlug?: Map<string, string>;
}

const PrinterProfileModal: React.FC<PrinterProfileModalProps> = ({ profile, onClose, formatDateTime, printProfileNameBySlug }) => {
  const { t } = useTranslation();
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
            <InfoRow label={t('profilePage.profileId')} value={`#${profile.id}`} />
            <InfoRow label={t('profilePage.printerBinding')} value={profile.printer_id ? `ID ${profile.printer_id}` : t('profilePage.notSpecifiedF')} />
            <InfoRow label={t('profilePage.created')} value={formatDateTime(profile.created_at)} />
            <InfoRow label={t('profilePage.updated')} value={formatDateTime(profile.updated_at)} />
            <InfoRow label={t('profilePage.type')} value={profile.is_official ? t('profilePage.official') : t('profilePage.custom')} />
            <InfoRow label={t('profilePage.status')} value={profile.active ? t('profilePage.badge.active') : t('profilePage.badge.disabled')} />
            <InfoRow label={t('profilePage.source')} value={profile.source || t('profilePage.notSpecifiedM')} />
            <InfoRow label={t('profilePage.vendor')} value={profile.vendor || t('profilePage.notSpecifiedM')} />
            <InfoRow label="Setting ID" value={profile.setting_id || '—'} />
            <InfoRow label="External ID" value={profile.external_id || '—'} />
            <InfoRow
              label={t('profilePage.nozzleDiameters')}
              value={profile.nozzle_diameters && profile.nozzle_diameters.length > 0 ? profile.nozzle_diameters.join(', ') : t('profilePage.notSpecifiedPl')}
            />
            <InfoRow
              label={t('profilePage.printHeight')}
              value={
                typeof profile.printable_height_mm === 'number' ? `${profile.printable_height_mm.toFixed(0)} ${t('profilePage.mm')}` : t('profilePage.notSpecifiedF')}
            />
            <InfoRow
        label={t('profilePage.defaultPrintProfile')}
        value={profile.default_print_profile_slug
          ? (printProfileNameBySlug?.get(profile.default_print_profile_slug) || profile.default_print_profile_slug)
          : t('profilePage.notSetM')}
      />
          </div>
          {profile.description && (
            <div>
              <h4 className="text-sm font-semibold text-white mb-2">{t('profilePage.description')}</h4>
              <p className="text-sm text-gray-200 whitespace-pre-wrap">{profile.description}</p>
            </div>
          )}
          {profile.notes && (
            <div>
              <h4 className="text-sm font-semibold text-white mb-2">{t('profilePage.notes')}</h4>
              <p className="text-sm text-gray-200 whitespace-pre-wrap">{profile.notes}</p>
            </div>
          )}
          {profile.start_gcode && (
            <div>
              <h4 className="text-sm font-semibold text-white mb-2">{t('profilePage.startGcode')}</h4>
              <pre className="bg-black/40 border border-white/10 rounded-xl p-4 text-xs text-gray-200 overflow-auto max-h-60 whitespace-pre-wrap">
                {profile.start_gcode}
              </pre>
            </div>
          )}
          {profile.end_gcode && (
            <div>
              <h4 className="text-sm font-semibold text-white mb-2">{t('profilePage.endGcode')}</h4>
              <pre className="bg-black/40 border border-white/10 rounded-xl p-4 text-xs text-gray-200 overflow-auto max-h-60 whitespace-pre-wrap">
                {profile.end_gcode}
              </pre>
            </div>
          )}
          <div>
            <h4 className="text-sm font-semibold text-white mb-2">{t('profilePage.orcaSlicerSettings')}</h4>
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
  const { t } = useTranslation();
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
  const defaultNozzle = profile.default_nozzle ? `${profile.default_nozzle} ${t('profilePage.mm')}` : t('profilePage.notSpecifiedN');
  const layerHeight =
    typeof profile.layer_height_mm === 'number' ? `${profile.layer_height_mm.toFixed(2)} ${t('profilePage.mm')}` : t('profilePage.notSpecifiedF');

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
            <InfoRow label={t('profilePage.profileId')} value={`#${profile.id}`} />
            <InfoRow label={t('profilePage.created')} value={formatDateTime(profile.created_at)} />
            <InfoRow label={t('profilePage.updated')} value={formatDateTime(profile.updated_at)} />
            <InfoRow label={t('profilePage.category')} value={profile.category || t('profilePage.notSpecifiedF')} />
            <InfoRow label={t('profilePage.type')} value={profile.is_official ? t('profilePage.official') : t('profilePage.custom')} />
            <InfoRow label={t('profilePage.status')} value={profile.active ? t('profilePage.badge.active') : t('profilePage.badge.disabled')} />
            <InfoRow label={t('profilePage.source')} value={profile.source || t('profilePage.notSpecifiedM')} />
            <InfoRow label={t('profilePage.vendor')} value={profile.vendor || t('profilePage.notSpecifiedM')} />
            <InfoRow label="Setting ID" value={profile.setting_id || '—'} />
            <InfoRow label="External ID" value={profile.external_id || '—'} />
            <InfoRow label={t('profilePage.qualityClass')} value={profile.quality_tier || '—'} />
            <InfoRow label={t('profilePage.defaultNozzle')} value={defaultNozzle} />
            <InfoRow label={t('profilePage.layerHeight')} value={layerHeight} />
          </div>
          {profile.description && (
            <div>
              <h4 className="text-sm font-semibold text-white mb-2">{t('profilePage.description')}</h4>
              <p className="text-sm text-gray-200 whitespace-pre-wrap">{profile.description}</p>
            </div>
          )}
          {profile.notes && (
            <div>
              <h4 className="text-sm font-semibold text-white mb-2">{t('profilePage.notes')}</h4>
              <p className="text-sm text-gray-200 whitespace-pre-wrap">{profile.notes}</p>
            </div>
          )}
          {printersList.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-white mb-2">{t('profilePage.compatiblePrinters')}</h4>
              <div className="flex flex-wrap gap-2">
                {printersList.map((item) => (
                  <span
                    key={`${item.printer_slug}-${item.relation_type}-${item.condition ?? 'explicit'}`}
                    className="px-2 py-1 bg-white/10 border border-white/15 rounded-lg text-xs text-gray-100"
                  >
                    {item.printer_slug}
                    {item.relation_type === 'condition' && item.condition ? ` (${t('profilePage.condition')}: ${item.condition})` : null}
                  </span>
                ))}
              </div>
            </div>
          )}
          {filamentsList.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-white mb-2">{t('profilePage.compatibleFilaments')}</h4>
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
            <h4 className="text-sm font-semibold text-white mb-2">{t('profilePage.orcaSlicerSettings')}</h4>
            <pre className="bg-black/40 border border-white/10 rounded-xl p-4 text-xs text-gray-200 overflow-auto max-h-72 whitespace-pre">
              {JSON.stringify(profile.orcaslicer_settings ?? {}, null, 2)}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
};
