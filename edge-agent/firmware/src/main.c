#include "bambu.h"
#include "ams_journal_flash.h"
#include "cloud.h"
#include "config.h"
#include "nfc_console.h"

#include "esp_event.h"
#include "esp_log.h"
#include "esp_netif.h"
#include "esp_netif_sntp.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "driver/usb_serial_jtag_vfs.h"
#include "nvs_flash.h"

#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include "freertos/task.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define FH_PROVISION_MAX 8192
#define FH_WIFI_CONNECTED BIT0
#define FH_SESSION_MS 20000ULL
#define FH_UPLOAD_INTERVAL_MS 15000ULL

static const char *TAG = "fh_edge";
static fh_config config;
static fh_config proposal;
static char provision_line[FH_PROVISION_MAX + 1];
static EventGroupHandle_t wifi_events;
static TaskHandle_t runtime_task;
static volatile bool provision_window_open;
static uint64_t retry_at[FH_MAX_CONNECTIONS];
static uint32_t retry_delay[FH_MAX_CONNECTIONS];
static uint64_t last_upload_at[FH_MAX_CONNECTIONS];
static bool cloud_disabled[FH_MAX_CONNECTIONS];
static uint32_t reject_delay[FH_MAX_CONNECTIONS];
static uint64_t cloud_retry_at[FH_MAX_CONNECTIONS];
static uint32_t auth_failures[FH_MAX_CONNECTIONS];
static uint64_t first_auth_failure_at[FH_MAX_CONNECTIONS];
static uint64_t last_heartbeat_at[FH_MAX_CONNECTIONS];
static bool heartbeat_sent[FH_MAX_CONNECTIONS];
static bool printer_unreachable[FH_MAX_CONNECTIONS];
static fh_ams_state diagnostic_feed;
static bool journal_warning_issued;

static uint64_t monotonic_ms(void)
{
    return (uint64_t)(esp_timer_get_time() / 1000);
}

static void wifi_event(void *arg, esp_event_base_t base, int32_t id, void *data)
{
    if (base == IP_EVENT && id == IP_EVENT_STA_GOT_IP)
        xEventGroupSetBits(wifi_events, FH_WIFI_CONNECTED);
    else if (base == WIFI_EVENT && id == WIFI_EVENT_STA_DISCONNECTED)
        xEventGroupClearBits(wifi_events, FH_WIFI_CONNECTED);
}

static bool wifi_start(void)
{
    if (esp_netif_init() != ESP_OK || esp_event_loop_create_default() != ESP_OK)
        return false;
    if (!esp_netif_create_default_wifi_sta()) return false;
    wifi_events = xEventGroupCreate();
    if (!wifi_events) return false;
    wifi_init_config_t defaults = WIFI_INIT_CONFIG_DEFAULT();
    if (esp_wifi_init(&defaults) != ESP_OK ||
        esp_event_handler_register(WIFI_EVENT, ESP_EVENT_ANY_ID, wifi_event, NULL) != ESP_OK ||
        esp_event_handler_register(IP_EVENT, IP_EVENT_STA_GOT_IP, wifi_event, NULL) != ESP_OK ||
        esp_wifi_set_mode(WIFI_MODE_STA) != ESP_OK) return false;
    wifi_config_t connection = {0};
    memcpy(connection.sta.ssid, config.wifi_ssid, strlen(config.wifi_ssid));
    memcpy(connection.sta.password, config.wifi_password, strlen(config.wifi_password));
    connection.sta.threshold.authmode = strlen(config.wifi_password) ? WIFI_AUTH_WPA2_PSK :
                                       WIFI_AUTH_OPEN;
    if (esp_wifi_set_config(WIFI_IF_STA, &connection) != ESP_OK ||
        esp_wifi_start() != ESP_OK) return false;
    esp_sntp_config_t sntp = ESP_NETIF_SNTP_DEFAULT_CONFIG("pool.ntp.org");
    esp_netif_sntp_init(&sntp);
    return true;
}

