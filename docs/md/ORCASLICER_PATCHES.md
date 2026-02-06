не# Патч-файлы для исправления синхронизации OrcaSlicer ↔ FilamentHub

## ✅ Статус: Все патчи применены

Все патчи были успешно применены к файлам OrcaSlicer в форке `filamenthub-integration`.

**Дата применения:** 2025-11-23

---

## Применённые патчи

### ✅ Патч 1: Фильтрация экспорта пресетов (только синхронизированные)

**Файл:** `src/slic3r/GUI/FilamentHubPanel.cpp`

**Строка:** 4683-4691

**Описание:** 
Экспортируются только пресеты с `fhub_id` (синхронизированные с FilamentHub). Это предотвращает экспорт всех пользовательских пресетов.

**Код:**
```cpp
// Пропускаем пресеты без маппинга (не синхронизированные)
// ВАЖНО: Экспортируем только пресеты, которые имеют fhub_id (синхронизированы с FilamentHub)
// Это предотвращает экспорт всех пользовательских пресетов
if (!preset_data.contains("fhub_id")) {
    BOOST_LOG_TRIVIAL(debug) << "FilamentHub: Skipping preset " << preset.name
                            << " (external_id=" << preset.setting_id
                            << ") - no mapping found, not synced with FilamentHub";
    continue; // Пропускаем этот пресет
}
```

---

### ✅ Патч 2: Метод `download_profile_info` в FilamentHubClient

**Файлы:**
- `src/slic3r/Utils/FilamentHubClient.hpp` (объявление метода)
- `src/slic3r/Utils/FilamentHubClient.cpp` (реализация метода)

**Описание:**
Добавлен метод для скачивания .info файлов из FilamentHub API. Используется для сохранения метаданных после импорта.

**Код в .hpp:**
```cpp
/**
 * \brief Download preset .info file in INI format
 * 
 * Downloads a preset .info file from FilamentHub API in OrcaSlicer-compatible INI format.
 * This is used to preserve FilamentHub metadata (user_id, setting_id, updated_time) after import.
 * 
 * \param preset_id Preset ID in FilamentHub
 * \param access_token JWT access token
 * \param on_complete Called when download succeeds. Parameters: (info_content, http_status)
 * \param on_error Called when download fails. Parameters: (response_body, error_message, http_status)
 */
void download_profile_info(
    int preset_id,
    const std::string& access_token,
    std::function<void(std::string /* info_content */, unsigned /* http_status */)> on_complete,
    std::function<void(std::string /* body */, std::string /* error */, unsigned /* http_status */)> on_error
) const;
```

**Код в .cpp:**
```cpp
void FilamentHubClient::download_profile_info(
    int preset_id,
    const std::string& access_token,
    std::function<void(std::string, unsigned)> on_complete,
    std::function<void(std::string, std::string, unsigned)> on_error
) const
{
    try {
        std::string url = s_api_base_url + "/api/v1/presets/" + std::to_string(preset_id) + "/export/orcaslicer.info";
        
        // ВАЖНО: Выполняем HTTP запрос в отдельном потоке, чтобы не блокировать текущий поток
        std::thread([url, access_token, on_complete, on_error]() {
            try {
                BOOST_LOG_TRIVIAL(debug) << "FilamentHub: Starting HTTP request for .info file: " << url;
                
                Http::get(url)
                    .header("Content-Type", "text/plain")
                    .header("Accept", "text/plain")
                    .header("Authorization", "Bearer " + access_token)
                    .timeout_connect(10)
                    .timeout_max(30)
                    .on_complete([on_complete](std::string body, unsigned status) {
                        BOOST_LOG_TRIVIAL(info) << "FilamentHub: .info file download successful. Status: " << status;
                        on_complete(body, status);
                    })
                    .on_error([on_error](std::string body, std::string error, unsigned status) {
                        BOOST_LOG_TRIVIAL(error) << "FilamentHub: .info file download failed. Error: " << error << ", Status: " << status;
                        on_error(body, error, status);
                    })
                    .perform_sync();
                    
                BOOST_LOG_TRIVIAL(debug) << "FilamentHub: HTTP request completed for .info file";
            } catch (const std::exception& e) {
                BOOST_LOG_TRIVIAL(error) << "FilamentHub: Exception in download_profile_info thread: " << e.what();
                on_error("", std::string("Exception: ") + e.what(), 0);
            }
        }).detach(); // Отсоединяем поток, чтобы он завершился самостоятельно
    } catch (const std::exception& e) {
        BOOST_LOG_TRIVIAL(error) << "FilamentHub: Exception in download_profile_info: " << e.what();
        on_error("", std::string("Exception: ") + e.what(), 0);
    }
}
```

