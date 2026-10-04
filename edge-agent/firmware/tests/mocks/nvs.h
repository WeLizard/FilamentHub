#ifndef TEST_NVS_H
#define TEST_NVS_H

#include <stddef.h>

typedef int nvs_handle_t;
typedef int esp_err_t;
#define ESP_OK 0
#define NVS_READONLY 0
#define NVS_READWRITE 1

esp_err_t nvs_open(const char *name, int mode, nvs_handle_t *handle);
esp_err_t nvs_get_blob(nvs_handle_t handle, const char *key, void *data, size_t *length);
esp_err_t nvs_set_blob(nvs_handle_t handle, const char *key, const void *data, size_t length);
esp_err_t nvs_commit(nvs_handle_t handle);
void nvs_close(nvs_handle_t handle);

#endif
