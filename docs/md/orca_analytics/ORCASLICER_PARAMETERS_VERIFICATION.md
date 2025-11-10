# Сверка параметров FilamentHub с OrcaSlicer

Дата проверки: 2025-01-XX
Сверка меню создания профиля с:
1. Существующими профилями FilamentHub
2. Документацией OrcaSlicer (`ORCASLICER_PARAMETERS_FULL.md`)
3. Исходным кодом OrcaSlicer (если доступен)

## ✅ Реализованные параметры (в buildOrcaslicerSettings)

### Вкладка "Профиль прутка"

#### Температуры
- ✅ `nozzle_temperature_range_low` - минимальная температура
- ✅ `nozzle_temperature_range_high` - максимальная температура
- ✅ `nozzle_temperature_initial_layer` - температура первого слоя
- ✅ `idle_temperature` - температура простоя
- ❓ `temperature_vitrification` - температура витрификации (закомментирован в коде)
- ✅ `chamber_temperature` - температура камеры
- ✅ `activate_chamber_temp_control` - включить контроль камеры

#### Свойства филамента
- ✅ `filament_max_volumetric_speed` - максимальная объемная скорость
- ✅ `filament_adaptive_volumetric_speed` - адаптивная объемная скорость
- ✅ `volumetric_speed_coefficients` - коэффициенты объемной скорости
- ✅ `filament_shrink` - усадка филамента
- ✅ `filament_shrinkage_compensation_z` - компенсация усадки по Z
- ✅ `default_filament_colour` - цвет филамента по умолчанию
- ✅ `filament_adhesiveness_category` - категория адгезии
- ✅ `filament_is_support` - используется как поддержка
- ✅ `filament_soluble` - растворимый
- ✅ `filament_printable` - категория печатаемости

#### Ретракция
- ✅ `filament_deretraction_speed` - скорость де-ретракции
- ✅ `filament_retraction_minimum_travel` - минимальное расстояние для ретракции
- ✅ `filament_retract_before_wipe` - ретракция перед очисткой
- ✅ `filament_retract_when_changing_layer` - ретракция при смене слоя
- ✅ `filament_retract_restart_extra` - дополнительная де-ретракция

#### Lift (подъем Z)
- ✅ `filament_z_hop` - подъем Z при ретракции
- ✅ `filament_z_hop_types` - типы подъема Z
- ✅ `filament_retract_lift_above` - подъем Z выше определенной высоты
- ✅ `filament_retract_lift_below` - подъем Z ниже определенной высоты
- ✅ `filament_retract_lift_enforce` - принудительный подъем Z

#### Wipe (очистка)
- ✅ `filament_wipe` - включить очистку
- ✅ `filament_wipe_distance` - расстояние очистки
- ✅ `filament_flush_temp` - температура промывки при смене филамента
- ✅ `filament_flush_volumetric_speed` - объемная скорость промывки

#### Pressure Advance
- ✅ `pressure_advance` - значение pressure advance
- ✅ `enable_pressure_advance` - включить pressure advance
- ✅ `adaptive_pressure_advance` - адаптивный pressure advance
- ✅ `adaptive_pressure_advance_bridges` - адаптивный PA для мостов
- ✅ `adaptive_pressure_advance_overhangs` - адаптивный PA для свесов

### Вкладка "Охлаждение"

#### Основные вентиляторы
- ✅ `fan_min_speed` - минимальная скорость вентилятора
- ✅ `fan_max_speed` - максимальная скорость вентилятора
- ✅ `fan_cooling_layer_time` - время охлаждения слоя
- ✅ `slow_down_layer_time` - время слоя для замедления (порог макс. скорости)
- ✅ `full_fan_speed_layer` - слой для полной скорости вентилятора
- ✅ `close_fan_the_first_x_layers` - закрыть вентилятор на первых X слоях
- ✅ `reduce_fan_stop_start_freq` - уменьшить частоту вкл/выкл

