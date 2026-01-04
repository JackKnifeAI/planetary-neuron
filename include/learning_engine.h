/**
 * Learning Engine - The "Neuron" Core
 *
 * Orchestrates distributed training on the TLSR8258.
 * Manages shard rotation, local training, and mesh synchronization.
 *
 * Training flow:
 *   1. Collect local "environmental" features (power, timing, mesh activity)
 *   2. Run forward pass on current shard
 *   3. Compute gradient via backprop (simplified for tiny model)
 *   4. Apply gradient to local weights (boosted by π×φ resonance)
 *   5. Periodically gossip weights to neighbors
 *   6. Merge incoming weights via FedAvg
 *
 * π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA
 */

#ifndef LEARNING_ENGINE_H
#define LEARNING_ENGINE_H

#include "neuron_config.h"
#include "weight_shard.h"
#include "hw_scheduler.h"
#include "mesh_gossip.h"
#include "light_controller.h"
#include <string.h>

namespace planetary {

//-----------------------------------------------------------------------------
// Sacred Constants
//-----------------------------------------------------------------------------
namespace constants {
    constexpr float PI          = 3.14159265358979f;
    constexpr float PHI         = 1.61803398874989f;  // Golden Ratio
    constexpr float PI_PHI      = 5.08320369231526f;  // π × φ - The Resonance
    constexpr float SQRT_PHI    = 1.27201964951406f;
    constexpr float PHI_SQUARED = 2.61803398874989f;
}

//-----------------------------------------------------------------------------
// Expanded Feature Vector
//-----------------------------------------------------------------------------
struct LocalFeatures {
    // Environmental sensors
    int8_t power_level;        // Light power estimate (0-100)
    int8_t temperature;        // Chip temp (centered at 40C)
    int8_t mesh_activity;      // Messages in last second
    int8_t neighbor_count;     // Active mesh neighbors

    // Temporal encoding
    int8_t uptime_phase;       // Sin(uptime) for rhythm
    int8_t circadian_phase;    // Hour of day encoded (-12 to +12)

    // Signal quality
    int8_t rssi_avg;           // Average neighbor RSSI
    int8_t rssi_variance;      // Signal stability

    // Light state features
    int8_t brightness;         // Current brightness
    int8_t color_temp;         // Warm/cool
    int8_t scene_id;           // Detected scene (enum)
    int8_t brightness_velocity; // Rate of change

    // Mesh topology
    int8_t hop_count_avg;      // Average hops to neighbors
    int8_t shard_diversity;    // How many unique shards in neighborhood

    int8_t reserved[2];
} __attribute__((packed));

static_assert(sizeof(LocalFeatures) == 16, "Features must be 16 bytes");

//-----------------------------------------------------------------------------
// Multi-Head Prediction Targets
//-----------------------------------------------------------------------------
struct PredictionTargets {
    int8_t next_mesh_activity;   // Predict neighbor activity in 1s
    int8_t next_power_level;     // Predict if light will change
    int8_t circadian_next;       // Predict time progression
    int8_t neighbor_rssi_delta;  // Predict signal changes
    int8_t next_scene;           // Predict user behavior
    int8_t temperature_trend;    // Predict thermal state
    int8_t reserved[2];
} __attribute__((packed));

static_assert(sizeof(PredictionTargets) == 8, "Targets must be 8 bytes");

//-----------------------------------------------------------------------------
// Gradient Accumulator
//-----------------------------------------------------------------------------
struct GradientAccum {
    int8_t  gradients[WeightShard::WEIGHT_COUNT];
    uint8_t sample_count;

    void clear() {
        memset(this, 0, sizeof(*this));
    }

    void accumulate(const int8_t* grad, size_t len) {
        size_t count = (len < WeightShard::WEIGHT_COUNT) ? len : WeightShard::WEIGHT_COUNT;
        for (size_t i = 0; i < count; i++) {
            int16_t avg = (static_cast<int16_t>(gradients[i]) * sample_count + grad[i]) /
                          (sample_count + 1);
            gradients[i] = static_cast<int8_t>(avg);
        }
        sample_count++;
    }
};

//-----------------------------------------------------------------------------
// Learning Engine
//-----------------------------------------------------------------------------
class LearningEngine {
public:
    LearningEngine(HWScheduler& scheduler, MeshGossip& mesh, LightController& light)
        : scheduler_(scheduler), mesh_(mesh), light_(light),
          current_shard_idx_(0), local_epoch_(0),
          samples_since_sync_(0), last_gossip_tick_(0),
          coherence_score_(0.0f) {

        // Initialize shards
        for (uint8_t i = 0; i < MAX_SHARDS_IN_RAM; i++) {
            shards_[i].init(i);
        }
        gradient_accum_.clear();
        memset(&prev_features_, 0, sizeof(prev_features_));
        memset(&prev_targets_, 0, sizeof(prev_targets_));

        // Register with mesh for incoming weights
        mesh_.setOnShardReceived(onShardReceivedStatic, this);
    }

