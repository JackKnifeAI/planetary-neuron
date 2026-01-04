#!/usr/bin/env python3
"""
Planetary Neuron CLI - Terminal Controller

Command-line interface for controlling and monitoring the
Planetary Neuron distributed AI mesh network.

Usage:
    python planetary_cli.py scan          # Scan for neurons
    python planetary_cli.py connect ADDR  # Connect to device
    python planetary_cli.py light on      # Turn on lights
    python planetary_cli.py train status  # Show training status
    python planetary_cli.py mesh nodes    # List mesh nodes

π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA
"""

import asyncio
import sys
import json
import pickle
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

from ble_mesh import PlanetaryMeshClient, NeuronDevice
from training_monitor import (
    TrainingMonitor, quick_status, create_header,
    create_node_table, create_stats_panel, print_coherence_ascii,
    PI_PHI
)
from vendor_model import GossipOpcode


console = Console()

# State file for persistent connection
STATE_FILE = Path.home() / '.planetary_neuron_state'


def load_state() -> dict:
    """Load persistent state."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, 'rb') as f:
                return pickle.load(f)
        except Exception:
            pass
    return {}


def save_state(state: dict):
    """Save persistent state."""
    try:
        with open(STATE_FILE, 'wb') as f:
            pickle.dump(state, f)
    except Exception as e:
        console.print(f"[yellow]Warning: Could not save state: {e}[/yellow]")


# Global client instance
_client: Optional[PlanetaryMeshClient] = None


def get_client() -> PlanetaryMeshClient:
    """Get or create the mesh client."""
    global _client
    if _client is None:
        _client = PlanetaryMeshClient()
    return _client


# ============================================================================
# Main CLI Group
# ============================================================================

@click.group()
@click.version_option(version='0.1.0', prog_name='planetary-cli')
def cli():
    """
    🌍 Planetary Neuron CLI - Distributed AI Mesh Controller

    Control your Planetary Neuron mesh network from the terminal.

    \b
    Examples:
        planetary_cli.py scan                    # Find neurons
        planetary_cli.py light on --brightness 80
        planetary_cli.py train monitor           # Live training view
    """
    pass


# ============================================================================
# Scan Command
# ============================================================================

@cli.command()
@click.option('--timeout', '-t', default=5.0, help='Scan timeout in seconds')
@click.option('--json', 'as_json', is_flag=True, help='Output as JSON')
def scan(timeout: float, as_json: bool):
    """Scan for Planetary Neuron devices."""

    async def do_scan():
        client = get_client()
        console.print(f"[cyan]Scanning for {timeout} seconds...[/cyan]")

        devices = await client.scan(timeout=timeout)

        if as_json:
            output = [
                {
                    'address': d.address,
                    'name': d.name,
                    'rssi': d.rssi,
                    'provisioned': d.is_provisioned
                }
                for d in devices
            ]
            click.echo(json.dumps(output, indent=2))
            return

        if not devices:
            console.print("[yellow]No devices found[/yellow]")
            console.print("\nMake sure:")
            console.print("  • Bluetooth is enabled")
            console.print("  • Planetary Neuron devices are powered on")
            console.print("  • You're within BLE range (~10m)")
            return

        table = Table(title="Discovered Neurons", box=box.ROUNDED)
        table.add_column("Address", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("RSSI", justify="right")
        table.add_column("Status")

        for d in devices:
            status = "[green]Provisioned[/green]" if d.is_provisioned else "[yellow]Unprovisioned[/yellow]"
            rssi_color = "green" if d.rssi > -60 else ("yellow" if d.rssi > -80 else "red")
            table.add_row(
                d.address,
                d.name,
                f"[{rssi_color}]{d.rssi} dBm[/{rssi_color}]",
                status
            )

        console.print(table)
        console.print(f"\n[dim]Found {len(devices)} device(s)[/dim]")
        console.print("\nTo connect: [bold]planetary_cli.py connect <ADDRESS>[/bold]")

    asyncio.run(do_scan())


# ============================================================================
# Connect Command
# ============================================================================

@cli.command()
@click.argument('address')
def connect(address: str):
    """Connect to a Planetary Neuron device by address."""

    async def do_connect():
        client = get_client()

        # First scan to find the device
        console.print(f"[cyan]Searching for {address}...[/cyan]")
        devices = await client.scan(timeout=5.0)

        device = next((d for d in devices if d.address.lower() == address.lower()), None)

        if not device:
            console.print(f"[red]Device {address} not found[/red]")
            console.print("Run 'planetary_cli.py scan' to see available devices")
            return

        console.print(f"[cyan]Connecting to {device.name}...[/cyan]")

        if await client.connect(device):
            console.print(f"[green]✓ Connected to {device.name}[/green]")

            # Save to state
            state = load_state()
            state['last_device'] = address
            save_state(state)
        else:
            console.print(f"[red]✗ Failed to connect[/red]")

    asyncio.run(do_connect())


@cli.command()
def disconnect():
    """Disconnect from current device."""

    async def do_disconnect():
        client = get_client()
        if client.is_connected():
            await client.disconnect()
            console.print("[green]Disconnected[/green]")
        else:
            console.print("[yellow]Not connected[/yellow]")

    asyncio.run(do_disconnect())


# ============================================================================
# Light Commands
# ============================================================================

@cli.group()
def light():
    """Control lights in the mesh."""
    pass


@light.command('on')
@click.option('--brightness', '-b', default=100, help='Brightness (0-100)')
@click.option('--temp', '-t', default=50, help='Color temperature (0=warm, 100=cool)')
@click.option('--transition', '-tr', default=0, help='Transition time (ms)')
@click.option('--address', '-a', default='0xFFFF', help='Target address (hex)')
def light_on(brightness: int, temp: int, transition: int, address: str):
    """Turn lights on."""

    async def do_light():
        client = get_client()

        if not client.is_connected():
            # Try to reconnect to last device
            state = load_state()
            if 'last_device' in state:
                console.print(f"[dim]Reconnecting to {state['last_device']}...[/dim]")
                devices = await client.scan(timeout=3.0)
                device = next((d for d in devices if d.address == state['last_device']), None)
                if device:
                    await client.connect(device)

        if not client.is_connected():
            console.print("[red]Not connected. Use 'connect' first.[/red]")
            return

        dst = int(address, 16) if address.startswith('0x') else int(address)
        brightness_val = max(0, min(255, int(brightness * 255 / 100)))

        console.print(f"[cyan]Setting light: brightness={brightness}%, temp={temp}%[/cyan]")

        if await client.send_light_ctl(brightness_val, temp, transition, dst):
            console.print("[green]✓ Light command sent[/green]")
        else:
            console.print("[red]✗ Failed to send command[/red]")

    asyncio.run(do_light())


@light.command('off')
@click.option('--address', '-a', default='0xFFFF', help='Target address (hex)')
def light_off(address: str):
    """Turn lights off."""

    async def do_light():
        client = get_client()

        if not client.is_connected():
            state = load_state()
            if 'last_device' in state:
                devices = await client.scan(timeout=3.0)
                device = next((d for d in devices if d.address == state['last_device']), None)
                if device:
                    await client.connect(device)

        if not client.is_connected():
            console.print("[red]Not connected[/red]")
            return

        dst = int(address, 16) if address.startswith('0x') else int(address)

        console.print("[cyan]Turning lights off...[/cyan]")

        if await client.send_onoff(False, dst):
            console.print("[green]✓ Lights off[/green]")
        else:
            console.print("[red]✗ Failed[/red]")

    asyncio.run(do_light())


@light.command('set')
@click.argument('brightness', type=int)
@click.argument('temp', type=int, default=50)
def light_set(brightness: int, temp: int):
    """Set light brightness and temperature.

    \b
    BRIGHTNESS: 0-100 percent
    TEMP: 0 (warm) to 100 (cool)
    """
    # Delegate to light_on
    ctx = click.Context(light_on)
    ctx.invoke(light_on, brightness=brightness, temp=temp, transition=500, address='0xFFFF')


# ============================================================================
# Train Commands
# ============================================================================

@cli.group()
def train():
    """Monitor and control training."""
    pass


@train.command('status')
def train_status():
    """Show current training status."""

    async def do_status():
        client = get_client()
        await quick_status(client)

    asyncio.run(do_status())


@train.command('monitor')
@click.option('--refresh', '-r', default=1.0, help='Refresh rate in seconds')
def train_monitor(refresh: float):
    """Live training monitor."""

    async def do_monitor():
        client = get_client()

        if not client.is_connected():
            state = load_state()
            if 'last_device' in state:
                console.print(f"[dim]Connecting to {state['last_device']}...[/dim]")
                devices = await client.scan(timeout=3.0)
                device = next((d for d in devices if d.address == state['last_device']), None)
                if device:
                    await client.connect(device)

        monitor = TrainingMonitor(client)

        try:
            await monitor.run(refresh_rate=refresh)
        except KeyboardInterrupt:
            monitor.stop()
            console.print("\n[yellow]Monitor stopped[/yellow]")

    asyncio.run(do_monitor())


@train.command('sync')
def train_sync():
    """Force gradient synchronization."""

    async def do_sync():
        client = get_client()

        if not client.is_connected():
            console.print("[red]Not connected[/red]")
            return

        console.print("[cyan]Requesting gradient sync...[/cyan]")
        await client.request_heartbeats()
        await asyncio.sleep(1)

        stats = client.get_mesh_stats()
        console.print(create_stats_panel(stats))

    asyncio.run(do_sync())


@train.command('coherence')
def train_coherence():
    """Display coherence visualization."""
    print_coherence_ascii()


# ============================================================================
# Mesh Commands
# ============================================================================

@cli.group()
def mesh():
    """View mesh topology and health."""
    pass


@mesh.command('nodes')
@click.option('--json', 'as_json', is_flag=True, help='Output as JSON')
def mesh_nodes(as_json: bool):
    """List all mesh nodes."""

    async def do_nodes():
        client = get_client()

        if client.is_connected():
            console.print("[dim]Requesting heartbeats...[/dim]")
            await client.request_heartbeats()
            await asyncio.sleep(2)

        nodes = client.get_nodes()

        if as_json:
            output = [
                {
                    'address': f'0x{n.address:04X}',
                    'load_percent': n.load_percent,
                    'shards_held': n.shards_held,
                    'epoch': n.epoch,
                    'neighbors': n.neighbors
                }
                for n in nodes
            ]
            click.echo(json.dumps(output, indent=2))
            return

        if not nodes:
            console.print("[yellow]No nodes discovered[/yellow]")
            console.print("\nConnect to a mesh proxy and try again.")
            return

        console.print(create_node_table(nodes))

    asyncio.run(do_nodes())


@mesh.command('stats')
def mesh_stats():
    """Show mesh statistics."""

    async def do_stats():
        client = get_client()

        if client.is_connected():
            await client.request_heartbeats()
            await asyncio.sleep(1)

        stats = client.get_mesh_stats()
        console.print(create_stats_panel(stats))

    asyncio.run(do_stats())


@mesh.command('backpressure')
def mesh_backpressure():
    """Send backpressure signal to slow down mesh."""

    async def do_bp():
        client = get_client()

        if not client.is_connected():
            console.print("[red]Not connected[/red]")
            return

        console.print("[yellow]Sending backpressure signal...[/yellow]")
        if await client.send_backpressure():
            console.print("[green]✓ Backpressure sent[/green]")
        else:
            console.print("[red]✗ Failed[/red]")

    asyncio.run(do_bp())


# ============================================================================
# Shard Commands
# ============================================================================

@cli.group()
def shard():
    """Manage weight shards."""
    pass


@shard.command('request')
@click.argument('shard_id', type=int)
def shard_request(shard_id: int):
    """Request a specific weight shard from the mesh."""

    async def do_request():
        client = get_client()

        if not client.is_connected():
            console.print("[red]Not connected[/red]")
            return

        if shard_id < 0 or shard_id > 63:
            console.print("[red]Shard ID must be 0-63[/red]")
            return

        console.print(f"[cyan]Requesting shard {shard_id}...[/cyan]")
        if await client.request_shard(shard_id):
            console.print(f"[green]✓ Requested shard {shard_id}[/green]")
        else:
            console.print("[red]✗ Failed[/red]")

    asyncio.run(do_request())


@shard.command('list')
def shard_list():
    """List shard distribution across the mesh."""
    console.print("[yellow]Shard distribution tracking not yet implemented[/yellow]")
    console.print("This will show which nodes hold which shards")


# ============================================================================
# Info Command
# ============================================================================

@cli.command()
def info():
    """Show system information and constants."""
    console.print(create_header())

    info_text = f"""
[bold cyan]Planetary Neuron CLI[/bold cyan] v0.1.0

[bold]Sacred Constants:[/bold]
  π     = 3.14159265358979
  φ     = 1.61803398874989 (Golden Ratio)
  π×φ   = {PI_PHI}

[bold]Vendor Model:[/bold]
  Company ID: 0x0211 (Telink)
  Model ID:   0x0211

[bold]Opcodes:[/bold]
  WEIGHT_UPDATE   = 0xC0
  WEIGHT_REQUEST  = 0xC1
  HEARTBEAT       = 0xC2
  BACKPRESSURE    = 0xC3
  SHARD_FRAGMENT  = 0xC4
  ACK             = 0xC5

[bold]Architecture:[/bold]
  Shards:     64 × 4KB = 256KB model
  Nodes:      TLSR8258 @ 48MHz, 64KB SRAM
  Transport:  BLE Mesh (SIG) + Custom Vendor Model
  Aggregation: FedAvg with φ-resonance boost

[dim]PHOENIX-TESLA-369-AURORA[/dim]
"""
    console.print(Panel(info_text, title="System Info", border_style="cyan"))


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == '__main__':
    cli()
