#include "ams_journal_flash.h"
#include "ams_journal.h"

#include "esp_partition.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"

#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static fh_ams_journal journal;
static const esp_partition_t *partition;
static SemaphoreHandle_t mutex;
static fh_journal_entry *replay;

static void poll_task(void *argument)
{
    (void)argument;
    while (true) {
        fh_journal_flash_poll((uint64_t)(esp_timer_get_time() / 1000));
        vTaskDelay(pdMS_TO_TICKS(5000));
    }
}

static bool flash_read(void *context, size_t offset, void *data, size_t length)
{
    return esp_partition_read(context, offset, data, length) == ESP_OK;
}

static bool flash_write(void *context, size_t offset, const void *data, size_t length)
{
    return esp_partition_write(context, offset, data, length) == ESP_OK;
}

static bool flash_erase(void *context, size_t offset, size_t length)
{
    return esp_partition_erase_range(context, offset, length) == ESP_OK;
}

bool fh_journal_flash_start(const fh_config *config)
{
    if (!config || config->connection_count > FH_MAX_CONNECTIONS) return false;
    partition = esp_partition_find_first(ESP_PARTITION_TYPE_DATA, 0x40,
                                         "ams_journal");
    if (!partition || partition->address != 0x320000 ||
        partition->size != FH_JOURNAL_SLOTS * FH_JOURNAL_RECORD_BYTES)
        return false;
    mutex = xSemaphoreCreateMutex();
    replay = malloc(sizeof(*replay));
    if (!mutex || !replay) return false;
    fh_journal_identity ids[FH_MAX_CONNECTIONS] = {0};
    for (size_t i = 0; i < config->connection_count; i++) {
        memcpy(ids[i].id, config->connections[i].id, sizeof(ids[i].id));
        memcpy(ids[i].source_id, config->connections[i].source_instance_id,
               sizeof(ids[i].source_id));
    }
    uint64_t marker = ((uint64_t)esp_random() << 32) | esp_random();
    if (!marker) marker = 1;
    fh_journal_io io = {flash_read, flash_write, flash_erase, (void *)partition};
    if (!fh_journal_open(&journal, io, ids, config->connection_count, marker))
        return false;
    if (xTaskCreate(poll_task, "fh_journal", 4096, NULL, 3, NULL) != pdPASS) {
        fh_journal_close(&journal);
        journal.faulted = true;
        return false;
    }
    return true;
}

bool fh_journal_flash_observe(size_t connection, const fh_ams_state *feed,
                              const char *observed_at, uint64_t sample_ms)
{
    if (!mutex || xSemaphoreTake(mutex, portMAX_DELAY) != pdTRUE) return false;
    bool ok = fh_journal_observe(&journal, connection, feed, observed_at, sample_ms);
    xSemaphoreGive(mutex);
    return ok;
}

bool fh_journal_flash_poll(uint64_t now_ms)
{
    if (!mutex || xSemaphoreTake(mutex, portMAX_DELAY) != pdTRUE) return false;
    bool ok = fh_journal_poll(&journal, now_ms);
    xSemaphoreGive(mutex);
    return ok;
}

void fh_journal_flash_read(uint64_t after_sequence, unsigned limit)
{
    if (!mutex || !replay || limit < 1 || limit > 4 ||
        xSemaphoreTake(mutex, portMAX_DELAY) != pdTRUE) {
        puts("{\"event\":\"ams_journal\",\"error\":\"unavailable\"}");
        return;
    }
    if (!journal.initialized || journal.faulted) {
        puts("{\"event\":\"ams_journal\",\"error\":\"storage_fault\"}");
        xSemaphoreGive(mutex); return;
    }
    uint64_t oldest = journal.oldest_sequence;
    uint64_t newest = journal.newest_sequence;
    xSemaphoreGive(mutex);
    if (oldest && after_sequence < oldest - 1)
        printf("{\"event\":\"ams_journal_gap\",\"reason\":\"retention\","
               "\"from_seq\":\"%" PRIu64 "\",\"to_seq\":\"%" PRIu64 "\"}\n",
               after_sequence + 1, oldest - 1);
    unsigned emitted = 0;
    uint64_t cursor = after_sequence;
    while (emitted < limit && cursor < newest) {
        if (xSemaphoreTake(mutex, portMAX_DELAY) != pdTRUE) break;
        bool found = fh_journal_next(&journal, cursor, replay);
        xSemaphoreGive(mutex);
        if (!found) break;
        char *observation = fh_ams_historical_event_json(&replay->feed, replay->id,
                                                          replay->observed_at,
                                                          replay->sample_ms);
        if (!observation) break;
        printf("{\"event\":\"ams_journal\",\"status\":\"historical\","
               "\"sequence\":\"%" PRIu64 "\",\"boot_marker\":\"%016" PRIx64 "\","
               "\"source_instance_id\":\"%s\",\"coalesced_before\":%" PRIu32 ","
               "\"observation\":%s}\n", replay->sequence, replay->boot_marker,
               replay->source_id, replay->coalesced, observation);
        free(observation);
        cursor = replay->sequence;
        emitted++;
    }
    if (xSemaphoreTake(mutex, portMAX_DELAY) != pdTRUE) return;
    bool faulted = journal.faulted;
    unsigned pending = (unsigned)journal.pending[0] + (unsigned)journal.pending[1];
    newest = journal.newest_sequence;
    xSemaphoreGive(mutex);
    if (faulted)
        puts("{\"event\":\"ams_journal\",\"error\":\"storage_fault\"}");
    else
        printf("{\"event\":\"ams_journal_page\",\"oldest_seq\":\"%" PRIu64
               "\",\"newest_seq\":\"%" PRIu64 "\",\"next_after_seq\":\"%" PRIu64
               "\",\"returned\":%u,\"pending_uncommitted\":%u}\n",
               oldest, newest, cursor, emitted,
               pending);
    fflush(stdout);
}
