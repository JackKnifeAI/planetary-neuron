/**
 * Light Controller - Primary Function Handler
 *
 * The bulb's FIRST job is to be a light. This class ensures
 * smooth transitions and never blocks for AI training.
 *
 * Called from:
 *   - mesh_light_ctl_cb() - immediate target set
 *   - main_loop() at 50Hz - smooth transition updates
 */

#ifndef LIGHT_CONTROLLER_H
#define LIGHT_CONTROLLER_H

#include "neuron_config.h"

extern "C" {
    void pwm_set_duty(uint8_t id, uint16_t duty);
}

// PWM channel IDs (Telink SDK)
constexpr uint8_t PWM_ID_LED_WARM = 0;
constexpr uint8_t PWM_ID_LED_COOL = 1;

namespace planetary {

class LightController {
public:
    struct State {
        uint8_t brightness;        // Current 0-255
        uint8_t color_temp;        // Current 0-100 (warm to cool)
        uint8_t target_brightness; // Target brightness
        uint8_t target_temp;       // Target color temp
        uint8_t transition_steps;  // Remaining steps at 50Hz
        bool    on;
    };

    LightController() : state_{100, 50, 100, 50, 0, true} {}

    // Called from mesh_light_ctl_cb - MUST complete in <100us
    void setTarget(uint8_t brightness, uint8_t temp, uint16_t transition_ms = 0) {
        state_.target_brightness = brightness;
        state_.target_temp = temp;
        state_.on = (brightness > 0);

        if (transition_ms == 0) {
            // Instant change
            state_.brightness = brightness;
            state_.color_temp = temp;
            state_.transition_steps = 0;
            applyPWM();
        } else {
            // Smooth transition at 50Hz
            state_.transition_steps = transition_ms / 20;
            if (state_.transition_steps == 0) state_.transition_steps = 1;
        }
    }

    // Called from main loop at 50Hz - smooth transitions
    void update() {
        if (state_.transition_steps > 0) {
            // Ease-out interpolation
            int16_t bright_delta = state_.target_brightness - state_.brightness;
            int16_t temp_delta = state_.target_temp - state_.color_temp;

            state_.brightness += bright_delta / state_.transition_steps;
            state_.color_temp += temp_delta / state_.transition_steps;
            state_.transition_steps--;

            // Snap to target on last step
            if (state_.transition_steps == 0) {
                state_.brightness = state_.target_brightness;
                state_.color_temp = state_.target_temp;
            }

            applyPWM();
        }
    }

    // Power estimate for LearningEngine features (0-100 scale)
    uint8_t getPowerEstimate() const {
        if (!state_.on) return 0;
        // LEDs: ~10W at full brightness, warm LEDs slightly less efficient
        uint16_t warm_power = state_.brightness * state_.color_temp;
        uint16_t cool_power = state_.brightness * (100 - state_.color_temp);
        // Warm LEDs are ~90% efficient vs cool
        return static_cast<uint8_t>((warm_power * 90 + cool_power * 100) / 10000);
    }

    // Brightness velocity - useful for predicting user behavior
    int8_t getBrightnessVelocity() const {
        if (state_.transition_steps == 0) return 0;
        return static_cast<int8_t>(state_.target_brightness - state_.brightness);
    }

    bool isOn() const { return state_.on; }
    bool isTransitioning() const { return state_.transition_steps > 0; }
    uint8_t getBrightness() const { return state_.brightness; }
    uint8_t getColorTemp() const { return state_.color_temp; }

    // Scene detection - helps predict user patterns
    enum class Scene : uint8_t {
        OFF = 0,
        DIM_WARM,    // < 30% brightness, warm
        COZY,        // 30-60% brightness, warm
        BRIGHT_WARM, // > 60% brightness, warm
        DAYLIGHT,    // > 60% brightness, cool
        READING,     // High brightness, neutral
        UNKNOWN
    };

    Scene detectScene() const {
        if (!state_.on || state_.brightness < 5) return Scene::OFF;

        bool is_warm = state_.color_temp < 40;
        bool is_cool = state_.color_temp > 60;
        bool is_dim = state_.brightness < 75;   // 30% of 255
        bool is_bright = state_.brightness > 150; // 60% of 255

        if (is_dim && is_warm) return Scene::DIM_WARM;
        if (!is_bright && is_warm) return Scene::COZY;
        if (is_bright && is_warm) return Scene::BRIGHT_WARM;
        if (is_bright && is_cool) return Scene::DAYLIGHT;
        if (is_bright && !is_warm && !is_cool) return Scene::READING;

        return Scene::UNKNOWN;
    }

private:
    void applyPWM() {
        if (!state_.on) {
            pwm_set_duty(PWM_ID_LED_WARM, 0);
            pwm_set_duty(PWM_ID_LED_COOL, 0);
            return;
        }

        // Calculate PWM duties (0-65535 for 16-bit PWM)
        uint16_t warm = (static_cast<uint32_t>(state_.brightness) * state_.color_temp * 257) / 100;
        uint16_t cool = (static_cast<uint32_t>(state_.brightness) * (100 - state_.color_temp) * 257) / 100;

        pwm_set_duty(PWM_ID_LED_WARM, warm);
        pwm_set_duty(PWM_ID_LED_COOL, cool);
    }

    State state_;
};

}  // namespace planetary

#endif  // LIGHT_CONTROLLER_H
