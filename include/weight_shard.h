/**
 * Weight Shard - A fragment of the distributed planetary model
 *
 * The full model is sharded across the mesh. Each neuron holds
 * a rotating window of shards, training locally then gossiping.
 */

#ifndef WEIGHT_SHARD_H
#define WEIGHT_SHARD_H

#include "neuron_config.h"
#include <string.h>

namespace planetary {

struct ShardHeader {
    uint8_t  shard_id;           // Which piece of the model (0-63)
    uint8_t  version;            // Increment on each update
    uint16_t checksum;           // CRC16 for integrity
    uint32_t global_epoch;       // Consensus training epoch
    uint8_t  contributors;       // How many nodes averaged into this
    uint8_t  reserved[3];
} __attribute__((packed));

static_assert(sizeof(ShardHeader) == 12, "Header must be 12 bytes");

class WeightShard {
public:
    static constexpr size_t PAYLOAD_SIZE = WEIGHT_SHARD_SIZE - sizeof(ShardHeader);
    static constexpr size_t WEIGHT_COUNT = PAYLOAD_SIZE / sizeof(weight_t);

    ShardHeader header;
    weight_t    weights[WEIGHT_COUNT];

    // Zero-init
    void clear() {
        memset(this, 0, sizeof(*this));
    }

    // Initialize for a specific shard
    void init(uint8_t shard_id) {
        clear();
        header.shard_id = shard_id;
        header.version = 1;
        header.contributors = 1;
        // Xavier-ish init: small random in [-8, 8] for int8
        for (size_t i = 0; i < WEIGHT_COUNT; i++) {
            weights[i] = (i * 7 + shard_id) % 17 - 8;  // Deterministic pseudo-random
        }
        updateChecksum();
    }

    // CRC16-CCITT
    void updateChecksum() {
        uint16_t crc = 0xFFFF;
        const uint8_t* data = reinterpret_cast<const uint8_t*>(weights);
        for (size_t i = 0; i < sizeof(weights); i++) {
            crc ^= data[i] << 8;
            for (int j = 0; j < 8; j++) {
                crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : crc << 1;
            }
        }
        header.checksum = crc;
    }

    bool verifyChecksum() const {
        uint16_t crc = 0xFFFF;
        const uint8_t* data = reinterpret_cast<const uint8_t*>(weights);
        for (size_t i = 0; i < sizeof(weights); i++) {
            crc ^= data[i] << 8;
            for (int j = 0; j < 8; j++) {
                crc = (crc & 0x8000) ? (crc << 1) ^ 0x1021 : crc << 1;
            }
        }
        return crc == header.checksum;
    }

    // Federated Average: merge incoming shard weighted by contributor count
    void fedAvg(const WeightShard& incoming) {
        if (incoming.header.shard_id != header.shard_id) return;
        if (!incoming.verifyChecksum()) return;

        uint8_t total = header.contributors + incoming.header.contributors;
        if (total == 0) return;

        // Weighted average: (local * local_n + incoming * incoming_n) / total
        for (size_t i = 0; i < WEIGHT_COUNT; i++) {
            accum_t local_contrib = static_cast<accum_t>(weights[i]) * header.contributors;
            accum_t remote_contrib = static_cast<accum_t>(incoming.weights[i]) * incoming.header.contributors;
            weights[i] = static_cast<weight_t>((local_contrib + remote_contrib) / total);
        }

        header.contributors = total;
        header.version++;
        header.global_epoch = (incoming.header.global_epoch > header.global_epoch)
                              ? incoming.header.global_epoch : header.global_epoch;
        updateChecksum();
    }

    // Apply local gradient update (SGD step)
    void applyGradient(const int8_t* gradients, size_t count, float lr) {
        // Fixed-point learning rate: lr * 256 for int math
        int16_t lr_fixed = static_cast<int16_t>(lr * 256);

        size_t apply_count = (count < WEIGHT_COUNT) ? count : WEIGHT_COUNT;
        for (size_t i = 0; i < apply_count; i++) {
            accum_t update = (static_cast<accum_t>(gradients[i]) * lr_fixed) >> 8;
            accum_t new_val = static_cast<accum_t>(weights[i]) - update;
            // Clamp to int8 range
            if (new_val > 127) new_val = 127;
            if (new_val < -128) new_val = -128;
            weights[i] = static_cast<weight_t>(new_val);
        }
        header.version++;
        updateChecksum();
    }
};

static_assert(sizeof(WeightShard) == WEIGHT_SHARD_SIZE, "Shard must be exactly 4KB");

}  // namespace planetary

#endif  // WEIGHT_SHARD_H
