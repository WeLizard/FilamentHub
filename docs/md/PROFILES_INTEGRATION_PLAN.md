# План интеграции согласования профилей в существующий сайт

## 📐 Текущая структура сайта

### FilamentDetailPage (страница филамента)
- Заголовок с информацией о филаменте
- Табы: **"Пресеты"** и **"Отзывы"**
- На табе "Пресеты":
  - Официальный пресет (если есть) - в отдельной карточке с градиентом
  - Пресеты сообщества - в списке
- Кнопка "Добавить в профиль" для сохранения пресета
- Показываются принтеры, связанные с пресетом (если есть `preset.printers`)

### ProfilePage (профиль пользователя)
- Вкладки: `dashboard`, `presets`, `printer-profiles`, `print-profiles`, `history`, `calculator`, `settings`
- На `dashboard` есть заглушка "Комбинации профилей"
- Показываются карточки пресетов с информацией о связанных принтерах

### CatalogPage (каталог материалов)
- Список карточек материалов (`FilamentSummaryCard`)
- Фильтры по бренду и типу материала

---

## 💡 Варианты интеграции

### 1. На странице филамента (FilamentDetailPage)

**Место:** После выбора пресета, в том же табе "Пресеты"

**Идея:** Когда пользователь выбирает пресет (нажимает "Добавить в профиль"), показывать рекомендации по профилям печати и принтера

**Реализация:**
1. Когда пользователь нажимает "Добавить в профиль" на пресете
2. После успешного сохранения показываем модалку или раскрывающийся блок:
   ```
   ✅ Пресет добавлен в профиль!
   
   💡 Рекомендуемые профили:
   - Профиль печати: 0.20mm Standard (если совместим)
   - Профиль принтера: Ender 3 Pro 0.4mm (если совместим)
   
   [Добавить профили] [Пропустить]
   ```

**Или:**
Показывать рекомендации прямо под официальным пресетом:
```tsx
{/* После официального пресета */}
{officialPreset && user && (
  <div className="mt-4 bg-white/5 rounded-xl border border-white/10 p-4">
    <h4 className="text-sm font-semibold text-white mb-2">
      💡 Рекомендуемые профили для этого пресета
    </h4>
    {/* Список рекомендуемых PrintProfile и PrinterProfile */}
  </div>
)}
```

---

### 2. В профиле пользователя (ProfilePage)

**Место:** Вкладка `dashboard`, вместо заглушки "Комбинации профилей"

**Идея:** Показывать автоматически найденные комбинации из профилей пользователя

**Реализация:**
1. Заменить заглушку на реальный блок
2. Автоматически находить комбинации:
   - PrinterProfile → PrintProfile (через `default_print_profile_slug`)
   - PrintProfile → Filament (через `print_profile_filaments`)
   - Filament → Preset (через `preset.filament_id`)

3. Показывать карточки комбинаций:
```tsx
{/* Вкладка dashboard */}
{foundCombinations.map((combination) => (
  <div className="bg-white/10 rounded-xl border border-white/20 p-6">
    <div className="flex items-center gap-3 mb-3">
      <Printer className="w-5 h-5 text-blue-400" />
      <span>{combination.printer_profile?.name}</span>
      <ArrowRight className="w-4 h-4 text-gray-400" />
      <Settings className="w-5 h-5 text-purple-400" />
      <span>{combination.print_profile?.name}</span>
      <ArrowRight className="w-4 h-4 text-gray-400" />
      <Package className="w-5 h-5 text-green-400" />
      <span>{combination.filament?.name}</span>
      <ArrowRight className="w-4 h-4 text-gray-400" />
      <Thermometer className="w-5 h-5 text-red-400" />
      <span>{combination.preset?.name}</span>
    </div>
    <button className="px-4 py-2 bg-purple-600 text-white rounded-lg">
      Экспорт в OrcaSlicer
    </button>
  </div>
))}
```

