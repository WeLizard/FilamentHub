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
    uint32_t delay = retry_delay[index] ? retry_delay[index] * 2 : 5000;
    if (delay > 300000) delay = 300000;
    retry_delay[index] = delay;
    retry_at[index] = monotonic_ms() + delay;
}

static void clear_retry(int index)
{
    retry_delay[index] = 0;
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
        retry_later(index);
        return;
    }
    if (!connection->bridge_token[0] || cloud_disabled[index] ||
        !have_observation || !fh_telemetry_fresh(&latest, monotonic_ms())) {
        clear_retry(index);
        return;
    }
    if (!time_ready() || !fh_telemetry_fresh(&latest, monotonic_ms())) {
        retry_later(index);
        return;
    }
    if (last_upload_at[index] && monotonic_ms() - last_upload_at[index] <
        FH_UPLOAD_INTERVAL_MS) return;
    fh_cloud_result result = fh_cloud_snapshot(&config, index, &latest,
                                                monotonic_ms(), observed_at);
    last_upload_at[index] = monotonic_ms();
    if (result == FH_CLOUD_OK) clear_retry(index);
    else if (result == FH_CLOUD_REVOKED) revoke_token(index);
    else if (result == FH_CLOUD_REJECTED) {
        ESP_LOGW(TAG, "Observation rejected; repair connection %d", index + 1);
        cloud_disabled[index] = true;
        clear_retry(index);
    } else retry_later(index);
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
            if (monotonic_ms() < retry_at[index]) continue;
            fh_connection *connection = &config.connections[index];
            if (!connection->bridge_token[0] && !cloud_disabled[index]) {
                if (connection->pairing_code[0] && time_ready()) {
                    fh_cloud_result result = fh_cloud_pair(&config, index);
                    if (result == FH_CLOUD_OK) clear_retry(index);
                    else if (result == FH_CLOUD_REJECTED) {
                        ESP_LOGW(TAG, "Pairing rejected; provision a new code for connection %d",
                                 index + 1);
                        cloud_disabled[index] = true;
                    } else retry_later(index);
                }
            }
            observe_connection(index);
        }
        vTaskDelay(pdMS_TO_TICKS(config.connection_count ? 1000 : 30000));
    }
}
