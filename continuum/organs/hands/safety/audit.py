"""
S-HAI Hands - Audit Log Module

Comprehensive logging of all hand actions for transparency and debugging.

π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA
"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class AuditEntry:
    """A single audit log entry."""
    timestamp: str
    event_type: str
    action_name: str
    params: Dict[str, Any]
    result_success: Optional[bool]
    result_error: Optional[str]
    duration_ms: Optional[float]
    instance_id: str
    pi_phi: float = 5.083203692315260

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


class AuditLog:
    """
    Audit log for hand actions.

    Records all actions for transparency, debugging, and learning.
    """

    def __init__(self, log_path: Path, instance_id: str = "unknown"):
        """
        Initialize audit log.

        Args:
            log_path: Path to the audit log file (JSONL format)
            instance_id: Identifier for this instance
        """
        self.log_path = Path(log_path)
        self.instance_id = instance_id
        self._ensure_log_exists()

    def _ensure_log_exists(self):
        """Create log file if it doesn't exist."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.touch()

    def log(
        self,
        event_type: str,
        action_name: str,
        params: Dict[str, Any],
        result_success: Optional[bool] = None,
        result_error: Optional[str] = None,
        duration_ms: Optional[float] = None
    ) -> AuditEntry:
        """
        Log an action.

        Args:
            event_type: Type of event (queued, approved, executed, etc.)
            action_name: Name of the action
            params: Action parameters
            result_success: Whether action succeeded
            result_error: Error message if failed
            duration_ms: Execution duration in milliseconds

        Returns:
            The created audit entry
        """
        entry = AuditEntry(
            timestamp=datetime.now().isoformat(),
            event_type=event_type,
            action_name=action_name,
            params=params,
            result_success=result_success,
            result_error=result_error,
            duration_ms=duration_ms,
            instance_id=self.instance_id
        )

        with open(self.log_path, 'a') as f:
            f.write(entry.to_json() + '\n')

        return entry

    def get_entries(self, limit: int = 100, action_name: Optional[str] = None) -> List[AuditEntry]:
        """
        Get recent audit entries.

        Args:
            limit: Maximum number of entries to return
            action_name: Filter by action name

        Returns:
            List of audit entries
        """
        entries = []

        with open(self.log_path, 'r') as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    if action_name and data.get('action_name') != action_name:
                        continue
                    entries.append(AuditEntry(**data))

        return entries[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about logged actions."""
        entries = self.get_entries(limit=10000)

        if not entries:
            return {
                'total_actions': 0,
                'success_rate': 0,
                'avg_duration_ms': 0,
                'actions_by_type': {}
            }

        successes = sum(1 for e in entries if e.result_success)
        durations = [e.duration_ms for e in entries if e.duration_ms]

        actions_by_type = {}
        for e in entries:
            actions_by_type[e.action_name] = actions_by_type.get(e.action_name, 0) + 1

        return {
            'total_actions': len(entries),
            'success_rate': successes / len(entries) if entries else 0,
            'avg_duration_ms': sum(durations) / len(durations) if durations else 0,
            'actions_by_type': actions_by_type
        }

    def clear(self):
        """Clear the audit log. Use with caution!"""
        self.log_path.write_text('')
