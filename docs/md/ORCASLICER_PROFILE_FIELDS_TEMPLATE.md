# OrcaSlicer Profile Fields Template (Reference Guide)

> **Source:** OrcaSlicer code (`src/libslic3r/Preset.cpp`, lines 883-1022)  
> **Date:** 2024  
> **Note:** Not all fields are required. Fields may be missing in JSON profiles.

## Common Fields (Общие поля)

These fields are present in the root of any profile JSON file:

```json
{
  "version": "2.3.0.0",           // Profile format version
  "type": "filament|machine|process",  // Profile type
  "name": "Profile Name",         // Profile name
  "from": "system|user",          // Source (system/user)
  "inherits": "Base Profile",     // Base profile for inheritance
  "setting_id": "unique_id",      // Unique setting ID
  "instantiation": "true|false",  // Instantiation flag
  "renamed_from": "Old Name",     // Old name (if renamed)
  
  // FilamentHub metadata (added by us)
  "fhub_id": 123,                 // Preset ID in FilamentHub
  "fhub_source": "filamenthub",   // Source (FilamentHub)
  "fhub_draft_id": "uuid",        // Draft ID (for inactive presets)
  
  // Rest of the fields are specific to each profile type
}
```

---

## 1. FILAMENT PRESET FIELDS (Поля пресетов филаментов)

> **⚠️ ВАЖНО:** Эти поля используются ТОЛЬКО для профилей типа `type: "filament"`  
> **Source:** `s_Preset_filament_options` в `Preset.cpp` (строки 951-985)

**Complete list of fields from `s_Preset_filament_options`:**

### Базовые свойства филамента
- `default_filament_colour` - Цвет филамента по умолчанию (hex, например "#FF0000")
- `required_nozzle_HRC` - Требуемая твердость сопла HRC
- `filament_diameter` - Диаметр филамента (например "1.75")
- `pellet_flow_coefficient` - Коэффициент потока для пеллет
- `volumetric_speed_coefficients` - Коэффициенты объемной скорости
- `filament_type` - Тип материала (PLA, ABS, PETG, TPU и т.д.)
- `filament_soluble` - Растворимый (0|1)
- `filament_is_support` - Используется как поддержка (0|1)
- `filament_printable` - Категория печатаемости (0-5)
- `filament_max_volumetric_speed` - Максимальная объемная скорость экструзии
- `filament_adaptive_volumetric_speed` - Адаптивная объемная скорость (0|1)
- `filament_flow_ratio` - Коэффициент потока (множитель, например "0.95")
- `filament_density` - Плотность в г/см³ (например "1.24")
- `filament_adhesiveness_category` - Категория адгезии (0-?)
- `filament_cost` - Стоимость (в копейках за грамм)
- `filament_minimal_purge_on_wipe_tower` - Минимальная очистка на башне очистки (%)
- `filament_vendor` - Производитель филамента

### Температуры экструдера (nozzle)
- `nozzle_temperature` - Температура экструдера
- `nozzle_temperature_initial_layer` - Температура для первого слоя
- `nozzle_temperature_range_low` - Минимальная температура
- `nozzle_temperature_range_high` - Максимальная температура
- `idle_temperature` - Температура простоя (0-255)

### Температуры стола (bed/plate)
- `hot_plate_temp` - Температура горячего стола
- `hot_plate_temp_initial_layer` - Температура горячего стола для первого слоя
- `cool_plate_temp` - Температура холодного стола
- `cool_plate_temp_initial_layer` - Температура холодного стола для первого слоя
- `eng_plate_temp` - Температура инженерного стола
- `eng_plate_temp_initial_layer` - Температура инженерного стола для первого слоя
- `textured_plate_temp` - Температура текстурированного стола
- `textured_plate_temp_initial_layer` - Температура текстурированного стола для первого слоя
- `textured_cool_plate_temp` - Температура холодного текстурированного стола
- `textured_cool_plate_temp_initial_layer` - Температура холодного текстурированного стола для первого слоя
- `supertack_plate_temp` - Температура супер-липкого стола
- `supertack_plate_temp_initial_layer` - Температура супер-липкого стола для первого слоя
- `temperature_vitrification` - Температура витрификации

### Камера
- `chamber_temperature` - Температура камеры (0 = выключено)
- `activate_chamber_temp_control` - Активировать контроль температуры камеры (0|1)

### Вентиляторы (fans)
- `fan_min_speed` - Минимальная скорость вентилятора (0-100)
- `fan_max_speed` - Максимальная скорость вентилятора (0-100)
- `enable_overhang_bridge_fan` - Включить вентилятор для свесов и мостов (0|1)
- `overhang_fan_speed` - Скорость вентилятора для свесов (0-100)
- `overhang_fan_threshold` - Порог свеса для активации вентилятора (например "25%")
- `close_fan_the_first_x_layers` - Закрыть вентилятор на первых X слоях
- `full_fan_speed_layer` - Слой для полной скорости вентилятора
- `fan_cooling_layer_time` - Время охлаждения слоя вентилятором (секунды)
- `slow_down_for_layer_cooling` - Замедление для охлаждения слоя (0|1)
- `slow_down_layer_time` - Время слоя для замедления (секунды)
- `slow_down_min_speed` - Минимальная скорость при замедлении (мм/с)
- `dont_slow_down_outer_wall` - Не замедлять внешнюю стенку (0|1)
- `reduce_fan_stop_start_freq` - Уменьшить частоту включения/выключения вентилятора (0|1)
- `additional_cooling_fan_speed` - Дополнительная скорость охлаждения (для TPU и т.д.)
- `support_material_interface_fan_speed` - Скорость вентилятора для интерфейса поддержки (-1 = по умолчанию)
- `internal_bridge_fan_speed` - Скорость вентилятора для внутренних мостов (-1 = по умолчанию)
- `ironing_fan_speed` - Скорость вентилятора для ironing (-1 = по умолчанию)

### Вытяжка (exhaust)
- `complete_print_exhaust_fan_speed` - Скорость вытяжки после печати (0-100)
- `during_print_exhaust_fan_speed` - Скорость вытяжки во время печати (0-100)
- `activate_air_filtration` - Активировать воздушный фильтр (0|1)

### Retraction (ретракция)
- `filament_retraction_length` - Длина ретракции (мм, или "nil")
- `filament_retraction_speed` - Скорость ретракции (мм/с, или "nil")
- `filament_deretraction_speed` - Скорость де-ретракции (мм/с, или "nil")
- `filament_retraction_minimum_travel` - Минимальное расстояние перемещения для ретракции (мм, или "nil")
- `filament_retract_before_wipe` - Ретракция перед очисткой ("nil" или процент, например "70%")
- `filament_retract_when_changing_layer` - Ретракция при смене слоя (0|1|nil)
- `filament_retract_restart_extra` - Дополнительная де-ретракция (мм, или "nil")
- `filament_retraction_distances_when_cut` - Расстояния ретракции при обрезке
- `filament_long_retractions_when_cut` - Длинные ретракции при обрезке
- `long_retractions_when_ec` - Длинные ретракции при смене экструдера (0|1)
- `retraction_distances_when_ec` - Расстояния ретракции при смене экструдера (мм)

