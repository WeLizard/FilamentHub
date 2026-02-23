# Промпт: Исследование производителей филамента

> Запускать через Qwen/Gemini CLI в отдельном окне.
> Gemini — веб-поиск и сбор данных, Qwen — структурирование.

---

## Промпт для Gemini (поиск)

```
Задача: собрать максимально полный список производителей филамента (пластика) для 3D-печати.
Для каждого производителя нужно:
- Полное название компании
- Страна
- Сайт (URL)
- URL логотипа (если найдёшь на сайте или в открытом доступе)
- Краткое описание (1-2 предложения): что производят, чем известны
- Основные виды материалов (PLA, PETG, ABS, TPU, нейлон, поликарбонат, и т.д.)

### 1. Российские производители (ПОЛНЫЙ список)
Найди ВСЕ российские бренды филамента. Поищи по запросам:
- "российские производители филамента для 3D печати"
- "купить филамент российского производства"
- "отечественный пластик для 3D принтера"
- "производители пластика 3D печать Россия 2024 2025"
- Маркетплейсы: Wildberries, Ozon — раздел "филамент", фильтр по российским брендам
- 3D-печать форумы: 3dtoday.ru, 3deshnik.ru

Известные мне (проверь и дополни):
- Bestfilament
- Filamentarno
- Grafillex (Graphtec?)
- FDPlast
- Lider-3D
- MonoFilament
- Plastiq
- Greg (greg3d)
- Nit (nit3d)
- eFilament
- U3Print
- REC 3D
- SEM Filament
- ABSmaker
- Spb Plastic
- Element 3D
- ST-Plast
- PrintProduct
- TiTi Flex
- X Filament
- MaxPrint3D
- 3Dpla
- Syntech
- Tiger3D (?)
- Volprint
- FunFilament
- ESUN (производство в России?)

### 2. Европейские производители (основные + доступные в РФ)
Поищи:
- "best filament brands Europe 2024 2025"
- "European filament manufacturers"
- Немецкие, чешские, польские, испанские, итальянские, скандинавские

Известные:
- Prusament (Чехия)
- Fiberlogy (Польша)
- Fillamentum (Чехия)
- ColorFabb (Нидерланды)
- Extrudr (Австрия)
- FormFutura (Нидерланды)
- Spectrum Filaments (Польша)
- Devil Design (Польша)
- Herz (Германия)
- DAS FILAMENT (Германия)
- 3DJake (Австрия, ритейлер со своим брендом)
- Prusa Polymers (Чехия)
- Recreus (Испания, гибкие)
- Smartfil (Испания)
- Polymaker (основа Китай, но сильное присутствие в Европе)

### 3. Китайские производители (основные + доступные глобально)
Поищи:
- "best Chinese filament brands"
- "Chinese filament manufacturers AliExpress"
- "top filament brands from China 2024 2025"

Известные:
- eSUN (Shenzhen eSUN Industrial)
- Sunlu
- Creality (свой филамент)
- Bambu Lab (свой филамент)
- Jayo
- Kingroon
- Eryone
- Geeetech
- Anycubic
- ELEGOO
- Overture
- IIEST
- Kexcelled
- Polymaker (Шанхай)
- RepRapper
- PolyTerra / PolyLite (бренды Polymaker)
- Voxelab
- Mingda
- Flashforge (свой филамент)
- YOUSU

### 4. Логотипы
Для каждого бренда попробуй найти URL логотипа:
- На официальном сайте (обычно в header или footer)
- На странице "About" / "Press Kit" / "Media"
- Google Images: "brand_name filament logo png"
- Clearbit Logo API: https://logo.clearbit.com/domain.com

### Формат вывода

JSON-файл `brands_research.json`:

```json
[
  {
    "name": "Bestfilament",
    "slug": "bestfilament",
    "country": "RU",
    "region": "russia",
    "website": "https://bestfilament.ru",
    "logo_url": "https://bestfilament.ru/logo.png",
    "description": "Один из крупнейших российских производителей филамента. Широкий ассортимент PLA, PETG, ABS.",
    "materials": ["PLA", "PETG", "ABS", "TPU", "HIPS"],
    "verified": false
  }
]
```

Поля:
- `name` — как на сайте производителя
- `slug` — латиницей, lowercase, дефисы вместо пробелов
- `country` — ISO 3166-1 alpha-2 (RU, CN, CZ, PL, NL, DE, ES, AT...)
- `region` — "russia", "europe", "china"
- `website` — с https://
- `logo_url` — прямая ссылка на изображение (или null)
- `description` — на русском, 1-2 предложения
- `materials` — массив строк
- `verified` — всегда false (верификация вручную)

ВАЖНО:
- Не придумывай бренды — только реально существующие
- Если не уверен в URL логотипа — ставь null
- Slug должен быть уникальным
- Сайт должен быть рабочим (проверь если можешь)
```

## Как запускать

### Вариант 1: только Gemini (рекомендуется)
```bash
gemini "содержимое промпта выше"
```
Gemini сам поищет в интернете и соберёт данные.

### Вариант 2: Gemini → Qwen
1. Gemini собирает сырые данные по каждому региону
2. Qwen структурирует в JSON и проверяет дубликаты/ошибки:
```bash
qwen "Вот сырые данные о производителях филамента: {вставить вывод Gemini}. Структурируй в JSON по формату: [{"name": ..., "slug": ..., "country": ..., "region": ..., "website": ..., "logo_url": ..., "description": ..., "materials": [...], "verified": false}]. Проверь дубликаты, исправь slugs, убери несуществующие бренды."
```

### Вариант 3: Через PAL clink из Claude Code
```
clink(cli_name="gemini", prompt="...", background=true)
```

## После сбора данных

1. Результат сохранить в `docs/brands/brands_research.json`
2. Логотипы скачать в `frontend/public/brands/` (или загрузить на CDN)
3. Импорт в БД — через скрипт или админку
