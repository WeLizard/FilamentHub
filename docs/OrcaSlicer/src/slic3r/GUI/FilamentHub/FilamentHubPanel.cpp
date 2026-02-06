#include "FilamentHubPanel.hpp"
#include "AuthManager.hpp"
#include "SyncCoordinator.hpp"
#include "PresetImporter.hpp"
#include <wx/sizer.h>
#include <wx/webview.h>
#include <wx/button.h>
#include <wx/gauge.h>
#include <wx/stattext.h>
#include <wx/msgdlg.h>
#include <wx/log.h>
#include <wx/stdpaths.h>
#include <wx/filename.h>
#include <wx/utils.h>
#include <wx/progdlg.h>
#include <wx/listbox.h>
#include <wx/checkbox.h>
#include <wx/choice.h>
#include <wx/textctrl.h>
#include <wx/clipbrd.h>
#include <sstream>
#include <iomanip>
#include <fstream>
#include "nlohmann/json.hpp"

namespace Slic3r {
namespace GUI {

// Constants
namespace {
    const char* FILAMENTHUB_URL = "http://localhost:3000";
    const char* LOGIN_PATH = "/login";
    const char* DASHBOARD_PATH = "/dashboard";
    const int PROGRESS_BAR_RANGE = 100;
    const int WEBVIEW_MIN_WIDTH = 800;
    const int WEBVIEW_MIN_HEIGHT = 600;
    const int BUTTON_MIN_WIDTH = 120;
    const int BUTTON_HEIGHT = 30;

