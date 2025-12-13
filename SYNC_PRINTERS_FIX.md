# Исправление импорта профилей принтеров

**Дата:** 2025-11-23  
**Проблема:** При импорте профилей принтеров из OrcaSlicer записывается "Принтер 1921" вместо правильного имени

---

## 🔍 Анализ проблемы

### Что происходит сейчас:

1. OrcaSlicer отправляет `preset.name` (например "Voron 2.4 350 0.4 nozzle")
2. Backend ищет принтер по `printer_model`, `printer_vendor`, `inherits`
3. Если не находит - создает новый принтер
4. При создании принтера формируется имя из `manufacturer` и `model`
5. Но если эти поля пустые → имя = "Custom Unknown" → БД генерирует ID

### Где проблема:

**OrcaSlicer не отправляет `printer_model` и `printer_vendor`!**

Эти поля находятся в `orcaslicer_json` но не добавляются в `profile_data`.

---

## ✅ Решение

### 1. OrcaSlicer: Добавить метаданные в payload

**Файл:** `docs/OrcaSlicer/src/slic3r/GUI/FilamentHubPanel.cpp`  
**Функция:** `export_printer_profiles_to_filamenthub_internal()`, строка ~5420

**Добавлено:**

```cpp
// ВАЖНО: Добавляем метаданные для правильного сопоставления принтера
// Извлекаем vendor и model из orcaslicer_json
if (orcaslicer_json.contains("printer_model") && !orcaslicer_json["printer_model"].is_null()) {
    profile_data["printer_model"] = orcaslicer_json["printer_model"];
}
if (orcaslicer_json.contains("printer_vendor") && !orcaslicer_json["printer_vendor"].is_null()) {
    profile_data["vendor"] = orcaslicer_json["printer_vendor"];
}
if (orcaslicer_json.contains("inherits") && !orcaslicer_json["inherits"].is_null()) {
    profile_data["inherits"] = orcaslicer_json["inherits"];
}

// Логируем для отладки
BOOST_LOG_TRIVIAL(info) << "FilamentHub: [PRINTER EXPORT] " 
                       << "name='" << preset.name << "'"
                       << ", printer_model=" << (orcaslicer_json.contains("printer_model") ? orcaslicer_json["printer_model"].dump() : "null")
                       << ", vendor=" << (orcaslicer_json.contains("printer_vendor") ? orcaslicer_json["printer_vendor"].dump() : "null");
```

### 2. Backend уже имеет логику

**Файл:** `backend/app/api/v1/endpoints/orca_sync.py`  
**Функция:** `_ensure_printer_id()`, строки 99-448

Логика уже реализована:
- ✅ Извлекает `printer_model` из `profile_settings`
- ✅ Извлекает `printer_vendor` из `profile_vendor` или metadata
- ✅ Извлекает из `inherits` если нет прямых полей
- ✅ Сопоставляет с существующими принтерами в БД
- ✅ Создает новый принтер с правильным именем

**Проблема была в том что OrcaSlicer не передавал эти поля!**

---

## 📊 Как работает после исправления

### Пример 1: Voron 2.4 350

**OrcaSlicer отправляет:**
```json
{
  "name": "Voron 2.4 350 0.4 nozzle",
  "printer_model": "Voron 2.4 350",
  "vendor": "Voron",
  "inherits": "Voron/Voron 2.4 350",
  ...
}
```

**Backend:**
1. Ищет принтер по `printer_model = "Voron 2.4 350"` → находит!
2. Возвращает `printer_id` существующего принтера
3. Создает профиль принтера с правильным `printer_id`

**Результат:** ✅ Профиль привязан к "Voron 2.4 350"

### Пример 2: Пользовательский принтер

**OrcaSlicer отправляет:**
```json
{
  "name": "My Custom Printer 0.4 nozzle",
  "printer_model": null,
  "vendor": null,
  "inherits": null,
  ...
}
```

**Backend:**
1. Ищет по имени "My Custom Printer" → не находит
2. Создает новый принтер:
   - `manufacturer = "Custom"` (fallback)
   - `model = "My Custom Printer"` (из очищенного имени)
   - `name = "Custom My Custom Printer"` или просто `"My Custom Printer"`

**Результат:** ✅ Создан принтер "My Custom Printer"

---

## 🧪 Тестирование

### Тест 1: Стандартный принтер

```bash
# 1. В OrcaSlicer есть профиль "Voron 2.4 350 0.4 nozzle"
# 2. Экспортировать в FilamentHub
# 3. Проверить в БД:
SELECT pp.name, p.name as printer_name, p.manufacturer, p.model
FROM printer_profiles pp
JOIN printers p ON pp.printer_id = p.id
WHERE pp.name LIKE '%Voron%';

# Ожидается:
# pp.name = "Voron 2.4 350 0.4 nozzle"
# p.name = "Voron 2.4 350"
# p.manufacturer = "Voron"
# p.model = "2.4 350"
```

### Тест 2: Пользовательский принтер

```bash
# 1. В OrcaSlicer создать свой профиль "My Awesome Printer 0.6 nozzle"
# 2. Экспортировать в FilamentHub
# 3. Проверить в БД:
SELECT pp.name, p.name as printer_name, p.manufacturer, p.model
FROM printer_profiles pp
JOIN printers p ON pp.printer_id = p.id
WHERE pp.name LIKE '%Awesome%';

# Ожидается:
# pp.name = "My Awesome Printer 0.6 nozzle"
# p.name = "My Awesome Printer"
# p.manufacturer = "Custom"
# p.model = "My Awesome Printer"
```

---

## ⚠️ Известные ограничения

1. **Пользовательские принтеры без metadata:**  
   Если пользователь создал принтер с нуля, у него нет `printer_model` и `vendor`.  
   Backend создаст новый принтер с `manufacturer="Custom"`.

2. **Дубликаты принтеров:**  
   Если пользователь создал свой профиль для стандартного принтера, но не указал `inherits`,  
   может создаться дубликат.

3. **Сопоставление не 100%:**  
   Логика сопоставления хорошая, но не идеальная. Возможны случаи когда принтер не найден.

---

## 🔄 Синхронизация обратно в OrcaSlicer

**Статус:** ❌ Пока отключено (как попросил пользователь)

**Почему:**
- Нужно избежать проблем с перезаписью настроек пользователя
- Профили принтеров могут иметь специфичные настройки для конкретной машины
- Риск испортить рабочую конфигурацию

**Когда включать:**
- После тщательного тестирования импорта
- Добавить флаг `sync_enabled` для профилей принтеров (как у филаментов)
- Пользователь сам решает какие профили синхронизировать

---

## 📝 Changelog

### 2025-11-23

**OrcaSlicer:**
- ✅ Добавлено извлечение `printer_model`, `printer_vendor`, `inherits` в `export_printer_profiles_to_filamenthub_internal()`
- ✅ Добавлено логирование для отладки

**Backend:**
- ✅ Логика `_ensure_printer_id()` уже была реализована
- ⏳ TODO: Добавить `sync_enabled` для профилей принтеров (как у филаментов)

**Тестирование:**
- ⏳ Протестировать импорт стандартных принтеров
- ⏳ Протестировать импорт пользовательских принтеров
- ⏳ Проверить сопоставление с существующими принтерами в БД


