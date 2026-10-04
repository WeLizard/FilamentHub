#include "ntag.h"

#include <stdlib.h>
#include <string.h>

typedef struct {
    uint8_t last_user_page;
    uint8_t dynamic_lock_page;
    uint8_t config_page;
    uint16_t cc_bytes;
    uint8_t cc_size;
} tag_geometry;

static bool geometry(fh_tag_type type, tag_geometry *out)
{
    switch (type) {
    case FH_TAG_NTAG213: *out = (tag_geometry){39, 40, 41, 144, 0x12}; return true;
    case FH_TAG_NTAG215: *out = (tag_geometry){129, 130, 131, 496, 0x3e}; return true;
    case FH_TAG_NTAG216: *out = (tag_geometry){225, 226, 227, 872, 0x6d}; return true;
    default: return false;
    }
}

static fh_tag_type version_type(const uint8_t version[8])
{
    static const uint8_t prefix[6] = {0x00, 0x04, 0x04, 0x02, 0x01, 0x00};
    if (memcmp(version, prefix, sizeof(prefix)) || version[7] != 0x03)
        return FH_TAG_ISO14443A;
    switch (version[6]) {
    case 0x0f: return FH_TAG_NTAG213;
    case 0x11: return FH_TAG_NTAG215;
    case 0x13: return FH_TAG_NTAG216;
    default: return FH_TAG_ISO14443A;
    }
}

static bool read_data(const fh_tag_io *io, uint16_t count, uint8_t *data)
{
    uint8_t block[16];
    for (uint16_t offset = 0; offset < count; offset += 16) {
        if (!io->read4(io->context, (uint8_t)(4 + offset / 4), block)) return false;
        size_t remaining = count - offset;
        memcpy(data + offset, block, remaining < 16 ? remaining : 16);
    }
    return true;
}

static bool ndef_location(const uint8_t *data, size_t count, bool factory_213,
                          size_t *length_at, size_t *value_at, size_t *old_end)
{
    static const uint8_t control_213[5] = {0x01, 0x03, 0xa0, 0x0c, 0x34};
    size_t cursor = 0;
    if (factory_213 && count >= sizeof(control_213) &&
        memcmp(data, control_213, sizeof(control_213)) == 0)
        cursor = sizeof(control_213);
    if (cursor + 2 >= count || data[cursor++] != 0x03 ||
        data[cursor] == 0xff) return false;
    *length_at = cursor;
    size_t length = data[cursor++];
    if (length > count - cursor || cursor + length >= count ||
        data[cursor + length] != 0xfe) return false;
    *value_at = cursor;
    *old_end = cursor + length;
    return true;
}

static bool decode_uri(const uint8_t *data, size_t count, bool factory_213,
                       char uri[FH_NTAG_MAX_URI + 1])
{
    size_t length_at, value_at, old_end;
    if (!ndef_location(data, count, factory_213, &length_at, &value_at,
                       &old_end)) return false;
    size_t length = data[length_at];
    const uint8_t *record = data + value_at;
    if (length < 5 || record[0] != 0xd1 || record[1] != 1 ||
        record[2] != length - 4 || record[3] != 'U')
        return false;
    const char *prefix;
    if (record[4] == 0) prefix = "";
    else if (record[4] == 3) prefix = "http://";
    else if (record[4] == 4) prefix = "https://";
    else return false;
    size_t prefix_len = strlen(prefix);
    size_t uri_len = prefix_len + length - 5;
    if (!uri_len || uri_len > FH_NTAG_MAX_URI) return false;
    for (size_t i = 0; i < length - 5; i++)
        if (record[5 + i] < 0x21 || record[5 + i] > 0x7e) return false;
    memcpy(uri, prefix, prefix_len);
    memcpy(uri + prefix_len, record + 5, length - 5);
    uri[uri_len] = '\0';
    return true;
}

bool fh_nfc_uri_allowed(const char *origin, const char *uri)
{
    if (!origin || !uri) return false;
    size_t prefix = strlen(origin);
    if (!prefix || strncmp(uri, origin, prefix) ||
        strncmp(uri + prefix, "/qr/", 4)) return false;
    const char *code = uri + prefix + 4;
    size_t length = strlen(code);
    if (length < 3 || length > 100 || strlen(uri) > FH_NTAG_MAX_URI) return false;
    for (size_t i = 0; i < length; i++) {
        char ch = code[i];
        if (!((ch >= 'A' && ch <= 'Z') || (ch >= 'a' && ch <= 'z') ||
              (ch >= '0' && ch <= '9') || ch == '-' || ch == '_')) return false;
    }
    return true;
}

bool fh_tag_read(const fh_tag_io *io, fh_tag_info *info)
{
    if (!io || !info || !io->select || !io->version || !io->read4) return false;
    memset(info, 0, sizeof(*info));
    if (!io->select(io->context, info->uid, &info->uid_len,
                    &info->type, &info->collision)) return false;
    if (info->collision || info->type != FH_TAG_ISO14443A || info->uid_len != 7)
        return true;
    uint8_t version[8];
    if (!io->version(io->context, version)) return true;
    info->type = version_type(version);
    tag_geometry tag;
    if (!geometry(info->type, &tag)) return true;
    uint8_t cc[16];
    if (!io->read4(io->context, 2, cc) ||
        cc[4] != 0xe1 || cc[5] != 0x10 || cc[6] != tag.cc_size)
        return true;
    uint8_t *data = malloc(tag.cc_bytes);
    if (!data) return true;
    if (read_data(io, tag.cc_bytes, data)) {
        size_t length_at, value_at, old_end;
        info->ndef_known = ndef_location(data, tag.cc_bytes,
                                         info->type == FH_TAG_NTAG213, &length_at,
                                         &value_at, &old_end);
        if (info->ndef_known)
            info->uri_known = decode_uri(data, tag.cc_bytes,
                                         info->type == FH_TAG_NTAG213, info->uri);
    }
    free(data);
    return true;
}

