# FilamentHub 🎯

Централизованная платформа для управления материалами 3D-печати и настройками слайсеров.

## 🚀 О проекте

FilamentHub — это веб-сервис, который позволяет:
- **Производителям пластика** добавлять свои бренды и рекомендуемые настройки
- **Пользователям** получать готовые пресеты для OrcaSlicer и других слайсеров
- **Сообществу** делиться настройками и получать оптимальные параметры через алгоритм weighted average
- **Всем** рассчитывать стоимость печати через калькулятор

## ✨ Ключевые особенности

- 🔌 **Интеграция с OrcaSlicer** - прямо в UI слайсера (планируется)
- 📱 **QR-коды на катушках** - отсканировал → профиль импортирован (планируется)
- 👥 **Краудсорсинг настроек** - weighted average алгоритм
- 🏭 **Для производителей** - бесплатная верификация + платная аналитика (планируется)

## 📊 Текущий статус

**Backend MVP в разработке (~40%)**

- ✅ Структура проекта
- ✅ Модели данных (Brand, Filament, Preset)
- ✅ API Endpoints (Brands, Filaments)
- ✅ Frontend заглушка (HTML)
- ⏳ Database migrations
- ⏳ Authentication
- ⏳ G-code parser
- ⏳ Calculator

## 🏗️ Архитектура

### Backend
```
Python 3.11+ + FastAPI + SQLAlchemy (async) + PostgreSQL + Redis
```

### Frontend (планируется)
```
TypeScript + React 18 + Vite + shadcn/ui + TailwindCSS
```

### Интеграция с OrcaSlicer
```
REST API → CLI инструмент → JSON профили → OrcaSlicer
```

## 🚀 Быстрый старт

Смотри [backend/README.md](backend/README.md) или [backend/QUICKSTART.md](backend/QUICKSTART.md) для детальных инструкций по запуску Backend.

**TL;DR:**
```bash
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1  # Windows
pip install -e ".[dev]"
docker-compose up -d
cp env.example .env  # настрой DATABASE_URL и SECRET_KEY
.\quickstart.ps1  # автоматический запуск
```

Откройте: http://localhost:8000/static/index.html

## 📁 Структура проекта

```
FilamentHub/
├── backend/           # Python FastAPI (в разработке)
│   ├── app/          # Основной код
│   ├── alembic/      # Database migrations
│   ├── static/       # HTML frontend (заглушка)
│   └── tests/        # Тесты
├── 3dcalc/          # Legacy PHP (портируется)
├── docs/             # Референсные проекты
├── .cursor/rules/   # Правила для AI агента
├── ROADMAP.md        # План разработки
└── TODO.md           # Текущие задачи
```

## 📝 Документация

- [ROADMAP.md](ROADMAP.md) - План разработки и roadmap
- [TODO.md](TODO.md) - Текущие задачи
- [AGENTS.md](AGENTS.md) - Правила работы с AI агентом
- [backend/README.md](backend/README.md) - Backend документация
- [backend/QUICKSTART.md](backend/QUICKSTART.md) - Быстрый старт Backend

## 👥 Команда

**Реальность:** Соло-разработка (1 человек + AI ассистент)

## 💰 Ограничения

- Бюджет: $0 (на старте)
- Время: Part-time разработка
- Фокус: Backend MVP за 3-4 месяца

## 📄 Лицензия

Private repository - все права защищены.

---

**Made with ❤️ for 3D printing community**

