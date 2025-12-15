/** Админ-панель для управления платформой */

import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Shield, FileText, Building2, Users, BarChart3, CheckCircle, Home, Printer as PrinterIcon, Package, User, LogOut, Database, MessageCircle, Send, Settings } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { AdminBrandRequests } from '../components/admin/AdminBrandRequests';
import { AdminBrands } from '../components/admin/AdminBrands';
import { AdminPresets } from '../components/admin/AdminPresets';
import { AdminUsers } from '../components/admin/AdminUsers';
import { AdminStats } from '../components/admin/AdminStats';
import { AdminPrinters } from '../components/admin/AdminPrinters';
import { AdminPrinterRequests } from '../components/admin/AdminPrinterRequests';
import { AdminDatabase } from '../components/admin/AdminDatabase';
import { AdminFeedback } from '../components/admin/AdminFeedback';
import { AdminNotifications } from '../components/admin/AdminNotifications';
import { AdminMaintenance } from '../components/admin/AdminMaintenance';

type AdminTab = 'requests' | 'brands' | 'presets' | 'users' | 'stats' | 'printers' | 'printer-requests' | 'feedback' | 'notifications' | 'database' | 'maintenance';

export function AdminPanel() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<AdminTab>('requests');

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  // Проверка что пользователь админ
  if (!user || user.role !== 'admin') {
    return (
      <div className="min-h-screen bg-gradient-to-br from-purple-900 via-purple-800 to-indigo-900 flex items-center justify-center p-4">
        <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-8 border border-white/20 text-center max-w-md">
          <Shield className="w-16 h-16 text-red-400 mx-auto mb-4" />
          <h1 className="text-2xl font-bold text-white mb-2">Доступ запрещен</h1>
          <p className="text-gray-300">Эта страница доступна только администраторам</p>
        </div>
      </div>
    );
  }

  const tabs = [
    { id: 'requests' as AdminTab, label: 'Заявки на верификацию', icon: FileText, count: null },
    { id: 'brands' as AdminTab, label: 'Бренды', icon: Building2, count: null },
    { id: 'presets' as AdminTab, label: 'Модерация пресетов', icon: CheckCircle, count: null },
    { id: 'printers' as AdminTab, label: 'Принтеры', icon: PrinterIcon, count: null },
    { id: 'printer-requests' as AdminTab, label: 'Заявки на принтеры', icon: Package, count: null },
    { id: 'users' as AdminTab, label: 'Пользователи', icon: Users, count: null },
    { id: 'feedback' as AdminTab, label: 'Обратная связь', icon: MessageCircle, count: null },
    { id: 'notifications' as AdminTab, label: 'Уведомления', icon: Send, count: null },
    { id: 'stats' as AdminTab, label: 'Статистика', icon: BarChart3, count: null },
    { id: 'database' as AdminTab, label: 'База данных', icon: Database, count: null },
    { id: 'maintenance' as AdminTab, label: 'Технические работы', icon: Settings, count: null },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-900 via-purple-800 to-indigo-900 py-4 md:py-8 px-2 md:px-4">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-4 md:mb-8">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-2">
            <div className="flex items-center gap-2 md:gap-3">
              <Shield className="w-6 h-6 md:w-8 md:h-8 text-yellow-400" />
              <h1 className="text-xl md:text-3xl font-bold text-white">Админ-панель</h1>
            </div>
            <div className="flex items-center gap-2 md:gap-3">
              <Link
                to="/"
                className="flex items-center gap-1.5 px-2.5 md:px-4 py-1.5 md:py-2 rounded-lg transition-all text-gray-300 hover:text-white hover:bg-white/10 text-xs md:text-base"
              >
                <Home className="w-4 h-4 md:w-5 md:h-5" />
                <span className="hidden sm:inline">Главная</span>
              </Link>
              <Link
                to="/profile"
                className="flex items-center gap-1.5 px-2.5 md:px-4 py-1.5 md:py-2 rounded-lg transition-all text-gray-300 hover:text-white hover:bg-white/10 text-xs md:text-base"
              >
                <User className="w-4 h-4 md:w-5 md:h-5" />
                <span className="hidden sm:inline">Профиль</span>
              </Link>
              <button
                onClick={handleLogout}
                className="flex items-center gap-1.5 px-2.5 md:px-4 py-1.5 md:py-2 bg-red-600/20 hover:bg-red-600/30 active:bg-red-600/40 text-red-400 rounded-lg transition-all text-xs md:text-base"
              >
                <LogOut className="w-4 h-4 md:w-5 md:h-5" />
                <span className="hidden sm:inline">Выход</span>
              </button>
            </div>
          </div>
          <p className="text-gray-300 text-xs md:text-base">Управление FilamentHub</p>
        </div>

        {/* Tabs - горизонтальный скролл на мобильных */}
        <div className="overflow-x-auto -mx-2 px-2 md:mx-0 md:px-0 mb-4 md:mb-6 scrollbar-hide">
          <div className="bg-white/10 backdrop-blur-sm rounded-lg md:rounded-xl border border-white/20 p-1.5 md:p-2 flex gap-1.5 md:gap-2 min-w-max">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`
                    flex items-center gap-1.5 px-2.5 md:px-4 py-1.5 md:py-2 rounded-lg transition-all whitespace-nowrap text-xs md:text-sm
                    ${isActive
                      ? 'bg-purple-600 text-white shadow-lg'
                      : 'bg-white/5 text-gray-300 hover:bg-white/10 active:bg-white/15'
                    }
                  `}
                >
                  <Icon className="w-3.5 h-3.5 md:w-4 md:h-4" />
                  <span className="hidden md:inline">{tab.label}</span>
                  <span className="md:hidden">{tab.label.split(' ')[0]}</span>
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
        </div>

        {/* Content */}
        <div className="bg-white/10 backdrop-blur-sm rounded-lg md:rounded-xl border border-white/20 p-3 md:p-6">
          {activeTab === 'requests' && <AdminBrandRequests />}
          {activeTab === 'brands' && <AdminBrands />}
          {activeTab === 'presets' && <AdminPresets />}
          {activeTab === 'printers' && <AdminPrinters />}
          {activeTab === 'printer-requests' && <AdminPrinterRequests />}
          {activeTab === 'users' && <AdminUsers />}
          {activeTab === 'feedback' && <AdminFeedback />}
          {activeTab === 'notifications' && <AdminNotifications />}
          {activeTab === 'stats' && <AdminStats />}
          {activeTab === 'database' && <AdminDatabase />}
          {activeTab === 'maintenance' && <AdminMaintenance />}
        </div>
      </div>
    </div>
  );
}