static bool wifi_ready(void)
{
    if (xEventGroupGetBits(wifi_events) & FH_WIFI_CONNECTED) return true;
    esp_wifi_connect();
    EventBits_t bits = xEventGroupWaitBits(wifi_events, FH_WIFI_CONNECTED,
                                           pdFALSE, pdTRUE, pdMS_TO_TICKS(10000));
    return (bits & FH_WIFI_CONNECTED) != 0;
}

static bool time_ready(void)
{
    time_t now = time(NULL);
    if (now >= 1704067200) return true;
    esp_netif_sntp_sync_wait(pdMS_TO_TICKS(10000));
    return time(NULL) >= 1704067200;
}

static void retry_later(int index)
{
    retry_delay[index] = fh_backoff_ms(retry_delay[index], FH_RETRY_INITIAL_MS,
                                       FH_RETRY_MAX_MS);
    retry_at[index] = monotonic_ms() + retry_delay[index];
}

/* The server answered but refused this request: wait longer, never give up.
 * Only cloud traffic waits; the printer is still observed locally meanwhile. */
static void reject_later(int index)
{
    reject_delay[index] = fh_backoff_ms(reject_delay[index], FH_REJECT_INITIAL_MS,
                                        FH_REJECT_MAX_MS);
    cloud_retry_at[index] = monotonic_ms() + reject_delay[index];
}

static void clear_retry(int index)
{
    retry_delay[index] = 0;
    reject_delay[index] = 0;
    cloud_retry_at[index] = 0;
    retry_at[index] = 0;
}

static void revoke_token(int index)
{
    fh_config *changed = malloc(sizeof(*changed));
    if (changed) {
        *changed = config;
        memset(changed->connections[index].bridge_token, 0,
               sizeof(changed->connections[index].bridge_token));
        if (fh_config_store(changed)) config = *changed;
        free(changed);
    }
    cloud_disabled[index] = true;
    clear_retry(index);
}

/* One place decides what a cloud answer means for the link, so a snapshot, a
 * heartbeat and a pairing request cannot disagree. The link is only ever
 * switched off for good by a credential the server repeatedly refuses. */
static void handle_cloud_result(int index, fh_cloud_result result)
{
    if (result != FH_CLOUD_REVOKED && result != FH_CLOUD_RETRY) auth_failures[index] = 0;
    switch (result) {
    case FH_CLOUD_OK:
        clear_retry(index);
        break;
    case FH_CLOUD_STALE:
        retry_at[index] = monotonic_ms() + FH_RETRY_INITIAL_MS;
        break;
    case FH_CLOUD_REVOKED:
        if (auth_failures[index] == 0) first_auth_failure_at[index] = monotonic_ms();
        auth_failures[index]++;
        if (fh_auth_failure_is_final(auth_failures[index], first_auth_failure_at[index],
                                     monotonic_ms())) {
            ESP_LOGW(TAG, "Token refused repeatedly; provision a new pairing code for connection %d",
                     index + 1);
            revoke_token(index);
            auth_failures[index] = 0;
        } else {
            reject_later(index);
        }
        break;
    case FH_CLOUD_REJECTED:
        ESP_LOGW(TAG, "Request refused by the server for connection %d; retrying later",
                 index + 1);
        reject_later(index);
        break;
    default:
        retry_later(index);
        break;
    }
}

static bool utc_now_text(char output[32])
{
    time_t now = time(NULL);
    if (now < 1704067200) return false;
    struct tm utc;
    gmtime_r(&now, &utc);
    return strftime(output, 32, "%Y-%m-%dT%H:%M:%S+00:00", &utc) > 0;
}

/* While the printer cannot be read the helper still reports in, flagged as
 * "printer unreachable", so a switched-off printer is not mistaken for a dead
 * link. Runs on its own clock, independent of the observation back-off. */
