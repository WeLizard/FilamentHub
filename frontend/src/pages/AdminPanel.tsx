/** Админ-панель для управления платформой */

import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Shield, FileText, Building2, Users, BarChart3, CheckCircle, Home, Printer as PrinterIcon, Package, User, LogOut } from 'lucide-react';
import { useAuth } from '../contexts/AuthContext';
import { AdminBrandRequests } from '../components/admin/AdminBrandRequests';
import { AdminBrands } from '../components/admin/AdminBrands';
import { AdminPresets } from '../components/admin/AdminPresets';
import { AdminUsers } from '../components/admin/AdminUsers';
import { AdminStats } from '../components/admin/AdminStats';
import { AdminPrinters } from '../components/admin/AdminPrinters';
import { AdminPrinterRequests } from '../components/admin/AdminPrinterRequests';

type AdminTab = 'requests' | 'brands' | 'presets' | 'users' | 'stats' | 'printers' | 'printer-requests';

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
    { id: 'stats' as AdminTab, label: 'Статистика', icon: BarChart3, count: null },
  ];

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-900 via-purple-800 to-indigo-900 py-8 px-4">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center space-x-3">
              <Shield className="w-8 h-8 text-yellow-400" />
              <h1 className="text-3xl font-bold text-white">Админ-панель</h1>
            </div>
            <div className="flex items-center space-x-3">
              <Link
                to="/"
                className="flex items-center space-x-2 px-4 py-2 rounded-lg transition-all text-gray-300 hover:text-white hover:bg-white/10"
              >
                <Home className="w-5 h-5" />
                <span>На главную</span>
              </Link>
              <Link
                to="/profile"
                className="flex items-center space-x-2 px-4 py-2 rounded-lg transition-all text-gray-300 hover:text-white hover:bg-white/10"
              >
                <User className="w-5 h-5" />
                <span>Профиль</span>
              </Link>
              <button
                onClick={handleLogout}
                className="flex items-center space-x-2 px-4 py-2 bg-red-600/20 hover:bg-red-600/30 text-red-400 rounded-lg transition-all"
              >
                <LogOut className="w-5 h-5" />
                <span>Выход</span>
              </button>
            </div>
          </div>
          <p className="text-gray-300">Управление платформой FilamentHub</p>
        </div>

        {/* Tabs */}
        <div className="bg-white/10 backdrop-blur-sm rounded-xl border border-white/20 mb-6 p-2 flex flex-wrap gap-2">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`
                  flex items-center space-x-2 px-4 py-2 rounded-lg transition-all
                  ${isActive
                    ? 'bg-purple-600 text-white shadow-lg'
                    : 'bg-white/5 text-gray-300 hover:bg-white/10'
                  }
                `}
              >
                <Icon className="w-4 h-4" />
                <span>{tab.label}</span>
                {tab.count !== null && tab.count > 0 && (
                  <span className={`
                    ml-2 px-2 py-0.5 rounded-full text-xs font-semibold
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
        <div className="bg-white/10 backdrop-blur-sm rounded-xl border border-white/20 p-6">
          {activeTab === 'requests' && <AdminBrandRequests />}
          {activeTab === 'brands' && <AdminBrands />}
          {activeTab === 'presets' && <AdminPresets />}
          {activeTab === 'printers' && <AdminPrinters />}
          {activeTab === 'printer-requests' && <AdminPrinterRequests />}
          {activeTab === 'users' && <AdminUsers />}
          {activeTab === 'stats' && <AdminStats />}
        </div>
      </div>
    </div>
  );
}