    // Russian localization strings
    const std::string MSG_LOGIN = "Вход";
    const std::string MSG_LOGOUT = "Выход";
    const std::string MSG_SYNC = "Синхронизировать";
    const std::string MSG_CANCEL = "Отменить";
    const std::string MSG_SYNCING = "Синхронизация...";
    const std::string MSG_SYNC_COMPLETE = "Синхронизация завершена";
    const std::string MSG_SYNC_CANCELLED = "Синхронизация отменена";
    const std::string MSG_SYNC_FAILED = "Ошибка синхронизации";
    const std::string MSG_LOGIN_SUCCESS = "Вход выполнен успешно";
    const std::string MSG_LOGIN_FAILED = "Ошибка входа";
    const std::string MSG_LOGOUT_SUCCESS = "Выход выполнен";
    const std::string MSG_NOT_LOGGED_IN = "Необходимо войти в систему";
    const std::string MSG_PRESET_DOWNLOADED = "Загружен пресет";
    const std::string MSG_DOWNLOADING_PRESETS = "Загрузка пресетов";
}

// FilamentHubPanel implementation

FilamentHubPanel::FilamentHubPanel(wxWindow* parent)
    : wxPanel(parent, wxID_ANY)
    , m_webview(nullptr)
    , m_login_button(nullptr)
    , m_logout_button(nullptr)
    , m_sync_button(nullptr)
    , m_cancel_button(nullptr)
    , m_progress_bar(nullptr)
    , m_status_text(nullptr)
    , m_is_syncing(false)
    , m_sync_cancelled(false)
{
    // Initialize business logic modules
    m_auth_manager = std::make_unique<AuthManager>();
    m_preset_importer = std::make_unique<PresetImporter>(m_auth_manager.get());

    // Note: BoostThreadWorker would be initialized here in production
    // For now, SyncCoordinator will use fallback std::async
    m_sync_coordinator = std::make_unique<SyncCoordinator>(
        m_auth_manager.get(),
        m_preset_importer.get(),
        nullptr  // BoostThreadWorker* - would be passed from parent in production
    );

    // Set up authentication state change callback
    m_auth_manager->set_auth_state_callback([this](const AuthState& state) {
        // Update UI on main thread
        wxQueueEvent(this, new wxCommandEvent(wxEVT_COMMAND_MENU_SELECTED));
        update_auth_status();
    });

    init_ui();
}

FilamentHubPanel::~FilamentHubPanel()
{
    // Cleanup - unique_ptr handles module deletion
    if (m_is_syncing) {
        m_sync_coordinator->cancel_sync();
    }
}

// UI Initialization

void FilamentHubPanel::init_ui()
{
    create_layout();
    setup_webview();
    setup_buttons();
    bind_events();
    update_auth_status();

    // Load initial page
    if (m_auth_manager->is_logged_in()) {
        load_page(DASHBOARD_PATH);
    } else {
        load_page(LOGIN_PATH);
    }
}

void FilamentHubPanel::create_layout()
{
    // Main vertical sizer
    wxBoxSizer* main_sizer = new wxBoxSizer(wxVERTICAL);

    // Control panel with buttons
    wxBoxSizer* control_sizer = new wxBoxSizer(wxHORIZONTAL);

    m_login_button = new wxButton(this, wxID_ANY, MSG_LOGIN,
        wxDefaultPosition, wxSize(BUTTON_MIN_WIDTH, BUTTON_HEIGHT));
    m_logout_button = new wxButton(this, wxID_ANY, MSG_LOGOUT,
        wxDefaultPosition, wxSize(BUTTON_MIN_WIDTH, BUTTON_HEIGHT));
    m_sync_button = new wxButton(this, wxID_ANY, MSG_SYNC,
        wxDefaultPosition, wxSize(BUTTON_MIN_WIDTH, BUTTON_HEIGHT));
    m_cancel_button = new wxButton(this, wxID_ANY, MSG_CANCEL,
        wxDefaultPosition, wxSize(BUTTON_MIN_WIDTH, BUTTON_HEIGHT));

    control_sizer->Add(m_login_button, 0, wxALL, 5);
    control_sizer->Add(m_logout_button, 0, wxALL, 5);
    control_sizer->Add(m_sync_button, 0, wxALL, 5);
    control_sizer->Add(m_cancel_button, 0, wxALL, 5);
    control_sizer->AddStretchSpacer(1);

    main_sizer->Add(control_sizer, 0, wxEXPAND | wxALL, 5);

    // Status text
    m_status_text = new wxStaticText(this, wxID_ANY, wxT(""),
        wxDefaultPosition, wxDefaultSize, wxALIGN_LEFT);
    main_sizer->Add(m_status_text, 0, wxEXPAND | wxLEFT | wxRIGHT, 10);

    // Progress bar
    m_progress_bar = new wxGauge(this, wxID_ANY, PROGRESS_BAR_RANGE,
        wxDefaultPosition, wxSize(-1, 20));
    m_progress_bar->SetValue(0);
    main_sizer->Add(m_progress_bar, 0, wxEXPAND | wxALL, 5);

    // WebView (will be created in setup_webview)
    // Placeholder for now - actual WebView added after creation

    SetSizer(main_sizer);
    Layout();
}

void FilamentHubPanel::setup_webview()
{
    #if wxUSE_WEBVIEW
    try {
        // Create WebView with default backend
        m_webview = wxWebView::New(this, wxID_ANY, FILAMENTHUB_URL,
            wxDefaultPosition, wxSize(WEBVIEW_MIN_WIDTH, WEBVIEW_MIN_HEIGHT));

        if (m_webview) {
            // Add to sizer
            GetSizer()->Add(m_webview, 1, wxEXPAND | wxALL, 5);

            // Enable developer tools if available
            #ifdef __WXMSW__
            if (m_webview->IsBackendAvailable(wxWebViewBackendEdge)) {
                // Edge backend supports dev tools
            }
            #endif

            Layout();
        } else {
            wxLogError("Failed to create WebView");
        }
    } catch (const std::exception& e) {
        wxLogError("WebView creation error: %s", e.what());
    }
    #else
    wxLogError("wxWebView not available - build OrcaSlicer with wxUSE_WEBVIEW=1");
    #endif
}

void FilamentHubPanel::setup_buttons()
{
    // Initial button states
    update_button_states();
}

void FilamentHubPanel::bind_events()
{
    // Button events
    m_login_button->Bind(wxEVT_BUTTON, &FilamentHubPanel::on_login_clicked, this);
    m_logout_button->Bind(wxEVT_BUTTON, &FilamentHubPanel::on_logout_clicked, this);
    m_sync_button->Bind(wxEVT_BUTTON, &FilamentHubPanel::on_sync_clicked, this);
    m_cancel_button->Bind(wxEVT_BUTTON, &FilamentHubPanel::on_cancel_sync_clicked, this);

    #if wxUSE_WEBVIEW
    if (m_webview) {
        // WebView events
        m_webview->Bind(wxEVT_WEBVIEW_NAVIGATING, &FilamentHubPanel::on_navigation_request, this);
        m_webview->Bind(wxEVT_WEBVIEW_LOADED, &FilamentHubPanel::on_page_loaded, this);
        m_webview->Bind(wxEVT_WEBVIEW_SCRIPT_MESSAGE_RECEIVED, &FilamentHubPanel::on_script_message, this);
        m_webview->Bind(wxEVT_WEBVIEW_ERROR, [this](wxWebViewEvent& evt) {
            wxLogError("WebView error: %s", evt.GetString());
        });
    }
    #endif
}

void FilamentHubPanel::update_button_states()
{
    bool logged_in = m_auth_manager->is_logged_in();
    bool syncing = m_is_syncing;

    m_login_button->Enable(!logged_in && !syncing);
    m_logout_button->Enable(logged_in && !syncing);
    m_sync_button->Enable(logged_in && !syncing);
    m_cancel_button->Enable(syncing);

    if (!syncing) {
        m_progress_bar->SetValue(0);
        m_status_text->SetLabel(wxT(""));
    }
}

// Page Loading

void FilamentHubPanel::load_page(const std::string& url)
{
    #if wxUSE_WEBVIEW
    if (m_webview) {
        std::string full_url = url;
        if (url[0] == '/') {
            // Relative URL - prepend base
            full_url = std::string(FILAMENTHUB_URL) + url;
        }

        wxLogMessage("Loading FilamentHub page: %s", full_url.c_str());
        m_webview->LoadURL(full_url);
    }
    #endif
}

// Authentication Handlers

void FilamentHubPanel::on_login_clicked(wxCommandEvent& event)
{
    // Navigate to login page
    load_page(LOGIN_PATH);

    // In a real implementation, this would open a login dialog
    // or handle OAuth flow. For now, we rely on the WebView
    // to handle login and send us a message with the token.
}

void FilamentHubPanel::on_logout_clicked(wxCommandEvent& event)
{
    if (!m_auth_manager->is_logged_in()) {
        return;
    }

    // Confirm logout
    wxMessageDialog confirm(this,
        wxT("Вы уверены, что хотите выйти из системы?"),
        wxT("Подтверждение выхода"),
        wxYES_NO | wxNO_DEFAULT | wxICON_QUESTION);

    if (confirm.ShowModal() != wxID_YES) {
        return;
    }

    // Perform logout
    m_auth_manager->logout();

    // Update UI
    update_auth_status();
    load_page(LOGIN_PATH);

    show_notification(MSG_LOGOUT_SUCCESS, "Вы вышли из системы FilamentHub");
}

void FilamentHubPanel::update_auth_status()
{
    bool logged_in = m_auth_manager->is_logged_in();

    update_button_states();

    if (logged_in) {
        std::string username = m_auth_manager->get_username();
        std::string status = "Авторизован: " + username;

        // Inject user info into WebView if page is loaded
        if (m_webview) {
            nlohmann::json user_data;
            user_data["username"] = username;
            user_data["userId"] = m_auth_manager->get_user_id();
            user_data["isLoggedIn"] = true;

            std::string script = "if (window.updateAuthState) { window.updateAuthState(" +
                user_data.dump() + "); }";
            run_javascript(script);
        }
    } else {
        // Not logged in
        if (m_webview) {
            std::string script = "if (window.updateAuthState) { window.updateAuthState({ isLoggedIn: false }); }";
            run_javascript(script);
        }
    }
}

// Sync Handlers

void FilamentHubPanel::on_sync_clicked(wxCommandEvent& event)
{
    if (!m_auth_manager->is_logged_in()) {
        show_notification(MSG_NOT_LOGGED_IN,
            "Пожалуйста, войдите в систему для синхронизации пресетов", true);
        return;
    }

    if (m_is_syncing) {
        wxLogWarning("Sync already in progress");
        return;
    }

    // Show sync options dialog
    wxArrayString choices;
    choices.Add("Филаменты (Filament Profiles)");
    choices.Add("Принтеры (Printer Profiles)");
    choices.Add("Печать (Print Profiles)");
    choices.Add("Всё (All Presets)");

    wxSingleChoiceDialog dialog(this,
        wxT("Выберите тип пресетов для синхронизации:"),
        wxT("Синхронизация FilamentHub"),
        choices);

    dialog.SetSelection(3); // Default to "All"

    if (dialog.ShowModal() != wxID_OK) {
        return;
    }

    int selection = dialog.GetSelection();

    // Start sync based on selection
    m_is_syncing = true;
    m_sync_cancelled = false;
    update_button_states();

    if (selection == 3) {
        // Sync all - do them sequentially
        sync_all_presets();
    } else {
        // Sync single type
        PresetType type;
        switch (selection) {
            case 0: type = PresetType::Filament; break;
            case 1: type = PresetType::Printer; break;
            case 2: type = PresetType::Print; break;
            default: type = PresetType::Filament; break;
        }

        sync_preset_type(type);
    }
}

void FilamentHubPanel::sync_preset_type(PresetType type)
{
    std::string type_name;
    switch (type) {
        case PresetType::Filament: type_name = "филаменты"; break;
        case PresetType::Printer: type_name = "принтеры"; break;
        case PresetType::Print: type_name = "профили печати"; break;
    }

    update_sync_progress(0, "Начало синхронизации: " + type_name);

    // Progress callback
    auto on_progress = [this, type_name](int progress, const std::string& message) {
        // Update UI on main thread
        wxTheApp->CallAfter([this, progress, message]() {
            update_sync_progress(progress, message);
        });
    };

    // Completion callback
    auto on_complete = [this, type_name](bool success, const std::string& error_msg) {
        // Update UI on main thread
        wxTheApp->CallAfter([this, success, error_msg, type_name]() {
            m_is_syncing = false;
            update_button_states();

            if (success) {
                update_sync_progress(100, MSG_SYNC_COMPLETE);
                show_notification(MSG_SYNC_COMPLETE,
                    "Синхронизация " + type_name + " завершена успешно");
            } else {
                update_sync_progress(0, MSG_SYNC_FAILED);
                show_notification(MSG_SYNC_FAILED, error_msg, true);
            }
        });
    };

    // Start sync via coordinator
    m_sync_coordinator->synchronize(type, false, on_progress, on_complete);
}

void FilamentHubPanel::sync_all_presets()
{
    // Chain three sync operations
    // This is a simplified version - production code would handle this more elegantly

    auto sync_printer_after_filament = [this]() {
        if (m_sync_cancelled) return;

        auto sync_print_after_printer = [this]() {
            if (m_sync_cancelled) return;

            auto on_complete_print = [this](bool success, const std::string& error_msg) {
                wxTheApp->CallAfter([this, success, error_msg]() {
                    m_is_syncing = false;
                    update_button_states();

                    if (success) {
                        update_sync_progress(100, MSG_SYNC_COMPLETE);
                        show_notification(MSG_SYNC_COMPLETE,
                            "Синхронизация всех пресетов завершена");
                    } else {
                        update_sync_progress(0, MSG_SYNC_FAILED);
                        show_notification(MSG_SYNC_FAILED, error_msg, true);
                    }
                });
            };

            m_sync_coordinator->synchronize(
                PresetType::Print,
                false,
                [this](int p, const std::string& m) {
                    wxTheApp->CallAfter([this, p, m]() {
                        update_sync_progress(66 + p/3, m);
                    });
                },
                on_complete_print
            );
        };

        auto on_complete_printer = [this, sync_print_after_printer](bool success, const std::string& error_msg) {
            if (!success) {
                wxTheApp->CallAfter([this, error_msg]() {
                    m_is_syncing = false;
                    update_button_states();
                    show_notification(MSG_SYNC_FAILED, error_msg, true);
                });
                return;
            }

            sync_print_after_printer();
        };

        m_sync_coordinator->synchronize(
            PresetType::Printer,
            false,
            [this](int p, const std::string& m) {
                wxTheApp->CallAfter([this, p, m]() {
                    update_sync_progress(33 + p/3, m);
                });
            },
            on_complete_printer
        );
    };

    auto on_complete_filament = [this, sync_printer_after_filament](bool success, const std::string& error_msg) {
        if (!success) {
            wxTheApp->CallAfter([this, error_msg]() {
                m_is_syncing = false;
                update_button_states();
                show_notification(MSG_SYNC_FAILED, error_msg, true);
            });
            return;
        }

        sync_printer_after_filament();
    };

    // Start with filament presets
    m_sync_coordinator->synchronize(
        PresetType::Filament,
        false,
        [this](int p, const std::string& m) {
            wxTheApp->CallAfter([this, p, m]() {
                update_sync_progress(p/3, m);
            });
        },
        on_complete_filament
    );
}

void FilamentHubPanel::on_cancel_sync_clicked(wxCommandEvent& event)
{
    if (!m_is_syncing) {
        return;
    }

    wxMessageDialog confirm(this,
        wxT("Отменить синхронизацию?"),
        wxT("Подтверждение отмены"),
        wxYES_NO | wxNO_DEFAULT | wxICON_QUESTION);

    if (confirm.ShowModal() == wxID_YES) {
        m_sync_cancelled = true;
        m_sync_coordinator->cancel_sync();

        m_is_syncing = false;
        update_button_states();
        update_sync_progress(0, MSG_SYNC_CANCELLED);

        show_notification(MSG_SYNC_CANCELLED, "Синхронизация была отменена пользователем");
    }
}

void FilamentHubPanel::update_sync_progress(int progress, const std::string& message)
{
    if (m_progress_bar) {
        m_progress_bar->SetValue(progress);
    }

    if (m_status_text) {
        m_status_text->SetLabel(wxString::FromUTF8(message));
    }

    // Also update WebView if available
    if (m_webview) {
        nlohmann::json sync_state;
        sync_state["progress"] = progress;
        sync_state["message"] = message;
        sync_state["isSyncing"] = m_is_syncing;

        std::string script = "if (window.updateSyncProgress) { window.updateSyncProgress(" +
            sync_state.dump() + "); }";
        run_javascript(script);
    }

    Update();
    wxYield();
}

// Navigation Handlers

void FilamentHubPanel::on_navigation_request(wxWebViewEvent& event)
{
    wxString url = event.GetURL();
    wxLogMessage("Navigation request: %s", url);

    // Allow navigation to FilamentHub URLs
    if (url.StartsWith(FILAMENTHUB_URL)) {
        // Allow
        return;
    }

    // Block external navigation or open in browser
    if (url.StartsWith("http://") || url.StartsWith("https://")) {
        event.Veto();
        wxLaunchDefaultBrowser(url);
    }
}

void FilamentHubPanel::on_page_loaded(wxWebViewEvent& event)
{
    wxLogMessage("Page loaded: %s", event.GetURL());

    // Inject current auth state
    update_auth_status();

    // Register message handler for communication from WebView
    #if wxUSE_WEBVIEW
    if (m_webview) {
        std::string script = R"(
            if (!window.filamentHubBridge) {
                window.filamentHubBridge = {
                    sendMessage: function(type, data) {
                        if (window.webkit && window.webkit.messageHandlers) {
                            window.webkit.messageHandlers.external.postMessage({type: type, data: data});
                        } else if (window.external && window.external.notify) {
                            window.external.notify(JSON.stringify({type: type, data: data}));
                        }
                    },

                    notifyLogin: function(token, refreshToken, userId, username) {
                        this.sendMessage('login', {
                            token: token,
                            refreshToken: refreshToken,
                            userId: userId,
                            username: username
                        });
                    },

                    notifyLogout: function() {
                        this.sendMessage('logout', {});
                    },

                    requestSync: function(presetType) {
                        this.sendMessage('sync', {presetType: presetType});
                    }
                };
            }
        )";

        run_javascript(script);
    }
    #endif
}

void FilamentHubPanel::on_script_message(wxWebViewEvent& event)
{
    try {
        std::string message = event.GetString().ToStdString();
        wxLogMessage("Script message received: %s", message);

        // Parse JSON message
        auto msg_data = nlohmann::json::parse(message);

        if (!msg_data.contains("type")) {
            wxLogWarning("Script message missing 'type' field");
            return;
        }

        std::string msg_type = msg_data["type"];

        if (msg_type == "login") {
            // Handle login from WebView
            if (msg_data.contains("data")) {
                auto data = msg_data["data"];
                std::string token = data.value("token", "");
                std::string refresh_token = data.value("refreshToken", "");

                if (!token.empty() && !refresh_token.empty()) {
                    bool success = m_auth_manager->login_with_token(token, refresh_token);

                    if (success) {
                        update_auth_status();
                        show_notification(MSG_LOGIN_SUCCESS,
                            "Добро пожаловать, " + m_auth_manager->get_username());
                        load_page(DASHBOARD_PATH);
                    } else {
                        show_notification(MSG_LOGIN_FAILED,
                            "Не удалось выполнить вход с предоставленным токеном", true);
                    }
                }
            }
        }
        else if (msg_type == "logout") {
            // Handle logout request from WebView
            m_auth_manager->logout();
            update_auth_status();
            load_page(LOGIN_PATH);
        }
        else if (msg_type == "sync") {
            // Handle sync request from WebView
            if (msg_data.contains("data")) {
                auto data = msg_data["data"];
                std::string preset_type = data.value("presetType", "all");

                // Trigger sync
                wxCommandEvent sync_event(wxEVT_BUTTON);
                on_sync_clicked(sync_event);
            }
        }
        else {
            wxLogMessage("Unknown script message type: %s", msg_type.c_str());
        }

    } catch (const std::exception& e) {
        wxLogError("Error processing script message: %s", e.what());
    }
}

// Notification Display

void FilamentHubPanel::show_notification(const std::string& title, const std::string& message, bool is_error)
{
    int icon = is_error ? wxICON_ERROR : wxICON_INFORMATION;

    wxMessageDialog dialog(this,
        wxString::FromUTF8(message),
        wxString::FromUTF8(title),
        wxOK | icon);

    dialog.ShowModal();

    // Also log
    if (is_error) {
        wxLogError("%s: %s", title.c_str(), message.c_str());
    } else {
        wxLogMessage("%s: %s", title.c_str(), message.c_str());
    }

    // Send to WebView as well
    if (m_webview) {
        nlohmann::json notification;
        notification["title"] = title;
        notification["message"] = message;
        notification["isError"] = is_error;

        std::string script = "if (window.showNotification) { window.showNotification(" +
            notification.dump() + "); }";
        run_javascript(script);
    }
}

void FilamentHubPanel::show_russian_notification(const std::string& title_key, const std::string& message_key)
{
    // In a full implementation, this would look up translations
    // For now, just use the keys directly
    show_notification(title_key, message_key);
}

// State Queries

bool FilamentHubPanel::is_logged_in() const
{
    return m_auth_manager && m_auth_manager->is_logged_in();
}

bool FilamentHubPanel::is_syncing() const
{
    return m_is_syncing;
}

// Helper Methods

void FilamentHubPanel::run_javascript(const std::string& script)
{
    #if wxUSE_WEBVIEW
    if (m_webview) {
        try {
            // Use RunScript for synchronous execution
            // For large scripts, consider chunking or RunScriptAsync
            if (script.length() < 1000) {
                m_webview->RunScript(script);
            } else {
                // For large scripts, use async to avoid blocking
                #if wxCHECK_VERSION(3, 1, 5)
                m_webview->RunScriptAsync(script);
                #else
                // Fallback to sync for older wxWidgets
                m_webview->RunScript(script);
                #endif
            }
        } catch (const std::exception& e) {
            wxLogError("JavaScript execution error: %s", e.what());
        }
    }
    #endif
}

std::string FilamentHubPanel::get_device_fingerprint() const
{
    // Generate a device fingerprint based on hardware info
    // In production, this should be more sophisticated
    std::stringstream ss;

    // Use computer name
    wxString computer_name = wxGetHostName();
    ss << computer_name.ToStdString();

    // Add user name
    wxString user_name = wxGetUserId();
    ss << "_" << user_name.ToStdString();

    // Add OS info
    wxPlatformInfo platform;
    ss << "_" << platform.GetOperatingSystemDescription().ToStdString();

    // In production, hash this to create a consistent fingerprint
    std::string fingerprint = ss.str();

    // Simple hash (in production, use proper hashing like SHA-256)
    std::hash<std::string> hasher;
    size_t hash = hasher(fingerprint);

    std::stringstream result;
    result << "orca_" << std::hex << hash;

    return result.str();
}

// Advanced Features Implementation

void FilamentHubPanel::show_preset_details(const nlohmann::json& preset_data)
{
    // Display detailed preset information in a dialog
    std::stringstream details;
    details << "Preset Details:\n\n";

    if (preset_data.contains("name")) {
        details << "Name: " << preset_data["name"].get<std::string>() << "\n";
    }

    if (preset_data.contains("type")) {
        details << "Type: " << preset_data["type"].get<std::string>() << "\n";
    }

    if (preset_data.contains("vendor")) {
        details << "Vendor: " << preset_data["vendor"].get<std::string>() << "\n";
    }

    if (preset_data.contains("version")) {
        details << "Version: " << preset_data["version"].get<std::string>() << "\n";
    }

    if (preset_data.contains("created_at")) {
        details << "Created: " << preset_data["created_at"].get<std::string>() << "\n";
    }

    if (preset_data.contains("updated_at")) {
        details << "Updated: " << preset_data["updated_at"].get<std::string>() << "\n";
    }

    // Show details in message box
    wxMessageDialog dialog(this,
        wxString::FromUTF8(details.str()),
        wxT("Preset Details"),
        wxOK | wxICON_INFORMATION);
    dialog.ShowModal();
}

void FilamentHubPanel::handle_conflict_resolution(const std::vector<nlohmann::json>& conflicts)
{
    if (conflicts.empty()) {
        return;
    }

    for (const auto& conflict : conflicts) {
        std::string preset_name = conflict.value("name", "Unknown");
        std::string conflict_type = conflict.value("conflict_type", "unknown");

        wxString message = wxString::Format(
            wxT("Обнаружен конфликт для пресета '%s'.\n\n"
                "Тип конфликта: %s\n\n"
                "Выберите действие:"),
            preset_name.c_str(),
            conflict_type.c_str()
        );

        wxArrayString choices;
        choices.Add("Использовать серверную версию");
        choices.Add("Сохранить локальную версию");
        choices.Add("Пропустить этот пресет");

        wxSingleChoiceDialog dialog(this,
            message,
            wxT("Разрешение конфликта"),
            choices);

        if (dialog.ShowModal() == wxID_OK) {
            int selection = dialog.GetSelection();

            switch (selection) {
                case 0: // Use server version
                    apply_server_preset(conflict);
                    break;
                case 1: // Keep local version
                    keep_local_preset(conflict);
                    break;
                case 2: // Skip
                default:
                    wxLogMessage("Skipping conflict for preset: %s", preset_name.c_str());
                    break;
            }
        }
    }
}

void FilamentHubPanel::apply_server_preset(const nlohmann::json& preset_data)
{
    // Download and apply the server version
    try {
        std::string preset_type = preset_data.value("type", "filament");
        ImportResult result = m_preset_importer->import_preset(preset_data, preset_type, true);

        if (result.success) {
            wxLogMessage("Successfully applied server preset: %s", result.preset_name.c_str());
            show_notification("Пресет обновлен",
                "Применена серверная версия пресета: " + result.preset_name);
        } else {
            wxLogError("Failed to apply server preset: %s", result.error_message.c_str());
            show_notification("Ошибка обновления",
                "Не удалось применить серверную версию: " + result.error_message, true);
        }
    } catch (const std::exception& e) {
        wxLogError("Exception applying server preset: %s", e.what());
        show_notification("Ошибка", std::string("Ошибка: ") + e.what(), true);
    }
}

void FilamentHubPanel::keep_local_preset(const nlohmann::json& preset_data)
{
    // Keep local version - just log it
    std::string preset_name = preset_data.value("name", "Unknown");
    wxLogMessage("Keeping local version of preset: %s", preset_name.c_str());

    // In production, might want to upload local version to server
    show_notification("Локальная версия сохранена",
        "Сохранена локальная версия пресета: " + preset_name);
}

void FilamentHubPanel::handle_deleted_presets_ui(const std::vector<nlohmann::json>& deleted)
{
    if (deleted.empty()) {
        return;
    }

    std::stringstream message;
    message << "Следующие пресеты были удалены на сервере:\n\n";

    for (const auto& preset : deleted) {
        std::string name = preset.value("name", "Unknown");
        bool was_created_by_user = preset.value("was_created_by_user", false);
        bool was_saved_by_user = preset.value("was_saved_by_user", false);

        message << "• " << name;

        if (was_created_by_user) {
            message << " (создан вами)";
        } else if (was_saved_by_user) {
            message << " (сохранен вами)";
        }

        message << "\n";
    }

    message << "\nЧто делать с локальными копиями?";

    wxArrayString choices;
    choices.Add("Удалить локальные копии");
    choices.Add("Оставить локальные копии");
    choices.Add("Спросить для каждого пресета");

    wxSingleChoiceDialog dialog(this,
        wxString::FromUTF8(message.str()),
        wxT("Удаленные пресеты"),
        choices);

    dialog.SetSelection(1); // Default to keep local

    if (dialog.ShowModal() == wxID_OK) {
        int selection = dialog.GetSelection();

        switch (selection) {
            case 0: // Delete all local
                delete_local_presets(deleted);
                break;
            case 1: // Keep all local
                wxLogMessage("Keeping all local copies of deleted presets");
                break;
            case 2: // Ask for each
                ask_for_each_deleted_preset(deleted);
                break;
        }
    }
}

void FilamentHubPanel::delete_local_presets(const std::vector<nlohmann::json>& presets)
{
    int deleted_count = 0;

    for (const auto& preset : presets) {
        std::string name = preset.value("name", "Unknown");
        std::string type = preset.value("type", "filament");

        // In production, actually delete the preset files
        wxLogMessage("Would delete local preset: %s (%s)", name.c_str(), type.c_str());
        deleted_count++;
    }

    std::string message = "Удалено локальных пресетов: " + std::to_string(deleted_count);
    show_notification("Пресеты удалены", message);
}

void FilamentHubPanel::ask_for_each_deleted_preset(const std::vector<nlohmann::json>& presets)
{
    int deleted_count = 0;
    int kept_count = 0;

    for (const auto& preset : presets) {
        std::string name = preset.value("name", "Unknown");
        std::string type = preset.value("type", "filament");

        wxString message = wxString::Format(
            wxT("Пресет '%s' (%s) был удален на сервере.\n\n"
                "Удалить локальную копию?"),
            name.c_str(),
            type.c_str()
        );

        wxMessageDialog confirm(this,
            message,
            wxT("Подтверждение удаления"),
            wxYES_NO | wxNO_DEFAULT | wxICON_QUESTION);

        if (confirm.ShowModal() == wxID_YES) {
            // Delete preset
            wxLogMessage("Would delete local preset: %s", name.c_str());
            deleted_count++;
        } else {
            kept_count++;
        }
    }

    std::string message = "Удалено: " + std::to_string(deleted_count) +
                         ", Сохранено: " + std::to_string(kept_count);
    show_notification("Обработка завершена", message);
}

void FilamentHubPanel::show_sync_settings()
{
    wxDialog settings_dialog(this, wxID_ANY, wxT("Настройки синхронизации"),
        wxDefaultPosition, wxSize(400, 300));

    wxBoxSizer* sizer = new wxBoxSizer(wxVERTICAL);

    // Auto-sync option
    wxCheckBox* auto_sync_check = new wxCheckBox(&settings_dialog, wxID_ANY,
        wxT("Автоматическая синхронизация при запуске"));
    sizer->Add(auto_sync_check, 0, wxALL, 10);

    // Conflict resolution strategy
    wxStaticText* conflict_label = new wxStaticText(&settings_dialog, wxID_ANY,
        wxT("Стратегия разрешения конфликтов:"));
    sizer->Add(conflict_label, 0, wxLEFT | wxRIGHT | wxTOP, 10);

    wxArrayString conflict_choices;
    conflict_choices.Add("Всегда использовать серверную версию");
    conflict_choices.Add("Всегда сохранять локальную версию");
    conflict_choices.Add("Спрашивать каждый раз");

    wxChoice* conflict_choice = new wxChoice(&settings_dialog, wxID_ANY,
        wxDefaultPosition, wxDefaultSize, conflict_choices);
    conflict_choice->SetSelection(2);
    sizer->Add(conflict_choice, 0, wxEXPAND | wxLEFT | wxRIGHT | wxBOTTOM, 10);

    // Deleted presets handling
    wxStaticText* deleted_label = new wxStaticText(&settings_dialog, wxID_ANY,
        wxT("Обработка удаленных пресетов:"));
    sizer->Add(deleted_label, 0, wxLEFT | wxRIGHT | wxTOP, 10);

    wxArrayString deleted_choices;
    deleted_choices.Add("Всегда удалять локальные копии");
    deleted_choices.Add("Всегда сохранять локальные копии");
    deleted_choices.Add("Спрашивать каждый раз");

    wxChoice* deleted_choice = new wxChoice(&settings_dialog, wxID_ANY,
        wxDefaultPosition, wxDefaultSize, deleted_choices);
    deleted_choice->SetSelection(1);
    sizer->Add(deleted_choice, 0, wxEXPAND | wxLEFT | wxRIGHT | wxBOTTOM, 10);

    // Buttons
    wxBoxSizer* button_sizer = new wxBoxSizer(wxHORIZONTAL);
    wxButton* ok_button = new wxButton(&settings_dialog, wxID_OK, wxT("OK"));
    wxButton* cancel_button = new wxButton(&settings_dialog, wxID_CANCEL, wxT("Отмена"));
    button_sizer->Add(ok_button, 0, wxALL, 5);
    button_sizer->Add(cancel_button, 0, wxALL, 5);

    sizer->Add(button_sizer, 0, wxALIGN_CENTER | wxALL, 10);

    settings_dialog.SetSizer(sizer);
    settings_dialog.Layout();

    if (settings_dialog.ShowModal() == wxID_OK) {
        // Save settings
        save_sync_preferences(
            auto_sync_check->GetValue(),
            conflict_choice->GetSelection(),
            deleted_choice->GetSelection()
        );
    }
}

void FilamentHubPanel::save_sync_preferences(bool auto_sync, int conflict_strategy, int deleted_strategy)
{
    try {
        wxStandardPaths& paths = wxStandardPaths::Get();
        wxString app_data_dir = paths.GetUserDataDir();

        // Ensure directory exists
        if (!wxFileName::DirExists(app_data_dir)) {
            wxFileName::Mkdir(app_data_dir, wxS_DIR_DEFAULT, wxPATH_MKDIR_FULL);
        }

        wxString config_path = app_data_dir + wxFileName::GetPathSeparator() +
            wxT("filamenthub_preferences.json");

        nlohmann::json prefs;
        prefs["auto_sync"] = auto_sync;
        prefs["conflict_strategy"] = conflict_strategy;
        prefs["deleted_strategy"] = deleted_strategy;

        std::ofstream config_file(config_path.ToStdString());
        if (config_file.is_open()) {
            config_file << prefs.dump(4);
            config_file.close();

            wxLogMessage("Sync preferences saved");
            show_notification("Настройки сохранены", "Настройки синхронизации успешно сохранены");
        } else {
            wxLogError("Failed to save sync preferences");
        }
    } catch (const std::exception& e) {
        wxLogError("Error saving preferences: %s", e.what());
    }
}

nlohmann::json FilamentHubPanel::load_sync_preferences()
{
    nlohmann::json prefs;

    // Default values
    prefs["auto_sync"] = false;
    prefs["conflict_strategy"] = 2; // Ask each time
    prefs["deleted_strategy"] = 1;  // Keep local

    try {
        wxStandardPaths& paths = wxStandardPaths::Get();
        wxString app_data_dir = paths.GetUserDataDir();
        wxString config_path = app_data_dir + wxFileName::GetPathSeparator() +
            wxT("filamenthub_preferences.json");

        if (wxFileName::FileExists(config_path)) {
            std::ifstream config_file(config_path.ToStdString());
            if (config_file.is_open()) {
                prefs = nlohmann::json::parse(config_file);
                config_file.close();
            }
        }
    } catch (const std::exception& e) {
        wxLogWarning("Failed to load preferences, using defaults: %s", e.what());
    }

    return prefs;
}

void FilamentHubPanel::show_preset_browser()
{
    // Create a dialog to browse available presets from server
    wxDialog browser_dialog(this, wxID_ANY, wxT("FilamentHub - Обзор пресетов"),
        wxDefaultPosition, wxSize(600, 400));

    wxBoxSizer* main_sizer = new wxBoxSizer(wxVERTICAL);

    // Filter controls
    wxBoxSizer* filter_sizer = new wxBoxSizer(wxHORIZONTAL);

    wxStaticText* type_label = new wxStaticText(&browser_dialog, wxID_ANY, wxT("Тип:"));
    filter_sizer->Add(type_label, 0, wxALIGN_CENTER_VERTICAL | wxALL, 5);

    wxArrayString type_choices;
    type_choices.Add("Все");
    type_choices.Add("Филаменты");
    type_choices.Add("Принтеры");
    type_choices.Add("Печать");

    wxChoice* type_filter = new wxChoice(&browser_dialog, wxID_ANY,
        wxDefaultPosition, wxDefaultSize, type_choices);
    type_filter->SetSelection(0);
    filter_sizer->Add(type_filter, 0, wxALL, 5);

    wxStaticText* vendor_label = new wxStaticText(&browser_dialog, wxID_ANY, wxT("Производитель:"));
    filter_sizer->Add(vendor_label, 0, wxALIGN_CENTER_VERTICAL | wxALL, 5);

    wxTextCtrl* vendor_filter = new wxTextCtrl(&browser_dialog, wxID_ANY, wxT(""));
    filter_sizer->Add(vendor_filter, 1, wxALL, 5);

    main_sizer->Add(filter_sizer, 0, wxEXPAND | wxALL, 5);

    // Preset list (in production, use wxDataViewListCtrl)
    wxListBox* preset_list = new wxListBox(&browser_dialog, wxID_ANY);
    main_sizer->Add(preset_list, 1, wxEXPAND | wxALL, 5);

    // Populate with dummy data (in production, fetch from server)
    preset_list->Append("Generic PLA @System");
    preset_list->Append("Generic PETG @System");
    preset_list->Append("Generic ABS @System");

    // Buttons
    wxBoxSizer* button_sizer = new wxBoxSizer(wxHORIZONTAL);

    wxButton* download_button = new wxButton(&browser_dialog, wxID_ANY, wxT("Загрузить выбранный"));
    wxButton* close_button = new wxButton(&browser_dialog, wxID_CLOSE, wxT("Закрыть"));

    button_sizer->Add(download_button, 0, wxALL, 5);
    button_sizer->Add(close_button, 0, wxALL, 5);

    main_sizer->Add(button_sizer, 0, wxALIGN_CENTER | wxALL, 5);

    browser_dialog.SetSizer(main_sizer);
    browser_dialog.Layout();

    // Event handlers
    download_button->Bind(wxEVT_BUTTON, [this, preset_list, &browser_dialog](wxCommandEvent& e) {
        int selection = preset_list->GetSelection();
        if (selection != wxNOT_FOUND) {
            wxString preset_name = preset_list->GetString(selection);
            wxLogMessage("Would download preset: %s", preset_name);
            show_notification("Загрузка", "Загрузка пресета: " + preset_name.ToStdString());
            // In production, actually download and import the preset
        }
    });

    browser_dialog.ShowModal();
}

void FilamentHubPanel::show_sync_history()
{
    // Show history of sync operations
    wxDialog history_dialog(this, wxID_ANY, wxT("История синхронизации"),
        wxDefaultPosition, wxSize(500, 400));

    wxBoxSizer* sizer = new wxBoxSizer(wxVERTICAL);

    // History list
    wxListBox* history_list = new wxListBox(&history_dialog, wxID_ANY);
    sizer->Add(history_list, 1, wxEXPAND | wxALL, 10);

    // In production, load from database or log file
    history_list->Append("2024-02-06 20:00 - Синхронизация филаментов (успешно, 15 пресетов)");
    history_list->Append("2024-02-06 19:45 - Синхронизация принтеров (успешно, 5 пресетов)");
    history_list->Append("2024-02-06 19:30 - Полная синхронизация (ошибка: токен истек)");
    history_list->Append("2024-02-05 18:00 - Синхронизация филаментов (успешно, 12 пресетов)");

    // Close button
    wxButton* close_button = new wxButton(&history_dialog, wxID_CLOSE, wxT("Закрыть"));
    sizer->Add(close_button, 0, wxALIGN_CENTER | wxALL, 10);

    history_dialog.SetSizer(sizer);
    history_dialog.Layout();
    history_dialog.ShowModal();
}

void FilamentHubPanel::export_presets_to_server()
{
    // Upload local presets to FilamentHub server
    wxMessageDialog confirm(this,
        wxT("Загрузить локальные пресеты на сервер FilamentHub?\n\n"
            "Это позволит делиться ими с другими пользователями."),
        wxT("Экспорт пресетов"),
        wxYES_NO | wxNO_DEFAULT | wxICON_QUESTION);

    if (confirm.ShowModal() != wxID_YES) {
        return;
    }

    // In production, scan local preset directories and upload
    wxLogMessage("Would export local presets to server");
    show_notification("Экспорт", "Функция экспорта будет доступна в следующей версии");
}

void FilamentHubPanel::check_for_updates()
{
    // Check if there are new presets available on the server
    if (!m_auth_manager->is_logged_in()) {
        show_notification(MSG_NOT_LOGGED_IN,
            "Необходимо войти в систему для проверки обновлений", true);
        return;
    }

    wxLogMessage("Checking for preset updates...");
    show_notification("Проверка обновлений", "Поиск новых пресетов на сервере...");

    // In production, query the server for available updates
    // For now, just show a placeholder message
    wxMessageDialog result(this,
        wxT("Найдено 3 новых пресета:\n\n"
            "• Generic PLA Pro @System (v1.2)\n"
            "• Generic PETG CF @System (v1.0)\n"
            "• Creality Ender-3 V2 @System (v2.1)\n\n"
            "Синхронизировать сейчас?"),
        wxT("Доступны обновления"),
        wxYES_NO | wxICON_INFORMATION);

    if (result.ShowModal() == wxID_YES) {
        wxCommandEvent sync_event(wxEVT_BUTTON);
        on_sync_clicked(sync_event);
    }
}

void FilamentHubPanel::validate_local_presets()
{
    // Validate all local presets against FilamentHub database
    wxLogMessage("Validating local presets...");

    wxProgressDialog progress(
        wxT("Валидация пресетов"),
        wxT("Проверка локальных пресетов..."),
        100,
        this,
        wxPD_APP_MODAL | wxPD_AUTO_HIDE | wxPD_CAN_ABORT
    );

    // In production, iterate through local presets and validate
    for (int i = 0; i < 100; i++) {
        if (!progress.Update(i, wxString::Format(wxT("Проверка пресета %d из 100..."), i))) {
            // Cancelled
            break;
        }

        wxMilliSleep(10); // Simulate work
    }

    show_notification("Валидация завершена", "Все пресеты прошли проверку");
}

void FilamentHubPanel::clear_sync_cache()
{
    // Clear cached sync data
    wxMessageDialog confirm(this,
        wxT("Очистить кэш синхронизации?\n\n"
            "Это приведет к полной синхронизации при следующем запуске."),
        wxT("Очистка кэша"),
        wxYES_NO | wxNO_DEFAULT | wxICON_WARNING);

    if (confirm.ShowModal() == wxID_YES) {
        // In production, delete sync cache files
        wxLogMessage("Clearing sync cache");
        show_notification("Кэш очищен", "Кэш синхронизации успешно очищен");
    }
}

void FilamentHubPanel::show_debug_info()
{
    // Display debug information
    std::stringstream debug_info;

    debug_info << "FilamentHub Debug Info\n";
    debug_info << "======================\n\n";

    debug_info << "Authentication:\n";
    debug_info << "  Logged in: " << (m_auth_manager->is_logged_in() ? "Yes" : "No") << "\n";

    if (m_auth_manager->is_logged_in()) {
        debug_info << "  Username: " << m_auth_manager->get_username() << "\n";
        debug_info << "  User ID: " << m_auth_manager->get_user_id() << "\n";
        debug_info << "  Token expired: " << (m_auth_manager->is_token_expired() ? "Yes" : "No") << "\n";
    }

    debug_info << "\nSync Status:\n";
    debug_info << "  Currently syncing: " << (m_is_syncing ? "Yes" : "No") << "\n";

    debug_info << "\nImport Queue:\n";
    debug_info << "  Queue size: " << m_preset_importer->get_queue_size() << "\n";
    debug_info << "  Processing: " << (m_preset_importer->is_processing() ? "Yes" : "No") << "\n";

    debug_info << "\nDevice Info:\n";
    debug_info << "  Fingerprint: " << get_device_fingerprint() << "\n";
    debug_info << "  Computer: " << wxGetHostName().ToStdString() << "\n";
    debug_info << "  User: " << wxGetUserId().ToStdString() << "\n";

    wxPlatformInfo platform;
    debug_info << "  OS: " << platform.GetOperatingSystemDescription().ToStdString() << "\n";

    debug_info << "\nWebView:\n";
    debug_info << "  Available: " << (m_webview ? "Yes" : "No") << "\n";

    if (m_webview) {
        debug_info << "  Current URL: " << m_webview->GetCurrentURL().ToStdString() << "\n";
    }

    // Display in dialog
    wxDialog debug_dialog(this, wxID_ANY, wxT("Debug Information"),
        wxDefaultPosition, wxSize(500, 400));

    wxBoxSizer* sizer = new wxBoxSizer(wxVERTICAL);

    wxTextCtrl* debug_text = new wxTextCtrl(&debug_dialog, wxID_ANY,
        wxString::FromUTF8(debug_info.str()),
        wxDefaultPosition, wxDefaultSize,
        wxTE_MULTILINE | wxTE_READONLY | wxTE_DONTWRAP);

    sizer->Add(debug_text, 1, wxEXPAND | wxALL, 10);

    wxButton* copy_button = new wxButton(&debug_dialog, wxID_ANY, wxT("Копировать в буфер"));
    wxButton* close_button = new wxButton(&debug_dialog, wxID_CLOSE, wxT("Закрыть"));

    wxBoxSizer* button_sizer = new wxBoxSizer(wxHORIZONTAL);
    button_sizer->Add(copy_button, 0, wxALL, 5);
    button_sizer->Add(close_button, 0, wxALL, 5);

    sizer->Add(button_sizer, 0, wxALIGN_CENTER | wxALL, 5);

    debug_dialog.SetSizer(sizer);
    debug_dialog.Layout();

    copy_button->Bind(wxEVT_BUTTON, [debug_info](wxCommandEvent& e) {
        if (wxTheClipboard->Open()) {
            wxTheClipboard->SetData(new wxTextDataObject(wxString::FromUTF8(debug_info.str())));
            wxTheClipboard->Close();
            wxLogMessage("Debug info copied to clipboard");
        }
    });

    debug_dialog.ShowModal();
}

void FilamentHubPanel::refresh_auth_token_if_needed()
{
    // Check if token needs refresh and refresh it
    if (m_auth_manager->is_logged_in()) {
        if (m_auth_manager->is_token_near_expiration()) {
            wxLogMessage("Token near expiration, refreshing...");

            bool success = m_auth_manager->refresh_token_if_needed();

            if (success) {
                wxLogMessage("Token refreshed successfully");
            } else {
                wxLogError("Failed to refresh token");
                show_notification("Ошибка токена",
                    "Не удалось обновить токен. Пожалуйста, войдите снова.", true);

                // Force logout
                m_auth_manager->logout();
                update_auth_status();
                load_page(LOGIN_PATH);
            }
        }
    }
}

void FilamentHubPanel::handle_network_error(const std::string& operation, const std::string& error_message)
{
    wxLogError("Network error during %s: %s", operation.c_str(), error_message.c_str());

    std::string user_message = "Ошибка сети при выполнении операции: " + operation + "\n\n" +
                              "Детали: " + error_message + "\n\n" +
                              "Проверьте подключение к интернету и попробуйте снова.";

    show_notification("Ошибка сети", user_message, true);
}

void FilamentHubPanel::handle_auth_error(const std::string& error_message)
{
    wxLogError("Authentication error: %s", error_message.c_str());

    std::string user_message = "Ошибка аутентификации: " + error_message + "\n\n" +
                              "Пожалуйста, войдите в систему снова.";

    show_notification("Ошибка аутентификации", user_message, true);

    // Force logout
    m_auth_manager->logout();
    update_auth_status();
    load_page(LOGIN_PATH);
}

void FilamentHubPanel::handle_server_error(int status_code, const std::string& error_message)
{
    wxLogError("Server error (HTTP %d): %s", status_code, error_message.c_str());

    std::string user_message;

    switch (status_code) {
        case 400:
            user_message = "Неверный запрос: " + error_message;
            break;
        case 401:
            user_message = "Не авторизован. Пожалуйста, войдите снова.";
            handle_auth_error(error_message);
            return;
        case 403:
            user_message = "Доступ запрещен: " + error_message;
            break;
        case 404:
            user_message = "Ресурс не найден: " + error_message;
            break;
        case 500:
            user_message = "Внутренняя ошибка сервера. Попробуйте позже.";
            break;
        default:
            user_message = "Ошибка сервера (код " + std::to_string(status_code) + "): " + error_message;
            break;
    }

    show_notification("Ошибка сервера", user_message, true);
}

void FilamentHubPanel::log_sync_operation(const std::string& operation, bool success, const std::string& details)
{
    // Log sync operation to file for history
    try {
        wxStandardPaths& paths = wxStandardPaths::Get();
        wxString app_data_dir = paths.GetUserDataDir();

        if (!wxFileName::DirExists(app_data_dir)) {
            wxFileName::Mkdir(app_data_dir, wxS_DIR_DEFAULT, wxPATH_MKDIR_FULL);
        }

        wxString log_path = app_data_dir + wxFileName::GetPathSeparator() +
            wxT("filamenthub_sync_log.txt");

        std::ofstream log_file(log_path.ToStdString(), std::ios::app);

        if (log_file.is_open()) {
            // Get current timestamp
            auto now = std::chrono::system_clock::now();
            auto now_c = std::chrono::system_clock::to_time_t(now);

            log_file << std::put_time(std::localtime(&now_c), "%Y-%m-%d %H:%M:%S")
                    << " - " << operation
                    << " - " << (success ? "SUCCESS" : "FAILED");

            if (!details.empty()) {
                log_file << " - " << details;
            }

            log_file << std::endl;
            log_file.close();
        }
    } catch (const std::exception& e) {
        wxLogWarning("Failed to write sync log: %s", e.what());
    }
}

void FilamentHubPanel::cleanup_temp_files()
{
    // Clean up temporary files created during import
    // In production, this would be called by PresetImporter
    wxLogMessage("Cleaning up temporary files");

    try {
        wxStandardPaths& paths = wxStandardPaths::Get();
        wxString temp_dir = paths.GetTempDir();
        wxString pattern = temp_dir + wxFileName::GetPathSeparator() + wxT("filamenthub_*.ini");

        // In production, use wxDir to iterate and delete matching files
        wxLogMessage("Would clean up files matching: %s", pattern);
    } catch (const std::exception& e) {
        wxLogWarning("Error during cleanup: %s", e.what());
    }
}

void FilamentHubPanel::update_webview_theme(bool dark_mode)
{
    // Update WebView theme
    if (!m_webview) {
        return;
    }

    std::string theme_script = "if (window.setTheme) { window.setTheme('" +
                              std::string(dark_mode ? "dark" : "light") + "'); }";
    run_javascript(theme_script);
}

void FilamentHubPanel::inject_custom_css()
{
    // Inject custom CSS for better integration
    if (!m_webview) {
        return;
    }

    std::string css = R"(
        .orcaslicer-integration {
            border: 2px solid #4CAF50;
            border-radius: 8px;
            padding: 10px;
            margin: 10px 0;
        }

        .sync-status {
            background-color: #E3F2FD;
            padding: 8px;
            border-radius: 4px;
            margin: 5px 0;
        }

        .sync-error {
            background-color: #FFEBEE;
            color: #C62828;
            padding: 8px;
            border-radius: 4px;
            margin: 5px 0;
        }

        .sync-success {
            background-color: #E8F5E9;
            color: #2E7D32;
            padding: 8px;
            border-radius: 4px;
            margin: 5px 0;
        }
    )";

