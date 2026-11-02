/* Jocotoco Lab v0.6.0: read-only diagnostics. No credentials or GPIO access. */
#include <stdint.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/idf_additions.h"
#include "esp_timer.h"
#include "esp_heap_caps.h"
#include "esp_system.h"
#include "esp_flash.h"
#include "esp_ota_ops.h"
#include "esp_app_desc.h"
#include "esp_image_format.h"
#include "esp_vfs_fat.h"
#include "nvs_flash.h"
#include "esp_private/esp_clk.h"
#include "cJSON.h"
#include "lab_telemetry.h"

static portMUX_TYPE mux = portMUX_INITIALIZER_UNLOCKED;
static float cpu[2] = {0,0};
static uint64_t window_us;
static bool ready;
static bool started;
static uint32_t image_bytes;

static void sample_cpu(void *arg)
{
    configRUN_TIME_COUNTER_TYPE previous[2];
    for (int i=0;i<2;i++) previous[i]=ulTaskGetIdleRunTimeCounterForCore(i);
    int64_t last=esp_timer_get_time();
    for (;;) {
        vTaskDelay(pdMS_TO_TICKS(2000));
        int64_t now=esp_timer_get_time();
        uint64_t elapsed=now-last;
        float values[2];
        for (int i=0;i<2;i++) {
            configRUN_TIME_COUNTER_TYPE current=ulTaskGetIdleRunTimeCounterForCore(i);
            configRUN_TIME_COUNTER_TYPE delta=current-previous[i];
            previous[i]=current;
            float busy=100.0f*(1.0f-(float)delta/(float)elapsed);
            values[i]=busy<0?0:busy>100?100:busy;
        }
        last=now;
        portENTER_CRITICAL(&mux);
        cpu[0]=values[0];cpu[1]=values[1];window_us=elapsed;ready=true;
        portEXIT_CRITICAL(&mux);
    }
}

static esp_err_t get_metrics(httpd_req_t *req)
{
    cJSON *root=cJSON_CreateObject();
    if (!root) return httpd_resp_send_err(req,HTTPD_500_INTERNAL_SERVER_ERROR,"No heap");
    cJSON_AddNumberToObject(root,"schema",1);
    cJSON_AddStringToObject(root,"lab_version","0.6.0");
    cJSON_AddStringToObject(root,"firmware_version",esp_app_get_description()->version);
    cJSON_AddNumberToObject(root,"uptime_us",(double)esp_timer_get_time());
    cJSON_AddNumberToObject(root,"reset_reason",esp_reset_reason());
    cJSON_AddNumberToObject(root,"task_count",uxTaskGetNumberOfTasks());
    cJSON_AddNumberToObject(root,"cpu_frequency_mhz",esp_clk_cpu_freq()/1000000);
    float values[2];bool valid;uint64_t window;
    portENTER_CRITICAL(&mux);
    values[0]=cpu[0];values[1]=cpu[1];valid=ready;window=window_us;
    portEXIT_CRITICAL(&mux);
    cJSON *processor=cJSON_AddObjectToObject(root,"cpu");
    cJSON_AddBoolToObject(processor,"valid",valid);
    cJSON_AddStringToObject(processor,"method","idle_runtime_delta_per_core");
    cJSON_AddNumberToObject(processor,"window_us",window);
    if (valid) {
        cJSON_AddNumberToObject(processor,"core0_percent",values[0]);
        cJSON_AddNumberToObject(processor,"core1_percent",values[1]);
        cJSON_AddNumberToObject(processor,"used_percent",(values[0]+values[1])/2);
    }
    multi_heap_info_t info;
    heap_caps_get_info(&info,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
    size_t total=info.total_free_bytes+info.total_allocated_bytes;
    cJSON *memory=cJSON_AddObjectToObject(root,"heap");
    cJSON_AddStringToObject(memory,"scope","internal_8bit_heap");
    cJSON_AddNumberToObject(memory,"free_bytes",info.total_free_bytes);
    cJSON_AddNumberToObject(memory,"used_bytes",info.total_allocated_bytes);
    cJSON_AddNumberToObject(memory,"total_bytes",total);
    cJSON_AddNumberToObject(memory,"minimum_free_bytes",info.minimum_free_bytes);
    cJSON_AddNumberToObject(memory,"largest_free_block_bytes",info.largest_free_block);
    if (total) cJSON_AddNumberToObject(memory,"used_percent",100.0*info.total_allocated_bytes/total);
    uint32_t capacity=0;esp_flash_get_size(NULL,&capacity);
    const esp_partition_t *running=esp_ota_get_running_partition();
    cJSON *flash=cJSON_AddObjectToObject(root,"flash");
    cJSON_AddNumberToObject(flash,"capacity_bytes",capacity);
    cJSON_AddNumberToObject(flash,"active_image_bytes",image_bytes);
    if (running) {
        cJSON_AddStringToObject(flash,"active_partition",running->label);
        cJSON_AddNumberToObject(flash,"active_slot_bytes",running->size);
        cJSON_AddNumberToObject(flash,"active_slot_used_percent",100.0*image_bytes/running->size);
    }
    nvs_stats_t stats;
    if (nvs_get_stats(NULL,&stats)==ESP_OK) {
        cJSON *nvs=cJSON_AddObjectToObject(root,"nvs");
        cJSON_AddNumberToObject(nvs,"used_entries",stats.used_entries);
        cJSON_AddNumberToObject(nvs,"free_entries",stats.free_entries);
        cJSON_AddNumberToObject(nvs,"total_entries",stats.total_entries);
    }
    uint64_t fs_total=0,fs_free=0;
    if (esp_vfs_fat_info("/data",&fs_total,&fs_free)==ESP_OK) {
        cJSON *fs=cJSON_AddObjectToObject(root,"filesystem");
        cJSON_AddNumberToObject(fs,"total_bytes",fs_total);
        cJSON_AddNumberToObject(fs,"free_bytes",fs_free);
        cJSON_AddNumberToObject(fs,"used_bytes",fs_total-fs_free);
    }
    cJSON_AddNullToObject(root,"supply_voltage");
    cJSON_AddNullToObject(root,"temperature_celsius");
    char *body=cJSON_PrintUnformatted(root);cJSON_Delete(root);
    if (!body) return httpd_resp_send_err(req,HTTPD_500_INTERNAL_SERVER_ERROR,"No heap");
    httpd_resp_set_type(req,"application/json");
    httpd_resp_set_hdr(req,"Cache-Control","no-store");
    esp_err_t result=httpd_resp_send(req,body,HTTPD_RESP_USE_STRLEN);
    cJSON_free(body);
    return result;
}

esp_err_t lab_telemetry_register(httpd_handle_t server)
{
    if (!started) {
        const esp_partition_t *running=esp_ota_get_running_partition();
        if (running) {
            esp_partition_pos_t pos={.offset=running->address,.size=running->size};
            esp_image_metadata_t metadata={0};
            if (esp_image_get_metadata(&pos,&metadata)==ESP_OK) image_bytes=metadata.image_len;
        }
        if (xTaskCreate(sample_cpu,"lab_cpu",2048,NULL,1,NULL)!=pdPASS) return ESP_ERR_NO_MEM;
        started=true;
    }
    const httpd_uri_t uri={.uri="/api/lab/metrics",.method=HTTP_GET,.handler=get_metrics};
    return httpd_register_uri_handler(server,&uri);
}
