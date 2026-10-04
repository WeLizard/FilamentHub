#include "ams_journal.h"

#include <stdlib.h>
#include <string.h>

#define HEADER_BYTES 160u
#define CRC_OFFSET 156u
#define COMMIT_OFFSET (FH_JOURNAL_RECORD_BYTES - 4u)
#define COMMIT_VALUE 0u
#define MAGIC 0x314a4146u
#define VERSION 1u

typedef struct { uint8_t *bytes; size_t at; size_t end; bool ok; } writer;
typedef struct { const uint8_t *bytes; size_t at; size_t end; bool ok; } reader;

static void put(writer *w, uint64_t value, size_t count)
{
    if (!w->ok || count > w->end - w->at) { w->ok = false; return; }
    for (size_t i = 0; i < count; i++) w->bytes[w->at++] = (uint8_t)(value >> (i * 8));
}

static uint64_t get(reader *r, size_t count)
{
    if (!r->ok || count > r->end - r->at) { r->ok = false; return 0; }
    uint64_t value = 0;
    for (size_t i = 0; i < count; i++) value |= (uint64_t)r->bytes[r->at++] << (i * 8);
    return value;
}

static void put_bytes(writer *w, const void *data, size_t count)
{
    if (!w->ok || count > w->end - w->at) { w->ok = false; return; }
    memcpy(w->bytes + w->at, data, count); w->at += count;
}

static void get_bytes(reader *r, void *data, size_t count)
{
    if (!r->ok || count > r->end - r->at) { r->ok = false; return; }
    memcpy(data, r->bytes + r->at, count); r->at += count;
}

static uint32_t crc_update(uint32_t crc, const uint8_t *data, size_t length)
{
    for (size_t i = 0; i < length; i++) {
        crc ^= data[i];
        for (int bit = 0; bit < 8; bit++)
            crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1u)));
    }
    return crc;
}

static uint32_t record_crc(const uint8_t *data, size_t length)
{
    uint32_t crc = crc_update(0xffffffffu, data, CRC_OFFSET);
    return ~crc_update(crc, data + HEADER_BYTES, length);
}

static bool same_slot(const fh_ams_slot *a, const fh_ams_slot *b)
{
    return a->provider_index == b->provider_index && a->unit_id == b->unit_id &&
           a->tray_id == b->tray_id && a->presence_bit == b->presence_bit &&
           a->external == b->external && a->present_known == b->present_known &&
           (!a->present_known || a->present == b->present) &&
           a->material_known == b->material_known &&
           (!a->material_known || strcmp(a->material, b->material) == 0) &&
           a->color_known == b->color_known &&
           (!a->color_known || strcmp(a->color_hex, b->color_hex) == 0) &&
           a->remaining_percent_known == b->remaining_percent_known &&
           (!a->remaining_percent_known || a->remaining_percent == b->remaining_percent) &&
           a->remaining_grams_known == b->remaining_grams_known &&
           (!a->remaining_grams_known || a->remaining_grams == b->remaining_grams);
}

static bool same_feed(const fh_ams_state *a, const fh_ams_state *b)
{
    if (a->slot_count != b->slot_count ||
        a->topology_complete != b->topology_complete ||
        a->active_known != b->active_known ||
        (a->active_known && a->active_index != b->active_index)) return false;
    for (size_t i = 0; i < a->slot_count; i++)
        if (!same_slot(&a->slots[i], &b->slots[i])) return false;
    return true;
}

static bool encode_feed(writer *w, const fh_ams_state *feed)
{
    if (feed->slot_count > FH_AMS_MAX_SLOTS) return false;
    put(w, feed->slot_count, 1); put(w, feed->topology_complete, 1);
    put(w, feed->topology_at_ms, 8); put(w, feed->active_known, 1);
    put(w, feed->active_index, 2); put(w, feed->active_at_ms, 8);
    put(w, feed->report_at_ms, 8);
    for (size_t i = 0; i < feed->slot_count; i++) {
        const fh_ams_slot *s = &feed->slots[i];
        uint8_t flags = (s->external ? 1 : 0) | (s->present_known ? 2 : 0) |
            (s->present ? 4 : 0) | (s->material_known ? 8 : 0) |
            (s->color_known ? 16 : 0) | (s->remaining_percent_known ? 32 : 0) |
            (s->remaining_grams_known ? 64 : 0);
        if (!memchr(s->material, 0, sizeof(s->material)) ||
            !memchr(s->color_hex, 0, sizeof(s->color_hex))) return false;
        put(w, s->provider_index, 2); put(w, s->unit_id, 1);
        put(w, s->tray_id, 1); put(w, s->presence_bit, 1); put(w, flags, 1);
        put(w, (uint32_t)s->remaining_percent, 4);
        put(w, (uint32_t)s->remaining_grams, 4);
        put(w, s->present_at_ms, 8); put(w, s->material_at_ms, 8);
        put(w, s->color_at_ms, 8); put(w, s->remaining_percent_at_ms, 8);
        put(w, s->remaining_grams_at_ms, 8); put(w, s->slot_at_ms, 8);
        put_bytes(w, s->material, sizeof(s->material));
        put_bytes(w, s->color_hex, sizeof(s->color_hex));
    }
    return w->ok;
}

