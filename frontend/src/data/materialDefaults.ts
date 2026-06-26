/**
 * Стандартные значения по умолчанию для типовых пластиков
 * Основано на профилях @FilamentHub из OrcaSlicer
 */

export interface MaterialDefaults {
  // Базовые параметры пресета
  extruder_temp: number;
  bed_temp: number;
  print_speed: number;
  travel_speed: number;
  layer_height: number;
  flow_rate: number;
  fan_speed: number;
  retraction_length: number;
  retraction_speed: number;

  // Расширенные параметры OrcaSlicer
  orcaslicer_settings: {
    // Температуры
    nozzle_temperature_range_low?: number;
    nozzle_temperature_range_high?: number;
    nozzle_temperature_initial_layer?: number;
    bed_temperature_initial_layer?: number;
    idle_temperature?: number;
    chamber_temperature?: number;
    activate_chamber_temp_control?: boolean;

    // Свойства филамента
    filament_max_volumetric_speed?: number;
    filament_adaptive_volumetric_speed?: boolean;
    filament_shrink?: string; // Процент в формате "99.8%"
    filament_shrinkage_compensation_z?: string; // Процент
    filament_is_support?: boolean;
    filament_soluble?: boolean;

    // Вентиляторы
    fan_min_speed?: number;
    fan_max_speed?: number;
    overhang_fan_speed?: number;
    close_fan_the_first_x_layers?: number;

    // Ретракт (расширенная)
    filament_deretraction_speed?: number;
    filament_retraction_minimum_travel?: number;
    filament_retract_when_changing_layer?: boolean;

    // Pressure Advance
    pressure_advance?: number;
    enable_pressure_advance?: boolean;
    adaptive_pressure_advance?: boolean;

    // Экструдер
    filament_extruder_variant?: string;
    compatible_printers?: string[];

    // Другие параметры
    [key: string]: unknown;
  };
}

/**
 * Маппинг стандартных значений по типам материалов
 */
