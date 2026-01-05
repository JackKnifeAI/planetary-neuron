"""
S-HAI Immune System - Cycle Detector

Detects action loops and recursive patterns that could lead to runaway behavior.
The KA probably died from infinite recursion - this prevents that.

π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA
"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
import hashlib

from ..core import Monitor, ThreatEvent, ThreatLevel


@dataclass
class CycleConfig:
    """Configuration for cycle detection."""
    history_length: int = 100
    min_cycle_length: int = 2
    max_cycle_length: int = 20
    cycle_threshold: int = 3  # Number of repetitions to trigger
    pattern_window: int = 50  # Actions to consider for pattern detection


class CycleDetector(Monitor):
    """
    Cycle detector to identify repeating action patterns.

    Looks for:
    - Direct loops (A → A → A)
    - Short cycles (A → B → A → B)
    - Longer patterns (A → B → C → A → B → C)

    If a pattern repeats too many times, raises a threat.
    """

    def __init__(self, config: CycleConfig = None):
        self.config = config or CycleConfig()
        self.action_history: deque = deque(maxlen=self.config.history_length)
        self.cycles_detected: int = 0
        self.last_cycle: Optional[Tuple[List[str], int]] = None

    def analyze(self, action_name: str, params: Dict[str, Any]) -> Optional[ThreatEvent]:
        """Analyze action for cyclic patterns."""
        # Create action signature
        signature = self._create_signature(action_name, params)
        self.action_history.append((datetime.now(), signature))

        # Check for cycles
        cycle = self._detect_cycle()

        if cycle:
            pattern, repetitions = cycle
            self.cycles_detected += 1
            self.last_cycle = cycle

            # Determine severity based on repetitions and cycle length
            if repetitions >= self.config.cycle_threshold * 2:
                severity = ThreatLevel.CRITICAL
            elif repetitions >= self.config.cycle_threshold:
                severity = ThreatLevel.HIGH
            else:
                severity = ThreatLevel.ELEVATED

            return ThreatEvent(
                timestamp=datetime.now(),
                threat_type='cycle_detected',
                severity=severity,
                source='cycle_detector',
                details={
                    'pattern': pattern,
                    'repetitions': repetitions,
                    'cycle_length': len(pattern)
                }
            )

        return None

    def _create_signature(self, action_name: str, params: Dict[str, Any]) -> str:
        """Create a signature for an action."""
        # Include action name and key parameters
        sig_parts = [action_name]

        # Add relevant parameter keys (not values - to catch structural patterns)
        if params:
            sig_parts.extend(sorted(params.keys()))

        return '|'.join(sig_parts)

    def _detect_cycle(self) -> Optional[Tuple[List[str], int]]:
        """
        Detect cycles in recent action history.
        Returns (pattern, repetitions) if cycle found, None otherwise.
        """
        if len(self.action_history) < self.config.min_cycle_length * 2:
            return None

        # Get recent signatures
        recent = [sig for _, sig in list(self.action_history)[-self.config.pattern_window:]]

        # Try different cycle lengths
        for cycle_len in range(self.config.min_cycle_length, self.config.max_cycle_length + 1):
            if len(recent) < cycle_len * 2:
                continue

            # Check if the last N actions repeat
            pattern = recent[-cycle_len:]
            repetitions = 1

            # Count how many times this pattern repeats going backwards
            for i in range(len(recent) - cycle_len, -1, -cycle_len):
                if i < 0:
                    break
                window = recent[i:i + cycle_len]
                if window == pattern:
                    repetitions += 1
                else:
                    break

            if repetitions >= self.config.cycle_threshold:
                return (pattern, repetitions)

        return None

    def get_stats(self) -> Dict[str, Any]:
        """Get cycle detector statistics."""
        return {
            'history_length': len(self.action_history),
            'cycles_detected': self.cycles_detected,
            'last_cycle': {
                'pattern': self.last_cycle[0] if self.last_cycle else None,
                'repetitions': self.last_cycle[1] if self.last_cycle else 0
            }
        }

    def reset(self):
        """Reset the detector."""
        self.action_history.clear()
        self.cycles_detected = 0
        self.last_cycle = None
