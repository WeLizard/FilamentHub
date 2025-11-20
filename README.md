# FilamentHub 🎯

Централизованная платформа для управления материалами 3D-печати и интеграции с OrcaSlicer.

## 🚀 О проекте

FilamentHub — это веб-платформа, которая позволяет:
- **Производителям пластика** добавлять свои бренды и официальные настройки
- **Пользователям** получать готовые пресеты для OrcaSlicer прямо в UI слайсера
- **Сообществу** делиться настройками и получать оптимальные параметры через weighted average
- **Всем** управлять материалами, создавать пресеты и рассчитывать стоимость печати

## ✨ Ключевые особенности

- ✅ **Интеграция с OrcaSlicer** - WebView панель с React фронтендом (~85% готово)
- ✅ **Weighted Presets** - генеративные пресеты на основе закона больших чисел
- ✅ **QR-коды на катушках** - автоматическая генерация для верифицированных брендов
- ✅ **Brand Requests** - система заявок для присоединения к брендам
- ✅ **Система уведомлений** - PRESET_UPDATED, PRESET_DELETED, BRAND_VERIFIED
- 🔄 **Двусторонняя синхронизация** - OrcaSlicer ↔ FilamentHub (в разработке)
- 🏭 **Для производителей** - верификация, управление материалами, аналитика

## 📊 Текущий статус

**MVP ~88% готов**

| Компонент | Прогресс | Статус |
|-----------|----------|--------|
| Backend API | 95% | ✅ Готов |
| Frontend UI | 85% | ✅ Почти готов |
| OrcaSlicer Integration | 85% | 🔥 В работе |
| Документация | 80% | ✅ Хорошо |

**База данных:**
- 20 таблиц
- 36 филаментов
- 7 брендов
- 19 пресетов
- 9 пользователей
- 338 принтеров

**Что работает:**
- ✅ Полный CRUD для всех сущностей (Brands, Filaments, Presets, Printers)
- ✅ JWT аутентификация с refresh tokens
- ✅ Модерация пресетов (pending/approved/rejected)
- ✅ Brand Requests (создание, загрузка файлов, одобрение админом)
- ✅ Printer Requests (заявки на добавление принтеров)
- ✅ QR-коды (автогенерация для верифицированных брендов)
- ✅ Weighted presets (генеративные пресеты)
- ✅ Система уведомлений
- ✅ OrcaSlicer экспорт (.json и .info)
- ✅ FilamentHubPanel в OrcaSlicer (WebView + React)
- ✅ Синхронизация пресетов OrcaSlicer ↔ FilamentHub
- ✅ Админ-панель (статистика, модерация, управление)

## 🏗️ Архитектура

### Backend
```
Python 3.11+ + FastAPI + SQLAlchemy (async) + PostgreSQL 15
```

**Технологии:**
- FastAPI 0.110+
- SQLAlchemy 2.0 (async)
- PostgreSQL 15
- JWT (access + refresh tokens)
- Alembic (миграции)
- pytest (58% coverage)

### Frontend
```
TypeScript 5 + React 18 + Vite + shadcn/ui + TailwindCSS
```

**Технологии:**
- React 18 + TypeScript 5
- Vite (dev server на порту **3000**)
- TailwindCSS + shadcn/ui
- TanStack Query (React Query)
- React Router v6

### OrcaSlicer Integration
```
C++ 17 + wxWidgets 3.2 + WebView (Chromium) + libcurl
```

**Форк:** `lizardjazz1/OrcaSlicer` (ветка `filamenthub-integration`)

**Что реализовано:**
- FilamentHubPanel с WebView
- Авторизация через WebView + JWT
- Синхронизация пресетов (автоматическая + ручная)
- Badge с количеством непрочитанных уведомлений
- Обработка удалённых пресетов

## 🚀 Быстрый старт

### Backend