export const MATERIAL_DEFAULTS: Record<string, MaterialDefaults> = {
  ABS: {
    extruder_temp: 270,
    bed_temp: 90,
    print_speed: 50,
    travel_speed: 150,
    layer_height: 0.2,
    flow_rate: 100,
    fan_speed: 10,
    retraction_length: 5.0,
    retraction_speed: 45.0,
    orcaslicer_settings: {
      nozzle_temperature_range_low: 240,
      nozzle_temperature_range_high: 280,
      nozzle_temperature_initial_layer: 260,
      idle_temperature: 170,
      chamber_temperature: 0,
      activate_chamber_temp_control: false,
      filament_max_volumetric_speed: 28.6,
      filament_adaptive_volumetric_speed: false,
      filament_shrink: '100%',
      filament_shrinkage_compensation_z: '100%',
      filament_is_support: false,
      filament_soluble: false,
      fan_min_speed: 10,
      fan_max_speed: 80,
      overhang_fan_speed: 80,
      close_fan_the_first_x_layers: 3,
      pressure_advance: 0.02,
      enable_pressure_advance: false,
      adaptive_pressure_advance: false,
      filament_extruder_variant: 'Direct Drive Standard',
    },
  },

  PLA: {
    extruder_temp: 210,
    bed_temp: 60,
    print_speed: 80,
    travel_speed: 150,
    layer_height: 0.2,
    flow_rate: 100,
    fan_speed: 100,
    retraction_length: 5.0,
    retraction_speed: 45.0,
    orcaslicer_settings: {
      nozzle_temperature_range_low: 190,
      nozzle_temperature_range_high: 230,
      nozzle_temperature_initial_layer: 205,
      idle_temperature: 150,
      chamber_temperature: 0,
      activate_chamber_temp_control: false,
      filament_max_volumetric_speed: 15,
      filament_adaptive_volumetric_speed: false,
      filament_shrink: '100%',
      filament_shrinkage_compensation_z: '100%',
      filament_is_support: false,
      filament_soluble: false,
      fan_min_speed: 20,
      fan_max_speed: 100,
      overhang_fan_speed: 100,
      close_fan_the_first_x_layers: 1,
      pressure_advance: 0.02,
      enable_pressure_advance: false,
      adaptive_pressure_advance: false,
      filament_extruder_variant: 'Direct Drive Standard',
    },
  },

  PETG: {
    extruder_temp: 240,
    bed_temp: 80,
    print_speed: 60,
    travel_speed: 150,
    layer_height: 0.2,
    flow_rate: 100,
    fan_speed: 50,
    retraction_length: 5.0,
    retraction_speed: 45.0,
    orcaslicer_settings: {
      nozzle_temperature_range_low: 220,
      nozzle_temperature_range_high: 260,
      nozzle_temperature_initial_layer: 235,
      idle_temperature: 200,
      chamber_temperature: 0,
      activate_chamber_temp_control: false,
      filament_max_volumetric_speed: 12,
      filament_adaptive_volumetric_speed: false,
      filament_shrink: '100%',
      filament_shrinkage_compensation_z: '100%',
      filament_is_support: false,
      filament_soluble: false,
      fan_min_speed: 30,
      fan_max_speed: 70,
      overhang_fan_speed: 70,
      close_fan_the_first_x_layers: 2,
      pressure_advance: 0.02,
      enable_pressure_advance: false,
      adaptive_pressure_advance: false,
      filament_extruder_variant: 'Direct Drive Standard',
    },
  },

  TPU: {
    extruder_temp: 230,
    bed_temp: 60,
    print_speed: 30,
    travel_speed: 150,
    layer_height: 0.2,
    flow_rate: 95,
    fan_speed: 0,
    retraction_length: 0,
    retraction_speed: 20,
    orcaslicer_settings: {
      nozzle_temperature_range_low: 210,
      nozzle_temperature_range_high: 250,
      nozzle_temperature_initial_layer: 225,
      idle_temperature: 150,
      chamber_temperature: 0,
      activate_chamber_temp_control: false,
      filament_max_volumetric_speed: 5,
      filament_adaptive_volumetric_speed: false,
      filament_shrink: '100%',
      filament_shrinkage_compensation_z: '100%',
      filament_is_support: false,
      filament_soluble: false,
      fan_min_speed: 0,
      fan_max_speed: 0,
      overhang_fan_speed: 0,
      close_fan_the_first_x_layers: 0,
      pressure_advance: 0,
      enable_pressure_advance: false,
      adaptive_pressure_advance: false,
      filament_extruder_variant: 'Direct Drive Standard',
    },
  },

  ASA: {
    extruder_temp: 270,
    bed_temp: 100,
    print_speed: 50,
    travel_speed: 150,
    layer_height: 0.2,
    flow_rate: 100,
    fan_speed: 10,
    retraction_length: 5.0,
    retraction_speed: 45.0,
    orcaslicer_settings: {
      nozzle_temperature_range_low: 240,
      nozzle_temperature_range_high: 280,
      nozzle_temperature_initial_layer: 260,
      idle_temperature: 170,
      chamber_temperature: 0,
      activate_chamber_temp_control: false,
      filament_max_volumetric_speed: 28.6,
      filament_adaptive_volumetric_speed: false,
      filament_shrink: '100%',
      filament_shrinkage_compensation_z: '100%',
      filament_is_support: false,
      filament_soluble: false,
      fan_min_speed: 10,
      fan_max_speed: 80,
      overhang_fan_speed: 80,
      close_fan_the_first_x_layers: 3,
      pressure_advance: 0.02,
      enable_pressure_advance: false,
      adaptive_pressure_advance: false,
      filament_extruder_variant: 'Direct Drive Standard',
    },
  },

  PA: {
    extruder_temp: 260,
    bed_temp: 80,
    print_speed: 50,
    travel_speed: 150,
    layer_height: 0.2,
    flow_rate: 95,
    fan_speed: 20,
    retraction_length: 5.0,
    retraction_speed: 45.0,
    orcaslicer_settings: {
      nozzle_temperature_range_low: 240,
      nozzle_temperature_range_high: 280,
      nozzle_temperature_initial_layer: 255,
      idle_temperature: 200,
      chamber_temperature: 0,
      activate_chamber_temp_control: false,
      filament_max_volumetric_speed: 12,
      filament_adaptive_volumetric_speed: false,
      filament_shrink: '100%',
      filament_shrinkage_compensation_z: '100%',
      filament_is_support: false,
      filament_soluble: false,
      fan_min_speed: 10,
      fan_max_speed: 50,
      overhang_fan_speed: 50,
      close_fan_the_first_x_layers: 3,
      pressure_advance: 0.02,
      enable_pressure_advance: false,
      adaptive_pressure_advance: false,
      filament_extruder_variant: 'Direct Drive Standard',
    },
  },

  PC: {
    extruder_temp: 280,
    bed_temp: 110,
    print_speed: 40,
    travel_speed: 150,
    layer_height: 0.2,
    flow_rate: 100,
    fan_speed: 0,
    retraction_length: 5.0,
    retraction_speed: 45.0,
    orcaslicer_settings: {
      nozzle_temperature_range_low: 260,
      nozzle_temperature_range_high: 300,
      nozzle_temperature_initial_layer: 275,
      idle_temperature: 220,
      chamber_temperature: 60,
      activate_chamber_temp_control: true,
      filament_max_volumetric_speed: 10,
      filament_adaptive_volumetric_speed: false,
      filament_shrink: '100%',
      filament_shrinkage_compensation_z: '100%',
      filament_is_support: false,
      filament_soluble: false,
      fan_min_speed: 0,
      fan_max_speed: 20,
      overhang_fan_speed: 20,
      close_fan_the_first_x_layers: 5,
      pressure_advance: 0.02,
      enable_pressure_advance: false,
      adaptive_pressure_advance: false,
      filament_extruder_variant: 'Direct Drive Standard',
    },
  },

  PVA: {
    extruder_temp: 200,
    bed_temp: 60,
    print_speed: 50,
    travel_speed: 150,
    layer_height: 0.2,
    flow_rate: 100,
    fan_speed: 100,
    retraction_length: 5.0,
    retraction_speed: 45.0,
    orcaslicer_settings: {
      nozzle_temperature_range_low: 190,
      nozzle_temperature_range_high: 220,
      nozzle_temperature_initial_layer: 205,
      idle_temperature: 150,
      chamber_temperature: 0,
      activate_chamber_temp_control: false,
      filament_max_volumetric_speed: 8,
      filament_adaptive_volumetric_speed: false,
      filament_shrink: '100%',
      filament_shrinkage_compensation_z: '100%',
      filament_is_support: true,
      filament_soluble: true,
      fan_min_speed: 50,
      fan_max_speed: 100,
      overhang_fan_speed: 100,
      close_fan_the_first_x_layers: 1,
      pressure_advance: 0.02,
      enable_pressure_advance: false,
      adaptive_pressure_advance: false,
      filament_extruder_variant: 'Direct Drive Standard',
    },
  },
};

