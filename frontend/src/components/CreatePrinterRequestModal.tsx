/** Модальное окно для создания запроса на добавление принтера */

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { X, Save } from 'lucide-react';
import { Printer3DIcon } from './icons/Printer3DIcon';
import { printerRequestsAPI } from '../api/printerRequestsAPI';
import { translateApiError } from '../utils/translateApiError';
import { ModalOverlay } from './ModalOverlay';
import type { AxiosError } from 'axios';

interface CreatePrinterRequestModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function CreatePrinterRequestModal({ isOpen, onClose }: CreatePrinterRequestModalProps) {
  const { t } = useTranslation();
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
      alert(t('printerRequest.successMessage'));
    },
    onError: (error: AxiosError<{ detail: unknown }>) => {
      alert(translateApiError(t, error.response?.data?.detail, t('printerRequest.createError')));
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
    <ModalOverlay onClose={onClose}>
      <div
        className="bg-gradient-to-br from-purple-900 to-indigo-900 rounded-2xl shadow-2xl border border-white/20 max-w-2xl w-full max-h-[85vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-white/10">
          <div className="flex items-center space-x-3">
            <Printer3DIcon className="w-6 h-6 text-purple-400" />
            <h3 className="text-2xl font-bold text-white">{t('printerRequest.title')}</h3>
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
            {t('printerRequest.subtitle')}
          </p>

          <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerRequest.printerName')} *</label>
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
                placeholder={t('printerRequest.namePlaceholder')}
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerRequest.manufacturer')} *</label>
                <input
                  type="text"
                  value={formData.manufacturer}
                  onChange={(e) => setFormData({ ...formData, manufacturer: e.target.value })}
                  required
                  placeholder={t('printerRequest.manufacturerPlaceholder')}
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerRequest.model')} *</label>
                <input
                  type="text"
                  value={formData.model}
                  onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                  required
                  placeholder={t('printerRequest.modelPlaceholder')}
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
                placeholder={t('printerRequest.slugPlaceholder')}
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
              <p className="text-xs text-gray-400 mt-1">
                {t('printerRequest.slugHint')}
              </p>
            </div>
          </div>

          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerRequest.description')}</label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              rows={3}
              placeholder={t('printerRequest.descriptionPlaceholder')}
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
            />
          </div>

          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerRequest.volumeX')}</label>
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
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerRequest.volumeY')}</label>
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
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerRequest.volumeZ')}</label>
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
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerRequest.nozzleDiameter')}</label>
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
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerRequest.maxExtruderTemp')}</label>
              <input
                type="number"
                value={formData.max_extruder_temp}
                onChange={(e) => setFormData({ ...formData, max_extruder_temp: e.target.value })}
                placeholder="250"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerRequest.maxBedTemp')}</label>
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
            <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerRequest.imageUrl')}</label>
            <input
              type="url"
              value={formData.image_url}
              onChange={(e) => setFormData({ ...formData, image_url: e.target.value })}
              placeholder="https://example.com/printer.jpg"
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
          </div>

          <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerRequest.additionalInfo')}</label>
            <textarea
              value={formData.message}
              onChange={(e) => setFormData({ ...formData, message: e.target.value })}
              rows={3}
              placeholder={t('printerRequest.additionalInfoPlaceholder')}
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 resize-none"
            />
          </div>

          <div className="flex items-center justify-end space-x-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-6 py-3 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all"
            >
              {t('printerRequest.cancel')}
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="flex items-center space-x-2 px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-xl transition-all disabled:opacity-50"
            >
              <Save className="w-5 h-5" />
              <span>{t('printerRequest.submit')}</span>
            </button>
          </div>
        </form>
        </div>
      </div>
    </ModalOverlay>
  );
}

