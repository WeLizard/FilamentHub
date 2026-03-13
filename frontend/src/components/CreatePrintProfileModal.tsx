/** Modal for creating and editing Orca process profiles. */

import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Save, Loader2, Layers } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { printerProfilesAPI, printProfilesAPI } from '../api/client';
import { Dropdown } from './Dropdown';
import { translateApiError } from '../utils/translateApiError';
import { useAuth } from '../contexts/AuthContext';
import type { PrintProfile, PrinterProfile } from '../types/api';

interface CreatePrintProfileModalProps {
  isOpen: boolean;
  onClose: () => void;
  profile?: PrintProfile | null;
  baseProfile?: PrintProfile | null;
  printerProfileContext?: PrinterProfile | null;
}

const DEFAULT_PROCESS_BASE = 'fdm_process_common';
const DEFAULT_PROCESS_VERSION = '01.00.00.00';

const QUALITY_TIER_LABELS: Record<string, string> = {
  superdraft: 'Extra Draft',
  draft: 'Draft',
  standard: 'Standard',
  optimal: 'Optimal',
  fine: 'Fine',
  highdetail: 'Extra Fine',
};

const QUALITY_TIER_OPTIONS = [
  'superdraft',
  'draft',
  'standard',
  'optimal',
  'fine',
  'highdetail',
];

const INFILL_PATTERN_OPTIONS = [
  'crosshatch',
  'gyroid',
  'grid',
  'line',
  'rectilinear',
  'alignedrectilinear',
  'cubic',
  'adaptivecubic',
  'supportcubic',
  'honeycomb',
  '3dhoneycomb',
  'lightning',
  'concentric',
  'hilbertcurve',
  'archimedeanchords',
  'octagramspiral',
];
const SUPPORT_TYPE_OPTIONS = ['normal(auto)', 'tree(auto)', 'normal(manual)', 'tree(manual)'];
const SEAM_POSITION_OPTIONS = ['aligned', 'aligned_back', 'nearest', 'back', 'random'];
const IRONING_TYPE_OPTIONS = ['no ironing', 'top', 'topmost', 'solid'];
const BOOLEAN_OVERRIDE_OPTIONS = ['', '1', '0'];
const DEFAULT_NOZZLE_SIZES = ['0.2', '0.25', '0.3', '0.4', '0.5', '0.6', '0.8', '1.0'];

const slugifyValue = (value: string): string =>
  value
    .toLowerCase()
    .trim()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/\s+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '');

const readSettingString = (settings: Record<string, unknown> | undefined, key: string): string => {
  const value = settings?.[key];
  if (typeof value === 'string') {
    return value;
  }
  if (typeof value === 'number') {
    return String(value);
  }
  if (Array.isArray(value) && value.length > 0) {
    return String(value[0] ?? '');
  }
  return '';
};

const readSettingList = (settings: Record<string, unknown> | undefined, key: string): string[] => {
  const value = settings?.[key];
  if (Array.isArray(value)) {
    return value
      .map((item) => String(item ?? '').trim())
      .filter((item) => item.length > 0);
  }
  if (typeof value === 'string') {
    return value
      .split(',')
      .map((item) => item.trim())
      .filter((item) => item.length > 0);
  }
  return [];
};

const readSettingBooleanString = (settings: Record<string, unknown> | undefined, key: string): string => {
  const value = settings?.[key];
  if (typeof value === 'boolean') {
    return value ? '1' : '0';
  }
  if (typeof value === 'number') {
    return value === 0 ? '0' : '1';
  }
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    if (!normalized) {
      return '';
    }
    if (['1', 'true', 'yes'].includes(normalized)) {
      return '1';
    }
    if (['0', 'false', 'no'].includes(normalized)) {
      return '0';
    }
  }
  return '';
};

const normalizeNumericString = (value: string): string => {
  const trimmed = value.trim();
  if (!trimmed) {
    return '';
  }
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed)) {
    return '';
  }
  return parsed.toString();
};

const normalizePercentString = (value: string): string => {
  const trimmed = value.trim().replace('%', '');
  if (!trimmed) {
    return '';
  }
  const parsed = Number(trimmed);
  if (!Number.isFinite(parsed)) {
    return '';
  }
  return `${parsed}%`;
};

const normalizeNumericOrPercentString = (value: string): string => {
  const trimmed = value.trim();
  if (!trimmed) {
    return '';
  }
  if (trimmed.endsWith('%')) {
    return normalizePercentString(trimmed);
  }
  return normalizeNumericString(trimmed);
};

const dedupeStringValues = (values: string[]): string[] =>
  Array.from(
    new Set(
      values
        .map((item) => item.trim())
        .filter((item) => item.length > 0),
    ),
  );

const qualityTierLabel = (value: string): string => QUALITY_TIER_LABELS[value.toLowerCase()] ?? value;

const buildRecommendedName = (layerHeight: string, qualityTier: string, printerTag: string): string => {
  const normalizedLayerHeight = normalizeNumericString(layerHeight);
  if (!normalizedLayerHeight || !qualityTier.trim()) {
    return '';
  }
  return `${normalizedLayerHeight}mm ${qualityTierLabel(qualityTier)} @${printerTag}`;
};

const areStringArraysEqual = (left: string[], right: string[]): boolean => {
  if (left.length !== right.length) {
    return false;
  }
  return left.every((value, index) => value === right[index]);
};

const buildPrinterProfileOptionLabel = (printerProfile: PrinterProfile): string => {
  const printerDetails = [printerProfile.printer_manufacturer, printerProfile.printer_model]
    .filter(Boolean)
    .join(' ');

  if (printerDetails) {
    return `${printerProfile.name} · ${printerDetails}`;
  }

  if (printerProfile.printer_name) {
    return `${printerProfile.name} · ${printerProfile.printer_name}`;
  }

  return printerProfile.name;
};