---

### ✅ Патч 3: Метод `update_preset_info_file` в FilamentHubPanel

**Файлы:**
- `src/slic3r/GUI/FilamentHubPanel.hpp` (объявление метода)
- `src/slic3r/GUI/FilamentHubPanel.cpp` (реализация метода)

**Описание:**
После импорта пресета через `import_json_presets()` OrcaSlicer создаёт .info файл с пустыми значениями. Этот метод скачивает правильный .info файл из FilamentHub API и обновляет файл пресета.

**Код в .hpp:**
```cpp
/**
 * \brief Update preset .info file with FilamentHub metadata
 * 
 * After importing a preset via import_json_presets(), OrcaSlicer creates a .info file with empty values.
 * This method downloads the correct .info file from FilamentHub API and updates the preset file.
 * 
 * IMPORTANT: We don't use fields sync_info, user_id, setting_id, base_id, updated_time from Preset object,
 * as they may be overwritten by BambuLab system. Instead, we download the .info file from API.
 * 
 * \param preset_id Preset ID in FilamentHub
 * \param preset_name Preset name in OrcaSlicer (with [FilamentHub] postfix)
 * \param access_token JWT token for API access
 */
void update_preset_info_file(int preset_id, const std::string& preset_name, const std::string& access_token);
```

**Код в .cpp:**
См. файл `src/slic3r/GUI/FilamentHubPanel.cpp`, метод `update_preset_info_file()` (после метода `import_preset_silent`).

---

### ✅ Патч 3.3: Вызов `update_preset_info_file` после импорта

**Файл:** `src/slic3r/GUI/FilamentHubPanel.cpp`

**Строки:** 
- После строки 2391 (в методе `import_preset_silent`)
- После строки 2705 (в методе `import_preset_silent_with_callback`)

**Описание:**
Вызов метода `update_preset_info_file` после успешного импорта пресета для обновления .info файла с метаданными FilamentHub.

**Код:**
```cpp
// Обновляем .info файл с метаданными FilamentHub
// ВАЖНО: Это нужно делать ПОСЛЕ импорта, так как import_json_presets() создаёт .info файл с пустыми значениями
// Мы скачиваем правильный .info файл из API и обновляем файл пресета
BOOST_LOG_TRIVIAL(debug) << "FilamentHub: [IMPORT STEP 11.10] Updating .info file with FilamentHub metadata...";
update_preset_info_file(preset_id, actual_preset_name, access_token);
```

---

### ✅ Патч 4: Защита от бесконечного цикла экспорта

**Файл:** `src/slic3r/GUI/FilamentHubPanel.cpp`

**Описание:**
Проверка флага `m_is_syncing` перед экспортом и правильный сброс флага во всех случаях (успех, ошибка, таймаут).

**Статус:** Уже реализовано в коде. Флаг проверяется в начале метода `export_filament_presets_to_filamenthub` и сбрасывается во всех callback'ах (on_complete, on_error).

---

## Следующие шаги

1. ✅ Все патчи применены
2. ⏳ **Пересобрать OrcaSlicer** (выполнишь сам)
3. ⏳ Протестировать синхронизацию

---

## Тестирование

После пересборки OrcaSlicer нужно протестировать:

1. **Экспорт пресетов:**
   - ✅ Проверить, что экспортируются только пресеты с `fhub_id`
   - ✅ Проверить, что сообщение об экспорте не повторяется бесконечно

2. **Импорт пресетов:**
   - ✅ Проверить, что .info файлы обновляются с правильными метаданными
   - ✅ Проверить, что `user_id`, `setting_id`, `updated_time` заполнены

3. **Дубликаты филаментов:**
   - ✅ Проверить, что не создаются дубликаты при импорте
   - ✅ Проверить, что существующие филаменты находятся правильно

---

## Примечания

- Все патчи применены к файлам в `docs/OrcaSlicer/`
- Код готов к компиляции
- После пересборки OrcaSlicer синхронизация должна работать корректно

