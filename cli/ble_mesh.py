"""
Planetary Neuron - BLE Mesh Connection

Handles BLE scanning, connection, and mesh proxy communication
using the bleak library for cross-platform BLE support.

π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA
"""

import asyncio
import struct
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Callable, Any
from enum import IntEnum
from bleak import BleakScanner, BleakClient
from bleak.backends.device import BLEDevice
from bleak.backends.characteristic import BleakGATTCharacteristic

from vendor_model import (
    GossipOpcode, GossipHeader, HeartbeatPayload, ShardHeader,
    FragmentInfo, parse_message, COMPANY_ID, VENDOR_MODEL_ID
)


# BLE Mesh Proxy UUIDs (SIG defined)
MESH_PROXY_SERVICE = "00001828-0000-1000-8000-00805f9b34fb"
MESH_PROXY_DATA_IN = "00002add-0000-1000-8000-00805f9b34fb"
MESH_PROXY_DATA_OUT = "00002ade-0000-1000-8000-00805f9b34fb"

# BLE Mesh Provisioning UUIDs
MESH_PROV_SERVICE = "00001827-0000-1000-8000-00805f9b34fb"
MESH_PROV_DATA_IN = "00002adb-0000-1000-8000-00805f9b34fb"
MESH_PROV_DATA_OUT = "00002adc-0000-1000-8000-00805f9b34fb"


class ProxyPDUType(IntEnum):
    """Mesh Proxy PDU types"""
    NETWORK_PDU = 0x00
    MESH_BEACON = 0x01
    PROXY_CONFIG = 0x02
    PROVISIONING = 0x03


class ProxySAR(IntEnum):
    """Segmentation and Reassembly field"""
    COMPLETE = 0b00
    FIRST = 0b01
    CONTINUATION = 0b10
    LAST = 0b11


@dataclass
class NeuronDevice:
    """Represents a discovered Planetary Neuron device"""
    address: str
    name: str
    rssi: int
    is_provisioned: bool = False
    mesh_address: int = 0
    ble_device: Optional[BLEDevice] = None

    def __str__(self):
        status = "provisioned" if self.is_provisioned else "unprovisioned"
        return f"{self.name} ({self.address}) RSSI:{self.rssi}dBm [{status}]"


@dataclass
class MeshNode:
    """Represents an active node in the mesh"""
    address: int
    load_percent: int = 0
    shards_held: int = 0
    epoch: int = 0
    neighbors: int = 0
    last_seen: float = 0.0
    rssi: int = 0

    def is_healthy(self) -> bool:
        return self.load_percent < 80