static bool decode_feed(reader *r, fh_ams_state *feed)
{
    memset(feed, 0, sizeof(*feed));
    feed->slot_count = (uint8_t)get(r, 1);
    feed->topology_complete = get(r, 1) != 0;
    feed->topology_at_ms = get(r, 8); feed->active_known = get(r, 1) != 0;
    feed->active_index = (uint16_t)get(r, 2);
    feed->active_at_ms = get(r, 8); feed->report_at_ms = get(r, 8);
    if (!r->ok || feed->slot_count > FH_AMS_MAX_SLOTS) return false;
    for (size_t i = 0; i < feed->slot_count; i++) {
        fh_ams_slot *s = &feed->slots[i];
        s->provider_index = (uint16_t)get(r, 2);
        s->unit_id = (uint8_t)get(r, 1); s->tray_id = (uint8_t)get(r, 1);
        s->presence_bit = (uint8_t)get(r, 1);
        uint8_t flags = (uint8_t)get(r, 1);
        s->external = (flags & 1) != 0; s->present_known = (flags & 2) != 0;
        s->present = (flags & 4) != 0; s->material_known = (flags & 8) != 0;
        s->color_known = (flags & 16) != 0;
        s->remaining_percent_known = (flags & 32) != 0;
        s->remaining_grams_known = (flags & 64) != 0;
        s->remaining_percent = (int32_t)get(r, 4);
        s->remaining_grams = (int32_t)get(r, 4);
        s->present_at_ms = get(r, 8); s->material_at_ms = get(r, 8);
        s->color_at_ms = get(r, 8); s->remaining_percent_at_ms = get(r, 8);
        s->remaining_grams_at_ms = get(r, 8); s->slot_at_ms = get(r, 8);
        get_bytes(r, s->material, sizeof(s->material));
        get_bytes(r, s->color_hex, sizeof(s->color_hex));
        if (!r->ok || (flags & 128) ||
            !memchr(s->material, 0, sizeof(s->material)) ||
            !memchr(s->color_hex, 0, sizeof(s->color_hex))) return false;
    }
    return r->ok && r->at == r->end;
}

static bool make_record(fh_ams_journal *j, size_t identity, uint64_t seq,
                        uint32_t coalesced, const fh_ams_state *feed,
                        const char *utc, uint64_t sample)
{
    memset(j->scratch, 0xff, FH_JOURNAL_RECORD_BYTES);
    writer w = { j->scratch, 0, CRC_OFFSET, true };
    put(&w, MAGIC, 4); put(&w, VERSION, 2); put(&w, 0, 2);
    put(&w, seq, 8); put(&w, j->boot_marker, 8); put(&w, sample, 8);
    put(&w, coalesced, 4);
    put_bytes(&w, j->identities[identity].id, 33);
    put_bytes(&w, j->identities[identity].source_id, 49);
    char time[32] = {0};
    if (utc) memcpy(time, utc, strnlen(utc, sizeof(time) - 1));
    put_bytes(&w, time, 32);
    if (!w.ok) return false;
    writer body = {j->scratch, HEADER_BYTES, COMMIT_OFFSET, true};
    if (!encode_feed(&body, feed) || body.at - HEADER_BYTES > UINT16_MAX)
        return false;
    j->scratch[6] = (uint8_t)(body.at - HEADER_BYTES);
    j->scratch[7] = (uint8_t)((body.at - HEADER_BYTES) >> 8);
    uint32_t crc = record_crc(j->scratch, body.at - HEADER_BYTES);
    for (int i = 0; i < 4; i++) j->scratch[CRC_OFFSET + i] = (uint8_t)(crc >> (i * 8));
    return true;
}

