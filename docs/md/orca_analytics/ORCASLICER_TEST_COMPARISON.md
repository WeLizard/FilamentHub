# Сравнение TEST-1 ABS и TEST-2 ABS

Детальное сравнение двух тестовых профилей для выявления всех различий.

## Основные отличия

### 1. Air Filtration (Воздушная фильтрация)
- **TEST-1**: `activate_air_filtration: ["0"]` - отключено
- **TEST-2**: `activate_air_filtration: ["1"]` - включено

### 2. Chamber Temperature Control (Контроль температуры камеры)
- **TEST-1**: `activate_chamber_temp_control: ["0"]` - отключено
- **TEST-2**: `activate_chamber_temp_control: ["1"]` - включено
- **TEST-1**: `chamber_temperature: ["0"]` - температура камеры 0
- **TEST-2**: `chamber_temperature: ["1"]` - температура камеры 1

### 3. Adaptive Pressure Advance (Адаптивный Pressure Advance)
- **TEST-1**: `adaptive_pressure_advance: ["0"]` - отключено
- **TEST-2**: `adaptive_pressure_advance: ["1"]` - включено
- **TEST-1**: `adaptive_pressure_advance_bridges: ["0"]` - отключено
- **TEST-2**: `adaptive_pressure_advance_bridges: ["1"]` - включено
- **TEST-1**: `adaptive_pressure_advance_overhangs: ["0"]` - отключено
- **TEST-2**: `adaptive_pressure_advance_overhangs: ["1"]` - включено

### 4. Filament Adaptive Volumetric Speed
- **TEST-1**: `filament_adaptive_volumetric_speed: ["0"]` - отключено
- **TEST-2**: `filament_adaptive_volumetric_speed: ["1"]` - включено

### 5. Don't Slow Down Outer Wall
- **TEST-1**: `dont_slow_down_outer_wall: ["0"]` - отключено
- **TEST-2**: `dont_slow_down_outer_wall: ["1"]` - включено

### 6. Filament Cooling (Охлаждение при загрузке)
- **TEST-1**: `filament_cooling_initial_speed: ["0"]` - отключено
- **TEST-2**: `filament_cooling_initial_speed: ["7"]` - включено (скорость 7)
- **TEST-1**: `filament_cooling_final_speed: ["0"]` - отключено
- **TEST-2**: `filament_cooling_final_speed: ["8"]` - включено (скорость 8)
- **TEST-1**: `filament_cooling_moves: ["0"]` - отключено
- **TEST-2**: `filament_cooling_moves: ["6"]` - включено (6 движений)

### 7. Filament Deretraction Speed
- **TEST-1**: `filament_deretraction_speed: ["nil"]` - не задано
- **TEST-2**: `filament_deretraction_speed: ["30"]` - скорость 30 мм/с

### 8. Filament End Gcode (небольшая опечатка)
- **TEST-1**: `filament_end_gcode: ["; filament end gcode \nSET_FAN_SPEED FAN=Nevermore SPEED=0"]`
- **TEST-2**: `filament_end_gcode: ["; filament end gcode \nSET_FAN_SPEEDwqe FAN=Nevermore SPEED=0"]` - опечатка "SPEEDwqe"

### 9. Filament Is Support
- **TEST-1**: `filament_is_support: ["0"]` - не используется как поддержка
- **TEST-2**: `filament_is_support: ["1"]` - используется как поддержка

### 10. Filament Loading/Unloading Speeds
- **TEST-1**: `filament_loading_speed: ["0"]` - скорость загрузки 0
- **TEST-2**: `filament_loading_speed: ["2"]` - скорость загрузки 2 мм/с
- **TEST-1**: `filament_loading_speed_start: ["0"]` - начальная скорость 0
- **TEST-2**: `filament_loading_speed_start: ["1"]` - начальная скорость 1 мм/с
- **TEST-1**: `filament_unloading_speed: ["0"]` - скорость выгрузки 0
- **TEST-2**: `filament_unloading_speed: ["4"]` - скорость выгрузки 4 мм/с
- **TEST-1**: `filament_unloading_speed_start: ["0"]` - начальная скорость выгрузки 0
- **TEST-2**: `filament_unloading_speed_start: ["3"]` - начальная скорость выгрузки 3 мм/с

### 11. Filament Multitool Ramming
- **TEST-1**: `filament_multitool_ramming: ["0"]` - отключено
- **TEST-2**: `filament_multitool_ramming: ["1"]` - включено

### 12. Filament Notes
- **TEST-1**: `filament_notes: [""]` - пусто
- **TEST-2**: `filament_notes: ["123v123v"]` - есть заметки

### 13. Filament Retract Before Wipe
- **TEST-1**: `filament_retract_before_wipe: ["nil"]` - не задано
- **TEST-2**: `filament_retract_before_wipe: ["70%"]` - ретракция 70% перед очисткой

