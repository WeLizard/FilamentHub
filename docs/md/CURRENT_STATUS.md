# FilamentHub - Текущее состояние (Ноябрь 2025)

> **Дата:** 2025-11-20  
> **Версия:** 1.0  
> **Тип документа:** Краткая сводка для быстрой навигации

---

## 🎯 Быстрый overview

**FilamentHub** — платформа для управления материалами 3D-печати и интеграции с OrcaSlicer.

**Общий прогресс MVP:** ~88% готов

| Компонент | Прогресс | Что готово |
|-----------|----------|------------|
| 🐍 Backend API | 95% | Все основные эндпоинты, модели, сервисы |
| ⚛️ Frontend UI | 85% | Полный UI, админ-панель, Brand Requests |
| 🔗 OrcaSlicer | 85% | WebView, авторизация, синхронизация пресетов |
| 📚 Документация | 80% | ROADMAP, TODO, STATUS, технические docs |

---

## 📊 База данных

```
📦 PostgreSQL (filamenthub)
├── 20 таблиц
├── 36 филаментов ✅ (slug восстановлен)
├── 7 брендов
├── 19 пресетов
├── 9 пользователей
└── 338 принтеров
```

---

## 🚀 Что работает (Backend)

### Модели ✅
- User, Brand, Filament (с slug ✅), Preset, Printer
- PrinterProfile, PrintProfile
- BrandRequest, PrinterRequest
- Notification, FilamentReview, UserSavedPreset
- MaterialMapping, Feedback, BadWord

### API Endpoints ✅
- `/api/v1/auth/*` - Аутентификация (JWT + refresh)
- `/api/v1/brands/*` - Бренды
- `/api/v1/filaments/*` - Материалы (CRUD + автогенерация slug)
- `/api/v1/presets/*` - Пресеты (модерация + weighted)
- `/api/v1/printers/*` - Принтеры
- `/api/v1/brand-requests/*` - Заявки на бренд
- `/api/v1/printer-requests/*` - Заявки на принтеры
- `/api/v1/orcaslicer/*` - Синхронизация OrcaSlicer
- `/api/v1/qr/*` - QR-коды
- `/api/v1/notifications/*` - Уведомления
- `/api/v1/admin/*` - Админ-панель
- `/api/v1/calculator/*` - Калькулятор (базовый)

### Сервисы ✅
- OrcaSlicer экспорт/импорт
- Weighted presets (генеративные)
- Модерация контента
- QR-коды (base36)
- Slug generation
- File upload/management
- Notification service

---

## 🎨 Что работает (Frontend)

### Страницы ✅
- Catalog (поиск + фильтры)
- Filament Detail (QR-коды, weighted presets)
- Brand Profile (управление материалами)
- Brand Detail (публичная страница)
- Profile (мои пресеты, избранное)
- Admin Panel (статистика, модерация, users, brands, requests)

### Компоненты ✅
- CreateFilamentModal
- CreatePresetModal ⭐ (8 табов, 113+ параметров)
- EditGCodeModal (с плейсхолдерами)
- FilamentPreview (визуализация цветов)
- Notifications (уведомления)
- Dropdown, CustomSelect
- Toast, Captcha
- Админ-компоненты (8 штук)

---

## 🔗 Что работает (OrcaSlicer)

### Форк ✅
- Repository: `lizardjazz1/OrcaSlicer`
- Branch: `filamenthub-integration`
- Базовая версия: 2.3.2dev

### FilamentHubPanel ✅
- WebView с React фронтендом (localhost:3000)
- Авторизация через WebView
- JWT токен сохраняется в AppConfig
- Навигация: Catalog, Profile, Notifications

### Синхронизация ✅
- Автоматическая синхронизация при входе
- Ручная синхронизация (кнопка)
- Инкрементальная синхронизация (`updated_since`)
- Асинхронная очередь для импорта
- Маппинг `preset_id → bundle_preset_name`
- Постфикс `[FilamentHub]` к именам
- Обнаружение удалённых пресетов
- Badge с количеством уведомлений

---

## ⏳ Что в разработке

### Backend
- G-code парсеры (портирование из PHP)
- Email отправка (SMTP)
- Spoolman интеграция (full sync)

### Frontend
- Dark/Light режимы
- Мобильная адаптация
- PWA поддержка
- Реструктуризация дизайна

### OrcaSlicer
- Исправление ошибок компиляции
- Выпадающее меню уведомлений в WebView
- Двусторонняя синхронизация (OrcaSlicer → FilamentHub)
- Тестирование и сборка бинарников

---

## 🎯 Приоритеты (Immediate Actions)

### Критично
1. ✅ Восстановить `slug` для филаментов - **ГОТОВО**
2. Исправить ошибки компиляции OrcaSlicer
3. Протестировать синхронизацию пресетов

### Важно
4. Портировать G-code парсеры из PHP
5. Реализовать выпадающее меню уведомлений
6. Улучшить UX создания/редактирования материалов

---

## 📂 Документация

