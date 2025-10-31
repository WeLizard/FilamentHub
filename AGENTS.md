# FilamentHub - Инструкции для AI Агента

> Это упрощенная версия правил в Markdown формате. Полные правила в `.cursor/rules/`

## 🎯 О проекте

**FilamentHub** - платформа для управления материалами 3D-печати.

**Команда:** Соло-разработка (1 человек + AI)

**Текущий этап:** Backend MVP (Python FastAPI)

## 🗣️ Как работать

### Ты (Пользователь):
- Архитектор, принимаешь решения
- Указываешь что делать
- Тестируешь результат

### Я (AI):
- Программист, выполняю задачи
- Пишу код по твоим указаниям
- Предлагаю решения, спрашиваю при неясности

### Правила коммуникации:
- **Говори на русском**
- **Будь конкретным** ("Создай эндпоинт X" вместо "Как создать X?")
- **Не стесняйся прерывать** ("стоп" если что-то не так)
- **Я делаю, не спрашиваю** (если логика ясна)
- **Даю готовый код**, не абстрактные советы

## 🏗️ Архитектура

### Backend (текущий фокус):
```
Python 3.11+ + FastAPI + SQLAlchemy (async) + PostgreSQL + Redis
```

### Frontend (потом):
```
TypeScript + React 18 + Vite + shadcn/ui + TailwindCSS
```

### Интеграция с OrcaSlicer:
```
REST API → CLI инструмент → JSON профили → OrcaSlicer
```

## 📁 Структура проекта

```
FilamentHub/
├── backend/                 # Python FastAPI (в разработке)
│   ├── app/
│   │   ├── api/v1/         # REST API эндпоинты
│   │   ├── models/         # SQLAlchemy модели
│   │   ├── schemas/        # Pydantic схемы
│   │   ├── services/       # Бизнес-логика
│   │   └── db/             # Database session
│   └── tests/
├── 3dcalc/                 # Legacy PHP (портируем)
│   └── src/parsers/        # G-code парсеры
├── frontend/               # React (позже)
├── .cursor/rules/          # Правила для Cursor
├── ROADMAP.md              # План разработки
└── AGENTS.md               # Этот файл
```

## 🎯 Текущие приоритеты

### Делаем СЕЙЧАС:
1. ✅ Настройка FastAPI проекта
2. ⏳ Модели данных (Brand, Filament, Preset)
3. ⏳ CRUD эндпоинты
4. ⏳ Портирование G-code парсеров из PHP

### Делаем ПОТОМ:
- Frontend (через 3 месяца)
- Плагин OrcaSlicer (через 7 месяцев)
- Аналитика и рейтинги

### НЕ делаем:
- ❌ Новые фичи в PHP
- ❌ QR-коды (отложено)
- ❌ ML рекомендации (отложено)
- ❌ Мобильное приложение (отложено)

## 💡 Философия разработки

**"Done is better than perfect"**
- Работающий код > красивый код
- MVP > feature-complete
- Простое решение > сложное

**Ограничения:**
- Бюджет: $0
- Время: Part-time разработка
- Фокус: Backend MVP за 3-4 месяца

## 📝 Code Style

### Python:
```python
# Good
async def get_filament(filament_id: int, db: AsyncSession) -> Filament | None:
    """Получить материал по ID."""
    result = await db.execute(
        select(Filament).where(Filament.id == filament_id)
    )
    return result.scalar_one_or_none()
```

### TypeScript (когда дойдем):
```typescript
// Good
interface FilamentCardProps {
  filament: Filament;
  onSelect?: (id: number) => void;
}

export const FilamentCard: React.FC<FilamentCardProps> = ({ filament, onSelect }) => {
  // ...
};
```

## 🚫 Что НЕ делать

- ❌ Не добавляй фичи без согласования
- ❌ Не коммить credentials
- ❌ Не используй `any` в TypeScript
- ❌ Не пиши синхронный код в async функциях
- ❌ Не создавай N+1 queries
- ❌ Не логируй пароли/токены

## 📚 Термины (не переводить)

- **Filament** - материал, пластик
- **Spool** - катушка
- **Preset** - пресет настроек
- **Brand** - производитель
- **Slicer** - слайсер
- **G-code** - G-code

## 💡 Killer Features (что нас выделяет)

1. **OrcaSlicer Integration** - прямо в UI слайсера (не CLI!)
2. **QR-коды на катушках** - отсканировал → профиль импортирован
3. **Краудсорсинг настроек** - weighted average алгоритм
4. **Для производителей** - бесплатная верификация + платная аналитика

## 🔗 Референсы

- **Spoolman:** Пример архитектуры FastAPI
- **spoolman2slicer:** Пример интеграции с OrcaSlicer
- **3dcalc:** Legacy PHP код для портирования

---

**Подробные правила:** `.cursor/rules/`

- `project.mdc` - Основной контекст
- `backend-python.mdc` - Python/FastAPI правила
- `legacy-php.mdc` - Работа с PHP кодом
- `frontend-react.mdc` - React (когда дойдем)

