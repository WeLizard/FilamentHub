#include "AuthManager.hpp"
#include <fstream>
#include <sstream>
#include <iomanip>
#include <ctime>
#include <stdexcept>
#include <wx/stdpaths.h>
#include <wx/filename.h>
#include <wx/log.h>
#include <boost/beast/core.hpp>
#include <boost/beast/http.hpp>
#include <boost/beast/version.hpp>
#include <boost/asio/connect.hpp>
#include <boost/asio/ip/tcp.hpp>
#include <boost/asio/ssl.hpp>

namespace beast = boost::beast;
namespace http = beast::http;
namespace net = boost::asio;
namespace ssl = boost::asio::ssl;
using tcp = boost::asio::ip::tcp;

namespace Slic3r {
namespace GUI {

// JWT helper functions
namespace {
    // Base64 URL-safe decoding
    std::string base64_url_decode(const std::string& input) {
        std::string output = input;
        // Replace URL-safe characters
        std::replace(output.begin(), output.end(), '-', '+');
        std::replace(output.begin(), output.end(), '_', '/');

        // Add padding if needed
        while (output.length() % 4 != 0) {
            output += '=';
        }

        // Base64 decode table
        static const std::string base64_chars =
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
            "abcdefghijklmnopqrstuvwxyz"
            "0123456789+/";

        std::string decoded;
        std::vector<int> T(256, -1);
        for (int i = 0; i < 64; i++) T[base64_chars[i]] = i;

        int val = 0, valb = -8;
        for (unsigned char c : output) {
            if (T[c] == -1) break;
            val = (val << 6) + T[c];
            valb += 6;
            if (valb >= 0) {
                decoded.push_back(char((val >> valb) & 0xFF));
                valb -= 8;
            }
        }
        return decoded;
    }