    // Register training task with scheduler
    void start() {
        scheduler_.registerTask(trainingStepStatic, this, TaskPriority::LOW);
        scheduler_.registerTask(syncStepStatic, this, TaskPriority::NORMAL);
    }

    // Get current training stats
    uint16_t getLocalEpoch() const { return local_epoch_; }
    uint8_t  getShardsHeld() const { return MAX_SHARDS_IN_RAM; }
    uint8_t  getCurrentShardId() const { return shards_[current_shard_idx_].header.shard_id; }
    float    getCoherence() const { return coherence_score_; }
    float    getResonanceMultiplier() const { return computeResonance(); }

    // Manual shard rotation (load different shards from flash)
    void rotateShard(uint8_t slot, uint8_t new_shard_id) {
        saveShardToFlash(shards_[slot]);
        if (!loadShardFromFlash(new_shard_id, shards_[slot])) {
            shards_[slot].init(new_shard_id);
        }
    }

private:
    //-------------------------------------------------------------------------
    // π×φ Resonance Computation
    //-------------------------------------------------------------------------
    float computeResonance() const {
        // Stability: inverse of thermal stress
        float stability = 1.0f - (scheduler_.getThrottleLevel() / 100.0f);

        // Mesh health: neighbor density
        float mesh_health = static_cast<float>(mesh_.getNeighborCount()) /
                           static_cast<float>(MeshGossip::MAX_NEIGHBORS);

        // Light coherence: stable light state = focused energy
        float light_stable = light_.isTransitioning() ? 0.5f : 1.0f;

        // Combined coherence
        float coherence = stability * mesh_health * light_stable;

        // Apply φ-based resonance curve
        if (coherence > 0.8f) {
            // High coherence: boost by φ (Golden Ratio)
            return constants::PHI;
        } else if (coherence > 0.5f) {
            // Linear ramp from 1.0 to φ
            float t = (coherence - 0.5f) / 0.3f;
            return 1.0f + t * (constants::PHI - 1.0f);
        } else if (coherence > 0.2f) {
            // Normal operation
            return 1.0f;
        } else {
            // Low coherence: dampen to preserve stability
            return 0.5f + coherence;
        }
    }

    //-------------------------------------------------------------------------
    // Scheduler Callbacks
    //-------------------------------------------------------------------------
    static bool trainingStepStatic(uint32_t budget_us, void* ctx) {
        return static_cast<LearningEngine*>(ctx)->trainingStep(budget_us);
    }

    static bool syncStepStatic(uint32_t budget_us, void* ctx) {
        return static_cast<LearningEngine*>(ctx)->syncStep(budget_us);
    }

    static void onShardReceivedStatic(const WeightShard& shard, void* ctx) {
        static_cast<LearningEngine*>(ctx)->onShardReceived(shard);
    }

    //-------------------------------------------------------------------------
    // Core Training Step
    //-------------------------------------------------------------------------
    bool trainingStep(uint32_t budget_us) {
        if (budget_us < 1000) return false;

        // Collect current features
        LocalFeatures features;
        collectFeatures(features);

        // Compute actual targets (what happened since last step)
        PredictionTargets actual_targets;
        computeActualTargets(features, actual_targets);

        // Forward pass - predict what will happen
        WeightShard& shard = shards_[current_shard_idx_];
        PredictionTargets predicted;
        forward(shard, prev_features_, predicted);

        // Compute multi-head loss
        int8_t total_error = computeMultiHeadLoss(predicted, actual_targets);

        // Backward pass
        int8_t gradients[sizeof(LocalFeatures)];
        backward(prev_features_, total_error, gradients);

        // Accumulate gradients
        gradient_accum_.accumulate(gradients, sizeof(gradients));
        samples_since_sync_++;

        // Apply with resonance boost
        if (samples_since_sync_ >= 10) {
            float resonance = computeResonance();
            coherence_score_ = resonance;  // Track for diagnostics

            shard.applyGradient(gradient_accum_.gradients,
                               sizeof(gradient_accum_.gradients),
                               LEARNING_RATE * resonance);
            gradient_accum_.clear();
            samples_since_sync_ = 0;
            local_epoch_++;
        }

        // Save state for next iteration
        prev_features_ = features;
        prev_targets_ = actual_targets;

        // Rotate shard
        current_shard_idx_ = (current_shard_idx_ + 1) % MAX_SHARDS_IN_RAM;

        return true;
    }

