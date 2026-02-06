# OrcaSlicer Filament Profile Parameters (Полный список)

Полный список параметров профилей филаментов в OrcaSlicer на основе анализа реальных пользовательских профилей (TEST-1 ABS, TEST-2 ABS).

## Базовые поля профиля

- `type`: "filament" (необязательно, по умолчанию определяется из контекста)
- `name`: имя профиля (обязательно)
- `inherits`: базовый профиль для наследования (например "Voron Generic ABS")
- `from`: "system" | "User"
- `version`: версия профиля (например "2.3.0.0")
- `instantiation`: "true" | "false" (необязательно)
- `setting_id` или `filament_settings_id`: уникальный ID настройки
- `filament_id`: уникальный ID филамента (необязательно)

## Температуры

### Экструдер (nozzle)
- `nozzle_temperature`: температура экструдера
- `nozzle_temperature_initial_layer`: температура для первого слоя
- `nozzle_temperature_range_low`: минимальная температура
- `nozzle_temperature_range_high`: максимальная температура
- `idle_temperature`: температура простоя (0-255)

### Стол (bed/plate)
- `hot_plate_temp`: температура горячего стола
- `hot_plate_temp_initial_layer`: температура горячего стола для первого слоя
- `cool_plate_temp`: температура холодного стола
- `cool_plate_temp_initial_layer`: температура холодного стола для первого слоя
- `eng_plate_temp`: температура инженерного стола
- `eng_plate_temp_initial_layer`: температура инженерного стола для первого слоя
- `textured_plate_temp`: температура текстурированного стола
- `textured_plate_temp_initial_layer`: температура текстурированного стола для первого слоя
- `textured_cool_plate_temp`: температура холодного текстурированного стола (новое!)
- `textured_cool_plate_temp_initial_layer`: температура холодного текстурированного стола для первого слоя
- `supertack_plate_temp`: температура супер-липкого стола
- `supertack_plate_temp_initial_layer`: температура супер-липкого стола для первого слоя
- `temperature_vitrification`: температура витрификации

### Камера
- `chamber_temperature`: температура камеры (0 = выключено)
- `activate_chamber_temp_control`: активировать контроль температуры камеры (0|1)

## Вентиляторы (fans)

### Основные
- `fan_min_speed`: минимальная скорость вентилятора (0-100)
- `fan_max_speed`: максимальная скорость вентилятора (0-100)
- `overhang_fan_speed`: скорость вентилятора для свесов (0-100)
- `overhang_fan_threshold`: порог свеса для активации вентилятора (например "25%")
- `fan_cooling_layer_time`: время охлаждения слоя вентилятором (секунды)
- `close_fan_the_first_x_layers`: закрыть вентилятор на первых X слоях
- `full_fan_speed_layer`: слой для полной скорости вентилятора
- `reduce_fan_stop_start_freq`: уменьшить частоту включения/выключения вентилятора (0|1)
- `additional_cooling_fan_speed`: дополнительная скорость охлаждения (для TPU и т.д.)

### Специальные вентиляторы
- `enable_overhang_bridge_fan`: включить вентилятор для свесов и мостов (0|1)
- `internal_bridge_fan_speed`: скорость вентилятора для внутренних мостов (-1 = по умолчанию)
- `ironing_fan_speed`: скорость вентилятора для ironing (-1 = по умолчанию)
- `support_material_interface_fan_speed`: скорость вентилятора для интерфейса поддержки (-1 = по умолчанию)

### Вытяжка (exhaust)
- `complete_print_exhaust_fan_speed`: скорость вытяжки после печати (0-100)
- `during_print_exhaust_fan_speed`: скорость вытяжки во время печати (0-100)
- `activate_air_filtration`: активировать воздушный фильтр (0|1)

## Свойства филамента

### Основные
- `filament_type`: тип материала (PLA, ABS, PETG, TPU, etc.)
- `filament_vendor`: производитель
- `filament_diameter`: диаметр филамента (например "1.75")
- `filament_density`: плотность в г/см³ (например "1.04")
- `filament_cost`: стоимость (в копейках за грамм, например "852")
- `filament_settings_id`: ID настроек филамента (обычно = name)
- `filament_is_support`: используется ли как поддержка (0|1)
- `filament_soluble`: растворимый (0|1)
- `filament_printable`: категория печатаемости (0-5, где 3 = нормальная)

