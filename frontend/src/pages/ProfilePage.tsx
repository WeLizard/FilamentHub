/** Страница профиля пользователя */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
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
  Upload,
  Trash2,
  Thermometer,
  Gauge,
  Clock,
} from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { presetsAPI } from '../api/client';
import type { Preset } from '../types/api';

export const ProfilePage: React.FC = () => {
  const { user } = useAuth();
  const [userTab, setUserTab] = useState<'dashboard' | 'presets' | 'history' | 'calculator'>(
    'dashboard'
  );

  // Загружаем пресеты пользователя
  const { data: userPresetsData } = useQuery({
    queryKey: ['user-presets'],
    queryFn: () => presetsAPI.list({ active_only: true, page: 1, size: 100 }),
  });

  const userPresets = userPresetsData?.items || [];

  // TODO: Загрузить историю печати (когда будет эндпоинт)
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="text-center mb-8">
        <div className="flex items-center justify-center space-x-3 mb-4">
          <div className="w-16 h-16 bg-gradient-to-r from-purple-500 to-pink-500 rounded-xl flex items-center justify-center shadow-lg shadow-purple-500/25">
            <User className="w-8 h-8 text-white" />
          </div>
          <div>
            <h2 className="text-3xl font-bold text-white">Мой профиль</h2>
            <p className="text-gray-300">
              {user.full_name || user.username} • {user.role === 'user' ? '3D печатник' : 'Производитель'}
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
              value="156"
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
              label="Использованных материалов"
              value="23"
              color="from-green-500/20 to-emerald-500/20"
              borderColor="border-green-500/30"
              iconColor="text-green-400"
            />
            <StatCard
              icon={Star}
              label="Средний рейтинг"
              value="4.7"
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
            <button className="bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white px-4 py-2 rounded-xl transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40">
              <Plus className="w-4 h-4 inline mr-2" />
              Новый пресет
            </button>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {userPresets.map((preset) => (
              <PresetCard key={preset.id} preset={preset} />
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
            <div>
              <p className="text-white font-medium">{preset.name}</p>
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
}

const PresetCard: React.FC<PresetCardProps> = ({ preset }) => (
  <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 border border-white/20 shadow-xl">
    <div className="flex items-center justify-between mb-4">
      <h4 className="text-xl font-bold text-white">{preset.name}</h4>
      <div className="flex space-x-2">
        <button className="p-2 bg-white/10 hover:bg-white/20 rounded-lg text-white transition-all">
          <Download className="w-4 h-4" />
        </button>
        <button className="p-2 bg-white/10 hover:bg-white/20 rounded-lg text-white transition-all">
          <Upload className="w-4 h-4" />
        </button>
        <button className="p-2 bg-white/10 hover:bg-white/20 rounded-lg text-white transition-all">
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
    </div>

    <div className="grid grid-cols-2 gap-4 mb-4 text-sm">
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
      <div className="flex items-center space-x-2">
        <CheckCircle className="w-4 h-4 text-green-400" />
        <span className="text-gray-300">Использований: {preset.usage_count}</span>
      </div>
    </div>

    <div className="flex items-center justify-between text-sm">
      <span className="text-gray-400">
        Создан: {new Date(preset.created_at).toLocaleDateString('ru-RU')}
      </span>
      {preset.rating && (
        <div className="flex items-center space-x-1">
          <Star className="w-4 h-4 text-yellow-400 fill-current" />
          <span className="text-white">{preset.rating.toFixed(1)}</span>
        </div>
      )}
    </div>
  </div>
);

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

