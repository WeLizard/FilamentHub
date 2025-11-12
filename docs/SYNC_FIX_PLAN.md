# План исправления синхронизации OrcaSlicer ↔ FilamentHub

## 🔍 Диагностика проблемы

### Проблема:
В логах нет записей о синхронизации:
- ❌ Нет `[info] FilamentHub: ========== SYNC BUTTON CLICKED ==========`
- ❌ Нет `[info] FilamentHub: ========== synchronize_presets() CALLED ==========`
- ❌ Нет API запросов к backend

### Возможные причины:

1. **Кнопка "Synchronize" не видна или не активна**
   - Кнопка скрыта до логина: `m_sync_button->Hide(); // Hidden by default (shown when logged in)`
   - Пользователь не залогинен → кнопка скрыта → нельзя нажать

2. **Обработчик события не вызывается**
   - Проблема с привязкой события: `m_sync_button->Bind(wxEVT_BUTTON, &FilamentHubPanel::on_sync_button_click, this);`
   - Событие не доходит до обработчика

3. **Логирование не работает**
   - `BOOST_LOG_TRIVIAL(info)` не настроен для уровня `info`
   - Логи пишутся в другой файл
   - Логи не пишутся вообще

4. **Пользователь не нажимал кнопку**
   - Кнопка не была нажата
   - Или нажата, но не обработана

---

## 📋 План исправления

### Шаг 1: Проверка видимости кнопки и состояния логина

**Что проверить:**
1. Видна ли кнопка "Synchronize" в UI OrcaSlicer?
2. Залогинен ли пользователь в FilamentHub?
3. Показывается ли кнопка после логина?

**Как проверить:**
- Открыть OrcaSlicer
- Перейти на вкладку "FilamentHub"
- Проверить, видна ли кнопка "Synchronize"
- Если кнопка не видна → проверить, залогинен ли пользователь

**Что исправить:**
- Если кнопка не показывается после логина → исправить `update_ui_for_login_state()`
- Если пользователь не залогинен → добавить кнопку "Login" и логику логина

---

### Шаг 2: Проверка работы логирования

**Что проверить:**
1. Работает ли `BOOST_LOG_TRIVIAL(info)`?
2. Настроен ли уровень логирования для `info`?
3. Пишутся ли логи в файл?

**Как проверить:**
- Добавить тестовый лог при инициализации `FilamentHubPanel`
- Проверить, появляется ли этот лог в файле
- Если лог не появляется → проблема с настройкой логирования

**Что исправить:**
- Если логирование не работает → настроить `BOOST_LOG_TRIVIAL` для уровня `info`
- Если логи пишутся в другой файл → найти правильный файл логов
- Добавить более явное логирование в начале `on_sync_button_click()`

---

### Шаг 3: Проверка привязки события кнопки

**Что проверить:**
1. Правильно ли привязан обработчик события?
2. Вызывается ли обработчик при нажатии кнопки?
3. Есть ли ошибки при компиляции?

**Как проверить:**
- Проверить, что `m_sync_button->Bind(wxEVT_BUTTON, &FilamentHubPanel::on_sync_button_click, this);` вызывается
- Добавить лог в начале `on_sync_button_click()` с максимальным приоритетом
- Проверить, что обработчик не переопределяется где-то еще

**Что исправить:**
- Если обработчик не вызывается → проверить привязку события
- Если есть ошибки компиляции → исправить ошибки
- Добавить проверку, что кнопка существует перед привязкой события

---

### Шаг 4: Проверка загрузки токена

**Что проверить:**
1. Есть ли токен в `AppConfig`?
2. Правильно ли загружается токен?
3. Возвращает ли `load_auth_token()` `true`?

**Как проверить:**
- Проверить файл конфигурации OrcaSlicer (`OrcaSlicer.conf`)
- Найти секцию `[filamenthub]` и ключи `access_token` и `user_id`
- Если токена нет → пользователь не залогинен
- Если токен есть → проверить, правильно ли он загружается

**Что исправить:**
- Если токена нет → добавить логику логина
- Если токен есть, но не загружается → исправить `load_auth_token()`
- Добавить более подробное логирование в `load_auth_token()`

---

### Шаг 5: Проверка работы API запросов

**Что проверить:**
1. Работают ли API запросы к backend?
2. Доступен ли backend по адресу `http://localhost:8000`?
3. Правильно ли формируются HTTP запросы?

**Как проверить:**
- Проверить, работает ли backend (запущен ли сервер)
- Проверить, доступен ли backend по адресу `http://localhost:8000`
- Проверить, правильно ли формируются HTTP запросы в `FilamentHubClient`
- Добавить логирование всех HTTP запросов

**Что исправить:**
- Если backend не работает → запустить backend
- Если backend недоступен → исправить URL или настройки сети
- Если HTTP запросы не работают → исправить `FilamentHubClient`

