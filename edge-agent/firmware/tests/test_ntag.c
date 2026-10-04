#include "ntag.h"

#include <assert.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    uint8_t memory[231 * 4];
    uint8_t uid[7];
    uint8_t version[8];
    fh_tag_type type;
    int selects;
    int writes;
    int fail_write_at;
    int swap_after_writes;
    int remove_after_writes;
    int corrupt_write_at;
    bool collision;
    uint8_t last_user_page;
} fake_tag;

static bool select_tag(void *ctx, uint8_t uid[10], size_t *length,
                       fh_tag_type *type, bool *collision)
{
    fake_tag *tag = ctx;
    tag->selects++;
    if (tag->remove_after_writes &&
        tag->writes >= tag->remove_after_writes) return false;
    *type = tag->type;
    *collision = tag->collision;
    *length = tag->type == FH_TAG_ISO15693 ? 8 : 7;
    memcpy(uid, tag->uid, 7);
    if (*length == 8) uid[7] = 0x42;
    if (tag->swap_after_writes && tag->writes >= tag->swap_after_writes)
        uid[6] ^= 0xff;
    return true;
}

static bool version_tag(void *ctx, uint8_t version[8])
{
    memcpy(version, ((fake_tag *)ctx)->version, 8);
    return true;
}

static bool read4(void *ctx, uint8_t page, uint8_t bytes[16])
{
    fake_tag *tag = ctx;
    if (page > 227) return false;
    memcpy(bytes, tag->memory + (size_t)page * 4, 16);
    return true;
}

static bool write_page(void *ctx, uint8_t page, const uint8_t bytes[4])
{
    fake_tag *tag = ctx;
    tag->writes++;
    assert(page >= 4 && page <= tag->last_user_page);
    if (tag->fail_write_at == tag->writes) return false;
    memcpy(tag->memory + (size_t)page * 4, bytes, 4);
    if (tag->corrupt_write_at == tag->writes)
        tag->memory[(size_t)page * 4] ^= 1;
    return true;
}

static void setup(fake_tag *tag, uint8_t storage, uint8_t cc_size,
                  uint8_t last_user, uint8_t dynamic_lock)
{
    memset(tag, 0, sizeof(*tag));
    tag->type = FH_TAG_ISO14443A;
    tag->last_user_page = last_user;
    const uint8_t uid[] = {0x04, 0x11, 0x22, 0x33, 0x44, 0x55, 0x66};
    memcpy(tag->uid, uid, 7);
    const uint8_t version[] = {0x00, 0x04, 0x04, 0x02, 0x01, 0x00, storage, 0x03};
    memcpy(tag->version, version, 8);
    uint8_t *cc = tag->memory + 3 * 4;
    cc[0] = 0xe1; cc[1] = 0x10; cc[2] = cc_size; cc[3] = 0;
    uint8_t *user = tag->memory + 4 * 4;
    if (storage == 0x0f) {
        const uint8_t factory[] = {0x01, 0x03, 0xa0, 0x0c, 0x34,
                                   0x03, 0x00, 0xfe};
        memcpy(user, factory, sizeof(factory));
    } else {
        user[0] = 0x03; user[1] = 0; user[2] = 0xfe;
    }
    tag->memory[(size_t)(dynamic_lock + 1) * 4 + 3] = 0xff;
}

static fh_tag_io interface(fake_tag *tag)
{
    return (fh_tag_io){tag, select_tag, version_tag, read4, write_page};
}