/**
 * Получить стандартные значения для типа материала
 */
export function getMaterialDefaults(materialType: string): MaterialDefaults | null {
  return MATERIAL_DEFAULTS[materialType.toUpperCase()] || null;
}

/**
 * Применить стандартные значения к форме создания пресета
 */
export function applyMaterialDefaults(
  materialType: string,
  setters: {
    // Базовые параметры
    setExtruderTemp: (value: number) => void;
    setBedTemp: (value: number) => void;
    setPrintSpeed: (value: number) => void;
    setTravelSpeed: (value: number) => void;
    setFlowRate: (value: number) => void;
    setFanSpeed: (value: number) => void;
    setRetractionLength: (value: number) => void;
    setRetractionSpeed: (value: number) => void;

    // Расширенные параметры
    setTempRangeLow: (value: number | '') => void;
    setTempRangeHigh: (value: number | '') => void;
    setNozzleTempInitialLayer: (value: number | '') => void;
    setBedTempInitialLayer: (value: number | '') => void;
    setIdleTemperature: (value: number | '') => void;
    setChamberTemp: (value: number | '') => void;
    setEnableChamberControl: (value: boolean) => void;
    setVolumetricSpeed: (value: number | '') => void;
    setAdaptiveVolumetricSpeed: (value: boolean) => void;
    setFilamentShrink: (value: string) => void;
    setFilamentShrinkageCompensationZ: (value: string) => void;
    setFilamentIsSupport: (value: boolean) => void;
    setFilamentSoluble: (value: boolean) => void;
    setFanMinSpeed: (value: number | '') => void;
    setFanMaxSpeed: (value: number | '') => void;
    setOverhangFanSpeed: (value: number | '') => void;
    setCloseFanFirstXLayers: (value: number | '') => void;
    setPressureAdvance: (value: number | '') => void;
    setEnablePressureAdvance: (value: boolean) => void;
    setAdaptivePressureAdvance: (value: boolean) => void;
  }
): void {
  const defaults = getMaterialDefaults(materialType);
  if (!defaults) return;

  // Применяем базовые параметры
  setters.setExtruderTemp(defaults.extruder_temp);
  setters.setBedTemp(defaults.bed_temp);
  setters.setPrintSpeed(defaults.print_speed);
  setters.setTravelSpeed(defaults.travel_speed);
  setters.setFlowRate(defaults.flow_rate);
  setters.setFanSpeed(defaults.fan_speed);
  setters.setRetractionLength(defaults.retraction_length);
  setters.setRetractionSpeed(defaults.retraction_speed);

  // Применяем расширенные параметры
  const settings = defaults.orcaslicer_settings;
  if (settings.nozzle_temperature_range_low !== undefined) {
    setters.setTempRangeLow(settings.nozzle_temperature_range_low);
  }
  if (settings.nozzle_temperature_range_high !== undefined) {
    setters.setTempRangeHigh(settings.nozzle_temperature_range_high);
  }
  if (settings.nozzle_temperature_initial_layer !== undefined) {
    setters.setNozzleTempInitialLayer(settings.nozzle_temperature_initial_layer);
  }
  if (settings.bed_temperature_initial_layer !== undefined) {
    setters.setBedTempInitialLayer(settings.bed_temperature_initial_layer);
  }
  if (settings.idle_temperature !== undefined) {
    setters.setIdleTemperature(settings.idle_temperature);
  }
  if (settings.chamber_temperature !== undefined) {
    setters.setChamberTemp(settings.chamber_temperature);
  }
  if (settings.activate_chamber_temp_control !== undefined) {
    setters.setEnableChamberControl(settings.activate_chamber_temp_control);
  }
  if (settings.filament_max_volumetric_speed !== undefined) {
    setters.setVolumetricSpeed(settings.filament_max_volumetric_speed);
  }
  if (settings.filament_adaptive_volumetric_speed !== undefined) {
    setters.setAdaptiveVolumetricSpeed(settings.filament_adaptive_volumetric_speed);
  }
  if (settings.filament_shrink !== undefined) {
    setters.setFilamentShrink(settings.filament_shrink);
  }
  if (settings.filament_shrinkage_compensation_z !== undefined) {
    setters.setFilamentShrinkageCompensationZ(settings.filament_shrinkage_compensation_z);
  }
  if (settings.filament_is_support !== undefined) {
    setters.setFilamentIsSupport(settings.filament_is_support);
  }
  if (settings.filament_soluble !== undefined) {
    setters.setFilamentSoluble(settings.filament_soluble);
  }
  if (settings.fan_min_speed !== undefined) {
    setters.setFanMinSpeed(settings.fan_min_speed);
  }
  if (settings.fan_max_speed !== undefined) {
    setters.setFanMaxSpeed(settings.fan_max_speed);
  }
  if (settings.overhang_fan_speed !== undefined) {
    setters.setOverhangFanSpeed(settings.overhang_fan_speed);
  }
  if (settings.close_fan_the_first_x_layers !== undefined) {
    setters.setCloseFanFirstXLayers(settings.close_fan_the_first_x_layers);
  }
  if (settings.pressure_advance !== undefined) {
    setters.setPressureAdvance(settings.pressure_advance);
  }
  if (settings.enable_pressure_advance !== undefined) {
    setters.setEnablePressureAdvance(settings.enable_pressure_advance);
  }
  if (settings.adaptive_pressure_advance !== undefined) {
    setters.setAdaptivePressureAdvance(settings.adaptive_pressure_advance);
  }
}

// Порядок базовых типов в выпадающих списках: сначала распространённые
// «короткие» типы, затем (по алфавиту) подробные варианты (PLA Max, PLA Pro,
// -CF/-GF и т.д.). Список легко переупорядочить под предпочтения.
export const BASE_TYPE_PRIORITY = ['PLA', 'PETG', 'ABS', 'ASA', 'TPU', 'PA', 'PC', 'PVA', 'PET', 'HIPS', 'PP'];

export function sortMaterialTypes(types: string[]): string[] {
  const priorityIndex = (type: string): number => {
    const i = BASE_TYPE_PRIORITY.indexOf(type.toUpperCase());
    return i === -1 ? Number.MAX_SAFE_INTEGER : i;
  };
  return [...types].sort((a, b) => {
    const diff = priorityIndex(a) - priorityIndex(b);
    return diff !== 0 ? diff : a.localeCompare(b);
  });
}

