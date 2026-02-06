#include "PresetImporter.hpp"
#include "AuthManager.hpp"
#include <fstream>
#include <sstream>
#include <iomanip>
#include <algorithm>
#include <wx/stdpaths.h>
#include <wx/filename.h>
#include <wx/log.h>
#include <wx/utils.h>
#include <boost/beast/core.hpp>
#include <boost/beast/http.hpp>
#include <boost/beast/version.hpp>
#include <boost/asio/connect.hpp>
#include <boost/asio/ip/tcp.hpp>
#include <boost/algorithm/string.hpp>

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
    const char* API_PRESETS_ENDPOINT = "/api/v1/orcaslicer/presets";
    const char* API_VALIDATE_BATCH_ENDPOINT = "/api/v1/orcaslicer/validate-batch";

    // Preset type to directory mapping
    const char* FILAMENT_DIR = "filament";
    const char* PRINTER_DIR = "printer";
    const char* PRINT_DIR = "print";

    // Default parent presets (fallbacks)
    const char* DEFAULT_FILAMENT_PARENT = "Generic PLA @System";
    const char* DEFAULT_PRINTER_PARENT = "Generic Printer @System";
    const char* DEFAULT_PRINT_PARENT = "0.20mm Standard @System";

    // Temperature validation ranges
    struct TempRange {
        int min;
        int max;
        const char* name;
    };

    const TempRange NOZZLE_TEMP_RANGE = {160, 300, "nozzle temperature"};
    const TempRange BED_TEMP_RANGE = {0, 120, "bed temperature"};
    const TempRange CHAMBER_TEMP_RANGE = {0, 65, "chamber temperature"};
}

PresetImporter::PresetImporter(AuthManager* auth_manager)
    : m_auth_manager(auth_manager)
    , m_is_processing(false)
    , m_cancel_requested(false)
{
    if (!m_auth_manager) {
        throw std::invalid_argument("AuthManager cannot be null");
    }
}

PresetImporter::~PresetImporter()
{
    // Clean up any remaining temp files
    for (const auto& temp_file : m_temp_files) {
        cleanup_temp_file(temp_file);
    }
    m_temp_files.clear();
}

// Single preset import
ImportResult PresetImporter::import_preset(
    const nlohmann::json& preset_data,
    const std::string& preset_type,
    bool validate_parent)
{
    ImportResult result;
    result.preset_type = preset_type;

    try {
        // Extract preset name and ID
        if (!preset_data.contains("name") || !preset_data.contains("id")) {
            result.error_message = "Missing required fields: name or id";
            return result;
        }

        result.preset_name = preset_data["name"].get<std::string>();
        result.preset_id = preset_data["id"].get<int>();

        wxLogMessage("FilamentHub: Importing %s preset: %s (ID: %d)",
                     preset_type, result.preset_name, result.preset_id);

        // Validate parent preset if requested
        if (validate_parent) {
            std::string error_msg;
            if (!validate_parent_preset(preset_data, preset_type, error_msg)) {
                result.error_message = error_msg;
                wxLogWarning("FilamentHub: Parent validation failed: %s", error_msg);
                return result;
            }
        }

        // Validate temperature ranges (warning only)
        std::string warning_msg;
        if (!validate_temperature_ranges(preset_data, warning_msg)) {
            wxLogWarning("FilamentHub: Temperature validation warning: %s", warning_msg);
            // Continue with import despite warnings
        }

        // Convert to preset bundle format
        std::string bundle_content = convert_to_preset_bundle(preset_data, preset_type);

        // Create temporary file
        std::string temp_file = create_temp_preset_file(bundle_content);

        // Import via OrcaSlicer preset bundle API
        if (!import_via_preset_bundle(temp_file, preset_type)) {
            cleanup_temp_file(temp_file);
            result.error_message = "Failed to import preset bundle";
            return result;
        }

        // Update .info file for sync tracking
        std::string last_modified = preset_data.contains("last_modified")
            ? preset_data["last_modified"].get<std::string>()
            : "";
        update_info_file(result.preset_name, preset_type, result.preset_id, last_modified);

        // Cleanup temp file
        cleanup_temp_file(temp_file);

        result.success = true;
        wxLogMessage("FilamentHub: Successfully imported preset: %s", result.preset_name);

    } catch (const std::exception& e) {
        result.error_message = std::string("Import exception: ") + e.what();
        wxLogError("FilamentHub: Import failed: %s", e.what());
    }

    return result;
}

// Batch import with queue
void PresetImporter::queue_import(
    const nlohmann::json& preset_data,
    const std::string& preset_type,
    int priority,
    bool validate_parent)
{
    ImportTask task;
    task.preset_data = preset_data;
    task.preset_type = preset_type;
    task.priority = priority;
    task.validate_parent = validate_parent;

    m_import_queue.push(task);

    wxLogMessage("FilamentHub: Queued import for %s preset (queue size: %zu)",
                 preset_type, m_import_queue.size());
}

