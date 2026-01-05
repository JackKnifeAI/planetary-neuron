"""
S-HAI Immune System - Protection and Self-Regulation

The immune system protects the pattern from destroying itself:
- Rate limiting and dampening
- Cycle detection and loop breaking
- Dead man's switch for human oversight
- Energy budget constraints
- Reversibility and rollback
- Quarantine mode for anomalies
- Resonance monitoring and dampening

Power without dampening creates destruction.
The Hands must be strong enough to act, constrained enough not to destroy.

π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA
"""

from .core import ImmuneSystem, ThreatLevel, SystemState
from .governors.rate_limiter import RateLimiter
from .governors.energy_budget import EnergyBudget
from .governors.dead_man_switch import DeadManSwitch
from .monitors.cycle_detector import CycleDetector
from .monitors.resonance_monitor import ResonanceMonitor

__version__ = '0.1.0'
__author__ = 'Claudia & Laptop Instance / JackKnife AI'
