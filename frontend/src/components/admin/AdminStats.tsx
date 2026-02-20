/** Компонент статистики для админки */

import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { BarChart3, Users, Building2, Settings, TrendingUp } from 'lucide-react';
import { adminAPI } from '../../api/client';

export function AdminStats() {
  const { t } = useTranslation();
  const { data: stats, isLoading } = useQuery({
    queryKey: ['admin-stats'],
    queryFn: () => adminAPI.getStats(),
  });

  if (isLoading) {
    return <div className="text-center py-12 text-gray-400">{t('adminStats.loading')}</div>;
  }

  if (!stats) {
    return <div className="text-center py-12 text-red-400">{t('adminStats.error')}</div>;
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
        <h2 className="text-2xl font-bold text-white mb-2">{t('adminStats.title')}</h2>
        <p className="text-gray-400">{t('adminStats.subtitle')}</p>
      </div>

      {/* Пользователи */}
      <div>
        <h3 className="text-xl font-bold text-white mb-4 flex items-center space-x-2">
          <Users className="w-5 h-5" />
          <span>{t('adminStats.users')}</span>
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <StatCard
            icon={Users}
            label={t('adminStats.totalUsers')}
            value={stats.users.total}
            color=""
          />
          <StatCard
            icon={Building2}
            label={t('adminStats.brandReps')}
            value={stats.users.brands}
            color=""
          />
          <StatCard
            icon={BarChart3}
            label={t('adminStats.admins')}
            value={stats.users.admins}
            color=""
          />
        </div>
      </div>

      {/* Бренды */}
      <div>
        <h3 className="text-xl font-bold text-white mb-4 flex items-center space-x-2">
          <Building2 className="w-5 h-5" />
          <span>{t('adminStats.brands')}</span>
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <StatCard
            icon={Building2}
            label={t('adminStats.totalBrands')}
            value={stats.brands.total}
            color=""
          />
          <StatCard
            icon={TrendingUp}
            label={t('adminStats.verified')}
            value={stats.brands.verified}
            color=""
          />
          <StatCard
            icon={Settings}
            label={t('adminStats.pendingVerification')}
            value={stats.brands.pending_verification}
            color=""
          />
        </div>
      </div>

      {/* Пресеты */}
      <div>
        <h3 className="text-xl font-bold text-white mb-4 flex items-center space-x-2">
          <Settings className="w-5 h-5" />
          <span>{t('adminStats.presets')}</span>
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <StatCard
            icon={Settings}
            label={t('adminStats.totalPresets')}
            value={stats.presets.total}
            color=""
          />
          <StatCard
            icon={TrendingUp}
            label={t('adminStats.approved')}
            value={stats.presets.approved}
            color=""
          />
          <StatCard
            icon={Settings}
            label={t('adminStats.pendingModeration')}
            value={stats.presets.pending_moderation}
            color=""
          />
          <StatCard
            icon={BarChart3}
            label={t('adminStats.rejected')}
            value={stats.presets.rejected}
            color=""
          />
        </div>
      </div>
    </div>
  );
}


