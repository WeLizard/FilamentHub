#include "core.h"
#include "config.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

static uint64_t persisted_high;
static bool storage_ok = true;

static bool reserve(uint64_t high, void *context)
{
    (void)context;
    if (!storage_ok) return false;
    persisted_high = high;
    return true;
}

int main(void)
{
    assert(fh_private_ipv4("192.168.1.44"));
    assert(fh_private_ipv4("10.0.0.1"));
    assert(!fh_private_ipv4("8.8.8.8"));
    assert(!fh_private_ipv4("192.168.1.999"));
    assert(!fh_private_ipv4("+10.0.0.1"));
    assert(!fh_private_ipv4("010.0.0.1"));
    assert(fh_valid_origin("https://filamenthub.ru", false));
    assert(!fh_valid_origin("http://192.168.1.2:3000", false));
    assert(fh_valid_origin("http://192.168.1.2:3000", true));
    assert(!fh_valid_origin("http://8.8.8.8", true));
    assert(!fh_valid_origin("https://filamenthub.ru/path", false));
    assert(!fh_valid_origin("https://user@filamenthub.ru", false));
    assert(fh_valid_serial("P2S-1234"));
    assert(!fh_valid_serial("bad/topic"));

    const char *valid_json = "{\"p\":{\"text\":\"quoted \\\"[\\\"\"}}";
    assert(fh_json_shape_ok(valid_json, strlen(valid_json), 4));
    const char *nested = "{\"a\":[[[[0]]]]}";
    assert(!fh_json_shape_ok(nested, strlen(nested), 4));
    const char *nul_escape = "{\"secret\":\"a\\u0000b\"}";
    assert(!fh_json_shape_ok(nul_escape, strlen(nul_escape), 4));
    const char raw_nul[] = {'{', '}', '\0', '{', '}'};
    assert(!fh_json_shape_ok(raw_nul, sizeof(raw_nul), 4));

    static fh_frame frame;
    static char report[5000];
    memset(report, 'x', sizeof(report));
    assert(!fh_frame_feed(&frame, report, 2048, 0, sizeof(report)));
    assert(!fh_frame_feed(&frame, report + 2048, 2048, 2048, sizeof(report)));
    assert(fh_frame_feed(&frame, report + 4096, 904, 4096, sizeof(report)));
    assert(frame.length == sizeof(report));
    assert(memcmp(frame.data, report, sizeof(report)) == 0);
    fh_frame_reset(&frame);
    assert(!fh_frame_feed(&frame, report, 10, 0, FH_REPORT_MAX + 1));
    assert(!frame.active);
    assert(!fh_frame_feed(&frame, report, 10, 10, 20));
    assert(!fh_frame_feed(&frame, report, 10, 0, 20));
    assert(!fh_frame_feed(&frame, report + 11, 10, 11, 20));
    assert(!frame.active);

    fh_telemetry facts;
    fh_telemetry_reset(&facts);
    fh_text_update(&facts.state, "printing", 1000);
    assert(fh_telemetry_fresh(&facts, 31000));
    assert(!fh_telemetry_fresh(&facts, 31001));
    fh_telemetry_reset(&facts);
    assert(!fh_telemetry_fresh(&facts, 1001));
    assert(strcmp(fh_bambu_state("PREPARE"), "preparing") == 0);
    assert(strcmp(fh_bambu_state("RUNNING"), "printing") == 0);
    assert(fh_valid_progress(73));
    assert(!fh_valid_progress(73.5));

    uint64_t next = 1, high = 0;
    assert(fh_next_sequence(&next, &high, reserve, NULL) == 1);
    assert(high == 1024 && persisted_high == 1024);
    next = persisted_high + 1;
    high = persisted_high;
    storage_ok = false;
    assert(fh_next_sequence(&next, &high, reserve, NULL) == 0);
    assert(next == 1025 && persisted_high == 1024);
    storage_ok = true;
    assert(fh_next_sequence(&next, &high, reserve, NULL) == 1025);
    assert(persisted_high == 2048);
    next = 9007199254740992ULL;
    assert(fh_next_sequence(&next, &high, reserve, NULL) == 0);

    printf("Core host tests passed; config=%lu bytes\n", (unsigned long)sizeof(fh_config));
    return 0;
}