static bool decode_record(fh_ams_journal *j, fh_journal_entry *out)
{
    reader h = {j->scratch, 0, CRC_OFFSET, true};
    if (get(&h, 4) != MAGIC || get(&h, 2) != VERSION) return false;
    size_t length = (size_t)get(&h, 2);
    if (length > COMMIT_OFFSET - HEADER_BYTES) return false;
    memset(out, 0, sizeof(*out));
    out->sequence = get(&h, 8); out->boot_marker = get(&h, 8);
    out->sample_ms = get(&h, 8); out->coalesced = (uint32_t)get(&h, 4);
    get_bytes(&h, out->id, 33); get_bytes(&h, out->source_id, 49);
    get_bytes(&h, out->observed_at, 32);
    if (!h.ok || !out->sequence || !memchr(out->id, 0, 33) ||
        !memchr(out->source_id, 0, 49) ||
        !memchr(out->observed_at, 0, 32)) return false;
    if (!fh_valid_id(out->id, 32) || !fh_valid_id(out->source_id, 48))
        return false;
    uint32_t stored = 0;
    for (int i = 0; i < 4; i++) stored |= (uint32_t)j->scratch[CRC_OFFSET + i] << (i * 8);
    if (stored != record_crc(j->scratch, length)) return false;
    reader body = {j->scratch, HEADER_BYTES, HEADER_BYTES + length, true};
    return decode_feed(&body, &out->feed);
}

static size_t slot_of(uint64_t sequence)
{
    return (size_t)((sequence - 1) % FH_JOURNAL_SLOTS);
}

static bool read_slot(fh_ams_journal *j, size_t slot, fh_journal_entry *out,
                      bool *empty, bool *torn)
{
    size_t offset = slot * FH_JOURNAL_RECORD_BYTES;
    if (!j->io.read(j->io.context, offset, j->scratch,
                    FH_JOURNAL_RECORD_BYTES)) return false;
    *empty = true;
    for (size_t i = 0; i < FH_JOURNAL_RECORD_BYTES; i++)
        if (j->scratch[i] != 0xff) { *empty = false; break; }
    *torn = false;
    if (*empty) return true;
    bool committed = true;
    bool erased_footer = true;
    for (size_t i = COMMIT_OFFSET; i < FH_JOURNAL_RECORD_BYTES; i++)
        committed &= j->scratch[i] == 0;
    for (size_t i = COMMIT_OFFSET; i < FH_JOURNAL_RECORD_BYTES; i++)
        erased_footer &= j->scratch[i] == 0xff;
    /* A partially programmed footer is indistinguishable from bit damage. */
    if (!committed && !erased_footer) return false;
    if (erased_footer) {
        const uint8_t prefix[6] = {0x46, 0x41, 0x4a, 0x31, 1, 0};
        bool plausible = true;
        for (size_t i = 0; i < sizeof(prefix); i++)
            plausible &= j->scratch[i] == prefix[i] || j->scratch[i] == 0xff;
        if (!plausible) return false;
        *torn = true; return true;
    }
    reader h = {j->scratch, 0, 8, true};
    if (get(&h, 4) != MAGIC || get(&h, 2) != VERSION ||
        get(&h, 2) > COMMIT_OFFSET - HEADER_BYTES) return false;
    return decode_record(j, out) && slot_of(out->sequence) == slot;
}

bool fh_journal_open(fh_ams_journal *j, fh_journal_io io,
                     const fh_journal_identity *identities, size_t count,
                     uint64_t boot_marker)
{
    if (!j || !io.read || !io.write || !io.erase ||
        count > 2 || (count && !identities) || !boot_marker) return false;
    for (size_t i = 0; i < count; i++)
        if (!fh_valid_id(identities[i].id, 32) ||
            !fh_valid_id(identities[i].source_id, 48)) return false;
    memset(j, 0, sizeof(*j));
    j->io = io; j->identity_count = (uint8_t)count;
    j->boot_marker = boot_marker;
    if (count) memcpy(j->identities, identities, count * sizeof(*identities));
    j->scratch = malloc(FH_JOURNAL_RECORD_BYTES);
    if (!j->scratch) return false;
    fh_journal_entry *entry = malloc(sizeof(*entry));
    if (!entry) { fh_journal_close(j); return false; }
    for (size_t slot = 0; slot < FH_JOURNAL_SLOTS; slot++) {
        bool empty, torn;
        if (!read_slot(j, slot, entry, &empty, &torn)) goto fail;
        if (empty || torn) continue;
        if (!j->oldest_sequence || entry->sequence < j->oldest_sequence)
            j->oldest_sequence = entry->sequence;
        if (entry->sequence > j->newest_sequence) j->newest_sequence = entry->sequence;
    }
    if (j->newest_sequence) {
        if (j->newest_sequence - j->oldest_sequence >= FH_JOURNAL_SLOTS)
            goto fail;
        for (uint64_t seq = j->oldest_sequence; seq <= j->newest_sequence; seq++) {
            bool empty, torn;
            if (!read_slot(j, slot_of(seq), entry, &empty, &torn) ||
                empty || torn || entry->sequence != seq) goto fail;
            for (size_t i = 0; i < count; i++)
                if (!strcmp(entry->id, j->identities[i].id) &&
                    !strcmp(entry->source_id, j->identities[i].source_id)) {
                    j->committed_feed[i] = entry->feed;
                    j->committed[i] = true;
                }
        }
    }
    j->initialized = true;
    free(entry);
    return true;
fail:
    free(entry);
    free(j->scratch);
    j->scratch = NULL;
    j->faulted = true;
    return false;
}