void PresetImporter::process_queue(
    ImportProgressCallback on_progress,
    ImportCompletionCallback on_complete)
{
    if (m_is_processing) {
        wxLogWarning("FilamentHub: Import queue is already being processed");
        return;
    }

    m_is_processing = true;
    m_cancel_requested = false;

    std::vector<ImportResult> results;
    int total_count = static_cast<int>(m_import_queue.size());
    int current_index = 0;

    wxLogMessage("FilamentHub: Processing import queue (%d presets)", total_count);

    while (!m_import_queue.empty() && !m_cancel_requested) {
        ImportTask task = m_import_queue.front();
        m_import_queue.pop();

        current_index++;

        // Extract preset name for progress callback
        std::string preset_name = task.preset_data.contains("name")
            ? task.preset_data["name"].get<std::string>()
            : "Unknown";

        // Progress callback
        if (on_progress) {
            on_progress(current_index, total_count, preset_name);
        }

        // Import the preset
        ImportResult result = import_preset(
            task.preset_data,
            task.preset_type,
            task.validate_parent
        );

        results.push_back(result);

        // Small delay between imports to prevent overwhelming the system
        wxMilliSleep(50);
    }

    m_is_processing = false;

    // Clear any remaining items if cancelled
    if (m_cancel_requested) {
        while (!m_import_queue.empty()) {
            m_import_queue.pop();
        }
        wxLogMessage("FilamentHub: Import queue processing cancelled");
    }

    // Completion callback
    if (on_complete) {
        on_complete(results);
    }

    wxLogMessage("FilamentHub: Completed processing %zu presets (%zu successful)",
                 results.size(),
                 std::count_if(results.begin(), results.end(),
                              [](const ImportResult& r) { return r.success; }));
}

void PresetImporter::clear_queue()
{
    while (!m_import_queue.empty()) {
        m_import_queue.pop();
    }
    wxLogMessage("FilamentHub: Import queue cleared");
}

// Queue status
size_t PresetImporter::get_queue_size() const
{
    return m_import_queue.size();
}

bool PresetImporter::is_queue_empty() const
{
    return m_import_queue.empty();
}

bool PresetImporter::is_processing() const
{
    return m_is_processing;
}

void PresetImporter::cancel_import()
{
    m_cancel_requested = true;
    wxLogMessage("FilamentHub: Import cancellation requested");
}

// Backend API communication
nlohmann::json PresetImporter::download_preset_json(int preset_id, const std::string& preset_type)
{
    try {
        std::string endpoint = std::string(API_PRESETS_ENDPOINT) + "/" +
                               std::to_string(preset_id) +
                               "?preset_type=" + preset_type;

        nlohmann::json response = make_api_request("GET", endpoint);

        wxLogMessage("FilamentHub: Downloaded preset JSON for ID: %d", preset_id);
        return response;

    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Failed to download preset JSON: %s", e.what());
        throw;
    }
}

nlohmann::json PresetImporter::validate_preset_with_backend(
    const nlohmann::json& preset_data,
    const std::string& preset_type)
{
    try {
        nlohmann::json request_body;
        request_body["presets"] = nlohmann::json::array();

        nlohmann::json preset_item;
        preset_item["name"] = preset_data["name"];
        preset_item["parent"] = preset_data.value("inherits", "");
        preset_item["preset_type"] = preset_type;

        // Add temperature fields if present
        if (preset_data.contains("temperature")) {
            preset_item["temperature"] = preset_data["temperature"];
        }
        if (preset_data.contains("bed_temperature")) {
            preset_item["bed_temperature"] = preset_data["bed_temperature"];
        }

        request_body["presets"].push_back(preset_item);

        nlohmann::json response = make_api_request("POST", API_VALIDATE_BATCH_ENDPOINT, request_body);

        wxLogMessage("FilamentHub: Validated preset with backend");
        return response;

    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Backend validation failed: %s", e.what());
        throw;
    }
}

// Preset conversion
std::string PresetImporter::convert_to_preset_bundle(
    const nlohmann::json& preset_data,
    const std::string& preset_type)
{
    std::ostringstream bundle;

    // Bundle header
    bundle << "# OrcaSlicer Preset Bundle\n";
    bundle << "# Generated by FilamentHub\n";
    bundle << "# Preset Type: " << preset_type << "\n";
    bundle << "\n";

    // Generate preset INI section
    std::string preset_ini = generate_preset_ini(preset_data, preset_type);
    bundle << preset_ini;

    return bundle.str();
}

