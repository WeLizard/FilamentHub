# Отображение удалённых пресетов на сайте (WebView)

## Идея

Вместо использования механизма уведомлений OrcaSlicer (NotificationManager), отображаем информацию об удалённых пресетах **на сайте** (в WebView), где пользователь может удобно с ними взаимодействовать.

---

## Как это работает?

### 1. Обнаружение удалённых пресетов (C++)

**Где**: `FilamentHubPanel::synchronize_presets()`

**Когда**: Во время синхронизации пресетов

**Как**:
- C++ проверяет, существует ли пресет в `PresetBundle` (через `preset_exists_in_bundle()`)
- Если пресет не найден, но есть маппинг в `AppConfig` → пресет удалён локально
- Собираем список удалённых пресетов:
```cpp
struct DeletedPreset {
    int preset_id;
    std::string preset_name;
    std::string bundle_preset_name;  // Имя пресета в OrcaSlicer
};
std::vector<DeletedPreset> deleted_presets;
```

### 2. Отправка на сайт (C++ → WebView)

**Где**: `FilamentHubPanel::synchronize_presets()` (после завершения синхронизации)

**Как**: Отправляем список удалённых пресетов через JavaScript в WebView

```cpp
// После синхронизации, если есть удалённые пресеты
if (!deleted_presets.empty()) {
    // Отправляем на сайт через JavaScript
    nlohmann::json deleted_presets_json;
    deleted_presets_json["command"] = "show_deleted_presets";
    deleted_presets_json["presets"] = nlohmann::json::array();
    
    for (const auto& preset : deleted_presets) {
        nlohmann::json preset_json;
        preset_json["preset_id"] = preset.preset_id;
        preset_json["preset_name"] = preset.preset_name;
        preset_json["bundle_preset_name"] = preset.bundle_preset_name;
        deleted_presets_json["presets"].push_back(preset_json);
    }
    
    // Вызываем JavaScript функцию на сайте
    wxString js_code = wxString::Format(
        R"(
            (function() {
                try {
                    var data = %s;
                    if (window.filamenthub && typeof window.filamenthub.showDeletedPresets === 'function') {
                        window.filamenthub.showDeletedPresets(data.presets);
                    } else {
                        console.warn('FilamentHub: showDeletedPresets function not available');
                    }
                } catch (e) {
                    console.error('FilamentHub: Error showing deleted presets:', e);
                }
            })();
        )",
        deleted_presets_json.dump().c_str()
    );
    
    WebView::RunScript(m_browser, js_code);
}
```

### 3. Отображение на сайте (React Frontend)

**Где**: React компонент (например, `DeletedPresetsDialog.tsx`)

**Как**: 
- Слушаем сообщения от C++ через `window.filamenthub.showDeletedPresets()`
- Отображаем диалог/уведомление с списком удалённых пресетов
- Пользователь выбирает действие для каждого пресета (или для всех сразу)

