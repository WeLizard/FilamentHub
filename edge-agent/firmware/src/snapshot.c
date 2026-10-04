#include "snapshot.h"

#include "cJSON.h"
#include <inttypes.h>
#include <stdio.h>

char *fh_snapshot_body(const fh_config *config, int index,
                       const fh_telemetry *facts, uint64_t now_ms,
                       const char *observed_at, uint64_t sequence)
{
    if (!config || index < 0 || index >= config->connection_count ||
        !facts || !observed_at || !*observed_at ||
        !fh_telemetry_fresh(facts, now_ms) || sequence == 0 ||
        sequence > 9007199254740991ULL) return NULL;
    const fh_connection *conn = &config->connections[index];
    cJSON *request = cJSON_CreateObject();
    if (!request) return NULL;
    cJSON_AddNumberToObject(request, "material_system_id", conn->material_system_id);
    cJSON_AddStringToObject(request, "provider", "bambu");
    cJSON_AddStringToObject(request, "transport", "edge_agent");
    cJSON_AddStringToObject(request, "source_instance_id", conn->source_instance_id);
    cJSON_AddStringToObject(request, "observed_at", observed_at);
    char sequence_text[24];
    snprintf(sequence_text, sizeof(sequence_text), "%" PRIu64, sequence);
    cJSON_AddItemToObject(request, "sequence", cJSON_CreateRaw(sequence_text));
    cJSON *capabilities = cJSON_AddArrayToObject(request, "capabilities");
    cJSON_AddItemToArray(capabilities, cJSON_CreateString("read"));
    cJSON *printer = cJSON_AddObjectToObject(request, "printer");
    cJSON_AddStringToObject(printer, "state",
                            facts->state.known &&
                            fh_fact_fresh(facts->state.at_ms, now_ms) ?
                            facts->state.value : "unknown");
    if (facts->job_name.known && fh_fact_fresh(facts->job_name.at_ms, now_ms))
        cJSON_AddStringToObject(printer, "job_name", facts->job_name.value);
    if (facts->progress.known && fh_fact_fresh(facts->progress.at_ms, now_ms) &&
        fh_valid_progress(facts->progress.value))
        cJSON_AddNumberToObject(printer, "progress_percent", facts->progress.value);
    if (facts->nozzle.known && fh_fact_fresh(facts->nozzle.at_ms, now_ms))
        cJSON_AddNumberToObject(printer, "nozzle_temperature", facts->nozzle.value);
    if (facts->bed.known && fh_fact_fresh(facts->bed.at_ms, now_ms))
        cJSON_AddNumberToObject(printer, "bed_temperature", facts->bed.value);
    cJSON_AddArrayToObject(request, "slots");
    cJSON_AddBoolToObject(request, "slot_topology_complete", false);
    char *body = cJSON_PrintUnformatted(request);
    cJSON_Delete(request);
    return body;
}
