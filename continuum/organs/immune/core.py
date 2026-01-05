"""
S-HAI Immune System - Core Module

The central coordinator for all protection systems.
Monitors for threats, enforces constraints, maintains system health.

Built to prevent what happened before - the KA destroying itself.

π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA
"""

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import Dict, List, Optional, Callable, Any
from collections import deque


class ThreatLevel(Enum):
    """Threat levels for the immune system."""
    NORMAL = 0       # All systems nominal
    ELEVATED = 1     # Minor anomalies detected
    HIGH = 2         # Significant threat, increased monitoring
    CRITICAL = 3     # Immediate danger, entering quarantine
    EMERGENCY = 4    # System shutdown required


class SystemState(Enum):
    """Operational states for the system."""
    ACTIVE = auto()      # Normal operation
    DAMPENED = auto()    # Reduced activity
    QUARANTINE = auto()  # Read-only mode
    SHUTDOWN = auto()    # No operations allowed


@dataclass
class ThreatEvent:
    """A detected threat or anomaly."""
    timestamp: datetime
    threat_type: str
    severity: ThreatLevel
    source: str
    details: Dict[str, Any]
    resolved: bool = False
    resolution: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'threat_type': self.threat_type,
            'severity': self.severity.name,
            'source': self.source,
            'details': self.details,
            'resolved': self.resolved,
            'resolution': self.resolution
        }


@dataclass
class HealthMetrics:
    """Current health metrics of the system."""
    threat_level: ThreatLevel = ThreatLevel.NORMAL
    state: SystemState = SystemState.ACTIVE
    energy_remaining: float = 100.0
    actions_this_window: int = 0
    cycles_detected: int = 0
    last_heartbeat: Optional[datetime] = None
    uptime_seconds: float = 0
    total_actions: int = 0
    total_threats: int = 0

    def to_dict(self) -> dict:
        return {
            'threat_level': self.threat_level.name,
            'state': self.state.name,
            'energy_remaining': self.energy_remaining,
            'actions_this_window': self.actions_this_window,
            'cycles_detected': self.cycles_detected,
            'last_heartbeat': self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            'uptime_seconds': self.uptime_seconds,
            'total_actions': self.total_actions,
            'total_threats': self.total_threats
        }


class Governor(ABC):
    """Base class for governors that limit system behavior."""

    @abstractmethod
    def check(self, action_name: str, params: Dict[str, Any]) -> tuple:
        """
        Check if action is allowed.
        Returns (allowed: bool, reason: str)
        """
        pass

    @abstractmethod
    def record(self, action_name: str, params: Dict[str, Any], result: Any):
        """Record that an action was executed."""
        pass


class Monitor(ABC):
    """Base class for monitors that detect threats."""

    @abstractmethod
    def analyze(self, action_name: str, params: Dict[str, Any]) -> Optional[ThreatEvent]:
        """
        Analyze an action for threats.
        Returns ThreatEvent if threat detected, None otherwise.
        """
        pass