**Компонент**:
```tsx
// DeletedPresetsDialog.tsx
interface DeletedPreset {
  preset_id: number;
  preset_name: string;
  bundle_preset_name: string;
}

export const DeletedPresetsDialog: React.FC = () => {
  const [deletedPresets, setDeletedPresets] = useState<DeletedPreset[]>([]);
  const [isOpen, setIsOpen] = useState(false);
  
  useEffect(() => {
    // Регистрируем функцию для вызова из C++
    if (typeof window !== 'undefined') {
      (window as any).filamenthub = (window as any).filamenthub || {};
      (window as any).filamenthub.showDeletedPresets = (presets: DeletedPreset[]) => {
        setDeletedPresets(presets);
        setIsOpen(true);
      };
    }
  }, []);
  
  const handleAction = (presetId: number, action: 'restore' | 'delete' | 'skip') => {
    // Отправляем действие обратно в C++
    if ((window as any).wx?.postMessage) {
      (window as any).wx.postMessage(JSON.stringify({
        command: 'handle_deleted_preset',
        data: {
          preset_id: presetId,
          action: action
        }
      }));
    }
    
    // Удаляем пресет из списка
    setDeletedPresets(prev => prev.filter(p => p.preset_id !== presetId));
    
    // Закрываем диалог, если список пуст
    if (deletedPresets.length === 1) {
      setIsOpen(false);
    }
  };
  
  return (
    <Dialog open={isOpen} onOpenChange={setIsOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Удалённые пресеты</DialogTitle>
          <DialogDescription>
            Обнаружено {deletedPresets.length} пресетов, которые были удалены из OrcaSlicer, но остаются в FilamentHub.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          {deletedPresets.map(preset => (
            <div key={preset.preset_id} className="flex items-center justify-between p-2 border rounded">
              <span>{preset.preset_name}</span>
              <div className="flex gap-2">
                <Button onClick={() => handleAction(preset.preset_id, 'restore')}>
                  Восстановить
                </Button>
                <Button onClick={() => handleAction(preset.preset_id, 'delete')}>
                  Удалить из FilamentHub
                </Button>
                <Button onClick={() => handleAction(preset.preset_id, 'skip')}>
                  Пропустить
                </Button>
              </div>
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button onClick={() => {
            // Восстановить все
            deletedPresets.forEach(preset => handleAction(preset.preset_id, 'restore'));
          }}>
            Восстановить все
          </Button>
          <Button onClick={() => {
            // Удалить все из FilamentHub
            deletedPresets.forEach(preset => handleAction(preset.preset_id, 'delete'));
          }}>
            Удалить все из FilamentHub
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
```

### 4. Обработка действия (WebView → C++)

**Где**: `FilamentHubPanel::OnScriptMessage()`

**Как**: Обрабатываем команду `handle_deleted_preset`

```cpp
void FilamentHubPanel::OnScriptMessage(wxWebViewEvent& evt)
{
    // ... существующий код ...
    
    if (command == "handle_deleted_preset") {
        int preset_id = j["data"]["preset_id"].get<int>();
        std::string action = j["data"]["action"].get<std::string>();
        
        if (action == "restore") {
            // Восстанавливаем пресет (импортируем обратно)
            import_preset_silent(preset_id);
        } else if (action == "delete") {
            // Удаляем пресет из FilamentHub
            delete_preset_from_filamenthub(preset_id, access_token);
        } else if (action == "skip") {
            // Пропускаем (просто удаляем маппинг)
            remove_preset_mapping(preset_id);
        }
    }
}
```

---

## Преимущества подхода

### ✅ Единообразие UX
- Все взаимодействие происходит на сайте (в WebView)
- Пользователь уже работает в интерфейсе FilamentHub
- Не нужно переключаться между разными системами уведомлений

### ✅ Гибкость
- Можно показать красивый диалог с иконками, описаниями, кнопками
- Можно добавить фильтры, поиск, групповые действия
- Можно показать дополнительную информацию о пресетах (рейтинг, количество использований, etc.)

### ✅ Сохранение состояния
- Если пользователь закроет диалог, можно сохранить состояние и показать снова
- Можно сохранить предпочтения пользователя (например, "всегда восстанавливать")

### ✅ Не блокирует работу
- Диалог на сайте не блокирует работу в OrcaSlicer
- Пользователь может продолжить работу, диалог останется открытым

### ✅ Простота реализации
- Используем существующий механизм обмена сообщениями (`window.filamenthub`, `window.wx.postMessage`)
- Не нужно изучать NotificationManager OrcaSlicer
- Все логика на стороне React (проще тестировать и отлаживать)

---

## Недостатки подхода

### ❌ Зависимость от WebView
- Если пользователь не на вкладке FilamentHub, диалог не будет виден
- Нужно решить, что делать, если пользователь на другой вкладке

### ❌ Нужно хранить состояние
- Если пользователь закроет диалог, нужно сохранить список удалённых пресетов
- Можно сохранить в `AppConfig` или в состоянии React компонента

---

## Решение проблемы "пользователь на другой вкладке"

### Вариант 1: Показывать при следующем открытии вкладки FilamentHub

**Как**:
- Сохраняем список удалённых пресетов в `AppConfig`
- При открытии вкладки FilamentHub (`init()` или `Show()`) проверяем, есть ли pending deleted presets
- Если есть, показываем диалог

