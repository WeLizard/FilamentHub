#include "pn5180_hal.h"

#include "driver/gpio.h"
#include "esp_rom_sys.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include <string.h>

/* PN5180 direct-command and register values: NXP PN5180 product data sheet,
 * Rev. 3.6, sections 11.4 and 11.5. Only register/RF commands are emitted. */
enum {
    CMD_WRITE_REGISTER = 0x00, CMD_AND_MASK = 0x02,
    CMD_OR_MASK = 0x01, CMD_READ_REGISTER = 0x04,
    CMD_SEND_DATA = 0x09, CMD_READ_DATA = 0x0a,
    CMD_LOAD_RF = 0x11, CMD_RF_ON = 0x16, CMD_RF_OFF = 0x17,
    REG_SYSTEM = 0x00, REG_IRQ_STATUS = 0x02, REG_IRQ_CLEAR = 0x03,
    REG_CRC_RX = 0x12, REG_RX_STATUS = 0x13, REG_CRC_TX = 0x19,
    REG_RF_STATUS = 0x1d,
};

#define IRQ_RX (1u << 0)
#define IRQ_ERROR (1u << 17)
#define RX_COLLISION (1u << 18)
#define RX_PROTOCOL_ERROR (1u << 17)
#define RX_INTEGRITY_ERROR (1u << 16)

typedef enum { FRAME_OK, FRAME_NONE, FRAME_COLLISION, FRAME_ERROR } frame_result;

static void delay_at_least_ms(uint32_t milliseconds)
{
    /* vTaskDelay can return just before a tick; one extra tick guarantees
     * the requested RF field-off/on time at the configured tick rate. */
    TickType_t ticks = (TickType_t)(((uint64_t)milliseconds *
                         configTICK_RATE_HZ + 999u) / 1000u + 1u);
    vTaskDelay(ticks);
}

static bool wait_busy(fh_pn5180 *reader, int level, int timeout_ms)
{
    int64_t deadline = esp_timer_get_time() + (int64_t)timeout_ms * 1000;
    while (gpio_get_level(reader->pins.busy) != level) {
        if (esp_timer_get_time() >= deadline) return false;
        vTaskDelay(1);
    }
    return true;
}

static bool command(fh_pn5180 *reader, const uint8_t *tx, size_t tx_len,
                    uint8_t *rx, size_t rx_len)
{
    if (!reader || !reader->spi || !tx || !tx_len || tx_len > 32 ||
        rx_len > 16 || (rx_len && !rx)) return false;
    spi_transaction_t transfer = {0};
    transfer.tx_buffer = tx;
    transfer.length = tx_len * 8;
    if (!wait_busy(reader, 0, 100)) return false;
    gpio_set_level(reader->pins.nss, 0);
    esp_rom_delay_us(10);
    esp_err_t err = spi_device_polling_transmit(reader->spi, &transfer);
    bool completed = err == ESP_OK && wait_busy(reader, 1, 100);
    gpio_set_level(reader->pins.nss, 1);
    if (!completed || !wait_busy(reader, 0, 100)) return false;
    if (!rx_len) return true;
    uint8_t dummy[16] = {0};
    memset(&transfer, 0, sizeof(transfer));
    transfer.tx_buffer = dummy;
    transfer.rx_buffer = rx;
    transfer.length = rx_len * 8;
    gpio_set_level(reader->pins.nss, 0);
    esp_rom_delay_us(10);
    err = spi_device_polling_transmit(reader->spi, &transfer);
    completed = err == ESP_OK && wait_busy(reader, 1, 100);
    gpio_set_level(reader->pins.nss, 1);
    return completed && wait_busy(reader, 0, 100);
}

static bool mask_register(fh_pn5180 *reader, uint8_t command_code,
                          uint8_t reg, uint32_t mask)
{
    uint8_t command_bytes[6] = {command_code, reg, (uint8_t)mask,
        (uint8_t)(mask >> 8), (uint8_t)(mask >> 16), (uint8_t)(mask >> 24)};
    return command(reader, command_bytes, sizeof(command_bytes), NULL, 0);
}

static bool read_register(fh_pn5180 *reader, uint8_t reg, uint32_t *value)
{
    uint8_t request[2] = {CMD_READ_REGISTER, reg};
    uint8_t reply[4];
    if (!value || !command(reader, request, sizeof(request), reply, sizeof(reply)))
        return false;
    *value = (uint32_t)reply[0] | ((uint32_t)reply[1] << 8) |
             ((uint32_t)reply[2] << 16) | ((uint32_t)reply[3] << 24);
    return true;
}

