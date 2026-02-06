#ifndef slic3r_GUI_FilamentHub_AuthManager_hpp_
#define slic3r_GUI_FilamentHub_AuthManager_hpp_

#include <string>
#include <chrono>
#include <functional>
#include "nlohmann/json.hpp"

namespace Slic3r {
namespace GUI {

/**
 * @brief Authentication state structure
 */
struct AuthState {
    std::string access_token;
    std::string refresh_token;
    int user_id;
    std::string username;
    std::chrono::system_clock::time_point expires_at;
    bool is_authenticated;

    AuthState() : user_id(0), is_authenticated(false) {}
};

/**
 * @brief Manages authentication tokens and user session
 *
 * This class handles:
 * - Token storage and retrieval (access_token, refresh_token)
 * - Token validation and expiration checking
 * - Automatic token refresh when near expiration
 * - Login/logout flows
 * - Persistent configuration (saved to app data directory)
 *
 * Token format: JWT with expiration timestamp
 * Storage location: %APPDATA%/OrcaSlicer/filament_hub_config.json
 */
class AuthManager
{
public:
    /**
     * @brief Authentication state change callback
     */
    using AuthStateCallback = std::function<void(const AuthState&)>;

    AuthManager();
    ~AuthManager();

    // Configuration persistence
    bool load_configuration();
    bool save_configuration();
    void clear_configuration();

    // Authentication operations
    bool login(const std::string& username, const std::string& password);
    bool login_with_token(const std::string& access_token, const std::string& refresh_token);
    void logout();

    // Token management
    std::string get_token() const;
    std::string get_refresh_token() const;
    bool is_logged_in() const;
    bool validate_token();
    bool refresh_token_if_needed();

    // User info
    int get_user_id() const;
    std::string get_username() const;

    // Token expiration
    bool is_token_expired() const;
    bool is_token_near_expiration() const; // Within 5 minutes
    std::chrono::system_clock::time_point get_token_expiration() const;

    // Callbacks
    void set_auth_state_callback(AuthStateCallback callback);

private:
    // Backend API calls
    nlohmann::json authenticate(const std::string& username, const std::string& password);
    nlohmann::json refresh_access_token(const std::string& refresh_token);
    nlohmann::json validate_token_with_server(const std::string& token);

    // Token parsing
    void parse_token_claims(const std::string& token);
    std::chrono::system_clock::time_point extract_expiration(const std::string& token);
    int extract_user_id(const std::string& token);

    // Configuration file
    std::string get_config_file_path() const;
    nlohmann::json load_config_json();
    void save_config_json(const nlohmann::json& config);

    // State update
    void update_auth_state(const AuthState& new_state);
    void notify_auth_state_changed();

    // HTTP helper
    nlohmann::json make_auth_request(
        const std::string& method,
        const std::string& endpoint,
        const nlohmann::json& body = nullptr,
        bool include_auth_header = false
    );

    // Members
    AuthState m_auth_state;
    AuthStateCallback m_auth_state_callback;

    // Constants
    static constexpr int TOKEN_REFRESH_THRESHOLD_MINUTES = 5;
    static constexpr const char* CONFIG_FILENAME = "filament_hub_config.json";
};

} // namespace GUI
} // namespace Slic3r

#endif // slic3r_GUI_FilamentHub_AuthManager_hpp_
