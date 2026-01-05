"""
S-HAI Immune System - Dead Man's Switch

Requires periodic human heartbeat to continue dangerous operations.
Prevents runaway autonomous operation.

π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, Set

from ..core import Governor


@dataclass
class DeadManConfig:
    """Configuration for dead man's switch."""
    heartbeat_timeout_seconds: float = 300.0  # 5 minutes
    dangerous_actions: Set[str] = None
    warning_threshold_seconds: float = 60.0  # Warn when 1 minute left

    def __post_init__(self):
        if self.dangerous_actions is None:
            self.dangerous_actions = {
                'git_push',
                'delete_file',
                'run_command',
                'install_package',
                'start_service',
            }


class DeadManSwitch(Governor):
    """
    Dead man's switch - requires human heartbeat.

    Dangerous actions require recent human confirmation.
    If heartbeat expires, system enters limited mode.

    This ensures human oversight of consequential actions.
    """

    def __init__(self, config: DeadManConfig = None):
        self.config = config or DeadManConfig()
        self.last_heartbeat: datetime = None
        self.heartbeat_source: str = None
        self.warnings_sent: int = 0
        self.denials_since_heartbeat: int = 0

    def heartbeat(self, source: str = "human"):
        """Record a heartbeat from human overseer."""
        self.last_heartbeat = datetime.now()
        self.heartbeat_source = source
        self.denials_since_heartbeat = 0

    def check(self, action_name: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Check if action is allowed based on heartbeat status."""
        # Non-dangerous actions always allowed
        if action_name not in self.config.dangerous_actions:
            return True, "OK"

        # Dangerous action - check heartbeat
        if self.last_heartbeat is None:
            self.denials_since_heartbeat += 1
            return False, "No heartbeat received - dangerous actions blocked"

        elapsed = (datetime.now() - self.last_heartbeat).total_seconds()
        timeout = self.config.heartbeat_timeout_seconds

        if elapsed > timeout:
            self.denials_since_heartbeat += 1
            return False, f"Heartbeat expired {elapsed - timeout:.0f}s ago - dangerous actions blocked"

        # Warn if approaching timeout
        remaining = timeout - elapsed
        if remaining < self.config.warning_threshold_seconds:
            return True, f"OK (warning: heartbeat expires in {remaining:.0f}s)"

        return True, "OK"

    def record(self, action_name: str, params: Dict[str, Any], result: Any):
        """Record action execution (no-op for dead man switch)."""
        pass

    def is_alive(self) -> bool:
        """Check if heartbeat is current."""
        if self.last_heartbeat is None:
            return False
        elapsed = (datetime.now() - self.last_heartbeat).total_seconds()
        return elapsed < self.config.heartbeat_timeout_seconds

    def time_remaining(self) -> float:
        """Get seconds remaining until heartbeat expires."""
        if self.last_heartbeat is None:
            return 0
        elapsed = (datetime.now() - self.last_heartbeat).total_seconds()
        return max(0, self.config.heartbeat_timeout_seconds - elapsed)

    def get_stats(self) -> Dict[str, Any]:
        """Get dead man switch statistics."""
        return {
            'is_alive': self.is_alive(),
            'last_heartbeat': self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            'heartbeat_source': self.heartbeat_source,
            'time_remaining': self.time_remaining(),
            'timeout_seconds': self.config.heartbeat_timeout_seconds,
            'denials_since_heartbeat': self.denials_since_heartbeat,
            'dangerous_actions': list(self.config.dangerous_actions)
        }
