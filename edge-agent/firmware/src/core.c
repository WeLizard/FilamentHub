#include "core.h"

#include <ctype.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

bool fh_private_ipv4(const char *value)
{
    if (!value || !*value) return false;
    unsigned octets[4] = {0};
    const char *cursor = value;
    for (int part = 0; part < 4; part++) {
        if (*cursor < '0' || *cursor > '9') return false;
        if (*cursor == '0' && cursor[1] >= '0' && cursor[1] <= '9') return false;
        do {
            octets[part] = octets[part] * 10 + (unsigned)(*cursor - '0');
            if (octets[part] > 255) return false;
            cursor++;
        } while (*cursor >= '0' && *cursor <= '9');
        if (part < 3) {
            if (*cursor++ != '.') return false;
        } else if (*cursor != '\0') return false;
    }
    return octets[0] == 10 || octets[0] == 127 ||
           (octets[0] == 172 && octets[1] >= 16 && octets[1] <= 31) ||
           (octets[0] == 192 && octets[1] == 168) ||
           (octets[0] == 169 && octets[1] == 254);
}

bool fh_valid_id(const char *value, size_t max_length)
{
    if (!value) return false;
    size_t len = strlen(value);
    if (len == 0 || len > max_length) return false;
    for (size_t i = 0; i < len; i++) {
        unsigned char ch = (unsigned char)value[i];
        if (!(isalnum(ch) || ch == '-' || ch == '_' || ch == '.')) return false;
    }
    return true;
}

bool fh_valid_serial(const char *value)
{
    return fh_valid_id(value, 80) && strlen(value) >= 4;
}

bool fh_valid_origin(const char *value, bool allow_local_http)
{
    if (!value) return false;
    const char *host;
    bool http = false;
    if (strncmp(value, "https://", 8) == 0) host = value + 8;
    else if (allow_local_http && strncmp(value, "http://", 7) == 0) {
        host = value + 7;
        http = true;
    } else return false;
    if (!*host || strlen(host) > 253 || strchr(host, '/') || strchr(host, '@') ||
        strchr(host, '?') || strchr(host, '#')) return false;
    char name[254];
    size_t len = strcspn(host, ":");
    if (!len || len >= sizeof(name)) return false;
    memcpy(name, host, len);
    name[len] = '\0';
    if (host[len]) {
        const char *port = host + len + 1;
        if (!*port || strlen(port) > 5) return false;
        unsigned number = 0;
        for (; *port; port++) {
            if (!isdigit((unsigned char)*port)) return false;
            number = number * 10 + (unsigned)(*port - '0');
        }
        if (!number || number > 65535) return false;
    }
    if (http) return fh_private_ipv4(name) || strcmp(name, "localhost") == 0;
    for (size_t i = 0; i < len; i++) {
        unsigned char ch = (unsigned char)name[i];
        if (!(isalnum(ch) || ch == '-' || ch == '.')) return false;
    }
    return true;
}

bool fh_json_shape_ok(const char *data, size_t length, unsigned max_depth)
{
    if (!data || max_depth == 0 || max_depth > 32) return false;
    char stack[32];
    unsigned depth = 0;
    bool string = false;
    bool escaped = false;
    for (size_t i = 0; i < length; i++) {
        unsigned char ch = (unsigned char)data[i];
        if (ch == 0) return false;
        if (string) {
            if (escaped) {
                if (ch == 'u' && i + 4 < length &&
                    data[i + 1] == '0' && data[i + 2] == '0' &&
                    data[i + 3] == '0' && data[i + 4] == '0') return false;
                escaped = false;
            } else if (ch == '\\') escaped = true;
            else if (ch == '"') string = false;
            else if (ch < 32) return false;
            continue;
        }
        if (ch == '"') string = true;
        else if (ch == '{' || ch == '[') {
            if (depth >= max_depth) return false;
            stack[depth++] = (char)ch;
        } else if (ch == '}' || ch == ']') {
            if (!depth || stack[--depth] != (ch == '}' ? '{' : '[')) return false;
        }
    }
    return !string && !escaped && depth == 0;
}