static bool clear_irq(fh_pn5180 *reader)
{
    return mask_register(reader, CMD_WRITE_REGISTER, REG_IRQ_CLEAR, UINT32_MAX);
}

bool fh_pn_rx_bounded(uint32_t rx_status, size_t capacity, size_t *length)
{
    if (!length || rx_status & (RX_COLLISION | RX_PROTOCOL_ERROR |
                                RX_INTEGRITY_ERROR)) return false;
    size_t received = rx_status & 0x1ffu;
    if (!received || received > capacity || received > 16) return false;
    *length = received;
    return true;
}

static bool set_crc(fh_pn5180 *reader, bool tx, bool rx)
{
    return mask_register(reader, tx ? CMD_OR_MASK : CMD_AND_MASK,
                         REG_CRC_TX, tx ? 1u : UINT32_MAX - 1u) &&
           mask_register(reader, rx ? CMD_OR_MASK : CMD_AND_MASK,
                         REG_CRC_RX, rx ? 1u : UINT32_MAX - 1u);
}

static bool set_rf(fh_pn5180 *reader, uint8_t protocol)
{
    if (reader->rf_on) {
        const uint8_t off[2] = {CMD_RF_OFF, 0};
        if (!command(reader, off, sizeof(off), NULL, 0)) return false;
        reader->rf_on = false;
        /* A selected Type A tag needs field-off time to return to IDLE
         * before the next REQA and anticollision sequence. */
        delay_at_least_ms(10);
    }
    const uint8_t load[3] = {CMD_LOAD_RF, protocol, (uint8_t)(protocol | 0x80)};
    const uint8_t on[2] = {CMD_RF_ON, 0};
    uint32_t status;
    if (!mask_register(reader, CMD_AND_MASK, REG_SYSTEM, UINT32_MAX - 0x40u) ||
        !mask_register(reader, CMD_AND_MASK, REG_SYSTEM, UINT32_MAX - 7u) ||
        !command(reader, load, sizeof(load), NULL, 0) ||
        !command(reader, on, sizeof(on), NULL, 0) ||
        !read_register(reader, REG_RF_STATUS, &status) ||
        !(status & (1u << 17))) return false;
    reader->rf_on = true;
    delay_at_least_ms(5);
    return true;
}

static bool send_rf(fh_pn5180 *reader, const uint8_t *data, size_t length,
                    uint8_t valid_bits)
{
    if (!data || !length || length > 16 || valid_bits > 7) return false;
    if (!mask_register(reader, CMD_AND_MASK, REG_SYSTEM, UINT32_MAX - 7u) ||
        !mask_register(reader, CMD_OR_MASK, REG_SYSTEM, 3u)) return false;
    int64_t deadline = esp_timer_get_time() + 100000;
    uint32_t state;
    do {
        if (!read_register(reader, REG_RF_STATUS, &state)) return false;
        if (((state >> 24) & 7u) == 1u) break;
        if (esp_timer_get_time() >= deadline) return false;
        vTaskDelay(1);
    } while (true);
    if (!clear_irq(reader)) return false;
    uint8_t frame[18] = {CMD_SEND_DATA, valid_bits};
    memcpy(frame + 2, data, length);
    return command(reader, frame, length + 2, NULL, 0);
}

static frame_result receive_rf(fh_pn5180 *reader, uint8_t *output,
                               size_t capacity, size_t *length,
                               uint32_t *status_out)
{
    int64_t deadline = esp_timer_get_time() + 100000;
    uint32_t irq = 0;
    do {
        if (!read_register(reader, REG_IRQ_STATUS, &irq)) return FRAME_ERROR;
        if (irq & (IRQ_RX | IRQ_ERROR)) break;
        if (esp_timer_get_time() >= deadline) return FRAME_NONE;
        vTaskDelay(1);
    } while (true);
    uint32_t status = 0;
    bool status_ok = read_register(reader, REG_RX_STATUS, &status);
    clear_irq(reader);
    if (!status_ok) return FRAME_ERROR;
    if (status_out) *status_out = status;
    if (status & RX_COLLISION) return FRAME_COLLISION;
    if ((irq & IRQ_ERROR) || !fh_pn_rx_bounded(status, capacity, length))
        return FRAME_ERROR;
    uint8_t request[2] = {CMD_READ_DATA, 0};
    return command(reader, request, sizeof(request), output, *length) ?
           FRAME_OK : FRAME_ERROR;
}

