# OrcaSlicer Profile Export Reference

## Общее
- Профили делятся на два типа: `printer_profiles` (настройки принтера) и `print_profiles` (настройки печати).
- Бэкенд хранит данные в PostgreSQL, сериализует через Pydantic-схемы и отдаёт OrcaSlicer в JSON.
- Поле `orcaslicer_settings` содержит исходный JSON из OrcaSlicer (ключи совпадают с `PresetBundle`); остальные столбцы отвечают за метаданные FilamentHub.

## Профили принтеров (`printer_profiles`)
- `id`: числовой первичный ключ.
- `printer_id`: FK на `printers` (может быть `NULL` для пользовательских профилей).
- `owner_user_id`: владелец профиля (может быть `NULL` для официальных).
- `name`, `slug`: обязательные строковые идентификаторы; `slug` уникален.
- `description`: длинное описание (до 10k символов).
- `is_official`: флаг официального профиля производителя.
- `active`: мягкое удаление/черновики.
- `orcaslicer_settings`: полная структура OrcaSlicer (JSON).
- `start_gcode`, `end_gcode`: G-code вставки (опционально).
- `notes`: дополнительные заметки.
- `created_at`, `updated_at`: таймстемпы (UTC, с автообновлением).

### Payload импорта/экспорта
- `external_id`: ID из OrcaSlicer (для синхронизации).
- `fhub_id`: если обновляем существующую запись.
- `name` / `slug` / `description`.
- `printer_id` или `printer_slug`: связь с сущностью `Printer`; если ни одно ни другое не указано, профиль остаётся отвязанным.
- `active`: опционально; по умолчанию импорт идёт как черновик (`False`).
- `orcaslicer_settings`: JSON от OrcaSlicer (обязателен).
- `start_gcode`, `end_gcode`, `notes`: опционально.

### Минимальный JSON для экспорта
```json
{
  "name": "Voron 2.4 350",
  "slug": "voron-24-350",
  "orcaslicer_settings": { "...": "..." },
  "printer_id": 42,
  "active": true,
  "start_gcode": "M117 Heating...",
  "end_gcode": "M104 S0\nM140 S0",
  "notes": "Custom profile from FilamentHub"
}
```

## Профили печати (`print_profiles`)
- `id`: числовой первичный ключ.
- `owner_user_id`: владелец (может быть `NULL`).
- `name`, `slug`: обязательные значения; `slug` уникален.
- `description`: текстовое поле (до 10k символов).
- `category`: произвольная строка для группировки (например, `speed`, `quality`).
- `is_official`: флаг официальных пресетов.
- `active`: флаг `True/False`.
- `compatible_printers`: JSON-массив ID/slug принтеров.
- `compatible_filaments`: JSON-массив ID/slug филаментов.
- `orcaslicer_settings`: оригинальный JSON профиля печати.
- `notes`: произвольный текст.
- `created_at`, `updated_at`: таймстемпы.

### Payload импорта/экспорта
- `external_id`: ID OrcaSlicer.
- `fhub_id`: обновление существующей записи.
- `name` / `slug` / `description` / `category`.
- `active`: по умолчанию импортируется как `False`.
- `compatible_printers`: массив строк (slug или внутренние ID).
- `compatible_filaments`: массив строк (slug или внутренние ID).
- `orcaslicer_settings`: JSON профиля.
- `notes`: текстовые заметки.

### Минимальный JSON для экспорта
```json
{
  "name": "0.2 Quality",
  "slug": "voron-02-quality",
  "category": "quality",
  "orcaslicer_settings": {
    "layer_height": 0.2,
    "infill_speed": 80
  },
  "compatible_printers": ["voron-24-350"],
  "compatible_filaments": ["pla-pro"],
  "active": true
}
```

## Порядок синхронизации
1. OrcaSlicer делает GET `/api/v1/orcaslicer/printer-profiles?updated_since=...` и `/print-profiles` — получает список актуальных профилей (фильтр по времени обновления).
2. Для импорта из OrcaSlicer вызывается POST `/orcaslicer/printer-profiles/import` или `/print-profiles/import` с массивом вышеописанных payload.
3. Ответ содержит `results[]` со статусом (`created`, `updated`, `skipped`, `error`) и деталями (ID FilamentHub, сообщения).

## Заметки по данным
- `orcaslicer_settings` хранит «как есть» структуру из файлов OrcaSlicer: удобно хранить `inherit`/`compatible_*` поля прямо в JSON.
- `slug` генерируется через сервис `generate_unique_slug`, поэтому при импорте можно не передавать — бэкенд создаст автоматически.
- Для ссылок `compatible_printers` / `compatible_filaments` можно использовать смешанный список: `["123", "voron-24-350"]`; бэкенд попытается сматчить как по ID, так и по slug.

## TODO / вопросы
- Дополнить схему хранения API-ключа OrcaSlicer (сейчас в работе).
- Решить, нужно ли хранить версию пресета (`orcaslicer_settings["version"]`) отдельным столбцом для быстрого диффа.
- Определить стратегию конфликтов: что делать, если OrcaSlicer шлёт slug, который уже занят другим пользователем.


