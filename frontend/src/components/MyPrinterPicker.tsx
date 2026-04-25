/** Виджет выбора основного принтера пользователя из каталога */

import { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Printer as PrinterIcon, Search, Check, X, Loader2, AlertCircle } from 'lucide-react';
import type { AxiosError } from 'axios';
import { authAPI, printersAPI } from '../api/client';
import { translateApiError } from '../utils/translateApiError';
import { useAuth } from '../contexts/AuthContext';
import type { User } from '../types/api';

interface MyPrinterPickerProps {
  user: User;
}

export const MyPrinterPicker: React.FC<MyPrinterPickerProps> = ({ user }) => {
  const { t } = useTranslation();
  const { refreshUser } = useAuth();
  const queryClient = useQueryClient();

  const [pickerOpen, setPickerOpen] = useState(false);
  const [search, setSearch] = useState('');
  const [error, setError] = useState<string | null>(null);

  // Подгрузка деталей выбранного принтера
  const { data: currentPrinter, isLoading: isLoadingCurrent } = useQuery({
    queryKey: ['printer', user.printer_id],
    queryFn: () => (user.printer_id ? printersAPI.get(user.printer_id) : null),
    enabled: !!user.printer_id,
  });

  // Список принтеров для выбора (загружается только когда picker открыт)
  const { data: printersList, isLoading: isLoadingList } = useQuery({
    queryKey: ['printers', 'picker', search],
    queryFn: () =>
      printersAPI.list({
        page: 1,
        size: 50,
        active_only: true,
        search: search.trim() || undefined,
      }),
    enabled: pickerOpen,
  });

  const updateMutation = useMutation({
    mutationFn: (printer_id: number | null) => authAPI.updateProfile({ printer_id }),
    onSuccess: () => {
      setError(null);
      setPickerOpen(false);
      setSearch('');
      refreshUser();
      queryClient.invalidateQueries({ queryKey: ['user'] });
      queryClient.invalidateQueries({ queryKey: ['printer'] });
    },
    onError: (err: AxiosError<{ detail: unknown }>) => {
      setError(translateApiError(t, err.response?.data?.detail, t('myPrinter.updateError')));
    },
  });

  const handleSelect = (printerId: number) => {
    updateMutation.mutate(printerId);
  };

  const handleClear = () => {
    updateMutation.mutate(null);
  };

  const printerList = useMemo(() => printersList?.items ?? [], [printersList]);

  return (
    <div className="bg-gradient-to-br from-gray-900/80 to-gray-800/80 rounded-2xl p-6 border border-white/10">
      <div className="flex items-center gap-3 mb-4">
        <div className="p-2 bg-blue-600/20 rounded-xl">
          <PrinterIcon className="w-5 h-5 text-blue-400" />
        </div>
        <div>
          <h3 className="text-lg font-bold text-white">{t('myPrinter.title')}</h3>
          <p className="text-sm text-gray-400">{t('myPrinter.description')}</p>
        </div>
      </div>

      {/* Текущий выбор */}
      {user.printer_id ? (
        <div className="flex items-center justify-between gap-4 p-4 bg-white/5 rounded-xl border border-white/10 mb-3">
          <div className="flex items-center gap-3 min-w-0">
            {isLoadingCurrent ? (
              <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
            ) : currentPrinter ? (
              <>
                <div className="p-2 bg-emerald-500/15 rounded-lg shrink-0">
                  <Check className="w-4 h-4 text-emerald-400" />
                </div>
                <div className="min-w-0">
                  <div className="font-semibold text-white truncate">
                    {currentPrinter.manufacturer} {currentPrinter.model}
                  </div>
                  {currentPrinter.family && (
                    <div className="text-xs text-gray-400 truncate">
                      {currentPrinter.family}
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="flex items-center gap-2 text-amber-400">
                <AlertCircle className="w-4 h-4" />
                <span className="text-sm">{t('myPrinter.notFound')}</span>
              </div>
            )}
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => setPickerOpen(true)}
              disabled={updateMutation.isPending}
              className="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg transition-colors"
            >
              {t('myPrinter.change')}
            </button>
            <button
              type="button"
              onClick={handleClear}
              disabled={updateMutation.isPending}
              className="p-1.5 text-gray-400 hover:text-red-400 disabled:opacity-50 transition-colors"
              title={t('myPrinter.clear')}
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-center justify-between gap-4 p-4 bg-amber-500/5 rounded-xl border border-amber-500/20 mb-3">
          <div className="flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-amber-400 shrink-0" />
            <div className="text-sm text-amber-200">{t('myPrinter.noneSelected')}</div>
          </div>
          <button
            type="button"
            onClick={() => setPickerOpen(true)}
            disabled={updateMutation.isPending}
            className="px-3 py-1.5 text-sm bg-amber-500 hover:bg-amber-400 disabled:opacity-50 text-gray-900 font-medium rounded-lg transition-colors shrink-0"
          >
            {t('myPrinter.choose')}
          </button>
        </div>
      )}

      {error && (
        <div className="p-3 mb-3 bg-red-500/10 border border-red-500/30 rounded-lg text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Раскрываемая панель поиска */}
      {pickerOpen && (
        <div className="mt-3 bg-gray-950/40 rounded-xl border border-white/10 overflow-hidden">
          <div className="p-3 border-b border-white/10">
            <div className="relative">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t('myPrinter.searchPlaceholder')}
                className="w-full pl-9 pr-3 py-2 bg-white/5 text-white text-sm border border-white/10 rounded-lg focus:outline-none focus:border-blue-500"
                autoFocus
              />
            </div>
          </div>

          <div className="max-h-72 overflow-y-auto">
            {isLoadingList ? (
              <div className="flex items-center justify-center py-8 text-gray-400">
                <Loader2 className="w-5 h-5 animate-spin" />
              </div>
            ) : printerList.length === 0 ? (
              <div className="py-8 px-4 text-center text-sm text-gray-400">
                {t('myPrinter.empty')}
              </div>
            ) : (
              <ul className="divide-y divide-white/5">
                {printerList.map((p) => {
                  const isSelected = p.id === user.printer_id;
                  return (
                    <li key={p.id}>
                      <button
                        type="button"
                        onClick={() => handleSelect(p.id)}
                        disabled={updateMutation.isPending || isSelected}
                        className={`w-full text-left px-4 py-3 hover:bg-white/5 transition-colors flex items-center justify-between gap-3 ${
                          isSelected ? 'bg-blue-500/10' : ''
                        }`}
                      >
                        <div className="min-w-0">
                          <div className="font-medium text-white text-sm truncate">
                            {p.manufacturer} {p.model}
                          </div>
                          {p.family && (
                            <div className="text-xs text-gray-500 truncate">{p.family}</div>
                          )}
                        </div>
                        {isSelected && (
                          <Check className="w-4 h-4 text-blue-400 shrink-0" />
                        )}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <div className="p-2 border-t border-white/10 flex justify-end">
            <button
              type="button"
              onClick={() => {
                setPickerOpen(false);
                setSearch('');
              }}
              className="px-3 py-1.5 text-sm text-gray-400 hover:text-white transition-colors"
            >
              {t('common.cancel')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
