# Параметры OrcaSlicer для UI формы

Структура всех параметров для добавления в CreatePresetModal.

## Структура по секциям

### 1. Температуры (Temperature)

#### Экструдер
- `nozzle_temperature_range_low` - минимальная температура (число)
- `nozzle_temperature_range_high` - максимальная температура (число)
- `nozzle_temperature_initial_layer` - температура первого слоя (число, опционально)
- `idle_temperature` - температура простоя 0-255 (число, опционально)

#### Стол (уже есть базовый bed_temp, но можно добавить специфичные)
- `hot_plate_temp_initial_layer` - горячий стол первый слой (число)
- `cool_plate_temp_initial_layer` - холодный стол первый слой (число)
- `eng_plate_temp_initial_layer` - инженерный стол первый слой (число)
- `textured_plate_temp_initial_layer` - текстурированный стол первый слой (число)

#### Камера (уже есть)
- `chamber_temperature` - температура камеры (число)
- `activate_chamber_temp_control` - включить контроль (boolean)

### 2. Вентиляторы (Fans) - базовые уже есть

#### Дополнительные параметры вентиляторов
- `overhang_fan_speed` - скорость для свесов 0-100 (число)
- `overhang_fan_threshold` - порог свеса "25%" (строка с %)
- `fan_cooling_layer_time` - время охлаждения слоя (секунды)
- `close_fan_the_first_x_layers` - закрыть вентилятор на первых X слоях (число)
- `full_fan_speed_layer` - слой для полной скорости (число)
- `reduce_fan_stop_start_freq` - уменьшить частоту вкл/выкл (boolean)
- `additional_cooling_fan_speed` - дополнительная скорость охлаждения (число)

#### Специальные вентиляторы
- `enable_overhang_bridge_fan` - включить для свесов и мостов (boolean)
- `internal_bridge_fan_speed` - скорость для внутренних мостов -1 или число
- `ironing_fan_speed` - скорость для ironing -1 или число
- `support_material_interface_fan_speed` - скорость для интерфейса поддержки -1 или число

#### Вытяжка
- `complete_print_exhaust_fan_speed` - скорость вытяжки после печати 0-100 (число)
- `during_print_exhaust_fan_speed` - скорость вытяжки во время печати 0-100 (число)
- `activate_air_filtration` - активировать воздушный фильтр (boolean)

### 3. Свойства филамента (Filament Properties)

#### Поток и скорость (уже есть базовые)
- `filament_max_volumetric_speed` - максимальная объемная скорость (число, уже есть)
- `filament_adaptive_volumetric_speed` - адаптивная объемная скорость (boolean)
- `volumetric_speed_coefficients` - коэффициенты объемной скорости (строка)

#### Усадка
- `filament_shrink` - усадка филамента "99.8%" (строка с %)
- `filament_shrinkage_compensation_z` - компенсация усадки по Z "100%" (строка с %)

#### Визуальные
- `default_filament_colour` - цвет филамента "#000000" (строка hex)
- `filament_adhesiveness_category` - категория адгезии 0-? (число)

#### Дополнительные
- `filament_is_support` - используется как поддержка (boolean)
- `filament_soluble` - растворимый (boolean)
- `filament_printable` - категория печатаемости 0-5 (число, 3 = нормальная)

### 4. Ретракция (Retraction) - базовые уже есть

#### Дополнительные параметры ретракции
- `filament_deretraction_speed` - скорость де-ретракции (число или "nil")
- `filament_retraction_minimum_travel` - минимальное расстояние для ретракции (число или "nil")
- `filament_retract_before_wipe` - ретракция перед очисткой "70%" (строка с % или "nil")
- `filament_retract_when_changing_layer` - ретракция при смене слоя (boolean)
- `filament_retract_restart_extra` - дополнительная де-ретракция (число или "nil")
- `filament_retraction_distances_when_cut` - расстояния ретракции при обрезке (строка)
- `filament_long_retractions_when_cut` - длинные ретракции при обрезке (строка)

#### Lift (подъем Z)
- `filament_z_hop` - подъем Z при ретракции (число или "nil")
- `filament_z_hop_types` - типы подъема Z "Normal Lift" или "nil" (строка)
- `filament_retract_lift_above` - подъем Z выше определенной высоты (число)
- `filament_retract_lift_below` - подъем Z ниже определенной высоты (число)
- `filament_retract_lift_enforce` - принудительный подъем Z "All Surfaces" или "nil" (строка)

### 5. Wipe (очистка)

- `filament_wipe` - включить очистку (boolean)
- `filament_wipe_distance` - расстояние очистки (число или "nil")
- `filament_flush_temp` - температура промывки при смене филамента (число)
- `filament_flush_volumetric_speed` - объемная скорость промывки (число)

