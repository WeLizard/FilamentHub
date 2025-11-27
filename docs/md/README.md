# FilamentHub - Документация

> **Дата обновления:** 2025-11-20  
> **Версия:** 1.0

---

## 📚 Навигация по документам

### 🎯 Начни здесь

**Для новых разработчиков:**
1. 📖 [`CURRENT_STATUS.md`](./CURRENT_STATUS.md) - Краткая сводка (читать в первую очередь)
2. 📊 [`PROJECT_STATUS.md`](./PROJECT_STATUS.md) - Детальный технический анализ
3. 🗺️ [`../ROADMAP.md`](../ROADMAP.md) - Дорожная карта развития
4. ☑️ [`../TODO.md`](../TODO.md) - Текущие задачи

### 🏗️ Архитектура и контекст

**Основные правила (Cursor Rules):**
- [`../.cursor/rules/project.mdc`](../.cursor/rules/project.mdc) - Основной контекст проекта
- [`../.cursor/rules/backend-python.mdc`](../.cursor/rules/backend-python.mdc) - Python/FastAPI правила
- [`../.cursor/rules/frontend-react.mdc`](../.cursor/rules/frontend-react.mdc) - React/TypeScript правила
- [`../.cursor/rules/orcaslicer-integration.mdc`](../.cursor/rules/orcaslicer-integration.mdc) - OrcaSlicer интеграция

### 🔗 OrcaSlicer Integration

**Настройка и использование:**
- [`ORCASLICER_SUBMODULE_SETUP.md`](./ORCASLICER_SUBMODULE_SETUP.md) - Настройка submodule
- [`ORCASLICER_SUBMODULE_USAGE.md`](./ORCASLICER_SUBMODULE_USAGE.md) - Использование
- [`WHY_SUBMODULE.md`](./WHY_SUBMODULE.md) - Объяснение структуры
- [`OrcaSlicer/CHANGES.md`](./OrcaSlicer/CHANGES.md) - Лог изменений в форке

**Технические детали:**
- [`SYNC_CHAIN_ANALYSIS.md`](./SYNC_CHAIN_ANALYSIS.md) - Анализ цепочки синхронизации
- [`SYNC_EXPLANATION.md`](./SYNC_EXPLANATION.md) - Объяснение синхронизации
- [`SYNC_FULL_CHAIN.md`](./SYNC_FULL_CHAIN.md) - Полная цепочка
- [`TOKEN_EXPLANATION.md`](./TOKEN_EXPLANATION.md) - JWT токены
- [`IMPORT_COMPARISON.md`](./IMPORT_COMPARISON.md) - Сравнение методов импорта

### 🎨 Дизайн-документы

**Обработка удалённых пресетов:**
- [`DELETED_PRESET_FINAL_APPROACH.md`](./DELETED_PRESET_FINAL_APPROACH.md) - Финальный подход ⭐
- [`DELETED_PRESET_WEBVIEW_APPROACH.md`](./DELETED_PRESET_WEBVIEW_APPROACH.md) - WebView подход
- [`DELETED_PRESET_NOTIFICATIONS_APPROACH.md`](./DELETED_PRESET_NOTIFICATIONS_APPROACH.md) - Уведомления
- [`DELETED_PRESET_NOTIFICATION_OPTIONS.md`](./DELETED_PRESET_NOTIFICATION_OPTIONS.md) - Опции
- [`DELETED_PRESET_DIALOG_PLACEMENT.md`](./DELETED_PRESET_DIALOG_PLACEMENT.md) - Размещение диалогов
- [`DELETED_PRESET_UX_VARIANTS.md`](./DELETED_PRESET_UX_VARIANTS.md) - UX варианты

**Рейтинговая система:**
- [`RATING_SYSTEM_LOGIC.md`](./RATING_SYSTEM_LOGIC.md) - Логика рейтингов
- [`RATING_SYSTEM_OPTIONS.md`](./RATING_SYSTEM_OPTIONS.md) - Опции

### 📦 Референсы

**Сторонние проекты для изучения:**
- [`Spoolman-master/`](./Spoolman-master/) - Референс FastAPI архитектуры
- [`spoolman2slicer-main/`](./spoolman2slicer-main/) - Референс интеграции со слайсерами
- [`3dcalc/`](./3dcalc/) - Legacy PHP приложение (G-code парсеры)

