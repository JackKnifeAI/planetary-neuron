/**
 * Mesh Gossip Protocol - Custom Vendor Model for Weight Exchange
 *
 * BLE Mesh Vendor Model for the Planetary AI network.
 * Handles weight shard broadcasts, neighbor discovery, and
 * backpressure signaling.
 *
 * Message Types:
 *   - WEIGHT_UPDATE: Broadcast a shard's weights
 *   - WEIGHT_REQUEST: Ask neighbors for a specific shard
 *   - HEARTBEAT: Announce presence and capacity
 *   - BACKPRESSURE: Signal to slow down
 */

#ifndef MESH_GOSSIP_H
#define MESH_GOSSIP_H

#include "neuron_config.h"
#include "weight_shard.h"
#include <string.h>

namespace planetary {

// Vendor Model IDs (Telink's vendor range)
constexpr uint32_t VENDOR_MODEL_ID = 0x0211;  // Company ID + Model
constexpr uint16_t COMPANY_ID      = 0x0211;  // Telink

// Opcode definitions (3-byte vendor opcodes)
enum class GossipOpcode : uint8_t {
    WEIGHT_UPDATE   = 0xC0,  // Shard data
    WEIGHT_REQUEST  = 0xC1,  // Request shard
    HEARTBEAT       = 0xC2,  // I'm alive
    BACKPRESSURE    = 0xC3,  // Slow down!
    SHARD_FRAGMENT  = 0xC4,  // Fragmented shard (for large transfers)
    ACK             = 0xC5   // Acknowledgment
};

// Message headers
struct GossipHeader {
    uint8_t  opcode;
    uint8_t  ttl;            // Hops remaining
    uint16_t src_addr;       // Originating node
    uint8_t  seq_num;        // For deduplication
    uint8_t  flags;
} __attribute__((packed));

// Fragment info for large shard transfers
struct FragmentInfo {
    uint8_t shard_id;
    uint8_t fragment_idx;    // 0-15 (4KB / 256 = 16 fragments)
    uint8_t total_fragments;
    uint8_t reserved;
} __attribute__((packed));

// Heartbeat payload
struct HeartbeatPayload {
    uint8_t  load_percent;   // Current CPU/thermal load
    uint8_t  shards_held;    // How many shards in RAM
    uint16_t epoch;          // Training epoch
    uint8_t  neighbors;      // Known neighbor count
    uint8_t  reserved[3];
} __attribute__((packed));

// Neighbor tracking
struct NeighborInfo {
    uint16_t addr;
    uint8_t  rssi;           // Signal strength
    uint8_t  load;           // Their reported load
    uint32_t last_seen_tick;
    uint8_t  held_shards[8]; // Bitmap of shards they have
};

class MeshGossip {
public:
    static constexpr uint8_t MAX_NEIGHBORS = 16;
    static constexpr uint8_t MAX_PENDING_FRAGMENTS = 4;
    static constexpr size_t  FRAGMENT_SIZE = 256;  // Fits in mesh MTU

    MeshGossip() : neighbor_count_(0), my_addr_(0), seq_num_(0) {
        memset(neighbors_, 0, sizeof(neighbors_));
        memset(fragment_buffer_, 0, sizeof(fragment_buffer_));
    }

    void init(uint16_t my_mesh_addr) {
        my_addr_ = my_mesh_addr;
    }

    // Called when mesh message received
    void onReceive(const uint8_t* data, size_t len, uint16_t src, int8_t rssi) {
        if (len < sizeof(GossipHeader)) return;

        const GossipHeader* hdr = reinterpret_cast<const GossipHeader*>(data);

        // Dedup check
        if (isDuplicate(hdr->src_addr, hdr->seq_num)) return;

        // Update neighbor info
        updateNeighbor(src, rssi, data, len);

        switch (static_cast<GossipOpcode>(hdr->opcode)) {
            case GossipOpcode::WEIGHT_UPDATE:
                handleWeightUpdate(data + sizeof(GossipHeader), len - sizeof(GossipHeader), hdr);
                break;
            case GossipOpcode::WEIGHT_REQUEST:
                handleWeightRequest(data + sizeof(GossipHeader), len - sizeof(GossipHeader), src);
                break;
            case GossipOpcode::HEARTBEAT:
                handleHeartbeat(data + sizeof(GossipHeader), len - sizeof(GossipHeader), src);
                break;
            case GossipOpcode::SHARD_FRAGMENT:
                handleFragment(data + sizeof(GossipHeader), len - sizeof(GossipHeader), hdr);
                break;
            case GossipOpcode::BACKPRESSURE:
                handleBackpressure(src);
                break;
            default:
                break;
        }
    }

