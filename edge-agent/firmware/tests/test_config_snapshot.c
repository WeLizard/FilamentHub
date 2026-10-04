#include "config.h"
#include "snapshot.h"
#include "report.h"
#include "cJSON.h"
#include "nvs.h"

#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned char slots[2][8192];
static size_t slot_lengths[2];
static unsigned char staged[8192];
static size_t staged_length;
static int staged_slot;
static bool fail_commit;
static unsigned random_seed = 1;

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

void esp_fill_random(void *data, size_t length)
{
    unsigned char *bytes = data;
    for (size_t i = 0; i < length; i++) bytes[i] = (unsigned char)random_seed++;
}

esp_err_t nvs_open(const char *name, int mode, nvs_handle_t *handle)
{
    (void)mode;
    if (strcmp(name, "fh_edge") != 0) return 1;
    *handle = 1;
    return ESP_OK;
}

esp_err_t nvs_get_blob(nvs_handle_t handle, const char *key, void *data, size_t *length)
{
    (void)handle;
    int slot = strcmp(key, "config_b") == 0 ? 1 : 0;
    if (!slot_lengths[slot] || *length < slot_lengths[slot]) return 1;
    memcpy(data, slots[slot], slot_lengths[slot]);
    *length = slot_lengths[slot];
    return ESP_OK;
}

esp_err_t nvs_set_blob(nvs_handle_t handle, const char *key, const void *data,
                       size_t length)
{
    (void)handle;
    if (length > sizeof(staged)) return 1;
    staged_slot = strcmp(key, "config_b") == 0 ? 1 : 0;
    staged_length = length;
    memcpy(staged, data, length);
    return ESP_OK;
}

esp_err_t nvs_commit(nvs_handle_t handle)
{
    (void)handle;
    if (fail_commit) return 1;
    memcpy(slots[staged_slot], staged, staged_length);
    slot_lengths[staged_slot] = staged_length;
    staged_length = 0;
    return ESP_OK;
}

void nvs_close(nvs_handle_t handle) { (void)handle; }

static bool parse(const char *line, const fh_config *previous, fh_config *out)
{
    return fh_config_parse_line(line, strlen(line), previous, out);
}

