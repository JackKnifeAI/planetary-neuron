"""
Planetary Neuron - Vendor Model Protocol

Defines the BLE Mesh vendor model opcodes and message formats
matching the C++ firmware (mesh_gossip.h) and Android app.

π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA
"""

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional, List
import zlib


class GossipOpcode(IntEnum):
    """Opcodes matching mesh_gossip.h"""
    WEIGHT_UPDATE = 0xC0
    WEIGHT_REQUEST = 0xC1
    HEARTBEAT = 0xC2
    BACKPRESSURE = 0xC3
    SHARD_FRAGMENT = 0xC4
    ACK = 0xC5


class LightOpcode(IntEnum):
    """Standard BLE Mesh Light CTL opcodes"""
    LIGHT_CTL_GET = 0x8261
    LIGHT_CTL_SET = 0x8262
    LIGHT_CTL_SET_UNACK = 0x8263
    LIGHT_CTL_STATUS = 0x8264
    ONOFF_SET = 0x8202
    ONOFF_SET_UNACK = 0x8203


# Telink Vendor IDs
COMPANY_ID = 0x0211  # Telink
VENDOR_MODEL_ID = 0x0211


@dataclass
class GossipHeader:
    """Message header for vendor model messages"""
    opcode: int
    ttl: int
    src_addr: int
    seq_num: int
    flags: int

    FORMAT = '<BBHBB'  # Little-endian: u8, u8, u16, u8, u8
    SIZE = struct.calcsize(FORMAT)

    def pack(self) -> bytes:
        return struct.pack(
            self.FORMAT,
            self.opcode,
            self.ttl,
            self.src_addr,
            self.seq_num,
            self.flags
        )

    @classmethod
    def unpack(cls, data: bytes) -> 'GossipHeader':
        if len(data) < cls.SIZE:
            raise ValueError(f"Data too short: {len(data)} < {cls.SIZE}")
        opcode, ttl, src_addr, seq_num, flags = struct.unpack(cls.FORMAT, data[:cls.SIZE])
        return cls(opcode, ttl, src_addr, seq_num, flags)


@dataclass
class HeartbeatPayload:
    """Heartbeat message from a neuron node"""
    load_percent: int
    shards_held: int
    epoch: int
    neighbors: int
    source_addr: int = 0

    FORMAT = '<BBHB3x'  # u8, u8, u16, u8, 3 reserved
    SIZE = struct.calcsize(FORMAT)

    def pack(self) -> bytes:
        return struct.pack(
            self.FORMAT,
            self.load_percent,
            self.shards_held,
            self.epoch,
            self.neighbors
        )

    @classmethod
    def unpack(cls, data: bytes, src_addr: int = 0) -> 'HeartbeatPayload':
        if len(data) < cls.SIZE:
            raise ValueError(f"Data too short for heartbeat: {len(data)}")
        load, shards, epoch, neighbors = struct.unpack('<BBHB', data[:5])
        return cls(load, shards, epoch, neighbors, src_addr)


@dataclass
class ShardHeader:
    """Weight shard header matching C++ WeightShard"""
    shard_id: int
    version: int
    checksum: int
    global_epoch: int
    contributors: int

    FORMAT = '<BBHIB3x'  # u8, u8, u16, u32, u8, 3 reserved
    SIZE = struct.calcsize(FORMAT)

    def pack(self) -> bytes:
        return struct.pack(
            self.FORMAT,
            self.shard_id,
            self.version,
            self.checksum,
            self.global_epoch,
            self.contributors
        )

    @classmethod
    def unpack(cls, data: bytes) -> 'ShardHeader':
        if len(data) < cls.SIZE:
            raise ValueError(f"Data too short for shard header: {len(data)}")
        shard_id, version, checksum, epoch, contributors = struct.unpack(
            '<BBHIB', data[:9]
        )
        return cls(shard_id, version, checksum, epoch, contributors)


