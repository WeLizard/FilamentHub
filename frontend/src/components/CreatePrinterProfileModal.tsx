/** Модальное окно для создания printer profile */

import { useState, useEffect, FormEvent, useMemo } from 'react';
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
import { useTranslation } from 'react-i18next';
import { translateApiError } from '../utils/translateApiError';

interface CreatePrinterProfileModalProps {
  isOpen: boolean;
  onClose: () => void;
  profile?: PrinterProfile | null; // Если передан, то редактирование
  baseProfile?: PrinterProfile | null; // Базовый профиль для клонирования
  onRequestPrinter?: () => void; // Callback для открытия модалки создания заявки на принтер
}

type CanonicalOption = {
  value: string;
  labelKey: string;
};

const ORCA_PRINTER_STRUCTURE_OPTIONS: CanonicalOption[] = [
  { value: 'undefine', labelKey: 'printerProfile.options.printerStructure.undefine' },
  { value: 'corexy', labelKey: 'printerProfile.options.printerStructure.corexy' },
  { value: 'i3', labelKey: 'printerProfile.options.printerStructure.i3' },
  { value: 'hbot', labelKey: 'printerProfile.options.printerStructure.hbot' },
  { value: 'delta', labelKey: 'printerProfile.options.printerStructure.delta' },
];

const ORCA_GCODE_FLAVOR_OPTIONS: CanonicalOption[] = [
  { value: 'marlin', labelKey: 'printerProfile.options.gcodeFlavor.marlin' },
  { value: 'klipper', labelKey: 'printerProfile.options.gcodeFlavor.klipper' },
  { value: 'reprapfirmware', labelKey: 'printerProfile.options.gcodeFlavor.reprapfirmware' },
  { value: 'marlin2', labelKey: 'printerProfile.options.gcodeFlavor.marlin2' },
];

const ORCA_PRINTER_TECHNOLOGY_OPTIONS: CanonicalOption[] = [
  { value: 'FFF', labelKey: 'printerProfile.options.printerTechnology.fff' },
  { value: 'SLA', labelKey: 'printerProfile.options.printerTechnology.sla' },
];

const ORCA_DEFAULT_BED_TYPE_OPTIONS: CanonicalOption[] = [
  { value: 'Cool Plate', labelKey: 'printerProfile.options.defaultBedType.coolPlate' },
  { value: 'Engineering Plate', labelKey: 'printerProfile.options.defaultBedType.engineeringPlate' },
  { value: 'High Temp Plate', labelKey: 'printerProfile.options.defaultBedType.highTempPlate' },
  { value: 'Textured PEI Plate', labelKey: 'printerProfile.options.defaultBedType.texturedPeiPlate' },
  { value: 'Textured Cool Plate', labelKey: 'printerProfile.options.defaultBedType.texturedCoolPlate' },
  { value: 'SuperTack Plate', labelKey: 'printerProfile.options.defaultBedType.superTackPlate' },
];

const ORCA_POWER_LOSS_RECOVERY_OPTIONS: CanonicalOption[] = [
  { value: 'printer_configuration', labelKey: 'printerProfile.options.powerLossRecovery.printerConfiguration' },
  { value: 'enable', labelKey: 'printerProfile.options.powerLossRecovery.enable' },
  { value: 'disable', labelKey: 'printerProfile.options.powerLossRecovery.disable' },
];

const ORCA_BED_TEMPERATURE_FORMULA_OPTIONS: CanonicalOption[] = [
  { value: 'by_first_filament', labelKey: 'printerProfile.options.bedTemperatureFormula.byFirstFilament' },
  { value: 'by_highest_temp', labelKey: 'printerProfile.options.bedTemperatureFormula.byHighestTemp' },
];

const ORCA_NOZZLE_VOLUME_TYPE_OPTIONS: CanonicalOption[] = [
  { value: 'Standard', labelKey: 'printerProfile.options.nozzleVolumeType.standard' },
  { value: 'High Flow', labelKey: 'printerProfile.options.nozzleVolumeType.highFlow' },
];

const ORCA_EXTRUDER_TYPE_OPTIONS: CanonicalOption[] = [
  { value: 'Direct Drive', labelKey: 'printerProfile.options.extruderType.directDrive' },
  { value: 'Bowden', labelKey: 'printerProfile.options.extruderType.bowden' },
];

const ORCA_NOZZLE_TYPE_OPTIONS: CanonicalOption[] = [
  { value: 'undefine', labelKey: 'printerProfile.options.nozzleType.undefine' },
  { value: 'brass', labelKey: 'printerProfile.options.nozzleType.brass' },
  { value: 'hardened_steel', labelKey: 'printerProfile.options.nozzleType.hardenedSteel' },
  { value: 'stainless_steel', labelKey: 'printerProfile.options.nozzleType.stainlessSteel' },
  { value: 'tungsten_carbide', labelKey: 'printerProfile.options.nozzleType.tungstenCarbide' },
  { value: 'E3D', labelKey: 'printerProfile.options.nozzleType.e3d' },
];

const ORCA_Z_HOP_TYPE_OPTIONS: CanonicalOption[] = [
  { value: 'Auto Lift', labelKey: 'printerProfile.options.zHopType.autoLift' },
  { value: 'Normal Lift', labelKey: 'printerProfile.options.zHopType.normalLift' },
  { value: 'Slope Lift', labelKey: 'printerProfile.options.zHopType.slopeLift' },
  { value: 'Spiral Lift', labelKey: 'printerProfile.options.zHopType.spiralLift' },
];

const ORCA_RETRACT_LIFT_ENFORCE_OPTIONS: CanonicalOption[] = [
  { value: 'All Surfaces', labelKey: 'printerProfile.options.retractLiftEnforce.allSurfaces' },
  { value: 'Top Only', labelKey: 'printerProfile.options.retractLiftEnforce.topOnly' },
  { value: 'Bottom Only', labelKey: 'printerProfile.options.retractLiftEnforce.bottomOnly' },
  { value: 'Top and Bottom', labelKey: 'printerProfile.options.retractLiftEnforce.topAndBottom' },
];

const ORCA_LONG_RETRACTION_LEVEL_OPTIONS: CanonicalOption[] = [
  { value: '0', labelKey: 'printerProfile.options.longRetractionLevel.disabled' },
  { value: '1', labelKey: 'printerProfile.options.longRetractionLevel.machine' },
  { value: '2', labelKey: 'printerProfile.options.longRetractionLevel.filament' },
];

const ORCA_PRINTER_GCODE_FIELDS = [
  { key: 'file_start_gcode', labelKey: 'printerProfile.gcode.fileStart' },
  { key: 'machine_start_gcode', labelKey: 'printerProfile.gcode.machineStart' },
  { key: 'machine_end_gcode', labelKey: 'printerProfile.gcode.machineEnd' },
  { key: 'printing_by_object_gcode', labelKey: 'printerProfile.gcode.printingByObject' },
  { key: 'before_layer_change_gcode', labelKey: 'printerProfile.gcode.beforeLayerChange' },
  { key: 'layer_change_gcode', labelKey: 'printerProfile.gcode.layerChange' },
  { key: 'time_lapse_gcode', labelKey: 'printerProfile.gcode.timelapse' },
  { key: 'wrapping_detection_gcode', labelKey: 'printerProfile.gcode.clumpingDetection' },
  { key: 'change_filament_gcode', labelKey: 'printerProfile.gcode.changeFilament' },
  { key: 'change_extrusion_role_gcode', labelKey: 'printerProfile.gcode.changeExtrusionRole' },
  { key: 'machine_pause_gcode', labelKey: 'printerProfile.gcode.pause' },
  { key: 'template_custom_gcode', labelKey: 'printerProfile.gcode.templateCustom' },
] as const;