### 6. Скорости и замедления

- `slow_down_for_layer_cooling` - замедление для охлаждения слоя (boolean)
- `slow_down_layer_time` - время слоя для замедления (секунды, число)
- `slow_down_min_speed` - минимальная скорость при замедлении мм/с (число)
- `dont_slow_down_outer_wall` - не замедлять внешнюю стенку (boolean)

### 7. Pressure Advance (предварительное давление)

- `pressure_advance` - значение pressure advance (число, уже есть)
- `enable_pressure_advance` - включить pressure advance (boolean, уже есть)
- `adaptive_pressure_advance` - адаптивный pressure advance (boolean)
- `adaptive_pressure_advance_bridges` - адаптивный PA для мостов (boolean)
- `adaptive_pressure_advance_overhangs` - адаптивный PA для свесов (boolean)
- `adaptive_pressure_advance_model` - модель адаптивного PA (строка с данными, сложно для UI)

### 8. Мультитул (Multitool)

- `filament_multitool_ramming` - включить ramming для мультитула (boolean)
- `filament_multitool_ramming_flow` - поток ramming для мультитула % (число)
- `filament_multitool_ramming_volume` - объем ramming для мультитула мм³ (число)
- `filament_ramming_parameters` - параметры ramming (строка с данными, сложно для UI)
- `filament_toolchange_delay` - задержка при смене инструмента секунды (число)

### 9. Загрузка/выгрузка филамента

- `filament_loading_speed` - скорость загрузки мм/с (число)
- `filament_loading_speed_start` - начальная скорость загрузки мм/с (число)
- `filament_unloading_speed` - скорость выгрузки мм/с (число)
- `filament_unloading_speed_start` - начальная скорость выгрузки мм/с (число)
- `filament_change_length` - длина смены филамента мм (число)

### 10. Охлаждение при загрузке (для мультитула)

- `filament_cooling_initial_speed` - начальная скорость охлаждения (число)
- `filament_cooling_final_speed` - конечная скорость охлаждения (число)
- `filament_cooling_moves` - количество движений охлаждения (число)

### 11. Stamping (штамповка, для мультитула)

- `filament_stamping_distance` - расстояние штамповки мм (число)
- `filament_stamping_loading_speed` - скорость загрузки при штамповке мм/с (число)

### 12. Экструдер

- `filament_extruder_variant` - вариант экструдера "Direct Drive Standard" (строка)
- `required_nozzle_HRC` - требуемая твердость сопла HRC "3" (число)

### 13. Дополнительные параметры

- `filament_minimal_purge_on_wipe_tower` - минимальная очистка на башне очистки % (число)
- `long_retractions_when_ec` - длинные ретракции при смене экструдера (boolean)
- `retraction_distances_when_ec` - расстояния ретракции при смене экструдера мм (число)
- `pellet_flow_coefficient` - коэффициент потока для пеллет (число)

### 14. G-code

- `filament_start_gcode` - начальный G-code для филамента (многострочная строка, textarea)
- `filament_end_gcode` - конечный G-code для филамента (многострочная строка, textarea)

### 15. Совместимость

- `compatible_printers` - список совместимых принтеров (массив строк, сложно для UI - можно пропустить)
- `compatible_printers_condition` - условие совместимости принтеров (строка, сложно)
- `compatible_prints` - список совместимых профилей печати (массив строк, сложно)
- `compatible_prints_condition` - условие совместимости профилей печати (строка, сложно)

### 16. Заметки

- `filament_notes` - заметки пользователя (строка, textarea)

## Приоритеты для UI

**Высокий приоритет (показываем всем):**
- Температуры (диапазоны) ✅
- Объемная скорость ✅
- Вентиляторы (мин/макс) ✅
- Камера ✅
- Ретракция (базовые + продвинутые)
- Pressure Advance ✅
- Заметки

**Средний приоритет (продвинутые пользователи):**
- Wipe
- Скорости и замедления
- Адаптивный Pressure Advance
- Вытяжка и фильтрация
- Усадка

**Низкий приоритет (только для экспертов):**
- Мультитул параметры
- Загрузка/выгрузка
- Stamping
- Экструдер варианты
- G-code

## Структура UI формы

Рекомендуется организовать по аккордеонам/секциям:
1. Базовые настройки (уже есть)
2. Расширенные температуры
3. Расширенные вентиляторы
4. Ретракция и подъем Z
5. Wipe и очистка
6. Pressure Advance (расширенные)
7. Скорости и замедления
8. Мультитул
9. Загрузка/выгрузка
10. G-code
11. Заметки