int main(void)
{
    static fh_config config, reloaded, changed;
    const char *line = "{\"wifi\":{\"ssid\":\"LAB\",\"password\":\"PASSWORD\"},"
        "\"cloud\":{\"origin\":\"https://filamenthub.ru\"},"
        "\"connections\":[{\"id\":\"p2s\",\"host\":\"192.168.1.44\","
        "\"serial\":\"P2S-1234\",\"access_code\":\"ABCDEFGH\","
        "\"bambu_cert_pem\":\"-----BEGIN CERTIFICATE-----\\n"
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\\n"
        "-----END CERTIFICATE-----\\n\",\"pairing_code\":\"12345678\"}]}";
    assert(parse(line, NULL, &config));
    assert(config.connection_count == 1);
    assert(strlen(config.node_instance_id) >= 16);
    assert(strlen(config.connections[0].source_instance_id) >= 16);
    assert(fh_config_store(&config));
    assert(fh_config_load(&reloaded));
    assert(strcmp(reloaded.connections[0].serial, "P2S-1234") == 0);

    strcpy(reloaded.connections[0].bridge_token, "fhpb_scoped");
    reloaded.connections[0].physical_printer_id = 3;
    reloaded.connections[0].material_system_id = 5;
    reloaded.connections[0].sequence_reserved_high = 1024;
    assert(fh_config_store(&reloaded));
    assert(fh_config_load(&config));
    assert(config.connections[0].sequence_next == 1025);

    char same[2048];
    strcpy(same, line);
    char *code = strstr(same, ",\"pairing_code\":\"12345678\"");
    assert(code);
    memmove(code, code + strlen(",\"pairing_code\":\"12345678\""),
            strlen(code + strlen(",\"pairing_code\":\"12345678\"")) + 1);
    assert(parse(same, &config, &changed));
    assert(strcmp(changed.connections[0].bridge_token, "fhpb_scoped") == 0);
    assert(changed.connections[0].sequence_next == 1025);
    assert(parse(same, NULL, &changed));
    assert(!changed.connections[0].bridge_token[0]);
    assert(!changed.connections[0].pairing_code[0]);

    char other[2048];
    strcpy(other, same);
    char *origin = strstr(other, "filamenthub.ru");
    assert(origin);
    memcpy(origin, "other-site.net", strlen("other-site.net"));
    assert(parse(other, &config, &changed));
    assert(!changed.connections[0].bridge_token[0]);
    assert(strcmp(changed.connections[0].source_instance_id,
                  config.connections[0].source_instance_id) != 0);
    char changed_id[2048];
    strcpy(changed_id, same);
    char *id = strstr(changed_id, "\"id\":\"p2s\"");
    assert(id);
    id[strlen("\"id\":\"p2")] = 'x';
    assert(parse(changed_id, &config, &changed));
    assert(!changed.connections[0].bridge_token[0]);
    char changed_serial[2048];
    strcpy(changed_serial, same);
    char *serial = strstr(changed_serial, "P2S-1234");
    assert(serial);
    memcpy(serial, "P2S-9999", 8);
    assert(parse(changed_serial, &config, &changed));
    assert(!changed.connections[0].bridge_token[0]);
    assert(!parse("{\"wifi\":{},\"cloud\":{},\"connections\":[],\"typo\":1}",
                  &config, &changed));
    assert(!parse("{\"wifi\":{},\"wifi\":{},\"cloud\":{},\"connections\":[]}",
                  &config, &changed));
    assert(!parse("{\"wifi\":{\"ssid\":\"a\\u0000b\"},\"cloud\":{},\"connections\":[]}",
                  &config, &changed));
    char trailing[2050];
    snprintf(trailing, sizeof(trailing), "%s evil", line);
    assert(!parse(trailing, &config, &changed));
    const char *nfc_line = "{\"wifi\":{\"ssid\":\"LAB\",\"password\":\"PASSWORD\"},"
        "\"cloud\":{\"origin\":\"https://filamenthub.ru\"},"
        "\"connections\":[],\"nfc\":{\"sck\":0,\"miso\":1,\"mosi\":3,"
        "\"nss\":4,\"busy\":5,\"rst\":6}}";
    assert(parse(nfc_line, &config, &changed));
    assert(changed.nfc.enabled && changed.nfc.rst == 6);
    assert(parse("{\"cloud\":{\"origin\":\"http://192.168.1.2:3000\","
                 "\"allow_local_http\":true},\"connections\":[],"
                 "\"nfc\":{\"sck\":0,\"miso\":1,\"mosi\":3,"
                 "\"nss\":4,\"busy\":5,\"rst\":6}}", &config, &changed));
    assert(changed.nfc.enabled && !changed.wifi_ssid[0]);
    fh_nfc_pins pins = changed.nfc;
    pins.rst = 18;
    assert(!fh_nfc_pins_valid(&pins));
    pins.rst = 2;
    assert(!fh_nfc_pins_valid(&pins));
    pins.rst = pins.sck;
    assert(!fh_nfc_pins_valid(&pins));
    assert(parse("{\"wifi\":{\"ssid\":\"LAB\",\"password\":\"PASSWORD\"},"
                 "\"cloud\":{\"origin\":\"https://filamenthub.ru\"},"
                 "\"connections\":[]}", &config, &changed));
    assert(!changed.nfc.enabled);

    changed = config;
    strcpy(changed.wifi_ssid, "CHANGED");
    fail_commit = true;
    assert(!fh_config_store(&changed));
    fail_commit = false;
    assert(fh_config_load(&reloaded));
    assert(strcmp(reloaded.wifi_ssid, "LAB") == 0);

    fh_telemetry facts;
    fh_telemetry_reset(&facts);
    fh_text_update(&facts.state, "printing", 1000);
    fh_text_update(&facts.job_name, "part \"quoted\".gcode", 1000);
    fh_number_update(&facts.progress, 73, 1000);
    fh_number_update(&facts.nozzle, 220.5, 1000);
    char *body = fh_snapshot_body(&config, 0, &facts, 2000,
                                  "2026-10-03T10:00:00Z", 1025);
    assert(body);
    cJSON *snapshot = cJSON_Parse(body);
    assert(snapshot);
    assert(strcmp(cJSON_GetObjectItem(snapshot, "provider")->valuestring, "bambu") == 0);
    assert(strcmp(cJSON_GetObjectItem(snapshot, "transport")->valuestring, "edge_agent") == 0);
    assert(cJSON_GetObjectItem(snapshot, "sequence")->valuedouble == 1025);
    assert(cJSON_GetObjectItem(snapshot, "device_identity") == NULL);
    assert(cJSON_GetArraySize(cJSON_GetObjectItem(snapshot, "slots")) == 0);
    assert(cJSON_IsFalse(cJSON_GetObjectItem(snapshot, "slot_topology_complete")));
    cJSON *capabilities = cJSON_GetObjectItem(snapshot, "capabilities");
    assert(cJSON_GetArraySize(capabilities) == 1);
    assert(strcmp(cJSON_GetArrayItem(capabilities, 0)->valuestring, "read") == 0);
    cJSON *printer = cJSON_GetObjectItem(snapshot, "printer");
    assert(strcmp(cJSON_GetObjectItem(printer, "state")->valuestring, "printing") == 0);
    assert(cJSON_GetObjectItem(printer, "progress_percent")->valueint == 73);
    assert(strcmp(cJSON_GetObjectItem(printer, "job_name")->valuestring,
                  "part \"quoted\".gcode") == 0);
    cJSON_Delete(snapshot);
    free(body);
    assert(!fh_snapshot_body(&config, 0, &facts, 31001,
                             "2026-10-03T10:00:00Z", 1026));
    char job_key[180] = {0};
    fh_telemetry_reset(&facts);
    const char *full = "{\"print\":{\"command\":\"push_status\",\"msg\":0,"
                       "\"task_id\":\"1\",\"gcode_state\":\"RUNNING\","
                       "\"subtask_name\":\"job-a\",\"mc_percent\":42}}";
    assert(fh_report_apply(&facts, job_key, full, strlen(full), 1000));
    assert(strcmp(facts.state.value, "printing") == 0);
    assert(facts.progress.value == 42);
    const char *partial = "{\"print\":{\"nozzle_temper\":230.5}}";
    assert(fh_report_apply(&facts, job_key, partial, strlen(partial), 2000));
    assert(facts.progress.value == 42 && facts.progress.at_ms == 1000);
    assert(facts.nozzle.value == 230.5 && facts.nozzle.at_ms == 2000);
    const char *new_job = "{\"print\":{\"task_id\":\"2\","
                          "\"gcode_state\":\"PREPARE\"}}";
    assert(fh_report_apply(&facts, job_key, new_job, strlen(new_job), 3000));
    assert(strcmp(facts.state.value, "preparing") == 0);
    assert(!facts.progress.known && !facts.job_name.known);
    assert(fh_report_apply(&facts, job_key, full, strlen(full), 4000));
    const char *empty_full = "{\"print\":{\"command\":\"push_status\","
                             "\"msg\":0,\"gcode_state\":\"IDLE\"}}";
    assert(fh_report_apply(&facts, job_key, empty_full, strlen(empty_full), 5000));
    assert(!facts.progress.known && !facts.job_name.known);
    fh_telemetry_reset(&facts);
    job_key[0] = '\0';
    assert(!fh_telemetry_fresh(&facts, 5001));
    assert(fh_report_apply(&facts, job_key, partial, strlen(partial), 6000));
    assert(!facts.state.known && !facts.progress.known && facts.nozzle.known);
    typedef struct {
        uint32_t version;
        char node_instance_id[49];
        char wifi_ssid[33];
        char wifi_password[65];
        char cloud_origin[254];
        bool allow_local_http;
        uint8_t connection_count;
        fh_connection connections[FH_MAX_CONNECTIONS];
    } old_config;
    struct {
        uint32_t magic, generation, crc;
        old_config config;
    } legacy = {0};
    assert(sizeof(old_config) == 5464);
    assert((unsigned char *)&legacy.config - (unsigned char *)&legacy == 16);
    legacy.magic = 0x46484333U;
    legacy.generation = 999;
    fh_config old = config;
    old.version = 1;
    memcpy(&legacy.config, &old, sizeof(legacy.config));
    legacy.crc = crc32_bytes(&legacy.config, sizeof(legacy.config));
    memcpy(slots[0], &legacy, sizeof(legacy));
    slot_lengths[0] = sizeof(legacy);
    assert(fh_config_load(&reloaded));
    assert(reloaded.version == 2 && !reloaded.nfc.enabled);
    assert(strcmp(reloaded.connections[0].serial, "P2S-1234") == 0);
    assert(fh_config_store(&reloaded));
    assert(fh_config_load(&changed) && changed.version == 2);
    puts("Config and snapshot host tests passed");
    return 0;
}
