export type OrcaStructuredFieldKind =
  | 'boolean'
  | 'enum'
  | 'integer'
  | 'float'
  | 'percent'
  | 'floatOrPercent'
  | 'string'
  | 'stringList'
  | 'integerList'
  | 'floatList';

export type OrcaStructuredFieldTab =
  | 'quality'
  | 'strength'
  | 'speed'
  | 'support'
  | 'multimaterial'
  | 'others';

export interface OrcaStructuredFieldDef {
  key: string;
  kind: OrcaStructuredFieldKind;
  tab: OrcaStructuredFieldTab;
  section: string;
}

const splitLines = (value: string): string[] =>
  value
    .trim()
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

const buildFieldDefs = (
  kind: OrcaStructuredFieldKind,
  tab: OrcaStructuredFieldTab,
  section: string,
  keysBlock: string,
): OrcaStructuredFieldDef[] => splitLines(keysBlock).map((key) => ({ key, kind, tab, section }));

const enumValues = (valuesBlock: string): string[] => splitLines(valuesBlock);

export const ORCA_STRUCTURED_TAB_ORDER: OrcaStructuredFieldTab[] = [
  'quality',
  'strength',
  'speed',
  'support',
  'multimaterial',
  'others',
];

export const ORCA_STRUCTURED_SECTION_ORDER: Record<OrcaStructuredFieldTab, string[]> = {
  quality: [
    'layerHeight',
    'lineWidth',
    'seam',
    'precision',
    'ironing',
    'wallGenerator',
    'wallsAndSurfaces',
    'bridging',
    'overhangs',
  ],
  strength: ['walls', 'topBottomShells', 'infill', 'advanced'],
  speed: ['initialLayerSpeed', 'otherLayersSpeed', 'overhangSpeed', 'travelSpeed', 'acceleration', 'jerk', 'advanced'],
  support: ['support', 'raft', 'supportFilament', 'supportIroning', 'advanced', 'treeSupports'],
  multimaterial: ['primeTower', 'featureFilaments', 'oozePrevention', 'flushOptions', 'advanced'],
  others: ['skirt', 'brim', 'specialMode', 'fuzzySkin', 'gcodeOutput', 'postProcessing', 'notes'],
};

