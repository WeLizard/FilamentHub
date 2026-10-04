#ifndef FH_EDGE_SNAPSHOT_H
#define FH_EDGE_SNAPSHOT_H

#include "config.h"
#include "core.h"

#include <stdint.h>

char *fh_snapshot_body(const fh_config *config, int index,
                       const fh_telemetry *facts, uint64_t now_ms,
                       const char *observed_at, uint64_t sequence);

#endif