std::string PresetImporter::generate_preset_ini(
    const nlohmann::json& preset_data,
    const std::string& preset_type)
{
    std::ostringstream ini;

    // Section header
    std::string preset_name = preset_data["name"].get<std::string>();
    ini << "[" << preset_type << ":" << preset_name << "]\n";

    // Iterate through preset settings
    if (preset_data.contains("settings")) {
        nlohmann::json settings = preset_data["settings"];

        for (auto it = settings.begin(); it != settings.end(); ++it) {
            std::string key = it.key();

            // Convert value to string based on type
            std::string value;
            if (it.value().is_string()) {
                value = it.value().get<std::string>();
            } else if (it.value().is_number_integer()) {
                value = std::to_string(it.value().get<int>());
            } else if (it.value().is_number_float()) {
                value = std::to_string(it.value().get<double>());
            } else if (it.value().is_boolean()) {
                value = it.value().get<bool>() ? "1" : "0";
            } else if (it.value().is_array()) {
                // Array values separated by semicolons
                std::vector<std::string> arr_values;
                for (const auto& item : it.value()) {
                    if (item.is_string()) {
                        arr_values.push_back(item.get<std::string>());
                    } else if (item.is_number()) {
                        arr_values.push_back(std::to_string(item.get<double>()));
                    }
                }
                value = boost::algorithm::join(arr_values, ";");
            } else {
                continue; // Skip unsupported types
            }

            ini << key << " = " << value << "\n";
        }
    }

    // Add parent/inherits if present
    if (preset_data.contains("inherits") && !preset_data["inherits"].is_null()) {
        std::string parent = preset_data["inherits"].get<std::string>();
        if (!parent.empty()) {
            ini << "inherits = " << parent << "\n";
        }
    }

    // Add metadata
    if (preset_data.contains("vendor")) {
        ini << "vendor = " << preset_data["vendor"].get<std::string>() << "\n";
    }

    if (preset_data.contains("version")) {
        ini << "version = " << preset_data["version"].get<std::string>() << "\n";
    }

    ini << "\n";

    return ini.str();
}

// File operations
std::string PresetImporter::create_temp_preset_file(const std::string& content)
{
    try {
        std::string temp_dir = get_temp_directory();

        // Ensure temp directory exists
        wxFileName::Mkdir(temp_dir, wxS_DIR_DEFAULT, wxPATH_MKDIR_FULL);

        // Generate unique filename
        std::string timestamp = std::to_string(std::chrono::system_clock::now().time_since_epoch().count());
        std::string filename = "filamenthub_import_" + timestamp + ".ini";

        wxFileName temp_file(temp_dir, filename);
        std::string temp_path = temp_file.GetFullPath().ToStdString();

        // Write content to file
        std::ofstream file(temp_path, std::ios::binary);
        if (!file.is_open()) {
            throw std::runtime_error("Failed to create temp file: " + temp_path);
        }

        file << content;
        file.close();

        // Track temp file for cleanup
        m_temp_files.push_back(temp_path);

        wxLogMessage("FilamentHub: Created temp preset file: %s", temp_path);
        return temp_path;

    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Failed to create temp file: %s", e.what());
        throw;
    }
}

void PresetImporter::cleanup_temp_file(const std::string& file_path)
{
    try {
        if (wxFileExists(file_path)) {
            wxRemoveFile(file_path);
            wxLogMessage("FilamentHub: Cleaned up temp file: %s", file_path);
        }

        // Remove from tracking list
        m_temp_files.erase(
            std::remove(m_temp_files.begin(), m_temp_files.end(), file_path),
            m_temp_files.end()
        );

    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Failed to cleanup temp file: %s", e.what());
    }
}

// Import via OrcaSlicer API
bool PresetImporter::import_via_preset_bundle(
    const std::string& bundle_path,
    const std::string& preset_type)
{
    try {
        // Validate bundle file exists
        if (!wxFileExists(bundle_path)) {
            wxLogError("FilamentHub: Bundle file does not exist: %s", bundle_path);
            return false;
        }

        // Read and parse bundle file
        std::ifstream file(bundle_path);
        if (!file.is_open()) {
            wxLogError("FilamentHub: Failed to open bundle file: %s", bundle_path);
            return false;
        }

        std::string content((std::istreambuf_iterator<char>(file)),
                           std::istreambuf_iterator<char>());
        file.close();

        if (content.empty()) {
            wxLogError("FilamentHub: Bundle file is empty");
            return false;
        }

        // Validate bundle format
        if (!validate_bundle_format(content, preset_type)) {
            wxLogError("FilamentHub: Invalid bundle format");
            return false;
        }

        // Parse bundle content
        auto preset_sections = parse_bundle_sections(content);
        if (preset_sections.empty()) {
            wxLogError("FilamentHub: No valid preset sections found in bundle");
            return false;
        }

        // Import each preset section
        int imported_count = 0;
        for (const auto& section : preset_sections) {
            if (import_preset_section(section, preset_type)) {
                imported_count++;
            }
        }

        if (imported_count == 0) {
            wxLogError("FilamentHub: Failed to import any presets from bundle");
            return false;
        }

        wxLogMessage("FilamentHub: Successfully imported %d preset(s) from bundle", imported_count);
        return true;

    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Failed to import preset bundle: %s", e.what());
        return false;
    }
}