#### Специальные вентиляторы
- ✅ `enable_overhang_bridge_fan` - включить для свесов и мостов
- ✅ `overhang_fan_speed` - скорость для свесов
- ✅ `overhang_fan_threshold` - порог свеса
- ✅ `internal_bridge_fan_speed` - скорость для внутренних мостов
- ✅ `support_material_interface_fan_speed` - скорость для интерфейса поддержки
- ✅ `ironing_fan_speed` - скорость для ironing
- ✅ `additional_cooling_fan_speed` - дополнительная скорость охлаждения

#### Вытяжка
- ✅ `during_print_exhaust_fan_speed` - скорость вытяжки во время печати
- ✅ `complete_print_exhaust_fan_speed` - скорость вытяжки после печати
- ✅ `activate_air_filtration` - активировать воздушный фильтр

### Вкладка "Переопределение параметров"

#### Скорости и замедления
- ✅ `slow_down_for_layer_cooling` - замедление для охлаждения слоя
- ✅ `slow_down_min_speed` - минимальная скорость при замедлении
- ✅ `dont_slow_down_outer_wall` - не замедлять внешнюю стенку

#### Дополнительные параметры ретракции
- ✅ `filament_retraction_distances_when_cut` - расстояния ретракции при обрезке
- ✅ `filament_long_retractions_when_cut` - длинные ретракции при обрезке
- ✅ `long_retractions_when_ec` - длинные ретракции при смене экструдера
- ✅ `retraction_distances_when_ec` - расстояния ретракции при смене экструдера

### Вкладка "Дополнительно"

#### G-code
- ✅ `filament_start_gcode` - начальный G-code для филамента (ИСПРАВЛЕНО)
- ✅ `filament_end_gcode` - конечный G-code для филамента (ИСПРАВЛЕНО)

#### Мультитул
- ✅ `filament_multitool_ramming` - включить ramming для мультитула
- ✅ `filament_multitool_ramming_flow` - поток ramming для мультитула
- ✅ `filament_multitool_ramming_volume` - объем ramming для мультитула
- ❌ `filament_ramming_parameters` - параметры ramming (не реализован, сложный параметр)

#### Загрузка/выгрузка филамента
- ✅ `filament_loading_speed` - скорость загрузки
- ✅ `filament_loading_speed_start` - начальная скорость загрузки
- ✅ `filament_unloading_speed` - скорость выгрузки
- ✅ `filament_unloading_speed_start` - начальная скорость выгрузки
- ✅ `filament_change_length` - длина смены филамента

#### Охлаждение при загрузке
- ✅ `filament_cooling_initial_speed` - начальная скорость охлаждения
- ✅ `filament_cooling_final_speed` - конечная скорость охлаждения
- ✅ `filament_cooling_moves` - количество движений охлаждения

#### Stamping
- ✅ `filament_stamping_distance` - расстояние штамповки
- ✅ `filament_stamping_loading_speed` - скорость загрузки при штамповке

#### Дополнительные параметры
- ✅ `filament_minimal_purge_on_wipe_tower` - минимальная очистка на башне очистки
- ✅ `pellet_flow_coefficient` - коэффициент потока для пеллет

### Вкладка "Экструдер ММ"
- ✅ `filament_extruder_variant` - вариант экструдера
- ✅ `required_nozzle_HRC` - требуемая твердость сопла HRC

### Вкладка "Зависимости"
- ✅ `compatible_printers` - список совместимых принтеров
- ✅ `compatible_printers_condition` - условие совместимости принтеров
- ✅ `compatible_prints` - список совместимых профилей печати
- ✅ `compatible_prints_condition` - условие совместимости профилей печати

### Вкладка "Заметки"
- ✅ `filament_notes` - заметки пользователя

---

## ❌ Недостающие параметры (есть в OrcaSlicer, но не реализованы)

### Температуры стола (bed/plate)
**ВАЖНО:** В нашей форме есть только базовое поле `bed_temp`, но нет специфичных полей для разных типов столов!

**ТЕКУЩЕЕ ПОВЕДЕНИЕ:** В `orcaslicer_exporter.py:69-76` все типы столов получают одинаковую температуру из базового поля `bed_temp`. Это означает, что если пользователь задаст разную температуру для разных типов столов в `orcaslicer_settings`, экспортер её не увидит (он перезаписывает температуры стола базовым значением).

**ПРОБЛЕМА:** Нет возможности задать разные температуры для разных типов столов через UI.