### Визуальные
- `default_filament_colour`: цвет филамента по умолчанию (например "#000000")
- `filament_adhesiveness_category`: категория адгезии (0-?)

### Поток и скорость
- `filament_max_volumetric_speed`: максимальная объемная скорость экструзии
- `filament_flow_ratio`: коэффициент потока (множитель, например "0.95")
- `filament_adaptive_volumetric_speed`: адаптивная объемная скорость (0|1)
- `volumetric_speed_coefficients`: коэффициенты объемной скорости (строка)

### Усадка
- `filament_shrink`: усадка филамента (например "99.8%")
- `filament_shrinkage_compensation_z`: компенсация усадки по Z (например "100%")

## Retraction (ретракция)

### Основные
- `filament_retraction_length`: длина ретракции (мм, или "nil")
- `filament_retraction_speed`: скорость ретракции (мм/с, или "nil")
- `filament_deretraction_speed`: скорость де-ретракции (мм/с, или "nil")
- `filament_retraction_minimum_travel`: минимальное расстояние перемещения для ретракции (мм, или "nil")
- `filament_retract_before_wipe`: ретракция перед очисткой ("nil" или процент, например "70%")
- `filament_retract_when_changing_layer`: ретракция при смене слоя (0|1|nil)
- `filament_retract_restart_extra`: дополнительная де-ретракция (мм, или "nil")
- `filament_retraction_distances_when_cut`: расстояния ретракции при обрезке
- `filament_long_retractions_when_cut`: длинные ретракции при обрезке

### Lift (подъем Z)
- `filament_z_hop`: подъем Z при ретракции (мм, или "nil")
- `filament_z_hop_types`: типы подъема Z ("nil" или "Normal Lift" и т.д.)
- `filament_retract_lift_above`: подъем Z выше определенной высоты
- `filament_retract_lift_below`: подъем Z ниже определенной высоты
- `filament_retract_lift_enforce`: принудительный подъем Z ("nil" или "All Surfaces" и т.д.)

## Wipe (очистка)

- `filament_wipe`: включить очистку (0|1)
- `filament_wipe_distance`: расстояние очистки (мм, или "nil")
- `filament_flush_temp`: температура промывки при смене филамента
- `filament_flush_volumetric_speed`: объемная скорость промывки

## Скорости и замедления

- `slow_down_for_layer_cooling`: замедление для охлаждения слоя (0|1)
- `slow_down_layer_time`: время слоя для замедления (секунды)
- `slow_down_min_speed`: минимальная скорость при замедлении (мм/с)
- `dont_slow_down_outer_wall`: не замедлять внешнюю стенку (0|1)

## Pressure Advance (предварительное давление)

- `pressure_advance`: значение pressure advance (например "0.038")
- `enable_pressure_advance`: включить pressure advance (0|1)
- `adaptive_pressure_advance`: адаптивный pressure advance (0|1)
- `adaptive_pressure_advance_bridges`: адаптивный PA для мостов (0|1)
- `adaptive_pressure_advance_overhangs`: адаптивный PA для свесов (0|1)
- `adaptive_pressure_advance_model`: модель адаптивного PA (строка с данными)

## Мультитул (multitool) параметры

- `filament_multitool_ramming`: включить ramming для мультитула (0|1)
- `filament_multitool_ramming_flow`: поток ramming для мультитула (%)
- `filament_multitool_ramming_volume`: объем ramming для мультитула (мм³)
- `filament_ramming_parameters`: параметры ramming (строка с данными)
- `filament_toolchange_delay`: задержка при смене инструмента (секунды)

## Загрузка/выгрузка филамента

- `filament_loading_speed`: скорость загрузки (мм/с)
- `filament_loading_speed_start`: начальная скорость загрузки (мм/с)
- `filament_unloading_speed`: скорость выгрузки (мм/с)
- `filament_unloading_speed_start`: начальная скорость выгрузки (мм/с)
- `filament_change_length`: длина смены филамента (мм)

## Охлаждение при загрузке (для мультитула)

