#ifndef FH_EDGE_AMS_JOURNAL_FLASH_H
#define FH_EDGE_AMS_JOURNAL_FLASH_H

#include "ams.h"
#include "config.h"

bool fh_journal_flash_start(const fh_config *config);
bool fh_journal_flash_observe(size_t connection, const fh_ams_state *feed,
                              const char *observed_at, uint64_t sample_ms);
bool fh_journal_flash_poll(uint64_t now_ms);
void fh_journal_flash_read(uint64_t after_sequence, unsigned limit);

#endif
