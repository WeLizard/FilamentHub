/** Admin dashboard — platform statistics & SEO tools */

import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import {
  BarChart3, Users, Building2, Settings, TrendingUp,
  Package, HardDrive, Printer, BookOpen, Star,
  Bell, RefreshCw, Globe, Search,
} from 'lucide-react';
import { adminAPI } from '../../api/client';

function StatCard({ icon: Icon, label, value, sub, color }: {
  icon: any;
  label: string;
  value: number | string;
  sub?: string;
  color?: string;
}) {
  return (
    <div className={`bg-white/5 rounded-xl p-5 border border-white/10 ${color || ''}`}>
      <div className="flex items-center justify-between mb-3">
        <Icon className="w-6 h-6 text-purple-400" />
        <span className="text-2xl font-bold text-white">{value}</span>
      </div>
      <p className="text-gray-400 text-sm">{label}</p>
      {sub && <p className="text-gray-500 text-xs mt-1">{sub}</p>}
    </div>
  );
}

function Section({ icon: Icon, title, children }: {
  icon: any;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <h3 className="text-lg font-bold text-white mb-3 flex items-center space-x-2">
        <Icon className="w-5 h-5 text-purple-400" />
        <span>{title}</span>
      </h3>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        {children}
      </div>
    </div>
  );
}

function SeoSection({ t }: { t: (key: string) => string }) {
  return (
    <div>
      <h3 className="text-lg font-bold text-white mb-3 flex items-center space-x-2">
        <Globe className="w-5 h-5 text-purple-400" />
        <span>{t('adminStats.seo.title')}</span>
      </h3>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <a
          href="https://webmaster.yandex.ru/site/https:filamenthub.ru:443/dashboard/"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-3 bg-white/5 rounded-xl p-4 border border-white/10 hover:bg-white/10 transition-colors"
        >
          <Search className="w-8 h-8 text-yellow-400 shrink-0" />
          <div>
            <p className="text-white font-medium">{t('adminStats.seo.yandexWebmaster')}</p>
            <p className="text-gray-500 text-xs">{t('adminStats.seo.yandexDesc')}</p>
          </div>
        </a>
        <a
          href="https://search.google.com/search-console?resource_id=https%3A%2F%2Ffilamenthub.ru%2F"
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-3 bg-white/5 rounded-xl p-4 border border-white/10 hover:bg-white/10 transition-colors"
        >
          <Search className="w-8 h-8 text-blue-400 shrink-0" />
          <div>
            <p className="text-white font-medium">{t('adminStats.seo.googleConsole')}</p>
            <p className="text-gray-500 text-xs">{t('adminStats.seo.googleDesc')}</p>
          </div>
        </a>
      </div>
      <div className="mt-3 grid grid-cols-1 md:grid-cols-3 gap-3">
        <a
          href="https://filamenthub.ru/robots.txt"
          target="_blank"
          rel="noopener noreferrer"
          className="text-center bg-white/5 rounded-lg p-3 border border-white/10 hover:bg-white/10 transition-colors"
        >
          <p className="text-gray-300 text-sm">robots.txt</p>
        </a>
        <a
          href="https://filamenthub.ru/sitemap.xml"
          target="_blank"
          rel="noopener noreferrer"
          className="text-center bg-white/5 rounded-lg p-3 border border-white/10 hover:bg-white/10 transition-colors"
        >
          <p className="text-gray-300 text-sm">sitemap.xml</p>
        </a>
        <a
          href="https://pagespeed.web.dev/analysis?url=https%3A%2F%2Ffilamenthub.ru"
          target="_blank"
          rel="noopener noreferrer"
          className="text-center bg-white/5 rounded-lg p-3 border border-white/10 hover:bg-white/10 transition-colors"
        >
          <p className="text-gray-300 text-sm">PageSpeed Insights</p>
        </a>
      </div>
    </div>
  );
}