### 🗄️ Backup

- [`filamenthub_backup_20251106_211559.sql`](./filamenthub_backup_20251106_211559.sql) - Backup базы данных

---

## 🔍 Быстрый поиск

### По компонентам

| Компонент | Где искать |
|-----------|-----------|
| Backend API | `PROJECT_STATUS.md` → Backend |
| Frontend UI | `PROJECT_STATUS.md` → Frontend |
| OrcaSlicer | `PROJECT_STATUS.md` → OrcaSlicer Integration |
| База данных | `CURRENT_STATUS.md` → База данных |
| Roadmap | `../ROADMAP.md` |
| TODO | `../TODO.md` |

### По темам

| Тема | Документ |
|------|----------|
| Быстрый overview | `CURRENT_STATUS.md` |
| Технический анализ | `PROJECT_STATUS.md` |
| План развития | `../ROADMAP.md` |
| Текущие задачи | `../TODO.md` |
| Синхронизация OrcaSlicer | `SYNC_*.md` |
| Удалённые пресеты | `DELETED_PRESET_*.md` |
| Рейтинги | `RATING_SYSTEM_*.md` |
| Настройка OrcaSlicer | `ORCASLICER_SUBMODULE_*.md` |

---

## 📊 Статистика документации

**Всего документов:** 25+

**Категории:**
- 📖 Основные (4) - STATUS, ROADMAP, TODO, README
- 🏗️ Архитектура (4) - Cursor Rules
- 🔗 OrcaSlicer (12) - Интеграция, синхронизация, настройка
- 🎨 Дизайн (8) - Удалённые пресеты, рейтинги
- 📦 Референсы (3) - Spoolman, spoolman2slicer, 3dcalc

**Общий объем:** ~50,000+ строк документации

---

## 🚀 Быстрый старт

### Для разработчиков

1. **Читай:**
   - `CURRENT_STATUS.md` - overview
   - `PROJECT_STATUS.md` - детали
   - `../ROADMAP.md` - план

2. **Настройка:**
   - Backend: `cd backend && python main.py`
   - Frontend: `cd frontend && npm run dev` (порт 3000!)
   - OrcaSlicer: См. `ORCASLICER_SUBMODULE_SETUP.md`

3. **Кодинг:**
   - Следуй Cursor Rules (`.cursor/rules/`)
   - Проверяй TODO (`../TODO.md`)
   - Обновляй документацию

### Для AI агентов (Cursor)

1. **Контекст:**
   - Читай `project.mdc` для понимания проекта
   - Используй специфичные правила (`backend-python.mdc`, `frontend-react.mdc`)
   
2. **Навигация:**
   - `CURRENT_STATUS.md` - текущее состояние
   - `PROJECT_STATUS.md` - технические детали
   - `ROADMAP.md` - приоритеты

3. **Работа:**
   - Следуй правилам коммуникации
   - Обновляй TODO при выполнении задач
   - Актуализируй документацию при изменениях

---

## 📝 Как обновлять документацию

### При добавлении фичи
1. Обнови `CURRENT_STATUS.md` (краткое описание)
2. Обнови `PROJECT_STATUS.md` (детали реализации)
3. Обнови `ROADMAP.md` (отметь выполненное, обнови прогресс)
4. Обнови `TODO.md` (mark as completed)

### При изменении архитектуры
1. Обнови соответствующий Cursor Rule (`.cursor/rules/`)
2. Обнови `PROJECT_STATUS.md`
3. Создай дизайн-документ если нужно (как `DELETED_PRESET_*.md`)

### При написании нового модуля
1. Добавь описание в `PROJECT_STATUS.md`
2. Добавь в TODO если требуется доработка
3. Обнови ROADMAP если это milestone

---

## 🆘 Помощь

### Не можешь найти информацию?

1. **Поиск по файлам:** Используй grep или IDE поиск
2. **Спроси AI:** Cursor может найти нужный документ
3. **Читай индекс:** Этот файл содержит ссылки на всё

### Документ устарел?

1. Открой issue или обнови сам
2. Добавь дату обновления в начало документа
3. Обнови раздел "История изменений" если есть

---

**Составлено:** Cursor AI Agent  
**Дата:** 2025-11-20  
**Следующий update:** При добавлении новых документов

**Вопросы?** Читай `CURRENT_STATUS.md` или спрашивай AI агента.


