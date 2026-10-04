#include "nfc_console.h"
#include "ams_journal_flash.h"

#include "core.h"
#include "ntag.h"
#include "pn5180_hal.h"

#include "cJSON.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define FH_NFC_LINE_MAX 384

typedef struct {
    fh_nfc_pins pins;
    char origin[254];
    char line[FH_NFC_LINE_MAX + 1];
} nfc_context;

static nfc_context bench;

static void reply_error(const char *error)
{
    printf("{\"ok\":false,\"error\":\"%s\"}\n", error);
    fflush(stdout);
}

static bool exact_keys(const cJSON *object, const char *first,
                       const char *second, const char *third)
{
    for (const cJSON *item = object->child; item; item = item->next) {
        if (!item->string ||
            (strcmp(item->string, first) &&
             (!second || strcmp(item->string, second)) &&
             (!third || strcmp(item->string, third)))) return false;
        for (const cJSON *prior = object->child; prior != item; prior = prior->next)
            if (strcmp(prior->string, item->string) == 0) return false;
    }
    return true;
}

static bool uid_from_hex(const char *hex, uint8_t uid[7])
{
    if (!hex || strlen(hex) != 14) return false;
    for (int i = 0; i < 7; i++) {
        unsigned value = 0;
        for (int digit = 0; digit < 2; digit++) {
            char ch = hex[i * 2 + digit];
            unsigned nibble;
            if (ch >= '0' && ch <= '9') nibble = (unsigned)(ch - '0');
            else if (ch >= 'a' && ch <= 'f') nibble = (unsigned)(ch - 'a' + 10);
            else if (ch >= 'A' && ch <= 'F') nibble = (unsigned)(ch - 'A' + 10);
            else return false;
            value = (value << 4) | nibble;
        }
        uid[i] = (uint8_t)value;
    }
    return true;
}

static bool decimal_sequence(const char *text, uint64_t *value)
{
    if (!text || !*text || strlen(text) > 20) return false;
    uint64_t next = 0;
    for (const char *cursor = text; *cursor; cursor++) {
        if (*cursor < '0' || *cursor > '9' ||
            next > (UINT64_MAX - (uint64_t)(*cursor - '0')) / 10)
            return false;
        next = next * 10 + (uint64_t)(*cursor - '0');
    }
    *value = next;
    return true;
}

static const char *type_name(fh_tag_type type)
{
    switch (type) {
    case FH_TAG_ISO14443A: return "iso14443a";
    case FH_TAG_ISO15693: return "iso15693";
    case FH_TAG_NTAG213: return "ntag213";
    case FH_TAG_NTAG215: return "ntag215";
    case FH_TAG_NTAG216: return "ntag216";
    default: return "unknown";
    }
}

static void reply_read(const fh_tag_info *info)
{
    cJSON *response = cJSON_CreateObject();
    if (!response) { reply_error("memory"); return; }
    cJSON_AddBoolToObject(response, "ok", true);
    cJSON_AddStringToObject(response, "type", type_name(info->type));
    char uid[21] = {0};
    for (size_t i = 0; i < info->uid_len && i < 10; i++)
        snprintf(uid + i * 2, 3, "%02X", info->uid[i]);
    cJSON_AddStringToObject(response, "uid", uid);
    cJSON_AddBoolToObject(response, "ndef_known", info->ndef_known);
    if (info->uri_known) cJSON_AddStringToObject(response, "uri", info->uri);
    char *serialized = cJSON_PrintUnformatted(response);
    cJSON_Delete(response);
    if (!serialized) { reply_error("memory"); return; }
    puts(serialized);
    fflush(stdout);
    free(serialized);
}

