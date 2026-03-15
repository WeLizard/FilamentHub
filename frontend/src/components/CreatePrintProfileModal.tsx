/** Modal for creating and editing Orca process profiles. */

import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Save, Loader2, Layers } from 'lucide-react';
import { ModalOverlay } from './ModalOverlay';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { filamentsAPI, printerProfilesAPI, printProfilesAPI } from '../api/client';
import {
  ORCA_ADVANCED_ENUM_OPTIONS,
  ORCA_ADVANCED_ENUM_LABELS,
  ORCA_ADVANCED_FIELD_DEFS,
  ORCA_ADVANCED_FIELD_KEYS,
  ORCA_ADVANCED_FIELD_LABELS,
  ORCA_STRUCTURED_TAB_ORDER,
  type OrcaStructuredFieldDef,
  type OrcaStructuredFieldTab,
} from './createPrintProfileOrcaFields';
import { Dropdown } from './Dropdown';
import { translateApiError } from '../utils/translateApiError';
import { useAuth } from '../contexts/AuthContext';
import type { Filament, PrintProfile, PrinterProfile } from '../types/api';

interface CreatePrintProfileModalProps {
  isOpen: boolean;
  onClose: () => void;
  profile?: PrintProfile | null;
  baseProfile?: PrintProfile | null;
  printerProfileContext?: PrinterProfile | null;
}

type PrintProfileTabKey = OrcaStructuredFieldTab;

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
const BOOLEAN_OVERRIDE_OPTIONS = ['0', '1'];
const DEFAULT_NOZZLE_SIZES = ['0.2', '0.25', '0.3', '0.4', '0.5', '0.6', '0.8', '1.0'];
const CORE_STRUCTURED_PROCESS_KEYS = new Set([
  'type',
  'name',
  'from',
  'instantiation',
  'inherits',
  'version',
  'print_settings_id',
  'setting_id',
  'fhub_id',
  'fhub_source',
  'default_nozzle_diameter',
  'layer_height',
  'initial_layer_print_height',
  'wall_loops',
  'top_shell_layers',
  'bottom_shell_layers',
  'sparse_infill_density',
  'sparse_infill_pattern',
  'initial_layer_speed',
  'initial_layer_infill_speed',
  'internal_solid_infill_speed',
  'bridge_speed',
  'outer_wall_speed',
  'inner_wall_speed',
  'sparse_infill_speed',
  'travel_speed',
  'default_acceleration',
  'travel_acceleration',
  'enable_support',
  'support_type',
  'support_threshold_angle',
  'brim_width',
  'skirt_loops',
  'raft_layers',
  'seam_position',
  'ironing_type',
  'enable_arc_fitting',
  'spiral_mode',
  'compatible_printers',
  'compatible_filaments',
  'compatible_printers_condition',
  'notes',
]);
const ADVANCED_PROCESS_EXCLUDED_KEYS = new Set([...CORE_STRUCTURED_PROCESS_KEYS, ...ORCA_ADVANCED_FIELD_KEYS]);

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

const stripPercentSuffix = (value: string): string => value.trim().replace(/%$/, '');

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

const normalizeComparableValue = (value: string): string =>
  value
    .trim()
    .replace(/\s+/g, ' ')
    .toLowerCase();

const qualityTierLabel = (value: string): string => QUALITY_TIER_LABELS[value.toLowerCase()] ?? value;

const titleCaseWord = (value: string): string =>
  value.length > 0 ? `${value.charAt(0).toUpperCase()}${value.slice(1)}` : value;

const humanizeOrcaValue = (value: string): string => {
  if (/^\d+$/.test(value)) {
    return value;
  }

  return value
    .split(/[_-]/g)
    .map((segment) => titleCaseWord(segment))
    .join(' ');
};

const humanizeOrcaFieldKey = (value: string): string =>
  value
    .split('_')
    .map((segment) => {
      const normalized = segment.toLowerCase();
      if (normalized === 'xy') {
        return 'XY';
      }
      if (normalized === 'z') {
        return 'Z';
      }
      if (normalized === 'mmu') {
        return 'MMU';
      }
      if (normalized === 'gcode') {
        return 'G-code';
      }
      return titleCaseWord(segment);
    })
    .join(' ');

const normalizeI18nKeyPart = (value: string): string =>
  value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');

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

const splitStructuredListInput = (value: string): string[] =>
  value
    .split(/\r?\n|,/g)
    .map((item) => item.trim())
    .filter((item) => item.length > 0);

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

const buildCompatibleFilamentValue = (filament: Filament): string =>
  filament.brand_name ? `${filament.name} @${filament.brand_name}` : filament.name;

const buildFilamentOptionLabel = (filament: Filament): string => {
  const parts = [filament.brand_name, filament.name, filament.material_type].filter(Boolean);
  return parts.join(' · ');
};

const pickAdvancedProcessSettings = (settings: Record<string, unknown> | undefined): Record<string, unknown> => {
  if (!settings) {
    return {};
  }

  const next: Record<string, unknown> = {};
  Object.entries(settings).forEach(([key, value]) => {
    if (ADVANCED_PROCESS_EXCLUDED_KEYS.has(key) || value === undefined) {
      return;
    }
    next[key] = value;
  });

  return next;
};

