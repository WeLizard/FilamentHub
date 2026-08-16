/** Админ-панель для управления платформой */

import { lazy, Suspense, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Shield, FileText, Building2, Users, BarChart3, CheckCircle, Home, Package, User, LogOut, Database, Mail, Settings, BookOpen, Sparkles, ScanSearch, Layers, Loader2, Calculator } from 'lucide-react';
import { Printer3DIcon } from '../components/icons/Printer3DIcon';
import { useAuth } from '../contexts/AuthContext';
import { adminAPI } from '../api/client';
import { PageBackground } from '../components/PageBackground';

const AdminBrandRequests = lazy(() => import('../components/admin/AdminBrandRequests').then((module) => ({ default: module.AdminBrandRequests })));
const AdminBrands = lazy(() => import('../components/admin/AdminBrands').then((module) => ({ default: module.AdminBrands })));
const AdminMaterials = lazy(() => import('../components/admin/AdminMaterials').then((module) => ({ default: module.AdminMaterials })));
const AdminPresets = lazy(() => import('../components/admin/AdminPresets').then((module) => ({ default: module.AdminPresets })));
const AdminUsers = lazy(() => import('../components/admin/AdminUsers').then((module) => ({ default: module.AdminUsers })));
const AdminStats = lazy(() => import('../components/admin/AdminStats').then((module) => ({ default: module.AdminStats })));
const AdminPrinters = lazy(() => import('../components/admin/AdminPrinters').then((module) => ({ default: module.AdminPrinters })));
const AdminPrinterRequests = lazy(() => import('../components/admin/AdminPrinterRequests').then((module) => ({ default: module.AdminPrinterRequests })));
const AdminDatabaseDiagnostics = lazy(() => import('../components/admin/AdminDatabaseDiagnostics').then((module) => ({ default: module.AdminDatabaseDiagnostics })));
const AdminCommunications = lazy(() => import('../components/admin/AdminCommunications').then((module) => ({ default: module.AdminCommunications })));
const AdminMaintenance = lazy(() => import('../components/admin/AdminMaintenance').then((module) => ({ default: module.AdminMaintenance })));
const AdminWiki = lazy(() => import('../components/admin/AdminWiki').then((module) => ({ default: module.AdminWiki })));
const AdminSubscriptions = lazy(() => import('../components/admin/AdminSubscriptions').then((module) => ({ default: module.AdminSubscriptions })));
const AdminCalculatorDefaults = lazy(() => import('../components/admin/AdminCalculatorDefaults').then((module) => ({ default: module.AdminCalculatorDefaults })));
const AdminCalculatorCountryDefaults = lazy(() => import('../components/admin/AdminCalculatorCountryDefaults').then((module) => ({ default: module.AdminCalculatorCountryDefaults })));
const AdminOrcaSchemaObservations = lazy(() => import('../components/admin/AdminOrcaSchemaObservations').then((module) => ({ default: module.AdminOrcaSchemaObservations })));

type AdminTab = 'requests' | 'brands' | 'materials' | 'presets' | 'users' | 'stats' | 'printers' | 'printer-requests' | 'communications' | 'database' | 'maintenance' | 'wiki' | 'subscriptions' | 'calculator' | 'orca-schema';