### Lift (подъем Z)
- `filament_z_hop` - Подъем Z при ретракции (мм, или "nil")
- `filament_z_hop_types` - Типы подъема Z ("nil" или "Normal Lift" и т.д.)
- `filament_retract_lift_above` - Подъем Z выше определенной высоты
- `filament_retract_lift_below` - Подъем Z ниже определенной высоты
- `filament_retract_lift_enforce` - Принудительный подъем Z ("nil" или "All Surfaces" и т.д.)

### Wipe (очистка)
- `filament_wipe` - Включить очистку (0|1)
- `filament_wipe_distance` - Расстояние очистки (мм, или "nil")
- `filament_flush_temp` - Температура промывки при смене филамента
- `filament_flush_volumetric_speed` - Объемная скорость промывки

### Pressure Advance (предварительное давление)
- `enable_pressure_advance` - Включить pressure advance (0|1)
- `pressure_advance` - Значение pressure advance (например "0.038")
- `adaptive_pressure_advance` - Адаптивный pressure advance (0|1)
- `adaptive_pressure_advance_bridges` - Адаптивный PA для мостов (0|1)
- `adaptive_pressure_advance_overhangs` - Адаптивный PA для свесов (0|1)
- `adaptive_pressure_advance_model` - Модель адаптивного PA (строка с данными)

### Усадка
- `filament_shrink` - Усадка филамента (например "99.8%")
- `filament_shrinkage_compensation_z` - Компенсация усадки по Z (например "100%")

### Мультитул (multitool) параметры
- `filament_multitool_ramming` - Включить ramming для мультитула (0|1)
- `filament_multitool_ramming_flow` - Поток ramming для мультитула (%)
- `filament_multitool_ramming_volume` - Объем ramming для мультитула (мм³)
- `filament_ramming_parameters` - Параметры ramming (строка с данными)
- `filament_toolchange_delay` - Задержка при смене инструмента (секунды)

### Загрузка/выгрузка филамента
- `filament_loading_speed` - Скорость загрузки (мм/с)
- `filament_loading_speed_start` - Начальная скорость загрузки (мм/с)
- `filament_unloading_speed` - Скорость выгрузки (мм/с)
- `filament_unloading_speed_start` - Начальная скорость выгрузки (мм/с)
- `filament_change_length` - Длина смены филамента (мм)

### Охлаждение при загрузке (для мультитула)
- `filament_cooling_initial_speed` - Начальная скорость охлаждения
- `filament_cooling_final_speed` - Конечная скорость охлаждения
- `filament_cooling_moves` - Количество движений охлаждения

### Stamping (штамповка, для мультитула)
- `filament_stamping_distance` - Расстояние штамповки (мм)
- `filament_stamping_loading_speed` - Скорость загрузки при штамповке (мм/с)

### Экструдер
- `filament_extruder_variant` - Вариант экструдера (например "Direct Drive Standard")

### G-code
- `filament_start_gcode` - Начальный G-code для филамента (многострочная строка)
- `filament_end_gcode` - Конечный G-code для филамента (многострочная строка)

### Совместимость
- `compatible_printers` - Список совместимых принтеров (массив строк)
- `compatible_printers_condition` - Условие совместимости принтеров (строка)
- `compatible_prints` - Список совместимых профилей печати (массив строк)
- `compatible_prints_condition` - Условие совместимости профилей печати (строка)

### Заметки
- `filament_notes` - Заметки пользователя (строка, может быть пустой)

---

## 2. Printer Profile Fields (Профили принтеров)

**Полный список полей из `s_Preset_printer_options`:**

### Базовые настройки принтера
- `printer_technology` - Технология принтера (FFF|SLA)
- `printer_model` - Модель принтера (ссылка на базовую модель)
- `printer_variant` - Вариант принтера (например "0.4")
- `printer_extruder_id` - ID экструдера принтера
- `printer_extruder_variant` - Вариант экструдера принтера
- `extruder_variant_list` - Список вариантов экструдеров
- `default_nozzle_volume_type` - Тип объема сопла по умолчанию
- `default_print_profile` - Профиль печати по умолчанию
- `inherits` - Базовый профиль для наследования

### Область печати
- `printable_area` - Область печати (полигон точек)
- `extruder_printable_area` - Область печати экструдера (группы точек)
- `bed_exclude_area` - Исключаемая область стола (полигон точек)
- `printable_height` - Высота печати (мм)
- `extruder_printable_height` - Высота печати экструдера (мм)
- `extruder_clearance_radius` - Радиус очистки экструдера
- `extruder_clearance_height_to_lid` - Высота очистки до крышки
- `extruder_clearance_height_to_rod` - Высота очистки до стержня
- `nozzle_height` - Высота сопла
- `master_extruder_id` - ID главного экструдера

### Стол (bed)
- `bed_custom_texture` - Пользовательская текстура стола
- `bed_custom_model` - Пользовательская модель стола
- `support_multi_bed_types` - Поддержка нескольких типов столов (0|1)
- `default_bed_type` - Тип стола по умолчанию
- `bed_temperature_formula` - Формула температуры стола
- `bed_mesh_min` - Минимальная точка сетки стола
- `bed_mesh_max` - Максимальная точка сетки стола
- `bed_mesh_probe_distance` - Расстояние зондирования сетки стола
- `adaptive_bed_mesh_margin` - Отступ адаптивной сетки стола

### Сопло (nozzle)
- `nozzle_type` - Тип сопла
- `nozzle_hrc` - Твердость сопла HRC
- `nozzle_volume` - Объем сопла
- `nozzle_flush_dataset` - Набор данных промывки сопла

### G-code
- `machine_start_gcode` - Начальный G-code принтера
- `machine_end_gcode` - Конечный G-code принтера
- `before_layer_change_gcode` - G-code перед сменой слоя
- `printing_by_object_gcode` - G-code при печати по объектам
- `layer_change_gcode` - G-code при смене слоя
- `time_lapse_gcode` - G-code для таймлапса
- `wrapping_detection_gcode` - G-code для обнаружения обертывания
- `change_filament_gcode` - G-code при смене филамента
- `change_extrusion_role_gcode` - G-code при смене роли экструзии
- `machine_pause_gcode` - G-code при паузе принтера
- `template_custom_gcode` - Пользовательский шаблон G-code

### Вентиляторы
- `fan_kickstart` - Запуск вентилятора
- `fan_speedup_time` - Время ускорения вентилятора
- `fan_speedup_overhangs` - Ускорение вентилятора для свесов
- `auxiliary_fan` - Вспомогательный вентилятор