int main(void)
{
    const char *origin = "https://filamenthub.ru";
    const char *uri = "https://filamenthub.ru/qr/FHQ1_01_X_U_abcdefghijklmnop";
    assert(fh_nfc_uri_allowed(origin, uri));
    assert(!fh_nfc_uri_allowed(origin, "https://evil.test/qr/FHQ1_01_X_U_abcdefghijklmnop"));
    assert(!fh_nfc_uri_allowed(origin, "https://filamenthub.ru/qr/X?token=secret"));
    const uint8_t types[3] = {0x0f, 0x11, 0x13};
    const uint8_t cc[3] = {0x12, 0x3e, 0x6d};
    const uint8_t last[3] = {39, 129, 225};
    const uint8_t locks[3] = {40, 130, 226};
    for (int index = 0; index < 3; index++) {
        fake_tag tag;
        setup(&tag, types[index], cc[index], last[index], locks[index]);
        uint8_t protected_before[16];
        memcpy(protected_before, tag.memory + 2 * 4, 8);
        memcpy(protected_before + 8, tag.memory + (size_t)locks[index] * 4, 8);
        fh_tag_io io = interface(&tag);
        fh_tag_info info;
        assert(fh_tag_read(&io, &info));
        assert(info.ndef_known && !info.uri_known);
        assert(fh_tag_write_uri(&io, origin, tag.uid, 7, uri));
        assert(tag.writes > 1);
        assert(fh_tag_read(&io, &info));
        assert(info.uri_known && strcmp(info.uri, uri) == 0);
        assert(memcmp(protected_before, tag.memory + 2 * 4, 8) == 0);
        assert(memcmp(protected_before + 8,
                      tag.memory + (size_t)locks[index] * 4, 8) == 0);
        if (index == 0) {
            const uint8_t prefix[] = {0x01, 0x03, 0xa0, 0x0c, 0x34};
            assert(memcmp(tag.memory + 4 * 4, prefix, sizeof(prefix)) == 0);
        }
        setup(&tag, types[index], cc[index], last[index], locks[index]);
        tag.memory[2 * 4 + 2] = 1;
        assert(!fh_tag_write_uri(&io, origin, tag.uid, 7, uri) && tag.writes == 0);
        setup(&tag, types[index], cc[index], last[index], locks[index]);
        tag.memory[(size_t)locks[index] * 4] = 1;
        assert(!fh_tag_write_uri(&io, origin, tag.uid, 7, uri) && tag.writes == 0);
        setup(&tag, types[index], cc[index], last[index], locks[index]);
        tag.memory[(size_t)(locks[index] + 1) * 4 + 3] = 4;
        assert(!fh_tag_write_uri(&io, origin, tag.uid, 7, uri) && tag.writes == 0);
    }
    fake_tag tag;
    setup(&tag, 0x0f, 0x12, 39, 40);
    fh_tag_io io = interface(&tag);
    const char *long_origin = "https://very-long-local-domain.example";
    char long_uri[240];
    strcpy(long_uri, "https://very-long-local-domain.example/qr/");
    memset(long_uri + strlen(long_uri), 'A', 100);
    long_uri[strlen("https://very-long-local-domain.example/qr/") + 100] = '\0';
    assert(!fh_tag_write_uri(&io, long_origin, tag.uid, 7, long_uri));
    assert(tag.writes == 0);
    setup(&tag, 0x0f, 0x12, 39, 40);
    tag.swap_after_writes = 1;
    assert(!fh_tag_write_uri(&io, origin, tag.uid, 7, uri));
    assert(tag.writes == 1);
    setup(&tag, 0x0f, 0x12, 39, 40);
    tag.remove_after_writes = 1;
    assert(!fh_tag_write_uri(&io, origin, tag.uid, 7, uri));
    assert(tag.writes == 1);
    setup(&tag, 0x0f, 0x12, 39, 40);
    tag.corrupt_write_at = 1;
    assert(!fh_tag_write_uri(&io, origin, tag.uid, 7, uri));
    assert(tag.writes == 1);
    setup(&tag, 0x0f, 0x12, 39, 40);
    tag.version[1] = 0x05;
    assert(!fh_tag_write_uri(&io, origin, tag.uid, 7, uri));
    assert(tag.writes == 0);
    setup(&tag, 0x0f, 0x12, 39, 40);
    assert(fh_tag_write_uri(&io, origin, tag.uid, 7, uri));
    int write_count = tag.writes;
    for (int boundary = 1; boundary <= write_count; boundary++) {
        setup(&tag, 0x0f, 0x12, 39, 40);
        tag.fail_write_at = boundary;
        assert(!fh_tag_write_uri(&io, origin, tag.uid, 7, uri));
        assert(tag.writes == boundary);
        tag.fail_write_at = 0;
        assert(fh_tag_write_uri(&io, origin, tag.uid, 7, uri));
        fh_tag_info repaired;
        assert(fh_tag_read(&io, &repaired));
        assert(repaired.uri_known && strcmp(repaired.uri, uri) == 0);
    }
    setup(&tag, 0x0f, 0x12, 39, 40);
    tag.memory[4 * 4 + 2] = 0x01;
    assert(!fh_tag_write_uri(&io, origin, tag.uid, 7, uri));
    assert(tag.writes == 0);
    setup(&tag, 0x11, 0x3e, 129, 130);
    uint8_t *data = tag.memory + 4 * 4;
    const char *compressed = "filamenthub.ru/qr/FH-001";
    size_t compressed_len = strlen(compressed);
    data[0] = 0x03;
    data[1] = (uint8_t)(compressed_len + 5);
    data[2] = 0xd1; data[3] = 1; data[4] = (uint8_t)(compressed_len + 1);
    data[5] = 'U'; data[6] = 4;
    memcpy(data + 7, compressed, compressed_len);
    data[7 + compressed_len] = 0xfe;
    fh_tag_info info;
    assert(fh_tag_read(&io, &info));
    assert(info.uri_known &&
           strcmp(info.uri, "https://filamenthub.ru/qr/FH-001") == 0);
    setup(&tag, 0x0f, 0x12, 39, 40);
    tag.collision = true;
    assert(!fh_tag_write_uri(&io, origin, tag.uid, 7, uri));
    assert(tag.writes == 0);
    tag.type = FH_TAG_ISO15693;
    assert(fh_tag_read(&io, &(fh_tag_info){0}));
    puts("NTAG host tests passed");
    return 0;
}
