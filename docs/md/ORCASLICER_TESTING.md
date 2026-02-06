# Тестирование синхронизации FilamentHub в OrcaSlicer

## 📍 Где найти логи

**Windows:**
```
C:\Users\<User>\AppData\Roaming\OrcaSlicer\log\
```

Или запусти OrcaSlicer из командной строки чтобы видеть логи в консоли:
```powershell
cd F:\FilamentHub\docs\OrcaSlicer\build\OrcaSlicer\Release
.\OrcaSlicer.exe
```

## 🧪 План тестирования

### 1. Авторизация ✅
**Что проверяем:**
- [ ] Открыть OrcaSlicer
- [ ] Перейти на вкладку **FilamentHub**
- [ ] Нажать кнопку **"Login"**
- [ ] Открывается модальное окно авторизации
- [ ] Ввести email и пароль
- [ ] После успешного входа:
  - [ ] Кнопка "Login" скрывается
  - [ ] Появляется кнопка "Logout"
  - [ ] Отображается имя пользователя (или email)
  - [ ] Отображается количество пресетов ("Presets: X")

**Логи для проверки:**
```
FilamentHub: Login success received. User ID: X
FilamentHub: Auto-syncing presets after login...
FilamentHub: Calling get_current_user with token length: X
```

### 2. Синхронизация пресетов ✅
**Что проверяем:**
- [ ] После авторизации запускается автоматическая синхронизация
- [ ] Или нажать кнопку **"Synchronize"** вручную
- [ ] Кнопка показывает состояние синхронизации ("Synchronizing...")
- [ ] После завершения синхронизации:
  - [ ] Кнопка возвращается в нормальное состояние
  - [ ] Обновляется количество пресетов

**Логи для проверки:**
```
FilamentHub: Starting preset synchronization (force_full_sync=...)
FilamentHub: Received presets list. Status: 200
FilamentHub: Received X presets
FilamentHub: Processing preset ID=..., name=...
FilamentHub: Profile downloaded successfully. Size: ...
FilamentHub: Profile imported successfully. Name: ...
FilamentHub: Saved mapping preset_id=... -> bundle_preset_name=...
FilamentHub: Synchronization completed. Synced: X, Updated: Y, Errors: Z
```

### 3. Импорт пресетов ✅
**Что проверяем:**
- [ ] Пресеты импортируются в OrcaSlicer
- [ ] Открыть вкладку **"Принтер"** (Printer tab)
- [ ] Найти dropdown **"Профиль прутка"** (Filament Profile)
- [ ] Проверить, что появились пресеты с постфиксом `[FilamentHub]`
- [ ] Имена пресетов должны быть: `ИмяПресета [FilamentHub]`

**Логи для проверки:**
```
FilamentHub: Profile imported successfully. Name: ...
FilamentHub: Saved mapping preset_id=... -> bundle_preset_name=...
```

### 4. Проверка родительских пресетов ✅
**Что проверяем:**
- [ ] В логах ищем сообщения о поиске родительских пресетов
- [ ] Проверить, что родительские пресеты находятся правильно

**Логи для проверки:**
```
FilamentHub: Looking for parent preset 'fdm_filament_pla' in system presets...
FilamentHub: Parent preset 'fdm_filament_pla' found (exact match)
```

**Или если не найден:**
```
FilamentHub: Available system presets (X total):
  - Generic PLA @System
  - Generic ABS @System
  - ...
FilamentHub: Parent preset 'fdm_filament_pla' not found in system presets, using 'fdm_filament_common' as fallback
```

### 5. Обновление маппинга системных пресетов (ВАЖНО!)
**После тестирования:**

1. **Найти в логах список системных пресетов:**
   ```
   FilamentHub: Available system presets (X total):
     - Generic PLA @System
     - Generic ABS @System
     - Generic PETG @System
     ...
   ```

2. **Обновить `material_type_base_map` в backend:**
   - Файл: `backend/app/services/orcaslicer_exporter.py`
   - Обновить маппинг с реальными именами из логов

**Пример:**
```python
material_type_base_map = {
    "PLA": "Generic PLA @System",  # было: "fdm_filament_pla"
    "ABS": "Generic ABS @System",  # было: "fdm_filament_abs"
    "PETG": "Generic PETG @System",  # было: "fdm_filament_pet"
    ...
}
```

## 🐛 Возможные проблемы и решения

### Проблема 1: "No auth token found"
**Решение:** Убедиться что авторизация прошла успешно

### Проблема 2: "Failed to import profile"
**Решение:** 
- Проверить логи на ошибки
- Убедиться что родительский пресет найден
- Проверить формат JSON профиля

### Проблема 3: Пресеты не появляются в dropdown
**Решение:**
- Проверить что маппинг сохранился
- Проверить что `wxGetApp().load_current_presets()` вызывается
- Перезапустить OrcaSlicer

### Проблема 4: "Parent preset not found"
**Решение:**
- Скопировать список системных пресетов из логов
- Обновить `material_type_base_map` в backend
- Пересоздать пресет или пересинхронизировать

## 📝 Что записать после тестирования

1. **Список системных пресетов** из логов
2. **Имена импортированных пресетов** (для проверки маппинга)
3. **Ошибки**, если есть
4. **Время синхронизации** (сколько пресетов синхронизировано за сколько времени)

## ✅ Критерии успеха

- [ ] Авторизация работает
- [ ] Синхронизация запускается автоматически после авторизации
- [ ] Пресеты импортируются в OrcaSlicer
- [ ] Пресеты появляются в dropdown "Профиль прутка" с постфиксом `[FilamentHub]`
- [ ] Маппинг пресетов сохраняется правильно
- [ ] Логи показывают реальные имена системных пресетов

## 🔄 Следующие шаги после успешного тестирования

1. Обновить `material_type_base_map` с реальными именами
2. Протестировать обновление пресетов (если изменились на FilamentHub)
3. Протестировать удаление пресетов (если удалены на FilamentHub)
4. Добавить визуальную пометку FilamentHub пресетов в dropdown

