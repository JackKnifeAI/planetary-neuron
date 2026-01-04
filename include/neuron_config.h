/**
 * Planetary Neuron - Configuration
 * TLSR8258 Resource Budget:
 *   - SRAM: 64KB total, ~40KB usable after BLE stack
 *   - Flash: 512KB, ~256KB for weights/state
 *   - CPU: 48MHz RISC, no FPU
 */

#ifndef NEURON_CONFIG_H
#define NEURON_CONFIG_H

#include <stdint.h>

namespace planetary {

// Memory budget (bytes)
constexpr uint32_t SRAM_BUDGET         = 40 * 1024;  // 40KB for neuron
constexpr uint32_t WEIGHT_SHARD_SIZE   = 4 * 1024;   // 4KB per shard
constexpr uint32_t GRADIENT_BUFFER_SIZE = 2 * 1024;  // 2KB gradient ring
constexpr uint32_t MESH_MSG_MAX_SIZE   = 380;        // BLE mesh MTU limit

// Model sharding
constexpr uint8_t  MAX_SHARDS_IN_RAM   = 4;          // 16KB for weights
constexpr uint8_t  TOTAL_MODEL_SHARDS  = 64;         // 256KB full model
constexpr uint8_t  SHARD_ROTATION_MS   = 100;        // Swap shards every 100ms

// Federated learning
constexpr float    LEARNING_RATE       = 0.001f;
constexpr uint8_t  LOCAL_EPOCHS        = 1;          // Train before sync
constexpr uint8_t  MIN_NEIGHBORS_SYNC  = 2;          // Min peers for FedAvg
constexpr uint16_t GOSSIP_INTERVAL_MS  = 5000;       // Weight broadcast period

// Hardware safety
constexpr uint8_t  MAX_CPU_DUTY_CYCLE  = 30;         // % for AI tasks
constexpr uint8_t  TEMP_THROTTLE_C     = 55;         // Throttle above this
constexpr uint8_t  TEMP_SHUTDOWN_C     = 70;         // Kill AI above this

// Scheduler timeslots (microseconds)
constexpr uint32_t BLE_GUARD_US        = 2000;       // Don't touch near BLE events
constexpr uint32_t AI_TIMESLOT_US      = 5000;       // Max AI burst

// Quantization
using weight_t = int8_t;                             // INT8 quantized
using accum_t  = int32_t;                            // Accumulator for MAC ops

}  // namespace planetary

#endif  // NEURON_CONFIG_H