```cpp
// В FilamentHubPanel::init() или Show()
void FilamentHubPanel::init() {
    // ... существующий код ...
    
    // Проверяем pending deleted presets
    if (has_pending_deleted_presets()) {
        std::vector<DeletedPreset> pending_presets = load_pending_deleted_presets();
        show_deleted_presets_on_website(pending_presets);
    }
}
```

### Вариант 2: Показывать уведомление в NotificationManager + диалог на сайте

**Как**:
- Показываем уведомление через `NotificationManager` с hypertext "Открыть FilamentHub"
- При клике на hypertext переключаемся на вкладку FilamentHub и показываем диалог
- Это комбинация двух подходов

### Вариант 3: Всегда показывать диалог (даже если пользователь на другой вкладке)

**Как**:
- Показываем диалог на сайте в любом случае
- Пользователь увидит диалог, когда откроет вкладку FilamentHub
- Диалог останется открытым до тех пор, пока пользователь не обработает все пресеты

**Рекомендация**: Вариант 1 (показывать при следующем открытии вкладки FilamentHub)

---

## Вопрос: "Как сайт поймёт, что пресеты удалили?"

### Ответ: C++ сообщает сайту

**Механизм**:
1. **C++ обнаруживает** удалённые пресеты во время синхронизации (проверяет `preset_exists_in_bundle()`)
2. **C++ отправляет** список удалённых пресетов на сайт через JavaScript (`window.filamenthub.showDeletedPresets()`)
3. **Сайт получает** список и отображает диалог
4. **Пользователь выбирает** действие на сайте
5. **Сайт отправляет** действие обратно в C++ через `window.wx.postMessage()`
6. **C++ обрабатывает** действие (восстанавливает, удаляет, пропускает)

**Важно**: Сайт **не знает** о том, что пресеты удалены, пока C++ не сообщит об этом. C++ является единственным источником правды о состоянии пресетов в OrcaSlicer.

---

## Реализация

### Шаг 1: Добавить функцию в JavaScript API (C++)

```cpp
// В FilamentHubPanel::init_js_api()
wxString js_api = R"(
    // ... существующий код ...
    
    window.filamenthub = {
        // ... существующие функции ...
        
        showDeletedPresets: function(presets) {
            // Отправляем событие на сайт
            if (window.postMessage) {
                window.postMessage(JSON.stringify({
                    command: 'show_deleted_presets',
                    presets: presets
                }), '*');
            }
        }
    };
)";
```

### Шаг 2: Создать React компонент для удалённых пресетов

```tsx
// frontend/src/components/DeletedPresetsDialog.tsx
// (код выше)
```

### Шаг 3: Добавить обработчик в OnScriptMessage (C++)

```cpp
// В FilamentHubPanel::OnScriptMessage()
if (command == "handle_deleted_preset") {
    // ... код выше ...
}
```

### Шаг 4: Интегрировать компонент в Layout или отдельную страницу

```tsx
// frontend/src/components/Layout.tsx
import { DeletedPresetsDialog } from './DeletedPresetsDialog';

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  // ... существующий код ...
  
  return (
    <div>
      {/* ... существующий код ... */}
      <DeletedPresetsDialog />
    </div>
  );
};
```

---

## Вопросы для обсуждения:

1. **Где показывать диалог?**
   - Отдельный диалог поверх всего сайта?
   - Уведомление в системе уведомлений сайта?
   - Отдельная страница?

2. **Что делать, если пользователь не на вкладке FilamentHub?**
   - Показывать при следующем открытии вкладки (Вариант 1) - рекомендую
   - Показывать уведомление в NotificationManager + диалог на сайте (Вариант 2)
   - Всегда показывать диалог (Вариант 3)

3. **Какие действия должны быть в диалоге?**
   - Восстановить (импортировать обратно в OrcaSlicer)
   - Удалить из FilamentHub
   - Пропустить (просто удалить маппинг)
   - Запомнить выбор (применять автоматически в будущем)

4. **Нужно ли показывать диалог, если пользователь уже обработал все пресеты?**
   - Да, показывать всегда
   - Нет, показывать только если есть новые удалённые пресеты

5. **Нужно ли сохранять состояние диалога?**
   - Да, сохранять в `AppConfig` или в состоянии React компонента
   - Нет, показывать только один раз при обнаружении