static void run_command(size_t length)
{
    if (!fh_json_shape_ok(bench.line, length, 4)) {
        reply_error("invalid_command"); return;
    }
    cJSON *request = cJSON_ParseWithLengthOpts(bench.line, length + 1,
                                                NULL, true);
    const cJSON *command = cJSON_GetObjectItemCaseSensitive(request, "command");
    if (cJSON_IsString(command) && command->valuestring &&
        strcmp(command->valuestring, "journal_read") == 0) {
        const cJSON *after = cJSON_GetObjectItemCaseSensitive(request, "after_seq");
        const cJSON *limit = cJSON_GetObjectItemCaseSensitive(request, "limit");
        uint64_t sequence;
        if (!cJSON_IsObject(request) ||
            !exact_keys(request, "command", "after_seq", "limit") ||
            !cJSON_IsString(after) || !decimal_sequence(after->valuestring, &sequence) ||
            !cJSON_IsNumber(limit) || limit->valuedouble < 1 ||
            limit->valuedouble > 4 || limit->valueint != limit->valuedouble) {
            cJSON_Delete(request); reply_error("invalid_command"); return;
        }
        unsigned page_limit = (unsigned)limit->valueint;
        cJSON_Delete(request);
        fh_journal_flash_read(sequence, page_limit);
        return;
    }
    if (!bench.pins.enabled) {
        cJSON_Delete(request); reply_error("reader_disabled"); return;
    }
    bool read = cJSON_IsString(command) && command->valuestring &&
                strcmp(command->valuestring, "read") == 0;
    bool write = cJSON_IsString(command) && command->valuestring &&
                 strcmp(command->valuestring, "write_uri") == 0;
    if (!cJSON_IsObject(request) ||
        !(read || write) ||
        !exact_keys(request, "command", write ? "expected_uid" : NULL,
                    write ? "uri" : NULL)) {
        cJSON_Delete(request);
        reply_error("invalid_command");
        return;
    }
    uint8_t expected_uid[7];
    const cJSON *uri = NULL;
    if (write) {
        const cJSON *expected = cJSON_GetObjectItemCaseSensitive(request,
                                                                   "expected_uid");
        uri = cJSON_GetObjectItemCaseSensitive(request, "uri");
        if (!cJSON_IsString(expected) ||
            !uid_from_hex(expected->valuestring, expected_uid) ||
            !cJSON_IsString(uri) || !uri->valuestring ||
            !fh_nfc_uri_allowed(bench.origin, uri->valuestring)) {
            cJSON_Delete(request);
            reply_error("invalid_write_request");
            return;
        }
    }
    fh_pn5180 reader;
    if (!fh_pn5180_open(&reader, &bench.pins)) {
        cJSON_Delete(request);
        reply_error("reader_unavailable");
        return;
    }
    fh_tag_io io = fh_pn5180_tag_io(&reader);
    if (read) {
        fh_tag_info info;
        if (!fh_tag_read(&io, &info)) reply_error("no_tag_or_io_error");
        else if (info.collision) reply_error("multiple_tags_or_collision");
        else reply_read(&info);
    } else {
        bool success = fh_tag_write_uri(&io, bench.origin, expected_uid, 7,
                                         uri->valuestring);
        if (success) puts("{\"ok\":true,\"written\":true}");
        else reply_error("write_rejected_or_interrupted");
    }
    fh_pn5180_close(&reader);
    cJSON_Delete(request);
    fflush(stdout);
}

static void console_task(void *argument)
{
    (void)argument;
    while (true) {
        size_t used = 0;
        bool overflow = false;
        for (;;) {
            int ch = getchar();
            if (ch == EOF) {
                clearerr(stdin);
                vTaskDelay(pdMS_TO_TICKS(50));
                continue;
            }
            if (ch == '\n') break;
            if (ch == '\r') continue;
            if (used >= FH_NFC_LINE_MAX) overflow = true;
            else bench.line[used++] = (char)ch;
        }
        bench.line[used] = '\0';
        if (overflow) reply_error("command_too_long");
        else run_command(used);
        memset(bench.line, 0, sizeof(bench.line));
    }
}

bool fh_nfc_console_start(const fh_nfc_pins *pins, const char *origin)
{
    if (!pins || !origin || strlen(origin) >= sizeof(bench.origin)) return false;
    memset(&bench, 0, sizeof(bench));
    bench.pins = *pins;
    strcpy(bench.origin, origin);
    return xTaskCreate(console_task, "fh_nfc_console", 12288, NULL, 5,
                       NULL) == pdPASS;
}
