/**
 * Shard Coordinator - Manages distributed weight shards across the mesh
 *
 * Tracks which nodes hold which shards, coordinates shard rotation,
 * and handles fragment reassembly for large transfers.
 *
 * π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA
 */

package ai.jackknife.planetary.training

import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.util.concurrent.ConcurrentHashMap

/**
 * Status of a neuron node in the mesh
 */
data class NeuronStatus(
    val address: Int,
    val loadPercent: Int,
    val shardsHeld: Int,
    val epoch: Int,
    val neighbors: Int,
    val lastSeenMs: Long,
    val heldShardIds: Set<Int> = emptySet()
)

/**
 * Reassembly buffer for fragmented shard transfers
 */
class FragmentBuffer(
    val shardId: Int,
    val totalFragments: Int
) {
    private val fragments = arrayOfNulls<ByteArray>(totalFragments)
    private var receivedMask = 0

    fun addFragment(index: Int, data: ByteArray): Boolean {
        if (index >= totalFragments) return false
        fragments[index] = data
        receivedMask = receivedMask or (1 shl index)
        return isComplete()
    }

    fun isComplete(): Boolean {
        val completeMask = (1 shl totalFragments) - 1
        return receivedMask == completeMask
    }

    fun assemble(): ByteArray? {
        if (!isComplete()) return null
        return fragments.filterNotNull().reduce { acc, bytes -> acc + bytes }
    }
}

/**
 * Coordinates shard distribution and training across the mesh
 */
object ShardCoordinator {
    private const val TAG = "ShardCoordinator"
    private const val TOTAL_SHARDS = 64
    private const val NODE_TIMEOUT_MS = 30_000L

    // Node tracking
    private val _nodes = MutableStateFlow<Map<Int, NeuronStatus>>(emptyMap())
    val nodes: StateFlow<Map<Int, NeuronStatus>> = _nodes.asStateFlow()

    // Shard ownership map: shardId -> set of node addresses
    private val shardOwners = ConcurrentHashMap<Int, MutableSet<Int>>()

    // Fragment reassembly buffers
    private val fragmentBuffers = ConcurrentHashMap<Pair<Int, Int>, FragmentBuffer>()

    // Global training stats
    private val _globalEpoch = MutableStateFlow(0)
    val globalEpoch: StateFlow<Int> = _globalEpoch.asStateFlow()

    private val _meshCoherence = MutableStateFlow(0f)
    val meshCoherence: StateFlow<Float> = _meshCoherence.asStateFlow()

    /**
     * Update node status from heartbeat
     */
    fun updateNode(address: Int, loadPercent: Int, epoch: Int, neighbors: Int = 0, shardsHeld: Int = 0) {
        val now = System.currentTimeMillis()
        val current = _nodes.value.toMutableMap()

        val existing = current[address]
        val updated = NeuronStatus(
            address = address,
            loadPercent = loadPercent,
            shardsHeld = shardsHeld,
            epoch = epoch,
            neighbors = neighbors,
            lastSeenMs = now,
            heldShardIds = existing?.heldShardIds ?: emptySet()
        )

        current[address] = updated
        _nodes.value = current

        // Update global epoch to max seen
        if (epoch > _globalEpoch.value) {
            _globalEpoch.value = epoch
        }

        updateCoherence()
        pruneStaleNodes()
    }

    /**
     * Record that a node holds a specific shard
     */
    fun recordShardOwnership(nodeAddress: Int, shardId: Int) {
        shardOwners.getOrPut(shardId) { mutableSetOf() }.add(nodeAddress)

        // Update node's held shards
        val current = _nodes.value.toMutableMap()
        current[nodeAddress]?.let { node ->
            current[nodeAddress] = node.copy(
                heldShardIds = node.heldShardIds + shardId
            )
            _nodes.value = current
        }
    }

    /**
     * Handle incoming shard fragment
     * Returns assembled shard data if complete, null otherwise
     */
    fun handleFragment(
        sourceAddress: Int,
        shardId: Int,
        fragmentIdx: Int,
        totalFragments: Int,
        data: ByteArray
    ): ByteArray? {
        val key = Pair(sourceAddress, shardId)

        val buffer = fragmentBuffers.getOrPut(key) {
            FragmentBuffer(shardId, totalFragments)
        }

        if (buffer.addFragment(fragmentIdx, data)) {
            fragmentBuffers.remove(key)
            recordShardOwnership(sourceAddress, shardId)
            return buffer.assemble()
        }

        return null
    }

    /**
     * Get coverage stats: how many unique shards are held across the mesh
     */
    fun getShardCoverage(): Pair<Int, Int> {
        return Pair(shardOwners.size, TOTAL_SHARDS)
    }

    /**
     * Find nodes that could provide a missing shard
     */
    fun findShardProviders(shardId: Int): List<NeuronStatus> {
        val owners = shardOwners[shardId] ?: return emptyList()
        return _nodes.value.filterKeys { it in owners }.values.toList()
    }

    /**
     * Calculate mesh coherence (0.0 to 1.0)
     * Based on node health, epoch alignment, and shard coverage
     */
    private fun updateCoherence() {
        val activeNodes = _nodes.value.values.filter {
            System.currentTimeMillis() - it.lastSeenMs < NODE_TIMEOUT_MS
        }

        if (activeNodes.isEmpty()) {
            _meshCoherence.value = 0f
            return
        }

        // Factor 1: Average node health (inverse of load)
        val avgHealth = activeNodes.map { 1f - (it.loadPercent / 100f) }.average().toFloat()

        // Factor 2: Epoch alignment (how synchronized are nodes)
        val epochs = activeNodes.map { it.epoch }
        val epochSpread = (epochs.maxOrNull() ?: 0) - (epochs.minOrNull() ?: 0)
        val epochAlignment = 1f / (1f + epochSpread * 0.1f)

        // Factor 3: Shard coverage
        val (held, total) = getShardCoverage()
        val coverage = held.toFloat() / total.toFloat()

        // Combined coherence
        _meshCoherence.value = (avgHealth * 0.3f + epochAlignment * 0.4f + coverage * 0.3f)
            .coerceIn(0f, 1f)

        Log.d(TAG, "Mesh coherence: ${_meshCoherence.value} (health=$avgHealth, align=$epochAlignment, coverage=$coverage)")
    }

    /**
     * Remove nodes that haven't sent heartbeats recently
     */
    private fun pruneStaleNodes() {
        val now = System.currentTimeMillis()
        val current = _nodes.value.toMutableMap()
        val stale = current.filter { now - it.value.lastSeenMs > NODE_TIMEOUT_MS }.keys

        if (stale.isNotEmpty()) {
            stale.forEach { addr ->
                current.remove(addr)
                // Remove from shard ownership
                shardOwners.values.forEach { it.remove(addr) }
            }
            _nodes.value = current
            Log.d(TAG, "Pruned ${stale.size} stale nodes")
        }
    }

    /**
     * Reset coordinator state
     */
    fun reset() {
        _nodes.value = emptyMap()
        shardOwners.clear()
        fragmentBuffers.clear()
        _globalEpoch.value = 0
        _meshCoherence.value = 0f
    }
}
