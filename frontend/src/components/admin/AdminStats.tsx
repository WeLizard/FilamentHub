/** Компонент статистики для админки */

import { useQuery } from '@tanstack/react-query';
import { BarChart3, Users, Building2, Settings, TrendingUp } from 'lucide-react';
import { adminAPI } from '../../api/client';

export function AdminStats() {
  const { data: stats, isLoading } = useQuery({
    queryKey: ['admin-stats'],
    queryFn: () => adminAPI.getStats(),
  });

  if (isLoading) {
    return <div className="text-center py-12 text-gray-400">Загрузка статистики...</div>;
  }

  if (!stats) {
    return <div className="text-center py-12 text-red-400">Ошибка загрузки статистики</div>;
  }

  const StatCard = ({ icon: Icon, label, value, color }: {
    icon: any;
    label: string;
    value: number | string;
    color: string;
  }) => (
    <div className={`bg-white/5 rounded-xl p-6 border border-white/10 ${color}`}>
      <div className="flex items-center justify-between mb-4">
        <Icon className="w-8 h-8 text-purple-400" />
        <span className="text-3xl font-bold text-white">{value}</span>
      </div>
      <p className="text-gray-400 text-sm">{label}</p>
    </div>
  );

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white mb-2">Статистика платформы</h2>
        <p className="text-gray-400">Общая информация о платформе</p>
      </div>

      {/* Пользователи */}
      <div>
        <h3 className="text-xl font-bold text-white mb-4 flex items-center space-x-2">
          <Users className="w-5 h-5" />
          <span>Пользователи</span>
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <StatCard
            icon={Users}
            label="Всего пользователей"
            value={stats.users.total}
            color=""
          />
          <StatCard
            icon={Building2}
            label="Представителей брендов"
            value={stats.users.brands}
            color=""
          />
          <StatCard
            icon={BarChart3}
            label="Администраторов"
            value={stats.users.admins}
            color=""
          />
        </div>
      </div>

      {/* Бренды */}
      <div>
        <h3 className="text-xl font-bold text-white mb-4 flex items-center space-x-2">
          <Building2 className="w-5 h-5" />
          <span>Бренды</span>
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <StatCard
            icon={Building2}
            label="Всего брендов"
            value={stats.brands.total}
            color=""
          />
          <StatCard
            icon={TrendingUp}
            label="Верифицированных"
            value={stats.brands.verified}
            color=""
          />
          <StatCard
            icon={Settings}
            label="Ожидают верификации"
            value={stats.brands.pending_verification}
            color=""
          />
        </div>
      </div>

      {/* Пресеты */}
      <div>
        <h3 className="text-xl font-bold text-white mb-4 flex items-center space-x-2">
          <Settings className="w-5 h-5" />
          <span>Пресеты</span>
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <StatCard
            icon={Settings}
            label="Всего пресетов"
            value={stats.presets.total}
            color=""
          />
          <StatCard
            icon={TrendingUp}
            label="Одобренных"
            value={stats.presets.approved}
            color=""
          />
          <StatCard
            icon={Settings}
            label="Ожидают модерации"
            value={stats.presets.pending_moderation}
            color=""
          />
          <StatCard
            icon={BarChart3}
            label="Отклоненных"
            value={stats.presets.rejected}
            color=""
          />
        </div>
      </div>
    </div>
  );
}


