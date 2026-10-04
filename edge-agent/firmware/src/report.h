#ifndef FH_EDGE_REPORT_H
#define FH_EDGE_REPORT_H

#include "core.h"

bool fh_report_apply(fh_telemetry *facts, char job_key[180],
                     const char *payload, size_t length, uint64_t now_ms);

#endif
