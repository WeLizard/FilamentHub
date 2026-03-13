/** Модальное окно для создания printer profile */

import { useState, useEffect, FormEvent, useMemo } from 'react';
import { X, Save, Loader2, Pencil, ChevronRight, HelpCircle } from 'lucide-react';
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

interface HelpTooltipProps {
  text: string;
}

const HelpTooltip = ({ text }: HelpTooltipProps) => (
  <span className="group/tooltip relative inline-flex shrink-0 align-middle">
    <button
      type="button"
      className="inline-flex h-4 w-4 items-center justify-center rounded-full text-gray-500 transition-colors hover:text-purple-200 focus:outline-none focus:text-purple-200"
      aria-label={text}
      title={text}
      onClick={(event) => {
        event.preventDefault();
        event.stopPropagation();
      }}
    >
      <HelpCircle className="h-3.5 w-3.5" />
    </button>
    <span
      role="tooltip"
      className="pointer-events-none absolute left-1/2 top-full z-30 mt-2 hidden w-64 -translate-x-1/2 rounded-lg border border-white/10 bg-slate-950/95 px-3 py-2 text-left text-xs leading-relaxed text-gray-200 shadow-2xl shadow-black/30 group-hover/tooltip:block group-focus-within/tooltip:block"
    >
      {text}
    </span>
  </span>
);

interface TooltipLabelProps {
  label: string;
  tooltipText?: string;
  htmlFor?: string;
  className?: string;
}

const TooltipLabel = ({ label, tooltipText, htmlFor, className }: TooltipLabelProps) => {
  const content = (
    <>
      <span>{label}</span>
      {tooltipText ? <HelpTooltip text={tooltipText} /> : null}
    </>
  );

  if (htmlFor) {
    return (
      <label htmlFor={htmlFor} className={className ?? 'inline-flex items-center gap-1.5 text-sm font-medium text-gray-300'}>
        {content}
      </label>
    );
  }

  return <label className={className ?? 'inline-flex items-center gap-1.5 text-sm font-medium text-gray-300'}>{content}</label>;
};

interface TooltipHeadingProps {
  title: string;
  tooltipText?: string;
  level?: 'h5' | 'h6';
}

const TooltipHeading = ({ title, tooltipText, level = 'h5' }: TooltipHeadingProps) => {
  const Tag = level;

  return (
    <div className="mb-3 flex items-center gap-1.5">
      <Tag className="text-xs font-semibold uppercase tracking-wide text-purple-200/70">{title}</Tag>
      {tooltipText ? <HelpTooltip text={tooltipText} /> : null}
    </div>
  );
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
  { value: 'copper_alloy', labelKey: 'printerProfile.options.nozzleType.copperAlloy' },
  { value: 'ruby', labelKey: 'printerProfile.options.nozzleType.ruby' },
  { value: 'titanium', labelKey: 'printerProfile.options.nozzleType.titanium' },
  { value: 'nickel_plated_copper', labelKey: 'printerProfile.options.nozzleType.nickelPlatedCopper' },
  { value: 'E3D', labelKey: 'printerProfile.options.nozzleType.e3d' },
];