**НЕДОСТАЮЩИЕ ПАРАМЕТРЫ В UI:**
- ❌ `hot_plate_temp` - температура горячего стола
- ❌ `hot_plate_temp_initial_layer` - температура горячего стола для первого слоя
- ❌ `cool_plate_temp` - температура холодного стола
- ❌ `cool_plate_temp_initial_layer` - температура холодного стола для первого слоя
- ❌ `eng_plate_temp` - температура инженерного стола
- ❌ `eng_plate_temp_initial_layer` - температура инженерного стола для первого слоя
- ❌ `textured_plate_temp` - температура текстурированного стола
- ❌ `textured_plate_temp_initial_layer` - температура текстурированного стола для первого слоя
- ❌ `textured_cool_plate_temp` - температура холодного текстурированного стола
- ❌ `textured_cool_plate_temp_initial_layer` - температура холодного текстурированного стола для первого слоя
- ❌ `supertack_plate_temp` - температура супер-липкого стола
- ❌ `supertack_plate_temp_initial_layer` - температура супер-липкого стола для первого слоя

### Основная температура экструдера
- ✅ `nozzle_temperature` - основная температура экструдера (ПРАВИЛЬНО: используется `extruder_temp` из базовых полей и экспортируется в JSON через `orcaslicer_exporter.py:62`)

### Pressure Advance - дополнительные параметры
- ❌ `adaptive_pressure_advance_model` - модель адаптивного PA (сложный параметр, строка с данными)

### Wipe - возможно есть в OrcaSlicer, но не реализован
- ❌ `fan_always_on` - вентилятор всегда включен (закомментирован в коде как "возможно есть")

---

## ⚠️ Проблемы с названиями параметров

### G-code параметры
**ТЕКУЩИЕ (неправильные):**
- `start_filament_gcode`
- `end_filament_gcode`

**ПРАВИЛЬНЫЕ (по документации OrcaSlicer):**
- `filament_start_gcode`
- `filament_end_gcode`

**ИСПРАВЛЕНО:** Названия исправлены на `filament_start_gcode` и `filament_end_gcode`. Добавлена поддержка старых названий для обратной совместимости.

---

## 📊 Статистика

**Всего параметров в OrcaSlicer:** ~113 (по `ORCASLICER_PARAMETERS_FULL.md`)

**Реализовано в FilamentHub:** ~80

**Не реализовано:**
- Температуры стола (12 параметров) - **ВАЖНО!**
- `temperature_vitrification` (1 параметр)
- `adaptive_pressure_advance_model` (1 параметр)
- `fan_always_on` (1 параметр) - возможно не существует в OrcaSlicer
- `filament_ramming_parameters` (1 параметр) - сложный, не для UI

**Итого недостающих:** ~15 параметров (из них 12 - температуры стола)

---

## 🔧 Рекомендации по исправлению

### Критичные (нужно исправить сразу):
1. **Исправить названия G-code параметров:**
   - `start_filament_gcode` → `filament_start_gcode`
   - `end_filament_gcode` → `filament_end_gcode`

2. **Добавить температуры стола в вкладку "Профиль прутка":**
   - Добавить секцию "Температуры стола" с выбором типа стола
   - Реализовать поля для всех типов столов (hot, cool, eng, textured, textured_cool, supertack)
   - Каждый тип стола должен иметь `temp` и `temp_initial_layer`

### Желательные (можно добавить позже):
3. Добавить `temperature_vitrification` если это нужно для конкретных материалов
4. Проверить в исходниках OrcaSlicer, существует ли `fan_always_on`

### Опциональные (можно пропустить):
5. `adaptive_pressure_advance_model` - слишком сложный для UI
6. `filament_ramming_parameters` - настраивается через OrcaSlicer

---

## 📝 Следующие шаги

1. ✅ Создать этот документ (текущий файл)
2. ✅ Исправить названия G-code параметров (выполнено)
3. ⏳ Добавить температуры стола в UI (критично!)
4. ⏳ Проверить исходники OrcaSlicer для `fan_always_on` и `temperature_vitrification`
5. ⏳ Протестировать с реальными профилями OrcaSlicer