export function AdminPanel() {
  const { t } = useTranslation();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<AdminTab>('requests');
  const schemaCountQuery = useQuery({
    queryKey: ['admin-orca-schema-count'],
    queryFn: () => adminAPI.listOrcaSchemaObservations({ page: 1, size: 1, status: 'new' }),
    enabled: user?.role === 'admin',
  });
  // Модерация — очередь, а не справочник: она копится, пока на неё не смотрят.
  const pendingPresetsQuery = useQuery({
    queryKey: ['admin-pending-presets-count'],
    queryFn: () => adminAPI.countPendingPresets(),
    enabled: user?.role === 'admin',
  });

  // Переписка и обращения ждут ответа человека: без метки о них узнают, только
  // если зайти во вкладку.
  const unreadCommunicationsQuery = useQuery({
    queryKey: ['admin-communications-unread-count'],
    queryFn: () => adminAPI.countUnreadCommunications(),
    enabled: user?.role === 'admin',
  });
  const unreadCommunications =
    (unreadCommunicationsQuery.data?.unread_emails || 0) +
    (unreadCommunicationsQuery.data?.new_feedback || 0);

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  if (!user || user.role !== 'admin') {
    return (
      <PageBackground className="flex items-center justify-center p-4">
        <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-8 border border-white/20 text-center max-w-md">
          <Shield className="w-16 h-16 text-red-400 mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-white mb-2">{t('adminPanel.accessDenied')}</h1>
          <p className="text-gray-300">{t('adminPanel.accessDeniedMessage')}</p>
        </div>
      </PageBackground>
    );
  }

  const tabs = [
    { id: 'requests' as AdminTab, label: t('adminPanel.tabs.requests'), shortLabel: t('adminPanel.shortTabs.requests'), icon: FileText, count: null },
    { id: 'brands' as AdminTab, label: t('adminPanel.tabs.brands'), shortLabel: t('adminPanel.shortTabs.brands'), icon: Building2, count: null },
    { id: 'materials' as AdminTab, label: t('adminPanel.tabs.materials'), shortLabel: t('adminPanel.shortTabs.materials'), icon: Layers, count: null },
    { id: 'presets' as AdminTab, label: t('adminPanel.tabs.presets'), shortLabel: t('adminPanel.shortTabs.presets'), icon: CheckCircle, count: pendingPresetsQuery.data?.pending_count || null },
    { id: 'printers' as AdminTab, label: t('adminPanel.tabs.printers'), shortLabel: t('adminPanel.shortTabs.printers'), icon: Printer3DIcon, count: null },
    { id: 'printer-requests' as AdminTab, label: t('adminPanel.tabs.printer-requests'), shortLabel: t('adminPanel.shortTabs.printer-requests'), icon: Package, count: null },
    { id: 'users' as AdminTab, label: t('adminPanel.tabs.users'), shortLabel: t('adminPanel.shortTabs.users'), icon: Users, count: null },
    { id: 'communications' as AdminTab, label: t('adminPanel.tabs.communications'), shortLabel: t('adminPanel.shortTabs.communications'), icon: Mail, count: unreadCommunications || null },
    { id: 'wiki' as AdminTab, label: t('adminPanel.tabs.wiki'), shortLabel: t('adminPanel.shortTabs.wiki'), icon: BookOpen, count: null },
    { id: 'stats' as AdminTab, label: t('adminPanel.tabs.stats'), shortLabel: t('adminPanel.shortTabs.stats'), icon: BarChart3, count: null },
    { id: 'database' as AdminTab, label: t('adminPanel.tabs.database'), shortLabel: t('adminPanel.shortTabs.database'), icon: Database, count: null },
    { id: 'orca-schema' as AdminTab, label: t('adminPanel.tabs.orcaSchema'), shortLabel: t('adminPanel.shortTabs.orcaSchema'), icon: ScanSearch, count: schemaCountQuery.data?.new_count ?? null },
    { id: 'calculator' as AdminTab, label: t('adminPanel.tabs.calculator'), shortLabel: t('adminPanel.shortTabs.calculator'), icon: Calculator, count: null },
    { id: 'subscriptions' as AdminTab, label: t('adminPanel.tabs.subscriptions'), shortLabel: t('adminPanel.shortTabs.subscriptions'), icon: Sparkles, count: null },
    { id: 'maintenance' as AdminTab, label: t('adminPanel.tabs.maintenance'), shortLabel: t('adminPanel.shortTabs.maintenance'), icon: Settings, count: null },
  ];

  return (
    <PageBackground className="py-4 md:py-8 px-2 md:px-4">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-4 md:mb-8">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
            <div className="flex items-center space-x-2 md:space-x-3">
              <Shield className="w-6 h-6 md:w-8 md:h-8 text-yellow-400" />
              <h1 className="text-xl md:text-3xl font-bold text-white">{t('adminPanel.header')}</h1>
            </div>
            <div className="flex flex-wrap items-center gap-2 md:gap-3">
              <Link
                to="/"
                className="flex items-center space-x-1.5 md:space-x-2 px-2.5 md:px-4 py-1.5 md:py-2 rounded-lg transition-all text-gray-300 hover:text-white hover:bg-white/10 text-xs md:text-base"
              >
                <Home className="w-4 h-4 md:w-5 md:h-5" />
                <span className="hidden sm:inline">{t('adminPanel.toHome')}</span>
              </Link>
              <Link
                to="/profile"
                className="flex items-center space-x-1.5 md:space-x-2 px-2.5 md:px-4 py-1.5 md:py-2 rounded-lg transition-all text-gray-300 hover:text-white hover:bg-white/10 text-xs md:text-base"
              >
                <User className="w-4 h-4 md:w-5 md:h-5" />
                <span className="hidden sm:inline">{t('adminPanel.toProfile')}</span>
              </Link>
              <button
                onClick={handleLogout}
                className="flex items-center space-x-1.5 md:space-x-2 px-2.5 md:px-4 py-1.5 md:py-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded-lg transition-all text-xs md:text-base"
              >
                <LogOut className="w-4 h-4 md:w-5 md:h-5" />
                <span className="hidden sm:inline">{t('adminPanel.logout')}</span>
              </button>
            </div>
          </div>
          <p className="text-gray-300 text-xs md:text-base">{t('adminPanel.subheader')}</p>
        </div>

        {/* Tabs */}
        <div className="bg-white/10 backdrop-blur-sm rounded-lg md:rounded-xl border border-white/20 mb-4 md:mb-6 p-1.5 md:p-2 flex flex-wrap gap-1.5 md:gap-2">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`
                  flex items-center gap-1.5 md:gap-2 px-2.5 md:px-4 py-1.5 md:py-2 rounded-lg transition-all text-xs md:text-sm
                  ${isActive
                    ? 'bg-purple-600 text-white shadow-lg'
                    : 'bg-white/5 text-gray-300 hover:bg-white/10'
                  }
                `}
              >
                <Icon className="w-3.5 h-3.5 md:w-4 md:h-4" />
                <span className="hidden md:inline">{tab.label}</span>
                <span className="md:hidden">{tab.shortLabel}</span>
                {tab.count !== null && tab.count > 0 && (
                  <span className={`
                    ml-1 md:ml-2 px-1.5 md:px-2 py-0.5 rounded-full text-[10px] md:text-xs font-semibold
                    ${isActive ? 'bg-purple-700' : 'bg-purple-600'}
                  `}>
                    {tab.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Content */}
        <div className="bg-white/10 backdrop-blur-sm rounded-lg md:rounded-xl border border-white/20 p-3 md:p-6">
          <Suspense fallback={<div className="flex min-h-48 items-center justify-center"><Loader2 className="h-7 w-7 animate-spin text-purple-300" /></div>}>
            {activeTab === 'requests' && <AdminBrandRequests />}
            {activeTab === 'brands' && <AdminBrands />}
            {activeTab === 'materials' && <AdminMaterials />}
            {activeTab === 'presets' && <AdminPresets />}
            {activeTab === 'printers' && <AdminPrinters />}
            {activeTab === 'printer-requests' && <AdminPrinterRequests />}
            {activeTab === 'users' && <AdminUsers />}
            {activeTab === 'communications' && <AdminCommunications />}
            {activeTab === 'wiki' && <AdminWiki />}
            {activeTab === 'stats' && <AdminStats />}
            {activeTab === 'database' && <AdminDatabaseDiagnostics />}
            {activeTab === 'orca-schema' && <AdminOrcaSchemaObservations />}
            {activeTab === 'calculator' && (
              <>
                <AdminCalculatorDefaults />
                <AdminCalculatorCountryDefaults />
              </>
            )}
            {activeTab === 'subscriptions' && <AdminSubscriptions />}
            {activeTab === 'maintenance' && <AdminMaintenance />}
          </Suspense>
        </div>
      </div>
    </PageBackground>
  );
}