const readStructuredAdvancedFieldValue = (
  settings: Record<string, unknown> | undefined,
  field: OrcaStructuredFieldDef,
): string => {
  switch (field.kind) {
    case 'boolean':
      return readSettingBooleanString(settings, field.key);
    case 'integerList':
    case 'floatList':
    case 'stringList':
      return readSettingList(settings, field.key).join('\n');
    case 'percent':
      return stripPercentSuffix(readSettingString(settings, field.key));
    default:
      return readSettingString(settings, field.key);
  }
};

const buildStructuredAdvancedValues = (settings: Record<string, unknown> | undefined): Record<string, string> =>
  ORCA_ADVANCED_FIELD_DEFS.reduce<Record<string, string>>((acc, field) => {
    acc[field.key] = readStructuredAdvancedFieldValue(settings, field);
    return acc;
  }, {});

const normalizeStructuredAdvancedFieldValue = (field: OrcaStructuredFieldDef, rawValue: string): unknown => {
  switch (field.kind) {
    case 'boolean':
      return rawValue;
    case 'integer':
      return normalizeNumericString(rawValue);
    case 'float':
      return normalizeNumericString(rawValue);
    case 'percent':
      return normalizePercentString(rawValue);
    case 'floatOrPercent':
      return normalizeNumericOrPercentString(rawValue);
    case 'enum':
    case 'string':
      return rawValue.trim();
    case 'stringList': {
      const values = splitStructuredListInput(rawValue);
      return values;
    }
    case 'integerList': {
      const values = splitStructuredListInput(rawValue)
        .map((value) => normalizeNumericString(value))
        .filter((value) => value.length > 0)
        .map((value) => Number(value));
      return values;
    }
    case 'floatList': {
      const values = splitStructuredListInput(rawValue)
        .map((value) => normalizeNumericString(value))
        .filter((value) => value.length > 0)
        .map((value) => Number(value));
      return values;
    }
    default:
      return rawValue.trim();
  }
};

const buildStructuredAdvancedSettings = (values: Record<string, string>): Record<string, unknown> =>
  ORCA_ADVANCED_FIELD_DEFS.reduce<Record<string, unknown>>((acc, field) => {
    const normalized = normalizeStructuredAdvancedFieldValue(field, values[field.key] ?? '');

    if (Array.isArray(normalized)) {
      if (normalized.length > 0) {
        acc[field.key] = normalized;
      }
      return acc;
    }

    if (typeof normalized === 'string') {
      if (normalized.length > 0) {
        acc[field.key] = normalized;
      }
      return acc;
    }

    acc[field.key] = normalized;
    return acc;
  }, {});

const stripAdvancedProcessSettings = (settings: Record<string, unknown> | undefined): Record<string, unknown> => {
  if (!settings) {
    return {};
  }

  const next = { ...settings };
  Object.keys(pickAdvancedProcessSettings(settings)).forEach((key) => {
    delete next[key];
  });
  delete next.compatible_printers_condition;

  return next;
};

const sortJsonValue = (value: unknown): unknown => {
  if (Array.isArray(value)) {
    return value.map(sortJsonValue);
  }
  if (value && typeof value === 'object') {
    return Object.keys(value as Record<string, unknown>)
      .sort()
      .reduce<Record<string, unknown>>((acc, key) => {
        acc[key] = sortJsonValue((value as Record<string, unknown>)[key]);
        return acc;
      }, {});
  }
  return value;
};

const stableStringify = (value: unknown): string => JSON.stringify(sortJsonValue(value));

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

interface SectionCardProps {
  title: string;
  children: ReactNode;
}

const SectionCard: React.FC<SectionCardProps> = ({ title, children }) => (
  <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
    <h3 className="text-sm font-semibold text-white">{title}</h3>
    <div className="mt-4">{children}</div>
  </div>
);

