#ifndef FH_EDGE_AMS_H
#define FH_EDGE_AMS_H

#include "core.h"

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* A fixed MCU bound, not a claim about every Bambu topology. Excess input is
 * rejected as a whole rather than publishing a truncated topology. */
#define FH_AMS_MAX_SLOTS 32

typedef struct {
    uint16_t provider_index;
    uint8_t unit_id;
    uint8_t tray_id;
    uint8_t presence_bit;
    bool external;
    bool present_known;
    bool present;
    uint64_t present_at_ms;
    bool material_known;
    char material[81];
    uint64_t material_at_ms;
    bool color_known;
    char color_hex[7];
    uint64_t color_at_ms;
    bool remaining_percent_known;
    int remaining_percent;
    uint64_t remaining_percent_at_ms;
    bool remaining_grams_known;
    int remaining_grams;
    uint64_t remaining_grams_at_ms;
    uint64_t slot_at_ms;
} fh_ams_slot;

typedef struct {
    fh_ams_slot slots[FH_AMS_MAX_SLOTS];
    uint8_t slot_count;
    bool topology_complete;
    uint64_t topology_at_ms;
    bool active_known;
    uint16_t active_index;
    uint64_t active_at_ms;
    uint64_t report_at_ms;
} fh_ams_state;

typedef enum {
    FH_AMS_NO_REPORT,
    FH_AMS_OBSERVED,
    FH_AMS_INVALID,
} fh_ams_result;

void fh_ams_reset(fh_ams_state *state);
fh_ams_result fh_ams_apply(fh_ams_state *state, const char *payload,
                           size_t length, uint64_t now_ms);
/* Returns one bounded local diagnostic line. The caller frees the result. */
char *fh_ams_event_json(const fh_ams_state *state, const char *connection_id,
                        const char *observed_at, uint64_t now_ms);
char *fh_ams_historical_event_json(const fh_ams_state *state,
                                   const char *connection_id,
                                   const char *observed_at, uint64_t sample_ms);
char *fh_ams_lifecycle_json(const char *connection_id, bool transport_error);

#endif