**Если комбинация неполная:**
```tsx
{/* Неполная комбинация */}
<div className="bg-white/5 rounded-xl border border-dashed border-white/20 p-6">
  <div className="flex items-center gap-3 mb-3">
    <Printer className="w-5 h-5 text-blue-400" />
    <span>Voron 2.4 350</span>
    <X className="w-4 h-4 text-gray-400" />
    <span className="text-gray-400">Профиль печати не выбран</span>
  </div>
  <button className="px-4 py-2 bg-white/10 text-white rounded-lg">
    Настроить комбинацию
  </button>
</div>
```

---

### 3. В карточке пресета (PresetCard в профиле)

**Место:** В `ProfilePage` на вкладке `presets`

**Идея:** Показывать в карточке пресета, какие профили печати и принтера можно использовать с ним

**Реализация:**
В компоненте `PresetCard` добавить информацию о совместимых профилях:
```tsx
{preset.compatible_print_profiles && preset.compatible_print_profiles.length > 0 && (
  <div className="mt-2 flex items-center gap-2 flex-wrap">
    <span className="text-xs text-gray-400">Совместимые профили печати:</span>
    {preset.compatible_print_profiles.map((profile) => (
      <span className="px-2 py-0.5 bg-purple-600/20 text-purple-300 text-xs rounded">
        {profile.name}
      </span>
    ))}
  </div>
)}
```

---

### 4. В модалке просмотра пресета (ViewPresetModal)

**Место:** Когда пользователь открывает пресет для просмотра

**Идея:** Показывать рекомендации по профилям печати и принтера прямо в модалке

**Реализация:**
Добавить секцию "Рекомендуемые профили" в `ViewPresetModal`:
```tsx
<div className="mt-6 border-t border-white/10 pt-4">
  <h4 className="text-sm font-semibold text-white mb-3">
    💡 Рекомендуемые профили
  </h4>
  {/* Список PrintProfile и PrinterProfile */}
</div>
```

---

## 🎯 Предлагаемый подход

### Фаза 1: Минимальная интеграция (без изменения UI)

1. **В профиле пользователя** - заменить заглушку "Комбинации профилей" на реальный блок:
   - Автоматически находить комбинации из профилей пользователя
   - Показывать карточки комбинаций
   - Кнопка "Экспорт в OrcaSlicer" для готовых комбинаций

2. **API эндпоинт** для получения комбинаций:
   ```
   GET /api/v1/profiles/combinations
   ```
   Возвращает комбинации профилей пользователя

### Фаза 2: Рекомендации (опционально)

3. **На странице филамента** - показывать рекомендации после выбора пресета:
   - В модалке после "Добавить в профиль"
   - Или раскрывающийся блок под пресетом

4. **API эндпоинты:**
   ```
   GET /api/v1/filaments/{id}/presets/{preset_id}/recommended-profiles
   ```
   Возвращает рекомендуемые PrintProfile и PrinterProfile для комбинации Filament + Preset

---

## 📝 Что нужно сделать

1. **Backend:**
   - Эндпоинт `GET /api/v1/profiles/combinations` - получить комбинации профилей пользователя
   - Логика автоматического поиска комбинаций из существующих профилей
   - Эндпоинт для рекомендаций (опционально)

2. **Frontend:**
   - Компонент `ProfileCombinations` для отображения комбинаций в профиле
   - Заменить заглушку в `ProfilePage` на реальный компонент
   - Добавить API функцию `getProfileCombinations()`

3. **UI/UX:**
   - Использовать существующий стиль карточек (`bg-white/10 rounded-xl`)
   - Показывать статус комбинации (полная/неполная)
   - Кнопка "Экспорт в OrcaSlicer" для готовых комбинаций

---

## ❓ Вопросы для обсуждения

1. **Приоритет:** Что важнее - показывать комбинации в профиле или рекомендации на странице филамента?
2. **Неполные комбинации:** Показывать ли принтеры без профилей печати, или скрывать их?
3. **Экспорт:** Что экспортировать, если пользователь не выбрал PrintProfile и PrinterProfile - только Filament + Preset?
4. **Рекомендации:** Показывать ли рекомендации агрессивно (модалка) или ненавязчиво (раскрывающийся блок)?

---

## ✅ Следующие шаги

1. Реализовать backend эндпоинт для получения комбинаций
2. Создать компонент `ProfileCombinations` 
3. Заменить заглушку в профиле на реальный компонент
4. Протестировать на существующих данных