static frame_result frame(fh_pn5180 *reader, const uint8_t *request,
                          size_t request_len, uint8_t valid_bits,
                          bool tx_crc, bool rx_crc,
                          uint8_t *reply, size_t capacity, size_t *reply_len,
                          uint32_t *rx_status)
{
    if (!set_crc(reader, tx_crc, rx_crc) ||
        !send_rf(reader, request, request_len, valid_bits)) return FRAME_ERROR;
    return receive_rf(reader, reply, capacity, reply_len, rx_status);
}

static bool select_a(void *context, uint8_t uid[10], size_t *uid_len,
                     fh_tag_type *type, bool *collision)
{
    fh_pn5180 *reader = context;
    *collision = false;
    *uid_len = 0;
    if (!set_rf(reader, 0x00)) return false;
    uint8_t atqa[2], request = 0x26;
    size_t received;
    frame_result result = frame(reader, &request, 1, 7, false, false,
                                atqa, sizeof(atqa), &received, NULL);
    if (result == FRAME_COLLISION) {
        *type = FH_TAG_ISO14443A;
        *collision = true;
        return true;
    }
    if (result != FRAME_OK || received != 2) return false;
    uint8_t level1[5], level2[5];
    uint8_t anticoll[2] = {0x93, 0x20};
    result = frame(reader, anticoll, 2, 0, false, false,
                   level1, sizeof(level1), &received, NULL);
    if (result == FRAME_COLLISION) {
        *type = FH_TAG_ISO14443A;
        *collision = true;
        return true;
    }
    if (result != FRAME_OK || received != 5 ||
        (uint8_t)(level1[0] ^ level1[1] ^ level1[2] ^ level1[3]) != level1[4])
        return false;
    uint8_t select[7] = {0x93, 0x70};
    memcpy(select + 2, level1, 5);
    uint8_t sak[1];
    result = frame(reader, select, 7, 0, true, true,
                   sak, sizeof(sak), &received, NULL);
    if (result != FRAME_OK || received != 1) return false;
    *type = FH_TAG_ISO14443A;
    if (!(sak[0] & 0x04)) {
        memcpy(uid, level1, 4);
        *uid_len = 4;
        return true;
    }
    if (level1[0] != 0x88) return false;
    anticoll[0] = 0x95;
    result = frame(reader, anticoll, 2, 0, false, false,
                   level2, sizeof(level2), &received, NULL);
    if (result == FRAME_COLLISION) {
        *collision = true;
        return true;
    }
    if (result != FRAME_OK || received != 5 ||
        (uint8_t)(level2[0] ^ level2[1] ^ level2[2] ^ level2[3]) != level2[4])
        return false;
    select[0] = 0x95;
    memcpy(select + 2, level2, 5);
    result = frame(reader, select, 7, 0, true, true,
                   sak, sizeof(sak), &received, NULL);
    if (result != FRAME_OK || received != 1 || (sak[0] & 0x04)) return false;
    memcpy(uid, level1 + 1, 3);
    memcpy(uid + 3, level2, 4);
    *uid_len = 7;
    return true;
}

static bool select_any(void *context, uint8_t uid[10], size_t *uid_len,
                       fh_tag_type *type, bool *collision)
{
    if (select_a(context, uid, uid_len, type, collision)) return true;
    fh_pn5180 *reader = context;
    if (!set_rf(reader, 0x0d)) return false;
    const uint8_t inventory[3] = {0x26, 0x01, 0x00};
    uint8_t response[10];
    size_t received;
    frame_result result = frame(reader, inventory, sizeof(inventory), 0,
                                true, true, response, sizeof(response),
                                &received, NULL);
    if (result == FRAME_COLLISION) {
        *type = FH_TAG_ISO15693;
        *collision = true;
        *uid_len = 0;
        return true;
    }
    if (result != FRAME_OK || received != 10 || (response[0] & 0x01)) return false;
    memcpy(uid, response + 2, 8);
    *uid_len = 8;
    *type = FH_TAG_ISO15693;
    *collision = false;
    return true;
}