---

## 🛠️ Конкретные исправления

### 1. Добавить явное логирование при инициализации

**Файл:** `docs/OrcaSlicer/src/slic3r/GUI/FilamentHubPanel.cpp`

**Изменения:**
```cpp
void FilamentHubPanel::init()
{
    BOOST_LOG_TRIVIAL(info) << "FilamentHub: ========== FilamentHubPanel::init() CALLED ==========";
    BOOST_LOG_TRIVIAL(info) << "FilamentHub: Initializing FilamentHubPanel...";
    
    // ... existing code ...
    
    // Проверяем, что кнопка создана
    if (m_sync_button == nullptr) {
        BOOST_LOG_TRIVIAL(error) << "FilamentHub: m_sync_button is null!";
    } else {
        BOOST_LOG_TRIVIAL(info) << "FilamentHub: m_sync_button created successfully";
    }
    
    // Проверяем, что обработчик привязан
    BOOST_LOG_TRIVIAL(info) << "FilamentHub: Binding sync button click handler...";
    m_sync_button->Bind(wxEVT_BUTTON, &FilamentHubPanel::on_sync_button_click, this);
    BOOST_LOG_TRIVIAL(info) << "FilamentHub: Sync button click handler bound successfully";
}
```

---

### 2. Добавить логирование в начале `on_sync_button_click()`

**Файл:** `docs/OrcaSlicer/src/slic3r/GUI/FilamentHubPanel.cpp`

**Изменения:**
```cpp
void FilamentHubPanel::on_sync_button_click(wxCommandEvent& evt)
{
    // ЯВНОЕ ЛОГИРОВАНИЕ С МАКСИМАЛЬНЫМ ПРИОРИТЕТОМ
    BOOST_LOG_TRIVIAL(error) << "FilamentHub: ========== SYNC BUTTON CLICKED (ERROR LEVEL FOR VISIBILITY) ==========";
    BOOST_LOG_TRIVIAL(info) << "FilamentHub: ========== SYNC BUTTON CLICKED ==========";
    BOOST_LOG_TRIVIAL(warning) << "FilamentHub: ========== SYNC BUTTON CLICKED (WARNING LEVEL) ==========";
    
    // Проверяем, что обработчик вызывается
    wxMessageBox("Sync button clicked!", "FilamentHub", wxOK | wxICON_INFORMATION);
    
    // ... existing code ...
}
```

**Примечание:** `wxMessageBox` добавлен для немедленной визуальной проверки, что обработчик вызывается. После подтверждения можно удалить.

---

### 3. Добавить проверку видимости кнопки

**Файл:** `docs/OrcaSlicer/src/slic3r/GUI/FilamentHubPanel.cpp`

**Изменения:**
```cpp
void FilamentHubPanel::update_ui_for_login_state(bool is_logged_in)
{
    BOOST_LOG_TRIVIAL(info) << "FilamentHub: update_ui_for_login_state called. is_logged_in=" << (is_logged_in ? "true" : "false");
    
    if (is_logged_in) {
        // Show logged-in UI elements
        m_profile_button->Show();
        m_preset_count_label->Show();
        m_sync_button->Show(); // ВАЖНО: Показываем кнопку синхронизации
        m_logout_button->Show();
        
        BOOST_LOG_TRIVIAL(info) << "FilamentHub: Showing sync button (user is logged in)";
        
        // Hide not-logged-in UI elements
        m_login_button->Hide();
    } else {
        // Show not-logged-in UI elements
        m_login_button->Show();
        
        // Hide logged-in UI elements
        m_profile_button->Hide();
        m_preset_count_label->Hide();
        m_sync_button->Hide(); // ВАЖНО: Скрываем кнопку синхронизации
        m_logout_button->Hide();
        
        BOOST_LOG_TRIVIAL(info) << "FilamentHub: Hiding sync button (user is not logged in)";
    }
    
    // Обновляем layout
    m_info_panel->Layout();
    BOOST_LOG_TRIVIAL(info) << "FilamentHub: UI updated for login state";
}
```

---

### 4. Добавить проверку состояния кнопки перед нажатием

**Файл:** `docs/OrcaSlicer/src/slic3r/GUI/FilamentHubPanel.cpp`

