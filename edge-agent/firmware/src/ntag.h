#ifndef FH_EDGE_NTAG_H
#define FH_EDGE_NTAG_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define FH_NTAG_MAX_DATA 872
#define FH_NTAG_MAX_URI 249

typedef enum {
    FH_TAG_NONE = 0,
    FH_TAG_ISO14443A,
    FH_TAG_ISO15693,
    FH_TAG_NTAG213,
    FH_TAG_NTAG215,
    FH_TAG_NTAG216,
} fh_tag_type;

typedef struct {
    void *context;
    bool (*select)(void *context, uint8_t uid[10], size_t *uid_len,
                   fh_tag_type *type, bool *collision);
    bool (*version)(void *context, uint8_t version[8]);
    bool (*read4)(void *context, uint8_t first_page, uint8_t bytes[16]);
    bool (*write_page)(void *context, uint8_t page, const uint8_t bytes[4]);
} fh_tag_io;

typedef struct {
    fh_tag_type type;
    uint8_t uid[10];
    size_t uid_len;
    bool collision;
    bool ndef_known;
    bool uri_known;
    char uri[FH_NTAG_MAX_URI + 1];
} fh_tag_info;

bool fh_tag_read(const fh_tag_io *io, fh_tag_info *info);
bool fh_tag_write_uri(const fh_tag_io *io, const char *origin,
                      const uint8_t *expected_uid, size_t expected_uid_len,
                      const char *uri);
bool fh_nfc_uri_allowed(const char *origin, const char *uri);

#endif