export function AdminStats() {
  const { t } = useTranslation();
  const { data: stats, isLoading, refetch, dataUpdatedAt } = useQuery({
    queryKey: ['admin-stats'],
    queryFn: () => adminAPI.getStats(),
    refetchInterval: 60_000,
  });

  if (isLoading) {
    return <div className="text-center py-12 text-gray-400">{t('adminStats.loading')}</div>;
  }

  if (!stats) {
    return <div className="text-center py-12 text-red-400">{t('adminStats.error')}</div>;
  }

  const updatedAt = dataUpdatedAt ? new Date(dataUpdatedAt).toLocaleTimeString() : '';

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white mb-1">{t('adminStats.title')}</h2>
          <p className="text-gray-400 text-sm">{t('adminStats.subtitle')}</p>
        </div>
        <div className="flex items-center gap-3">
          {updatedAt && (
            <span className="text-gray-500 text-xs">{updatedAt}</span>
          )}
          <button
            onClick={() => refetch()}
            className="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
            title={t('adminStats.refresh')}
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Users */}
      <Section icon={Users} title={t('adminStats.users')}>
        <StatCard icon={Users} label={t('adminStats.totalUsers')} value={stats.users.total} />
        <StatCard icon={TrendingUp} label={t('adminStats.active24h')} value={stats.users.active_24h} />
        <StatCard icon={TrendingUp} label={t('adminStats.active7d')} value={stats.users.active_7d} />
        <StatCard icon={Users} label={t('adminStats.registered24h')} value={stats.users.registered_24h} />
        <StatCard icon={Users} label={t('adminStats.registered7d')} value={stats.users.registered_7d} />
        <StatCard icon={Users} label={t('adminStats.registered30d')} value={stats.users.registered_30d} />
        <StatCard icon={Building2} label={t('adminStats.brandReps')} value={stats.users.brands} />
        <StatCard icon={BarChart3} label={t('adminStats.admins')} value={stats.users.admins} />
      </Section>

      {/* Brands */}
      <Section icon={Building2} title={t('adminStats.brands')}>
        <StatCard icon={Building2} label={t('adminStats.totalBrands')} value={stats.brands.total} />
        <StatCard icon={TrendingUp} label={t('adminStats.verified')} value={stats.brands.verified} />
        <StatCard icon={Settings} label={t('adminStats.pendingVerification')} value={stats.brands.pending_verification} />
      </Section>

      {/* Presets */}
      <Section icon={Settings} title={t('adminStats.presets')}>
        <StatCard icon={Settings} label={t('adminStats.totalPresets')} value={stats.presets.total} />
        <StatCard icon={TrendingUp} label={t('adminStats.approved')} value={stats.presets.approved} />
        <StatCard icon={Settings} label={t('adminStats.pendingModeration')} value={stats.presets.pending_moderation} />
        <StatCard icon={BarChart3} label={t('adminStats.rejected')} value={stats.presets.rejected} />
      </Section>

      {/* Content */}
      <Section icon={Package} title={t('adminStats.content')}>
        <StatCard icon={Package} label={t('adminStats.filaments')} value={stats.content.filaments} />
        <StatCard icon={Printer} label={t('adminStats.printers')} value={stats.content.printers} />
        <StatCard icon={Settings} label={t('adminStats.printerProfiles')} value={stats.content.printer_profiles} />
        <StatCard icon={Star} label={t('adminStats.reviewsTotal')} value={stats.content.reviews_total}
          sub={t('adminStats.reviewsWeek', { count: stats.content.reviews_7d })} />
        <StatCard icon={BookOpen} label={t('adminStats.wikiArticles')} value={stats.content.wiki_articles} />
      </Section>

      {/* Hardware & Sync */}
      <Section icon={HardDrive} title={t('adminStats.hardware')}>
        <StatCard icon={HardDrive} label={t('adminStats.devices')} value={stats.hardware.devices} />
        <StatCard icon={Package} label={t('adminStats.spools')} value={stats.hardware.spools} />
        <StatCard icon={Settings} label={t('adminStats.gateSlots')} value={stats.hardware.gate_slots}
          sub={t('adminStats.gateSlotsAssigned', { count: stats.hardware.gate_slots_assigned })} />
        <StatCard icon={RefreshCw} label={t('adminStats.syncDevices')} value={stats.hardware.sync_devices}
          sub={t('adminStats.syncActive7d', { count: stats.hardware.sync_devices_active_7d })} />
      </Section>

      {/* Notifications */}
      <Section icon={Bell} title={t('adminStats.notificationsSection')}>
        <StatCard icon={Bell} label={t('adminStats.unreadNotifications')} value={stats.notifications.unread} />
      </Section>

      {/* SEO Tools */}
      <SeoSection t={t} />
    </div>
  );
}