- `filament_cooling_initial_speed`: начальная скорость охлаждения
- `filament_cooling_final_speed`: конечная скорость охлаждения
- `filament_cooling_moves`: количество движений охлаждения

## Stamping (штамповка, для мультитула)

- `filament_stamping_distance`: расстояние штамповки (мм)
- `filament_stamping_loading_speed`: скорость загрузки при штамповке (мм/с)

## Экструдер

- `filament_extruder_variant`: вариант экструдера (например "Direct Drive Standard")
- `required_nozzle_HRC`: требуемая твердость сопла HRC (например "3")

## Дополнительные параметры

- `filament_minimal_purge_on_wipe_tower`: минимальная очистка на башне очистки (%)
- `long_retractions_when_ec`: длинные ретракции при смене экструдера (0|1)
- `retraction_distances_when_ec`: расстояния ретракции при смене экструдера (мм)
- `pellet_flow_coefficient`: коэффициент потока для пеллет (например "0.4157")

## G-code

- `filament_start_gcode`: начальный G-code для филамента (многострочная строка)
- `filament_end_gcode`: конечный G-code для филамента (многострочная строка)

## Совместимость

- `compatible_printers`: список совместимых принтеров (массив строк)
- `compatible_printers_condition`: условие совместимости принтеров (строка)
- `compatible_prints`: список совместимых профилей печати (массив строк)
- `compatible_prints_condition`: условие совместимости профилей печати (строка)

## Заметки

- `filament_notes`: заметки пользователя (строка, может быть пустой)

## Особенности формата

1. **Все значения как массивы строк**: `["значение"]` или `["nil"]` для пустых
2. **Температуры**: целые числа в градусах Цельсия
3. **Проценты**: строки вида `"50%"` или просто числа `["50"]`
4. **Скорости**: обычно в мм/с, но могут быть проценты для вентиляторов
5. **Логические**: `"0"` или `"1"` в массиве `["0"]` или `["1"]`
6. **Специальные значения**: `"nil"` для отключенных параметров, `"-1"` для "по умолчанию"
7. **Многострочные строки**: используют `\n` для переноса строки в G-code

## Различия между TEST-1 и TEST-2

**TEST-2 имеет дополнительные включенные функции:**
- `activate_air_filtration`: "1" (в TEST-1: "0")
- `activate_chamber_temp_control`: "1" (в TEST-1: "0")
- `adaptive_pressure_advance`: "1" (в TEST-1: "0")
- `filament_retraction_length`: "0.8" (в TEST-1: "nil")
- `filament_retraction_speed`: "30" (в TEST-1: "nil")
- `filament_deretraction_speed`: "30" (в TEST-1: "nil")
- `filament_z_hop`: "0.4" (в TEST-1: "nil")
- `filament_wipe_distance`: "1" (в TEST-1: "nil")
- `filament_multitool_ramming`: "1" (в TEST-1: "0")
- И другие различия в параметрах загрузки/выгрузки

## Маппинг FilamentHub → OrcaSlicer (обновленный)

| FilamentHub | OrcaSlicer | Примечание |
|-------------|------------|------------|
| `extruder_temp` | `nozzle_temperature` | Температура экструдера |
| `bed_temp` | `hot_plate_temp`, `cool_plate_temp`, etc. | Температура стола |
| `print_speed` | ❌ | Нет прямого маппинга (это process параметр) |
| `travel_speed` | ❌ | Нет прямого маппинга |
| `layer_height` | ❌ | Это параметр process, не filament |
| `first_layer_height` | ❌ | Это параметр process, не filament |
| `flow_rate` | `filament_flow_ratio` | Коэффициент потока (процент → множитель) |
| `fan_speed` | `fan_min_speed`, `fan_max_speed` | Скорость вентилятора |
| `retraction_length` | `filament_retraction_length` | Длина ретракции |
| `retraction_speed` | `filament_retraction_speed` | Скорость ретракции |
| `density` | `filament_density` | Плотность |
| `diameter` | `filament_diameter` | Диаметр |
| `price_per_kg` | `filament_cost` | Цена (рубли/кг → копейки/г) |
| `material_type` | `filament_type` | Тип материала |
| `brand.name` | `filament_vendor` | Производитель |
| `color_hex` | `default_filament_colour` | Цвет филамента |