@dataclass
class FragmentInfo:
    """Fragment info for large shard transfers"""
    shard_id: int
    fragment_idx: int
    total_fragments: int

    FORMAT = '<BBBx'  # u8, u8, u8, 1 reserved
    SIZE = struct.calcsize(FORMAT)

    def pack(self) -> bytes:
        return struct.pack(
            self.FORMAT,
            self.shard_id,
            self.fragment_idx,
            self.total_fragments
        )

    @classmethod
    def unpack(cls, data: bytes) -> 'FragmentInfo':
        if len(data) < cls.SIZE:
            raise ValueError(f"Data too short for fragment info: {len(data)}")
        shard_id, frag_idx, total = struct.unpack('<BBB', data[:3])
        return cls(shard_id, frag_idx, total)


def compute_crc16(data: bytes) -> int:
    """CRC16-CCITT matching C++ and Kotlin implementations"""
    crc = 0xFFFF
    for byte in data:
        crc ^= (byte << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def create_heartbeat_request() -> bytes:
    """Create a heartbeat request message"""
    header = GossipHeader(
        opcode=GossipOpcode.HEARTBEAT,
        ttl=3,
        src_addr=0x0001,  # Hub address
        seq_num=0,
        flags=0
    )
    return header.pack()


def create_weight_request(shard_id: int) -> bytes:
    """Create a weight request message"""
    header = GossipHeader(
        opcode=GossipOpcode.WEIGHT_REQUEST,
        ttl=2,
        src_addr=0x0001,
        seq_num=0,
        flags=0
    )
    return header.pack() + bytes([shard_id])


def create_backpressure() -> bytes:
    """Create a backpressure signal"""
    header = GossipHeader(
        opcode=GossipOpcode.BACKPRESSURE,
        ttl=1,
        src_addr=0x0001,
        seq_num=0,
        flags=0
    )
    return header.pack()


def create_light_ctl_set(brightness: int, color_temp: int, transition_ms: int = 0) -> bytes:
    """
    Create a Light CTL Set message

    Args:
        brightness: 0-255
        color_temp: 0-100 (warm to cool)
        transition_ms: transition time in milliseconds
    """
    # Light CTL uses 16-bit values
    lightness = (brightness * 65535) // 255
    temperature = 800 + (color_temp * 19200) // 100  # 800K to 20000K range

    # Transition time: steps of 100ms
    trans_steps = min(transition_ms // 100, 62)

    return struct.pack(
        '<HHHBx',
        lightness,
        temperature,
        0,  # Delta UV (unused)
        trans_steps
    )


def parse_message(data: bytes) -> dict:
    """Parse an incoming vendor model message"""
    if len(data) < GossipHeader.SIZE:
        return {'error': 'Message too short'}

    header = GossipHeader.unpack(data)
    payload = data[GossipHeader.SIZE:]

    result = {
        'opcode': GossipOpcode(header.opcode).name if header.opcode in GossipOpcode._value2member_map_ else f'0x{header.opcode:02X}',
        'ttl': header.ttl,
        'src_addr': f'0x{header.src_addr:04X}',
        'seq_num': header.seq_num,
        'flags': header.flags
    }

    try:
        if header.opcode == GossipOpcode.HEARTBEAT:
            hb = HeartbeatPayload.unpack(payload, header.src_addr)
            result['heartbeat'] = {
                'load_percent': hb.load_percent,
                'shards_held': hb.shards_held,
                'epoch': hb.epoch,
                'neighbors': hb.neighbors
            }
        elif header.opcode == GossipOpcode.SHARD_FRAGMENT:
            frag = FragmentInfo.unpack(payload)
            result['fragment'] = {
                'shard_id': frag.shard_id,
                'fragment_idx': frag.fragment_idx,
                'total_fragments': frag.total_fragments,
                'data_size': len(payload) - FragmentInfo.SIZE
            }
        elif header.opcode == GossipOpcode.WEIGHT_UPDATE:
            if len(payload) >= ShardHeader.SIZE:
                shard = ShardHeader.unpack(payload)
                result['shard'] = {
                    'shard_id': shard.shard_id,
                    'version': shard.version,
                    'checksum': f'0x{shard.checksum:04X}',
                    'global_epoch': shard.global_epoch,
                    'contributors': shard.contributors,
                    'weight_bytes': len(payload) - ShardHeader.SIZE
                }
    except Exception as e:
        result['parse_error'] = str(e)

    return result