### Экструдер
- `single_extruder_multi_material` - Один экструдер, несколько материалов (0|1)
- `manual_filament_change` - Ручная смена филамента (0|1)
- `extruder_type` - Тип экструдера
- `use_firmware_retraction` - Использовать ретракцию прошивки (0|1)
- `use_relative_e_distances` - Использовать относительные расстояния E (0|1)
- `physical_extruder_map` - Карта физических экструдеров

### Ретракция и перемещения
- `z_hop_types` - Типы подъема Z
- `travel_slope` - Наклон перемещения
- `retract_lift_enforce` - Принудительный подъем при ретракции
- `z_offset` - Смещение Z
- `enable_long_retraction_when_cut` - Включить длинную ретракцию при обрезке (0|1)
- `long_retractions_when_cut` - Длинные ретракции при обрезке
- `retraction_distances_when_cut` - Расстояния ретракции при обрезке

### Охлаждение и загрузка
- `cooling_tube_retraction` - Ретракция охлаждающей трубки
- `cooling_tube_length` - Длина охлаждающей трубки
- `high_current_on_filament_swap` - Высокий ток при смене филамента (0|1)
- `parking_pos_retraction` - Ретракция в позиции парковки
- `extra_loading_move` - Дополнительное движение загрузки
- `purge_in_prime_tower` - Очистка в башне прайминга (0|1)
- `enable_filament_ramming` - Включить ramming филамента (0|1)
- `grab_length` - Длина захвата

### Специальные функции
- `silent_mode` - Тихий режим (0|1)
- `scan_first_layer` - Сканирование первого слоя (0|1)
- `wrapping_detection_layers` - Слои обнаружения обертывания
- `wrapping_exclude_area` - Исключаемая область обертывания
- `upward_compatible_machine` - Совместимая машина вверх
- `printer_structure` - Структура принтера
- `best_object_pos` - Лучшая позиция объекта
- `head_wrap_detect_zone` - Зона обнаружения обертывания головы
- `preferred_orientation` - Предпочтительная ориентация
- `emit_machine_limits_to_gcode` - Выдавать ограничения машины в G-code (0|1)
- `pellet_modded_printer` - Принтер с модификацией для пеллет (0|1)
- `disable_m73` - Отключить M73 (0|1)

### Температура камеры
- `support_chamber_temp_control` - Поддержка контроля температуры камеры (0|1)
- `support_air_filtration` - Поддержка воздушной фильтрации (0|1)

### Время и стоимость
- `machine_load_filament_time` - Время загрузки филамента
- `machine_unload_filament_time` - Время выгрузки филамента
- `machine_tool_change_time` - Время смены инструмента
- `time_cost` - Стоимость времени

### Сетевые настройки (Print Host)
- `host_type` - Тип хоста
- `print_host` - Хост печати
- `printhost_apikey` - API ключ хоста печати
- `bbl_use_printhost` - Использовать хост печати BBL (0|1)
- `print_host_webui` - WebUI хоста печати
- `printhost_cafile` - CA файл хоста печати
- `printhost_port` - Порт хоста печати
- `printhost_authorization_type` - Тип авторизации хоста печати
- `printhost_user` - Пользователь хоста печати
- `printhost_password` - Пароль хоста печати
- `printhost_ssl_ignore_revoke` - Игнорировать отзыв SSL (0|1)

### Дополнительные настройки
- `gcode_flavor` - Вкус G-code (Marlin, RepRap, etc.)
- `thumbnails` - Миниатюры
- `thumbnails_format` - Формат миниатюр
- `printer_notes` - Заметки о принтере

---

## 3. Print Profile Fields (Профили печати / Process)

**Полный список полей из `s_Preset_print_options`:**

### Базовые настройки слоя
- `layer_height` - Высота слоя (мм)
- `initial_layer_print_height` - Высота первого слоя (мм)
- `wall_loops` - Количество петель стенок
- `alternate_extra_wall` - Чередующаяся дополнительная стенка (0|1)
- `slice_closing_radius` - Радиус закрытия среза
- `spiral_mode` - Спиральный режим (0|1)
- `spiral_mode_smooth` - Плавный спиральный режим (0|1)
- `spiral_mode_max_xy_smoothing` - Максимальное сглаживание XY в спиральном режиме
- `spiral_starting_flow_ratio` - Коэффициент потока начала спирали
- `spiral_finishing_flow_ratio` - Коэффициент потока окончания спирали
- `slicing_mode` - Режим нарезки

### Оболочка (Shell)
- `top_shell_layers` - Количество слоев верхней оболочки
- `top_shell_thickness` - Толщина верхней оболочки
- `top_surface_density` - Плотность верхней поверхности
- `bottom_surface_density` - Плотность нижней поверхности
- `bottom_shell_layers` - Количество слоев нижней оболочки
- `bottom_shell_thickness` - Толщина нижней оболочки
- `extra_perimeters_on_overhangs` - Дополнительные периметры на свесах (0|1)
- `ensure_vertical_shell_thickness` - Обеспечить вертикальную толщину оболочки (0|1)
- `reduce_crossing_wall` - Уменьшить пересекающуюся стенку (0|1)
- `detect_thin_wall` - Обнаруживать тонкую стенку (0|1)
- `detect_overhang_wall` - Обнаруживать свес стенки (0|1)
- `overhang_reverse` - Обратный свес (0|1)
- `overhang_reverse_threshold` - Порог обратного свеса
- `overhang_reverse_internal_only` - Обратный свес только внутренний (0|1)
- `wall_direction` - Направление стенки
- `wall_sequence` - Последовательность стенок
- `is_infill_first` - Заполнение сначала (0|1)

### Швы (Seams)
- `seam_position` - Позиция шва
- `staggered_inner_seams` - Смещенные внутренние швы (0|1)
- `seam_gap` - Зазор шва
- `seam_slope_type` - Тип наклона шва
- `seam_slope_conditional` - Условный наклон шва (0|1)
- `scarf_angle_threshold` - Порог угла шарфа
- `scarf_joint_speed` - Скорость соединения шарфа
- `scarf_joint_flow_ratio` - Коэффициент потока соединения шарфа
- `seam_slope_start_height` - Начальная высота наклона шва
- `seam_slope_entire_loop` - Наклон шва по всей петле (0|1)
- `seam_slope_min_length` - Минимальная длина наклона шва
- `seam_slope_steps` - Шаги наклона шва
- `seam_slope_inner_walls` - Наклон шва внутренних стенок (0|1)
- `scarf_overhang_threshold` - Порог свеса шарфа