const LEGACY_COMPATIBILITY_GCODE_FIELDS = [
  { key: 'machine_resume_gcode', labelKey: 'printerProfile.gcode.machineResume' },
  { key: 'machine_cancel_gcode', labelKey: 'printerProfile.gcode.machineCancel' },
  { key: 'machine_custom_gcode', labelKey: 'printerProfile.gcode.machineCustom' },
  { key: 'toolchange_gcode', labelKey: 'printerProfile.gcode.toolchange' },
] as const;

const parsePrintableAreaPoint = (rawPoint: string): { x: number; y: number } | null => {
  const trimmed = rawPoint.trim();
  if (!trimmed) {
    return null;
  }

  const [xRaw, yRaw] = trimmed.split('x');
  if (xRaw === undefined || yRaw === undefined) {
    return null;
  }

  const x = Number(xRaw);
  const y = Number(yRaw);
  if (!Number.isFinite(x) || !Number.isFinite(y)) {
    return null;
  }

  return { x, y };
};

const parsePrintableAreaPolygon = (rawValue: string): string[] | null => {
  const normalized = rawValue
    .split(',')
    .map((item) => item.trim())
    .filter((item) => item.length > 0);

  if (normalized.length === 0) {
    return [];
  }

  return normalized.every((item) => parsePrintableAreaPoint(item) !== null) ? normalized : null;
};

const getPrintableAreaDimensions = (area: unknown): { x: string; y: string } => {
  if (!area) {
    return { x: '', y: '' };
  }

  if (Array.isArray(area)) {
    const points = area
      .map((point) => parsePrintableAreaPoint(String(point)))
      .filter((point): point is { x: number; y: number } => point !== null);
    if (points.length === 0) {
      return { x: '', y: '' };
    }

    const xMin = Math.min(...points.map((point) => point.x));
    const xMax = Math.max(...points.map((point) => point.x));
    const yMin = Math.min(...points.map((point) => point.y));
    const yMax = Math.max(...points.map((point) => point.y));

    return {
      x: String(xMax - xMin),
      y: String(yMax - yMin),
    };
  }

  if (typeof area === 'object') {
    const areaRecord = area as Record<string, unknown>;
    if (areaRecord.x !== undefined || areaRecord.y !== undefined) {
      return {
        x: areaRecord.x !== undefined ? String(areaRecord.x) : '',
        y: areaRecord.y !== undefined ? String(areaRecord.y) : '',
      };
    }
    if (
      typeof areaRecord.x_min === 'number' &&
      typeof areaRecord.x_max === 'number' &&
      typeof areaRecord.y_min === 'number' &&
      typeof areaRecord.y_max === 'number'
    ) {
      return {
        x: String(areaRecord.x_max - areaRecord.x_min),
        y: String(areaRecord.y_max - areaRecord.y_min),
      };
    }
  }

  return { x: '', y: '' };
};