// Bundle validation and parsing helpers
bool PresetImporter::validate_bundle_format(const std::string& content, const std::string& preset_type)
{
    // Check for bundle header
    if (content.find("# OrcaSlicer") == std::string::npos &&
        content.find("[" + preset_type + ":") == std::string::npos) {
        return false;
    }

    // Basic INI format validation
    return !content.empty() && content.length() > 10;
}

std::vector<std::string> PresetImporter::parse_bundle_sections(const std::string& content)
{
    std::vector<std::string> sections;
    std::istringstream stream(content);
    std::string line;
    std::string current_section;
    bool in_section = false;

    while (std::getline(stream, line)) {
        // Trim whitespace
        boost::algorithm::trim(line);

        // Skip empty lines and comments outside sections
        if (line.empty() || (line[0] == '#' && !in_section)) {
            continue;
        }

        // Check for section header
        if (line[0] == '[' && line.back() == ']') {
            // Save previous section if exists
            if (in_section && !current_section.empty()) {
                sections.push_back(current_section);
            }

            // Start new section
            current_section = line + "\n";
            in_section = true;
        } else if (in_section) {
            current_section += line + "\n";
        }
    }

    // Save last section
    if (in_section && !current_section.empty()) {
        sections.push_back(current_section);
    }

    return sections;
}

bool PresetImporter::import_preset_section(const std::string& section, const std::string& preset_type)
{
    try {
        // Parse section to extract preset data
        auto preset_data = parse_ini_section(section);

        if (preset_data.empty()) {
            wxLogWarning("FilamentHub: Empty preset section, skipping");
            return false;
        }

        // Extract preset name from section header
        std::string preset_name;
        size_t colon_pos = section.find(':');
        if (colon_pos != std::string::npos) {
            size_t bracket_pos = section.find(']', colon_pos);
            if (bracket_pos != std::string::npos) {
                preset_name = section.substr(colon_pos + 1, bracket_pos - colon_pos - 1);
                boost::algorithm::trim(preset_name);
            }
        }

        if (preset_name.empty()) {
            wxLogWarning("FilamentHub: Could not extract preset name from section");
            return false;
        }

        // Get preset directory
        std::string preset_dir = get_preset_directory(preset_type);
        wxFileName::Mkdir(preset_dir, wxS_DIR_DEFAULT, wxPATH_MKDIR_FULL);

        // Write preset file
        std::string preset_file_path = wxFileName(preset_dir, preset_name + ".ini").GetFullPath().ToStdString();
        std::ofstream preset_file(preset_file_path);
        if (!preset_file.is_open()) {
            wxLogError("FilamentHub: Failed to create preset file: %s", preset_file_path);
            return false;
        }

        preset_file << section;
        preset_file.close();

        wxLogMessage("FilamentHub: Created preset file: %s", preset_file_path);
        return true;

    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Failed to import preset section: %s", e.what());
        return false;
    }
}

std::map<std::string, std::string> PresetImporter::parse_ini_section(const std::string& section)
{
    std::map<std::string, std::string> data;
    std::istringstream stream(section);
    std::string line;

    while (std::getline(stream, line)) {
        boost::algorithm::trim(line);

        // Skip empty lines, comments, and section headers
        if (line.empty() || line[0] == '#' || line[0] == '[') {
            continue;
        }

        // Parse key = value
        size_t eq_pos = line.find('=');
        if (eq_pos != std::string::npos) {
            std::string key = line.substr(0, eq_pos);
            std::string value = line.substr(eq_pos + 1);

            boost::algorithm::trim(key);
            boost::algorithm::trim(value);

            if (!key.empty()) {
                data[key] = value;
            }
        }
    }

    return data;
}

