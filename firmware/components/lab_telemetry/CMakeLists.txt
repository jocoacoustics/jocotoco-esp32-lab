idf_component_register(SRCS "lab_telemetry.c" INCLUDE_DIRS "include"
    PRIV_REQUIRES esp_http_server esp_timer esp_hw_support heap nvs_flash
                  app_update esp_app_format spi_flash bootloader_support fatfs json)
