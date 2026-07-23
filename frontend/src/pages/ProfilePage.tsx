/** Страница профиля пользователя */

import { lazy, Suspense, useState, useMemo, useEffect, useRef, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  User,
  Package,
  Settings,
  Calculator,
  Play,
  Star,
  XCircle,
  Plus,
  Download,
  Trash2,
  Thermometer,
  Gauge,
  Edit,
  Wind,
  Fan,
  Factory,
  Loader2,
  Eye,
  Clock,
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
  BriefcaseBusiness,
  FileText,
  UsersRound,
} from 'lucide-react';
import { Printer3DIcon } from '../components/icons/Printer3DIcon';
import { useAuth } from '../contexts/AuthContext';
import { useHeaderVisible } from '../hooks/useHeaderVisible';
import { presetsAPI, filamentsAPI, brandsAPI, savedPresetsAPI, filamentReviewsAPI, printerProfilesAPI, printProfilesAPI, authAPI, spoolsAPI, qrAPI, devicesAPI, presetSlotsAPI, printersAPI, calculatorAPI, crmAPI } from '../api/client';
import { extractQrShortCode, createQrFrameDecoder } from '../utils/qrScanner';
import type { UserSpool, SpoolState, UserPrinterDevice } from '../api/client';
import { SpoolIcon } from '../components/icons/SpoolIcon';
import api from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { getSpoolCurrentLocation, getSpoolLastLocation } from '../utils/spoolLocation';
import { getDeviceLinkState, useNow } from '../utils/deviceLink';
import { notifyProfileChanged } from '../utils/pluginBridge';
import { downloadBlob } from '../utils/download';
const CreatePresetModal = lazy(() =>
  import('../components/CreatePresetModal').then(m => ({ default: m.CreatePresetModal }))
);
import { ViewPresetModal } from '../components/ViewPresetModal';
import { ModalOverlay } from '../components/ModalOverlay';
import { ConfirmModal } from '../components/ConfirmModal';
import { ConfirmDeleteModal } from '../components/ConfirmDeleteModal';
import { toast } from '../components/Toast';
import { OrcaSettingsView } from '../components/OrcaSettingsView';
import { CreatePrinterRequestModal } from '../components/CreatePrinterRequestModal';
import { SettingsTab } from '../components/SettingsTab';
import { ExportFromOrcaSlicerButton } from '../components/ExportFromOrcaSlicerButton';
import { ExportPrinterProfilesButton } from '../components/ExportPrinterProfilesButton';
import { MyPrintersList } from '../components/MyPrintersList';
const CreatePrinterProfileModal = lazy(() =>
  import('../components/CreatePrinterProfileModal').then(m => ({ default: m.CreatePrinterProfileModal }))
);
import { CreatePrintProfileModal } from '../components/CreatePrintProfileModal';
import { PresetSyncToggle } from '../components/PresetSyncToggle';
import { Badge, BADGE_CONFIG, type BadgeType } from '../components/Badge';
import { PresetSlotsPanel } from '../components/presetSlots/PresetSlotsPanel';
import { BrandProfilePage } from './BrandProfilePage';
import { CalculatorPage } from './CalculatorPage';
import { CrmWorkspacePage } from './CrmWorkspacePage';
import type { Preset, PrinterProfile, PrintProfile, Filament } from '../types/api';

type CalculatorWorkspaceMode = 'calculator' | 'history' | 'quotes' | 'orders' | 'customers';