static bool tag_command(fh_pn5180 *reader, const uint8_t *request,
                        size_t request_len, uint8_t *response,
                        size_t expected, bool ack)
{
    size_t received = 0;
    uint32_t status = 0;
    frame_result result = frame(reader, request, request_len, 0, true, !ack,
                                response, expected, &received, &status);
    if (result != FRAME_OK || received != expected) return false;
    if (ack) return (status & (7u << 13)) == (4u << 13) &&
                    (response[0] & 0x0f) == 0x0a;
    return (status & (7u << 13)) == 0;
}

static bool get_version(void *context, uint8_t version[8])
{
    const uint8_t request = 0x60;
    if (!tag_command(context, &request, 1, version, 8, false)) return false;
    fh_pn5180 *reader = context;
    const uint8_t prefix[6] = {0x00, 0x04, 0x04, 0x02, 0x01, 0x00};
    if (memcmp(version, prefix, sizeof(prefix)) == 0 && version[7] == 0x03) {
        if (version[6] == 0x0f) reader->writable_end = 39;
        else if (version[6] == 0x11) reader->writable_end = 129;
        else if (version[6] == 0x13) reader->writable_end = 225;
    }
    return true;
}

static bool read4(void *context, uint8_t first_page, uint8_t bytes[16])
{
    const uint8_t request[2] = {0x30, first_page};
    return tag_command(context, request, 2, bytes, 16, false);
}

static bool write_page(void *context, uint8_t page, const uint8_t bytes[4])
{
    fh_pn5180 *reader = context;
    if (!reader || page < 4 || page > reader->writable_end || !bytes) return false;
    uint8_t request[6] = {0xa2, page};
    memcpy(request + 2, bytes, 4);
    uint8_t ack[1];
    return tag_command(context, request, sizeof(request), ack, 1, true);
}

bool fh_pn5180_open(fh_pn5180 *reader, const fh_nfc_pins *pins)
{
    if (!reader || !fh_nfc_pins_valid(pins)) return false;
    memset(reader, 0, sizeof(*reader));
    reader->pins = *pins;
    gpio_config_t out = {
        .pin_bit_mask = (1ULL << pins->nss) | (1ULL << pins->rst),
        .mode = GPIO_MODE_OUTPUT,
    };
    gpio_config_t in = {
        .pin_bit_mask = 1ULL << pins->busy,
        .mode = GPIO_MODE_INPUT,
    };
    if (gpio_config(&out) != ESP_OK || gpio_config(&in) != ESP_OK) return false;
    gpio_set_level(pins->nss, 1);
    gpio_set_level(pins->rst, 0);
    spi_bus_config_t bus = {
        .mosi_io_num = pins->mosi, .miso_io_num = pins->miso,
        .sclk_io_num = pins->sck, .quadwp_io_num = -1, .quadhd_io_num = -1,
    };
    if (spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_DISABLED) != ESP_OK)
        return false;
    reader->bus_open = true;
    spi_device_interface_config_t device = {
        .clock_speed_hz = 2000000, .mode = 0, .spics_io_num = -1,
        .queue_size = 1,
    };
    if (spi_bus_add_device(SPI2_HOST, &device, &reader->spi) != ESP_OK) {
        fh_pn5180_close(reader);
        return false;
    }
    delay_at_least_ms(20);
    gpio_set_level(pins->rst, 1);
    delay_at_least_ms(100);
    uint32_t irq;
    if (!wait_busy(reader, 0, 500) ||
        !read_register(reader, REG_IRQ_STATUS, &irq) ||
        !(irq & (1u << 2))) {
        fh_pn5180_close(reader);
        return false;
    }
    if (!clear_irq(reader)) {
        fh_pn5180_close(reader);
        return false;
    }
    return true;
}

void fh_pn5180_close(fh_pn5180 *reader)
{
    if (!reader) return;
    if (reader->spi) {
        if (reader->rf_on) {
            const uint8_t off[2] = {CMD_RF_OFF, 0};
            command(reader, off, sizeof(off), NULL, 0);
        }
        spi_bus_remove_device(reader->spi);
    }
    if (reader->bus_open) spi_bus_free(SPI2_HOST);
    memset(reader, 0, sizeof(*reader));
}

fh_tag_io fh_pn5180_tag_io(fh_pn5180 *reader)
{
    return (fh_tag_io){reader, select_any, get_version, read4, write_page};
}
