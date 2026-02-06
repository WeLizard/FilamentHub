#ifndef slic3r_GUI_FilamentHubPanel_hpp_
#define slic3r_GUI_FilamentHubPanel_hpp_

#include <wx/panel.h>
#include <wx/webview.h>
#include <wx/button.h>
#include <wx/gauge.h>
#include <wx/stattext.h>
#include <memory>
#include <string>

namespace Slic3r {
namespace GUI {

// Forward declarations
class AuthManager;
class SyncCoordinator;
class PresetImporter;

/**
 * @brief FilamentHub panel for OrcaSlicer integration
 *
 * This class handles the UI layer for FilamentHub integration,
 * delegating business logic to specialized modules:
 * - AuthManager: Token and authentication management
 * - SyncCoordinator: Sync orchestration using SyncPlan API
 * - PresetImporter: Preset download and import operations
 *
 * Responsibilities:
 * - WebView setup and navigation
 * - Button event handlers
 * - Progress display and notifications
 * - UI state management
 */
class FilamentHubPanel : public wxPanel
{
public:
    FilamentHubPanel(wxWindow* parent);
    ~FilamentHubPanel();

    // UI initialization
    void init_ui();
    void load_page(const std::string& url);

    // Authentication UI handlers
    void on_login_clicked(wxCommandEvent& event);
    void on_logout_clicked(wxCommandEvent& event);
    void update_auth_status();

    // Sync UI handlers
    void on_sync_clicked(wxCommandEvent& event);
    void on_cancel_sync_clicked(wxCommandEvent& event);
    void update_sync_progress(int progress, const std::string& message);

    // Navigation handlers
    void on_navigation_request(wxWebViewEvent& event);
    void on_page_loaded(wxWebViewEvent& event);
    void on_script_message(wxWebViewEvent& event);

    // Notification display
    void show_notification(const std::string& title, const std::string& message, bool is_error = false);
    void show_russian_notification(const std::string& title_key, const std::string& message_key);

    // State queries
    bool is_logged_in() const;
    bool is_syncing() const;

private:
    // UI components
    wxWebView* m_webview;
    wxButton* m_login_button;
    wxButton* m_logout_button;
    wxButton* m_sync_button;
    wxButton* m_cancel_button;
    wxGauge* m_progress_bar;
    wxStaticText* m_status_text;

    // Business logic modules
    std::unique_ptr<AuthManager> m_auth_manager;
    std::unique_ptr<SyncCoordinator> m_sync_coordinator;
    std::unique_ptr<PresetImporter> m_preset_importer;

    // State flags
    bool m_is_syncing;
    bool m_sync_cancelled;

    // Helper methods
    void setup_webview();
    void setup_buttons();
    void bind_events();
    void update_button_states();
    void run_javascript(const std::string& script);
    std::string get_device_fingerprint() const;

    // Layout
    void create_layout();

    // Advanced features
    void sync_preset_type(PresetType type);
    void sync_all_presets();
    void show_preset_details(const nlohmann::json& preset_data);
    void handle_conflict_resolution(const std::vector<nlohmann::json>& conflicts);
    void apply_server_preset(const nlohmann::json& preset_data);
    void keep_local_preset(const nlohmann::json& preset_data);
    void handle_deleted_presets_ui(const std::vector<nlohmann::json>& deleted);
    void delete_local_presets(const std::vector<nlohmann::json>& presets);
    void ask_for_each_deleted_preset(const std::vector<nlohmann::json>& presets);

    // Settings and preferences
    void show_sync_settings();
    void save_sync_preferences(bool auto_sync, int conflict_strategy, int deleted_strategy);
    nlohmann::json load_sync_preferences();

    // Preset management
    void show_preset_browser();
    void show_sync_history();
    void export_presets_to_server();
    void check_for_updates();
    void validate_local_presets();
    void clear_sync_cache();
    void show_debug_info();

    // Token and error handling
    void refresh_auth_token_if_needed();
    void handle_network_error(const std::string& operation, const std::string& error_message);
    void handle_auth_error(const std::string& error_message);
    void handle_server_error(int status_code, const std::string& error_message);

    // Logging and utilities
    void log_sync_operation(const std::string& operation, bool success, const std::string& details);
    void cleanup_temp_files();
    void update_webview_theme(bool dark_mode);
    void inject_custom_css();
    void setup_periodic_token_refresh();
    void on_refresh_timer(wxTimerEvent& event);
    void update_webview_badge(int count);
    void enable_webview_features();

    // Formatting utilities
    std::string format_timestamp(const std::string& iso_timestamp);
    std::string format_file_size(size_t bytes);
    bool validate_preset_name(const std::string& name);
    std::vector<std::string> get_available_preset_types();
    std::string preset_type_to_russian(const std::string& type);
};

} // namespace GUI
} // namespace Slic3r

#endif // slic3r_GUI_FilamentHubPanel_hpp_
