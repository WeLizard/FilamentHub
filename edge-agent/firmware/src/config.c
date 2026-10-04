#include "config.h"

#include "cJSON.h"
#include "esp_random.h"
#include "nvs.h"

#include <ctype.h>
#include <math.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define FH_CONFIG_VERSION 2U
#define FH_CONFIG_MAGIC 0x46484333U

typedef struct {
    uint32_t magic;
    uint32_t generation;
    uint32_t crc;
    fh_config config;
} fh_saved_config;

typedef struct {
    uint32_t version;
    char node_instance_id[49];
    char wifi_ssid[33];
    char wifi_password[65];
    char cloud_origin[254];
    bool allow_local_http;
    uint8_t connection_count;
    fh_connection connections[FH_MAX_CONNECTIONS];
} fh_config_v1;

typedef struct {
    uint32_t magic;
    uint32_t generation;
    uint32_t crc;
    fh_config_v1 config;
} fh_saved_config_v1;

_Static_assert(sizeof(fh_config_v1) == offsetof(fh_config, nfc),
               "Version-1 configuration layout changed");
_Static_assert(offsetof(fh_saved_config_v1, config) ==
                   offsetof(fh_saved_config, config),
               "Version-1 NVS header layout changed");

static uint32_t active_generation;
static int active_slot = -1;

static uint32_t crc32_bytes(const void *data, size_t length)
{
    const unsigned char *bytes = data;
    uint32_t crc = UINT32_MAX;
    for (size_t i = 0; i < length; i++) {
        crc ^= bytes[i];
        for (int bit = 0; bit < 8; bit++)
            crc = (crc >> 1) ^ (0xedb88320U & (0U - (crc & 1U)));
    }
    return ~crc;
}

static bool saved_valid(const fh_saved_config *value)
{
    return value->magic == FH_CONFIG_MAGIC && value->config.version == FH_CONFIG_VERSION &&
           value->generation != 0 &&
           value->crc == crc32_bytes(&value->config, sizeof(value->config));
}

static bool legacy_valid(const fh_saved_config_v1 *value)
{
    return value->magic == FH_CONFIG_MAGIC && value->config.version == 1U &&
           value->generation != 0 &&
           value->crc == crc32_bytes(&value->config, sizeof(value->config));
}

bool fh_config_load(fh_config *out)
{
    nvs_handle_t handle;
    if (nvs_open("fh_edge", NVS_READONLY, &handle) != ESP_OK) return false;
    fh_saved_config *candidate = malloc(sizeof(*candidate));
    if (!candidate) { nvs_close(handle); return false; }
    bool found = false;
    for (int slot = 0; slot < 2; slot++) {
        size_t length = sizeof(*candidate);
        if (nvs_get_blob(handle, slot ? "config_b" : "config_a", candidate, &length) != ESP_OK)
            continue;
        bool current = length == sizeof(*candidate) && saved_valid(candidate);
        bool legacy = length == sizeof(fh_saved_config_v1) &&
                      legacy_valid((const fh_saved_config_v1 *)candidate);
        if (!current && !legacy) continue;
        if (!found || candidate->generation > active_generation) {
            if (current) *out = candidate->config;
            else {
                memset(out, 0, sizeof(*out));
                memcpy(out, &((fh_saved_config_v1 *)candidate)->config,
                       sizeof(fh_config_v1));
                out->version = FH_CONFIG_VERSION;
            }
            active_generation = candidate->generation;
            active_slot = slot;
            found = true;
        }
    }
    free(candidate);
    nvs_close(handle);
    if (found) {
        for (int i = 0; i < out->connection_count; i++) {
            fh_connection *conn = &out->connections[i];
            conn->sequence_next = conn->sequence_reserved_high + 1;
        }
    }
    return found;
}

bool fh_config_store(const fh_config *value)
{
    if (active_generation == UINT32_MAX) return false;
    fh_saved_config *saved = malloc(sizeof(*saved));
    if (!saved) return false;
    saved->magic = FH_CONFIG_MAGIC;
    saved->generation = active_generation + 1;
    saved->config = *value;
    saved->crc = crc32_bytes(&saved->config, sizeof(saved->config));
    nvs_handle_t handle;
    if (nvs_open("fh_edge", NVS_READWRITE, &handle) != ESP_OK) {
        free(saved);
        return false;
    }
    int next_slot = active_slot == 0 ? 1 : 0;
    esp_err_t err = nvs_set_blob(handle, next_slot ? "config_b" : "config_a",
                                  saved, sizeof(*saved));
    if (err == ESP_OK) err = nvs_commit(handle);
    nvs_close(handle);
    free(saved);
    if (err != ESP_OK) return false;
    active_generation++;
    active_slot = next_slot;
    return true;
}

