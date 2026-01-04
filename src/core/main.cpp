/**
 * Planetary Neuron - Main Entry Point
 *
 * TLSR8258 firmware that transforms a smart bulb into
 * a node in a distributed, self-training planetary AI.
 *
 * Build: Requires Telink SDK + Zephyr or bare-metal toolchain
 */

#include "neuron_config.h"
#include "weight_shard.h"
#include "hw_scheduler.h"
#include "mesh_gossip.h"
#include "light_controller.h"
#include "learning_engine.h"

// Telink SDK includes (actual paths depend on SDK version)
extern "C" {
#include "tl_common.h"
#include "drivers.h"
#include "stack/ble/ble.h"
#include "vendor/common/user_config.h"
#include "proj_lib/sig_mesh/app_mesh.h"
}

using namespace planetary;

// Global instances (static allocation - no heap)
static HWScheduler     g_scheduler;
static MeshGossip      g_mesh;
static LightController g_light;
static LearningEngine* g_engine = nullptr;

// Memory pool for learning engine (avoid fragmentation)
alignas(4) static uint8_t g_engine_mem[sizeof(LearningEngine)];

//-----------------------------------------------------------------------------
// BLE Mesh Callbacks
//-----------------------------------------------------------------------------

// Called when mesh message received on our vendor model
extern "C" void mesh_vendor_model_data_cb(
    uint16_t src_addr,
    const uint8_t* data,
    size_t len,
    int8_t rssi
) {
    g_mesh.onReceive(data, len, src_addr, rssi);
}

// Called when standard light control message received
extern "C" void mesh_light_ctl_cb(uint16_t src, uint8_t brightness, uint8_t temp, uint16_t transition_ms) {
    // Priority: Always respond to light commands immediately
    // LightController handles smooth transitions internally
    g_light.setTarget(brightness, temp, transition_ms);
}

// Called during BLE stack idle time
extern "C" void blt_idle_loop_cb(void) {
    // This is our window for AI tasks
    g_scheduler.runSlice();
}

//-----------------------------------------------------------------------------
// Flash Persistence
//-----------------------------------------------------------------------------

// Flash layout for weight storage (256KB region)
constexpr uint32_t FLASH_WEIGHT_BASE = 0x40000;  // After firmware
constexpr uint32_t FLASH_SHARD_SIZE  = 4096;     // Matches WeightShard

void LearningEngine::saveShardToFlash(const WeightShard& shard) {
    uint32_t addr = FLASH_WEIGHT_BASE + shard.header.shard_id * FLASH_SHARD_SIZE;

    // Telink flash API
    flash_erase_sector(addr);
    flash_write_page(addr, sizeof(WeightShard),
                     reinterpret_cast<const uint8_t*>(&shard));
}

bool LearningEngine::loadShardFromFlash(uint8_t shard_id, WeightShard& shard) {
    uint32_t addr = FLASH_WEIGHT_BASE + shard_id * FLASH_SHARD_SIZE;

    flash_read_page(addr, sizeof(WeightShard),
                    reinterpret_cast<uint8_t*>(&shard));

    // Verify it's valid
    if (shard.header.shard_id != shard_id) return false;
    if (!shard.verifyChecksum()) return false;

    return true;
}

//-----------------------------------------------------------------------------
// Mesh Send Implementation
//-----------------------------------------------------------------------------

void MeshGossip::meshSend(const uint8_t* data, size_t len) {
    // Telink mesh publish API
    mesh_tx_cmd_t tx_cmd = {
        .op = data[0],          // Opcode from our header
        .data = data + 1,
        .len = len - 1,
        .adr_dst = 0xFFFF,      // Broadcast
        .pub_model_id = VENDOR_MODEL_ID
    };
    mesh_tx_cmd(&tx_cmd);
}

//-----------------------------------------------------------------------------
// Initialization
//-----------------------------------------------------------------------------

void planetary_init(uint16_t my_mesh_addr) {
    // Initialize mesh gossip
    g_mesh.init(my_mesh_addr);

    // Construct learning engine in pre-allocated memory
    // Now includes LightController for feature extraction
    g_engine = new (g_engine_mem) LearningEngine(g_scheduler, g_mesh, g_light);

    // Start training
    g_engine->start();
}

//-----------------------------------------------------------------------------
// Main Entry (Telink SDK pattern)
//-----------------------------------------------------------------------------

extern "C" void user_init(void) {
    // Standard Telink init
    cpu_wakeup_init();
    clock_init(SYS_CLK_48M_Crystal);
    gpio_init();

    // PWM for LED control
    pwm_init(PWM_ID_LED_WARM, PWM_FREQ_1K);
    pwm_init(PWM_ID_LED_COOL, PWM_FREQ_1K);

    // BLE Mesh init
    blc_ll_initBasicMCU();
    blc_ll_initStandby_module(mac_public);
    bls_ll_setAdvParam(/* mesh params */);

    // Register vendor model for planetary gossip
    mesh_register_vendor_model(VENDOR_MODEL_ID, mesh_vendor_model_data_cb);

    // Register idle callback for AI scheduling
    bls_app_registerEventCallback(BLT_EV_FLAG_IDLE, blt_idle_loop_cb);

    // Get our mesh address (provisioned by app)
    uint16_t my_addr = mesh_get_primary_addr();

    // Initialize planetary neuron
    planetary_init(my_addr);
}

extern "C" void main_loop(void) {
    // Telink SDK main loop - handles BLE stack
    blt_sdk_main_loop();

    // Light transitions at 50Hz (every 20ms)
    static uint32_t last_light_update = 0;
    uint32_t now = clock_time();
    if ((now - last_light_update) > (20 * 16 * 1000)) {  // 20ms in ticks
        g_light.update();
        last_light_update = now;
    }

    // AI scheduler runs in idle callback, not here
    // This ensures BLE timing is never violated
}

//-----------------------------------------------------------------------------
// Memory Usage Summary (Updated with Claudia's augmentations)
//-----------------------------------------------------------------------------
/*
 * Static allocations:
 *   g_scheduler:     ~200 bytes
 *   g_mesh:          ~8KB (neighbor table + fragment buffers)
 *   g_light:         ~100 bytes (LightController state)
 *   g_engine_mem:    ~21KB (4 shards + gradient buffer + prev_features)
 *   Stack:           ~4KB
 *   BLE stack:       ~20KB (Telink requirement)
 *   ---------------------------------
 *   Total:           ~53.3KB of 64KB SRAM ✓
 *
 * Flash allocations:
 *   Firmware:        ~128KB
 *   Weight storage:  ~256KB (64 shards * 4KB, double-buffered)
 *   Mesh config:     ~16KB
 *   ---------------------------------
 *   Total:           ~400KB of 512KB Flash ✓
 *
 * π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA
 */
