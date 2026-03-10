/** Admin dashboard — platform statistics, Docker metrics & SEO tools */

import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import {
  BarChart3, Users, Building2, Settings, TrendingUp,
  Package, HardDrive, Printer, BookOpen, Star,
  Bell, RefreshCw, Globe, Search, Server,
  Activity, Gauge, Loader2,
} from 'lucide-react';
import { adminAPI } from '../../api/client';

/* ─── Compact stat card (inline, 1-row friendly) ─── */
function Stat({ icon: Icon, label, value, sub, accent }: {
  icon: any;
  label: string;
  value: number | string;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="flex items-center gap-3 bg-white/5 rounded-lg px-3 py-2.5 border border-white/10 min-w-0">
      <Icon className={`w-4 h-4 shrink-0 ${accent || 'text-purple-400'}`} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-1.5">
          <span className="text-lg font-bold text-white leading-none">{value}</span>
          <span className="text-gray-400 text-xs truncate">{label}</span>
        </div>
        {sub && <p className="text-gray-500 text-[11px] truncate mt-0.5">{sub}</p>}
      </div>
    </div>
  );
}

/* ─── Section header ─── */
function Section({ icon: Icon, title, children, cols }: {
  icon: any;
  title: string;
  children: React.ReactNode;
  cols?: string;
}) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-300 mb-2 flex items-center gap-1.5 uppercase tracking-wider">
        <Icon className="w-4 h-4 text-purple-400" />
        {title}
      </h3>
      <div className={cols || 'grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2'}>
        {children}
      </div>
    </div>
  );
}

/* ─── Docker container card ─── */
function DockerCard({ c }: { c: any }) {
  const isRunning = c.status === 'running';
  return (
    <div className="bg-white/5 rounded-lg px-3 py-2.5 border border-white/10">
      <div className="flex items-center gap-2 mb-1.5">
        <div className={`w-2 h-2 rounded-full ${isRunning ? 'bg-green-400' : 'bg-red-400'}`} />
        <span className="text-white text-sm font-medium truncate">{c.name}</span>
        {c.restart_count > 0 && (
          <span className="text-orange-400 text-[10px] font-mono ml-auto">R:{c.restart_count}</span>
        )}
      </div>
      <div className="grid grid-cols-3 gap-1 text-[11px]">
        <div>
          <span className="text-gray-500">CPU</span>
          <p className="text-gray-300 font-mono">{c.cpu}</p>
        </div>
        <div>
          <span className="text-gray-500">RAM</span>
          <p className="text-gray-300 font-mono">{c.mem_perc}</p>
        </div>
        <div>
          <span className="text-gray-500">NET</span>
          <p className="text-gray-300 font-mono truncate">{c.net_io?.split('/')[0]?.trim()}</p>
        </div>
      </div>
    </div>
  );
}

/* ─── PageSpeed score circle ─── */
function ScoreCircle({ score, label }: { score: number; label: string }) {
  const color = score >= 90 ? 'text-green-400' : score >= 50 ? 'text-orange-400' : 'text-red-400';
  const bgColor = score >= 90 ? 'border-green-400/30' : score >= 50 ? 'border-orange-400/30' : 'border-red-400/30';
  return (
    <div className="flex flex-col items-center gap-1">
      <div className={`w-14 h-14 rounded-full border-[3px] ${bgColor} flex items-center justify-center`}>
        <span className={`text-lg font-bold ${color}`}>{score}</span>
      </div>
      <span className="text-gray-400 text-[11px] text-center">{label}</span>
    </div>
  );
}

function PageSpeedMetric({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div className="text-center">
      <p className="text-white font-mono text-sm">{value}{unit && <span className="text-gray-500 text-xs"> {unit}</span>}</p>
      <p className="text-gray-500 text-[11px]">{label}</p>
    </div>
  );
}

