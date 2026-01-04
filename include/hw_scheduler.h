/**
 * Hardware Scheduler - Cooperative scheduling with BLE stack
 *
 * The TLSR8258 BLE mesh has hard real-time requirements.
 * This scheduler ensures AI tasks yield before BLE events.
 *
 * Strategy:
 *   - Hook into BLE stack's idle callback
 *   - Run AI in micro-bursts (5ms max)
 *   - Monitor chip temperature via ADC
 *   - Throttle/kill AI if thermal limits exceeded
 */

#ifndef HW_SCHEDULER_H
#define HW_SCHEDULER_H

#include "neuron_config.h"

namespace planetary {

// Forward declare - actual impl depends on Telink SDK
extern "C" {
    uint32_t clock_time(void);           // Telink system tick
    uint32_t blt_get_next_event_tick(void); // Next BLE event
    uint16_t adc_sample_temp(void);      // Read internal temp sensor
    void     cpu_sleep_wakeup(int, int, uint32_t);
}

enum class TaskState : uint8_t {
    IDLE,
    RUNNING,
    THROTTLED,
    KILLED
};

enum class TaskPriority : uint8_t {
    CRITICAL = 0,   // BLE mesh (never preempt)
    HIGH     = 1,   // Light control commands
    NORMAL   = 2,   // Weight sync/gossip
    LOW      = 3    // Local training
};

// Scheduler callback signature
using TaskCallback = bool (*)(uint32_t budget_us, void* ctx);

struct ScheduledTask {
    TaskCallback callback;
    void*        context;
    TaskPriority priority;
    TaskState    state;
    uint32_t     last_run_tick;
    uint32_t     total_runtime_us;
    uint16_t     run_count;
};

class HWScheduler {
public:
    static constexpr uint8_t MAX_TASKS = 8;
    static constexpr uint32_t TICK_PER_US = 16;  // TLSR8258 @ 16MHz tick

    HWScheduler() : task_count_(0), current_temp_c_(25), throttle_level_(0) {}

    // Register a task with the scheduler
    bool registerTask(TaskCallback cb, void* ctx, TaskPriority prio) {
        if (task_count_ >= MAX_TASKS) return false;

        tasks_[task_count_] = {
            .callback = cb,
            .context = ctx,
            .priority = prio,
            .state = TaskState::IDLE,
            .last_run_tick = 0,
            .total_runtime_us = 0,
            .run_count = 0
        };
        task_count_++;
        return true;
    }

    // Call this from the BLE idle callback (blt_sdk_main_loop)
    void runSlice() {
        updateThermals();

        if (throttle_level_ >= 100) {
            // Thermal emergency - no AI tasks
            return;
        }

        uint32_t now = clock_time();
        uint32_t next_ble = blt_get_next_event_tick();
        uint32_t available_ticks = (next_ble > now + BLE_GUARD_US * TICK_PER_US)
                                   ? (next_ble - now - BLE_GUARD_US * TICK_PER_US)
                                   : 0;

        if (available_ticks == 0) return;

        // Convert to microseconds and apply throttle
        uint32_t budget_us = available_ticks / TICK_PER_US;
        if (budget_us > AI_TIMESLOT_US) budget_us = AI_TIMESLOT_US;
        budget_us = (budget_us * (100 - throttle_level_)) / 100;

        if (budget_us < 100) return;  // Not worth context switch

        // Find highest priority runnable task
        ScheduledTask* best = nullptr;
        for (uint8_t i = 0; i < task_count_; i++) {
            if (tasks_[i].state == TaskState::KILLED) continue;
            if (tasks_[i].state == TaskState::THROTTLED && throttle_level_ > 50) continue;

            if (!best || tasks_[i].priority < best->priority) {
                best = &tasks_[i];
            }
        }

        if (!best) return;

        // Run the task
        uint32_t start = clock_time();
        best->state = TaskState::RUNNING;

        bool wants_more = best->callback(budget_us, best->context);

        uint32_t elapsed = (clock_time() - start) / TICK_PER_US;
        best->total_runtime_us += elapsed;
        best->run_count++;
        best->last_run_tick = now;
        best->state = wants_more ? TaskState::IDLE : TaskState::IDLE;
    }

    // Get current thermal throttle percentage
    uint8_t getThrottleLevel() const { return throttle_level_; }
    uint8_t getCurrentTemp() const { return current_temp_c_; }

    // Duty cycle tracking
    uint8_t getAIDutyCycle() const {
        uint32_t total = 0;
        for (uint8_t i = 0; i < task_count_; i++) {
            if (tasks_[i].priority >= TaskPriority::NORMAL) {
                total += tasks_[i].total_runtime_us;
            }
        }
        // Rough estimate over last second
        return static_cast<uint8_t>((total / 10000) % 100);
    }

private:
    void updateThermals() {
        // Read temp every ~100 calls to avoid ADC overhead
        static uint8_t sample_counter = 0;
        if (++sample_counter < 100) return;
        sample_counter = 0;

        // TLSR8258 internal temp sensor (rough calibration)
        uint16_t raw = adc_sample_temp();
        current_temp_c_ = (raw - 1100) / 4;  // Approximate conversion

        // Progressive throttling
        if (current_temp_c_ >= TEMP_SHUTDOWN_C) {
            throttle_level_ = 100;  // Kill all AI
        } else if (current_temp_c_ >= TEMP_THROTTLE_C) {
            // Linear throttle from 55C (0%) to 70C (100%)
            throttle_level_ = ((current_temp_c_ - TEMP_THROTTLE_C) * 100) /
                              (TEMP_SHUTDOWN_C - TEMP_THROTTLE_C);
        } else {
            throttle_level_ = 0;
        }
    }

    ScheduledTask tasks_[MAX_TASKS];
    uint8_t       task_count_;
    uint8_t       current_temp_c_;
    uint8_t       throttle_level_;
};

}  // namespace planetary

#endif  // HW_SCHEDULER_H
