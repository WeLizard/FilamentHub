#ifndef slic3r_GUI_FilamentHub_PresetImporter_hpp_
#define slic3r_GUI_FilamentHub_PresetImporter_hpp_

#include <string>
#include <vector>
#include <queue>
#include <memory>
#include <functional>
#include "nlohmann/json.hpp"

namespace Slic3r {
namespace GUI {

// Forward declarations
class AuthManager;

/**
 * @brief Preset import operation result
 */
struct ImportResult {
    bool success;
    std::string preset_name;
    std::string preset_type;
    std::string error_message;
    int preset_id;

    ImportResult() : success(false), preset_id(0) {}
};

/**
 * @brief Queued import task
 */
struct ImportTask {
    nlohmann::json preset_data;
    std::string preset_type;
    int priority;
    bool validate_parent;

    ImportTask() : priority(0), validate_parent(true) {}
};

/**
 * @brief Handles preset download and import operations
 *
 * This class manages:
 * - Downloading preset JSON from backend API
 * - Validating preset data (parent presets, temperature ranges)
 * - Converting JSON to OrcaSlicer preset format
 * - Importing via preset bundle mechanism
 * - Updating .info files for sync tracking
 * - Import queue for batch operations
 *
 * Supports three preset types:
 * - Filament profiles
 * - Printer profiles
 * - Print profiles (process settings)
 */
class PresetImporter
{
public:
    /**
     * @brief Progress callback: (current, total, preset_name) -> void
     */
    using ImportProgressCallback = std::function<void(int, int, const std::string&)>;

    /**
     * @brief Completion callback: (results) -> void
     */
    using ImportCompletionCallback = std::function<void(const std::vector<ImportResult>&)>;

    PresetImporter(AuthManager* auth_manager);
    ~PresetImporter();

    // Single preset import
    ImportResult import_preset(
        const nlohmann::json& preset_data,
        const std::string& preset_type,
        bool validate_parent = true
    );

    // Batch import with queue
    void queue_import(
        const nlohmann::json& preset_data,
        const std::string& preset_type,
        int priority = 0,
        bool validate_parent = true
    );

    void process_queue(
        ImportProgressCallback on_progress,
        ImportCompletionCallback on_complete
    );

    void clear_queue();

    // Queue status
    size_t get_queue_size() const;
    bool is_queue_empty() const;
    bool is_processing() const;

    // Cancel ongoing import
    void cancel_import();

private:
    // Backend API communication
    nlohmann::json download_preset_json(int preset_id, const std::string& preset_type);

    nlohmann::json validate_preset_with_backend(
        const nlohmann::json& preset_data,
        const std::string& preset_type
    );

    // Preset conversion
    std::string convert_to_preset_bundle(
        const nlohmann::json& preset_data,
        const std::string& preset_type
    );

    std::string generate_preset_ini(
        const nlohmann::json& preset_data,
        const std::string& preset_type
    );

    // File operations
    std::string create_temp_preset_file(const std::string& content);
    void cleanup_temp_file(const std::string& file_path);

    // Import via OrcaSlicer API
    bool import_via_preset_bundle(
        const std::string& bundle_path,
        const std::string& preset_type
    );

    // Info file management
    void update_info_file(
        const std::string& preset_name,
        const std::string& preset_type,
        int preset_id,
        const std::string& last_modified
    );

    nlohmann::json read_info_file(
        const std::string& preset_name,
        const std::string& preset_type
    );

    // Validation helpers
    bool validate_parent_preset(
        const nlohmann::json& preset_data,
        const std::string& preset_type,
        std::string& error_message
    );

    bool validate_temperature_ranges(
        const nlohmann::json& preset_data,
        std::string& warning_message
    );

    // Path helpers
    std::string get_preset_directory(const std::string& preset_type) const;
    std::string get_info_file_path(
        const std::string& preset_name,
        const std::string& preset_type
    ) const;
    std::string get_temp_directory() const;

    // Queue processing
    void process_next_task(
        ImportProgressCallback on_progress,
        int current_index,
        int total_count,
        std::vector<ImportResult>& results
    );

    // HTTP helper
    nlohmann::json make_api_request(
        const std::string& method,
        const std::string& endpoint,
        const nlohmann::json& body = nullptr
    );

    // Members
    AuthManager* m_auth_manager;

    // Import queue
    std::queue<ImportTask> m_import_queue;
    bool m_is_processing;
    bool m_cancel_requested;

    // Temp file tracking
    std::vector<std::string> m_temp_files;
};

} // namespace GUI
} // namespace Slic3r

#endif // slic3r_GUI_FilamentHub_PresetImporter_hpp_