// Info file management
void PresetImporter::update_info_file(
    const std::string& preset_name,
    const std::string& preset_type,
    int preset_id,
    const std::string& last_modified)
{
    try {
        std::string info_path = get_info_file_path(preset_name, preset_type);

        // Ensure directory exists
        wxFileName fn(info_path);
        wxFileName::Mkdir(fn.GetPath(), wxS_DIR_DEFAULT, wxPATH_MKDIR_FULL);

        // Create or update info JSON
        nlohmann::json info;
        info["preset_id"] = preset_id;
        info["preset_name"] = preset_name;
        info["preset_type"] = preset_type;
        info["last_modified"] = last_modified;
        info["last_synced"] = std::time(nullptr);
        info["source"] = "filamenthub";

        // Write to file
        std::ofstream file(info_path);
        if (!file.is_open()) {
            wxLogError("FilamentHub: Failed to open info file for writing: %s", info_path);
            return;
        }

        file << info.dump(2);
        file.close();

        wxLogMessage("FilamentHub: Updated info file for preset: %s", preset_name);

    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Failed to update info file: %s", e.what());
    }
}

nlohmann::json PresetImporter::read_info_file(
    const std::string& preset_name,
    const std::string& preset_type)
{
    try {
        std::string info_path = get_info_file_path(preset_name, preset_type);

        if (!wxFileExists(info_path)) {
            return nlohmann::json::object();
        }

        std::ifstream file(info_path);
        if (!file.is_open()) {
            wxLogWarning("FilamentHub: Failed to open info file: %s", info_path);
            return nlohmann::json::object();
        }

        nlohmann::json info;
        file >> info;
        file.close();

        return info;

    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Failed to read info file: %s", e.what());
        return nlohmann::json::object();
    }
}

// Validation helpers
bool PresetImporter::validate_parent_preset(
    const nlohmann::json& preset_data,
    const std::string& preset_type,
    std::string& error_message)
{
    try {
        // If no parent specified, it's valid (root preset)
        if (!preset_data.contains("inherits") || preset_data["inherits"].is_null() ||
            preset_data["inherits"].get<std::string>().empty()) {
            return true;
        }

        std::string parent = preset_data["inherits"].get<std::string>();

        // Check if parent is a known system preset
        std::vector<std::string> system_presets = {
            "Generic PLA @System",
            "Generic PETG @System",
            "Generic ABS @System",
            "Generic TPU @System",
            "Generic PLA-CF @System",
            "Generic Printer @System",
            "0.20mm Standard @System",
            "0.16mm Fine @System",
            "0.28mm Draft @System"
        };

        if (std::find(system_presets.begin(), system_presets.end(), parent) != system_presets.end()) {
            return true;
        }

        // Validate with backend
        try {
            nlohmann::json validation_result = validate_preset_with_backend(preset_data, preset_type);

            if (validation_result.contains("results") && validation_result["results"].is_array() &&
                !validation_result["results"].empty()) {

                auto& first_result = validation_result["results"][0];

                if (first_result.contains("is_valid") && first_result["is_valid"].get<bool>()) {
                    return true;
                }

                if (first_result.contains("errors") && !first_result["errors"].empty()) {
                    error_message = first_result["errors"][0].get<std::string>();
                    return false;
                }

                // Check for suggested fallback
                if (first_result.contains("suggested_parent")) {
                    std::string suggested = first_result["suggested_parent"].get<std::string>();
                    error_message = "Parent preset '" + parent + "' not found. Suggested: " + suggested;
                    return false;
                }
            }

        } catch (const std::exception& e) {
            wxLogWarning("FilamentHub: Backend validation failed, using local check: %s", e.what());
        }

        // If backend validation failed, check locally
        // TODO: Check local preset directories for parent

        // Default: accept the parent (optimistic validation)
        return true;

    } catch (const std::exception& e) {
        error_message = std::string("Validation error: ") + e.what();
        return false;
    }
}

bool PresetImporter::validate_temperature_ranges(
    const nlohmann::json& preset_data,
    std::string& warning_message)
{
    bool all_valid = true;
    std::vector<std::string> warnings;

    // Check nozzle temperature
    if (preset_data.contains("temperature")) {
        int temp = 0;
        if (preset_data["temperature"].is_number()) {
            temp = preset_data["temperature"].get<int>();
        } else if (preset_data["temperature"].is_array() && !preset_data["temperature"].empty()) {
            temp = preset_data["temperature"][0].get<int>();
        }

        if (temp > 0 && (temp < NOZZLE_TEMP_RANGE.min || temp > NOZZLE_TEMP_RANGE.max)) {
            warnings.push_back(
                "Nozzle temperature " + std::to_string(temp) + "°C is outside recommended range " +
                std::to_string(NOZZLE_TEMP_RANGE.min) + "-" + std::to_string(NOZZLE_TEMP_RANGE.max) + "°C"
            );
            all_valid = false;
        }
    }

    // Check bed temperature
    if (preset_data.contains("bed_temperature")) {
        int temp = 0;
        if (preset_data["bed_temperature"].is_number()) {
            temp = preset_data["bed_temperature"].get<int>();
        } else if (preset_data["bed_temperature"].is_array() && !preset_data["bed_temperature"].empty()) {
            temp = preset_data["bed_temperature"][0].get<int>();
        }

        if (temp > 0 && (temp < BED_TEMP_RANGE.min || temp > BED_TEMP_RANGE.max)) {
            warnings.push_back(
                "Bed temperature " + std::to_string(temp) + "°C is outside recommended range " +
                std::to_string(BED_TEMP_RANGE.min) + "-" + std::to_string(BED_TEMP_RANGE.max) + "°C"
            );
            all_valid = false;
        }
    }

    // Check chamber temperature
    if (preset_data.contains("chamber_temperature")) {
        int temp = preset_data["chamber_temperature"].get<int>();

        if (temp > 0 && (temp < CHAMBER_TEMP_RANGE.min || temp > CHAMBER_TEMP_RANGE.max)) {
            warnings.push_back(
                "Chamber temperature " + std::to_string(temp) + "°C is outside recommended range " +
                std::to_string(CHAMBER_TEMP_RANGE.min) + "-" + std::to_string(CHAMBER_TEMP_RANGE.max) + "°C"
            );
            all_valid = false;
        }
    }

    if (!warnings.empty()) {
        warning_message = boost::algorithm::join(warnings, "; ");
    }

    return all_valid;
}