### 14. Filament Retract Lift Enforce
- **TEST-1**: `filament_retract_lift_enforce: ["nil"]` - не задано
- **TEST-2**: `filament_retract_lift_enforce: ["All Surfaces"]` - принудительный подъем на всех поверхностях

### 15. Filament Retract Restart Extra
- **TEST-1**: `filament_retract_restart_extra: ["nil"]` - не задано
- **TEST-2**: `filament_retract_restart_extra: ["0"]` - дополнительная де-ретракция 0

### 16. Filament Retraction Length
- **TEST-1**: `filament_retraction_length: ["nil"]` - не задано
- **TEST-2**: `filament_retraction_length: ["0.8"]` - длина ретракции 0.8 мм

### 17. Filament Retraction Minimum Travel
- **TEST-1**: `filament_retraction_minimum_travel: ["nil"]` - не задано
- **TEST-2**: `filament_retraction_minimum_travel: ["1"]` - минимальное расстояние 1 мм

### 18. Filament Retraction Speed
- **TEST-1**: `filament_retraction_speed: ["nil"]` - не задано
- **TEST-2**: `filament_retraction_speed: ["30"]` - скорость ретракции 30 мм/с

### 19. Filament Soluble
- **TEST-1**: `filament_soluble: ["0"]` - не растворимый
- **TEST-2**: `filament_soluble: ["1"]` - растворимый

### 20. Filament Stamping
- **TEST-1**: `filament_stamping_distance: ["0"]` - расстояние штамповки 0
- **TEST-2**: `filament_stamping_distance: ["10"]` - расстояние штамповки 10 мм
- **TEST-1**: `filament_stamping_loading_speed: ["0"]` - скорость загрузки при штамповке 0
- **TEST-2**: `filament_stamping_loading_speed: ["9"]` - скорость загрузки при штамповке 9 мм/с

### 21. Filament Start Gcode
- **TEST-1**: `filament_start_gcode: ["; Filament gcode\nSET_FAN_SPEED FAN=Nevermore SPEED=1"]`
- **TEST-2**: `filament_start_gcode: ["; Filament gcode\nSET_FAN_SPEED FAN=Nevermore SPEED=1\nrwqev"]` - добавлен "rwqev"

### 22. Filament Toolchange Delay
- **TEST-1**: `filament_toolchange_delay: ["0"]` - задержка 0
- **TEST-2**: `filament_toolchange_delay: ["5"]` - задержка 5 секунд

### 23. Filament Wipe Distance
- **TEST-1**: `filament_wipe_distance: ["nil"]` - не задано
- **TEST-2**: `filament_wipe_distance: ["1"]` - расстояние очистки 1 мм

### 24. Filament Z Hop
- **TEST-1**: `filament_z_hop: ["nil"]` - не задано
- **TEST-2**: `filament_z_hop: ["0.4"]` - подъем Z 0.4 мм

### 25. Filament Z Hop Types
- **TEST-1**: `filament_z_hop_types: ["nil"]` - не задано
- **TEST-2**: `filament_z_hop_types: ["Normal Lift"]` - тип подъема "Normal Lift"

### 26. Full Fan Speed Layer
- **TEST-1**: `full_fan_speed_layer: ["0"]` - слой 0
- **TEST-2**: `full_fan_speed_layer: ["1"]` - слой 1

### 27. Idle Temperature
- **TEST-1**: `idle_temperature: ["0"]` - температура простоя 0
- **TEST-2**: `idle_temperature: ["2"]` - температура простоя 2°C

### 28. Reduce Fan Stop Start Freq
- **TEST-1**: `reduce_fan_stop_start_freq: ["0"]` - отключено
- **TEST-2**: `reduce_fan_stop_start_freq: ["1"]` - включено

## Итоговая статистика

**Всего различий: 28 параметров**

### Категории различий:

1. **Включенные функции (11 параметров):**
   - Air filtration, Chamber temp control, Adaptive PA, Adaptive volumetric speed, Multitool ramming, и т.д.

2. **Retraction параметры (6 параметров):**
   - Длина, скорость, минимальное расстояние, подъем Z, очистка

3. **Загрузка/выгрузка (5 параметров):**
   - Скорости загрузки/выгрузки, охлаждение при загрузке

4. **Дополнительные настройки (6 параметров):**
   - Штамповка, задержка смены инструмента, температура простоя, и т.д.

## Выводы

TEST-2 - это более продвинутая конфигурация с:
- Включенными дополнительными функциями (фильтрация, камера, adaptive PA)
- Настроенной ретракцией (длина, скорость, z-hop)
- Параметрами загрузки/выгрузки для мультитула
- Большим количеством настроек для профессиональной печати

TEST-1 - более простая базовая конфигурация с большинством параметров по умолчанию или отключенными.