**Изменения:**
```cpp
void FilamentHubPanel::on_sync_button_click(wxCommandEvent& evt)
{
    BOOST_LOG_TRIVIAL(info) << "FilamentHub: ========== SYNC BUTTON CLICKED ==========";
    
    // Проверяем, что кнопка существует
    if (m_sync_button == nullptr) {
        BOOST_LOG_TRIVIAL(error) << "FilamentHub: m_sync_button is null! Cannot handle click.";
        return;
    }
    
    // Проверяем, что кнопка видима
    if (!m_sync_button->IsShown()) {
        BOOST_LOG_TRIVIAL(warning) << "FilamentHub: Sync button is hidden! Cannot handle click.";
        return;
    }
    
    // Проверяем, что кнопка активна
    if (!m_sync_button->IsEnabled()) {
        BOOST_LOG_TRIVIAL(warning) << "FilamentHub: Sync button is disabled! Cannot handle click.";
        return;
    }
    
    BOOST_LOG_TRIVIAL(info) << "FilamentHub: Sync button is visible and enabled. Proceeding with sync...";
    
    // ... existing code ...
}
```

---

### 5. Добавить логирование при загрузке токена

**Файл:** `docs/OrcaSlicer/src/slic3r/GUI/FilamentHubPanel.cpp`

**Изменения:**
```cpp
bool FilamentHubPanel::load_auth_token(std::string& access_token, int& user_id)
{
    BOOST_LOG_TRIVIAL(info) << "FilamentHub: ========== load_auth_token() CALLED ==========";
    
    if (wxGetApp().app_config == nullptr) {
        BOOST_LOG_TRIVIAL(error) << "FilamentHub: app_config is null, cannot load token";
        return false;
    }
    
    BOOST_LOG_TRIVIAL(info) << "FilamentHub: app_config is not null. Loading token...";
    
    std::string token = wxGetApp().app_config->get(CONFIG_SECTION_FILAMENTHUB, CONFIG_KEY_ACCESS_TOKEN);
    std::string user_id_str = wxGetApp().app_config->get(CONFIG_SECTION_FILAMENTHUB, CONFIG_KEY_USER_ID);
    
    BOOST_LOG_TRIVIAL(info) << "FilamentHub: Loading auth token - token length: " << token.length() 
                            << ", user_id_str: '" << user_id_str << "'";
    BOOST_LOG_TRIVIAL(info) << "FilamentHub: CONFIG_SECTION_FILAMENTHUB: " << CONFIG_SECTION_FILAMENTHUB;
    BOOST_LOG_TRIVIAL(info) << "FilamentHub: CONFIG_KEY_ACCESS_TOKEN: " << CONFIG_KEY_ACCESS_TOKEN;
    BOOST_LOG_TRIVIAL(info) << "FilamentHub: CONFIG_KEY_USER_ID: " << CONFIG_KEY_USER_ID;
    
    // ... existing code ...
}
```

---

### 6. Добавить логирование HTTP запросов

**Файл:** `docs/OrcaSlicer/src/slic3r/Utils/FilamentHubClient.cpp`

**Изменения:**
```cpp
void FilamentHubClient::get_my_presets(
    const std::string& access_token,
    const std::string& updated_since,
    std::function<void(std::string, unsigned)> on_complete,
    std::function<void(std::string, std::string, unsigned)> on_error
) const
{
    BOOST_LOG_TRIVIAL(info) << "FilamentHub: ========== get_my_presets() CALLED ==========";
    BOOST_LOG_TRIVIAL(info) << "FilamentHub: API base URL: " << s_api_base_url;
    BOOST_LOG_TRIVIAL(info) << "FilamentHub: Token length: " << access_token.length();
    BOOST_LOG_TRIVIAL(info) << "FilamentHub: updated_since: " << (updated_since.empty() ? "(empty)" : updated_since);
    
    std::string url = s_api_base_url + "/api/v1/auth/my-presets";
    if (!updated_since.empty()) {
        url += "?updated_since=" + updated_since;
    }
    
    BOOST_LOG_TRIVIAL(info) << "FilamentHub: Request URL: " << url;
    BOOST_LOG_TRIVIAL(info) << "FilamentHub: Sending GET request to: " << url;
    
    Http::get(url)
        .header("Authorization", "Bearer " + access_token)
        .header("Content-Type", "application/json")
        .header("Accept", "application/json")
        .timeout_connect(10)
        .timeout_max(30)
        .on_complete([on_complete, url](std::string body, unsigned status) {
            BOOST_LOG_TRIVIAL(info) << "FilamentHub: Received response from: " << url;
            BOOST_LOG_TRIVIAL(info) << "FilamentHub: HTTP status: " << status;
            BOOST_LOG_TRIVIAL(info) << "FilamentHub: Response body size: " << body.size() << " bytes";
            if (body.size() < 500) {
                BOOST_LOG_TRIVIAL(info) << "FilamentHub: Response body: " << body;
            } else {
                BOOST_LOG_TRIVIAL(info) << "FilamentHub: Response body (first 500 chars): " << body.substr(0, 500);
            }
            on_complete(body, status);
        })
        .on_error([on_error, url](std::string body, std::string error, unsigned status) {
            BOOST_LOG_TRIVIAL(error) << "FilamentHub: Error requesting: " << url;
            BOOST_LOG_TRIVIAL(error) << "FilamentHub: HTTP status: " << status;
            BOOST_LOG_TRIVIAL(error) << "FilamentHub: Error: " << error;
            BOOST_LOG_TRIVIAL(error) << "FilamentHub: Response body: " << body;
            on_error(body, error, status);
        })
        .perform_sync();
    
    BOOST_LOG_TRIVIAL(info) << "FilamentHub: HTTP request sent (sync)";
}
```