export const ProfilePage: React.FC = () => {
  const { user, refreshUser } = useAuth();
  const queryClient = useQueryClient();
  const { t } = useTranslation();
  const isHeaderVisible = useHeaderVisible();
  const [isUploadingAvatar, setIsUploadingAvatar] = useState(false);
  const handleAvatarUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setIsUploadingAvatar(true);
    try {
      await authAPI.uploadAvatar(file);
      await refreshUser();
    } catch {
      // ошибка загрузки — оставляем прежний аватар
    } finally {
      setIsUploadingAvatar(false);
    }
  };
  const location = useLocation();
  const navigate = useNavigate();
  const profileSearchParams = useMemo(
    () => new URLSearchParams(location.search),
    [location.search],
  );
  const spoolIntakeFilamentId = useMemo(() => {
    const rawId = profileSearchParams.get('filament_id');
    if (profileSearchParams.get('add_spool') !== '1' || !rawId) {
      return null;
    }
    const parsed = Number(rawId);
    return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
  }, [profileSearchParams]);
  const spoolIntakeSource = profileSearchParams.get('source') === 'qr' ? 'qr' : 'manual';
  const [showBrandCabinet, setShowBrandCabinet] = useState<boolean>(
    () => Boolean((location.state as { brandCabinet?: boolean } | null)?.brandCabinet),
  ); // Показывать ли кабинет производителя
  const [isAddBrandFlowActive, setIsAddBrandFlowActive] = useState(false);
  const [userTab, setUserTab] = useState<'dashboard' | 'presets' | 'spools' | 'calculator-pro' | 'settings' | 'printer-profiles'>(() => {
    // Deep-link на конкретную вкладку: navigate('/profile', { state: { tab } })
    const requested = profileSearchParams.get('tab')
      ?? (location.state as { tab?: string } | null)?.tab;
    const valid = ['dashboard', 'presets', 'spools', 'calculator-pro', 'settings', 'printer-profiles'];
    return valid.includes(requested ?? '')
      ? (requested as 'dashboard' | 'presets' | 'spools' | 'calculator-pro' | 'settings' | 'printer-profiles')
      : 'dashboard';
  });
  const [calculatorWorkspaceMode, setCalculatorWorkspaceMode] = useState<CalculatorWorkspaceMode>('calculator');
  const [calculatorEconomicsOpen, setCalculatorEconomicsOpen] = useState(false);
  const [calculatorQuoteProfileOpen, setCalculatorQuoteProfileOpen] = useState(false);
  const [isAddSpoolOpen, setIsAddSpoolOpen] = useState(
    () => profileSearchParams.get('add_spool') === '1' && spoolIntakeFilamentId !== null,
  );
  const [showHelpModal, setShowHelpModal] = useState(false);
  const [isCreatePresetModalOpen, setIsCreatePresetModalOpen] = useState(false);
  const [isViewPresetModalOpen, setIsViewPresetModalOpen] = useState(false);
  const [isCreatePrinterRequestModalOpen, setIsCreatePrinterRequestModalOpen] = useState(false);
  const [editingPreset, setEditingPreset] = useState<Preset | null>(null);
  const [viewingPreset, setViewingPreset] = useState<Preset | null>(null);
  const [deletingPreset, setDeletingPreset] = useState<Preset | null>(null);
  const [selectedPrinterProfile, setSelectedPrinterProfile] = useState<PrinterProfile | null>(null);
  const [selectedPrintProfile, setSelectedPrintProfile] = useState<PrintProfile | null>(null);
  const [expandedPrinterProfileId, setExpandedPrinterProfileId] = useState<number | null>(null); // ID профиля принтера, для которого показываем профили печати
  const [isCreatePrinterProfileModalOpen, setIsCreatePrinterProfileModalOpen] = useState(false);
  const [isCreatePrintProfileModalOpen, setIsCreatePrintProfileModalOpen] = useState(false);
  const [editingPrinterProfile, setEditingPrinterProfile] = useState<PrinterProfile | null>(null);
  const [editingPrintProfile, setEditingPrintProfile] = useState<PrintProfile | null>(null);
  const [createPrintProfileContext, setCreatePrintProfileContext] = useState<PrinterProfile | null>(null);
  const [_viewMode, _setViewMode] = useState<'grid' | 'list'>('grid');
  const [presetFilter, setPresetFilter] = useState<'all' | 'own' | 'saved' | 'drafts'>('all');
  const [isScanning, setIsScanning] = useState(false);

  useEffect(() => {
    const requestedTab = profileSearchParams.get('tab');
    if (requestedTab === 'spools') {
      setUserTab('spools');
    }
    if (profileSearchParams.get('add_spool') === '1' && spoolIntakeFilamentId !== null) {
      setIsAddSpoolOpen(true);
    }
  }, [profileSearchParams, spoolIntakeFilamentId]);

  const setAddSpoolOpen = (open: boolean) => {
    setIsAddSpoolOpen(open);
    if (open || profileSearchParams.get('add_spool') !== '1') {
      return;
    }
    const nextParams = new URLSearchParams(profileSearchParams);
    nextParams.delete('add_spool');
    nextParams.delete('filament_id');
    nextParams.delete('source');
    const nextSearch = nextParams.toString();
    navigate(`${location.pathname}${nextSearch ? `?${nextSearch}` : ''}`, { replace: true });
  };
  const workspaceHistoryQuery = useQuery({
    queryKey: ['calculator-pro', 'history'],
    queryFn: () => calculatorAPI.listHistory({ page: 1, size: 50 }),
    enabled: userTab === 'calculator-pro' && (user?.has_calculator_access ?? false),
  });
  const workspaceSummaryQuery = useQuery({
    queryKey: ['crm', 'summary'],
    queryFn: crmAPI.getSummary,
    enabled: userTab === 'calculator-pro' && (user?.has_calculator_access ?? false),
  });
  const profileBadges = useMemo(() => {
    const validBadgeTypes = new Set<BadgeType>(Object.keys(BADGE_CONFIG) as BadgeType[]);
    return (user?.badges ?? []).filter((badge): badge is BadgeType => validBadgeTypes.has(badge as BadgeType));
  }, [user?.badges]);
  const renderExpandableProfileBadge = (badge: BadgeType) => (
    <span
      key={badge}
      className="group inline-flex h-10 cursor-default items-center overflow-hidden rounded-full border border-white/10 bg-black/25 px-2 text-gray-100 shadow-md shadow-black/10 transition-all duration-300 hover:border-amber-300/35 hover:bg-black/40 focus-within:border-amber-300/35 focus-within:bg-black/40"
      title={t(BADGE_CONFIG[badge].titleKey)}
      tabIndex={0}
    >
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white/8 transition-colors duration-300 group-hover:bg-white/12 group-focus-within:bg-white/12">
        <Badge type={badge} size="sm" />
      </span>
      <span className="ml-0 max-w-0 overflow-hidden whitespace-nowrap text-xs font-medium opacity-0 transition-all duration-300 group-hover:ml-2 group-hover:max-w-40 group-hover:opacity-100 group-focus-within:ml-2 group-focus-within:max-w-40 group-focus-within:opacity-100">
        {t(BADGE_CONFIG[badge].labelKey)}
      </span>
    </span>
  );

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

  const { data: printProfilesData, isLoading: _isLoadingPrintProfiles } = useQuery({
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
      queryClient.invalidateQueries({ queryKey: ['presets-stats'] });
      notifyProfileChanged();
    },
  });

  // Мутация для удаления сохранённого пресета
  const unsavePresetMutation = useMutation({
    mutationFn: (presetId: number) => savedPresetsAPI.unsave(presetId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saved-presets'] });
      queryClient.invalidateQueries({ queryKey: ['saved-presets-details'] });
      queryClient.invalidateQueries({ queryKey: ['user-presets'] });
      queryClient.invalidateQueries({ queryKey: ['presets-stats'] });
      notifyProfileChanged();
    },
    onError: (error: any) => {
      toast.error(translateApiError(t, error.response?.data?.detail, t('profilePage.unsaveError')));
    },
  });

  const handleDeletePreset = (preset: Preset) => {
    setDeletingPreset(preset);
  };

  const confirmDeletePreset = () => {
    if (!deletingPreset) return;
    if (deletingPreset.source === 'saved') {
      unsavePresetMutation.mutate(deletingPreset.id);
    } else {
      deletePresetMutation.mutate(deletingPreset.id);
    }
    setDeletingPreset(null);
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


  const handleDownloadPrinterProfile = async (profile: PrinterProfile) => {
    try {
      const response = await api.get(`/printer-profiles/${profile.id}/export/orcaslicer.json`, {
        responseType: 'blob',
      });
      
      const blob = new Blob([response.data], { type: 'application/json' });
      const base = safeFileName(profile.slug || profile.name || `printer-profile-${profile.id}`);
      downloadBlob(blob, `${base || 'printer-profile'}.orca_printer.json`);
    } catch (error: any) {
      toast.error(`${t('profilePage.downloadPrinterProfileError')}: ${translateApiError(t, error?.response?.data?.detail, t('profilePage.unknownError'))}`);
    }
  };

  const handleDownloadPrintProfile = async (profile: PrintProfile) => {
    try {
      const response = await api.get(`/print-profiles/${profile.id}/export/orcaslicer.json`, {
        responseType: 'blob',
      });
      
      const blob = new Blob([response.data], { type: 'application/json' });
      const base = safeFileName(profile.slug || profile.name || `print-profile-${profile.id}`);
      downloadBlob(blob, `${base || 'print-profile'}.orca_process.json`);
    } catch (error: any) {
      toast.error(`${t('profilePage.downloadPrintProfileError')}: ${translateApiError(t, error?.response?.data?.detail, t('profilePage.unknownError'))}`);
    }
  };

  const combinationsDraftCount = 0;

  if (!user) {
    return null; // ProtectedRoute должен это обработать
  }

  // Если выбран профиль компании, показываем BrandProfilePage
  if (showBrandCabinet) {
    return (
      <div>
        {/* Переключатель профилей */}
        {!isAddBrandFlowActive && (
          <div className="flex justify-center mb-4 min-[1140px]:mb-0 relative z-10 pointer-events-none">
            <div className="flex bg-white/10 rounded-lg p-1 border border-white/20 pointer-events-auto">
              <button
                onClick={() => setShowBrandCabinet(false)}
                className="flex items-center space-x-2 px-6 py-2 rounded-lg transition-all text-gray-300 hover:text-white"
              >
                <User className="w-4 h-4" />
                <span className="hidden sm:inline">{t('profilePage.user')}</span>
                <span className="sm:hidden">{t('profilePage.profile')}</span>
              </button>
              <button
                onClick={() => setShowBrandCabinet(true)}
                className="flex items-center space-x-2 px-6 py-2 rounded-lg transition-all bg-green-600 text-white shadow-lg shadow-green-500/25"
              >
                <Factory className="w-4 h-4" />
                <span className="hidden sm:inline">{t('profilePage.company')}</span>
                <span className="sm:hidden">{t('profilePage.brand')}</span>
              </button>
            </div>
          </div>
        )}
        
        <div
          className={
            user.brand_id
              ? isAddBrandFlowActive
                ? ''
                : 'min-[1140px]:-mt-14'
              : 'md:mt-12'
          }
        >
          <BrandProfilePage
            onBack={() => setShowBrandCabinet(false)}
            initialEditing={Boolean((location.state as { editBrand?: boolean } | null)?.editBrand)}
            onAddBrandFlowChange={setIsAddBrandFlowActive}
          />
        </div>
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
      
      {/* Header — компактная строка: аватар + имя·роль + ачивки (без крупного «Мой профиль») */}
      <div className="mb-4 md:mb-6 min-[1140px]:!-mt-16">
        <div className="flex items-center gap-3 mb-3 md:mb-4">
          <label className="group/avatar relative w-11 h-11 md:w-14 md:h-14 shrink-0 rounded-xl overflow-hidden cursor-pointer shadow-lg shadow-purple-500/25" title={t('profilePage.avatarUpload')}>
            {user.avatar_url ? (
              <img src={user.avatar_url} alt={user.full_name || user.username} className="w-full h-full object-cover" />
            ) : (
              <span className="w-full h-full flex items-center justify-center bg-gradient-to-r from-purple-500 to-pink-500">
                <User className="w-6 h-6 md:w-7 md:h-7 text-white" />
              </span>
            )}
            <span className="absolute inset-0 flex items-center justify-center bg-black/45 opacity-0 group-hover/avatar:opacity-100 transition-opacity">
              {isUploadingAvatar ? <Loader2 className="w-4 h-4 text-white animate-spin" /> : <Camera className="w-4 h-4 text-white" />}
            </span>
            <input type="file" accept=".png,.jpg,.jpeg,.bmp,.webp" onChange={handleAvatarUpload} className="hidden" disabled={isUploadingAvatar} />
          </label>
          <div className="min-w-0">
            <p className="text-base md:text-xl font-bold text-white truncate">{user.full_name || user.username}</p>
            <p className="text-xs md:text-sm text-gray-400">{t('profilePage.printer3d')}</p>
          </div>
          {profileBadges.length > 0 && (
            <div className="hidden sm:flex items-center gap-2 overflow-x-auto whitespace-nowrap scrollbar-hide min-w-0">
              {profileBadges.map(renderExpandableProfileBadge)}
            </div>
          )}
        </div>
        {profileBadges.length > 0 && (
          <div className="sm:hidden mb-3 w-full">
            <div className="flex items-center gap-2 overflow-x-auto whitespace-nowrap scrollbar-hide">
              {profileBadges.map(renderExpandableProfileBadge)}
            </div>
          </div>
        )}

        {/* Tabs - горизонтальный скролл на мобильных */}
        <div className="overflow-x-auto -mx-4 px-4 md:mx-0 md:px-0 scrollbar-hide">
          <div className="flex justify-start md:justify-center gap-1.5 md:gap-2 mt-3 md:mt-4 min-w-max">
            {([
              { id: 'dashboard' as const, label: t('profilePage.tabs.dashboard'), shortLabel: t('profilePage.tabs.dashboardShort'), icon: Play },
              { id: 'presets' as const, label: t('profilePage.tabs.presets'), shortLabel: t('profilePage.tabs.presetsShort'), icon: Settings },
              { id: 'printer-profiles' as const, label: t('profilePage.tabs.printers'), shortLabel: t('profilePage.tabs.printersShort'), icon: Printer3DIcon },
              { id: 'spools' as const, label: t('profilePage.tabs.spools'), shortLabel: t('profilePage.tabs.spoolsShort'), icon: Package },
              {
                id: 'calculator-pro' as const,
                label: t('profilePage.tabs.calculatorPro'),
                shortLabel: t('profilePage.tabs.calculatorProShort'),
                icon: Calculator,
                premium: true,
              },
              { id: 'settings' as const, label: t('profilePage.tabs.settings'), shortLabel: t('profilePage.tabs.settingsShort'), icon: Cog },
            ]).map((tab) => {
              const isPremiumTab = tab.premium === true;
              const hasCalculatorProAccess = user?.has_calculator_access ?? false;
              const isLocked = isPremiumTab && !hasCalculatorProAccess;
              
              return (
                <button
                  key={tab.id}
                  onClick={() => setUserTab(tab.id)}
                  className={`flex items-center gap-1.5 md:gap-2 px-2.5 md:px-4 py-1.5 md:py-2 rounded-lg transition-all text-xs md:text-sm whitespace-nowrap ${
                    userTab === tab.id
                      ? 'bg-purple-600 text-white shadow-lg shadow-purple-500/25'
                      : isLocked
                      ? 'text-gray-400 hover:text-white hover:bg-white/10 active:bg-white/15'
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
              {typeof window !== 'undefined' && window.filamenthub?.exportFilamentPresets && (
                <ExportFromOrcaSlicerButton />
              )}
              {typeof window !== 'undefined' && window.filamenthub?.scanOrphanedPresets && (
                <button
                  onClick={async () => {
                    if (isScanning) return;
                    setIsScanning(true);
                    try {
                      await window.filamenthub!.scanOrphanedPresets!();
                    } catch (e) {
                      console.error('Orphaned scan error:', e);
                    } finally {
                      setIsScanning(false);
                    }
                  }}
                  disabled={isScanning}
                  className="px-3 py-2 rounded-lg border text-sm font-medium transition-all bg-white/10 border-white/20 text-white hover:bg-white/20 disabled:opacity-50 disabled:cursor-not-allowed"
                  title={t('profilePage.scanOrphanedTitle')}
                >
                  {isScanning ? (
                    <Loader2 className="w-4 h-4 inline mr-1.5 animate-spin" />
                  ) : (
                    <RotateCcw className="w-4 h-4 inline mr-1.5" />
                  )}
                  <span className="hidden sm:inline">{t('profilePage.scanOrphaned')}</span>
                </button>
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
          printerProfiles={myPrinterProfiles.map((profile) => ({ id: profile.id, name: profile.name }))}
          onRefetch={refetchSpools}
          isAddOpen={isAddSpoolOpen}
          setIsAddOpen={setAddSpoolOpen}
          initialFilamentId={spoolIntakeFilamentId}
          initialSource={spoolIntakeSource}
        />
      )}

      {/* Print Calculator Tab */}
      {userTab === 'calculator-pro' && (
        <div className="space-y-4">
          <section className="relative mx-auto max-w-7xl overflow-hidden rounded-[1.65rem] border border-white/10 bg-slate-950/70 shadow-xl shadow-black/25 backdrop-blur-xl">
            <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_0%_0%,rgba(34,211,238,0.16),transparent_30%),radial-gradient(circle_at_100%_0%,rgba(245,158,11,0.1),transparent_26%)]" />
            <div className="relative p-3.5 md:p-4">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
                <div className="flex min-w-0 items-center gap-3">
                  <span className="shrink-0 rounded-full border border-cyan-400/25 bg-cyan-400/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-cyan-200">
                    {t('profilePage.calculator.proBadge')}
                  </span>
                  <h2 className="truncate text-base font-semibold text-white md:text-lg">{t('crmWorkspace.workspaceTitle')}</h2>
                </div>

                {calculatorWorkspaceMode === 'calculator' && (
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => setCalculatorEconomicsOpen((open) => !open)}
                      aria-expanded={calculatorEconomicsOpen}
                      className={`inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-xs font-medium transition ${calculatorEconomicsOpen ? 'border-cyan-400/30 bg-cyan-400/15 text-cyan-50' : 'border-white/10 bg-white/5 text-slate-300 hover:bg-white/10 hover:text-white'}`}
                    >
                      <Settings className="h-3.5 w-3.5" />
                      {t('profilePage.calculator.staticEconomicsTitle')}
                      <ChevronDown className={`h-3.5 w-3.5 transition-transform ${calculatorEconomicsOpen ? 'rotate-180' : ''}`} />
                    </button>
                    <button
                      type="button"
                      onClick={() => setCalculatorQuoteProfileOpen((open) => !open)}
                      aria-expanded={calculatorQuoteProfileOpen}
                      className={`inline-flex items-center gap-2 rounded-xl border px-3 py-2 text-xs font-medium transition ${calculatorQuoteProfileOpen ? 'border-cyan-400/30 bg-cyan-400/15 text-cyan-50' : 'border-white/10 bg-white/5 text-slate-300 hover:bg-white/10 hover:text-white'}`}
                    >
                      <FileText className="h-3.5 w-3.5" />
                      {t('profilePage.calculator.quoteProfileTitle')}
                      <ChevronDown className={`h-3.5 w-3.5 transition-transform ${calculatorQuoteProfileOpen ? 'rotate-180' : ''}`} />
                    </button>
                  </div>
                )}
              </div>

              <div className="mt-3 flex flex-col gap-3 border-t border-white/10 pt-3 xl:flex-row xl:items-center xl:justify-between">
                <div className="min-w-0 overflow-x-auto scrollbar-hide" role="tablist" aria-label={t('crmWorkspace.workspaceTitle')}>
                  <div className="flex min-w-max gap-1">
                    {([
                      { id: 'calculator' as const, label: t('profilePage.calculator.tabs.calculator'), icon: Calculator },
                      { id: 'history' as const, label: t('profilePage.calculator.tabs.history'), icon: Clock },
                      { id: 'quotes' as const, label: t('crmWorkspace.tabs.quotesShort'), icon: FileText },
                      { id: 'orders' as const, label: t('crmWorkspace.tabs.orders'), icon: BriefcaseBusiness },
                      { id: 'customers' as const, label: t('crmWorkspace.tabs.customers'), icon: UsersRound },
                    ]).map((item) => (
                      <button
                        key={item.id}
                        type="button"
                        role="tab"
                        aria-selected={calculatorWorkspaceMode === item.id}
                        onClick={() => setCalculatorWorkspaceMode(item.id)}
                        className={`inline-flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold transition md:text-sm ${calculatorWorkspaceMode === item.id ? 'bg-cyan-500 text-slate-950 shadow-md shadow-cyan-500/20' : 'text-slate-300 hover:bg-white/10 hover:text-white'}`}
                      >
                        <item.icon className="h-4 w-4" />
                        {item.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-400">
                  <span><strong className="mr-1 font-semibold tabular-nums text-white">{workspaceHistoryQuery.isPending ? '—' : workspaceHistoryQuery.data?.total ?? 0}</strong>{t('profilePage.calculator.workspaceSavedEstimates')}</span>
                  <span><strong className="mr-1 font-semibold tabular-nums text-white">{workspaceSummaryQuery.isPending ? '—' : (workspaceSummaryQuery.data?.quotes_draft ?? 0) + (workspaceSummaryQuery.data?.quotes_sent ?? 0)}</strong>{t('crmWorkspace.metrics.awaiting')}</span>
                  <span><strong className="mr-1 font-semibold tabular-nums text-white">{workspaceSummaryQuery.isPending ? '—' : workspaceSummaryQuery.data?.orders_active ?? 0}</strong>{t('crmWorkspace.metrics.activeOrders')}</span>
                </div>
              </div>
            </div>
          </section>

          {calculatorWorkspaceMode === 'calculator' || calculatorWorkspaceMode === 'history' ? (
            <div className="mx-auto max-w-7xl">
              <CalculatorPage
                embedded
                activeTab={calculatorWorkspaceMode}
                onActiveTabChange={setCalculatorWorkspaceMode}
                staticSettingsOpen={calculatorEconomicsOpen}
                quoteProfileOpen={calculatorQuoteProfileOpen}
                onStaticSettingsOpenChange={setCalculatorEconomicsOpen}
                onQuoteProfileOpenChange={setCalculatorQuoteProfileOpen}
              />
            </div>
          ) : (
            <div className="mx-auto max-w-7xl">
              <CrmWorkspacePage
                embedded
                activeTab={calculatorWorkspaceMode}
                onActiveTabChange={setCalculatorWorkspaceMode}
                onNewCalculation={() => setCalculatorWorkspaceMode('calculator')}
              />
            </div>
          )}
        </div>
      )}

      {/* Printer Profiles Tab */}
      {userTab === 'printer-profiles' && (
        <div className="space-y-8">
          <MyPrintersList
            printerProfiles={myPrinterProfiles.map((p) => ({ id: p.id, name: p.name }))}
            onEditConfiguration={(profile) => {
              setEditingPrinterProfile(profile);
              setIsCreatePrinterProfileModalOpen(true);
            }}
          />

          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between pt-6 border-t border-white/10">
            <div>
              <h2 className="text-2xl font-bold text-white">{t('profilePage.orcaProfilesHeading')}</h2>
              <p className="text-sm text-gray-400">
                {t('profilePage.orcaProfilesDescription')}
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
                                const hasCompatiblePrinterSlug = pp.compatible_printers?.includes(profile.printer_slug || '');
                                const hasCompatiblePrinterName = pp.compatible_printers?.includes(profile.name || '');
                                return hasPrinterLink || hasCompatiblePrinterSlug || hasCompatiblePrinterName;
                              })
                            : [];

                          const isProfileExpanded = expandedPrinterProfileId === profile.id;
                          // Полный профиль для редактирования (карточка из printer.profiles
                          // может быть облегчённой — модалке нужен полный объект).
                          const fullPrinterProfile = myPrinterProfiles.find((p) => p.id === profile.id);

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
                                <div className="flex items-center gap-2 shrink-0">
                                  {printProfilesForPrinterProfile.length > 0 && (
                                    <StatusBadge label={t('profilePage.printProfilesCount', { count: printProfilesForPrinterProfile.length })} variant="accent" />
                                  )}
                                  {fullPrinterProfile && (
                                    <button
                                      type="button"
                                      onClick={() => {
                                        setEditingPrinterProfile(fullPrinterProfile);
                                        setIsCreatePrinterProfileModalOpen(true);
                                      }}
                                      className="p-1.5 bg-white/10 hover:bg-white/20 rounded-lg text-white transition-all"
                                      title={t('profilePage.edit')}
                                    >
                                      <Edit className="w-4 h-4" />
                                    </button>
                                  )}
                                </div>
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
                                              {!printProfile.is_official && (
                                                <button
                                                  type="button"
                                                  onClick={() => {
                                                    setEditingPrintProfile(printProfile);
                                                    setIsCreatePrintProfileModalOpen(true);
                                                  }}
                                                  className="px-2 py-1 rounded border border-white/20 text-xs text-white/90 hover:bg-white/10 transition-all flex items-center gap-1"
                                                >
                                                  <Edit className="w-3 h-3" />
                                                  {t('profilePage.edit')}
                                                </button>
                                              )}
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
                                      setCreatePrintProfileContext(profile);
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
      <Suspense fallback={null}>
        <CreatePresetModal
          isOpen={isCreatePresetModalOpen}
          onClose={handleClosePresetModal}
          preset={editingPreset}
        />
      </Suspense>

      {/* View Preset Modal */}
      <ViewPresetModal
        isOpen={isViewPresetModalOpen}
        onClose={() => {
          setIsViewPresetModalOpen(false);
          setViewingPreset(null);
        }}
        preset={viewingPreset}
      />

      {/* Activate Preset Modal */}
      {/* Create Printer Request Modal */}
      <CreatePrinterRequestModal
        isOpen={isCreatePrinterRequestModalOpen}
        onClose={() => setIsCreatePrinterRequestModalOpen(false)}
      />

      {/* Create/Edit Printer Profile Modal */}
      <Suspense fallback={null}>
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
      </Suspense>

      {/* Create/Edit Print Profile Modal */}
      <CreatePrintProfileModal
        isOpen={isCreatePrintProfileModalOpen}
        onClose={() => {
          setIsCreatePrintProfileModalOpen(false);
          setEditingPrintProfile(null);
          setCreatePrintProfileContext(null);
        }}
        profile={editingPrintProfile}
        printerProfileContext={createPrintProfileContext}
      />

      {/* Help Modal */}
      {showHelpModal && (
        <ModalOverlay onClose={() => setShowHelpModal(false)}>
          <div className={`bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 rounded-2xl w-full max-w-4xl overflow-hidden flex flex-col border border-white/20 shadow-2xl mx-4 ${isHeaderVisible ? 'max-h-[calc(100vh-100px)]' : 'max-h-[90vh]'}`}>
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
        </ModalOverlay>
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

      <ConfirmDeleteModal
        isOpen={deletingPreset !== null}
        onClose={() => setDeletingPreset(null)}
        onConfirm={confirmDeletePreset}
        message={deletingPreset?.source === 'saved' ? t('profilePage.confirmUnsave') : t('profilePage.confirmDelete')}
        isLoading={unsavePresetMutation.isPending || deletePresetMutation.isPending}
      />
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
                ? `${spool.price.toFixed(0)} ${BASIC_CURRENCY_SYMBOL}`
                : `${((spool.filament!.price_per_kg! * spool.initial_weight_g) / 1000).toFixed(0)} ${BASIC_CURRENCY_SYMBOL}`}
            </span>
            {spool.price == null && spool.filament?.price_per_kg != null && (
              <span className="text-gray-600 ml-1">
                ({spool.filament.price_per_kg.toFixed(0)} {BASIC_CURRENCY_SYMBOL}/кг, рек.)
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

        {/* Current slot badge, or the last known slot for shelf twins */}
        {(() => {
          const current = getSpoolCurrentLocation(spool.extra);
          if (current) {
            return (
              <span className="inline-flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded bg-purple-500/20 border border-purple-500/30 text-purple-300 w-fit">
                <span className="font-mono">MMU</span>
                <span className="text-purple-400">{current.printer}</span>
                <span>#{current.gate}</span>
              </span>
            );
          }
          const last = getSpoolLastLocation(spool.extra);
          if (!last) return null;
          const dateLabel = last.unloadedAt
            ? new Date(last.unloadedAt).toLocaleDateString()
            : null;
          return (
            <span className="text-[10px] text-gray-500 w-fit">
              {t('profilePage.spoolLastLocation', {
                printer: last.printer,
                gate: last.gate,
              })}
              {dateLabel && ` · ${dateLabel}`}
            </span>
          );
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
            {(['shelf', 'active', 'archived', 'empty'] as const).map(s => (
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
  initialFilamentId?: number | null;
  initialSource?: 'manual' | 'qr';
  onSaved: () => void;
  onCancel: () => void;
}

const SpoolForm: React.FC<SpoolFormProps> = ({
  mode,
  spool,
  initialFilamentId = null,
  initialSource = 'manual',
  onSaved,
  onCancel,
}) => {
  const { user } = useAuth();
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [filamentId, setFilamentId] = useState<string>(spool?.filament_id ? String(spool.filament_id) : '');
  const [initialWeight, setInitialWeight] = useState<string>(spool ? String(spool.initial_weight_g) : '1000');
  const [usedWeight, setUsedWeight] = useState<string>(spool ? String(spool.used_weight_g) : '0');
  const [state, setState] = useState<SpoolState>(spool?.state ?? 'shelf');
  const [source, setSource] = useState(spool?.source ?? initialSource);
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
  const cameraDetectorRef = useRef<((video: HTMLVideoElement) => Promise<string | null>) | null>(null);
  const isCameraScanningRef = useRef(false);
  const appliedInitialFilamentRef = useRef<number | null>(null);
  // Touch-primary devices (phones/tablets) get camera-first UX; desktop gets
  // manual code entry as the primary path (webcam scanning is awkward there).
  const isTouchDevice = useMemo(
    () =>
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(pointer: coarse)').matches,
    [],
  );
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

  const devicesQuery = useQuery<UserPrinterDevice[]>({
    queryKey: ['spool-form-devices'],
    queryFn: () => devicesAPI.list(),
    enabled: mode === 'create',
  });
  const allDevices = devicesQuery.data ?? [];

  const { data: initialFilament } = useQuery({
    queryKey: ['spool-form-initial-filament', initialFilamentId],
    queryFn: () => filamentsAPI.get(initialFilamentId!),
    enabled: mode === 'create' && initialFilamentId !== null,
  });

  const hhDevices = useMemo(
    () => allDevices.filter((d) => d.supports_hh),
    [allDevices],
  );

  useEffect(() => {
    if (
      mode !== 'create'
      || !initialFilament
      || appliedInitialFilamentRef.current === initialFilament.id
    ) {
      return;
    }
    appliedInitialFilamentRef.current = initialFilament.id;
    setScannedFilament(initialFilament);
    setFilamentId(String(initialFilament.id));
    setSource(initialSource);
    if (initialFilament.spool_weight && initialFilament.spool_weight > 0) {
      setInitialWeight(String(initialFilament.spool_weight));
    }
  }, [initialFilament, initialSource, mode]);

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
        recommended_nozzle_temp_min: null,
        recommended_nozzle_temp_max: null,
        recommended_bed_temp_min: null,
        recommended_bed_temp_max: null,
        required_nozzle_hrc: null,
        description: null,
        views_count: null,
        scans_count: null,
        qr_code: null,
        active: true,
        availability: 'available',
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
    setSource(spool.source);
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
      setSource('qr');
      if (response.filament.spool_weight && response.filament.spool_weight > 0) {
        setInitialWeight(String(response.filament.spool_weight));
      }
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

    setIsCameraBusy(true);
    setIsCameraOpen(true);

    try {
      const decode = await createQrFrameDecoder();

      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' } },
        audio: false,
      });
      cameraStreamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }

      cameraDetectorRef.current = decode;
      isCameraScanningRef.current = true;
      setIsCameraReady(true);

      let lastDecodeAt = 0;
      const scanFrame = async (now: number) => {
        if (!isCameraScanningRef.current) {
          return;
        }

        const video = videoRef.current;
        const decoder = cameraDetectorRef.current;

        if (!video || !decoder || video.readyState < 2) {
          cameraFrameRef.current = requestAnimationFrame((ts) => {
            void scanFrame(ts);
          });
          return;
        }

        // Throttle to ~8 decodes/sec — ample for QR, keeps the device cool.
        if (now - lastDecodeAt >= 120) {
          lastDecodeAt = now;
          try {
            const rawValue = await decoder(video);
            if (!isCameraScanningRef.current) {
              return;
            }
            if (rawValue) {
              stopCameraScan();
              await resolveQrCode(rawValue);
              return;
            }
          } catch {
            // Игнорируем временные ошибки декодирования и продолжаем цикл.
          }
        }

        cameraFrameRef.current = requestAnimationFrame((ts) => {
          void scanFrame(ts);
        });
      };

      cameraFrameRef.current = requestAnimationFrame((ts) => {
        void scanFrame(ts);
      });
    } catch (error: any) {
      stopCameraScan();
      if (error?.name === 'NotAllowedError' || error?.name === 'PermissionDeniedError') {
        setQrError(t('profilePage.spoolAddModal.scanQrCameraPermissionDenied'));
      } else if (error?.message === 'qr-decoder-unavailable') {
        setQrError(t('profilePage.spoolAddModal.scanQrCameraNotSupported'));
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
    if (mode === 'create' && parsedUsed === parsedInitial) {
      setErrorText(t('profilePage.spoolActions.emptyOnCreate'));
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
        ...(mode === 'create' ? { source } : {}),
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
        let availableHhDevices = hhDevices;
        if (!devicesQuery.isSuccess) {
          const refreshedDevices = await devicesQuery.refetch();
          availableHhDevices = (refreshedDevices.data ?? []).filter((device) => device.supports_hh);
        }
        if (availableHhDevices.length > 0) {
          setCreatedSpool(newSpool);
          if (availableHhDevices.length === 1) {
            setSelectedDeviceId(String(availableHhDevices[0].id));
          }
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

  const handlePutOnShelf = async () => {
    if (!createdSpool) return;
    setAssigning(true);
    setErrorText(null);
    try {
      await spoolsAPI.update(createdSpool.id, { state: 'shelf' });
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

        <div className="flex flex-wrap gap-2 pt-1">
          <button
            type="button"
            onClick={handlePutOnShelf}
            disabled={assigning}
            className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-medium transition-colors disabled:opacity-50"
          >
            {t('profilePage.spoolGateStep.skip')}
          </button>
          <button
            type="button"
            onClick={handleAssignToGate}
            disabled={assigning || !selectedDeviceId || selectedGate === ''}
            className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg border border-white/20 text-gray-200 text-sm font-medium hover:bg-white/10 disabled:opacity-50 transition-colors"
          >
            {assigning && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            {t('profilePage.spoolGateStep.assign')}
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

            {/* Мобила: камера — основной способ */}
            {isTouchDevice && (
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
                className="w-full inline-flex items-center justify-center gap-2 px-3 py-2.5 rounded-md bg-purple-600/80 hover:bg-purple-600 text-white text-sm font-medium transition-colors disabled:opacity-60"
              >
                {isCameraBusy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Camera className="w-4 h-4" />}
                <span>{isCameraOpen ? t('profilePage.spoolAddModal.scanQrCameraStop') : t('profilePage.spoolAddModal.scanQrCameraStart')}</span>
              </button>
            )}

            {/* Превью камеры */}
            {isCameraOpen && (
              <div className="rounded-lg overflow-hidden border border-white/15 bg-black/30">
                <video ref={videoRef} className="w-full max-h-64 object-cover" playsInline muted autoPlay />
                <div className="px-3 py-2 text-xs text-gray-300 border-t border-white/10">
                  <p>{isCameraReady ? t('profilePage.spoolAddModal.scanQrCameraHint') : t('profilePage.spoolAddModal.scanQrCameraStarting')}</p>
                </div>
              </div>
            )}

            {/* Ручной ввод кода — основной на ПК, запасной на мобиле */}
            {isTouchDevice && (
              <p className="text-[11px] text-gray-500 pt-1">{t('profilePage.spoolAddModal.scanQrOrEnterCode')}</p>
            )}
            <input
              type="text"
              value={qrInput}
              onChange={(e) => setQrInput(e.target.value)}
              placeholder={t('profilePage.spoolAddModal.scanQrPlaceholder')}
              className={inputCls}
              disabled={qrBusy}
            />
            <div className="flex gap-2 flex-wrap">
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
                onClick={handlePasteQrFromClipboard}
                disabled={qrBusy}
                className="px-3 py-2 rounded-md border border-white/20 text-gray-300 text-xs hover:bg-white/10 transition-colors disabled:opacity-60"
              >
                {t('profilePage.spoolAddModal.scanQrPaste')}
              </button>
              {/* ПК: камера доступна, но второстепенно (вебкой неудобно) */}
              {!isTouchDevice && (
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
                  className="px-3 py-2 rounded-md border border-white/20 text-gray-400 text-xs hover:bg-white/10 transition-colors disabled:opacity-60 inline-flex items-center gap-1.5"
                >
                  {isCameraBusy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Camera className="w-3.5 h-3.5" />}
                  <span>{isCameraOpen ? t('profilePage.spoolAddModal.scanQrCameraStop') : t('profilePage.spoolAddModal.scanQrCameraStart')}</span>
                </button>
              )}
            </div>
          </div>
        )}

        <select
          value={filamentId}
          onChange={(e) => {
            setFilamentId(e.target.value);
            setScannedFilament(null);
            setSource('manual');
          }}
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

      <div className={`grid grid-cols-1 gap-3 ${mode === 'edit' ? 'md:grid-cols-2' : ''}`}>
        {mode === 'edit' && (
          <div>
            <label className={labelCls}>{t('profilePage.spoolAddModal.state')}</label>
            <select value={state} onChange={e => setState(e.target.value as SpoolState)} className={inputCls}>
              {(['shelf', 'active', 'archived', 'empty'] as const).map(s => (
                <option key={s} value={s}>{t(`profilePage.spoolState.${s}`)}</option>
              ))}
            </select>
          </div>
        )}

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
  printerProfiles: Array<{ id: number; name: string }>;
  onRefetch: () => void;
  isAddOpen: boolean;
  setIsAddOpen: (v: boolean) => void;
  initialFilamentId?: number | null;
  initialSource?: 'manual' | 'qr';
}

const AddDeviceForm: React.FC<{
  newDeviceName: string;
  setNewDeviceName: (v: string) => void;
  selectedPrinterId: number | null;
  setSelectedPrinterId: (v: number | null) => void;
  printerSearchQuery: string;
  setPrinterSearchQuery: (v: string) => void;
  isCreatingDevice: boolean;
  handleCreateDevice: () => void;
  onCancel: () => void;
}> = ({
  newDeviceName, setNewDeviceName,
  selectedPrinterId, setSelectedPrinterId,
  printerSearchQuery, setPrinterSearchQuery,
  isCreatingDevice, handleCreateDevice, onCancel,
}) => {
  const { t } = useTranslation();
  const [showDropdown, setShowDropdown] = useState(false);

  const { data: printersData } = useQuery({
    queryKey: ['printers-for-device', printerSearchQuery],
    queryFn: () => printersAPI.list({
      active_only: true,
      page: 1,
      size: 20,
      search: printerSearchQuery || undefined,
    }),
  });

  const printers = printersData?.items || [];
  const selectedPrinter = printers.find(p => p.id === selectedPrinterId);

  return (
    <div className="bg-black/20 border border-white/10 rounded-lg p-3 space-y-3">
      {/* Printer selection */}
      <div>
        <p className="text-xs text-gray-400 mb-1">{t('profilePage.deviceSetup.selectPrinter')}</p>
        <div className="relative">
          <input
            type="text"
            value={selectedPrinterId ? (selectedPrinter ? `${selectedPrinter.manufacturer || ''} ${selectedPrinter.name}`.trim() : printerSearchQuery) : printerSearchQuery}
            onChange={(e) => {
              setPrinterSearchQuery(e.target.value);
              setSelectedPrinterId(null);
              setShowDropdown(true);
            }}
            onFocus={() => setShowDropdown(true)}
            placeholder={t('profilePage.deviceSetup.searchPrinter')}
            className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-white placeholder-gray-600 focus:border-purple-500 focus:outline-none"
          />
          {showDropdown && printers.length > 0 && !selectedPrinterId && (
            <div className="absolute z-10 w-full mt-1 max-h-40 overflow-y-auto bg-gray-800 border border-white/20 rounded-lg shadow-lg">
              {printers.map((printer) => (
                <button
                  key={printer.id}
                  type="button"
                  onClick={() => {
                    setSelectedPrinterId(printer.id);
                    setNewDeviceName(`${printer.manufacturer || ''} ${printer.name}`.trim());
                    setPrinterSearchQuery('');
                    setShowDropdown(false);
                  }}
                  className="w-full text-left px-3 py-2 text-sm text-gray-200 hover:bg-purple-600/30 transition-colors"
                >
                  <span className="text-gray-400">{printer.manufacturer}</span>{' '}
                  <span className="text-white font-medium">{printer.name}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
      {/* Device name */}
      <div>
        <p className="text-xs text-gray-400 mb-1">{t('profilePage.deviceSetup.nameLabel')}</p>
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
            onClick={onCancel}
            className="px-3 py-1.5 rounded-lg border border-white/10 text-gray-400 text-sm hover:bg-white/10"
          >
            {t('common.cancel')}
          </button>
        </div>
      </div>
    </div>
  );
};

const SpoolsTab: React.FC<SpoolsTabProps> = ({
  spools,
  printerProfiles,
  onRefetch,
  isAddOpen,
  setIsAddOpen,
  initialFilamentId = null,
  initialSource = 'manual',
}) => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [spoolTab, setSpoolTab] = useState<'shelf' | 'active' | 'archived'>('active');
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
  const [selectedPrinterId, setSelectedPrinterId] = useState<number | null>(null);
  const [printerSearchQuery, setPrinterSearchQuery] = useState('');
  const [revealedKeys, setRevealedKeys] = useState<Record<number, string>>({});
  const [copiedDeviceId, setCopiedDeviceId] = useState<number | null>(null);
  const [editingHostname, setEditingHostname] = useState<Record<number, string>>({});
  const [savingHostname, setSavingHostname] = useState<number | null>(null);
  const [regeneratingDeviceId, setRegeneratingDeviceId] = useState<number | null>(null);
  const [deletingDeviceId, setDeletingDeviceId] = useState<number | null>(null);
  const deviceLinkNow = useNow();
  const [deletingSpoolId, setDeletingSpoolId] = useState<number | null>(null);

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
      const result = await devicesAPI.createWithKey(name, selectedPrinterId || undefined);
      setRevealedKeys((prev) => ({ ...prev, [result.device.id]: result.api_key }));
      setNewDeviceName('');
      setSelectedPrinterId(null);
      setPrinterSearchQuery('');
      setShowNewDeviceForm(false);
      queryClient.invalidateQueries({ queryKey: ['devices'] });
      await refetchDevices();
    } catch (error: any) {
      setSetupError(translateApiError(t, error?.response?.data?.detail));
    } finally {
      setIsCreatingDevice(false);
    }
  };

  const handleRegenerateKey = (deviceId: number) => {
    setRegeneratingDeviceId(deviceId);
  };

  const performRegenerateKey = async (deviceId: number) => {
    setRegeneratingDeviceId(null);
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

  const handleDeleteDevice = (deviceId: number) => {
    setDeletingDeviceId(deviceId);
  };

  const performDeleteDevice = async (deviceId: number) => {
    setDeletingDeviceId(null);
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

  const handleDelete = (id: number) => {
    setDeletingSpoolId(id);
  };

  const performDeleteSpool = async (id: number) => {
    setDeletingSpoolId(null);
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
    { key: 'active', label: t('profilePage.spoolTabs.active'), count: spoolTabCounts.active },
    { key: 'shelf', label: t('profilePage.spoolTabs.shelf'), count: spoolTabCounts.shelf },
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
            <AddDeviceForm
              newDeviceName={newDeviceName}
              setNewDeviceName={setNewDeviceName}
              selectedPrinterId={selectedPrinterId}
              setSelectedPrinterId={setSelectedPrinterId}
              printerSearchQuery={printerSearchQuery}
              setPrinterSearchQuery={setPrinterSearchQuery}
              isCreatingDevice={isCreatingDevice}
              handleCreateDevice={handleCreateDevice}
              onCancel={() => {
                setShowNewDeviceForm(false);
                setNewDeviceName('');
                setSelectedPrinterId(null);
                setPrinterSearchQuery('');
              }}
            />
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
            const linkState = getDeviceLinkState(device.last_seen_at, deviceLinkNow);
            return (
              <div key={device.id} className="bg-black/20 border border-white/10 rounded-lg p-3 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="text-white font-medium text-sm">{device.name}</span>
                    {linkState === 'active' ? (
                      <span title={t('deviceLink.tooltip')} className="flex items-center gap-1 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-medium text-emerald-300">
                        <Zap className="w-3 h-3" />
                        {device.gate_count != null
                          ? t('profilePage.deviceSetup.connectedGates', { count: device.gate_count })
                          : t('profilePage.deviceSetup.connected')}
                      </span>
                    ) : linkState === 'never' ? (
                      <span title={t('deviceLink.tooltip')} className="flex items-center gap-1 rounded-full bg-amber-500/15 px-2 py-0.5 text-[11px] font-medium text-amber-300">
                        <Clock className="w-3 h-3" />
                        {t('profilePage.deviceSetup.awaitingConnection')}
                      </span>
                    ) : (
                      <span
                        title={t('deviceLink.tooltip')}
                        className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ${
                          linkState === 'delayed' ? 'bg-amber-500/15 text-amber-300' : 'bg-white/10 text-gray-400'
                        }`}
                      >
                        <Clock className="w-3 h-3" />
                        {t(`deviceLink.${linkState}`)}
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
            initialFilamentId={initialFilamentId}
            initialSource={initialSource}
            onSaved={() => {
              setIsAddOpen(false);
              onRefetch();
            }}
            onCancel={() => setIsAddOpen(false)}
          />
        )}

        {editingSpool && (
          <ModalOverlay onClose={() => setEditingSpool(null)}>
            <div className="w-full max-w-2xl">
              <SpoolForm
                mode="edit"
                spool={editingSpool}
                onSaved={() => {
                  setEditingSpool(null);
                  onRefetch();
                }}
                onCancel={() => setEditingSpool(null)}
              />
            </div>
          </ModalOverlay>
        )}

        {usingSpool && (
          <ModalOverlay onClose={() => setUsingSpool(null)}>
            <div className="w-full max-w-xl">
              <UseSpoolForm
                spool={usingSpool}
                onSaved={() => {
                  setUsingSpool(null);
                  onRefetch();
                }}
                onCancel={() => setUsingSpool(null)}
              />
            </div>
          </ModalOverlay>
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
              <PresetSlotsPanel compact spools={spools} printerProfiles={printerProfiles} />
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

      <ConfirmModal
        isOpen={regeneratingDeviceId !== null}
        onClose={() => setRegeneratingDeviceId(null)}
        onConfirm={() => {
          if (regeneratingDeviceId !== null) void performRegenerateKey(regeneratingDeviceId);
        }}
        message={t('profilePage.deviceSetup.regenerateConfirm')}
        variant="warning"
      />

      <ConfirmDeleteModal
        isOpen={deletingDeviceId !== null}
        onClose={() => setDeletingDeviceId(null)}
        onConfirm={() => {
          if (deletingDeviceId !== null) void performDeleteDevice(deletingDeviceId);
        }}
        message={t('profilePage.deviceSetup.deleteConfirm')}
      />

      <ConfirmDeleteModal
        isOpen={deletingSpoolId !== null}
        onClose={() => setDeletingSpoolId(null)}
        onConfirm={() => {
          if (deletingSpoolId !== null) void performDeleteSpool(deletingSpoolId);
        }}
        message={t('profilePage.spoolActions.deleteConfirm')}
      />
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
  const [_isImporting, setIsImporting] = useState(false);
  const [_isInOrcaSlicer, setIsInOrcaSlicer] = useState(false);

  // Проверяем, запущен ли frontend внутри OrcaSlicer
  useEffect(() => {
    // Проверяем наличие window.filamenthub или window.wx
    const inOrca = typeof window !== 'undefined' && (
      window.filamenthub?.importProfile ||
      window.wx?.postMessage
    );
    setIsInOrcaSlicer(Boolean(inOrca));

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
              toast.error(`${t('profilePage.importError')}: ${data.message || t('profilePage.unknownError')}`);
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
      
      downloadBlob(blob, filename);
    } catch (error: any) {
      console.error('Error downloading preset:', error);

      let errorMessage = t('profilePage.unknownError');
      if (error.response) {
        const status = error.response.status;
        const data = error.response.data;

        if (status === 0) {
          // Network error (injected by interceptor)
          errorMessage = translateApiError(t, data?.detail, t('profilePage.errors.connectionError'));
        } else if (status === 401) {
          errorMessage = t('profilePage.errors.authRequired');
        } else if (status === 404) {
          errorMessage = t('profilePage.errors.presetNotFound');
        } else if (status === 500) {
          errorMessage = `${t('profilePage.errors.serverExportError')}: ${translateApiError(t, data?.detail, t('profilePage.errors.internalError'))}`;
          console.error('Error 500 details:', data?.detail);
        } else {
          errorMessage = translateApiError(t, data?.detail, `${t('profilePage.errors.errorCode', { code: status })}: ${data?.message || t('profilePage.errors.requestError')}`);
        }
      } else {
        errorMessage = error.message || t('profilePage.errors.requestError');
      }

      toast.error(`${t('profilePage.downloadPresetError')}: ${errorMessage}`);
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
              {!preset.active && preset.source === 'own' && !preset.name?.includes('@fh') && (
                <span className="px-2 py-0.5 bg-orange-600/30 rounded text-orange-300 text-xs font-medium whitespace-nowrap">
                  {t('profilePage.draft')}
                </span>
              )}
              {preset.orcaslicer_settings?.orphaned && (
                <span className="px-2 py-0.5 bg-purple-600/30 rounded text-purple-300 text-xs font-medium whitespace-nowrap" title={t('profilePage.orphanedTooltip')}>
                  {t('profilePage.orphaned')}
                </span>
              )}
              {preset.orcaslicer_settings?.enrichment && (
                <span className="px-2 py-0.5 bg-cyan-600/20 rounded text-cyan-400 text-xs whitespace-nowrap">
                  {t('profilePage.materialDetected', { type: (preset.orcaslicer_settings.enrichment as Record<string, unknown>).material_type as string })}
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
          {/* Edit only for own presets */}
          {preset.source === 'own' && (
            <button
              onClick={() => onEdit?.(preset)}
              className="p-2 bg-white/10 hover:bg-white/20 rounded-lg text-white transition-all"
              title={t('profilePage.edit')}
            >
              <Edit className="w-4 h-4" />
            </button>
          )}
          {/* View (details + version history) for all presets */}
          <button
            onClick={() => onView?.(preset)}
            className="p-2 bg-white/10 hover:bg-white/20 rounded-lg text-white transition-all"
            title={t('profilePage.viewPreset')}
          >
            <Eye className="w-4 h-4" />
          </button>
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


const BASIC_CURRENCY_SYMBOL = '₽';

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

interface PrinterProfileModalProps {
  profile: PrinterProfile;
  onClose: () => void;
  formatDateTime: (value: string) => string;
  printProfileNameBySlug?: Map<string, string>;
}

const PrinterProfileModal: React.FC<PrinterProfileModalProps> = ({ profile, onClose, formatDateTime, printProfileNameBySlug }) => {
  const { t } = useTranslation();

  return (
    <ModalOverlay onClose={onClose}>
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
          <OrcaSettingsView settings={profile.orcaslicer_settings} />
        </div>
      </div>
    </ModalOverlay>
  );
};

interface PrintProfileModalProps {
  profile: PrintProfile;
  onClose: () => void;
  formatDateTime: (value: string) => string;
}

const PrintProfileModal: React.FC<PrintProfileModalProps> = ({ profile, onClose, formatDateTime }) => {
  const { t } = useTranslation();

  const printersList = profile.printer_links ?? [];
  const filamentsList = profile.filament_links ?? [];
  const defaultNozzle = profile.default_nozzle ? `${profile.default_nozzle} ${t('profilePage.mm')}` : t('profilePage.notSpecifiedN');
  const layerHeight =
    typeof profile.layer_height_mm === 'number' ? `${profile.layer_height_mm.toFixed(2)} ${t('profilePage.mm')}` : t('profilePage.notSpecifiedF');

  return (
    <ModalOverlay onClose={onClose}>
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
          <OrcaSettingsView settings={profile.orcaslicer_settings} />
        </div>
      </div>
    </ModalOverlay>
  );
};