static void heartbeat_if_due(int index)
{
    fh_connection *connection = &config.connections[index];
    char observed_at[32];
    if (!printer_unreachable[index] || cloud_disabled[index] || !connection->bridge_token[0] ||
        monotonic_ms() < cloud_retry_at[index] ||
        !(xEventGroupGetBits(wifi_events) & FH_WIFI_CONNECTED) || !utc_now_text(observed_at) ||
        !fh_heartbeat_due(heartbeat_sent[index], last_heartbeat_at[index], monotonic_ms()))
        return;
    heartbeat_sent[index] = true;
    last_heartbeat_at[index] = monotonic_ms();
    fh_cloud_result result = fh_cloud_heartbeat(&config, index, false, observed_at);
    if (result == FH_CLOUD_REVOKED) handle_cloud_result(index, result);
}

static void print_ams_line(char *line)
{
    if (!line) return;
    puts(line);
    fflush(stdout);
    free(line);
}

static void provision_task(void *argument)
{
    while (provision_window_open) {
        size_t used = 0;
        bool oversized = false;
        for (;;) {
            int ch = getchar();
            if (ch == EOF) {
                clearerr(stdin);
                vTaskDelay(pdMS_TO_TICKS(50));
                if (!provision_window_open) break;
                continue;
            }
            if (ch == '\n') break;
            if (ch == '\r') continue;
            if (used >= FH_PROVISION_MAX) oversized = true;
            else provision_line[used++] = (char)ch;
        }
        if (!provision_window_open) break;
        provision_line[used] = '\0';
        if (oversized || !fh_config_parse_line(provision_line, used,
                                                config.version ? &config : NULL,
                                                &proposal) ||
            !fh_config_store(&proposal)) {
            memset(provision_line, 0, sizeof(provision_line));
            memset(&proposal, 0, sizeof(proposal));
            puts("Configuration rejected; saved configuration unchanged.");
            continue;
        }
        memset(provision_line, 0, sizeof(provision_line));
        puts("Configuration saved. Rebooting.");
        fflush(stdout);
        esp_restart();
    }
    xTaskNotifyGive(runtime_task);
    vTaskDelete(NULL);
}

static void observe_connection(int index)
{
    fh_connection *connection = &config.connections[index];
    if (!fh_bambu_start(connection)) {
        print_ams_line(fh_ams_lifecycle_json(connection->id, true));
        printer_unreachable[index] = true;
        retry_later(index);
        return;
    }
    uint64_t until = monotonic_ms() + FH_SESSION_MS;
    fh_telemetry latest = {0};
    char observed_at[32] = {0};
    char feed_observed_at[32] = {0};
    bool have_observation = false;
    bool have_ams = false;
    uint32_t last_feed_revision = 0;
    while (monotonic_ms() < until &&
           (xEventGroupGetBits(wifi_events) & FH_WIFI_CONNECTED) &&
           !fh_bambu_failed()) {
        uint32_t revision;
        if (fh_bambu_observation(&latest, observed_at, &revision))
            have_observation = true;
        uint32_t feed_revision;
        if (fh_bambu_ams_observation(&diagnostic_feed, feed_observed_at,
                                      &feed_revision) &&
            feed_revision != last_feed_revision && !fh_bambu_failed()) {
            last_feed_revision = feed_revision;
            have_ams = true;
            if (!fh_journal_flash_observe((size_t)index, &diagnostic_feed,
                                           feed_observed_at, monotonic_ms()) &&
                !journal_warning_issued) {
                ESP_LOGE(TAG, "AMS journal unavailable for connection %d", index + 1);
                journal_warning_issued = true;
            }
            print_ams_line(fh_ams_event_json(&diagnostic_feed, connection->id,
                                              feed_observed_at, monotonic_ms()));
        }
        vTaskDelay(pdMS_TO_TICKS(100));
    }
    bool failed = fh_bambu_failed();
    bool wifi_lost = !(xEventGroupGetBits(wifi_events) & FH_WIFI_CONNECTED);
    fh_bambu_stop();
    print_ams_line(fh_ams_lifecycle_json(connection->id, failed || wifi_lost));
    if (failed || wifi_lost || (!have_observation && !have_ams)) {
        printer_unreachable[index] = !wifi_lost;
        retry_later(index);
        return;
    }
    printer_unreachable[index] = false;
    if (!connection->bridge_token[0] || cloud_disabled[index] ||
        !have_observation || !fh_telemetry_fresh(&latest, monotonic_ms())) {
        clear_retry(index);
        return;
    }
    if (!time_ready() || !fh_telemetry_fresh(&latest, monotonic_ms())) {
        retry_later(index);
        return;
    }
    if (monotonic_ms() < cloud_retry_at[index]) return;
    if (last_upload_at[index] && monotonic_ms() - last_upload_at[index] <
        FH_UPLOAD_INTERVAL_MS) return;
    fh_cloud_result result = fh_cloud_snapshot(&config, index, &latest,
                                                monotonic_ms(), observed_at);
    last_upload_at[index] = monotonic_ms();
    handle_cloud_result(index, result);
}

