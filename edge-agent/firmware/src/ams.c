#include "ams.h"

#include "cJSON.h"

#include <ctype.h>
#include <errno.h>
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static const cJSON *field(const cJSON *object, const char *name)
{
    return cJSON_GetObjectItemCaseSensitive(object, name);
}

static bool integer(const cJSON *item, int *out)
{
    if (cJSON_IsNumber(item)) {
        double number = item->valuedouble;
        if (!isfinite(number) || number < -1 || number > 100000 || floor(number) != number)
            return false;
        *out = (int)number;
        return true;
    }
    if (!cJSON_IsString(item) || !item->valuestring || !*item->valuestring)
        return false;
    const char *text = item->valuestring;
    if (*text == '-') text++;
    if (!*text) return false;
    for (const char *cursor = text; *cursor; cursor++)
        if (*cursor < '0' || *cursor > '9') return false;
    long number = strtol(item->valuestring, NULL, 10);
    if (number < -1 || number > 100000) return false;
    *out = (int)number;
    return true;
}

static bool hex_bits(const cJSON *item, uint64_t *out)
{
    if (!cJSON_IsString(item) || !item->valuestring || !*item->valuestring)
        return false;
    for (const char *cursor = item->valuestring; *cursor; cursor++)
        if (!( (*cursor >= '0' && *cursor <= '9') ||
               (*cursor >= 'a' && *cursor <= 'f') ||
               (*cursor >= 'A' && *cursor <= 'F'))) return false;
    errno = 0;
    unsigned long long bits = strtoull(item->valuestring, NULL, 16);
    if (errno == ERANGE) return false;
    *out = (uint64_t)bits;
    return true;
}

void fh_ams_reset(fh_ams_state *state)
{
    if (state) memset(state, 0, sizeof(*state));
}

static void remove_slots(fh_ams_state *state, bool external)
{
    for (size_t index = 0; index < state->slot_count; ) {
        if (state->slots[index].external == external) {
            state->slots[index] = state->slots[--state->slot_count];
            memset(&state->slots[state->slot_count], 0, sizeof(state->slots[0]));
        } else index++;
    }
}

static fh_ams_slot *slot_for(fh_ams_state *state, uint8_t unit_id,
                             uint8_t tray_id, uint16_t provider_index,
                             uint8_t presence_bit, bool external)
{
    fh_ams_slot *found = NULL;
    for (size_t index = 0; index < state->slot_count; index++) {
        fh_ams_slot *slot = &state->slots[index];
        if (slot->external == external && slot->unit_id == unit_id &&
            slot->tray_id == tray_id) found = slot;
        else if (slot->provider_index == provider_index) return NULL;
    }
    if (!found) {
        if (state->slot_count >= FH_AMS_MAX_SLOTS) return NULL;
        found = &state->slots[state->slot_count++];
        memset(found, 0, sizeof(*found));
    }
    found->unit_id = unit_id;
    found->tray_id = tray_id;
    found->provider_index = provider_index;
    found->presence_bit = presence_bit;
    found->external = external;
    return found;
}

static bool color(const char *text, char result[7])
{
    if (!text) return false;
    if (*text == '#') text++;
    size_t length = strlen(text);
    if (length != 6 && length != 8) return false;
    for (size_t i = 0; i < length; i++) {
        char ch = text[i];
        if (ch >= 'a' && ch <= 'f') ch -= 'a' - 'A';
        if (!((ch >= '0' && ch <= '9') || (ch >= 'A' && ch <= 'F')))
            return false;
        if (i < 6) result[i] = ch;
    }
    result[6] = '\0';
    return length != 8 || text[6] != '0' || text[7] != '0';
}

static bool material(const cJSON *item, char result[81])
{
    if (!cJSON_IsString(item) || !item->valuestring) return false;
    const char *start = item->valuestring;
    while (*start && isspace((unsigned char)*start)) start++;
    const char *end = start + strlen(start);
    while (end > start && isspace((unsigned char)end[-1])) end--;
    size_t length = (size_t)(end - start);
    if (!length || length > 80) return false;
    memcpy(result, start, length);
    result[length] = '\0';
    return true;
}