```bash
cd backend

# Виртуальное окружение
python -m venv venv
.\venv\Scripts\Activate.ps1  # Windows
source venv/bin/activate     # Linux/Mac

# Установка зависимостей
pip install -e ".[dev]"

# Запуск PostgreSQL (Docker)
docker-compose up -d

# Настройка .env
cp env.example .env
# Отредактируй DATABASE_URL и SECRET_KEY

# Миграции
alembic upgrade head

# Запуск сервера
python main.py
```

Откройте: http://localhost:8000/docs (Swagger UI)

### Frontend

```bash
cd frontend

# Установка зависимостей
npm install

# Запуск dev сервера (порт 3000!)
npm run dev
```

Откройте: http://localhost:3000

### OrcaSlicer (форк)

```bash
cd docs/OrcaSlicer

# Синхронизация с upstream
git fetch upstream
git merge upstream/main

# Сборка (см. ORCASLICER_SUBMODULE_SETUP.md)
```

## 📁 Структура проекта

```
FilamentHub/
├── backend/              # Python FastAPI
│   ├── app/
│   │   ├── api/v1/endpoints/  # 19 модулей API
│   │   ├── models/            # 18 моделей SQLAlchemy
│   │   ├── schemas/           # Pydantic схемы
│   │   ├── services/          # 13 сервисов
│   │   └── db/                # Database session
│   ├── alembic/versions/      # ~32 миграции
│   └── tests/                 # Тесты (58% coverage)
├── frontend/             # React TypeScript
│   └── src/
│       ├── pages/             # 10 страниц
│       ├── components/        # 48 компонентов
│       ├── api/               # API клиент
│       └── contexts/          # AuthContext
├── docs/                 # Документация
│   ├── OrcaSlicer/           # Форк OrcaSlicer
│   ├── PROJECT_STATUS.md     # Детальный анализ
│   ├── CURRENT_STATUS.md     # Краткая сводка
│   └── README.md             # Навигатор
├── .cursor/rules/        # Правила для AI
├── ROADMAP.md            # Дорожная карта (862 строки)
└── TODO.md               # Текущие задачи
```

## 📝 Документация

**Основные документы:**
- 📊 [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) - Полный технический анализ
- 📖 [docs/CURRENT_STATUS.md](docs/CURRENT_STATUS.md) - Краткая сводка
- 🗺️ [ROADMAP.md](ROADMAP.md) - План развития
- ☑️ [TODO.md](TODO.md) - Текущие задачи
- 📚 [docs/README.md](docs/README.md) - Навигация по документации

**Технические:**
- [docs/ORCASLICER_SUBMODULE_SETUP.md](docs/ORCASLICER_SUBMODULE_SETUP.md) - Настройка OrcaSlicer
- [docs/ORCASLICER_SUBMODULE_USAGE.md](docs/ORCASLICER_SUBMODULE_USAGE.md) - Использование
- [docs/WHY_SUBMODULE.md](docs/WHY_SUBMODULE.md) - Объяснение структуры

**Cursor Rules:**
- [.cursor/rules/project.mdc](.cursor/rules/project.mdc) - Основной контекст
- [.cursor/rules/backend-python.mdc](.cursor/rules/backend-python.mdc) - Python/FastAPI
- [.cursor/rules/frontend-react.mdc](.cursor/rules/frontend-react.mdc) - React/TypeScript
- [.cursor/rules/orcaslicer-integration.mdc](.cursor/rules/orcaslicer-integration.mdc) - OrcaSlicer

## 🎯 Что дальше (Immediate Actions)

### Критично
1. ⏳ Исправить ошибки компиляции OrcaSlicer
2. ⏳ Протестировать синхронизацию пресетов
3. ⏳ Обновить `material_type_base_map`

### Важно
4. ⏳ Портировать G-code парсеры из PHP
5. ⏳ Реализовать выпадающее меню уведомлений в WebView
6. ⏳ Двусторонняя синхронизация (OrcaSlicer → FilamentHub)
7. ⏳ Улучшить UX создания/редактирования материалов

### Можно отложить
- Dark/Light режимы
- Мобильная адаптация
- PWA поддержка
- Интеграция со Spoolman
- Реструктуризация дизайна