### Заполнение (Infill)
- `sparse_infill_density` - Плотность разреженного заполнения (%)
- `fill_multiline` - Многострочное заполнение (0|1)
- `sparse_infill_pattern` - Паттерн разреженного заполнения
- `lateral_lattice_angle_1` - Угол боковой решетки 1
- `lateral_lattice_angle_2` - Угол боковой решетки 2
- `infill_overhang_angle` - Угол свеса заполнения
- `top_surface_pattern` - Паттерн верхней поверхности
- `bottom_surface_pattern` - Паттерн нижней поверхности
- `infill_direction` - Направление заполнения
- `solid_infill_direction` - Направление сплошного заполнения
- `counterbore_hole_bridging` - Мостование зенкованных отверстий (0|1)
- `infill_shift_step` - Шаг сдвига заполнения
- `sparse_infill_rotate_template` - Поворот шаблона разреженного заполнения (0|1)
- `solid_infill_rotate_template` - Поворот шаблона сплошного заполнения (0|1)
- `symmetric_infill_y_axis` - Симметричное заполнение по оси Y (0|1)
- `skeleton_infill_density` - Плотность скелетного заполнения
- `infill_lock_depth` - Глубина блокировки заполнения
- `skin_infill_depth` - Глубина заполнения кожи
- `skin_infill_density` - Плотность заполнения кожи
- `align_infill_direction_to_model` - Выровнять направление заполнения по модели (0|1)
- `extra_solid_infills` - Дополнительные сплошные заполнения (0|1)
- `minimum_sparse_infill_area` - Минимальная область разреженного заполнения
- `reduce_infill_retraction` - Уменьшить ретракцию заполнения (0|1)
- `internal_solid_infill_pattern` - Паттерн внутреннего сплошного заполнения
- `gap_fill_target` - Цель заполнения зазоров
- `infill_combination` - Комбинация заполнения (0|1)
- `infill_combination_max_layer_height` - Максимальная высота слоя комбинации заполнения
- `infill_anchor` - Якорь заполнения
- `infill_anchor_max` - Максимальный якорь заполнения

### Ironing (Глажка)
- `ironing_type` - Тип глажки
- `ironing_pattern` - Паттерн глажки
- `ironing_flow` - Поток глажки (%)
- `ironing_speed` - Скорость глажки (мм/с)
- `ironing_spacing` - Расстояние глажки (мм)
- `ironing_angle` - Угол глажки
- `ironing_angle_fixed` - Фиксированный угол глажки (0|1)
- `ironing_inset` - Вставка глажки (мм)
- `support_ironing` - Глажка поддержки (0|1)
- `support_ironing_pattern` - Паттерн глажки поддержки
- `support_ironing_flow` - Поток глажки поддержки (%)
- `support_ironing_spacing` - Расстояние глажки поддержки (мм)

### Скорости (Speeds)
- `inner_wall_speed` - Скорость внутренней стенки (мм/с)
- `outer_wall_speed` - Скорость внешней стенки (мм/с)
- `sparse_infill_speed` - Скорость разреженного заполнения (мм/с)
- `internal_solid_infill_speed` - Скорость внутреннего сплошного заполнения (мм/с)
- `top_surface_speed` - Скорость верхней поверхности (мм/с)
- `support_speed` - Скорость поддержки (мм/с)
- `support_interface_speed` - Скорость интерфейса поддержки (мм/с)
- `bridge_speed` - Скорость моста (мм/с)
- `internal_bridge_speed` - Скорость внутреннего моста (мм/с)
- `gap_infill_speed` - Скорость заполнения зазоров (мм/с)
- `travel_speed` - Скорость перемещения (мм/с)
- `travel_speed_z` - Скорость перемещения по Z (мм/с)
- `initial_layer_speed` - Скорость первого слоя (мм/с)
- `initial_layer_infill_speed` - Скорость заполнения первого слоя (мм/с)
- `initial_layer_travel_speed` - Скорость перемещения первого слоя (мм/с)
- `small_perimeter_speed` - Скорость малого периметра (мм/с)
- `small_perimeter_threshold` - Порог малого периметра
- `enable_overhang_speed` - Включить скорость свеса (0|1)
- `overhang_1_4_speed` - Скорость свеса 1/4 (мм/с)
- `overhang_2_4_speed` - Скорость свеса 2/4 (мм/с)
- `overhang_3_4_speed` - Скорость свеса 3/4 (мм/с)
- `overhang_4_4_speed` - Скорость свеса 4/4 (мм/с)
- `slowdown_for_curled_perimeters` - Замедление для скрученных периметров (0|1)
- `max_travel_detour_distance` - Максимальное расстояние объезда перемещения

### Ускорения (Accelerations)
- `outer_wall_acceleration` - Ускорение внешней стенки (мм/с²)
- `initial_layer_acceleration` - Ускорение первого слоя (мм/с²)
- `top_surface_acceleration` - Ускорение верхней поверхности (мм/с²)
- `default_acceleration` - Ускорение по умолчанию (мм/с²)
- `travel_acceleration` - Ускорение перемещения (мм/с²)
- `inner_wall_acceleration` - Ускорение внутренней стенки (мм/с²)
- `sparse_infill_acceleration` - Ускорение разреженного заполнения (мм/с²)
- `internal_solid_infill_acceleration` - Ускорение внутреннего сплошного заполнения (мм/с²)
- `bridge_acceleration` - Ускорение моста (мм/с²)
- `accel_to_decel_enable` - Включить ускорение до замедления (0|1)
- `accel_to_decel_factor` - Фактор ускорения до замедления

### Рывки (Jerks)
- `default_jerk` - Рывок по умолчанию (мм/с)
- `outer_wall_jerk` - Рывок внешней стенки (мм/с)
- `inner_wall_jerk` - Рывок внутренней стенки (мм/с)
- `infill_jerk` - Рывок заполнения (мм/с)
- `top_surface_jerk` - Рывок верхней поверхности (мм/с)
- `initial_layer_jerk` - Рывок первого слоя (мм/с)
- `travel_jerk` - Рывок перемещения (мм/с)
- `default_junction_deviation` - Отклонение соединения по умолчанию

### Ширина линий (Line Widths)
- `line_width` - Ширина линии (мм)
- `initial_layer_line_width` - Ширина линии первого слоя (мм)
- `inner_wall_line_width` - Ширина линии внутренней стенки (мм)
- `outer_wall_line_width` - Ширина линии внешней стенки (мм)
- `sparse_infill_line_width` - Ширина линии разреженного заполнения (мм)
- `internal_solid_infill_line_width` - Ширина линии внутреннего сплошного заполнения (мм)
- `skin_infill_line_width` - Ширина линии заполнения кожи (мм)
- `skeleton_infill_line_width` - Ширина линии скелетного заполнения (мм)
- `top_surface_line_width` - Ширина линии верхней поверхности (мм)
- `support_line_width` - Ширина линии поддержки (мм)
- `min_bead_width` - Минимальная ширина бусины (мм)
- `min_length_factor` - Фактор минимальной длины
- `min_width_top_surface` - Минимальная ширина верхней поверхности (мм)
- `initial_layer_min_bead_width` - Минимальная ширина бусины первого слоя (мм)

