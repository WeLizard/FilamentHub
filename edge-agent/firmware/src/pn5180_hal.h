#ifndef FH_EDGE_PN5180_HAL_H
#define FH_EDGE_PN5180_HAL_H

#include "config.h"
#include "ntag.h"

#include "driver/spi_master.h"

typedef struct {
    spi_device_handle_t spi;
    fh_nfc_pins pins;
    bool bus_open;
    bool rf_on;
    uint8_t writable_end;
} fh_pn5180;

bool fh_pn5180_open(fh_pn5180 *reader, const fh_nfc_pins *pins);
void fh_pn5180_close(fh_pn5180 *reader);
fh_tag_io fh_pn5180_tag_io(fh_pn5180 *reader);
bool fh_pn_rx_bounded(uint32_t rx_status, size_t capacity, size_t *length);

#endif
