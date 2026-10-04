#include "bambu.h"
#include "report.h"

#include "esp_log.h"
#include "esp_timer.h"
#include "mqtt_client.h"
#include "freertos/semphr.h"

#include <stdio.h>
#include <string.h>
#include <time.h>

typedef struct {
    esp_mqtt_client_handle_t client;
    portMUX_TYPE lock;
    fh_frame frame;
    fh_telemetry facts;
    SemaphoreHandle_t feed_mutex;
    fh_ams_state feed;
    char feed_observed_at[32];
    uint32_t feed_revision;
    char observed_at[32];
    char job_key[180];
    char topic[100];
    char request_topic[100];
    bool valid_topic;
    bool failed;
    bool pending;
    uint32_t revision;
} bambu_session;

static bambu_session session = {.lock = portMUX_INITIALIZER_UNLOCKED};

static void receive_report(const char *payload, size_t length)
{
    uint64_t now_ms = (uint64_t)(esp_timer_get_time() / 1000);
    time_t wall_time = time(NULL);
    char observed_at[32] = {0};
    if (wall_time >= 1704067200) {
        struct tm utc;
        gmtime_r(&wall_time, &utc);
        strftime(observed_at, sizeof(observed_at), "%Y-%m-%dT%H:%M:%SZ", &utc);
    }
    fh_telemetry updated;
    char updated_job_key[180];
    portENTER_CRITICAL(&session.lock);
    updated = session.facts;
    strcpy(updated_job_key, session.job_key);
    portEXIT_CRITICAL(&session.lock);
    bool changed = fh_report_apply(&updated, updated_job_key,
                                   payload, length, now_ms);
    if (xSemaphoreTake(session.feed_mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        if (fh_ams_apply(&session.feed, payload, length, now_ms) == FH_AMS_OBSERVED) {
            strcpy(session.feed_observed_at, observed_at);
            session.feed_revision++;
        }
        xSemaphoreGive(session.feed_mutex);
    }
    portENTER_CRITICAL(&session.lock);
    session.facts = updated;
    strcpy(session.job_key, updated_job_key);
    if (changed && observed_at[0]) {
        strcpy(session.observed_at, observed_at);
        session.pending = true;
        session.revision++;
    }
    portEXIT_CRITICAL(&session.lock);
}

static void mqtt_event(void *arg, esp_event_base_t base, int32_t event_id, void *event_data)
{
    esp_mqtt_event_handle_t event = event_data;
    if (event_id == MQTT_EVENT_CONNECTED) {
        esp_mqtt_client_subscribe(event->client, session.topic, 0);
    } else if (event_id == MQTT_EVENT_SUBSCRIBED) {
        const char *request = "{\"pushing\":{\"sequence_id\":\"0\",\"command\":\"pushall\"}}";
        esp_mqtt_client_publish(event->client, session.request_topic, request, 0, 0, 0);
    } else if (event_id == MQTT_EVENT_DATA) {
        if (event->current_data_offset == 0) {
            session.valid_topic = event->topic_len == (int)strlen(session.topic) &&
                                  memcmp(event->topic, session.topic, event->topic_len) == 0;
        }
        if (!session.valid_topic || event->data_len < 0 || event->total_data_len < 0 ||
            event->current_data_offset < 0) {
            fh_frame_reset(&session.frame);
            return;
        }
        if (fh_frame_feed(&session.frame, event->data, (size_t)event->data_len,
                          (size_t)event->current_data_offset,
                          (size_t)event->total_data_len)) {
            receive_report(session.frame.data, session.frame.length);
            fh_frame_reset(&session.frame);
        }
    } else if (event_id == MQTT_EVENT_DISCONNECTED || event_id == MQTT_EVENT_ERROR) {
        portENTER_CRITICAL(&session.lock);
        fh_telemetry_reset(&session.facts);
        session.pending = false;
        session.observed_at[0] = '\0';
        session.job_key[0] = '\0';
        session.failed = true;
        portEXIT_CRITICAL(&session.lock);
        if (xSemaphoreTake(session.feed_mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
            fh_ams_reset(&session.feed);
            session.feed_observed_at[0] = '\0';
            session.feed_revision = 0;
            xSemaphoreGive(session.feed_mutex);
        }
        fh_frame_reset(&session.frame);
    }
}

bool fh_bambu_start(const fh_connection *connection)
{
    if (session.client) return false;
    if (!session.feed_mutex) {
        session.feed_mutex = xSemaphoreCreateMutex();
        if (!session.feed_mutex) return false;
    }
    fh_frame_reset(&session.frame);
    if (xSemaphoreTake(session.feed_mutex, pdMS_TO_TICKS(1000)) != pdTRUE)
        return false;
    fh_ams_reset(&session.feed);
    session.feed_observed_at[0] = '\0';
    session.feed_revision = 0;
    xSemaphoreGive(session.feed_mutex);
    portENTER_CRITICAL(&session.lock);
    fh_telemetry_reset(&session.facts);
    session.observed_at[0] = '\0';
    session.job_key[0] = '\0';
    session.pending = false;
    session.failed = false;
    session.revision = 0;
    portEXIT_CRITICAL(&session.lock);
    if (snprintf(session.topic, sizeof(session.topic), "device/%s/report",
                 connection->serial) >= sizeof(session.topic) ||
        snprintf(session.request_topic, sizeof(session.request_topic), "device/%s/request",
                 connection->serial) >= sizeof(session.request_topic)) return false;
    esp_mqtt_client_config_t config = {
        .broker.address.hostname = connection->host,
        .broker.address.port = 8883,
        .broker.address.transport = MQTT_TRANSPORT_OVER_SSL,
        .broker.verification.certificate = connection->bambu_cert_pem,
        .broker.verification.common_name = connection->serial,
        .credentials.username = "bblp",
        .credentials.authentication.password = connection->access_code,
        .session.keepalive = 20,
        .network.disable_auto_reconnect = true,
        .network.timeout_ms = 8000,
        .task.stack_size = 8192,
        .buffer.size = 2048,
    };
    session.client = esp_mqtt_client_init(&config);
    if (!session.client) return false;
    if (esp_mqtt_client_register_event(session.client, ESP_EVENT_ANY_ID,
                                       mqtt_event, NULL) != ESP_OK ||
        esp_mqtt_client_start(session.client) != ESP_OK) {
        esp_mqtt_client_destroy(session.client);
        session.client = NULL;
        return false;
    }
    return true;
}

void fh_bambu_stop(void)
{
    if (session.client) {
        esp_mqtt_client_stop(session.client);
        esp_mqtt_client_destroy(session.client);
        session.client = NULL;
    }
    portENTER_CRITICAL(&session.lock);
    fh_telemetry_reset(&session.facts);
    session.observed_at[0] = '\0';
    session.pending = false;
    portEXIT_CRITICAL(&session.lock);
    if (session.feed_mutex &&
        xSemaphoreTake(session.feed_mutex, pdMS_TO_TICKS(1000)) == pdTRUE) {
        fh_ams_reset(&session.feed);
        session.feed_observed_at[0] = '\0';
        session.feed_revision = 0;
        xSemaphoreGive(session.feed_mutex);
    }
    fh_frame_reset(&session.frame);
}

bool fh_bambu_failed(void)
{
    portENTER_CRITICAL(&session.lock);
    bool failed = session.failed;
    portEXIT_CRITICAL(&session.lock);
    return failed;
}

bool fh_bambu_observation(fh_telemetry *facts, char observed_at[32],
                          uint32_t *revision)
{
    portENTER_CRITICAL(&session.lock);
    bool pending = session.pending && !session.failed;
    if (pending) {
        *facts = session.facts;
        strcpy(observed_at, session.observed_at);
        *revision = session.revision;
    }
    portEXIT_CRITICAL(&session.lock);
    return pending;
}

void fh_bambu_ack(uint32_t revision)
{
    portENTER_CRITICAL(&session.lock);
    if (session.revision == revision) session.pending = false;
    portEXIT_CRITICAL(&session.lock);
}

bool fh_bambu_ams_observation(fh_ams_state *feed, char observed_at[32],
                               uint32_t *revision)
{
    if (!feed || !observed_at || !revision || !session.feed_mutex ||
        xSemaphoreTake(session.feed_mutex, pdMS_TO_TICKS(1000)) != pdTRUE)
        return false;
    bool available = session.feed_revision > 0;
    if (available) {
        *feed = session.feed;
        strcpy(observed_at, session.feed_observed_at);
        *revision = session.feed_revision;
    }
    xSemaphoreGive(session.feed_mutex);
    return available && !fh_bambu_failed();
}