---

## 🧪 План тестирования

### Тест 1: Проверка видимости кнопки
1. Открыть OrcaSlicer
2. Перейти на вкладку "FilamentHub"
3. Проверить, видна ли кнопка "Synchronize"
4. Если кнопка не видна → проверить, залогинен ли пользователь
5. Если пользователь не залогинен → залогиниться
6. Проверить, появилась ли кнопка после логина

### Тест 2: Проверка работы логирования
1. Пересобрать OrcaSlicer с добавленным логированием
2. Запустить OrcaSlicer
3. Проверить логи при инициализации `FilamentHubPanel`
4. Проверить, появляются ли логи `[info] FilamentHub: ========== FilamentHubPanel::init() CALLED ==========`
5. Если лог не появляется → проблема с настройкой логирования

### Тест 3: Проверка нажатия кнопки
1. Открыть OrcaSlicer
2. Перейти на вкладку "FilamentHub"
3. Убедиться, что пользователь залогинен
4. Нажать кнопку "Synchronize"
5. Проверить, появляется ли `wxMessageBox` "Sync button clicked!"
6. Если `wxMessageBox` не появляется → обработчик не вызывается
7. Проверить логи, появляются ли записи `[info] FilamentHub: ========== SYNC BUTTON CLICKED ==========`

### Тест 4: Проверка загрузки токена
1. Открыть OrcaSlicer
2. Перейти на вкладку "FilamentHub"
3. Убедиться, что пользователь залогинен
4. Нажать кнопку "Synchronize"
5. Проверить логи, появляются ли записи о загрузке токена
6. Если токен не загружается → проверить файл конфигурации `OrcaSlicer.conf`

### Тест 5: Проверка API запросов
1. Убедиться, что backend запущен на `http://localhost:8000`
2. Открыть OrcaSlicer
3. Перейти на вкладку "FilamentHub"
4. Убедиться, что пользователь залогинен
5. Нажать кнопку "Synchronize"
6. Проверить логи, появляются ли записи о HTTP запросах
7. Проверить логи backend, появляются ли запросы от OrcaSlicer

---

## ✅ Чеклист исправлений

- [ ] Добавить явное логирование при инициализации `FilamentHubPanel`
- [ ] Добавить логирование в начале `on_sync_button_click()` с максимальным приоритетом
- [ ] Добавить проверку видимости кнопки перед нажатием
- [ ] Добавить проверку состояния кнопки (существует ли, видна ли, активна ли)
- [ ] Добавить логирование при загрузке токена
- [ ] Добавить логирование HTTP запросов в `FilamentHubClient`
- [ ] Добавить `wxMessageBox` для немедленной визуальной проверки (временно)
- [ ] Проверить, что кнопка показывается после логина
- [ ] Проверить, что обработчик события привязан правильно
- [ ] Проверить, что токен загружается из `AppConfig`
- [ ] Проверить, что backend доступен по адресу `http://localhost:8000`
- [ ] Пересобрать OrcaSlicer с исправлениями
- [ ] Протестировать синхронизацию

---

## 🎯 Приоритет исправлений

### Критично (делать первым):
1. ✅ Добавить явное логирование в начале `on_sync_button_click()` (с `wxMessageBox` для проверки)
2. ✅ Проверить, что кнопка показывается после логина
3. ✅ Проверить, что обработчик события привязан правильно

### Важно (делать вторым):
4. ✅ Добавить логирование при загрузке токена
5. ✅ Добавить логирование HTTP запросов
6. ✅ Проверить, что токен загружается из `AppConfig`

### Желательно (делать третьим):
7. ✅ Добавить проверку видимости кнопки перед нажатием
8. ✅ Добавить проверку состояния кнопки
9. ✅ Улучшить обработку ошибок

---

## 📝 Резюме

**Основная проблема:** В логах нет записей о синхронизации, что означает, что либо:
1. Кнопка "Synchronize" не нажималась
2. Обработчик события не вызывается
3. Логирование не работает
4. Пользователь не залогинен (кнопка скрыта)

**План действий:**
1. Добавить явное логирование для диагностики
2. Проверить видимость кнопки и состояние логина
3. Проверить работу логирования
4. Проверить привязку события кнопки
5. Проверить загрузку токена
6. Проверить работу API запросов

**Следующий шаг:** Добавить логирование и проверить, что происходит при нажатии кнопки "Synchronize".