### Коэффициенты потока (Flow Ratios)
- `print_flow_ratio` - Коэффициент потока печати (%)
- `first_layer_flow_ratio` - Коэффициент потока первого слоя (%)
- `outer_wall_flow_ratio` - Коэффициент потока внешней стенки (%)
- `inner_wall_flow_ratio` - Коэффициент потока внутренней стенки (%)
- `overhang_flow_ratio` - Коэффициент потока свеса (%)
- `sparse_infill_flow_ratio` - Коэффициент потока разреженного заполнения (%)
- `internal_solid_infill_flow_ratio` - Коэффициент потока внутреннего сплошного заполнения (%)
- `gap_fill_flow_ratio` - Коэффициент потока заполнения зазоров (%)
- `support_flow_ratio` - Коэффициент потока поддержки (%)
- `support_interface_flow_ratio` - Коэффициент потока интерфейса поддержки (%)
- `top_solid_infill_flow_ratio` - Коэффициент потока верхнего сплошного заполнения (%)
- `bottom_solid_infill_flow_ratio` - Коэффициент потока нижнего сплошного заполнения (%)
- `set_other_flow_ratios` - Установить другие коэффициенты потока (0|1)
- `bridge_flow` - Поток моста (%)
- `internal_bridge_flow` - Поток внутреннего моста (%)
- `small_area_infill_flow_compensation` - Компенсация потока заполнения малой области (0|1)
- `small_area_infill_flow_compensation_model` - Модель компенсации потока заполнения малой области

### Поддержка (Support)
- `enable_support` - Включить поддержку (0|1)
- `support_type` - Тип поддержки
- `support_threshold_angle` - Пороговый угол поддержки
- `support_threshold_overlap` - Пороговое перекрытие поддержки
- `enforce_support_layers` - Принудительные слои поддержки (0|1)
- `support_on_build_plate_only` - Поддержка только на столе (0|1)
- `support_critical_regions_only` - Поддержка только критических областей (0|1)
- `support_remove_small_overhang` - Удалить малый свес поддержки (0|1)
- `support_angle` - Угол поддержки
- `support_interface_top_layers` - Верхние слои интерфейса поддержки
- `support_interface_bottom_layers` - Нижние слои интерфейса поддержки
- `support_interface_pattern` - Паттерн интерфейса поддержки
- `support_interface_spacing` - Расстояние интерфейса поддержки
- `support_interface_loop_pattern` - Паттерн петли интерфейса поддержки
- `support_top_z_distance` - Расстояние Z верхней поддержки
- `support_bottom_z_distance` - Расстояние Z нижней поддержки
- `support_object_xy_distance` - Расстояние XY поддержки от объекта
- `support_object_first_layer_gap` - Зазор первого слоя поддержки от объекта
- `support_base_pattern` - Паттерн базы поддержки
- `support_base_pattern_spacing` - Расстояние паттерна базы поддержки
- `support_expansion` - Расширение поддержки
- `support_style` - Стиль поддержки
- `support_interface_not_for_body` - Интерфейс поддержки не для тела (0|1)
- `support_bottom_interface_spacing` - Расстояние нижнего интерфейса поддержки

### Tree Support (Древовидная поддержка)
- `tree_support_branch_angle` - Угол ветви древовидной поддержки
- `tree_support_angle_slow` - Медленный угол древовидной поддержки
- `tree_support_wall_count` - Количество стенок древовидной поддержки
- `tree_support_top_rate` - Скорость верха древовидной поддержки
- `tree_support_branch_distance` - Расстояние ветвей древовидной поддержки
- `tree_support_tip_diameter` - Диаметр кончика древовидной поддержки
- `tree_support_branch_diameter` - Диаметр ветви древовидной поддержки
- `tree_support_branch_diameter_angle` - Угол диаметра ветви древовидной поддержки
- `tree_support_branch_distance_organic` - Органическое расстояние ветвей древовидной поддержки
- `tree_support_branch_diameter_organic` - Органический диаметр ветви древовидной поддержки
- `tree_support_branch_angle_organic` - Органический угол ветви древовидной поддержки
- `tree_support_auto_brim` - Автоматический брызг древовидной поддержки (0|1)
- `tree_support_brim_width` - Ширина брызга древовидной поддержки

### Raft (Плот)
- `raft_layers` - Количество слоев плота
- `raft_first_layer_density` - Плотность первого слоя плота
- `raft_first_layer_expansion` - Расширение первого слоя плота
- `raft_contact_distance` - Расстояние контакта плота
- `raft_expansion` - Расширение плота

### Brim (Брызг)
- `brim_width` - Ширина брызга (мм)
- `brim_object_gap` - Зазор брызга от объекта (мм)
- `brim_type` - Тип брызга
- `brim_ears_max_angle` - Максимальный угол ушей брызга
- `brim_ears_detection_length` - Длина обнаружения ушей брызга

### Skirt (Юбка)
- `skirt_type` - Тип юбки
- `skirt_loops` - Количество петель юбки
- `skirt_speed` - Скорость юбки (мм/с)
- `min_skirt_length` - Минимальная длина юбки (мм)
- `skirt_distance` - Расстояние юбки (мм)
- `skirt_start_angle` - Начальный угол юбки
- `skirt_height` - Высота юбки
- `single_loop_draft_shield` - Однослойный защитный экран (0|1)
- `draft_shield` - Защитный экран (0|1)

### Prime Tower (Башня прайминга)
- `enable_prime_tower` - Включить башню прайминга (0|1)
- `prime_tower_enable_framework` - Включить каркас башни прайминга (0|1)
- `prime_tower_width` - Ширина башни прайминга (мм)
- `prime_tower_brim_width` - Ширина брызга башни прайминга (мм)
- `prime_tower_skip_points` - Пропустить точки башни прайминга
- `prime_volume` - Объем прайминга
- `prime_tower_infill_gap` - Зазор заполнения башни прайминга
- `prime_tower_flat_ironing` - Плоская глажка башни прайминга (0|1)
- `wipe_tower_no_sparse_layers` - Башня очистки без разреженных слоев (0|1)
- `wipe_tower_cone_angle` - Угол конуса башни очистки
- `wipe_tower_extra_spacing` - Дополнительное расстояние башни очистки
- `wipe_tower_max_purge_speed` - Максимальная скорость очистки башни очистки
- `wipe_tower_wall_type` - Тип стенки башни очистки
- `wipe_tower_extra_rib_length` - Дополнительная длина ребра башни очистки
- `wipe_tower_rib_width` - Ширина ребра башни очистки
- `wipe_tower_fillet_wall` - Фаска стенки башни очистки (0|1)
- `wipe_tower_filament` - Филамент башни очистки
- `wiping_volumes_extruders` - Объемы очистки экструдеров
- `wipe_tower_bridging` - Мостование башни очистки (0|1)
- `wipe_tower_extra_flow` - Дополнительный поток башни очистки
- `single_extruder_multi_material_priming` - Прайминг мультиматериала одним экструдером (0|1)

