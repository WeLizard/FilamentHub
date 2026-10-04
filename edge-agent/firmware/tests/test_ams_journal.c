#include "ams_journal.h"

#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define FLASH_BYTES (FH_JOURNAL_SLOTS * FH_JOURNAL_RECORD_BYTES)

typedef struct {
    uint8_t bytes[FLASH_BYTES];
    size_t writes;
    size_t erases;
    size_t write_budget;
    bool limit_write;
} fake_flash;

static bool read_flash(void *context, size_t at, void *out, size_t length)
{
    fake_flash *flash = context;
    if (at > FLASH_BYTES || length > FLASH_BYTES - at) return false;
    memcpy(out, flash->bytes + at, length);
    return true;
}

static bool write_flash(void *context, size_t at, const void *data, size_t length)
{
    fake_flash *flash = context;
    if (at > FLASH_BYTES || length > FLASH_BYTES - at) return false;
    size_t count = length;
    if (flash->limit_write && count > flash->write_budget)
        count = flash->write_budget;
    const uint8_t *source = data;
    for (size_t i = 0; i < count; i++) {
        assert((flash->bytes[at + i] & source[i]) == source[i]);
        flash->bytes[at + i] &= source[i];
    }
    flash->writes++;
    if (flash->limit_write) {
        flash->write_budget -= count;
        if (count != length) return false;
    }
    return true;
}

static bool erase_flash(void *context, size_t at, size_t length)
{
    fake_flash *flash = context;
    if (at % 4096 || length % 4096 || at > FLASH_BYTES ||
        length > FLASH_BYTES - at) return false;
    memset(flash->bytes + at, 0xff, length);
    flash->erases++;
    return true;
}

static fh_journal_io io_for(fake_flash *flash)
{
    fh_journal_io io = {read_flash, write_flash, erase_flash, flash};
    return io;
}

static fh_journal_identity identities[2] = {
    {"p2s-a", "source-a-1234567890123456"},
    {"p2s-b", "source-b-1234567890123456"},
};

static void make_feed(fh_ams_state *state, int value, size_t slots)
{
    fh_ams_reset(state);
    state->slot_count = (uint8_t)slots;
    state->topology_complete = true;
    state->topology_at_ms = 100;
    state->active_known = true;
    state->active_index = 0;
    state->active_at_ms = 100;
    state->report_at_ms = 100;
    for (size_t i = 0; i < slots; i++) {
        fh_ams_slot *slot = &state->slots[i];
        slot->provider_index = (uint16_t)i;
        slot->unit_id = (uint8_t)(i / 4);
        slot->tray_id = (uint8_t)(i % 4);
        slot->present_known = slot->present = true;
        slot->present_at_ms = 100;
        slot->material_known = true;
        memset(slot->material, 'A' + (char)(i % 26), 80);
        slot->material[80] = 0;
        slot->material_at_ms = 100;
        slot->color_known = true;
        strcpy(slot->color_hex, "ABCDEF");
        slot->color_at_ms = 100;
        slot->remaining_grams_known = true;
        slot->remaining_grams = value;
        slot->remaining_grams_at_ms = 100;
        slot->slot_at_ms = 100;
    }
}

static fake_flash *new_flash(void)
{
    fake_flash *flash = malloc(sizeof(*flash));
    assert(flash);
    memset(flash, 0xff, sizeof(*flash));
    flash->writes = flash->erases = 0;
    flash->limit_write = false;
    return flash;
}

