#include "cloud.h"
#include "snapshot.h"

#include "cJSON.h"
#include "esp_crt_bundle.h"
#include "esp_http_client.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdint.h>

#define FH_RESPONSE_MAX 1536

static bool valid_bridge_token(const char *value, size_t capacity)
{
    if (!value || strncmp(value, "fhpb_", 5) != 0) return false;
    size_t length = strlen(value);
    if (length <= 5 || length >= capacity) return false;
    for (size_t i = 5; i < length; i++) {
        char ch = value[i];
        if (!((ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') ||
              (ch >= '0' && ch <= '9') || ch == '_' || ch == '-'))
            return false;
    }
    return true;
}

typedef struct {
    char body[FH_RESPONSE_MAX + 1];
    size_t length;
    bool oversized;
} response_buffer;

static esp_err_t response_event(esp_http_client_event_t *event)
{
    if (event->event_id != HTTP_EVENT_ON_DATA || !event->data || event->data_len <= 0)
        return ESP_OK;
    response_buffer *response = event->user_data;
    if ((size_t)event->data_len > FH_RESPONSE_MAX - response->length) {
        response->oversized = true;
        return ESP_FAIL;
    }
    memcpy(response->body + response->length, event->data, (size_t)event->data_len);
    response->length += (size_t)event->data_len;
    response->body[response->length] = '\0';
    return ESP_OK;
}

static fh_cloud_result post_json(const fh_config *config, const char *path,
                                 const char *token, const char *body,
                                 response_buffer *response, int *status)
{
    char url[320];
    int size = snprintf(url, sizeof(url), "%s%s", config->cloud_origin, path);
    if (size < 0 || (size_t)size >= sizeof(url)) return FH_CLOUD_REJECTED;
    bool https = strncmp(config->cloud_origin, "https://", 8) == 0;
    esp_http_client_config_t request = {
        .url = url,
        .method = HTTP_METHOD_POST,
        .timeout_ms = 10000,
        .disable_auto_redirect = true,
        .event_handler = response_event,
        .user_data = response,
        .crt_bundle_attach = https ? esp_crt_bundle_attach : NULL,
        .buffer_size = 1024,
        .buffer_size_tx = 1024,
    };
    esp_http_client_handle_t client = esp_http_client_init(&request);
    if (!client) return FH_CLOUD_RETRY;
    esp_http_client_set_header(client, "Content-Type", "application/json");
    if (token) esp_http_client_set_header(client, "X-FilamentHub-Bridge-Token", token);
    esp_http_client_set_post_field(client, body, (int)strlen(body));
    esp_err_t err = esp_http_client_perform(client);
    *status = err == ESP_OK ? esp_http_client_get_status_code(client) : 0;
    esp_http_client_cleanup(client);
    if (err != ESP_OK || response->oversized) return FH_CLOUD_RETRY;
    if (*status == 401 && token) return FH_CLOUD_REVOKED;
    if (*status >= 500 || *status == 429) return FH_CLOUD_RETRY;
    if (*status != 200) return FH_CLOUD_REJECTED;
    return FH_CLOUD_OK;
}

fh_cloud_result fh_cloud_pair(fh_config *config, int index)
{
    fh_connection *conn = &config->connections[index];
    if (!conn->pairing_code[0]) return FH_CLOUD_REJECTED;
    cJSON *request = cJSON_CreateObject();
    if (!request) return FH_CLOUD_RETRY;
    cJSON_AddStringToObject(request, "pairing_code", conn->pairing_code);
    cJSON_AddStringToObject(request, "provider", "bambu");
    cJSON_AddStringToObject(request, "transport", "edge_agent");
    cJSON_AddStringToObject(request, "source_instance_id", conn->source_instance_id);
    cJSON_AddStringToObject(request, "node_instance_id", config->node_instance_id);
    cJSON_AddStringToObject(request, "plugin_version", FH_EDGE_VERSION);
    cJSON *capabilities = cJSON_AddArrayToObject(request, "capabilities");
    cJSON_AddItemToArray(capabilities, cJSON_CreateString("read"));
    if (conn->physical_printer_id > 0 && conn->material_system_id > 0) {
        cJSON_AddNumberToObject(request, "previous_physical_printer_id",
                                conn->physical_printer_id);
        cJSON_AddNumberToObject(request, "previous_material_system_id",
                                conn->material_system_id);
    }
    char *body = cJSON_PrintUnformatted(request);
    cJSON_Delete(request);
    if (!body) return FH_CLOUD_RETRY;
    response_buffer response = {0};
    int status = 0;
    fh_cloud_result result = post_json(config, "/api/v1/printer-bridge/pair", NULL,
                                       body, &response, &status);
    free(body);
    if (result != FH_CLOUD_OK) return result;
    if (!fh_json_shape_ok(response.body, response.length, 8)) return FH_CLOUD_RETRY;
    cJSON *reply = cJSON_ParseWithLength(response.body, response.length);
    const cJSON *token = cJSON_GetObjectItemCaseSensitive(reply, "bridge_token");
    const cJSON *printer = cJSON_GetObjectItemCaseSensitive(reply, "physical_printer_id");
    const cJSON *system = cJSON_GetObjectItemCaseSensitive(reply, "material_system_id");
    bool accepted = cJSON_IsString(token) &&
                    valid_bridge_token(token->valuestring, sizeof(conn->bridge_token)) &&
                    cJSON_IsNumber(printer) && printer->valuedouble >= 1 &&
                    printer->valuedouble <= INT32_MAX &&
                    floor(printer->valuedouble) == printer->valuedouble &&
                    cJSON_IsNumber(system) && system->valuedouble >= 1 &&
                    system->valuedouble <= INT32_MAX &&
                    floor(system->valuedouble) == system->valuedouble;
    if (accepted) {
        fh_config *changed = malloc(sizeof(*changed));
        if (!changed) { cJSON_Delete(reply); return FH_CLOUD_RETRY; }
        *changed = *config;
        fh_connection *saved = &changed->connections[index];
        strcpy(saved->bridge_token, token->valuestring);
        saved->physical_printer_id = printer->valueint;
        saved->material_system_id = system->valueint;
        memset(saved->pairing_code, 0, sizeof(saved->pairing_code));
        if (fh_config_store(changed)) *config = *changed;
        else accepted = false;
        free(changed);
    }
    cJSON_Delete(reply);
    return accepted ? FH_CLOUD_OK : FH_CLOUD_RETRY;
}

typedef struct {
    fh_config *config;
    int index;
} reserve_context;

static bool reserve_sequence(uint64_t high, void *context)
{
    reserve_context *scope = context;
    fh_config *changed = malloc(sizeof(*changed));
    if (!changed) return false;
    *changed = *scope->config;
    changed->connections[scope->index].sequence_reserved_high = high;
    bool saved = fh_config_store(changed);
    free(changed);
    if (!saved) return false;
    scope->config->connections[scope->index].sequence_reserved_high = high;
    return true;
}

fh_cloud_result fh_cloud_snapshot(fh_config *config, int index,
                                  const fh_telemetry *facts, uint64_t now_ms,
                                  const char *observed_at)
{
    fh_connection *conn = &config->connections[index];
    if (!conn->bridge_token[0] || !fh_telemetry_fresh(facts, now_ms) ||
        !observed_at || !*observed_at) return FH_CLOUD_REJECTED;
    reserve_context scope = {.config = config, .index = index};
    uint64_t sequence = fh_next_sequence(&conn->sequence_next,
                                          &conn->sequence_reserved_high,
                                          reserve_sequence, &scope);
    if (!sequence) return FH_CLOUD_RETRY;
    char *body = fh_snapshot_body(config, index, facts, now_ms, observed_at, sequence);
    if (!body) return FH_CLOUD_RETRY;
    response_buffer response = {0};
    int status = 0;
    fh_cloud_result result = post_json(config, "/api/v1/printer-bridge/snapshot",
                                       conn->bridge_token, body, &response, &status);
    free(body);
    if (result != FH_CLOUD_OK) return result;
    if (!fh_json_shape_ok(response.body, response.length, 8)) return FH_CLOUD_RETRY;
    cJSON *reply = cJSON_ParseWithLength(response.body, response.length);
    const cJSON *accepted = cJSON_GetObjectItemCaseSensitive(reply, "accepted");
    result = cJSON_IsTrue(accepted) ? FH_CLOUD_OK : FH_CLOUD_REJECTED;
    cJSON_Delete(reply);
    return result;
}