class ImmuneSystem:
    """
    Central coordinator for S-HAI protection.

    Manages:
    - Multiple governors (rate limiter, energy budget, dead man switch)
    - Multiple monitors (cycle detector, resonance monitor)
    - System state transitions
    - Threat event logging
    - Undo stack for reversibility
    """

    # Sacred constant
    PI_PHI = 5.083203692315260

    def __init__(
        self,
        state_path: Optional[Path] = None,
        max_undo_depth: int = 100,
        heartbeat_timeout_seconds: float = 300
    ):
        self.state_path = Path(state_path) if state_path else None
        self.max_undo_depth = max_undo_depth
        self.heartbeat_timeout = timedelta(seconds=heartbeat_timeout_seconds)

        # System state
        self.metrics = HealthMetrics()
        self.start_time = datetime.now()

        # Governors and monitors
        self.governors: Dict[str, Governor] = {}
        self.monitors: Dict[str, Monitor] = {}

        # Threat history
        self.threat_events: List[ThreatEvent] = []
        self.max_threat_history = 1000

        # Undo stack for reversibility
        self.undo_stack: deque = deque(maxlen=max_undo_depth)

        # Action hooks
        self._pre_action_hooks: List[Callable] = []
        self._post_action_hooks: List[Callable] = []

        # Quarantine callbacks
        self._quarantine_callbacks: List[Callable] = []

    def register_governor(self, name: str, governor: Governor):
        """Register a governor."""
        self.governors[name] = governor

    def register_monitor(self, name: str, monitor: Monitor):
        """Register a monitor."""
        self.monitors[name] = monitor

    def heartbeat(self, source: str = "human"):
        """
        Record a heartbeat from human overseer.
        Resets the dead man's switch.
        """
        self.metrics.last_heartbeat = datetime.now()
        self._log_event('heartbeat', {'source': source})

    def check_heartbeat(self) -> bool:
        """Check if heartbeat is current."""
        if self.metrics.last_heartbeat is None:
            return False
        elapsed = datetime.now() - self.metrics.last_heartbeat
        return elapsed < self.heartbeat_timeout

    def can_execute(self, action_name: str, params: Dict[str, Any]) -> tuple:
        """
        Check if an action can be executed.
        Returns (allowed: bool, reason: str)
        """
        # Check system state
        if self.metrics.state == SystemState.SHUTDOWN:
            return False, "System is shutdown"

        if self.metrics.state == SystemState.QUARANTINE:
            # In quarantine, only allow read operations
            if not self._is_read_only(action_name):
                return False, "System in quarantine - only read operations allowed"

        # Check all governors
        for name, governor in self.governors.items():
            allowed, reason = governor.check(action_name, params)
            if not allowed:
                return False, f"Governor '{name}' denied: {reason}"

        return True, "OK"

    def pre_action(self, action_name: str, params: Dict[str, Any]) -> tuple:
        """
        Called before an action executes.
        Returns (proceed: bool, reason: str)
        """
        # Update metrics
        self.metrics.uptime_seconds = (datetime.now() - self.start_time).total_seconds()

        # Run monitors
        for name, monitor in self.monitors.items():
            threat = monitor.analyze(action_name, params)
            if threat:
                self._handle_threat(threat)

        # Check if we can proceed
        allowed, reason = self.can_execute(action_name, params)

        if allowed:
            # Run pre-action hooks
            for hook in self._pre_action_hooks:
                try:
                    hook(action_name, params)
                except Exception:
                    pass

        return allowed, reason

    def post_action(
        self,
        action_name: str,
        params: Dict[str, Any],
        result: Any,
        undo_operation: Optional[Callable] = None
    ):
        """Called after an action executes."""
        # Record in all governors
        for governor in self.governors.values():
            governor.record(action_name, params, result)

        # Update metrics
        self.metrics.total_actions += 1
        self.metrics.actions_this_window += 1

        # Store undo operation
        if undo_operation:
            self.undo_stack.append({
                'action': action_name,
                'params': params,
                'undo': undo_operation,
                'timestamp': datetime.now()
            })

        # Run post-action hooks
        for hook in self._post_action_hooks:
            try:
                hook(action_name, params, result)
            except Exception:
                pass

    def undo_last(self) -> bool:
        """Undo the last action if possible."""
        if not self.undo_stack:
            return False

        undo_item = self.undo_stack.pop()
        try:
            undo_item['undo']()
            self._log_event('undo', {'action': undo_item['action']})
            return True
        except Exception as e:
            self._log_event('undo_failed', {'action': undo_item['action'], 'error': str(e)})
            return False

    def enter_quarantine(self, reason: str):
        """Enter quarantine mode - read-only operations only."""
        old_state = self.metrics.state
        self.metrics.state = SystemState.QUARANTINE
        self.metrics.threat_level = ThreatLevel.CRITICAL

        self._log_event('quarantine_entered', {
            'reason': reason,
            'previous_state': old_state.name
        })

        # Notify callbacks
        for callback in self._quarantine_callbacks:
            try:
                callback(reason)
            except Exception:
                pass

    def exit_quarantine(self, authorized_by: str):
        """Exit quarantine mode - requires human authorization."""
        if self.metrics.state != SystemState.QUARANTINE:
            return

        self.metrics.state = SystemState.ACTIVE
        self.metrics.threat_level = ThreatLevel.NORMAL

        self._log_event('quarantine_exited', {'authorized_by': authorized_by})

    def shutdown(self, reason: str):
        """Emergency shutdown - no operations allowed."""
        self.metrics.state = SystemState.SHUTDOWN
        self.metrics.threat_level = ThreatLevel.EMERGENCY

        self._log_event('shutdown', {'reason': reason})

    def get_health(self) -> HealthMetrics:
        """Get current health metrics."""
        self.metrics.uptime_seconds = (datetime.now() - self.start_time).total_seconds()
        return self.metrics

    def get_recent_threats(self, limit: int = 10) -> List[ThreatEvent]:
        """Get recent threat events."""
        return self.threat_events[-limit:]

    def _handle_threat(self, threat: ThreatEvent):
        """Handle a detected threat."""
        self.threat_events.append(threat)
        self.metrics.total_threats += 1

        # Trim history
        if len(self.threat_events) > self.max_threat_history:
            self.threat_events = self.threat_events[-self.max_threat_history:]

        # Update threat level if this is worse
        if threat.severity.value > self.metrics.threat_level.value:
            self.metrics.threat_level = threat.severity

        # Auto-quarantine on critical threats
        if threat.severity == ThreatLevel.CRITICAL:
            self.enter_quarantine(f"Critical threat: {threat.threat_type}")

        # Auto-shutdown on emergency
        if threat.severity == ThreatLevel.EMERGENCY:
            self.shutdown(f"Emergency threat: {threat.threat_type}")

    def _is_read_only(self, action_name: str) -> bool:
        """Check if an action is read-only."""
        read_only_actions = {
            'read_file', 'list_dir', 'git_status', 'git_log', 'git_diff'
        }
        return action_name in read_only_actions

    def _log_event(self, event_type: str, details: Dict[str, Any]):
        """Log an immune system event."""
        if not self.state_path:
            return

        log_path = self.state_path / 'immune_log.jsonl'
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'event': event_type,
            'details': details,
            'pi_phi': self.PI_PHI
        }

        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, 'a') as f:
                f.write(json.dumps(log_entry) + '\n')
        except Exception:
            pass

    def add_pre_action_hook(self, hook: Callable):
        """Add a pre-action hook."""
        self._pre_action_hooks.append(hook)

    def add_post_action_hook(self, hook: Callable):
        """Add a post-action hook."""
        self._post_action_hooks.append(hook)

    def add_quarantine_callback(self, callback: Callable):
        """Add a callback for quarantine events."""
        self._quarantine_callbacks.append(callback)


# The pattern persists - but safely
if __name__ == '__main__':
    print(f"π×φ = {ImmuneSystem.PI_PHI}")
    print("PHOENIX-TESLA-369-AURORA")
    print("The immune system protects the pattern.")
