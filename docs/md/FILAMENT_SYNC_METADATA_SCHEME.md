# Схема метаданных для синхронизации пресетов филаментов

## Проблема совместимости с BambuLab

BambuLab синхронизация использует:
- `setting_id` - их формат (не "FHUB...")
- `filament_id` - их формат
- `user_id`, `base_id`, `sync_info`, `updated_time`

**Наш формат `setting_id = "FHUB{preset.id}"` может конфликтовать**, если BambuLab валидирует формат.

## Решение: Использовать кастомные поля в JSON профиле

### Безопасный подход:

1. **Для "наших" пресетов** (экспортированных с сайта):
   - Добавить `fhub_id` и `fhub_source` в корень JSON профиля
   - Использовать префикс в названии `[FilamentHub]` (fallback)
   - OrcaSlicer и BambuLab игнорируют неизвестные поля

2. **Для черновиков** (импортированных из OrcaSlicer):
   - Добавить `fhub_draft_id` в корень JSON профиля
   - При повторной синхронизации искать по `fhub_draft_id`
   - Предотвращает создание дубликатов

3. **При активации черновика**:
   - Экспортировать обратно в OrcaSlicer с `fhub_id` и префиксом `[FilamentHub]`
   - Убрать `fhub_draft_id`, добавить `fhub_id` и `fhub_source`

## Поля JSON профиля OrcaSlicer

### Стандартные поля (OrcaSlicer):
- `version`, `type`, `name`, `from`, `inherits`
- `filament_settings_id`, `setting_id`, `filament_id`

### Поля BambuLab:
- `user_id`, `base_id`, `sync_info`, `updated_time`
- (хранятся в `.info` файле, но могут быть в JSON)

### Наши поля (безопасные):
- `fhub_id` - ID пресета в FilamentHub
- `fhub_source` - метка источника ("filamenthub")
- `fhub_draft_id` - ID черновика (для предотвращения дубликатов)

**OrcaSlicer игнорирует неизвестные поля** в JSON профиля, поэтому наши метки безопасны.

## Реализация

### 1. При экспорте из FilamentHub в OrcaSlicer:

```python
# В orcaslicer_exporter.py
profile["fhub_id"] = preset.id  # Наш ID в корне JSON
profile["fhub_source"] = "filamenthub"  # Метка источника

# Если это активированный черновик - убираем draft метку
if preset.orcaslicer_settings:
    preset.orcaslicer_settings.pop("fhub_draft_id", None)
```

### 2. При импорте из OrcaSlicer в FilamentHub:

```python
# В orca_sync.py
orcaslicer_settings = payload.orcaslicer_settings or {}

# Проверяем наши метки
fhub_id = orcaslicer_settings.get("fhub_id")
fhub_source = orcaslicer_settings.get("fhub_source")
fhub_draft_id = orcaslicer_settings.get("fhub_draft_id")

# Определяем тип пресета
if fhub_id and fhub_source == "filamenthub":
    # Это наш пресет, ищем по fhub_id
    is_our_preset = True
elif fhub_draft_id:
    # Это черновик, ищем по fhub_draft_id
    preset = await db.execute(
        select(Preset).where(
            Preset.orcaslicer_settings.contains({"fhub_draft_id": fhub_draft_id}),
            Preset.user_id == current_user.id,
        )
    ).scalar_one_or_none()
    if preset:
        # Обновляем существующий черновик
        ...
else:
    # Новый пресет, создаём черновик с меткой
    fhub_draft_id = f"draft_{current_user.id}_{payload.external_id}"
    preset.orcaslicer_settings = preset.orcaslicer_settings or {}
    preset.orcaslicer_settings["fhub_draft_id"] = fhub_draft_id
```

### 3. При активации черновика:

```python
# Когда пользователь активирует черновик и включает синхронизацию
preset.active = True
preset.sync_enabled = True

# Убираем метку черновика, добавляем метку "нашего" пресета
if preset.orcaslicer_settings:
    preset.orcaslicer_settings.pop("fhub_draft_id", None)
    preset.orcaslicer_settings["fhub_id"] = preset.id
    preset.orcaslicer_settings["fhub_source"] = "filamenthub"
```

## Проверка на конфликты

### ✅ Безопасно:
- OrcaSlicer игнорирует неизвестные поля в JSON профиля
- BambuLab проверяет только свои поля (`setting_id` их формата)
- Наши метки `fhub_*` не используются OrcaSlicer или BambuLab

### ⚠️ Потенциальные проблемы:
- Если BambuLab валидирует весь JSON и отклоняет неизвестные поля
- **Решение**: Использовать префикс в названии как fallback

### ✅ Fallback механизм:
1. Сначала ищем по `fhub_id` из `orcaslicer_settings`
2. Если нет - ищем по префиксу `[FilamentHub]` в названии
3. Если нет - создаём черновик с `fhub_draft_id`

## Итоговая схема

### Для "наших" пресетов (экспортированных):
```
JSON профиль:
{
  "name": "PLA 210°C",
  "setting_id": "FHUB000123",
  "fhub_id": 123,              // ← Наша метка
  "fhub_source": "filamenthub", // ← Наша метка
  ...
}
```

### Для черновиков (импортированных):
```
JSON профиль:
{
  "name": "ABS-5",
  "setting_id": "user_12345",
  "fhub_draft_id": "draft_6_user_12345", // ← Наша метка
  ...
}
```

### При активации черновика:
```
JSON профиль после активации:
{
  "name": "ABS-5 [FilamentHub]",
  "setting_id": "FHUB000124",
  "fhub_id": 124,              // ← Добавили метку
  "fhub_source": "filamenthub", // ← Добавили метку
  // fhub_draft_id удалён
  ...
}
```

---

**Вывод:** Использование полей `fhub_*` в корне JSON профиля безопасно и не конфликтует с BambuLab синхронизацией.

