# Объяснение CMake Warnings при сборке OrcaSlicer

## 📋 Типы предупреждений

### 1. CMake Warning CMP0175 (add_custom_command DEPENDS)

**Что это:**
```
CMake Warning (dev) at CMakeLists.txt:763 (add_custom_command):
  The following keywords are not supported when using
  add_custom_command(TARGET): DEPENDS.

  Policy CMP0175 is not set: add_custom_command() rejects invalid arguments.
```

**Объяснение:**
- В CMake используется старый синтаксис `add_custom_command(TARGET ... DEPENDS ...)`
- В новых версиях CMake (3.21+) параметр `DEPENDS` не поддерживается с `TARGET`
- Это предупреждение для разработчиков (dev warning)

**Критичность:** ❌ **НЕ критично** - это просто предупреждение о устаревшем синтаксисе

**Решение:**
- Можно игнорировать - сборка проходит успешно
- Для устранения: обновить CMakeLists.txt в OrcaSlicer, убрать DEPENDS из add_custom_command(TARGET)
- Или добавить `cmake_policy(SET CMP0175 NEW)` в начало CMakeLists.txt

---

### 2. CMake Warning CMP0167 (FindBoost module)

**Что это:**
```
CMake Warning (dev) at cmake/modules/FindOpenVDB.cmake:372 (find_package):
  Policy CMP0167 is not set: The FindBoost module is removed.
```

**Объяснение:**
- В новых версиях CMake (3.28+) модуль `FindBoost` удален
- Теперь используется `find_package(Boost)` с `BoostConfig.cmake`
- Это предупреждение о том, что используется старый способ поиска Boost

**Критичность:** ❌ **НЕ критично** - Boost находится успешно через BoostConfig.cmake

**Решение:**
- Можно игнорировать - Boost находится корректно
- Для устранения: обновить FindOpenVDB.cmake в OrcaSlicer

---

### 3. CMake Warning CMP0177 (install DESTINATION paths)

**Что это:**
```
CMake Warning (dev) at CMakeLists.txt:968 (install):
  Policy CMP0177 is not set: install() DESTINATION paths are normalized.
```

**Объяснение:**
- В новых версиях CMake пути в `install()` нормализуются автоматически
- Это предупреждение о политике нормализации путей

**Критичность:** ❌ **НЕ критично** - установка проходит успешно

---

## ✅ Вывод

**Все эти warnings:**
- ❌ **НЕ критичны** для сборки
- ✅ Сборка проходит успешно
- ✅ Это просто предупреждения о устаревшем синтаксисе CMake
- ✅ Можно игнорировать (или скрыть с `-Wno-dev`)

**Что делать:**
1. **Игнорировать** - сборка работает нормально
2. **Скрыть** - запустить CMake с флагом `-Wno-dev`
3. **Исправить** (опционально) - обновить CMakeLists.txt в OrcaSlicer (но это не наша задача, это нужно делать в upstream)

---

## 🔇 Как скрыть warnings (если мешают)

### Вариант 1: Добавить флаг в CMakeLists.txt
```cmake
if(POLICY CMP0175)
  cmake_policy(SET CMP0175 OLD)  # Игнорировать предупреждение
endif()

if(POLICY CMP0167)
  cmake_policy(SET CMP0167 OLD)  # Игнорировать предупреждение
endif()

if(POLICY CMP0177)
  cmake_policy(SET CMP0177 OLD)  # Игнорировать предупреждение
endif()
```

### Вариант 2: Запустить CMake с флагом
```bash
cmake .. -Wno-dev
```

### Вариант 3: Игнорировать полностью
Просто не обращать внимание - это warnings для разработчиков OrcaSlicer, не для нас.

---

**Итог:** Это нормальные предупреждения от CMake о устаревшем синтаксисе в самом OrcaSlicer. Не мешают сборке, можно игнорировать.