### Компенсация
- `elefant_foot_compensation` - Компенсация слоновьей ноги (мм)
- `elefant_foot_compensation_layers` - Слои компенсации слоновьей ноги
- `xy_contour_compensation` - Компенсация контура XY (мм)
- `xy_hole_compensation` - Компенсация отверстий XY (мм)
- `resolution` - Разрешение

### Экструдеры
- `print_extruder_id` - ID экструдера печати
- `print_extruder_variant` - Вариант экструдера печати
- `wall_filament` - Филамент стенки
- `sparse_infill_filament` - Филамент разреженного заполнения
- `solid_infill_filament` - Филамент сплошного заполнения
- `support_filament` - Филамент поддержки
- `support_interface_filament` - Филамент интерфейса поддержки

### Специальные функции
- `fuzzy_skin` - Размытая кожа (0|1)
- `fuzzy_skin_thickness` - Толщина размытой кожи (мм)
- `fuzzy_skin_point_distance` - Расстояние точек размытой кожи (мм)
- `fuzzy_skin_first_layer` - Размытая кожа первого слоя (0|1)
- `fuzzy_skin_noise_type` - Тип шума размытой кожи
- `fuzzy_skin_mode` - Режим размытой кожи
- `fuzzy_skin_scale` - Масштаб размытой кожи
- `fuzzy_skin_octaves` - Октавы размытой кожи
- `fuzzy_skin_persistence` - Персистентность размытой кожи
- `max_volumetric_extrusion_rate_slope` - Максимальный наклон объемной скорости экструзии
- `max_volumetric_extrusion_rate_slope_segment_length` - Длина сегмента максимального наклона объемной скорости экструзии
- `extrusion_rate_smoothing_external_perimeter_only` - Сглаживание скорости экструзии только внешнего периметра (0|1)
- `bridge_no_support` - Мост без поддержки (0|1)
- `thick_bridges` - Толстые мосты (0|1)
- `thick_internal_bridges` - Толстые внутренние мосты (0|1)
- `dont_filter_internal_bridges` - Не фильтровать внутренние мосты (0|1)
- `enable_extra_bridge_layer` - Включить дополнительный слой моста (0|1)
- `max_bridge_length` - Максимальная длина моста (мм)
- `bridge_angle` - Угол моста
- `internal_bridge_angle` - Угол внутреннего моста
- `bridge_density` - Плотность моста (%)
- `internal_bridge_density` - Плотность внутреннего моста (%)
- `make_overhang_printable` - Сделать свес печатаемым (0|1)
- `make_overhang_printable_angle` - Угол делания свеса печатаемым
- `make_overhang_printable_hole_size` - Размер отверстия делания свеса печатаемым
- `detect_narrow_internal_solid_infill` - Обнаруживать узкое внутреннее сплошное заполнение (0|1)
- `precise_outer_wall` - Точная внешняя стенка (0|1)
- `precise_z_height` - Точная высота Z (0|1)
- `only_one_wall_top` - Только одна стенка сверху (0|1)
- `only_one_wall_first_layer` - Только одна стенка первого слоя (0|1)
- `filter_out_gap_fill` - Фильтровать заполнение зазоров (0|1)
- `enable_wrapping_detection` - Включить обнаружение обертывания (0|1)

### Генератор стенок
- `wall_generator` - Генератор стенок
- `wall_transition_length` - Длина перехода стенки
- `wall_transition_filter_deviation` - Отклонение фильтра перехода стенки
- `wall_transition_angle` - Угол перехода стенки
- `wall_distribution_count` - Количество распределения стенок
- `min_feature_size` - Минимальный размер элемента

### Перекрытия
- `infill_wall_overlap` - Перекрытие заполнения и стенки (%)
- `top_bottom_infill_wall_overlap` - Перекрытие заполнения верх/низ и стенки (%)

### Очистка (Wipe)
- `role_based_wipe_speed` - Скорость очистки на основе роли (0|1)
- `wipe_speed` - Скорость очистки (мм/с)
- `wipe_on_loops` - Очистка на петлях (0|1)
- `wipe_before_external_loop` - Очистка перед внешней петлей (0|1)

### Специальные настройки
- `ooze_prevention` - Предотвращение протекания (0|1)
- `standby_temperature_delta` - Дельта температуры ожидания
- `preheat_time` - Время предварительного нагрева
- `preheat_steps` - Шаги предварительного нагрева
- `interface_shells` - Интерфейсные оболочки (0|1)
- `flush_into_infill` - Промывка в заполнение (0|1)
- `flush_into_objects` - Промывка в объекты (0|1)
- `flush_into_support` - Промывка в поддержку (0|1)

### Порядок печати
- `print_sequence` - Последовательность печати
- `print_order` - Порядок печати

### G-code
- `filename_format` - Формат имени файла
- `gcode_comments` - Комментарии G-code (0|1)
- `gcode_label_objects` - Метки объектов G-code (0|1)
- `gcode_add_line_number` - Добавить номера строк G-code (0|1)
- `enable_arc_fitting` - Включить подгонку дуг (0|1)
- `post_process` - Постобработка

### Таймлапс
- `timelapse_type` - Тип таймлапса

### Специальные функции
- `independent_support_layer_height` - Независимая высота слоя поддержки (0|1)
- `slow_down_layers` - Замедлить слои
- `exclude_object` - Исключить объект (0|1)
- `interlocking_beam` - Блокирующая балка (0|1)
- `interlocking_orientation` - Ориентация блокировки
- `interlocking_beam_layer_count` - Количество слоев блокирующей балки
- `interlocking_depth` - Глубина блокировки
- `interlocking_boundary_avoidance` - Избегание границы блокировки
- `interlocking_beam_width` - Ширина блокирующей балки
- `calib_flowrate_topinfill_special_order` - Специальный порядок калибровки потока верхнего заполнения
- `hole_to_polyhole` - Отверстие в полиотверстие (0|1)
- `hole_to_polyhole_threshold` - Порог отверстия в полиотверстие
- `hole_to_polyhole_twisted` - Скрученное отверстие в полиотверстие (0|1)
- `mmu_segmented_region_max_width` - Максимальная ширина сегментированной области MMU
- `mmu_segmented_region_interlocking_depth` - Глубина блокировки сегментированной области MMU

### Совместимость
- `compatible_printers` - Список совместимых принтеров (массив строк)
- `compatible_printers_condition` - Условие совместимости принтеров (строка)

### Заметки
- `notes` - Заметки пользователя (строка, может быть пустой)

---

## 4. SLA PRINT PROFILE FIELDS (Поля SLA пресетов печати)

> **⚠️ ВАЖНО:** Эти поля используются ТОЛЬКО для SLA профилей типа `type: "sla_print"`  
> **Source:** `s_Preset_sla_print_options` в `Preset.cpp` (строки 1024-1069)

