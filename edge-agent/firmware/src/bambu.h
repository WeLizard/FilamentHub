#ifndef FH_EDGE_BAMBU_H
#define FH_EDGE_BAMBU_H

#include "config.h"
#include "core.h"
#include "ams.h"

#include <stdbool.h>
#include <stdint.h>

bool fh_bambu_start(const fh_connection *connection);
void fh_bambu_stop(void);
bool fh_bambu_failed(void);
bool fh_bambu_observation(fh_telemetry *facts, char observed_at[32],
                          uint32_t *revision);
void fh_bambu_ack(uint32_t revision);
bool fh_bambu_ams_observation(fh_ams_state *feed, char observed_at[32],
                               uint32_t *revision);

#endif
