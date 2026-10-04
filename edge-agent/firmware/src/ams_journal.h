#ifndef FH_EDGE_AMS_JOURNAL_H
#define FH_EDGE_AMS_JOURNAL_H

#include "ams.h"
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define FH_JOURNAL_SLOTS 32
#define FH_JOURNAL_RECORD_BYTES 8192
#define FH_JOURNAL_MIN_INTERVAL_MS 300000ULL

typedef struct {
    bool (*read)(void *context, size_t offset, void *data, size_t length);
    bool (*write)(void *context, size_t offset, const void *data, size_t length);
    bool (*erase)(void *context, size_t offset, size_t length);
    void *context;
} fh_journal_io;

typedef struct {
    char id[33];
    char source_id[49];
} fh_journal_identity;

typedef struct {
    uint64_t sequence;
    uint64_t boot_marker;
    uint64_t sample_ms;
    uint32_t coalesced;
    char id[33];
    char source_id[49];
    char observed_at[32];
    fh_ams_state feed;
} fh_journal_entry;

typedef struct {
    fh_journal_io io;
    fh_journal_identity identities[2];
    uint8_t identity_count;
    uint64_t boot_marker;
    uint64_t newest_sequence;
    uint64_t oldest_sequence;
    uint64_t last_commit_ms;
    uint32_t dropped[2];
    bool pending[2];
    bool committed[2];
    bool faulted;
    bool initialized;
    uint8_t *scratch;
    fh_ams_state pending_feed[2];
    fh_ams_state committed_feed[2];
    uint64_t pending_since[2];
    uint64_t pending_sample[2];
    char pending_utc[2][32];
} fh_ams_journal;

bool fh_journal_open(fh_ams_journal *journal, fh_journal_io io,
                     const fh_journal_identity *identities, size_t count,
                     uint64_t boot_marker);
void fh_journal_close(fh_ams_journal *journal);
bool fh_journal_observe(fh_ams_journal *journal, size_t identity,
                        const fh_ams_state *feed, const char *observed_at,
                        uint64_t sample_ms);
bool fh_journal_poll(fh_ams_journal *journal, uint64_t now_ms);
bool fh_journal_next(fh_ams_journal *journal, uint64_t after_sequence,
                     fh_journal_entry *entry);

#endif