**Complete list of fields from `s_Preset_sla_print_options`:**

### Layer settings
- `layer_height` - Layer height (mm)
- `faded_layers` - Faded layers
- `slice_closing_radius` - Slice closing radius

### Support settings
- `supports_enable` - Enable supports (0|1)
- `support_head_front_diameter` - Support head front diameter
- `support_head_penetration` - Support head penetration
- `support_head_width` - Support head width
- `support_pillar_diameter` - Support pillar diameter
- `support_small_pillar_diameter_percent` - Small pillar diameter percent
- `support_max_bridges_on_pillar` - Max bridges on pillar
- `support_pillar_connection_mode` - Pillar connection mode
- `support_buildplate_only` - Support on buildplate only (0|1)
- `support_pillar_widening_factor` - Pillar widening factor
- `support_base_diameter` - Support base diameter
- `support_base_height` - Support base height
- `support_base_safety_distance` - Support base safety distance
- `support_critical_angle` - Support critical angle
- `support_max_bridge_length` - Max bridge length
- `support_max_pillar_link_distance` - Max pillar link distance
- `support_object_elevation` - Support object elevation
- `support_points_density_relative` - Support points density relative
- `support_points_minimal_distance` - Support points minimal distance

### Pad settings
- `pad_enable` - Enable pad (0|1)
- `pad_wall_thickness` - Pad wall thickness
- `pad_wall_height` - Pad wall height
- `pad_brim_size` - Pad brim size
- `pad_max_merge_distance` - Pad max merge distance
- `pad_wall_slope` - Pad wall slope
- `pad_object_gap` - Pad object gap
- `pad_around_object` - Pad around object (0|1)
- `pad_around_object_everywhere` - Pad around object everywhere (0|1)
- `pad_object_connector_stride` - Pad object connector stride
- `pad_object_connector_width` - Pad object connector width
- `pad_object_connector_penetration` - Pad object connector penetration

### Hollowing settings
- `hollowing_enable` - Enable hollowing (0|1)
- `hollowing_min_thickness` - Hollowing min thickness
- `hollowing_quality` - Hollowing quality
- `hollowing_closing_distance` - Hollowing closing distance

### Other settings
- `filename_format` - Filename format
- `default_sla_print_profile` - Default SLA print profile
- `compatible_printers` - List of compatible printers (array of strings)
- `compatible_printers_condition` - Compatible printers condition (string)
- `inherits` - Base profile for inheritance

---

## 5. SLA MATERIAL PROFILE FIELDS (Поля SLA пресетов материалов)

> **⚠️ ВАЖНО:** Эти поля используются ТОЛЬКО для SLA профилей типа `type: "sla_material"`  
> **Source:** `s_Preset_sla_material_options` в `Preset.cpp` (строки 1071-1090)

**Complete list of fields from `s_Preset_sla_material_options`:**

### Material properties
- `material_colour` - Material colour
- `material_type` - Material type
- `material_vendor` - Material vendor
- `material_density` - Material density
- `material_print_speed` - Material print speed

### Layer settings
- `initial_layer_height` - Initial layer height (mm)

### Exposure settings
- `exposure_time` - Exposure time
- `initial_exposure_time` - Initial exposure time

### Material correction
- `material_correction` - Material correction
- `material_correction_x` - Material correction X
- `material_correction_y` - Material correction Y
- `material_correction_z` - Material correction Z

### Cost and volume
- `bottle_cost` - Bottle cost
- `bottle_volume` - Bottle volume
- `bottle_weight` - Bottle weight

### Default profile
- `default_sla_material_profile` - Default SLA material profile

### Compatibility
- `compatible_prints` - List of compatible print profiles (array of strings)
- `compatible_prints_condition` - Compatible prints condition (string)
- `compatible_printers` - List of compatible printers (array of strings)
- `compatible_printers_condition` - Compatible printers condition (string)
- `inherits` - Base profile for inheritance

---

## 6. SLA PRINTER PROFILE FIELDS (Поля SLA профилей принтеров)

> **⚠️ ВАЖНО:** Эти поля используются ТОЛЬКО для SLA профилей типа `type: "machine"` с `printer_technology: "SLA"`  
> **Source:** `s_Preset_sla_printer_options` в `Preset.cpp` (строки 1092-1110)

**Complete list of fields from `s_Preset_sla_printer_options`:**

### Basic settings
- `printer_technology` - Printer technology (must be "SLA")
- `printable_area` - Printable area
- `printable_height` - Printable height (mm)
- `bed_custom_texture` - Bed custom texture
- `bed_custom_model` - Bed custom model
- `inherits` - Base profile for inheritance

### Display settings
- `display_width` - Display width (mm)
- `display_height` - Display height (mm)
- `display_pixels_x` - Display pixels X
- `display_pixels_y` - Display pixels Y
- `display_mirror_x` - Display mirror X (0|1)
- `display_mirror_y` - Display mirror Y (0|1)
- `display_orientation` - Display orientation

### Tilt settings
- `fast_tilt_time` - Fast tilt time
- `slow_tilt_time` - Slow tilt time
- `area_fill` - Area fill

### Correction settings
- `relative_correction` - Relative correction
- `relative_correction_x` - Relative correction X
- `relative_correction_y` - Relative correction Y
- `relative_correction_z` - Relative correction Z
- `absolute_correction` - Absolute correction

### Compensation
- `elefant_foot_compensation` - Elephant foot compensation
- `elefant_foot_min_width` - Elephant foot min width

### Gamma correction
- `gamma_correction` - Gamma correction

### Exposure time limits
- `min_exposure_time` - Min exposure time
- `max_exposure_time` - Max exposure time
- `min_initial_exposure_time` - Min initial exposure time
- `max_initial_exposure_time` - Max initial exposure time

---

## 7. MACHINE LIMITS FIELDS (Поля ограничений машины)

> **⚠️ ВАЖНО:** Эти поля используются для Printer Profiles (`TYPE_PRINTER`) для ограничений движения принтера  
> **Source:** `s_Preset_machine_limits_options` в `Preset.cpp` (строки 987-996)

**Complete list of fields from `s_Preset_machine_limits_options`:**

### Acceleration limits
- `machine_max_acceleration_extruding` - Max acceleration when extruding
- `machine_max_acceleration_retracting` - Max acceleration when retracting
- `machine_max_acceleration_travel` - Max acceleration when traveling
- `machine_max_acceleration_x` - Max acceleration X axis
- `machine_max_acceleration_y` - Max acceleration Y axis
- `machine_max_acceleration_z` - Max acceleration Z axis
- `machine_max_acceleration_e` - Max acceleration E axis

### Speed limits
- `machine_max_speed_x` - Max speed X axis
- `machine_max_speed_y` - Max speed Y axis
- `machine_max_speed_z` - Max speed Z axis
- `machine_max_speed_e` - Max speed E axis

