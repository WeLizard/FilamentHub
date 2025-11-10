# OrcaSlicer FilamentHub Recon 2025-11-10

## Текущее состояние форка
- Ветка `filamenthub-integration` присутствует в локальном репозитории, но фактический код интеграции отсутствует: нет `FilamentHubPanel`, `FilamentHubAuth` и других файлов, упомянутых в `CHANGES.md`. Файл содержит только описание того, что планировалось добавить.
- Поиск по `src/` не даёт ни одного упоминания `FilamentHub`, значит придётся реализовывать вкладку и сетевой клиент с нуля.

## GUI: навигация и вкладки
- Основная многовкладочная панель (`m_tabpanel`) формируется в `MainFrame::create_tabpanel()`. Таб «Device» создаётся/вставляется в момент переключения в режим с мониторингом принтера. Добавление пользовательской вкладки потребует аналогичной вставки в `m_tabpanel` с собственным `wxPanel`.

```1203:1263:docs/OrcaSlicer/src/slic3r/GUI/MainFrame.cpp
        if (!m_monitor) {
            m_monitor = new MonitorPanel(m_tabpanel, wxID_ANY, wxDefaultPosition, wxDefaultSize);
            m_monitor->SetBackgroundColour(*wxWHITE);
        }
        m_monitor->Show(false);
        m_tabpanel->InsertPage(tpMonitor, m_monitor, _L("Device"), std::string("tab_monitor_active"), std::string("tab_monitor_active"));
...
        if (m_printer_view == nullptr) {
            m_printer_view = new PrinterWebView(m_tabpanel);
            Bind(EVT_LOAD_PRINTER_URL, [this](LoadPrinterViewEvent& evt) {
                wxString url = evt.GetString();
                wxString key = evt.GetAPIkey();
                m_printer_view->load_url(url, key);
            });
        }
        m_printer_view->Show(false);
        m_tabpanel->InsertPage(tpMonitor, m_printer_view, _L("Device"), std::string("tab_monitor_active"), std::string("tab_monitor_active"));
```

- Управление пресетами (принтер/печать/филамент) живёт в специализированных вкладках `TabPrint`, `TabFilament`, `TabPrinter`. Они наследуются от `Tab` и создаются через `MainFrame::create_preset_tabs()`. Новая вкладка FilamentHub может реализовываться либо как `Tab` (с использованием механики `ParamsDialog`), либо как отдельный `wxPanel` рядом с 3D-редактором/просмотром.

```1348:1365:docs/OrcaSlicer/src/slic3r/GUI/MainFrame.cpp
void MainFrame::create_preset_tabs()
{
    wxGetApp().update_label_colours_from_appconfig();
    m_param_dialog = new ParamsDialog(m_plater);
    add_created_tab(new TabPrint(m_param_panel), "cog");
    ...
    add_created_tab(new TabFilament(m_param_dialog->panel()), "spool");
    add_created_tab(new TabPrinter(m_param_dialog->panel()), "printer");
    m_param_panel->rebuild_panels();
    m_param_dialog->panel()->rebuild_panels();
}
```

- Диалог сохранения «Physical Printer» содержит готовую инфраструктуру для настроек печатных хостов (OctoPrint, SimplyPrint и т.д.). Этот код можно повторно использовать для управления FilamentHub-коннектором или для вызова синхронизации профилей.

```51:211:docs/OrcaSlicer/src/slic3r/GUI/PhysicalPrinterDialog.cpp
PhysicalPrinterDialog::PhysicalPrinterDialog(wxWindow* parent) :
    DPIDialog(parent, wxID_ANY, _L("Physical Printer"), ... )
{
    ...
    m_optgroup = new ConfigOptionsGroup(this, _L("Print Host upload"), m_config);
    check_host_key_valid();
    build_printhost_settings(m_optgroup);
    ...
}
```

## Работа с пресетами и хранилищем
- Пользовательские пресеты загружаются из `data_dir()/presets/<user>/`. Если путь не задан в `AppConfig`, используется дефолтная папка `DEFAULT_USER_FOLDER_NAME`. Это ключевой механизм, к которому надо подключить импорт FilamentHub (запись файла + вызов `load_user_presets`).

```831:869:docs/OrcaSlicer/src/libslic3r/PresetBundle.cpp
PresetsConfigSubstitutions PresetBundle::load_user_presets(std::string user, ...)
{
    fs::path user_folder(data_dir() + "/" + PRESET_USER_DIR);
    if (!fs::exists(user_folder)) fs::create_directory(user_folder);
    std::string dir_user_presets = data_dir() + "/" + PRESET_USER_DIR + "/" + user;
    ...
    this->prints.load_presets(dir_user_presets, PRESET_PRINT_NAME, ...);
    this->filaments.load_presets(dir_user_presets, PRESET_FILAMENT_NAME, ...);
    this->printers.load_presets(dir_user_presets, PRESET_PRINTER_NAME, ...);
    ...
    this->update_multi_material_filament_presets();
    this->update_compatible(PresetSelectCompatibleType::Never);
}
```

- Есть альтернативный путь подгрузки пресетов напрямую из облака: `PresetBundle::load_user_presets(AppConfig&, std::map<std::string, std::map<std::string,std::string>>& my_presets, ...)` принимает JSON-структуру, разбирает `type` (`print`, `filament`, `printer`) и создаёт/обновляет записи без файловой системы. Это идеальная точка для импортов из API FilamentHub.

