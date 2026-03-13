/** Modal for creating and editing Orca process profiles. */

import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Save, Loader2, Layers } from 'lucide-react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { printProfilesAPI } from '../api/client';
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

const INFILL_PATTERN_OPTIONS = ['crosshatch', 'gyroid', 'grid', 'rectilinear', 'cubic'];
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

const normalizeCompatiblePrinters = (value: string): string[] =>
  Array.from(
    new Set(
      value
        .split(/[\r\n,]+/)
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
  const [outerWallSpeed, setOuterWallSpeed] = useState('');
  const [innerWallSpeed, setInnerWallSpeed] = useState('');
  const [infillSpeed, setInfillSpeed] = useState('');
  const [travelSpeed, setTravelSpeed] = useState('');
  const [compatiblePrintersInput, setCompatiblePrintersInput] = useState('');
  const [notes, setNotes] = useState('');
  const [nameManuallyChanged, setNameManuallyChanged] = useState(false);

  const sourceProfile = profile ?? baseProfile ?? null;
  const sourceSettings = (sourceProfile?.orcaslicer_settings ?? {}) as Record<string, unknown>;

  const compatiblePrinterNames = normalizeCompatiblePrinters(compatiblePrintersInput);
  const recommendedPrinterTag = compatiblePrinterNames[0] || printerProfileContext?.name || 'FilamentHub';
  const recommendedName =
    !profile && !baseProfile && layerHeight.trim() && qualityTier.trim()
      ? buildRecommendedName(layerHeight, qualityTier, recommendedPrinterTag)
      : '';

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

    const nextCompatiblePrinters = [
      ...(sourceProfile?.compatible_printers?.filter(Boolean) ?? []),
      ...readSettingList(sourceSettings, 'compatible_printers'),
    ];
    const uniqueCompatiblePrinters = Array.from(new Set(nextCompatiblePrinters));
    const contextNozzle =
      printerProfileContext?.nozzle_diameters?.[0] != null ? String(printerProfileContext.nozzle_diameters[0]) : '';

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
      setOuterWallSpeed(readSettingString(sourceSettings, 'outer_wall_speed'));
      setInnerWallSpeed(readSettingString(sourceSettings, 'inner_wall_speed'));
      setInfillSpeed(readSettingString(sourceSettings, 'sparse_infill_speed'));
      setTravelSpeed(readSettingString(sourceSettings, 'travel_speed'));
      setCompatiblePrintersInput(uniqueCompatiblePrinters.join('\n'));
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
      setOuterWallSpeed(readSettingString(sourceSettings, 'outer_wall_speed'));
      setInnerWallSpeed(readSettingString(sourceSettings, 'inner_wall_speed'));
      setInfillSpeed(readSettingString(sourceSettings, 'sparse_infill_speed'));
      setTravelSpeed(readSettingString(sourceSettings, 'travel_speed'));
      setCompatiblePrintersInput(
        (uniqueCompatiblePrinters.length > 0 ? uniqueCompatiblePrinters : printerProfileContext?.name ? [printerProfileContext.name] : []).join('\n'),
      );
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
    setOuterWallSpeed('');
    setInnerWallSpeed('');
    setInfillSpeed('');
    setTravelSpeed('');
    setCompatiblePrintersInput(printerProfileContext?.name || '');
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
    const compatiblePrinters = normalizeCompatiblePrinters(compatiblePrintersInput);

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
    const outerWallSpeedValue = normalizeNumericString(outerWallSpeed);
    const innerWallSpeedValue = normalizeNumericString(innerWallSpeed);
    const infillSpeedValue = normalizeNumericString(infillSpeed);
    const travelSpeedValue = normalizeNumericString(travelSpeed);
    const profileSource = profile?.source === 'system' ? 'system' : 'user';

    const mergedSettings: Record<string, unknown> = {
      ...sourceSettings,
      type: 'process',
      name: trimmedName,
      from: profileSource,
      instantiation: 'true',
      inherits: readSettingString(sourceSettings, 'inherits') || DEFAULT_PROCESS_BASE,
      version: readSettingString(sourceSettings, 'version') || DEFAULT_PROCESS_VERSION,
      print_settings_id: trimmedName,
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
    setOrDelete('outer_wall_speed', outerWallSpeedValue);
    setOrDelete('inner_wall_speed', innerWallSpeedValue);
    setOrDelete('sparse_infill_speed', infillSpeedValue);
    setOrDelete('travel_speed', travelSpeedValue);

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
        outerWallSpeed: readSettingString(baseSettings, 'outer_wall_speed'),
        innerWallSpeed: readSettingString(baseSettings, 'inner_wall_speed'),
        infillSpeed: readSettingString(baseSettings, 'sparse_infill_speed'),
        travelSpeed: readSettingString(baseSettings, 'travel_speed'),
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
        outerWallSpeed: outerWallSpeedValue,
        innerWallSpeed: innerWallSpeedValue,
        infillSpeed: infillSpeedValue,
        travelSpeed: travelSpeedValue,
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
            <div>
              <label className="mb-2 block text-sm font-medium text-gray-300">
                {t('createPrintProfile.name')} <span className="text-red-400">*</span>
                {recommendedName && (
                  <span className="ml-2 text-xs text-gray-400">
                    ({t('createPrintProfile.recommendedFormat')}: &quot;{recommendedName}&quot;)
                  </span>
                )}
              </label>
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
              {recommendedName && name && name.trim() !== recommendedName && (
                <p className="mt-1 text-xs text-amber-400">
                  {t('createPrintProfile.recommendedFormatHint')}: &quot;{recommendedName}&quot;
                </p>
              )}
            </div>

            <div>
              <label className="mb-2 block text-sm font-medium text-gray-300">
                {t('createPrintProfile.slug')} <span className="text-red-400">*</span>
              </label>
              <input
                type="text"
                value={slug}
                onChange={(event) => setSlug(event.target.value)}
                className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 font-mono text-sm text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                placeholder="0-20mm-standard-vendor-printer-0-4-nozzle"
                required
              />
              <p className="mt-1 text-xs text-gray-500">{t('createPrintProfile.slugHint')}</p>
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-4">
            <div>
              <label className="mb-2 block text-sm font-medium text-gray-300">{t('createPrintProfile.qualityTier')}</label>
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
            </div>

            <div>
              <label className="mb-2 block text-sm font-medium text-gray-300">{t('createPrintProfile.defaultNozzle')}</label>
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
            </div>

            <div>
              <label className="mb-2 block text-sm font-medium text-gray-300">{t('createPrintProfile.layerHeight')}</label>
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
            </div>

            <div>
              <label className="mb-2 block text-sm font-medium text-gray-300">{t('createPrintProfile.initialLayerHeight')}</label>
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
            </div>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <h3 className="text-sm font-semibold text-white">{t('createPrintProfile.compatibilitySection')}</h3>
            <div className="mt-4">
              <label className="mb-2 block text-sm font-medium text-gray-300">
                {t('createPrintProfile.compatiblePrinters')} <span className="text-red-400">*</span>
              </label>
              <textarea
                value={compatiblePrintersInput}
                onChange={(event) => setCompatiblePrintersInput(event.target.value)}
                rows={3}
                className="w-full resize-none rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                placeholder={printerProfileContext?.name || t('createPrintProfile.compatiblePrintersPlaceholder')}
              />
              <p className="mt-1 text-xs text-gray-500">{t('createPrintProfile.compatiblePrintersHint')}</p>
            </div>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <h3 className="text-sm font-semibold text-white">{t('createPrintProfile.structureSection')}</h3>
            <div className="mt-4 grid gap-4 md:grid-cols-3">
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-300">{t('createPrintProfile.wallLoops')}</label>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={wallLoops}
                  onChange={(event) => setWallLoops(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="2"
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-300">{t('createPrintProfile.topShellLayers')}</label>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={topShellLayers}
                  onChange={(event) => setTopShellLayers(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="3"
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-300">{t('createPrintProfile.bottomShellLayers')}</label>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={bottomShellLayers}
                  onChange={(event) => setBottomShellLayers(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="3"
                />
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <h3 className="text-sm font-semibold text-white">{t('createPrintProfile.infillSection')}</h3>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-300">{t('createPrintProfile.infillDensity')}</label>
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
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-300">{t('createPrintProfile.infillPattern')}</label>
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
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <h3 className="text-sm font-semibold text-white">{t('createPrintProfile.speedSection')}</h3>
            <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-300">{t('createPrintProfile.outerWallSpeed')}</label>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={outerWallSpeed}
                  onChange={(event) => setOuterWallSpeed(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="120"
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-300">{t('createPrintProfile.innerWallSpeed')}</label>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={innerWallSpeed}
                  onChange={(event) => setInnerWallSpeed(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="40"
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-300">{t('createPrintProfile.infillSpeed')}</label>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={infillSpeed}
                  onChange={(event) => setInfillSpeed(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="50"
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-gray-300">{t('createPrintProfile.travelSpeed')}</label>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={travelSpeed}
                  onChange={(event) => setTravelSpeed(event.target.value)}
                  className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                  placeholder="400"
                />
              </div>
            </div>
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <div>
              <label className="mb-2 block text-sm font-medium text-gray-300">{t('createPrintProfile.category')}</label>
              <input
                type="text"
                value={category}
                onChange={(event) => setCategory(event.target.value)}
                className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                placeholder={t('createPrintProfile.categoryPlaceholder')}
              />
            </div>

            <div>
              <label className="mb-2 block text-sm font-medium text-gray-300">{t('createPrintProfile.description')}</label>
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                rows={3}
                className="w-full resize-none rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
                placeholder={t('createPrintProfile.descriptionPlaceholder')}
              />
            </div>
          </div>

          <div>
            <label className="mb-2 block text-sm font-medium text-gray-300">{t('createPrintProfile.notes')}</label>
            <textarea
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              rows={3}
              className="w-full resize-none rounded-lg border border-white/10 bg-white/5 px-4 py-2 text-white placeholder-gray-500 focus:border-purple-500 focus:outline-none"
              placeholder={t('createPrintProfile.notesPlaceholder')}
            />
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
    </div>
  );
};