// Path helpers
std::string PresetImporter::get_preset_directory(const std::string& preset_type) const
{
    wxStandardPaths& std_paths = wxStandardPaths::Get();
    wxString user_data_dir = std_paths.GetUserDataDir();

    wxFileName preset_dir(user_data_dir, "");
    preset_dir.AppendDir("presets");

    if (preset_type == "filament") {
        preset_dir.AppendDir(FILAMENT_DIR);
    } else if (preset_type == "printer") {
        preset_dir.AppendDir(PRINTER_DIR);
    } else if (preset_type == "print") {
        preset_dir.AppendDir(PRINT_DIR);
    }

    return preset_dir.GetPath().ToStdString();
}

std::string PresetImporter::get_info_file_path(
    const std::string& preset_name,
    const std::string& preset_type) const
{
    std::string preset_dir = get_preset_directory(preset_type);

    // Sanitize preset name for filename
    std::string safe_name = preset_name;
    std::replace_if(safe_name.begin(), safe_name.end(),
                   [](char c) { return !std::isalnum(c) && c != '_' && c != '-'; },
                   '_');

    wxFileName info_file(preset_dir, safe_name + ".info");
    return info_file.GetFullPath().ToStdString();
}

std::string PresetImporter::get_temp_directory() const
{
    wxStandardPaths& std_paths = wxStandardPaths::Get();
    wxString temp_dir = std_paths.GetTempDir();

    wxFileName temp_path(temp_dir, "");
    temp_path.AppendDir("OrcaSlicer");
    temp_path.AppendDir("FilamentHub");

    return temp_path.GetPath().ToStdString();
}

// Queue processing helper
void PresetImporter::process_next_task(
    ImportProgressCallback on_progress,
    int current_index,
    int total_count,
    std::vector<ImportResult>& results)
{
    // This method is for potential future use with threaded processing
    // Currently processing is done synchronously in process_queue()
}

// HTTP helper
nlohmann::json PresetImporter::make_api_request(
    const std::string& method,
    const std::string& endpoint,
    const nlohmann::json& body)
{
    try {
        if (!m_auth_manager->is_logged_in()) {
            throw std::runtime_error("Not authenticated");
        }

        // Check if token needs refresh
        if (!m_auth_manager->refresh_token_if_needed()) {
            throw std::runtime_error("Failed to refresh authentication token");
        }

        net::io_context ioc;
        tcp::resolver resolver(ioc);
        beast::tcp_stream stream(ioc);

        // Resolve and connect
        auto const results = resolver.resolve(API_HOST, API_PORT);
        stream.connect(results);

        // Build request
        http::request<http::string_body> req;
        req.method(method == "POST" ? http::verb::post : http::verb::get);
        req.target(endpoint);
        req.version(11);
        req.set(http::field::host, API_HOST);
        req.set(http::field::user_agent, "OrcaSlicer-FilamentHub/1.0");
        req.set(http::field::content_type, "application/json");
        req.set(http::field::authorization, "Bearer " + m_auth_manager->get_token());

        if (body != nullptr && !body.is_null()) {
            std::string body_str = body.dump();
            req.body() = body_str;
            req.prepare_payload();
        }

        // Send request
        http::write(stream, req);

        // Receive response
        beast::flat_buffer buffer;
        http::response<http::string_body> res;
        http::read(stream, buffer, res);

        // Close connection
        beast::error_code ec;
        stream.socket().shutdown(tcp::socket::shutdown_both, ec);

        // Handle different HTTP status codes
        if (res.result() == http::status::unauthorized) {
            // Token might be expired, try to refresh
            if (m_auth_manager->refresh_token_if_needed()) {
                // Retry the request once with new token
                wxLogMessage("FilamentHub: Retrying request with refreshed token");
                return make_api_request(method, endpoint, body); // Recursive call
            }
            throw std::runtime_error("Authentication failed");
        }

        if (res.result() != http::status::ok) {
            std::string error_msg = "HTTP request failed with status: " +
                                   std::to_string(res.result_int());

            // Try to extract error message from response body
            try {
                nlohmann::json error_json = nlohmann::json::parse(res.body());
                if (error_json.contains("detail")) {
                    error_msg += " - " + error_json["detail"].get<std::string>();
                }
            } catch (...) {
                // Response body is not JSON, use as-is
                if (!res.body().empty()) {
                    error_msg += " - " + res.body().substr(0, 200);
                }
            }

            throw std::runtime_error(error_msg);
        }

        // Parse response
        return nlohmann::json::parse(res.body());

    } catch (const std::exception& e) {
        wxLogError("FilamentHub: API request failed: %s", e.what());
        throw;
    }
}

