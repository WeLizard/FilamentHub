/** Личный кабинет производителя */

import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
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
  MapPin,
  Thermometer,
  Gauge,
  Edit,
  Trash2,
  CheckCircle,
  Star,
  X,
  Loader2,
  ArrowLeft,
  Check,
  Paperclip,
  XCircle,
  FileText,
  Fan,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { authAPI, brandsAPI, filamentsAPI, brandRequestsAPI, presetsAPI, qrAPI } from '../api/client';
import { CreateFilamentModal } from '../components/CreateFilamentModal';
import { CreatePresetModal } from '../components/CreatePresetModal';
import { Dropdown } from '../components/Dropdown';
import { FilamentPreview } from '../components/FilamentPreview';
import type { Filament, Brand, BrandRequest, Preset } from '../types/api';

interface BrandProfilePageProps {
  onBack?: () => void; // Callback для возврата в обычный профиль
}

export const BrandProfilePage: React.FC<BrandProfilePageProps> = ({ onBack }) => {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [brandTab, setBrandTab] = useState<'materials' | 'presets' | 'qr' | 'analytics' | 'usage'>('materials');
  const [isCreateFilamentModalOpen, setIsCreateFilamentModalOpen] = useState(false);
  const [isCreatePresetModalOpen, setIsCreatePresetModalOpen] = useState(false);
  const [editingFilament, setEditingFilament] = useState<Filament | null>(null);
  const [editingPreset, setEditingPreset] = useState<Preset | null>(null);
  const [deletingFilamentId, setDeletingFilamentId] = useState<number | null>(null);
  const [showQRFilament, setShowQRFilament] = useState<Filament | null>(null);

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

  // Мутация для удаления материала
  const deleteFilamentMutation = useMutation({
    mutationFn: (id: number) => filamentsAPI.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['brand-filaments'] });
      queryClient.invalidateQueries({ queryKey: ['filaments'] });
      queryClient.invalidateQueries({ queryKey: ['filaments', 'material-types'] });
      setDeletingFilamentId(null);
    },
    onError: (err: any) => {
      alert(err.response?.data?.detail || 'Ошибка при удалении материала');
      setDeletingFilamentId(null);
    },
  });

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
        <div className="text-red-400 text-xl">Необходимо войти в систему</div>
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
        <div className="text-white text-xl">Загрузка...</div>
      </div>
    );
  }

  if (!brandData) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-red-400 text-xl">Бренд не найден</div>
      </div>
    );
  }

  // Вычисляем статистику
  const totalScans = filaments.reduce((sum, f) => sum + (f.scans_count || 0), 0);
  const totalViews = filaments.reduce((sum, f) => sum + (f.views_count || 0), 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="text-center mb-8">
        <div className="flex items-center justify-center space-x-3 mb-4">
          <div className="w-16 h-16 bg-gradient-to-r from-green-500 to-emerald-500 rounded-xl flex items-center justify-center shadow-lg shadow-green-500/25">
            <Factory className="w-8 h-8 text-white" />
          </div>
          <div>
            <h2 className="text-3xl font-bold text-white">{brandData.name}</h2>
            <div className="flex items-center justify-center space-x-2 text-gray-300">
              {brandData.verified && <Shield className="w-4 h-4 text-green-400" />}
              <span>{brandData.verified ? 'Верифицированный производитель' : 'Производитель'}</span>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex justify-center space-x-2 mt-4">
          {[
            { id: 'materials', label: 'Материалы', icon: Package },
            { id: 'presets', label: 'Пресеты', icon: Settings },
            { id: 'qr', label: 'QR-коды', icon: QrCode },
            { id: 'analytics', label: 'Аналитика', icon: BarChart3 },
            { id: 'usage', label: 'Использование', icon: TrendingUp },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setBrandTab(tab.id as any)}
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
            <h3 className="text-2xl font-bold text-white">Мои материалы</h3>
            <button
              onClick={handleCreateFilament}
              disabled={isLoadingFilaments}
              className="bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700 text-white px-4 py-2 rounded-xl transition-all shadow-lg shadow-green-500/25 hover:shadow-green-500/40 disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
            >
              <Plus className="w-4 h-4" />
              <span>Новый материал</span>
            </button>
          </div>

          {/* Loading State */}
          {isLoadingFilaments && (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 text-purple-400 animate-spin mr-3" />
              <span className="text-gray-300 text-lg">Загрузка материалов...</span>
            </div>
          )}

          {/* Error State */}
          {filamentsError && (
            <div className="bg-red-500/20 border border-red-500/30 rounded-xl p-4">
              <div className="flex items-center space-x-2 text-red-300">
                <XCircle className="w-5 h-5" />
                <span>Ошибка загрузки материалов. Попробуйте обновить страницу.</span>
              </div>
            </div>
          )}

          {/* Materials Grid */}
          {!isLoadingFilaments && !filamentsError && (
            <>
              {filaments.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  {filaments.map((filament) => (
                    <FilamentCard
                      key={filament.id}
                      filament={filament}
                      onEdit={handleEditFilament}
                      onDelete={handleDeleteFilament}
                      onShowQR={(filament) => setShowQRFilament(filament)}
                    />
                  ))}
                </div>
              ) : (
                <div className="text-center py-12">
                  <Package className="w-16 h-16 text-gray-400 mx-auto mb-4" />
                  <p className="text-gray-400 text-xl mb-2">У вас пока нет материалов</p>
                  <p className="text-gray-500 text-sm mb-6">Создайте первый материал для вашего бренда</p>
                  <button
                    onClick={handleCreateFilament}
                    className="bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700 text-white px-6 py-3 rounded-xl transition-all shadow-lg shadow-green-500/25 hover:shadow-green-500/40 flex items-center space-x-2 mx-auto"
                  >
                    <Plus className="w-4 h-4" />
                    <span>Создать первый материал</span>
                  </button>
                </div>
              )}
            </>
          )}

          {/* Delete Loading Indicator */}
          {deleteFilamentMutation.isPending && (
            <div className="fixed bottom-4 right-4 bg-purple-600/90 backdrop-blur-sm text-white px-4 py-3 rounded-xl shadow-lg flex items-center space-x-2 z-50">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>Удаление материала...</span>
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
                  <h3 className="text-xl font-bold text-white">Подтверждение удаления</h3>
                </div>
                <p className="text-gray-300 mb-6">
                  Вы уверены, что хотите удалить материал "{filaments.find(f => f.id === deletingFilamentId)?.name}"?
                  <br />
                  <span className="text-red-400 text-sm mt-2 block">Это действие нельзя отменить.</span>
                </p>
                <div className="flex justify-end space-x-3">
                  <button
                    onClick={cancelDeleteFilament}
                    disabled={deleteFilamentMutation.isPending}
                    className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all disabled:opacity-50"
                  >
                    Отмена
                  </button>
                  <button
                    onClick={confirmDeleteFilament}
                    disabled={deleteFilamentMutation.isPending}
                    className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-xl transition-all disabled:opacity-50 flex items-center space-x-2"
                  >
                    {deleteFilamentMutation.isPending ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span>Удаление...</span>
                      </>
                    ) : (
                      <>
                        <Trash2 className="w-4 h-4" />
                        <span>Удалить</span>
                      </>
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
            <h3 className="text-2xl font-bold text-white">Официальные пресеты</h3>
            <button
              onClick={handleCreatePreset}
              disabled={isLoadingPresets || filaments.length === 0}
              className="bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700 text-white px-4 py-2 rounded-xl transition-all shadow-lg shadow-green-500/25 hover:shadow-green-500/40 disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"
              title={filaments.length === 0 ? 'Сначала создайте материал' : ''}
            >
              <Plus className="w-4 h-4" />
              <span>Новый пресет</span>
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
                      <span className="text-gray-300">Сопло: {preset.extruder_temp}°C</span>
                    </div>
                    <div className="flex items-center space-x-1">
                      <Thermometer className="w-4 h-4 text-red-400" />
                      <span className="text-gray-300">Стол: {preset.bed_temp}°C</span>
                    </div>
                    <div className="flex items-center space-x-1">
                      <Gauge className="w-4 h-4 text-blue-400" />
                      <span className="text-gray-300">Скорость: {preset.print_speed}mm/s</span>
                    </div>
                    {preset.fan_speed !== null && (
                      <div className="flex items-center space-x-1">
                        <Fan className="w-4 h-4 text-green-400" />
                        <span className="text-gray-300">Вентилятор: {preset.fan_speed}%</span>
                      </div>
                    )}
                  </div>
                  <div className="flex items-center justify-between text-xs text-gray-400">
                    <span>{new Date(preset.created_at).toLocaleDateString('ru-RU')}</span>
                    <div className="flex items-center space-x-2">
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
              <p className="text-gray-400 text-xl mb-2">У вас пока нет официальных пресетов</p>
              <p className="text-gray-500 text-sm">
                {filaments.length === 0 
                  ? 'Сначала создайте материал' 
                  : 'Создайте пресет для одного из ваших материалов'}
              </p>
            </div>
          )}
        </div>
      )}

      {/* QR Codes Tab */}
      {brandTab === 'qr' && (
        <div className="space-y-6">
          <div className="flex items-center justify-between">
            <h3 className="text-2xl font-bold text-white">QR-коды материалов</h3>
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
                <p className="text-gray-400 text-xl">QR-коды автоматически создаются при создании материалов</p>
                <p className="text-gray-500 text-sm mt-2">Создайте материал, чтобы получить QR-код</p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Analytics Tab */}
      {brandTab === 'analytics' && (
        <div className="space-y-6">
          <h3 className="text-2xl font-bold text-white">Аналитика по материалам</h3>

          {/* Stats Cards */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <StatCard
              icon={QrCode}
              label="Всего сканирований"
              value={totalScans.toString()}
              color="from-green-500/20 to-emerald-500/20"
              borderColor="border-green-500/30"
              iconColor="text-green-400"
            />
            <StatCard
              icon={Package}
              label="QR-кодов"
              value={filaments.filter(f => f.qr_code).length.toString()}
              color="from-blue-500/20 to-cyan-500/20"
              borderColor="border-blue-500/30"
              iconColor="text-blue-400"
            />
            <StatCard
              icon={Eye}
              label="Материалов"
              value={filaments.length.toString()}
              color="from-purple-500/20 to-pink-500/20"
              borderColor="border-purple-500/30"
              iconColor="text-purple-400"
            />
            <StatCard
              icon={TrendingUp}
              label="Просмотров"
              value={totalViews.toString()}
              color="from-yellow-500/20 to-orange-500/20"
              borderColor="border-yellow-500/30"
              iconColor="text-yellow-400"
            />
          </div>

          {/* Materials Statistics */}
          <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
            <h3 className="text-xl font-bold text-white mb-4">Статистика по материалам</h3>
            {filaments.length > 0 ? (
              <div className="space-y-3">
                {filaments.map((filament) => (
                  <MaterialStatCard key={filament.id} filament={filament} />
                ))}
              </div>
            ) : (
              <p className="text-gray-400 text-center py-8">Нет данных</p>
            )}
          </div>
        </div>
      )}

      {/* Usage Tab */}
      {brandTab === 'usage' && (
        <div className="space-y-6">
          <h3 className="text-2xl font-bold text-white">Аналитика использования</h3>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Regional Statistics - ЗАГЛУШКА */}
            <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
              <h3 className="text-xl font-bold text-white mb-4 flex items-center">
                <MapPin className="w-5 h-5 mr-2" />
                Региональная статистика [ЗАГЛУШКА]
              </h3>
              <div className="space-y-3">
                {[
                  { region: 'Москва', usage: 2456, growth: 12 },
                  { region: 'Санкт-Петербург', usage: 1892, growth: 8 },
                  { region: 'Новосибирск', usage: 1234, growth: 15 },
                ].map((item, index) => (
                  <div key={index} className="flex items-center justify-between p-3 bg-white/5 rounded-xl">
                    <div className="flex items-center space-x-3">
                      <MapPin className="w-5 h-5 text-blue-400" />
                      <span className="text-white">{item.region}</span>
                    </div>
                    <div className="text-right">
                      <p className="text-white font-semibold">{item.usage}</p>
                      <p className="text-green-400 text-sm">+{item.growth}%</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Popular Printers - ЗАГЛУШКА */}
            <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
              <h3 className="text-xl font-bold text-white mb-4">Популярные принтеры [ЗАГЛУШКА]</h3>
              <div className="space-y-3">
                {[
                  { printer: 'Ender 3 Pro', usage: 1247, percentage: 45 },
                  { printer: 'Prusa MK3', usage: 892, percentage: 32 },
                  { printer: 'CR-10', usage: 654, percentage: 23 },
                ].map((item, index) => (
                  <div key={index} className="p-3 bg-white/5 rounded-xl">
                    <div className="flex justify-between mb-2">
                      <span className="text-white">{item.printer}</span>
                      <span className="text-gray-400">{item.percentage}%</span>
                    </div>
                    <div className="w-full bg-white/10 rounded-full h-2">
                      <div
                        className="bg-gradient-to-r from-purple-500 to-pink-500 h-2 rounded-full transition-all"
                        style={{ width: `${item.percentage}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
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

      {/* Create Preset Modal */}
      <CreatePresetModal
        isOpen={isCreatePresetModalOpen}
        onClose={handleClosePresetModal}
        preset={editingPreset}
        brandId={user.brand_id || undefined}
      />

      {/* QR Code Modal */}
      {showQRFilament && showQRFilament.qr_code && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-gradient-to-br from-gray-900 via-gray-800 to-gray-900 rounded-2xl w-full max-w-lg overflow-hidden flex flex-col border border-white/20 shadow-2xl">
            {/* Header */}
            <div className="flex items-center justify-between p-6 border-b border-white/10">
              <div className="flex items-center space-x-3">
                <QrCode className="w-6 h-6 text-green-400" />
                <h2 className="text-2xl font-bold text-white">QR-код материала</h2>
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
                  <p className="text-gray-300 text-sm mb-2">Код:</p>
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
                      alert('Код скопирован в буфер обмена');
                    }
                  }}
                  className="px-6 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-all flex items-center space-x-2"
                >
                  <Check className="w-4 h-4" />
                  <span>Копировать код</span>
                </button>
              </div>
            </div>

            {/* Close Button */}
            <div className="p-6 border-t border-white/10">
              <button
                onClick={() => setShowQRFilament(null)}
                className="w-full px-6 py-3 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-xl transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40"
              >
                Закрыть
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

/** Форма выбора/создания бренда */
const BrandSelectionForm: React.FC = () => {
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

  // Загружаем список брендов с поиском (только верифицированные для выбора)
  const { data: brandsData, isLoading: isLoadingBrands } = useQuery({
    queryKey: ['brands', 'selection', { search: brandSearch }],
    queryFn: () => brandsAPI.list({ active_only: true, page: 1, size: 100, search: brandSearch || undefined }),
  });

  // Фильтруем только верифицированные бренды для выбора
  const verifiedBrands = brandsData?.items.filter((brand: Brand) => brand.verified) || [];

  // Находим выбранный бренд для отображения
  const selectedBrand = selectedBrandId ? verifiedBrands.find((b: Brand) => b.id === selectedBrandId) : null;

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
          console.error('Ошибка при загрузке файлов:', uploadError);
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
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Ошибка при отправке заявки');
    },
  });

  // Мутация для отзыва заявки
  const cancelRequestMutation = useMutation({
    mutationFn: (id: number) => brandRequestsAPI.cancel(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['brand-requests'] });
      refetchRequests();
    },
    onError: (err: any) => {
      alert(err.response?.data?.detail || 'Ошибка при отзыве заявки');
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
      const freshRequests = await refetchRequests();
      // Обновляем submittedRequest только если его еще нет или он устарел
      if (submittedRequest && updatedRequest.id === submittedRequest.id) {
        const freshRequest = freshRequests.data?.find((r) => r.id === updatedRequest.id);
        // Используем данные из updatedRequest (они самые свежие после загрузки)
        // Не перезаписываем их данными из refetch, чтобы избежать дублирования
      }
    },
    onError: (err: any) => {
      setError(err.response?.data?.detail || 'Ошибка при загрузке файла');
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
    onError: (err: any) => {
      alert(err.response?.data?.detail || 'Ошибка при удалении файла');
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
      setError(`Разрешены только файлы: ${allowedExtensions.join(', ')}`);
      return;
    }
    // Проверяем размер (50 MB)
    if (file.size > 50 * 1024 * 1024) {
      setError('Размер файла не должен превышать 50 MB');
      return;
    }
    setError(null);
    await uploadFileMutation.mutateAsync({ requestId: submittedRequest.id, file });
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
    
    // Белый список личных почтовых доменов (синхронизирован с backend/app/core/personal_email_domains.txt)
    const personalDomains = [
      // Google
      'gmail.com',
      // Microsoft (Outlook/Hotmail)
      'outlook.com', 'hotmail.com', 'hotmail.co.uk', 'hotmail.fr', 'hotmail.de',
      'live.com', 'msn.com', 'outlook.fr', 'outlook.de',
      // Yahoo
      'yahoo.com', 'yahoo.co.uk', 'yahoo.fr', 'yahoo.de', 'yahoo.it',
      'yahoo.es', 'yahoo.com.au', 'yahoo.co.jp', 'yahoo.ca',
      'ymail.com', 'rocketmail.com',
      // Apple
      'icloud.com', 'me.com', 'mac.com',
      // Mail.ru Group (российские)
      'mail.ru', 'inbox.ru', 'list.ru', 'bk.ru', 'internet.ru',
      'xmail.ru', 'mail.ua',
      // Yandex (российские)
      'yandex.ru', 'yandex.com', 'yandex.ua', 'yandex.kz', 'yandex.by', 'ya.ru',
      // Rambler (российские)
      'rambler.ru', 'rambler.ua', 'lenta.ru', 'autorambler.ru',
      'myrambler.ru', 'ro.ru',
      // ProtonMail (шифрование)
      'protonmail.com', 'proton.me', 'protonmail.ch',
      // Mail.com и поддомены (популярные)
      'mail.com', 'email.com', 'usa.com', 'myself.com',
      'consultant.com', 'post.com', 'iname.com', 'engineer.com',
      // GMX
      'gmx.com', 'gmx.net', 'gmx.de', 'gmx.fr', 'gmx.at', 'gmx.ch',
      // Другие популярные международные
      'aol.com', 'zoho.com', 'tutanota.com', 'fastmail.com',
      'disroot.org', 'hey.com',
      // Региональные для СНГ и других стран
      'ukr.net', 'i.ua', 'meta.ua', 'bigmir.net',
    ];
    
    return personalDomains.includes(emailDomain);
  };

  const handleCreateBrandRequest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newBrandName.trim() || !newBrandSlug.trim()) {
      setError('Заполните название и slug бренда');
      return;
    }
    // Проверяем обязательное подтверждение достоверности данных
    if (!confirmAccuracy) {
      setError('Необходимо подтвердить достоверность предоставленных данных');
      return;
    }
    
    // Проверяем корпоративность email
    const userEmail = user?.email || '';
    const isCorporate = isCorporateEmail(companyEmail || userEmail, companyWebsite);
    
    // Если email указан И не корпоративный → документы и описание обязательны
    if (companyEmail && !isCorporate) {
      if (!proofText.trim()) {
        setError('Опишите подтверждающие документы (обязательно при использовании личной почты)');
        return;
      }
      if (localFiles.length === 0) {
        setError('При использовании личной почты обязательно прикрепите подтверждающие документы (доверенность, письмо от компании, выписка из ЕГРЮЛ/ЕГРИП и т.д.)');
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
      setError('Выберите бренд');
      return;
    }
    // Проверяем обязательное подтверждение достоверности данных
    if (!confirmAccuracy) {
      setError('Необходимо подтвердить достоверность предоставленных данных');
      return;
    }
    setError(null);
    await createRequestMutation.mutateAsync({
      request_type: 'join',
      brand_id: selectedBrandId,
      message: message.trim() || undefined,
      company_email: companyEmail.trim() || undefined,
      company_website: companyWebsite.trim() || undefined,
      social_media_urls: socialMediaUrls.length > 0 ? socialMediaUrls : undefined,
      // Для JOIN заявок не требуем подтверждающих документов - админ уточнит у существующих представителей
      proof_text: message.trim() || 'Заявка на вступление в бренд',
      files: undefined,
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
              {submittedRequest.request_type === 'create' ? 'Заявка на создание бренда отправлена!' : 'Заявка на вступление отправлена!'}
            </h2>
            <p className="text-gray-300">
              {submittedRequest.request_type === 'create' 
                ? `Заявка на создание бренда "${submittedRequest.new_brand_name}" отправлена на рассмотрение.`
                : `Ваша заявка на вступление в бренд отправлена на рассмотрение.`}
            </p>
          </div>

          <div className="bg-yellow-500/20 border border-yellow-500/50 rounded-xl p-6 mb-6">
            <div className="flex items-start space-x-4">
              <Shield className="w-6 h-6 text-yellow-400 flex-shrink-0 mt-0.5" />
              <div>
                <h3 className="text-lg font-semibold text-yellow-300 mb-2">Ожидание рассмотрения</h3>
                <p className="text-yellow-200 text-sm">
                  Ваша заявка находится на модерации. Администратор проверит предоставленные подтверждающие документы и примет решение. После одобрения заявки вы получите доступ к личному кабинету производителя.
                </p>
              </div>
            </div>
          </div>

          <div className="space-y-4">
            <div className="bg-white/5 rounded-xl p-4 border border-white/10">
              <h4 className="text-white font-medium mb-3">Детали заявки:</h4>
              <div className="space-y-3 text-sm">
                <div>
                  <span className="text-gray-400">Статус: </span>
                  <span className={`font-medium ${
                    submittedRequest.status === 'pending' ? 'text-yellow-400' :
                    submittedRequest.status === 'approved' ? 'text-green-400' :
                    'text-red-400'
                  }`}>
                    {submittedRequest.status === 'pending' ? 'Ожидает рассмотрения' :
                     submittedRequest.status === 'approved' ? 'Одобрена' :
                     'Отклонена'}
                  </span>
                </div>
                
                {submittedRequest.request_type === 'create' && submittedRequest.new_brand_name && (
                  <>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <span className="text-gray-400">Название: </span>
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
                        <span className="text-gray-400 mb-1">Описание бренда:</span>
                        <span className="text-white text-xs bg-white/5 rounded-lg p-2">{submittedRequest.new_brand_description}</span>
                      </div>
                    )}
                  </>
                )}

                {submittedRequest.request_type === 'join' && submittedRequest.brand_id && (
                  <div>
                    <span className="text-gray-400">Бренд: </span>
                    <span className="text-white font-medium">
                      {submittedRequest.brand_name || `Бренд #${submittedRequest.brand_id}`}
                    </span>
                  </div>
                )}

                {/* Email и сайт компании в одну строку */}
                {(submittedRequest.company_email || submittedRequest.company_website) && (
                  <div className="grid grid-cols-2 gap-4">
                    {submittedRequest.company_email && (
                      <div>
                        <span className="text-gray-400">Ваш Email: </span>
                        <span className="text-white">{submittedRequest.company_email}</span>
                      </div>
                    )}
                    {submittedRequest.company_website && (
                      <div>
                        <span className="text-gray-400">Сайт компании: </span>
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
                    <span className="text-gray-400 mb-2">Социальные сети:</span>
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
                    <span className="text-gray-400 mb-1">Сообщение:</span>
                    <span className="text-white text-xs bg-white/5 rounded-lg p-2">{submittedRequest.message}</span>
                  </div>
                )}

                {submittedRequest.proof_text && (
                  <div className="flex flex-col">
                    <span className="text-gray-400 mb-1">Описание подтверждающих документов:</span>
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
                  Прикрепленные файлы (PDF, изображения, документы)
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
                        fileName = parts[parts.length - 1] || `Файл ${index + 1}`;
                      } else if (fileInfo && typeof fileInfo === 'object' && 'path' in fileInfo) {
                        // Новый формат: объект с path и name
                        filePath = fileInfo.path;
                        const pathParts = filePath.split('/');
                        fileName = fileInfo.name || pathParts[pathParts.length - 1] || `Файл ${index + 1}`;
                      } else {
                        // Fallback на случай неожиданного формата
                        filePath = '';
                        fileName = `Файл ${index + 1}`;
                      }
                      
                      // Формируем URL для доступа к файлу
                      // filePath уже в формате "brand_requests/5/file.jpg"
                      const fileUrl = `/uploads/${filePath}`;
                      
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
                                if (confirm('Удалить этот файл?')) {
                                  deleteFileMutation.mutate({
                                    requestId: submittedRequest.id,
                                    filePath: filePath, // Используем путь для удаления
                                  });
                                }
                              }}
                              disabled={deleteFileMutation.isPending}
                              className="ml-2 p-1 text-red-400 hover:text-red-300 transition-colors disabled:opacity-50 flex-shrink-0"
                              title="Удалить файл"
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
                          <span className="text-sm">Загрузка...</span>
                        </>
                      ) : (
                        <>
                          <Paperclip className="w-4 h-4" />
                          <span className="text-sm">Прикрепить файл</span>
                        </>
                      )}
                    </div>
                  </label>
                </div>
                <p className="text-xs text-gray-400 mt-2">
                  Разрешены: PDF, JPG, PNG, DOC, DOCX (макс. 50 MB)
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
                Обновить статус
              </button>
              {submittedRequest.status === 'pending' && (
                <button
                  onClick={() => {
                    if (confirm('Вы уверены, что хотите отозвать эту заявку?')) {
                      cancelRequestMutation.mutate(submittedRequest.id);
                      setSubmittedRequest(null);
                    }
                  }}
                  disabled={cancelRequestMutation.isPending}
                  className="px-6 py-3 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {cancelRequestMutation.isPending ? 'Отзыв...' : 'Отозвать заявку'}
                </button>
              )}
            </div>

            <p className="text-center text-gray-400 text-xs mt-4">
              После верификации вы получите уведомление и сможете привязать бренд к аккаунту
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
              Создать новый бренд
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
                <h3 className="text-sm font-semibold text-blue-300 mb-1">Процесс верификации</h3>
                <p className="text-xs text-blue-200">
                После подачи заявки администратор проверит предоставленные подтверждающие документы и контактные данные (корпоративный email, сайт, официальные документы) и примет решение в течение 3–5 рабочих дней. После одобрения вы автоматически получите доступ к кабинету производителя.</p>
              </div>
            </div>
          </div>

          <form onSubmit={handleCreateBrandRequest} className="space-y-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">
                Название бренда *
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
                Уникальный идентификатор для URL (только латиница, цифры и дефисы)
              </p>
            </div>

            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">
                Описание (необязательно)
              </label>
              <textarea
                value={newBrandDescription}
                onChange={(e) => setNewBrandDescription(e.target.value)}
                rows={3}
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent transition-all resize-none"
                placeholder="Краткое описание бренда..."
              />
            </div>

            {/* Контактная информация */}
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">
                    Email компании
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
                        Использовать мой email
                      </button>
                    )}
                    {companyEmail && isPersonalEmail(companyEmail) && (
                      <div className="mt-1 p-2 bg-yellow-500/20 border border-yellow-500/30 rounded-lg">
                        <p className="text-xs text-yellow-300">
                          ⚠️ Вы используете личную почту. Обязательно прикрепите подтверждающие документы.
                        </p>
                      </div>
                    )}
                  </div>
                </div>

                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">
                    Сайт компании
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
                  Соцсети бренда
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
                      Добавить
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
                Описание подтверждающих документов
                {(() => {
                  const userEmail = user?.email || '';
                  const isCorporate = isCorporateEmail(companyEmail || userEmail, companyWebsite);
                  return (!companyEmail || !isCorporate) ? (
                    <span className="text-red-400"> *</span>
                  ) : (
                    <span className="text-gray-400 text-xs"> (необязательно для корпоративной почты)</span>
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
                    return "Опционально: опишите подтверждающие документы для ускорения верификации (доверенность, выписка из ЕГРЮЛ/ЕГРИП и т.д.)";
                  }
                  return "При использовании личной почты (например, @gmail.com) обязательно прикрепите подтверждающие документы и опишите их содержание: доверенность, выписку из ЕГРЮЛ/ЕГРИП (для ИП), ссылки на соцсети, маркетплейсы или фото продукции с логотипом или упаковкой";
                })()}
              />
              {(() => {
                const userEmail = user?.email || '';
                const isCorporate = isCorporateEmail(companyEmail || userEmail, companyWebsite);
                if (!isCorporate && companyEmail) {
                  return (
                    <p className="mt-1 text-xs text-red-300">
                      Текстовое описание не заменяет документы — оно лишь поясняет их содержание.
                    </p>
                  );
                }
                return null;
              })()}
            </div>

            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">
                Прикрепить документы
                {(() => {
                  const userEmail = user?.email || '';
                  const isCorporate = isCorporateEmail(companyEmail || userEmail, companyWebsite);
                  return !isCorporate && companyEmail ? (
                    <span className="text-red-400"> *</span>
                  ) : (
                    <span className="text-gray-400 text-xs"> (необязательно для корпоративной почты)</span>
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
                        return 'Обязательно: нажмите для выбора файлов';
                      }
                      return 'Нажмите для выбора файлов';
                    })()}
                  </span>
                  <span className="text-xs text-gray-400">PDF, JPG, PNG, DOC, DOCX (макс. 50 MB)</span>
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
                Дополнительное сообщение <span className="text-gray-400 text-xs">(необязательно)</span>
              </label>
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                rows={2}
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent transition-all resize-none"
                placeholder="Любая дополнительная информация для администратора..."
              />
            </div>

            <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-3 mb-4">
              <p className="text-xs text-blue-200 mb-2">
                <strong className="text-blue-300">Важно:</strong> В случае отсутствия возможности предоставить стандартные документы (например, при регистрации авторского бренда физическим лицом без ИП), вы можете связаться с администрацией для согласования альтернативного способа верификации.
              </p>
              <a
                href="mailto:admin@filamenthub.ru?subject=Заявка на верификацию бренда&body=Здравствуйте! Я хочу зарегистрировать бренд на платформе FilamentHub."
                className="inline-flex items-center space-x-2 text-xs text-blue-300 hover:text-blue-200 transition-colors"
              >
                <Share2 className="w-3 h-3" />
                <span>Связаться с администратором</span>
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
                      Я подтверждаю, что вся предоставленная информация является достоверной. Предоставление ложных сведений может повлечь отказ в верификации и блокировку аккаунта. {' '}
                      <a href="/user-agreement" target="_blank" className="text-green-400 hover:text-green-300 underline">
                       Пользовательское соглашение
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
                    Отправка заявки...
                  </>
                ) : (
                  <>
                    <Plus className="w-5 h-5 mr-2" />
                    Подать заявку на создание бренда
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
                Отмена
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
          <h2 className="text-2xl font-bold text-white mb-2">Получите доступ к кабинету производителя</h2>
          <p className="text-gray-300 mb-4">
            Чтобы добавлять официальные профили материалов, управлять рекомендованными настройками печати и получать аналитику по использованию ваших филаментов, подайте заявку на подключение к FilamentHub как официальный представитель бренда.
          </p>
          
          {/* Информационный блок о процессе */}
          <div className="bg-blue-500/20 border border-blue-500/50 rounded-xl p-4 mb-6">
            <div className="flex items-start space-x-3">
              <Shield className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
              <div className="text-left">
                <h3 className="text-sm font-semibold text-blue-300 mb-1">Процесс верификации</h3>
                <ul className="text-xs text-blue-200 space-y-1 list-disc list-inside">
                  <li>Выберите: присоединиться к существующему бренду или зарегистрировать новый</li>
                  <li>Укажите подтверждающие документы или контактные данные, подтверждающие ваше право представлять бренд</li>
                  <li>Администрация проверит информацию и примет решение в течение 3–5 рабочих дней</li>
                  <li>После одобрения вы автоматически получите доступ к кабинету производителя</li>
                </ul>
              </div>
            </div>
          </div>
        </div>

        {/* Список моих заявок */}
        {myRequests && myRequests.length > 0 && (
          <div className="mb-6">
            <h3 className="text-lg font-bold text-white mb-4">Мои заявки</h3>
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
                        {request.status === 'pending' ? 'Ожидает' :
                         request.status === 'approved' ? 'Одобрена' :
                         'Отклонена'}
                      </span>
                      <span className="text-white font-medium">
                        {request.request_type === 'create' 
                          ? `Создание бренда "${request.new_brand_name}"`
                          : 'Вступление в бренд'}
                      </span>
                    </div>
                    {request.status === 'pending' && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation(); // Предотвращаем клик по карточке
                          if (confirm('Вы уверены, что хотите отозвать эту заявку?')) {
                            cancelRequestMutation.mutate(request.id);
                          }
                        }}
                        disabled={cancelRequestMutation.isPending}
                        className="px-3 py-1 text-xs bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded-lg transition-all disabled:opacity-50"
                      >
                        Отозвать
                      </button>
                    )}
                  </div>
                  <p className="text-gray-400 text-sm">
                    Подано: {new Date(request.created_at).toLocaleDateString('ru-RU')}
                  </p>
                  {request.status === 'pending' && (
                    <p className="text-gray-300 text-xs mt-2 italic">
                      Нажмите на заявку, чтобы просмотреть детали и добавить файлы
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
            Вариант 1: Присоединиться к существующему бренду
          </label>
          <p className="text-xs text-gray-400 mb-3">
            Если ваш бренд уже зарегистрирован в каталоге FilamentHub.
          </p>
          <Dropdown
            value={selectedBrandId || ''}
            onChange={(val) => {
              const id = val === '' ? null : Number(val);
              setSelectedBrandId(id);
              if (id) {
                const brand = verifiedBrands.find((b) => b.id === id);
                if (brand) {
                  setBrandSearch(brand.name);
                }
              } else {
                setBrandSearch('');
              }
            }}
            options={verifiedBrands.map((brand: Brand) => ({
              value: brand.id,
              label: brand.name,
              icon: <Shield className="w-4 h-4 text-green-400 flex-shrink-0" />,
            }))}
            placeholder="Начните вводить название бренда..."
            filterable
            filterValue={brandSearch}
            onFilterChange={setBrandSearch}
            emptyMessage="Бренды не найдены"
            renderOption={(option) => (
              <>
                <span className="flex items-center gap-2">
                  <Shield className="w-4 h-4 text-green-400 flex-shrink-0" />
                  <span>{option.label}</span>
                  <span className="text-gray-400 text-xs">(верифицирован)</span>
                </span>
                {selectedBrandId === option.value && (
                  <Check className="w-5 h-5 text-purple-400 flex-shrink-0" />
                )}
              </>
            )}
          />
          {selectedBrandId && (
            <div className="space-y-4">
              <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4">
                <div className="flex items-start space-x-3">
                  <Shield className="w-5 h-5 text-blue-400 flex-shrink-0 mt-0.5" />
                  <div className="flex-1">
                    <p className="text-xs text-blue-200">
                      После подачи заявки администратор свяжется с существующими представителями бренда <strong className="text-blue-300">{selectedBrand?.name}</strong> для подтверждения вашего членства. Убедитесь, что они ожидают ваш запрос. Подтверждающие документы предоставлять не требуется.
                    </p>
                  </div>
                </div>
              </div>

              {/* Контактные данные */}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">
                    Email для связи (необязательно)
                  </label>
                  <input
                    type="email"
                    value={companyEmail}
                    onChange={(e) => setCompanyEmail(e.target.value)}
                    className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent transition-all"
                    placeholder={user?.email || "email@example.com"}
                  />
                </div>
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">
                    Сайт компании (необязательно)
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

              {/* Социальные сети */}
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">
                  Социальные сети (необязательно)
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
                      Добавить
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

              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">
                  Дополнительное сообщение (необязательно)
                </label>
                <textarea
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  rows={3}
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent transition-all resize-none"
                  placeholder="Любая дополнительная информация для администратора или представителей бренда (например: ваше имя, должность, контакты для связи)"
                />
                <p className="mt-1 text-xs text-gray-400">
                  Вы можете указать свою должность, контакты или любую другую информацию, которая поможет подтвердить ваше членство.
                </p>
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
                      Я подтверждаю, что вся предоставленная информация является достоверной. Предоставление ложных сведений может повлечь отказ в верификации и блокировку аккаунта. 
                      <a href="/user-agreement" target="_blank" className="text-green-400 hover:text-green-300 underline">
                       Пользовательское соглашение
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
                    Отправка заявки...
                  </>
                ) : (
                  <>
                    <CheckCircle className="w-5 h-5 mr-2" />
                    Присоединиться к бренду
                  </>
                )}
              </button>
            </div>
          )}
          
          <div className="relative flex items-center my-6">
            <div className="flex-1 border-t border-white/20"></div>
            <span className="px-4 text-sm text-gray-400">или</span>
            <div className="flex-1 border-t border-white/20"></div>
          </div>

          <label className="block text-gray-300 mb-2 text-sm font-medium">
            Вариант 2: Зарегистрировать новый бренд
          </label>
          <p className="text-xs text-gray-400 mb-3">
            Если вы представляете бренд, которого ещё нет на платформе. После модерации вы получите доступ к кабинету производителя.
          </p>

          <div className="bg-yellow-500/20 border border-yellow-500/50 rounded-xl p-4 mb-4">
            <div className="flex items-start space-x-3">
              <Shield className="w-5 h-5 text-yellow-400 flex-shrink-0 mt-0.5" />
              <div className="text-left">
                <p className="text-xs text-yellow-200">
                  Пожалуйста, убедитесь, что ваш бренд действительно ещё не зарегистрирован на платформе перед подачей заявки.
                </p>
              </div>
            </div>
          </div>

          <button
            onClick={() => setIsCreatingNew(true)}
            className="w-full bg-gradient-to-r from-green-600 to-emerald-600 hover:from-green-700 hover:to-emerald-700 text-white px-6 py-3 rounded-xl transition-all shadow-lg shadow-green-500/25 hover:shadow-green-500/40 flex items-center justify-center"
          >
            <Plus className="w-5 h-5 mr-2" />
            Зарегистрировать новый бренд
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

interface FilamentCardProps {
  filament: Filament;
  onEdit: (filament: Filament) => void;
  onDelete: (filament: Filament) => void;
  onShowQR: (filament: Filament) => void;
}

const FilamentCard: React.FC<FilamentCardProps> = ({ filament, onEdit, onDelete, onShowQR }) => {
  // Загружаем пресеты для материала
  const { data: presetsData } = useQuery({
    queryKey: ['filament-presets', filament.id],
    queryFn: () => filamentsAPI.getPresets(filament.id),
  });

  const presets = presetsData?.items || [];
  const officialPreset = presets.find((p) => p.is_official);
  const communityPresets = presets.filter((p) => !p.is_official);
  const totalPresets = presets.length;

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
              title="Показать QR-код"
            >
              <QrCode className="w-4 h-4" />
            </button>
          )}
          <button
            onClick={() => onEdit(filament)}
            className="p-2 bg-white/10 hover:bg-purple-500/20 rounded-lg text-white transition-all"
            title="Редактировать"
          >
            <Edit className="w-4 h-4" />
          </button>
          <button
            onClick={() => onDelete(filament)}
            className="p-2 bg-white/10 hover:bg-red-500/20 rounded-lg text-white transition-all"
            title="Удалить"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Filament Preview */}
      <div className="flex justify-center mb-4 py-3 bg-white/5 rounded-xl border border-white/10">
        <FilamentPreview
          colorHex={filament.color_hex || '#FFFFFF'}
          visualSettings={(filament as any).visual_settings}
          size="medium"
        />
      </div>

      {/* Material Type and Status */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center space-x-2">
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
            <span>Активен</span>
          </span>
        ) : (
          <span className="px-2 py-1 bg-gray-500/20 text-gray-400 text-xs rounded-full">
            Неактивен
          </span>
        )}
      </div>

      {/* Official Preset Info */}
      {officialPreset && (
        <div className="mb-4 p-3 bg-purple-500/10 rounded-xl border border-purple-500/20">
          <div className="flex items-center space-x-2 mb-2">
            <CheckCircle className="w-4 h-4 text-green-400" />
            <span className="text-white text-sm font-medium">Официальный пресет</span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="flex items-center space-x-1">
              <Thermometer className="w-3 h-3 text-red-400" />
              <span className="text-gray-300">Сопло: {officialPreset.extruder_temp}°C</span>
            </div>
            <div className="flex items-center space-x-1">
              <Gauge className="w-3 h-3 text-blue-400" />
              <span className="text-gray-300">Стол: {officialPreset.bed_temp}°C</span>
            </div>
            <div className="flex items-center space-x-1">
              <Gauge className="w-3 h-3 text-green-400" />
              <span className="text-gray-300">Скорость: {officialPreset.print_speed}mm/s</span>
            </div>
            {officialPreset.fan_speed !== undefined && (
              <div className="flex items-center space-x-1">
                <Settings className="w-3 h-3 text-yellow-400" />
                <span className="text-gray-300">Вентилятор: {officialPreset.fan_speed}%</span>
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
          <div className="text-gray-400">Пресетов</div>
        </div>
        <div className="text-center p-2 bg-white/5 rounded-lg">
          <div className="flex items-center justify-center space-x-1 text-gray-400 mb-1">
            <Eye className="w-3 h-3" />
          </div>
          <div className="text-white font-semibold">{filament.views_count || 0}</div>
          <div className="text-gray-400">Просмотров</div>
        </div>
        <div className="text-center p-2 bg-white/5 rounded-lg">
          <div className="flex items-center justify-center space-x-1 text-gray-400 mb-1">
            <QrCode className="w-3 h-3" />
          </div>
          <div className="text-white font-semibold">{filament.scans_count || 0}</div>
          <div className="text-gray-400">Сканирований</div>
        </div>
      </div>

      {/* Price and Additional Info */}
      <div className="pt-4 border-t border-white/10">
        <div className="flex items-center justify-between text-sm">
          {filament.price_per_kg ? (
            <div>
              <span className="text-gray-400">Цена: </span>
              <span className="text-white font-semibold">{Math.round(filament.price_per_kg)}₽/кг</span>
            </div>
          ) : (
            <span className="text-gray-500 text-xs">Цена не указана</span>
          )}
          {filament.density && (
            <div className="text-gray-400 text-xs">
              Плотность: {filament.density} г/см³
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
          <p className="text-gray-400 text-sm">сканирований</p>
        </div>
        <div className="flex space-x-2">
          <button
            onClick={() => handleDownload(600)}
            className="p-2 bg-white/10 hover:bg-white/20 rounded-lg text-white transition-all"
            title="Скачать QR-код (600x600)"
          >
            <Download className="w-4 h-4" />
          </button>
          <button
            onClick={() => navigator.clipboard.writeText(shortCode)}
            className="p-2 bg-white/10 hover:bg-white/20 rounded-lg text-white transition-all"
            title="Копировать код"
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
        <p className="text-white font-semibold">{filament.scans_count || 0} сканирований</p>
        <p className="text-green-400 text-sm">{filament.views_count || 0} просмотров</p>
      </div>
    </div>
  );
};