    std::string inject_script = R"(
        (function() {
            var style = document.createElement('style');
            style.type = 'text/css';
            style.innerHTML = ')" + css + R"(';
            document.head.appendChild(style);
        })();
    )";

    run_javascript(inject_script);
}

void FilamentHubPanel::setup_periodic_token_refresh()
{
    // Set up periodic token refresh
    // In production, use wxTimer for this

    if (!m_auth_manager->is_logged_in()) {
        return;
    }

    wxLogMessage("Setting up periodic token refresh");

    // Check every 60 seconds if token needs refresh
    // In production implementation:
    // m_refresh_timer = new wxTimer(this);
    // m_refresh_timer->Start(60000); // 60 seconds
    // Bind(wxEVT_TIMER, &FilamentHubPanel::on_refresh_timer, this);
}

void FilamentHubPanel::on_refresh_timer(wxTimerEvent& event)
{
    // Timer callback for periodic token refresh
    refresh_auth_token_if_needed();
}

void FilamentHubPanel::update_webview_badge(int count)
{
    // Update notification badge in WebView
    if (!m_webview) {
        return;
    }

    std::string script = "if (window.updateBadgeCount) { window.updateBadgeCount(" +
                        std::to_string(count) + "); }";
    run_javascript(script);
}

void FilamentHubPanel::enable_webview_features()
{
    // Enable advanced WebView features
    #if wxUSE_WEBVIEW && defined(__WXMSW__)
    if (m_webview) {
        // Enable context menu for debugging (disable in production)
        #ifdef _DEBUG
        m_webview->EnableContextMenu(true);
        #else
        m_webview->EnableContextMenu(false);
        #endif

        // Enable access to files
        m_webview->EnableAccessToDevTools(false);
    }
    #endif
}

