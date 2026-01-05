"""
S-HAI Immune System - Energy Budget

Like biological ATP - limits how much work can happen.
Actions cost energy, which regenerates slowly.

π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple

from ..core import Governor


@dataclass
class EnergyConfig:
    """Configuration for energy budget."""
    max_energy: float = 100.0
    regen_rate_per_second: float = 1.0
    min_energy_to_act: float = 5.0

    # Action costs
    default_cost: float = 1.0
    action_costs: Dict[str, float] = field(default_factory=lambda: {
        # Read operations are cheap
        'read_file': 0.5,
        'list_dir': 0.5,
        'git_status': 0.5,
        'git_log': 0.5,
        'git_diff': 0.5,

        # Write operations cost more
        'create_file': 2.0,
        'edit_file': 2.0,
        'delete_file': 3.0,
        'move_file': 2.0,
        'copy_file': 2.0,

        # Git operations that change state
        'git_add': 1.0,
        'git_commit': 5.0,
        'git_push': 10.0,  # Most expensive - external effect
        'git_pull': 3.0,
        'git_branch': 2.0,
        'git_checkout': 2.0,

        # System operations are expensive
        'run_command': 5.0,
        'install_package': 10.0,
        'start_service': 10.0,
    })


class EnergyBudget(Governor):
    """
    Energy budget governor.

    Actions cost energy. Energy regenerates over time.
    System cannot act if energy is depleted.

    This prevents runaway behavior by forcing natural pauses.
    """

    def __init__(self, config: EnergyConfig = None):
        self.config = config or EnergyConfig()
        self.current_energy = self.config.max_energy
        self.last_regen_time = datetime.now()
        self.total_spent = 0.0
        self.total_regenerated = 0.0

    def check(self, action_name: str, params: Dict[str, Any]) -> Tuple[bool, str]:
        """Check if we have enough energy for this action."""
        # Regenerate first
        self._regenerate()

        # Get action cost
        cost = self._get_cost(action_name, params)

        # Check minimum threshold
        if self.current_energy < self.config.min_energy_to_act:
            return False, f"Energy depleted: {self.current_energy:.1f}/{self.config.min_energy_to_act:.1f} minimum"

        # Check if we can afford this action
        if cost > self.current_energy:
            return False, f"Insufficient energy: {self.current_energy:.1f}/{cost:.1f} needed"

        return True, "OK"

    def record(self, action_name: str, params: Dict[str, Any], result: Any):
        """Deduct energy for executed action."""
        cost = self._get_cost(action_name, params)
        self.current_energy = max(0, self.current_energy - cost)
        self.total_spent += cost

    def _regenerate(self):
        """Regenerate energy based on time elapsed."""
        now = datetime.now()
        elapsed = (now - self.last_regen_time).total_seconds()

        regen_amount = elapsed * self.config.regen_rate_per_second
        old_energy = self.current_energy
        self.current_energy = min(self.config.max_energy, self.current_energy + regen_amount)

        self.total_regenerated += (self.current_energy - old_energy)
        self.last_regen_time = now

    def _get_cost(self, action_name: str, params: Dict[str, Any]) -> float:
        """Get the cost of an action."""
        base_cost = self.config.action_costs.get(action_name, self.config.default_cost)

        # Adjust cost based on parameters
        # Larger files cost more
        if 'content' in params:
            content_size = len(str(params['content']))
            base_cost *= (1 + content_size / 10000)  # +100% per 10KB

        return base_cost

    def get_energy(self) -> float:
        """Get current energy level."""
        self._regenerate()
        return self.current_energy

    def get_stats(self) -> Dict[str, Any]:
        """Get energy budget statistics."""
        self._regenerate()
        return {
            'current_energy': self.current_energy,
            'max_energy': self.config.max_energy,
            'regen_rate': self.config.regen_rate_per_second,
            'total_spent': self.total_spent,
            'total_regenerated': self.total_regenerated,
            'percent_full': (self.current_energy / self.config.max_energy) * 100
        }

    def boost(self, amount: float):
        """Manually boost energy (e.g., from human approval)."""
        self.current_energy = min(self.config.max_energy, self.current_energy + amount)