- `PresetBundle::setup_directories()` гарантирует наличие системных папок (`data_dir`, `ota`, `preset_user`). Сама `PresetBundle` поддерживает списки `prints`, `filaments`, `printers`, `physical_printers`. Состояние текущих выборов синхронизируется с UI.

## Сетевой слой и интеграция с хостами
- Базовая фабрика печатных хостов (`PrintHost::get_print_host`) выдаёт класс на основе `host_type`. Добавление FilamentHub как источника профилей не обязательно проходит через этот путь, но полезно изучить готовые паттерны авторизации/загрузки (например, SimplyPrint).

```40:72:docs/OrcaSlicer/src/slic3r/Utils/PrintHost.cpp
PrintHost* PrintHost::get_print_host(DynamicPrintConfig *config)
{
    ...
    switch (host_type) {
        case htOctoPrint: return new OctoPrint(config);
        ...
        case htSimplyPrint: return new SimplyPrint(config);
        case htElegooLink: return new ElegooLink(config);
        default:          return nullptr;
    }
}
```

- SimplyPrint-интеграция демонстрирует полный цикл OAuth, хранение токена в `data_dir`, сетевые вызовы через `Http` (обёртка над libcurl). Для FilamentHub (авторизация по `X-API-Key`) достаточно повторить структуру `do_api_call` и переопределить обработчики `on_complete`.

```185:339:docs/OrcaSlicer/src/slic3r/Utils/SimplyPrint.cpp
bool SimplyPrint::do_api_call(std::function<Http(bool)> build_request,
                              std::function<bool(std::string, unsigned)> on_complete,
                              std::function<bool(std::string, std::string, unsigned)> on_error) const
{
    if (cred.find("access_token") == cred.end()) {
        return false;
    }
    ...
    create_request(cred.at("access_token"), false)
        .on_error([&res, &on_error, this, &create_request](std::string body, std::string error, unsigned http_status) {
            if (http_status == 401) {
                ...
                auto http = Http::post(TOKEN_URL);
                ...
            } else {
                res = on_error(body, error, http_status);
            }
        })
        .perform_sync();
    return res;
}
```

- Очередь фоновых загрузок (`PrintHostJobQueue`) уже реализует прогресс/отмену/ошибки. Если FilamentHub таб потребует загрузки профиля или экспорта G-code, логично пользоваться этим API.

## Конфиги приложения и пути
- `GUI_App::init_app_config()` находит или создаёт `data_dir`. На Windows это `C:\Users\<User>\AppData\Roaming\OrcaSlicer`, если рядом с бинарником нет папки `data_dir`. Там же лежат `app_config.ini`, `plugins`, `presets`.

```2030:2084:docs/OrcaSlicer/src/slic3r/GUI/GUI_App.cpp
void GUI_App::init_app_config()
{
    SetAppName(SLIC3R_APP_KEY);
    if (data_dir().empty()) {
        auto _app_folder = boost::filesystem::path(wxStandardPaths::Get().GetExecutablePath().ToUTF8().data()).parent_path();
        boost::filesystem::path app_data_dir_path = _app_folder / "data_dir";
        if (boost::filesystem::exists(app_data_dir_path)) {
            set_data_dir(app_data_dir_path.string());
        } else {
            std::string data_dir = wxStandardPaths::Get().GetUserDataDir().ToUTF8().data();
            set_data_dir(data_dir);
            if (!boost::filesystem::exists(data_dir_path)){
                boost::filesystem::create_directory(data_dir_path);
            }
        }
        ...
    }
    if (!app_config)
        app_config = new AppConfig();
    ...
}
```

- Любые новые настройки для FilamentHub (API key, URL, отметки о синхронизации) стоит хранить в `AppConfig`, чтобы они попадали в `%APPDATA%`.

## Выводы и точки интеграции
- **UI**: придётся добавить новую вкладку или панель в `MainFrame`, возможно переиспользовать существующий `MonitorPanel`/`PrinterWebView`, либо внедрить `wxNotebook` страницу специально для FilamentHub.
- **Данные**: для импорта/экспорта профилей идеально подходит `PresetBundle::load_user_presets` как API-ориентированный путь без прямых файловых манипуляций. Для офлайн режима можно генерировать `.json` (формат Orca preset) и класть в `presets/<user>`.
- **Сеть**: использовать паттерн SimplyPrint (`Http` + обработка 401) и хранение токенов/ключей через `AppConfig`. Авторизация по `X-API-Key` упростит реализацию.
- **Синхронизация**: нужно продумать кэширование `updated_at` и хранение `slug`/`id`, чтобы соответствовать нашим backend-эндпоинтам `/orcaslicer/printer-profiles` и `/orcaslicer/print-profiles`.

## Следующие шаги
1. Спроектировать структуру клиента FilamentHub в OrcaSlicer (класс, где хранить ключ, где обновлять профили).
2. Подготовить UI-макет вкладки FilamentHub: список профилей (принтер/печать/филамент), кнопки «Синхронизировать», «Импортировать из Orca».
3. Определить формат обмена (JSON) и маппинг с `PresetBundle`. Проверить, какие поля нужны минимум (name, slug, inherits, compatible_*).
4. Продумать сохранение API key: диалог в `Preferences` или в новой вкладке.
5. Составить план тестов (авторизация, полный sync, конфликт версий, офлайн режим).

## Статус TODO
- `orca-analysis-plan` — выполнено (описание архитектуры собрали).
- `orca-analysis-report` — выполнено (отчёт добавлен в `docs/md/orca_analytics`).