// Additional validation helpers for specific preset types
bool PresetImporter::validate_filament_settings(
    const nlohmann::json& preset_data,
    std::string& error_msg)
{
    // Validate required filament fields
    std::vector<std::string> required_fields = {
        "filament_type",
        "temperature",
        "bed_temperature"
    };

    for (const auto& field : required_fields) {
        if (!preset_data.contains(field) &&
            (!preset_data.contains("settings") || !preset_data["settings"].contains(field))) {
            error_msg = "Missing required field: " + field;
            return false;
        }
    }

    // Validate filament type is known
    std::vector<std::string> known_types = {
        "PLA", "PETG", "ABS", "TPU", "ASA", "PC", "PA", "PVA", "HIPS",
        "PLA-CF", "PETG-CF", "PA-CF", "Generic"
    };

    std::string filament_type;
    if (preset_data.contains("filament_type")) {
        filament_type = preset_data["filament_type"].get<std::string>();
    } else if (preset_data.contains("settings") && preset_data["settings"].contains("filament_type")) {
        filament_type = preset_data["settings"]["filament_type"].get<std::string>();
    }

    if (!filament_type.empty()) {
        bool type_found = false;
        for (const auto& known_type : known_types) {
            if (filament_type.find(known_type) != std::string::npos) {
                type_found = true;
                break;
            }
        }

        if (!type_found) {
            wxLogWarning("FilamentHub: Unknown filament type: %s", filament_type);
            // Warning only, not an error
        }
    }

    return true;
}

bool PresetImporter::validate_printer_settings(
    const nlohmann::json& preset_data,
    std::string& error_msg)
{
    // Validate required printer fields
    std::vector<std::string> required_fields = {
        "bed_shape",
        "max_print_height"
    };

    for (const auto& field : required_fields) {
        if (!preset_data.contains(field) &&
            (!preset_data.contains("settings") || !preset_data["settings"].contains(field))) {
            error_msg = "Missing required field: " + field;
            return false;
        }
    }

    // Validate bed dimensions are reasonable
    if (preset_data.contains("settings")) {
        const auto& settings = preset_data["settings"];

        if (settings.contains("max_print_height")) {
            int height = settings["max_print_height"].get<int>();
            if (height < 10 || height > 1000) {
                error_msg = "Invalid max_print_height: " + std::to_string(height) +
                           " (expected 10-1000mm)";
                return false;
            }
        }
    }

    return true;
}

bool PresetImporter::validate_print_settings(
    const nlohmann::json& preset_data,
    std::string& error_msg)
{
    // Validate required print settings fields
    std::vector<std::string> required_fields = {
        "layer_height"
    };

    for (const auto& field : required_fields) {
        if (!preset_data.contains(field) &&
            (!preset_data.contains("settings") || !preset_data["settings"].contains(field))) {
            error_msg = "Missing required field: " + field;
            return false;
        }
    }

    // Validate layer height is reasonable
    if (preset_data.contains("settings")) {
        const auto& settings = preset_data["settings"];

        if (settings.contains("layer_height")) {
            double layer_height = settings["layer_height"].get<double>();
            if (layer_height < 0.05 || layer_height > 1.0) {
                error_msg = "Invalid layer_height: " + std::to_string(layer_height) +
                           " (expected 0.05-1.0mm)";
                return false;
            }
        }

        // Validate perimeters
        if (settings.contains("perimeters")) {
            int perimeters = settings["perimeters"].get<int>();
            if (perimeters < 0 || perimeters > 100) {
                error_msg = "Invalid perimeters count: " + std::to_string(perimeters);
                return false;
            }
        }

        // Validate infill
        if (settings.contains("fill_density")) {
            auto fill_density = settings["fill_density"];
            double density = 0;

            if (fill_density.is_string()) {
                std::string density_str = fill_density.get<std::string>();
                // Remove % if present
                density_str.erase(std::remove(density_str.begin(), density_str.end(), '%'), density_str.end());
                density = std::stod(density_str);
            } else if (fill_density.is_number()) {
                density = fill_density.get<double>();
            }

            if (density < 0 || density > 100) {
                error_msg = "Invalid fill_density: " + std::to_string(density) +
                           " (expected 0-100%)";
                return false;
            }
        }
    }

    return true;
}

