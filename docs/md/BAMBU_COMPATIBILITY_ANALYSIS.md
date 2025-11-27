# Анализ совместимости с BambuLab синхронизацией

## Как работает BambuLab синхронизация

### Поля, которые использует BambuLab:
1. **`setting_id`** - уникальный ID в облаке BambuLab (их формат)
2. **`filament_id`** - ID филамента в облаке
3. **`user_id`** - ID пользователя BambuLab
4. **`base_id`** - базовый ID пресета
5. **`sync_info`** - статус синхронизации ("create", "update", "delete", "")
6. **`updated_time`** - timestamp последнего обновления

### Где хранятся эти поля:
- В `.info` файле профиля (INI формат)
- В JSON профиле (для некоторых полей)

### Процесс синхронизации BambuLab:
1. OrcaSlicer проверяет `preset.setting_id` (читается из `.info` файла)
2. Если `setting_id` пустой и `sync_info == "create"` → создаёт новый пресет в облаке
3. Если `setting_id` есть и `sync_info == "update"` → обновляет пресет в облаке
4. BambuLab API возвращает `setting_id` после создания/обновления

## Как мы используем эти поля

### Текущая реализация:
```python
# В orcaslicer_exporter.py
profile["setting_id"] = f"FHUB{preset.id:06d}"  # Наш формат с префиксом "FHUB"
profile["filament_id"] = f"FHUB{filament.id:06d}"  # Наш формат
```

### Проблема:
- BambuLab может проверять формат `setting_id` перед синхронизацией
- Если формат не соответствует их ожиданиям, они могут игнорировать пресет
- НО: если формат другой (наш "FHUB..."), они должны просто игнорировать наш пресет, не ломая свою синхронизацию

## Решение: Использовать кастомные поля в `orcaslicer_settings`

### Безопасный подход:
1. **Для "наших" пресетов** (экспортированных с сайта):
   - Добавить поле `fhub_id` в `orcaslicer_settings` (не в корень JSON!)
   - ИЛИ использовать префикс в названии `[FilamentHub]` (уже используется)
   - При импорте искать `fhub_id` в `orcaslicer_settings` или префикс в названии

2. **Для черновиков** (импортированных из OrcaSlicer):
   - При создании черновика добавить `fhub_draft_id` в `orcaslicer_settings`
   - При повторной синхронизации искать по `fhub_draft_id`
   - Это предотвратит создание дубликатов

### Почему это безопасно:
- `orcaslicer_settings` - это наше поле в FilamentHub
- BambuLab не знает о наших полях в `orcaslicer_settings`
- OrcaSlicer просто игнорирует неизвестные поля в JSON профиля
- Наши метки не попадут в `.info` файл (там только стандартные поля)

## План реализации

### 1. При экспорте из FilamentHub в OrcaSlicer:
```python
# В orcaslicer_exporter.py
if preset.orcaslicer_settings is None:
    preset.orcaslicer_settings = {}
preset.orcaslicer_settings["fhub_id"] = preset.id
preset.orcaslicer_settings["fhub_source"] = "filamenthub"  # Метка что это наш пресет
```

### 2. При импорте из OrcaSlicer в FilamentHub:
```python
# В orca_sync.py
orcaslicer_settings = payload.orcaslicer_settings or {}
fhub_id = orcaslicer_settings.get("fhub_id")
fhub_source = orcaslicer_settings.get("fhub_source")

if fhub_id and fhub_source == "filamenthub":
    # Это наш пресет, ищем по fhub_id
    preset = await db.get(Preset, fhub_id)
elif fhub_draft_id := orcaslicer_settings.get("fhub_draft_id"):
    # Это черновик, ищем по fhub_draft_id
    preset = await db.execute(
        select(Preset).where(
            Preset.orcaslicer_settings.contains({"fhub_draft_id": fhub_draft_id}),
            Preset.user_id == current_user.id,
        )
    ).scalar_one_or_none()
else:
    # Новый пресет, создаём черновик
    # Сохраняем fhub_draft_id для предотвращения дубликатов
```

### 3. Для черновиков при импорте:
```python
# При создании черновика
preset.orcaslicer_settings = preset.orcaslicer_settings or {}
preset.orcaslicer_settings["fhub_draft_id"] = f"draft_{current_user.id}_{payload.external_id}"
```

### 4. При активации черновика:
```python
# Когда пользователь активирует черновик и включает синхронизацию
# Экспортируем его обратно в OrcaSlicer с правильным названием
# Убираем fhub_draft_id, добавляем fhub_id и fhub_source
preset.orcaslicer_settings.pop("fhub_draft_id", None)
preset.orcaslicer_settings["fhub_id"] = preset.id
preset.orcaslicer_settings["fhub_source"] = "filamenthub"
```

## Проверка на конфликты

### Что нужно проверить:
1. ✅ BambuLab не читает `orcaslicer_settings` - это наше поле
2. ✅ BambuLab не использует `fhub_*` поля - это наши метки
3. ✅ OrcaSlicer игнорирует неизвестные поля в JSON профиля
4. ✅ `.info` файл не содержит `orcaslicer_settings` - там только стандартные поля

### Риски:
- **Низкий риск**: BambuLab может валидировать JSON профиль и отклонять неизвестные поля
- **Решение**: Использовать префикс в названии как fallback
- **Дополнительно**: Добавить проверку формата `setting_id` при импорте

## Итоговая схема

### Для "наших" пресетов (экспортированных):
- В JSON профиле: `orcaslicer_settings.fhub_id` и `orcaslicer_settings.fhub_source`
- В названии: постфикс `[FilamentHub]` (добавляется в C++)
- При импорте: ищем по `fhub_id` из `orcaslicer_settings` или по префиксу в названии

### Для черновиков (импортированных):
- В JSON профиле: `orcaslicer_settings.fhub_draft_id`
- В названии: без префикса `[FilamentHub]`
- При импорте: ищем по `fhub_draft_id` для предотвращения дубликатов
- При активации: экспортируем обратно с `fhub_id` и префиксом `[FilamentHub]`

---

**Вывод:** Использование кастомных полей в `orcaslicer_settings` безопасно и не конфликтует с BambuLab синхронизацией.

