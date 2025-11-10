# OrcaSlicer - Соблюдение лицензии AGPL-3.0

> **ВАЖНО:** OrcaSlicer использует лицензию **AGPL-3.0** (GNU Affero General Public License v3.0)  
> При модификации кода OrcaSlicer **ОБЯЗАТЕЛЬНО** соблюдать требования этой лицензии!

---

## ⚠️ Ключевые требования AGPL-3.0

### 1. **Открытость исходного кода**
- Весь модифицированный код OrcaSlicer должен быть **открытым**
- Форк должен быть **публичным** на GitHub
- Нельзя делать приватный форк с модификациями (нарушение лицензии)

### 2. **Сохранение копирайтов и уведомлений**
- Обязательно сохранять все копирайты оригинального кода
- Добавлять уведомления о модификациях
- Сохранять файл LICENSE.txt

### 3. **Предоставление исходников при распространении**
- При распространении бинарников OrcaSlicer с нашими модификациями:
  - Должны предоставить исходный код модификаций
  - Можем ссылаться на публичный репозиторий на GitHub
  - Исходники должны быть доступны всем пользователям

### 4. **Сетевое взаимодействие**
- Если модифицированный OrcaSlicer взаимодействует с FilamentHub API через сеть:
  - Это **НЕ считается** распространением кода FilamentHub
  - FilamentHub (backend) остается под своей лицензией (MIT/Apache)
  - Только код **внутри OrcaSlicer** должен быть под AGPL-3.0

---

## ✅ Что нужно делать при модификации OrcaSlicer

### 1. Сохранять копирайты в модифицированных файлах

**Пример для нового файла:**
```cpp
/*
 * FilamentHub Integration for OrcaSlicer
 * 
 * Copyright (C) 2025 FilamentHub
 * 
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 * 
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 * 
 * You should have received a copy of the GNU Affero General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */
```

**Пример для модификации существующего файла:**
```cpp
// ... оригинальный копирайт SoftFever/OrcaSlicer ...

/*
 * Modified by FilamentHub (2025)
 * - Добавлена интеграция с FilamentHub API
 * - Добавлен новый tab "FilamentHub"
 */
```

### 2. Добавлять уведомления о модификациях

В начале модифицированных файлов добавлять комментарий:
```cpp
/*
 * MODIFICATIONS BY FILAMENTHUB (2025)
 * 
 * This file was modified to integrate FilamentHub functionality.
 * Original copyright (C) SoftFever/OrcaSlicer.
 * 
 * Modifications:
 * - Добавлена авторизация через FilamentHub API
 * - Добавлен новый tab "FilamentHub" в GUI
 * - Добавлена синхронизация профилей из FilamentHub
 * 
 * Source: https://github.com/lizardjazz1/OrcaSlicer
 * Branch: filamenthub-integration
 */
```

### 3. Создать файл CHANGES.md или MODIFICATIONS.md

В корне форка создать файл с описанием всех модификаций:

```markdown
# FilamentHub Modifications to OrcaSlicer

This fork of OrcaSlicer includes modifications to integrate FilamentHub functionality.

## Modified Files

1. `src/slic3r/GUI/MainFrame.cpp`
   - Added FilamentHub tab integration
   
2. `src/slic3r/GUI/FilamentHubPanel.cpp` (NEW)
   - New panel for FilamentHub integration
   
3. `src/slic3r/GUI/FilamentHubAuth.cpp` (NEW)
   - Authentication with FilamentHub API

## Build Fixes

1. `CMakeLists.txt`
   - Fixed OpenCV detection for Windows builds
   - Fixed OCCT DLL path resolution
   
2. `src/libslic3r/CMakeLists.txt`
   - Fixed OpenCV include paths

## License

All modifications are licensed under AGPL-3.0, same as original OrcaSlicer.

Source code: https://github.com/lizardjazz1/OrcaSlicer
Branch: filamenthub-integration
```

### 4. При коммитах использовать правильные сообщения

```bash
# Плохо:
git commit -m "add filamenthub tab"

# Хорошо:
git commit -m "feat: add FilamentHub tab integration (AGPL-3.0 compliant)"
```

---

## 🔍 Разделение лицензий

### OrcaSlicer форк (AGPL-3.0)
- **Весь код в `docs/OrcaSlicer/`** - под AGPL-3.0
- **Любые модификации в OrcaSlicer** - под AGPL-3.0
- **Форк на GitHub** - должен быть публичным

