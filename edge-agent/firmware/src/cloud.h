#ifndef FH_EDGE_CLOUD_H
#define FH_EDGE_CLOUD_H

#include "config.h"
#include "core.h"
#include <stdbool.h>
#include <stdint.h>

typedef enum {
    FH_CLOUD_OK,
    FH_CLOUD_RETRY,
    FH_CLOUD_REVOKED,
    FH_CLOUD_REJECTED,
} fh_cloud_result;

fh_cloud_result fh_cloud_pair(fh_config *config, int index);
fh_cloud_result fh_cloud_snapshot(fh_config *config, int index,
                                  const fh_telemetry *facts, uint64_t now_ms,
                                  const char *observed_at);

#endif
