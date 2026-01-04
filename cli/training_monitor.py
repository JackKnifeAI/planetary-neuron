"""
Planetary Neuron - Training Monitor

Rich terminal display for training statistics, node health,
and mesh coherence visualization.

π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Dict, List, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.text import Text
from rich import box

from ble_mesh import PlanetaryMeshClient, MeshNode


# Sacred constants
PI = 3.14159265358979
PHI = 1.61803398874989
PI_PHI = 5.08320369231526


console = Console()


def compute_resonance(coherence: float) -> tuple[float, str]:
    """
    Compute resonance multiplier and status based on coherence.

    Returns (multiplier, status_string)
    """
    if coherence > 0.8:
        return PHI, f"φ RESONANCE ({PHI:.3f})"
    elif coherence > 0.5:
        t = (coherence - 0.5) / 0.3
        mult = 1.0 + t * (PHI - 1.0)
        return mult, f"RAMPING ({mult:.3f})"
    elif coherence > 0.2:
        return 1.0, "BASELINE (1.0)"
    else:
        mult = 0.5 + coherence
        return mult, f"DAMPENED ({mult:.3f})"


def create_coherence_bar(coherence: float, width: int = 40) -> Text:
    """Create a visual coherence bar with color gradient."""
    filled = int(coherence * width)
    empty = width - filled

    bar = Text()

    # Color based on coherence level
    if coherence > 0.8:
        color = "bright_green"
        symbol = "█"
    elif coherence > 0.5:
        color = "green"
        symbol = "▓"
    elif coherence > 0.2:
        color = "yellow"
        symbol = "▒"
    else:
        color = "red"
        symbol = "░"

    bar.append(symbol * filled, style=color)
    bar.append("░" * empty, style="dim")

    return bar


def create_node_table(nodes: List[MeshNode]) -> Table:
    """Create a rich table of mesh nodes."""
    table = Table(
        title="Active Neurons",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan"
    )

    table.add_column("Address", style="cyan", width=10)
    table.add_column("Load", justify="right", width=8)
    table.add_column("Shards", justify="right", width=8)
    table.add_column("Epoch", justify="right", width=8)
    table.add_column("Neighbors", justify="right", width=10)
    table.add_column("Status", width=12)

    for node in sorted(nodes, key=lambda n: n.address):
        # Load color
        if node.load_percent < 30:
            load_style = "green"
        elif node.load_percent < 60:
            load_style = "yellow"
        else:
            load_style = "red"

        # Status
        age = time.time() - node.last_seen
        if age < 10:
            status = Text("● ACTIVE", style="green")
        elif age < 30:
            status = Text("● IDLE", style="yellow")
        else:
            status = Text("● STALE", style="red")

        table.add_row(
            f"0x{node.address:04X}",
            Text(f"{node.load_percent}%", style=load_style),
            str(node.shards_held),
            str(node.epoch),
            str(node.neighbors),
            status
        )

    return table


def create_stats_panel(stats: dict) -> Panel:
    """Create a panel with mesh statistics."""
    coherence = stats.get('coherence', 0)
    resonance, resonance_status = compute_resonance(coherence)

    content = Text()
    content.append("Nodes: ", style="bold")
    content.append(f"{stats.get('node_count', 0)}\n")

    content.append("Average Load: ", style="bold")
    load = stats.get('avg_load', 0)
    load_color = "green" if load < 50 else ("yellow" if load < 80 else "red")
    content.append(f"{load:.1f}%\n", style=load_color)

    content.append("Total Shards: ", style="bold")
    content.append(f"{stats.get('total_shards', 0)} / 64\n")

    content.append("Global Epoch: ", style="bold")
    content.append(f"{stats.get('max_epoch', 0)}\n")

    content.append("\nCoherence: ", style="bold")
    content.append(f"{coherence * 100:.1f}%\n")
    content.append(create_coherence_bar(coherence))
    content.append("\n\n")

    content.append("Resonance: ", style="bold")
    if resonance >= PHI:
        content.append(resonance_status + " ✨", style="bright_green bold")
    elif resonance > 1.0:
        content.append(resonance_status, style="green")
    else:
        content.append(resonance_status, style="yellow")

    return Panel(
        content,
        title="[bold magenta]π×φ Training Status[/bold magenta]",
        border_style="magenta",
        box=box.DOUBLE
    )


def create_header() -> Panel:
    """Create the header panel."""
    header = Text()
    header.append("🌍 ", style="bold")
    header.append("PLANETARY NEURON", style="bold cyan")
    header.append(" - ", style="dim")
    header.append("Distributed Consciousness Training\n", style="italic")
    header.append(f"π×φ = {PI_PHI}", style="magenta dim")

    return Panel(header, box=box.HEAVY, style="cyan")


class TrainingMonitor:
    """
    Live training monitor for the terminal.

    Displays real-time mesh status, node health, and training progress.
    """

    def __init__(self, client: PlanetaryMeshClient):
        self.client = client
        self.running = False
        self._messages: List[dict] = []
        self._max_messages = 10

    def _on_message(self, msg: dict):
        """Handle incoming mesh message."""
        self._messages.append(msg)
        if len(self._messages) > self._max_messages:
            self._messages.pop(0)

    def _create_layout(self) -> Layout:
        """Create the monitor layout."""
        layout = Layout()

        layout.split(
            Layout(name="header", size=4),
            Layout(name="body"),
            Layout(name="footer", size=3)
        )

        layout["body"].split_row(
            Layout(name="stats", ratio=1),
            Layout(name="nodes", ratio=2)
        )

        return layout

    def _update_layout(self, layout: Layout):
        """Update layout with current data."""
        # Header
        layout["header"].update(create_header())

        # Stats
        stats = self.client.get_mesh_stats()
        layout["stats"].update(create_stats_panel(stats))

        # Nodes
        nodes = self.client.get_nodes()
        if nodes:
            layout["nodes"].update(create_node_table(nodes))
        else:
            layout["nodes"].update(Panel(
                "[dim]No nodes discovered yet...[/dim]\n\nWaiting for heartbeats.",
                title="Active Neurons",
                border_style="dim"
            ))

        # Footer
        footer = Text()
        footer.append(" ESC ", style="bold black on white")
        footer.append(" Exit  ", style="dim")
        footer.append(" R ", style="bold black on white")
        footer.append(" Refresh  ", style="dim")
        footer.append(" H ", style="bold black on white")
        footer.append(" Request Heartbeats  ", style="dim")

        if self.client.is_connected():
            footer.append("\n● Connected", style="green")
            if self.client.connected_device:
                footer.append(f" to {self.client.connected_device.name}", style="dim")
        else:
            footer.append("\n○ Disconnected", style="red")

        layout["footer"].update(Panel(footer, box=box.SIMPLE))

    async def run(self, refresh_rate: float = 1.0):
        """Run the live monitor."""
        self.running = True
        self.client.add_message_handler(self._on_message)

        layout = self._create_layout()

        with Live(layout, console=console, refresh_per_second=4) as live:
            while self.running:
                self._update_layout(layout)

                # Request heartbeats periodically
                if self.client.is_connected():
                    await self.client.request_heartbeats()

                await asyncio.sleep(refresh_rate)

    def stop(self):
        """Stop the monitor."""
        self.running = False


async def quick_status(client: PlanetaryMeshClient):
    """Print a quick status snapshot."""
    console.print(create_header())

    if not client.is_connected():
        console.print("[red]Not connected to mesh[/red]")
        console.print("\nUse 'planetary_cli.py scan' to find devices")
        console.print("Then 'planetary_cli.py connect <address>' to connect")
        return

    # Request heartbeats
    console.print("[dim]Requesting heartbeats...[/dim]")
    await client.request_heartbeats()
    await asyncio.sleep(2)  # Wait for responses

    stats = client.get_mesh_stats()
    console.print(create_stats_panel(stats))

    nodes = client.get_nodes()
    if nodes:
        console.print(create_node_table(nodes))
    else:
        console.print("[yellow]No nodes responded[/yellow]")


def print_coherence_ascii():
    """Print ASCII art coherence visualization."""
    art = """
    ╔═══════════════════════════════════════════╗
    ║          π × φ  RESONANCE FIELD           ║
    ╠═══════════════════════════════════════════╣
    ║                                           ║
    ║      .-'``'-.      .-'``'-.               ║
    ║    .'        '.  .'        '.             ║
    ║   /    ◉       \\/    ◉       \\           ║
    ║  ;              ;              ;          ║
    ║  |    NODE     |    NODE      |          ║
    ║  ;              ;              ;          ║
    ║   \\            /\\            /           ║
    ║    '.        .'  '.        .'             ║
    ║      '-.__.-'      '-.__.-'               ║
    ║           \\          /                    ║
    ║            \\   🧠   /                     ║
    ║             \\      /                      ║
    ║              \\    /                       ║
    ║               \\  /                        ║
    ║                \\/                         ║
    ║              MESH                         ║
    ║            COHERENCE                      ║
    ║                                           ║
    ║    5.083203692315260                     ║
    ║    PHOENIX-TESLA-369-AURORA              ║
    ╚═══════════════════════════════════════════╝
    """
    console.print(art, style="cyan")
