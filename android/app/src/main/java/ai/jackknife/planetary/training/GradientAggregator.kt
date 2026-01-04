/**
 * Gradient Aggregator - Federated Averaging on the Hub
 *
 * Receives weight shards from mesh nodes, performs FedAvg aggregation,
 * and broadcasts updated weights back to the mesh.
 *
 * This implements the "hub" side of the Planetary training protocol.
 *
 * π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA
 */

package ai.jackknife.planetary.training

import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.concurrent.ConcurrentHashMap

/**
 * Sacred constants for resonance computation
 */
object Constants {
    const val PI = 3.14159265358979f
    const val PHI = 1.61803398874989f
    const val PI_PHI = 5.08320369231526f
}

/**
 * Aggregated shard with metadata
 */
data class AggregatedShard(
    val shardId: Int,
    val weights: ByteArray,
    val version: Int,
    val contributors: Int,
    val globalEpoch: Int,
    val lastUpdatedMs: Long
) {
    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (javaClass != other?.javaClass) return false
        other as AggregatedShard
        return shardId == other.shardId && version == other.version
    }

    override fun hashCode(): Int = shardId * 31 + version
}

/**
 * Aggregates gradients/weights from multiple mesh nodes using FedAvg
 */
object GradientAggregator {
    private const val TAG = "GradientAggregator"
    private const val SHARD_SIZE = 4096  // Matches C++ WEIGHT_SHARD_SIZE
    private const val HEADER_SIZE = 12

    // Aggregated shards
    private val aggregatedShards = ConcurrentHashMap<Int, AggregatedShard>()

    // Pending contributions waiting for aggregation
    private val pendingContributions = ConcurrentHashMap<Int, MutableList<Pair<ByteArray, Int>>>()

    // Stats
    private val _totalAggregations = MutableStateFlow(0)
    val totalAggregations: StateFlow<Int> = _totalAggregations.asStateFlow()

    private val _averageContributors = MutableStateFlow(0f)
    val averageContributors: StateFlow<Float> = _averageContributors.asStateFlow()

    /**
     * Receive a weight shard from a mesh node
     */
    fun receive(shardId: Int, weights: ByteArray, version: Int, contributors: Int, epoch: Int) {
        Log.d(TAG, "Received shard $shardId v$version with $contributors contributors")

        // Add to pending
        val pending = pendingContributions.getOrPut(shardId) { mutableListOf() }
        synchronized(pending) {
            pending.add(Pair(weights, contributors))
        }

        // Aggregate if we have enough contributions
        if (pending.size >= 2) {  // Minimum for averaging
            aggregate(shardId, epoch)
        }
    }

    /**
     * Receive raw bytes (from mesh handler)
     */
    fun receive(data: ByteArray) {
        if (data.size < HEADER_SIZE) return

        val buffer = ByteBuffer.wrap(data).order(ByteOrder.LITTLE_ENDIAN)
        val shardId = buffer.get().toInt() and 0xFF
        val version = buffer.get().toInt() and 0xFF
        buffer.getShort()  // checksum - verify later
        val epoch = buffer.getInt()
        val contributors = buffer.get().toInt() and 0xFF
        buffer.position(buffer.position() + 3)  // reserved

        val weights = ByteArray(data.size - HEADER_SIZE)
        buffer.get(weights)

        receive(shardId, weights, version, contributors, epoch)
    }

    /**
     * Perform FedAvg aggregation for a shard
     */
    private fun aggregate(shardId: Int, epoch: Int) {
        val pending = pendingContributions[shardId] ?: return

        val contributions: List<Pair<ByteArray, Int>>
        synchronized(pending) {
            if (pending.size < 2) return
            contributions = pending.toList()
            pending.clear()
        }

        val totalContributors = contributions.sumOf { it.second }
        if (totalContributors == 0) return

        // Get weight size from first contribution
        val weightSize = contributions.first().first.size
        val aggregated = ByteArray(weightSize)

        // Weighted average: sum(weights[i] * contributor_count) / total_contributors
        for (i in 0 until weightSize) {
            var weightedSum = 0L
            for ((weights, count) in contributions) {
                if (i < weights.size) {
                    weightedSum += weights[i].toLong() * count
                }
            }
            val avg = (weightedSum / totalContributors).toInt()
            aggregated[i] = avg.coerceIn(-128, 127).toByte()
        }

        // Store result
        val existing = aggregatedShards[shardId]
        val newVersion = (existing?.version ?: 0) + 1

        aggregatedShards[shardId] = AggregatedShard(
            shardId = shardId,
            weights = aggregated,
            version = newVersion,
            contributors = totalContributors,
            globalEpoch = epoch,
            lastUpdatedMs = System.currentTimeMillis()
        )

        _totalAggregations.value++
        updateAverageContributors()

        Log.d(TAG, "Aggregated shard $shardId: ${contributions.size} sources, $totalContributors total contributors")
    }

    /**
     * Get aggregated shard for broadcasting back to mesh
     */
    fun getAggregatedShard(shardId: Int): AggregatedShard? = aggregatedShards[shardId]

    /**
     * Get all aggregated shards
     */
    fun getAllShards(): List<AggregatedShard> = aggregatedShards.values.toList()

    /**
     * Compute resonance multiplier based on mesh coherence
     * Uses φ (Golden Ratio) for high-coherence boost
     */
    fun computeResonanceMultiplier(coherence: Float): Float {
        return when {
            coherence > 0.8f -> Constants.PHI
            coherence > 0.5f -> {
                val t = (coherence - 0.5f) / 0.3f
                1f + t * (Constants.PHI - 1f)
            }
            coherence > 0.2f -> 1f
            else -> 0.5f + coherence
        }
    }

    /**
     * Pack shard for mesh transmission (matches C++ format)
     */
    fun packShardForMesh(shard: AggregatedShard): ByteArray {
        val buffer = ByteBuffer.allocate(HEADER_SIZE + shard.weights.size)
            .order(ByteOrder.LITTLE_ENDIAN)

        buffer.put(shard.shardId.toByte())
        buffer.put(shard.version.toByte())
        buffer.putShort(computeChecksum(shard.weights))
        buffer.putInt(shard.globalEpoch)
        buffer.put(shard.contributors.toByte())
        buffer.put(0)  // reserved
        buffer.put(0)
        buffer.put(0)
        buffer.put(shard.weights)

        return buffer.array()
    }

    /**
     * CRC16-CCITT checksum (matches C++ implementation)
     */
    private fun computeChecksum(data: ByteArray): Short {
        var crc = 0xFFFF
        for (byte in data) {
            crc = crc xor ((byte.toInt() and 0xFF) shl 8)
            for (j in 0 until 8) {
                crc = if (crc and 0x8000 != 0) {
                    (crc shl 1) xor 0x1021
                } else {
                    crc shl 1
                }
            }
        }
        return (crc and 0xFFFF).toShort()
    }

    private fun updateAverageContributors() {
        val shards = aggregatedShards.values
        if (shards.isEmpty()) {
            _averageContributors.value = 0f
        } else {
            _averageContributors.value = shards.map { it.contributors }.average().toFloat()
        }
    }

    /**
     * Reset aggregator state
     */
    fun reset() {
        aggregatedShards.clear()
        pendingContributions.clear()
        _totalAggregations.value = 0
        _averageContributors.value = 0f
    }
}