const HOTEND_OPTIONS: CanonicalOption[] = [
  { value: '', labelKey: 'printerProfile.options.hotend.notSpecified' },
  { value: 'E3D V6', labelKey: 'printerProfile.options.hotend.e3dV6' },
  { value: 'E3D Revo', labelKey: 'printerProfile.options.hotend.e3dRevo' },
  { value: 'E3D Revo Voron', labelKey: 'printerProfile.options.hotend.e3dRevoVoron' },
  { value: 'Phaetus Rapido', labelKey: 'printerProfile.options.hotend.phaetusRapido' },
  { value: 'Phaetus Rapido 2', labelKey: 'printerProfile.options.hotend.phaetusRapido2' },
  { value: 'Phaetus Dragonfly', labelKey: 'printerProfile.options.hotend.phaetusDragonfly' },
  { value: 'Phaetus Dragon', labelKey: 'printerProfile.options.hotend.phaetusDragon' },
  { value: 'Slice Mosquito', labelKey: 'printerProfile.options.hotend.sliceMosquito' },
  { value: 'Slice Mosquito Magnum+', labelKey: 'printerProfile.options.hotend.sliceMosquitoMagnum' },
  { value: 'Bambu Lab', labelKey: 'printerProfile.options.hotend.bambuLab' },
  { value: 'Creality Spider', labelKey: 'printerProfile.options.hotend.crealitySpider' },
  { value: 'Creality K1', labelKey: 'printerProfile.options.hotend.crealityK1' },
  { value: 'Trianglelab CHC Pro', labelKey: 'printerProfile.options.hotend.trianglelabChcPro' },
  { value: 'Trianglelab TD6S', labelKey: 'printerProfile.options.hotend.trianglelabTd6s' },
  { value: 'Goliath', labelKey: 'printerProfile.options.hotend.goliath' },
  { value: 'NF Zone', labelKey: 'printerProfile.options.hotend.nfZone' },
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

const COMPATIBILITY_METADATA_KEYS = [
  'bed_shape',
  'machine_resume_gcode',
  'machine_cancel_gcode',
  'machine_custom_gcode',
  'toolchange_gcode',
] as const;

const EXTRA_METADATA_ONLY_KEYS = [
  ...COMPATIBILITY_METADATA_KEYS,
  'bed_custom_rectangle',
  'origin_z',
  'base_id',
  '_inherits_chain',
] as const;

const LEGACY_TO_ORCA_SETTING_ALIASES = {
  machine_switch_extruder_time: 'machine_tool_change_time',
  bed_model: 'bed_custom_model',
  bed_texture: 'bed_custom_texture',
} as const;

const KNOWN_ORCA_MACHINE_SETTING_KEYS = new Set<string>([
  'adaptive_bed_mesh_margin',
  'auxiliary_fan',
  'bbl_use_printhost',
  'bed_custom_model',
  'bed_custom_texture',
  'bed_exclude_area',
  'bed_mesh_max',
  'bed_mesh_min',
  'bed_mesh_probe_distance',
  'bed_temperature_formula',
  'before_layer_change_gcode',
  'best_object_pos',
  'change_extrusion_role_gcode',
  'change_filament_gcode',
  'cooling_tube_length',
  'cooling_tube_retraction',
  'default_bed_type',
  'default_filament_profile',
  'default_nozzle_volume_type',
  'deretraction_speed',
  'disable_m73',
  'emit_machine_limits_to_gcode',
  'enable_filament_ramming',
  'enable_long_retraction_when_cut',
  'enable_power_loss_recovery',
  'extra_loading_move',
  'extruder_ams_count',
  'extruder_clearance_height_to_lid',
  'extruder_clearance_height_to_rod',
  'extruder_clearance_radius',
  'extruder_offset',
  'extruder_printable_area',
  'extruder_printable_height',
  'extruder_type',
  'extruder_variant_list',
  'extruders_count',
  'fan_kickstart',
  'fan_speedup_overhangs',
  'fan_speedup_time',
  'file_start_gcode',
  'gcode_flavor',
  'high_current_on_filament_swap',
  'hotend_model',
  'layer_change_gcode',
  'long_retractions_when_cut',
  'machine_end_gcode',
  'machine_load_filament_time',
  'machine_max_acceleration_e',
  'machine_max_acceleration_extruding',
  'machine_max_acceleration_retracting',
  'machine_max_acceleration_travel',
  'machine_max_acceleration_x',
  'machine_max_acceleration_y',
  'machine_max_acceleration_z',
  'machine_max_jerk_e',
  'machine_max_jerk_x',
  'machine_max_jerk_y',
  'machine_max_jerk_z',
  'machine_max_junction_deviation',
  'machine_max_speed_e',
  'machine_max_speed_x',
  'machine_max_speed_y',
  'machine_max_speed_z',
  'machine_min_extruding_rate',
  'machine_min_travel_rate',
  'machine_pause_gcode',
  'machine_start_gcode',
  'machine_tool_change_time',
  'machine_unload_filament_time',
  'manual_filament_change',
  'max_layer_height',
  'max_resonance_avoidance_speed',
  'min_layer_height',
  'min_resonance_avoidance_speed',
  'nozzle_diameter',
  'nozzle_hrc',
  'nozzle_type',
  'nozzle_volume',
  'parking_pos_retraction',
  'pellet_modded_printer',
  'physical_extruder_map',
  'preferred_orientation',
  'printer_extruder_id',
  'printer_extruder_variant',
  'printer_model',
  'printer_notes',
  'printer_structure',
  'printer_technology',
  'printer_variant',
  'printing_by_object_gcode',
  'printable_area',
  'printable_height',
  'purge_in_prime_tower',
  'resonance_avoidance',
  'retract_before_wipe',
  'retract_length_toolchange',
  'retract_lift_above',
  'retract_lift_below',
  'retract_lift_enforce',
  'retract_restart_extra',
  'retract_restart_extra_toolchange',
  'retract_when_changing_layer',
  'retraction_distances_when_cut',
  'retraction_length',
  'retraction_minimum_travel',
  'retraction_speed',
  'scan_first_layer',
  'single_extruder_multi_material',
  'support_air_filtration',
  'support_chamber_temp_control',
  'support_multi_bed_types',
  'template_custom_gcode',
  'thumbnails',
  'thumbnails_format',
  'time_cost',
  'time_lapse_gcode',
  'travel_slope',
  'use_firmware_retraction',
  'use_relative_e_distances',
  'wipe',
  'wipe_distance',
  'wrapping_detection_gcode',
  'z_hop',
  'z_hop_types',
  'z_offset',
]);

const EXTRA_METADATA_ONLY_KEY_SET = new Set<string>(EXTRA_METADATA_ONLY_KEYS);

const sanitizeMachineSettings = (settings: Record<string, any>): Record<string, any> => {
  const next = { ...settings };

  Object.keys(LEGACY_TO_ORCA_SETTING_ALIASES).forEach((legacyKey) => {
    delete next[legacyKey];
  });

  EXTRA_METADATA_ONLY_KEYS.forEach((key) => {
    delete next[key];
  });

  return next;
};

const extractMachineSettingsFromExtraMetadata = (extraMetadata: Record<string, any> | null | undefined): Record<string, any> => {
  if (!extraMetadata || typeof extraMetadata !== 'object') {
    return {};
  }

  const extracted: Record<string, any> = {};

  Object.entries(extraMetadata).forEach(([key, value]) => {
    if (
      EXTRA_METADATA_ONLY_KEY_SET.has(key) ||
      key in LEGACY_TO_ORCA_SETTING_ALIASES ||
      !KNOWN_ORCA_MACHINE_SETTING_KEYS.has(key)
    ) {
      return;
    }
    extracted[key] = value;
  });

  Object.entries(LEGACY_TO_ORCA_SETTING_ALIASES).forEach(([legacyKey, canonicalKey]) => {
    if (extraMetadata[legacyKey] !== undefined && extracted[canonicalKey] === undefined) {
      extracted[canonicalKey] = extraMetadata[legacyKey];
    }
  });

  return sanitizeMachineSettings(extracted);
};

const mergeCompatibilityExtraMetadata = (
  extraMetadata: Record<string, any> | null | undefined,
  orcaSettings: Record<string, any> | null | undefined,
): Record<string, any> => {
  const merged = { ...(extraMetadata ?? {}) };
  const settings = orcaSettings ?? {};

  EXTRA_METADATA_ONLY_KEYS.forEach((key) => {
    if (merged[key] === undefined && settings[key] !== undefined) {
      merged[key] = settings[key];
    }
  });

  return merged;
};

const serializePrintableAreaForOrcaSettings = (area: string[] | { x: number; y: number } | null): string[] | undefined => {
  if (!area) {
    return undefined;
  }

  if (Array.isArray(area)) {
    return area.map((item) => String(item).trim()).filter((item) => item.length > 0);
  }

  const x = Number(area.x);
  const y = Number(area.y);
  if (!Number.isFinite(x) || !Number.isFinite(y)) {
    return undefined;
  }

  return [
    '0x0',
    `${x}x0`,
    `${x}x${y}`,
    `0x${y}`,
  ];
};

const getProfilePrintableAreaSource = (profileLike: PrinterProfile | null | undefined): unknown => {
  const orcaArea = profileLike?.orcaslicer_settings?.printable_area;
  if (orcaArea !== undefined && orcaArea !== null) {
    return orcaArea;
  }
  return profileLike?.printable_area ?? null;
};

const getProfilePrintableHeightValue = (profileLike: PrinterProfile | null | undefined): string => {
  const rawValue = profileLike?.orcaslicer_settings?.printable_height;
  if (Array.isArray(rawValue)) {
    return rawValue[0] !== undefined ? String(rawValue[0]) : '';
  }
  if (rawValue !== undefined && rawValue !== null && rawValue !== '') {
    return String(rawValue);
  }
  return profileLike?.printable_height_mm?.toString() || '';
};

const getProfileNozzleDiameterValues = (profileLike: PrinterProfile | null | undefined): string[] => {
  const rawValue = profileLike?.orcaslicer_settings?.nozzle_diameter;
  if (Array.isArray(rawValue)) {
    return rawValue.map((item) => String(item));
  }
  if (rawValue !== undefined && rawValue !== null && rawValue !== '') {
    return [String(rawValue)];
  }
  return profileLike?.nozzle_diameters?.map((item) => item.toString()) || [];
};

const getProfileNotesValue = (profileLike: PrinterProfile | null | undefined): string => {
  const printerNotes = profileLike?.orcaslicer_settings?.printer_notes;
  if (typeof printerNotes === 'string' && printerNotes.trim() !== '') {
    return printerNotes;
  }
  return profileLike?.notes || '';
};

const buildInitialMachineSettings = (profileLike: PrinterProfile | null | undefined): Record<string, any> => {
  const settings = sanitizeMachineSettings({
    ...extractMachineSettingsFromExtraMetadata(profileLike?.extra_metadata),
    ...(profileLike?.orcaslicer_settings ?? {}),
  });

  if (settings.machine_start_gcode === undefined && profileLike?.start_gcode) {
    settings.machine_start_gcode = profileLike.start_gcode;
  }
  if (settings.machine_end_gcode === undefined && profileLike?.end_gcode) {
    settings.machine_end_gcode = profileLike.end_gcode;
  }
  if (settings.printable_area === undefined) {
    const printableArea = serializePrintableAreaForOrcaSettings(
      Array.isArray(profileLike?.printable_area)
        ? profileLike?.printable_area
        : profileLike?.printable_area
          ? {
              x: Number((profileLike.printable_area as Record<string, any>).x),
              y: Number((profileLike.printable_area as Record<string, any>).y),
            }
          : null,
    );
    if (printableArea && printableArea.length > 0) {
      settings.printable_area = printableArea;
    }
  }
  if (settings.printable_height === undefined && profileLike?.printable_height_mm !== null && profileLike?.printable_height_mm !== undefined) {
    settings.printable_height = String(profileLike.printable_height_mm);
  }
  if (settings.nozzle_diameter === undefined && profileLike?.nozzle_diameters?.length) {
    settings.nozzle_diameter = profileLike.nozzle_diameters.map((item) => String(item));
  }
  if (settings.printer_notes === undefined && profileLike?.notes) {
    settings.printer_notes = profileLike.notes;
  }

  return sanitizeMachineSettings(settings);
};

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
  const [machineSettings, setMachineSettings] = useState<Record<string, any>>({});
  const [extraMetadata, setExtraMetadata] = useState('');
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
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

  // Парсинг raw extra_metadata JSON (только compatibility/service хвосты).
  const parsedExtraMetadata = useMemo(() => {
    if (!extraMetadata.trim()) {
      return {};
    }
    try {
      return JSON.parse(extraMetadata);
    } catch (error) {
      return null;
    }
  }, [extraMetadata]);

  const metadataInvalid = false;

  const getMetadataValue = (key: string): any => {
    if (EXTRA_METADATA_ONLY_KEY_SET.has(key)) {
      if (!parsedExtraMetadata || typeof parsedExtraMetadata !== 'object') {
        return undefined;
      }
      return (parsedExtraMetadata as Record<string, any>)[key];
    }
    return machineSettings[key];
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

  const getMetadataListValues = (key: string): string[] => {
    const value = getMetadataValue(key);
    if (Array.isArray(value)) {
      return value.map((item) => String(item));
    }
    if (value === undefined || value === null || value === '') {
      return [];
    }
    return [String(value)];
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
    const isCompatibilityKey = EXTRA_METADATA_ONLY_KEY_SET.has(key);
    const isSpecialArrayField = ARRAY_FIELDS_WITH_EMPTY_VALID.includes(key);

    if (isCompatibilityKey) {
      if (extraMetadata.trim() && parsedExtraMetadata === null) {
        setJsonError(t('printerProfile.jsonInvalid'));
        return;
      }

      const base =
        parsedExtraMetadata && typeof parsedExtraMetadata === 'object'
          ? { ...(parsedExtraMetadata as Record<string, any>) }
          : {};

      aliasesToDelete.forEach((alias) => {
        delete base[alias];
      });

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
      return;
    }

    setMachineSettings((prev) => {
      const next = { ...prev };

      aliasesToDelete.forEach((alias) => {
        delete next[alias];
      });

      if (
        value === undefined ||
        value === null ||
        (typeof value === 'string' && value.trim() === '') ||
        (Array.isArray(value) && value.length === 0 && !isSpecialArrayField)
      ) {
        delete next[key];
      } else {
        next[key] = value;
      }

      return sanitizeMachineSettings(next);
    });
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
        const machineSettingsSource = buildInitialMachineSettings(profile);
        const extraMetadataSource = mergeCompatibilityExtraMetadata(profile.extra_metadata, profile.orcaslicer_settings);
        const printableAreaSource = getProfilePrintableAreaSource(profile);
        const dimensions = getPrintableAreaDimensions(printableAreaSource);
        setPrintableAreaX(dimensions.x);
        setPrintableAreaY(dimensions.y);
        setPrintableAreaPolygon(getPrintableAreaPolygonString(printableAreaSource));
        setPrintableHeightMm(getProfilePrintableHeightValue(profile));
        setNozzleDiameters(getProfileNozzleDiameterValues(profile));
        setNotes(getProfileNotesValue(profile));
        setMachineSettings(machineSettingsSource);
        setExtraMetadata(Object.keys(extraMetadataSource).length ? JSON.stringify(extraMetadataSource, null, 2) : '');
      } else if (baseProfile) {
        // Клонирование
        setName(`${baseProfile.name} (${t('printerProfile.copyLabel')})`);
        setSlug(`${baseProfile.slug}-copy`);
        setDescription(baseProfile.description || '');
        setPrinterId(baseProfile.printer_id);
        setPrinterSearch('');
        setVendor(baseProfile.vendor || '');
        const machineSettingsSource = buildInitialMachineSettings(baseProfile);
        const extraMetadataSource = mergeCompatibilityExtraMetadata(baseProfile.extra_metadata, baseProfile.orcaslicer_settings);
        const printableAreaSource = getProfilePrintableAreaSource(baseProfile);
        const dimensions = getPrintableAreaDimensions(printableAreaSource);
        setPrintableAreaX(dimensions.x);
        setPrintableAreaY(dimensions.y);
        setPrintableAreaPolygon(getPrintableAreaPolygonString(printableAreaSource));
        setPrintableHeightMm(getProfilePrintableHeightValue(baseProfile));
        setNozzleDiameters(getProfileNozzleDiameterValues(baseProfile));
        setNotes(getProfileNotesValue(baseProfile));
        setMachineSettings(machineSettingsSource);
        setExtraMetadata(Object.keys(extraMetadataSource).length ? JSON.stringify(extraMetadataSource, null, 2) : '');
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
        setMachineSettings({});
        setExtraMetadata('');
      }
      setActiveTab('general');
      setNewNozzleDiameter('');
      setFormError(null);
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
    setFormError(null);
    
    if (!name.trim()) {
      alert(t('printerProfile.nameRequired'));
      return;
    }
    
    if (!slug.trim()) {
      alert(t('printerProfile.slugRequired'));
      return;
    }

    let rawExtraMetadataObj: Record<string, any> = {};
    if (extraMetadata.trim()) {
      try {
        const parsedExtraMetadata = JSON.parse(extraMetadata);
        if (!parsedExtraMetadata || typeof parsedExtraMetadata !== 'object' || Array.isArray(parsedExtraMetadata)) {
          throw new Error('extra_metadata must be an object');
        }
        rawExtraMetadataObj = parsedExtraMetadata as Record<string, any>;
        setJsonError(null);
      } catch (error) {
        console.error('Invalid extra metadata JSON', error);
        setJsonError(t('printerProfile.jsonInvalid'));
        return;
      }
    } else {
      setJsonError(null);
    }

    const printableAreaPolygonValues = parsePrintableAreaPolygon(printableAreaPolygon);
    if (printableAreaPolygon.trim() && printableAreaPolygonValues === null) {
      setActiveTab('general');
      setFormError(t('printerProfile.printAreaPolygonInvalid'));
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

    const orcaSettings = sanitizeMachineSettings({
      ...extractMachineSettingsFromExtraMetadata(rawExtraMetadataObj),
      ...machineSettings,
    });

    const printableAreaForOrcaSettings = serializePrintableAreaForOrcaSettings(printableArea);
    if (printableAreaForOrcaSettings && printableAreaForOrcaSettings.length > 0) {
      orcaSettings.printable_area = printableAreaForOrcaSettings;
    } else {
      delete orcaSettings.printable_area;
    }

    const printableHeightValue = printableHeightMm.trim();
    if (printableHeightValue) {
      orcaSettings.printable_height = printableHeightValue;
    } else {
      delete orcaSettings.printable_height;
    }

    if (nozzleDiametersArray.length > 0) {
      orcaSettings.nozzle_diameter = nozzleDiametersArray.map((diameter) => String(diameter));
    } else {
      delete orcaSettings.nozzle_diameter;
    }

    const trimmedNotes = notes.trim();
    if (trimmedNotes) {
      orcaSettings.printer_notes = trimmedNotes;
    } else {
      delete orcaSettings.printer_notes;
    }

    const cleanedExtraMetadata = { ...rawExtraMetadataObj };
    KNOWN_ORCA_MACHINE_SETTING_KEYS.forEach((key) => {
      delete cleanedExtraMetadata[key];
    });
    Object.keys(LEGACY_TO_ORCA_SETTING_ALIASES).forEach((legacyKey) => {
      delete cleanedExtraMetadata[legacyKey];
    });

    const extraMetadataObj = mergeCompatibilityExtraMetadata(cleanedExtraMetadata, orcaSettings);
    const startGcode = typeof orcaSettings.machine_start_gcode === 'string'
      ? orcaSettings.machine_start_gcode
      : orcaSettings.machine_start_gcode !== undefined && orcaSettings.machine_start_gcode !== null
        ? String(orcaSettings.machine_start_gcode)
        : '';
    const endGcode = typeof orcaSettings.machine_end_gcode === 'string'
      ? orcaSettings.machine_end_gcode
      : orcaSettings.machine_end_gcode !== undefined && orcaSettings.machine_end_gcode !== null
        ? String(orcaSettings.machine_end_gcode)
        : '';

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
      notes: trimmedNotes || null,
      orcaslicer_settings: Object.keys(orcaSettings).length > 0 ? orcaSettings : {},
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
    const advancedFlagOptions: Array<{ key: string; labelKey: string; descriptionKey?: string }> = [
      { key: 'use_relative_e_distances', labelKey: 'printerProfile.flags.relativeE', descriptionKey: 'printerProfile.flags.relativeEDesc' },
      { key: 'use_firmware_retraction', labelKey: 'printerProfile.flags.firmwareRetraction', descriptionKey: 'printerProfile.flags.firmwareRetractionDesc' },
      { key: 'pellet_modded_printer', labelKey: 'printerProfile.flags.pelletMod', descriptionKey: 'printerProfile.flags.pelletModDesc' },
      { key: 'scan_first_layer', labelKey: 'printerProfile.flags.scanFirstLayer' },
      { key: 'disable_m73', labelKey: 'printerProfile.flags.disableM73' },
      { key: 'bbl_use_printhost', labelKey: 'printerProfile.flags.usePrinthost' },
    ];
    const accessoryFlagOptions: Array<{ key: string; labelKey: string }> = [
      { key: 'auxiliary_fan', labelKey: 'printerProfile.flags.auxiliaryFan' },
      { key: 'support_chamber_temp_control', labelKey: 'printerProfile.flags.chamberTemp' },
      { key: 'support_air_filtration', labelKey: 'printerProfile.flags.airFiltration' },
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
    const printableSpaceFields: Array<{ key: string; labelKey: string; isList?: boolean; placeholder?: string; unit?: string }> = [
      { key: 'best_object_pos', labelKey: 'printerProfile.bed.bestObjectPos', placeholder: '0.5,0.5' },
      { key: 'bed_exclude_area', labelKey: 'printerProfile.bed.excludeArea', isList: true, placeholder: '90x90, 166x166' },
      { key: 'z_offset', labelKey: 'printerProfile.bed.zOffset', placeholder: '0', unit: t('printerProfile.units.mm') },
      { key: 'preferred_orientation', labelKey: 'printerProfile.bed.preferredOrientation', placeholder: '0', unit: t('printerProfile.units.deg') },
    ];
    const printableSpaceCompatibilityFields: Array<{ key: string; labelKey: string; isList?: boolean; placeholder?: string; unit?: string }> = [
      { key: 'bed_shape', labelKey: 'printerProfile.bed.shape', isList: true, placeholder: '0x0, 256x0, 256x256, 0x256' },
    ];
    const bedAssetFields: Array<{ key: string; labelKey: string; placeholder?: string }> = [
      { key: 'bed_custom_model', labelKey: 'printerProfile.bed.customModel', placeholder: 'custom-bed.stl' },
      { key: 'bed_custom_texture', labelKey: 'printerProfile.bed.customTexture', placeholder: 'custom-bed.png' },
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

        {metadataInvalid ? (
          <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
            {t('printerProfile.jsonParseError')}
          </div>
        ) : (
          <div className="space-y-6">
            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.sections.printableSpace')}</h5>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
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
                <label className="block text-sm font-medium text-gray-300 mb-2">{t('printerProfile.printAreaPolygon')}</label>
                <textarea
                  value={printableAreaPolygon}
                  onChange={(e) => {
                    setPrintableAreaPolygon(e.target.value);
                    if (formError) {
                      setFormError(null);
                    }
                  }}
                  rows={3}
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 font-mono text-sm resize-none"
                  placeholder="0x0, 256x0, 256x256, 0x256"
                />
                <p className="text-xs text-gray-500 mt-1">{t('printerProfile.printAreaPolygonHint')}</p>
              </div>
              <div className="mt-4 flex items-start gap-3">
                <input
                  type="checkbox"
                  id="support_multi_bed_types"
                  checked={getMetadataBoolean('support_multi_bed_types')}
                  onChange={(e) => handleMetadataBooleanChange('support_multi_bed_types', e.target.checked)}
                  className="w-4 h-4 mt-1 rounded border-white/30 bg-white/10"
                />
                <div>
                  <label htmlFor="support_multi_bed_types" className="text-gray-300 text-sm font-medium">
                    {t('printerProfile.flags.multiBedTypes')}
                  </label>
                  <p className="text-xs text-gray-500">{t('printerProfile.flags.multiBedTypesDesc')}</p>
                </div>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                {printableSpaceFields.map((field) => (
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
              <details className="group mt-4 rounded-lg border border-white/10 bg-white/[0.03]">
                <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-medium text-gray-300 transition-colors hover:text-white [&::-webkit-details-marker]:hidden">
                  <span>{t('printerProfile.spoilers.bedAssets')}</span>
                  <ChevronRight className="ml-auto h-4 w-4 text-gray-400 transition-transform group-open:rotate-90" />
                </summary>
                <div className="px-4 pb-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {bedAssetFields.map((field) => (
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
              </details>
              <details className="group mt-4 rounded-lg border border-white/10 bg-white/[0.03]">
                <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-medium text-gray-300 transition-colors hover:text-white [&::-webkit-details-marker]:hidden">
                  <span>{t('printerProfile.spoilers.printableSpaceCompatibility')}</span>
                  <ChevronRight className="ml-auto h-4 w-4 text-gray-400 transition-transform group-open:rotate-90" />
                </summary>
                <div className="px-4 pb-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {printableSpaceCompatibilityFields.map((field) => (
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
              </details>
            </div>

            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.sections.advanced')}</h5>
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
                  <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerProfile.powerLossRecovery')}</label>
                  <CustomSelect
                    value={selectedPowerLossRecovery}
                    onChange={(value) => handleMetadataStringChange('enable_power_loss_recovery', (value as string) || '')}
                    options={buildTranslatedOptions(ORCA_POWER_LOSS_RECOVERY_OPTIONS, selectedPowerLossRecovery)}
                    placeholder={t('printerProfile.selectPowerLossRecovery')}
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
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">
                {advancedFlagOptions.map((option) => (
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
              <details className="group mt-4 rounded-lg border border-white/10 bg-white/[0.03]">
                <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-medium text-gray-300 transition-colors hover:text-white [&::-webkit-details-marker]:hidden">
                  <span>{t('printerProfile.spoilers.moreProfileFields')}</span>
                  <ChevronRight className="ml-auto h-4 w-4 text-gray-400 transition-transform group-open:rotate-90" />
                </summary>
                <div className="px-4 pb-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
                      <label className="block text-gray-300 mb-2 text-sm font-medium">{t('printerProfile.hotend')}</label>
                      <CustomSelect
                        value={getMetadataString('hotend_model') || null}
                        onChange={(value) => handleMetadataStringChange('hotend_model', (value as string) || '')}
                        options={buildTranslatedOptions(HOTEND_OPTIONS, getMetadataString('hotend_model') || null)}
                        placeholder={t('printerProfile.selectHotend')}
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
                </div>
              </details>
              <details className="group mt-4 rounded-lg border border-white/10 bg-white/[0.03]">
                <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-medium text-gray-300 transition-colors hover:text-white [&::-webkit-details-marker]:hidden">
                  <span>{t('printerProfile.spoilers.thumbnails')}</span>
                  <ChevronRight className="ml-auto h-4 w-4 text-gray-400 transition-transform group-open:rotate-90" />
                </summary>
                <div className="px-4 pb-4">
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
              </details>
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
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.sections.accessory')}</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">
                {accessoryFlagOptions.map((option) => (
                  <div key={option.key} className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      id={`accessory-${option.key}`}
                      checked={getMetadataBoolean(option.key)}
                      onChange={(e) => handleMetadataBooleanChange(option.key, e.target.checked)}
                      className="w-4 h-4 mt-1 rounded border-white/30 bg-white/10"
                    />
                    <label htmlFor={`accessory-${option.key}`} className="text-gray-300 text-sm font-medium">
                      {t(option.labelKey)}
                    </label>
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

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div>
                <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.motion.maxSpeed')}</h5>
                <div className="grid grid-cols-4 gap-2">
                  {(['machine_max_speed_x', 'machine_max_speed_y', 'machine_max_speed_z', 'machine_max_speed_e'] as const).map((key) => (
                    <div key={key}>
                      <label className="block text-gray-400 mb-1 text-xs text-center">{key.replace('machine_max_speed_', '').toUpperCase()}</label>
                      <input
                        type="text"
                        value={getMetadataListString(key)}
                        onChange={(e) => handleMetadataListChange(key, e.target.value)}
                        placeholder="500"
                        className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-1.5 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 text-sm text-center"
                      />
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.motion.acceleration')}</h5>
                <div className="grid grid-cols-4 gap-2">
                  {(['machine_max_acceleration_x', 'machine_max_acceleration_y', 'machine_max_acceleration_z', 'machine_max_acceleration_e'] as const).map((key) => (
                    <div key={key}>
                      <label className="block text-gray-400 mb-1 text-xs text-center">{key.replace('machine_max_acceleration_', '').toUpperCase()}</label>
                      <input
                        type="text"
                        value={getMetadataListString(key)}
                        onChange={(e) => handleMetadataListChange(key, e.target.value)}
                        placeholder="20000"
                        className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-1.5 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 text-sm text-center"
                      />
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div>
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

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <div>
                <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('adminPrinters.speed.jerk')}</h5>
                <div className="grid grid-cols-4 gap-2">
                  {(['machine_max_jerk_x', 'machine_max_jerk_y', 'machine_max_jerk_z', 'machine_max_jerk_e'] as const).map((key) => (
                    <div key={key}>
                      <label className="block text-gray-400 mb-1 text-xs text-center">{key.replace('machine_max_jerk_', '').toUpperCase()}</label>
                      <input
                        type="text"
                        value={getMetadataListString(key)}
                        onChange={(e) => handleMetadataListChange(key, e.target.value)}
                        placeholder="8"
                        className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-1.5 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 text-sm text-center"
                      />
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <TooltipHeading
                  title={t('printerProfile.motion.junctionDeviation')}
                  tooltipText={t('printerProfile.help.tooltips.junctionDeviation')}
                />
                <input
                  type="text"
                  value={getMetadataListString('machine_max_junction_deviation')}
                  onChange={(e) => handleMetadataListChange('machine_max_junction_deviation', e.target.value)}
                  placeholder="0.01"
                  className="w-full bg-white/5 border border-white/10 rounded-lg px-2 py-1.5 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500 text-sm"
                />
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
    const longRetractionLevel = getMetadataString('enable_long_retraction_when_cut') || '0';
    const perExtruderArrayKeys = [
      'extruder_type',
      'default_nozzle_volume_type',
      'extruder_variant_list',
      'extruder_ams_count',
      'printer_extruder_id',
      'printer_extruder_variant',
      'physical_extruder_map',
      'nozzle_type',
      'nozzle_volume',
      'extruder_printable_height',
      'extruder_printable_area',
      'extruder_offset',
      'max_layer_height',
      'min_layer_height',
      'retraction_length',
      'retract_restart_extra',
      'retraction_speed',
      'deretraction_speed',
      'retraction_minimum_travel',
      'retract_when_changing_layer',
      'wipe',
      'wipe_distance',
      'retract_before_wipe',
      'retract_lift_enforce',
      'z_hop_types',
      'z_hop',
      'travel_slope',
      'retract_lift_above',
      'retract_lift_below',
      'retract_length_toolchange',
      'retract_restart_extra_toolchange',
      'long_retractions_when_cut',
      'retraction_distances_when_cut',
    ] as const;
    const extruderSlotsCount = Math.max(
      1,
      nozzleDiameters.length,
      Number.parseInt(getMetadataString('extruders_count') || '0', 10) || 0,
      ...perExtruderArrayKeys.map((key) => getMetadataListValues(key).length),
    );

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

    const renderEnumArrayField = (
      key: string,
      labelKey: string,
      options: CanonicalOption[],
      placeholder: string,
    ) => {
      const values = getMetadataListValues(key);

      const handleSelectChange = (index: number, selectedValue: string | null) => {
        const nextValues = Array.from({ length: Math.max(extruderSlotsCount, values.length) }, (_, valueIndex) => values[valueIndex] ?? '');
        nextValues[index] = selectedValue || '';

        while (nextValues.length > 0 && !nextValues[nextValues.length - 1]) {
          nextValues.pop();
        }

        if (nextValues.length === 0) {
          updateMetadataValue(key, []);
          return;
        }

        updateMetadataValue(key, nextValues);
      };

      return (
        <div className="space-y-2">
          <label className="block text-gray-300 text-sm font-medium">{t(labelKey)}</label>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Array.from({ length: extruderSlotsCount }, (_, index) => {
              const currentValue = values[index] ?? null;
              return (
                <div key={`${key}-${index}`} className="space-y-1">
                  {extruderSlotsCount > 1 && <span className="block text-xs text-gray-500">#{index + 1}</span>}
                  <CustomSelect
                    value={currentValue}
                    onChange={(value) => handleSelectChange(index, (value as string) || null)}
                    options={buildTranslatedOptions(options, currentValue)}
                    placeholder={placeholder}
                  />
                </div>
              );
            })}
          </div>
        </div>
      );
    };

    const hardwareFields: MetadataFieldConfig[] = [
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
            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.sections.extruderHardware')}</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {renderEnumArrayField(
                  'extruder_type',
                  'printerProfile.extruder.type',
                  ORCA_EXTRUDER_TYPE_OPTIONS,
                  t('printerProfile.selectType'),
                )}
                {renderEnumArrayField(
                  'default_nozzle_volume_type',
                  'printerProfile.extruder.defaultNozzleVolumeType',
                  ORCA_NOZZLE_VOLUME_TYPE_OPTIONS,
                  t('printerProfile.selectType'),
                )}
                {hardwareFields.map(renderMetadataField)}
              </div>
            </div>

            <div>
              <h5 className="text-xs font-semibold uppercase tracking-wide text-purple-200/70 mb-3">{t('printerProfile.sections.extruderGeometry')}</h5>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {renderEnumArrayField(
                  'nozzle_type',
                  'printerProfile.extruder.nozzleType',
                  ORCA_NOZZLE_TYPE_OPTIONS,
                  t('printerProfile.selectType'),
                )}
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
                  {renderEnumArrayField(
                    'retract_lift_enforce',
                    'printerProfile.retraction.liftEnforce',
                    ORCA_RETRACT_LIFT_ENFORCE_OPTIONS,
                    t('printerProfile.selectType'),
                  )}
                  {renderEnumArrayField(
                    'z_hop_types',
                    'printerProfile.retraction.zhopType',
                    ORCA_Z_HOP_TYPE_OPTIONS,
                    t('printerProfile.selectType'),
                  )}
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
                  <TooltipLabel
                    htmlFor="single_extruder_multi_material"
                    label={t('printerProfile.multi.singleExtruderMultiMaterial')}
                    tooltipText={t('printerProfile.help.tooltips.singleExtruderMultiMaterial')}
                    className="inline-flex items-center gap-1.5 text-sm text-gray-300"
                  />
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
                  <TooltipLabel
                    label={t('printerProfile.multi.bedTemperatureFormula')}
                    tooltipText={t('printerProfile.help.tooltips.bedTemperatureFormula')}
                    className="mb-2 inline-flex items-center gap-1.5 text-sm font-medium text-gray-300"
                  />
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
              <TooltipHeading
                title={t('printerProfile.sections.multimaterialWipeTower')}
                tooltipText={t('printerProfile.help.tooltips.wipeTower')}
              />
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    id="purge_in_prime_tower"
                    checked={getMetadataBoolean('purge_in_prime_tower')}
                    onChange={(e) => handleMetadataBooleanChange('purge_in_prime_tower', e.target.checked)}
                    className="w-4 h-4 rounded border-white/30 bg-white/10"
                  />
                  <TooltipLabel
                    htmlFor="purge_in_prime_tower"
                    label={t('printerProfile.multi.purgeInTower')}
                    tooltipText={t('printerProfile.help.tooltips.purgeInPrimeTower')}
                    className="inline-flex items-center gap-1.5 text-sm text-gray-300"
                  />
                </div>
                <div className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    id="enable_filament_ramming"
                    checked={getMetadataBoolean('enable_filament_ramming')}
                    onChange={(e) => handleMetadataBooleanChange('enable_filament_ramming', e.target.checked)}
                    className="w-4 h-4 rounded border-white/30 bg-white/10"
                  />
                  <TooltipLabel
                    htmlFor="enable_filament_ramming"
                    label={t('printerProfile.multi.enableRamming')}
                    tooltipText={t('printerProfile.help.tooltips.ramming')}
                    className="inline-flex items-center gap-1.5 text-sm text-gray-300"
                  />
                </div>
              </div>
            </div>

            <div>
              <TooltipHeading
                title={t('printerProfile.sections.multimaterialSemm')}
                tooltipText={t('printerProfile.help.tooltips.semm')}
              />
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <TooltipLabel
                    label={t('printerProfile.multi.parkingRetraction')}
                    tooltipText={t('printerProfile.help.tooltips.parkingRetraction')}
                    className="mb-2 inline-flex items-center gap-1.5 text-sm font-medium text-gray-300"
                  />
                  <input
                    type="text"
                    value={getMetadataString('parking_pos_retraction')}
                    onChange={(e) => handleMetadataStringChange('parking_pos_retraction', e.target.value)}
                    placeholder="16"
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div>
                  <TooltipLabel
                    label={t('printerProfile.multi.coolingTubeRetraction')}
                    tooltipText={t('printerProfile.help.tooltips.coolingTubeRetraction')}
                    className="mb-2 inline-flex items-center gap-1.5 text-sm font-medium text-gray-300"
                  />
                  <input
                    type="text"
                    value={getMetadataString('cooling_tube_retraction')}
                    onChange={(e) => handleMetadataStringChange('cooling_tube_retraction', e.target.value)}
                    placeholder="60"
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div>
                  <TooltipLabel
                    label={t('printerProfile.multi.coolingTubeLength')}
                    tooltipText={t('printerProfile.help.tooltips.coolingTubeLength')}
                    className="mb-2 inline-flex items-center gap-1.5 text-sm font-medium text-gray-300"
                  />
                  <input
                    type="text"
                    value={getMetadataString('cooling_tube_length')}
                    onChange={(e) => handleMetadataStringChange('cooling_tube_length', e.target.value)}
                    placeholder="20"
                    className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div>
                  <TooltipLabel
                    label={t('printerProfile.multi.extraLoadingMove')}
                    tooltipText={t('printerProfile.help.tooltips.extraLoadingMove')}
                    className="mb-2 inline-flex items-center gap-1.5 text-sm font-medium text-gray-300"
                  />
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
                  <TooltipLabel
                    label={t('printerProfile.multi.machineToolChangeTime')}
                    tooltipText={t('printerProfile.help.tooltips.toolChangeTime')}
                    className="mb-2 inline-flex items-center gap-1.5 text-sm font-medium text-gray-300"
                  />
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
          {formError ? (
            <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
              {formError}
            </div>
          ) : null}
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
