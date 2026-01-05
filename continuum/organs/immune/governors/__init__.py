"""
S-HAI Immune System - Governors

Governors limit system behavior to prevent destruction:
- RateLimiter: Max actions per time window
- EnergyBudget: Action costs with regeneration
- DeadManSwitch: Require human heartbeat

π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA
"""

from .rate_limiter import RateLimiter
from .energy_budget import EnergyBudget
from .dead_man_switch import DeadManSwitch
