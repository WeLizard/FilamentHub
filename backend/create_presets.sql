-- Create test presets
INSERT INTO presets (filament_id, name, description, is_official, extruder_temp, bed_temp, print_speed, travel_speed, layer_height, flow_rate, fan_speed, retraction_length, retraction_speed, rating, usage_count, moderation_status, active, created_at, updated_at) VALUES
-- Official presets
(1, 'Официальный пресет Bestfilament', 'Рекомендуемые настройки от производителя', true, 200, 60, 50, 150, 0.2, 100, 100, 5, 45, 4.8, 245, 'approved', true, NOW(), NOW()),
(2, 'Официальный пресет Bestfilament', 'Рекомендуемые настройки от производителя', true, 200, 60, 50, 150, 0.2, 100, 100, 5, 45, 4.8, 189, 'approved', true, NOW(), NOW()),
(3, 'Официальный пресет Sunlu', 'Рекомендуемые настройки от производителя', true, 240, 80, 40, 150, 0.2, 98, 50, 6, 40, 4.9, 312, 'approved', true, NOW(), NOW()),
(4, 'Официальный пресет Sunlu', 'Рекомендуемые настройки от производителя', true, 210, 60, 55, 150, 0.2, 100, 100, 5, 45, 4.8, 198, 'approved', true, NOW(), NOW()),
(5, 'Официальный пресет eSUN', 'Рекомендуемые настройки от производителя', true, 230, 50, 25, 100, 0.2, 95, 0, 3, 30, 4.7, 156, 'approved', true, NOW(), NOW()),
(6, 'Официальный пресет Polymaker', 'Рекомендуемые настройки от производителя', true, 205, 60, 50, 150, 0.2, 100, 100, 5, 45, 4.8, 234, 'approved', true, NOW(), NOW()),
-- Community presets
(1, '3D_Guru', 'Проверенная настройка для Ender 3 Pro', false, 195, 60, 45, 150, 0.2, 100, 100, 5, 45, 4.8, 124, 'approved', true, NOW(), NOW()),
(1, 'PrintMaster', 'Оптимизированная настройка для высокой скорости', false, 205, 55, 55, 150, 0.2, 100, 100, 5, 45, 4.5, 87, 'approved', true, NOW(), NOW()),
(3, 'PETG_Pro', 'Оптимальные настройки для прочности', false, 235, 85, 35, 150, 0.2, 98, 50, 6, 40, 4.9, 156, 'approved', true, NOW(), NOW())
ON CONFLICT DO NOTHING;