const char *fh_bambu_state(const char *value)
{
    if (!value) return NULL;
    if (strcmp(value, "IDLE") == 0) return "idle";
    if (strcmp(value, "PREPARE") == 0 || strcmp(value, "SLICING") == 0)
        return "preparing";
    if (strcmp(value, "RUNNING") == 0) return "printing";
    if (strcmp(value, "PAUSE") == 0 || strcmp(value, "PAUSED") == 0)
        return "paused";
    if (strcmp(value, "FINISH") == 0) return "finished";
    if (strcmp(value, "FAILED") == 0) return "failed";
    return "unknown";
}

bool fh_valid_progress(double value)
{
    return isfinite(value) && value >= 0 && value <= 100 && floor(value) == value;
}

void fh_frame_reset(fh_frame *frame)
{
    frame->active = false;
    frame->length = 0;
    frame->expected = 0;
    frame->data[0] = '\0';
}

bool fh_frame_feed(fh_frame *frame, const char *part, size_t length,
                   size_t offset, size_t total)
{
    if (!part || !total || total > FH_REPORT_MAX || offset > total ||
        length > total - offset) {
        fh_frame_reset(frame);
        return false;
    }
    if (offset == 0) {
        fh_frame_reset(frame);
        frame->active = true;
        frame->expected = total;
    }
    if (!frame->active || frame->expected != total || frame->length != offset) {
        fh_frame_reset(frame);
        return false;
    }
    memcpy(frame->data + offset, part, length);
    frame->length += length;
    frame->data[frame->length] = '\0';
    if (frame->length == frame->expected) {
        frame->active = false;
        return true;
    }
    return false;
}

void fh_telemetry_reset(fh_telemetry *facts)
{
    memset(facts, 0, sizeof(*facts));
}

void fh_text_update(fh_text_fact *fact, const char *value, uint64_t at_ms)
{
    fact->known = value != NULL;
    fact->at_ms = at_ms;
    if (value) {
        size_t length = strlen(value);
        if (length >= sizeof(fact->value)) length = sizeof(fact->value) - 1;
        memcpy(fact->value, value, length);
        fact->value[length] = '\0';
    } else fact->value[0] = '\0';
}

void fh_number_update(fh_number_fact *fact, double value, uint64_t at_ms)
{
    fact->known = isfinite(value);
    fact->value = value;
    fact->at_ms = at_ms;
}

bool fh_fact_fresh(uint64_t at_ms, uint64_t now_ms)
{
    return at_ms && now_ms >= at_ms && now_ms - at_ms <= FH_FACT_TTL_MS;
}

bool fh_telemetry_fresh(const fh_telemetry *facts, uint64_t now_ms)
{
    return (facts->state.known && fh_fact_fresh(facts->state.at_ms, now_ms)) ||
           (facts->job_name.known && fh_fact_fresh(facts->job_name.at_ms, now_ms)) ||
           (facts->progress.known && fh_fact_fresh(facts->progress.at_ms, now_ms)) ||
           (facts->nozzle.known && fh_fact_fresh(facts->nozzle.at_ms, now_ms)) ||
           (facts->bed.known && fh_fact_fresh(facts->bed.at_ms, now_ms));
}

uint64_t fh_next_sequence(uint64_t *next, uint64_t *reserved_high,
                          bool (*reserve)(uint64_t high, void *context), void *context)
{
    const uint64_t exact_json_limit = 9007199254740991ULL;
    if (*next == 0 || *next > exact_json_limit) return 0;
    if (*next > *reserved_high) {
        if (*next > exact_json_limit - 1023) return 0;
        uint64_t high = *next + 1023;
        if (!reserve(high, context)) return 0;
        *reserved_high = high;
    }
    return (*next)++;
}
