# Извлечение метаданных из JSON файла пресета в OrcaSlicer

## Проблема

При экспорте пресетов из OrcaSlicer в FilamentHub метки `fhub_id`, `fhub_source`, `fhub_draft_id` теряются, потому что:

1. `get_config_json(preset.config)` извлекает только поля из `preset.config`
2. `preset.config` содержит только известные конфигурационные опции
3. Неизвестные поля (`fhub_id`, `fhub_source`) не сохраняются в `preset.config` при импорте
4. При экспорте метки теряются → создаются дубликаты → синхронизация по 100 раз

## Решение

**Изменения только в FilamentHubPanel** - читать JSON файл пресета напрямую и извлекать метки оттуда.

**Важно:** Не трогаем основную логику OrcaSlicer, все изменения изолированы в нашем модуле.

### Изменения в `FilamentHubPanel.cpp`

**Только для filament presets** - в функции `export_filament_presets_to_filamenthub_internal()`:

```cpp
// После получения orcaslicer_json из get_config_json(preset.config)
nlohmann::json orcaslicer_json = get_config_json(preset.config);

// Читаем оригинальный JSON файл для извлечения метаданных
if (!preset.file.empty() && boost::filesystem::exists(preset.file)) {
    try {
        nlohmann::json original_json;
        boost::nowide::ifstream ifs(preset.file);
        ifs >> original_json;
        ifs.close();
        
        // Извлекаем метки FilamentHub из оригинального JSON
        if (original_json.contains("fhub_id")) {
            orcaslicer_json["fhub_id"] = original_json["fhub_id"];
        }
        if (original_json.contains("fhub_source")) {
            orcaslicer_json["fhub_source"] = original_json["fhub_source"];
        }
        if (original_json.contains("fhub_draft_id")) {
            orcaslicer_json["fhub_draft_id"] = original_json["fhub_draft_id"];
        }
        
        BOOST_LOG_TRIVIAL(debug) << "FilamentHub: Extracted metadata from JSON file: "
                                 << "fhub_id=" << (original_json.contains("fhub_id") ? std::to_string(original_json["fhub_id"].get<int>()) : "none")
                                 << ", fhub_source=" << (original_json.contains("fhub_source") ? original_json["fhub_source"].get<std::string>() : "none")
                                 << ", fhub_draft_id=" << (original_json.contains("fhub_draft_id") ? original_json["fhub_draft_id"].get<std::string>() : "none");
    } catch (const std::exception& e) {
        BOOST_LOG_TRIVIAL(warning) << "FilamentHub: Failed to read original JSON file for metadata: " << e.what();
    }
}
```

### Где изменить

**Файл:** `docs/OrcaSlicer/src/slic3r/GUI/FilamentHubPanel.cpp`

**Функция:** `export_filament_presets_to_filamenthub_internal()`

**Строка:** ~4596 (после `nlohmann::json orcaslicer_json = get_config_json(preset.config);`)

**Важно:** 
- Изменение **только в FilamentHubPanel**, не трогаем основную логику OrcaSlicer
- Изменение **только для filament presets** (printer и print profiles используют другой механизм маппинга)

### Альтернативное решение (если файл недоступен)

Если `preset.file` пустой или файл недоступен, можно использовать маппинг из AppConfig (как сейчас делается с `fhub_id`), но это менее надёжно. В этом случае метки будут теряться, но это не критично - пресет найдётся по имени или создастся как новый черновик.

### Проверка

После изменений:
1. Импортируем пресет с метками из FilamentHub
2. Экспортируем его обратно
3. Проверяем, что метки сохранились в `orcaslicer_settings`

---

**Вывод:** Да, нужно пересобрать OrcaSlicer с этими изменениями, чтобы метки сохранялись при экспорте.

