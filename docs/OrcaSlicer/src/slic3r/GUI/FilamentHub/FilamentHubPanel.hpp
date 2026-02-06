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
};

} // namespace GUI
} // namespace Slic3r

#endif // slic3r_GUI_FilamentHubPanel_hpp_