    // Parse JWT token and extract payload
    nlohmann::json parse_jwt_payload(const std::string& token) {
        auto first_dot = token.find('.');
        if (first_dot == std::string::npos) {
            throw std::runtime_error("Invalid JWT token format");
        }

        auto second_dot = token.find('.', first_dot + 1);
        if (second_dot == std::string::npos) {
            throw std::runtime_error("Invalid JWT token format");
        }

        std::string payload_encoded = token.substr(first_dot + 1, second_dot - first_dot - 1);
        std::string payload_decoded = base64_url_decode(payload_encoded);

        return nlohmann::json::parse(payload_decoded);
    }
}

AuthManager::AuthManager()
    : m_auth_state()
    , m_auth_state_callback(nullptr)
{
    load_configuration();
}

AuthManager::~AuthManager()
{
    // Nothing to clean up
}

// Configuration persistence
bool AuthManager::load_configuration()
{
    try {
        std::string config_path = get_config_file_path();
        std::ifstream config_file(config_path);

        if (!config_file.is_open()) {
            wxLogMessage("FilamentHub: No existing config file found");
            return false;
        }

        nlohmann::json config;
        config_file >> config;
        config_file.close();

        if (config.contains("access_token") && config.contains("refresh_token")) {
            m_auth_state.access_token = config["access_token"].get<std::string>();
            m_auth_state.refresh_token = config["refresh_token"].get<std::string>();

            if (config.contains("user_id")) {
                m_auth_state.user_id = config["user_id"].get<int>();
            }

            if (config.contains("username")) {
                m_auth_state.username = config["username"].get<std::string>();
            }

            // Parse token to get expiration
            parse_token_claims(m_auth_state.access_token);

            // Validate token is still good
            if (!is_token_expired()) {
                m_auth_state.is_authenticated = true;
                wxLogMessage("FilamentHub: Loaded authentication config successfully");
                notify_auth_state_changed();
                return true;
            } else {
                wxLogMessage("FilamentHub: Token expired, will need to refresh");
                // Try to refresh
                if (refresh_token_if_needed()) {
                    return true;
                }
            }
        }

        return false;
    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Failed to load configuration: %s", e.what());
        return false;
    }
}

bool AuthManager::save_configuration()
{
    try {
        std::string config_path = get_config_file_path();

        // Ensure directory exists
        wxFileName fn(config_path);
        wxFileName::Mkdir(fn.GetPath(), wxS_DIR_DEFAULT, wxPATH_MKDIR_FULL);

        nlohmann::json config;
        config["access_token"] = m_auth_state.access_token;
        config["refresh_token"] = m_auth_state.refresh_token;
        config["user_id"] = m_auth_state.user_id;
        config["username"] = m_auth_state.username;

        std::ofstream config_file(config_path);
        if (!config_file.is_open()) {
            wxLogError("FilamentHub: Failed to open config file for writing");
            return false;
        }

        config_file << config.dump(2);
        config_file.close();

        wxLogMessage("FilamentHub: Configuration saved successfully");
        return true;
    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Failed to save configuration: %s", e.what());
        return false;
    }
}

void AuthManager::clear_configuration()
{
    try {
        std::string config_path = get_config_file_path();

        if (wxFileExists(config_path)) {
            wxRemoveFile(config_path);
            wxLogMessage("FilamentHub: Configuration cleared");
        }

        m_auth_state = AuthState();
        notify_auth_state_changed();
    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Failed to clear configuration: %s", e.what());
    }
}

// Authentication operations
bool AuthManager::login(const std::string& username, const std::string& password)
{
    try {
        wxLogMessage("FilamentHub: Attempting login for user: %s", username);

        nlohmann::json response = authenticate(username, password);

        if (response.contains("access_token") && response.contains("refresh_token")) {
            m_auth_state.access_token = response["access_token"].get<std::string>();
            m_auth_state.refresh_token = response["refresh_token"].get<std::string>();
            m_auth_state.username = username;

            // Parse token claims
            parse_token_claims(m_auth_state.access_token);
            m_auth_state.is_authenticated = true;

            // Save to disk
            save_configuration();

            wxLogMessage("FilamentHub: Login successful for user: %s", username);
            notify_auth_state_changed();
            return true;
        }

        wxLogError("FilamentHub: Login failed - invalid response format");
        return false;
    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Login failed: %s", e.what());
        return false;
    }
}

bool AuthManager::login_with_token(const std::string& access_token, const std::string& refresh_token)
{
    try {
        m_auth_state.access_token = access_token;
        m_auth_state.refresh_token = refresh_token;

        // Parse token claims
        parse_token_claims(access_token);

        // Validate with server
        if (validate_token()) {
            m_auth_state.is_authenticated = true;
            save_configuration();
            notify_auth_state_changed();
            return true;
        }

        return false;
    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Token login failed: %s", e.what());
        return false;
    }
}

void AuthManager::logout()
{
    wxLogMessage("FilamentHub: Logging out user: %s", m_auth_state.username);
    clear_configuration();
}

// Token management
std::string AuthManager::get_token() const
{
    return m_auth_state.access_token;
}

std::string AuthManager::get_refresh_token() const
{
    return m_auth_state.refresh_token;
}

bool AuthManager::is_logged_in() const
{
    return m_auth_state.is_authenticated && !is_token_expired();
}

bool AuthManager::validate_token()
{
    try {
        if (m_auth_state.access_token.empty()) {
            return false;
        }

        // First check local expiration
        if (is_token_expired()) {
            wxLogMessage("FilamentHub: Token expired locally");
            return false;
        }

        // Validate with server
        nlohmann::json response = validate_token_with_server(m_auth_state.access_token);

        if (response.contains("valid") && response["valid"].get<bool>()) {
            wxLogMessage("FilamentHub: Token validated successfully");
            return true;
        }

        wxLogWarning("FilamentHub: Token validation failed");
        return false;
    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Token validation error: %s", e.what());
        return false;
    }
}

bool AuthManager::refresh_token_if_needed()
{
    try {
        // Check if we need to refresh
        if (!is_token_near_expiration() && !is_token_expired()) {
            return true; // Token is still good
        }

        if (m_auth_state.refresh_token.empty()) {
            wxLogError("FilamentHub: Cannot refresh - no refresh token available");
            return false;
        }

        wxLogMessage("FilamentHub: Refreshing access token");
        nlohmann::json response = refresh_access_token(m_auth_state.refresh_token);

        if (response.contains("access_token")) {
            m_auth_state.access_token = response["access_token"].get<std::string>();

            // Update refresh token if provided
            if (response.contains("refresh_token")) {
                m_auth_state.refresh_token = response["refresh_token"].get<std::string>();
            }

            // Parse new token claims
            parse_token_claims(m_auth_state.access_token);

            // Save updated tokens
            save_configuration();

            wxLogMessage("FilamentHub: Token refreshed successfully");
            notify_auth_state_changed();
            return true;
        }

        wxLogError("FilamentHub: Token refresh failed - invalid response");
        return false;
    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Token refresh error: %s", e.what());
        m_auth_state.is_authenticated = false;
        notify_auth_state_changed();
        return false;
    }
}

// User info
int AuthManager::get_user_id() const
{
    return m_auth_state.user_id;
}

std::string AuthManager::get_username() const
{
    return m_auth_state.username;
}

// Token expiration
bool AuthManager::is_token_expired() const
{
    auto now = std::chrono::system_clock::now();
    return now >= m_auth_state.expires_at;
}

bool AuthManager::is_token_near_expiration() const
{
    auto now = std::chrono::system_clock::now();
    auto threshold = m_auth_state.expires_at - std::chrono::minutes(TOKEN_REFRESH_THRESHOLD_MINUTES);
    return now >= threshold;
}

std::chrono::system_clock::time_point AuthManager::get_token_expiration() const
{
    return m_auth_state.expires_at;
}

// Callbacks
void AuthManager::set_auth_state_callback(AuthStateCallback callback)
{
    m_auth_state_callback = callback;
}

// Private methods - Backend API calls
nlohmann::json AuthManager::authenticate(const std::string& username, const std::string& password)
{
    nlohmann::json body;
    body["username"] = username;
    body["password"] = password;

    return make_auth_request("POST", "/api/v1/auth/login", body, false);
}

nlohmann::json AuthManager::refresh_access_token(const std::string& refresh_token)
{
    nlohmann::json body;
    body["refresh_token"] = refresh_token;

    return make_auth_request("POST", "/api/v1/auth/refresh", body, false);
}

nlohmann::json AuthManager::validate_token_with_server(const std::string& token)
{
    return make_auth_request("GET", "/api/v1/auth/validate", nullptr, true);
}

// Token parsing
void AuthManager::parse_token_claims(const std::string& token)
{
    try {
        nlohmann::json payload = parse_jwt_payload(token);

        // Extract user_id
        if (payload.contains("sub")) {
            // "sub" could be user_id as string or int
            if (payload["sub"].is_string()) {
                m_auth_state.user_id = std::stoi(payload["sub"].get<std::string>());
            } else if (payload["sub"].is_number()) {
                m_auth_state.user_id = payload["sub"].get<int>();
            }
        } else if (payload.contains("user_id")) {
            m_auth_state.user_id = payload["user_id"].get<int>();
        }

        // Extract expiration
        if (payload.contains("exp")) {
            int64_t exp = payload["exp"].get<int64_t>();
            m_auth_state.expires_at = std::chrono::system_clock::from_time_t(exp);
        }

        // Extract username if available
        if (payload.contains("username")) {
            m_auth_state.username = payload["username"].get<std::string>();
        }

    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Failed to parse token claims: %s", e.what());
        throw;
    }
}

std::chrono::system_clock::time_point AuthManager::extract_expiration(const std::string& token)
{
    try {
        nlohmann::json payload = parse_jwt_payload(token);

        if (payload.contains("exp")) {
            int64_t exp = payload["exp"].get<int64_t>();
            return std::chrono::system_clock::from_time_t(exp);
        }

        // Default to expired if no expiration found
        return std::chrono::system_clock::now() - std::chrono::hours(1);
    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Failed to extract expiration: %s", e.what());
        return std::chrono::system_clock::now() - std::chrono::hours(1);
    }
}

int AuthManager::extract_user_id(const std::string& token)
{
    try {
        nlohmann::json payload = parse_jwt_payload(token);

        if (payload.contains("sub")) {
            if (payload["sub"].is_string()) {
                return std::stoi(payload["sub"].get<std::string>());
            } else if (payload["sub"].is_number()) {
                return payload["sub"].get<int>();
            }
        } else if (payload.contains("user_id")) {
            return payload["user_id"].get<int>();
        }

        return 0;
    } catch (const std::exception& e) {
        wxLogError("FilamentHub: Failed to extract user_id: %s", e.what());
        return 0;
    }
}

// Configuration file
std::string AuthManager::get_config_file_path() const
{
    wxStandardPaths& std_paths = wxStandardPaths::Get();
    wxString user_data_dir = std_paths.GetUserDataDir();

    wxFileName config_file(user_data_dir, CONFIG_FILENAME);
    return config_file.GetFullPath().ToStdString();
}

nlohmann::json AuthManager::load_config_json()
{
    std::string config_path = get_config_file_path();
    std::ifstream config_file(config_path);

    if (!config_file.is_open()) {
        return nlohmann::json::object();
    }

    nlohmann::json config;
    config_file >> config;
    config_file.close();

    return config;
}

void AuthManager::save_config_json(const nlohmann::json& config)
{
    std::string config_path = get_config_file_path();

    // Ensure directory exists
    wxFileName fn(config_path);
    wxFileName::Mkdir(fn.GetPath(), wxS_DIR_DEFAULT, wxPATH_MKDIR_FULL);

    std::ofstream config_file(config_path);
    if (config_file.is_open()) {
        config_file << config.dump(2);
        config_file.close();
    }
}

// State update
void AuthManager::update_auth_state(const AuthState& new_state)
{
    m_auth_state = new_state;
    notify_auth_state_changed();
}

void AuthManager::notify_auth_state_changed()
{
    if (m_auth_state_callback) {
        m_auth_state_callback(m_auth_state);
    }
}

// HTTP helper
nlohmann::json AuthManager::make_auth_request(
    const std::string& method,
    const std::string& endpoint,
    const nlohmann::json& body,
    bool include_auth_header)
{
    try {
        // TODO: This should use FilamentHubClient or similar HTTP client
        // For now, implementing basic Boost.Beast HTTP request

        std::string host = "localhost"; // TODO: Make configurable
        std::string port = "8000";      // TODO: Make configurable

        net::io_context ioc;
        tcp::resolver resolver(ioc);
        beast::tcp_stream stream(ioc);

        // Look up the domain name
        auto const results = resolver.resolve(host, port);

        // Make the connection
        stream.connect(results);

        // Set up the HTTP request
        http::request<http::string_body> req;
        req.method(method == "POST" ? http::verb::post : http::verb::get);
        req.target(endpoint);
        req.version(11);
        req.set(http::field::host, host);
        req.set(http::field::user_agent, "OrcaSlicer-FilamentHub/1.0");
        req.set(http::field::content_type, "application/json");

        if (include_auth_header && !m_auth_state.access_token.empty()) {
            req.set(http::field::authorization, "Bearer " + m_auth_state.access_token);
        }

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
            throw std::runtime_error("HTTP request failed with status: " + std::to_string(res.result_int()));
        }

        // Parse JSON response
        return nlohmann::json::parse(res.body());

    } catch (const std::exception& e) {
        wxLogError("FilamentHub: HTTP request failed: %s", e.what());
        throw;
    }
}

} // namespace GUI
} // namespace Slic3r
