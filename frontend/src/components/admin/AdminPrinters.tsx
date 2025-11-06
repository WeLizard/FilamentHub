/** Компонент для управления принтерами в админке */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Printer, Plus, Edit, Trash2, X, Save } from 'lucide-react';
import { adminAPI, printersAPI } from '../../api/client';
import type { Printer as PrinterType } from '../../types/api';
import { useHeaderVisible } from '../../hooks/useHeaderVisible';

export function AdminPrinters() {
  const isHeaderVisible = useHeaderVisible();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);
  const [editingPrinter, setEditingPrinter] = useState<PrinterType | null>(null);
  const [searchQuery, setSearchQuery] = useState('');

  // Загрузка принтеров
  const { data, isLoading, error } = useQuery({
    queryKey: ['admin-printers', page, searchQuery],
    queryFn: () => printersAPI.list({
      page,
      size: 20,
      active_only: false,
      search: searchQuery || undefined,
    }),
  });

  // Создание принтера
  const createMutation = useMutation({
    mutationFn: adminAPI.createPrinter,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-printers'] });
      setIsCreateModalOpen(false);
    },
  });

  // Обновление принтера
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => adminAPI.updatePrinter(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-printers'] });
      setEditingPrinter(null);
    },
  });

  // Удаление принтера
  const deleteMutation = useMutation({
    mutationFn: (id: number) => adminAPI.deletePrinter(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin-printers'] });
    },
  });

  const handleDelete = (id: number) => {
    if (confirm('Вы уверены, что хотите удалить этот принтер?')) {
      deleteMutation.mutate(id);
    }
  };

  if (isLoading) {
    return <div className="text-center py-12 text-gray-400">Загрузка принтеров...</div>;
  }

  // Если есть реальная ошибка (не просто пустой список)
  if (error) {
    const errorMessage = error instanceof Error 
      ? error.message 
      : 'Неизвестная ошибка';
    
    // Проверяем, не является ли это просто отсутствием данных
    const isNotFound = errorMessage.includes('404') || errorMessage.includes('not found');
    
    if (!isNotFound) {
      return (
        <div className="text-center py-12">
          <div className="text-red-400 mb-2">Ошибка загрузки принтеров</div>
          <div className="text-gray-400 text-sm">{errorMessage}</div>
        </div>
      );
    }
  }

  const printers = data?.items || [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold text-white mb-2">Принтеры</h2>
          <p className="text-gray-400">Всего: {data?.total || 0}</p>
        </div>
        <button
          onClick={() => setIsCreateModalOpen(true)}
          className="flex items-center space-x-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-xl transition-all"
        >
          <Plus className="w-5 h-5" />
          <span>Добавить принтер</span>
        </button>
      </div>

      {/* Поиск */}
      <div className="relative">
        <input
          type="text"
          value={searchQuery}
          onChange={(e) => {
            setSearchQuery(e.target.value);
            setPage(1);
          }}
          placeholder="Поиск по названию, производителю или модели..."
          className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
        />
      </div>

      {/* Список принтеров */}
      {printers.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <Printer className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p>Нет принтеров для отображения</p>
        </div>
      ) : (
        <div className="space-y-4">
          {printers.map((printer) => (
            <div
              key={printer.id}
              className="bg-white/5 rounded-xl p-4 border border-white/10 hover:border-white/20 transition-all"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center space-x-3 mb-2">
                    <Printer className="w-5 h-5 text-purple-400" />
                    <h3 className="text-lg font-semibold text-white">{printer.name}</h3>
                    <span className="px-2 py-1 rounded bg-purple-500/20 text-purple-300 text-xs font-semibold">
                      {printer.manufacturer} {printer.model}
                    </span>
                    {!printer.active && (
                      <span className="px-2 py-1 rounded bg-red-500/20 text-red-400 text-xs font-semibold">
                        Неактивен
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-gray-400 space-y-1">
                    <p>Slug: {printer.slug}</p>
                    {printer.description && <p>{printer.description}</p>}
                    {(printer.build_volume_x || printer.build_volume_y || printer.build_volume_z) && (
                      <p>
                        Объём печати: {printer.build_volume_x || '?'} × {printer.build_volume_y || '?'} × {printer.build_volume_z || '?'} мм
                      </p>
                    )}
                    {printer.nozzle_diameter && <p>Сопло: {printer.nozzle_diameter}мм</p>}
                    {(printer.max_extruder_temp || printer.max_bed_temp) && (
                      <p>
                        Температуры: сопло до {printer.max_extruder_temp || '?'}°C, стол до {printer.max_bed_temp || '?'}°C
                      </p>
                    )}
                  </div>
                </div>
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => setEditingPrinter(printer)}
                    className="p-2 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-all"
                    title="Редактировать"
                  >
                    <Edit className="w-5 h-5" />
                  </button>
                  <button
                    onClick={() => handleDelete(printer.id)}
                    className="p-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg transition-all"
                    title="Удалить"
                  >
                    <Trash2 className="w-5 h-5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Пагинация */}
      {data && data.pages > 1 && (
        <div className="flex items-center justify-center space-x-2">
          <button
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page === 1}
            className="px-4 py-2 rounded-lg bg-white/5 text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-white/10"
          >
            Назад
          </button>
          <span className="text-gray-400">Страница {page} из {data.pages}</span>
          <button
            onClick={() => setPage(p => Math.min(data.pages, p + 1))}
            disabled={page === data.pages}
            className="px-4 py-2 rounded-lg bg-white/5 text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-white/10"
          >
            Вперед
          </button>
        </div>
      )}

      {/* Модальное окно создания/редактирования */}
      {(isCreateModalOpen || editingPrinter) && (
        <PrinterModal
          printer={editingPrinter}
          onClose={() => {
            setIsCreateModalOpen(false);
            setEditingPrinter(null);
          }}
          onSave={(data) => {
            if (editingPrinter) {
              updateMutation.mutate({ id: editingPrinter.id, data });
            } else {
              createMutation.mutate(data);
            }
          }}
          isLoading={createMutation.isPending || updateMutation.isPending}
        />
      )}
    </div>
  );
}

interface PrinterModalProps {
  printer: PrinterType | null;
  onClose: () => void;
  onSave: (data: any) => void;
  isLoading: boolean;
}

function PrinterModal({ printer, onClose, onSave, isLoading }: PrinterModalProps) {
  const isHeaderVisible = useHeaderVisible();
  const [formData, setFormData] = useState({
    name: printer?.name || '',
    manufacturer: printer?.manufacturer || '',
    model: printer?.model || '',
    slug: printer?.slug || '',
    description: printer?.description || '',
    build_volume_x: printer?.build_volume_x?.toString() || '',
    build_volume_y: printer?.build_volume_y?.toString() || '',
    build_volume_z: printer?.build_volume_z?.toString() || '',
    nozzle_diameter: printer?.nozzle_diameter?.toString() || '',
    max_extruder_temp: printer?.max_extruder_temp?.toString() || '',
    max_bed_temp: printer?.max_bed_temp?.toString() || '',
    image_url: printer?.image_url || '',
    active: printer?.active ?? true,
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const data = {
      name: formData.name,
      manufacturer: formData.manufacturer,
      model: formData.model,
      slug: formData.slug,
      description: formData.description || undefined,
      build_volume_x: formData.build_volume_x ? parseFloat(formData.build_volume_x) : undefined,
      build_volume_y: formData.build_volume_y ? parseFloat(formData.build_volume_y) : undefined,
      build_volume_z: formData.build_volume_z ? parseFloat(formData.build_volume_z) : undefined,
      nozzle_diameter: formData.nozzle_diameter ? parseFloat(formData.nozzle_diameter) : undefined,
      max_extruder_temp: formData.max_extruder_temp ? parseInt(formData.max_extruder_temp) : undefined,
      max_bed_temp: formData.max_bed_temp ? parseInt(formData.max_bed_temp) : undefined,
      image_url: formData.image_url || undefined,
      ...(printer ? { active: formData.active } : {}),
    };
    onSave(data);
  };

  return (
    <div className={`fixed inset-0 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4 z-50 ${isHeaderVisible ? 'pt-[88px]' : ''}`}>
      <div className="bg-gradient-to-br from-purple-900 to-indigo-900 rounded-2xl max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col border border-white/20">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-white/10">
          <h3 className="text-2xl font-bold text-white">
            {printer ? 'Редактировать принтер' : 'Создать принтер'}
          </h3>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-6">
          <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Название *</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Производитель *</label>
              <input
                type="text"
                value={formData.manufacturer}
                onChange={(e) => setFormData({ ...formData, manufacturer: e.target.value })}
                required
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Модель *</label>
              <input
                type="text"
                value={formData.model}
                onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                required
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Slug *</label>
              <input
                type="text"
                value={formData.slug}
                onChange={(e) => setFormData({ ...formData, slug: e.target.value })}
                required
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">Описание</label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              rows={3}
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
            />
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Объём X (мм)</label>
              <input
                type="number"
                step="0.1"
                value={formData.build_volume_x}
                onChange={(e) => setFormData({ ...formData, build_volume_x: e.target.value })}
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Объём Y (мм)</label>
              <input
                type="number"
                step="0.1"
                value={formData.build_volume_y}
                onChange={(e) => setFormData({ ...formData, build_volume_y: e.target.value })}
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Объём Z (мм)</label>
              <input
                type="number"
                step="0.1"
                value={formData.build_volume_z}
                onChange={(e) => setFormData({ ...formData, build_volume_z: e.target.value })}
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Диаметр сопла (мм)</label>
              <input
                type="number"
                step="0.1"
                value={formData.nozzle_diameter}
                onChange={(e) => setFormData({ ...formData, nozzle_diameter: e.target.value })}
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Макс. темп. сопла (°C)</label>
              <input
                type="number"
                value={formData.max_extruder_temp}
                onChange={(e) => setFormData({ ...formData, max_extruder_temp: e.target.value })}
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Макс. темп. стола (°C)</label>
              <input
                type="number"
                value={formData.max_bed_temp}
                onChange={(e) => setFormData({ ...formData, max_bed_temp: e.target.value })}
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
          </div>

          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">URL изображения</label>
            <input
              type="url"
              value={formData.image_url}
              onChange={(e) => setFormData({ ...formData, image_url: e.target.value })}
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
          </div>

          {printer && (
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="active"
                checked={formData.active}
                onChange={(e) => setFormData({ ...formData, active: e.target.checked })}
                className="w-4 h-4 rounded"
              />
              <label htmlFor="active" className="text-gray-300 text-sm">Активен</label>
            </div>
          )}

          <div className="flex items-center justify-end space-x-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-6 py-3 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all"
            >
              Отмена
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="flex items-center space-x-2 px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-xl transition-all disabled:opacity-50"
            >
              <Save className="w-5 h-5" />
              <span>{printer ? 'Сохранить' : 'Создать'}</span>
            </button>
          </div>
        </form>
        </div>
      </div>
    </div>
  );
}