static void update_slot(fh_ams_slot *slot, const cJSON *tray, uint64_t now_ms,
                        bool external)
{
    slot->slot_at_ms = now_ms;
    const cJSON *type = field(tray, "tray_type");
    if (type) {
        slot->material_known = material(type, slot->material);
        slot->material_at_ms = now_ms;
        if (!slot->material_known) slot->material[0] = '\0';
        if (external || cJSON_IsString(type)) {
            slot->present_known = true;
            slot->present = slot->material_known;
            slot->present_at_ms = now_ms;
        } else if (cJSON_IsNull(type)) {
            slot->present_known = false;
            slot->present_at_ms = now_ms;
        }
    }
    const cJSON *tray_color = field(tray, "tray_color");
    if (tray_color) {
        slot->color_known = cJSON_IsString(tray_color) &&
                            color(tray_color->valuestring, slot->color_hex);
        slot->color_at_ms = now_ms;
        if (!slot->color_known) slot->color_hex[0] = '\0';
    }
    const cJSON *remain = field(tray, "remain");
    if (remain) {
        int value;
        slot->remaining_percent_known = integer(remain, &value) && value <= 100 && value >= 0;
        if (slot->remaining_percent_known) slot->remaining_percent = value;
        slot->remaining_percent_at_ms = now_ms;
    }
    const cJSON *remain_g = field(tray, "remain_g");
    if (remain_g) {
        int value;
        slot->remaining_grams_known = integer(remain_g, &value) && value >= 0;
        if (slot->remaining_grams_known) slot->remaining_grams = value;
        slot->remaining_grams_at_ms = now_ms;
    }
}

static bool mark_seen(uint16_t provider_index, uint16_t seen[FH_AMS_MAX_SLOTS],
                      size_t *count)
{
    for (size_t i = 0; i < *count; i++)
        if (seen[i] == provider_index) return false;
    if (*count >= FH_AMS_MAX_SLOTS) return false;
    seen[(*count)++] = provider_index;
    return true;
}

static bool apply_units(fh_ams_state *state, const cJSON *units,
                        uint64_t now_ms, uint16_t seen[FH_AMS_MAX_SLOTS],
                        size_t *seen_count, bool *complete)
{
    if (cJSON_IsNull(units)) {
        remove_slots(state, false);
        *complete = false;
        return true;
    }
    if (!cJSON_IsArray(units)) return false;
    if (cJSON_GetArraySize(units) == 0) remove_slots(state, false);
    for (const cJSON *unit = units->child; unit; unit = unit->next) {
        if (!cJSON_IsObject(unit)) return false;
        int unit_id;
        if (!integer(field(unit, "id"), &unit_id) || unit_id < 0 || unit_id > 253)
            return false;
        uint64_t info = 0;
        const cJSON *info_item = field(unit, "info");
        if (info_item && (cJSON_IsNull(info_item) ||
                          (cJSON_IsString(info_item) && info_item->valuestring &&
                           !*info_item->valuestring))) info_item = NULL;
        if (info_item && !hex_bits(info_item, &info)) return false;
        const cJSON *trays = field(unit, "tray");
        if (!trays) { *complete = false; continue; }
        if (!cJSON_IsArray(trays)) return false;
        for (const cJSON *tray = trays->child; tray; tray = tray->next) {
            if (!cJSON_IsObject(tray)) return false;
            int tray_id;
            if (!integer(field(tray, "id"), &tray_id) || tray_id < 0 ||
                tray_id > 3 || (unit_id >= 128 && tray_id != 0)) return false;
            uint16_t provider_index;
            int presence_bit;
            if (unit_id >= 128 || (info_item && (info & 15u) == 4u)) {
                provider_index = (uint16_t)unit_id;
                presence_bit = 16 + (unit_id >= 128 ? unit_id - 128 : 0) + tray_id;
            } else if (info_item && (info & 15u) == 5u) {
                provider_index = (uint16_t)(24 + tray_id);
                presence_bit = 24 + tray_id;
            } else {
                provider_index = (uint16_t)(unit_id * 4 + tray_id);
                presence_bit = provider_index;
                if (!info_item) for (size_t i = 0; i < state->slot_count; i++) {
                    const fh_ams_slot *old = &state->slots[i];
                    if (!old->external && old->unit_id == unit_id &&
                        old->tray_id == tray_id) {
                        provider_index = old->provider_index;
                        presence_bit = old->presence_bit;
                        break;
                    }
                }
            }
            if (presence_bit >= 64 || !mark_seen(provider_index, seen, seen_count))
                return false;
            fh_ams_slot *slot = slot_for(state, (uint8_t)unit_id,
                                          (uint8_t)tray_id, provider_index,
                                          (uint8_t)presence_bit, false);
            if (!slot) return false;
            update_slot(slot, tray, now_ms, false);
        }
    }
    return true;
}