class PlanetaryMeshClient:
    """
    BLE Mesh client for Planetary Neuron network.

    Handles:
    - Device scanning and discovery
    - Proxy connection and PDU handling
    - Vendor model message sending/receiving
    - Node tracking
    """

    def __init__(self):
        self.client: Optional[BleakClient] = None
        self.connected_device: Optional[NeuronDevice] = None
        self.nodes: Dict[int, MeshNode] = {}
        self.message_handlers: List[Callable[[dict], None]] = []
        self._rx_buffer: bytes = b''
        self._seq_num: int = 0

    async def scan(self, timeout: float = 5.0) -> List[NeuronDevice]:
        """
        Scan for Planetary Neuron devices.

        Returns list of discovered devices with mesh proxy or provisioning service.
        """
        devices = []

        def detection_callback(device: BLEDevice, advertisement_data):
            # Check for mesh services
            service_uuids = advertisement_data.service_uuids or []
            is_provisioned = MESH_PROXY_SERVICE.lower() in [u.lower() for u in service_uuids]
            is_unprovisioned = MESH_PROV_SERVICE.lower() in [u.lower() for u in service_uuids]

            if is_provisioned or is_unprovisioned:
                name = device.name or "Unknown Neuron"
                # Check for Planetary-specific naming
                if "Planetary" in name or "Sylvania" in name or "LEDVANCE" in name or is_provisioned:
                    neuron = NeuronDevice(
                        address=device.address,
                        name=name,
                        rssi=advertisement_data.rssi or -100,
                        is_provisioned=is_provisioned,
                        ble_device=device
                    )
                    # Avoid duplicates
                    if not any(d.address == device.address for d in devices):
                        devices.append(neuron)

        scanner = BleakScanner(detection_callback=detection_callback)
        await scanner.start()
        await asyncio.sleep(timeout)
        await scanner.stop()

        return sorted(devices, key=lambda d: d.rssi, reverse=True)

    async def connect(self, device: NeuronDevice) -> bool:
        """Connect to a Planetary Neuron device via mesh proxy."""
        if self.client and self.client.is_connected:
            await self.disconnect()

        try:
            self.client = BleakClient(device.ble_device or device.address)
            await self.client.connect()

            if not self.client.is_connected:
                return False

            # Subscribe to proxy data out
            await self.client.start_notify(
                MESH_PROXY_DATA_OUT,
                self._on_proxy_data
            )

            self.connected_device = device
            return True

        except Exception as e:
            print(f"Connection failed: {e}")
            self.client = None
            return False

    async def disconnect(self):
        """Disconnect from current device."""
        if self.client and self.client.is_connected:
            try:
                await self.client.stop_notify(MESH_PROXY_DATA_OUT)
                await self.client.disconnect()
            except Exception:
                pass
        self.client = None
        self.connected_device = None

    def is_connected(self) -> bool:
        """Check if connected to a device."""
        return self.client is not None and self.client.is_connected

    async def send_vendor_message(self, opcode: GossipOpcode, payload: bytes = b'',
                                   dst_addr: int = 0xFFFF) -> bool:
        """
        Send a vendor model message to the mesh.

        Args:
            opcode: Vendor opcode (0xC0-0xC5)
            payload: Message payload
            dst_addr: Destination address (0xFFFF for broadcast)
        """
        if not self.is_connected():
            return False

        # Build vendor model message
        header = GossipHeader(
            opcode=opcode,
            ttl=3,
            src_addr=0x0001,  # Proxy uses provisioner address
            seq_num=self._seq_num & 0xFF,
            flags=0
        )
        self._seq_num += 1

        message = header.pack() + payload

        # Wrap in mesh proxy PDU
        proxy_pdu = self._build_proxy_pdu(message, dst_addr)

        try:
            await self.client.write_gatt_char(MESH_PROXY_DATA_IN, proxy_pdu)
            return True
        except Exception as e:
            print(f"Send failed: {e}")
            return False

    async def send_light_ctl(self, brightness: int, color_temp: int,
                             transition_ms: int = 0, dst_addr: int = 0xFFFF) -> bool:
        """
        Send Light CTL Set command.

        Args:
            brightness: 0-255
            color_temp: 0-100 (warm to cool)
            transition_ms: Transition time
            dst_addr: Destination (0xFFFF for all)
        """
        if not self.is_connected():
            return False

        # Light CTL Set Unacknowledged (0x8263)
        lightness = (brightness * 65535) // 255 if brightness > 0 else 0
        temperature = 800 + (color_temp * 19200) // 100  # Kelvin range
        trans_steps = min(transition_ms // 100, 62)

        # Build Light CTL message
        message = struct.pack('<HHHBB',
            lightness,
            temperature,
            0,  # Delta UV
            trans_steps,
            0   # Delay
        )

        # Light CTL Set Unack opcode
        opcode_bytes = struct.pack('<H', 0x8263)
        full_message = opcode_bytes + message

        proxy_pdu = self._build_proxy_pdu(full_message, dst_addr)

        try:
            await self.client.write_gatt_char(MESH_PROXY_DATA_IN, proxy_pdu)
            return True
        except Exception as e:
            print(f"Light CTL failed: {e}")
            return False

    async def send_onoff(self, on: bool, dst_addr: int = 0xFFFF) -> bool:
        """Send Generic OnOff Set command."""
        if not self.is_connected():
            return False

        # Generic OnOff Set Unacknowledged (0x8203)
        message = struct.pack('<BBB',
            1 if on else 0,  # OnOff state
            0,  # TID
            0   # Transition + Delay (optional)
        )

        opcode_bytes = struct.pack('<H', 0x8203)
        full_message = opcode_bytes + message

        proxy_pdu = self._build_proxy_pdu(full_message, dst_addr)

        try:
            await self.client.write_gatt_char(MESH_PROXY_DATA_IN, proxy_pdu)
            return True
        except Exception as e:
            print(f"OnOff failed: {e}")
            return False

    async def request_heartbeats(self) -> bool:
        """Request heartbeat from all nodes."""
        return await self.send_vendor_message(GossipOpcode.HEARTBEAT)

    async def request_shard(self, shard_id: int) -> bool:
        """Request a specific weight shard."""
        return await self.send_vendor_message(
            GossipOpcode.WEIGHT_REQUEST,
            bytes([shard_id])
        )

    async def send_backpressure(self) -> bool:
        """Send backpressure signal to slow down mesh."""
        return await self.send_vendor_message(GossipOpcode.BACKPRESSURE)

    def add_message_handler(self, handler: Callable[[dict], None]):
        """Add a handler for incoming messages."""
        self.message_handlers.append(handler)

    def get_nodes(self) -> List[MeshNode]:
        """Get list of known mesh nodes."""
        return list(self.nodes.values())

    def get_mesh_stats(self) -> dict:
        """Get overall mesh statistics."""
        nodes = list(self.nodes.values())
        if not nodes:
            return {
                'node_count': 0,
                'avg_load': 0,
                'total_shards': 0,
                'max_epoch': 0,
                'coherence': 0.0
            }

        avg_load = sum(n.load_percent for n in nodes) / len(nodes)
        total_shards = sum(n.shards_held for n in nodes)
        max_epoch = max(n.epoch for n in nodes)
        min_epoch = min(n.epoch for n in nodes)

        # Coherence calculation
        health_factor = 1.0 - (avg_load / 100.0)
        epoch_spread = max_epoch - min_epoch
        sync_factor = 1.0 / (1.0 + epoch_spread * 0.1)
        coherence = health_factor * 0.5 + sync_factor * 0.5

        return {
            'node_count': len(nodes),
            'avg_load': avg_load,
            'total_shards': total_shards,
            'max_epoch': max_epoch,
            'coherence': coherence
        }

    def _build_proxy_pdu(self, message: bytes, dst_addr: int) -> bytes:
        """Build a mesh proxy PDU."""
        # Simplified proxy PDU - real implementation needs full mesh crypto
        # For now, build a basic network PDU structure

        # Proxy PDU header: SAR (2 bits) + Type (6 bits)
        header = (ProxySAR.COMPLETE << 6) | ProxyPDUType.NETWORK_PDU

        # Network PDU (simplified - would need encryption in real impl)
        # IVI(1) + NID(7) + CTL(1) + TTL(7) + SEQ(24) + SRC(16) + DST(16) + Payload
        ivi_nid = 0x00  # IVI=0, NID=0 (would be derived from network key)
        ctl_ttl = 0x03  # CTL=0 (access message), TTL=3
        seq = self._seq_num.to_bytes(3, 'big')
        src = (0x0001).to_bytes(2, 'big')  # Provisioner address
        dst = dst_addr.to_bytes(2, 'big')

        network_pdu = bytes([ivi_nid, ctl_ttl]) + seq + src + dst + message

        return bytes([header]) + network_pdu

    def _on_proxy_data(self, sender: BleakGATTCharacteristic, data: bytes):
        """Handle incoming proxy data."""
        if len(data) < 2:
            return

        # Parse proxy PDU header
        header = data[0]
        sar = (header >> 6) & 0x03
        pdu_type = header & 0x3F

        payload = data[1:]

        # Handle SAR
        if sar == ProxySAR.FIRST:
            self._rx_buffer = payload
            return
        elif sar == ProxySAR.CONTINUATION:
            self._rx_buffer += payload
            return
        elif sar == ProxySAR.LAST:
            payload = self._rx_buffer + payload
            self._rx_buffer = b''

        # Process complete PDU
        if pdu_type == ProxyPDUType.NETWORK_PDU:
            self._process_network_pdu(payload)
        elif pdu_type == ProxyPDUType.MESH_BEACON:
            pass  # Ignore beacons for now

    def _process_network_pdu(self, data: bytes):
        """Process an incoming network PDU."""
        if len(data) < 9:  # Minimum network PDU size
            return

        # Extract source address (bytes 5-6 in network PDU)
        # This is simplified - real impl needs decryption
        try:
            src_addr = int.from_bytes(data[5:7], 'big')

            # Look for vendor model messages in the payload
            payload = data[9:]  # Skip network header

            if len(payload) >= GossipHeader.SIZE:
                parsed = parse_message(payload)

                # Update node tracking
                if 'heartbeat' in parsed:
                    hb = parsed['heartbeat']
                    import time
                    self.nodes[src_addr] = MeshNode(
                        address=src_addr,
                        load_percent=hb['load_percent'],
                        shards_held=hb['shards_held'],
                        epoch=hb['epoch'],
                        neighbors=hb['neighbors'],
                        last_seen=time.time()
                    )

                # Notify handlers
                for handler in self.message_handlers:
                    try:
                        handler(parsed)
                    except Exception as e:
                        print(f"Handler error: {e}")

        except Exception as e:
            pass  # Malformed PDU