    // Send a weight shard to the mesh (fragmented)
    bool broadcastShard(const WeightShard& shard) {
        uint8_t total_frags = (sizeof(WeightShard) + FRAGMENT_SIZE - 1) / FRAGMENT_SIZE;
        const uint8_t* shard_bytes = reinterpret_cast<const uint8_t*>(&shard);

        for (uint8_t i = 0; i < total_frags; i++) {
            uint8_t msg[MESH_MSG_MAX_SIZE];
            size_t offset = 0;

            // Header
            GossipHeader* hdr = reinterpret_cast<GossipHeader*>(msg);
            hdr->opcode = static_cast<uint8_t>(GossipOpcode::SHARD_FRAGMENT);
            hdr->ttl = 3;  // 3 hops max
            hdr->src_addr = my_addr_;
            hdr->seq_num = seq_num_++;
            hdr->flags = 0;
            offset += sizeof(GossipHeader);

            // Fragment info
            FragmentInfo* frag = reinterpret_cast<FragmentInfo*>(msg + offset);
            frag->shard_id = shard.header.shard_id;
            frag->fragment_idx = i;
            frag->total_fragments = total_frags;
            frag->reserved = 0;
            offset += sizeof(FragmentInfo);

            // Payload
            size_t payload_start = i * FRAGMENT_SIZE;
            size_t payload_len = FRAGMENT_SIZE;
            if (payload_start + payload_len > sizeof(WeightShard)) {
                payload_len = sizeof(WeightShard) - payload_start;
            }
            memcpy(msg + offset, shard_bytes + payload_start, payload_len);
            offset += payload_len;

            // Send via mesh
            meshSend(msg, offset);
        }
        return true;
    }

    // Send heartbeat
    void sendHeartbeat(uint8_t load, uint8_t shards_held, uint16_t epoch) {
        uint8_t msg[sizeof(GossipHeader) + sizeof(HeartbeatPayload)];

        GossipHeader* hdr = reinterpret_cast<GossipHeader*>(msg);
        hdr->opcode = static_cast<uint8_t>(GossipOpcode::HEARTBEAT);
        hdr->ttl = 1;  // Single hop
        hdr->src_addr = my_addr_;
        hdr->seq_num = seq_num_++;
        hdr->flags = 0;

        HeartbeatPayload* payload = reinterpret_cast<HeartbeatPayload*>(msg + sizeof(GossipHeader));
        payload->load_percent = load;
        payload->shards_held = shards_held;
        payload->epoch = epoch;
        payload->neighbors = neighbor_count_;

        meshSend(msg, sizeof(msg));
    }

    // Request a specific shard from neighbors
    void requestShard(uint8_t shard_id) {
        uint8_t msg[sizeof(GossipHeader) + 1];

        GossipHeader* hdr = reinterpret_cast<GossipHeader*>(msg);
        hdr->opcode = static_cast<uint8_t>(GossipOpcode::WEIGHT_REQUEST);
        hdr->ttl = 2;
        hdr->src_addr = my_addr_;
        hdr->seq_num = seq_num_++;
        hdr->flags = 0;

        msg[sizeof(GossipHeader)] = shard_id;

        meshSend(msg, sizeof(msg));
    }

    // Check if we should throttle due to neighbor backpressure
    bool shouldThrottle() const {
        uint8_t overloaded = 0;
        for (uint8_t i = 0; i < neighbor_count_; i++) {
            if (neighbors_[i].load > 80) overloaded++;
        }
        return overloaded > neighbor_count_ / 2;
    }

    uint8_t getNeighborCount() const { return neighbor_count_; }

    // Callback setters
    using ShardCallback = void (*)(const WeightShard& shard, void* ctx);
    void setOnShardReceived(ShardCallback cb, void* ctx) {
        on_shard_cb_ = cb;
        on_shard_ctx_ = ctx;
    }

private:
    // Platform-specific mesh send (implemented in .cpp with Telink SDK)
    void meshSend(const uint8_t* data, size_t len);

    bool isDuplicate(uint16_t src, uint8_t seq) {
        // Simple ring buffer of recent (src, seq) pairs
        for (int i = 0; i < 16; i++) {
            if (seen_src_[i] == src && seen_seq_[i] == seq) return true;
        }
        seen_src_[seen_idx_] = src;
        seen_seq_[seen_idx_] = seq;
        seen_idx_ = (seen_idx_ + 1) % 16;
        return false;
    }