static bool apply_external(fh_ams_state *state, const cJSON *tray,
                           uint64_t now_ms, uint16_t seen[FH_AMS_MAX_SLOTS],
                           size_t *seen_count)
{
    if (!cJSON_IsObject(tray)) return false;
    int index = 255;
    const cJSON *id = field(tray, "id");
    if (id && (!integer(id, &index) || (index != 254 && index != 255)))
        return false;
    if (!mark_seen((uint16_t)index, seen, seen_count)) return false;
    fh_ams_slot *slot = slot_for(state, (uint8_t)index, 0,
                                  (uint16_t)index, 0, true);
    if (!slot) return false;
    update_slot(slot, tray, now_ms, true);
    return true;
}

fh_ams_result fh_ams_apply(fh_ams_state *state, const char *payload,
                           size_t length, uint64_t now_ms)
{
    if (!state || !now_ms || length > FH_REPORT_MAX ||
        !fh_json_shape_ok(payload, length, 16))
        return FH_AMS_INVALID;
    const char *parse_end = NULL;
    cJSON *message = cJSON_ParseWithLengthOpts(payload, length, &parse_end, false);
    if (parse_end && parse_end <= payload + length) {
        for (const char *cursor = parse_end; cursor < payload + length; cursor++)
            if (*cursor != ' ' && *cursor != '\t' && *cursor != '\r' &&
                *cursor != '\n') {
                cJSON_Delete(message);
                return FH_AMS_INVALID;
            }
    }
    const cJSON *report = field(message, "print");
    if (!cJSON_IsObject(report)) { cJSON_Delete(message); return FH_AMS_INVALID; }
    const cJSON *command = field(report, "command");
    const cJSON *msg = field(report, "msg");
    bool full = cJSON_IsString(command) && command->valuestring &&
                strcmp(command->valuestring, "push_status") == 0 &&
                ((cJSON_IsNumber(msg) && msg->valuedouble == 0) ||
                 (cJSON_IsString(msg) && msg->valuestring &&
                  strcmp(msg->valuestring, "0") == 0));
    const cJSON *ams = field(report, "ams");
    const cJSON *virtual_slots = field(report, "vir_slot");
    const cJSON *virtual_tray = field(report, "vt_tray");
    if (!full && !ams && !virtual_slots && !virtual_tray) {
        cJSON_Delete(message);
        return FH_AMS_NO_REPORT;
    }
    fh_ams_state *next = malloc(sizeof(*next));
    if (!next) { cJSON_Delete(message); return FH_AMS_INVALID; }
    if (full) fh_ams_reset(next);
    else *next = *state;
    bool valid = true;
    bool complete = full;
    bool topology_evidence = false;
    uint16_t seen[FH_AMS_MAX_SLOTS];
    size_t seen_count = 0;
    if (ams) {
        if (cJSON_IsNull(ams)) {
            remove_slots(next, false);
            next->active_known = false;
            next->topology_complete = false;
            complete = false;
        } else if (!cJSON_IsObject(ams)) valid = false;
        else {
            const cJSON *units = field(ams, "ams");
            if (units) {
                topology_evidence = cJSON_IsArray(units);
                valid = apply_units(next, units, now_ms, seen, &seen_count, &complete);
                if (!full && (cJSON_IsNull(units) ||
                              (cJSON_IsArray(units) && cJSON_GetArraySize(units) == 0)))
                    next->topology_complete = false;
            }
            const cJSON *bits_item = field(ams, "tray_exist_bits");
            if (valid && bits_item) {
                uint64_t bits;
                bool unknown = cJSON_IsNull(bits_item) ||
                               (cJSON_IsString(bits_item) && bits_item->valuestring &&
                                !*bits_item->valuestring);
                if (!unknown && !hex_bits(bits_item, &bits)) valid = false;
                else for (size_t i = 0; i < next->slot_count; i++) {
                    fh_ams_slot *slot = &next->slots[i];
                    if (slot->external) continue;
                    slot->present_known = !unknown;
                    if (!unknown)
                        slot->present = (bits & (UINT64_C(1) << slot->presence_bit)) != 0;
                    slot->present_at_ms = now_ms;
                    slot->slot_at_ms = now_ms;
                }
            }
            const cJSON *active = field(ams, "tray_now");
            if (valid && active) {
                int index;
                next->active_known = integer(active, &index) &&
                                     index >= 0 && index <= 1023;
                if (next->active_known) next->active_index = (uint16_t)index;
                next->active_at_ms = now_ms;
            }
        }
    }
    if (valid && virtual_slots && !cJSON_IsArray(virtual_slots) &&
        !cJSON_IsNull(virtual_slots)) valid = false;
    if (valid && cJSON_IsArray(virtual_slots)) {
        if (cJSON_GetArraySize(virtual_slots) == 0) {
            remove_slots(next, true);
            if (!full) next->topology_complete = false;
        } else topology_evidence = true;
        for (const cJSON *tray = virtual_slots->child; valid && tray; tray = tray->next)
            valid = apply_external(next, tray, now_ms, seen, &seen_count);
    } else if (valid && virtual_tray) {
        if (cJSON_IsNull(virtual_tray)) {
            for (size_t i = 0; i < next->slot_count; ) {
                if (next->slots[i].external && next->slots[i].provider_index == 255) {
                    next->slots[i] = next->slots[--next->slot_count];
                    memset(&next->slots[next->slot_count], 0, sizeof(next->slots[0]));
                } else i++;
            }
            if (!full) next->topology_complete = false;
        } else {
            topology_evidence = true;
            valid = apply_external(next, virtual_tray, now_ms, seen, &seen_count);
        }
    } else if (valid && cJSON_IsNull(virtual_slots)) {
        remove_slots(next, true);
        if (!full) next->topology_complete = false;
    }
    if (valid) {
        if (!full) {
            if (next->slot_count != state->slot_count)
                next->topology_complete = false;
            else for (size_t i = 0; i < next->slot_count; i++) {
                bool found = false;
                for (size_t j = 0; j < state->slot_count; j++)
                    if (next->slots[i].provider_index == state->slots[j].provider_index &&
                        next->slots[i].external == state->slots[j].external) found = true;
                if (!found) next->topology_complete = false;
            }
        }
        if (full) {
            next->topology_complete = complete && topology_evidence;
            next->topology_at_ms = next->topology_complete ? now_ms : 0;
        }
        next->report_at_ms = now_ms;
        *state = *next;
    }
    free(next);
    cJSON_Delete(message);
    return valid ? FH_AMS_OBSERVED : FH_AMS_INVALID;
}