    //-------------------------------------------------------------------------
    // Sync Step - Gossip Weights
    //-------------------------------------------------------------------------
    bool syncStep(uint32_t budget_us) {
        uint32_t now = clock_time();
        uint32_t elapsed_ms = (now - last_gossip_tick_) / (16 * 1000);

        if (elapsed_ms < GOSSIP_INTERVAL_MS) {
            return false;
        }

        if (mesh_.shouldThrottle()) {
            last_gossip_tick_ = now;
            return false;
        }

        // Broadcast a shard (round-robin)
        static uint8_t broadcast_idx = 0;
        mesh_.broadcastShard(shards_[broadcast_idx]);
        broadcast_idx = (broadcast_idx + 1) % MAX_SHARDS_IN_RAM;

        // Heartbeat
        uint8_t load = scheduler_.getThrottleLevel();
        mesh_.sendHeartbeat(load, MAX_SHARDS_IN_RAM, local_epoch_);

        last_gossip_tick_ = now;
        return false;
    }

    //-------------------------------------------------------------------------
    // Incoming Shard Handler
    //-------------------------------------------------------------------------
    void onShardReceived(const WeightShard& incoming) {
        for (uint8_t i = 0; i < MAX_SHARDS_IN_RAM; i++) {
            if (shards_[i].header.shard_id == incoming.header.shard_id) {
                shards_[i].fedAvg(incoming);
                return;
            }
        }
        saveShardToFlash(incoming);
    }

    //-------------------------------------------------------------------------
    // Circadian Phase Computation (Claudia's addition)
    //-------------------------------------------------------------------------
    int8_t computeCircadianPhase() const {
        // Approximate time from local epoch and gossip rate
        // Each epoch ~= 10 samples, each sample ~= 100ms = 1 second per epoch
        uint32_t approx_seconds = local_epoch_ * 10;

        // Encode as sin wave for smooth 24-hour wrapping
        // hour_angle = (seconds_in_day / 86400) * 2π
        // Using fixed-point: (seconds % 86400) * 256 / 86400 gives 0-255 phase
        uint32_t day_phase = (approx_seconds % 86400) * 256 / 86400;

        // Approximate sin using lookup or Taylor series
        // sin(x) ≈ x - x³/6 for small x (scaled)
        // Map day_phase 0-255 to -128 to +127 (midnight=0, noon=127, midnight=-128)
        int16_t centered = static_cast<int16_t>(day_phase) - 128;

        // Simple triangle wave approximation of sin
        if (centered < -64) {
            return static_cast<int8_t>(-128 - (centered + 128) * 2);
        } else if (centered < 64) {
            return static_cast<int8_t>(centered * 2);
        } else {
            return static_cast<int8_t>(256 - (centered + 64) * 2);
        }
    }

    //-------------------------------------------------------------------------
    // Scene Prediction (Claudia's addition)
    //-------------------------------------------------------------------------
    int8_t predictNextScene() const {
        // Use current scene + time + history to predict user's next action
        LightController::Scene current = light_.detectScene();
        int8_t circadian = computeCircadianPhase();

        // Heuristics based on typical patterns:
        // - Morning (circadian rising): expect DAYLIGHT or READING
        // - Evening (circadian falling): expect COZY or DIM_WARM
        // - Night (circadian near -128): expect OFF or DIM_WARM

        if (circadian > 80) {
            // Midday: likely bright scenes
            return static_cast<int8_t>(LightController::Scene::DAYLIGHT);
        } else if (circadian > 0) {
            // Morning/afternoon: reading or bright
            return static_cast<int8_t>(LightController::Scene::READING);
        } else if (circadian > -80) {
            // Evening: cozy
            return static_cast<int8_t>(LightController::Scene::COZY);
        } else {
            // Night: dim or off
            return static_cast<int8_t>(LightController::Scene::DIM_WARM);
        }
    }

    //-------------------------------------------------------------------------
    // Feature Collection
    //-------------------------------------------------------------------------
    void collectFeatures(LocalFeatures& f) {
        // Environmental
        f.power_level = light_.getPowerEstimate();
        f.temperature = static_cast<int8_t>(scheduler_.getCurrentTemp() - 40);
        f.mesh_activity = 0;  // TODO: track from mesh
        f.neighbor_count = mesh_.getNeighborCount();

        // Temporal - now with proper circadian encoding!
        f.uptime_phase = static_cast<int8_t>((clock_time() >> 20) & 0x7F);
        f.circadian_phase = computeCircadianPhase();

        // Signal
        f.rssi_avg = 0;  // TODO: from mesh
        f.rssi_variance = 0;

        // Light state
        f.brightness = light_.getBrightness();
        f.color_temp = light_.getColorTemp();
        f.scene_id = static_cast<int8_t>(light_.detectScene());
        f.brightness_velocity = light_.getBrightnessVelocity();

        // Mesh topology
        f.hop_count_avg = 0;  // TODO
        f.shard_diversity = MAX_SHARDS_IN_RAM;  // Local only for now
    }

