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

export interface OrcaStructuredFieldDef {
  key: string;
  kind: OrcaStructuredFieldKind;
}

const splitLines = (value: string): string[] =>
  value
    .trim()
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.length > 0);

const buildFieldDefs = (kind: OrcaStructuredFieldKind, keysBlock: string): OrcaStructuredFieldDef[] =>
  splitLines(keysBlock).map((key) => ({ key, kind }));

const enumValues = (valuesBlock: string): string[] => splitLines(valuesBlock);

export const ORCA_ADVANCED_FIELD_KIND_ORDER: OrcaStructuredFieldKind[] = [
  'enum',
  'boolean',
  'integer',
  'float',
  'percent',
  'floatOrPercent',
  'string',
  'stringList',
  'integerList',
  'floatList',
];

export const ORCA_ADVANCED_FIELD_DEFS: OrcaStructuredFieldDef[] = [
  ...buildFieldDefs(
    'boolean',
    `
alternate_extra_wall
spiral_mode_smooth
extra_perimeters_on_overhangs
reduce_crossing_wall
detect_thin_wall
detect_overhang_wall
overhang_reverse
overhang_reverse_internal_only
staggered_inner_seams
is_infill_first
symmetric_infill_y_axis
align_infill_direction_to_model
reduce_infill_retraction
ironing_angle_fixed
support_ironing
fuzzy_skin_first_layer
extrusion_rate_smoothing_external_perimeter_only
single_loop_draft_shield
brim_use_efc_outline
independent_support_layer_height
support_interface_loop_pattern
support_on_build_plate_only
support_critical_regions_only
bridge_no_support
thick_bridges
thick_internal_bridges
support_remove_small_overhang
support_interface_not_for_body
ooze_prevention
interface_shells
enable_prime_tower
prime_tower_enable_framework
prime_tower_skip_points
prime_tower_flat_ironing
enable_tower_interface_features
enable_tower_interface_cooldown_during_tower
wipe_tower_no_sparse_layers
flush_into_infill
flush_into_objects
flush_into_support
detect_narrow_internal_solid_infill
gcode_add_line_number
precise_z_height
infill_combination
adaptive_layer_height
enable_overhang_speed
slowdown_for_curled_perimeters
only_one_wall_top
only_one_wall_first_layer
set_other_flow_ratios
role_based_wipe_speed
accel_to_decel_enable
wipe_on_loops
wipe_before_external_loop
precise_outer_wall
tree_support_auto_brim
gcode_comments
gcode_label_objects
exclude_object
make_overhang_printable
wipe_tower_fillet_wall
single_extruder_multi_material_priming
hole_to_polyhole
hole_to_polyhole_twisted
small_area_infill_flow_compensation
enable_wrapping_detection
seam_slope_conditional
seam_slope_entire_loop
seam_slope_inner_walls
interlocking_beam
calib_flowrate_topinfill_special_order
`,
  ),
  ...buildFieldDefs(
    'enum',
    `
slicing_mode
ensure_vertical_shell_thickness
wall_direction
wall_sequence
top_surface_pattern
bottom_surface_pattern
counterbore_hole_bridging
internal_solid_infill_pattern
gap_fill_target
ironing_pattern
support_ironing_pattern
fuzzy_skin
fuzzy_skin_noise_type
fuzzy_skin_mode
skirt_type
draft_shield
brim_type
support_base_pattern
support_style
support_interface_pattern
dont_filter_internal_bridges
enable_extra_bridge_layer
print_sequence
print_order
timelapse_type
wall_generator
wipe_tower_wall_type
seam_slope_type
`,
  ),
  ...buildFieldDefs(
    'integer',
    `
fill_multiline
fuzzy_skin_octaves
skirt_height
enforce_support_layers
support_interface_top_layers
support_interface_bottom_layers
wall_filament
sparse_infill_filament
solid_infill_filament
support_filament
support_interface_filament
standby_temperature_delta
preheat_steps
elefant_foot_compensation_layers
tree_support_wall_count
wall_distribution_count
slow_down_layers
wipe_tower_filament
scarf_angle_threshold
seam_slope_steps
interlocking_beam_layer_count
interlocking_depth
interlocking_boundary_avoidance
`,
  ),
  ...buildFieldDefs(
    'float',
    `
slice_closing_radius
spiral_starting_flow_ratio
spiral_finishing_flow_ratio
top_shell_thickness
bottom_shell_thickness
lateral_lattice_angle_1
lateral_lattice_angle_2
infill_overhang_angle
infill_direction
solid_infill_direction
infill_shift_step
infill_lock_depth
skin_infill_depth
minimum_sparse_infill_area
ironing_speed
ironing_spacing
ironing_angle
ironing_inset
support_ironing_spacing
fuzzy_skin_thickness
fuzzy_skin_point_distance
fuzzy_skin_scale
fuzzy_skin_persistence
max_volumetric_extrusion_rate_slope
max_volumetric_extrusion_rate_slope_segment_length
top_surface_speed
support_speed
support_object_xy_distance
support_object_first_layer_gap
support_interface_speed
gap_infill_speed
travel_speed_z
outer_wall_acceleration
initial_layer_acceleration
top_surface_acceleration
skirt_speed
min_skirt_length
skirt_distance
skirt_start_angle
brim_object_gap
brim_ears_max_angle
brim_ears_detection_length
raft_first_layer_expansion
raft_contact_distance
raft_expansion
support_base_pattern_spacing
support_expansion
support_angle
support_interface_spacing
support_top_z_distance
max_bridge_length
support_bottom_z_distance
preheat_time
bridge_flow
internal_bridge_flow
elefant_foot_compensation
xy_contour_compensation
xy_hole_compensation
resolution
prime_tower_width
prime_tower_brim_width
prime_volume
tree_support_branch_angle
tree_support_angle_slow
tree_support_branch_distance
tree_support_tip_diameter
tree_support_branch_diameter
tree_support_branch_diameter_angle
support_bottom_interface_spacing
wall_transition_angle
min_length_factor
small_perimeter_threshold
bridge_angle
internal_bridge_angle
filter_out_gap_fill
inner_wall_acceleration
default_jerk
outer_wall_jerk
inner_wall_jerk
infill_jerk
top_surface_jerk
initial_layer_jerk
travel_jerk
default_junction_deviation
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
tree_support_brim_width
make_overhang_printable_angle
make_overhang_printable_hole_size
wipe_tower_cone_angle
wipe_tower_max_purge_speed
wipe_tower_extra_rib_length
wipe_tower_rib_width
wipe_tower_bridging
wipe_tower_rotation_angle
tree_support_branch_distance_organic
tree_support_branch_diameter_organic
tree_support_branch_angle_organic
mmu_segmented_region_max_width
mmu_segmented_region_interlocking_depth
scarf_joint_flow_ratio
seam_slope_min_length
interlocking_orientation
interlocking_beam_width
`,
  ),
  ...buildFieldDefs(
    'percent',
    `
top_surface_density
bottom_surface_density
skeleton_infill_density
skin_infill_density
ironing_flow
support_ironing_flow
raft_first_layer_density
infill_wall_overlap
top_bottom_infill_wall_overlap
prime_tower_infill_gap
tree_support_top_rate
wall_transition_length
wall_transition_filter_deviation
min_feature_size
min_bead_width
accel_to_decel_factor
bridge_density
internal_bridge_density
initial_layer_min_bead_width
wipe_tower_extra_spacing
wipe_tower_extra_flow
scarf_overhang_threshold
`,
  ),
  ...buildFieldDefs(
    'floatOrPercent',
    `
spiral_mode_max_xy_smoothing
overhang_reverse_threshold
max_travel_detour_distance
internal_bridge_speed
support_threshold_overlap
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
infill_combination_max_layer_height
overhang_1_4_speed
overhang_2_4_speed
overhang_3_4_speed
overhang_4_4_speed
small_perimeter_speed
min_width_top_surface
seam_gap
wipe_speed
bridge_acceleration
sparse_infill_acceleration
internal_solid_infill_acceleration
initial_layer_travel_speed
infill_anchor
infill_anchor_max
hole_to_polyhole_threshold
scarf_joint_speed
seam_slope_start_height
`,
  ),
  ...buildFieldDefs(
    'string',
    `
sparse_infill_rotate_template
solid_infill_rotate_template
extra_solid_infills
filename_format
`,
  ),
  ...buildFieldDefs(
    'stringList',
    `
print_extruder_variant
post_process
small_area_infill_flow_compensation_model
`,
  ),
  ...buildFieldDefs(
    'integerList',
    `
print_extruder_id
`,
  ),
  ...buildFieldDefs(
    'floatList',
    `
wiping_volumes_extruders
`,
  ),
];

export const ORCA_ADVANCED_FIELD_KEYS = new Set(ORCA_ADVANCED_FIELD_DEFS.map((field) => field.key));

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