static cJSON *event_base(const char *connection_id, const char *status)
{
    if (!fh_valid_id(connection_id, 32)) return NULL;
    cJSON *root = cJSON_CreateObject();
    if (!root) return NULL;
    if (!cJSON_AddStringToObject(root, "event", "ams") ||
        !cJSON_AddStringToObject(root, "connection_id", connection_id) ||
        !cJSON_AddStringToObject(root, "status", status)) {
        cJSON_Delete(root);
        return NULL;
    }
    return root;
}

static char *finish_event(cJSON *root)
{
    if (!root) return NULL;
    char *line = cJSON_PrintUnformatted(root);
    cJSON_Delete(root);
    if (line && strlen(line) > 16384) { free(line); return NULL; }
    return line;
}

static char *render_event(const fh_ams_state *state, const char *connection_id,
                          const char *observed_at, uint64_t now_ms,
                          bool historical)
{
    if (!state || !observed_at || !now_ms) return NULL;
    bool live = fh_fact_fresh(state->report_at_ms, now_ms);
    bool topology = live && state->topology_complete &&
                    fh_fact_fresh(state->topology_at_ms, now_ms);
    bool slots_fresh = false;
    bool active_present = false;
    for (size_t i = 0; live && i < state->slot_count; i++)
        slots_fresh |= fh_fact_fresh(state->slots[i].slot_at_ms, now_ms);
    for (size_t i = 0; live && i < state->slot_count; i++)
        if (fh_fact_fresh(state->slots[i].slot_at_ms, now_ms) &&
            state->slots[i].provider_index == state->active_index)
            active_present = true;
    const char *status = !live ? "stale" :
                         (topology || slots_fresh ? "observed" : "unknown");
    cJSON *root = event_base(connection_id, historical ? "historical" : status);
    if (!root) return NULL;
    if (historical && !cJSON_AddStringToObject(root, "capture_status", status))
        goto fail;
    if (live && observed_at[0] &&
        !cJSON_AddStringToObject(root, "observed_at", observed_at)) goto fail;
    if (live && !observed_at[0] &&
        !cJSON_AddStringToObject(root, "time_basis", "monotonic")) goto fail;
    if (live && !cJSON_AddNumberToObject(root, "report_age_ms",
                                          now_ms - state->report_at_ms)) goto fail;
    if (!cJSON_AddBoolToObject(root, "slot_topology_complete", topology))
        goto fail;
    if (topology && !cJSON_AddNumberToObject(root, "topology_age_ms",
                                              now_ms - state->topology_at_ms)) goto fail;
    cJSON *slots = cJSON_AddArrayToObject(root, "slots");
    if (!slots) goto fail;
    for (size_t i = 0; live && i < state->slot_count; i++) {
        const fh_ams_slot *slot = &state->slots[i];
        if (!fh_fact_fresh(slot->slot_at_ms, now_ms)) continue;
        cJSON *entry = cJSON_CreateObject();
        if (!entry) goto fail;
        cJSON_AddItemToArray(slots, entry);
        if (!cJSON_AddNumberToObject(entry, "provider_index", slot->provider_index) ||
            !cJSON_AddStringToObject(entry, "kind", slot->external ? "external" : "slot") ||
            !cJSON_AddNumberToObject(entry, "slot_age_ms",
                                     now_ms - slot->slot_at_ms))
            goto fail;
        cJSON *ages = cJSON_AddObjectToObject(entry, "field_age_ms");
        if (!ages) goto fail;
        if (slot->present_known && fh_fact_fresh(slot->present_at_ms, now_ms) &&
            (!cJSON_AddBoolToObject(entry, "present", slot->present) ||
             !cJSON_AddNumberToObject(ages, "present",
                                      now_ms - slot->present_at_ms))) goto fail;
        if (active_present && state->active_known &&
            fh_fact_fresh(state->active_at_ms, now_ms) &&
            (!cJSON_AddBoolToObject(entry, "active_feed",
                                    slot->provider_index == state->active_index) ||
             !cJSON_AddNumberToObject(ages, "active_feed",
                                      now_ms - state->active_at_ms))) goto fail;
        if (slot->material_known && fh_fact_fresh(slot->material_at_ms, now_ms) &&
            (!cJSON_AddStringToObject(entry, "material", slot->material) ||
             !cJSON_AddNumberToObject(ages, "material",
                                      now_ms - slot->material_at_ms))) goto fail;
        if (slot->color_known && fh_fact_fresh(slot->color_at_ms, now_ms) &&
            (!cJSON_AddStringToObject(entry, "color_hex", slot->color_hex) ||
             !cJSON_AddNumberToObject(ages, "color_hex",
                                      now_ms - slot->color_at_ms))) goto fail;
        if (slot->remaining_percent_known &&
            fh_fact_fresh(slot->remaining_percent_at_ms, now_ms) &&
            (!cJSON_AddNumberToObject(entry, "remaining_percent",
                                      slot->remaining_percent) ||
             !cJSON_AddNumberToObject(ages, "remaining_percent",
                                      now_ms - slot->remaining_percent_at_ms))) goto fail;
        if (slot->remaining_grams_known &&
            fh_fact_fresh(slot->remaining_grams_at_ms, now_ms) &&
            (!cJSON_AddNumberToObject(entry, "remaining_grams",
                                      slot->remaining_grams) ||
             !cJSON_AddNumberToObject(ages, "remaining_grams",
                                      now_ms - slot->remaining_grams_at_ms))) goto fail;
    }
    return finish_event(root);
fail:
    cJSON_Delete(root);
    return NULL;
}

char *fh_ams_event_json(const fh_ams_state *state, const char *connection_id,
                        const char *observed_at, uint64_t now_ms)
{
    return render_event(state, connection_id, observed_at, now_ms, false);
}

char *fh_ams_historical_event_json(const fh_ams_state *state,
                                   const char *connection_id,
                                   const char *observed_at, uint64_t sample_ms)
{
    return render_event(state, connection_id, observed_at, sample_ms, true);
}

char *fh_ams_lifecycle_json(const char *connection_id, bool transport_error)
{
    cJSON *root = event_base(connection_id, transport_error ? "offline" : "stale");
    if (!root) return NULL;
    if (!cJSON_AddStringToObject(root, "reason",
                                 transport_error ? "transport_error" : "session_closed") ||
        !cJSON_AddBoolToObject(root, "slot_topology_complete", false) ||
        !cJSON_AddArrayToObject(root, "slots")) {
        cJSON_Delete(root);
        return NULL;
    }
    return finish_event(root);
}