void fh_random_identity(char output[49])
{
    unsigned char bytes[16];
    esp_fill_random(bytes, sizeof(bytes));
    memcpy(output, "edge-", 5);
    for (int i = 0; i < 16; i++) snprintf(output + 5 + 2 * i, 3, "%02x", bytes[i]);
}

bool fh_nfc_pins_valid(const fh_nfc_pins *pins)
{
    if (!pins || !pins->enabled) return false;
    const uint8_t values[6] = {pins->sck, pins->miso, pins->mosi,
                                pins->nss, pins->busy, pins->rst};
    for (size_t i = 0; i < 6; i++) {
        uint8_t pin = values[i];
        if (pin > 21 || pin == 2 || pin == 8 || pin == 9 || pin == 11 ||
            (pin >= 12 && pin <= 19)) return false;
        for (size_t j = 0; j < i; j++) if (pin == values[j]) return false;
    }
    return true;
}

static bool pin_field(const cJSON *parent, const char *key, uint8_t *out)
{
    const cJSON *item = cJSON_GetObjectItemCaseSensitive(parent, key);
    if (!cJSON_IsNumber(item) || !isfinite(item->valuedouble) ||
        item->valuedouble < 0 || item->valuedouble > 21 ||
        floor(item->valuedouble) != item->valuedouble) return false;
    *out = (uint8_t)item->valueint;
    return true;
}

static bool string_field(const cJSON *parent, const char *key, char *target,
                         size_t capacity, size_t min_length)
{
    const cJSON *field = cJSON_GetObjectItemCaseSensitive(parent, key);
    if (!cJSON_IsString(field) || !field->valuestring) return false;
    size_t length = strlen(field->valuestring);
    if (length < min_length || length >= capacity) return false;
    memcpy(target, field->valuestring, length + 1);
    return true;
}

static bool one_line_secret(const char *value)
{
    for (const unsigned char *p = (const unsigned char *)value; *p; p++)
        if (*p < 32 || *p == 127) return false;
    return true;
}

static bool object_keys(const cJSON *object, const char *const *allowed, size_t count)
{
    for (const cJSON *item = object->child; item; item = item->next) {
        if (!item->string) return false;
        bool recognized = false;
        for (size_t i = 0; i < count; i++)
            if (strcmp(item->string, allowed[i]) == 0) recognized = true;
        if (!recognized) return false;
        for (const cJSON *prior = object->child; prior != item; prior = prior->next)
            if (strcmp(prior->string, item->string) == 0) return false;
    }
    return true;
}

