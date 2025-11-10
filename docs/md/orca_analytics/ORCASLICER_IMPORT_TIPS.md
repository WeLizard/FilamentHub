# OrcaSlicer Import Tips for Cursor Agent

## Быстрый запуск
- Активируй backend venv: `cd backend && .\.venv\Scripts\activate` (на Windows) или `source backend/.venv/bin/activate` (Linux/Mac).
- Прогони импорт: `python ../scripts/import_orca_presets_db.py`.
- Скрипт использует `Settings.ORCA_SYSTEM_PRESETS_PATH` (`docs/orca_bundles/system_presets`), база берётся из `.env` в `backend/`.

## Перед запуском
- Убедись, что PostgreSQL доступна и что переменные `DATABASE_URL` и `SECRET_KEY` заданы в `backend/.env`.
- Если импорт идёт в тестовую БД — можно запускать повторно: скрипт обновляет и дополняет записи.
- Предупреждения `Printer model 'None' not found for machine preset 'fdm_*_common'` нормальны: эти пресеты служебные и не имеют отдельного `machine_model`.

## После импорта
- Итоговый отчёт (`{'vendors': …, 'printers': …}`) выводится в консоль — зафиксируй его в задачах/комментариях.
- Новые данные попадают в таблицы `printers`, `printer_profiles`, `print_profiles`; связи совместимости заполнить отдельным этапом.

## Команды git перед пушем
1. `git status` — проверить список изменений.
2. `git add <files>` — добавить обновлённые модели, миграции, скрипты и каталоги `docs/imgs`, `docs/orca_bundles`.
3. `git commit -m "Add Orca preset importer and data dumps"` — сделать коммит.
4. `git push origin <branch>` — пушить после подтверждения у владельца.