### Minimum rates
- `machine_min_extruding_rate` - Min extruding rate
- `machine_min_travel_rate` - Min travel rate

### Jerk limits
- `machine_max_jerk_x` - Max jerk X axis
- `machine_max_jerk_y` - Max jerk Y axis
- `machine_max_jerk_z` - Max jerk Z axis
- `machine_max_jerk_e` - Max jerk E axis
- `machine_max_junction_deviation` - Max junction deviation

### Resonance avoidance (ported from Qidi slicer)
- `resonance_avoidance` - Resonance avoidance (0|1)
- `min_resonance_avoidance_speed` - Min resonance avoidance speed
- `max_resonance_avoidance_speed` - Max resonance avoidance speed

---

## 8. PHYSICAL PRINTER FIELDS (Поля физических принтеров)

> **⚠️ ВАЖНО:** Physical Printer - это отдельный класс, НЕ Preset. Физический принтер использует Printer Preset и хранит сетевые настройки.  
> **Source:** `s_PhysicalPrinter_opts` в `Preset.cpp` (строки 3377-3393)

**Complete list of fields from `s_PhysicalPrinter_opts`:**

### Basic settings
- `preset_name` - Preset name (temporary option for compatibility with older Slicer versions)
- `preset_names` - List of preset names (set of strings)
- `printer_technology` - Printer technology (FFF|SLA)

### Print Host settings (network settings)
- `bbl_use_printhost` - Use BBL print host (0|1)
- `host_type` - Host type
- `print_host` - Print host URL/IP
- `print_host_webui` - Print host WebUI URL
- `printhost_apikey` - Print host API key
- `printhost_cafile` - Print host CA file path
- `printhost_port` - Print host port
- `printhost_authorization_type` - Print host authorization type
- `printhost_user` - Print host username (HTTP digest authentication RFC 2617)
- `printhost_password` - Print host password
- `printhost_ssl_ignore_revoke` - Ignore SSL certificate revocation (0|1)

**Note:** Physical Printer JSON format may also include fields from the associated Printer Preset.

---

## 9. PROJECT OPTIONS FIELDS (Поля опций проекта)

> **⚠️ ВАЖНО:** Эти поля используются для хранения конфигурации проекта (.3mf файлы), НЕ как отдельные JSON пресеты профилей  
> **Source:** `s_project_options` в `PresetBundle.cpp` (строки 37-52)  
> **Note:** TYPE_PLATE и TYPE_MODEL используются внутри проекта, но не имеют отдельных JSON файлов пресетов.

**Complete list of fields from `s_project_options`:**

### Filament flushing and colors
- `flush_volumes_vector` - Flush volumes vector (for multi-material)
- `flush_volumes_matrix` - Flush volumes matrix (for multi-material flushing)
- `filament_colour` - Filament colour (array of hex colors)
- `filament_colour_type` - Filament colour type
- `filament_multi_colour` - Filament multi colour settings

### Wipe tower settings
- `wipe_tower_x` - Wipe tower X position
- `wipe_tower_y` - Wipe tower Y position
- `wipe_tower_rotation_angle` - Wipe tower rotation angle

### Bed and extruder settings
- `curr_bed_type` - Current bed type
- `flush_multiplier` - Flush multiplier
- `nozzle_volume_type` - Nozzle volume type
- `filament_map_mode` - Filament map mode
- `filament_map` - Filament map configuration

**Note:** These fields are stored in project files (.3mf) and are specific to each project/plate, not as reusable presets.

---

## Важные замечания

1. **Формат значений:**
   - Все значения в OrcaSlicer хранятся как **массивы строк**: `["значение"]` или `["nil"]` для пустых
   - Это связано с поддержкой мультиэкструдеров (каждый экструдер - элемент массива)
   - Для обычного пресета используется массив из одного элемента `[value]`

2. **Обязательные поля:**
   - `version`, `name`, `from`, `inherits` (для наследования), `type`
   - Для filament: `filament_settings_id`
   - Для printer: `printer_model` (обычно)
   - Для print: `print_settings_id` (обычно)
   - Для SLA print: `print_settings_id` (обычно)
   - Для SLA material: `material_type` (обычно)

3. **Необязательные поля:**
   - Большинство полей необязательны
   - Если поле отсутствует, используется значение из базового профиля (`inherits`)

4. **FilamentHub метаданные:**
   - `fhub_id`, `fhub_source`, `fhub_draft_id` - добавляются нами в корень JSON
   - Эти поля игнорируются OrcaSlicer, но сохраняются в JSON файле

5. **Совместимость:**
   - Поля могут различаться между версиями OrcaSlicer
   - Новые версии могут добавлять новые поля
   - Старые поля могут быть устаревшими, но все еще поддерживаются

---

## Использование шаблона

Этот шаблон можно использовать для:
1. **Проверки полноты данных** - убедиться, что все важные поля присутствуют
2. **Валидации JSON** - проверить, что поля имеют правильные имена
3. **Документирования** - понимать структуру профилей OrcaSlicer
4. **Разработки** - знать, какие поля можно использовать при экспорте/импорте

---

**Источник:** `docs/OrcaSlicer/src/libslic3r/Preset.cpp` (строки 883-1110)

**Все типы пресетов и конфигураций:**

### JSON Profile Presets (сохраняются как отдельные .json файлы):
1. **Filament Presets** (`TYPE_FILAMENT`, `type: "filament"`) - строки 951-985
2. **Print Profiles** (`TYPE_PRINT`, `type: "process"`) - строки 883-949
3. **Printer Profiles** (`TYPE_PRINTER`, `type: "machine"`, `printer_technology: "FFF"`) - строки 998-1022
4. **SLA Print Profiles** (`TYPE_SLA_PRINT`, `type: "sla_print"`) - строки 1024-1069
5. **SLA Material Profiles** (`TYPE_SLA_MATERIAL`, `type: "sla_materials"`) - строки 1071-1090
6. **SLA Printer Profiles** (`TYPE_PRINTER`, `type: "machine"`, `printer_technology: "SLA"`) - строки 1092-1110

### Дополнительные конфигурации:
7. **Machine Limits** (используются в Printer Profiles) - строки 987-996
8. **Physical Printers** (`TYPE_PHYSICAL_PRINTER`, класс `PhysicalPrinter`) - строки 3377-3393
   - НЕ является Preset, но имеет свой JSON формат
   - Связывает Printer Preset с сетевыми настройками (Print Host)

### Проектные конфигурации (хранятся в .3mf файлах, НЕ отдельные пресеты):
9. **Project Options** (`TYPE_PLATE`, `TYPE_MODEL`) - строки 37-52 в `PresetBundle.cpp`
   - Используются внутри проектов, не как отдельные JSON профили
   - Содержат настройки для конкретного проекта/пластины/модели

