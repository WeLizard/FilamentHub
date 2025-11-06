# Маппинг параметров OrcaSlicer на вкладки UI

## Вкладки (как в OrcaSlicer):

### 1. "Профиль прутка" (Filament Profile)
**Основные параметры филамента**

#### Температуры
- `nozzle_temperature_range_low` - минимальная температура
- `nozzle_temperature_range_high` - максимальная температура
- `nozzle_temperature_initial_layer` - температура первого слоя
- `idle_temperature` - температура простоя
- `chamber_temperature` - температура камеры
- `activate_chamber_temp_control` - включить контроль камеры

#### Свойства филамента
- `filament_max_volumetric_speed` - максимальная объемная скорость
- `filament_adaptive_volumetric_speed` - адаптивная объемная скорость
- `volumetric_speed_coefficients` - коэффициенты объемной скорости
- `filament_shrink` - усадка филамента
- `filament_shrinkage_compensation_z` - компенсация усадки по Z
- `default_filament_colour` - цвет филамента
- `filament_adhesiveness_category` - категория адгезии
- `filament_is_support` - используется как поддержка
- `filament_soluble` - растворимый
- `filament_printable` - категория печатаемости

#### Ретракция
- `filament_retraction_length` - длина ретракции (базовое поле)
- `filament_retraction_speed` - скорость ретракции (базовое поле)
- `filament_deretraction_speed` - скорость де-ретракции
- `filament_retraction_minimum_travel` - минимальное расстояние для ретракции
- `filament_retract_before_wipe` - ретракция перед очисткой
- `filament_retract_when_changing_layer` - ретракция при смене слоя
- `filament_retract_restart_extra` - дополнительная де-ретракция

#### Lift (подъем Z)
- `filament_z_hop` - подъем Z при ретракции
- `filament_z_hop_types` - типы подъема Z
- `filament_retract_lift_above` - подъем Z выше определенной высоты
- `filament_retract_lift_below` - подъем Z ниже определенной высоты
- `filament_retract_lift_enforce` - принудительный подъем Z

#### Wipe
- `filament_wipe` - включить очистку
- `filament_wipe_distance` - расстояние очистки
- `filament_flush_temp` - температура промывки
- `filament_flush_volumetric_speed` - объемная скорость промывки

#### Pressure Advance
- `pressure_advance` - значение pressure advance
- `enable_pressure_advance` - включить pressure advance
- `adaptive_pressure_advance` - адаптивный pressure advance
- `adaptive_pressure_advance_bridges` - адаптивный PA для мостов
- `adaptive_pressure_advance_overhangs` - адаптивный PA для свесов

### 2. "Охлаждение" (Cooling)
**Все параметры связанные с вентиляторами**

#### Основные вентиляторы
- `fan_min_speed` - минимальная скорость вентилятора (базовое поле fan_speed маппится)
- `fan_max_speed` - максимальная скорость вентилятора
- `overhang_fan_speed` - скорость для свесов
- `overhang_fan_threshold` - порог свеса
- `fan_cooling_layer_time` - время охлаждения слоя
- `close_fan_the_first_x_layers` - закрыть вентилятор на первых X слоях
- `full_fan_speed_layer` - слой для полной скорости
- `reduce_fan_stop_start_freq` - уменьшить частоту вкл/выкл
- `additional_cooling_fan_speed` - дополнительная скорость охлаждения

#### Специальные вентиляторы
- `enable_overhang_bridge_fan` - включить для свесов и мостов
- `internal_bridge_fan_speed` - скорость для внутренних мостов
- `ironing_fan_speed` - скорость для ironing
- `support_material_interface_fan_speed` - скорость для интерфейса поддержки

#### Вытяжка
- `complete_print_exhaust_fan_speed` - скорость вытяжки после печати
- `during_print_exhaust_fan_speed` - скорость вытяжки во время печати
- `activate_air_filtration` - активировать воздушный фильтр

### 3. "Переопределение параметров" (Parameter Override)
**Дополнительные параметры процесса печати**

#### Скорости и замедления
- `slow_down_for_layer_cooling` - замедление для охлаждения слоя
- `slow_down_layer_time` - время слоя для замедления
- `slow_down_min_speed` - минимальная скорость при замедлении
- `dont_slow_down_outer_wall` - не замедлять внешнюю стенку

#### Дополнительные параметры ретракции
- `filament_retraction_distances_when_cut` - расстояния ретракции при обрезке
- `filament_long_retractions_when_cut` - длинные ретракции при обрезке
- `long_retractions_when_ec` - длинные ретракции при смене экструдера
- `retraction_distances_when_ec` - расстояния ретракции при смене экструдера

### 4. "Дополнительно" (Advanced)
**Продвинутые настройки**

#### Мультитул
- `filament_multitool_ramming` - включить ramming для мультитула
- `filament_multitool_ramming_flow` - поток ramming для мультитула
- `filament_multitool_ramming_volume` - объем ramming для мультитула
- `filament_ramming_parameters` - параметры ramming (строка)
- `filament_toolchange_delay` - задержка при смене инструмента

#### Загрузка/выгрузка филамента
- `filament_loading_speed` - скорость загрузки
- `filament_loading_speed_start` - начальная скорость загрузки
- `filament_unloading_speed` - скорость выгрузки
- `filament_unloading_speed_start` - начальная скорость выгрузки
- `filament_change_length` - длина смены филамента

#### Охлаждение при загрузке (для мультитула)
- `filament_cooling_initial_speed` - начальная скорость охлаждения
- `filament_cooling_final_speed` - конечная скорость охлаждения
- `filament_cooling_moves` - количество движений охлаждения

#### Stamping (штамповка, для мультитула)
- `filament_stamping_distance` - расстояние штамповки
- `filament_stamping_loading_speed` - скорость загрузки при штамповке

#### Дополнительные параметры
- `filament_minimal_purge_on_wipe_tower` - минимальная очистка на башне очистки
- `pellet_flow_coefficient` - коэффициент потока для пеллет

### 5. "Экструдер мм" (Extruder mm)
**Настройки экструдера**

- `filament_extruder_variant` - вариант экструдера (например "Direct Drive Standard")
- `required_nozzle_HRC` - требуемая твердость сопла HRC
- `filament_diameter` - диаметр филамента (базовое поле)
- `filament_density` - плотность филамента (базовое поле)
- `filament_flow_ratio` - коэффициент потока (базовое поле flow_rate маппится)

### 6. "Зависимости" (Dependencies)
**Совместимость с принтерами и профилями**

- `compatible_printers` - список совместимых принтеров (массив строк)
- `compatible_printers_condition` - условие совместимости принтеров
- `compatible_prints` - список совместимых профилей печати (массив строк)
- `compatible_prints_condition` - условие совместимости профилей печати

### 7. "Заметки" (Notes)
**Заметки пользователя**

- `filament_notes` - заметки пользователя (многострочная строка, textarea)

---

## Итого

**7 вкладок** - точно как в OrcaSlicer:
1. Профиль прутка - основные параметры филамента (температуры, ретракция, PA, wipe)
2. Охлаждение - все параметры вентиляторов
3. Переопределение параметров - дополнительные параметры процесса
4. Дополнительно - мультитул, загрузка/выгрузка, продвинутые настройки
5. Экструдер мм - настройки экструдера
6. Зависимости - совместимость
7. Заметки - заметки пользователя

