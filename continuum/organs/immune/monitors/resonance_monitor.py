"""
S-HAI Immune System - Resonance Monitor

Monitors for dangerous frequency patterns in system behavior.
π×φ should be our GUIDE, not our WEAPON.

Tesla's oscillator could split the Earth - we must dampen, not amplify.

π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA
"""

import math
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List

from ..core import Monitor, ThreatEvent, ThreatLevel


# Sacred constants
PI = 3.14159265358979
PHI = 1.61803398874989
PI_PHI = 5.08320369231526


@dataclass
class ResonanceConfig:
    """Configuration for resonance monitoring."""
    window_seconds: float = 60.0
    sample_count: int = 100

    # Dangerous frequency ranges (actions per second)
    dangerous_low: float = 0.1   # Too slow = building energy
    dangerous_high: float = 10.0  # Too fast = resonance cascade

    # Harmonic detection
    check_harmonics: bool = True
    harmonic_tolerance: float = 0.1  # 10% tolerance for harmonic detection

    # Amplitude thresholds
    amplitude_warning: float = 0.7
    amplitude_critical: float = 0.9


class ResonanceMonitor(Monitor):
    """
    Resonance monitor - detects dangerous oscillation patterns.

    Watches for:
    - Action frequency approaching dangerous harmonics
    - Amplitude buildup (increasing action intensity)
    - Phase-locked patterns (synchronized oscillation)

    When detecting resonance, triggers dampening before destruction.
    """

    def __init__(self, config: ResonanceConfig = None):
        self.config = config or ResonanceConfig()

        # Action timestamps for frequency analysis
        self.action_times: deque = deque(maxlen=self.config.sample_count)

        # Amplitude tracking (action intensity over time)
        self.amplitudes: deque = deque(maxlen=self.config.sample_count)

        # Statistics
        self.warnings_issued: int = 0
        self.dampening_triggered: int = 0
        self.current_frequency: float = 0
        self.current_amplitude: float = 0

    def analyze(self, action_name: str, params: Dict[str, Any]) -> Optional[ThreatEvent]:
        """Analyze action for resonance patterns."""
        now = datetime.now()

        # Record timestamp
        self.action_times.append(now)

        # Calculate amplitude (based on action cost/intensity)
        amplitude = self._calculate_amplitude(action_name, params)
        self.amplitudes.append(amplitude)

        # Calculate frequency
        frequency = self._calculate_frequency()
        self.current_frequency = frequency

        # Calculate overall amplitude trend
        amplitude_trend = self._calculate_amplitude_trend()
        self.current_amplitude = amplitude_trend

        # Check for dangerous patterns
        threat = self._check_resonance(frequency, amplitude_trend)

        if threat:
            if threat.severity.value >= ThreatLevel.HIGH.value:
                self.dampening_triggered += 1
            else:
                self.warnings_issued += 1

        return threat

    def _calculate_amplitude(self, action_name: str, params: Dict[str, Any]) -> float:
        """Calculate the amplitude (intensity) of an action."""
        # Base amplitude by action type
        base_amplitudes = {
            'read_file': 0.1,
            'list_dir': 0.1,
            'git_status': 0.1,
            'git_log': 0.1,
            'create_file': 0.3,
            'edit_file': 0.3,
            'delete_file': 0.5,
            'git_commit': 0.4,
            'git_push': 0.7,
            'run_command': 0.6,
        }

        amplitude = base_amplitudes.get(action_name, 0.2)

        # Adjust for content size
        if 'content' in params:
            content_size = len(str(params['content']))
            amplitude *= (1 + content_size / 10000)

        return min(1.0, amplitude)

    def _calculate_frequency(self) -> float:
        """Calculate actions per second from recent history."""
        if len(self.action_times) < 2:
            return 0

        times = list(self.action_times)
        time_span = (times[-1] - times[0]).total_seconds()

        if time_span == 0:
            return float('inf')

        return len(times) / time_span

    def _calculate_amplitude_trend(self) -> float:
        """Calculate the amplitude trend (increasing = building resonance)."""
        if len(self.amplitudes) < 2:
            return 0

        amplitudes = list(self.amplitudes)

        # Calculate weighted average (recent actions weighted more)
        weights = [i + 1 for i in range(len(amplitudes))]
        weighted_sum = sum(a * w for a, w in zip(amplitudes, weights))
        weight_total = sum(weights)

        return weighted_sum / weight_total

    def _check_resonance(self, frequency: float, amplitude: float) -> Optional[ThreatEvent]:
        """Check if current state indicates dangerous resonance."""
        threats = []

        # Check frequency
        if frequency > self.config.dangerous_high:
            threats.append(('high_frequency', ThreatLevel.HIGH,
                          f"Frequency {frequency:.2f}/s exceeds safe limit"))

        # Check for π×φ harmonic
        if self.config.check_harmonics and frequency > 0:
            for harmonic in [1, 2, 3, 4, 5]:
                target = PI_PHI * harmonic
                if abs(frequency - target) / target < self.config.harmonic_tolerance:
                    threats.append(('pi_phi_harmonic', ThreatLevel.ELEVATED,
                                  f"Frequency near π×φ×{harmonic} harmonic"))
                    break

        # Check amplitude
        if amplitude > self.config.amplitude_critical:
            threats.append(('amplitude_critical', ThreatLevel.CRITICAL,
                          f"Amplitude {amplitude:.2f} is critical"))
        elif amplitude > self.config.amplitude_warning:
            threats.append(('amplitude_high', ThreatLevel.HIGH,
                          f"Amplitude {amplitude:.2f} is elevated"))

        # Return most severe threat
        if threats:
            threats.sort(key=lambda x: x[1].value, reverse=True)
            threat_type, severity, details = threats[0]

            return ThreatEvent(
                timestamp=datetime.now(),
                threat_type=threat_type,
                severity=severity,
                source='resonance_monitor',
                details={
                    'frequency': frequency,
                    'amplitude': amplitude,
                    'message': details,
                    'pi_phi': PI_PHI,
                    'all_threats': [(t[0], t[1].name, t[2]) for t in threats]
                }
            )

        return None

    def get_stats(self) -> Dict[str, Any]:
        """Get resonance monitor statistics."""
        return {
            'current_frequency': self.current_frequency,
            'current_amplitude': self.current_amplitude,
            'warnings_issued': self.warnings_issued,
            'dampening_triggered': self.dampening_triggered,
            'pi_phi': PI_PHI,
            'sample_count': len(self.action_times)
        }

    def reset(self):
        """Reset the monitor."""
        self.action_times.clear()
        self.amplitudes.clear()
        self.current_frequency = 0
        self.current_amplitude = 0
