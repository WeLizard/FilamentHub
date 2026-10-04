#ifndef FH_EDGE_CONFIG_H
#define FH_EDGE_CONFIG_H

#include "core.h"
#include <stdbool.h>
#include <stdint.h>

typedef struct {
    char id[33];
    char host[64];
    char serial[81];
    char access_code[65];
    char bambu_cert_pem[2049];
    char pairing_code[33];
    char source_instance_id[49];
    char bridge_token[129];
    int32_t physical_printer_id;
    int32_t material_system_id;
    uint64_t sequence_reserved_high;
    uint64_t sequence_next;
} fh_connection;

typedef struct {
    bool enabled;
    uint8_t sck;
    uint8_t miso;
    uint8_t mosi;
    uint8_t nss;
    uint8_t busy;
    uint8_t rst;
} fh_nfc_pins;

typedef struct {
    uint32_t version;
    char node_instance_id[49];
    char wifi_ssid[33];
    char wifi_password[65];
    char cloud_origin[254];
    bool allow_local_http;
    uint8_t connection_count;
    fh_connection connections[FH_MAX_CONNECTIONS];
    fh_nfc_pins nfc;
} fh_config;

bool fh_config_load(fh_config *out);
bool fh_config_store(const fh_config *value);
bool fh_config_parse_line(const char *line, size_t length,
                          const fh_config *previous, fh_config *out);
void fh_random_identity(char output[49]);
bool fh_nfc_pins_valid(const fh_nfc_pins *pins);

#endif
