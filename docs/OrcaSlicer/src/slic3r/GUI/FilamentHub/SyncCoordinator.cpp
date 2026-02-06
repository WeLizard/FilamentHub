#include "SyncCoordinator.hpp"
#include "AuthManager.hpp"
#include "PresetImporter.hpp"
#include <fstream>
#include <sstream>
#include <wx/stdpaths.h>
#include <wx/filename.h>
#include <wx/log.h>
#include <boost/beast/core.hpp>
#include <boost/beast/http.hpp>
#include <boost/beast/version.hpp>
#include <boost/asio/connect.hpp>
#include <boost/asio/ip/tcp.hpp>

namespace beast = boost::beast;
namespace http = beast::http;
namespace net = boost::asio;
using tcp = boost::asio::ip::tcp;

namespace Slic3r {
namespace GUI {

// Constants
namespace {
    const char* API_HOST = "localhost";
    const char* API_PORT = "8000";
    const char* API_SYNC_PLAN_ENDPOINT = "/api/v1/orcaslicer/sync-plan";
    const char* API_DELETED_PRESETS_ENDPOINT = "/api/v1/orcaslicer/deleted-presets";
    const char* API_SYNC_STATUS_ENDPOINT = "/api/v1/orcaslicer/sync-status";
    const char* CONFIG_FILENAME = "filamenthub_sync.json";
}

// SyncJob class - implements async sync operation using Job pattern
class SyncJob : public Slic3r::GUI::Job {
public:
    SyncJob(
        SyncCoordinator* coordinator,
        PresetType type,
        bool force_full_sync,
        SyncCoordinator::ProgressCallback on_progress,
        SyncCoordinator::CompletionCallback on_complete
    )
        : m_coordinator(coordinator)
        , m_type(type)
        , m_force_full_sync(force_full_sync)
        , m_on_progress(on_progress)
        , m_on_complete(on_complete)
    {
    }

    void process(Ctl& ctl) override {
        try {
            // Step 1: Request sync plan (10%)
            if (ctl.was_canceled()) return;

            ctl.update_status(10, "Requesting sync plan...");
            update_progress_callback(10, "Requesting sync plan...");

            SyncPlan plan = m_coordinator->request_sync_plan(
                m_type,
                m_coordinator->get_device_fingerprint(),
                m_force_full_sync
            );

            // Step 2: Process deleted presets (20%)
            if (ctl.was_canceled()) return;

            ctl.update_status(20, "Processing deleted presets...");
            update_progress_callback(20, "Processing deleted presets...");

            if (!plan.deleted_on_server.empty()) {
                m_coordinator->handle_deleted_presets(plan.deleted_on_server, m_type);
            }

            // Step 3: Process conflicts (30%)
            if (ctl.was_canceled()) return;

            ctl.update_status(30, "Checking conflicts...");
            update_progress_callback(30, "Checking conflicts...");

            if (!plan.conflicts.empty()) {
                m_coordinator->handle_conflicts(plan.conflicts, m_type);
            }

            // Step 4: Download presets (40-90%)
            if (ctl.was_canceled()) return;

            ctl.update_status(40, "Downloading presets...");
            update_progress_callback(40, "Downloading presets...");

            if (!plan.to_download.empty()) {
                m_coordinator->process_sync_plan(plan, m_type, [this, &ctl](int progress, const std::string& status) {
                    if (ctl.was_canceled()) return;
                    // Map progress from 40-90%
                    int mapped_progress = 40 + (progress * 50 / 100);
                    ctl.update_status(mapped_progress, status);
                    update_progress_callback(mapped_progress, status);
                });
            }

            // Step 5: Update sync version (95%)
            if (ctl.was_canceled()) return;

            ctl.update_status(95, "Updating sync status...");
            update_progress_callback(95, "Updating sync status...");

            m_coordinator->update_sync_version(m_type, plan.sync_version);

            // Step 6: Report success (100%)
            ctl.update_status(100, "Sync complete");
            update_progress_callback(100, "Sync complete");

            m_coordinator->report_sync_status(m_type, plan.device_fingerprint, true, "");

        } catch (const std::exception& e) {
            wxLogError("FilamentHub: Sync job failed: %s", e.what());
            ctl.show_error_info(e.what(), -1, "Sync failed", "");
            throw; // Re-throw to pass to finalize()
        }
    }