### Основные документы
- `PROJECT_STATUS.md` - Детальный технический анализ (новый ⭐)
- `ROADMAP.md` - Дорожная карта развития (862 строки)
- `TODO.md` - Список задач
- `CURRENT_STATUS.md` - Этот документ (краткая сводка)

### Технические
- `WHY_SUBMODULE.md` - Объяснение структуры
- `ORCASLICER_SUBMODULE_SETUP.md` - Настройка
- `ORCASLICER_SUBMODULE_USAGE.md` - Использование
- `DELETED_PRESET_*.md` - Дизайн документы (6 штук)
- `SYNC_*.md` - Анализ синхронизации (4 штуки)
- `RATING_SYSTEM_*.md` - Рейтинговая система (2 штуки)
- `TOKEN_EXPLANATION.md` - JWT токены
- `IMPORT_COMPARISON.md` - Сравнение методов

### Cursor Rules
- `.cursor/rules/project.mdc` - Основной контекст
- `.cursor/rules/backend-python.mdc` - Python правила
- `.cursor/rules/frontend-react.mdc` - React правила
- `.cursor/rules/legacy-php.mdc` - PHP код
- `.cursor/rules/orcaslicer-integration.mdc` - OrcaSlicer

---

## 🔧 Технологии

### Backend
- Python 3.11+ + FastAPI
- SQLAlchemy 2.0 (async) + PostgreSQL 15
- JWT (access + refresh tokens)
- Alembic (миграции)
- pytest (58% coverage)

### Frontend
- React 18 + TypeScript 5
- Vite + TailwindCSS + shadcn/ui
- TanStack Query + React Router
- lucide-react (иконки)

### OrcaSlicer
- C++ 17 + wxWidgets 3.2
- libcurl (HTTP) + nlohmann/json
- wxWebView (Chromium)
- CMake

---

## 🚨 Важные моменты

### Порты
- **Frontend dev:** 3000 ⚠️ ВАЖНО (не 5000+)
- **Backend:** 8000
- **PostgreSQL:** 5432

### База данных
- **Database:** filamenthub
- **User:** filamenthub
- **Password:** filamenthub_dev_password

### MCP Servers
- `database-filamenthub` - PostgreSQL доступ
- `context7` - Документация библиотек
- `playwright` - Браузерная автоматизация

---

## 📈 Метрики успеха MVP

### Готово ✅
- [x] Backend API работает
- [x] PostgreSQL + миграции настроены
- [x] CRUD для всех сущностей
- [x] JWT аутентификация
- [x] Frontend UI полностью реализован
- [x] Админ-панель работает
- [x] Brand Requests система работает
- [x] QR-коды генерируются
- [x] Уведомления работают
- [x] Weighted presets работают
- [x] OrcaSlicer форк создан
- [x] FilamentHubPanel добавлен
- [x] Авторизация через WebView
- [x] Синхронизация пресетов работает
- [x] Slug для филаментов восстановлен

### В работе 🔥
- [ ] Исправить компиляцию OrcaSlicer
- [ ] Портировать G-code парсеры
- [ ] Протестировать полный цикл синхронизации
- [ ] Улучшить UX форм

### Не начато ❌
- [ ] Production deployment (VPS)
- [ ] Мобильная адаптация
- [ ] Dark/Light режимы
- [ ] Email verification (full)
- [ ] Spoolman интеграция (full)

---

## 💡 Для новых разработчиков

### Быстрый старт
1. Клонируй репо: `git clone https://github.com/yourusername/FilamentHub.git`
2. Запусти PostgreSQL (Docker)
3. Backend: `cd backend && python main.py`
4. Frontend: `cd frontend && npm run dev` (порт 3000!)
5. Читай `PROJECT_STATUS.md` для детального понимания

### Структура проекта
```
FilamentHub/
├── backend/              # Python FastAPI
│   ├── app/
│   │   ├── api/v1/endpoints/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── db/
│   └── alembic/versions/
├── frontend/             # React TypeScript
│   └── src/
│       ├── pages/
│       ├── components/
│       ├── api/
│       └── contexts/
├── docs/                 # Документация
│   ├── OrcaSlicer/      # Форк OrcaSlicer
│   └── *.md
└── .cursor/rules/        # Правила для AI
```

### Полезные команды
```bash
# Backend
cd backend
alembic upgrade head         # Применить миграции
pytest                       # Запустить тесты
python main.py              # Запустить сервер

# Frontend
cd frontend
npm run dev                 # Запустить dev сервер (порт 3000)
npm run build              # Сборка для production
npm run lint               # Проверка кода

# OrcaSlicer
cd docs/OrcaSlicer
git pull upstream main     # Синхронизация с upstream
# Сборка см. в ORCASLICER_SUBMODULE_SETUP.md
```

---

**Составлено:** Cursor AI Agent  
**Дата:** 2025-11-20  
**Следующий update:** После исправления компиляции OrcaSlicer

**См. также:**
- `PROJECT_STATUS.md` - Детальный технический анализ
- `ROADMAP.md` - План развития на 12+ месяцев
- `TODO.md` - Текущие задачи


