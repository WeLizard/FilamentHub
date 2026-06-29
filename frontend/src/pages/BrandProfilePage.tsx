/** Личный кабинет производителя */

import { lazy, Suspense, useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import {
  Factory,
  Package,
  QrCode,
  BarChart3,
  TrendingUp,
  Shield,
  Plus,
  Settings,
  Eye,
  Download,
  Copy,
  Share2,
  Thermometer,
  Gauge,
  Edit,
  Trash2,
  CheckCircle,
  X,
  Loader2,
  Check,
  Paperclip,
  XCircle,
  FileText,
  Fan,
  AlertTriangle,
  Grid3x3,
  List,
  Upload,
  Info,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { brandsAPI, filamentsAPI, brandRequestsAPI, presetsAPI, qrAPI } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { PERSONAL_EMAIL_DOMAINS } from '../data/personalEmailDomains';
import { currencySymbol } from '../utils/currency';
import { filamentImportAPI, filamentLinesAPI } from '../api/client';
import { ModalOverlay } from '../components/ModalOverlay';
import { HSLColorPicker } from '../components/HSLColorPicker';
import { SocialIcon } from '../components/socialIcons';
import type { FilamentImportResult } from '../types/api';
import { CreateFilamentModal } from '../components/CreateFilamentModal';
const CreatePresetModal = lazy(() =>
  import('../components/CreatePresetModal').then(m => ({ default: m.CreatePresetModal }))
);
import { PresetSyncToggle } from '../components/PresetSyncToggle';
import { Dropdown } from '../components/Dropdown';
import { FilamentPreview } from '../components/FilamentPreview';
import type { Filament, FilamentAvailability, Brand, BrandRequest, Preset } from '../types/api';
import type { AxiosError } from 'axios';

interface BrandProfilePageProps {
  onBack?: () => void; // Callback для возврата в обычный профиль
}

export const BrandProfilePage: React.FC<BrandProfilePageProps> = ({ onBack }) => {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [brandTab, setBrandTab] = useState<'materials' | 'presets' | 'qr' | 'analytics' | 'usage'>('materials');
  const [materialsViewMode, setMaterialsViewMode] = useState<'grid' | 'list'>('grid');
  const [isCreateFilamentModalOpen, setIsCreateFilamentModalOpen] = useState(false);
  const [isCreatePresetModalOpen, setIsCreatePresetModalOpen] = useState(false);
  const [editingFilament, setEditingFilament] = useState<Filament | null>(null);
  const [editingPreset, setEditingPreset] = useState<Preset | null>(null);
  const [deletingFilamentId, setDeletingFilamentId] = useState<number | null>(null);
  const [deletingLine, setDeletingLine] = useState<{ id: number; name: string } | null>(null);
  const [showQRFilament, setShowQRFilament] = useState<Filament | null>(null);
  const [isEditingProfile, setIsEditingProfile] = useState(false);
  const [profileDescription, setProfileDescription] = useState('');
  const [profileWebsite, setProfileWebsite] = useState('');
  const [profileLogoUrl, setProfileLogoUrl] = useState('');
  const [profileLogoBg, setProfileLogoBg] = useState('');
  const [logoBgPickerOpen, setLogoBgPickerOpen] = useState(false);
  const [showCsvHelp, setShowCsvHelp] = useState(false);
  const [profileSocialUrls, setProfileSocialUrls] = useState<string[]>([]);
  const [profileShopLinks, setProfileShopLinks] = useState<{ platform: string; url: string }[]>([]);
  const [profilePriceHidden, setProfilePriceHidden] = useState(false);
  const [profileError, setProfileError] = useState<string | null>(null);
  const [isUploadingLogo, setIsUploadingLogo] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [importResult, setImportResult] = useState<FilamentImportResult | null>(null);
  const [isBrandLogoVisible, setIsBrandLogoVisible] = useState(false);

  // Загружаем данные бренда
  const { data: brandData, isLoading: isLoadingBrand } = useQuery({
    queryKey: ['brand', user?.brand_id],
    queryFn: () => brandsAPI.get(user!.brand_id!),
    enabled: !!user?.brand_id,
  });

  // Загружаем материалы производителя
  const { 
    data: filamentsData, 
    isLoading: isLoadingFilaments,
    error: filamentsError 
  } = useQuery({
    queryKey: ['brand-filaments', user?.brand_id],
    queryFn: () => filamentsAPI.list({ active_only: false, brand_id: user?.brand_id ?? undefined, page: 1, size: 100 }),
    enabled: !!user?.brand_id,
  });

  const filaments = filamentsData?.items || [];

  // Группировка материалов по линейке (как на публичной странице бренда):
  // материалы с line_name — под заголовком линейки, остальные — отдельной группой.
  const materialLineGroups = (() => {
    const byLine = new Map<string, { lineName: string; items: typeof filaments }>();
    const ungrouped: typeof filaments = [];
    for (const f of filaments) {
      if (f.line_name && f.line_id) {
        const key = String(f.line_id);
        const g = byLine.get(key);
        if (g) g.items.push(f);
        else byLine.set(key, { lineName: f.line_name, items: [f] });
      } else {
        ungrouped.push(f);
      }
    }
    const groups: { key: string; lineName: string | null; items: typeof filaments }[] =
      Array.from(byLine.entries()).map(([key, v]) => ({ key, lineName: v.lineName, items: v.items }));
    if (ungrouped.length) groups.push({ key: 'ungrouped', lineName: null, items: ungrouped });
    return groups;
  })();

  // Загружаем официальные пресеты производителя (для его материалов)
  const { 
    data: presetsData, 
    isLoading: isLoadingPresets 
  } = useQuery({
    queryKey: ['brand-presets', user?.brand_id],
    queryFn: async () => {
      // Получаем все пресеты для материалов этого бренда
      const allPresets: Preset[] = [];
      for (const filament of filaments) {
        const presets = await presetsAPI.list({ 
          active_only: false, 
          filament_id: filament.id, 
          is_official: true,
          page: 1, 
          size: 100 
        });
        allPresets.push(...presets.items);
      }
      return { items: allPresets };
    },
    enabled: !!user?.brand_id && filaments.length > 0,
  });

  const brandPresets = presetsData?.items || [];

  const { data: usageData } = useQuery({
    queryKey: ['brand-usage', user?.brand_id],
    queryFn: () => brandsAPI.getUsage(user!.brand_id!),
    enabled: !!user?.brand_id && brandTab === 'usage',
  });

  useEffect(() => {
    setIsBrandLogoVisible(Boolean(brandData?.logo_url));
  }, [brandData?.logo_url]);

  // Мутация для удаления материала
  const deleteFilamentMutation = useMutation({
    mutationFn: (id: number) => filamentsAPI.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['brand-filaments'] });
      queryClient.invalidateQueries({ queryKey: ['filaments'] });
      queryClient.invalidateQueries({ queryKey: ['filaments', 'material-types'] });
      setDeletingFilamentId(null);
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      alert(translateApiError(t, err.response?.data?.detail, t('brandProfile.errorDeleteMaterial')));
      setDeletingFilamentId(null);
    },
  });

  const deleteLineMutation = useMutation({
    mutationFn: (id: number) => filamentLinesAPI.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['brand-filaments'] });
      if (brandData?.id) queryClient.invalidateQueries({ queryKey: ['filament-lines', brandData.id] });
      setDeletingLine(null);
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      setProfileError(translateApiError(t, err.response?.data?.detail, t('brandProfile.errorDeleteLine')));
      setDeletingLine(null);
    },
  });

  // Мутация для обновления профиля бренда
  const updateBrandMutation = useMutation({
    mutationFn: (data: { description?: string | null; website?: string | null; logo_url?: string | null; logo_bg?: string | null; social_media_urls?: string[] | null; shop_links?: { platform: string; url: string }[] | null; price_hidden?: boolean }) =>
      brandsAPI.update(user!.brand_id!, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['brand', user?.brand_id] });
      setIsEditingProfile(false);
      setProfileError(null);
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      setProfileError(translateApiError(t, err.response?.data?.detail, t('brandProfile.errorUpdateProfile')));
    },
  });

  const handleEditProfile = () => {
    if (brandData) {
      setProfileDescription(brandData.description || '');
      setProfileWebsite(brandData.website || '');
      setProfileLogoUrl(brandData.logo_url || '');
      setProfileLogoBg(brandData.logo_bg || '');
      setProfileSocialUrls(brandData.social_media_urls || []);
      setProfileShopLinks(brandData.shop_links || []);
      setProfilePriceHidden(brandData.price_hidden || false);
      setProfileError(null);
      setIsEditingProfile(true);
    }
  };

  const handleSaveProfile = () => {
    updateBrandMutation.mutate({
      description: profileDescription.trim() || null,
      website: profileWebsite.trim() || null,
      logo_url: profileLogoUrl.trim() || null,
      logo_bg: profileLogoBg.trim() || null,
      social_media_urls: profileSocialUrls.filter((u) => u.trim()),
      shop_links: profileShopLinks.filter((l) => l.url.trim()),
      price_hidden: profilePriceHidden,
    });
  };

  const handleLogoUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !brandData?.id) return;
    setIsUploadingLogo(true);
    try {
      const updated = await brandsAPI.uploadLogo(brandData.id, file);
      setProfileLogoUrl(updated.logo_url || '');
      queryClient.invalidateQueries({ queryKey: ['brand', user?.brand_id] });
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      setProfileError(translateApiError(t, detail, t('brandProfile.logoUploadError')));
    } finally {
      setIsUploadingLogo(false);
      e.target.value = '';
    }
  };

  const handleImportCsv = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !brandData?.id) return;
    setIsImporting(true);
    try {
      const res = await filamentImportAPI.importCsv(brandData.id, file);
      setImportResult(res);
      queryClient.invalidateQueries({ queryKey: ['brand-filaments'] });
      queryClient.invalidateQueries({ queryKey: ['filament-lines', brandData.id] });
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
      setProfileError(translateApiError(t, detail, t('brandProfile.importError')));
    } finally {
      setIsImporting(false);
      e.target.value = '';
    }
  };

  const handleCreateFilament = () => {
    setEditingFilament(null);
    setIsCreateFilamentModalOpen(true);
  };

  const handleEditFilament = (filament: Filament) => {
    setEditingFilament(filament);
    setIsCreateFilamentModalOpen(true);
  };

  const handleDeleteFilament = (filament: Filament) => {
    setDeletingFilamentId(filament.id);
  };

  const confirmDeleteFilament = () => {
    if (deletingFilamentId) {
      deleteFilamentMutation.mutate(deletingFilamentId);
    }
  };

  const cancelDeleteFilament = () => {
    setDeletingFilamentId(null);
  };

  const handleCloseFilamentModal = () => {
    setIsCreateFilamentModalOpen(false);
    setEditingFilament(null);
  };

  const handleCreatePreset = () => {
    setEditingPreset(null);
    setIsCreatePresetModalOpen(true);
  };

  const handleEditPreset = (preset: Preset) => {
    setEditingPreset(preset);
    setIsCreatePresetModalOpen(true);
  };

  const handleClosePresetModal = () => {
    setIsCreatePresetModalOpen(false);
    setEditingPreset(null);
  };

  if (!user) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-red-400 text-xl">{t('brandProfile.loginRequired')}</div>
      </div>
    );
  }

  // Если у пользователя нет brand_id, показываем форму выбора/создания бренда
  if (!user.brand_id) {
    return <BrandSelectionForm />;
  }

  if (isLoadingBrand) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-white text-xl">{t('brandProfile.loading')}</div>
      </div>
    );
  }

  if (!brandData) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-red-400 text-xl">{t('brandProfile.brandNotFound')}</div>
      </div>
    );
  }

  // Вычисляем статистику
  const totalScans = filaments.reduce((sum, f) => sum + (f.scans_count || 0), 0);
  const totalViews = filaments.reduce((sum, f) => sum + (f.views_count || 0), 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex justify-center md:justify-end mb-4">
          <div className="relative flex flex-col items-center md:inline-flex md:flex-row md:items-center">
            <div
              className={`mb-3 inline-flex h-16 shrink-0 items-center justify-center overflow-hidden rounded-xl shadow-lg p-0.5 md:mb-0 md:absolute md:right-full md:top-1/2 md:mr-3 md:-translate-y-1/2 ${
                isBrandLogoVisible && brandData.logo_url
                  ? 'border border-white/10 bg-white/10'
                  : 'w-16 bg-gradient-to-r from-green-500 to-emerald-500 shadow-green-500/25'
              }`}
              style={isBrandLogoVisible && brandData.logo_url && brandData.logo_bg ? { backgroundColor: brandData.logo_bg } : undefined}
            >
              {isBrandLogoVisible && brandData.logo_url ? (
                <img
                  src={brandData.logo_url}
                  alt={brandData.name}
                  className="block h-full w-auto max-w-[15rem] object-contain"
                  onError={() => setIsBrandLogoVisible(false)}
                />
              ) : (
                <Factory className="w-8 h-8 text-white" />
              )}
            </div>
            <div className="text-center md:text-right">
              <div className="flex items-center justify-center space-x-2 md:justify-end">
                <h2 className="text-3xl font-bold text-white">{brandData.name}</h2>
                <button
                  onClick={handleEditProfile}
                  className="p-1.5 text-gray-400 hover:text-white hover:bg-white/10 rounded-lg transition-all"
                  title={t('brandProfile.editProfile')}
                >
                  <Edit className="w-4 h-4" />
                </button>
              </div>
              <div className="mt-1 flex items-center justify-center space-x-2 text-gray-300 md:justify-end">
                {brandData.verified && <Shield className="w-4 h-4 text-green-400" />}
                <span>{brandData.verified ? t('brandProfile.verifiedManufacturer') : t('brandProfile.manufacturer')}</span>
              </div>
              {brandData.description && (
                <p className="mt-1 max-w-md text-sm text-gray-400 md:mx-0">{brandData.description}</p>
              )}
              {brandData.website && (
                <a
                  href={brandData.website.startsWith('http') ? brandData.website : `https://${brandData.website}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="mt-1 inline-block text-sm text-purple-400 hover:text-purple-300"
                >
                  {brandData.website}
                </a>
              )}
              <div className="mt-3">
                <button
                  onClick={() => navigate(`/brands/${brandData.id}`)}
                  className="inline-flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-sm text-white transition-all hover:bg-white/10"
                >
                  <Eye className="w-4 h-4" />
                  <span>{t('brandProfile.openPublicPage')}</span>
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex justify-center space-x-2 mt-4">
          {([
            { id: 'materials', label: t('brandProfile.tabs.materials'), icon: Package },
            { id: 'presets', label: t('brandProfile.tabs.presets'), icon: Settings },
            { id: 'qr', label: t('brandProfile.tabs.qr'), icon: QrCode },
            { id: 'analytics', label: t('brandProfile.tabs.analytics'), icon: BarChart3 },
            { id: 'usage', label: t('brandProfile.tabs.usage'), icon: TrendingUp },
          ] as const).map((tab) => (
            <button
              key={tab.id}
              onClick={() => setBrandTab(tab.id)}
              className={`flex items-center space-x-2 px-4 py-2 rounded-lg transition-all ${
                brandTab === tab.id
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

      {/* Materials Tab */}
      {brandTab === 'materials' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h3 className="text-2xl font-bold text-white">{t('brandProfile.myMaterials')}</h3>
            <div className="flex items-center space-x-3">
              {/* View Mode Toggle */}
              <div className="flex items-center bg-white/10 rounded-lg p-1 border border-white/20">
                <button
                  onClick={() => setMaterialsViewMode('grid')}
                  className={`p-2 rounded transition-all ${
                    materialsViewMode === 'grid'
                      ? 'bg-purple-600 text-white'
                      : 'text-gray-400 hover:text-white'
                  }`}
                  title={t('brandProfile.gridView')}
                >
                  <Grid3x3 className="w-4 h-4" />
                </button>
                <button
                  onClick={() => setMaterialsViewMode('list')}
                  className={`p-2 rounded transition-all ${
                    materialsViewMode === 'list'
                      ? 'bg-purple-600 text-white'
                      : 'text-gray-400 hover:text-white'
                  }`}
                  title={t('brandProfile.listView')}
                >
                  <List className="w-4 h-4" />
                </button>
              </div>
            <a
              href={filamentImportAPI.templateUrl}
              download
              className="px-4 py-2 rounded-xl border border-white/20 bg-white/10 text-gray-300 hover:text-white hover:bg-white/20 transition-all flex items-center space-x-2"
            >
              <Download className="w-4 h-4" />
              <span>{t('brandProfile.importTemplate')}</span>
            </a>
            <button
              type="button"
              onClick={() => setShowCsvHelp((v) => !v)}
              className={`px-3 py-2 rounded-xl border border-white/20 transition-all flex items-center ${showCsvHelp ? 'bg-purple-600/30 text-white' : 'bg-white/10 text-gray-300 hover:text-white hover:bg-white/20'}`}
              title={t('brandProfile.csvHelpToggle')}
            >
              <Info className="w-4 h-4" />
            </button>
            <label className="px-4 py-2 rounded-xl border border-white/20 bg-white/10 text-gray-300 hover:text-white hover:bg-white/20 transition-all cursor-pointer flex items-center space-x-2">
              {isImporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
              <span>{t('brandProfile.importCsv')}</span>
              <input type="file" accept=".csv,text/csv" onChange={handleImportCsv} className="hidden" disabled={isImporting} />
            </label>
            <button
              onClick={handleCreateFilament}
              disabled={isLoadingFilaments}
              className="bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700 text-white px-4 py-2 rounded-xl transition-all shadow-lg shadow-green-500/25 hover:shadow-green-500/40 disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
            >
              <Plus className="w-4 h-4" />
              <span>{t('brandProfile.newMaterial')}</span>
            </button>
            </div>
          </div>

          {showCsvHelp && (
            <div className="mb-4 p-4 rounded-xl border border-white/10 bg-white/5 text-sm text-gray-300">
              <p className="font-medium text-white mb-2">{t('brandProfile.csvHelpTitle')}</p>
              <ul className="space-y-1">
                <li><code className="text-purple-300">name</code> — {t('brandProfile.csvColName')}</li>
                <li><code className="text-purple-300">material_type</code> — {t('brandProfile.csvColMaterial')}</li>
                <li><code className="text-purple-300">color_name</code> — {t('brandProfile.csvColColorName')}</li>
                <li><code className="text-purple-300">color_hex</code> — {t('brandProfile.csvColColorHex')}</li>
                <li><code className="text-purple-300">price_per_kg</code> — {t('brandProfile.csvColPrice')}</li>
                <li><code className="text-purple-300">spool_weight</code> — {t('brandProfile.csvColSpool')}</li>
                <li><code className="text-purple-300">line</code> — {t('brandProfile.csvColLine')}</li>
                <li>
                  <code className="text-purple-300">availability</code> — {t('brandProfile.csvColAvailability')}{' '}
                  <code className="text-gray-200">available</code>, <code className="text-gray-200">discontinued</code>, <code className="text-gray-200">coming_soon</code>
                </li>
              </ul>
              <p className="text-gray-500 text-xs mt-2">{t('brandProfile.csvHelpNote')}</p>
            </div>
          )}

          {/* Loading State */}
          {isLoadingFilaments && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 text-purple-400 animate-spin mr-3" />
              <span className="text-gray-300 text-lg">{t('brandProfile.loadingMaterials')}</span>
            </div>
          )}

          {/* Error State */}
          {filamentsError && (
            <div className="bg-red-500/20 border border-red-500/30 rounded-xl p-4">
              <div className="flex items-center space-x-2 text-red-300">
                <XCircle className="w-5 h-5" />
                <span>{t('brandProfile.errorLoadMaterials')}</span>
              </div>
            </div>
          )}

          {/* Materials Grid/List */}
          {!isLoadingFilaments && !filamentsError && (
            <>
              {filaments.length > 0 ? (
                <div className="space-y-6">
                  {materialLineGroups.map((group) => (
                    <div key={group.key}>
                      {group.lineName && (
                        <div className="flex items-center gap-2 mb-3">
                          <h3 className="text-base font-semibold text-white">{group.lineName}</h3>
                          <button
                            type="button"
                            onClick={() => setDeletingLine({ id: Number(group.key), name: group.lineName! })}
                            title={t('brandProfile.deleteLine')}
                            className="p-1 text-gray-500 hover:text-red-400 transition-colors"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      )}
                      {materialsViewMode === 'grid' ? (
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                          {group.items.map((filament) => (
                            <FilamentCard
                              key={filament.id}
                              filament={filament}
                              onEdit={handleEditFilament}
                              onDelete={handleDeleteFilament}
                              onShowQR={(filament) => setShowQRFilament(filament)}
                              viewMode="grid"
                            />
                          ))}
                        </div>
                      ) : (
                        <div className="space-y-3">
                          {group.items.map((filament) => (
                            <FilamentCard
                              key={filament.id}
                              filament={filament}
                              onEdit={handleEditFilament}
                              onDelete={handleDeleteFilament}
                              onShowQR={(filament) => setShowQRFilament(filament)}
                              viewMode="list"
                            />
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-12">
                  <Package className="w-16 h-16 text-gray-400 mx-auto mb-4" />
                  <p className="text-gray-400 text-xl mb-2">{t('brandProfile.noMaterials')}</p>
                  <p className="text-gray-500 text-sm">{t('brandProfile.createFirstMaterial')}</p>
                </div>
              )}
            </>
          )}

          {/* Delete Loading Indicator */}
          {deleteFilamentMutation.isPending && (
            <div className="fixed bottom-4 right-4 bg-purple-600/90 backdrop-blur-sm text-white px-4 py-3 rounded-xl shadow-lg flex items-center space-x-2 z-50">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>{t('brandProfile.deletingMaterial')}</span>
            </div>
          )}

          {/* Delete Confirmation Modal */}
          {deletingFilamentId && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
              <div className="bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 rounded-2xl p-6 w-full max-w-md border border-white/20 shadow-2xl">
                <div className="flex items-center space-x-3 mb-4">
                  <div className="w-12 h-12 bg-red-500/20 rounded-full flex items-center justify-center">
                    <Trash2 className="w-6 h-6 text-red-400" />
                  </div>
                  <h3 className="text-xl font-bold text-white">{t('brandProfile.confirmDelete')}</h3>
                </div>
                <p className="text-gray-300 mb-6">
                  {t('brandProfile.confirmDeleteMaterial', { name: filaments.find(f => f.id === deletingFilamentId)?.name })}
                  <br />
                  <span className="text-red-400 text-sm mt-2 block">{t('brandProfile.actionIrreversible')}</span>
                </p>
                <div className="flex justify-end space-x-3">
                  <button
                    onClick={cancelDeleteFilament}
                    disabled={deleteFilamentMutation.isPending}
                    className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all disabled:opacity-50"
                  >
                    {t('brandProfile.cancel')}
                  </button>
                  <button
                    onClick={confirmDeleteFilament}
                    disabled={deleteFilamentMutation.isPending}
                    className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-xl transition-all disabled:opacity-50 flex items-center space-x-2"
                  >
                    {deleteFilamentMutation.isPending ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>{t('brandProfile.deleting')}</span>
                      </>
                    ) : (
                      <>
                        <Trash2 className="w-4 h-4" />
                        <span>{t('brandProfile.delete')}</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          )}

          {deletingLine && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
              <div className="bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 rounded-2xl p-6 w-full max-w-md border border-white/20 shadow-2xl">
                <div className="flex items-center space-x-3 mb-4">
                  <div className="w-12 h-12 bg-red-500/20 rounded-full flex items-center justify-center">
                    <Trash2 className="w-6 h-6 text-red-400" />
                  </div>
                  <h3 className="text-xl font-bold text-white">{t('brandProfile.deleteLine')}</h3>
                </div>
                <p className="text-gray-300 mb-6">
                  {t('brandProfile.confirmDeleteLine', { name: deletingLine.name })}
                  <br />
                  <span className="text-gray-400 text-sm mt-2 block">{t('brandProfile.deleteLineNote')}</span>
                </p>
                <div className="flex justify-end space-x-3">
                  <button
                    onClick={() => setDeletingLine(null)}
                    disabled={deleteLineMutation.isPending}
                    className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all disabled:opacity-50"
                  >
                    {t('brandProfile.cancel')}
                  </button>
                  <button
                    onClick={() => deleteLineMutation.mutate(deletingLine.id)}
                    disabled={deleteLineMutation.isPending}
                    className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-xl transition-all disabled:opacity-50 flex items-center space-x-2"
                  >
                    {deleteLineMutation.isPending ? (
                      <><Loader2 className="w-4 h-4 animate-spin" /><span>{t('brandProfile.deleting')}</span></>
                    ) : (
                      <><Trash2 className="w-4 h-4" /><span>{t('brandProfile.delete')}</span></>
                    )}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Presets Tab */}
      {brandTab === 'presets' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h3 className="text-2xl font-bold text-white">{t('brandProfile.officialPresets')}</h3>
            <button
              onClick={handleCreatePreset}
              disabled={isLoadingPresets || filaments.length === 0}
              className="bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700 text-white px-4 py-2 rounded-xl transition-all shadow-lg shadow-green-500/25 hover:shadow-green-500/40 disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
              title={filaments.length === 0 ? t('brandProfile.createMaterialFirst') : ''}
            >
              <Plus className="w-4 h-4" />
              <span>{t('brandProfile.newPreset')}</span>
            </button>
          </div>

          {isLoadingPresets ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-gray-400" />
            </div>
          ) : brandPresets.length > 0 ? (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {brandPresets.map((preset) => (
                <div
                  key={preset.id}
                  className="bg-white/10 backdrop-blur-sm rounded-xl p-4 border border-white/20 hover:bg-white/15 transition-all cursor-pointer"
                  onClick={() => handleEditPreset(preset)}
                >
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1">
                      <h4 className="text-lg font-bold text-white mb-1">{preset.name}</h4>
                      {preset.description && (
                        <p className="text-gray-400 text-sm line-clamp-2">{preset.description}</p>
                      )}
                    </div>
                    {preset.is_official && (
                      <Shield className="w-5 h-5 text-green-400 flex-shrink-0 ml-2" />
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-sm mb-3">
                    <div className="flex items-center space-x-1">
                      <Thermometer className="w-4 h-4 text-red-400" />
                      <span className="text-gray-300">{t('brandProfile.nozzle')}: {preset.extruder_temp}°C</span>
                    </div>
                    <div className="flex items-center space-x-1">
                      <Thermometer className="w-4 h-4 text-red-400" />
                      <span className="text-gray-300">{t('brandProfile.bed')}: {preset.bed_temp}°C</span>
                    </div>
                    <div className="flex items-center space-x-1">
                      <Gauge className="w-4 h-4 text-blue-400" />
                      <span className="text-gray-300">{t('brandProfile.speed')}: {preset.print_speed}mm/s</span>
                    </div>
                    {preset.fan_speed !== null && (
                      <div className="flex items-center space-x-1">
                        <Fan className="w-4 h-4 text-green-400" />
                        <span className="text-gray-300">{t('brandProfile.fan')}: {preset.fan_speed}%</span>
                      </div>
                    )}
                  </div>
                  <div className="flex items-center justify-between text-xs text-gray-400">
                    <span>{new Date(preset.created_at).toLocaleDateString('ru-RU')}</span>
                    <div className="flex items-center space-x-2">
                      {/* Переключатель синхронизации - показываем для всех пресетов бренда */}
                      <PresetSyncToggle preset={preset} size="sm" className="p-1" />
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleEditPreset(preset);
                        }}
                        className="p-1 hover:bg-white/10 rounded transition-all"
                      >
                        <Edit className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-center py-12 bg-white/10 backdrop-blur-sm rounded-2xl border border-white/20">
              <Settings className="w-16 h-16 text-gray-400 mx-auto mb-4" />
              <p className="text-gray-400 text-xl mb-2">{t('brandProfile.noPresets')}</p>
              <p className="text-gray-500 text-sm">
                {filaments.length === 0
                  ? t('brandProfile.createMaterialFirst')
                  : t('brandProfile.createPresetForMaterial')}
              </p>
            </div>
          )}
        </div>
      )}

      {/* QR Codes Tab */}
      {brandTab === 'qr' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h3 className="text-2xl font-bold text-white">{t('brandProfile.qrCodes')}</h3>
          </div>

          <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
            {filaments.filter(f => f.qr_code).length > 0 ? (
              <div className="space-y-3">
                {filaments
                  .filter(f => f.qr_code)
                  .map((filament) => (
                    <QRCodeCard key={filament.id} filament={filament} />
                  ))}
              </div>
            ) : (
              <div className="text-center py-12">
                <QrCode className="w-16 h-16 text-gray-400 mx-auto mb-4" />
                <p className="text-gray-400 text-xl">{t('brandProfile.qrAutoCreated')}</p>
                <p className="text-gray-500 text-sm mt-2">{t('brandProfile.createMaterialForQR')}</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Analytics Tab */}
      {brandTab === 'analytics' && (
        <div className="space-y-6">
          <h3 className="text-2xl font-bold text-white">{t('brandProfile.materialAnalytics')}</h3>

          {/* Stats Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <StatCard
              icon={QrCode}
              label={t('brandProfile.totalScans')}
              value={totalScans.toString()}
              color="from-green-500/20 to-emerald-500/20"
              borderColor="border-green-500/30"
              iconColor="text-green-400"
            />
            <StatCard
              icon={Package}
              label={t('brandProfile.qrCodesCount')}
              value={filaments.filter(f => f.qr_code).length.toString()}
              color="from-blue-500/20 to-cyan-500/20"
              borderColor="border-blue-500/30"
              iconColor="text-blue-400"
            />
            <StatCard
              icon={Eye}
              label={t('brandProfile.materialsCount')}
              value={filaments.length.toString()}
              color="from-purple-500/20 to-pink-500/20"
              borderColor="border-purple-500/30"
              iconColor="text-purple-400"
            />
            <StatCard
              icon={TrendingUp}
              label={t('brandProfile.viewsCount')}
              value={totalViews.toString()}
              color="from-yellow-500/20 to-orange-500/20"
              borderColor="border-yellow-500/30"
              iconColor="text-yellow-400"
            />
          </div>

          {/* Materials Statistics */}
          <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
            <h3 className="text-xl font-bold text-white mb-4">{t('brandProfile.materialStats')}</h3>
            {filaments.length > 0 ? (
              <div className="space-y-3">
                {filaments.map((filament) => (
                  <MaterialStatCard key={filament.id} filament={filament} />
                ))}
              </div>
            ) : (
              <p className="text-gray-400 text-center py-8">{t('brandProfile.noData')}</p>
            )}
          </div>
        </div>
      )}

      {/* Usage Tab */}
      {brandTab === 'usage' && (
        <div className="space-y-6">
          <h3 className="text-2xl font-bold text-white">{t('brandProfile.usageAnalytics')}</h3>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <StatCard
              icon={Package}
              label={t('brandProfile.spoolsTracked')}
              value={(usageData?.spools_tracked ?? 0).toString()}
              color="from-green-500/20 to-emerald-500/20"
              borderColor="border-green-500/30"
              iconColor="text-green-400"
            />
            <StatCard
              icon={TrendingUp}
              label={t('brandProfile.presetUsage')}
              value={(usageData?.total_preset_usage ?? 0).toString()}
              color="from-purple-500/20 to-pink-500/20"
              borderColor="border-purple-500/30"
              iconColor="text-purple-400"
            />
            <StatCard
              icon={Package}
              label={t('brandProfile.presetsCount')}
              value={(usageData?.presets_count ?? 0).toString()}
              color="from-blue-500/20 to-cyan-500/20"
              borderColor="border-blue-500/30"
              iconColor="text-blue-400"
            />
          </div>

          <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
            <h3 className="text-xl font-bold text-white mb-4">{t('brandProfile.popularPrinters')}</h3>
            {usageData && usageData.popular_printers.length > 0 ? (
              <div className="space-y-3">
                {usageData.popular_printers.map((p) => {
                  const max = usageData.popular_printers[0].count || 1;
                  const pct = Math.round((p.count / max) * 100);
                  return (
                    <div key={p.printer_id} className="p-3 bg-white/5 rounded-xl">
                      <div className="flex justify-between mb-2">
                        <span className="text-white">{p.name}</span>
                        <span className="text-gray-400">{p.count}</span>
                      </div>
                      <div className="w-full bg-white/10 rounded-full h-2">
                        <div
                          className="bg-gradient-to-r from-purple-500 to-pink-500 h-2 rounded-full transition-all"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-gray-400 text-center py-8">{t('brandProfile.noData')}</p>
            )}
          </div>
        </div>
      )}

      {/* Create/Edit Filament Modal */}
      <CreateFilamentModal
        isOpen={isCreateFilamentModalOpen}
        onClose={handleCloseFilamentModal}
        filament={editingFilament}
        brandId={user.brand_id || undefined}
      />

      {/* Результат CSV-импорта */}
      {importResult && (
        <ModalOverlay onClose={() => setImportResult(null)}>
          <div className="bg-gray-900 rounded-2xl p-6 border border-white/20 max-w-lg w-full max-h-[80vh] overflow-y-auto">
            <h3 className="text-lg font-bold text-white mb-4">{t('brandProfile.importResultTitle')}</h3>
            <div className="flex gap-4 mb-4 text-sm">
              <span className="text-green-400">{t('brandProfile.importCreated')}: {importResult.created}</span>
              <span className="text-gray-400">{t('brandProfile.importSkipped')}: {importResult.skipped}</span>
              <span className="text-red-400">{t('brandProfile.importErrors')}: {importResult.errors}</span>
            </div>
            {importResult.rows.filter((r) => r.status !== 'created').length > 0 && (
              <div className="space-y-1 mb-4 text-xs">
                {importResult.rows.filter((r) => r.status !== 'created').map((r) => (
                  <div key={r.row} className={r.status === 'error' ? 'text-red-300' : 'text-gray-400'}>
                    {t('brandProfile.importRow')} {r.row}: {r.name || '—'} — {r.message ? translateApiError(t, { code: r.message }, r.message) : r.status}
                  </div>
                ))}
              </div>
            )}
            <button
              onClick={() => setImportResult(null)}
              className="w-full px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-xl transition-all"
            >
              {t('brandProfile.importClose')}
            </button>
          </div>
        </ModalOverlay>
      )}

      {/* Create Preset Modal */}
      <Suspense fallback={null}>
        <CreatePresetModal
          isOpen={isCreatePresetModalOpen}
          onClose={handleClosePresetModal}
          preset={editingPreset}
          brandId={user.brand_id || undefined}
        />
      </Suspense>

      {/* QR Code Modal */}
      {showQRFilament && showQRFilament.qr_code && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 rounded-2xl w-full max-w-lg overflow-hidden flex flex-col border border-white/20 shadow-2xl">
            {/* Header */}
            <div className="flex items-center justify-between p-6 border-b border-white/10">
              <div className="flex items-center space-x-3">
                <QrCode className="w-6 h-6 text-green-400" />
                <h2 className="text-2xl font-bold text-white">{t('brandProfile.materialQRCode')}</h2>
              </div>
              <button
                onClick={() => setShowQRFilament(null)}
                className="p-2 hover:bg-white/10 rounded-lg text-white transition-all"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Content */}
            <div className="p-6 bg-gradient-to-br from-green-500/20 to-emerald-500/20 border border-green-500/30 rounded-xl m-6">
              <div className="flex flex-col items-center space-y-4">
                {/* QR Code */}
                <div className="p-4 bg-white rounded-xl">
                  <img
                    src={qrAPI.getQRCodeURL(showQRFilament.id, 256)}
                    alt={`QR Code ${showQRFilament.qr_code}`}
                    className="w-64 h-64"
                  />
                </div>
                
                {/* QR Code Info */}
                <div className="text-center">
                  <p className="text-gray-300 text-sm mb-2">{t('brandProfile.code')}:</p>
                  <p className="text-white font-mono text-lg font-bold">{showQRFilament.qr_code}</p>
                  <p className="text-gray-400 text-sm mt-2">{showQRFilament.name}</p>
                </div>
                
                {/* Download Buttons */}
                <div className="flex flex-wrap gap-3 justify-center">
                  <button
                    onClick={() => qrAPI.downloadQRCode(showQRFilament.id, 300)}
                    className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-all flex items-center space-x-2"
                  >
                    <Download className="w-4 h-4" />
                    <span>300x300</span>
                  </button>
                  <button
                    onClick={() => qrAPI.downloadQRCode(showQRFilament.id, 600)}
                    className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-all flex items-center space-x-2"
                  >
                    <Download className="w-4 h-4" />
                    <span>600x600</span>
                  </button>
                  <button
                    onClick={() => qrAPI.downloadQRCode(showQRFilament.id, 1200)}
                    className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-all flex items-center space-x-2"
                  >
                    <Download className="w-4 h-4" />
                    <span>1200x1200</span>
                  </button>
                </div>
                
                {/* Copy Button */}
                <button
                  onClick={() => {
                    if (showQRFilament.qr_code) {
                      navigator.clipboard.writeText(showQRFilament.qr_code);
                      alert(t('brandProfile.codeCopied'));
                    }
                  }}
                  className="px-6 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-all flex items-center space-x-2"
                >
                  <Check className="w-4 h-4" />
                  <span>{t('brandProfile.copyCode')}</span>
                </button>
              </div>
            </div>

            {/* Close Button */}
            <div className="p-6 border-t border-white/10">
              <button
                onClick={() => setShowQRFilament(null)}
                className="w-full px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-xl transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40"
              >
                {t('brandProfile.close')}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Profile Modal */}
      {isEditingProfile && (
        <ModalOverlay onClose={() => setIsEditingProfile(false)}>
          <div className="bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 rounded-2xl w-full max-w-4xl max-h-[90vh] flex flex-col overflow-hidden border border-white/20 shadow-2xl">
            <div className="flex items-center justify-between p-6 border-b border-white/10 shrink-0">
              <div className="flex items-center space-x-3">
                <Edit className="w-6 h-6 text-purple-400" />
                <h2 className="text-2xl font-bold text-white">{t('brandProfile.editProfile')}</h2>
              </div>
              <button onClick={() => setIsEditingProfile(false)} className="text-gray-400 hover:text-white transition-colors">
                <X className="w-6 h-6" />
              </button>
            </div>
            <div className="p-6 space-y-4 flex-1 overflow-y-auto">
              {profileError && (
                <div className="p-3 bg-red-500/20 border border-red-500/30 rounded-lg text-red-300 text-sm">
                  {profileError}
                </div>
              )}
              <div className="grid md:grid-cols-2 gap-5">
              <div className="space-y-4">
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('brandProfile.descriptionLabel')}</label>
                <textarea
                  value={profileDescription}
                  onChange={(e) => setProfileDescription(e.target.value)}
                  rows={3}
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all resize-none"
                  placeholder={t('brandProfile.descriptionPlaceholder')}
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('brandProfile.websiteLabel')}</label>
                <input
                  type="url"
                  value={profileWebsite}
                  onChange={(e) => setProfileWebsite(e.target.value)}
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                  placeholder="https://example.com"
                />
              </div>
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('brandProfile.logoUrlLabel')}</label>
                <div className="flex gap-2">
                  <input
                    type="url"
                    value={profileLogoUrl}
                    onChange={(e) => setProfileLogoUrl(e.target.value)}
                    className="flex-1 px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent transition-all"
                    placeholder="https://example.com/logo.png"
                  />
                  <label className="px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-gray-300 hover:text-white hover:bg-white/20 cursor-pointer transition-all flex items-center gap-2 whitespace-nowrap">
                    {isUploadingLogo ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                    <span className="text-sm">{t('brandProfile.uploadLogo')}</span>
                    <input
                      type="file"
                      accept=".png,.jpg,.jpeg,.webp,.svg"
                      onChange={handleLogoUpload}
                      className="hidden"
                      disabled={isUploadingLogo}
                    />
                  </label>
                </div>
                {profileLogoUrl && (
                  <div className="mt-2 flex items-center space-x-3">
                    <img
                      src={profileLogoUrl}
                      alt="Logo preview"
                      className="w-12 h-12 rounded-lg object-contain bg-white/5"
                      onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                    />
                    <span className="text-gray-500 text-xs">{t('brandProfile.logoPreview')}</span>
                  </div>
                )}
                <div className="mt-3">
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{t('brandProfile.logoBgLabel')}</label>
                  <div className="flex items-center gap-3">
                    <HSLColorPicker
                      color={profileLogoBg || '#ffffff'}
                      onChange={(hex) => setProfileLogoBg(hex)}
                      isOpen={logoBgPickerOpen}
                      onToggle={setLogoBgPickerOpen}
                    />
                    <span className="text-sm font-mono text-gray-400">{profileLogoBg || t('brandProfile.logoBgDefault')}</span>
                    {profileLogoBg && (
                      <button
                        type="button"
                        onClick={() => setProfileLogoBg('')}
                        className="ml-auto px-3 py-2 bg-white/10 border border-white/20 rounded-xl text-gray-300 hover:text-white hover:bg-white/20 transition-all text-sm whitespace-nowrap"
                      >
                        {t('brandProfile.logoBgReset')}
                      </button>
                    )}
                  </div>
                  {profileLogoUrl && (
                    <div
                      className="mt-2 inline-flex h-16 w-16 items-center justify-center overflow-hidden rounded-xl border border-white/10 p-0.5"
                      style={profileLogoBg ? { backgroundColor: profileLogoBg } : { backgroundColor: 'rgba(255,255,255,0.1)' }}
                    >
                      <img
                        src={profileLogoUrl}
                        alt="Logo on background"
                        className="block h-full w-auto object-contain"
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none'; }}
                      />
                    </div>
                  )}
                  <p className="text-gray-500 text-xs mt-1">{t('brandProfile.logoBgHint')}</p>
                </div>
              </div>
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('brandProfile.socialMediaLabel')}</label>
                <div className="space-y-2">
                  {profileSocialUrls.map((url, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <span className="shrink-0 w-9 h-9 flex items-center justify-center rounded-lg bg-white/5 border border-white/10 text-gray-300">
                        <SocialIcon url={url} className="w-4 h-4" />
                      </span>
                      <input
                        type="url"
                        value={url}
                        onChange={(e) => setProfileSocialUrls(profileSocialUrls.map((u, j) => (j === i ? e.target.value : u)))}
                        placeholder="https://..."
                        className="flex-1 px-4 py-2.5 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                      />
                      <button type="button" onClick={() => setProfileSocialUrls(profileSocialUrls.filter((_, j) => j !== i))} className="px-3 bg-white/10 hover:bg-red-500/20 rounded-xl text-gray-300 transition-all">
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                  <button type="button" onClick={() => setProfileSocialUrls([...profileSocialUrls, ''])} className="text-sm text-purple-300 hover:text-purple-200">+ {t('brandProfile.addLink')}</button>
                </div>
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('brandProfile.shopLinksLabel')}</label>
                <div className="space-y-2">
                  {profileShopLinks.map((link, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <span className="shrink-0 w-9 h-9 flex items-center justify-center rounded-lg bg-white/5 border border-white/10 text-gray-300">
                        <SocialIcon url={link.url} className="w-4 h-4" />
                      </span>
                      <input
                        type="text"
                        value={link.platform}
                        onChange={(e) => setProfileShopLinks(profileShopLinks.map((l, j) => (j === i ? { ...l, platform: e.target.value } : l)))}
                        placeholder={t('brandProfile.shopPlatformPlaceholder')}
                        className="w-28 px-3 py-2.5 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                      />
                      <input
                        type="url"
                        value={link.url}
                        onChange={(e) => setProfileShopLinks(profileShopLinks.map((l, j) => (j === i ? { ...l, url: e.target.value } : l)))}
                        placeholder="https://..."
                        className="flex-1 px-4 py-2.5 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                      />
                      <button type="button" onClick={() => setProfileShopLinks(profileShopLinks.filter((_, j) => j !== i))} className="px-3 bg-white/10 hover:bg-red-500/20 rounded-xl text-gray-300 transition-all">
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ))}
                  <button type="button" onClick={() => setProfileShopLinks([...profileShopLinks, { platform: '', url: '' }])} className="text-sm text-purple-300 hover:text-purple-200">+ {t('brandProfile.addShop')}</button>
                </div>
              </div>
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={profilePriceHidden}
                  onChange={(e) => setProfilePriceHidden(e.target.checked)}
                  className="w-4 h-4 rounded border-white/20 bg-white/10 text-purple-500 focus:ring-purple-500"
                />
                <span className="text-gray-300 text-sm font-medium">{t('brandProfile.priceHiddenLabel')}</span>
              </label>
            </div>
            <div className="p-6 border-t border-white/10 flex justify-end space-x-3 shrink-0">
              <button
                onClick={() => setIsEditingProfile(false)}
                className="px-6 py-2.5 text-gray-300 hover:text-white hover:bg-white/10 rounded-xl transition-all"
              >
                {t('brandProfile.cancel')}
              </button>
              <button
                onClick={handleSaveProfile}
                disabled={updateBrandMutation.isPending}
                className="px-6 py-2.5 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-xl transition-all shadow-lg shadow-purple-500/25 flex items-center space-x-2 disabled:opacity-50"
              >
                {updateBrandMutation.isPending ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Check className="w-4 h-4" />
                )}
                <span>{t('brandProfile.save')}</span>
              </button>
            </div>
          </div>
        </ModalOverlay>
      )}
    </div>
  );
};

/** Форма выбора/создания бренда */
const BrandSelectionForm: React.FC = () => {
  const { t } = useTranslation();
  const { user, refreshUser } = useAuth();
  const queryClient = useQueryClient();
  const [selectedBrandId, setSelectedBrandId] = useState<number | null>(null);
  const [brandSearch, setBrandSearch] = useState(''); // Поиск бренда
  const [isCreatingNew, setIsCreatingNew] = useState(false);
  const [submittedRequest, setSubmittedRequest] = useState<BrandRequest | null>(null); // Отправленная заявка
  const [newBrandName, setNewBrandName] = useState('');
  const [newBrandSlug, setNewBrandSlug] = useState('');
  const [slugManuallyEdited, setSlugManuallyEdited] = useState(false); // Отслеживаем, редактировал ли пользователь slug вручную
  const [newBrandDescription, setNewBrandDescription] = useState('');
  // Структурированные поля для подтверждающих документов
  // Автоматически заполняем email компании из email пользователя
  const [companyEmail, setCompanyEmail] = useState(user?.email || '');
  const [companyWebsite, setCompanyWebsite] = useState('');
  const [socialMediaUrls, setSocialMediaUrls] = useState<string[]>([]);
  const [socialMediaInput, setSocialMediaInput] = useState(''); // Временный input для добавления ссылки
  const [proofText, setProofText] = useState(''); // Описание подтверждающих документов
  const [message, setMessage] = useState(''); // Дополнительное сообщение
  const [error, setError] = useState<string | null>(null);
  // Файлы для загрузки (локально перед отправкой заявки)
  const [localFiles, setLocalFiles] = useState<File[]>([]);
  // Чекбокс для подтверждения достоверности данных (обязательный)
  const [confirmAccuracy, setConfirmAccuracy] = useState(false); // Подтверждение достоверности данных
  
  // Загружаем мои заявки
  const { data: myRequests, refetch: refetchRequests } = useQuery({
    queryKey: ['brand-requests', 'my'],
    queryFn: () => brandRequestsAPI.getMy(),
  });

  // При загрузке страницы, если есть pending заявка - показываем её
  useEffect(() => {
    if (myRequests && myRequests.length > 0 && !submittedRequest) {
      const pendingRequest = myRequests.find((r) => r.status === 'pending');
      if (pendingRequest) {
        setSubmittedRequest(pendingRequest);
      }
    }
  }, [myRequests, submittedRequest]);

  // Загружаем список брендов с поиском (все бренды)
  const { data: brandsData, isLoading: _isLoadingBrands } = useQuery({
    queryKey: ['brands', 'selection', { search: brandSearch }],
    queryFn: () => brandsAPI.list({ active_only: true, page: 1, size: 100, search: brandSearch || undefined }),
  });

  // Все бренды для выбора
  const allBrands = brandsData?.items || [];

  // Находим выбранный бренд для отображения
  const selectedBrand = selectedBrandId ? allBrands.find((b: Brand) => b.id === selectedBrandId) : null;
  
  // Загружаем информацию о выбранном бренде с количеством сотрудников
  const { data: selectedBrandInfo } = useQuery({
    queryKey: ['brand', selectedBrandId, 'employees'],
    queryFn: () => brandsAPI.get(selectedBrandId!, true),
    enabled: !!selectedBrandId,
  });
  
  // Определяем, есть ли у выбранного бренда сотрудники
  const hasEmployees = selectedBrandInfo?.employees_count ? selectedBrandInfo.employees_count > 0 : false;

  // Мутация для создания заявки на создание бренда
  const createRequestMutation = useMutation({
    mutationFn: async (data: {
      request_type: 'create' | 'join';
      brand_id?: number;
      new_brand_name?: string;
      new_brand_slug?: string;
      new_brand_description?: string;
      new_brand_website?: string;
      message?: string;
      company_email?: string;
      company_website?: string;
      social_media_urls?: string[];
      proof_text: string;
      files?: File[]; // Файлы для загрузки после создания заявки
    }) => {
      // Сначала создаем заявку (убираем files из API вызова)
      const { files, ...requestData } = data;
      const request = await brandRequestsAPI.create(requestData);
      
      // Затем загружаем файлы если есть
      if (files && files.length > 0 && request.id) {
        try {
          for (const file of files) {
            await brandRequestsAPI.uploadFile(request.id, file);
          }
          // Обновляем заявку после загрузки файлов
          const updatedRequest = await brandRequestsAPI.get(request.id);
          return updatedRequest;
        } catch (uploadError: any) {
          // Если загрузка файлов не удалась, все равно возвращаем заявку
          // (файлы можно загрузить позже через UI)
          console.error('Error uploading files:', uploadError);
          // Возвращаем заявку без файлов - пользователь сможет загрузить их позже
          return request;
        }
      }
      
      return request;
    },
    onSuccess: async (newRequest) => {
      queryClient.invalidateQueries({ queryKey: ['brands'] });
      queryClient.invalidateQueries({ queryKey: ['brand-requests'] });
      // Показываем статус отправленной заявки
      setSubmittedRequest(newRequest);
      setIsCreatingNew(false);
      setSelectedBrandId(null);
      setBrandSearch('');
      setNewBrandName('');
      setNewBrandSlug('');
      setSlugManuallyEdited(false); // Сбрасываем флаг при очистке формы
      setNewBrandDescription('');
      setCompanyEmail('');
      setCompanyWebsite('');
      setSocialMediaUrls([]);
      setSocialMediaInput('');
      setProofText('');
      setMessage('');
      setLocalFiles([]);
      setConfirmAccuracy(false);
      // Для JOIN заявок не очищаем поля при успехе, так как они не используются
      refetchRequests();
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      setError(translateApiError(t, err.response?.data?.detail, t('brandProfile.errorSubmitRequest')));
    },
  });

  // Мутация для отзыва заявки
  const cancelRequestMutation = useMutation({
    mutationFn: (id: number) => brandRequestsAPI.cancel(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['brand-requests'] });
      refetchRequests();
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      alert(translateApiError(t, err.response?.data?.detail, t('brandProfile.errorCancelRequest')));
    },
  });

  // Мутация для загрузки файла
  const uploadFileMutation = useMutation({
    mutationFn: ({ requestId, file }: { requestId: number; file: File }) =>
      brandRequestsAPI.uploadFile(requestId, file),
    onSuccess: async (updatedRequest) => {
      // Сразу обновляем submittedRequest данными из ответа (самые свежие данные)
      if (submittedRequest && updatedRequest.id === submittedRequest.id) {
        setSubmittedRequest(updatedRequest);
      }
      // Инвалидируем кэш для обновления списка заявок
      queryClient.invalidateQueries({ queryKey: ['brand-requests'] });
      // Обновляем список заявок в фоне, но не перезаписываем submittedRequest если данные уже актуальны
      await refetchRequests();
      // Обновляем submittedRequest только если его еще нет или он устарел
      if (submittedRequest && updatedRequest.id === submittedRequest.id) {
        // Используем данные из updatedRequest (они самые свежие после загрузки)
        // Не перезаписываем их данными из refetch, чтобы избежать дублирования
      }
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      setError(translateApiError(t, err.response?.data?.detail, t('brandProfile.errorUploadFile')));
    },
  });

  // Мутация для удаления файла
  const deleteFileMutation = useMutation({
    mutationFn: ({ requestId, filePath }: { requestId: number; filePath: string }) =>
      brandRequestsAPI.deleteFile(requestId, filePath),
    onSuccess: async (updatedRequest) => {
      // Сразу обновляем submittedRequest данными из ответа
      if (submittedRequest && updatedRequest.id === submittedRequest.id) {
        setSubmittedRequest(updatedRequest);
      }
      // Инвалидируем кэш для обновления списка заявок
      queryClient.invalidateQueries({ queryKey: ['brand-requests'] });
      // Обновляем список заявок в фоне
      refetchRequests();
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      alert(translateApiError(t, err.response?.data?.detail, t('brandProfile.errorDeleteFile')));
    },
  });

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!submittedRequest || submittedRequest.status !== 'pending') {
      return;
    }
    const file = e.target.files?.[0];
    if (!file) {
      return;
    }
    // Проверяем расширение файла
    const allowedExtensions = ['.pdf', '.jpg', '.jpeg', '.png', '.doc', '.docx'];
    const fileExt = '.' + file.name.split('.').pop()?.toLowerCase();
    if (!allowedExtensions.includes(fileExt)) {
      setError(t('brandProfile.errorAllowedFiles', { types: allowedExtensions.join(', ') }));
      return;
    }
    // Проверяем размер (50 MB)
    if (file.size > 50 * 1024 * 1024) {
      setError(t('brandProfile.errorFileSize'));
      return;
    }
    setError(null);
    await uploadFileMutation.mutateAsync({ requestId: submittedRequest.id, file });
    e.target.value = ''; // Сбрасываем input
  };

  // Обработчик выбора файлов для формы JOIN (если у бренда нет сотрудников)
  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    const allowedExtensions = ['.pdf', '.jpg', '.jpeg', '.png', '.doc', '.docx'];
    const validFiles = files.filter((file) => {
      const fileExt = '.' + file.name.split('.').pop()?.toLowerCase();
      return allowedExtensions.includes(fileExt) && file.size <= 50 * 1024 * 1024;
    });
    
    if (validFiles.length !== files.length) {
      setError(t('brandProfile.errorSomeFilesRejected'));
    } else {
      setError(null);
    }
    
    if (localFiles.length + validFiles.length > 10) {
      setError(t('brandProfile.errorMaxFiles'));
      return;
    }
    
    setLocalFiles([...localFiles, ...validFiles]);
    e.target.value = ''; // Сбрасываем input
  };

  // Нормализация URL сайта: убрать http/https/www., оставить только домен
  const normalizeWebsiteUrl = (website: string | null): string | null => {
    if (!website) return null;
    try {
      // Если нет протокола, добавляем http:// для парсинга
      let url = website.trim();
      if (!url.startsWith('http://') && !url.startsWith('https://')) {
        url = `http://${url}`;
      }
      
      const urlObj = new URL(url);
      let domain = urlObj.hostname.toLowerCase();
      
      // Убираем www.
      domain = domain.replace(/^www\./, '');
      
      // Убираем порт если есть
      if (domain.includes(':')) {
        domain = domain.split(':')[0];
      }
      
      return domain || null;
    } catch {
      return null;
    }
  };

  // Проверка является ли email корпоративным (домен совпадает с сайтом)
  const isCorporateEmail = (email: string, website: string | null): boolean => {
    if (!email || !website) return false;
    try {
      const emailDomain = email.split('@')[1]?.toLowerCase();
      if (!emailDomain) return false;
      
      const websiteDomain = normalizeWebsiteUrl(website);
      if (!websiteDomain) return false;
      
      return emailDomain === websiteDomain;
    } catch {
      return false;
    }
  };

  // Проверка является ли email личным (из белого списка популярных почтовых сервисов)
  const isPersonalEmail = (email: string): boolean => {
    if (!email || !email.includes('@')) return false;
    const emailDomain = email.split('@')[1]?.toLowerCase();
    if (!emailDomain) return false;
    
    // Личные почтовые домены — единый источник: data/personalEmailDomains.ts
    return (PERSONAL_EMAIL_DOMAINS as readonly string[]).includes(emailDomain);
  };

  const handleCreateBrandRequest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newBrandName.trim() || !newBrandSlug.trim()) {
      setError(t('brandProfile.errorFillNameAndSlug'));
      return;
    }
    // Проверяем обязательное подтверждение достоверности данных
    if (!confirmAccuracy) {
      setError(t('brandProfile.errorConfirmAccuracy'));
      return;
    }
    
    // Проверяем корпоративность email
    const userEmail = user?.email || '';
    const isCorporate = isCorporateEmail(companyEmail || userEmail, companyWebsite);
    
    // Если email указан И не корпоративный → документы и описание обязательны
    if (companyEmail && !isCorporate) {
      if (!proofText.trim()) {
        setError(t('brandProfile.errorDescribeProofDocs'));
        return;
      }
      if (localFiles.length === 0) {
        setError(t('brandProfile.errorAttachProofDocs'));
        return;
      }
    }
    setError(null);
    await createRequestMutation.mutateAsync({
      request_type: 'create',
      new_brand_name: newBrandName.trim(),
      new_brand_slug: newBrandSlug.trim().toLowerCase().replace(/\s+/g, '-'),
      new_brand_description: newBrandDescription.trim() || undefined,
      new_brand_website: companyWebsite.trim() || undefined, // Используем company_website из блока "Информация о компании"
      message: message.trim() || undefined,
      company_email: companyEmail.trim() || undefined,
      company_website: companyWebsite.trim() || undefined,
      social_media_urls: socialMediaUrls.length > 0 ? socialMediaUrls : undefined,
      proof_text: proofText.trim(),
      files: localFiles.length > 0 ? localFiles : undefined,
    });
  };

  const handleJoinBrandRequest = async () => {
    if (!selectedBrandId) {
      setError(t('brandProfile.errorSelectBrand'));
      return;
    }
    // Проверяем обязательное подтверждение достоверности данных
    if (!confirmAccuracy) {
      setError(t('brandProfile.errorConfirmAccuracy'));
      return;
    }
    
    // Если бренд не верифицирован ИЛИ у бренда нет сотрудников - требуем полную заявку как для CREATE
    if (!selectedBrand?.verified || !hasEmployees) {
      // Проверяем корпоративность email
      const userEmail = user?.email || '';
      const isCorporate = isCorporateEmail(companyEmail || userEmail, companyWebsite);
      
      // Если email указан И не корпоративный → документы и описание обязательны
      if (companyEmail && !isCorporate) {
        if (!proofText.trim()) {
          setError(t('brandProfile.errorDescribeProofDocs'));
          return;
        }
        if (localFiles.length === 0) {
          setError(t('brandProfile.errorAttachProofDocsShort'));
          return;
        }
      }
      
      // Если требуются документы → описание обязательно
      if (!proofText.trim()) {
        setError(t('brandProfile.errorProofRequired'));
        return;
      }
    }
    
    setError(null);
    await createRequestMutation.mutateAsync({
      request_type: 'join',
      brand_id: selectedBrandId,
      message: message.trim() || undefined,
      company_email: companyEmail.trim() || undefined,
      company_website: companyWebsite.trim() || undefined,
      social_media_urls: socialMediaUrls.length > 0 ? socialMediaUrls : undefined,
      // Если у бренда нет сотрудников - требуем полную заявку с документами
      proof_text: hasEmployees ? (message.trim() || 'Brand join request') : proofText.trim(),
      files: hasEmployees ? undefined : (localFiles.length > 0 ? localFiles : undefined),
    });
  };

  const generateSlug = (name: string) => {
    return name
      .toLowerCase()
      .replace(/\s+/g, '-')
      .replace(/[^a-z0-9-]/g, '');
  };

  // Функция для валидации и очистки slug при вводе
  const sanitizeSlug = (input: string): string => {
    // Разрешаем только латиницу, цифры и дефисы
    // Убираем пробелы, спецсимволы, кириллицу и т.д.
    return input
      .toLowerCase()
      .replace(/\s+/g, '-')  // Пробелы → дефисы
      .replace(/[^a-z0-9-]/g, ''); // Удаляем всё кроме латиницы, цифр и дефисов
  };

  // Если показываем статус отправленной заявки
  if (submittedRequest) {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-8 border border-white/20 shadow-xl">
          <div className="text-center mb-8">
            <div className="w-20 h-20 bg-gradient-to-r from-yellow-500 to-orange-500 rounded-xl flex items-center justify-center mx-auto mb-4 shadow-lg shadow-yellow-500/25">
              <Shield className="w-10 h-10 text-white" />
            </div>
            <h2 className="text-2xl font-bold text-white mb-2">
              {submittedRequest.request_type === 'create' ? t('brandProfile.requestCreateSent') : t('brandProfile.requestJoinSent')}
            </h2>
            <p className="text-gray-300">
              {submittedRequest.request_type === 'create' 
                ? t('brandProfile.requestCreateDescription', { name: submittedRequest.new_brand_name })
                : t('brandProfile.requestJoinDescription')}
            </p>
          </div>

          <div className="bg-yellow-500/20 border border-yellow-500/50 rounded-xl p-6 mb-6">
            <div className="flex items-start space-x-4">
              <Shield className="w-6 h-6 text-yellow-400 flex-shrink-0 mt-0.5" />
              <div>
                <h3 className="text-lg font-semibold text-yellow-300 mb-2">{t('brandProfile.awaitingReview')}</h3>
                <p className="text-yellow-200 text-sm">
                  {t('brandProfile.awaitingReviewDescription')}
                </p>
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <div className="bg-white/5 rounded-xl p-4 border border-white/10">
              <h4 className="text-white font-medium mb-3">{t('brandProfile.requestDetails')}:</h4>
              <div className="space-y-3 text-sm">
                <div>
                  <span className="text-gray-400">{t('brandProfile.status')}: </span>
                  <span className={`font-medium ${
                    submittedRequest.status === 'pending' ? 'text-yellow-400' :
                    submittedRequest.status === 'approved' ? 'text-green-400' :
                    'text-red-400'
                  }`}>
                    {submittedRequest.status === 'pending' ? t('brandProfile.statusPending') :
                     submittedRequest.status === 'approved' ? t('brandProfile.statusApproved') :
                     t('brandProfile.statusRejected')}
                  </span>
                </div>
                
                {submittedRequest.request_type === 'create' && submittedRequest.new_brand_name && (
                  <>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <span className="text-gray-400">{t('brandProfile.name')}: </span>
                        <span className="text-white font-medium">{submittedRequest.new_brand_name}</span>
                      </div>
                      {submittedRequest.new_brand_slug && (
                        <div>
                          <span className="text-gray-400">Slug: </span>
                          <span className="text-white font-mono">{submittedRequest.new_brand_slug}</span>
                        </div>
                      )}
                    </div>
                    {submittedRequest.new_brand_description && (
                      <div className="flex flex-col">
                        <span className="text-gray-400 mb-1">{t('brandProfile.brandDescription')}:</span>
                        <span className="text-white text-xs bg-white/5 rounded-lg p-2">{submittedRequest.new_brand_description}</span>
                      </div>
                    )}
                  </>
                )}

                {submittedRequest.request_type === 'join' && submittedRequest.brand_id && (
                  <div>
                    <span className="text-gray-400">{t('brandProfile.brand')}: </span>
                    <span className="text-white font-medium">
                      {submittedRequest.brand_name || `${t('brandProfile.brand')} #${submittedRequest.brand_id}`}
                    </span>
                  </div>
                )}

                {/* Email и сайт компании в одну строку */}
                {(submittedRequest.company_email || submittedRequest.company_website) && (
                  <div className="grid grid-cols-2 gap-4">
                    {submittedRequest.company_email && (
                      <div>
                        <span className="text-gray-400">{t('brandProfile.yourEmail')}: </span>
                        <span className="text-white">{submittedRequest.company_email}</span>
                      </div>
                    )}
                    {submittedRequest.company_website && (
                      <div>
                        <span className="text-gray-400">{t('brandProfile.companyWebsite')}: </span>
                        {(() => {
                          const websiteUrl = submittedRequest.company_website.startsWith('http://') || submittedRequest.company_website.startsWith('https://')
                            ? submittedRequest.company_website
                            : `https://${submittedRequest.company_website}`;
                          return (
                            <a
                              href={websiteUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-purple-400 hover:text-purple-300 underline"
                            >
                              {submittedRequest.company_website}
                            </a>
                          );
                        })()}
                      </div>
                    )}
                  </div>
                )}

                {submittedRequest.social_media_urls && submittedRequest.social_media_urls.length > 0 && (
                  <div className="flex flex-col">
                    <span className="text-gray-400 mb-2">{t('brandProfile.socialMedia')}:</span>
                    <div className="flex flex-wrap gap-2">
                      {submittedRequest.social_media_urls.map((url, index) => {
                        const fullUrl = url.startsWith('http://') || url.startsWith('https://') 
                          ? url 
                          : `https://${url}`;
                        return (
                          <a
                            key={index}
                            href={fullUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="px-2 py-1 bg-white/10 rounded-lg border border-white/20 text-purple-400 hover:text-purple-300 hover:bg-white/15 transition-all text-xs"
                          >
                            {url}
                          </a>
                        );
                      })}
                    </div>
                  </div>
                )}

                {submittedRequest.message && (
                  <div className="flex flex-col">
                    <span className="text-gray-400 mb-1">{t('brandProfile.message')}:</span>
                    <span className="text-white text-xs bg-white/5 rounded-lg p-2">{submittedRequest.message}</span>
                  </div>
                )}

                {submittedRequest.proof_text && (
                  <div className="flex flex-col">
                    <span className="text-gray-400 mb-1">{t('brandProfile.proofDocsDescription')}:</span>
                    <span className="text-white text-xs bg-white/5 rounded-lg p-2">{submittedRequest.proof_text}</span>
                  </div>
                )}
              </div>
            </div>

            {/* Загрузка файлов */}
            {submittedRequest.status === 'pending' && (
              <div className="bg-white/5 rounded-xl p-4 border border-white/10">
                <h4 className="text-white font-medium mb-3 flex items-center">
                  <Paperclip className="w-4 h-4 mr-2 text-green-400" />
                  {t('brandProfile.attachedFiles')}
                </h4>
                {submittedRequest.proof_files && submittedRequest.proof_files.length > 0 && (
                  <div className="space-y-3 mb-4">
                    {/* Убираем дубликаты по пути файла */}
                    {Array.from(
                      new Map(
                        submittedRequest.proof_files.map((fileInfo) => {
                          const filePath = typeof fileInfo === 'string' ? fileInfo : fileInfo.path;
                          return [filePath, fileInfo];
                        })
                      ).values()
                    ).map((fileInfo, index) => {
                      // Поддержка старого формата (строка) и нового (объект)
                      let filePath: string;
                      let fileName: string;
                      
                      if (typeof fileInfo === 'string') {
                        // Старый формат: строка с путем (для обратной совместимости)
                        filePath = fileInfo as string;
                        const parts = filePath.split('/');
                        fileName = parts[parts.length - 1] || `${t('brandProfile.file')} ${index + 1}`;
                      } else if (fileInfo && typeof fileInfo === 'object' && 'path' in fileInfo) {
                        // Новый формат: объект с path и name
                        filePath = fileInfo.path;
                        const pathParts = filePath.split('/');
                        fileName = fileInfo.name || pathParts[pathParts.length - 1] || `${t('brandProfile.file')} ${index + 1}`;
                      } else {
                        // Fallback на случай неожиданного формата
                        filePath = '';
                        fileName = `${t('brandProfile.file')} ${index + 1}`;
                      }
                      
                      // Формируем URL для доступа к файлу (auth через query token)
                      // filePath уже в формате "brand_requests/5/file.jpg"
                      const accessToken = localStorage.getItem('access_token');
                      const fileUrl = `/api/v1/uploads/${filePath}${accessToken ? `?token=${accessToken}` : ''}`;
                      
                      return (
                        <div
                          key={index}
                          className="bg-white/5 rounded-lg p-3 border border-white/10"
                        >
                          <div className="flex items-center justify-between">
                            <a
                              href={fileUrl}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="flex items-center space-x-2 text-green-400 hover:text-green-300 flex-1 min-w-0"
                            >
                              <FileText className="w-4 h-4 flex-shrink-0" />
                              <span className="truncate" title={fileName}>{fileName}</span>
                            </a>
                            <button
                              onClick={() => {
                                if (confirm(t('brandProfile.confirmDeleteFile'))) {
                                  deleteFileMutation.mutate({
                                    requestId: submittedRequest.id,
                                    filePath: filePath, // Используем путь для удаления
                                  });
                                }
                              }}
                              disabled={deleteFileMutation.isPending}
                              className="ml-2 p-1 text-red-400 hover:text-red-300 transition-colors disabled:opacity-50 flex-shrink-0"
                              title={t('brandProfile.deleteFile')}
                            >
                              <XCircle className="w-4 h-4" />
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
                <div className="flex items-center space-x-2">
                  <label className="flex-1 cursor-pointer">
                    <input
                      type="file"
                      onChange={handleFileUpload}
                      accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
                      disabled={uploadFileMutation.isPending}
                      className="hidden"
                    />
                    <div className="flex items-center justify-center space-x-2 px-4 py-2 bg-green-600/20 hover:bg-green-600/30 border border-green-500/50 rounded-lg text-green-300 transition-all disabled:opacity-50 disabled:cursor-not-allowed">
                      {uploadFileMutation.isPending ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          <span className="text-sm">{t('brandProfile.uploading')}</span>
                        </>
                      ) : (
                        <>
                          <Paperclip className="w-4 h-4" />
                          <span className="text-sm">{t('brandProfile.attachFile')}</span>
                        </>
                      )}
                    </div>
                  </label>
                </div>
                <p className="text-xs text-gray-400 mt-2">
                  {t('brandProfile.allowedFormats')}
                </p>
              </div>
            )}

            <div className="flex space-x-4 pt-4">
              <button
                onClick={() => {
                  setSubmittedRequest(null);
                  refreshUser(); // Обновляем пользователя на случай если заявка уже одобрена
                  refetchRequests();
                }}
                className="flex-1 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white px-6 py-3 rounded-xl transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 flex items-center justify-center"
              >
                <CheckCircle className="w-5 h-5 mr-2" />
                {t('brandProfile.refreshStatus')}
              </button>
              {submittedRequest.status === 'pending' && (
                <button
                  onClick={() => {
                    if (confirm(t('brandProfile.confirmCancelRequest'))) {
                      cancelRequestMutation.mutate(submittedRequest.id);
                      setSubmittedRequest(null);
                    }
                  }}
                  disabled={cancelRequestMutation.isPending}
                  className="px-6 py-3 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {cancelRequestMutation.isPending ? t('brandProfile.cancelling') : t('brandProfile.cancelRequest')}
                </button>
              )}
            </div>

            <p className="text-center text-gray-400 text-xs mt-4">
              {t('brandProfile.afterVerificationNotice')}
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (isCreatingNew) {
    return (
      <div className="max-w-2xl mx-auto">
        <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-8 border border-white/20 shadow-xl">
          <div className="flex items-center justify-between mb-6">
            <h2 className="text-2xl font-bold text-white flex items-center">
              <Factory className="w-6 h-6 mr-3 text-green-400" />
              {t('brandProfile.createNewBrand')}
            </h2>
            <button
              onClick={() => {
                setIsCreatingNew(false);
                setError(null);
              }}
              className="p-2 bg-white/10 hover:bg-white/20 rounded-lg text-white transition-all"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          {error && (
            <div className="mb-4 p-4 bg-red-500/20 border border-red-500/50 rounded-xl text-red-300">
              {error}
            </div>
          )}

          <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4 mb-4">
            <div className="flex items-start space-x-3">
              <Shield className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
              <div className="flex-1">
                <h3 className="text-sm font-semibold text-blue-300 mb-1">{t('brandProfile.verificationProcess')}</h3>
                <p className="text-xs text-blue-200">
                {t('brandProfile.verificationDescription')}</p>
              </div>
            </div>
          </div>

          <form onSubmit={handleCreateBrandRequest} className="space-y-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">
                {t('brandProfile.brandName')} *
              </label>
              <input
                type="text"
                value={newBrandName}
                onChange={(e) => {
                  setNewBrandName(e.target.value);
                  // Автоматически обновляем slug только если пользователь не редактировал его вручную
                  if (!slugManuallyEdited) {
                    setNewBrandSlug(generateSlug(e.target.value));
                  }
                }}
                required
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent transition-all"
                placeholder="ThermPlast"
              />
            </div>

            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Slug *</label>
              <input
                type="text"
                value={newBrandSlug}
                onChange={(e) => {
                  // Автоматически фильтруем запрещенные символы
                  const sanitized = sanitizeSlug(e.target.value);
                  setNewBrandSlug(sanitized);
                  setSlugManuallyEdited(true); // Помечаем, что пользователь редактирует slug вручную
                }}
                required
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent transition-all"
                placeholder="thermplast"
              />
              <p className="mt-1 text-xs text-gray-400">
                {t('brandProfile.slugHint')}
              </p>
            </div>

            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">
                {t('brandProfile.descriptionOptional')}
              </label>
              <textarea
                value={newBrandDescription}
                onChange={(e) => setNewBrandDescription(e.target.value)}
                rows={3}
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent transition-all resize-none"
                placeholder={t('brandProfile.descriptionPlaceholder')}
              />
            </div>

            {/* Контактная информация */}
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">
                    {t('brandProfile.companyEmail')}
                  </label>
                  <div className="space-y-1">
                    <input
                      type="email"
                      value={companyEmail}
                      onChange={(e) => setCompanyEmail(e.target.value)}
                      className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent transition-all"
                      placeholder="info@thermplast.ru"
                    />
                    {user?.email && user.email !== companyEmail && (
                      <button
                        type="button"
                        onClick={() => setCompanyEmail(user.email)}
                        className="text-xs text-green-400 hover:text-green-300 transition-colors"
                      >
                        {t('brandProfile.useMyEmail')}
                      </button>
                    )}
                    {companyEmail && isPersonalEmail(companyEmail) && (
                      <div className="mt-1 p-2 bg-yellow-500/20 border border-yellow-500/30 rounded-lg">
                        <p className="text-xs text-yellow-300">
                          {t('brandProfile.personalEmailWarning')}
                        </p>
                      </div>
                    )}
                  </div>
                </div>

                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">
                    {t('brandProfile.companyWebsite')}
                  </label>
                  <input
                    type="text"
                    value={companyWebsite}
                    onChange={(e) => setCompanyWebsite(e.target.value)}
                    className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent transition-all"
                    placeholder="thermplast.ru"
                  />
                </div>
              </div>

              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">
                  {t('brandProfile.brandSocialMedia')}
                </label>
                <div className="space-y-2">
                  <div className="flex space-x-2">
                    <input
                      type="url"
                      value={socialMediaInput}
                      onChange={(e) => setSocialMediaInput(e.target.value)}
                      onKeyPress={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          if (socialMediaInput.trim() && !socialMediaUrls.includes(socialMediaInput.trim())) {
                            setSocialMediaUrls([...socialMediaUrls, socialMediaInput.trim()]);
                            setSocialMediaInput('');
                          }
                        }
                      }}
                      className="flex-1 px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent transition-all"
                      placeholder="vk.com/thermplast; t.me/thermplast"
                    />
                    <button
                      type="button"
                      onClick={() => {
                        if (socialMediaInput.trim() && !socialMediaUrls.includes(socialMediaInput.trim())) {
                          setSocialMediaUrls([...socialMediaUrls, socialMediaInput.trim()]);
                          setSocialMediaInput('');
                        }
                      }}
                      className="px-4 py-3 bg-green-600/20 hover:bg-green-600/30 border border-green-500/50 rounded-xl text-green-300 transition-all"
                    >
                      {t('brandProfile.add')}
                    </button>
                  </div>
                  {socialMediaUrls.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {socialMediaUrls.map((url, index) => (
                        <div
                          key={index}
                          className="flex items-center space-x-2 px-3 py-1 bg-white/10 rounded-lg border border-white/20"
                        >
                          <span className="text-white text-xs truncate max-w-[200px]">{url}</span>
                          <button
                            type="button"
                            onClick={() => {
                              setSocialMediaUrls(socialMediaUrls.filter((_, i) => i !== index));
                            }}
                            className="text-red-400 hover:text-red-300"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>

            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">
                {t('brandProfile.proofDocsLabel')}
                {(() => {
                  const userEmail = user?.email || '';
                  const isCorporate = isCorporateEmail(companyEmail || userEmail, companyWebsite);
                  return (!companyEmail || !isCorporate) ? (
                    <span className="text-red-400"> *</span>
                  ) : (
                    <span className="text-gray-400 text-xs"> ({t('brandProfile.optionalForCorporate')})</span>
                  );
                })()}
              </label>
              <textarea
                value={proofText}
                onChange={(e) => setProofText(e.target.value)}
                required={(() => {
                  const userEmail = user?.email || '';
                  const isCorporate = isCorporateEmail(companyEmail || userEmail, companyWebsite);
                  return !isCorporate && !!companyEmail;
                })()}
                rows={4}
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent transition-all resize-none"
                placeholder={(() => {
                  const userEmail = user?.email || '';
                  const isCorporate = isCorporateEmail(companyEmail || userEmail, companyWebsite);
                  if (isCorporate && companyEmail) {
                    return t('brandProfile.proofPlaceholderCorporate');
                  }
                  return t('brandProfile.proofPlaceholderPersonal');
                })()}
              />
              {(() => {
                const userEmail = user?.email || '';
                const isCorporate = isCorporateEmail(companyEmail || userEmail, companyWebsite);
                if (!isCorporate && companyEmail) {
                  return (
                    <p className="mt-1 text-xs text-red-300">
                      {t('brandProfile.proofTextHint')}
                    </p>
                  );
                }
                return null;
              })()}
            </div>

            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">
                {t('brandProfile.attachDocs')}
                {(() => {
                  const userEmail = user?.email || '';
                  const isCorporate = isCorporateEmail(companyEmail || userEmail, companyWebsite);
                  return !isCorporate && companyEmail ? (
                    <span className="text-red-400"> *</span>
                  ) : (
                    <span className="text-gray-400 text-xs"> ({t('brandProfile.optionalForCorporate')})</span>
                  );
                })()}
              </label>
              <div className="bg-white/5 rounded-xl p-4 border border-white/10 border-dashed">
                <input
                  type="file"
                  multiple
                  onChange={(e) => {
                    const files = Array.from(e.target.files || []);
                    const allowedExtensions = ['.pdf', '.jpg', '.jpeg', '.png', '.doc', '.docx'];
                    const validFiles = files.filter((file) => {
                      const fileExt = '.' + file.name.split('.').pop()?.toLowerCase();
                      return allowedExtensions.includes(fileExt) && file.size <= 50 * 1024 * 1024;
                    });
                    setLocalFiles([...localFiles, ...validFiles]);
                  }}
                  accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
                  className="hidden"
                  id="file-upload-create"
                />
                <label
                  htmlFor="file-upload-create"
                  className="flex flex-col items-center justify-center space-y-2 cursor-pointer py-4"
                >
                  <Paperclip className="w-6 h-6 text-green-400" />
                  <span className="text-sm text-gray-300">
                    {(() => {
                      const userEmail = user?.email || '';
                      const isCorporate = isCorporateEmail(companyEmail || userEmail, companyWebsite);
                      if (!isCorporate && companyEmail && localFiles.length === 0) {
                        return t('brandProfile.requiredSelectFiles');
                      }
                      return t('brandProfile.selectFiles');
                    })()}
                  </span>
                  <span className="text-xs text-gray-400">{t('brandProfile.allowedFormats')}</span>
                </label>
                {localFiles.length > 0 && (
                  <div className="mt-4 space-y-2">
                    {localFiles.map((file, index) => (
                      <div
                        key={index}
                        className="flex items-center justify-between bg-white/10 rounded-lg p-2 border border-white/20"
                      >
                        <div className="flex items-center space-x-2 flex-1 min-w-0">
                          <FileText className="w-4 h-4 text-green-400 flex-shrink-0" />
                          <span className="text-white text-sm truncate">{file.name}</span>
                          <span className="text-gray-400 text-xs">({(file.size / 1024 / 1024).toFixed(2)} MB)</span>
                        </div>
                        <button
                          type="button"
                          onClick={() => {
                            setLocalFiles(localFiles.filter((_, i) => i !== index));
                          }}
                          className="ml-2 p-1 text-red-400 hover:text-red-300 transition-colors"
                        >
                          <XCircle className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">
                {t('brandProfile.additionalMessage')} <span className="text-gray-400 text-xs">({t('brandProfile.optional')})</span>
              </label>
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                rows={2}
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent transition-all resize-none"
                placeholder={t('brandProfile.additionalMessagePlaceholder')}
              />
            </div>

            <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-3 mb-4">
              <p className="text-xs text-blue-200 mb-2">
                <strong className="text-blue-300">{t('brandProfile.important')}:</strong> {t('brandProfile.alternativeVerification')}
              </p>
              <a
                href="mailto:admin@filamenthub.ru?subject=Brand verification request&body=Hello! I would like to register a brand on FilamentHub."
                className="inline-flex items-center space-x-2 text-xs text-blue-300 hover:text-blue-200 transition-colors"
              >
                <Share2 className="w-3 h-3" />
                <span>{t('brandProfile.contactAdmin')}</span>
              </a>
            </div>

            {/* Обязательное подтверждение достоверности данных */}
            <div className="bg-white/5 rounded-xl p-4 border border-white/10 mb-4">
              <label className="flex items-start space-x-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={confirmAccuracy}
                  onChange={(e) => setConfirmAccuracy(e.target.checked)}
                  required
                  className="mt-1 w-4 h-4 rounded border-white/20 bg-white/10 text-green-500 focus:ring-2 focus:ring-green-500"
                />
                  <div className="flex-1">
                    <span className="text-sm text-white">
                      {t('brandProfile.confirmAccuracyText')} {' '}
                      <a href="/user-agreement" target="_blank" className="text-green-400 hover:text-green-300 underline">
                       {t('brandProfile.userAgreement')}
                      </a>
                    </span>
                  </div>
              </label>
            </div>

            <div className="flex space-x-4 pt-4">
                <button
                type="submit"
                disabled={createRequestMutation.isPending || !confirmAccuracy}
                className="flex-1 bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700 text-white px-6 py-3 rounded-xl transition-all shadow-lg shadow-green-500/25 hover:shadow-green-500/40 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
              >
                {createRequestMutation.isPending ? (
                  <>
                    <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                    {t('brandProfile.submittingRequest')}
                  </>
                ) : (
                  <>
                    <Plus className="w-5 h-5 mr-2" />
                    {t('brandProfile.submitCreateRequest')}
                  </>
                )}
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsCreatingNew(false);
                  setError(null);
                  setCompanyEmail('');
                  setCompanyWebsite('');
                  setSocialMediaUrls([]);
                  setSocialMediaInput('');
                  setProofText('');
                  setMessage('');
                  setLocalFiles([]);
                }}
                disabled={createRequestMutation.isPending}
                className="px-6 py-3 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {t('brandProfile.cancel')}
              </button>
            </div>
          </form>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-8 border border-white/20 shadow-xl">
        <div className="text-center mb-8">
          <div className="w-16 h-16 bg-gradient-to-r from-green-500 to-emerald-500 rounded-xl flex items-center justify-center mx-auto mb-4 shadow-lg shadow-green-500/25">
            <Factory className="w-8 h-8 text-white" />
          </div>
          <h2 className="text-2xl font-bold text-white mb-2">{t('brandProfile.getManufacturerAccess')}</h2>
          <p className="text-gray-300 mb-4">
            {t('brandProfile.getManufacturerAccessDescription')}
          </p>
          
          {/* Информационный блок о процессе */}
          <div className="bg-blue-500/20 border border-blue-500/50 rounded-xl p-4 mb-6">
            <div className="flex items-start space-x-3">
              <Shield className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
              <div className="text-left">
                <h3 className="text-sm font-semibold text-blue-300 mb-1">{t('brandProfile.verificationProcess')}</h3>
                <ul className="text-xs text-blue-200 space-y-1 list-disc list-inside">
                  <li>{t('brandProfile.verifyStep1')}</li>
                  <li>{t('brandProfile.verifyStep2')}</li>
                  <li>{t('brandProfile.verifyStep3')}</li>
                  <li>{t('brandProfile.verifyStep4')}</li>
                </ul>
              </div>
            </div>
          </div>
        </div>

        {/* Список моих заявок */}
        {myRequests && myRequests.length > 0 && (
          <div className="mb-6">
            <h3 className="text-lg font-bold text-white mb-4">{t('brandProfile.myRequests')}</h3>
            <div className="space-y-3">
              {myRequests.map((request) => (
                <div
                  key={request.id}
                  className={`bg-white/10 backdrop-blur-sm rounded-xl p-4 border border-white/20 shadow-md ${
                    request.status === 'pending' ? 'cursor-pointer hover:bg-white/15 transition-all' : ''
                  }`}
                  onClick={() => {
                    if (request.status === 'pending') {
                      setSubmittedRequest(request);
                    }
                  }}
                >
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center space-x-3">
                      <span className={`px-3 py-1 rounded-lg text-xs font-medium ${
                        request.status === 'pending' ? 'bg-yellow-500/20 text-yellow-300' :
                        request.status === 'approved' ? 'bg-green-500/20 text-green-300' :
                        'bg-red-500/20 text-red-300'
                      }`}>
                        {request.status === 'pending' ? t('brandProfile.statusPendingShort') :
                         request.status === 'approved' ? t('brandProfile.statusApproved') :
                         t('brandProfile.statusRejected')}
                      </span>
                      <span className="text-white font-medium">
                        {request.request_type === 'create'
                          ? t('brandProfile.createBrandRequest', { name: request.new_brand_name })
                          : t('brandProfile.joinBrandRequest')}
                      </span>
                    </div>
                    {request.status === 'pending' && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation(); // Предотвращаем клик по карточке
                          if (confirm(t('brandProfile.confirmCancelRequest'))) {
                            cancelRequestMutation.mutate(request.id);
                          }
                        }}
                        disabled={cancelRequestMutation.isPending}
                        className="px-3 py-1 text-xs bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded-lg transition-all disabled:opacity-50"
                      >
                        {t('brandProfile.cancelRequestShort')}
                      </button>
                    )}
                  </div>
                  <p className="text-gray-400 text-sm">
                    {t('brandProfile.submitted')}: {new Date(request.created_at).toLocaleDateString('ru-RU')}
                  </p>
                  {request.status === 'pending' && (
                    <p className="text-gray-300 text-xs mt-2 italic">
                      {t('brandProfile.clickToViewDetails')}
                    </p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {error && (
          <div className="mb-4 p-4 bg-red-500/20 border border-red-500/50 rounded-xl text-red-300">
            {error}
          </div>
        )}

        <div className="space-y-4">
          <label className="block text-gray-300 mb-2 text-sm font-medium">
            {t('brandProfile.option1JoinExisting')}
          </label>
          <p className="text-xs text-gray-400 mb-3">
            {t('brandProfile.option1Description')}
          </p>
          <Dropdown
            value={selectedBrandId || ''}
            onChange={(val) => {
              const id = val === '' ? null : Number(val);
              setSelectedBrandId(id);
              if (id) {
                const brand = allBrands.find((b) => b.id === id);
                if (brand) {
                  setBrandSearch(brand.name);
                }
              } else {
                setBrandSearch('');
              }
            }}
            options={allBrands.map((brand: Brand) => ({
              value: brand.id,
              label: brand.name,
              icon: brand.verified ? (
                <Shield className="w-4 h-4 text-green-400 flex-shrink-0" />
              ) : (
                <Factory className="w-4 h-4 text-gray-400 flex-shrink-0" />
              ),
            }))}
            placeholder={t('brandProfile.searchBrandPlaceholder')}
            filterable
            filterValue={brandSearch}
            onFilterChange={setBrandSearch}
            emptyMessage={t('brandProfile.brandsNotFound')}
            renderOption={(option) => {
              const brand = allBrands.find((b) => b.id === option.value);
              return (
              <>
                <span className="flex items-center gap-2">
                    {brand?.verified ? (
                  <Shield className="w-4 h-4 text-green-400 flex-shrink-0" />
                    ) : (
                      <Factory className="w-4 h-4 text-gray-400 flex-shrink-0" />
                    )}
                  <span>{option.label}</span>
                    {brand?.verified ? (
                  <span className="text-gray-400 text-xs">({t('brandProfile.verified')})</span>
                    ) : (
                      <span className="text-gray-500 text-xs">({t('brandProfile.notVerified')})</span>
                    )}
                </span>
                {selectedBrandId === option.value && (
                  <Check className="w-5 h-5 text-purple-400 flex-shrink-0" />
                )}
              </>
              );
            }}
          />
          {selectedBrandId && (
            <div className="space-y-4">
              {selectedBrand?.verified && hasEmployees ? (
              <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4">
                <div className="flex items-start space-x-3">
                  <Shield className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
                  <div className="flex-1">
                    <p className="text-xs text-blue-200">
                      {t('brandProfile.joinVerifiedBrandInfo', { name: selectedBrand?.name })}
                    </p>
                  </div>
                </div>
              </div>
              ) : (
                <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-4">
                  <div className="flex items-start space-x-3">
                    <AlertTriangle className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
                    <div className="flex-1">
                      <p className="text-xs text-yellow-200">
                        {!selectedBrand?.verified ? (
                          <>{t('brandProfile.brandNotVerifiedWarning', { name: selectedBrand?.name })}</>
                        ) : (
                          <>{t('brandProfile.brandNoEmployeesWarning', { name: selectedBrand?.name })}</>
                        )}
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {/* Контактная информация */}
              <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">
                      {t('brandProfile.companyEmail')}
                  </label>
                    <div className="space-y-1">
                  <input
                    type="email"
                    value={companyEmail}
                    onChange={(e) => setCompanyEmail(e.target.value)}
                    className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent transition-all"
                        placeholder="info@example.com"
                      />
                      {user?.email && user.email !== companyEmail && (
                        <button
                          type="button"
                          onClick={() => setCompanyEmail(user.email)}
                          className="text-xs text-green-400 hover:text-green-300 transition-colors"
                        >
                          {t('brandProfile.useMyEmail')}
                        </button>
                      )}
                      {companyEmail && isPersonalEmail(companyEmail) && (
                        <div className="mt-1 p-2 bg-yellow-500/20 border border-yellow-500/30 rounded-lg">
                          <p className="text-xs text-yellow-300">
                            {t('brandProfile.personalEmailWarning')}
                          </p>
                </div>
                      )}
                    </div>
                  </div>

                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">
                      {t('brandProfile.companyWebsite')}
                  </label>
                  <input
                    type="text"
                    value={companyWebsite}
                    onChange={(e) => setCompanyWebsite(e.target.value)}
                    className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent transition-all"
                    placeholder="example.com"
                  />
                </div>
              </div>

              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">
                    {t('brandProfile.brandSocialMedia')}
                </label>
                <div className="space-y-2">
                  <div className="flex space-x-2">
                    <input
                      type="url"
                      value={socialMediaInput}
                      onChange={(e) => setSocialMediaInput(e.target.value)}
                      onKeyPress={(e) => {
                        if (e.key === 'Enter') {
                          e.preventDefault();
                          if (socialMediaInput.trim() && !socialMediaUrls.includes(socialMediaInput.trim())) {
                            setSocialMediaUrls([...socialMediaUrls, socialMediaInput.trim()]);
                            setSocialMediaInput('');
                          }
                        }
                      }}
                      className="flex-1 px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent transition-all"
                      placeholder="vk.com/thermplast; t.me/thermplast"
                    />
                    <button
                      type="button"
                      onClick={() => {
                        if (socialMediaInput.trim() && !socialMediaUrls.includes(socialMediaInput.trim())) {
                          setSocialMediaUrls([...socialMediaUrls, socialMediaInput.trim()]);
                          setSocialMediaInput('');
                        }
                      }}
                      className="px-4 py-3 bg-green-600/20 hover:bg-green-600/30 border border-green-500/50 rounded-xl text-green-300 transition-all"
                    >
                      {t('brandProfile.add')}
                    </button>
                  </div>
                  {socialMediaUrls.length > 0 && (
                    <div className="flex flex-wrap gap-2">
                      {socialMediaUrls.map((url, index) => (
                        <div
                          key={index}
                          className="flex items-center space-x-2 px-3 py-1 bg-white/10 rounded-lg border border-white/20"
                        >
                          <span className="text-white text-xs truncate max-w-[200px]">{url}</span>
                          <button
                            type="button"
                            onClick={() => {
                              setSocialMediaUrls(socialMediaUrls.filter((_, i) => i !== index));
                            }}
                            className="text-red-400 hover:text-red-300"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                </div>
              </div>

            {/* Поля для подтверждающих документов - показываем если бренд не верифицирован ИЛИ у бренда нет сотрудников */}
              {(!selectedBrand?.verified || !hasEmployees) && (
                <>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">
                      {t('brandProfile.proofDocsLabel')}
                      {(() => {
                        const userEmail = user?.email || '';
                        const isCorporate = isCorporateEmail(companyEmail || userEmail, companyWebsite);
                        return (!companyEmail || !isCorporate) ? (
                          <span className="text-red-400"> *</span>
                        ) : (
                          <span className="text-gray-400 text-xs"> ({t('brandProfile.optionalForCorporate')})</span>
                        );
                      })()}
                    </label>
                    <textarea
                      value={proofText}
                      onChange={(e) => setProofText(e.target.value)}
                      required={(() => {
                        const userEmail = user?.email || '';
                        const isCorporate = isCorporateEmail(companyEmail || userEmail, companyWebsite);
                        return !isCorporate && !!companyEmail;
                      })()}
                      rows={4}
                      className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent transition-all resize-none"
                      placeholder={(() => {
                        const userEmail = user?.email || '';
                        const isCorporate = isCorporateEmail(companyEmail || userEmail, companyWebsite);
                        if (isCorporate && companyEmail) {
                          return t('brandProfile.proofPlaceholderCorporate');
                        }
                        return t('brandProfile.proofPlaceholderPersonal');
                      })()}
                    />
                    {(() => {
                      const userEmail = user?.email || '';
                      const isCorporate = isCorporateEmail(companyEmail || userEmail, companyWebsite);
                      if (!isCorporate && companyEmail) {
                        return (
                          <p className="mt-1 text-xs text-red-300">
                            {t('brandProfile.proofTextHint')}
                          </p>
                        );
                      }
                      return null;
                    })()}
                  </div>

                  <div>
                    <label className="block text-gray-300 mb-2 text-sm font-medium">
                      {t('brandProfile.attachDocs')}
                      {(() => {
                        const userEmail = user?.email || '';
                        const isCorporate = isCorporateEmail(companyEmail || userEmail, companyWebsite);
                        return !isCorporate && companyEmail ? (
                          <span className="text-red-400"> *</span>
                        ) : (
                          <span className="text-gray-400 text-xs"> ({t('brandProfile.optionalForCorporate')})</span>
                        );
                      })()}
                    </label>
                    <div className="bg-white/5 rounded-xl p-4 border border-white/10 border-dashed">
                      <input
                        type="file"
                        multiple
                        onChange={handleFileSelect}
                        accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
                        className="hidden"
                        id="file-upload-join"
                      />
                      <label
                        htmlFor="file-upload-join"
                        className="flex flex-col items-center justify-center space-y-2 cursor-pointer py-4"
                      >
                        <Paperclip className="w-6 h-6 text-green-400" />
                        <span className="text-sm text-gray-300">
                          {(() => {
                            const userEmail = user?.email || '';
                            const isCorporate = isCorporateEmail(companyEmail || userEmail, companyWebsite);
                            if (!isCorporate && companyEmail && localFiles.length === 0) {
                              return t('brandProfile.requiredSelectFiles');
                            }
                            return t('brandProfile.selectFiles');
                          })()}
                        </span>
                        <span className="text-xs text-gray-400">{t('brandProfile.allowedFormats')}</span>
                      </label>
                      {localFiles.length > 0 && (
                        <div className="mt-4 space-y-2">
                          {localFiles.map((file, index) => (
                            <div
                              key={index}
                              className="flex items-center justify-between bg-white/10 rounded-lg p-2 border border-white/20"
                            >
                              <div className="flex items-center space-x-2 flex-1 min-w-0">
                                <FileText className="w-4 h-4 text-green-400 flex-shrink-0" />
                                <span className="text-white text-sm truncate">{file.name}</span>
                                <span className="text-gray-400 text-xs">({(file.size / 1024 / 1024).toFixed(2)} MB)</span>
                              </div>
                              <button
                                type="button"
                                onClick={() => {
                                  setLocalFiles(localFiles.filter((_, i) => i !== index));
                                }}
                                className="ml-2 p-1 text-red-400 hover:text-red-300 transition-colors"
                              >
                                <XCircle className="w-4 h-4" />
                              </button>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </>
              )}

              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">
                  {t('brandProfile.additionalMessage')} <span className="text-gray-400 text-xs">({t('brandProfile.optional')})</span>
                </label>
                <textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  rows={2}
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent transition-all resize-none"
                  placeholder={t('brandProfile.additionalMessagePlaceholder')}
                />
              </div>

              {/* Обязательное подтверждение достоверности данных */}
              <div className="bg-white/5 rounded-xl p-4 border border-white/10">
                <label className="flex items-start space-x-3 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={confirmAccuracy}
                    onChange={(e) => setConfirmAccuracy(e.target.checked)}
                    required
                    className="mt-1 w-4 h-4 rounded border-white/20 bg-white/10 text-green-500 focus:ring-2 focus:ring-green-500"
                  />
                  <div className="flex-1">
                    <span className="text-sm text-white">
                      {t('brandProfile.confirmAccuracyText')} 
                      <a href="/user-agreement" target="_blank" className="text-green-400 hover:text-green-300 underline">
                       {t('brandProfile.userAgreement')}
                      </a>
                    </span>
                  </div>
                </label>
              </div>

              <button
                onClick={handleJoinBrandRequest}
                disabled={createRequestMutation.isPending || !confirmAccuracy}
                className="w-full bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white px-6 py-3 rounded-xl transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center"
              >
                {createRequestMutation.isPending ? (
                  <>
                    <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                    {t('brandProfile.submittingRequest')}
                  </>
                ) : (
                  <>
                    <CheckCircle className="w-5 h-5 mr-2" />
                    {t('brandProfile.joinBrand')}
                  </>
                )}
              </button>
            </div>
          )}
          
          <div className="relative flex items-center my-6">
            <div className="flex-1 border-t border-white/20"></div>
            <span className="px-4 text-sm text-gray-400">{t('brandProfile.or')}</span>
            <div className="flex-1 border-t border-white/20"></div>
          </div>

          <label className="block text-gray-300 mb-2 text-sm font-medium">
            {t('brandProfile.option2RegisterNew')}
          </label>
          <p className="text-xs text-gray-400 mb-3">
            {t('brandProfile.option2Description')}
          </p>

          <div className="bg-yellow-500/20 border border-yellow-500/50 rounded-xl p-4 mb-4">
            <div className="flex items-start space-x-3">
              <Shield className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
              <div className="text-left">
                <p className="text-xs text-yellow-200">
                  {t('brandProfile.checkBrandNotExists')}
                </p>
              </div>
            </div>
          </div>

          <button
            onClick={() => setIsCreatingNew(true)}
            className="w-full bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700 text-white px-6 py-3 rounded-xl transition-all shadow-lg shadow-green-500/25 hover:shadow-green-500/40 flex items-center justify-center"
          >
            <Plus className="w-5 h-5 mr-2" />
            {t('brandProfile.registerNewBrand')}
          </button>
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

interface FilamentCardProps {
  filament: Filament;
  onEdit: (filament: Filament) => void;
  onDelete: (filament: Filament) => void;
  onShowQR: (filament: Filament) => void;
  viewMode?: 'grid' | 'list';
}

const FilamentCard: React.FC<FilamentCardProps> = ({ filament, onEdit, onDelete, onShowQR, viewMode = 'grid' }) => {
  const { t } = useTranslation();
  // Загружаем пресеты для материала
  const { data: presetsData } = useQuery({
    queryKey: ['filament-presets', filament.id],
    queryFn: () => filamentsAPI.getPresets(filament.id),
  });

  const presets = presetsData?.items || [];
  const officialPreset = presets.find((p) => p.is_official);
  const totalPresets = presets.length;

  // Быстрая смена статуса наличия прямо из списка кабинета.
  const cardQueryClient = useQueryClient();
  const availabilityMutation = useMutation({
    mutationFn: (availability: FilamentAvailability) => filamentsAPI.update(filament.id, { availability }),
    onSuccess: () => cardQueryClient.invalidateQueries({ queryKey: ['brand-filaments'] }),
  });
  const statusSelect = (
    <select
      value={filament.availability || 'available'}
      onClick={(e) => e.stopPropagation()}
      onChange={(e) => availabilityMutation.mutate(e.target.value as FilamentAvailability)}
      disabled={availabilityMutation.isPending}
      className="bg-white/10 border border-white/20 rounded-full px-2 py-0.5 text-xs text-gray-200 focus:outline-none focus:ring-1 focus:ring-purple-500 cursor-pointer disabled:opacity-50"
      title={t('createFilament.availabilityLabel')}
    >
      <option value="available" className="bg-gray-900">{t('createFilament.availability.available')}</option>
      <option value="discontinued" className="bg-gray-900">{t('createFilament.availability.discontinued')}</option>
      <option value="coming_soon" className="bg-gray-900">{t('createFilament.availability.coming_soon')}</option>
    </select>
  );

  if (viewMode === 'list') {
    return (
      <div className="p-2 bg-white/5 rounded-lg border border-white/10 hover:bg-white/10 transition-all group">
        <div className="flex items-center gap-3">
          {/* Filament Preview - компактный, прямоугольный */}
          <div className="flex-shrink-0">
            <div className="w-20 h-12 bg-white/5 rounded-lg border border-white/10 flex items-center justify-center overflow-hidden">
              <div style={{ transform: 'scale(0.4)', transformOrigin: 'center center' }}>
                <FilamentPreview
                  colorHex={filament.color_hex || '#FFFFFF'}
                  visualSettings={filament.visual_settings}
                  size="medium"
                />
              </div>
            </div>
          </div>
          
          {/* Main Info - компактное горизонтальное расположение */}
          <div className="flex-1 min-w-0 flex items-center gap-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-0.5">
                <h4 className="text-white font-medium text-sm truncate group-hover:text-purple-300 transition-colors">
                  {filament.name}
                </h4>
                {filament.color_name && (
                  <span className="text-gray-400 text-xs truncate" title={filament.color_name}>
                    {filament.color_name}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-3 text-xs text-gray-400">
                {officialPreset && (
                  <div className="flex items-center space-x-1">
                    <CheckCircle className="w-3 h-3 text-green-400" />
                    <span>{t('brandProfile.official')}</span>
                  </div>
                )}
                <div className="flex items-center space-x-1">
                  <Settings className="w-3 h-3" />
                  <span>{totalPresets}</span>
                </div>
                {filament.qr_code && (
                  <div className="flex items-center space-x-1">
                    <QrCode className="w-3 h-3" />
                  </div>
                )}
              </div>
            </div>
            
            {/* Badges */}
            <div className="flex items-center gap-1.5 flex-shrink-0">
              {statusSelect}
              <span className="px-2 py-0.5 bg-purple-500/20 text-purple-300 text-xs rounded-full">
                {filament.material_type}
              </span>
              {filament.diameter && (
                <span className="px-2 py-0.5 bg-blue-500/20 text-blue-300 text-xs rounded-full">
                  ⌀ {filament.diameter}
                </span>
              )}
              {filament.active === false && (
                <span className="px-2 py-0.5 bg-gray-500/20 text-gray-400 text-xs rounded-full">
                  {t('brandProfile.inactive')}
                </span>
              )}
            </div>
          </div>
          
          {/* Actions - компактные */}
          <div className="flex items-center gap-1 flex-shrink-0">
            {filament.qr_code && (
              <button
                onClick={() => onShowQR(filament)}
                className="p-1.5 bg-white/10 hover:bg-green-500/20 rounded-md text-white transition-all"
                title={t('brandProfile.qrCode')}
              >
                <QrCode className="w-3.5 h-3.5" />
              </button>
            )}
            <button
              onClick={() => onEdit(filament)}
              className="p-1.5 bg-white/10 hover:bg-purple-500/20 rounded-md text-white transition-all"
              title={t('brandProfile.edit')}
            >
              <Edit className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => onDelete(filament)}
              className="p-1.5 bg-white/10 hover:bg-red-500/20 rounded-md text-white transition-all"
              title={t('brandProfile.delete')}
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl hover:shadow-2xl hover:border-white/30 transition-all group">
      {/* Header with actions */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex-1 min-w-0">
          <h4 className="text-xl font-bold text-white truncate group-hover:text-purple-300 transition-colors">
            {filament.name}
          </h4>
          {filament.color_name && (
            <p className="text-gray-400 text-sm mt-1">{filament.color_name}</p>
          )}
        </div>
        <div className="flex space-x-2 ml-2">
          {filament.qr_code && (
            <button
              onClick={() => onShowQR(filament)}
              className="p-2 bg-white/10 hover:bg-green-500/20 rounded-lg text-white transition-all"
              title={t('brandProfile.showQRCode')}
            >
              <QrCode className="w-4 h-4" />
            </button>
          )}
          <button
            onClick={() => onEdit(filament)}
            className="p-2 bg-white/10 hover:bg-purple-500/20 rounded-lg text-white transition-all"
            title={t('brandProfile.edit')}
          >
            <Edit className="w-4 h-4" />
          </button>
          <button
            onClick={() => onDelete(filament)}
            className="p-2 bg-white/10 hover:bg-red-500/20 rounded-lg text-white transition-all"
            title={t('brandProfile.delete')}
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Filament Preview */}
      <div className="flex justify-center mb-4 py-3 bg-white/5 rounded-xl border border-white/10">
        <FilamentPreview
          colorHex={filament.color_hex || '#FFFFFF'}
          visualSettings={filament.visual_settings}
          size="medium"
        />
      </div>

      {/* Material Type and Status */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
          {statusSelect}
          <span className="px-3 py-1 bg-purple-500/20 text-purple-300 text-xs font-medium rounded-full">
            {filament.material_type}
          </span>
          {filament.diameter && (
            <span className="px-2 py-1 bg-blue-500/20 text-blue-300 text-xs rounded-full">
              ⌀ {filament.diameter}mm
            </span>
          )}
        </div>
        {filament.active !== false ? (
          <span className="px-2 py-1 bg-green-500/20 text-green-300 text-xs rounded-full flex items-center space-x-1">
            <CheckCircle className="w-3 h-3" />
            <span>{t('brandProfile.active')}</span>
          </span>
        ) : (
          <span className="px-2 py-1 bg-gray-500/20 text-gray-400 text-xs rounded-full">
            {t('brandProfile.inactive')}
          </span>
        )}
      </div>

      {/* Official Preset Info */}
      {officialPreset && (
        <div className="mb-4 p-3 bg-purple-500/10 rounded-xl border border-purple-500/20">
          <div className="flex items-center space-x-2 mb-2">
            <CheckCircle className="w-4 h-4 text-green-400" />
            <span className="text-white text-sm font-medium">{t('brandProfile.officialPreset')}</span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="flex items-center space-x-1">
              <Thermometer className="w-3 h-3 text-red-400" />
              <span className="text-gray-300">{t('brandProfile.nozzle')}: {officialPreset.extruder_temp}°C</span>
            </div>
            <div className="flex items-center space-x-1">
              <Gauge className="w-3 h-3 text-blue-400" />
              <span className="text-gray-300">{t('brandProfile.bed')}: {officialPreset.bed_temp}°C</span>
            </div>
            <div className="flex items-center space-x-1">
              <Gauge className="w-3 h-3 text-green-400" />
              <span className="text-gray-300">{t('brandProfile.speed')}: {officialPreset.print_speed}mm/s</span>
            </div>
            {officialPreset.fan_speed !== undefined && (
              <div className="flex items-center space-x-1">
                <Settings className="w-3 h-3 text-yellow-400" />
                <span className="text-gray-300">{t('brandProfile.fan')}: {officialPreset.fan_speed}%</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Statistics */}
      <div className="grid grid-cols-3 gap-2 mb-4 text-xs">
        <div className="text-center p-2 bg-white/5 rounded-lg">
          <div className="flex items-center justify-center space-x-1 text-gray-400 mb-1">
            <Settings className="w-3 h-3" />
          </div>
          <div className="text-white font-semibold">{totalPresets}</div>
          <div className="text-gray-400">{t('brandProfile.presetsCount')}</div>
        </div>
        <div className="text-center p-2 bg-white/5 rounded-lg">
          <div className="flex items-center justify-center space-x-1 text-gray-400 mb-1">
            <Eye className="w-3 h-3" />
          </div>
          <div className="text-white font-semibold">{filament.views_count || 0}</div>
          <div className="text-gray-400">{t('brandProfile.views')}</div>
        </div>
        <div className="text-center p-2 bg-white/5 rounded-lg">
          <div className="flex items-center justify-center space-x-1 text-gray-400 mb-1">
            <QrCode className="w-3 h-3" />
          </div>
          <div className="text-white font-semibold">{filament.scans_count || 0}</div>
          <div className="text-gray-400">{t('brandProfile.scans')}</div>
        </div>
      </div>

      {/* Price and Additional Info */}
      <div className="pt-4 border-t border-white/10">
        <div className="flex items-center justify-between text-sm">
          {filament.price_per_kg ? (
            <div>
              <span className="text-gray-400">{t('brandProfile.price')}: </span>
              <span className="text-white font-semibold">{Math.round(filament.price_per_kg)} {currencySymbol(filament.currency)}/{t('catalogPage.units.kg')}</span>
            </div>
          ) : (
            <span className="text-gray-500 text-xs">{t('brandProfile.priceNotSet')}</span>
          )}
          {filament.density && (
            <div className="text-gray-400 text-xs">
              {t('brandProfile.density')}: {filament.density} {t('brandProfile.densityUnit')}
            </div>
          )}
        </div>
        {filament.description && (
          <p className="text-gray-400 text-xs mt-2 line-clamp-2">{filament.description}</p>
        )}
      </div>
    </div>
  );
};

interface QRCodeCardProps {
  filament: Filament;
}

const QRCodeCard: React.FC<QRCodeCardProps> = ({ filament }) => {
  const { t } = useTranslation();
  // Используем реальный QR-код из филамента
  const shortCode = filament.qr_code || null;
  
  // Если QR-кода нет - не показываем карточку
  if (!shortCode) {
    return null;
  }

  const handleDownload = (size: number) => {
    qrAPI.downloadQRCode(filament.id, size);
  };

  return (
    <div className="flex items-center justify-between p-4 bg-white/5 rounded-xl hover:bg-white/10 transition-all">
      <div className="flex items-center space-x-4">
        {/* QR Code Preview */}
        {filament.qr_code && (
          <div className="w-12 h-12 bg-white rounded p-1">
            <img
              src={qrAPI.getQRCodeURL(filament.id, 48)}
              alt={`QR Code ${shortCode}`}
              className="w-full h-full"
            />
          </div>
        )}
        <div>
          <p className="text-white font-medium">{filament.name}</p>
          <p className="text-gray-400 text-sm font-mono">{shortCode}</p>
        </div>
      </div>
      <div className="flex items-center space-x-4">
        <div className="text-right">
          <p className="text-white font-semibold">{filament.scans_count || 0}</p>
          <p className="text-gray-400 text-sm">{t('brandProfile.scans')}</p>
        </div>
        <div className="flex space-x-2">
          <button
            onClick={() => handleDownload(600)}
            className="p-2 bg-white/10 hover:bg-white/20 rounded-lg text-white transition-all"
            title={t('brandProfile.downloadQR')}
          >
            <Download className="w-4 h-4" />
          </button>
          <button
            onClick={() => navigator.clipboard.writeText(shortCode)}
            className="p-2 bg-white/10 hover:bg-white/20 rounded-lg text-white transition-all"
            title={t('brandProfile.copyCode')}
          >
            <Copy className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
};

interface MaterialStatCardProps {
  filament: Filament;
}

const MaterialStatCard: React.FC<MaterialStatCardProps> = ({ filament }) => {
  const { t } = useTranslation();
  return (
    <div className="flex items-center justify-between p-4 bg-white/5 rounded-xl">
      <div className="flex items-center space-x-3">
        <div className="w-10 h-10 bg-gradient-to-r from-purple-500 to-pink-500 rounded-lg flex items-center justify-center">
          <Package className="w-5 h-5 text-white" />
        </div>
        <div>
          <p className="text-white font-medium">{filament.name}</p>
          <p className="text-gray-400 text-sm">{filament.material_type}</p>
        </div>
      </div>
      <div className="text-right">
        <p className="text-white font-semibold">{filament.scans_count || 0} {t('brandProfile.scans')}</p>
        <p className="text-green-400 text-sm">{filament.views_count || 0} {t('brandProfile.views')}</p>
      </div>
    </div>
  );
};
