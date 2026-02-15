# План: Рекомендованные пресеты «для твоего принтера»

## Суть
В каталоге показывать пресеты, которые наиболее подходят к принтеру пользователя. Используем данные, которые OrcaSlicer уже синхронизировал (printer_profiles → printer_id), + поле `User.printer_id`.

## Что уже есть
- `User.printer_id` — выбранный принтер пользователя (FK → printers.id)
- `PresetPrinter` — M2M связь пресетов с принтерами (на каком тестировали)
- `PrinterProfile` — профили принтеров из OrcaSlicer (owner_user_id, printer_id)
- `Printer` — принтеры с manufacturer, model, family, nozzle_diameter, build volume
- `preset_recommender.py` — взвешенное среднее для генеративных пресетов

## Архитектура решения

### Этап 1: Backend — сервис подбора пресетов

**Новый файл**: `backend/app/services/preset_matcher.py`

Алгоритм скоринга `score_preset_for_printer(preset, user_printer)`:

1. **Exact match** (score=1.0): пресет напрямую привязан к этому принтеру через `PresetPrinter`
2. **Same model** (score=0.9): пресет привязан к принтеру с тем же `manufacturer + model`
3. **Same family** (score=0.7): тот же manufacturer + `family` (напр. все Ender 3 = одна семья)
4. **Same manufacturer** (score=0.5): тот же manufacturer (Creality, Bambu Lab, etc.)
5. **Compatible by specs** (score=0.3): похожие характеристики (build volume ±20%, те же температурные лимиты)
6. **Бонусы**: +0.05 за official, +0.03 за weighted, +rating*0.02

Функция `get_recommended_presets(user_printer_id, db, limit=20)`:
- Берёт все approved+active пресеты
- Считает score для каждого
- Возвращает топ-N отсортированных по score DESC
- Поля: preset_id, score, match_reason ("Тестировано на вашем принтере", "Тот же производитель", etc.)

### Этап 2: Backend — новый endpoint

В `presets.py` добавить:

```
GET /api/v1/presets/recommended-for-printer?printer_id=X&filament_id=Y&limit=20
```

- `printer_id` — обязательный (ID принтера из таблицы printers)
- `filament_id` — опциональный фильтр по материалу
- Возвращает список пресетов с полем `match_score` и `match_reason`

### Этап 3: Frontend — секция «Рекомендовано для вашего принтера»

В `CatalogPage.tsx`:

1. Если user залогинен и у него есть `printer_id` (или синхронизированные printer_profiles) — показываем секцию **"Рекомендовано для {Printer Name}"** над основным каталогом
2. Горизонтальная карусель с топ-10 пресетами
3. Бейдж: "Совпадение 90%" / "Тот же принтер" / "Похожий принтер"
4. Если принтер не выбран — показываем CTA "Выберите принтер для персональных рекомендаций"

### Определение принтера пользователя

Приоритет:
1. `User.printer_id` (если выбран вручную)
2. Первый `PrinterProfile` с `owner_user_id = current_user.id` → его `printer_id`
3. Не определён → предложить выбрать

## Файлы для изменения

| Файл | Изменение |
|------|-----------|
| `backend/app/services/preset_matcher.py` | **НОВЫЙ** — сервис скоринга |
| `backend/app/api/v1/endpoints/presets.py` | Новый endpoint `recommended-for-printer` |
| `backend/app/schemas/preset.py` | Новая схема `RecommendedForPrinterResponse` |
| `frontend/src/api/client.ts` | Метод `presets.getRecommendedForPrinter()` |
| `frontend/src/pages/CatalogPage.tsx` | Секция рекомендаций |

## Что НЕ делаем (пока)
- Не трогаем OrcaSlicer C++ код
- Не добавляем ML/AI — простой детерминированный скоринг
- Не делаем отдельную страницу — встраиваем в существующий каталог
