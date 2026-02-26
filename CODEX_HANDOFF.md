# Codex Handoff

Обновлено: 2026-02-26

## Что уже сделано

1. Frontend/Auth
- Убран guest-probe `GET /api/v1/auth/me` без токена.
- Проверка maintenance переведена на публичный `/health`.

2. Backend `/health`
- В ответ добавлены поля:
  - `maintenance_mode`
  - `maintenance_message`

3. OrcaSlicer submodule
- В `submodule/OrcaSlicer` есть коммит:
  - `dec17f7a46` — `fix(sync): make m_full_sync_attempted atomic and use load/store`
- Это отдельный коммит поверх `8bdbb61270`.

4. Downloads (backend)
- Парсер имён дистрибутивов поддерживает `-setup`:
  - `OrcaSlicer-FilamentHub-<ver>-win64-setup.exe`
- Добавлен кэш SHA256 (по path+size+mtime), чтобы `/api/v1/downloads/orcaslicer` не тормозил на каждом запросе.

## Текущее состояние (важно)

1. Основной репозиторий (`F:/FilamentHub`)
- Указатель сабмодуля в индексе ещё на `8bdbb61270`.
- Рабочее дерево сабмодуля на `dec17f7a46`.

2. Submodule (`F:/FilamentHub/submodule/OrcaSlicer`)
- Ветка `filamenthub-integration` ahead of origin на 1 commit (`dec17f7a46`).
- Есть другие незакоммиченные локальные изменения (не трогались в этом хэндовере).

3. Дистрибутивы для сайта
- Файлы лежат в `backend/distributions/orcaslicer`:
  - `OrcaSlicer-FilamentHub-2.1.0-fh-win64-setup.exe`
  - `OrcaSlicer-FilamentHub-2.1.0-fh-win64-portable.zip`

## Что нужно сделать следующим шагом

1. Push субмодуля `filamenthub-integration` (чтобы `dec17f7a46` был на remote).
2. В основном репо закоммитить обновлённый указатель `submodule/OrcaSlicer`.
3. Закоммитить backend-фикс `backend/app/api/v1/endpoints/downloads.py`.
4. Push `main`.

## Ограничения/заметки

- В корне есть другие пользовательские изменения (`frontend/*`, `docs/*`, `.claude/*` и т.д.) — их не включать в технические коммиты, если это не согласовано отдельно.
- Использовать точечный `git add <file>`, без `git add .`.