void app_main(void)
{
    esp_err_t nvs = nvs_flash_init();
    if (nvs != ESP_OK) {
        ESP_LOGE(TAG, "Persistent storage unavailable; configuration kept intact");
        return;
    }
    bool configured = fh_config_load(&config);
    usb_serial_jtag_vfs_use_nonblocking();
    runtime_task = xTaskGetCurrentTaskHandle();
    provision_window_open = true;
    if (xTaskCreate(provision_task, "fh_provision", 8192, NULL, 5, NULL) != pdPASS) {
        ESP_LOGE(TAG, "Serial provisioning task unavailable");
        return;
    }
    if (configured) {
        puts("Serial provisioning open for 15 seconds; credentials are never echoed.");
        vTaskDelay(pdMS_TO_TICKS(15000));
        provision_window_open = false;
        ulTaskNotifyTake(pdTRUE, portMAX_DELAY);
    } else {
        puts("No saved configuration. Send one JSON line over serial to provision.");
        while (true) vTaskDelay(pdMS_TO_TICKS(1000));
    }
    if (!fh_journal_flash_start(&config))
        ESP_LOGE(TAG, "AMS journal unavailable; saved configuration kept intact");
    if (!fh_nfc_console_start(&config.nfc, config.cloud_origin))
        ESP_LOGE(TAG, "NFC serial task unavailable");
    if (!config.wifi_ssid[0]) {
        puts("NFC bench active without Wi-Fi; printer telemetry is unavailable.");
        return;
    }
    if (!wifi_start()) {
        ESP_LOGE(TAG, "Wi-Fi initialization failed");
        return;
    }
    while (true) {
        if (!wifi_ready()) {
            vTaskDelay(pdMS_TO_TICKS(5000));
            continue;
        }
        for (int index = 0; index < config.connection_count; index++) {
            heartbeat_if_due(index);
            if (monotonic_ms() < retry_at[index]) continue;
            fh_connection *connection = &config.connections[index];
            if (!connection->bridge_token[0] && !cloud_disabled[index]) {
                if (connection->pairing_code[0] && time_ready()) {
                    fh_cloud_result result = fh_cloud_pair(&config, index);
                    if (result == FH_CLOUD_REJECTED) {
                        /* A spent or invalid one-time code cannot heal by waiting. */
                        ESP_LOGW(TAG, "Pairing rejected; provision a new code for connection %d",
                                 index + 1);
                        cloud_disabled[index] = true;
                    } else handle_cloud_result(index, result);
                }
            }
            observe_connection(index);
        }
        vTaskDelay(pdMS_TO_TICKS(config.connection_count ? 1000 : 30000));
    }
}