bool fh_config_parse_line(const char *line, size_t length,
                          const fh_config *previous, fh_config *out)
{
    if (!fh_json_shape_ok(line, length, 12) || line[length] != '\0') return false;
    cJSON *root = cJSON_ParseWithLengthOpts(line, length + 1, NULL, true);
    if (!cJSON_IsObject(root)) { cJSON_Delete(root); return false; }
    static const char *const root_keys[] = {"wifi", "cloud", "connections", "nfc"};
    static const char *const wifi_keys[] = {"ssid", "password"};
    static const char *const cloud_keys[] = {"origin", "allow_local_http"};
    static const char *const connection_keys[] = {
        "id", "host", "serial", "access_code", "bambu_cert_pem", "pairing_code",
    };
    static const char *const nfc_keys[] = {"sck", "miso", "mosi", "nss", "busy", "rst"};
    const cJSON *wifi = cJSON_GetObjectItemCaseSensitive(root, "wifi");
    const cJSON *cloud = cJSON_GetObjectItemCaseSensitive(root, "cloud");
    const cJSON *connections = cJSON_GetObjectItemCaseSensitive(root, "connections");
    bool valid = (!wifi || cJSON_IsObject(wifi)) && cJSON_IsObject(cloud) &&
                 cJSON_IsArray(connections) &&
                 cJSON_GetArraySize(connections) <= FH_MAX_CONNECTIONS &&
                 object_keys(root, root_keys, 4) &&
                 (!wifi || object_keys(wifi, wifi_keys, 2)) &&
                 object_keys(cloud, cloud_keys, 2);
    if (!valid) { cJSON_Delete(root); return false; }
    memset(out, 0, sizeof(*out));
    out->version = FH_CONFIG_VERSION;
    if (previous && fh_valid_id(previous->node_instance_id, 48))
        memcpy(out->node_instance_id, previous->node_instance_id,
               sizeof(out->node_instance_id));
    else fh_random_identity(out->node_instance_id);
    const cJSON *allow_http = cJSON_GetObjectItemCaseSensitive(cloud, "allow_local_http");
    if (allow_http && !cJSON_IsBool(allow_http)) valid = false;
    out->allow_local_http = cJSON_IsTrue(allow_http);
    valid = valid &&
            (!wifi ||
             (string_field(wifi, "ssid", out->wifi_ssid, sizeof(out->wifi_ssid), 0) &&
              string_field(wifi, "password", out->wifi_password,
                           sizeof(out->wifi_password), 0))) &&
            string_field(cloud, "origin", out->cloud_origin, sizeof(out->cloud_origin), 1) &&
            fh_valid_origin(out->cloud_origin, out->allow_local_http) &&
            one_line_secret(out->wifi_password);
    if (!valid) { cJSON_Delete(root); return false; }
    out->connection_count = (uint8_t)cJSON_GetArraySize(connections);
    const cJSON *nfc = cJSON_GetObjectItemCaseSensitive(root, "nfc");
    if (nfc) {
        out->nfc.enabled = true;
        valid = cJSON_IsObject(nfc) && object_keys(nfc, nfc_keys, 6) &&
                pin_field(nfc, "sck", &out->nfc.sck) &&
                pin_field(nfc, "miso", &out->nfc.miso) &&
                pin_field(nfc, "mosi", &out->nfc.mosi) &&
                pin_field(nfc, "nss", &out->nfc.nss) &&
                pin_field(nfc, "busy", &out->nfc.busy) &&
                pin_field(nfc, "rst", &out->nfc.rst) &&
                fh_nfc_pins_valid(&out->nfc);
        if (!valid) { cJSON_Delete(root); return false; }
    }
    if (out->connection_count && !out->wifi_ssid[0]) {
        cJSON_Delete(root);
        return false;
    }
    for (int i = 0; i < out->connection_count; i++) {
        const cJSON *item = cJSON_GetArrayItem(connections, i);
        fh_connection *conn = &out->connections[i];
        valid = cJSON_IsObject(item) && object_keys(item, connection_keys, 6) &&
                string_field(item, "id", conn->id, sizeof(conn->id), 1) &&
                string_field(item, "host", conn->host, sizeof(conn->host), 1) &&
                string_field(item, "serial", conn->serial, sizeof(conn->serial), 4) &&
                string_field(item, "access_code", conn->access_code,
                             sizeof(conn->access_code), 1) &&
                string_field(item, "bambu_cert_pem", conn->bambu_cert_pem,
                             sizeof(conn->bambu_cert_pem), 64) &&
                fh_valid_id(conn->id, 32) && fh_private_ipv4(conn->host) &&
                fh_valid_serial(conn->serial) && one_line_secret(conn->access_code) &&
                strncmp(conn->bambu_cert_pem, "-----BEGIN CERTIFICATE-----", 27) == 0 &&
                strstr(conn->bambu_cert_pem, "-----END CERTIFICATE-----") != NULL;
        if (!valid) break;
        const cJSON *code = cJSON_GetObjectItemCaseSensitive(item, "pairing_code");
        if (code && (!cJSON_IsString(code) || !code->valuestring ||
                     strlen(code->valuestring) >= sizeof(conn->pairing_code))) {
            valid = false;
            break;
        }
        if (code && code->valuestring) strcpy(conn->pairing_code, code->valuestring);
        const fh_connection *prior = NULL;
        if (previous && strcmp(previous->cloud_origin, out->cloud_origin) == 0 &&
            previous->allow_local_http == out->allow_local_http)
            for (int old = 0; old < previous->connection_count; old++) {
            if (strcmp(previous->connections[old].id, conn->id) == 0 &&
                strcmp(previous->connections[old].serial, conn->serial) == 0) {
                prior = &previous->connections[old];
                break;
            }
        }
        if (prior) {
            strcpy(conn->source_instance_id, prior->source_instance_id);
            conn->physical_printer_id = prior->physical_printer_id;
            conn->material_system_id = prior->material_system_id;
            conn->sequence_reserved_high = prior->sequence_reserved_high;
            conn->sequence_next = prior->sequence_reserved_high + 1;
            if (!conn->pairing_code[0]) strcpy(conn->bridge_token, prior->bridge_token);
        } else fh_random_identity(conn->source_instance_id);
        if (!conn->bridge_token[0] && conn->pairing_code[0] &&
            (strlen(conn->pairing_code) < 8 || strlen(conn->pairing_code) > 32 ||
             !one_line_secret(conn->pairing_code))) valid = false;
        for (int previous_index = 0; previous_index < i; previous_index++)
            if (strcmp(out->connections[previous_index].id, conn->id) == 0 ||
                strcmp(out->connections[previous_index].serial, conn->serial) == 0) valid = false;
        if (!valid) break;
    }
    cJSON_Delete(root);
    return valid;
}
