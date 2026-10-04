#include "ams.h"
#include "cJSON.h"

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static fh_ams_result apply(fh_ams_state *state, const char *json, uint64_t at_ms)
{
    return fh_ams_apply(state, json, strlen(json), at_ms);
}

static cJSON *event(const fh_ams_state *state, const char *id, uint64_t now_ms)
{
    char *text = fh_ams_event_json(state, id, "2026-10-03T10:00:00Z", now_ms);
    assert(text && strlen(text) <= 16384);
    cJSON *parsed = cJSON_Parse(text);
    free(text);
    assert(parsed);
    return parsed;
}

static const cJSON *slot(const cJSON *message, int index)
{
    const cJSON *slots = cJSON_GetObjectItem(message, "slots");
    for (const cJSON *entry = slots->child; entry; entry = entry->next) {
        const cJSON *number = cJSON_GetObjectItem(entry, "provider_index");
        if (number && number->valueint == index) return entry;
    }
    return NULL;
}

int main(void)
{
    const char *full = "{\"print\":{\"command\":\"push_status\",\"msg\":0,"
        "\"ams\":{\"tray_exist_bits\":\"1\",\"tray_now\":\"0\",\"ams\":["
        "{\"id\":\"0\",\"info\":\"0\",\"tray\":[{\"id\":\"0\","
        "\"tray_type\":\" PLA \",\"tray_color\":\"#A1b2C3ff\","
        "\"remain\":\"55\",\"remain_g\":\"812\","
        "\"tray_uuid\":\"D1E2F3\"},{\"id\":\"1\","
        "\"tray_type\":\"\",\"tray_color\":\"00000000\","
        "\"remain\":-1}]}]},\"vt_tray\":{\"id\":\"255\","
        "\"tray_type\":\"ABS\",\"tray_color\":\"112233ff\"}}}";
    fh_ams_state first, second;
    fh_ams_reset(&first);
    fh_ams_reset(&second);
    assert(apply(&first, full, 1000) == FH_AMS_OBSERVED);
    assert(first.slot_count == 3 && first.topology_complete);
    cJSON *result = event(&first, "p2s-a", 1000);
    assert(strcmp(cJSON_GetObjectItem(result, "status")->valuestring,
                  "observed") == 0);
    assert(cJSON_IsTrue(cJSON_GetObjectItem(result, "slot_topology_complete")));
    const cJSON *one = slot(result, 0);
    const cJSON *empty = slot(result, 1);
    const cJSON *external = slot(result, 255);
    assert(one && empty && external);
    assert(cJSON_IsTrue(cJSON_GetObjectItem(one, "present")));
    assert(cJSON_IsTrue(cJSON_GetObjectItem(one, "active_feed")));
    assert(cJSON_GetObjectItem(one, "remaining_grams")->valueint == 812);
    assert(strcmp(cJSON_GetObjectItem(one, "material")->valuestring,
                  "PLA") == 0);
    assert(strcmp(cJSON_GetObjectItem(one, "color_hex")->valuestring,
                  "A1B2C3") == 0);
    assert(cJSON_IsFalse(cJSON_GetObjectItem(empty, "present")));
    assert(!cJSON_GetObjectItem(empty, "remaining_percent"));
    assert(strcmp(cJSON_GetObjectItem(external, "kind")->valuestring,
                  "external") == 0);
    char *serialized = cJSON_PrintUnformatted(result);
    assert(!strstr(serialized, "tray_uuid") && !strstr(serialized, "D1E2F3") &&
           !strstr(serialized, "spool_id") && !strstr(serialized, "access_code"));
    free(serialized);
    cJSON_Delete(result);

    assert(apply(&first, "{\"print\":{\"ams\":{\"tray_now\":\"1023\"}}}",
                 1100) == FH_AMS_OBSERVED);
    assert(first.active_known && first.active_index == 1023);
    result = event(&first, "p2s-a", 1100);
    assert(!cJSON_GetObjectItem(slot(result, 0), "active_feed"));
    cJSON_Delete(result);
    assert(apply(&first, "{\"print\":{\"ams\":{\"tray_now\":0}}}",
                 1200) == FH_AMS_OBSERVED);
    result = event(&first, "p2s-a", 1200);
    assert(cJSON_IsTrue(cJSON_GetObjectItem(slot(result, 0), "active_feed")));
    cJSON_Delete(result);
    assert(apply(&first, "{\"print\":{\"ams\":{\"tray_now\":\"65536\"}}}",
                 1300) == FH_AMS_OBSERVED);
    assert(!first.active_known);
    result = event(&first, "p2s-a", 1300);
    assert(!cJSON_GetObjectItem(slot(result, 0), "active_feed"));
    cJSON_Delete(result);
    assert(apply(&first, "{\"print\":{\"ams\":{\"tray_now\":1024}}}",
                 1400) == FH_AMS_OBSERVED);
    assert(!first.active_known);
    assert(apply(&first, "{\"print\":{\"ams\":{\"ams\":[{\"id\":0,"
                         "\"tray\":[{\"id\":0,\"remain_g\":800}]}]}}}",
                 1500) == FH_AMS_OBSERVED);
    result = event(&first, "p2s-a", 1500);
    assert(!cJSON_GetObjectItem(slot(result, 0), "active_feed"));
    cJSON_Delete(result);

    const char *partial = "{\"print\":{\"ams\":{\"ams\":[{\"id\":0,"
                          "\"tray\":[{\"id\":0,\"remain_g\":800}]}]}}}";
    assert(apply(&first, partial, 2000) == FH_AMS_OBSERVED);
    assert(first.slot_count == 3);
    result = event(&first, "p2s-a", 31500);
    one = slot(result, 0);
    assert(one && cJSON_GetObjectItem(one, "remaining_grams")->valueint == 800);
    assert(cJSON_GetObjectItem(cJSON_GetObjectItem(one, "field_age_ms"),
                               "remaining_grams")->valueint == 29500);
    assert(!cJSON_GetObjectItem(one, "material"));
    assert(!cJSON_GetObjectItem(one, "present"));
    assert(cJSON_IsFalse(cJSON_GetObjectItem(result, "slot_topology_complete")));
    assert(!slot(result, 1) && !slot(result, 255));
    cJSON_Delete(result);
    result = event(&first, "p2s-a", 33001);
    assert(strcmp(cJSON_GetObjectItem(result, "status")->valuestring,
                  "stale") == 0);
    assert(cJSON_GetArraySize(cJSON_GetObjectItem(result, "slots")) == 0);
    assert(!cJSON_GetObjectItem(result, "observed_at"));
    cJSON_Delete(result);
    char *without_utc = fh_ams_event_json(&first, "p2s-a", "", 2000);
    assert(without_utc && strstr(without_utc, "\"time_basis\":\"monotonic\"") &&
           !strstr(without_utc, "observed_at"));
    free(without_utc);

    assert(apply(&second, "{\"print\":{\"ams\":{\"ams\":[{\"id\":1,"
                           "\"tray\":[{\"id\":2,\"tray_type\":\"PETG\"}]}]}}}",
                 3000) == FH_AMS_OBSERVED);
    assert(second.slot_count == 1 && second.slots[0].provider_index == 6);
    assert(first.slot_count == 3);
    result = event(&second, "p2s-b", 3000);
    assert(!cJSON_GetObjectItem(result, "slot_topology_complete") ||
           cJSON_IsFalse(cJSON_GetObjectItem(result, "slot_topology_complete")));
    assert(slot(result, 6) && !slot(result, 0));
    cJSON_Delete(result);

    assert(apply(&first, "{\"print\":{\"ams\":{\"ams\":[]}}}",
                 4000) == FH_AMS_OBSERVED);
    assert(first.slot_count == 1 && first.slots[0].provider_index == 255);
    assert(!first.topology_complete);
    assert(apply(&first, "{\"print\":{\"vt_tray\":null}}", 5000) ==
           FH_AMS_OBSERVED);
    assert(first.slot_count == 0);
    assert(apply(&first, "{\"print\":{\"command\":\"push_status\","
                         "\"msg\":0,\"ams\":{\"ams\":[]}}}", 6000) ==
           FH_AMS_OBSERVED);
    assert(first.slot_count == 0 && first.topology_complete);
    result = event(&first, "p2s-a", 6000);
    assert(strcmp(cJSON_GetObjectItem(result, "status")->valuestring,
                  "observed") == 0);
    assert(cJSON_IsTrue(cJSON_GetObjectItem(result, "slot_topology_complete")));
    cJSON_Delete(result);
    assert(apply(&first, full, 7000) == FH_AMS_OBSERVED);
    assert(apply(&first, "{\"print\":{\"command\":\"push_status\","
                         "\"msg\":0,\"gcode_state\":\"IDLE\"}}", 8000) ==
           FH_AMS_OBSERVED);
    assert(first.slot_count == 0 && !first.topology_complete);
    result = event(&first, "p2s-a", 8000);
    assert(strcmp(cJSON_GetObjectItem(result, "status")->valuestring,
                  "unknown") == 0);
    cJSON_Delete(result);

    fh_ams_reset(&first); /* A disconnected session cannot merge old facts. */
    assert(apply(&first, partial, 9000) == FH_AMS_OBSERVED);
    assert(first.slot_count == 1 && !first.topology_complete);
    result = event(&first, "p2s-a", 9000);
    one = slot(result, 0);
    assert(one && !cJSON_GetObjectItem(one, "material") &&
           !cJSON_GetObjectItem(one, "present") &&
           cJSON_GetObjectItem(one, "remaining_grams")->valueint == 800);
    cJSON_Delete(result);
    assert(apply(&first, "{\"print\":{\"ams\":{\"tray_exist_bits\":\"1\"}}}",
                 9500) == FH_AMS_OBSERVED);
    result = event(&first, "p2s-a", 9500);
    assert(cJSON_IsTrue(cJSON_GetObjectItem(slot(result, 0), "present")));
    cJSON_Delete(result);
    assert(apply(&first, "{\"print\":{\"ams\":{\"tray_exist_bits\":null}}}",
                 9600) == FH_AMS_OBSERVED);
    result = event(&first, "p2s-a", 9600);
    assert(!cJSON_GetObjectItem(slot(result, 0), "present"));
    cJSON_Delete(result);

    fh_ams_state special;
    fh_ams_reset(&special);
    const char *ht = "{\"print\":{\"ams\":{\"tray_exist_bits\":\"10000\","
        "\"tray_now\":\"128\",\"ams\":[{\"id\":\"128\",\"info\":\"4\","
        "\"tray\":[{\"id\":0,\"tray_type\":\"PA6-CF\"}]}]}}}";
    assert(apply(&special, ht, 10000) == FH_AMS_OBSERVED);
    result = event(&special, "p2s-ht", 10000);
    assert(slot(result, 128) &&
           cJSON_IsTrue(cJSON_GetObjectItem(slot(result, 128), "present")));
    cJSON_Delete(result);
    fh_ams_reset(&special);
    const char *mixed = "{\"print\":{\"ams\":{\"tray_exist_bits\":\"4000000\","
        "\"ams\":[{\"id\":2,\"info\":\"5\",\"tray\":[{\"id\":2,"
        "\"tray_type\":\"PETG\"}]}]}}}";
    assert(apply(&special, mixed, 10000) == FH_AMS_OBSERVED);
    result = event(&special, "p2s-mixed", 10000);
    assert(slot(result, 26) &&
           cJSON_IsTrue(cJSON_GetObjectItem(slot(result, 26), "present")));
    cJSON_Delete(result);

    fh_ams_state prior = first;
    assert(apply(&first, "{\"print\":{\"ams\":{\"ams\":{}}}}", 10000) ==
           FH_AMS_INVALID);
    assert(memcmp(&first, &prior, sizeof(first)) == 0);
    char too_many[2048] = "{\"print\":{\"ams\":{\"ams\":[";
    for (int unit = 0; unit < 9; unit++) {
        char part[128];
        snprintf(part, sizeof(part), "%s{\"id\":%d,\"tray\":["
                 "{\"id\":0},{\"id\":1},{\"id\":2},{\"id\":3}]}",
                 unit ? "," : "", unit);
        assert(strlen(too_many) + strlen(part) + 5 < sizeof(too_many));
        strcat(too_many, part);
    }
    strcat(too_many, "]}}}");
    assert(apply(&first, too_many, 10000) == FH_AMS_INVALID);
    assert(memcmp(&first, &prior, sizeof(first)) == 0);
    char maximum[8192] = "{\"print\":{\"command\":\"push_status\","
                         "\"msg\":0,\"ams\":{\"ams\":[";
    char material_name[81];
    memset(material_name, 'P', 80);
    material_name[80] = '\0';
    for (int unit = 0; unit < 8; unit++) {
        char part[800];
        int used = snprintf(part, sizeof(part), "%s{\"id\":%d,\"tray\":[",
                            unit ? "," : "", unit);
        for (int tray = 0; tray < 4; tray++)
            used += snprintf(part + used, sizeof(part) - (size_t)used,
                             "%s{\"id\":%d,\"tray_type\":\"%s\","
                             "\"tray_color\":\"112233FF\",\"remain\":100,"
                             "\"remain_g\":100000}", tray ? "," : "",
                             tray, material_name);
        assert((size_t)used + 3 < sizeof(part));
        strcat(part, "]}");
        assert(strlen(maximum) + strlen(part) + 5 < sizeof(maximum));
        strcat(maximum, part);
    }
    strcat(maximum, "]}}}");
    fh_ams_state bounded;
    fh_ams_reset(&bounded);
    assert(apply(&bounded, maximum, 10000) == FH_AMS_OBSERVED);
    assert(bounded.slot_count == FH_AMS_MAX_SLOTS);
    char *bounded_event = fh_ams_event_json(&bounded, "p2s-max",
                                              "2026-10-03T10:00:00Z", 10000);
    assert(bounded_event && strlen(bounded_event) <= 16384);
    free(bounded_event);
    assert(apply(&first, "{\"print\":{\"ams\":{\"ams\":[{\"id\":0,"
                         "\"tray\":[{\"id\":0},{\"id\":0}]}]}}}", 10000) ==
           FH_AMS_INVALID);
    assert(memcmp(&first, &prior, sizeof(first)) == 0);
    assert(apply(&first, "{\"print\":{\"nozzle_temper\":221}}", 10000) ==
           FH_AMS_NO_REPORT);
    assert(memcmp(&first, &prior, sizeof(first)) == 0);
    char oversized[FH_REPORT_MAX + 2];
    memset(oversized, 'x', sizeof(oversized));
    oversized[sizeof(oversized) - 1] = '\0';
    assert(fh_ams_apply(&first, oversized, strlen(oversized), 10000) ==
           FH_AMS_INVALID);
    assert(memcmp(&first, &prior, sizeof(first)) == 0);
    char *closed = fh_ams_lifecycle_json("p2s-a", false);
    char *offline = fh_ams_lifecycle_json("p2s-a", true);
    assert(closed && offline && strstr(closed, "\"status\":\"stale\"") &&
           strstr(closed, "\"reason\":\"session_closed\"") &&
           strstr(offline, "\"status\":\"offline\"") &&
           strstr(offline, "\"reason\":\"transport_error\"") &&
           !strstr(offline, "observed_at"));
    free(closed);
    free(offline);
    puts("AMS host tests passed");
    return 0;
}
