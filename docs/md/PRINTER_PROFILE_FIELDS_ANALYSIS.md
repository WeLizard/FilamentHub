# Анализ: Все ли поля из OrcaSlicer сохраняются в профилях принтеров?

## Краткий ответ: ⚠️ Частично

### ✅ При импорте (из OrcaSlicer → FilamentHub)

**Статус:** ✅ **ДА, все поля сохраняются**

**Как это работает:**
1. OrcaSlicer отправляет полный JSON профиля в поле `orcaslicer_settings`
2. Backend сохраняет весь `orcaslicer_settings` как есть в БД (JSON поле)
3. Дополнительно извлекаются часто используемые поля в отдельные колонки

**Код:**
```python
# backend/app/api/v1/endpoints/orca_sync.py, строка 680-694
if payload.orcaslicer_settings:
    updated_settings = dict(payload.orcaslicer_settings)
    # ... сохранение меток FilamentHub ...
    profile.orcaslicer_settings = updated_settings  # ✅ ВСЕ поля сохраняются
```

**Вывод:** При импорте ВСЕ поля из OrcaSlicer сохраняются в `orcaslicer_settings`.

---

### ❌ При экспорте (из FilamentHub → OrcaSlicer)

**Статус:** ⚠️ **ПРОБЛЕМА: Не все поля сохраняются**

**Как это работает:**

1. **В OrcaSlicer C++ коде** (`FilamentHubPanel.cpp`, строка 5063):
   ```cpp
   nlohmann::json orcaslicer_json = get_config_json(preset.config);
   ```
   - `get_config_json()` извлекает только известные опции из `preset.config`
   - `preset.config` содержит только поля, которые OrcaSlicer знает и использует
   - **Кастомные поля (например, `fhub_*`) НЕ сохраняются в `preset.config`**

2. **Решение для метаданных FilamentHub** (строки 5068-5087):
   - Читается оригинальный JSON файл
   - Извлекаются только метаданные (`fhub_id`, `fhub_source`)
   - **Но остальные поля из оригинального JSON файла НЕ извлекаются**

3. **Проблема:**
   - Если в оригинальном JSON файле были поля, которых нет в `preset.config`, они **теряются**
   - Например: поля из Machine Limits, сетевые настройки Print Host, кастомные поля пользователя

**Код:**
```cpp
// FilamentHubPanel.cpp, строка 5063
nlohmann::json orcaslicer_json = get_config_json(preset.config); // ❌ Только известные опции

// Читаем оригинальный JSON только для метаданных FilamentHub
if (!preset.file.empty() && boost::filesystem::exists(preset.file)) {
    original_json >> ifs;
    // Извлекаем только fhub_id и fhub_source
    if (original_json.contains("fhub_id")) {
        orcaslicer_json["fhub_id"] = original_json["fhub_id"];
    }
    // ❌ Остальные поля из original_json НЕ копируются в orcaslicer_json
}
```

**Вывод:** При экспорте из OrcaSlicer теряются поля, которых нет в `preset.config`.

---

## Сравнение с Filament Presets

### ✅ Filament Presets (правильно)

**Статус:** ✅ **Проблема такая же, но для filament presets это менее критично**

**Код:** `FilamentHubPanel.cpp`, строки 4596-4639
- Также используется `get_config_json(preset.config)`
- Также читается оригинальный JSON только для метаданных
- Но для filament presets большинство полей находится в `preset.config`, поэтому потери минимальны

---

## Что нужно исправить

### Вариант 1: Читать весь оригинальный JSON файл (рекомендуется)

**Для Printer Profiles:**

```cpp
// Вместо:
nlohmann::json orcaslicer_json = get_config_json(preset.config);

// Делать:
nlohmann::json orcaslicer_json;

// Читаем весь оригинальный JSON файл
if (!preset.file.empty() && boost::filesystem::exists(preset.file)) {
    boost::filesystem::ifstream ifs(preset.file);
    ifs >> orcaslicer_json;
    ifs.close();
} else {
    // Fallback: используем get_config_json если файла нет
    orcaslicer_json = get_config_json(preset.config);
}

// Затем обновляем только измененные пользователем поля из preset.config
// (это нужно для того, чтобы отражены были изменения пользователя)
```

**Преимущества:**
- ✅ Сохраняются ВСЕ поля из оригинального JSON
- ✅ Не теряются кастомные поля
- ✅ Не теряются поля, которые OrcaSlicer не знает

**Недостатки:**
- ⚠️ Нужно обновлять поля из `preset.config` если пользователь их изменил
- ⚠️ Сложнее логика (нормализация формата значений)

### Вариант 2: Сохранять весь оригинальный JSON в FilamentHub

**В Backend:**
- При импорте сохранять весь оригинальный JSON в `orcaslicer_settings`
- При экспорте использовать сохраненный JSON, а не генерировать из `preset.config`

**Преимущества:**
- ✅ Гарантированно сохраняются все поля
- ✅ Проще логика в OrcaSlicer

**Недостатки:**
- ⚠️ Может быть рассинхронизация, если пользователь изменил профиль в OrcaSlicer

---

## Рекомендация

**Использовать Вариант 1** для Printer Profiles и Print Profiles:
1. Читать весь оригинальный JSON файл
2. Обновлять поля из `preset.config` если они были изменены
3. Отправлять полный JSON в FilamentHub

**Почему:**
- ✅ Гарантирует сохранение всех полей
- ✅ Сохраняет изменения пользователя
- ✅ Совместимо с текущей архитектурой

---

## Проверка наличия полей

### Поля, которые ТОЧНО сохраняются:
- ✅ Все поля из `s_Preset_printer_options` (если они есть в `preset.config`)
- ✅ `fhub_id`, `fhub_source` (читаются из оригинального JSON)

### Поля, которые МОГУТ ТЕРЯТЬСЯ:
- ⚠️ Поля из Machine Limits (если они не в `preset.config`)
- ⚠️ Сетевые настройки Print Host (если не используются)
- ⚠️ Кастомные поля пользователя
- ⚠️ Поля, которые OrcaSlicer не использует активно

---

## Вывод

**Текущее состояние:**
- ✅ При импорте: **ВСЕ поля сохраняются** в `orcaslicer_settings`
- ❌ При экспорте: **НЕ ВСЕ поля сохраняются** - теряются поля, которых нет в `preset.config`

**Нужно исправить:**
- При экспорте из OrcaSlicer читать весь оригинальный JSON файл, а не только `preset.config`

