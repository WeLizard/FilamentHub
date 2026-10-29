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
    /* The server already holds a newer snapshot; the local sequence was moved
     * past it, so a prompt retry is accepted. */
    FH_CLOUD_STALE,
} fh_cloud_result;

fh_cloud_result fh_cloud_pair(fh_config *config, int index);
fh_cloud_result fh_cloud_snapshot(fh_config *config, int index,
                                  const fh_telemetry *facts, uint64_t now_ms,
                                  const char *observed_at);
/* Proof of life while the printer cannot be read: the helper is up, the
 * printer behind it is (provider_reachable=false) or is not answering. */
fh_cloud_result fh_cloud_heartbeat(const fh_config *config, int index,
                                   bool provider_reachable, const char *observed_at);

#endif
