/** Модальное окно для создания printer profile */

import { useState, useEffect, FormEvent, useRef, useMemo } from 'react';
import { X, Save, Loader2, Pencil } from 'lucide-react';
import { Printer3DIcon } from './icons/Printer3DIcon';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { printerProfilesAPI, printersAPI } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import type { PrinterProfile, Printer } from '../types/api';
import { EditGCodeModal } from './EditGCodeModal';
import { useHeaderVisible } from '../hooks/useHeaderVisible';
import { CustomSelect } from './CustomSelect';
import { Dropdown } from './Dropdown';
import { useDebounce } from '../hooks/useDebounce';

interface CreatePrinterProfileModalProps {
  isOpen: boolean;
  onClose: () => void;
  profile?: PrinterProfile | null; // Если передан, то редактирование
  baseProfile?: PrinterProfile | null; // Базовый профиль для клонирования
  onRequestPrinter?: () => void; // Callback для открытия модалки создания заявки на принтер
}

export const CreatePrinterProfileModal: React.FC<CreatePrinterProfileModalProps> = ({
  isOpen,
  onClose,
  profile,
  baseProfile,
  onRequestPrinter,
}) => {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const isHeaderVisible = useHeaderVisible();
  
  // Поиск принтеров
  const [printerSearch, setPrinterSearch] = useState('');
  const debouncedPrinterSearch = useDebounce(printerSearch, 250);
  
  // Кэш выбранных принтеров (чтобы выбранный принтер не пропадал после фильтрации)
  const [printersCache, setPrintersCache] = useState<Record<number, Printer>>({});
  
  // Загружаем список принтеров для выбора с фильтрацией
  const { data: printersData } = useQuery({
    queryKey: ['printers', 'for-profile', { search: debouncedPrinterSearch }],
    queryFn: () => printersAPI.list({ 
      active_only: true, 
      page: 1, 
      size: 100,
      search: debouncedPrinterSearch || undefined,
    }),
    enabled: isOpen,
  });
  
  // Обновляем кэш при загрузке новых принтеров
  useEffect(() => {
    if (printersData?.items) {
      setPrintersCache((prev) => {
        const next = { ...prev };
        printersData.items.forEach((printer) => {
          next[printer.id] = printer;
        });
        return next;
      });
    }
  }, [printersData]);

  // Табы
  type TabKey = 'general' | 'motion' | 'extruders' | 'multimaterial' | 'gcode' | 'notes';
  const [activeTab, setActiveTab] = useState<TabKey>('general');

  // Форма
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [description, setDescription] = useState('');
  const [printerId, setPrinterId] = useState<number | null>(null);
  const [vendor, setVendor] = useState('');
  const [printableAreaX, setPrintableAreaX] = useState('');
  const [printableAreaY, setPrintableAreaY] = useState('');
  const [printableHeightMm, setPrintableHeightMm] = useState('');
  const [nozzleDiameters, setNozzleDiameters] = useState<string[]>([]);
  const [newNozzleDiameter, setNewNozzleDiameter] = useState('');
  const [notes, setNotes] = useState('');
  const [extraMetadata, setExtraMetadata] = useState('');
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [newMaterial, setNewMaterial] = useState('');
  const [defaultMaterials, setDefaultMaterials] = useState<string[]>([]);
  const [imageUrl, setImageUrl] = useState('');
  const [showGcodeModals, setShowGcodeModals] = useState<Record<string, boolean>>({});

  // Флаг для отслеживания, было ли имя изменено пользователем вручную
  const [nameManuallyChanged, setNameManuallyChanged] = useState(false);

  // Автогенерация имени в формате OrcaSlicer при выборе принтера и сопла
  // Срабатывает только если имя не было изменено пользователем вручную
  useEffect(() => {
    if (!profile && !baseProfile && !nameManuallyChanged && printerId && nozzleDiameters.length > 0) {
      const selectedPrinter = printersCache[printerId];
      if (selectedPrinter) {
        const firstNozzle = nozzleDiameters[0];
        const nozzleStr = parseFloat(firstNozzle).toString().replace(/\.?0+$/, '');
        const generatedName = `${selectedPrinter.name} ${nozzleStr} nozzle`;
        setName(generatedName);
      }
    }
  }, [printerId, nozzleDiameters, profile, baseProfile, printersCache, nameManuallyChanged]);

  // Сбрасываем флаг при изменении режима (редактирование/создание)
  useEffect(() => {
    if (isOpen) {
      setNameManuallyChanged(false);
    }
  }, [isOpen, profile, baseProfile]);

  // Генерируем slug из name при изменении
  useEffect(() => {
    if (!profile && !baseProfile && name) {
      const generatedSlug = name
        .toLowerCase()
        .trim()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-z0-9\s-]/g, '')
        .replace(/\s+/g, '-')
        .replace(/-+/g, '-')
        .replace(/^-|-$/g, '');
      setSlug(generatedSlug || '');
    }
  }, [name, profile, baseProfile]);

  // Парсинг extra_metadata
  const parsedMetadata = useMemo(() => {
    if (!extraMetadata.trim()) {
      return {};
    }
    try {
      return JSON.parse(extraMetadata);
    } catch (error) {
      return null;
    }
  }, [extraMetadata]);

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
      return value.join(', ');
    }
    if (value === undefined || value === null) {
      return '';
    }
    return String(value);
  };

  const getMetadataListValues = (key: string): string[] => {
    if (!extraMetadata.trim()) {
      return [];
    }
    try {
      const parsed = JSON.parse(extraMetadata);
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
      base = extraMetadata.trim() ? JSON.parse(extraMetadata) : {};
    } catch (error) {
      base = {};
    }
    
    const isSpecialArrayField = ARRAY_FIELDS_WITH_EMPTY_VALID.includes(key);
    
    if (
      value === undefined ||
      value === null ||
      (typeof value === 'string' && value.trim() === '') ||
      (Array.isArray(value) && value.length === 0 && !isSpecialArrayField)
    ) {
      delete base[key];
    } else {
      base[key] = value;
    }
    setJsonError(null);
    setExtraMetadata(Object.keys(base).length ? JSON.stringify(base, null, 2) : '');
  };

  const handleMetadataListChange = (key: string, rawValue: string) => {
    const normalized = rawValue
      .split(',')
      .map((item) => item.trim())
      .filter((item) => item.length > 0);
    
    const isSpecialArrayField = ARRAY_FIELDS_WITH_EMPTY_VALID.includes(key);
    
    if (normalized.length > 0) {
      updateMetadataValue(key, normalized);
    } else if (isSpecialArrayField) {
      updateMetadataValue(key, []);
    } else {
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

  const handleFormatJson = () => {
    if (!extraMetadata.trim()) return;
    try {
      const formatted = JSON.stringify(JSON.parse(extraMetadata), null, 2);
      setExtraMetadata(formatted);
      setJsonError(null);
    } catch (error) {
      setJsonError('Не удалось отформатировать JSON. Проверьте синтаксис.');
    }
  };

  // Заполняем форму при редактировании или клонировании
  useEffect(() => {
    if (isOpen) {
      if (profile) {
        // Редактирование
        setName(profile.name || '');
        setSlug(profile.slug || '');
        setDescription(profile.description || '');
        setPrinterId(profile.printer_id);
        setPrinterSearch('');
        setVendor(profile.vendor || '');
        if (profile.printable_area) {
          setPrintableAreaX(profile.printable_area.x?.toString() || '');
          setPrintableAreaY(profile.printable_area.y?.toString() || '');
        } else {
          setPrintableAreaX('');
          setPrintableAreaY('');
        }
        setPrintableHeightMm(profile.printable_height_mm?.toString() || '');
        setNozzleDiameters(profile.nozzle_diameters?.map(d => d.toString()) || []);
        setNotes(profile.notes || '');
        setExtraMetadata(profile.extra_metadata ? JSON.stringify(profile.extra_metadata, null, 2) : '');
        setDefaultMaterials([]); // TODO: если будет поле в модели
        setImageUrl(''); // TODO: если будет поле в модели
      } else if (baseProfile) {
        // Клонирование
        setName(`${baseProfile.name} (копия)`);
        setSlug(`${baseProfile.slug}-copy`);
        setDescription(baseProfile.description || '');
        setPrinterId(baseProfile.printer_id);
        setPrinterSearch('');
        setVendor(baseProfile.vendor || '');
        if (baseProfile.printable_area) {
          setPrintableAreaX(baseProfile.printable_area.x?.toString() || '');
          setPrintableAreaY(baseProfile.printable_area.y?.toString() || '');
        } else {
          setPrintableAreaX('');
          setPrintableAreaY('');
        }
        setPrintableHeightMm(baseProfile.printable_height_mm?.toString() || '');
        setNozzleDiameters(baseProfile.nozzle_diameters?.map(d => d.toString()) || []);
        setNotes(baseProfile.notes || '');
        setExtraMetadata(baseProfile.extra_metadata ? JSON.stringify(baseProfile.extra_metadata, null, 2) : '');
        setDefaultMaterials([]);
        setImageUrl('');
      } else {
        // Создание нового
        setName('');
        setSlug('');
        setDescription('');
        setPrinterId(null);
        setPrinterSearch('');
        setVendor('');
        setPrintableAreaX('');
        setPrintableAreaY('');
        setPrintableHeightMm('');
        setNozzleDiameters([]);
        setNotes('');
        setExtraMetadata('');
        setDefaultMaterials([]);
        setImageUrl('');
      }
      setActiveTab('general');
      setNewNozzleDiameter('');
      setNewMaterial('');
      setJsonError(null);
      setShowGcodeModals({});
    }
  }, [isOpen, profile, baseProfile]);

  // Мутация для создания/обновления
  const createMutation = useMutation({
    mutationFn: (data: any) => {
      if (profile) {
        return printerProfilesAPI.update(profile.id, data);
      }
      return printerProfilesAPI.create(data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['printer-profiles'] });
      queryClient.invalidateQueries({ queryKey: ['printer-profiles', user?.id] });
      onClose();
    },
    onError: (error: any) => {
      console.error('Ошибка сохранения printer profile:', error);
      alert(error?.response?.data?.detail || error?.message || 'Не удалось сохранить профиль принтера');
    },
  });

  const handleAddMaterial = () => {
    const trimmed = newMaterial.trim();
    if (!trimmed) return;
    if (defaultMaterials.includes(trimmed)) {
      setNewMaterial('');
      return;
    }
    setDefaultMaterials([...defaultMaterials, trimmed]);
    setNewMaterial('');
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

  const toggleGcodeModal = (key: string) => {
    setShowGcodeModals((prev) => ({
      ...prev,
      [key]: !prev[key],
    }));
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    
    if (!name.trim()) {
      alert('Введите название профиля');
      return;
    }
    
    if (!slug.trim()) {
      alert('Введите slug профиля');
      return;
    }

    let extraMetadataObj: Record<string, any> | undefined;
    if (extraMetadata.trim()) {
      try {
        extraMetadataObj = JSON.parse(extraMetadata);
        setJsonError(null);
      } catch (error) {
        console.error('Invalid extra metadata JSON', error);
        setJsonError('Некорректный JSON. Проверьте синтаксис.');
        return;
      }
    } else {
      setJsonError(null);
    }

    // Извлекаем start_gcode и end_gcode из extra_metadata для обратной совместимости
    const startGcode = extraMetadataObj?.machine_start_gcode || '';
    const endGcode = extraMetadataObj?.machine_end_gcode || '';

    const printableArea = (printableAreaX && printableAreaY) ? {
      x: parseFloat(printableAreaX),
      y: parseFloat(printableAreaY),
    } : null;

    const nozzleDiametersArray = nozzleDiameters
      .map(d => parseFloat(d))
      .filter(d => !isNaN(d) && d > 0);

    const data = {
      name: name.trim(),
      slug: slug.trim(),
      description: description.trim() || null,
      printer_id: printerId,
      vendor: vendor.trim() || null,
      printable_area: printableArea,
      printable_height_mm: printableHeightMm ? parseFloat(printableHeightMm) : null,
      nozzle_diameters: nozzleDiametersArray.length > 0 ? nozzleDiametersArray : null,
      start_gcode: startGcode || null,
      end_gcode: endGcode || null,
      notes: notes.trim() || null,
      extra_metadata: extraMetadataObj,
      active: true,
    };

    createMutation.mutate(data);
  };

  // Объединяем список принтеров с кэшем, чтобы выбранный принтер всегда был доступен
  const allPrinters = useMemo(() => {
    const fromData = printersData?.items || [];
    const fromCache = Object.values(printersCache);
    
    // Объединяем и убираем дубликаты
    const merged: Printer[] = [];
    const seenIds = new Set<number>();
    
    [...fromData, ...fromCache].forEach((printer) => {
      if (!seenIds.has(printer.id)) {
        seenIds.add(printer.id);
        merged.push(printer);
      }
    });
    
    return merged;
  }, [printersData?.items, printersCache]);
  
  const printers = allPrinters;

  // Создаем опции для Dropdown (вынесено наверх, чтобы избежать проблем с порядком хуков)
  const printerOptions = useMemo(() => {
    // Создаем опции из объединенного списка принтеров
    const options = printers.map((printer) => ({
      value: printer.id,
      label: `${printer.manufacturer} ${printer.model}`,
    }));
    
    // ВАЖНО: Если выбран принтер, но его нет в списке (например, после обновления списка),
    // добавляем его из кэша, чтобы он не пропал из поля ввода
    if (printerId && !printers.find(p => p.id === printerId) && printersCache[printerId]) {
      const cachedPrinter = printersCache[printerId];
      return [
        {
          value: cachedPrinter.id,
          label: `${cachedPrinter.manufacturer} ${cachedPrinter.model}`,
        },
        ...options,
      ];
    }
    
    return options;
  }, [printers, printerId, printersCache]);

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

  const handleAddNozzleDiameter = () => {
    const trimmed = newNozzleDiameter.trim();
    if (!trimmed) return;
    const value = parseFloat(trimmed);
    if (isNaN(value) || value <= 0) {
      alert('Введите корректное значение диаметра сопла (положительное число)');
      return;
    }
    const valueStr = value.toString();
    if (nozzleDiameters.includes(valueStr)) {
      setNewNozzleDiameter('');
      return;
    }
    setNozzleDiameters([...nozzleDiameters, valueStr]);
    setNewNozzleDiameter('');
  };

  const handleRemoveNozzleDiameter = (diameter: string) => {
    setNozzleDiameters(nozzleDiameters.filter(d => d !== diameter));
  };

  // Render functions для табов
  const renderGeneralTab = () => {
    // Получаем выбранный принтер для использования в UI
    const selectedPrinter = printerId ? (printers.find(p => p.id === printerId) || printersCache[printerId]) : null;
    
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
    const firmwareFlagOptions: Array<{ key: string; label: string; description?: string }> = [
      { key: 'use_relative_e_distances', label: 'Относительные координаты E', description: 'Включает относительный режим подачи в G-code (M83).' },
      { key: 'use_firmware_retraction', label: 'Откат на уровне прошивки', description: 'Передаёт управление ретрактом прошивке (G10/G11).' },
      { key: 'pellet_modded_printer', label: 'Гранульная модификация', description: 'Принтер модифицирован под гранулы / пеллетный экструдер.' },
      { key: 'support_multi_bed_types', label: 'Несколько типов столов', description: 'Поддерживает разные пластины и профили стола.' },
      { key: 'support_air_filtration', label: 'Фильтрация воздуха' },
      { key: 'support_chamber_temp_control', label: 'Контроль температуры камеры' },
      { key: 'auxiliary_fan', label: 'Внешний вентилятор' },
      { key: 'scan_first_layer', label: 'Сканирование первого слоя' },
      { key: 'disable_m73', label: 'Отключить отчёт времени M73' },
      { key: 'bbl_use_printhost', label: 'Использовать PrintHost' },
    ];
    const coolingFanFields: Array<{ key: string; label: string; placeholder?: string; unit?: string }> = [
      { key: 'fan_speedup_time', label: 'Время разгона вентилятора', placeholder: '2', unit: 'с' },
      { key: 'fan_speedup_overhangs', label: 'Разгон для свесов', placeholder: '30', unit: '%' },
      { key: 'fan_kickstart', label: 'Kickstart', placeholder: '100', unit: '%' },
    ];
    const extruderClearanceFields: Array<{ key: string; label: string; placeholder?: string; unit?: string }> = [
      { key: 'extruder_clearance_radius', label: 'Радиус рабочей зоны экструдера', placeholder: '65', unit: 'мм' },
      { key: 'extruder_clearance_height_to_rod', label: 'Высота до направляющих', placeholder: '36', unit: 'мм' },
      { key: 'extruder_clearance_height_to_lid', label: 'Высота до крышки', placeholder: '140', unit: 'мм' },
    ];
    const adaptiveMeshFields: Array<{ key: string; label: string; placeholder?: string }> = [
      { key: 'bed_mesh_min', label: 'Bed mesh min (координаты)', placeholder: '0x0, 256x0...' },
      { key: 'bed_mesh_max', label: 'Bed mesh max (координаты)', placeholder: '256x256...' },
      { key: 'bed_mesh_probe_distance', label: 'Расстояние между точками сетки (мм)', placeholder: '30' },
      { key: 'adaptive_bed_mesh_margin', label: 'Отступ сетки (мм)', placeholder: '5' },
    ];
    const bedGeometryFields: Array<{ key: string; label: string; isList?: boolean; placeholder?: string }> = [
      { key: 'bed_shape', label: 'Форма стола (мм)', isList: true, placeholder: '0x0, 256x0, 256x256, 0x256' },
      { key: 'bed_exclude_area', label: 'Запретные зоны стола', isList: true, placeholder: '90x90, 166x166' },
      { key: 'bed_custom_rectangle', label: 'Пользовательский прямоугольник', isList: true, placeholder: '0x0, 256x0, 256x256, 0x256' },
      { key: 'origin_z', label: 'Смещение по Z', placeholder: '0' },
    ];
    const thumbnailsFields: Array<{ key: string; label: string; placeholder?: string }> = [
      { key: 'thumbnails', label: 'Thumbnails', placeholder: '32x32,64x64' },
      { key: 'thumbnails_format', label: 'Формат миниатюр', placeholder: 'png,gcode,ufp...' },
    ];

    return (
      <div className="space-y-6">
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Название <span className="text-red-400">*</span>
            {selectedPrinter && nozzleDiameters.length > 0 && (
              <span className="text-xs text-gray-400 ml-2">
                (Рекомендуемый формат для OrcaSlicer: &quot;{selectedPrinter.name} {nozzleDiameters[0]} nozzle&quot;)
              </span>
            )}
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              setNameManuallyChanged(true); // Отмечаем, что имя изменено вручную
            }}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
            placeholder={selectedPrinter && nozzleDiameters.length > 0 
              ? `${selectedPrinter.name} ${nozzleDiameters[0]} nozzle`
              : "Например: Voron 2.4 350 0.4 nozzle"}
            required
          />
          {selectedPrinter && nozzleDiameters.length > 0 && !name.match(/nozzle$/i) && name && (
            <p className="text-xs text-amber-400 mt-1">
              💡 Рекомендуется формат для совместимости с OrcaSlicer: &quot;{selectedPrinter.name} {nozzleDiameters[0]} nozzle&quot;
            </p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Slug (уникальный идентификатор) <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 font-mono text-sm"
            placeholder="ender-3-pro-standard"
            required
          />
          <p className="text-xs text-gray-500 mt-1">Только латинские буквы, цифры и дефисы</p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Принтер (опционально)
          </label>
          <div className="space-y-2">
            <Dropdown
              value={printerId || ''}
              options={printerOptions}
              onChange={(val) => {
                if (val && typeof val === 'number') {
                  // ВАЖНО: Сначала находим и сохраняем выбранный принтер в кэш
                  const selectedPrinter = printers.find(p => p.id === val) || printersCache[val];
                  if (selectedPrinter) {
                    // Сохраняем в кэш синхронно, чтобы он сразу был доступен
                    setPrintersCache((prev) => ({ ...prev, [selectedPrinter.id]: selectedPrinter }));
                  }
                  // Устанавливаем ID синхронно
                  setPrinterId(val);
                  // Очищаем поиск с небольшой задержкой, чтобы дать время кэшу обновиться
                  // и чтобы выбранный принтер успел попасть в options перед очисткой
                  setTimeout(() => {
                    setPrinterSearch('');
                  }, 50);
                } else {
                  setPrinterId(null);
                  setPrinterSearch('');
                }
              }}
              placeholder="Выберите принтер или начните вводить название"
              filterable
              filterValue={printerSearch}
              onFilterChange={setPrinterSearch}
              emptyMessage="Принтер не найден"
            />
            {printers.length === 0 && printerSearch && (
              <p className="text-xs text-gray-400">
                Принтеры не найдены. Сначала запросите добавление принтера в базу.
              </p>
            )}
            {onRequestPrinter && (
              <p className="text-xs text-gray-400">
                Ваш принтер отсутствует в списке?{' '}
                <button
                  type="button"
                  onClick={() => {
                    onRequestPrinter();
                  }}
                  className="text-purple-400 hover:text-purple-300 underline"
                >
                  Запросить добавление принтера
                </button>
              </p>
            )}
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Vendor (производитель/поставщик)
          </label>
          <input
            type="text"
            value={vendor}
            onChange={(e) => setVendor(e.target.value)}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
            placeholder="Например: Bambu Lab, Creality"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-3">
            Рабочая область (мм)
          </label>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-xs text-gray-400 mb-1">Ширина X (мм)</label>
              <input
                type="number"
                step="0.1"
                value={printableAreaX}
                onChange={(e) => setPrintableAreaX(e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                placeholder="220"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Глубина Y (мм)</label>
              <input
                type="number"
                step="0.1"
                value={printableAreaY}
                onChange={(e) => setPrintableAreaY(e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                placeholder="220"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-400 mb-1">Высота Z (мм)</label>
              <input
                type="number"
                step="0.1"
                value={printableHeightMm}
                onChange={(e) => setPrintableHeightMm(e.target.value)}
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                placeholder="250"
              />
            </div>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Диаметры сопел (мм)
          </label>
          <div className="space-y-3">
            {nozzleDiameters.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {nozzleDiameters.map((diameter) => (
                  <span
                    key={diameter}
                    className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-purple-500/20 text-purple-200 text-sm"
                  >
                    {diameter} мм
                    <button
                      type="button"
                      onClick={() => handleRemoveNozzleDiameter(diameter)}
                      className="hover:text-white transition"
                      aria-label="Удалить диаметр"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
            <div className="flex gap-2">
              <input
                type="number"
                step="0.1"
                min="0.1"
                value={newNozzleDiameter}
                onChange={(e) => setNewNozzleDiameter(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    handleAddNozzleDiameter();
                  }
                }}
                placeholder="0.4"
                className="flex-1 bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />
              <button
                type="button"
                onClick={handleAddNozzleDiameter}
                className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-all"
              >
                Добавить
              </button>
            </div>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Материалы по умолчанию
          </label>
          <div className="flex flex-wrap gap-2 mb-2">
            {defaultMaterials.map((material) => (
              <span
                key={material}
                className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-indigo-500/20 text-indigo-100 text-xs"
              >
                {material}
                <button
                  type="button"
                  onClick={() => setDefaultMaterials(defaultMaterials.filter((m) => m !== material))}
                  className="hover:text-white transition"
                  aria-label="Удалить материал"
                >
                  ×
                </button>
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={newMaterial}
              onChange={(e) => setNewMaterial(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  handleAddMaterial();
                }
              }}
              placeholder="PLA"
              className="flex-1 bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
            />
            <button
              type="button"
              onClick={handleAddMaterial}
              className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg transition-all"
            >
              Добавить
            </button>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            URL изображения
          </label>
          <input
            type="url"
            value={imageUrl}
            onChange={(e) => setImageUrl(e.target.value)}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
          />
        </div>

        {metadataInvalid ? (
          <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            Не удалось разобрать JSON в поле «Дополнительные метаданные». Исправьте содержимое вручную или нажмите «Форматировать».
          </div>
        ) : (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Структура принтера</label>
                <CustomSelect
                  value={getMetadataString('printer_structure') || null}
                  onChange={(value) => handleMetadataStringChange('printer_structure', (value as string) || '')}
                  options={printerStructureOptions.map((option) => ({ value: option, label: option }))}
                  placeholder="Выберите структуру"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">G-code flavor</label>
                <CustomSelect
                  value={getMetadataString('gcode_flavor') || null}
                  onChange={(value) => handleMetadataStringChange('gcode_flavor', (value as string) || '')}
                  options={gcodeFlavorOptions.map((option) => ({ value: option, label: option }))}
                  placeholder="Выберите flavor"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Технология печати</label>
                <CustomSelect
                  value={getMetadataString('printer_technology') || null}
                  onChange={(value) => handleMetadataStringChange('printer_technology', (value as string) || '')}
                  options={printerTechnologyOptions.map((option) => ({ value: option, label: option }))}
                  placeholder="Выберите технологию"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Пластина стола по умолчанию</label>
                <CustomSelect
                  value={getMetadataString('default_bed_type') || null}
                  onChange={(value) => handleMetadataStringChange('default_bed_type', (value as string) || '')}
                  options={defaultBedTypeOptions.map((option) => ({ value: option, label: option }))}
                  placeholder="Выберите пластину"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Хотэнд</label>
                <input
                  type="text"
                  value={getMetadataString('hotend_model')}
                  onChange={(e) => handleMetadataStringChange('hotend_model', e.target.value)}
                  placeholder="Phaetus Rapido..."
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Стоимость часа печати</label>
                <input
                  type="text"
                  value={getMetadataString('time_cost')}
                  onChange={(e) => handleMetadataStringChange('time_cost', e.target.value)}
                  placeholder="0.0"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Профиль филамента по умолчанию</label>
                <input
                  type="text"
                  value={getMetadataListString('default_filament_profile')}
                  onChange={(e) => handleMetadataListChange('default_filament_profile', e.target.value)}
                  placeholder="Generic PLA"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Вариант принтера</label>
                <input
                  type="text"
                  value={getMetadataListString('printer_variant')}
                  onChange={(e) => handleMetadataListChange('printer_variant', e.target.value)}
                  placeholder="0.4"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                />
              </div>
            </div>

            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">Стол и ограничения</h5>
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
                      className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                    />
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">Флаги и режимы</h5>
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
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">Cooling Fan</h5>
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
                        className={`w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 ${field.unit ? 'pr-16' : ''}`}
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
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">Экструдер: рабочая область</h5>
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
                        className={`w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 ${field.unit ? 'pr-16' : ''}`}
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
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">Adaptive bed mesh</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {adaptiveMeshFields.map((field) => (
                  <div key={field.key}>
                    <label className="block text-gray-300 mb-2 text-sm font-medium">{field.label}</label>
                    <input
                      type="text"
                      value={getMetadataListString(field.key)}
                      onChange={(e) => handleMetadataListChange(field.key, e.target.value)}
                      placeholder={field.placeholder}
                      className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                    />
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">Thumbnails</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {thumbnailsFields.map((field) => (
                  <div key={field.key}>
                    <label className="block text-gray-300 mb-2 text-sm font-medium">{field.label}</label>
                    <input
                      type="text"
                      value={getMetadataString(field.key)}
                      onChange={(e) => handleMetadataStringChange(field.key, e.target.value)}
                      placeholder={field.placeholder}
                      className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                    />
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            Дополнительные метаданные (JSON)
          </label>
          <div className="flex flex-col md:flex-row md:items-start gap-2 mb-2">
            <textarea
              value={extraMetadata}
              onChange={(e) => {
                setExtraMetadata(e.target.value);
                if (jsonError) {
                  setJsonError(null);
                }
              }}
              rows={8}
              className="flex-1 bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 font-mono text-sm"
              placeholder='{"profile": "Bambu PLA", "bed_type": "Smooth Plate"}'
            />
            <button
              type="button"
              onClick={handleFormatJson}
              className="px-4 py-3 bg-white/10 hover:bg-white/20 text-white rounded-lg text-xs font-medium transition-all"
            >
              Форматировать
            </button>
          </div>
          {jsonError && <p className="text-red-400 text-xs mt-1">{jsonError}</p>}
          <p className="text-xs text-gray-500 mt-1">
            Для произвольных флагов из OrcaSlicer. Например: {"{\"source\":\"system\",\"profile\":\"Bambu X1C\"}"}.
          </p>
        </div>
      </div>
    );
  };

  const renderMotionTab = () => (
    <div className="space-y-6">
      {metadataInvalid ? (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          Невозможно отобразить настройки движения: extra_metadata содержит некорректный JSON.
        </div>
      ) : (
        <div className="space-y-6">
          <div>
            <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">Максимальная скорость (мм/с)</h5>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
              {(['machine_max_speed_x', 'machine_max_speed_y', 'machine_max_speed_z', 'machine_max_speed_e'] as const).map((key) => (
                <div key={key}>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{key.replace('machine_max_speed_', '').toUpperCase()}</label>
                  <input
                    type="text"
                    value={getMetadataListString(key)}
                    onChange={(e) => handleMetadataListChange(key, e.target.value)}
                    placeholder="500, 200"
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                  />
                </div>
              ))}
            </div>
          </div>

          <div>
            <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">Ускорения (мм/с²)</h5>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
              {(['machine_max_acceleration_x', 'machine_max_acceleration_y', 'machine_max_acceleration_z', 'machine_max_acceleration_e'] as const).map((key) => (
                <div key={key}>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{key.replace('machine_max_acceleration_', '').toUpperCase()}</label>
                  <input
                    type="text"
                    value={getMetadataListString(key)}
                    onChange={(e) => handleMetadataListChange(key, e.target.value)}
                    placeholder="20000, 20000"
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                  />
                </div>
              ))}
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mt-4">
              {([
                { key: 'machine_max_acceleration_extruding', label: 'Экструзия' },
                { key: 'machine_max_acceleration_retracting', label: 'Ретракция' },
                { key: 'machine_max_acceleration_travel', label: 'Перемещения' },
              ] as const).map(({ key, label }) => (
                <div key={key}>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{label}</label>
                  <input
                    type="text"
                    value={getMetadataListString(key)}
                    onChange={(e) => handleMetadataListChange(key, e.target.value)}
                    placeholder="20000"
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                  />
                </div>
              ))}
            </div>
          </div>

          <div>
            <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">Jerk (мм/с)</h5>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
              {(['machine_max_jerk_x', 'machine_max_jerk_y', 'machine_max_jerk_z', 'machine_max_jerk_e'] as const).map((key) => (
                <div key={key}>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{key.replace('machine_max_jerk_', '').toUpperCase()}</label>
                  <input
                    type="text"
                    value={getMetadataListString(key)}
                    onChange={(e) => handleMetadataListChange(key, e.target.value)}
                    placeholder="8, 8"
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                  />
                </div>
              ))}
            </div>
          </div>

          <div>
            <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">Минимальные скорости (мм/с)</h5>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Минимальная скорость экструзии</label>
                <input
                  type="text"
                  value={getMetadataListString('machine_min_extruding_rate')}
                  onChange={(e) => handleMetadataListChange('machine_min_extruding_rate', e.target.value)}
                  placeholder="0"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Минимальная скорость перемещения</label>
                <input
                  type="text"
                  value={getMetadataListString('machine_min_travel_rate')}
                  onChange={(e) => handleMetadataListChange('machine_min_travel_rate', e.target.value)}
                  placeholder="0"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );

  const renderExtrudersTab = () => {
    const extruderTypeOptions = ['Direct Drive', 'Bowden'];
    const nozzleTypeOptions = ['brass', 'hardened_steel', 'stainless_steel', 'undefine'];
    const selectedNozzleType = getMetadataListValues('nozzle_type')[0] ?? '';

    return (
      <div className="space-y-6">
        {metadataInvalid ? (
          <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            Невозможно показать настройки Orca для экструдера: extra_metadata содержит некорректный JSON.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Тип экструдера</label>
              <CustomSelect
                value={getMetadataString('extruder_type') || null}
                onChange={(value) => handleMetadataStringChange('extruder_type', (value as string) || '')}
                options={extruderTypeOptions.map((option) => ({ value: option, label: option }))}
                placeholder="Выберите тип"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Варианты экструдера</label>
              <input
                type="text"
                value={getMetadataListString('extruder_variant_list')}
                onChange={(e) => handleMetadataListChange('extruder_variant_list', e.target.value)}
                placeholder="Direct Drive Standard"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Тип сопла</label>
              <CustomSelect
                value={selectedNozzleType || null}
                onChange={(value) => handleMetadataSelectFromOptions('nozzle_type', (value as string) || null)}
                options={nozzleTypeOptions.map((option) => ({ value: option, label: option }))}
                placeholder="Выберите тип"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Объем сопла</label>
              <div className="relative">
                <input
                  type="text"
                  value={getMetadataListString('nozzle_volume')}
                  onChange={(e) => handleMetadataListChange('nozzle_volume', e.target.value)}
                  placeholder="107"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 pr-16"
                />
                <span className="absolute inset-y-0 right-4 flex items-center text-xs text-gray-400 pointer-events-none">мм³</span>
              </div>
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Зазор до крышки</label>
              <div className="relative">
                <input
                  type="text"
                  value={getMetadataString('extruder_clearance_height_to_lid')}
                  onChange={(e) => handleMetadataStringChange('extruder_clearance_height_to_lid', e.target.value)}
                  placeholder="90"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 pr-16"
                />
                <span className="absolute inset-y-0 right-4 flex items-center text-xs text-gray-400 pointer-events-none">мм</span>
              </div>
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Макс. радиус зоны экструдера</label>
              <div className="relative">
                <input
                  type="text"
                  value={getMetadataString('extruder_clearance_max_radius')}
                  onChange={(e) => handleMetadataStringChange('extruder_clearance_max_radius', e.target.value)}
                  placeholder="68"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 pr-16"
                />
                <span className="absolute inset-y-0 right-4 flex items-center text-xs text-gray-400 pointer-events-none">мм</span>
              </div>
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">ID экструдера принтера</label>
              <input
                type="text"
                value={getMetadataListString('printer_extruder_id')}
                onChange={(e) => handleMetadataListChange('printer_extruder_id', e.target.value)}
                placeholder="0"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Вариант экструдера принтера</label>
              <input
                type="text"
                value={getMetadataListString('printer_extruder_variant')}
                onChange={(e) => handleMetadataListChange('printer_extruder_variant', e.target.value)}
                placeholder="0"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Физическая карта экструдеров</label>
              <input
                type="text"
                value={getMetadataListString('physical_extruder_map')}
                onChange={(e) => handleMetadataListChange('physical_extruder_map', e.target.value)}
                placeholder="0, 1"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Макс. высота слоя (мм)</label>
              <input
                type="text"
                value={getMetadataString('max_layer_height')}
                onChange={(e) => handleMetadataStringChange('max_layer_height', e.target.value)}
                placeholder="0.3"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Мин. высота слоя (мм)</label>
              <input
                type="text"
                value={getMetadataString('min_layer_height')}
                onChange={(e) => handleMetadataStringChange('min_layer_height', e.target.value)}
                placeholder="0.1"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />
            </div>
          </div>
        )}

        <div>
          <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">Ретракция и Z-hop</h5>
          {metadataInvalid ? (
            <p className="text-xs text-red-200">
              Невозможно отобразить параметры: extra_metadata содержит некорректный JSON.
            </p>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Ретракция (мм)</label>
                <input
                  type="text"
                  value={getMetadataListString('retraction_length')}
                  onChange={(e) => handleMetadataListChange('retraction_length', e.target.value)}
                  placeholder="0.8"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Скорость ретракции (мм/с)</label>
                <input
                  type="text"
                  value={getMetadataListString('retraction_speed')}
                  onChange={(e) => handleMetadataListChange('retraction_speed', e.target.value)}
                  placeholder="30"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Скорость деретракции (мм/с)</label>
                <input
                  type="text"
                  value={getMetadataListString('deretraction_speed')}
                  onChange={(e) => handleMetadataListChange('deretraction_speed', e.target.value)}
                  placeholder="30"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Минимальное движение для ретракта (мм)</label>
                <input
                  type="text"
                  value={getMetadataListString('retraction_minimum_travel')}
                  onChange={(e) => handleMetadataListChange('retraction_minimum_travel', e.target.value)}
                  placeholder="1"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Ретракт перед очисткой (%)</label>
                <input
                  type="text"
                  value={getMetadataListString('retract_before_wipe')}
                  onChange={(e) => handleMetadataListChange('retract_before_wipe', e.target.value)}
                  placeholder="0%, 70%"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Wipe distance (мм)</label>
                <input
                  type="text"
                  value={getMetadataListString('wipe_distance')}
                  onChange={(e) => handleMetadataListChange('wipe_distance', e.target.value)}
                  placeholder="2"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Z-hop (мм)</label>
                <input
                  type="text"
                  value={getMetadataListString('z_hop')}
                  onChange={(e) => handleMetadataListChange('z_hop', e.target.value)}
                  placeholder="0.4"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Тип Z-hop</label>
                <input
                  type="text"
                  value={getMetadataListString('z_hop_types')}
                  onChange={(e) => handleMetadataListChange('z_hop_types', e.target.value)}
                  placeholder="Auto Lift"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">Ретракт при смене инструмента (мм)</label>
                <input
                  type="text"
                  value={getMetadataListString('retract_length_toolchange')}
                  onChange={(e) => handleMetadataListChange('retract_length_toolchange', e.target.value)}
                  placeholder="0.8"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
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
                    Длинная ретракция при резке
                  </label>
                  <p className="text-xs text-gray-500">Включает длинную ретракцию при резке нити</p>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  };

  const renderMultimaterialTab = () => (
    <div className="space-y-6">
      {metadataInvalid ? (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          Невозможно отобразить параметры мульти-материала: extra_metadata содержит некорректный JSON.
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
                Очищать в башне (purge_in_prime_tower)
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
                Включить ramming
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
                Ручная замена филамента
              </label>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Время загрузки филамента (сек)</label>
              <input
                type="text"
                value={getMetadataString('machine_load_filament_time')}
                onChange={(e) => handleMetadataStringChange('machine_load_filament_time', e.target.value)}
                placeholder="29"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Время выгрузки филамента (сек)</label>
              <input
                type="text"
                value={getMetadataString('machine_unload_filament_time')}
                onChange={(e) => handleMetadataStringChange('machine_unload_filament_time', e.target.value)}
                placeholder="29"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Время смены экструдера (сек)</label>
              <input
                type="text"
                value={getMetadataString('machine_switch_extruder_time')}
                onChange={(e) => handleMetadataStringChange('machine_switch_extruder_time', e.target.value)}
                placeholder="0"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Очистка перед парковкой (мм)</label>
              <input
                type="text"
                value={getMetadataString('parking_pos_retraction')}
                onChange={(e) => handleMetadataStringChange('parking_pos_retraction', e.target.value)}
                placeholder="например 16"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Cooling tube retraction (мм)</label>
              <input
                type="text"
                value={getMetadataString('cooling_tube_retraction')}
                onChange={(e) => handleMetadataStringChange('cooling_tube_retraction', e.target.value)}
                placeholder="60"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Cooling tube length (мм)</label>
              <input
                type="text"
                value={getMetadataString('cooling_tube_length')}
                onChange={(e) => handleMetadataStringChange('cooling_tube_length', e.target.value)}
                placeholder="20"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">Extra loading move (мм)</label>
              <input
                type="text"
                value={getMetadataString('extra_loading_move')}
                onChange={(e) => handleMetadataStringChange('extra_loading_move', e.target.value)}
                placeholder="0"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />
            </div>
            <div>
              <label className="block text-gray-300 mb-2 text-sm font-medium">High current on swap</label>
              <input
                type="text"
                value={getMetadataString('high_current_on_filament_swap')}
                onChange={(e) => handleMetadataStringChange('high_current_on_filament_swap', e.target.value)}
                placeholder="0"
                className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );

  const renderGcodeTab = () => (
    <div className="space-y-6">
      {metadataInvalid ? (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          Невозможно отобразить G-code: extra_metadata содержит некорректный JSON.
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
                      Символов: {value.length}
                    </span>
                  ) : null}
                </div>
                <div className="relative flex items-start gap-3">
                  <textarea
                    id={textareaId}
                    value={value}
                    onChange={(e) => handleMetadataStringChange(key, e.target.value)}
                    rows={8}
                    className="flex-1 bg-white/5 border border-white/10 rounded-lg px-4 py-2 pr-10 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 font-mono text-sm resize-none"
                    placeholder="; Ваш кастомный G-code..."
                  />
                  <button
                    type="button"
                    onClick={() => toggleGcodeModal(key)}
                    className={`absolute right-2 top-2 p-1.5 rounded hover:bg-white/10 transition-all ${
                      showGcodeModals[key]
                        ? 'text-purple-400 bg-purple-500/20'
                        : 'text-gray-400 hover:text-purple-400'
                    }`}
                    title="Вставить плейсхолдер"
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                  {showGcodeModals[key] && (
                    <EditGCodeModal
                      isOpen={showGcodeModals[key]}
                      onClose={() => toggleGcodeModal(key)}
                      onInsert={(placeholderText) => handleInsertGcodePlaceholder(key, textareaId, placeholderText)}
                      title={`Вставить плейсхолдер в ${label}`}
                    />
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );

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
          className={`bg-gradient-to-br from-gray-900 to-gray-800 rounded-2xl shadow-2xl border border-white/20 max-w-5xl w-full ${isHeaderVisible ? 'max-h-[calc(100vh-100px)]' : 'max-h-[90vh]'} overflow-hidden flex flex-col pointer-events-auto`}
          onClick={(e) => e.stopPropagation()}
          onMouseDown={(e) => e.stopPropagation()}
        >
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-white/10">
          <div className="flex items-center gap-3">
            <Printer3DIcon className="w-6 h-6 text-purple-400" />
            <h2 className="text-2xl font-bold text-white">
              {profile ? 'Редактировать профиль принтера' : baseProfile ? 'Клонировать профиль принтера' : 'Создать профиль принтера'}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-white/10 rounded-lg text-gray-400 hover:text-white transition-all"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tabs */}
        <div className="flex flex-wrap gap-2 mb-4 border-b border-white/20 px-6 pt-4">
          <button
            type="button"
            onClick={() => setActiveTab('general')}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-all ${
              activeTab === 'general'
                ? 'bg-white/10 text-white border-b-2 border-purple-500'
                : 'text-gray-400 hover:text-white hover:bg-white/5'
            }`}
          >
            Общая информация
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('motion')}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-all ${
              activeTab === 'motion'
                ? 'bg-white/10 text-white border-b-2 border-purple-500'
                : 'text-gray-400 hover:text-white hover:bg-white/5'
            }`}
          >
            Motion ability
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('extruders')}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-all ${
              activeTab === 'extruders'
                ? 'bg-white/10 text-white border-b-2 border-purple-500'
                : 'text-gray-400 hover:text-white hover:bg-white/5'
            }`}
          >
            Экструдеры
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('multimaterial')}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-all ${
              activeTab === 'multimaterial'
                ? 'bg-white/10 text-white border-b-2 border-purple-500'
                : 'text-gray-400 hover:text-white hover:bg-white/5'
            }`}
          >
            Multimaterial
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('gcode')}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-all ${
              activeTab === 'gcode'
                ? 'bg-white/10 text-white border-b-2 border-purple-500'
                : 'text-gray-400 hover:text-white hover:bg-white/5'
            }`}
          >
            G-code
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('notes')}
            className={`px-4 py-2 text-sm font-medium rounded-t-lg transition-all ${
              activeTab === 'notes'
                ? 'bg-white/10 text-white border-b-2 border-purple-500'
                : 'text-gray-400 hover:text-white hover:bg-white/5'
            }`}
          >
            Заметки
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto p-6 space-y-6">
          {activeTab === 'general' && renderGeneralTab()}
          {activeTab === 'motion' && renderMotionTab()}
          {activeTab === 'extruders' && renderExtrudersTab()}
          {activeTab === 'multimaterial' && renderMultimaterialTab()}

          {activeTab === 'gcode' && renderGcodeTab()}
          {activeTab === 'notes' && (
            <div className="space-y-6">
              {/* Заметки */}
              <div>
                <label className="block text-sm font-medium text-gray-300 mb-2">
                  Заметки (только для вас)
                </label>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={10}
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 resize-none"
                  placeholder="Личные заметки о профиле..."
                />
                <p className="text-xs text-gray-500 mt-1">
                  Эти заметки видны только вам и не отображаются при экспорте в OrcaSlicer
                </p>
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center justify-end gap-3 pt-4 border-t border-white/10">
            <button
              type="button"
              onClick={onClose}
              className="px-6 py-2 rounded-lg border border-white/20 text-gray-300 hover:bg-white/10 transition-all"
            >
              Отмена
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="px-6 py-2 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-lg transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {createMutation.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Сохранение...
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  {profile ? 'Сохранить изменения' : 'Создать профиль'}
                </>
              )}
            </button>
          </div>
        </form>
        </div>
      </div>
    </div>
  );
};

