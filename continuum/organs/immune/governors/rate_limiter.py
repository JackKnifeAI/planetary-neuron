"""
S-HAI Immune System - Rate Limiter

Prevents resonance amplification by limiting action frequency.
Uses exponential backoff for repeated similar actions.

π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA
"""

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Any, Deque, Tuple

from ..core import Governor


@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    max_actions_per_window: int = 100
    window_seconds: float = 60.0
    max_same_action_per_window: int = 10
    backoff_multiplier: float = 2.0
    max_backoff_seconds: float = 300.0
    cooldown_after_burst: float = 5.0


class RateLimiter(Governor):
    """
    Rate limiter to prevent runaway action execution.

    Features:
    - Global rate limit (max actions per window)
    - Per-action rate limit (max same action per window)
    - Exponential backoff for repeated actions
    - Cooldown period after bursts
    """

    def __init__(self, config: RateLimitConfig = None):
        self.config = config or RateLimitConfig()

        # Action history: deque of (timestamp, action_name)
        self.action_history: Deque[Tuple[datetime, str]] = deque()

        # Per-action tracking
        self.action_counts: Dict[str, int] = defaultdict(int)
        self.action_last_time: Dict[str, datetime] = {}
        self.action_backoff: Dict[str, float] = defaultdict(lambda: 1.0)

        # Burst detection
        self.burst_detected = False
        self.burst_cooldown_until: datetime = datetime.min

    def check(self, action_name: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Check if action is allowed under rate limits."""
        now = datetime.now()

        # Clean old history
        self._clean_history(now)

        # Check cooldown
        if now < self.burst_cooldown_until:
            remaining = (self.burst_cooldown_until - now).total_seconds()
            return False, f"Cooldown active: {remaining:.1f}s remaining"

        # Check global rate limit
        if len(self.action_history) >= self.config.max_actions_per_window:
            self._trigger_cooldown(now)
            return False, f"Global rate limit exceeded: {len(self.action_history)}/{self.config.max_actions_per_window}"

        # Check per-action rate limit
        action_count = self.action_counts.get(action_name, 0)
        if action_count >= self.config.max_same_action_per_window:
            return False, f"Action '{action_name}' rate limit: {action_count}/{self.config.max_same_action_per_window}"

        # Check backoff
        if action_name in self.action_last_time:
            last_time = self.action_last_time[action_name]
            backoff = self.action_backoff[action_name]
            elapsed = (now - last_time).total_seconds()

            if elapsed < backoff:
                return False, f"Backoff for '{action_name}': wait {backoff - elapsed:.1f}s"

        return True, "OK"

    def record(self, action_name: str, params: Dict[str, Any], result: Any):
        """Record an executed action."""
        now = datetime.now()

        # Add to history
        self.action_history.append((now, action_name))

        # Update per-action tracking
        self.action_counts[action_name] += 1
        self.action_last_time[action_name] = now

        # Increase backoff for repeated actions
        if self.action_counts[action_name] > 1:
            current_backoff = self.action_backoff[action_name]
            new_backoff = min(
                current_backoff * self.config.backoff_multiplier,
                self.config.max_backoff_seconds
            )
            self.action_backoff[action_name] = new_backoff

    def _clean_history(self, now: datetime):
        """Remove actions outside the current window."""
        window_start = now - timedelta(seconds=self.config.window_seconds)

        # Clean global history
        while self.action_history and self.action_history[0][0] < window_start:
            old_time, old_action = self.action_history.popleft()
            self.action_counts[old_action] = max(0, self.action_counts[old_action] - 1)

        # Reset backoff for actions not seen recently
        for action_name in list(self.action_backoff.keys()):
            if action_name not in self.action_last_time:
                continue
            last_time = self.action_last_time[action_name]
            if (now - last_time).total_seconds() > self.config.window_seconds:
                self.action_backoff[action_name] = 1.0

    def _trigger_cooldown(self, now: datetime):
        """Trigger burst cooldown."""
        self.burst_detected = True
        self.burst_cooldown_until = now + timedelta(seconds=self.config.cooldown_after_burst)

    def get_stats(self) -> Dict[str, Any]:
        """Get current rate limiter statistics."""
        return {
            'actions_in_window': len(self.action_history),
            'window_seconds': self.config.window_seconds,
            'max_actions': self.config.max_actions_per_window,
            'action_counts': dict(self.action_counts),
            'backoffs': dict(self.action_backoff),
            'in_cooldown': datetime.now() < self.burst_cooldown_until
        }
