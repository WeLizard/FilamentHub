# Анализ сценария синхронизации черновиков без меток

## Сценарий

**Ситуация:**
1. У пользователя в OrcaSlicer есть пресеты `ABS-5`, `ABS-6` БЕЗ меток (`fhub_id`, `fhub_source`, `fhub_draft_id`)
2. В FilamentHub уже есть черновики `ABS-5`, `ABS-6` (созданные ранее при первой синхронизации)
3. Черновики имеют `fhub_draft_id` в `orcaslicer_settings`
4. При следующей синхронизации из OrcaSlicer приходят те же пресеты, но БЕЗ меток

## Что произойдет при синхронизации?

### Текущая логика поиска (приоритеты):

1. **По `fhub_id` из payload** - не сработает (нет в payload)
2. **По меткам из `orcaslicer_settings`**:
   - `fhub_id` + `fhub_source` - не сработает (нет меток в JSON)
   - `fhub_draft_id` - не сработает (нет метки в JSON)
3. **По `external_id`** (OrcaSlicer's `preset.setting_id`) ✅ **НОВОЕ**
4. **По `name + filament_id + user_id`** (fallback)
5. **По `name + filament_name + material_type`** (для черновиков) ✅ **НОВОЕ**

### Решение ✅

**Реализовано комбинированный подход:**

#### 1. Поиск по `external_id` (Приоритет 3)
Добавлен поиск по `external_id` (OrcaSlicer's `preset.setting_id`), который стабилен и не меняется:

```python
if preset is None and payload.external_id:
    result = await db.execute(
        select(Preset).where(
            Preset.external_id == payload.external_id,
            Preset.user_id == current_user.id,
        )
    )
    preset = result.scalar_one_or_none()
```

#### 2. Улучшенный поиск черновиков (Приоритет 5)
Добавлен поиск по `name + filament_name + material_type` для черновиков, даже если `filament_id` отличается:

```python
if preset is None and not is_our_preset and payload.filament_name and payload.material_type:
    result = await db.execute(
        select(Preset)
        .join(Filament, Preset.filament_id == Filament.id)
        .where(
            Preset.name == payload.name,
            Filament.name == payload.filament_name,
            Filament.material_type == payload.material_type,
            Filament.brand_id == user_materials_brand_id,
            Preset.user_id == current_user.id,
            Preset.active == False,  # Только черновики
        )
    )
    preset = result.scalar_one_or_none()
```

## Итоговый порядок поиска:

1. **По `fhub_id` из payload** (явное указание)
2. **По меткам из `orcaslicer_settings`**:
   - `fhub_id` + `fhub_source` (для наших пресетов)
   - `fhub_draft_id` (для черновиков)
3. **По `external_id`** (OrcaSlicer's `preset.setting_id`) ✅ **НОВОЕ**
4. **По `name + filament_id + user_id`** (fallback)
5. **По `name + filament_name + material_type`** (для черновиков) ✅ **НОВОЕ**

## Результат

Теперь при синхронизации черновиков без меток:
- ✅ Поиск по `external_id` найдет существующий черновик (если `external_id` был сохранен)
- ✅ Поиск по `name + filament_name + material_type` найдет черновик даже если `filament_id` отличается
- ✅ Логирование на каждом этапе для отслеживания проблем
- ✅ Минимизированы дубликаты черновиков

## Пример работы:

**Первая синхронизация:**
- Создан черновик `Filament(id=100, name="ABS-5", brand_id=user_materials)`
- Создан черновик `Preset(id=200, name="ABS-5", filament_id=100, external_id="abc123", fhub_draft_id="xyz789")`

**Вторая синхронизация (без меток):**
- OrcaSlicer отправляет: `name="ABS-5", external_id="abc123", filament_name="ABS-5", material_type="ABS"`
- Поиск по `external_id="abc123"` → найдет `Preset(id=200)` ✅
- Обновит существующий черновик вместо создания дубликата

**Если `external_id` не совпадает:**
- Поиск по `name="ABS-5" + filament_name="ABS-5" + material_type="ABS"` → найдет черновик ✅
- Обновит существующий черновик

---

**Статус:** ✅ Реализовано. Логика поиска черновиков улучшена для предотвращения дубликатов.