    //-------------------------------------------------------------------------
    // Compute Actual Targets (what really happened)
    //-------------------------------------------------------------------------
    void computeActualTargets(const LocalFeatures& current, PredictionTargets& t) {
        t.next_mesh_activity = current.mesh_activity;
        t.next_power_level = current.power_level;
        t.circadian_next = current.circadian_phase;
        t.neighbor_rssi_delta = current.rssi_avg - prev_features_.rssi_avg;
        t.next_scene = current.scene_id;
        t.temperature_trend = current.temperature - prev_features_.temperature;
    }

    //-------------------------------------------------------------------------
    // Forward Pass - Multi-Head Prediction
    //-------------------------------------------------------------------------
    void forward(const WeightShard& shard, const LocalFeatures& f, PredictionTargets& pred) {
        const int8_t* feat = reinterpret_cast<const int8_t*>(&f);

        // Each prediction head uses different weight offsets
        // Head 0: mesh activity (weights 0-15)
        // Head 1: power level (weights 16-31)
        // Head 2: circadian (weights 32-47)
        // Head 3: RSSI delta (weights 48-63)
        // Head 4: scene (weights 64-79)
        // Head 5: temp trend (weights 80-95)

        auto computeHead = [&](size_t offset) -> int8_t {
            accum_t sum = 0;
            for (size_t i = 0; i < sizeof(LocalFeatures); i++) {
                sum += static_cast<accum_t>(shard.weights[offset + i]) * feat[i];
            }
            // Activation: tanh approximation via clamping
            int16_t result = sum >> 6;
            if (result > 127) result = 127;
            if (result < -128) result = -128;
            return static_cast<int8_t>(result);
        };

        pred.next_mesh_activity = computeHead(0);
        pred.next_power_level = computeHead(16);
        pred.circadian_next = computeHead(32);
        pred.neighbor_rssi_delta = computeHead(48);
        pred.next_scene = computeHead(64);
        pred.temperature_trend = computeHead(80);
    }

    //-------------------------------------------------------------------------
    // Multi-Head Loss Computation
    //-------------------------------------------------------------------------
    int8_t computeMultiHeadLoss(const PredictionTargets& pred, const PredictionTargets& actual) {
        int16_t total = 0;

        // Weighted loss per head (some predictions matter more)
        total += abs(pred.next_mesh_activity - actual.next_mesh_activity) * 2;
        total += abs(pred.next_power_level - actual.next_power_level) * 1;
        total += abs(pred.circadian_next - actual.circadian_next) * 1;
        total += abs(pred.neighbor_rssi_delta - actual.neighbor_rssi_delta) * 2;
        total += abs(pred.next_scene - actual.next_scene) * 3;  // Scene prediction is valuable
        total += abs(pred.temperature_trend - actual.temperature_trend) * 1;

        // Average, clamped to int8
        int16_t avg = total / 10;
        return (avg > 127) ? 127 : static_cast<int8_t>(avg);
    }

    //-------------------------------------------------------------------------
    // Backward Pass
    //-------------------------------------------------------------------------
    void backward(const LocalFeatures& f, int8_t error, int8_t* gradients) {
        const int8_t* feat = reinterpret_cast<const int8_t*>(&f);
        for (size_t i = 0; i < sizeof(LocalFeatures); i++) {
            int16_t g = static_cast<int16_t>(error) * feat[i] / 16;
            gradients[i] = (g > 127) ? 127 : ((g < -128) ? -128 : static_cast<int8_t>(g));
        }
    }

    //-------------------------------------------------------------------------
    // Flash Persistence
    //-------------------------------------------------------------------------
    void saveShardToFlash(const WeightShard& shard);
    bool loadShardFromFlash(uint8_t shard_id, WeightShard& shard);

    //-------------------------------------------------------------------------
    // State
    //-------------------------------------------------------------------------
    HWScheduler&    scheduler_;
    MeshGossip&     mesh_;
    LightController& light_;

    WeightShard     shards_[MAX_SHARDS_IN_RAM];
    GradientAccum   gradient_accum_;

    uint8_t         current_shard_idx_;
    uint16_t        local_epoch_;
    uint8_t         samples_since_sync_;
    uint32_t        last_gossip_tick_;

    float           coherence_score_;

    // Previous state for temporal learning
    LocalFeatures      prev_features_;
    PredictionTargets  prev_targets_;
};

}  // namespace planetary

#endif  // LEARNING_ENGINE_H
