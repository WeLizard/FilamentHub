# План: Миграция ошибок на коды (error codes i18n)

> **Дата создания:** 25 февраля 2026
> **Статус:** ~95% выполнено, осталось 2 задачи

---

## Контекст

Бэкенд возвращал ошибки на русском (`detail="Неверный пароль"`). Фронтенд показывал их как есть — перевод на другие языки невозможен. Переход на коды ошибок: бэкенд шлёт `detail={"code":"ERR_WRONG_PASSWORD"}`, фронтенд переводит через i18n.

---

## Что уже сделано (коммит 9da9735 и ранее)

### Backend

- [x] `backend/app/core/errors.py` — 80+ ERR_* констант со значениями-кодами (`ERR_USER_NOT_FOUND = "ERR_USER_NOT_FOUND"`)
- [x] `raise_error()` хелпер в errors.py (structured `{"code": ..., "params": ...}`)
- [x] Все хардкод-строки на русском удалены из endpoint-файлов (`detail="Русский текст"` → 0 вхождений)
- [x] `email_validator` — коды вместо строк
- [x] `file_service.py` — коды вместо строк
- [x] `dependencies.py` — коды вместо строк

### Frontend

- [x] `frontend/src/utils/translateApiError.ts` — утилита перевода ошибок
  - Обрабатывает: `{"code": "ERR_...", "params": {...}}`, строку `"ERR_..."`, legacy строку, массив Pydantic, null
- [x] `frontend/src/locales/ru/translation.json` — секция `apiErrors` с ~80 ключами
- [x] `frontend/src/locales/en/translation.json` — секция `apiErrors` с ~80 ключами
- [x] 25 компонентов используют `translateApiError` вместо прямого показа `detail`

---

## Что осталось

### Задача 1: `validate_text_field` — русские имена полей в params (СРЕДНИЙ ПРИОРИТЕТ)

**Проблема:** `validate_text_field()` вызывается с русскими именами полей:

```python
# backend/app/api/v1/endpoints/auth.py:122
is_valid, error_msg = await validate_text_field(data.username, db, "Имя пользователя")
```

Возвращает: `{"code": "ERR_BAD_WORDS", "params": {"field_name": "Имя пользователя"}}`

В английской локали это даст: `The field "Имя пользователя" contains prohibited words` — русское имя поля внутри английского предложения.

**Затронутые файлы и строки:**

| Файл | Русские field_name |
|------|-------------------|
| `auth.py` | "Имя пользователя", "Полное имя", "Биография" |
| `brands.py` | "Название бренда", "Описание бренда" |
| `filaments.py` | "Название материала", "Описание материала", "Название цвета" |
| `printers.py` | "Название принтера", "Описание принтера" |
| `print_profiles.py` | имена профилей |
| `printer_profiles.py` | имена профилей |
| `printer_requests.py` | имена принтеров |
| `brand_requests.py` | имена брендов |
| `filament_reviews.py` | тексты отзывов |
| `orca_sync.py` | имена пресетов |
| `admin.py` | различные поля |

**Решение:**

1. Передавать в `validate_text_field` ключ поля вместо русского названия:
   ```python
   # Было:
   await validate_text_field(data.username, db, "Имя пользователя")
   # Стало:
   await validate_text_field(data.username, db, "username")
   ```

2. Добавить в оба locale файла ключи полей:
   ```json
   // ru/translation.json
   "fieldNames": {
     "username": "Имя пользователя",
     "full_name": "Полное имя",
     "bio": "Биография",
     "brand_name": "Название бренда",
     "brand_description": "Описание бренда",
     "filament_name": "Название материала",
     "filament_description": "Описание материала",
     "color_name": "Название цвета",
     "printer_name": "Название принтера",
     "printer_description": "Описание принтера"
   }

   // en/translation.json
   "fieldNames": {
     "username": "Username",
     "full_name": "Full name",
     ...
   }
   ```

3. В `translateApiError.ts` — при получении `ERR_BAD_WORDS` / `ERR_REPEATED_CHARS` / `ERR_NO_LETTERS_OR_DIGITS`, перевести `params.field_name` через `t(`fieldNames.${params.field_name}`)` перед подстановкой.

4. Обновить `apiErrors` шаблоны если нужно (уже используют `{{field_name}}`).

**Объём:** ~15 строк в endpoint-файлах + ~20 ключей в locale + 5 строк в translateApiError.ts

---

### Задача 2: Консистентность формата — `detail=ERR_STRING` → `detail={"code": ERR_STRING}` (НИЗКИЙ ПРИОРИТЕТ)

**Проблема:** Часть endpoint-ов использует `raise HTTPException(400, detail=ERR_BRAND_SLUG_EXISTS)` (передаёт строку), а часть — `raise_error(400, ERR_BRAND_SLUG_EXISTS)` (передаёт dict). Оба формата работают через `translateApiError.ts`, но формат неконсистентен.

**Затронутые файлы:**

| Файл | Количество мест с `detail=ERR_*` (строка вместо dict) |
|------|------------------------------------------------------|
| `admin.py` | ~21 место |
| `wiki.py` | ~3 места |
| Остальные | используют `raise_error()` — уже ОК |

**Решение:** Заменить `raise HTTPException(status_code=N, detail=ERR_*)` на `raise_error(N, ERR_*)` в admin.py и wiki.py.

**Объём:** ~24 замены, механическая работа.

---

## Формат ошибок (справка)

```python
# Backend — structured error
raise_error(400, ERR_EMAIL_EXISTS)
# → HTTP 400, body: {"detail": {"code": "ERR_EMAIL_EXISTS"}}

# Backend — с параметрами
raise_error(400, ERR_EMAIL_DOMAIN_TYPO, params={"domain": "gmail.com"})
# → HTTP 400, body: {"detail": {"code": "ERR_EMAIL_DOMAIN_TYPO", "params": {"domain": "gmail.com"}}}

# Frontend — перевод
translateApiError(t, error.response?.data?.detail)
// → "Email уже зарегистрирован" (RU) / "Email already registered" (EN)
```

## Ключевые файлы

| Файл | Назначение |
|------|-----------|
| `backend/app/core/errors.py` | 80+ ERR_* констант + `raise_error()` |
| `backend/app/core/utils.py` | `validate_text_field()` — валидация текстовых полей |
| `frontend/src/utils/translateApiError.ts` | Утилита перевода ошибок API |
| `frontend/src/locales/ru/translation.json` | Русские переводы (`apiErrors` секция, ~строка 2741) |
| `frontend/src/locales/en/translation.json` | Английские переводы (`apiErrors` секция, ~строка 2719) |

## Проверка (после завершения)

1. Регистрация с `test@tandex.ru` → ошибка на языке юзера
2. Логин с неверным паролем → "Неверный пароль" (RU) / "Wrong password" (EN)
3. Дублирование email → "Email уже зарегистрирован" / "Email already registered"
4. Ввести запрещённое слово в имя пользователя → имя поля на языке юзера
5. Переключить язык → все ошибки меняют язык