    void finalize(bool canceled, std::exception_ptr& eptr) override {
        // Determine success: not canceled and no exception
        bool success = !canceled && !eptr;
        std::string error_message;

        if (eptr) {
            try {
                std::rethrow_exception(eptr);
            } catch (const std::exception& e) {
                error_message = e.what();
            } catch (...) {
                error_message = "Unknown error";
            }
            // Set to nullptr to prevent rethrow
            eptr = nullptr;
        } else if (canceled) {
            error_message = "Sync canceled";
        }

        // Call completion callback on main thread
        if (m_on_complete) {
            m_on_complete(success, error_message);
        }
    }

private:
    void update_progress_callback(int percent, const std::string& message) {
        if (m_on_progress) {
            m_on_progress(percent, message);
        }
    }

    SyncCoordinator* m_coordinator;
    PresetType m_type;
    bool m_force_full_sync;
    SyncCoordinator::ProgressCallback m_on_progress;
    SyncCoordinator::CompletionCallback m_on_complete;
};

// SyncCoordinator implementation
SyncCoordinator::SyncCoordinator(
    AuthManager* auth_manager,
    PresetImporter* preset_importer,
    BoostThreadWorker* worker)
    : m_auth_manager(auth_manager)
    , m_preset_importer(preset_importer)
    , m_worker(worker)
    , m_is_syncing(false)
    , m_cancel_requested(false)
    , m_current_sync_type(PresetType::Filament)
    , m_current_progress(0)
{
    if (!m_auth_manager) {
        throw std::invalid_argument("AuthManager cannot be null");
    }
    if (!m_preset_importer) {
        throw std::invalid_argument("PresetImporter cannot be null");
    }
    if (!m_worker) {
        throw std::invalid_argument("BoostThreadWorker cannot be null");
    }
}

SyncCoordinator::~SyncCoordinator()
{
    if (m_is_syncing) {
        cancel_sync();
    }
}

// Unified sync function for all preset types
void SyncCoordinator::synchronize(
    PresetType type,
    bool force_full_sync,
    ProgressCallback on_progress,
    CompletionCallback on_complete)
{
    if (m_is_syncing) {
        wxLogWarning("FilamentHub: Sync already in progress");
        if (on_complete) {
            on_complete(false, "Sync already in progress");
        }
        return;
    }

    // Check authentication
    if (!m_auth_manager->is_logged_in()) {
        wxLogError("FilamentHub: Not logged in");
        if (on_complete) {
            on_complete(false, "Not logged in");
        }
        return;
    }

    wxLogMessage("FilamentHub: Starting %s sync (force_full=%d)",
                 preset_type_to_string(type), force_full_sync);

    m_is_syncing = true;
    m_cancel_requested = false;
    m_current_sync_type = type;
    m_current_progress = 0;

    // Create and execute sync job
    // Note: We're not using BoostThreadWorker's Job pattern here
    // because the actual BoostThreadWorker implementation is not available
    // in this codebase. Instead, we'll use std::async as a fallback.
    auto job = std::make_shared<SyncJob>(this, type, force_full_sync, on_progress, on_complete);

    // Execute async
    std::async(std::launch::async, [this, job]() {
        job->execute();
        m_is_syncing = false;
    });
}

// Cancel ongoing sync
void SyncCoordinator::cancel_sync()
{
    if (!m_is_syncing) {
        return;
    }

    wxLogMessage("FilamentHub: Canceling sync");
    m_cancel_requested = true;
    // Note: Actual cancellation will be handled by the job
}

// Query sync state
bool SyncCoordinator::is_syncing() const
{
    return m_is_syncing;
}

PresetType SyncCoordinator::get_current_sync_type() const
{
    return m_current_sync_type;
}

// Backend API communication
SyncPlan SyncCoordinator::request_sync_plan(
    PresetType type,
    const std::string& device_fingerprint,
    bool force_full_sync)
{
    try {
        wxLogMessage("FilamentHub: Requesting sync plan for %s", preset_type_to_string(type));

        // Prepare request body
        nlohmann::json request_body;
        request_body["device_fingerprint"] = device_fingerprint;
        request_body["preset_type"] = preset_type_to_string(type);
        request_body["force_full_sync"] = force_full_sync;

        if (!force_full_sync) {
            int current_version = get_current_sync_version(type);
            request_body["last_sync_version"] = current_version;
        }

        // Make API request
        nlohmann::json response = make_api_request("POST", API_SYNC_PLAN_ENDPOINT, request_body);

        // Parse response into SyncPlan
        SyncPlan plan;

        if (response.contains("to_download") && response["to_download"].is_array()) {
            for (const auto& item : response["to_download"]) {
                plan.to_download.push_back(item);
            }
        }

        if (response.contains("deleted_on_server") && response["deleted_on_server"].is_array()) {
            for (const auto& item : response["deleted_on_server"]) {
                plan.deleted_on_server.push_back(item);
            }
        }

        if (response.contains("conflicts") && response["conflicts"].is_array()) {
            for (const auto& item : response["conflicts"]) {
                plan.conflicts.push_back(item);
            }
        }

        if (response.contains("sync_version")) {
            plan.sync_version = response["sync_version"].get<int>();
        }

        if (response.contains("device_fingerprint")) {
            plan.device_fingerprint = response["device_fingerprint"].get<std::string>();
        }

        wxLogMessage("FilamentHub: Sync plan received - to_download: %zu, deleted: %zu, conflicts: %zu",
                     plan.to_download.size(), plan.deleted_on_server.size(), plan.conflicts.size());

        return plan;

    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Failed to request sync plan: %s", e.what());
        throw;
    }
}

std::vector<nlohmann::json> SyncCoordinator::request_deleted_presets(
    PresetType type,
    const std::string& device_fingerprint)
{
    try {
        wxLogMessage("FilamentHub: Requesting deleted presets for %s", preset_type_to_string(type));

        nlohmann::json request_body;
        request_body["device_fingerprint"] = device_fingerprint;
        request_body["preset_type"] = preset_type_to_string(type);

        nlohmann::json response = make_api_request("POST", API_DELETED_PRESETS_ENDPOINT, request_body);

        std::vector<nlohmann::json> deleted_presets;
        if (response.contains("deleted_presets") && response["deleted_presets"].is_array()) {
            for (const auto& item : response["deleted_presets"]) {
                deleted_presets.push_back(item);
            }
        }

        return deleted_presets;

    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Failed to request deleted presets: %s", e.what());
        return {};
    }
}

void SyncCoordinator::report_sync_status(
    PresetType type,
    const std::string& device_fingerprint,
    bool success,
    const std::string& error_message)
{
    try {
        nlohmann::json request_body;
        request_body["device_fingerprint"] = device_fingerprint;
        request_body["preset_type"] = preset_type_to_string(type);
        request_body["success"] = success;

        if (!error_message.empty()) {
            request_body["error_message"] = error_message;
        }

        request_body["sync_version"] = get_current_sync_version(type);

        make_api_request("POST", API_SYNC_STATUS_ENDPOINT, request_body);

        wxLogMessage("FilamentHub: Sync status reported (success=%d)", success);

    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Failed to report sync status: %s", e.what());
        // Don't throw - reporting failure shouldn't break the sync
    }
}

// Sync plan processing
void SyncCoordinator::process_sync_plan(
    const SyncPlan& plan,
    PresetType type,
    ProgressCallback on_progress)
{
    try {
        if (plan.to_download.empty()) {
            wxLogMessage("FilamentHub: No presets to download");
            return;
        }

        wxLogMessage("FilamentHub: Processing %zu presets for download", plan.to_download.size());

        std::string preset_type_str = preset_type_to_string(type);
        size_t total = plan.to_download.size();
        size_t completed = 0;

        for (const auto& preset_data : plan.to_download) {
            if (m_cancel_requested) {
                wxLogMessage("FilamentHub: Download canceled");
                break;
            }

            try {
                // Import preset
                ImportResult result = m_preset_importer->import_preset(
                    preset_data,
                    preset_type_str,
                    true  // validate parent
                );

                if (!result.error_message.empty()) {
                    wxLogError("FilamentHub: Failed to import preset '%s': %s",
                              result.preset_name, result.error_message);
                } else {
                    wxLogMessage("FilamentHub: Successfully imported preset '%s'",
                                result.preset_name);
                }

                completed++;

                // Update progress
                if (on_progress) {
                    int progress = (completed * 100) / total;
                    std::string status = "Downloaded " + std::to_string(completed) +
                                       " of " + std::to_string(total) + " presets";
                    on_progress(progress, status);
                }

            } catch (const std::exception& e) {
                wxLogError("FilamentHub: Exception while importing preset: %s", e.what());
                // Continue with next preset
            }
        }

        wxLogMessage("FilamentHub: Completed importing %zu/%zu presets", completed, total);

    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Failed to process sync plan: %s", e.what());
        throw;
    }
}

void SyncCoordinator::handle_deleted_presets(
    const std::vector<nlohmann::json>& deleted,
    PresetType type)
{
    try {
        if (deleted.empty()) {
            return;
        }

        wxLogMessage("FilamentHub: Handling %zu deleted presets", deleted.size());

        // TODO: Implement user preference-based deletion handling
        // For now, just log the deleted presets
        for (const auto& preset : deleted) {
            std::string preset_name = "unknown";
            if (preset.contains("name")) {
                preset_name = preset["name"].get<std::string>();
            } else if (preset.contains("preset_name")) {
                preset_name = preset["preset_name"].get<std::string>();
            }

            bool was_created_by_user = false;
            if (preset.contains("was_created_by_user")) {
                was_created_by_user = preset["was_created_by_user"].get<bool>();
            }

            bool was_saved_by_user = false;
            if (preset.contains("was_saved_by_user")) {
                was_saved_by_user = preset["was_saved_by_user"].get<bool>();
            }

            wxLogMessage("FilamentHub: Deleted preset '%s' (created_by_user=%d, saved_by_user=%d)",
                        preset_name, was_created_by_user, was_saved_by_user);
        }

        // TODO: Based on user preferences:
        // - Auto-delete if not created/saved by user
        // - Show confirmation dialog if created/saved by user
        // - Apply saved rules from previous choices

    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Failed to handle deleted presets: %s", e.what());
    }
}

void SyncCoordinator::handle_conflicts(
    const std::vector<nlohmann::json>& conflicts,
    PresetType type)
{
    try {
        if (conflicts.empty()) {
            return;
        }

        wxLogMessage("FilamentHub: Handling %zu conflicts", conflicts.size());

        // TODO: Implement conflict resolution
        // For now, just log the conflicts
        for (const auto& conflict : conflicts) {
            std::string preset_name = "unknown";
            if (conflict.contains("name")) {
                preset_name = conflict["name"].get<std::string>();
            }

            std::string conflict_type = "unknown";
            if (conflict.contains("conflict_type")) {
                conflict_type = conflict["conflict_type"].get<std::string>();
            }

            wxLogWarning("FilamentHub: Conflict in preset '%s': %s",
                        preset_name, conflict_type);
        }

        // TODO: Show conflict resolution UI
        // - Show diff between local and server versions
        // - Allow user to choose: keep local, use server, or merge
        // - Save resolution preference for future conflicts

    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Failed to handle conflicts: %s", e.what());
    }
}

// Helper methods
std::string SyncCoordinator::preset_type_to_string(PresetType type) const
{
    switch (type) {
        case PresetType::Filament:
            return "filament";
        case PresetType::Printer:
            return "printer";
        case PresetType::Print:
            return "print";
        default:
            return "unknown";
    }
}

std::string SyncCoordinator::get_api_endpoint(const std::string& path) const
{
    return path;
}

int SyncCoordinator::get_current_sync_version(PresetType type) const
{
    try {
        std::string config_path = get_config_file_path();
        std::ifstream config_file(config_path);

        if (!config_file.is_open()) {
            return 0;  // No previous sync
        }

        nlohmann::json config;
        config_file >> config;
        config_file.close();

        std::string type_key = preset_type_to_string(type) + "_version";
        if (config.contains(type_key)) {
            return config[type_key].get<int>();
        }

        return 0;

    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Failed to get current sync version: %s", e.what());
        return 0;
    }
}

void SyncCoordinator::update_sync_version(PresetType type, int version)
{
    try {
        std::string config_path = get_config_file_path();

        // Load existing config
        nlohmann::json config;
        std::ifstream config_file(config_path);
        if (config_file.is_open()) {
            config_file >> config;
            config_file.close();
        }

        // Update version
        std::string type_key = preset_type_to_string(type) + "_version";
        config[type_key] = version;

        // Ensure directory exists
        wxFileName fn(config_path);
        wxFileName::Mkdir(fn.GetPath(), wxS_DIR_DEFAULT, wxPATH_MKDIR_FULL);

        // Save config
        std::ofstream out_file(config_path);
        if (out_file.is_open()) {
            out_file << config.dump(2);
            out_file.close();
            wxLogMessage("FilamentHub: Updated sync version for %s to %d",
                        preset_type_to_string(type), version);
        }

    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Failed to update sync version: %s", e.what());
    }
}

std::string SyncCoordinator::get_config_file_path() const
{
    wxStandardPaths& std_paths = wxStandardPaths::Get();
    wxString user_data_dir = std_paths.GetUserDataDir();

    wxFileName config_file(user_data_dir, CONFIG_FILENAME);
    return config_file.GetFullPath().ToStdString();
}

std::string SyncCoordinator::get_device_fingerprint() const
{
    // Generate or retrieve device fingerprint
    // For now, use a simple approach based on username and hostname
    try {
        std::string config_path = get_config_file_path();
        std::ifstream config_file(config_path);

        if (config_file.is_open()) {
            nlohmann::json config;
            config_file >> config;
            config_file.close();

            if (config.contains("device_fingerprint")) {
                return config["device_fingerprint"].get<std::string>();
            }
        }

        // Generate new fingerprint
        std::string username = m_auth_manager->get_username();
        wxString hostname = wxGetHostName();

        std::string fingerprint = username + "_" + hostname.ToStdString();

        // Save it
        nlohmann::json config;
        if (config_file.is_open()) {
            config_file >> config;
        }
        config["device_fingerprint"] = fingerprint;

        // Ensure directory exists
        wxFileName fn(config_path);
        wxFileName::Mkdir(fn.GetPath(), wxS_DIR_DEFAULT, wxPATH_MKDIR_FULL);

        std::ofstream out_file(config_path);
        if (out_file.is_open()) {
            out_file << config.dump(2);
            out_file.close();
        }

        return fingerprint;

    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Failed to get device fingerprint: %s", e.what());
        return "unknown_device";
    }
}

// HTTP request helper
nlohmann::json SyncCoordinator::make_api_request(
    const std::string& method,
    const std::string& endpoint,
    const nlohmann::json& body)
{
    try {
        std::string host = API_HOST;
        std::string port = API_PORT;

        net::io_context ioc;
        tcp::resolver resolver(ioc);
        beast::tcp_stream stream(ioc);

        // Look up the domain name
        auto const results = resolver.resolve(host, port);

        // Make the connection
        stream.connect(results);

        // Set up the HTTP request
        http::request<http::string_body> req;

        if (method == "POST") {
            req.method(http::verb::post);
        } else if (method == "GET") {
            req.method(http::verb::get);
        } else if (method == "PUT") {
            req.method(http::verb::put);
        } else if (method == "DELETE") {
            req.method(http::verb::delete_);
        } else {
            throw std::runtime_error("Unsupported HTTP method: " + method);
        }

        req.target(endpoint);
        req.version(11);
        req.set(http::field::host, host);
        req.set(http::field::user_agent, "OrcaSlicer-FilamentHub/1.0");
        req.set(http::field::content_type, "application/json");

        // Add authentication header
        std::string token = m_auth_manager->get_token();
        if (!token.empty()) {
            req.set(http::field::authorization, "Bearer " + token);
        }

        // Add body if present
        if (body != nullptr && !body.is_null()) {
            std::string body_str = body.dump();
            req.body() = body_str;
            req.prepare_payload();
        }

        // Send the HTTP request
        http::write(stream, req);

        // Receive the HTTP response
        beast::flat_buffer buffer;
        http::response<http::string_body> res;
        http::read(stream, buffer, res);

        // Gracefully close the socket
        beast::error_code ec;
        stream.socket().shutdown(tcp::socket::shutdown_both, ec);

        // Check response status
        if (res.result() != http::status::ok) {
            std::string error_msg = "HTTP request failed with status: " +
                                   std::to_string(res.result_int());

            // Try to include response body in error message
            if (!res.body().empty()) {
                error_msg += " - " + res.body().substr(0, 200);
            }

            throw std::runtime_error(error_msg);
        }

        // Parse JSON response
        return nlohmann::json::parse(res.body());

    } catch (const std::exception& e) {
        wxLogError("FilamentHub: API request failed: %s", e.what());
        throw;
    }
}

} // namespace GUI
} // namespace Slic3r