### FilamentHub Backend/Frontend (MIT/Apache)
- **Backend (`backend/`)** - отдельный проект, своя лицензия
- **Frontend (`frontend/`)** - отдельный проект, своя лицензия
- **Взаимодействие через REST API** - НЕ нарушает AGPL-3.0

**Почему это безопасно:**
- FilamentHub не использует код OrcaSlicer напрямую
- Взаимодействие через HTTP API считается "сетевым взаимодействием"
- AGPL-3.0 распространяется только на код внутри модифицированного OrcaSlicer

---

## ✅ Checklist соблюдения AGPL-3.0

При каждой модификации кода OrcaSlicer:

- [ ] Сохранены все оригинальные копирайты
- [ ] Добавлены уведомления о модификациях в файлы
- [ ] Обновлен файл `CHANGES.md` или `MODIFICATIONS.md`
- [ ] Форк остается публичным на GitHub
- [ ] При распространении бинарников - предоставлен доступ к исходникам (ссылка на GitHub)
- [ ] Коммиты содержат понятные сообщения
- [ ] Файл `LICENSE.txt` сохранен без изменений

---

## 📝 Пример структуры коммитов

```bash
# Коммит с модификацией существующего файла
git commit -m "mod: add FilamentHub tab to MainFrame (AGPL-3.0 compliant)

- Modified src/slic3r/GUI/MainFrame.cpp
- Added FilamentHubPanel integration
- Preserved original copyright notices
"

# Коммит с новым файлом
git commit -m "feat: add FilamentHubPanel for API integration (AGPL-3.0)

- New file: src/slic3r/GUI/FilamentHubPanel.cpp
- New file: src/slic3r/GUI/FilamentHubPanel.h
- Copyright (C) 2025 FilamentHub
- Licensed under AGPL-3.0
"
```

---

## 🚨 Чего НЕ делать

### ❌ Запрещено:
- Делать форк приватным (если есть модификации)
- Удалять копирайты оригинального кода
- Изменять файл LICENSE.txt
- Коммитить код без уведомлений о модификациях
- Распространять бинарники без доступа к исходникам
- Использовать код OrcaSlicer в коммерческом закрытом продукте

### ✅ Разрешено:
- Делать форк публичным с модификациями
- Добавлять новые файлы для интеграции FilamentHub
- Модифицировать существующие файлы (с сохранением копирайтов)
- Распространять бинарники (если предоставлен доступ к исходникам)
- Использовать FilamentHub API из OrcaSlicer (сетевое взаимодействие)

---

## 📚 Дополнительные ресурсы

- **Официальный текст AGPL-3.0:** `docs/OrcaSlicer/LICENSE.txt`
- **GNU AGPL FAQ:** https://www.gnu.org/licenses/agpl-faq.html
- **Software Freedom Law Center:** https://www.softwarefreedom.org/

---

## 💡 Практические рекомендации

### 1. При создании нового файла:
- Всегда добавлять header с копирайтом FilamentHub
- Указывать, что файл под AGPL-3.0
- Добавлять ссылку на репозиторий

### 2. При модификации существующего файла:
- Сохранять оригинальный копирайт
- Добавлять комментарий о модификациях в начале файла
- Указывать, что изменено

### 3. При пуше в GitHub:
- Убедиться, что репозиторий публичный
- Обновить README.md с описанием модификаций
- Создать/обновить CHANGES.md

### 4. При релизе бинарников:
- Создать GitHub Release с ссылкой на исходники
- Указать в описании, что исходники доступны в репозитории
- Добавить информацию о лицензии AGPL-3.0

---

## ✅ Текущий статус

**Форк:** ✅ Публичный на GitHub (`lizardjazz1/OrcaSlicer`)  
**Ветка:** ✅ `filamenthub-integration`  
**Правки:** ✅ Применены с сохранением копирайтов  
**LICENSE.txt:** ✅ Сохранен без изменений  

**Следующие шаги:**
- [ ] Создать файл `CHANGES.md` с описанием модификаций
- [ ] Добавить уведомления о модификациях в каждый измененный файл
- [ ] Обновить README.md форка с информацией о FilamentHub интеграции
- [ ] При создании новых файлов добавлять правильные headers

---

**ВАЖНО:** Нарушение AGPL-3.0 может привести к юридическим последствиям. Всегда консультируйтесь с юристом при сомнениях!

---

**Последнее обновление:** 2025-01-XX  
**Лицензия:** AGPL-3.0 (совместимо с оригинальным OrcaSlicer)

