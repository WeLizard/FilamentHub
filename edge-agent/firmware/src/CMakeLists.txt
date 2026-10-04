idf_component_register(SRCS "main.c" "core.c" "config.c" "cloud.c" "bambu.c" "report.c" "ams.c" "ams_journal.c" "ams_journal_flash.c" "snapshot.c" "ntag.c" "pn5180_hal.c" "nfc_console.c" INCLUDE_DIRS "."
    REQUIRES esp_wifi esp_event esp_netif nvs_flash esp_http_client mqtt json
             mbedtls esp_timer esp_driver_usb_serial_jtag esp_driver_spi
             esp_driver_gpio esp_system esp_partition)
