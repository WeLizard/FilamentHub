/**
 * Setting complexity levels mirrored from OrcaSlicer (`ConfigOptionDef.mode`).
 *
 * Extracted from upstream `src/libslic3r/PrintConfig.cpp` so our Simple /
 * Advanced / Expert selector matches exactly what Orca users already know —
 * no invented classification. `simple` is shown to everyone; `advanced` and
 * `expert` progressively reveal more. `develop` is treated as `expert`.
 *
 * Keys are OrcaSlicer config keys (the same ones buildOrcaslicerSettings emits).
 */

export type SettingMode = 'simple' | 'advanced' | 'expert';

export const MODE_RANK: Record<SettingMode, number> = { simple: 0, advanced: 1, expert: 2 };

/** OrcaSlicer mode per filament setting key. Absent key defaults to `simple`. */
export const ORCA_FIELD_MODE: Record<string, SettingMode> = {
  // --- Simple ---
  nozzle_temperature: 'simple',
  nozzle_temperature_initial_layer: 'simple',
  hot_plate_temp: 'simple',
  cool_plate_temp: 'simple',
  eng_plate_temp: 'simple',
  textured_plate_temp: 'simple',
  fan_min_speed: 'simple',
  fan_max_speed: 'simple',
  close_fan_the_first_x_layers: 'simple',
  additional_cooling_fan_speed: 'simple',
  slow_down_for_layer_cooling: 'simple',
  dont_slow_down_outer_wall: 'simple',
  reduce_fan_stop_start_freq: 'simple',
  chamber_temperature: 'simple',
  activate_chamber_temp_control: 'simple',
  idle_temperature: 'simple',
  temperature_vitrification: 'simple',
  enable_pressure_advance: 'simple',
  activate_air_filtration: 'simple',
  during_print_exhaust_fan_speed: 'simple',
  complete_print_exhaust_fan_speed: 'simple',
  slow_down_layer_time: 'simple',
  fan_cooling_layer_time: 'simple',
  // Filament overrides exposed in Simple (Orca keeps machine retract in Develop
  // but surfaces these basics on the filament — PrintConfig.cpp:7318).
  filament_retraction_length: 'simple',
  filament_z_hop: 'simple',
  filament_retraction_distances_when_cut: 'simple',
  filament_long_retractions_when_cut: 'simple',

  // --- Advanced ---
  pressure_advance: 'advanced',
  adaptive_pressure_advance: 'advanced',
  adaptive_pressure_advance_bridges: 'advanced',
  filament_flow_ratio: 'advanced',
  filament_max_volumetric_speed: 'advanced',
  filament_shrink: 'advanced',
  filament_shrinkage_compensation_z: 'advanced',
  filament_soluble: 'advanced',
  filament_is_support: 'advanced',
  full_fan_speed_layer: 'advanced',
  overhang_fan_speed: 'advanced',
  overhang_fan_threshold: 'advanced',
  internal_bridge_fan_speed: 'advanced',
  ironing_fan_speed: 'advanced',
  support_material_interface_fan_speed: 'advanced',
  slow_down_min_speed: 'advanced',
  // Filament overrides (retraction / wipe / z-hop) — advanced tier
  filament_retraction_speed: 'advanced',
  filament_deretraction_speed: 'advanced',
  filament_retraction_minimum_travel: 'advanced',
  filament_retract_before_wipe: 'advanced',
  filament_retract_when_changing_layer: 'advanced',
  filament_retract_restart_extra: 'advanced',
  filament_wipe: 'advanced',
  filament_wipe_distance: 'advanced',
  filament_z_hop_types: 'advanced',
  // Multimaterial (MMU / toolchange)
  filament_loading_speed: 'advanced',
  filament_loading_speed_start: 'advanced',
  filament_unloading_speed: 'advanced',
  filament_unloading_speed_start: 'advanced',
  filament_multitool_ramming: 'advanced',
  filament_multitool_ramming_flow: 'advanced',
  filament_multitool_ramming_volume: 'advanced',
  filament_toolchange_delay: 'advanced',
  filament_change_length: 'advanced',
  filament_start_gcode: 'advanced',
  filament_end_gcode: 'advanced',

  // --- Expert / Develop (comDevelop → expert) ---
  filament_adaptive_volumetric_speed: 'expert',
  volumetric_speed_coefficients: 'expert',
  required_nozzle_HRC: 'expert',
  filament_adhesiveness_category: 'expert',
};

/** True if a field of `fieldMode` (default 'simple') should show at `current`. */
export function isVisibleAtMode(fieldMode: SettingMode | undefined, current: SettingMode): boolean {
  return MODE_RANK[fieldMode ?? 'simple'] <= MODE_RANK[current];
}

/** Convenience: is a setting (by Orca key) visible at the current mode. */
export function isKeyVisible(key: string, current: SettingMode): boolean {
  return isVisibleAtMode(ORCA_FIELD_MODE[key], current);
}