void fh_journal_close(fh_ams_journal *j)
{
    if (!j) return;
    free(j->scratch);
    j->scratch = NULL; j->initialized = false;
}

bool fh_journal_observe(fh_ams_journal *j, size_t identity,
                        const fh_ams_state *feed, const char *utc,
                        uint64_t sample_ms)
{
    if (!j || !j->initialized || j->faulted || identity >= j->identity_count ||
        !feed || feed->slot_count > FH_AMS_MAX_SLOTS || !sample_ms ||
        (utc && strnlen(utc, 32) >= 32)) return false;
    if (j->pending[identity] && same_feed(feed, &j->pending_feed[identity])) return true;
    if (j->committed[identity] && same_feed(feed, &j->committed_feed[identity])) {
        if (j->pending[identity]) {
            j->pending[identity] = false;
            j->dropped[identity]++;
        }
        return true;
    }
    if (j->pending[identity]) j->dropped[identity]++;
    else j->pending_since[identity] = sample_ms;
    j->pending_feed[identity] = *feed;
    j->pending_sample[identity] = sample_ms;
    memset(j->pending_utc[identity], 0, 32);
    if (utc) strcpy(j->pending_utc[identity], utc);
    j->pending[identity] = true;
    return true;
}

bool fh_journal_poll(fh_ams_journal *j, uint64_t now_ms)
{
    if (!j || !j->initialized || j->faulted) return false;
    if (j->last_commit_ms && now_ms - j->last_commit_ms < FH_JOURNAL_MIN_INTERVAL_MS)
        return true;
    size_t selected = j->identity_count;
    for (size_t i = 0; i < j->identity_count; i++)
        if (j->pending[i] && (selected == j->identity_count ||
                              j->pending_since[i] < j->pending_since[selected])) selected = i;
    if (selected == j->identity_count) return true;
    if (j->newest_sequence == UINT64_MAX) { j->faulted = true; return false; }
    uint64_t seq = j->newest_sequence + 1;
    size_t slot = slot_of(seq), offset = slot * FH_JOURNAL_RECORD_BYTES;
    if (!make_record(j, selected, seq, j->dropped[selected],
                     &j->pending_feed[selected], j->pending_utc[selected],
                     j->pending_sample[selected])) { j->faulted = true; return false; }
    uint16_t length = (uint16_t)(j->scratch[6] | ((uint16_t)j->scratch[7] << 8));
    if (!j->io.erase(j->io.context, offset, FH_JOURNAL_RECORD_BYTES) ||
        !j->io.write(j->io.context, offset, j->scratch, HEADER_BYTES + length)) {
        j->faulted = true; return false;
    }
    uint32_t commit = COMMIT_VALUE;
    if (!j->io.write(j->io.context, offset + COMMIT_OFFSET, &commit, sizeof(commit))) {
        j->faulted = true; return false;
    }
    j->newest_sequence = seq;
    if (!j->oldest_sequence) j->oldest_sequence = seq;
    if (seq - j->oldest_sequence >= FH_JOURNAL_SLOTS)
        j->oldest_sequence = seq - FH_JOURNAL_SLOTS + 1;
    j->last_commit_ms = now_ms;
    j->committed_feed[selected] = j->pending_feed[selected];
    j->committed[selected] = true;
    j->pending[selected] = false;
    j->dropped[selected] = 0;
    return true;
}

bool fh_journal_next(fh_ams_journal *j, uint64_t after, fh_journal_entry *entry)
{
    if (!j || !j->initialized || j->faulted || !entry ||
        !j->oldest_sequence || after >= j->newest_sequence) return false;
    uint64_t seq = after < j->oldest_sequence ? j->oldest_sequence : after + 1;
    bool empty, torn;
    if (!read_slot(j, slot_of(seq), entry, &empty, &torn) ||
        empty || torn || entry->sequence != seq) {
        j->faulted = true; return false;
    }
    return true;
}
