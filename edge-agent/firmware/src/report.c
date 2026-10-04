#include "report.h"

#include "cJSON.h"

#include <math.h>
#include <stdio.h>
#include <string.h>

static bool update_text(const cJSON *report, const char *key, fh_text_fact *target,
                        uint64_t now_ms, bool state)
{
    const cJSON *item = cJSON_GetObjectItemCaseSensitive(report, key);
    if (!item) return false;
    if (cJSON_IsNull(item)) {
        fh_text_update(target, NULL, now_ms);
        return true;
    }
    if (!cJSON_IsString(item) || !item->valuestring) return false;
    const char *value = state ? fh_bambu_state(item->valuestring) : item->valuestring;
    if (strlen(value) > 300) return false;
    fh_text_update(target, value, now_ms);
    return true;
}

static bool update_number(const cJSON *report, const char *key, fh_number_fact *target,
                          double minimum, double maximum, uint64_t now_ms)
{
    const cJSON *item = cJSON_GetObjectItemCaseSensitive(report, key);
    if (!item) return false;
    if (cJSON_IsNull(item)) {
        fh_number_update(target, NAN, now_ms);
        return true;
    }
    if (!cJSON_IsNumber(item) || !isfinite(item->valuedouble) ||
        item->valuedouble < minimum || item->valuedouble > maximum) return false;
    if (strcmp(key, "mc_percent") == 0 && !fh_valid_progress(item->valuedouble))
        return false;
    fh_number_update(target, item->valuedouble, now_ms);
    return true;
}

bool fh_report_apply(fh_telemetry *facts, char job_key[180],
                     const char *payload, size_t length, uint64_t now_ms)
{
    if (!facts || !job_key || !fh_json_shape_ok(payload, length, 16)) return false;
    cJSON *message = cJSON_ParseWithLength(payload, length);
    const cJSON *report = cJSON_GetObjectItemCaseSensitive(message, "print");
    if (!cJSON_IsObject(report)) { cJSON_Delete(message); return false; }
    const cJSON *command = cJSON_GetObjectItemCaseSensitive(report, "command");
    const cJSON *msg = cJSON_GetObjectItemCaseSensitive(report, "msg");
    bool full = cJSON_IsString(command) && command->valuestring &&
                strcmp(command->valuestring, "push_status") == 0 &&
                ((cJSON_IsNumber(msg) && msg->valuedouble == 0) ||
                 (cJSON_IsString(msg) && msg->valuestring &&
                  strcmp(msg->valuestring, "0") == 0));
    const cJSON *identity = cJSON_GetObjectItemCaseSensitive(report, "task_id");
    if (!identity) identity = cJSON_GetObjectItemCaseSensitive(report, "subtask_id");
    if (!identity) identity = cJSON_GetObjectItemCaseSensitive(report, "gcode_file");
    char incoming_key[180] = {0};
    if (cJSON_IsString(identity) && identity->valuestring &&
        strlen(identity->valuestring) < sizeof(incoming_key) - 3)
        snprintf(incoming_key, sizeof(incoming_key), "id:%s", identity->valuestring);
    else if (cJSON_IsNumber(identity) && isfinite(identity->valuedouble))
        snprintf(incoming_key, sizeof(incoming_key), "id:%.0f", identity->valuedouble);
    const cJSON *name = cJSON_GetObjectItemCaseSensitive(report, "subtask_name");
    if (!incoming_key[0] && cJSON_IsString(name) && name->valuestring &&
        strlen(name->valuestring) < sizeof(incoming_key) - 5)
        snprintf(incoming_key, sizeof(incoming_key), "name:%s", name->valuestring);
    bool changed_name = cJSON_IsString(name) && name->valuestring &&
                        facts->job_name.known &&
                        strcmp(name->valuestring, facts->job_name.value) != 0;
    if (full || changed_name || (incoming_key[0] && job_key[0] &&
                 strcmp(incoming_key, job_key) != 0 &&
                 !(strncmp(incoming_key, "name:", 5) == 0 &&
                   strncmp(job_key, "id:", 3) == 0))) {
        fh_telemetry_reset(facts);
        job_key[0] = '\0';
    }
    if (incoming_key[0] &&
        !(strncmp(incoming_key, "name:", 5) == 0 &&
          strncmp(job_key, "id:", 3) == 0))
        strcpy(job_key, incoming_key);
    bool changed = update_text(report, "gcode_state", &facts->state, now_ms, true);
    if (!name) changed |= update_text(report, "gcode_file", &facts->job_name,
                                      now_ms, false);
    else changed |= update_text(report, "subtask_name", &facts->job_name,
                                now_ms, false);
    changed |= update_number(report, "mc_percent", &facts->progress, 0, 100, now_ms);
    changed |= update_number(report, "nozzle_temper", &facts->nozzle, -100, 600, now_ms);
    changed |= update_number(report, "bed_temper", &facts->bed, -100, 250, now_ms);
    if (changed) facts->observed_ms = now_ms;
    cJSON_Delete(message);
    return changed;
}
