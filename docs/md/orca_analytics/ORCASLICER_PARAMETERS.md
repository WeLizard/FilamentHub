# OrcaSlicer Filament Profile Parameters

Полный список параметров профилей филаментов в OrcaSlicer на основе анализа реальных профилей.

## Базовые поля профиля

- `type`: "filament" (обязательно)
- `name`: имя профиля (обязательно)
- `inherits`: базовый профиль для наследования (опционально)
- `from`: "system" | "user" (обязательно)
- `instantiation`: "true" | "false"
- `setting_id`: уникальный ID настройки
- `filament_id`: уникальный ID филамента
- `renamed_from`: старое имя (если переименован)

## Температуры

### Экструдер (nozzle)
- `nozzle_temperature`: температура экструдера
- `nozzle_temperature_initial_layer`: температура для первого слоя
- `nozzle_temperature_range_low`: минимальная температура
- `nozzle_temperature_range_high`: максимальная температура

### Стол (bed/plate)
- `hot_plate_temp`: температура горячего стола
- `hot_plate_temp_initial_layer`: температура горячего стола для первого слоя
- `cool_plate_temp`: температура холодного стола
- `cool_plate_temp_initial_layer`: температура холодного стола для первого слоя
- `eng_plate_temp`: температура инженерного стола
- `eng_plate_temp_initial_layer`: температура инженерного стола для первого слоя
- `textured_plate_temp`: температура текстурированного стола
- `textured_plate_temp_initial_layer`: температура текстурированного стола для первого слоя
- `supertack_plate_temp`: температура супер-липкого стола
- `supertack_plate_temp_initial_layer`: температура супер-липкого стола для первого слоя
- `temperature_vitrification`: температура витрификации

### Камера
- `chamber_temperatures`: температуры камеры

## Вентиляторы (fans)

- `fan_min_speed`: минимальная скорость вентилятора (0-100)
- `fan_max_speed`: максимальная скорость вентилятора (0-100)
- `overhang_fan_speed`: скорость вентилятора для свесов (0-100)
- `overhang_fan_threshold`: порог свеса для активации вентилятора (например "25%")
- `fan_cooling_layer_time`: время охлаждения слоя вентилятором (секунды)
- `close_fan_the_first_x_layers`: закрыть вентилятор на первых X слоях
- `full_fan_speed_layer`: слой для полной скорости вентилятора
- `reduce_fan_stop_start_freq`: уменьшить частоту включения/выключения вентилятора (0|1)
- `additional_cooling_fan_speed`: дополнительная скорость охлаждения (для TPU и т.д.)
- `complete_print_exhaust_fan_speed`: скорость вытяжки после печати (0-100)
- `during_print_exhaust_fan_speed`: скорость вытяжки во время печати (0-100)
- `activate_air_filtration`: активировать воздушный фильтр (0|1)

## Свойства филамента

- `filament_type`: тип материала (PLA, ABS, PETG, TPU, etc.)
- `filament_vendor`: производитель
- `filament_diameter`: диаметр филамента (например "1.75")
- `filament_density`: плотность в г/см³ (например "1.24")
- `filament_cost`: стоимость (в копейках за грамм)
- `filament_settings_id`: ID настроек филамента
- `filament_is_support`: используется ли как поддержка (0|1)
- `filament_soluble`: растворимый (0|1)
- `filament_max_volumetric_speed`: максимальная объемная скорость экструзии
- `filament_flow_ratio`: коэффициент потока (множитель, например "0.98")

## Retraction (ретракция)

- `filament_retraction_length`: длина ретракции (мм)
- `filament_retraction_speed`: скорость ретракции (мм/с)
- `filament_deretraction_speed`: скорость де-ретракции (или "nil")
- `filament_retraction_minimum_travel`: минимальное расстояние перемещения для ретракции
- `filament_retract_before_wipe`: ретракция перед очисткой (nil|значение)
- `filament_retract_when_changing_layer`: ретракция при смене слоя
- `filament_retract_restart_extra`: дополнительная де-ретракция
- `filament_retraction_distances_when_cut`: расстояния ретракции при обрезке
- `filament_long_retractions_when_cut`: длинные ретракции при обрезке

## Wipe (очистка)

- `filament_wipe`: включить очистку
- `filament_wipe_distance`: расстояние очистки
- `filament_z_hop`: подъем Z при очистке
- `filament_z_hop_types`: типы подъема Z

## Скорости и замедления

- `slow_down_for_layer_cooling`: замедление для охлаждения слоя (0|1)
- `slow_down_layer_time`: время слоя для замедления (секунды)
- `slow_down_min_speed`: минимальная скорость при замедлении (мм/с)

## Scarf seam (шов)

- `filament_scarf_seam_type`: тип шва ("none" | другие)
- `filament_scarf_height`: высота шва (например "10%")
- `filament_scarf_gap`: зазор шва (например "15%")
- `filament_scarf_length`: длина шва

## Дополнительные параметры

- `filament_shrink`: усадка филамента (например "100%")
- `filament_minimal_purge_on_wipe_tower`: минимальная очистка на башне очистки
- `required_nozzle_HRC`: требуемая твердость сопла HRC
- `compatible_printers`: список совместимых принтеров (массив строк)

## G-code

- `filament_start_gcode`: начальный G-code для филамента
- `filament_end_gcode`: конечный G-code для филамента

## Специальные параметры (для мультитула)

- `filament_load_time`: время загрузки филамента
- `filament_unload_time`: время выгрузки филамента
- `filament_loading_speed`: скорость загрузки
- `filament_unloading_speed`: скорость выгрузки
- `filament_loading_speed_start`: начальная скорость загрузки
- `filament_cooling_initial_speed`: начальная скорость охлаждения
- `filament_cooling_final_speed`: конечная скорость охлаждения
- `filament_cooling_moves`: количество движений охлаждения
- `filament_multitool_ramming`: включить ramming для мультитула (0|1)
- `filament_multitool_ramming_flow`: поток ramming для мультитула
- `filament_stamping_distance`: расстояние штамповки
- `filament_stamping_loading_speed`: скорость загрузки при штамповке

## Важные особенности

1. **Все значения как массивы строк**: `["значение"]` или `["nil"]` для пустых
2. **Температуры**: целые числа в градусах Цельсия
3. **Проценты**: строки вида `"50%"` или просто числа `["50"]`
4. **Скорости**: обычно в мм/с, но могут быть проценты для вентиляторов
5. **Наследование**: большинство профилей наследуются от `fdm_filament_common` или специфичных базовых профилей

## Маппинг FilamentHub → OrcaSlicer

| FilamentHub | OrcaSlicer | Примечание |
|-------------|------------|------------|
| `extruder_temp` | `nozzle_temperature` | Температура экструдера |
| `bed_temp` | `hot_plate_temp`, `cool_plate_temp`, etc. | Температура стола |
| `print_speed` | ❌ | Нет прямого маппинга |
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