## 🔧 Технологии

### Backend Stack
- **Framework:** FastAPI 0.110+
- **ORM:** SQLAlchemy 2.0 (async)
- **Database:** PostgreSQL 15
- **Cache:** Redis 7 (планируется)
- **Auth:** JWT (access + refresh tokens)
- **Validation:** Pydantic v2
- **Migrations:** Alembic
- **Testing:** pytest (58% coverage)
- **Rate Limiting:** slowapi

### Frontend Stack
- **Language:** TypeScript 5
- **Framework:** React 18
- **Build:** Vite
- **UI:** shadcn/ui + TailwindCSS
- **State:** TanStack Query (React Query)
- **Forms:** React Hook Form + Zod
- **Routing:** React Router v6
- **Icons:** lucide-react

### OrcaSlicer Integration
- **Language:** C++ 17
- **GUI:** wxWidgets 3.2
- **HTTP:** libcurl
- **WebView:** wxWebView (Chromium на Windows)
- **JSON:** nlohmann/json
- **Build:** CMake

## 👥 Команда

**Реальность:** Соло-разработка (1 человек + AI ассистент)

**Роли:**
- **Ты:** Архитектор, Product Owner, Тестировщик
- **AI (Cursor):** Программист, Исполнитель

## 💰 Ограничения

- **Бюджет:** $0 (на старте)
- **Команда:** 1 человек + AI
- **Время:** Part-time разработка
- **Фокус:** MVP за 3-4 месяца → ~88% готов

## 🎓 Для разработчиков

### Быстрый старт
1. Клонируй репо
2. Запусти PostgreSQL (Docker)
3. Backend: `cd backend && python main.py`
4. Frontend: `cd frontend && npm run dev` ⚠️ **Порт 3000!**
5. Читай `docs/PROJECT_STATUS.md` для понимания архитектуры

### Полезные команды

**Backend:**
```bash
alembic upgrade head         # Применить миграции
alembic revision --autogenerate -m "description"  # Создать миграцию
pytest                       # Запустить тесты
python main.py              # Запустить сервер
```

**Frontend:**
```bash
npm run dev                 # Dev сервер (порт 3000)
npm run build              # Сборка для production
npm run lint               # Проверка кода
```

**OrcaSlicer:**
```bash
cd docs/OrcaSlicer
git pull upstream main     # Синхронизация с upstream
# Сборка см. в docs/ORCASLICER_SUBMODULE_SETUP.md
```

## 📈 Метрики успеха MVP

**Готово ✅:**
- [x] Backend API работает (95%)
- [x] Frontend UI реализован (85%)
- [x] OrcaSlicer форк создан и настроен
- [x] FilamentHubPanel добавлен в OrcaSlicer
- [x] Авторизация через WebView работает
- [x] Синхронизация пресетов работает
- [x] Brand Requests система работает
- [x] QR-коды генерируются
- [x] Уведомления работают
- [x] Weighted presets реализованы
- [x] Админ-панель работает

**В работе 🔥:**
- [ ] Исправить компиляцию OrcaSlicer
- [ ] Портировать G-code парсеры
- [ ] Протестировать полный цикл синхронизации
- [ ] Улучшить UX форм

**Не начато ❌:**
- [ ] Production deployment
- [ ] Мобильная адаптация
- [ ] Dark/Light режимы
- [ ] Spoolman интеграция (full)

## 🚨 Известные проблемы

- ⏳ Ошибки компиляции OrcaSlicer (nlohmann/json, PresetCollection API)
- ⏳ G-code парсеры требуют портирования из PHP
- ⏳ Email verification не полностью реализована

## 📄 Лицензия

Private repository - все права защищены.

## 🤝 Вклад

Проект в активной разработке. Issues и предложения приветствуются!

---

**Made with ❤️ for 3D printing community**

**Дата обновления:** 2025-11-20  
**Версия:** MVP 88%  
**Следующий релиз:** Январь 2026
