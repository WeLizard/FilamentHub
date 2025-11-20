/** Модальное окно для создания запроса на добавление принтера */

import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { X, Printer, Save } from 'lucide-react';
import { printerRequestsAPI } from '../api/printerRequestsAPI';
import { useHeaderVisible } from '../hooks/useHeaderVisible';

interface CreatePrinterRequestModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function CreatePrinterRequestModal({ isOpen, onClose }: CreatePrinterRequestModalProps) {
  const isHeaderVisible = useHeaderVisible();
  const queryClient = useQueryClient();
  const [formData, setFormData] = useState({
    name: '',
    manufacturer: '',
    model: '',
    slug: '',
    description: '',
    build_volume_x: '',
    build_volume_y: '',
    build_volume_z: '',
    nozzle_diameter: '',
    max_extruder_temp: '',
    max_bed_temp: '',
    image_url: '',
    message: '',
  });

  const createMutation = useMutation({
    mutationFn: printerRequestsAPI.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['printer-requests'] });
      onClose();
      setFormData({
        name: '',
        manufacturer: '',
        model: '',
        slug: '',
        description: '',
        build_volume_x: '',
        build_volume_y: '',
        build_volume_z: '',
        nozzle_diameter: '',
        max_extruder_temp: '',
        max_bed_temp: '',
        image_url: '',
        message: '',
      });
      alert('Запрос на добавление принтера успешно создан! Он будет рассмотрен администратором.');
    },
    onError: (error: any) => {
      alert(error.response?.data?.detail || 'Ошибка при создании запроса');
    },
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
      message: formData.message || undefined,
    };
    createMutation.mutate(data);
  };

  if (!isOpen) return null;

  return (
    <div className={`fixed inset-0 z-[100] ${isHeaderVisible ? 'pt-[88px]' : ''}`}>
      {/* Backdrop - покрывает весь экран, включая хэдер */}
      <div 
        className="fixed inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />
      {/* Modal Container */}
      <div className="fixed inset-0 flex items-center justify-center pointer-events-none p-4" style={{ top: isHeaderVisible ? '88px' : '0' }}>
        {/* Modal */}
        <div 
          className={`bg-gradient-to-br from-purple-900 to-indigo-900 rounded-2xl shadow-2xl border border-white/20 max-w-2xl w-full ${isHeaderVisible ? 'max-h-[calc(100vh-120px)]' : 'max-h-[85vh]'} overflow-hidden flex flex-col pointer-events-auto`}
          onClick={(e) => e.stopPropagation()}
          onMouseDown={(e) => e.stopPropagation()}
        >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-white/10">
          <div className="flex items-center space-x-3">
            <Printer className="w-6 h-6 text-purple-400" />
            <h3 className="text-2xl font-bold text-white">Запрос на добавление принтера</h3>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white"
          >
            <X className="w-6 h-6" />
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-6">
          <p className="text-gray-300 mb-6 text-sm">
            Если ваш принтер отсутствует в базе, заполните форму ниже. Запрос будет рассмотрен администратором.
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Название принтера *</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => {
                  const name = e.target.value;
                  setFormData({ 
                    ...formData, 
                    name,
                    // Автогенерация slug из названия
                    slug: name
                      .toLowerCase()
                      .trim()
                      .replace(/[^a-z0-9\s-]/g, '')
                      .replace(/\s+/g, '-')
                      .replace(/-+/g, '-')
                      .replace(/^-|-$/g, ''),
                  });
                }}
                required
                placeholder="Например: Bambu Lab X1 Carbon"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Производитель *</label>
                <input
                  type="text"
                  value={formData.manufacturer}
                  onChange={(e) => setFormData({ ...formData, manufacturer: e.target.value })}
                  required
                  placeholder="Например: Bambu Lab"
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Модель *</label>
                <input
                  type="text"
                  value={formData.model}
                  onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                  required
                  placeholder="Например: X1 Carbon"
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
            </div>

            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Slug *</label>
              <input
                type="text"
                value={formData.slug}
                onChange={(e) => setFormData({ ...formData, slug: e.target.value })}
                required
                placeholder="Автоматически генерируется из названия"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
              <p className="text-xs text-gray-400 mt-1">
                URL-friendly идентификатор принтера (генерируется автоматически из названия)
              </p>
            </div>
          </div>

          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">Описание</label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              rows={3}
              placeholder="Краткое описание принтера..."
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
                placeholder="220"
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
                placeholder="220"
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
                placeholder="250"
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
                placeholder="0.4"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Макс. темп. сопла (°C)</label>
              <input
                type="number"
                value={formData.max_extruder_temp}
                onChange={(e) => setFormData({ ...formData, max_extruder_temp: e.target.value })}
                placeholder="250"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Макс. темп. стола (°C)</label>
              <input
                type="number"
                value={formData.max_bed_temp}
                onChange={(e) => setFormData({ ...formData, max_bed_temp: e.target.value })}
                placeholder="100"
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
              placeholder="https://example.com/printer.jpg"
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
          </div>

          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">Дополнительная информация</label>
            <textarea
              value={formData.message}
              onChange={(e) => setFormData({ ...formData, message: e.target.value })}
              rows={3}
              placeholder="Любая дополнительная информация о принтере..."
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
            />
          </div>

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
              disabled={createMutation.isPending}
              className="flex items-center space-x-2 px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-xl transition-all disabled:opacity-50"
            >
              <Save className="w-5 h-5" />
              <span>Отправить запрос</span>
            </button>
          </div>
        </form>
        </div>
      </div>
      </div>
    </div>
  );
}

