#ifndef slic3r_GUI_FilamentHub_SyncCoordinator_hpp_
#define slic3r_GUI_FilamentHub_SyncCoordinator_hpp_

#include <string>
#include <vector>
#include <memory>
#include <functional>
#include "nlohmann/json.hpp"

namespace Slic3r {
namespace GUI {

// Forward declarations
class AuthManager;
class PresetImporter;
class BoostThreadWorker;

/**
 * @brief Preset type enumeration
 */
enum class PresetType {
    Filament,
    Printer,
    Print
};

/**
 * @brief Sync plan structure returned from backend API
 */
struct SyncPlan {
    std::vector<nlohmann::json> to_download;
    std::vector<nlohmann::json> deleted_on_server;
    std::vector<nlohmann::json> conflicts;
    int sync_version;
    std::string device_fingerprint;
};

/**
 * @brief Coordinates synchronization with FilamentHub backend
 *
 * This class orchestrates the sync process using the new SyncPlan API:
 * 1. Requests sync plan from backend (POST /sync-plan)
 * 2. Processes to_download presets via PresetImporter
 * 3. Handles deleted_on_server presets according to user preferences
 * 4. Manages conflict resolution
 *
 * Uses BoostThreadWorker pattern for async operations instead of raw std::async.
 */
class SyncCoordinator
{
public:
    /**
     * @brief Progress callback: (progress_percent, status_message) -> void
     */
    using ProgressCallback = std::function<void(int, const std::string&)>;

    /**
     * @brief Completion callback: (success, error_message) -> void
     */
    using CompletionCallback = std::function<void(bool, const std::string&)>;

    SyncCoordinator(
        AuthManager* auth_manager,
        PresetImporter* preset_importer,
        BoostThreadWorker* worker
    );
    ~SyncCoordinator();

    // Unified sync function for all preset types
    void synchronize(
        PresetType type,
        bool force_full_sync,
        ProgressCallback on_progress,
        CompletionCallback on_complete
    );

    // Cancel ongoing sync
    void cancel_sync();

    // Query sync state
    bool is_syncing() const;
    PresetType get_current_sync_type() const;

private:
    // Backend API communication
    SyncPlan request_sync_plan(
        PresetType type,
        const std::string& device_fingerprint,
        bool force_full_sync
    );

    std::vector<nlohmann::json> request_deleted_presets(
        PresetType type,
        const std::string& device_fingerprint
    );

    void report_sync_status(
        PresetType type,
        const std::string& device_fingerprint,
        bool success,
        const std::string& error_message
    );

    // Sync plan processing
    void process_sync_plan(
        const SyncPlan& plan,
        PresetType type,
        ProgressCallback on_progress
    );

    void handle_deleted_presets(
        const std::vector<nlohmann::json>& deleted,
        PresetType type
    );

    void handle_conflicts(
        const std::vector<nlohmann::json>& conflicts,
        PresetType type
    );

    // Helper methods
    std::string preset_type_to_string(PresetType type) const;
    std::string get_api_endpoint(const std::string& path) const;
    int get_current_sync_version(PresetType type) const;
    void update_sync_version(PresetType type, int version);

    // HTTP request helper
    nlohmann::json make_api_request(
        const std::string& method,
        const std::string& endpoint,
        const nlohmann::json& body = nullptr
    );

    // Members
    AuthManager* m_auth_manager;
    PresetImporter* m_preset_importer;
    BoostThreadWorker* m_worker;

    // State
    bool m_is_syncing;
    bool m_cancel_requested;
    PresetType m_current_sync_type;
    int m_current_progress;
};

} // namespace GUI
} // namespace Slic3r

#endif // slic3r_GUI_FilamentHub_SyncCoordinator_hpp_