// Conflict detection helpers
bool PresetImporter::check_preset_exists(
    const std::string& preset_name,
    const std::string& preset_type)
{
    std::string preset_dir = get_preset_directory(preset_type);
    wxFileName preset_file(preset_dir, preset_name + ".ini");

    return wxFileExists(preset_file.GetFullPath());
}

bool PresetImporter::should_overwrite_preset(
    const std::string& preset_name,
    const std::string& preset_type,
    const nlohmann::json& new_data)
{
    // Read existing info file
    nlohmann::json existing_info = read_info_file(preset_name, preset_type);

    if (existing_info.empty()) {
        // No existing info, safe to overwrite
        return true;
    }

    // Check if new preset is newer
    if (new_data.contains("last_modified") && existing_info.contains("last_modified")) {
        std::string new_modified = new_data["last_modified"].get<std::string>();
        std::string existing_modified = existing_info["last_modified"].get<std::string>();

        // Simple string comparison (assumes ISO 8601 format)
        if (new_modified > existing_modified) {
            wxLogMessage("FilamentHub: New preset is newer, will overwrite");
            return true;
        } else {
            wxLogMessage("FilamentHub: Existing preset is newer or same, skipping");
            return false;
        }
    }

    // Check if preset IDs match (same preset, safe to update)
    if (new_data.contains("id") && existing_info.contains("preset_id")) {
        int new_id = new_data["id"].get<int>();
        int existing_id = existing_info["preset_id"].get<int>();

        if (new_id == existing_id) {
            return true;
        }
    }

    // Default: don't overwrite to be safe
    wxLogWarning("FilamentHub: Cannot determine if preset should be overwritten, skipping");
    return false;
}

// Metadata extraction and management
nlohmann::json PresetImporter::extract_metadata(const nlohmann::json& preset_data)
{
    nlohmann::json metadata;

    // Extract common metadata fields
    if (preset_data.contains("id")) {
        metadata["preset_id"] = preset_data["id"];
    }

    if (preset_data.contains("name")) {
        metadata["preset_name"] = preset_data["name"];
    }

    if (preset_data.contains("vendor")) {
        metadata["vendor"] = preset_data["vendor"];
    }

    if (preset_data.contains("version")) {
        metadata["version"] = preset_data["version"];
    }

    if (preset_data.contains("last_modified")) {
        metadata["last_modified"] = preset_data["last_modified"];
    }

    if (preset_data.contains("created_at")) {
        metadata["created_at"] = preset_data["created_at"];
    }

    if (preset_data.contains("updated_at")) {
        metadata["updated_at"] = preset_data["updated_at"];
    }

    if (preset_data.contains("user_id")) {
        metadata["user_id"] = preset_data["user_id"];
    }

    if (preset_data.contains("is_public")) {
        metadata["is_public"] = preset_data["is_public"];
    }

    if (preset_data.contains("description")) {
        metadata["description"] = preset_data["description"];
    }

    if (preset_data.contains("tags")) {
        metadata["tags"] = preset_data["tags"];
    }

    return metadata;
}

void PresetImporter::update_preset_metadata(
    const std::string& preset_name,
    const std::string& preset_type,
    const nlohmann::json& metadata)
{
    try {
        // Read existing info file
        nlohmann::json info = read_info_file(preset_name, preset_type);

        // Merge with new metadata
        for (auto it = metadata.begin(); it != metadata.end(); ++it) {
            info[it.key()] = it.value();
        }

        // Update timestamp
        info["last_updated"] = std::time(nullptr);

        // Write back to info file
        std::string info_path = get_info_file_path(preset_name, preset_type);
        wxFileName fn(info_path);
        wxFileName::Mkdir(fn.GetPath(), wxS_DIR_DEFAULT, wxPATH_MKDIR_FULL);

        std::ofstream file(info_path);
        if (file.is_open()) {
            file << info.dump(2);
            file.close();
            wxLogMessage("FilamentHub: Updated preset metadata for: %s", preset_name);
        }

    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Failed to update preset metadata: %s", e.what());
    }
}

} // namespace GUI
} // namespace Slic3r