static void journal_basic(void)
{
    fake_flash *flash = new_flash();
    fh_ams_journal *journal = calloc(1, sizeof(*journal));
    fh_journal_entry *entry = malloc(sizeof(*entry));
    assert(journal && entry);
    assert(fh_journal_open(journal, io_for(flash), identities, 2, 11));
    fh_ams_state *feed = malloc(sizeof(*feed));
    assert(feed);
    make_feed(feed, 800, 32);
    assert(fh_journal_observe(journal, 0, feed, "2026-10-03T10:00:00Z", 100));
    assert(fh_journal_poll(journal, 100));
    assert(journal->newest_sequence == 1 && flash->writes == 2);
    assert(fh_journal_next(journal, 0, entry));
    assert(entry->feed.slot_count == 32 && entry->feed.slots[31].remaining_grams == 800);
    assert(entry->sequence == 1 && entry->boot_marker == 11);
    size_t writes = flash->writes;
    feed->report_at_ms = 200;
    feed->slots[0].slot_at_ms = 200;
    assert(fh_journal_observe(journal, 0, feed, "2026-10-03T10:01:00Z", 200));
    assert(fh_journal_poll(journal, 300100));
    assert(flash->writes == writes); /* Ages, UTC and heartbeat do not write. */
    fh_ams_state live;
    fh_ams_reset(&live);
    fh_journal_close(journal);
    assert(fh_journal_open(journal, io_for(flash), identities, 2, 22));
    assert(live.slot_count == 0); /* Replay never hydrates live slots. */
    assert(fh_journal_next(journal, 0, entry) && entry->boot_marker == 11);
    assert(journal->committed[0] && !journal->pending[0]);
    char *history = fh_ams_historical_event_json(&entry->feed, entry->id,
                                                  entry->observed_at,
                                                  entry->sample_ms);
    assert(history && strstr(history, "\"status\":\"historical\"") &&
           strstr(history, "\"capture_status\":\"observed\"") &&
           !strstr(history, "\"status\":\"observed\""));
    free(history);

    make_feed(feed, 801, 1);
    assert(fh_journal_observe(journal, 0, feed, "", 300200));
    assert(fh_journal_poll(journal, 300200));
    assert(journal->newest_sequence == 2);
    make_feed(feed, 900, 1);
    assert(fh_journal_observe(journal, 0, feed, "", 300201));
    make_feed(feed, 901, 1);
    assert(fh_journal_observe(journal, 0, feed, "", 300202));
    make_feed(feed, 700, 1);
    assert(fh_journal_observe(journal, 1, feed, "", 300203));
    assert(fh_journal_poll(journal, 600199));
    assert(journal->newest_sequence == 2);
    assert(fh_journal_poll(journal, 600200));
    assert(fh_journal_next(journal, 2, entry));
    assert(entry->sequence == 3 && entry->coalesced == 1 &&
           strcmp(entry->id, "p2s-a") == 0);
    assert(fh_journal_poll(journal, 900200));
    assert(fh_journal_next(journal, 3, entry));
    assert(entry->sequence == 4 && strcmp(entry->id, "p2s-b") == 0);
    assert(!fh_journal_next(journal, 4, entry));
    free(feed); free(entry);
    fh_journal_close(journal); free(journal); free(flash);
}

static void journal_rebinding(void)
{
    fake_flash *flash = new_flash();
    fh_ams_journal *journal = calloc(1, sizeof(*journal));
    fh_ams_state *feed = malloc(sizeof(*feed));
    fh_journal_entry *entry = malloc(sizeof(*entry));
    assert(journal && feed && entry);
    make_feed(feed, 10, 1);
    assert(fh_journal_open(journal, io_for(flash), identities, 1, 1));
    assert(fh_journal_observe(journal, 0, feed, "", 100));
    assert(fh_journal_poll(journal, 100));
    fh_journal_close(journal);
    fh_journal_identity replacement = identities[0];
    strcpy(replacement.source_id, "replacement-source-1234567890123456");
    assert(fh_journal_open(journal, io_for(flash), &replacement, 1, 2));
    assert(!journal->committed[0]);
    assert(fh_journal_observe(journal, 0, feed, "", 200));
    assert(fh_journal_poll(journal, 200));
    assert(journal->newest_sequence == 2);
    assert(fh_journal_next(journal, 0, entry));
    assert(strcmp(entry->source_id, identities[0].source_id) == 0);
    assert(fh_journal_next(journal, 1, entry));
    assert(strcmp(entry->source_id, replacement.source_id) == 0);
    free(entry); free(feed); fh_journal_close(journal);
    free(journal); free(flash);
}

static void journal_torn(size_t budget)
{
    fake_flash *flash = new_flash();
    fh_ams_journal *journal = calloc(1, sizeof(*journal));
    fh_ams_state *feed = malloc(sizeof(*feed));
    fh_journal_entry *entry = malloc(sizeof(*entry));
    assert(journal && feed && entry);
    make_feed(feed, 100, 1);
    assert(fh_journal_open(journal, io_for(flash), identities, 2, 11));
    flash->limit_write = true; flash->write_budget = budget;
    assert(fh_journal_observe(journal, 0, feed, "", 100));
    bool complete = fh_journal_poll(journal, 100);
    assert(!complete && journal->faulted);
    fh_journal_close(journal);
    flash->limit_write = false;
    assert(fh_journal_open(journal, io_for(flash), identities, 2, 22));
    assert(journal->newest_sequence == 0);
    assert(fh_journal_observe(journal, 0, feed, "", 200));
    assert(fh_journal_poll(journal, 200));
    assert(fh_journal_next(journal, 0, entry));
    assert(entry->sequence == 1 && entry->boot_marker == 22);
    free(entry); free(feed);
    fh_journal_close(journal); free(journal); free(flash);
}