export const CreatePrintProfileModal: React.FC<CreatePrintProfileModalProps> = ({
  isOpen,
  onClose,
  profile,
  baseProfile,
  printerProfileContext,
}) => {
  const { t, i18n } = useTranslation();
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
  const [selectedCompatibleFilaments, setSelectedCompatibleFilaments] = useState<string[]>([]);
  const [compatibleFilamentSearch, setCompatibleFilamentSearch] = useState('');
  const [compatiblePrintersCondition, setCompatiblePrintersCondition] = useState('');
  const [structuredAdvancedValues, setStructuredAdvancedValues] = useState<Record<string, string>>({});
  const [advancedSettings, setAdvancedSettings] = useState('');
  const [advancedSettingsError, setAdvancedSettingsError] = useState<string | null>(null);
  const [notes, setNotes] = useState('');
  const [nameManuallyChanged, setNameManuallyChanged] = useState(false);
  const [activeTab, setActiveTab] = useState<PrintProfileTabKey>('quality');

  const sourceProfile = profile ?? baseProfile ?? null;
  const sourceSettings = (sourceProfile?.orcaslicer_settings ?? {}) as Record<string, unknown>;

  const printerProfilesQuery = useQuery({
    queryKey: ['create-print-profile-modal', 'printer-profiles', user?.id],
    queryFn: () =>
      printerProfilesAPI.list({
        owner_user_id: user?.id,
        active_only: true,
        size: 100,
      }),
    enabled: isOpen && Boolean(user?.id),
    staleTime: 60_000,
  });

  const filamentsQuery = useQuery({
    queryKey: ['create-print-profile-modal', 'filaments'],
    queryFn: () =>
      filamentsAPI.list({
        active_only: true,
        size: 100,
      }),
    enabled: isOpen,
    staleTime: 60_000,
  });

  const availablePrinterProfiles = printerProfilesQuery.data?.items ?? [];
  const availableFilaments = filamentsQuery.data?.items ?? [];
  const recommendedPrinterTag = selectedCompatiblePrinters[0] || printerProfileContext?.name || 'FilamentHub';
  const recommendedName =
    !profile && !baseProfile && layerHeight.trim() && qualityTier.trim()
      ? buildRecommendedName(layerHeight, qualityTier, recommendedPrinterTag)
      : '';
  const normalizedSelectedCompatiblePrinterNames = new Set(
    selectedCompatiblePrinters.map(normalizeComparableValue),
  );
  const availableCompatiblePrinterOptions = availablePrinterProfiles
    .filter((printerProfile) => !normalizedSelectedCompatiblePrinterNames.has(normalizeComparableValue(printerProfile.name)))
    .map((printerProfile) => ({
      value: printerProfile.id,
      label: buildPrinterProfileOptionLabel(printerProfile),
    }));
  const knownCompatiblePrinterNames = new Set(
    availablePrinterProfiles.map((printerProfile) => normalizeComparableValue(printerProfile.name)),
  );
  const normalizedSelectedCompatibleFilamentNames = new Set(
    selectedCompatibleFilaments.map(normalizeComparableValue),
  );
  const availableCompatibleFilamentOptions = availableFilaments
    .filter(
      (filament) =>
        !normalizedSelectedCompatibleFilamentNames.has(
          normalizeComparableValue(buildCompatibleFilamentValue(filament)),
        ),
    )
    .map((filament) => ({
      value: filament.id,
      label: buildFilamentOptionLabel(filament),
    }));
  const knownCompatibleFilamentNames = new Set(
    availableFilaments.map((filament) => normalizeComparableValue(buildCompatibleFilamentValue(filament))),
  );
  const showSupportThresholdField = enableSupport === '1' && supportType.includes('(auto)');
  const structuredFieldsByTabAndSection = useMemo(() => {
    const next = new Map<string, OrcaStructuredFieldDef[]>();

    ORCA_ADVANCED_FIELD_DEFS.forEach((field) => {
      const mapKey = `${field.tab}:${field.section}`;
      const existing = next.get(mapKey);
      if (existing) {
        existing.push(field);
      } else {
        next.set(mapKey, [field]);
      }
    });

    return next;
  }, []);

  useEffect(() => {
    if (isOpen) {
      setNameManuallyChanged(false);
      setActiveTab('quality');
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
    const nextCompatibleFilaments = dedupeStringValues([
      ...(sourceProfile?.compatible_filaments?.filter(Boolean) ?? []),
      ...readSettingList(sourceSettings, 'compatible_filaments'),
    ]);
    const contextNozzle =
      printerProfileContext?.nozzle_diameters?.[0] != null ? String(printerProfileContext.nozzle_diameters[0]) : '';
    const fallbackCompatiblePrinters =
      nextCompatiblePrinters.length > 0
        ? nextCompatiblePrinters
        : printerProfileContext?.name
          ? [printerProfileContext.name]
          : [];
    const sourceExtraMetadata =
      sourceProfile?.extra_metadata && typeof sourceProfile.extra_metadata === 'object' ? sourceProfile.extra_metadata : null;
    const nextCompatiblePrintersCondition =
      typeof sourceExtraMetadata?.compatible_printers_condition === 'string'
        ? sourceExtraMetadata.compatible_printers_condition
        : readSettingString(sourceSettings, 'compatible_printers_condition');
    const nextAdvancedSettings = pickAdvancedProcessSettings(sourceSettings);
    const nextStructuredAdvancedValues = buildStructuredAdvancedValues(sourceSettings);

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
      setSelectedCompatibleFilaments(nextCompatibleFilaments);
      setCompatibleFilamentSearch('');
      setCompatiblePrintersCondition(nextCompatiblePrintersCondition);
      setStructuredAdvancedValues(nextStructuredAdvancedValues);
      setAdvancedSettings(Object.keys(nextAdvancedSettings).length ? JSON.stringify(nextAdvancedSettings, null, 2) : '');
      setAdvancedSettingsError(null);
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
      setSelectedCompatibleFilaments(nextCompatibleFilaments);
      setCompatibleFilamentSearch('');
      setCompatiblePrintersCondition(nextCompatiblePrintersCondition);
      setStructuredAdvancedValues(nextStructuredAdvancedValues);
      setAdvancedSettings(Object.keys(nextAdvancedSettings).length ? JSON.stringify(nextAdvancedSettings, null, 2) : '');
      setAdvancedSettingsError(null);
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
    setSelectedCompatibleFilaments([]);
    setCompatibleFilamentSearch('');
    setCompatiblePrintersCondition('');
    setStructuredAdvancedValues(buildStructuredAdvancedValues(undefined));
    setAdvancedSettings('');
    setAdvancedSettingsError(null);
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
    const compatibleFilaments = dedupeStringValues(selectedCompatibleFilaments);
    const compatiblePrintersConditionValue = compatiblePrintersCondition.trim();

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

    let advancedSettingsObject: Record<string, unknown> = {};
    if (advancedSettings.trim()) {
      try {
        const parsed = JSON.parse(advancedSettings);
        if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
          throw new Error('advanced settings must be an object');
        }
        advancedSettingsObject = pickAdvancedProcessSettings(parsed as Record<string, unknown>);
        setAdvancedSettingsError(null);
      } catch (error) {
        console.error('Invalid advanced process settings JSON', error);
        setAdvancedSettingsError(t('createPrintProfile.jsonInvalid'));
        return;
      }
    } else {
      setAdvancedSettingsError(null);
    }

    const structuredAdvancedSettingsObject = buildStructuredAdvancedSettings(structuredAdvancedValues);

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
    const extraMetadataBase =
      sourceProfile?.extra_metadata && typeof sourceProfile.extra_metadata === 'object'
        ? { ...(sourceProfile.extra_metadata as Record<string, unknown>) }
        : {};
    const nextExtraMetadata = { ...extraMetadataBase };

    if (compatiblePrintersConditionValue) {
      nextExtraMetadata.compatible_printers_condition = compatiblePrintersConditionValue;
    } else {
      delete nextExtraMetadata.compatible_printers_condition;
    }

    const mergedSettings: Record<string, unknown> = {
      ...stripAdvancedProcessSettings(sourceSettings),
      ...structuredAdvancedSettingsObject,
      ...advancedSettingsObject,
      type: 'process',
      name: trimmedName,
      from: profileSource,
      instantiation: 'true',
      inherits: readSettingString(sourceSettings, 'inherits') || DEFAULT_PROCESS_BASE,
      version: readSettingString(sourceSettings, 'version') || DEFAULT_PROCESS_VERSION,
      print_settings_id: readSettingString(sourceSettings, 'print_settings_id') || trimmedName,
      compatible_printers: compatiblePrinters,
    };
    delete mergedSettings.compatible_printers_condition;

    const setOrDelete = (key: string, value: string) => {
      if (value) {
        mergedSettings[key] = value;
      } else {
        delete mergedSettings[key];
      }
    };

    const setOrDeleteList = (key: string, values: string[]) => {
      if (values.length > 0) {
        mergedSettings[key] = values;
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
    setOrDelete('notes', notes.trim());
    setOrDeleteList('compatible_filaments', compatibleFilaments);

    const data: Parameters<typeof printProfilesAPI.create>[0] = {
      name: trimmedName,
      slug: trimmedSlug,
      description: description.trim() || null,
      category: category.trim() || null,
      quality_tier: qualityTier.trim() || null,
      default_nozzle: defaultNozzle.trim() || null,
      layer_height_mm: layerHeightValue ? Number(layerHeightValue) : null,
      compatible_printers: compatiblePrinters,
      compatible_filaments: compatibleFilaments.length > 0 ? compatibleFilaments : null,
      extra_metadata: Object.keys(nextExtraMetadata).length > 0 ? nextExtraMetadata : null,
      notes: notes.trim() || null,
      active: true,
      source: profileSource,
      vendor: profile?.vendor ?? baseProfile?.vendor ?? printerProfileContext?.vendor ?? null,
      orcaslicer_settings: mergedSettings,
    };

    if (!profile && baseProfile) {
      const baseSettings = (baseProfile.orcaslicer_settings ?? {}) as Record<string, unknown>;
      const normalizedBaseCompatiblePrinters = Array.from(
        new Set([
          ...(baseProfile.compatible_printers?.filter(Boolean) ?? []),
          ...readSettingList(baseSettings, 'compatible_printers'),
        ]),
      ).sort();
      const normalizedCurrentCompatiblePrinters = [...compatiblePrinters].sort();
      const normalizedBaseCompatibleFilaments = dedupeStringValues([
        ...(baseProfile.compatible_filaments?.filter(Boolean) ?? []),
        ...readSettingList(baseSettings, 'compatible_filaments'),
      ]).sort();
      const normalizedCurrentCompatibleFilaments = [...compatibleFilaments].sort();
      const baseCompatiblePrintersCondition =
        typeof baseProfile.extra_metadata?.compatible_printers_condition === 'string'
          ? baseProfile.extra_metadata.compatible_printers_condition.trim()
          : readSettingString(baseSettings, 'compatible_printers_condition');
      const baseAdvancedSettings = pickAdvancedProcessSettings(baseSettings);
      const baseStructuredAdvancedSettings = buildStructuredAdvancedSettings(buildStructuredAdvancedValues(baseSettings));
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
        notes: baseProfile.notes ?? readSettingString(baseSettings, 'notes'),
        compatiblePrintersCondition: baseCompatiblePrintersCondition,
        structuredAdvancedSettings: stableStringify(baseStructuredAdvancedSettings),
        advancedSettings: stableStringify(baseAdvancedSettings),
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
        notes: notes.trim(),
        compatiblePrintersCondition: compatiblePrintersConditionValue,
        structuredAdvancedSettings: stableStringify(structuredAdvancedSettingsObject),
        advancedSettings: stableStringify(advancedSettingsObject),
      };

      const isIdenticalClone =
        Object.entries(currentComparableValues).every(([key, value]) => baseComparableValues[key as keyof typeof baseComparableValues] === value) &&
        areStringArraysEqual(normalizedBaseCompatiblePrinters, normalizedCurrentCompatiblePrinters) &&
        areStringArraysEqual(normalizedBaseCompatibleFilaments, normalizedCurrentCompatibleFilaments);

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
  const setStructuredAdvancedFieldValue = (key: string, value: string) => {
    setStructuredAdvancedValues((prev) => ({
      ...prev,
      [key]: value,
    }));
  };
  const getBooleanOverrideLabel = (option: string) => t(`createPrintProfile.booleanOptions.${option}`);
  const getBooleanSelectValue = (value: string) => (value === '1' ? '1' : '0');
  const structuredLabelLocale = i18n.resolvedLanguage?.startsWith('ru') ? 'ru' : 'en';
  const getStructuredFieldLabel = (fieldKey: string) =>
    t(`createPrintProfile.fieldLabels.${fieldKey}`, {
      defaultValue: ORCA_ADVANCED_FIELD_LABELS[fieldKey]?.[structuredLabelLocale] ?? humanizeOrcaFieldKey(fieldKey),
    });
  const getStructuredEnumLabel = (fieldKey: string, option: string) =>
    t(`createPrintProfile.fieldValues.${fieldKey}.${normalizeI18nKeyPart(option)}`, {
      defaultValue: ORCA_ADVANCED_ENUM_LABELS[fieldKey]?.[option]?.[structuredLabelLocale] ?? humanizeOrcaValue(option),
    });
  const renderStructuredAdvancedField = (field: OrcaStructuredFieldDef) => {
    const value = structuredAdvancedValues[field.key] ?? '';
    const enumOptions = ORCA_ADVANCED_ENUM_OPTIONS[field.key] ?? [];
    const label = getStructuredFieldLabel(field.key);
    const commonClassName =
      'w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none';
    const commonHint =
      field.kind === 'stringList' || field.kind === 'integerList' || field.kind === 'floatList'
        ? t('createPrintProfile.structuredListHint')
        : undefined;

    let control: ReactNode;
    switch (field.kind) {
      case 'boolean':
        control = (
          <select
            value={getBooleanSelectValue(value)}
            onChange={(event) => setStructuredAdvancedFieldValue(field.key, event.target.value)}
            className={commonClassName}
          >
            {BOOLEAN_OVERRIDE_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {getBooleanOverrideLabel(option)}
              </option>
            ))}
          </select>
        );
        break;
      case 'enum':
        control = (
          <select
            value={value}
            onChange={(event) => setStructuredAdvancedFieldValue(field.key, event.target.value)}
            className={commonClassName}
          >
            <option value="">{t('createPrintProfile.notSpecified')}</option>
            {enumOptions.map((option) => (
              <option key={option} value={option}>
                {getStructuredEnumLabel(field.key, option)}
              </option>
            ))}
          </select>
        );
        break;
      case 'integer':
        control = (
          <input
            type="number"
            step="1"
            value={value}
            onChange={(event) => setStructuredAdvancedFieldValue(field.key, event.target.value)}
            className={commonClassName}
          />
        );
        break;
      case 'float':
        control = (
          <input
            type="number"
            step="0.01"
            value={value}
            onChange={(event) => setStructuredAdvancedFieldValue(field.key, event.target.value)}
            className={commonClassName}
          />
        );
        break;
      case 'percent':
        control = (
          <input
            type="number"
            step="0.01"
            value={value}
            onChange={(event) => setStructuredAdvancedFieldValue(field.key, event.target.value)}
            className={commonClassName}
            placeholder="0-100"
          />
        );
        break;
      case 'floatOrPercent':
        control = (
          <input
            type="text"
            value={value}
            onChange={(event) => setStructuredAdvancedFieldValue(field.key, event.target.value)}
            className={commonClassName}
            placeholder="20 or 35%"
          />
        );
        break;
      case 'string':
        control = (
          <input
            type="text"
            value={value}
            onChange={(event) => setStructuredAdvancedFieldValue(field.key, event.target.value)}
            className={commonClassName}
          />
        );
        break;
      case 'stringList':
      case 'integerList':
      case 'floatList':
        control = (
          <textarea
            value={value}
            onChange={(event) => setStructuredAdvancedFieldValue(field.key, event.target.value)}
            rows={3}
            className={`${commonClassName} resize-y font-mono text-sm`}
            placeholder={t('createPrintProfile.structuredListPlaceholder')}
          />
        );
        break;
      default:
        control = (
          <input
            type="text"
            value={value}
            onChange={(event) => setStructuredAdvancedFieldValue(field.key, event.target.value)}
            className={commonClassName}
          />
        );
        break;
    }

    return (
      <FormField
        key={field.key}
        label={label}
        hint={commonHint}
        labelMinHeightClassName="min-h-0"
        className="min-w-0"
      >
        {control}
      </FormField>
    );
  };
  const getStructuredFields = (tab: PrintProfileTabKey, section: string): OrcaStructuredFieldDef[] =>
    structuredFieldsByTabAndSection.get(`${tab}:${section}`) ?? [];

  const renderStructuredSectionCard = (
    tab: PrintProfileTabKey,
    section: string,
    coreContent?: ReactNode,
    gridClassName = 'grid gap-4 md:grid-cols-2 xl:grid-cols-3',
  ) => {
    const fields = getStructuredFields(tab, section);
    const hasCoreContent = coreContent !== undefined && coreContent !== null;

    if (!hasCoreContent && fields.length === 0) {
      return null;
    }

    return (
      <SectionCard key={`${tab}-${section}`} title={t(`createPrintProfile.sections.${section}`)}>
        {hasCoreContent ? coreContent : null}
        {fields.length > 0 ? (
          <div className={hasCoreContent ? 'mt-4 border-t border-white/10 pt-4' : ''}>
            <div className={gridClassName}>{fields.map((field) => renderStructuredAdvancedField(field))}</div>
          </div>
        ) : null}
      </SectionCard>
    );
  };

  const renderQualityTab = () => (
    <div className="space-y-6">
      {renderStructuredSectionCard(
        'quality',
        'layerHeight',
        <div className="grid gap-4 md:grid-cols-2">
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
        </div>,
        'grid gap-4 md:grid-cols-2',
      )}
      {renderStructuredSectionCard('quality', 'lineWidth', undefined, 'grid gap-4 md:grid-cols-2 xl:grid-cols-3')}
      {renderStructuredSectionCard(
        'quality',
        'seam',
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
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
        </div>,
      )}
      {renderStructuredSectionCard(
        'quality',
        'precision',
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <FormField label={t('createPrintProfile.enableArcFitting')}>
            <select
              value={getBooleanSelectValue(enableArcFitting)}
              onChange={(event) => setEnableArcFitting(event.target.value)}
              className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white focus:border-purple-500 focus:outline-none"
            >
              {BOOLEAN_OVERRIDE_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {getBooleanOverrideLabel(option)}
                </option>
              ))}
            </select>
          </FormField>
        </div>,
      )}
      {renderStructuredSectionCard(
        'quality',
        'ironing',
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
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
        </div>,
      )}
      {renderStructuredSectionCard('quality', 'wallGenerator')}
      {renderStructuredSectionCard('quality', 'wallsAndSurfaces')}
      {renderStructuredSectionCard('quality', 'bridging')}
      {renderStructuredSectionCard('quality', 'overhangs')}
    </div>
  );

  const renderStrengthTab = () => (
    <div className="space-y-6">
      {renderStructuredSectionCard(
        'strength',
        'walls',
        <div className="grid gap-4 md:grid-cols-3">
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
        </div>,
      )}
      {renderStructuredSectionCard(
        'strength',
        'topBottomShells',
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
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
        </div>,
      )}
      {renderStructuredSectionCard(
        'strength',
        'infill',
        <div className="grid gap-4 md:grid-cols-2">
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
        </div>,
      )}
      {renderStructuredSectionCard('strength', 'advanced')}
    </div>
  );

  const renderSpeedTab = () => (
    <div className="space-y-6">
      {renderStructuredSectionCard(
        'speed',
        'initialLayerSpeed',
        <div className="grid gap-4 md:grid-cols-2">
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
        </div>,
      )}
      {renderStructuredSectionCard(
        'speed',
        'otherLayersSpeed',
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
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
        </div>,
      )}
      {renderStructuredSectionCard(
        'speed',
        'overhangSpeed',
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
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
        </div>,
      )}
      {renderStructuredSectionCard(
        'speed',
        'travelSpeed',
        <div className="grid gap-4 md:grid-cols-2">
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
        </div>,
      )}
      {renderStructuredSectionCard(
        'speed',
        'acceleration',
        <div className="grid gap-4 md:grid-cols-2">
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
        </div>,
      )}
      {renderStructuredSectionCard('speed', 'jerk')}
      {renderStructuredSectionCard('speed', 'advanced')}
    </div>
  );

  const renderSupportTab = () => (
    <div className="space-y-6">
      {renderStructuredSectionCard(
        'support',
        'support',
        <div className="grid gap-4 md:grid-cols-3">
          <FormField label={t('createPrintProfile.enableSupport')}>
            <select
              value={getBooleanSelectValue(enableSupport)}
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
                <option key={option} value={option}>
                  {getBooleanOverrideLabel(option)}
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
        </div>,
      )}
      {renderStructuredSectionCard(
        'support',
        'raft',
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
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
        </div>,
      )}
      {renderStructuredSectionCard('support', 'supportFilament')}
      {renderStructuredSectionCard('support', 'supportIroning')}
      {renderStructuredSectionCard('support', 'advanced')}
      {renderStructuredSectionCard('support', 'treeSupports')}
    </div>
  );

  const renderMultimaterialTab = () => (
    <div className="space-y-6">
      {renderStructuredSectionCard('multimaterial', 'primeTower')}
      {renderStructuredSectionCard('multimaterial', 'featureFilaments')}
      {renderStructuredSectionCard('multimaterial', 'oozePrevention')}
      {renderStructuredSectionCard('multimaterial', 'flushOptions')}
      {renderStructuredSectionCard('multimaterial', 'advanced')}
    </div>
  );

  const renderOthersTab = () => (
    <div className="space-y-6">
      {renderStructuredSectionCard(
        'others',
        'skirt',
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
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
        </div>,
      )}
      {renderStructuredSectionCard(
        'others',
        'brim',
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
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
        </div>,
      )}
      {renderStructuredSectionCard(
        'others',
        'specialMode',
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <FormField label={t('createPrintProfile.spiralMode')}>
            <select
              value={getBooleanSelectValue(spiralMode)}
              onChange={(event) => setSpiralMode(event.target.value)}
              className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white focus:border-purple-500 focus:outline-none"
            >
              {BOOLEAN_OVERRIDE_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {getBooleanOverrideLabel(option)}
                </option>
              ))}
            </select>
          </FormField>
        </div>,
      )}
      {renderStructuredSectionCard('others', 'fuzzySkin')}
      {renderStructuredSectionCard('others', 'gcodeOutput')}
      {renderStructuredSectionCard('others', 'postProcessing')}
      {renderStructuredSectionCard(
        'others',
        'notes',
        <FormField label={t('createPrintProfile.notes')} labelMinHeightClassName="min-h-0">
          <textarea
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            rows={5}
            className="w-full resize-none rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
            placeholder={t('createPrintProfile.notesPlaceholder')}
          />
        </FormField>,
        'grid gap-4',
      )}
    </div>
  );

  return (
    <ModalOverlay onClose={onClose} className="!bg-black/80">
      <div className="flex max-h-[90vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-white/20 bg-gradient-to-br from-gray-900 to-gray-800 shadow-2xl" onClick={(e) => e.stopPropagation()}>
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
          <SectionCard title={t('createPrintProfile.profileMetaSection')}>
            {printerProfileContext && (
              <div className="mb-6 rounded-xl border border-cyan-500/20 bg-cyan-500/10 px-4 py-3 text-sm text-cyan-100">
                {t('createPrintProfile.contextPrinter')}: <span className="font-medium text-white">{printerProfileContext.name}</span>
              </div>
            )}

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
                hint={
                  recommendedName && name && name.trim() !== recommendedName
                    ? `${t('createPrintProfile.recommendedFormatHint')}: "${recommendedName}"`
                    : undefined
                }
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

            <div className="mt-6 grid gap-6 lg:grid-cols-4">
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

              <FormField label={t('createPrintProfile.category')}>
                <input
                  type="text"
                  value={category}
                  onChange={(event) => setCategory(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder={t('createPrintProfile.categoryPlaceholder')}
                />
              </FormField>
            </div>

            <div className="mt-6">
              <FormField label={t('createPrintProfile.description')} labelMinHeightClassName="min-h-0">
                <textarea
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  rows={3}
                  className="w-full resize-none rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder={t('createPrintProfile.descriptionPlaceholder')}
                />
              </FormField>
            </div>
          </SectionCard>

          <SectionCard title={t('createPrintProfile.compatibilitySection')}>
            <div className="grid gap-6 xl:grid-cols-2">
              <div>
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
                    placeholder={
                      printerProfilesQuery.isPending
                        ? t('createPrintProfile.loadingCompatiblePrinters')
                        : t('createPrintProfile.addCompatiblePrinter')
                    }
                    filterable
                    filterValue={compatiblePrinterSearch}
                    onFilterChange={setCompatiblePrinterSearch}
                    emptyMessage={t('createPrintProfile.compatiblePrintersEmpty')}
                  />
                </FormField>

                {selectedCompatiblePrinters.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {selectedCompatiblePrinters.map((printerName) => {
                      const isKnownPrinter =
                        printerProfilesQuery.isPending ||
                        knownCompatiblePrinterNames.has(normalizeComparableValue(printerName));

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
                            <span className="rounded-full border border-amber-400/20 bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-100">
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

              <div>
                <FormField
                  label={t('createPrintProfile.compatibleFilaments')}
                  hint={t('createPrintProfile.compatibleFilamentsHint')}
                  labelMinHeightClassName="min-h-0"
                >
                  <Dropdown
                    label=""
                    value=""
                    options={availableCompatibleFilamentOptions}
                    onChange={(value) => {
                      if (typeof value !== 'number') {
                        return;
                      }
                      const selectedFilament = availableFilaments.find((filament) => filament.id === value);
                      if (!selectedFilament) {
                        return;
                      }
                      setSelectedCompatibleFilaments((prev) =>
                        dedupeStringValues([...prev, buildCompatibleFilamentValue(selectedFilament)]),
                      );
                      setCompatibleFilamentSearch('');
                    }}
                    placeholder={
                      filamentsQuery.isPending
                        ? t('createPrintProfile.loadingCompatibleFilaments')
                        : t('createPrintProfile.addCompatibleFilament')
                    }
                    filterable
                    filterValue={compatibleFilamentSearch}
                    onFilterChange={setCompatibleFilamentSearch}
                    emptyMessage={t('createPrintProfile.compatibleFilamentsEmpty')}
                  />
                </FormField>

                {selectedCompatibleFilaments.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    {selectedCompatibleFilaments.map((filamentName) => {
                      const isKnownFilament =
                        filamentsQuery.isPending ||
                        knownCompatibleFilamentNames.has(normalizeComparableValue(filamentName));

                      return (
                        <span
                          key={filamentName}
                          className={`flex items-center gap-2 rounded-lg border px-3 py-1.5 text-sm ${
                            isKnownFilament
                              ? 'border-cyan-500/30 bg-cyan-600/20 text-white'
                              : 'border-amber-500/30 bg-amber-500/10 text-amber-100'
                          }`}
                        >
                          <span>{filamentName}</span>
                          {!isKnownFilament && (
                            <span className="rounded-full border border-amber-400/20 bg-amber-500/15 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-100">
                              {t('createPrintProfile.unresolvedCompatibleFilament')}
                            </span>
                          )}
                          <button
                            type="button"
                            onClick={() => setSelectedCompatibleFilaments((prev) => prev.filter((value) => value !== filamentName))}
                            className="rounded p-0.5 text-inherit transition-colors hover:text-red-300"
                            title={t('createPrintProfile.removeCompatibleFilament')}
                          >
                            <X className="h-4 w-4" />
                          </button>
                        </span>
                      );
                    })}
                  </div>
                )}

                {filamentsQuery.isError && (
                  <p className="mt-2 text-xs text-amber-400">{t('createPrintProfile.compatibleFilamentsLoadError')}</p>
                )}

                {!filamentsQuery.isPending && availableFilaments.length === 0 && selectedCompatibleFilaments.length === 0 && (
                  <p className="mt-2 text-xs text-gray-400">{t('createPrintProfile.noCompatibleFilamentsAvailable')}</p>
                )}
              </div>
            </div>

            <div className="mt-6">
              <FormField
                label={t('createPrintProfile.compatiblePrintersCondition')}
                hint={t('createPrintProfile.compatiblePrintersConditionHint')}
                labelMinHeightClassName="min-h-0"
              >
                <textarea
                  value={compatiblePrintersCondition}
                  onChange={(event) => setCompatiblePrintersCondition(event.target.value)}
                  rows={2}
                  className="w-full resize-none rounded-lg border border-white/10 bg-white/5 px-4 py-2 font-mono text-sm text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="printer_notes=~/.*0.4 nozzle.*/ and nozzle_diameter[0]==0.4"
                />
              </FormField>
            </div>
          </SectionCard>

          <div className="rounded-xl border border-white/10 bg-white/[0.03]">
            <div className="flex flex-wrap gap-2 border-b border-white/10 px-4 pt-4">
              {ORCA_STRUCTURED_TAB_ORDER.map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setActiveTab(tab)}
                  className={`rounded-t-lg px-4 py-2 text-sm font-medium transition-all ${
                    activeTab === tab
                      ? 'border-b-2 border-purple-500 bg-white/10 text-white'
                      : 'text-gray-400 hover:bg-white/5 hover:text-white'
                  }`}
                >
                  {t(`createPrintProfile.tabs.${tab}`)}
                </button>
              ))}
            </div>

            <div className="space-y-6 p-4">
              <div>
                <div>
                  <h3 className="text-sm font-semibold text-white">{t(`createPrintProfile.tabs.${activeTab}`)}</h3>
                  <p className="mt-1 text-xs leading-relaxed text-gray-400">{t(`createPrintProfile.tabDescriptions.${activeTab}`)}</p>
                </div>
              </div>

              {activeTab === 'quality' && renderQualityTab()}
              {activeTab === 'strength' && renderStrengthTab()}
              {activeTab === 'speed' && renderSpeedTab()}
              {activeTab === 'support' && renderSupportTab()}
              {activeTab === 'multimaterial' && renderMultimaterialTab()}
              {activeTab === 'others' && renderOthersTab()}
            </div>
          </div>

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
    </ModalOverlay>
  );
};