interface FormFieldProps {
  label: ReactNode;
  children: ReactNode;
  required?: boolean;
  hint?: ReactNode;
  className?: string;
  labelMinHeightClassName?: string;
}

const FormField: React.FC<FormFieldProps> = ({
  label,
  children,
  required = false,
  hint,
  className = '',
  labelMinHeightClassName = 'min-h-[3rem]',
}) => (
  <div className={className}>
    <div className={`mb-2 flex items-end ${labelMinHeightClassName}`}>
      <label className="block text-sm font-medium leading-5 text-gray-300">
        {label} {required && <span className="text-red-400">*</span>}
      </label>
    </div>
    {children}
    {hint ? <p className="mt-1 text-xs text-gray-500">{hint}</p> : null}
  </div>
);

export const CreatePrintProfileModal: React.FC<CreatePrintProfileModalProps> = ({
  isOpen,
  onClose,
  profile,
  baseProfile,
  printerProfileContext,
}) => {
  const { t } = useTranslation();
  const { user } = useAuth();
  const queryClient = useQueryClient();

  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('');
  const [qualityTier, setQualityTier] = useState('');
  const [defaultNozzle, setDefaultNozzle] = useState('');
  const [layerHeight, setLayerHeight] = useState('');
  const [initialLayerHeight, setInitialLayerHeight] = useState('');
  const [wallLoops, setWallLoops] = useState('');
  const [topShellLayers, setTopShellLayers] = useState('');
  const [bottomShellLayers, setBottomShellLayers] = useState('');
  const [infillDensity, setInfillDensity] = useState('');
  const [infillPattern, setInfillPattern] = useState('');
  const [initialLayerSpeed, setInitialLayerSpeed] = useState('');
  const [initialLayerInfillSpeed, setInitialLayerInfillSpeed] = useState('');
  const [internalSolidInfillSpeed, setInternalSolidInfillSpeed] = useState('');
  const [bridgeSpeed, setBridgeSpeed] = useState('');
  const [outerWallSpeed, setOuterWallSpeed] = useState('');
  const [innerWallSpeed, setInnerWallSpeed] = useState('');
  const [infillSpeed, setInfillSpeed] = useState('');
  const [travelSpeed, setTravelSpeed] = useState('');
  const [defaultAcceleration, setDefaultAcceleration] = useState('');
  const [travelAcceleration, setTravelAcceleration] = useState('');
  const [enableSupport, setEnableSupport] = useState('');
  const [supportType, setSupportType] = useState('');
  const [supportThresholdAngle, setSupportThresholdAngle] = useState('');
  const [brimWidth, setBrimWidth] = useState('');
  const [skirtLoops, setSkirtLoops] = useState('');
  const [raftLayers, setRaftLayers] = useState('');
  const [seamPosition, setSeamPosition] = useState('');
  const [ironingType, setIroningType] = useState('');
  const [enableArcFitting, setEnableArcFitting] = useState('');
  const [spiralMode, setSpiralMode] = useState('');
  const [selectedCompatiblePrinters, setSelectedCompatiblePrinters] = useState<string[]>([]);
  const [compatiblePrinterSearch, setCompatiblePrinterSearch] = useState('');
  const [notes, setNotes] = useState('');
  const [nameManuallyChanged, setNameManuallyChanged] = useState(false);

  const sourceProfile = profile ?? baseProfile ?? null;
  const sourceSettings = (sourceProfile?.orcaslicer_settings ?? {}) as Record<string, unknown>;

  const printerProfilesQuery = useQuery({
    queryKey: ['create-print-profile-modal', 'printer-profiles', user?.id],
    queryFn: () =>
      printerProfilesAPI.list({
        owner_user_id: user?.id,
        active_only: true,
        size: 200,
      }),
    enabled: isOpen && Boolean(user?.id),
    staleTime: 60_000,
  });

  const availablePrinterProfiles = printerProfilesQuery.data?.items ?? [];
  const recommendedPrinterTag = selectedCompatiblePrinters[0] || printerProfileContext?.name || 'FilamentHub';
  const recommendedName =
    !profile && !baseProfile && layerHeight.trim() && qualityTier.trim()
      ? buildRecommendedName(layerHeight, qualityTier, recommendedPrinterTag)
      : '';
  const availableCompatiblePrinterOptions = availablePrinterProfiles
    .filter((printerProfile) => !selectedCompatiblePrinters.includes(printerProfile.name))
    .map((printerProfile) => ({
      value: printerProfile.id,
      label: buildPrinterProfileOptionLabel(printerProfile),
    }));
  const knownCompatiblePrinterNames = new Set(availablePrinterProfiles.map((printerProfile) => printerProfile.name));
  const showSupportThresholdField = enableSupport === '1' && supportType.includes('(auto)');

  useEffect(() => {
    if (isOpen) {
      setNameManuallyChanged(false);
    }
  }, [isOpen, profile, baseProfile]);

  useEffect(() => {
    if (!profile && !baseProfile && !nameManuallyChanged && recommendedName) {
      setName(recommendedName);
    }
  }, [baseProfile, nameManuallyChanged, profile, recommendedName]);

  useEffect(() => {
    if (!profile && !baseProfile && name) {
      setSlug(slugifyValue(name));
    }
  }, [name, profile, baseProfile]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const nextCompatiblePrinters = dedupeStringValues([
      ...(sourceProfile?.compatible_printers?.filter(Boolean) ?? []),
      ...readSettingList(sourceSettings, 'compatible_printers'),
    ]);
    const contextNozzle =
      printerProfileContext?.nozzle_diameters?.[0] != null ? String(printerProfileContext.nozzle_diameters[0]) : '';
    const fallbackCompatiblePrinters =
      nextCompatiblePrinters.length > 0
        ? nextCompatiblePrinters
        : printerProfileContext?.name
          ? [printerProfileContext.name]
          : [];

    if (profile) {
      setName(profile.name || '');
      setSlug(profile.slug || '');
      setDescription(profile.description || '');
      setCategory(profile.category || '');
      setQualityTier(profile.quality_tier || '');
      setDefaultNozzle(profile.default_nozzle || readSettingString(sourceSettings, 'default_nozzle_diameter') || contextNozzle);
      setLayerHeight(profile.layer_height_mm != null ? String(profile.layer_height_mm) : readSettingString(sourceSettings, 'layer_height'));
      setInitialLayerHeight(readSettingString(sourceSettings, 'initial_layer_print_height'));
      setWallLoops(readSettingString(sourceSettings, 'wall_loops'));
      setTopShellLayers(readSettingString(sourceSettings, 'top_shell_layers'));
      setBottomShellLayers(readSettingString(sourceSettings, 'bottom_shell_layers'));
      setInfillDensity(readSettingString(sourceSettings, 'sparse_infill_density').replace('%', ''));
      setInfillPattern(readSettingString(sourceSettings, 'sparse_infill_pattern'));
      setInitialLayerSpeed(readSettingString(sourceSettings, 'initial_layer_speed'));
      setInitialLayerInfillSpeed(readSettingString(sourceSettings, 'initial_layer_infill_speed'));
      setInternalSolidInfillSpeed(readSettingString(sourceSettings, 'internal_solid_infill_speed'));
      setBridgeSpeed(readSettingString(sourceSettings, 'bridge_speed'));
      setOuterWallSpeed(readSettingString(sourceSettings, 'outer_wall_speed'));
      setInnerWallSpeed(readSettingString(sourceSettings, 'inner_wall_speed'));
      setInfillSpeed(readSettingString(sourceSettings, 'sparse_infill_speed'));
      setTravelSpeed(readSettingString(sourceSettings, 'travel_speed'));
      setDefaultAcceleration(readSettingString(sourceSettings, 'default_acceleration'));
      setTravelAcceleration(readSettingString(sourceSettings, 'travel_acceleration'));
      setEnableSupport(readSettingBooleanString(sourceSettings, 'enable_support'));
      setSupportType(readSettingString(sourceSettings, 'support_type'));
      setSupportThresholdAngle(readSettingString(sourceSettings, 'support_threshold_angle'));
      setBrimWidth(readSettingString(sourceSettings, 'brim_width'));
      setSkirtLoops(readSettingString(sourceSettings, 'skirt_loops'));
      setRaftLayers(readSettingString(sourceSettings, 'raft_layers'));
      setSeamPosition(readSettingString(sourceSettings, 'seam_position'));
      setIroningType(readSettingString(sourceSettings, 'ironing_type'));
      setEnableArcFitting(readSettingBooleanString(sourceSettings, 'enable_arc_fitting'));
      setSpiralMode(readSettingBooleanString(sourceSettings, 'spiral_mode'));
      setSelectedCompatiblePrinters(fallbackCompatiblePrinters);
      setCompatiblePrinterSearch('');
      setNotes(profile.notes || '');
      return;
    }

    if (baseProfile) {
      setName(`${baseProfile.name} (${t('createPrintProfile.copy')})`);
      setSlug(`${baseProfile.slug}-copy`);
      setDescription(baseProfile.description || '');
      setCategory(baseProfile.category || '');
      setQualityTier(baseProfile.quality_tier || '');
      setDefaultNozzle(baseProfile.default_nozzle || readSettingString(sourceSettings, 'default_nozzle_diameter') || contextNozzle);
      setLayerHeight(baseProfile.layer_height_mm != null ? String(baseProfile.layer_height_mm) : readSettingString(sourceSettings, 'layer_height'));
      setInitialLayerHeight(readSettingString(sourceSettings, 'initial_layer_print_height'));
      setWallLoops(readSettingString(sourceSettings, 'wall_loops'));
      setTopShellLayers(readSettingString(sourceSettings, 'top_shell_layers'));
      setBottomShellLayers(readSettingString(sourceSettings, 'bottom_shell_layers'));
      setInfillDensity(readSettingString(sourceSettings, 'sparse_infill_density').replace('%', ''));
      setInfillPattern(readSettingString(sourceSettings, 'sparse_infill_pattern'));
      setInitialLayerSpeed(readSettingString(sourceSettings, 'initial_layer_speed'));
      setInitialLayerInfillSpeed(readSettingString(sourceSettings, 'initial_layer_infill_speed'));
      setInternalSolidInfillSpeed(readSettingString(sourceSettings, 'internal_solid_infill_speed'));
      setBridgeSpeed(readSettingString(sourceSettings, 'bridge_speed'));
      setOuterWallSpeed(readSettingString(sourceSettings, 'outer_wall_speed'));
      setInnerWallSpeed(readSettingString(sourceSettings, 'inner_wall_speed'));
      setInfillSpeed(readSettingString(sourceSettings, 'sparse_infill_speed'));
      setTravelSpeed(readSettingString(sourceSettings, 'travel_speed'));
      setDefaultAcceleration(readSettingString(sourceSettings, 'default_acceleration'));
      setTravelAcceleration(readSettingString(sourceSettings, 'travel_acceleration'));
      setEnableSupport(readSettingBooleanString(sourceSettings, 'enable_support'));
      setSupportType(readSettingString(sourceSettings, 'support_type'));
      setSupportThresholdAngle(readSettingString(sourceSettings, 'support_threshold_angle'));
      setBrimWidth(readSettingString(sourceSettings, 'brim_width'));
      setSkirtLoops(readSettingString(sourceSettings, 'skirt_loops'));
      setRaftLayers(readSettingString(sourceSettings, 'raft_layers'));
      setSeamPosition(readSettingString(sourceSettings, 'seam_position'));
      setIroningType(readSettingString(sourceSettings, 'ironing_type'));
      setEnableArcFitting(readSettingBooleanString(sourceSettings, 'enable_arc_fitting'));
      setSpiralMode(readSettingBooleanString(sourceSettings, 'spiral_mode'));
      setSelectedCompatiblePrinters(fallbackCompatiblePrinters);
      setCompatiblePrinterSearch('');
      setNotes(baseProfile.notes || '');
      return;
    }

    setName('');
    setSlug('');
    setDescription('');
    setCategory('');
    setQualityTier('');
    setDefaultNozzle(contextNozzle);
    setLayerHeight('');
    setInitialLayerHeight('');
    setWallLoops('');
    setTopShellLayers('');
    setBottomShellLayers('');
    setInfillDensity('');
    setInfillPattern('');
    setInitialLayerSpeed('');
    setInitialLayerInfillSpeed('');
    setInternalSolidInfillSpeed('');
    setBridgeSpeed('');
    setOuterWallSpeed('');
    setInnerWallSpeed('');
    setInfillSpeed('');
    setTravelSpeed('');
    setDefaultAcceleration('');
    setTravelAcceleration('');
    setEnableSupport('');
    setSupportType('');
    setSupportThresholdAngle('');
    setBrimWidth('');
    setSkirtLoops('');
    setRaftLayers('');
    setSeamPosition('');
    setIroningType('');
    setEnableArcFitting('');
    setSpiralMode('');
    setSelectedCompatiblePrinters(printerProfileContext?.name ? [printerProfileContext.name] : []);
    setCompatiblePrinterSearch('');
    setNotes('');
  }, [isOpen, profile, baseProfile, printerProfileContext, t]);

  const createMutation = useMutation({
    mutationFn: (data: Parameters<typeof printProfilesAPI.create>[0]) => {
      if (profile) {
        return printProfilesAPI.update(profile.id, data);
      }
      return printProfilesAPI.create(data);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['print-profiles'] });
      queryClient.invalidateQueries({ queryKey: ['print-profiles', user?.id] });
      onClose();
    },
    onError: (error: any) => {
      console.error('Error saving print profile:', error);
      alert(translateApiError(t, error?.response?.data?.detail, t('createPrintProfile.saveError')));
    },
  });

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();

    const trimmedName = name.trim();
    const trimmedSlug = slug.trim();
    const compatiblePrinters = dedupeStringValues(selectedCompatiblePrinters);

    if (!trimmedName) {
      alert(t('createPrintProfile.nameRequired'));
      return;
    }

    if (!trimmedSlug) {
      alert(t('createPrintProfile.slugRequired'));
      return;
    }

    if (compatiblePrinters.length === 0) {
      alert(t('createPrintProfile.compatiblePrintersRequired'));
      return;
    }

    const layerHeightValue = normalizeNumericString(layerHeight);
    const initialLayerHeightValue = normalizeNumericString(initialLayerHeight);
    const wallLoopsValue = normalizeNumericString(wallLoops);
    const topShellLayersValue = normalizeNumericString(topShellLayers);
    const bottomShellLayersValue = normalizeNumericString(bottomShellLayers);
    const infillDensityValue = normalizePercentString(infillDensity);
    const initialLayerSpeedValue = normalizeNumericOrPercentString(initialLayerSpeed);
    const initialLayerInfillSpeedValue = normalizeNumericOrPercentString(initialLayerInfillSpeed);
    const internalSolidInfillSpeedValue = normalizeNumericString(internalSolidInfillSpeed);
    const bridgeSpeedValue = normalizeNumericString(bridgeSpeed);
    const outerWallSpeedValue = normalizeNumericString(outerWallSpeed);
    const innerWallSpeedValue = normalizeNumericString(innerWallSpeed);
    const infillSpeedValue = normalizeNumericString(infillSpeed);
    const travelSpeedValue = normalizeNumericString(travelSpeed);
    const defaultAccelerationValue = normalizeNumericString(defaultAcceleration);
    const travelAccelerationValue = normalizeNumericString(travelAcceleration);
    const supportThresholdAngleValue = normalizeNumericString(supportThresholdAngle);
    const brimWidthValue = normalizeNumericString(brimWidth);
    const skirtLoopsValue = normalizeNumericString(skirtLoops);
    const raftLayersValue = normalizeNumericString(raftLayers);
    const profileSource = profile?.source === 'system' ? 'system' : 'user';

    const mergedSettings: Record<string, unknown> = {
      ...sourceSettings,
      type: 'process',
      name: trimmedName,
      from: profileSource,
      instantiation: 'true',
      inherits: readSettingString(sourceSettings, 'inherits') || DEFAULT_PROCESS_BASE,
      version: readSettingString(sourceSettings, 'version') || DEFAULT_PROCESS_VERSION,
      print_settings_id: readSettingString(sourceSettings, 'print_settings_id') || trimmedName,
      compatible_printers: compatiblePrinters,
    };

    const setOrDelete = (key: string, value: string) => {
      if (value) {
        mergedSettings[key] = value;
      } else {
        delete mergedSettings[key];
      }
    };

    setOrDelete('default_nozzle_diameter', defaultNozzle.trim());
    setOrDelete('layer_height', layerHeightValue);
    setOrDelete('initial_layer_print_height', initialLayerHeightValue || layerHeightValue);
    setOrDelete('wall_loops', wallLoopsValue);
    setOrDelete('top_shell_layers', topShellLayersValue);
    setOrDelete('bottom_shell_layers', bottomShellLayersValue);
    setOrDelete('sparse_infill_density', infillDensityValue);
    setOrDelete('sparse_infill_pattern', infillPattern.trim());
    setOrDelete('initial_layer_speed', initialLayerSpeedValue);
    setOrDelete('initial_layer_infill_speed', initialLayerInfillSpeedValue);
    setOrDelete('internal_solid_infill_speed', internalSolidInfillSpeedValue);
    setOrDelete('bridge_speed', bridgeSpeedValue);
    setOrDelete('outer_wall_speed', outerWallSpeedValue);
    setOrDelete('inner_wall_speed', innerWallSpeedValue);
    setOrDelete('sparse_infill_speed', infillSpeedValue);
    setOrDelete('travel_speed', travelSpeedValue);
    setOrDelete('default_acceleration', defaultAccelerationValue);
    setOrDelete('travel_acceleration', travelAccelerationValue);
    setOrDelete('enable_support', enableSupport);
    setOrDelete('support_type', supportType.trim());
    setOrDelete('support_threshold_angle', showSupportThresholdField ? supportThresholdAngleValue : '');
    setOrDelete('brim_width', brimWidthValue);
    setOrDelete('skirt_loops', skirtLoopsValue);
    setOrDelete('raft_layers', raftLayersValue);
    setOrDelete('seam_position', seamPosition.trim());
    setOrDelete('ironing_type', ironingType.trim());
    setOrDelete('enable_arc_fitting', enableArcFitting);
    setOrDelete('spiral_mode', spiralMode);

    const data: Parameters<typeof printProfilesAPI.create>[0] = {
      name: trimmedName,
      slug: trimmedSlug,
      description: description.trim() || null,
      category: category.trim() || null,
      quality_tier: qualityTier.trim() || null,
      default_nozzle: defaultNozzle.trim() || null,
      layer_height_mm: layerHeightValue ? Number(layerHeightValue) : null,
      compatible_printers: compatiblePrinters,
      notes: notes.trim() || null,
      active: true,
      source: profileSource,
      vendor: profile?.vendor ?? baseProfile?.vendor ?? printerProfileContext?.vendor ?? null,
      orcaslicer_settings: mergedSettings,
    };

    if (!profile && baseProfile?.compatible_filaments?.length) {
      data.compatible_filaments = baseProfile.compatible_filaments;
    }

    if (!profile && baseProfile) {
      const baseSettings = (baseProfile.orcaslicer_settings ?? {}) as Record<string, unknown>;
      const normalizedBaseCompatiblePrinters = Array.from(
        new Set([
          ...(baseProfile.compatible_printers?.filter(Boolean) ?? []),
          ...readSettingList(baseSettings, 'compatible_printers'),
        ]),
      ).sort();
      const normalizedCurrentCompatiblePrinters = [...compatiblePrinters].sort();
      const baseComparableValues = {
        qualityTier: baseProfile.quality_tier ?? '',
        defaultNozzle: baseProfile.default_nozzle ?? readSettingString(baseSettings, 'default_nozzle_diameter'),
        layerHeight:
          baseProfile.layer_height_mm != null ? normalizeNumericString(String(baseProfile.layer_height_mm)) : readSettingString(baseSettings, 'layer_height'),
        initialLayerHeight: readSettingString(baseSettings, 'initial_layer_print_height'),
        wallLoops: readSettingString(baseSettings, 'wall_loops'),
        topShellLayers: readSettingString(baseSettings, 'top_shell_layers'),
        bottomShellLayers: readSettingString(baseSettings, 'bottom_shell_layers'),
        infillDensity: readSettingString(baseSettings, 'sparse_infill_density'),
        infillPattern: readSettingString(baseSettings, 'sparse_infill_pattern'),
        initialLayerSpeed: readSettingString(baseSettings, 'initial_layer_speed'),
        initialLayerInfillSpeed: readSettingString(baseSettings, 'initial_layer_infill_speed'),
        internalSolidInfillSpeed: readSettingString(baseSettings, 'internal_solid_infill_speed'),
        bridgeSpeed: readSettingString(baseSettings, 'bridge_speed'),
        outerWallSpeed: readSettingString(baseSettings, 'outer_wall_speed'),
        innerWallSpeed: readSettingString(baseSettings, 'inner_wall_speed'),
        infillSpeed: readSettingString(baseSettings, 'sparse_infill_speed'),
        travelSpeed: readSettingString(baseSettings, 'travel_speed'),
        defaultAcceleration: readSettingString(baseSettings, 'default_acceleration'),
        travelAcceleration: readSettingString(baseSettings, 'travel_acceleration'),
        enableSupport: readSettingBooleanString(baseSettings, 'enable_support'),
        supportType: readSettingString(baseSettings, 'support_type'),
        supportThresholdAngle: readSettingString(baseSettings, 'support_threshold_angle'),
        brimWidth: readSettingString(baseSettings, 'brim_width'),
        skirtLoops: readSettingString(baseSettings, 'skirt_loops'),
        raftLayers: readSettingString(baseSettings, 'raft_layers'),
        seamPosition: readSettingString(baseSettings, 'seam_position'),
        ironingType: readSettingString(baseSettings, 'ironing_type'),
        enableArcFitting: readSettingBooleanString(baseSettings, 'enable_arc_fitting'),
        spiralMode: readSettingBooleanString(baseSettings, 'spiral_mode'),
      };

      const currentComparableValues = {
        qualityTier: qualityTier.trim(),
        defaultNozzle: defaultNozzle.trim(),
        layerHeight: layerHeightValue,
        initialLayerHeight: initialLayerHeightValue || layerHeightValue,
        wallLoops: wallLoopsValue,
        topShellLayers: topShellLayersValue,
        bottomShellLayers: bottomShellLayersValue,
        infillDensity: infillDensityValue,
        infillPattern: infillPattern.trim(),
        initialLayerSpeed: initialLayerSpeedValue,
        initialLayerInfillSpeed: initialLayerInfillSpeedValue,
        internalSolidInfillSpeed: internalSolidInfillSpeedValue,
        bridgeSpeed: bridgeSpeedValue,
        outerWallSpeed: outerWallSpeedValue,
        innerWallSpeed: innerWallSpeedValue,
        infillSpeed: infillSpeedValue,
        travelSpeed: travelSpeedValue,
        defaultAcceleration: defaultAccelerationValue,
        travelAcceleration: travelAccelerationValue,
        enableSupport,
        supportType: supportType.trim(),
        supportThresholdAngle: showSupportThresholdField ? supportThresholdAngleValue : '',
        brimWidth: brimWidthValue,
        skirtLoops: skirtLoopsValue,
        raftLayers: raftLayersValue,
        seamPosition: seamPosition.trim(),
        ironingType: ironingType.trim(),
        enableArcFitting,
        spiralMode,
      };

      const isIdenticalClone =
        Object.entries(currentComparableValues).every(([key, value]) => baseComparableValues[key as keyof typeof baseComparableValues] === value) &&
        areStringArraysEqual(normalizedBaseCompatiblePrinters, normalizedCurrentCompatiblePrinters);

      if (isIdenticalClone) {
        alert(t('createPrintProfile.duplicateCloneError'));
        return;
      }
    }

    createMutation.mutate(data);
  };

  if (!isOpen) {
    return null;
  }

  const nozzleOptions = Array.from(
    new Set([
      ...(printerProfileContext?.nozzle_diameters?.map((value) => String(value)) ?? []),
      ...DEFAULT_NOZZLE_SIZES,
    ]),
  );

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-white/20 bg-gradient-to-br from-gray-900 to-gray-800 shadow-2xl">
        <div className="flex items-center justify-between border-b border-white/10 p-6">
          <div className="flex items-center gap-3">
            <Layers className="h-6 w-6 text-purple-400" />
            <h2 className="text-2xl font-bold text-white">
              {profile ? t('createPrintProfile.editTitle') : baseProfile ? t('createPrintProfile.cloneTitle') : t('createPrintProfile.createTitle')}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-gray-400 transition-all hover:bg-white/10 hover:text-white"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex-1 space-y-6 overflow-y-auto p-6">
          <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/10 p-4">
            <h3 className="text-sm font-semibold text-cyan-200">{t('createPrintProfile.orcaSection')}</h3>
            <p className="mt-1 text-xs leading-relaxed text-cyan-100/80">{t('createPrintProfile.phaseOneHint')}</p>
            {printerProfileContext && (
              <p className="mt-3 text-xs text-cyan-100/80">
                {t('createPrintProfile.contextPrinter')}: <span className="font-medium text-cyan-100">{printerProfileContext.name}</span>
              </p>
            )}
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <FormField
              label={
                <>
                  {t('createPrintProfile.name')}
                  {recommendedName && (
                    <span className="ml-2 text-xs text-gray-400">
                      ({t('createPrintProfile.recommendedFormat')}: &quot;{recommendedName}&quot;)
                    </span>
                  )}
                </>
              }
              required
              hint={recommendedName && name && name.trim() !== recommendedName ? `${t('createPrintProfile.recommendedFormatHint')}: "${recommendedName}"` : undefined}
            >
              <input
                type="text"
                value={name}
                onChange={(event) => {
                  setName(event.target.value);
                  setNameManuallyChanged(true);
                }}
                className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                placeholder={recommendedName || t('createPrintProfile.namePlaceholder')}
                required
              />
            </FormField>

            <FormField label={t('createPrintProfile.slug')} required hint={t('createPrintProfile.slugHint')}>
              <input
                type="text"
                value={slug}
                onChange={(event) => setSlug(event.target.value)}
                className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 font-mono text-sm text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                placeholder="0-20mm-standard-vendor-printer-0-4-nozzle"
                required
              />
            </FormField>
          </div>

          <div className="grid gap-6 lg:grid-cols-4">
            <FormField label={t('createPrintProfile.qualityTier')}>
              <select
                value={qualityTier}
                onChange={(event) => setQualityTier(event.target.value)}
                className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white focus:border-purple-500 focus:outline-none"
              >
                <option value="">{t('createPrintProfile.notSpecified')}</option>
                {QUALITY_TIER_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {t(`createPrintProfile.qualityOptions.${option}`)}
                  </option>
                ))}
              </select>
            </FormField>

            <FormField label={t('createPrintProfile.defaultNozzle')}>
              <select
                value={defaultNozzle}
                onChange={(event) => setDefaultNozzle(event.target.value)}
                className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white focus:border-purple-500 focus:outline-none"
              >
                <option value="">{t('createPrintProfile.notSpecified')}</option>
                {nozzleOptions.map((size) => (
                  <option key={size} value={size}>
                    {size} {t('createPrintProfile.mm')}
                  </option>
                ))}
              </select>
            </FormField>

            <FormField label={t('createPrintProfile.layerHeight')}>
              <input
                type="number"
                step="0.01"
                min="0.01"
                max="1.0"
                value={layerHeight}
                onChange={(event) => setLayerHeight(event.target.value)}
                className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                placeholder="0.2"
              />
            </FormField>

            <FormField label={t('createPrintProfile.initialLayerHeight')}>
              <input
                type="number"
                step="0.01"
                min="0.01"
                max="1.0"
                value={initialLayerHeight}
                onChange={(event) => setInitialLayerHeight(event.target.value)}
                className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                placeholder={layerHeight || '0.2'}
              />
            </FormField>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <h3 className="text-sm font-semibold text-white">{t('createPrintProfile.compatibilitySection')}</h3>
            <div className="mt-4">
              <FormField
                label={t('createPrintProfile.compatiblePrinters')}
                required
                hint={t('createPrintProfile.compatiblePrintersHint')}
                labelMinHeightClassName="min-h-0"
              >
                <Dropdown
                  label=""
                  value=""
                  options={availableCompatiblePrinterOptions}
                  onChange={(value) => {
                    if (typeof value !== 'number') {
                      return;
                    }
                    const selectedPrinter = availablePrinterProfiles.find((printerProfile) => printerProfile.id === value);
                    if (!selectedPrinter) {
                      return;
                    }
                    setSelectedCompatiblePrinters((prev) => dedupeStringValues([...prev, selectedPrinter.name]));
                    setCompatiblePrinterSearch('');
                  }}
                  placeholder={printerProfilesQuery.isPending ? t('createPrintProfile.loadingCompatiblePrinters') : t('createPrintProfile.addCompatiblePrinter')}
                  filterable
                  filterValue={compatiblePrinterSearch}
                  onFilterChange={setCompatiblePrinterSearch}
                  emptyMessage={t('createPrintProfile.compatiblePrintersEmpty')}
                />
              </FormField>

              {selectedCompatiblePrinters.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {selectedCompatiblePrinters.map((printerName) => {
                    const isKnownPrinter = printerProfilesQuery.isPending || knownCompatiblePrinterNames.has(printerName);

                    return (
                      <span
                        key={printerName}
                        className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm ${
                          isKnownPrinter
                            ? 'border-purple-500/30 bg-purple-600/20 text-white'
                            : 'border-amber-500/30 bg-amber-500/10 text-amber-100'
                        }`}
                      >
                        <span>{printerName}</span>
                        {!isKnownPrinter && (
                          <span className="text-[10px] uppercase tracking-wide text-amber-200/80">
                            {t('createPrintProfile.unresolvedCompatiblePrinter')}
                          </span>
                        )}
                        <button
                          type="button"
                          onClick={() => setSelectedCompatiblePrinters((prev) => prev.filter((value) => value !== printerName))}
                          className="rounded p-0.5 text-inherit transition-colors hover:text-red-300"
                          title={t('createPrintProfile.removeCompatiblePrinter')}
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </span>
                    );
                  })}
                </div>
              )}

              {printerProfilesQuery.isError && (
                <p className="mt-2 text-xs text-amber-400">{t('createPrintProfile.compatiblePrintersLoadError')}</p>
              )}

              {!printerProfilesQuery.isPending && availablePrinterProfiles.length === 0 && selectedCompatiblePrinters.length === 0 && (
                <p className="mt-2 text-xs text-gray-400">{t('createPrintProfile.noCompatiblePrintersAvailable')}</p>
              )}
            </div>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <h3 className="text-sm font-semibold text-white">{t('createPrintProfile.structureSection')}</h3>
            <div className="mt-4 grid gap-4 md:grid-cols-3">
              <FormField label={t('createPrintProfile.wallLoops')}>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={wallLoops}
                  onChange={(event) => setWallLoops(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="2"
                />
              </FormField>
              <FormField label={t('createPrintProfile.topShellLayers')}>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={topShellLayers}
                  onChange={(event) => setTopShellLayers(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="3"
                />
              </FormField>
              <FormField label={t('createPrintProfile.bottomShellLayers')}>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={bottomShellLayers}
                  onChange={(event) => setBottomShellLayers(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="3"
                />
              </FormField>
            </div>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <h3 className="text-sm font-semibold text-white">{t('createPrintProfile.infillSection')}</h3>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <FormField label={t('createPrintProfile.infillDensity')}>
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="1"
                  value={infillDensity}
                  onChange={(event) => setInfillDensity(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="15"
                />
              </FormField>
              <FormField label={t('createPrintProfile.infillPattern')}>
                <select
                  value={infillPattern}
                  onChange={(event) => setInfillPattern(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white focus:border-purple-500 focus:outline-none"
                >
                  <option value="">{t('createPrintProfile.notSpecified')}</option>
                  {INFILL_PATTERN_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {t(`createPrintProfile.infillPatterns.${option}`)}
                    </option>
                  ))}
                </select>
              </FormField>
            </div>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <h3 className="text-sm font-semibold text-white">{t('createPrintProfile.speedSection')}</h3>
            <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <FormField label={t('createPrintProfile.outerWallSpeed')}>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={outerWallSpeed}
                  onChange={(event) => setOuterWallSpeed(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="200"
                />
              </FormField>
              <FormField label={t('createPrintProfile.innerWallSpeed')}>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={innerWallSpeed}
                  onChange={(event) => setInnerWallSpeed(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="300"
                />
              </FormField>
              <FormField label={t('createPrintProfile.infillSpeed')}>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={infillSpeed}
                  onChange={(event) => setInfillSpeed(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="270"
                />
              </FormField>
              <FormField label={t('createPrintProfile.travelSpeed')}>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={travelSpeed}
                  onChange={(event) => setTravelSpeed(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="500"
                />
              </FormField>
              <FormField label={t('createPrintProfile.initialLayerSpeed')}>
                <input
                  type="text"
                  value={initialLayerSpeed}
                  onChange={(event) => setInitialLayerSpeed(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="50 or 35%"
                />
              </FormField>
              <FormField label={t('createPrintProfile.initialLayerInfillSpeed')}>
                <input
                  type="text"
                  value={initialLayerInfillSpeed}
                  onChange={(event) => setInitialLayerInfillSpeed(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="105 or 35%"
                />
              </FormField>
              <FormField label={t('createPrintProfile.internalSolidInfillSpeed')}>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={internalSolidInfillSpeed}
                  onChange={(event) => setInternalSolidInfillSpeed(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="250"
                />
              </FormField>
              <FormField label={t('createPrintProfile.bridgeSpeed')}>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={bridgeSpeed}
                  onChange={(event) => setBridgeSpeed(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="50"
                />
              </FormField>
            </div>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <h3 className="text-sm font-semibold text-white">{t('createPrintProfile.accelerationSection')}</h3>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <FormField label={t('createPrintProfile.defaultAcceleration')}>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={defaultAcceleration}
                  onChange={(event) => setDefaultAcceleration(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="10000"
                />
              </FormField>
              <FormField label={t('createPrintProfile.travelAcceleration')}>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={travelAcceleration}
                  onChange={(event) => setTravelAcceleration(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="12000"
                />
              </FormField>
            </div>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <h3 className="text-sm font-semibold text-white">{t('createPrintProfile.supportSection')}</h3>
            <div className="mt-4 grid gap-4 md:grid-cols-3">
              <FormField label={t('createPrintProfile.enableSupport')}>
                <select
                  value={enableSupport}
                  onChange={(event) => {
                    const nextValue = event.target.value;
                    setEnableSupport(nextValue);
                    if (nextValue === '1' && !supportType) {
                      setSupportType('normal(auto)');
                    }
                  }}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white focus:border-purple-500 focus:outline-none"
                >
                  {BOOLEAN_OVERRIDE_OPTIONS.map((option) => (
                    <option key={option || 'inherit'} value={option}>
                      {t(`createPrintProfile.booleanOptions.${option || 'inherit'}`)}
                    </option>
                  ))}
                </select>
              </FormField>
              <FormField label={t('createPrintProfile.supportType')}>
                <select
                  value={supportType}
                  onChange={(event) => setSupportType(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white focus:border-purple-500 focus:outline-none"
                >
                  <option value="">{t('createPrintProfile.notSpecified')}</option>
                  {SUPPORT_TYPE_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {t(`createPrintProfile.supportTypes.${option}`)}
                    </option>
                  ))}
                </select>
              </FormField>
              <FormField
                label={t('createPrintProfile.supportThresholdAngle')}
                hint={!showSupportThresholdField ? t('createPrintProfile.supportThresholdAngleHint') : undefined}
              >
                <input
                  type="number"
                  min="0"
                  max="90"
                  step="1"
                  value={supportThresholdAngle}
                  onChange={(event) => setSupportThresholdAngle(event.target.value)}
                  disabled={!showSupportThresholdField}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                  placeholder="30"
                />
              </FormField>
            </div>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <h3 className="text-sm font-semibold text-white">{t('createPrintProfile.adhesionSection')}</h3>
            <div className="mt-4 grid gap-4 md:grid-cols-3">
              <FormField label={t('createPrintProfile.brimWidth')}>
                <input
                  type="number"
                  min="0"
                  step="0.1"
                  value={brimWidth}
                  onChange={(event) => setBrimWidth(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="5"
                />
              </FormField>
              <FormField label={t('createPrintProfile.skirtLoops')}>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={skirtLoops}
                  onChange={(event) => setSkirtLoops(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="0"
                />
              </FormField>
              <FormField label={t('createPrintProfile.raftLayers')}>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={raftLayers}
                  onChange={(event) => setRaftLayers(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="0"
                />
              </FormField>
            </div>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <h3 className="text-sm font-semibold text-white">{t('createPrintProfile.specialModesSection')}</h3>
            <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <FormField label={t('createPrintProfile.seamPosition')}>
                <select
                  value={seamPosition}
                  onChange={(event) => setSeamPosition(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white focus:border-purple-500 focus:outline-none"
                >
                  <option value="">{t('createPrintProfile.notSpecified')}</option>
                  {SEAM_POSITION_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {t(`createPrintProfile.seamPositions.${option}`)}
                    </option>
                  ))}
                </select>
              </FormField>
              <FormField label={t('createPrintProfile.ironingType')}>
                <select
                  value={ironingType}
                  onChange={(event) => setIroningType(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white focus:border-purple-500 focus:outline-none"
                >
                  <option value="">{t('createPrintProfile.notSpecified')}</option>
                  {IRONING_TYPE_OPTIONS.map((option) => (
                    <option key={option} value={option}>
                      {t(`createPrintProfile.ironingTypes.${option}`)}
                    </option>
                  ))}
                </select>
              </FormField>
              <FormField label={t('createPrintProfile.enableArcFitting')}>
                <select
                  value={enableArcFitting}
                  onChange={(event) => setEnableArcFitting(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white focus:border-purple-500 focus:outline-none"
                >
                  {BOOLEAN_OVERRIDE_OPTIONS.map((option) => (
                    <option key={option || 'inherit'} value={option}>
                      {t(`createPrintProfile.booleanOptions.${option || 'inherit'}`)}
                    </option>
                  ))}
                </select>
              </FormField>
              <FormField label={t('createPrintProfile.spiralMode')}>
                <select
                  value={spiralMode}
                  onChange={(event) => setSpiralMode(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white focus:border-purple-500 focus:outline-none"
                >
                  {BOOLEAN_OVERRIDE_OPTIONS.map((option) => (
                    <option key={option || 'inherit'} value={option}>
                      {t(`createPrintProfile.booleanOptions.${option || 'inherit'}`)}
                    </option>
                  ))}
                </select>
              </FormField>
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <FormField label={t('createPrintProfile.category')}>
              <input
                type="text"
                value={category}
                onChange={(event) => setCategory(event.target.value)}
                className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                placeholder={t('createPrintProfile.categoryPlaceholder')}
              />
            </FormField>

            <FormField label={t('createPrintProfile.description')}>
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                rows={3}
                className="w-full resize-none rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                placeholder={t('createPrintProfile.descriptionPlaceholder')}
              />
            </FormField>
          </div>

          <FormField label={t('createPrintProfile.notes')} labelMinHeightClassName="min-h-0">
            <textarea
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              rows={3}
              className="w-full resize-none rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
              placeholder={t('createPrintProfile.notesPlaceholder')}
            />
          </FormField>

          <div className="flex items-center justify-end gap-3 border-t border-white/10 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-white/20 px-6 py-2 text-gray-300 transition-all hover:bg-white/10"
            >
              {t('createPrintProfile.cancel')}
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending}
              className="flex items-center gap-2 rounded-lg bg-gradient-to-r from-purple-600 to-pink-600 px-6 py-2 text-white shadow-lg shadow-purple-500/25 transition-all hover:from-purple-700 hover:to-pink-700 hover:shadow-purple-500/40 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {createMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  {t('createPrintProfile.saving')}
                </>
              ) : (
                <>
                  <Save className="h-4 w-4" />
                  {profile ? t('createPrintProfile.saveChanges') : t('createPrintProfile.create')}
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