static void journal_bad_footer(size_t budget, bool post_commit_flip)
{
    fake_flash *flash = new_flash();
    fh_ams_journal *journal = calloc(1, sizeof(*journal));
    fh_ams_state *feed = malloc(sizeof(*feed));
    assert(journal && feed);
    make_feed(feed, 100, 1);
    assert(fh_journal_open(journal, io_for(flash), identities, 1, 11));
    assert(fh_journal_observe(journal, 0, feed, "", 100));
    if (!post_commit_flip) {
        flash->limit_write = true; flash->write_budget = budget;
        assert(!fh_journal_poll(journal, 100));
    } else {
        assert(fh_journal_poll(journal, 100));
        flash->bytes[FH_JOURNAL_RECORD_BYTES - 4] ^= 1;
    }
    fh_journal_close(journal);
    flash->limit_write = false;
    size_t erases = flash->erases;
    assert(!fh_journal_open(journal, io_for(flash), identities, 1, 22));
    assert(journal->faulted && journal->newest_sequence == 0);
    assert(flash->erases == erases); /* No implicit erase or sequence reuse. */
    assert(!fh_journal_poll(journal, 200));
    fh_journal_close(journal);
    free(feed); free(journal); free(flash);
}

static void journal_wrap_and_corruption(void)
{
    fake_flash *flash = new_flash();
    fh_ams_journal *journal = calloc(1, sizeof(*journal));
    fh_ams_state *feed = malloc(sizeof(*feed));
    fh_journal_entry *entry = malloc(sizeof(*entry));
    assert(journal && feed && entry);
    assert(fh_journal_open(journal, io_for(flash), identities, 1, 11));
    for (int i = 1; i <= 35; i++) {
        make_feed(feed, i, 1);
        uint64_t now = (uint64_t)i * FH_JOURNAL_MIN_INTERVAL_MS;
        assert(fh_journal_observe(journal, 0, feed, "", now));
        assert(fh_journal_poll(journal, now));
    }
    assert(journal->oldest_sequence == 4 && journal->newest_sequence == 35);
    assert(fh_journal_next(journal, 0, entry) && entry->sequence == 4);
    fh_journal_close(journal);
    assert(fh_journal_open(journal, io_for(flash), identities, 1, 22));
    assert(journal->oldest_sequence == 4 && journal->newest_sequence == 35);
    /* Confirmed CRC failure must fail closed and never erase the config or log. */
    fh_journal_close(journal);
    flash->bytes[160 + 4 * FH_JOURNAL_RECORD_BYTES] ^= 1;
    size_t erases = flash->erases;
    assert(!fh_journal_open(journal, io_for(flash), identities, 1, 33));
    assert(journal->faulted && flash->erases == erases);
    fh_journal_close(journal);
    free(entry); free(feed); free(journal); free(flash);
}

static void journal_unknown_corruption(void)
{
    fake_flash *flash = new_flash();
    fh_ams_journal *journal = calloc(1, sizeof(*journal));
    assert(journal);
    flash->bytes[0] = 0x12;
    assert(!fh_journal_open(journal, io_for(flash), identities, 1, 1));
    assert(journal->faulted && flash->erases == 0);
    fh_journal_close(journal); free(journal); free(flash);
}

int main(void)
{
    journal_basic();
    journal_rebinding();
    for (size_t cut = 0; cut < 8; cut++) journal_torn(cut);
    journal_torn(80); journal_torn(159); journal_torn(160);
    journal_torn(320); journal_torn(338); journal_torn(339);
    journal_bad_footer(340, false); journal_bad_footer(341, false);
    journal_bad_footer(342, false); journal_bad_footer(0, true);
    journal_wrap_and_corruption();
    journal_unknown_corruption();
    puts("AMS journal host tests passed");
    return 0;
}