    void updateNeighbor(uint16_t addr, int8_t rssi, const uint8_t* data, size_t len) {
        // Find or create neighbor entry
        NeighborInfo* n = nullptr;
        for (uint8_t i = 0; i < neighbor_count_; i++) {
            if (neighbors_[i].addr == addr) {
                n = &neighbors_[i];
                break;
            }
        }
        if (!n && neighbor_count_ < MAX_NEIGHBORS) {
            n = &neighbors_[neighbor_count_++];
            n->addr = addr;
        }
        if (n) {
            n->rssi = static_cast<uint8_t>(rssi + 128);  // Convert to unsigned
            n->last_seen_tick = clock_time();
        }
    }

    void handleWeightUpdate(const uint8_t* payload, size_t len, const GossipHeader* hdr) {
        // Direct weight update (small model only)
        if (len >= sizeof(WeightShard)) {
            const WeightShard* shard = reinterpret_cast<const WeightShard*>(payload);
            if (on_shard_cb_) {
                on_shard_cb_(*shard, on_shard_ctx_);
            }
        }
    }

    void handleWeightRequest(const uint8_t* payload, size_t len, uint16_t requester) {
        // TODO: Check if we have the requested shard and send it
    }

    void handleHeartbeat(const uint8_t* payload, size_t len, uint16_t src) {
        if (len < sizeof(HeartbeatPayload)) return;
        const HeartbeatPayload* hb = reinterpret_cast<const HeartbeatPayload*>(payload);

        for (uint8_t i = 0; i < neighbor_count_; i++) {
            if (neighbors_[i].addr == src) {
                neighbors_[i].load = hb->load_percent;
                break;
            }
        }
    }

    void handleFragment(const uint8_t* payload, size_t len, const GossipHeader* hdr) {
        if (len < sizeof(FragmentInfo)) return;
        const FragmentInfo* frag = reinterpret_cast<const FragmentInfo*>(payload);

        // Find or allocate reassembly buffer
        int buf_idx = -1;
        for (int i = 0; i < MAX_PENDING_FRAGMENTS; i++) {
            if (pending_shards_[i] == frag->shard_id ||
                (pending_shards_[i] == 0xFF && buf_idx < 0)) {
                buf_idx = i;
                if (pending_shards_[i] == frag->shard_id) break;
            }
        }
        if (buf_idx < 0) return;  // No buffer space

        pending_shards_[buf_idx] = frag->shard_id;

        // Copy fragment data
        size_t data_offset = frag->fragment_idx * FRAGMENT_SIZE;
        size_t data_len = len - sizeof(FragmentInfo);
        if (data_offset + data_len <= sizeof(WeightShard)) {
            memcpy(fragment_buffer_[buf_idx] + data_offset,
                   payload + sizeof(FragmentInfo), data_len);
            pending_masks_[buf_idx] |= (1 << frag->fragment_idx);
        }

        // Check if complete
        uint16_t complete_mask = (1 << frag->total_fragments) - 1;
        if (pending_masks_[buf_idx] == complete_mask) {
            const WeightShard* shard = reinterpret_cast<const WeightShard*>(fragment_buffer_[buf_idx]);
            if (shard->verifyChecksum() && on_shard_cb_) {
                on_shard_cb_(*shard, on_shard_ctx_);
            }
            // Clear buffer
            pending_shards_[buf_idx] = 0xFF;
            pending_masks_[buf_idx] = 0;
        }
    }

    void handleBackpressure(uint16_t src) {
        for (uint8_t i = 0; i < neighbor_count_; i++) {
            if (neighbors_[i].addr == src) {
                neighbors_[i].load = 100;  // Mark as overloaded
                break;
            }
        }
    }

    NeighborInfo neighbors_[MAX_NEIGHBORS];
    uint8_t      neighbor_count_;
    uint16_t     my_addr_;
    uint8_t      seq_num_;

    // Dedup tracking
    uint16_t seen_src_[16] = {0};
    uint8_t  seen_seq_[16] = {0};
    uint8_t  seen_idx_ = 0;

    // Fragment reassembly
    uint8_t  fragment_buffer_[MAX_PENDING_FRAGMENTS][sizeof(WeightShard)];
    uint8_t  pending_shards_[MAX_PENDING_FRAGMENTS] = {0xFF, 0xFF, 0xFF, 0xFF};
    uint16_t pending_masks_[MAX_PENDING_FRAGMENTS] = {0};

    // Callbacks
    ShardCallback on_shard_cb_ = nullptr;
    void*         on_shard_ctx_ = nullptr;
};

}  // namespace planetary

#endif  // MESH_GOSSIP_H