/* ─── PageSpeed Widget ─── */
function PageSpeedWidget({ t }: { t: (key: string) => string }) {
  const [strategy, setStrategy] = useState<'mobile' | 'desktop'>('mobile');
  const [enabled, setEnabled] = useState(false);
  const [showKeyInput, setShowKeyInput] = useState(false);
  const [keyDraft, setKeyDraft] = useState('');
  const [error, setError] = useState('');

  // Load API key from backend
  const { data: keyData } = useQuery({
    queryKey: ['admin-setting', 'pagespeed_api_key'],
    queryFn: () => adminAPI.getSetting('pagespeed_api_key'),
  });
  const apiKey = keyData?.value || '';

  const queryClient = useQueryClient();

  const saveKey = async () => {
    const trimmed = keyDraft.trim();
    await adminAPI.setSetting('pagespeed_api_key', trimmed);
    setShowKeyInput(false);
    setError('');
    queryClient.invalidateQueries({ queryKey: ['admin-setting', 'pagespeed_api_key'] });
  };

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ['pagespeed', strategy, apiKey],
    queryFn: async () => {
      let url = `https://www.googleapis.com/pagespeedonline/v5/runPagespeed?url=https://filamenthub.ru&strategy=${strategy}&category=performance`;
      if (apiKey) url += `&key=${apiKey}`;
      const res = await fetch(url);
      if (res.status === 429) {
        setError(t('adminStats.pagespeed.rateLimited'));
        throw new Error('Rate limited');
      }
      if (!res.ok) throw new Error('PageSpeed API error');
      setError('');
      return res.json();
    },
    enabled,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const lhr = data?.lighthouseResult;
  const score = lhr ? Math.round((lhr.categories?.performance?.score || 0) * 100) : null;
  const audits = lhr?.audits;

  return (
    <div className="bg-white/5 rounded-lg p-4 border border-white/10">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Gauge className="w-4 h-4 text-purple-400" />
          <span className="text-white text-sm font-medium">PageSpeed Insights</span>
          <button
            onClick={() => { setShowKeyInput(!showKeyInput); setKeyDraft(apiKey); }}
            className="text-gray-500 hover:text-gray-300 transition-colors"
            title={t('adminStats.pagespeed.apiKeySettings')}
          >
            <Settings className="w-3.5 h-3.5" />
          </button>
          {apiKey && <span className="text-green-500 text-[10px]">API Key</span>}
        </div>
        <div className="flex items-center gap-2">
          <div className="flex bg-white/5 rounded-lg p-0.5">
            <button
              onClick={() => { setStrategy('mobile'); setEnabled(true); }}
              className={`px-2.5 py-1 text-xs rounded-md transition-colors ${strategy === 'mobile' ? 'bg-purple-600 text-white' : 'text-gray-400 hover:text-white'}`}
            >
              Mobile
            </button>
            <button
              onClick={() => { setStrategy('desktop'); setEnabled(true); }}
              className={`px-2.5 py-1 text-xs rounded-md transition-colors ${strategy === 'desktop' ? 'bg-purple-600 text-white' : 'text-gray-400 hover:text-white'}`}
            >
              Desktop
            </button>
          </div>
          {!enabled && (
            <button
              onClick={() => setEnabled(true)}
              className="px-3 py-1 text-xs bg-purple-600 hover:bg-purple-500 text-white rounded-lg transition-colors"
            >
              {t('adminStats.pagespeed.check')}
            </button>
          )}
        </div>
      </div>

      {/* API Key input */}
      {showKeyInput && (
        <div className="flex items-center gap-2 mb-3">
          <input
            type="password"
            value={keyDraft}
            onChange={e => setKeyDraft(e.target.value)}
            placeholder="Google API Key"
            className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
          />
          <button onClick={saveKey}
            className="px-3 py-1.5 text-xs bg-purple-600 hover:bg-purple-500 text-white rounded-lg transition-colors"
          >
            {t('adminStats.pagespeed.saveKey')}
          </button>
        </div>
      )}

      {error && <p className="text-orange-400 text-xs mb-2">{error}</p>}

      {!enabled && !showKeyInput && (
        <p className="text-gray-500 text-xs">
          {apiKey ? t('adminStats.pagespeed.hint') : t('adminStats.pagespeed.noKey')}
        </p>
      )}

      {(isLoading || isFetching) && (
        <div className="flex items-center justify-center py-6 gap-2">
          <Loader2 className="w-4 h-4 text-purple-400 animate-spin" />
          <span className="text-gray-400 text-sm">{t('adminStats.pagespeed.analyzing')}</span>
        </div>
      )}

      {score !== null && !isFetching && (
        <div className="flex items-start gap-6">
          <ScoreCircle score={score} label="Performance" />
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-6 gap-y-2 flex-1">
            {audits?.['first-contentful-paint'] && (
              <PageSpeedMetric label="FCP" value={audits['first-contentful-paint'].displayValue} />
            )}
            {audits?.['largest-contentful-paint'] && (
              <PageSpeedMetric label="LCP" value={audits['largest-contentful-paint'].displayValue} />
            )}
            {audits?.['total-blocking-time'] && (
              <PageSpeedMetric label="TBT" value={audits['total-blocking-time'].displayValue} />
            )}
            {audits?.['cumulative-layout-shift'] && (
              <PageSpeedMetric label="CLS" value={audits['cumulative-layout-shift'].displayValue} />
            )}
            {audits?.['speed-index'] && (
              <PageSpeedMetric label="SI" value={audits['speed-index'].displayValue} />
            )}
            {audits?.interactive && (
              <PageSpeedMetric label="TTI" value={audits.interactive.displayValue} />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── SEO Section ─── */
function SeoSection({ t }: { t: (key: string) => string }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-gray-300 mb-2 flex items-center gap-1.5 uppercase tracking-wider">
        <Globe className="w-4 h-4 text-purple-400" />
        {t('adminStats.seo.title')}
      </h3>

      {/* Webmaster links */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
        <a href="https://webmaster.yandex.ru/site/https:filamenthub.ru:443/dashboard/"
          target="_blank" rel="noopener noreferrer"
          className="flex items-center gap-2 bg-white/5 rounded-lg px-3 py-2.5 border border-white/10 hover:bg-white/10 transition-colors"
        >
          <Search className="w-4 h-4 text-yellow-400 shrink-0" />
          <span className="text-gray-300 text-xs">{t('adminStats.seo.yandexWebmaster')}</span>
        </a>
        <a href="https://search.google.com/search-console?resource_id=https%3A%2F%2Ffilamenthub.ru%2F"
          target="_blank" rel="noopener noreferrer"
          className="flex items-center gap-2 bg-white/5 rounded-lg px-3 py-2.5 border border-white/10 hover:bg-white/10 transition-colors"
        >
          <Search className="w-4 h-4 text-blue-400 shrink-0" />
          <span className="text-gray-300 text-xs">{t('adminStats.seo.googleConsole')}</span>
        </a>
        <a href="https://filamenthub.ru/robots.txt" target="_blank" rel="noopener noreferrer"
          className="flex items-center gap-2 bg-white/5 rounded-lg px-3 py-2.5 border border-white/10 hover:bg-white/10 transition-colors"
        >
          <span className="text-gray-300 text-xs">robots.txt</span>
        </a>
        <a href="https://filamenthub.ru/sitemap.xml" target="_blank" rel="noopener noreferrer"
          className="flex items-center gap-2 bg-white/5 rounded-lg px-3 py-2.5 border border-white/10 hover:bg-white/10 transition-colors"
        >
          <span className="text-gray-300 text-xs">sitemap.xml</span>
        </a>
      </div>

      {/* PageSpeed widget */}
      <PageSpeedWidget t={t} />
    </div>
  );
}

/* ─── Docker Section ─── */
function DockerSection({ t }: { t: (key: string) => string }) {
  const [enabled, setEnabled] = useState(false);

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['admin-docker-stats'],
    queryFn: () => adminAPI.getDockerStats(),
    enabled,
    staleTime: 0,
    retry: false,
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-gray-300 flex items-center gap-1.5 uppercase tracking-wider">
          <Server className="w-4 h-4 text-purple-400" />
          {t('adminStats.docker.title')}
        </h3>
        <div className="flex items-center gap-2">
          {enabled && (
            <button onClick={() => refetch()}
              className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin' : ''}`} />
            </button>
          )}
          {!enabled && (
            <button onClick={() => setEnabled(true)}
              className="px-3 py-1 text-xs bg-purple-600 hover:bg-purple-500 text-white rounded-lg transition-colors"
            >
              {t('adminStats.docker.load')}
            </button>
          )}
        </div>
      </div>

      {isLoading && (
        <div className="flex items-center justify-center py-4 gap-2">
          <Loader2 className="w-4 h-4 text-purple-400 animate-spin" />
          <span className="text-gray-400 text-sm">{t('adminStats.docker.loading')}</span>
        </div>
      )}

      {data?.error && (
        <p className="text-orange-400 text-xs">{data.error}</p>
      )}

      {data?.containers && data.containers.length > 0 && !isFetching && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {data.containers.map((c: any) => (
            <DockerCard key={c.name} c={c} />
          ))}
        </div>
      )}
    </div>
  );
}

/* ─── Main Component ─── */
export function AdminStats() {
  const { t } = useTranslation();
  const { data: stats, isLoading, refetch, isFetching, dataUpdatedAt } = useQuery({
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
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-white">{t('adminStats.title')}</h2>
        <div className="flex items-center gap-2">
          {updatedAt && <span className="text-gray-500 text-xs">{updatedAt}</span>}
          <button
            onClick={() => refetch()}
            className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-gray-400 hover:text-white transition-colors"
            title={t('adminStats.refresh')}
          >
            <RefreshCw className={`w-4 h-4 ${isFetching ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Users */}
      <Section icon={Users} title={t('adminStats.users')}>
        <Stat icon={Users} label={t('adminStats.totalUsers')} value={stats.users.total} />
        <Stat icon={TrendingUp} label={t('adminStats.active24h')} value={stats.users.active_24h} accent="text-green-400" />
        <Stat icon={TrendingUp} label={t('adminStats.active7d')} value={stats.users.active_7d} accent="text-green-400" />
        <Stat icon={Users} label={t('adminStats.registered24h')} value={stats.users.registered_24h} accent="text-blue-400" />
        <Stat icon={Users} label={t('adminStats.registered7d')} value={stats.users.registered_7d} accent="text-blue-400" />
        <Stat icon={Users} label={t('adminStats.registered30d')} value={stats.users.registered_30d} accent="text-blue-400" />
        <Stat icon={Building2} label={t('adminStats.brandReps')} value={stats.users.brands} />
        <Stat icon={BarChart3} label={t('adminStats.admins')} value={stats.users.admins} />
      </Section>

      {/* Brands + Presets (combined row) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <Section icon={Building2} title={t('adminStats.brands')} cols="grid grid-cols-3 gap-2">
          <Stat icon={Building2} label={t('adminStats.totalBrands')} value={stats.brands.total} />
          <Stat icon={TrendingUp} label={t('adminStats.verified')} value={stats.brands.verified} accent="text-green-400" />
          <Stat icon={Settings} label={t('adminStats.pendingVerification')} value={stats.brands.pending_verification} accent="text-yellow-400" />
        </Section>

        <Section icon={Settings} title={t('adminStats.presets')} cols="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <Stat icon={Settings} label={t('adminStats.totalPresets')} value={stats.presets.total} />
          <Stat icon={TrendingUp} label={t('adminStats.approved')} value={stats.presets.approved} accent="text-green-400" />
          <Stat icon={Activity} label={t('adminStats.pendingModeration')} value={stats.presets.pending_moderation} accent="text-yellow-400" />
          <Stat icon={BarChart3} label={t('adminStats.rejected')} value={stats.presets.rejected} accent="text-red-400" />
        </Section>
      </div>

      {/* Content */}
      <Section icon={Package} title={t('adminStats.content')}>
        <Stat icon={Package} label={t('adminStats.filaments')} value={stats.content.filaments} />
        <Stat icon={Printer} label={t('adminStats.printers')} value={stats.content.printers} />
        <Stat icon={Settings} label={t('adminStats.printerProfiles')} value={stats.content.printer_profiles} />
        <Stat icon={Star} label={t('adminStats.reviewsTotal')} value={stats.content.reviews_total}
          sub={t('adminStats.reviewsWeek', { count: stats.content.reviews_7d })} />
        <Stat icon={BookOpen} label={t('adminStats.wikiArticles')} value={stats.content.wiki_articles} />
      </Section>

      {/* Hardware + Notifications (combined) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className="lg:col-span-2">
          <Section icon={HardDrive} title={t('adminStats.hardware')} cols="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <Stat icon={HardDrive} label={t('adminStats.devices')} value={stats.hardware.devices} />
            <Stat icon={Package} label={t('adminStats.spools')} value={stats.hardware.spools} />
            <Stat icon={Settings} label={t('adminStats.gateSlots')} value={stats.hardware.gate_slots}
              sub={t('adminStats.gateSlotsAssigned', { count: stats.hardware.gate_slots_assigned })} />
            <Stat icon={RefreshCw} label={t('adminStats.syncDevices')} value={stats.hardware.sync_devices}
              sub={t('adminStats.syncActive7d', { count: stats.hardware.sync_devices_active_7d })} />
          </Section>
        </div>
        <Section icon={Bell} title={t('adminStats.notificationsSection')} cols="grid grid-cols-1 gap-2">
          <Stat icon={Bell} label={t('adminStats.unreadNotifications')} value={stats.notifications.unread}
            accent={stats.notifications.unread > 0 ? 'text-orange-400' : 'text-purple-400'} />
        </Section>
      </div>

      {/* Docker */}
      <DockerSection t={t} />

      {/* SEO Tools */}
      <SeoSection t={t} />
    </div>
  );
}