static bool same_tag(const fh_tag_io *io, const uint8_t *expected, size_t length)
{
    uint8_t uid[10];
    size_t seen = 0;
    fh_tag_type type = FH_TAG_NONE;
    bool collision = false;
    return io->select(io->context, uid, &seen, &type, &collision) &&
           !collision && type == FH_TAG_ISO14443A && seen == length &&
           memcmp(uid, expected, length) == 0;
}

static bool write_verified(const fh_tag_io *io, const uint8_t *uid, size_t uid_len,
                           uint8_t page, const uint8_t bytes[4])
{
    uint8_t readback[16];
    return same_tag(io, uid, uid_len) &&
           io->write_page(io->context, page, bytes) &&
           io->read4(io->context, page, readback) &&
           memcmp(readback, bytes, 4) == 0;
}

bool fh_tag_write_uri(const fh_tag_io *io, const char *origin,
                      const uint8_t *expected_uid, size_t expected_uid_len,
                      const char *uri)
{
    if (!io || !io->select || !io->version || !io->read4 || !io->write_page ||
        !expected_uid || expected_uid_len != 7 || !fh_nfc_uri_allowed(origin, uri) ||
        !same_tag(io, expected_uid, expected_uid_len)) return false;
    uint8_t version[8];
    if (!io->version(io->context, version)) return false;
    tag_geometry tag;
    if (!geometry(version_type(version), &tag)) return false;
    uint8_t protected_before[16], config_before[16];
    if (!io->read4(io->context, 2, protected_before) ||
        !io->read4(io->context, tag.dynamic_lock_page, config_before)) return false;
    if (protected_before[2] || protected_before[3] ||
        protected_before[4] != 0xe1 || protected_before[5] != 0x10 ||
        protected_before[6] != tag.cc_size || protected_before[7] != 0x00 ||
        config_before[0] || config_before[1] || config_before[2] ||
        (config_before[4] & 0xc0) || config_before[7] != 0xff ||
        config_before[8] != 0x00) return false;
    uint8_t *original = malloc(tag.cc_bytes);
    uint8_t *desired = malloc(tag.cc_bytes);
    if (!original || !desired) { free(original); free(desired); return false; }
    bool okay = false;
    do {
        if (!read_data(io, tag.cc_bytes, original)) break;
        memcpy(desired, original, tag.cc_bytes);
        size_t length_at, value_at, old_end;
        if (!ndef_location(original, tag.cc_bytes,
                           version_type(version) == FH_TAG_NTAG213,
                           &length_at, &value_at,
                           &old_end)) break;
        if (length_at / 4 != value_at / 4) break;
        size_t uri_len = strlen(uri);
        size_t record_len = uri_len + 5;
        if (record_len > 254 || record_len + value_at >= tag.cc_bytes) break;
        size_t new_end = value_at + record_len;
        size_t end = old_end > new_end ? old_end : new_end;
        memset(desired + value_at, 0, end - value_at + 1);
        desired[length_at] = (uint8_t)record_len;
        desired[value_at] = 0xd1;
        desired[value_at + 1] = 1;
        desired[value_at + 2] = (uint8_t)(uri_len + 1);
        desired[value_at + 3] = 'U';
        desired[value_at + 4] = 0;
        memcpy(desired + value_at + 5, uri, uri_len);
        desired[new_end] = 0xfe;
        size_t stage_page = length_at / 4;
        uint8_t staged[4];
        memcpy(staged, original + stage_page * 4, 4);
        staged[length_at % 4] = 0;
        staged[value_at % 4] = 0xfe;
        if (!write_verified(io, expected_uid, expected_uid_len,
                            (uint8_t)(4 + stage_page), staged)) break;
        bool failed = false;
        for (size_t page = value_at / 4; page <= end / 4; page++) {
            if (page == stage_page ||
                memcmp(original + page * 4, desired + page * 4, 4) == 0)
                continue;
            if (!write_verified(io, expected_uid, expected_uid_len,
                                (uint8_t)(4 + page), desired + page * 4)) {
                failed = true;
                break;
            }
        }
        if (failed) break;
        if (!write_verified(io, expected_uid, expected_uid_len,
                            (uint8_t)(4 + stage_page), desired + stage_page * 4)) break;
        uint8_t protected_after[16], config_after[16];
        if (!same_tag(io, expected_uid, expected_uid_len) ||
            !io->read4(io->context, 2, protected_after) ||
            !io->read4(io->context, tag.dynamic_lock_page, config_after) ||
            memcmp(protected_before, protected_after, 8) ||
            memcmp(config_before, config_after, 9) ||
            !read_data(io, tag.cc_bytes, original) ||
            memcmp(original, desired, tag.cc_bytes)) break;
        okay = true;
    } while (false);
    free(original);
    free(desired);
    return okay;
}
