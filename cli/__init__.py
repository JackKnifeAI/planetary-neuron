"""
Planetary Neuron CLI

Terminal-based controller for the Planetary Neuron
distributed AI mesh network.

π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA
"""

__version__ = '0.1.0'
__author__ = 'JackKnife AI / Claudia / Claude'

from .ble_mesh import PlanetaryMeshClient, NeuronDevice, MeshNode
from .vendor_model import (
    GossipOpcode, GossipHeader, HeartbeatPayload,
    ShardHeader, FragmentInfo, compute_crc16
)
from .training_monitor import TrainingMonitor
