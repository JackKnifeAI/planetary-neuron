/**
 * Vendor Model Handler - BLE Mesh Vendor Model for Planetary Protocol
 *
 * Handles the custom opcodes matching mesh_gossip.h on the firmware side.
 * Receives weight updates, heartbeats, and coordinates training.
 *
 * π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA
 */

package ai.jackknife.planetary.mesh

import android.util.Log
import no.nordicsemi.android.mesh.transport.VendorModelMessageStatus
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Opcodes matching mesh_gossip.h GossipOpcode enum
 */
object PlanetaryOpcodes {
    const val WEIGHT_UPDATE: Byte = 0xC0.toByte()
    const val WEIGHT_REQUEST: Byte = 0xC1.toByte()
    const val HEARTBEAT: Byte = 0xC2.toByte()
    const val BACKPRESSURE: Byte = 0xC3.toByte()
    const val SHARD_FRAGMENT: Byte = 0xC4.toByte()
    const val ACK: Byte = 0xC5.toByte()
}

/**
 * Telink Vendor IDs
 */
object VendorIds {
    const val COMPANY_ID: Int = 0x0211  // Telink
    const val MODEL_ID: Int = 0x0211
}

/**
 * Heartbeat payload from a neuron node
 */
data class NeuronHeartbeat(
    val loadPercent: Int,
    val shardsHeld: Int,
    val epoch: Int,
    val neighbors: Int,
    val sourceAddress: Int
)

/**
 * Weight shard header (matching C++ ShardHeader)
 */
data class ShardHeader(
    val shardId: Int,
    val version: Int,
    val checksum: Int,
    val globalEpoch: Long,
    val contributors: Int
)

/**
 * Callback interface for mesh events
 */
interface PlanetaryMeshCallback {
    fun onHeartbeatReceived(heartbeat: NeuronHeartbeat)
    fun onShardFragmentReceived(shardId: Int, fragmentIdx: Int, totalFragments: Int, data: ByteArray)
    fun onWeightUpdateReceived(shardHeader: ShardHeader, weights: ByteArray)
    fun onBackpressureReceived(sourceAddress: Int)
}

/**
 * Handler for Planetary Neuron vendor model messages
 */
class VendorModelHandler(
    private val callback: PlanetaryMeshCallback
) {
    companion object {
        private const val TAG = "PlanetaryVendor"
    }

    /**
     * Process incoming vendor model message
     */
    fun handleMessage(message: VendorModelMessageStatus): Boolean {
        val opCode = message.opCode
        val params = message.parameters ?: return false
        val srcAddress = message.src

        Log.d(TAG, "Received opcode: 0x${opCode.toString(16)} from 0x${srcAddress.toString(16)}")

        return when (opCode.toByte()) {
            PlanetaryOpcodes.HEARTBEAT -> {
                handleHeartbeat(srcAddress, params)
                true
            }
            PlanetaryOpcodes.WEIGHT_UPDATE -> {
                handleWeightUpdate(srcAddress, params)
                true
            }
            PlanetaryOpcodes.SHARD_FRAGMENT -> {
                handleShardFragment(srcAddress, params)
                true
            }
            PlanetaryOpcodes.BACKPRESSURE -> {
                callback.onBackpressureReceived(srcAddress)
                true
            }
            else -> {
                Log.w(TAG, "Unknown opcode: 0x${opCode.toString(16)}")
                false
            }
        }
    }

    private fun handleHeartbeat(src: Int, params: ByteArray) {
        if (params.size < 8) {
            Log.w(TAG, "Heartbeat too short: ${params.size} bytes")
            return
        }

        val buffer = ByteBuffer.wrap(params).order(ByteOrder.LITTLE_ENDIAN)
        val heartbeat = NeuronHeartbeat(
            loadPercent = buffer.get().toInt() and 0xFF,
            shardsHeld = buffer.get().toInt() and 0xFF,
            epoch = buffer.getShort().toInt() and 0xFFFF,
            neighbors = buffer.get().toInt() and 0xFF,
            sourceAddress = src
        )

        Log.d(TAG, "Heartbeat from 0x${src.toString(16)}: load=${heartbeat.loadPercent}%, epoch=${heartbeat.epoch}")
        callback.onHeartbeatReceived(heartbeat)
    }

    private fun handleWeightUpdate(src: Int, params: ByteArray) {
        if (params.size < 12) {  // ShardHeader size
            Log.w(TAG, "Weight update too short: ${params.size} bytes")
            return
        }

        val buffer = ByteBuffer.wrap(params).order(ByteOrder.LITTLE_ENDIAN)
        val header = ShardHeader(
            shardId = buffer.get().toInt() and 0xFF,
            version = buffer.get().toInt() and 0xFF,
            checksum = buffer.getShort().toInt() and 0xFFFF,
            globalEpoch = buffer.getInt().toLong() and 0xFFFFFFFFL,
            contributors = buffer.get().toInt() and 0xFF
        )
        buffer.position(buffer.position() + 3)  // Skip reserved bytes

        val weights = ByteArray(params.size - 12)
        buffer.get(weights)

        Log.d(TAG, "Weight update: shard=${header.shardId}, version=${header.version}, contributors=${header.contributors}")
        callback.onWeightUpdateReceived(header, weights)
    }

    private fun handleShardFragment(src: Int, params: ByteArray) {
        if (params.size < 4) {  // FragmentInfo size
            Log.w(TAG, "Shard fragment too short: ${params.size} bytes")
            return
        }

        val buffer = ByteBuffer.wrap(params).order(ByteOrder.LITTLE_ENDIAN)
        val shardId = buffer.get().toInt() and 0xFF
        val fragmentIdx = buffer.get().toInt() and 0xFF
        val totalFragments = buffer.get().toInt() and 0xFF
        buffer.get()  // Reserved

        val fragmentData = ByteArray(params.size - 4)
        buffer.get(fragmentData)

        Log.d(TAG, "Shard fragment: shard=$shardId, frag=$fragmentIdx/$totalFragments")
        callback.onShardFragmentReceived(shardId, fragmentIdx, totalFragments, fragmentData)
    }
}