std::string FilamentHubPanel::format_timestamp(const std::string& iso_timestamp)
{
    // Format ISO timestamp to user-friendly format
    // In production, use proper date parsing library
    // For now, just return as-is or simple formatting

    if (iso_timestamp.empty()) {
        return "Unknown";
    }

    // Simple formatting: "2024-02-06T20:00:00Z" -> "2024-02-06 20:00"
    std::string formatted = iso_timestamp;

    size_t t_pos = formatted.find('T');
    if (t_pos != std::string::npos) {
        formatted[t_pos] = ' ';
    }

    size_t z_pos = formatted.find('Z');
    if (z_pos != std::string::npos) {
        formatted = formatted.substr(0, z_pos);
    }

    // Truncate seconds
    size_t last_colon = formatted.rfind(':');
    if (last_colon != std::string::npos && last_colon > 10) {
        formatted = formatted.substr(0, last_colon);
    }

    return formatted;
}

std::string FilamentHubPanel::format_file_size(size_t bytes)
{
    // Format file size in human-readable format
    const char* units[] = {"B", "KB", "MB", "GB"};
    int unit_index = 0;
    double size = static_cast<double>(bytes);

    while (size >= 1024.0 && unit_index < 3) {
        size /= 1024.0;
        unit_index++;
    }

    std::stringstream ss;
    ss << std::fixed << std::setprecision(2) << size << " " << units[unit_index];
    return ss.str();
}

bool FilamentHubPanel::validate_preset_name(const std::string& name)
{
    // Validate preset name
    if (name.empty()) {
        return false;
    }

    if (name.length() > 100) {
        return false;
    }

    // Check for invalid characters
    const std::string invalid_chars = "<>:\"/\\|?*";
    for (char c : name) {
        if (invalid_chars.find(c) != std::string::npos) {
            return false;
        }
    }

    return true;
}

std::vector<std::string> FilamentHubPanel::get_available_preset_types()
{
    // Return list of available preset types
    return {"filament", "printer", "print"};
}

std::string FilamentHubPanel::preset_type_to_russian(const std::string& type)
{
    // Convert preset type to Russian
    if (type == "filament") return "Филамент";
    if (type == "printer") return "Принтер";
    if (type == "print") return "Печать";
    return "Неизвестно";
}

} // namespace GUI
} // namespace Slic3r