const getPrintableAreaPolygonString = (area: unknown): string => {
  if (!Array.isArray(area)) {
    return '';
  }

  return area
    .map((item) => String(item).trim())
    .filter((item) => item.length > 0)
    .join(', ');
};

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
  const { t } = useTranslation();
  
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
  const [printableAreaPolygon, setPrintableAreaPolygon] = useState('');
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

  const buildTranslatedOptions = (options: CanonicalOption[], currentValue?: string | null) => {
    const translated = options.map((option) => ({
      value: option.value,
      label: t(option.labelKey),
    }));

    if (currentValue && !translated.some((option) => option.value === currentValue)) {
      translated.unshift({
        value: currentValue,
        label: `${currentValue} (${t('printerProfile.options.legacyValue')})`,
      });
    }

    return translated;
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

  const getMetadataLineListString = (key: string): string => {
    const value = getMetadataValue(key);
    if (Array.isArray(value)) {
      return value.map((item) => String(item)).join('\n');
    }
    if (value === undefined || value === null) {
      return '';
    }
    return String(value);
  };

  const getMetadataStringWithAliases = (key: string, aliases: string[] = []): string => {
    const primaryValue = getMetadataString(key);
    if (primaryValue) {
      return primaryValue;
    }

    for (const alias of aliases) {
      const aliasValue = getMetadataString(alias);
      if (aliasValue) {
        return aliasValue;
      }
    }

    return '';
  };

  const ARRAY_FIELDS_WITH_EMPTY_VALID = [
    'bed_exclude_area',
    'bed_shape',
    'bed_custom_rectangle',
    'extruder_type',
    'printer_extruder_id',
    'printer_extruder_variant',
    'physical_extruder_map',
    'extruder_variant_list',
    'extruder_printable_area',
    'default_nozzle_volume_type',
    'nozzle_type',
    'extruder_ams_count',
    'z_hop_types',
    'retract_lift_enforce',
    'retract_length_toolchange',
    'long_retractions_when_cut',
  ];

  const updateMetadataValue = (key: string, value: any, aliasesToDelete: string[] = []) => {
    let base: Record<string, any> = {};
    try {
      base = extraMetadata.trim() ? JSON.parse(extraMetadata) : {};
    } catch (error) {
      base = {};
    }

    aliasesToDelete.forEach((alias) => {
      delete base[alias];
    });

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

  const handleMetadataListChange = (key: string, rawValue: string, aliasesToDelete: string[] = []) => {
    const normalized = rawValue
      .split(',')
      .map((item) => item.trim())
      .filter((item) => item.length > 0);

    const isSpecialArrayField = ARRAY_FIELDS_WITH_EMPTY_VALID.includes(key);

    if (normalized.length > 0) {
      updateMetadataValue(key, normalized, aliasesToDelete);
    } else if (isSpecialArrayField) {
      updateMetadataValue(key, [], aliasesToDelete);
    } else {
      updateMetadataValue(key, undefined, aliasesToDelete);
    }
  };

  const handleMetadataLineListChange = (key: string, rawValue: string, aliasesToDelete: string[] = []) => {
    const normalized = rawValue
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter((item) => item.length > 0);

    const isSpecialArrayField = ARRAY_FIELDS_WITH_EMPTY_VALID.includes(key);

    if (normalized.length > 0) {
      updateMetadataValue(key, normalized, aliasesToDelete);
    } else if (isSpecialArrayField) {
      updateMetadataValue(key, [], aliasesToDelete);
    } else {
      updateMetadataValue(key, undefined, aliasesToDelete);
    }
  };

  const handleMetadataStringChange = (key: string, rawValue: string, aliasesToDelete: string[] = []) => {
    updateMetadataValue(key, rawValue, aliasesToDelete);
  };

  const handlePrinterVariantChange = (rawValue: string) => {
    const currentValue = getMetadataValue('printer_variant');
    if (Array.isArray(currentValue)) {
      const normalized = rawValue
        .split(',')
        .map((item) => item.trim())
        .filter((item) => item.length > 0);
      updateMetadataValue('printer_variant', normalized.length > 0 ? normalized : []);
      return;
    }

    handleMetadataStringChange('printer_variant', rawValue);
  };

  const handleMetadataBooleanChange = (key: string, checked: boolean, aliasesToDelete: string[] = []) => {
    updateMetadataValue(key, checked ? '1' : '0', aliasesToDelete);
  };

  const handleFormatJson = () => {
    if (!extraMetadata.trim()) return;
    try {
      const formatted = JSON.stringify(JSON.parse(extraMetadata), null, 2);
      setExtraMetadata(formatted);
      setJsonError(null);
    } catch (error) {
      setJsonError(t('printerProfile.jsonFormatError'));
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
        const dimensions = getPrintableAreaDimensions(profile.printable_area);
        setPrintableAreaX(dimensions.x);
        setPrintableAreaY(dimensions.y);
        setPrintableAreaPolygon(getPrintableAreaPolygonString(profile.printable_area));
        setPrintableHeightMm(profile.printable_height_mm?.toString() || '');
        setNozzleDiameters(profile.nozzle_diameters?.map(d => d.toString()) || []);
        setNotes(profile.notes || '');
        setExtraMetadata(profile.extra_metadata ? JSON.stringify(profile.extra_metadata, null, 2) : '');
        setDefaultMaterials([]); // TODO: если будет поле в модели
        setImageUrl(''); // TODO: если будет поле в модели
      } else if (baseProfile) {
        // Клонирование
        setName(`${baseProfile.name} (${t('printerProfile.copyLabel')})`);
        setSlug(`${baseProfile.slug}-copy`);
        setDescription(baseProfile.description || '');
        setPrinterId(baseProfile.printer_id);
        setPrinterSearch('');
        setVendor(baseProfile.vendor || '');
        const dimensions = getPrintableAreaDimensions(baseProfile.printable_area);
        setPrintableAreaX(dimensions.x);
        setPrintableAreaY(dimensions.y);
        setPrintableAreaPolygon(getPrintableAreaPolygonString(baseProfile.printable_area));
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
        setPrintableAreaPolygon('');
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
      console.error('Error saving printer profile:', error);
      alert(translateApiError(t, error?.response?.data?.detail, t('printerProfile.saveError')));
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
      alert(t('printerProfile.nameRequired'));
      return;
    }
    
    if (!slug.trim()) {
      alert(t('printerProfile.slugRequired'));
      return;
    }

    let extraMetadataObj: Record<string, any> = {};
    if (extraMetadata.trim()) {
      try {
        const parsedExtraMetadata = JSON.parse(extraMetadata) as Record<string, any>;
        if (parsedExtraMetadata.machine_switch_extruder_time && !parsedExtraMetadata.machine_tool_change_time) {
          parsedExtraMetadata.machine_tool_change_time = parsedExtraMetadata.machine_switch_extruder_time;
        }
        delete parsedExtraMetadata.machine_switch_extruder_time;
        extraMetadataObj = parsedExtraMetadata;
        setJsonError(null);
      } catch (error) {
        console.error('Invalid extra metadata JSON', error);
        setJsonError(t('printerProfile.jsonInvalid'));
        return;
      }
    } else {
      setJsonError(null);
    }

    // Извлекаем start_gcode и end_gcode из extra_metadata для обратной совместимости
    const startGcode = extraMetadataObj.machine_start_gcode || '';
    const endGcode = extraMetadataObj.machine_end_gcode || '';

    const printableAreaPolygonValues = parsePrintableAreaPolygon(printableAreaPolygon);
    if (printableAreaPolygon.trim() && printableAreaPolygonValues === null) {
      alert(t('printerProfile.printAreaPolygonInvalid'));
      return;
    }

    const printableArea = printableAreaPolygonValues && printableAreaPolygonValues.length > 0
      ? printableAreaPolygonValues
      : (printableAreaX && printableAreaY) ? {
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
      extra_metadata: Object.keys(extraMetadataObj).length > 0 ? extraMetadataObj : null,
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

  const handleAddNozzleDiameter = () => {
    const trimmed = newNozzleDiameter.trim();
    if (!trimmed) return;
    const value = parseFloat(trimmed);
    if (isNaN(value) || value <= 0) {
      alert(t('printerProfile.nozzleDiameterInvalid'));
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

    const selectedPrinterStructure = getMetadataString('printer_structure') || null;
    const selectedGcodeFlavor = getMetadataString('gcode_flavor') || null;
    const selectedPrinterTechnology = getMetadataString('printer_technology') || null;
    const selectedDefaultBedType = getMetadataString('default_bed_type') || null;
    const selectedPowerLossRecovery = getMetadataString('enable_power_loss_recovery') || null;
    const firmwareFlagOptions: Array<{ key: string; labelKey: string; descriptionKey?: string }> = [
      { key: 'use_relative_e_distances', labelKey: 'printerProfile.flags.relativeE', descriptionKey: 'printerProfile.flags.relativeEDesc' },
      { key: 'use_firmware_retraction', labelKey: 'printerProfile.flags.firmwareRetraction', descriptionKey: 'printerProfile.flags.firmwareRetractionDesc' },
      { key: 'pellet_modded_printer', labelKey: 'printerProfile.flags.pelletMod', descriptionKey: 'printerProfile.flags.pelletModDesc' },
      { key: 'support_multi_bed_types', labelKey: 'printerProfile.flags.multiBedTypes', descriptionKey: 'printerProfile.flags.multiBedTypesDesc' },
      { key: 'support_air_filtration', labelKey: 'printerProfile.flags.airFiltration' },
      { key: 'support_chamber_temp_control', labelKey: 'printerProfile.flags.chamberTemp' },
      { key: 'auxiliary_fan', labelKey: 'printerProfile.flags.auxiliaryFan' },
      { key: 'scan_first_layer', labelKey: 'printerProfile.flags.scanFirstLayer' },
      { key: 'disable_m73', labelKey: 'printerProfile.flags.disableM73' },
      { key: 'bbl_use_printhost', labelKey: 'printerProfile.flags.usePrinthost' },
    ];
    const coolingFanFields: Array<{ key: string; labelKey: string; placeholder?: string; unit?: string }> = [
      { key: 'fan_speedup_time', labelKey: 'printerProfile.cooling.speedupTime', placeholder: '2', unit: t('printerProfile.units.sec') },
      { key: 'fan_kickstart', labelKey: 'printerProfile.cooling.kickstart', placeholder: '0.25', unit: t('printerProfile.units.sec') },
    ];
    const extruderClearanceFields: Array<{ key: string; labelKey: string; placeholder?: string; unit?: string }> = [
      { key: 'extruder_clearance_radius', labelKey: 'printerProfile.extruderClearance.radius', placeholder: '65', unit: t('printerProfile.units.mm') },
      { key: 'extruder_clearance_height_to_rod', labelKey: 'printerProfile.extruderClearance.heightToRod', placeholder: '36', unit: t('printerProfile.units.mm') },
      { key: 'extruder_clearance_height_to_lid', labelKey: 'printerProfile.extruderClearance.heightToLid', placeholder: '140', unit: t('printerProfile.units.mm') },
    ];
    const adaptiveMeshFields: Array<{ key: string; labelKey: string; placeholder?: string; isList?: boolean }> = [
      { key: 'bed_mesh_min', labelKey: 'printerProfile.mesh.min', placeholder: '32,5' },
      { key: 'bed_mesh_max', labelKey: 'printerProfile.mesh.max', placeholder: '210,205' },
      { key: 'bed_mesh_probe_distance', labelKey: 'printerProfile.mesh.probeDistance', placeholder: '50,50' },
      { key: 'adaptive_bed_mesh_margin', labelKey: 'printerProfile.mesh.margin', placeholder: '5' },
    ];
    const bedGeometryFields: Array<{ key: string; labelKey: string; isList?: boolean; placeholder?: string; unit?: string }> = [
      { key: 'bed_shape', labelKey: 'printerProfile.bed.shape', isList: true, placeholder: '0x0, 256x0, 256x256, 0x256' },
      { key: 'best_object_pos', labelKey: 'printerProfile.bed.bestObjectPos', placeholder: '0.5,0.5' },
      { key: 'bed_exclude_area', labelKey: 'printerProfile.bed.excludeArea', isList: true, placeholder: '90x90, 166x166' },
      { key: 'bed_custom_rectangle', labelKey: 'printerProfile.bed.customRectangle', isList: true, placeholder: '0x0, 256x0, 256x256, 0x256' },
      { key: 'origin_z', labelKey: 'printerProfile.bed.originZ', placeholder: '0' },
      { key: 'z_offset', labelKey: 'printerProfile.bed.zOffset', placeholder: '0', unit: t('printerProfile.units.mm') },
      { key: 'preferred_orientation', labelKey: 'printerProfile.bed.preferredOrientation', placeholder: '0', unit: t('printerProfile.units.deg') },
    ];
    const thumbnailsFields: Array<{ key: string; labelKey: string; placeholder?: string }> = [
      { key: 'thumbnails', labelKey: 'printerProfile.thumbnails.sizes', placeholder: '48x48/PNG,300x300/PNG' },
      { key: 'thumbnails_format', labelKey: 'printerProfile.thumbnails.format', placeholder: 'PNG' },
    ];

    return (
      <div className="space-y-6">
        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            {t('printerProfile.name')} <span className="text-red-400">*</span>
            {selectedPrinter && nozzleDiameters.length > 0 && (
              <span className="text-xs text-gray-400 ml-2">
                ({t('printerProfile.nameFormatHint', { name: selectedPrinter.name, nozzle: nozzleDiameters[0] })})
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
              : t('printerProfile.namePlaceholder')}
            required
          />
          {selectedPrinter && nozzleDiameters.length > 0 && !name.match(/nozzle$/i) && name && (
            <p className="text-xs text-amber-400 mt-1">
              {t('printerProfile.nameFormatWarning', { name: selectedPrinter.name, nozzle: nozzleDiameters[0] })}
            </p>
          )}
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            {t('printerProfile.slug')} <span className="text-red-400">*</span>
          </label>
          <input
            type="text"
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 font-mono text-sm"
            placeholder="ender-3-pro-standard"
            required
          />
          <p className="text-xs text-gray-500 mt-1">{t('printerProfile.slugHint')}</p>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            {t('printerProfile.printer')}
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
              placeholder={t('printerProfile.printerPlaceholder')}
              filterable
              filterValue={printerSearch}
              onFilterChange={setPrinterSearch}
              emptyMessage={t('printerProfile.printerNotFound')}
            />
            {printers.length === 0 && printerSearch && (
              <p className="text-xs text-gray-400">
                {t('printerProfile.noPrintersHint')}
              </p>
            )}
            {onRequestPrinter && (
              <p className="text-xs text-gray-400">
                {t('printerProfile.printerMissing')}{' '}
                <button
                  type="button"
                  onClick={() => {
                    onRequestPrinter();
                  }}
                  className="text-purple-400 hover:text-purple-300 underline"
                >
                  {t('printerProfile.requestPrinter')}
                </button>
              </p>
            )}
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            {t('printerProfile.vendor')}
          </label>
          <input
            type="text"
            value={vendor}
            onChange={(e) => setVendor(e.target.value)}
            className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
            placeholder={t('printerProfile.vendorPlaceholder')}
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-3">
            {t('printerProfile.printArea')}
          </label>
          <div className="grid grid-cols-3 gap-4">
            <div>
              <label className="block text-xs text-gray-400 mb-1">{t('printerProfile.widthX')}</label>
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
              <label className="block text-xs text-gray-400 mb-1">{t('printerProfile.depthY')}</label>
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
              <label className="block text-xs text-gray-400 mb-1">{t('printerProfile.heightZ')}</label>
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
          <div className="mt-4">
            <label className="block text-xs text-gray-400 mb-1">{t('printerProfile.printAreaPolygon')}</label>
            <textarea
              value={printableAreaPolygon}
              onChange={(e) => setPrintableAreaPolygon(e.target.value)}
              rows={3}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 font-mono text-sm resize-none"
              placeholder="0x0, 256x0, 256x256, 0x256"
            />
            <p className="text-xs text-gray-500 mt-1">{t('printerProfile.printAreaPolygonHint')}</p>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            {t('printerProfile.nozzleDiameters')}
          </label>
          <div className="space-y-3">
            {nozzleDiameters.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {nozzleDiameters.map((diameter) => (
                  <span
                    key={diameter}
                    className="inline-flex items-center gap-1 px-3 py-1 rounded-full bg-purple-500/20 text-purple-200 text-sm"
                  >
                    {diameter} {t('printerProfile.units.mm')}
                    <button
                      type="button"
                      onClick={() => handleRemoveNozzleDiameter(diameter)}
                      className="hover:text-white transition"
                      aria-label={t('printerProfile.removeDiameter')}
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
                {t('printerProfile.add')}
              </button>
            </div>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            {t('printerProfile.defaultMaterials')}
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
                  aria-label={t('printerProfile.removeMaterial')}
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
              {t('printerProfile.add')}
            </button>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-300 mb-2">
            {t('printerProfile.imageUrl')}
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
            {t('printerProfile.jsonParseError')}
          </div>
        ) : (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerProfile.printerStructure')}</label>
                <CustomSelect
                  value={selectedPrinterStructure}
                  onChange={(value) => handleMetadataStringChange('printer_structure', (value as string) || '')}
                  options={buildTranslatedOptions(ORCA_PRINTER_STRUCTURE_OPTIONS, selectedPrinterStructure)}
                  placeholder={t('printerProfile.selectStructure')}
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerProfile.gcodeFlavor')}</label>
                <CustomSelect
                  value={selectedGcodeFlavor}
                  onChange={(value) => handleMetadataStringChange('gcode_flavor', (value as string) || '')}
                  options={buildTranslatedOptions(ORCA_GCODE_FLAVOR_OPTIONS, selectedGcodeFlavor)}
                  placeholder={t('printerProfile.selectFlavor')}
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerProfile.printTechnology')}</label>
                <CustomSelect
                  value={selectedPrinterTechnology}
                  onChange={(value) => handleMetadataStringChange('printer_technology', (value as string) || '')}
                  options={buildTranslatedOptions(ORCA_PRINTER_TECHNOLOGY_OPTIONS, selectedPrinterTechnology)}
                  placeholder={t('printerProfile.selectTechnology')}
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerProfile.defaultBedType')}</label>
                <CustomSelect
                  value={selectedDefaultBedType}
                  onChange={(value) => handleMetadataStringChange('default_bed_type', (value as string) || '')}
                  options={buildTranslatedOptions(ORCA_DEFAULT_BED_TYPE_OPTIONS, selectedDefaultBedType)}
                  placeholder={t('printerProfile.selectBedType')}
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerProfile.powerLossRecovery')}</label>
                <CustomSelect
                  value={selectedPowerLossRecovery}
                  onChange={(value) => handleMetadataStringChange('enable_power_loss_recovery', (value as string) || '')}
                  options={buildTranslatedOptions(ORCA_POWER_LOSS_RECOVERY_OPTIONS, selectedPowerLossRecovery)}
                  placeholder={t('printerProfile.selectPowerLossRecovery')}
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerProfile.hotend')}</label>
                <input
                  type="text"
                  value={getMetadataString('hotend_model')}
                  onChange={(e) => handleMetadataStringChange('hotend_model', e.target.value)}
                  placeholder="Phaetus Rapido..."
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerProfile.nozzleHrc')}</label>
                <input
                  type="text"
                  value={getMetadataString('nozzle_hrc')}
                  onChange={(e) => handleMetadataStringChange('nozzle_hrc', e.target.value)}
                  placeholder="0"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerProfile.timeCost')}</label>
                <input
                  type="text"
                  value={getMetadataString('time_cost')}
                  onChange={(e) => handleMetadataStringChange('time_cost', e.target.value)}
                  placeholder="0.0"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerProfile.defaultFilamentProfile')}</label>
                <input
                  type="text"
                  value={getMetadataListString('default_filament_profile')}
                  onChange={(e) => handleMetadataListChange('default_filament_profile', e.target.value)}
                  placeholder="Generic PLA"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                />
              </div>
              <div>
                <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerProfile.printerVariant')}</label>
                <input
                  type="text"
                  value={getMetadataString('printer_variant')}
                  onChange={(e) => handlePrinterVariantChange(e.target.value)}
                  placeholder="0.4"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                />
              </div>
            </div>

            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.sections.bedConstraints')}</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {bedGeometryFields.map((field) => (
                  <div key={field.key}>
                    <label className="block text-gray-300 mb-2 text-sm font-medium">{t(field.labelKey)}</label>
                    <div className="relative">
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
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.sections.flagsAndModes')}</h5>
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
                        {t(option.labelKey)}
                      </label>
                      {option.descriptionKey && <p className="text-xs text-gray-500">{t(option.descriptionKey)}</p>}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.sections.coolingFan')}</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {coolingFanFields.map((field) => (
                  <div key={field.key} className="space-y-2">
                    <label className="block min-h-[38px] text-gray-300 text-sm font-medium leading-tight flex items-end">{t(field.labelKey)}</label>
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
              <div className="mt-4 flex items-start gap-3">
                <input
                  type="checkbox"
                  id="fan_speedup_overhangs"
                  checked={getMetadataBoolean('fan_speedup_overhangs')}
                  onChange={(e) => handleMetadataBooleanChange('fan_speedup_overhangs', e.target.checked)}
                  className="w-4 h-4 mt-1 rounded border-white/30 bg-white/10"
                />
                <div>
                  <label htmlFor="fan_speedup_overhangs" className="text-gray-300 text-sm font-medium">
                    {t('printerProfile.cooling.speedupOverhangs')}
                  </label>
                  <p className="text-xs text-gray-500">{t('printerProfile.cooling.speedupOverhangsDesc')}</p>
                </div>
              </div>
            </div>

            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.sections.extruderClearance')}</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {extruderClearanceFields.map((field) => (
                  <div key={field.key} className="space-y-2">
                    <label className="block min-h-[38px] text-gray-300 text-sm font-medium leading-tight flex items-end">{t(field.labelKey)}</label>
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
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.sections.adaptiveBedMesh')}</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {adaptiveMeshFields.map((field) => (
                  <div key={field.key}>
                    <label className="block text-gray-300 mb-2 text-sm font-medium">{t(field.labelKey)}</label>
                    <input
                      type="text"
                      value={field.isList ? getMetadataListString(field.key) : getMetadataString(field.key)}
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
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.sections.thumbnails')}</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {thumbnailsFields.map((field) => (
                  <div key={field.key}>
                    <label className="block text-gray-300 mb-2 text-sm font-medium">{t(field.labelKey)}</label>
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
            {t('printerProfile.extraMetadata')}
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
              {t('printerProfile.formatJson')}
            </button>
          </div>
          {jsonError && <p className="text-red-400 text-xs mt-1">{jsonError}</p>}
          <p className="text-xs text-gray-500 mt-1">
            {t('printerProfile.extraMetadataHint')}
          </p>
        </div>
      </div>
    );
  };

  const renderMotionTab = () => {
    const motionFlagOptions: Array<{ key: string; labelKey: string; descriptionKey?: string }> = [
      {
        key: 'emit_machine_limits_to_gcode',
        labelKey: 'printerProfile.motion.emitMachineLimits',
        descriptionKey: 'printerProfile.motion.emitMachineLimitsDesc',
      },
    ];
    const resonanceSpeedFields: Array<{ key: string; labelKey: string; placeholder: string }> = [
      { key: 'min_resonance_avoidance_speed', labelKey: 'printerProfile.motion.resonanceSpeedMin', placeholder: '70' },
      { key: 'max_resonance_avoidance_speed', labelKey: 'printerProfile.motion.resonanceSpeedMax', placeholder: '120' },
    ];

    return (
      <div className="space-y-6">
        {metadataInvalid ? (
          <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            {t('printerProfile.jsonErrorMotion')}
          </div>
        ) : (
          <div className="space-y-6">
            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.motion.advanced')}</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {motionFlagOptions.map((option) => (
                  <div key={option.key} className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      id={`motion-flag-${option.key}`}
                      checked={getMetadataBoolean(option.key)}
                      onChange={(e) => handleMetadataBooleanChange(option.key, e.target.checked)}
                      className="w-4 h-4 mt-1 rounded border-white/30 bg-white/10"
                    />
                    <div>
                      <label htmlFor={`motion-flag-${option.key}`} className="text-gray-300 text-sm font-medium">
                        {t(option.labelKey)}
                      </label>
                      {option.descriptionKey && <p className="text-xs text-gray-500">{t(option.descriptionKey)}</p>}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.motion.resonanceAvoidanceTitle')}</h5>
              <div className="space-y-4">
                <div className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    id="resonance_avoidance"
                    checked={getMetadataBoolean('resonance_avoidance')}
                    onChange={(e) => handleMetadataBooleanChange('resonance_avoidance', e.target.checked)}
                    className="w-4 h-4 mt-1 rounded border-white/30 bg-white/10"
                  />
                  <div>
                    <label htmlFor="resonance_avoidance" className="text-gray-300 text-sm font-medium">
                      {t('printerProfile.motion.resonanceAvoidance')}
                    </label>
                    <p className="text-xs text-gray-500">{t('printerProfile.motion.resonanceAvoidanceDesc')}</p>
                  </div>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {resonanceSpeedFields.map((field) => (
                    <div key={field.key}>
                      <label className="block text-gray-300 mb-2 text-sm font-medium">{t(field.labelKey)}</label>
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

            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.motion.maxSpeed')}</h5>
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
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.motion.acceleration')}</h5>
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
                  { key: 'machine_max_acceleration_extruding', label: t('printerProfile.motion.extruding') },
                  { key: 'machine_max_acceleration_retracting', label: t('printerProfile.motion.retracting') },
                  { key: 'machine_max_acceleration_travel', label: t('printerProfile.motion.travel') },
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
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('adminPrinters.speed.jerk')}</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerProfile.motion.junctionDeviation')}</label>
                  <input
                    type="text"
                    value={getMetadataListString('machine_max_junction_deviation')}
                    onChange={(e) => handleMetadataListChange('machine_max_junction_deviation', e.target.value)}
                    placeholder="0.01"
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                  />
                </div>
              </div>
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
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.motion.minSpeeds')}</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerProfile.motion.minExtrudingRate')}</label>
                  <input
                    type="text"
                    value={getMetadataListString('machine_min_extruding_rate')}
                    onChange={(e) => handleMetadataListChange('machine_min_extruding_rate', e.target.value)}
                    placeholder="0"
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerProfile.motion.minTravelRate')}</label>
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
  };

  const renderExtrudersTab = () => {
    type MetadataFieldMode = 'string' | 'list' | 'lineList';
    type MetadataFieldConfig = {
      key: string;
      labelKey: string;
      placeholder?: string;
      mode?: MetadataFieldMode;
      rows?: number;
      unit?: string;
      helpKey?: string;
      helpText?: string;
    };

    const extruderTypeHelp = buildTranslatedOptions(ORCA_EXTRUDER_TYPE_OPTIONS)
      .map((option) => option.label)
      .join(', ');
    const nozzleVolumeTypeHelp = buildTranslatedOptions(ORCA_NOZZLE_VOLUME_TYPE_OPTIONS)
      .map((option) => option.label)
      .join(', ');
    const nozzleTypeHelp = buildTranslatedOptions(ORCA_NOZZLE_TYPE_OPTIONS)
      .map((option) => option.label)
      .join(', ');
    const zHopTypeHelp = buildTranslatedOptions(ORCA_Z_HOP_TYPE_OPTIONS)
      .map((option) => option.label)
      .join(', ');
    const retractLiftEnforceHelp = buildTranslatedOptions(ORCA_RETRACT_LIFT_ENFORCE_OPTIONS)
      .map((option) => option.label)
      .join(', ');
    const longRetractionLevel = getMetadataString('enable_long_retraction_when_cut') || '0';

    const renderMetadataField = (field: MetadataFieldConfig) => {
      const mode = field.mode ?? 'string';
      const value =
        mode === 'list'
          ? getMetadataListString(field.key)
          : mode === 'lineList'
            ? getMetadataLineListString(field.key)
            : getMetadataString(field.key);
      const handleChange = (rawValue: string) => {
        if (mode === 'list') {
          handleMetadataListChange(field.key, rawValue);
          return;
        }
        if (mode === 'lineList') {
          handleMetadataLineListChange(field.key, rawValue);
          return;
        }
        handleMetadataStringChange(field.key, rawValue);
      };
      const helpTexts = [
        field.helpKey ? t(field.helpKey) : null,
        field.helpText ? t('printerProfile.help.canonicalValues', { values: field.helpText }) : null,
        mode === 'lineList' ? t('printerProfile.help.oneValuePerLine') : null,
      ].filter(Boolean) as string[];

      return (
        <div key={field.key} className="space-y-2">
          <label className="block text-gray-300 text-sm font-medium">{t(field.labelKey)}</label>
          {field.rows ? (
            <textarea
              value={value}
              onChange={(e) => handleChange(e.target.value)}
              rows={field.rows}
              placeholder={field.placeholder}
              className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 font-mono text-sm resize-none"
            />
          ) : (
            <div className="relative">
              <input
                type="text"
                value={value}
                onChange={(e) => handleChange(e.target.value)}
                placeholder={field.placeholder}
                className={`w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 ${field.unit ? 'pr-16' : ''}`}
              />
              {field.unit && (
                <span className="absolute inset-y-0 right-4 flex items-center text-xs text-gray-400 pointer-events-none">
                  {field.unit}
                </span>
              )}
            </div>
          )}
          {helpTexts.length > 0 && (
            <div className="space-y-1">
              {helpTexts.map((helpText, index) => (
                <p key={`${field.key}-${index}`} className="text-xs text-gray-500">
                  {helpText}
                </p>
              ))}
            </div>
          )}
        </div>
      );
    };

    const hardwareFields: MetadataFieldConfig[] = [
      {
        key: 'extruder_type',
        labelKey: 'printerProfile.extruder.type',
        mode: 'lineList',
        rows: 2,
        placeholder: 'Direct Drive',
        helpText: extruderTypeHelp,
      },
      {
        key: 'default_nozzle_volume_type',
        labelKey: 'printerProfile.extruder.defaultNozzleVolumeType',
        mode: 'lineList',
        rows: 2,
        placeholder: 'Standard',
        helpText: nozzleVolumeTypeHelp,
      },
      {
        key: 'extruder_variant_list',
        labelKey: 'printerProfile.extruder.variants',
        mode: 'lineList',
        rows: 3,
        placeholder: 'Direct Drive Standard,Direct Drive High Flow',
        helpKey: 'printerProfile.extruder.variantsHint',
      },
      {
        key: 'extruder_ams_count',
        labelKey: 'printerProfile.extruder.amsCount',
        mode: 'lineList',
        rows: 3,
        placeholder: '0#1|1#1',
        helpKey: 'printerProfile.extruder.amsCountHint',
      },
      {
        key: 'printer_extruder_id',
        labelKey: 'printerProfile.extruder.printerId',
        mode: 'list',
        placeholder: '1, 2',
      },
      {
        key: 'printer_extruder_variant',
        labelKey: 'printerProfile.extruder.printerVariant',
        mode: 'lineList',
        rows: 3,
        placeholder: 'Direct Drive Standard',
      },
      {
        key: 'physical_extruder_map',
        labelKey: 'printerProfile.extruder.physicalMap',
        mode: 'list',
        placeholder: '0, 1',
      },
    ];

    const nozzleAndGeometryFields: MetadataFieldConfig[] = [
      {
        key: 'nozzle_type',
        labelKey: 'printerProfile.extruder.nozzleType',
        mode: 'lineList',
        rows: 3,
        placeholder: 'brass',
        helpText: nozzleTypeHelp,
      },
      {
        key: 'nozzle_volume',
        labelKey: 'printerProfile.extruder.nozzleVolume',
        mode: 'list',
        placeholder: '107',
        unit: t('adminPrinters.units.mm3'),
      },
      {
        key: 'extruder_printable_height',
        labelKey: 'printerProfile.extruder.printableHeight',
        mode: 'list',
        placeholder: '320',
        unit: t('printerProfile.units.mm'),
      },
      {
        key: 'extruder_printable_area',
        labelKey: 'printerProfile.extruder.printableArea',
        mode: 'lineList',
        rows: 3,
        placeholder: '0x0,325x0,325x320,0x320',
      },
      {
        key: 'extruder_offset',
        labelKey: 'printerProfile.extruder.offset',
        mode: 'lineList',
        rows: 2,
        placeholder: '0x0',
      },
      {
        key: 'max_layer_height',
        labelKey: 'printerProfile.extruder.maxLayerHeight',
        mode: 'list',
        placeholder: '0.3',
        unit: t('printerProfile.units.mm'),
      },
      {
        key: 'min_layer_height',
        labelKey: 'printerProfile.extruder.minLayerHeight',
        mode: 'list',
        placeholder: '0.1',
        unit: t('printerProfile.units.mm'),
      },
    ];

    const retractionFields: MetadataFieldConfig[] = [
      { key: 'retraction_length', labelKey: 'printerProfile.retraction.length', mode: 'list', placeholder: '0.8' },
      { key: 'retract_restart_extra', labelKey: 'printerProfile.retraction.restartExtra', mode: 'list', placeholder: '0' },
      { key: 'retraction_speed', labelKey: 'printerProfile.retraction.speed', mode: 'list', placeholder: '30' },
      { key: 'deretraction_speed', labelKey: 'printerProfile.retraction.deretractSpeed', mode: 'list', placeholder: '30' },
      { key: 'retraction_minimum_travel', labelKey: 'printerProfile.retraction.minTravel', mode: 'list', placeholder: '1' },
      {
        key: 'retract_when_changing_layer',
        labelKey: 'printerProfile.retraction.whenChangingLayer',
        mode: 'lineList',
        rows: 2,
        placeholder: '1',
        helpKey: 'printerProfile.retraction.boolArrayHint',
      },
      {
        key: 'wipe',
        labelKey: 'printerProfile.retraction.wipe',
        mode: 'lineList',
        rows: 2,
        placeholder: '0',
        helpKey: 'printerProfile.retraction.boolArrayHint',
      },
      { key: 'wipe_distance', labelKey: 'printerProfile.retraction.wipeDistance', mode: 'list', placeholder: '2' },
      { key: 'retract_before_wipe', labelKey: 'printerProfile.retraction.beforeWipe', mode: 'list', placeholder: '0%, 70%' },
    ];

    const zHopFields: MetadataFieldConfig[] = [
      {
        key: 'retract_lift_enforce',
        labelKey: 'printerProfile.retraction.liftEnforce',
        mode: 'lineList',
        rows: 2,
        placeholder: 'All Surfaces',
        helpText: retractLiftEnforceHelp,
      },
      {
        key: 'z_hop_types',
        labelKey: 'printerProfile.retraction.zhopType',
        mode: 'lineList',
        rows: 2,
        placeholder: 'Normal Lift',
        helpText: zHopTypeHelp,
      },
      { key: 'z_hop', labelKey: 'printerProfile.retraction.zHop', mode: 'list', placeholder: '0.4' },
      { key: 'travel_slope', labelKey: 'printerProfile.retraction.travelSlope', mode: 'list', placeholder: '3' },
      { key: 'retract_lift_above', labelKey: 'printerProfile.retraction.liftAbove', mode: 'list', placeholder: '0' },
      { key: 'retract_lift_below', labelKey: 'printerProfile.retraction.liftBelow', mode: 'list', placeholder: '259' },
    ];

    const materialChangeFields: MetadataFieldConfig[] = [
      { key: 'retract_length_toolchange', labelKey: 'printerProfile.retraction.toolchange', mode: 'list', placeholder: '0.8' },
      {
        key: 'retract_restart_extra_toolchange',
        labelKey: 'printerProfile.retraction.restartExtraToolchange',
        mode: 'list',
        placeholder: '0',
      },
      {
        key: 'long_retractions_when_cut',
        labelKey: 'printerProfile.retraction.longRetractionOnCut',
        mode: 'lineList',
        rows: 2,
        placeholder: '0',
        helpKey: 'printerProfile.retraction.boolArrayHint',
      },
      {
        key: 'retraction_distances_when_cut',
        labelKey: 'printerProfile.retraction.distanceWhenCut',
        mode: 'list',
        placeholder: '18',
      },
    ];

    return (
      <div className="space-y-6">
        {metadataInvalid ? (
          <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            {t('printerProfile.jsonErrorExtruder')}
          </div>
        ) : (
          <div className="space-y-6">
            <div className="rounded-xl border border-white/10 bg-white/5 px-4 py-3">
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-2">{t('printerProfile.sections.commonReferences')}</h5>
              <p className="text-xs text-gray-400">{t('printerProfile.extruder.commonArchitectures')}</p>
              <p className="text-xs text-gray-400 mt-2">{t('printerProfile.extruder.commonNozzleMaterials')}</p>
              <p className="text-xs text-gray-400 mt-2">{t('printerProfile.extruder.commonNozzleFlowFamilies')}</p>
            </div>

            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.sections.extruderHardware')}</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {hardwareFields.map(renderMetadataField)}
              </div>
            </div>

            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.sections.extruderGeometry')}</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {nozzleAndGeometryFields.map(renderMetadataField)}
              </div>
            </div>
          </div>
        )}

        <div>
          <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.sections.retractionZhop')}</h5>
          {metadataInvalid ? (
            <p className="text-xs text-red-200">
              {t('printerProfile.jsonErrorGeneric')}
            </p>
          ) : (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {retractionFields.map(renderMetadataField)}
              </div>

              <div>
                <h6 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.sections.zHop')}</h6>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {zHopFields.map(renderMetadataField)}
                </div>
              </div>

              <div>
                <h6 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.sections.retractionMaterialChange')}</h6>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <label className="block text-gray-300 text-sm font-medium">{t('printerProfile.retraction.enableLongRetractionWhenCut')}</label>
                    <CustomSelect
                      value={longRetractionLevel}
                      onChange={(value) => handleMetadataStringChange('enable_long_retraction_when_cut', (value as string) || '0')}
                      options={buildTranslatedOptions(ORCA_LONG_RETRACTION_LEVEL_OPTIONS, longRetractionLevel)}
                      placeholder={t('printerProfile.selectType')}
                    />
                    <p className="text-xs text-gray-500">{t('printerProfile.retraction.longRetractionOnCutDesc')}</p>
                  </div>
                  {materialChangeFields.map(renderMetadataField)}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  };

  const renderMultimaterialTab = () => {
    const selectedBedTemperatureFormula = getMetadataString('bed_temperature_formula') || null;

    return (
      <div className="space-y-6">
        {metadataInvalid ? (
          <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            {t('printerProfile.jsonErrorMultimaterial')}
          </div>
        ) : (
          <div className="space-y-6">
            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.sections.multimaterialSetup')}</h5>
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
                    {t('printerProfile.multi.singleExtruderMultiMaterial')}
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
                    {t('printerProfile.multi.manualFilamentChange')}
                  </label>
                </div>
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerProfile.multi.extrudersCount')}</label>
                  <input
                    type="text"
                    value={getMetadataString('extruders_count')}
                    onChange={(e) => handleMetadataStringChange('extruders_count', e.target.value)}
                    placeholder="1"
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerProfile.multi.bedTemperatureFormula')}</label>
                  <CustomSelect
                    value={selectedBedTemperatureFormula}
                    onChange={(value) => handleMetadataStringChange('bed_temperature_formula', (value as string) || '')}
                    options={buildTranslatedOptions(ORCA_BED_TEMPERATURE_FORMULA_OPTIONS, selectedBedTemperatureFormula)}
                    placeholder={t('printerProfile.selectType')}
                  />
                </div>
              </div>
            </div>

            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.sections.multimaterialWipeTower')}</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    id="purge_in_prime_tower"
                    checked={getMetadataBoolean('purge_in_prime_tower')}
                    onChange={(e) => handleMetadataBooleanChange('purge_in_prime_tower', e.target.checked)}
                    className="w-4 h-4 rounded border-white/30 bg-white/10"
                  />
                  <label htmlFor="purge_in_prime_tower" className="text-gray-300 text-sm">
                    {t('printerProfile.multi.purgeInTower')}
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
                    {t('printerProfile.multi.enableRamming')}
                  </label>
                </div>
              </div>
            </div>

            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.sections.multimaterialSemm')}</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerProfile.multi.parkingRetraction')}</label>
                  <input
                    type="text"
                    value={getMetadataString('parking_pos_retraction')}
                    onChange={(e) => handleMetadataStringChange('parking_pos_retraction', e.target.value)}
                    placeholder="16"
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerProfile.multi.coolingTubeRetraction')}</label>
                  <input
                    type="text"
                    value={getMetadataString('cooling_tube_retraction')}
                    onChange={(e) => handleMetadataStringChange('cooling_tube_retraction', e.target.value)}
                    placeholder="60"
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerProfile.multi.coolingTubeLength')}</label>
                  <input
                    type="text"
                    value={getMetadataString('cooling_tube_length')}
                    onChange={(e) => handleMetadataStringChange('cooling_tube_length', e.target.value)}
                    placeholder="20"
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerProfile.multi.extraLoadingMove')}</label>
                  <input
                    type="text"
                    value={getMetadataString('extra_loading_move')}
                    onChange={(e) => handleMetadataStringChange('extra_loading_move', e.target.value)}
                    placeholder="0"
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    id="high_current_on_filament_swap"
                    checked={getMetadataBoolean('high_current_on_filament_swap')}
                    onChange={(e) => handleMetadataBooleanChange('high_current_on_filament_swap', e.target.checked)}
                    className="w-4 h-4 rounded border-white/30 bg-white/10"
                  />
                  <label htmlFor="high_current_on_filament_swap" className="text-gray-300 text-sm">
                    {t('printerProfile.multi.highCurrentOnSwap')}
                  </label>
                </div>
              </div>
            </div>

            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.sections.multimaterialAdvanced')}</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerProfile.multi.loadTime')}</label>
                  <input
                    type="text"
                    value={getMetadataString('machine_load_filament_time')}
                    onChange={(e) => handleMetadataStringChange('machine_load_filament_time', e.target.value)}
                    placeholder="29"
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerProfile.multi.unloadTime')}</label>
                  <input
                    type="text"
                    value={getMetadataString('machine_unload_filament_time')}
                    onChange={(e) => handleMetadataStringChange('machine_unload_filament_time', e.target.value)}
                    placeholder="29"
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div>
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerProfile.multi.machineToolChangeTime')}</label>
                  <input
                    type="text"
                    value={getMetadataStringWithAliases('machine_tool_change_time', ['machine_switch_extruder_time'])}
                    onChange={(e) => handleMetadataStringChange('machine_tool_change_time', e.target.value, ['machine_switch_extruder_time'])}
                    placeholder="0"
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                  />
                  <p className="text-xs text-gray-500 mt-1">{t('printerProfile.multi.machineToolChangeTimeHint')}</p>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderGcodeTab = () => (
    <div className="space-y-6">
      {metadataInvalid ? (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {t('printerProfile.jsonErrorGcode')}
        </div>
      ) : (
        <div className="space-y-6">
          {ORCA_PRINTER_GCODE_FIELDS.map(({ key, labelKey }) => {
            const textareaId = `printer-gcode-${key}`;
            const value = getMetadataString(key);
            const label = t(labelKey);
            return (
              <div key={key}>
                <div className="flex items-center justify-between gap-3 mb-2">
                  <label className="text-gray-300 text-sm font-medium">{label}</label>
                  {value ? (
                    <span className="text-[10px] uppercase tracking-wider text-purple-200/60">
                      {t('printerProfile.gcode.chars')}: {value.length}
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
                    placeholder={t('printerProfile.gcode.placeholder')}
                  />
                  <button
                    type="button"
                    onClick={() => toggleGcodeModal(key)}
                    className={`absolute right-2 top-2 p-1.5 rounded hover:bg-white/10 transition-all ${
                      showGcodeModals[key]
                        ? 'text-purple-400 bg-purple-500/20'
                        : 'text-gray-400 hover:text-purple-400'
                    }`}
                    title={t('printerProfile.gcode.insertPlaceholder')}
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                  {showGcodeModals[key] && (
                    <EditGCodeModal
                      isOpen={showGcodeModals[key]}
                      onClose={() => toggleGcodeModal(key)}
                      onInsert={(placeholderText) => handleInsertGcodePlaceholder(key, textareaId, placeholderText)}
                      title={t('printerProfile.gcode.insertPlaceholderIn', { label })}
                    />
                  )}
                </div>
              </div>
            );
          })}

          <div className="rounded-xl border border-white/10 bg-white/5 px-4 py-3">
            <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-2">
              {t('printerProfile.gcode.legacyCompatibility')}
            </h5>
            <p className="text-xs text-gray-500">{t('printerProfile.gcode.legacyCompatibilityHint')}</p>
          </div>

          {LEGACY_COMPATIBILITY_GCODE_FIELDS.map(({ key, labelKey }) => {
            const textareaId = `printer-gcode-legacy-${key}`;
            const value = getMetadataString(key);
            const label = t(labelKey);
            return (
              <div key={key}>
                <div className="flex items-center justify-between gap-3 mb-2">
                  <label className="text-gray-300 text-sm font-medium">{label}</label>
                  {value ? (
                    <span className="text-[10px] uppercase tracking-wider text-purple-200/60">
                      {t('printerProfile.gcode.chars')}: {value.length}
                    </span>
                  ) : null}
                </div>
                <div className="relative flex items-start gap-3">
                  <textarea
                    id={textareaId}
                    value={value}
                    onChange={(e) => handleMetadataStringChange(key, e.target.value)}
                    rows={6}
                    className="flex-1 bg-white/5 border border-white/10 rounded-lg px-4 py-2 pr-10 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 font-mono text-sm resize-none"
                    placeholder={t('printerProfile.gcode.placeholder')}
                  />
                  <button
                    type="button"
                    onClick={() => toggleGcodeModal(key)}
                    className={`absolute right-2 top-2 p-1.5 rounded hover:bg-white/10 transition-all ${
                      showGcodeModals[key]
                        ? 'text-purple-400 bg-purple-500/20'
                        : 'text-gray-400 hover:text-purple-400'
                    }`}
                    title={t('printerProfile.gcode.insertPlaceholder')}
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                  {showGcodeModals[key] && (
                    <EditGCodeModal
                      isOpen={showGcodeModals[key]}
                      onClose={() => toggleGcodeModal(key)}
                      onInsert={(placeholderText) => handleInsertGcodePlaceholder(key, textareaId, placeholderText)}
                      title={t('printerProfile.gcode.insertPlaceholderIn', { label })}
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
              {profile ? t('printerProfile.titleEdit') : baseProfile ? t('printerProfile.titleClone') : t('printerProfile.titleCreate')}
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
            {t('printerProfile.tabs.general')}
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
            {t('printerProfile.tabs.motion')}
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
            {t('printerProfile.tabs.extruders')}
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
            {t('printerProfile.tabs.multimaterial')}
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
            {t('printerProfile.tabs.gcode')}
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
            {t('printerProfile.tabs.notes')}
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
                  {t('printerProfile.notesLabel')}
                </label>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={10}
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 resize-none"
                  placeholder={t('printerProfile.notesPlaceholder')}
                />
                <p className="text-xs text-gray-500 mt-1">
                  {t('printerProfile.notesHint')}
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
              {t('printerProfile.cancel')}
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="px-6 py-2 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-700 hover:to-pink-700 text-white rounded-lg transition-all shadow-lg shadow-purple-500/25 hover:shadow-purple-500/40 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {createMutation.isPending ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  {t('printerProfile.saving')}
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  {profile ? t('printerProfile.saveChanges') : t('printerProfile.createProfile')}
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
