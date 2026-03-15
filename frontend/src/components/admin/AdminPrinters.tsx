/** Компонент для управления принтерами в админке */

import { useEffect, useMemo, useState } from 'react';
import { ModalOverlay } from '../ModalOverlay';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Plus, Edit, Trash2, X, Save } from 'lucide-react';
import { Printer3DIcon } from '../icons/Printer3DIcon';
import { adminAPI, printersAPI } from '../../api/client';
import type { Printer as PrinterType } from '../../types/api';
import { EditGCodeModal } from '../EditGCodeModal';
import { CustomSelect } from '../CustomSelect';

const slugify = (value: string): string =>
  value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 200);

export function AdminPrinters() {
  const { t } = useTranslation();
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
    if (confirm(t('adminPrinters.confirmDelete'))) {
      deleteMutation.mutate(id);
    }
  };

  if (isLoading) {
    return <div className="text-center py-12 text-gray-400">{t('adminPrinters.loading')}</div>;
  }

  // Если есть реальная ошибка (не просто пустой список)
  if (error) {
    const errorMessage = error instanceof Error
      ? error.message
      : t('adminPrinters.unknownError');
    
    // Проверяем, не является ли это просто отсутствием данных
    const isNotFound = errorMessage.includes('404') || errorMessage.includes('not found');
    
    if (!isNotFound) {
      return (
        <div className="text-center py-12">
          <div className="text-red-400 mb-2">{t('adminPrinters.loadError')}</div>
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
          <h2 className="text-2xl font-bold text-white mb-2">{t('adminPrinters.title')}</h2>
          <p className="text-gray-400">{t('adminPrinters.total')}: {data?.total || 0}</p>
        </div>
        <button
          onClick={() => setIsCreateModalOpen(true)}
          className="flex items-center space-x-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-xl transition-all"
        >
          <Plus className="w-5 h-5" />
          <span>{t('adminPrinters.addPrinter')}</span>
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
          placeholder={t('adminPrinters.searchPlaceholder')}
          className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
        />
      </div>

      {/* Список принтеров */}
      {printers.length === 0 ? (
        <div className="text-center py-12 text-gray-400">
          <Printer3DIcon className="w-16 h-16 mx-auto mb-4 opacity-50" />
          <p>{t('adminPrinters.noPrinters')}</p>
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
                    <Printer3DIcon className="w-5 h-5 text-purple-400" />
                    <h3 className="text-lg font-semibold text-white">{printer.name}</h3>
                    <span className="px-2 py-1 rounded bg-purple-500/20 text-purple-300 text-xs font-semibold">
                      {printer.manufacturer} {printer.model}
                    </span>
                    {!printer.active && (
                      <span className="px-2 py-1 rounded bg-red-500/20 text-red-400 text-xs font-semibold">
                        {t('adminPrinters.inactive')}
                      </span>
                    )}
                  </div>
                  <div className="text-sm text-gray-400 space-y-1">
                    <p>Slug: {printer.slug}</p>
                    <p>{t('adminPrinters.source')}: {printer.source}</p>
                    {printer.vendor && <p>{t('adminPrinters.vendor')}: {printer.vendor}</p>}
                    {printer.model_id && <p>Model ID: {printer.model_id}</p>}
                    {printer.family && <p>{t('adminPrinters.family')}: {printer.family}</p>}
                    {printer.technology && <p>{t('adminPrinters.technology')}: {printer.technology}</p>}
                    {printer.description && <p>{printer.description}</p>}
                    {(printer.build_volume_x || printer.build_volume_y || printer.build_volume_z) && (
                      <p>
                        {t('adminPrinters.buildVolume')}: {printer.build_volume_x || '?'} × {printer.build_volume_y || '?'} × {printer.build_volume_z || '?'} {t('adminPrinters.mm')}
                      </p>
                    )}
                    {printer.nozzle_diameter && <p>{t('adminPrinters.nozzle')}: {printer.nozzle_diameter}{t('adminPrinters.mm')}</p>}
                    {printer.nozzle_options?.length ? (
                      <p>{t('adminPrinters.extraNozzles')}: {printer.nozzle_options.join(', ')} {t('adminPrinters.mm')}</p>
                    ) : null}
                    {(printer.max_extruder_temp || printer.max_bed_temp) && (
                      <p>
                        {t('adminPrinters.temps')}: {t('adminPrinters.nozzleUpTo')} {printer.max_extruder_temp || '?'}°C, {t('adminPrinters.bedUpTo')} {printer.max_bed_temp || '?'}°C
                      </p>
                    )}
                    {printer.default_materials?.length ? (
                      <p>{t('adminPrinters.defaultMaterials')}: {printer.default_materials.join(', ')}</p>
                    ) : null}
                  </div>
                </div>
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => setEditingPrinter(printer)}
                    className="p-2 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-all"
                    title={t('adminPrinters.edit')}
                  >
                    <Edit className="w-5 h-5" />
                  </button>
                  <button
                    onClick={() => handleDelete(printer.id)}
                    className="p-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg transition-all"
                    title={t('adminPrinters.delete')}
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
            {t('adminPrinters.prev')}
          </button>
          <span className="text-gray-400">{t('adminPrinters.page')} {page} {t('adminPrinters.of')} {data.pages}</span>
          <button
            onClick={() => setPage(p => Math.min(data.pages, p + 1))}
            disabled={page === data.pages}
            className="px-4 py-2 rounded-lg bg-white/5 text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-white/10"
          >
            {t('adminPrinters.next')}
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

type PrinterTabKey = 'general' | 'motion' | 'extruders' | 'multimaterial' | 'gcode' | 'notes';

const PRINTER_GCODE_FIELDS = [
  { key: 'machine_start_gcode', label: 'Machine start G-code' },
  { key: 'machine_end_gcode', label: 'Machine end G-code' },
  { key: 'machine_resume_gcode', label: 'Machine resume G-code' },
  { key: 'machine_pause_gcode', label: 'Machine pause G-code' },
  { key: 'machine_cancel_gcode', label: 'Machine cancel G-code' },
  { key: 'machine_custom_gcode', label: 'Machine custom G-code' },
  { key: 'printing_by_object_gcode', label: 'Printing by object G-code' },
  { key: 'before_layer_change_gcode', label: 'Before layer change G-code' },
  { key: 'layer_change_gcode', label: 'Layer change G-code' },
  { key: 'time_lapse_gcode', label: 'Time-lapse G-code' },
  { key: 'change_filament_gcode', label: 'Change filament G-code' },
  { key: 'change_extrusion_role_gcode', label: 'Change extrusion role G-code' },
  { key: 'wrapping_detection_gcode', label: 'Wrapping detection G-code' },
  { key: 'toolchange_gcode', label: 'Toolchange G-code' },
  { key: 'template_custom_gcode', label: 'Template custom G-code' },
] as const;

function PrinterModal({ printer, onClose, onSave, isLoading }: PrinterModalProps) {
  const { t } = useTranslation();
  const [formData, setFormData] = useState({
    name: printer?.name || '',
    manufacturer: printer?.manufacturer || '',
    model: printer?.model || '',
    slug: printer?.slug || '',
    model_id: printer?.model_id || '',
    vendor: printer?.vendor || '',
    family: printer?.family || '',
    technology: printer?.technology || '',
    description: printer?.description || '',
    build_volume_x: printer?.build_volume_x ? printer.build_volume_x.toString() : '',
    build_volume_y: printer?.build_volume_y ? printer.build_volume_y.toString() : '',
    build_volume_z: printer?.build_volume_z ? printer.build_volume_z.toString() : '',
    nozzle_diameter: printer?.nozzle_diameter ? printer.nozzle_diameter.toString() : '',
    nozzle_options: printer?.nozzle_options ? printer.nozzle_options.map((value) => value.toString()) : [],
    max_extruder_temp: printer?.max_extruder_temp ? printer.max_extruder_temp.toString() : '',
    max_bed_temp: printer?.max_bed_temp ? printer.max_bed_temp.toString() : '',
    default_materials: printer?.default_materials ? [...printer.default_materials] : [],
    extra_metadata: printer?.extra_metadata ? JSON.stringify(printer.extra_metadata, null, 2) : '',
    image_url: printer?.image_url || '',
    active: printer?.active ?? true,
  });
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [newNozzleOption, setNewNozzleOption] = useState('');
  const [newMaterial, setNewMaterial] = useState('');
  const [activeTab, setActiveTab] = useState<PrinterTabKey>('general');

  // Обновляем форму при изменении printer
  useEffect(() => {
    if (printer) {
      setFormData({
        name: printer.name || '',
        manufacturer: printer.manufacturer || '',
        model: printer.model || '',
        slug: printer.slug || '',
        model_id: printer.model_id || '',
        vendor: printer.vendor || '',
        family: printer.family || '',
        technology: printer.technology || '',
        description: printer.description || '',
        build_volume_x: printer.build_volume_x ? printer.build_volume_x.toString() : '',
        build_volume_y: printer.build_volume_y ? printer.build_volume_y.toString() : '',
        build_volume_z: printer.build_volume_z ? printer.build_volume_z.toString() : '',
        nozzle_diameter: printer.nozzle_diameter ? printer.nozzle_diameter.toString() : '',
        nozzle_options: printer.nozzle_options ? printer.nozzle_options.map((value) => value.toString()) : [],
        max_extruder_temp: printer.max_extruder_temp ? printer.max_extruder_temp.toString() : '',
        max_bed_temp: printer.max_bed_temp ? printer.max_bed_temp.toString() : '',
        default_materials: printer.default_materials ? [...printer.default_materials] : [],
        extra_metadata: printer.extra_metadata ? JSON.stringify(printer.extra_metadata, null, 2) : '',
        image_url: printer.image_url || '',
        active: printer.active ?? true,
      });
    } else {
      // Сброс формы при создании нового принтера
      setFormData({
        name: '',
        manufacturer: '',
        model: '',
        slug: '',
        model_id: '',
        vendor: '',
        family: '',
        technology: '',
        description: '',
        build_volume_x: '',
        build_volume_y: '',
        build_volume_z: '',
        nozzle_diameter: '',
        nozzle_options: [],
        max_extruder_temp: '',
        max_bed_temp: '',
        default_materials: [],
        extra_metadata: '',
        image_url: '',
        active: true,
      });
    }
    setJsonError(null);
    setNewNozzleOption('');
    setNewMaterial('');
    setActiveTab('general');
  }, [printer]);

  const parsedMetadata = useMemo(() => {
    if (!formData.extra_metadata.trim()) {
      return {};
    }
    try {
      return JSON.parse(formData.extra_metadata);
    } catch (error) {
      return null;
    }
  }, [formData.extra_metadata]);

  const metadataInvalid = parsedMetadata === null;

  const getMetadataValue = (key: string): any => {
    if (!parsedMetadata || typeof parsedMetadata !== 'object') {
      return undefined;
    }
    return (parsedMetadata as Record<string, any>)[key];
  };

  const getMetadataString = (key: string): string => {
    const value = getMetadataValue(key);
    if (Array.isArray(value)) {
      return value.join(', ');
    }
    if (value === undefined || value === null) {
      return '';
    }
    return String(value);
  };

  const getMetadataBoolean = (key: string): boolean => {
    const value = getMetadataValue(key);
    if (Array.isArray(value)) {
      return value.some((item) => item === '1' || item === 1 || item === true || String(item).toLowerCase() === 'true');
    }
    if (typeof value === 'string') {
      return value === '1' || value.toLowerCase() === 'true';
    }
    if (typeof value === 'number') {
      return value === 1;
    }
    if (typeof value === 'boolean') {
      return value;
    }
    return false;
  };

  const getMetadataListString = (key: string): string => {
    const value = getMetadataValue(key);
    if (Array.isArray(value)) {
      // Для пустого массива возвращаем пустую строку
      // Это правильно, так как пустой массив [] - это валидное значение для некоторых полей
      return value.join(', ');
    }
    if (value === undefined || value === null) {
      return '';
    }
    return String(value);
  };

  const getMetadataListValues = (key: string): string[] => {
    if (!formData.extra_metadata.trim()) {
      return [];
    }
    try {
      const parsed = JSON.parse(formData.extra_metadata);
      const value = parsed?.[key];
      if (Array.isArray(value)) {
        return value
          .map((item) => (typeof item === 'string' ? item.trim() : String(item)))
          .filter((item) => item.length > 0);
      }
      if (typeof value === 'string' && value.trim().length > 0) {
        return [value.trim()];
      }
    } catch {
      return [];
    }
    return [];
  };

  const handleInsertGcodePlaceholder = (metadataKey: string, textareaId: string, placeholderText: string) => {
    const currentValue = getMetadataString(metadataKey);
    const textarea = document.getElementById(textareaId) as HTMLTextAreaElement | null;
    const selectionStart = textarea ? textarea.selectionStart : currentValue.length;
    const selectionEnd = textarea ? textarea.selectionEnd : currentValue.length;
    const before = currentValue.slice(0, selectionStart);
    const after = currentValue.slice(selectionEnd);
    const newValue = `${before}${placeholderText}${after}`;
    handleMetadataStringChange(metadataKey, newValue);
    if (textarea) {
      setTimeout(() => {
        const cursorPos = selectionStart + placeholderText.length;
        textarea.setSelectionRange(cursorPos, cursorPos);
        textarea.focus();
      }, 0);
    }
  };

  // Специальные поля, для которых пустой массив [] - это валидное значение
  // (явно заданное в профиле, а не отсутствие значения)
  // Эти поля могут быть пустыми массивами для single-extruder принтеров или когда значение не задано
  const ARRAY_FIELDS_WITH_EMPTY_VALID = [
    'printer_extruder_id',
    'printer_extruder_variant',
    'physical_extruder_map',
    'extruder_variant_list',
    'nozzle_type',
    'z_hop_types',
    'retract_length_toolchange',
    'enable_long_retraction_when_cut',
  ];

  const updateMetadataValue = (key: string, value: any) => {
    let base: Record<string, any> = {};
    try {
      base = formData.extra_metadata.trim() ? JSON.parse(formData.extra_metadata) : {};
    } catch (error) {
      base = {};
    }
    
    // Для специальных полей пустой массив [] - это валидное значение, сохраняем его
    const isSpecialArrayField = ARRAY_FIELDS_WITH_EMPTY_VALID.includes(key);
    
    if (
      value === undefined ||
      value === null ||
      (typeof value === 'string' && value.trim() === '') ||
      (Array.isArray(value) && value.length === 0 && !isSpecialArrayField)
    ) {
      // Удаляем поле только если это не специальное поле с пустым массивом
      delete base[key];
    } else {
      // Сохраняем значение (включая пустые массивы для специальных полей)
      base[key] = value;
    }
    setJsonError(null);
    setFormData((prev) => ({
      ...prev,
      extra_metadata: Object.keys(base).length ? JSON.stringify(base, null, 2) : '',
    }));
  };

  const handleMetadataListChange = (key: string, rawValue: string) => {
    const normalized = rawValue
      .split(',')
      .map((item) => item.trim())
      .filter((item) => item.length > 0);
    
    // Для специальных полей пустой массив [] - это валидное значение
    const isSpecialArrayField = ARRAY_FIELDS_WITH_EMPTY_VALID.includes(key);
    
    if (normalized.length > 0) {
      // Если есть значения, сохраняем массив
      updateMetadataValue(key, normalized);
    } else if (isSpecialArrayField) {
      // Для специальных полей сохраняем пустой массив []
      updateMetadataValue(key, []);
    } else {
      // Для остальных полей удаляем поле (undefined)
      updateMetadataValue(key, undefined);
    }
  };

  const handleMetadataStringChange = (key: string, rawValue: string) => {
    updateMetadataValue(key, rawValue);
  };

  const handleMetadataSelectFromOptions = (key: string, selected: string | null) => {
    if (!selected) {
      updateMetadataValue(key, undefined);
      return;
    }
    updateMetadataValue(key, [selected]);
  };

  const handleMetadataBooleanChange = (key: string, checked: boolean) => {
    updateMetadataValue(key, checked ? '1' : '0');
  };

  const tabConfig: { key: PrinterTabKey; label: string; description: string }[] = [
    { key: 'general', label: t('adminPrinters.tabs.general'), description: t('adminPrinters.tabs.generalDesc') },
    { key: 'motion', label: t('adminPrinters.tabs.motion'), description: t('adminPrinters.tabs.motionDesc') },
    { key: 'extruders', label: t('adminPrinters.tabs.extruders'), description: t('adminPrinters.tabs.extrudersDesc') },
    { key: 'multimaterial', label: t('adminPrinters.tabs.multimaterial'), description: t('adminPrinters.tabs.multimaterialDesc') },
    { key: 'gcode', label: t('adminPrinters.tabs.gcode'), description: t('adminPrinters.tabs.gcodeDesc') },
    { key: 'notes', label: t('adminPrinters.tabs.notes'), description: t('adminPrinters.tabs.notesDesc') },
  ];

  const handleAddNozzle = () => {
    const trimmed = newNozzleOption.trim();
    if (!trimmed) return;
    if (formData.nozzle_options.includes(trimmed)) {
      setNewNozzleOption('');
      return;
    }
    setFormData((prev) => ({
      ...prev,
      nozzle_options: [...prev.nozzle_options, trimmed],
    }));
    setNewNozzleOption('');
  };

  const handleAddMaterial = () => {
    const trimmed = newMaterial.trim();
    if (!trimmed) return;
    if (formData.default_materials.includes(trimmed)) {
      setNewMaterial('');
      return;
    }
    setFormData((prev) => ({
      ...prev,
      default_materials: [...prev.default_materials, trimmed],
    }));
    setNewMaterial('');
  };

  const handleFormatJson = () => {
    if (!formData.extra_metadata.trim()) return;
    try {
      const formatted = JSON.stringify(JSON.parse(formData.extra_metadata), null, 2);
      setFormData((prev) => ({ ...prev, extra_metadata: formatted }));
      setJsonError(null);
    } catch (error) {
      setJsonError(t('adminPrinters.jsonFormatError'));
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    let extraMetadata: Record<string, any> | undefined;
    if (formData.extra_metadata.trim()) {
      try {
        extraMetadata = JSON.parse(formData.extra_metadata);
        setJsonError(null);
      } catch (error) {
        console.error('Invalid extra metadata JSON', error);
        setJsonError(t('adminPrinters.jsonInvalid'));
        return;
      }
    } else {
      setJsonError(null);
    }

    const data = {
      name: formData.name,
      manufacturer: formData.manufacturer,
      model: formData.model,
      slug: formData.slug,
      model_id: formData.model_id || undefined,
      // vendor автоматически заполняется из manufacturer (они дублируют друг друга)
      vendor: formData.vendor || formData.manufacturer || undefined,
      family: formData.family || undefined,
      technology: formData.technology || undefined,
      description: formData.description || undefined,
      build_volume_x: formData.build_volume_x ? parseFloat(formData.build_volume_x) : undefined,
      build_volume_y: formData.build_volume_y ? parseFloat(formData.build_volume_y) : undefined,
      build_volume_z: formData.build_volume_z ? parseFloat(formData.build_volume_z) : undefined,
      nozzle_diameter: formData.nozzle_diameter ? parseFloat(formData.nozzle_diameter) : undefined,
      nozzle_options: formData.nozzle_options.map((value) => parseFloat(value)).filter((value) => !Number.isNaN(value)),
      max_extruder_temp: formData.max_extruder_temp ? parseInt(formData.max_extruder_temp, 10) : undefined,
      max_bed_temp: formData.max_bed_temp ? parseInt(formData.max_bed_temp, 10) : undefined,
      default_materials: formData.default_materials.length ? formData.default_materials : undefined,
      extra_metadata: extraMetadata,
      image_url: formData.image_url || undefined,
      ...(printer ? { active: formData.active } : {}),
    };

    onSave(data);
  };

  const renderGeneralTab = () => {
    const firmwareFlagOptions: Array<{ key: string; label: string; description?: string }> = [
      { key: 'use_relative_e_distances', label: t('adminPrinters.flags.relativeE'), description: t('adminPrinters.flags.relativeEDesc') },
      { key: 'use_firmware_retraction', label: t('adminPrinters.flags.firmwareRetraction'), description: t('adminPrinters.flags.firmwareRetractionDesc') },
      { key: 'pellet_modded_printer', label: t('adminPrinters.flags.pelletMod'), description: t('adminPrinters.flags.pelletModDesc') },
      { key: 'support_multi_bed_types', label: t('adminPrinters.flags.multiBedTypes'), description: t('adminPrinters.flags.multiBedTypesDesc') },
      { key: 'support_air_filtration', label: t('adminPrinters.flags.airFiltration') },
      { key: 'support_chamber_temp_control', label: t('adminPrinters.flags.chamberTemp') },
      { key: 'auxiliary_fan', label: t('adminPrinters.flags.auxFan') },
      { key: 'scan_first_layer', label: t('adminPrinters.flags.scanFirstLayer') },
      { key: 'disable_m73', label: t('adminPrinters.flags.disableM73') },
      { key: 'bbl_use_printhost', label: t('adminPrinters.flags.usePrintHost') },
    ];
    const printerStructureOptions = ['corexy', 'cartesian', 'i3', 'delta', 'belt', 'polar', 'scara', 'undefine'];
    const gcodeFlavorOptions = ['marlin', 'marlin2', 'klipper', 'reprapfirmware'];
    const printerTechnologyOptions = ['FFF', 'FDM', 'CoreXY enclosed'];
    const defaultBedTypeOptions = [
      'Textured PEI Plate',
      'Smooth PEI Plate',
      'Engineering Plate',
      'High Temp Plate',
      'Cool Plate',
      'Auto',
    ];
    const coolingFanFields: Array<{ key: string; label: string; placeholder?: string; unit?: string }> = [
      { key: 'fan_speedup_time', label: t('adminPrinters.cooling.fanSpeedupTime'), placeholder: '2', unit: t('adminPrinters.units.sec') },
      { key: 'fan_speedup_overhangs', label: t('adminPrinters.cooling.fanSpeedupOverhangs'), placeholder: '30', unit: '%' },
      { key: 'fan_kickstart', label: t('adminPrinters.cooling.kickstart'), placeholder: '100', unit: '%' },
    ];
    const extruderClearanceFields: Array<{ key: string; label: string; placeholder?: string; unit?: string }> = [
      { key: 'extruder_clearance_radius', label: t('adminPrinters.clearance.radius'), placeholder: '65', unit: t('adminPrinters.mm') },
      { key: 'extruder_clearance_height_to_rod', label: t('adminPrinters.clearance.heightToRod'), placeholder: '36', unit: t('adminPrinters.mm') },
      { key: 'extruder_clearance_height_to_lid', label: t('adminPrinters.clearance.heightToLid'), placeholder: '140', unit: t('adminPrinters.mm') },
    ];
    const adaptiveMeshFields: Array<{ key: string; label: string; placeholder?: string }> = [
      { key: 'bed_mesh_min', label: t('adminPrinters.mesh.bedMeshMin'), placeholder: '0x0, 256x0...' },
      { key: 'bed_mesh_max', label: t('adminPrinters.mesh.bedMeshMax'), placeholder: '256x256...' },
      { key: 'bed_mesh_probe_distance', label: t('adminPrinters.mesh.probeDistance'), placeholder: '30' },
      { key: 'adaptive_bed_mesh_margin', label: t('adminPrinters.mesh.margin'), placeholder: '5' },
    ];
    const bedGeometryFields: Array<{ key: string; label: string; isList?: boolean; placeholder?: string }> = [
      { key: 'bed_shape', label: t('adminPrinters.bed.shape'), isList: true, placeholder: '0x0, 256x0, 256x256, 0x256' },
      { key: 'bed_exclude_area', label: t('adminPrinters.bed.excludeArea'), isList: true, placeholder: '90x90, 166x166' },
      { key: 'bed_custom_rectangle', label: t('adminPrinters.bed.customRectangle'), isList: true, placeholder: '0x0, 256x0, 256x256, 0x256' },
      { key: 'origin_z', label: t('adminPrinters.bed.originZ'), placeholder: '0' },
    ];
    const thumbnailsFields: Array<{ key: string; label: string; placeholder?: string }> = [
      { key: 'thumbnails', label: t('adminPrinters.thumbnailsLabel'), placeholder: '32x32,64x64' },
      { key: 'thumbnails_format', label: t('adminPrinters.thumbnailsFormat'), placeholder: 'png,gcode,ufp...' },
    ];

  return (
      <div className="space-y-8">
        <section className="space-y-4 bg-white/5 border border-white/10 rounded-2xl p-6 shadow-inner shadow-indigo-900/30">
          <div>
            <h4 className="text-sm font-semibold text-white uppercase tracking-wide">{t('adminPrinters.sections.general')}</h4>
            <p className="text-xs text-gray-400 mt-1">
              {t('adminPrinters.sections.generalDesc')}
            </p>
        </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.fields.name')} *</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                required
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.fields.manufacturer')} *</label>
              <input
                type="text"
                value={formData.manufacturer}
                onChange={(e) => {
                  const manufacturer = e.target.value;
                  setFormData({ 
                    ...formData, 
                    manufacturer,
                    // Автоматически заполняем vendor тем же значением (они дублируют друг друга)
                    vendor: manufacturer || formData.vendor,
                  });
                }}
                required
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.fields.model')} *</label>
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
            <div className="flex gap-2">
              <input
                type="text"
                value={formData.slug}
                onChange={(e) => setFormData({ ...formData, slug: e.target.value })}
                required
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
              <button
                type="button"
                onClick={() =>
                  setFormData((prev) => ({
                    ...prev,
                    slug: slugify(`${prev.manufacturer} ${prev.model}`),
                  }))
                }
                className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-xl text-xs font-medium transition-all"
              >
                {t('adminPrinters.generate')}
              </button>
            </div>
          </div>
        </div>
      </section>

      {/* Технические поля (скрыты для пользователя, заполняются автоматически при импорте) */}
      {/* vendor и model_id автоматически заполняются из manufacturer при создании */}
      {/* family и technology - опциональные поля для системных принтеров */}
      {(formData.family || formData.technology || formData.model_id || (printer && printer.source === 'system')) && (
        <section className="space-y-4 bg-white/5 border border-white/10 rounded-2xl p-6 shadow-inner shadow-indigo-900/30">
          <div>
            <h4 className="text-sm font-semibold text-white uppercase tracking-wide">{t('adminPrinters.sections.additional')}</h4>
            <p className="text-xs text-gray-400 mt-1">
              {t('adminPrinters.sections.additionalDesc')}
            </p>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {(formData.model_id || (printer && printer.source === 'system')) && (
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Model ID</label>
                <input
                  type="text"
                  value={formData.model_id}
                  onChange={(e) => setFormData({ ...formData, model_id: e.target.value })}
                  placeholder={t('adminPrinters.placeholders.autoFilled')}
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
            )}
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.fields.family')}</label>
              <input
                type="text"
                value={formData.family}
                onChange={(e) => setFormData({ ...formData, family: e.target.value })}
                placeholder={t('adminPrinters.placeholders.familyOptional')}
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.fields.technology')}</label>
              <input
                type="text"
                value={formData.technology}
                onChange={(e) => setFormData({ ...formData, technology: e.target.value })}
                placeholder={t('adminPrinters.placeholders.technologyOptional')}
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
          </div>
        </section>
      )}

      <section className="space-y-4 bg-white/5 border border-white/10 rounded-2xl p-6 shadow-inner shadow-indigo-900/30">
            <div>
          <h4 className="text-sm font-semibold text-white uppercase tracking-wide">{t('adminPrinters.sections.buildArea')}</h4>
          <p className="text-xs text-gray-400 mt-1">
            {t('adminPrinters.sections.buildAreaDesc')}
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.fields.widthX')}</label>
              <input
                type="number"
                step="0.1"
                value={formData.build_volume_x}
                onChange={(e) => setFormData({ ...formData, build_volume_x: e.target.value })}
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.fields.depthY')}</label>
              <input
                type="number"
                step="0.1"
                value={formData.build_volume_y}
                onChange={(e) => setFormData({ ...formData, build_volume_y: e.target.value })}
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
            <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.fields.heightZ')}</label>
              <input
                type="number"
                step="0.1"
                value={formData.build_volume_z}
                onChange={(e) => setFormData({ ...formData, build_volume_z: e.target.value })}
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
          </div>
      </section>

      <section className="space-y-4 bg-white/5 border border-white/10 rounded-2xl p-6 shadow-inner shadow-indigo-900/30">
            <div>
          <h4 className="text-sm font-semibold text-white uppercase tracking-wide">{t('adminPrinters.sections.materialsMedia')}</h4>
          <p className="text-xs text-gray-400 mt-1">
            {t('adminPrinters.sections.materialsMediaDesc')}
          </p>
        </div>
        <div>
          <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.fields.defaultMaterials')}</label>
          <div className="flex flex-wrap gap-2 mb-2">
            {formData.default_materials.map((material) => (
              <span
                key={material}
                className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-indigo-500/20 text-indigo-100 text-xs"
              >
                {material}
                <button
                  type="button"
                  onClick={() =>
                    setFormData((prev) => ({
                      ...prev,
                      default_materials: prev.default_materials.filter((value) => value !== material),
                    }))
                  }
                  className="hover:text-white transition"
                  aria-label={t('adminPrinters.removeMaterial')}
                >
                  ×
                </button>
              </span>
            ))}
            {formData.default_materials.length === 0 && (
              <span className="text-xs text-gray-500">{t('adminPrinters.noMaterials')}</span>
            )}
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={newMaterial}
              onChange={(e) => setNewMaterial(e.target.value)}
              placeholder="PLA"
              className="flex-1 px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
            <button
              type="button"
              onClick={handleAddMaterial}
              className="px-4 py-3 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all"
            >
              {t('adminPrinters.add')}
            </button>
          </div>
          <p className="text-gray-500 text-xs mt-1">
            {t('adminPrinters.materialsHint')}
          </p>
        </div>

        <div>
          <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.fields.imageUrl')}</label>
          <input
            type="url"
            value={formData.image_url}
            onChange={(e) => setFormData({ ...formData, image_url: e.target.value })}
            className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
          />
        </div>

        <div>
          <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.fields.extraMetadata')}</label>
          <div className="flex flex-col md:flex-row md:items-start gap-2 mb-2">
            <textarea
              value={formData.extra_metadata}
              onChange={(e) => {
                setFormData({ ...formData, extra_metadata: e.target.value });
                if (jsonError) {
                  setJsonError(null);
                }
              }}
              rows={8}
              className="flex-1 px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 font-mono text-sm"
              placeholder='{"profile": "Bambu PLA", "bed_type": "Smooth Plate"}'
            />
            <button
              type="button"
              onClick={handleFormatJson}
              className="px-4 py-3 bg-white/10 hover:bg-white/20 text-white rounded-xl text-xs font-medium transition-all"
            >
              {t('adminPrinters.format')}
            </button>
          </div>
          {jsonError && <p className="text-red-400 text-xs mt-1">{jsonError}</p>}
          <p className="text-gray-500 text-xs mt-1">
            {t('adminPrinters.metadataHint')}
          </p>
        </div>

        {printer && (
          <div className="flex items-center space-x-2 pt-2">
            <input
              type="checkbox"
              id="active"
              checked={formData.active}
              onChange={(e) => setFormData({ ...formData, active: e.target.checked })}
              className="w-4 h-4 rounded border-white/30 bg-white/10"
            />
            <label htmlFor="active" className="text-gray-300 text-sm">{t('adminPrinters.active')}</label>
          </div>
        )}
      </section>

      <section className="space-y-4 bg-white/5 border border-white/10 rounded-2xl p-6 shadow-inner shadow-indigo-900/30">
        <div>
          <h4 className="text-sm font-semibold text-white uppercase tracking-wide">{t('adminPrinters.sections.orcaConfig')}</h4>
          <p className="text-xs text-gray-400 mt-1">
            {t('adminPrinters.sections.orcaConfigDesc')}
          </p>
        </div>
        {metadataInvalid ? (
          <div className="rounded-2xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            {t('adminPrinters.jsonParseError')}
          </div>
        ) : (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.orca.printerStructure')}</label>
                <CustomSelect
                  value={getMetadataString('printer_structure') || null}
                  onChange={(value) => handleMetadataStringChange('printer_structure', (value as string) || '')}
                  options={printerStructureOptions.map((option) => ({ value: option, label: option }))}
                  placeholder={t('adminPrinters.placeholders.selectStructure')}
                  className="h-[52px]"
                />
                <p className="text-xs text-gray-500 mt-1">{t('adminPrinters.orca.printerStructureHint')}</p>
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.orca.gcodeFlavor')}</label>
                <CustomSelect
                  value={getMetadataString('gcode_flavor') || null}
                  onChange={(value) => handleMetadataStringChange('gcode_flavor', (value as string) || '')}
                  options={gcodeFlavorOptions.map((option) => ({ value: option, label: option }))}
                  placeholder={t('adminPrinters.placeholders.selectFlavor')}
                  className="h-[52px]"
                />
                <p className="text-xs text-gray-500 mt-1">{t('adminPrinters.orca.gcodeFlavorHint')}</p>
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.orca.printTechnology')}</label>
                <CustomSelect
                  value={getMetadataString('printer_technology') || null}
                  onChange={(value) => handleMetadataStringChange('printer_technology', (value as string) || '')}
                  options={printerTechnologyOptions.map((option) => ({ value: option, label: option }))}
                  placeholder={t('adminPrinters.placeholders.selectTechnology')}
                  className="h-[52px]"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.orca.defaultBedType')}</label>
                <CustomSelect
                  value={getMetadataString('default_bed_type') || null}
                  onChange={(value) => handleMetadataStringChange('default_bed_type', (value as string) || '')}
                  options={defaultBedTypeOptions.map((option) => ({ value: option, label: option }))}
                  placeholder={t('adminPrinters.placeholders.selectBedPlate')}
                  className="h-[52px]"
                />
              </div>
              {/* Скрываем модель и текстуру стола до появления справочников */}
              {/*
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Модель стола</label>
                <input
                  type="text"
                  value={getMetadataString('bed_model')}
                  onChange={(e) => handleMetadataStringChange('bed_model', e.target.value)}
                  placeholder="bbl-3dp-X1.stl"
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Текстура стола</label>
                <input
                  type="text"
                  value={getMetadataString('bed_texture')}
                  onChange={(e) => handleMetadataStringChange('bed_texture', e.target.value)}
                  placeholder="bbl-3dp-logo.svg"
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              */}
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.orca.hotend')}</label>
                <input
                  type="text"
                  value={getMetadataString('hotend_model')}
                  onChange={(e) => handleMetadataStringChange('hotend_model', e.target.value)}
                  placeholder="Phaetus Rapido..."
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
                <p className="text-xs text-gray-500 mt-1">{t('adminPrinters.orca.hotendHint')}</p>
              </div>
              {/* Формула температуры стола и ID настроек скрыты до уточнения назначения */}
              {/*
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Формула температуры стола</label>
                <input
                  type="text"
                  value={getMetadataString('bed_temperature_formula')}
                  onChange={(e) => handleMetadataStringChange('bed_temperature_formula', e.target.value)}
                  placeholder="by_first_filament"
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">ID настроек принтера</label>
                <input
                  type="text"
                  value={getMetadataString('printer_settings_id')}
                  onChange={(e) => handleMetadataStringChange('printer_settings_id', e.target.value)}
                  placeholder="например, GM001"
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              */}
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.orca.timeCost')}</label>
                <input
                  type="text"
                  value={getMetadataString('time_cost')}
                  onChange={(e) => handleMetadataStringChange('time_cost', e.target.value)}
                  placeholder="0.0"
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.orca.defaultFilamentProfile')}</label>
                <input
                  type="text"
                  value={getMetadataListString('default_filament_profile')}
                  onChange={(e) => handleMetadataListChange('default_filament_profile', e.target.value)}
                  placeholder="Generic PLA"
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
                <p className="text-xs text-gray-500 mt-1">{t('adminPrinters.orca.defaultFilamentProfileHint')}</p>
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.orca.printerVariant')}</label>
                <input
                  type="text"
                  value={getMetadataListString('printer_variant')}
                  onChange={(e) => handleMetadataListChange('printer_variant', e.target.value)}
                  placeholder="0.4"
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
                <p className="text-xs text-gray-500 mt-1">{t('adminPrinters.orca.printerVariantHint')}</p>
              </div>
            </div>

            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('adminPrinters.orca.bedAndLimits')}</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {bedGeometryFields.map((field) => (
                  <div key={field.key}>
                    <label className="block text-gray-300 mb-2 text-sm font-medium">{field.label}</label>
                    <input
                      type="text"
                      value={
                        field.isList
                          ? getMetadataListString(field.key)
                          : getMetadataString(field.key)
                      }
                      onChange={(e) =>
                        field.isList
                          ? handleMetadataListChange(field.key, e.target.value)
                          : handleMetadataStringChange(field.key, e.target.value)
                      }
                      placeholder={field.placeholder}
                      className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    />
                  </div>
                ))}
              </div>
              <p className="text-xs text-gray-500 mt-2">
                {t('adminPrinters.orca.coordinatesHint')}
              </p>
            </div>

            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('adminPrinters.orca.flagsAndModes')}</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {firmwareFlagOptions.map((option) => (
                  <div key={option.key} className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      id={`flag-${option.key}`}
                      checked={getMetadataBoolean(option.key)}
                      onChange={(e) => handleMetadataBooleanChange(option.key, e.target.checked)}
                      className="w-4 h-4 mt-1 rounded border-white/30 bg-white/10"
                    />
                    <div>
                      <label htmlFor={`flag-${option.key}`} className="text-gray-300 text-sm font-medium">
                        {option.label}
                      </label>
                      {option.description && <p className="text-xs text-gray-500">{option.description}</p>}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('adminPrinters.cooling.title')}</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {coolingFanFields.map((field) => (
                  <div key={field.key} className="space-y-2">
                    <label className="block min-h-[38px] text-gray-300 text-sm font-medium leading-tight flex items-end">{field.label}</label>
                    <div className="relative">
                      <input
                        type="text"
                        value={getMetadataString(field.key)}
                        onChange={(e) => handleMetadataStringChange(field.key, e.target.value)}
                        placeholder={field.placeholder}
                        className={`w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 ${field.unit ? 'pr-16' : ''}`}
                      />
                      {field.unit && (
                        <span className="absolute inset-y-0 right-4 flex items-center text-xs text-gray-400 pointer-events-none">
                          {field.unit}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('adminPrinters.orca.extruderClearance')}</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {extruderClearanceFields.map((field) => (
                  <div key={field.key} className="space-y-2">
                    <label className="block min-h-[38px] text-gray-300 text-sm font-medium leading-tight flex items-end">{field.label}</label>
                    <div className="relative">
                      <input
                        type="text"
                        value={getMetadataString(field.key)}
                        onChange={(e) => handleMetadataStringChange(field.key, e.target.value)}
                        placeholder={field.placeholder}
                        className={`w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 ${field.unit ? 'pr-16' : ''}`}
                      />
                      {field.unit && (
                        <span className="absolute inset-y-0 right-4 flex items-center text-xs text-gray-400 pointer-events-none">
                          {field.unit}
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('adminPrinters.mesh.title')}</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {adaptiveMeshFields.map((field) => (
                  <div key={field.key}>
                    <label className="block text-gray-300 mb-2 text-sm font-medium">{field.label}</label>
                    <input
                      type="text"
                      value={getMetadataListString(field.key)}
                      onChange={(e) => handleMetadataListChange(field.key, e.target.value)}
                      placeholder={field.placeholder}
                      className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    />
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('adminPrinters.thumbnailsTitle')}</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {thumbnailsFields.map((field) => (
                  <div key={field.key}>
                    <label className="block text-gray-300 mb-2 text-sm font-medium">{field.label}</label>
                    <input
                      type="text"
                      value={getMetadataString(field.key)}
                      onChange={(e) => handleMetadataStringChange(field.key, e.target.value)}
                      placeholder={field.placeholder}
                      className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
                    />
                  </div>
                ))}
              </div>
              <p className="text-xs text-gray-500 mt-2">
                {t('adminPrinters.orca.thumbnailsHint')}
              </p>
            </div>
          </div>
        )}
      </section>
    </div>
  );
  };

  const renderExtrudersTab = () => {
    const extruderTypeOptions = ['Direct Drive', 'Bowden'];
    const nozzleTypeOptions = ['brass', 'hardened_steel', 'stainless_steel', 'undefine'];
    const selectedNozzleType = getMetadataListValues('nozzle_type')[0] ?? '';

    return (
      <div className="space-y-8">
      <section className="space-y-4 bg-white/5 border border-white/10 rounded-2xl p-6 shadow-inner shadow-indigo-900/30">
        <div>
          <h4 className="text-sm font-semibold text-white uppercase tracking-wide">{t('adminPrinters.extruder.title')}</h4>
          <p className="text-xs text-gray-400 mt-1">
            {t('adminPrinters.extruder.desc')}
          </p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.extruder.nozzleDiameter')}</label>
              <div className="relative">
              <input
                type="number"
                step="0.1"
                value={formData.nozzle_diameter}
                onChange={(e) => setFormData({ ...formData, nozzle_diameter: e.target.value })}
                  placeholder="0.4"
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 pr-16"
              />
                <span className="absolute inset-y-0 right-4 flex items-center text-xs text-gray-400 pointer-events-none">{t('adminPrinters.mm')}</span>
              </div>
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.extruder.maxNozzleTemp')}</label>
              <div className="relative">
              <input
                type="number"
                value={formData.max_extruder_temp}
                onChange={(e) => setFormData({ ...formData, max_extruder_temp: e.target.value })}
                  placeholder="300"
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 pr-16"
              />
                <span className="absolute inset-y-0 right-4 flex items-center text-xs text-gray-400 pointer-events-none">°C</span>
              </div>
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.extruder.maxBedTemp')}</label>
              <div className="relative">
              <input
                type="number"
                value={formData.max_bed_temp}
                onChange={(e) => setFormData({ ...formData, max_bed_temp: e.target.value })}
                  placeholder="120"
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 pr-16"
                />
                <span className="absolute inset-y-0 right-4 flex items-center text-xs text-gray-400 pointer-events-none">°C</span>
              </div>
            </div>
          </div>

          <div>
          <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.extruder.extraNozzles')}</label>
          <div className="flex flex-wrap gap-2 mb-2">
            {formData.nozzle_options.map((option) => (
              <span
                key={option}
                className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-purple-500/20 text-purple-200 text-xs"
              >
                {option} {t('adminPrinters.units.mm')}
                <button
                  type="button"
                  onClick={() =>
                    setFormData((prev) => ({
                      ...prev,
                      nozzle_options: prev.nozzle_options.filter((value) => value !== option),
                    }))
                  }
                  className="hover:text-white transition"
                  aria-label={t('adminPrinters.removeNozzle')}
                >
                  ×
                </button>
              </span>
            ))}
            {formData.nozzle_options.length === 0 && (
              <span className="text-xs text-gray-500">{t('adminPrinters.extruder.noExtraNozzles')}</span>
            )}
          </div>
          <div className="flex gap-2">
            <input
              type="number"
              step="0.1"
              value={newNozzleOption}
              onChange={(e) => setNewNozzleOption(e.target.value)}
              placeholder="0.2"
              className="flex-1 px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
            <button
              type="button"
              onClick={handleAddNozzle}
              className="px-4 py-3 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all"
            >
              {t('adminPrinters.add')}
            </button>
          </div>
          <p className="text-gray-500 text-xs mt-1">
            {t('adminPrinters.extruder.extraNozzlesHint')}
          </p>
        </div>
        {metadataInvalid ? (
          <div className="rounded-2xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            {t('adminPrinters.extruder.jsonError')}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.extruder.type')}</label>
              <CustomSelect
                value={getMetadataString('extruder_type') || null}
                onChange={(value) => handleMetadataStringChange('extruder_type', (value as string) || '')}
                options={extruderTypeOptions.map((option) => ({ value: option, label: option }))}
                placeholder={t('adminPrinters.placeholders.selectType')}
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.extruder.variants')}</label>
              <input
                type="text"
                value={getMetadataListString('extruder_variant_list')}
                onChange={(e) => handleMetadataListChange('extruder_variant_list', e.target.value)}
                placeholder="Direct Drive Standard"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.extruder.nozzleType')}</label>
              <CustomSelect
                value={selectedNozzleType || null}
                onChange={(value) => handleMetadataSelectFromOptions('nozzle_type', (value as string) || null)}
                options={nozzleTypeOptions.map((option) => ({ value: option, label: option }))}
                placeholder={t('adminPrinters.placeholders.selectType')}
              />
          </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.extruder.nozzleVolume')}</label>
              <div className="relative">
                <input
                  type="text"
                  value={getMetadataListString('nozzle_volume')}
                  onChange={(e) => handleMetadataListChange('nozzle_volume', e.target.value)}
                  placeholder="107"
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 pr-16"
                />
                <span className="absolute inset-y-0 right-4 flex items-center text-xs text-gray-400 pointer-events-none">{t('adminPrinters.units.mm3')}</span>
              </div>
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.extruder.clearanceToLid')}</label>
              <div className="relative">
                <input
                  type="text"
                  value={getMetadataString('extruder_clearance_height_to_lid')}
                  onChange={(e) => handleMetadataStringChange('extruder_clearance_height_to_lid', e.target.value)}
                  placeholder="90"
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 pr-16"
                />
                <span className="absolute inset-y-0 right-4 flex items-center text-xs text-gray-400 pointer-events-none">{t('adminPrinters.units.mm')}</span>
              </div>
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.extruder.maxClearanceRadius')}</label>
              <div className="relative">
                <input
                  type="text"
                  value={getMetadataString('extruder_clearance_max_radius')}
                  onChange={(e) => handleMetadataStringChange('extruder_clearance_max_radius', e.target.value)}
                  placeholder="68"
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 pr-16"
                />
                <span className="absolute inset-y-0 right-4 flex items-center text-xs text-gray-400 pointer-events-none">{t('adminPrinters.units.mm')}</span>
              </div>
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.extruder.printerId')}</label>
              <input
                type="text"
                value={getMetadataListString('printer_extruder_id')}
                onChange={(e) => handleMetadataListChange('printer_extruder_id', e.target.value)}
                placeholder="0"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
              <p className="text-xs text-gray-500 mt-1">{t('adminPrinters.extruder.printerIdHint')}</p>
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.extruder.printerVariant')}</label>
              <input
                type="text"
                value={getMetadataListString('printer_extruder_variant')}
                onChange={(e) => handleMetadataListChange('printer_extruder_variant', e.target.value)}
                placeholder="0"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
              <p className="text-xs text-gray-500 mt-1">{t('adminPrinters.extruder.printerVariantHint')}</p>
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.extruder.physicalMap')}</label>
              <input
                type="text"
                value={getMetadataListString('physical_extruder_map')}
                onChange={(e) => handleMetadataListChange('physical_extruder_map', e.target.value)}
                placeholder="0, 1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
              <p className="text-xs text-gray-500 mt-1">{t('adminPrinters.extruder.physicalMapHint')}</p>
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.extruder.maxLayerHeight')}</label>
              <input
                type="text"
                value={getMetadataString('max_layer_height')}
                onChange={(e) => handleMetadataStringChange('max_layer_height', e.target.value)}
                placeholder="0.3"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.extruder.minLayerHeight')}</label>
              <input
                type="text"
                value={getMetadataString('min_layer_height')}
                onChange={(e) => handleMetadataStringChange('min_layer_height', e.target.value)}
                placeholder="0.1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
          </div>
        )}
      </section>

      <section className="space-y-4 bg-white/5 border border-white/10 rounded-2xl p-6 shadow-inner shadow-indigo-900/30">
        <h4 className="text-sm font-semibold text-white uppercase tracking-wide">{t('adminPrinters.retraction.title')}</h4>
        {metadataInvalid ? (
          <p className="text-xs text-red-200">
            {t('adminPrinters.retraction.jsonError')}
          </p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.retraction.length')}</label>
            <input
                type="text"
                value={getMetadataListString('retraction_length')}
                onChange={(e) => handleMetadataListChange('retraction_length', e.target.value)}
                placeholder="0.8"
              className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
            />
          </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.retraction.speed')}</label>
              <input
                type="text"
                value={getMetadataListString('retraction_speed')}
                onChange={(e) => handleMetadataListChange('retraction_speed', e.target.value)}
                placeholder="30"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.retraction.deretractionSpeed')}</label>
              <input
                type="text"
                value={getMetadataListString('deretraction_speed')}
                onChange={(e) => handleMetadataListChange('deretraction_speed', e.target.value)}
                placeholder="30"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.retraction.minTravel')}</label>
              <input
                type="text"
                value={getMetadataListString('retraction_minimum_travel')}
                onChange={(e) => handleMetadataListChange('retraction_minimum_travel', e.target.value)}
                placeholder="1"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.retraction.beforeWipe')}</label>
              <input
                type="text"
                value={getMetadataListString('retract_before_wipe')}
                onChange={(e) => handleMetadataListChange('retract_before_wipe', e.target.value)}
                placeholder="0%, 70%"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.retraction.wipeDistance')}</label>
              <input
                type="text"
                value={getMetadataListString('wipe_distance')}
                onChange={(e) => handleMetadataListChange('wipe_distance', e.target.value)}
                placeholder="2"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.retraction.zHop')}</label>
              <input
                type="text"
                value={getMetadataListString('z_hop')}
                onChange={(e) => handleMetadataListChange('z_hop', e.target.value)}
                placeholder="0.4"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.retraction.zHopType')}</label>
              <input
                type="text"
                value={getMetadataListString('z_hop_types')}
                onChange={(e) => handleMetadataListChange('z_hop_types', e.target.value)}
                placeholder="Auto Lift"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.retraction.toolchange')}</label>
              <input
                type="text"
                value={getMetadataListString('retract_length_toolchange')}
                onChange={(e) => handleMetadataListChange('retract_length_toolchange', e.target.value)}
                placeholder="0.8"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div className="flex items-start gap-3">
              <input
                type="checkbox"
                id="enable_long_retraction_when_cut"
                checked={getMetadataBoolean('enable_long_retraction_when_cut')}
                onChange={(e) => handleMetadataBooleanChange('enable_long_retraction_when_cut', e.target.checked)}
                className="w-4 h-4 mt-1 rounded border-white/30 bg-white/10"
              />
              <div>
                <label htmlFor="enable_long_retraction_when_cut" className="text-gray-300 text-sm font-medium">
                  {t('adminPrinters.retraction.longRetractionCut')}
                </label>
                <p className="text-xs text-gray-500">{t('adminPrinters.retraction.longRetractionCutHint')}</p>
              </div>
            </div>
          </div>
        )}
      </section>
      </div>
    );
  };

  const renderMotionTab = () => (
    <section className="space-y-6 bg-white/5 border border-white/10 rounded-2xl p-6 shadow-inner shadow-indigo-900/30">
      <div>
        <h4 className="text-sm font-semibold text-white uppercase tracking-wide">{t('adminPrinters.motion.title')}</h4>
        <p className="text-xs text-gray-400 mt-1">
          {t('adminPrinters.motion.desc')}
        </p>
      </div>
      {metadataInvalid ? (
        <div className="rounded-2xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {t('adminPrinters.motion.jsonError')}
        </div>
      ) : (
        <div className="space-y-6">
          <div>
            <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('adminPrinters.motion.maxSpeed')}</h5>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
              {(['machine_max_speed_x', 'machine_max_speed_y', 'machine_max_speed_z', 'machine_max_speed_e'] as const).map((key) => (
                <div key={key}>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{key.replace('machine_max_speed_', '').toUpperCase()}</label>
                  <input
                    type="text"
                    value={getMetadataListString(key)}
                    onChange={(e) => handleMetadataListChange(key, e.target.value)}
                    placeholder="500, 200"
                    className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                </div>
              ))}
            </div>
          </div>

          <div>
            <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('adminPrinters.motion.acceleration')}</h5>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
              {(
                [
                  'machine_max_acceleration_x',
                  'machine_max_acceleration_y',
                  'machine_max_acceleration_z',
                  'machine_max_acceleration_e',
                ] as const
              ).map((key) => (
                <div key={key}>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{key.replace('machine_max_acceleration_', '').toUpperCase()}</label>
                  <input
                    type="text"
                    value={getMetadataListString(key)}
                    onChange={(e) => handleMetadataListChange(key, e.target.value)}
                    placeholder="20000, 20000"
                    className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                </div>
              ))}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
              {(
                [
                  { key: 'machine_max_acceleration_extruding', label: t('adminPrinters.motion.extrusion') },
                  { key: 'machine_max_acceleration_retracting', label: t('adminPrinters.motion.retraction') },
                  { key: 'machine_max_acceleration_travel', label: t('adminPrinters.motion.travel') },
                ] as const
              ).map(({ key, label }) => (
                <div key={key}>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{label}</label>
                  <input
                    type="text"
                    value={getMetadataListString(key)}
                    onChange={(e) => handleMetadataListChange(key, e.target.value)}
                    placeholder="20000"
                    className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                </div>
              ))}
            </div>
          </div>

          <div>
            <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('adminPrinters.speed.jerk')}</h5>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
              {(
                [
                  'machine_max_jerk_x',
                  'machine_max_jerk_y',
                  'machine_max_jerk_z',
                  'machine_max_jerk_e',
                ] as const
              ).map((key) => (
                <div key={key}>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{key.replace('machine_max_jerk_', '').toUpperCase()}</label>
                  <input
                    type="text"
                    value={getMetadataListString(key)}
                    onChange={(e) => handleMetadataListChange(key, e.target.value)}
                    placeholder="8, 8"
                    className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                  />
                </div>
              ))}
            </div>
          </div>

          <div>
            <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('adminPrinters.motion.minSpeeds')}</h5>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.motion.minExtrusionRate')}</label>
                <input
                  type="text"
                  value={getMetadataListString('machine_min_extruding_rate')}
                  onChange={(e) => handleMetadataListChange('machine_min_extruding_rate', e.target.value)}
                  placeholder="0"
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.motion.minTravelRate')}</label>
                <input
                  type="text"
                  value={getMetadataListString('machine_min_travel_rate')}
                  onChange={(e) => handleMetadataListChange('machine_min_travel_rate', e.target.value)}
                  placeholder="0"
                  className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );

  const renderMultimaterialTab = () => (
    <section className="space-y-6 bg-white/5 border border-white/10 rounded-2xl p-6 shadow-inner shadow-indigo-900/30">
      <div>
        <h4 className="text-sm font-semibold text-white uppercase tracking-wide">Single extruder multi-material</h4>
        <p className="text-xs text-gray-400 mt-1">
          {t('adminPrinters.multimaterial.desc')}
        </p>
      </div>
      {metadataInvalid ? (
        <div className="rounded-2xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {t('adminPrinters.multimaterial.jsonError')}
        </div>
      ) : (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="single_extruder_multi_material"
                checked={getMetadataBoolean('single_extruder_multi_material')}
                onChange={(e) => handleMetadataBooleanChange('single_extruder_multi_material', e.target.checked)}
                className="w-4 h-4 rounded border-white/30 bg-white/10"
              />
              <label htmlFor="single_extruder_multi_material" className="text-gray-300 text-sm">
                Single Extruder Multi Material (SEMM)
              </label>
            </div>
            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="purge_in_prime_tower"
                checked={getMetadataBoolean('purge_in_prime_tower')}
                onChange={(e) => handleMetadataBooleanChange('purge_in_prime_tower', e.target.checked)}
                className="w-4 h-4 rounded border-white/30 bg-white/10"
              />
              <label htmlFor="purge_in_prime_tower" className="text-gray-300 text-sm">
                {t('adminPrinters.multimaterial.purgeInTower')}
              </label>
            </div>
            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="enable_filament_ramming"
                checked={getMetadataBoolean('enable_filament_ramming')}
                onChange={(e) => handleMetadataBooleanChange('enable_filament_ramming', e.target.checked)}
                className="w-4 h-4 rounded border-white/30 bg-white/10"
              />
              <label htmlFor="enable_filament_ramming" className="text-gray-300 text-sm">
                {t('adminPrinters.multimaterial.enableRamming')}
              </label>
            </div>
            <div className="flex items-center gap-3">
              <input
                type="checkbox"
                id="manual_filament_change"
                checked={getMetadataBoolean('manual_filament_change')}
                onChange={(e) => handleMetadataBooleanChange('manual_filament_change', e.target.checked)}
                className="w-4 h-4 rounded border-white/30 bg-white/10"
              />
              <label htmlFor="manual_filament_change" className="text-gray-300 text-sm">
                {t('adminPrinters.multimaterial.manualChange')}
              </label>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.multimaterial.loadTime')}</label>
              <input
                type="text"
                value={getMetadataString('machine_load_filament_time')}
                onChange={(e) => handleMetadataStringChange('machine_load_filament_time', e.target.value)}
                placeholder="29"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.multimaterial.unloadTime')}</label>
              <input
                type="text"
                value={getMetadataString('machine_unload_filament_time')}
                onChange={(e) => handleMetadataStringChange('machine_unload_filament_time', e.target.value)}
                placeholder="29"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.multimaterial.switchTime')}</label>
              <input
                type="text"
                value={getMetadataString('machine_switch_extruder_time')}
                onChange={(e) => handleMetadataStringChange('machine_switch_extruder_time', e.target.value)}
                placeholder="0"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.multimaterial.parkingRetraction')}</label>
              <input
                type="text"
                value={getMetadataString('parking_pos_retraction')}
                onChange={(e) => handleMetadataStringChange('parking_pos_retraction', e.target.value)}
                placeholder="e.g. 16"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.multimaterial.coolingTubeRetraction')}</label>
              <input
                type="text"
                value={getMetadataString('cooling_tube_retraction')}
                onChange={(e) => handleMetadataStringChange('cooling_tube_retraction', e.target.value)}
                placeholder="60"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.multimaterial.coolingTubeLength')}</label>
              <input
                type="text"
                value={getMetadataString('cooling_tube_length')}
                onChange={(e) => handleMetadataStringChange('cooling_tube_length', e.target.value)}
                placeholder="20"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">{t('adminPrinters.multimaterial.extraLoadingMove')}</label>
              <input
                type="text"
                value={getMetadataString('extra_loading_move')}
                onChange={(e) => handleMetadataStringChange('extra_loading_move', e.target.value)}
                placeholder="0"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">High current on swap</label>
              <input
                type="text"
                value={getMetadataString('high_current_on_filament_swap')}
                onChange={(e) => handleMetadataStringChange('high_current_on_filament_swap', e.target.value)}
                placeholder="0"
                className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500"
              />
            </div>
          </div>
            </div>
          )}
    </section>
  );

  const renderGcodeTab = () => (
    <section className="space-y-6 bg-white/5 border border-white/10 rounded-2xl p-6 shadow-inner shadow-indigo-900/30">
      <div>
        <h4 className="text-sm font-semibold text-white uppercase tracking-wide">{t('adminPrinters.gcode.title')}</h4>
        <p className="text-xs text-gray-400 mt-1">
          {t('adminPrinters.gcode.desc')}
        </p>
      </div>
      {metadataInvalid ? (
        <div className="rounded-2xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {t('adminPrinters.gcode.jsonError')}
        </div>
      ) : (
        <div className="space-y-6">
          {PRINTER_GCODE_FIELDS.map(({ key, label }) => {
            const textareaId = `printer-gcode-${key}`;
            const value = getMetadataString(key);
            return (
              <div key={key}>
                <div className="flex items-center justify-between gap-3 mb-2">
                  <label className="text-gray-300 text-sm font-medium">{label}</label>
                  {value ? (
                    <span className="text-[10px] uppercase tracking-wider text-purple-200/60">
                      {t('adminPrinters.gcode.chars')}: {value.length}
                    </span>
                  ) : null}
                </div>
                <div
                  className="flex items-start gap-3"
                  onClick={(e) => e.stopPropagation()}
                  onMouseDown={(e) => e.stopPropagation()}
                >
                  <textarea
                    id={textareaId}
                    value={value}
                    onChange={(e) => handleMetadataStringChange(key, e.target.value)}
                    rows={12}
                    className="flex-1 px-3 py-2 bg-black/30 border border-white/20 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 font-mono text-sm leading-5 resize-none"
                    placeholder={t('adminPrinters.gcode.placeholder')}
                  />
                  <EditGCodeModal
                    isOpen={activeTab === 'gcode'}
                    onClose={() => {}}
                    onInsert={(placeholderText) => handleInsertGcodePlaceholder(key, textareaId, placeholderText)}
                    title={t('adminPrinters.gcode.placeholders')}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );

  const renderNotesTab = () => (
    <section className="space-y-4 bg-white/5 border border-white/10 rounded-2xl p-6 shadow-inner shadow-indigo-900/30">
      <div>
        <h4 className="text-sm font-semibold text-white uppercase tracking-wide">{t('adminPrinters.notes.title')}</h4>
        <p className="text-xs text-gray-400 mt-1">
          {t('adminPrinters.notes.desc')}
        </p>
      </div>
      <textarea
        value={formData.description}
        onChange={(e) => setFormData({ ...formData, description: e.target.value })}
        rows={10}
        className="w-full px-4 py-3 bg-white/10 border border-white/20 rounded-xl text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500"
        placeholder={t('adminPrinters.notes.placeholder')}
      />
    </section>
  );
  return (
    <ModalOverlay onClose={onClose} className="!bg-black/70 !items-start">
      <div className="mx-auto mt-10 mb-6 w-full max-w-5xl px-4 md:px-8" onClick={(e) => e.stopPropagation()}>
        <div className="bg-gradient-to-br from-[#1c1140] to-[#23185a] rounded-3xl shadow-[0_20px_60px_-15px_rgba(76,29,149,0.7)] border border-white/15 h-[85vh] overflow-hidden flex flex-col">
          <div className="flex items-center justify-between px-6 md:px-10 py-6 border-b border-white/10">
            <div>
              <p className="text-xs uppercase tracking-[0.3em] text-purple-300/80 mb-2">{t('adminPrinters.modal.orcaForms')}</p>
              <h3 className="text-2xl font-bold text-white">
                {printer ? t('adminPrinters.modal.editPrinter') : t('adminPrinters.modal.createPrinter')}
              </h3>
            </div>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white transition"
              type="button"
              aria-label={t('adminPrinters.close')}
            >
              <X className="w-6 h-6" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto px-6 md:px-10 py-8">
            <form onSubmit={handleSubmit} className="flex flex-col h-full gap-8">
              <div className="flex flex-1 flex-col md:flex-row gap-6">
                <nav className="md:w-64 flex-shrink-0">
                  <div className="sticky top-0 space-y-2">
                    {tabConfig.map((tab) => {
                      const isActive = tab.key === activeTab;
                      return (
                        <button
                          key={tab.key}
                          type="button"
                          onClick={() => setActiveTab(tab.key)}
                          className={`w-full text-left px-4 py-3 rounded-2xl transition-all ${
                            isActive
                              ? 'bg-white/20 text-white shadow-[0_12px_30px_-12px_rgba(168,85,247,0.6)] ring-1 ring-purple-400/50'
                              : 'bg-white/5 text-gray-300 hover:bg-white/10'
                          }`}
                        >
                          <span className="block text-sm font-semibold">{tab.label}</span>
                          <span className="block text-xs text-purple-200/80 mt-1">{tab.description}</span>
                        </button>
                      );
                    })}
                  </div>
                </nav>
                <div className="flex-1 space-y-8 pb-6">
                  {activeTab === 'general' && renderGeneralTab()}
                  {activeTab === 'motion' && renderMotionTab()}
                  {activeTab === 'extruders' && renderExtrudersTab()}
                  {activeTab === 'multimaterial' && renderMultimaterialTab()}
                  {activeTab === 'gcode' && renderGcodeTab()}
                  {activeTab === 'notes' && renderNotesTab()}
                </div>
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-white/10 mt-auto">
            <button
              type="button"
              onClick={onClose}
              className="px-6 py-3 bg-white/10 hover:bg-white/20 text-white rounded-xl transition-all"
            >
              {t('adminPrinters.cancel')}
            </button>
            <button
              type="submit"
              disabled={isLoading}
                  className="flex items-center gap-2 px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-xl transition-all disabled:opacity-50"
            >
              <Save className="w-5 h-5" />
              <span>{printer ? t('adminPrinters.save') : t('adminPrinters.create')}</span>
            </button>
          </div>
        </form>
          </div>
        </div>
      </div>
    </ModalOverlay>
  );
}