export const ORCA_ADVANCED_FIELD_DEFS: OrcaStructuredFieldDef[] = [
  ...buildFieldDefs(
    'boolean',
    'strength',
    'walls',
    `
alternate_extra_wall
detect_thin_wall
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'quality',
    'overhangs',
    `
extra_perimeters_on_overhangs
detect_overhang_wall
overhang_reverse
overhang_reverse_internal_only
make_overhang_printable
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'quality',
    'seam',
    `
staggered_inner_seams
role_based_wipe_speed
wipe_on_loops
wipe_before_external_loop
seam_slope_conditional
seam_slope_entire_loop
seam_slope_inner_walls
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'quality',
    'wallsAndSurfaces',
    `
reduce_crossing_wall
is_infill_first
only_one_wall_top
only_one_wall_first_layer
set_other_flow_ratios
small_area_infill_flow_compensation
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'strength',
    'infill',
    `
symmetric_infill_y_axis
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'strength',
    'advanced',
    `
align_infill_direction_to_model
infill_combination
detect_narrow_internal_solid_infill
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'quality',
    'ironing',
    `
ironing_angle_fixed
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'support',
    'supportIroning',
    `
support_ironing
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'support',
    'advanced',
    `
independent_support_layer_height
support_interface_loop_pattern
bridge_no_support
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'support',
    'support',
    `
support_on_build_plate_only
support_critical_regions_only
support_remove_small_overhang
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'support',
    'supportFilament',
    `
support_interface_not_for_body
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'support',
    'treeSupports',
    `
tree_support_auto_brim
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'quality',
    'bridging',
    `
thick_bridges
thick_internal_bridges
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'speed',
    'advanced',
    `
extrusion_rate_smoothing_external_perimeter_only
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'speed',
    'overhangSpeed',
    `
enable_overhang_speed
slowdown_for_curled_perimeters
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'speed',
    'acceleration',
    `
accel_to_decel_enable
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'multimaterial',
    'primeTower',
    `
enable_prime_tower
prime_tower_enable_framework
prime_tower_skip_points
prime_tower_flat_ironing
enable_tower_interface_features
enable_tower_interface_cooldown_during_tower
wipe_tower_no_sparse_layers
wipe_tower_fillet_wall
single_extruder_multi_material_priming
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'multimaterial',
    'oozePrevention',
    `
ooze_prevention
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'multimaterial',
    'flushOptions',
    `
flush_into_infill
flush_into_objects
flush_into_support
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'multimaterial',
    'advanced',
    `
interface_shells
interlocking_beam
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'quality',
    'precision',
    `
precise_z_height
precise_outer_wall
hole_to_polyhole
hole_to_polyhole_twisted
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'quality',
    'layerHeight',
    `
adaptive_layer_height
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'others',
    'skirt',
    `
single_loop_draft_shield
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'others',
    'brim',
    `
brim_use_efc_outline
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'others',
    'specialMode',
    `
spiral_mode_smooth
enable_wrapping_detection
calib_flowrate_topinfill_special_order
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'others',
    'fuzzySkin',
    `
fuzzy_skin_first_layer
`,
  ),
  ...buildFieldDefs(
    'boolean',
    'others',
    'gcodeOutput',
    `
reduce_infill_retraction
gcode_add_line_number
gcode_comments
gcode_label_objects
exclude_object
`,
  ),
  ...buildFieldDefs(
    'enum',
    'others',
    'specialMode',
    `
slicing_mode
print_sequence
print_order
timelapse_type
`,
  ),
  ...buildFieldDefs(
    'enum',
    'strength',
    'advanced',
    `
ensure_vertical_shell_thickness
`,
  ),
  ...buildFieldDefs(
    'enum',
    'quality',
    'wallsAndSurfaces',
    `
wall_direction
wall_sequence
`,
  ),
  ...buildFieldDefs(
    'enum',
    'strength',
    'topBottomShells',
    `
top_surface_pattern
bottom_surface_pattern
`,
  ),
  ...buildFieldDefs(
    'enum',
    'quality',
    'bridging',
    `
counterbore_hole_bridging
dont_filter_internal_bridges
enable_extra_bridge_layer
`,
  ),
  ...buildFieldDefs(
    'enum',
    'strength',
    'infill',
    `
internal_solid_infill_pattern
gap_fill_target
`,
  ),
  ...buildFieldDefs(
    'enum',
    'quality',
    'ironing',
    `
ironing_pattern
`,
  ),
  ...buildFieldDefs(
    'enum',
    'support',
    'supportIroning',
    `
support_ironing_pattern
`,
  ),
  ...buildFieldDefs(
    'enum',
    'others',
    'fuzzySkin',
    `
fuzzy_skin
fuzzy_skin_noise_type
fuzzy_skin_mode
`,
  ),
  ...buildFieldDefs(
    'enum',
    'others',
    'skirt',
    `
skirt_type
draft_shield
`,
  ),
  ...buildFieldDefs(
    'enum',
    'others',
    'brim',
    `
brim_type
`,
  ),
  ...buildFieldDefs(
    'enum',
    'support',
    'support',
    `
support_style
`,
  ),
  ...buildFieldDefs(
    'enum',
    'support',
    'advanced',
    `
support_base_pattern
support_interface_pattern
`,
  ),
  ...buildFieldDefs(
    'enum',
    'quality',
    'wallGenerator',
    `
wall_generator
`,
  ),
  ...buildFieldDefs(
    'enum',
    'multimaterial',
    'primeTower',
    `
wipe_tower_wall_type
`,
  ),
  ...buildFieldDefs(
    'enum',
    'quality',
    'seam',
    `
seam_slope_type
`,
  ),
  ...buildFieldDefs(
    'integer',
    'strength',
    'infill',
    `
fill_multiline
`,
  ),
  ...buildFieldDefs(
    'integer',
    'others',
    'fuzzySkin',
    `
fuzzy_skin_octaves
`,
  ),
  ...buildFieldDefs(
    'integer',
    'others',
    'skirt',
    `
skirt_height
`,
  ),
  ...buildFieldDefs(
    'integer',
    'support',
    'support',
    `
enforce_support_layers
`,
  ),
  ...buildFieldDefs(
    'integer',
    'support',
    'advanced',
    `
support_interface_top_layers
support_interface_bottom_layers
tree_support_wall_count
`,
  ),
  ...buildFieldDefs(
    'integer',
    'support',
    'supportFilament',
    `
support_filament
support_interface_filament
`,
  ),
  ...buildFieldDefs(
    'integer',
    'multimaterial',
    'featureFilaments',
    `
wall_filament
sparse_infill_filament
solid_infill_filament
wipe_tower_filament
`,
  ),
  ...buildFieldDefs(
    'integer',
    'multimaterial',
    'oozePrevention',
    `
standby_temperature_delta
preheat_steps
`,
  ),
  ...buildFieldDefs(
    'integer',
    'quality',
    'precision',
    `
elefant_foot_compensation_layers
`,
  ),
  ...buildFieldDefs(
    'integer',
    'quality',
    'wallGenerator',
    `
wall_distribution_count
`,
  ),
  ...buildFieldDefs(
    'integer',
    'speed',
    'initialLayerSpeed',
    `
slow_down_layers
`,
  ),
  ...buildFieldDefs(
    'integer',
    'quality',
    'seam',
    `
scarf_angle_threshold
seam_slope_steps
`,
  ),
  ...buildFieldDefs(
    'integer',
    'multimaterial',
    'advanced',
    `
interlocking_beam_layer_count
interlocking_depth
interlocking_boundary_avoidance
`,
  ),
  ...buildFieldDefs(
    'float',
    'quality',
    'precision',
    `
slice_closing_radius
elefant_foot_compensation
xy_contour_compensation
xy_hole_compensation
resolution
`,
  ),
  ...buildFieldDefs(
    'float',
    'others',
    'specialMode',
    `
spiral_starting_flow_ratio
spiral_finishing_flow_ratio
`,
  ),
  ...buildFieldDefs(
    'float',
    'strength',
    'topBottomShells',
    `
top_shell_thickness
bottom_shell_thickness
`,
  ),
  ...buildFieldDefs(
    'float',
    'strength',
    'infill',
    `
lateral_lattice_angle_1
lateral_lattice_angle_2
infill_overhang_angle
infill_direction
solid_infill_direction
infill_shift_step
infill_lock_depth
skin_infill_depth
filter_out_gap_fill
`,
  ),
  ...buildFieldDefs(
    'float',
    'strength',
    'advanced',
    `
minimum_sparse_infill_area
bridge_angle
internal_bridge_angle
`,
  ),
  ...buildFieldDefs(
    'float',
    'speed',
    'otherLayersSpeed',
    `
ironing_speed
top_surface_speed
support_speed
support_interface_speed
gap_infill_speed
small_perimeter_threshold
`,
  ),
  ...buildFieldDefs(
    'float',
    'support',
    'supportIroning',
    `
support_ironing_spacing
`,
  ),
  ...buildFieldDefs(
    'float',
    'others',
    'fuzzySkin',
    `
fuzzy_skin_thickness
fuzzy_skin_point_distance
fuzzy_skin_scale
fuzzy_skin_persistence
`,
  ),
  ...buildFieldDefs(
    'float',
    'speed',
    'advanced',
    `
max_volumetric_extrusion_rate_slope
max_volumetric_extrusion_rate_slope_segment_length
`,
  ),
  ...buildFieldDefs(
    'float',
    'support',
    'advanced',
    `
support_object_xy_distance
support_object_first_layer_gap
support_base_pattern_spacing
support_expansion
support_angle
support_interface_spacing
support_top_z_distance
max_bridge_length
support_bottom_z_distance
support_bottom_interface_spacing
`,
  ),
  ...buildFieldDefs(
    'float',
    'speed',
    'travelSpeed',
    `
travel_speed_z
`,
  ),
  ...buildFieldDefs(
    'float',
    'speed',
    'acceleration',
    `
outer_wall_acceleration
initial_layer_acceleration
top_surface_acceleration
inner_wall_acceleration
`,
  ),
  ...buildFieldDefs(
    'float',
    'others',
    'skirt',
    `
skirt_speed
min_skirt_length
skirt_distance
skirt_start_angle
`,
  ),
  ...buildFieldDefs(
    'float',
    'others',
    'brim',
    `
brim_object_gap
brim_ears_max_angle
brim_ears_detection_length
`,
  ),
  ...buildFieldDefs(
    'float',
    'support',
    'support',
    `
raft_first_layer_expansion
`,
  ),
  ...buildFieldDefs(
    'float',
    'support',
    'raft',
    `
raft_contact_distance
raft_expansion
`,
  ),
  ...buildFieldDefs(
    'float',
    'multimaterial',
    'oozePrevention',
    `
preheat_time
`,
  ),
  ...buildFieldDefs(
    'float',
    'quality',
    'bridging',
    `
bridge_flow
internal_bridge_flow
`,
  ),
  ...buildFieldDefs(
    'float',
    'multimaterial',
    'primeTower',
    `
prime_tower_width
prime_tower_brim_width
prime_volume
wipe_tower_cone_angle
wipe_tower_max_purge_speed
wipe_tower_extra_rib_length
wipe_tower_rib_width
wipe_tower_bridging
wipe_tower_rotation_angle
`,
  ),
  ...buildFieldDefs(
    'float',
    'support',
    'treeSupports',
    `
tree_support_branch_angle
tree_support_angle_slow
tree_support_branch_distance
tree_support_tip_diameter
tree_support_branch_diameter
tree_support_branch_diameter_angle
tree_support_brim_width
tree_support_branch_distance_organic
tree_support_branch_diameter_organic
tree_support_branch_angle_organic
`,
  ),
  ...buildFieldDefs(
    'float',
    'quality',
    'wallGenerator',
    `
wall_transition_angle
min_length_factor
`,
  ),
  ...buildFieldDefs(
    'float',
    'speed',
    'jerk',
    `
default_jerk
outer_wall_jerk
inner_wall_jerk
infill_jerk
top_surface_jerk
initial_layer_jerk
travel_jerk
default_junction_deviation
`,
  ),
  ...buildFieldDefs(
    'float',
    'quality',
    'wallsAndSurfaces',
    `
top_solid_infill_flow_ratio
bottom_solid_infill_flow_ratio
print_flow_ratio
first_layer_flow_ratio
outer_wall_flow_ratio
inner_wall_flow_ratio
overhang_flow_ratio
sparse_infill_flow_ratio
internal_solid_infill_flow_ratio
gap_fill_flow_ratio
support_flow_ratio
support_interface_flow_ratio
`,
  ),
  ...buildFieldDefs(
    'float',
    'quality',
    'overhangs',
    `
make_overhang_printable_angle
make_overhang_printable_hole_size
`,
  ),
  ...buildFieldDefs(
    'float',
    'multimaterial',
    'advanced',
    `
mmu_segmented_region_max_width
mmu_segmented_region_interlocking_depth
interlocking_orientation
interlocking_beam_width
`,
  ),
  ...buildFieldDefs(
    'float',
    'quality',
    'seam',
    `
scarf_joint_flow_ratio
seam_slope_min_length
`,
  ),
  ...buildFieldDefs(
    'percent',
    'strength',
    'topBottomShells',
    `
top_surface_density
bottom_surface_density
top_bottom_infill_wall_overlap
`,
  ),
  ...buildFieldDefs(
    'percent',
    'strength',
    'infill',
    `
skeleton_infill_density
skin_infill_density
infill_wall_overlap
`,
  ),
  ...buildFieldDefs(
    'percent',
    'quality',
    'ironing',
    `
ironing_flow
`,
  ),
  ...buildFieldDefs(
    'percent',
    'support',
    'supportIroning',
    `
support_ironing_flow
`,
  ),
  ...buildFieldDefs(
    'percent',
    'support',
    'support',
    `
raft_first_layer_density
`,
  ),
  ...buildFieldDefs(
    'percent',
    'multimaterial',
    'primeTower',
    `
prime_tower_infill_gap
wipe_tower_extra_spacing
wipe_tower_extra_flow
`,
  ),
  ...buildFieldDefs(
    'percent',
    'support',
    'treeSupports',
    `
tree_support_top_rate
`,
  ),
  ...buildFieldDefs(
    'percent',
    'quality',
    'wallGenerator',
    `
wall_transition_length
wall_transition_filter_deviation
min_feature_size
min_bead_width
initial_layer_min_bead_width
`,
  ),
  ...buildFieldDefs(
    'percent',
    'speed',
    'acceleration',
    `
accel_to_decel_factor
`,
  ),
  ...buildFieldDefs(
    'percent',
    'quality',
    'bridging',
    `
bridge_density
internal_bridge_density
`,
  ),
  ...buildFieldDefs(
    'percent',
    'quality',
    'seam',
    `
scarf_overhang_threshold
`,
  ),
  ...buildFieldDefs(
    'floatOrPercent',
    'others',
    'specialMode',
    `
spiral_mode_max_xy_smoothing
`,
  ),
  ...buildFieldDefs(
    'floatOrPercent',
    'quality',
    'overhangs',
    `
overhang_reverse_threshold
`,
  ),
  ...buildFieldDefs(
    'floatOrPercent',
    'quality',
    'wallsAndSurfaces',
    `
max_travel_detour_distance
min_width_top_surface
`,
  ),
  ...buildFieldDefs(
    'floatOrPercent',
    'speed',
    'overhangSpeed',
    `
internal_bridge_speed
overhang_1_4_speed
overhang_2_4_speed
overhang_3_4_speed
overhang_4_4_speed
`,
  ),
  ...buildFieldDefs(
    'floatOrPercent',
    'support',
    'support',
    `
support_threshold_overlap
`,
  ),
  ...buildFieldDefs(
    'floatOrPercent',
    'quality',
    'lineWidth',
    `
line_width
initial_layer_line_width
inner_wall_line_width
outer_wall_line_width
sparse_infill_line_width
internal_solid_infill_line_width
skin_infill_line_width
skeleton_infill_line_width
top_surface_line_width
support_line_width
`,
  ),
  ...buildFieldDefs(
    'floatOrPercent',
    'strength',
    'advanced',
    `
infill_combination_max_layer_height
`,
  ),
  ...buildFieldDefs(
    'floatOrPercent',
    'speed',
    'otherLayersSpeed',
    `
small_perimeter_speed
`,
  ),
  ...buildFieldDefs(
    'floatOrPercent',
    'quality',
    'seam',
    `
seam_gap
wipe_speed
scarf_joint_speed
seam_slope_start_height
`,
  ),
  ...buildFieldDefs(
    'floatOrPercent',
    'speed',
    'acceleration',
    `
bridge_acceleration
sparse_infill_acceleration
internal_solid_infill_acceleration
`,
  ),
  ...buildFieldDefs(
    'floatOrPercent',
    'speed',
    'initialLayerSpeed',
    `
initial_layer_travel_speed
`,
  ),
  ...buildFieldDefs(
    'floatOrPercent',
    'strength',
    'infill',
    `
infill_anchor
infill_anchor_max
`,
  ),
  ...buildFieldDefs(
    'floatOrPercent',
    'quality',
    'precision',
    `
hole_to_polyhole_threshold
`,
  ),
  ...buildFieldDefs(
    'string',
    'strength',
    'infill',
    `
sparse_infill_rotate_template
solid_infill_rotate_template
`,
  ),
  ...buildFieldDefs(
    'string',
    'strength',
    'advanced',
    `
extra_solid_infills
`,
  ),
  ...buildFieldDefs(
    'string',
    'others',
    'gcodeOutput',
    `
filename_format
`,
  ),
  ...buildFieldDefs(
    'stringList',
    'others',
    'specialMode',
    `
print_extruder_variant
`,
  ),
  ...buildFieldDefs(
    'stringList',
    'others',
    'postProcessing',
    `
post_process
`,
  ),
  ...buildFieldDefs(
    'stringList',
    'quality',
    'wallsAndSurfaces',
    `
small_area_infill_flow_compensation_model
`,
  ),
  ...buildFieldDefs(
    'integerList',
    'multimaterial',
    'featureFilaments',
    `
print_extruder_id
`,
  ),
  ...buildFieldDefs(
    'floatList',
    'multimaterial',
    'flushOptions',
    `
wiping_volumes_extruders
`,
  ),
];

export const ORCA_ADVANCED_FIELD_KEYS = new Set(ORCA_ADVANCED_FIELD_DEFS.map((field) => field.key));

export const ORCA_ADVANCED_FIELD_LABELS: Record<string, { en: string; ru: string }> = {
  accel_to_decel_enable: { en: 'Enable accel_to_decel', ru: 'Включить accel_to_decel' },
  accel_to_decel_factor: { en: 'accel_to_decel factor', ru: 'Коэффициент accel_to_decel' },
  adaptive_layer_height: { en: 'Adaptive layer height', ru: 'Адаптивная высота слоя' },
  alternate_extra_wall: { en: 'Alternate extra wall', ru: 'Чередующийся доп. периметр' },
  bottom_shell_thickness: { en: 'Bottom shell thickness', ru: 'Толщина оболочки снизу' },
  bottom_solid_infill_flow_ratio: { en: 'Bottom surface flow ratio', ru: 'Поток нижней поверхности' },
  bottom_surface_pattern: { en: 'Bottom surface pattern', ru: 'Шаблон заполнения нижней поверхности' },
  bridge_acceleration: { en: 'Bridge', ru: 'Мосты' },
  bridge_angle: { en: 'External bridge infill direction', ru: 'Угол внешних мостов' },
  bridge_density: { en: 'External bridge density', ru: 'Плотность внешних мостов' },
  bridge_flow: { en: 'Bridge flow ratio', ru: 'Поток внешних мостов' },
  bridge_no_support: { en: 'Don\'t support bridges', ru: 'Не печатать поддержки под мостами' },
  brim_ears_detection_length: { en: 'Brim ear detection radius', ru: 'Радиус обнаружения ушек' },
  brim_ears_max_angle: { en: 'Brim ear max angle', ru: 'Максимальный угол ушек' },
  brim_object_gap: { en: 'Brim-object gap', ru: 'Смещение каймы' },
  brim_type: { en: 'Brim type', ru: 'Тип каймы' },
  brim_use_efc_outline: { en: 'Brim follows compensated outline', ru: 'Учитывать сдвиг контура' },
  calib_flowrate_topinfill_special_order: { en: 'Ironing Type', ru: 'Тип разглаживания' },
  counterbore_hole_bridging: { en: 'Bridge counterbore holes', ru: 'Опора отверстий в мостах' },
  default_jerk: { en: 'Default', ru: 'По умолчанию' },
  default_junction_deviation: { en: 'Junction deviation', ru: 'Junction deviation' },
  detect_narrow_internal_solid_infill: { en: 'Detect narrow internal solid infill', ru: 'Оптимизация заполнения узких мест' },
  detect_overhang_wall: { en: 'Detect overhang wall', ru: 'Обнаруживать нависающие периметры' },
  dont_filter_internal_bridges: { en: 'Filter out small internal bridges', ru: 'Убрать небольшие внутренние мосты (beta)' },
  draft_shield: { en: 'Draft shield', ru: 'Защитный кожух' },
  elefant_foot_compensation: { en: 'Elephant foot compensation', ru: 'Компенсация «слоновьей ноги»' },
  enable_extra_bridge_layer: { en: 'Extra bridge layers (beta)', ru: 'Двухслойные мосты (beta)' },
  enable_overhang_speed: { en: 'Slow down for overhang', ru: 'Замедляться на нависаниях' },
  enable_prime_tower: { en: 'Enable prime tower', ru: 'Включить prime tower' },
  enable_tower_interface_cooldown_during_tower: { en: 'Cool down from interface boost during prime tower', ru: 'Ранний сброс температуры' },
  enforce_support_layers: { en: 'Enforce support for the first layers', ru: 'Поддержка первых слоёв' },
  ensure_vertical_shell_thickness: { en: 'Ensure vertical shell thickness', ru: 'Сохранение толщины вертикальной оболочки' },
  exclude_object: { en: 'Exclude objects', ru: 'Исключение объектов' },
  extra_perimeters_on_overhangs: { en: 'Extra perimeters on overhangs', ru: 'Дополнительные периметры на нависаниях' },
  extrusion_rate_smoothing_external_perimeter_only: { en: 'Apply only on external features', ru: 'Применять только к видимым элементам' },
  filename_format: { en: 'Filename format', ru: 'Формат имени файла' },
  fill_multiline: { en: 'Sparse infill pattern', ru: 'Шаблон заполнения' },
  filter_out_gap_fill: { en: 'Filter out tiny gaps', ru: 'Минимальная длина щели' },
  first_layer_flow_ratio: { en: 'First layer flow ratio', ru: 'Первый слой модели' },
  flush_into_objects: { en: 'Flush into this object', ru: 'Прочищать в эту модель' },
  flush_into_support: { en: 'Flush into objects\' support', ru: 'Прочистка в поддержку' },
  fuzzy_skin: { en: 'Fuzzy Skin', ru: 'Нечёткая оболочка' },
  fuzzy_skin_first_layer: { en: 'Apply fuzzy skin to first layer', ru: 'Применять на первом слое' },
  fuzzy_skin_mode: { en: 'Fuzzy skin generator mode', ru: 'Метод создания оболочки' },
  fuzzy_skin_noise_type: { en: 'Fuzzy skin noise type', ru: 'Алгоритм генерации' },
  fuzzy_skin_octaves: { en: 'Fuzzy Skin Noise Octaves', ru: 'Количество октав нечёткой оболочки' },
  fuzzy_skin_persistence: { en: 'Fuzzy skin noise persistence', ru: 'Затухание шума нечёткой оболочки' },
  fuzzy_skin_point_distance: { en: 'Fuzzy skin point distance', ru: 'Длина сегментов' },
  fuzzy_skin_scale: { en: 'Fuzzy skin feature size', ru: 'Размер элемента нечёткой оболочки' },
  fuzzy_skin_thickness: { en: 'Fuzzy skin thickness', ru: 'Максимальное отклонение' },
  gap_fill_flow_ratio: { en: 'Gap fill flow ratio', ru: 'Заполнение щелей' },
  gap_fill_target: { en: 'Apply gap fill', ru: 'Заполнение щелей' },
  gap_infill_speed: { en: 'Gap infill', ru: 'Заполнение щелей' },
  gcode_add_line_number: { en: 'Add line number', ru: 'Нумеровать строки' },
  gcode_comments: { en: 'Verbose G-code', ru: 'Подробный G-код' },
  gcode_label_objects: { en: 'Label objects', ru: 'Помечать модели' },
  hole_to_polyhole: { en: 'Convert holes to polyholes', ru: 'Многогранные отверстия' },
  hole_to_polyhole_threshold: { en: 'Polyhole detection margin', ru: 'Предел обнаружения' },
  hole_to_polyhole_twisted: { en: 'Polyhole twist', ru: 'Скручивание многогранника' },
  independent_support_layer_height: { en: 'Independent support layer height', ru: 'Независимая высота слоя поддержки' },
  infill_anchor_max: { en: 'Maximum length of the infill anchor', ru: 'Предел стыковки линий шаблона' },
  infill_combination: { en: 'Infill combination', ru: 'Объединение слоёв заполнения' },
  infill_combination_max_layer_height: { en: 'Infill combination - Max layer height', ru: 'Предел высоты объединённого слоя' },
  infill_direction: { en: 'Sparse infill direction', ru: 'Угол шаблона заполнения' },
  infill_jerk: { en: 'Infill', ru: 'Заполнение' },
  infill_overhang_angle: { en: 'Sparse infill anchor length', ru: 'Длина привязок шаблона заполнения' },
  infill_wall_overlap: { en: 'Infill/Wall overlap', ru: 'Перекрытие заполнения с периметром' },
  initial_layer_acceleration: { en: 'First layer', ru: 'Первый слой' },
  initial_layer_jerk: { en: 'First layer', ru: 'Первый слой' },
  initial_layer_line_width: { en: 'First layer', ru: 'Первый слой' },
  initial_layer_min_bead_width: { en: 'First layer minimum wall width', ru: 'Минимальная ширина периметра первого слоя' },
  initial_layer_travel_speed: { en: 'First layer travel speed', ru: 'Холостые перемещения' },
  inner_wall_acceleration: { en: 'Inner wall', ru: 'Внутренние периметры' },
  inner_wall_flow_ratio: { en: 'Inner wall flow ratio', ru: 'Внутренние периметры' },
  inner_wall_jerk: { en: 'Inner wall', ru: 'Внутренние периметры' },
  inner_wall_line_width: { en: 'Inner wall', ru: 'Внутренние периметры' },
  internal_bridge_angle: { en: 'Internal bridge infill direction', ru: 'Угол внутренних мостов' },
  internal_bridge_density: { en: 'Internal bridge density', ru: 'Плотность внутренних мостов' },
  internal_bridge_flow: { en: 'Internal bridge flow ratio', ru: 'Поток внутренних мостов' },
  internal_bridge_speed: { en: 'Internal', ru: 'Внутренние' },
  internal_solid_infill_acceleration: { en: 'Internal solid infill', ru: 'Сплошное заполнение' },
  internal_solid_infill_flow_ratio: { en: 'Internal solid infill flow ratio', ru: 'Сплошное заполнение' },
  internal_solid_infill_line_width: { en: 'Internal solid infill', ru: 'Сплошное заполнение' },
  ironing_angle_fixed: { en: 'Fixed ironing angle', ru: 'Фиксированный угол разглаживания' },
  ironing_flow: { en: 'Ironing flow', ru: 'Поток' },
  line_width: { en: 'Default', ru: 'По умолчанию' },
  make_overhang_printable: { en: 'Make overhangs printable', ru: 'Делать нависания пригодными для печати' },
  make_overhang_printable_angle: { en: 'Make overhangs printable - Maximum angle', ru: 'Делать нависания пригодными для печати под максимальным углом' },
  make_overhang_printable_hole_size: { en: 'Make overhangs printable - Hole area', ru: 'Делать нависания отверстий пригодными для печати' },
  max_bridge_length: { en: 'Max bridge length', ru: 'Максимальный интервал опор' },
  max_travel_detour_distance: { en: 'Avoid crossing walls - Max detour length', ru: 'Максимальная длина обхода' },
  max_volumetric_extrusion_rate_slope: { en: 'Extrusion rate smoothing', ru: 'Сглаживание подачи' },
  max_volumetric_extrusion_rate_slope_segment_length: { en: 'Smoothing segment length', ru: 'Длина сглаживающего сегмента' },
  min_bead_width: { en: 'Minimum wall width', ru: 'Минимальная ширина периметра' },
  min_feature_size: { en: 'Minimum feature size', ru: 'Минимальный размер элемента' },
  min_length_factor: { en: 'Minimum wall length', ru: 'Минимальная длина периметра' },
  min_skirt_length: { en: 'Skirt minimum extrusion length', ru: 'Минимальная длина юбки' },
  min_width_top_surface: { en: 'One wall threshold', ru: 'Порог одного периметра' },
  minimum_sparse_infill_area: { en: 'Minimum sparse infill threshold', ru: 'Мин. порог разреженного заполнения' },
  only_one_wall_first_layer: { en: 'Only one wall on first layer', ru: 'Только один периметр на первом слое' },
  only_one_wall_top: { en: 'Only one wall on top surfaces', ru: 'Только один периметр на верхней поверхности' },
  ooze_prevention: { en: 'Enable ooze prevention', ru: 'Включить защиту от подтекания' },
  outer_wall_acceleration: { en: 'Outer wall', ru: 'Внешние периметры' },
  outer_wall_flow_ratio: { en: 'Outer wall flow ratio', ru: 'Внешние периметры' },
  outer_wall_jerk: { en: 'Outer wall', ru: 'Внешние периметры' },
  outer_wall_line_width: { en: 'Outer wall', ru: 'Внешние периметры' },
  overhang_flow_ratio: { en: 'Overhang flow ratio', ru: 'Нависания' },
  overhang_reverse: { en: 'Reverse on even', ru: 'Реверс на чётных слоях' },
  overhang_reverse_internal_only: { en: 'Reverse only internal perimeters', ru: 'Реверс только для внутренних периметров' },
  overhang_reverse_threshold: { en: 'Reverse threshold', ru: 'Порог для реверса' },
  post_process: { en: 'Post-processing Scripts', ru: 'Скрипты постобработки' },
  precise_outer_wall: { en: 'Precise wall', ru: 'Точные периметры' },
  preheat_steps: { en: 'Preheat steps', ru: 'Шагов преднагрева' },
  preheat_time: { en: 'Preheat time', ru: 'Время преднагрева' },
  prime_tower_brim_width: { en: 'Brim width', ru: 'Ширина каймы' },
  prime_tower_enable_framework: { en: 'Internal ribs', ru: 'Внутренние рёбра' },
  prime_tower_infill_gap: { en: 'Flush into objects\' infill', ru: 'Прочистка в заполнение' },
  prime_tower_skip_points: { en: 'Enable tower interface features', ru: 'Улучшенная адгезия' },
  prime_tower_width: { en: 'Width', ru: 'Ширина' },
  prime_volume: { en: 'Prime volume', ru: 'Объём сброса материала на черновой башне' },
  print_flow_ratio: { en: 'Flow ratio', ru: 'Коэффициент потока' },
  print_order: { en: 'Intra-layer order', ru: 'Очерёдность моделей' },
  raft_expansion: { en: 'Raft expansion', ru: 'Расширение подложки' },
  raft_first_layer_density: { en: 'First layer density', ru: 'Плотность первого слоя' },
  raft_first_layer_expansion: { en: 'First layer expansion', ru: 'Расширение первого слоя' },
  reduce_infill_retraction: { en: 'Reduce infill retraction', ru: 'Откат только при пересечении периметров' },
  role_based_wipe_speed: { en: 'Role base wipe speed', ru: 'Местная скорость очистки' },
  scarf_angle_threshold: { en: 'Conditional angle threshold', ru: 'Порог угла для косого шва' },
  scarf_joint_flow_ratio: { en: 'Scarf joint flow ratio', ru: 'Поток косого шва' },
  scarf_joint_speed: { en: 'Scarf joint speed', ru: 'Скорость косого шва' },
  scarf_overhang_threshold: { en: 'Conditional overhang threshold', ru: 'Порог нависания' },
  seam_gap: { en: 'Seam gap', ru: 'Зазор шва' },
  seam_slope_conditional: { en: 'Conditional scarf joint', ru: 'Ограничения косого шва' },
  seam_slope_entire_loop: { en: 'Scarf around entire wall', ru: 'Косой шов вдоль всего периметра' },
  seam_slope_inner_walls: { en: 'Scarf joint for inner walls', ru: 'Косой шов для внутренних периметров' },
  seam_slope_min_length: { en: 'Scarf length', ru: 'Длина косого шва' },
  seam_slope_start_height: { en: 'Scarf start height', ru: 'Начальная высота косого шва' },
  seam_slope_steps: { en: 'Scarf steps', ru: 'Шагов косого шва' },
  seam_slope_type: { en: 'Scarf joint seam (beta)', ru: 'Косой шов (beta)' },
  set_other_flow_ratios: { en: 'Set other flow ratios', ru: 'Другие настройки потока' },
  single_extruder_multi_material_priming: { en: 'Prime all printing extruders', ru: 'Подготовка всех печатающих экструдеров' },
  single_loop_draft_shield: { en: 'Single loop after first layer', ru: 'Один контур после первого слоя' },
  skin_infill_line_width: { en: 'Skin line width', ru: 'Ширина линии оболочки' },
  skirt_distance: { en: 'Skirt distance', ru: 'Смещение юбки' },
  skirt_height: { en: 'Skirt height', ru: 'Слоёв юбки' },
  skirt_speed: { en: 'Skirt speed', ru: 'Скорость юбки' },
  skirt_start_angle: { en: 'Skirt start point', ru: 'Начальная точка юбки' },
  skirt_type: { en: 'Skirt type', ru: 'Тип юбки' },
  slice_closing_radius: { en: 'Slice gap closing radius', ru: 'Радиус закрытия зазоров полигональной сетки' },
  slicing_mode: { en: 'Slicing Mode', ru: 'Режим нарезки' },
  slow_down_layers: { en: 'Number of slow layers', ru: 'Количество медленных слоёв' },
  slowdown_for_curled_perimeters: { en: 'Slow down for curled perimeters', ru: 'Замедляться на изогнутых периметрах' },
  small_area_infill_flow_compensation: { en: 'Small area flow compensation (beta)', ru: 'Компенсация потока небольших областей (beta)' },
  small_area_infill_flow_compensation_model: { en: 'Flow Compensation Model', ru: 'Модель компенсации потока' },
  small_perimeter_speed: { en: 'Small perimeters', ru: 'Короткие периметры' },
  small_perimeter_threshold: { en: 'Small perimeters threshold', ru: 'Порог коротких периметров' },
  solid_infill_direction: { en: 'Solid infill direction', ru: 'Угол шаблона сплошного заполнения' },
  solid_infill_filament: { en: 'Solid infill', ru: 'Сплошное заполнение' },
  sparse_infill_acceleration: { en: 'Sparse infill', ru: 'Заполнение' },
  sparse_infill_flow_ratio: { en: 'Sparse infill flow ratio', ru: 'Заполнение' },
  sparse_infill_line_width: { en: 'Sparse infill', ru: 'Заполнение' },
  spiral_finishing_flow_ratio: { en: 'Spiral finishing flow ratio', ru: 'Поток конца контура' },
  spiral_mode_max_xy_smoothing: { en: 'Max XY Smoothing', ru: 'Радиус выборки' },
  spiral_mode_smooth: { en: 'Smooth Spiral', ru: 'Сглаживание слоёв вазы' },
  spiral_starting_flow_ratio: { en: 'Spiral starting flow ratio', ru: 'Поток начала контура' },
  staggered_inner_seams: { en: 'Staggered inner seams', ru: 'Смещать внутренние швы' },
  standby_temperature_delta: { en: 'Temperature variation', ru: 'Разница температур' },
  support_line_width: { en: 'Support', ru: 'Поддержки' },
  support_angle: { en: 'Pattern angle', ru: 'Угол шаблона поддержки' },
  support_base_pattern: { en: 'Base pattern', ru: 'Шаблон поддержки' },
  support_base_pattern_spacing: { en: 'Base pattern spacing', ru: 'Отступ между линиями поддержки' },
  support_bottom_interface_spacing: { en: 'Bottom interface spacing', ru: 'Отступ между линиями связующего слоя снизу' },
  support_bottom_z_distance: { en: 'Bottom Z distance', ru: 'Зазор поддержки снизу' },
  support_critical_regions_only: { en: 'Ignore small overhangs', ru: 'Игнорировать небольшие нависания' },
  support_expansion: { en: 'Normal Support expansion', ru: 'Горизонтальное расширение поддержки' },
  support_flow_ratio: { en: 'Support flow ratio', ru: 'Поддержки' },
  support_interface_bottom_layers: { en: 'Bottom interface layers', ru: 'Связующие слои снизу' },
  support_interface_flow_ratio: { en: 'Support interface flow ratio', ru: 'Интерфейс поддержек' },
  support_interface_loop_pattern: { en: 'Interface use loop pattern', ru: 'Связующий слой петлями' },
  support_interface_not_for_body: { en: 'Support', ru: 'Поддержки' },
  support_interface_pattern: { en: 'Interface pattern', ru: 'Шаблон связующего слоя' },
  support_interface_spacing: { en: 'Top interface spacing', ru: 'Отступ между линиями связующего слоя сверху' },
  support_interface_speed: { en: 'Support interface', ru: 'Связующий слой' },
  support_interface_top_layers: { en: 'Top interface layers', ru: 'Связующие слои сверху' },
  support_ironing: { en: 'Ironing Support Interface', ru: 'Разглаживать связующий слой поддержки' },
  support_ironing_flow: { en: 'Support Ironing flow', ru: 'Поток разглаживания поддержки' },
  support_ironing_spacing: { en: 'Support Ironing line spacing', ru: 'Расстояние между линиями разглаживания поддержки' },
  support_object_first_layer_gap: { en: 'Support/object first layer gap', ru: 'Зазор между моделью и поддержкой на первом слое' },
  support_object_xy_distance: { en: 'Support/object XY distance', ru: 'Зазор между моделью и поддержкой по XY' },
  support_on_build_plate_only: { en: 'On build plate only', ru: 'Поддержка только от стола' },
  support_speed: { en: 'Support', ru: 'Поддержки' },
  support_style: { en: 'Style', ru: 'Стиль' },
  support_threshold_overlap: { en: 'Threshold overlap', ru: 'Порог перекрытия' },
  support_top_z_distance: { en: 'Top Z distance', ru: 'Зазор поддержки сверху' },
  skeleton_infill_line_width: { en: 'Skeleton line width', ru: 'Ширина линии каркаса' },
  thick_bridges: { en: 'Thick external bridges', ru: 'Толстые внешние мосты' },
  thick_internal_bridges: { en: 'Thick internal bridges', ru: 'Толстые внутренние мосты' },
  timelapse_type: { en: 'Timelapse', ru: 'Таймлапсы' },
  top_bottom_infill_wall_overlap: { en: 'Top/Bottom solid infill/wall overlap', ru: 'Перекрытие заполнения поверхности с периметром' },
  top_shell_thickness: { en: 'Top shell thickness', ru: 'Толщина оболочки сверху' },
  top_solid_infill_flow_ratio: { en: 'Top surface flow ratio', ru: 'Поток верхней поверхности' },
  top_surface_acceleration: { en: 'Top surface', ru: 'Верхняя поверхность' },
  top_surface_density: { en: 'Top surface density', ru: 'Плотность верхней поверхности' },
  top_surface_jerk: { en: 'Top surface', ru: 'Верхняя поверхность' },
  top_surface_line_width: { en: 'Top surface', ru: 'Верхняя поверхность' },
  top_surface_pattern: { en: 'Top surface pattern', ru: 'Шаблон заполнения верхней поверхности' },
  top_surface_speed: { en: 'Top surface', ru: 'Верхняя поверхность' },
  travel_jerk: { en: 'Travel', ru: 'Перемещения' },
  travel_speed_z: { en: 'Z travel', ru: 'Перемещение по Z' },
  tree_support_angle_slow: { en: 'Preferred Branch Angle', ru: 'Основной наклон ветвей' },
  tree_support_auto_brim: { en: 'Auto brim width', ru: 'Автоширина каймы' },
  tree_support_branch_angle: { en: 'Tree support branch angle', ru: 'Макс. наклон ветвей' },
  tree_support_branch_angle_organic: { en: 'Tree support branch angle', ru: 'Макс. наклон ветвей' },
  tree_support_branch_diameter_angle: { en: 'Branch Diameter Angle', ru: 'Конусность поддержки' },
  tree_support_branch_diameter_organic: { en: 'Support wall loops', ru: 'Периметры поддержки' },
  tree_support_branch_distance_organic: { en: 'Branch Density', ru: 'Плотность ветвей' },
  tree_support_brim_width: { en: 'Tree support brim width', ru: 'Ширина каймы древовидной поддержки' },
  tree_support_tip_diameter: { en: 'Tip Diameter', ru: 'Диаметр кончиков ветвей' },
  wall_direction: { en: 'Wall loop direction', ru: 'Направление печати периметров' },
  wall_distribution_count: { en: 'Wall distribution count', ru: 'Количество изменяемых периметров' },
  wall_filament: { en: 'Walls', ru: 'Периметры' },
  wall_generator: { en: 'Wall generator', ru: 'Генератор периметров' },
  wall_sequence: { en: 'Walls printing order', ru: 'Порядок печати периметров' },
  wall_transition_angle: { en: 'Wall transitioning threshold angle', ru: 'Пороговый угол перехода между периметрами' },
  wall_transition_filter_deviation: { en: 'Wall transitioning filter margin', ru: 'Граница фильтрации переходов между периметрами' },
  wall_transition_length: { en: 'Wall transition length', ru: 'Длина перехода между периметрами' },
  wipe_before_external_loop: { en: 'Wipe before external loop', ru: 'Смещённая подача перед внешним периметром' },
  wipe_on_loops: { en: 'Wipe on loops', ru: 'Сброс давления на шве' },
  wipe_speed: { en: 'Wipe speed', ru: 'Скорость очистки' },
  wipe_tower_bridging: { en: 'Maximal bridging distance', ru: 'Максимальная длина моста' },
  wipe_tower_cone_angle: { en: 'Stabilization cone apex angle', ru: 'Угол вершины стабилизирующего конуса' },
  wipe_tower_extra_flow: { en: 'Extra flow for purging', ru: 'Дополнительный поток для очистки' },
  wipe_tower_extra_spacing: { en: 'Wipe tower purge lines spacing', ru: 'Расстояние между линиями очистки черновой башни' },
  wipe_tower_fillet_wall: { en: 'Wipe tower', ru: 'Черновая башня' },
  wipe_tower_max_purge_speed: { en: 'Maximum wipe tower print speed', ru: 'Макс. скорость печати черновой башни' },
  wipe_tower_no_sparse_layers: { en: 'No sparse layers (beta)', ru: 'Без разреженных слоёв (beta)' },
  wipe_tower_rotation_angle: { en: 'Wipe tower rotation angle', ru: 'Угол поворота черновой башни' },
  wipe_tower_wall_type: { en: 'Wall type', ru: 'Форма черновой башни' },
  wiping_volumes_extruders: { en: 'Purging volumes - load/unload volumes', ru: 'Объём очистки - Объём загрузки/выгрузки' },
  xy_contour_compensation: { en: 'X-Y contour compensation', ru: 'Расширение контура слоя' },
  xy_hole_compensation: { en: 'X-Y hole compensation', ru: 'Расширение пустот в слое' },
};
export const ORCA_ADVANCED_ENUM_OPTIONS: Record<string, string[]> = {
  slicing_mode: enumValues(`
regular
even_odd
close_holes
`),
  ensure_vertical_shell_thickness: enumValues(`
none
ensure_critical_only
ensure_moderate
ensure_all
`),
  wall_direction: enumValues(`
auto
ccw
cw
`),
  wall_sequence: enumValues(`
inner wall/outer wall
outer wall/inner wall
inner-outer-inner wall
`),
  top_surface_pattern: enumValues(`
monotonic
monotonicline
rectilinear
alignedrectilinear
concentric
hilbertcurve
archimedeanchords
octagramspiral
`),
  bottom_surface_pattern: enumValues(`
monotonic
monotonicline
rectilinear
alignedrectilinear
concentric
hilbertcurve
archimedeanchords
octagramspiral
`),
  counterbore_hole_bridging: enumValues(`
none
partiallybridge
sacrificiallayer
`),
  internal_solid_infill_pattern: enumValues(`
monotonic
monotonicline
rectilinear
alignedrectilinear
concentric
hilbertcurve
archimedeanchords
octagramspiral
`),
  gap_fill_target: enumValues(`
everywhere
topbottom
nowhere
`),
  ironing_pattern: enumValues(`
rectilinear
concentric
`),
  support_ironing_pattern: enumValues(`
rectilinear
concentric
`),
  fuzzy_skin: enumValues(`
none
external
all
allwalls
disabled_fuzzy
`),
  fuzzy_skin_noise_type: enumValues(`
classic
perlin
billow
ridgedmulti
voronoi
`),
  fuzzy_skin_mode: enumValues(`
displacement
extrusion
combined
`),
  skirt_type: enumValues(`
combined
perobject
`),
  draft_shield: enumValues(`
disabled
enabled
`),
  brim_type: enumValues(`
auto_brim
brim_ears
painted
outer_only
inner_only
outer_and_inner
no_brim
`),
  support_base_pattern: enumValues(`
default
rectilinear
rectilinear-grid
honeycomb
lightning
hollow
`),
  support_style: enumValues(`
default
grid
snug
organic
tree_slim
tree_strong
tree_hybrid
`),
  support_interface_pattern: enumValues(`
auto
rectilinear
concentric
rectilinear_interlaced
grid
`),
  dont_filter_internal_bridges: enumValues(`
disabled
limited
nofilter
`),
  enable_extra_bridge_layer: enumValues(`
disabled
external_bridge_only
internal_bridge_only
apply_to_all
`),
  print_sequence: enumValues(`
by layer
by object
`),
  print_order: enumValues(`
default
as_obj_list
`),
  timelapse_type: enumValues(`
0
1
`),
  wall_generator: enumValues(`
classic
arachne
`),
  wipe_tower_wall_type: enumValues(`
rectangle
cone
rib
`),
  seam_slope_type: enumValues(`
none
external
all
`),
};

export const ORCA_ADVANCED_ENUM_LABELS: Record<string, Record<string, { en: string; ru: string }>> = {
  slicing_mode: {
    regular: { en: 'Regular', ru: 'Обычный' },
    even_odd: { en: 'Even-odd', ru: 'Чёт-нечёт' },
    close_holes: { en: 'Close holes', ru: 'Закрывать отверстия' },
  },
  ensure_vertical_shell_thickness: {
    none: { en: 'None', ru: 'Нет' },
    ensure_critical_only: { en: 'Critical only', ru: 'Только критичные' },
    ensure_moderate: { en: 'Moderate', ru: 'Умеренно' },
    ensure_all: { en: 'All', ru: 'Везде' },
  },
  wall_direction: {
    auto: { en: 'Auto', ru: 'Авто' },
    ccw: { en: 'Counter clockwise', ru: 'Против часовой стрелки' },
    cw: { en: 'Clockwise', ru: 'По часовой стрелке' },
  },
  wall_sequence: {
    'inner wall/outer wall': { en: 'Inner/Outer', ru: 'Внутренний / внешний' },
    'outer wall/inner wall': { en: 'Outer/Inner', ru: 'Внешний / внутренний' },
    'inner-outer-inner wall': { en: 'Inner/Outer/Inner', ru: 'Внутренний / внешний / внутренний' },
  },
  top_surface_pattern: {
    monotonic: { en: 'Monotonic', ru: 'Монотонный' },
    monotonicline: { en: 'Monotonic line', ru: 'Монотонные линии' },
    rectilinear: { en: 'Rectilinear', ru: 'Прямолинейный' },
    alignedrectilinear: { en: 'Aligned Rectilinear', ru: 'Выровненный прямолинейный' },
    concentric: { en: 'Concentric', ru: 'Концентрический' },
    hilbertcurve: { en: 'Hilbert Curve', ru: 'Кривая Гильберта' },
    archimedeanchords: { en: 'Archimedean Chords', ru: 'Архимедовы хорды' },
    octagramspiral: { en: 'Octagram Spiral', ru: 'Восьмиконечная спираль' },
  },
  bottom_surface_pattern: {
    monotonic: { en: 'Monotonic', ru: 'Монотонный' },
    monotonicline: { en: 'Monotonic line', ru: 'Монотонные линии' },
    rectilinear: { en: 'Rectilinear', ru: 'Прямолинейный' },
    alignedrectilinear: { en: 'Aligned Rectilinear', ru: 'Выровненный прямолинейный' },
    concentric: { en: 'Concentric', ru: 'Концентрический' },
    hilbertcurve: { en: 'Hilbert Curve', ru: 'Кривая Гильберта' },
    archimedeanchords: { en: 'Archimedean Chords', ru: 'Архимедовы хорды' },
    octagramspiral: { en: 'Octagram Spiral', ru: 'Восьмиконечная спираль' },
  },
  internal_solid_infill_pattern: {
    monotonic: { en: 'Monotonic', ru: 'Монотонный' },
    monotonicline: { en: 'Monotonic line', ru: 'Монотонные линии' },
    rectilinear: { en: 'Rectilinear', ru: 'Прямолинейный' },
    alignedrectilinear: { en: 'Aligned Rectilinear', ru: 'Выровненный прямолинейный' },
    concentric: { en: 'Concentric', ru: 'Концентрический' },
    hilbertcurve: { en: 'Hilbert Curve', ru: 'Кривая Гильберта' },
    archimedeanchords: { en: 'Archimedean Chords', ru: 'Архимедовы хорды' },
    octagramspiral: { en: 'Octagram Spiral', ru: 'Восьмиконечная спираль' },
  },
  counterbore_hole_bridging: {
    none: { en: 'None', ru: 'Нет' },
    partiallybridge: { en: 'Partially bridged', ru: 'Частичный мост' },
    sacrificiallayer: { en: 'Sacrificial layer', ru: 'Жертвенный слой' },
  },
  gap_fill_target: {
    everywhere: { en: 'Everywhere', ru: 'Везде' },
    topbottom: { en: 'Top and bottom surfaces', ru: 'Только верх и низ' },
    nowhere: { en: 'Nowhere', ru: 'Нигде' },
  },
  ironing_pattern: {
    rectilinear: { en: 'Rectilinear', ru: 'Прямолинейный' },
    concentric: { en: 'Concentric', ru: 'Концентрический' },
  },
  support_ironing_pattern: {
    rectilinear: { en: 'Rectilinear', ru: 'Прямолинейный' },
    concentric: { en: 'Concentric', ru: 'Концентрический' },
  },
  fuzzy_skin: {
    none: { en: 'None', ru: 'Нет' },
    external: { en: 'Contour', ru: 'Только контур' },
    all: { en: 'Contour and hole', ru: 'Контур и отверстия' },
    allwalls: { en: 'All walls', ru: 'Все стенки' },
    disabled_fuzzy: { en: 'Disabled', ru: 'Выключено' },
  },
  fuzzy_skin_noise_type: {
    classic: { en: 'Classic', ru: 'Классический' },
    perlin: { en: 'Perlin', ru: 'Перлин' },
    billow: { en: 'Billow', ru: 'Billow' },
    ridgedmulti: { en: 'Ridged Multifractal', ru: 'Ridged Multifractal' },
    voronoi: { en: 'Voronoi', ru: 'Вороной' },
  },
  fuzzy_skin_mode: {
    displacement: { en: 'Displacement', ru: 'Смещение' },
    extrusion: { en: 'Extrusion', ru: 'Экструзия' },
    combined: { en: 'Combined', ru: 'Комбинированный' },
  },
  skirt_type: {
    combined: { en: 'Combined', ru: 'Общая' },
    perobject: { en: 'Per object', ru: 'Отдельно для каждой модели' },
  },
  draft_shield: {
    disabled: { en: 'Disabled', ru: 'Выключено' },
    enabled: { en: 'Enabled', ru: 'Включено' },
  },
  brim_type: {
    auto_brim: { en: 'Auto', ru: 'Авто' },
    brim_ears: { en: 'Mouse ear', ru: 'Ушки' },
    painted: { en: 'Painted', ru: 'Нарисованная' },
    outer_only: { en: 'Outer brim only', ru: 'Только внешняя кайма' },
    inner_only: { en: 'Inner brim only', ru: 'Только внутренняя кайма' },
    outer_and_inner: { en: 'Outer and inner brim', ru: 'Внешняя и внутренняя кайма' },
    no_brim: { en: 'No-brim', ru: 'Без каймы' },
  },
  support_base_pattern: {
    default: { en: 'Default', ru: 'По умолчанию' },
    rectilinear: { en: 'Rectilinear', ru: 'Прямолинейный' },
    'rectilinear-grid': { en: 'Rectilinear grid', ru: 'Прямолинейная сетка' },
    honeycomb: { en: 'Honeycomb', ru: 'Соты' },
    lightning: { en: 'Lightning', ru: 'Молния' },
    hollow: { en: 'Hollow', ru: 'Полый' },
  },
  support_style: {
    default: { en: 'Default (Grid/Organic)', ru: 'По умолчанию (сетка / organic)' },
    grid: { en: 'Grid', ru: 'Сетка' },
    snug: { en: 'Snug', ru: 'Плотная' },
    organic: { en: 'Organic', ru: 'Organic' },
    tree_slim: { en: 'Tree Slim', ru: 'Дерево Slim' },
    tree_strong: { en: 'Tree Strong', ru: 'Дерево Strong' },
    tree_hybrid: { en: 'Tree Hybrid', ru: 'Дерево Hybrid' },
  },
  support_interface_pattern: {
    auto: { en: 'Auto', ru: 'Авто' },
    rectilinear: { en: 'Rectilinear', ru: 'Прямолинейный' },
    concentric: { en: 'Concentric', ru: 'Концентрический' },
    rectilinear_interlaced: { en: 'Rectilinear Interlaced', ru: 'Чересстрочный прямолинейный' },
    grid: { en: 'Grid', ru: 'Сетка' },
  },
  dont_filter_internal_bridges: {
    disabled: { en: 'Filter', ru: 'Фильтровать' },
    limited: { en: 'Limited filtering', ru: 'Ограниченная фильтрация' },
    nofilter: { en: 'No filtering', ru: 'Без фильтрации' },
  },
  enable_extra_bridge_layer: {
    disabled: { en: 'Disabled', ru: 'Выключено' },
    external_bridge_only: { en: 'External bridge only', ru: 'Только внешние мосты' },
    internal_bridge_only: { en: 'Internal bridge only', ru: 'Только внутренние мосты' },
    apply_to_all: { en: 'Apply to all', ru: 'Для всех мостов' },
  },
  print_sequence: {
    'by layer': { en: 'By layer', ru: 'По слоям' },
    'by object': { en: 'By object', ru: 'По моделям' },
  },
  print_order: {
    default: { en: 'Default', ru: 'По умолчанию' },
    as_obj_list: { en: 'As object list', ru: 'Как в списке моделей' },
  },
  timelapse_type: {
    '0': { en: 'Traditional', ru: 'Обычный' },
    '1': { en: 'Smooth', ru: 'Плавный' },
  },
  wall_generator: {
    classic: { en: 'Classic', ru: 'Классический' },
    arachne: { en: 'Arachne', ru: 'Arachne' },
  },
  wipe_tower_wall_type: {
    rectangle: { en: 'Rectangle', ru: 'Прямоугольник' },
    cone: { en: 'Cone', ru: 'Конус' },
    rib: { en: 'Rib', ru: 'Рёбра' },
  },
  seam_slope_type: {
    none: { en: 'None', ru: 'Нет' },
    external: { en: 'External', ru: 'Только внешние' },
    all: { en: 'All', ru: 'Все' },
  },
};
