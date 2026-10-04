#ifndef FH_EDGE_CORE_H
#define FH_EDGE_CORE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define FH_MAX_CONNECTIONS 2
#define FH_REPORT_MAX 24576
#define FH_FACT_TTL_MS 30000ULL

typedef struct {
    char value[301];
    uint64_t at_ms;
    bool known;
} fh_text_fact;

typedef struct {
    double value;
    uint64_t at_ms;
    bool known;
} fh_number_fact;

typedef struct {
    fh_text_fact state;
    fh_text_fact job_name;
    fh_number_fact progress;
    fh_number_fact nozzle;
    fh_number_fact bed;
    uint64_t observed_ms;
} fh_telemetry;

typedef struct {
    char data[FH_REPORT_MAX + 1];
    size_t length;
    size_t expected;
    bool active;
} fh_frame;

bool fh_private_ipv4(const char *value);
bool fh_valid_id(const char *value, size_t max_length);
bool fh_valid_serial(const char *value);
bool fh_valid_origin(const char *value, bool allow_local_http);
bool fh_json_shape_ok(const char *data, size_t length, unsigned max_depth);
const char *fh_bambu_state(const char *value);
bool fh_valid_progress(double value);
bool fh_frame_feed(fh_frame *frame, const char *part, size_t length,
                   size_t offset, size_t total);
void fh_frame_reset(fh_frame *frame);
void fh_telemetry_reset(fh_telemetry *facts);
void fh_text_update(fh_text_fact *fact, const char *value, uint64_t at_ms);
void fh_number_update(fh_number_fact *fact, double value, uint64_t at_ms);
bool fh_fact_fresh(uint64_t at_ms, uint64_t now_ms);
bool fh_telemetry_fresh(const fh_telemetry *facts, uint64_t now_ms);
uint64_t fh_next_sequence(uint64_t *next, uint64_t *reserved_high,
                          bool (*reserve)(uint64_t high, void *context), void *context);

#endif
