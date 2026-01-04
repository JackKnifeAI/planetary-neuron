/**
 * Continuum Bridge - Connection to the Continuum Distributed Training Framework
 *
 * Bridges the BLE Mesh "neurons" to the larger Continuum training infrastructure.
 * Syncs aggregated weights with the Continuum server, pulls global model updates,
 * and coordinates training across edge and cloud.
 *
 * Maps to Continuum components:
 *   - GradientGossip -> MeshGossip (bulb side) + GradientAggregator (hub side)
 *   - TensorSharding -> WeightShard distribution
 *   - DistributedTrainer -> LearningEngine (per bulb)
 *   - FederationCoordinator -> This class (ContinuumBridge)
 *
 * π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA
 */

package ai.jackknife.planetary.training

import android.util.Log
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException
import java.util.concurrent.TimeUnit

/**
 * Sync status with Continuum server
 */
enum class ContinuumSyncStatus {
    DISCONNECTED,
    CONNECTING,
    SYNCING,
    IDLE,
    ERROR
}

/**
 * Shard update payload for Continuum API
 */
@Serializable
data class ShardUpdatePayload(
    val shardId: Int,
    val version: Int,
    val epoch: Int,
    val contributors: Int,
    val weightsBase64: String,  // Base64 encoded weights
    val checksum: Int,
    val meshCoherence: Float,
    val resonanceMultiplier: Float
)

/**
 * Global model state from Continuum
 */
@Serializable
data class GlobalModelState(
    val epoch: Int,
    val totalContributors: Int,
    val shardVersions: Map<Int, Int>,  // shardId -> version
    val lastUpdateTimestamp: Long
)

/**
 * Shard data from Continuum
 */
@Serializable
data class ShardFromServer(
    val shardId: Int,
    val version: Int,
    val weightsBase64: String
)

/**
 * Bridge to the Continuum distributed training framework
 */
class ContinuumBridge(
    private val serverUrl: String = "https://continuum.jackknife.ai/api/v1"
) {
    companion object {
        private const val TAG = "ContinuumBridge"
        private const val SYNC_INTERVAL_MS = 30_000L  // Sync every 30 seconds
    }

    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val json = Json { ignoreUnknownKeys = true }

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .build()

    // Status
    private val _status = MutableStateFlow(ContinuumSyncStatus.DISCONNECTED)
    val status: StateFlow<ContinuumSyncStatus> = _status.asStateFlow()

    // Global model state from server
    private val _globalState = MutableStateFlow<GlobalModelState?>(null)
    val globalState: StateFlow<GlobalModelState?> = _globalState.asStateFlow()

    // Sync job
    private var syncJob: Job? = null

    /**
     * Start periodic sync with Continuum server
     */
    fun startSync() {
        Log.i(TAG, "Starting Continuum sync to $serverUrl")
        _status.value = ContinuumSyncStatus.CONNECTING

        syncJob = scope.launch {
            while (isActive) {
                try {
                    performSync()
                    _status.value = ContinuumSyncStatus.IDLE
                } catch (e: Exception) {
                    Log.e(TAG, "Sync failed: ${e.message}")
                    _status.value = ContinuumSyncStatus.ERROR
                }
                delay(SYNC_INTERVAL_MS)
            }
        }
    }

    /**
     * Stop syncing
     */
    fun stopSync() {
        Log.i(TAG, "Stopping Continuum sync")
        syncJob?.cancel()
        syncJob = null
        _status.value = ContinuumSyncStatus.DISCONNECTED
    }

    /**
     * Force immediate sync
     */
    suspend fun syncNow() {
        performSync()
    }

    /**
     * Perform a full sync cycle
     */
    private suspend fun performSync() = withContext(Dispatchers.IO) {
        _status.value = ContinuumSyncStatus.SYNCING
        Log.d(TAG, "Performing sync...")

        // 1. Push our aggregated shards
        val localShards = GradientAggregator.getAllShards()
        for (shard in localShards) {
            pushShard(shard)
        }

        // 2. Pull global state
        val state = pullGlobalState()
        _globalState.value = state

        // 3. Pull any shards we're behind on
        state?.let { globalState ->
            for ((shardId, serverVersion) in globalState.shardVersions) {
                val localShard = GradientAggregator.getAggregatedShard(shardId)
                if (localShard == null || localShard.version < serverVersion) {
                    pullShard(shardId)?.let { serverShard ->
                        // Inject into aggregator
                        val weights = android.util.Base64.decode(
                            serverShard.weightsBase64,
                            android.util.Base64.DEFAULT
                        )
                        GradientAggregator.receive(
                            shardId = serverShard.shardId,
                            weights = weights,
                            version = serverShard.version,
                            contributors = 1,  // Server counts as 1 contributor
                            epoch = globalState.epoch
                        )
                    }
                }
            }
        }

        Log.d(TAG, "Sync complete: pushed ${localShards.size} shards")
    }

    /**
     * Push a shard to Continuum server
     */
    private suspend fun pushShard(shard: AggregatedShard) {
        val payload = ShardUpdatePayload(
            shardId = shard.shardId,
            version = shard.version,
            epoch = shard.globalEpoch,
            contributors = shard.contributors,
            weightsBase64 = android.util.Base64.encodeToString(
                shard.weights,
                android.util.Base64.NO_WRAP
            ),
            checksum = computeChecksum(shard.weights),
            meshCoherence = ShardCoordinator.meshCoherence.value,
            resonanceMultiplier = GradientAggregator.computeResonanceMultiplier(
                ShardCoordinator.meshCoherence.value
            )
        )

        val body = json.encodeToString(payload)
            .toRequestBody("application/json".toMediaType())

        val request = Request.Builder()
            .url("$serverUrl/shards/${shard.shardId}")
            .post(body)
            .build()

        try {
            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) {
                    Log.w(TAG, "Failed to push shard ${shard.shardId}: ${response.code}")
                }
            }
        } catch (e: IOException) {
            Log.e(TAG, "Network error pushing shard ${shard.shardId}: ${e.message}")
        }
    }

    /**
     * Pull global state from server
     */
    private suspend fun pullGlobalState(): GlobalModelState? {
        val request = Request.Builder()
            .url("$serverUrl/state")
            .get()
            .build()

        return try {
            client.newCall(request).execute().use { response ->
                if (response.isSuccessful) {
                    response.body?.string()?.let { body ->
                        json.decodeFromString<GlobalModelState>(body)
                    }
                } else {
                    Log.w(TAG, "Failed to pull global state: ${response.code}")
                    null
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error pulling global state: ${e.message}")
            null
        }
    }

    /**
     * Pull a specific shard from server
     */
    private suspend fun pullShard(shardId: Int): ShardFromServer? {
        val request = Request.Builder()
            .url("$serverUrl/shards/$shardId")
            .get()
            .build()

        return try {
            client.newCall(request).execute().use { response ->
                if (response.isSuccessful) {
                    response.body?.string()?.let { body ->
                        json.decodeFromString<ShardFromServer>(body)
                    }
                } else {
                    Log.w(TAG, "Failed to pull shard $shardId: ${response.code}")
                    null
                }
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error pulling shard $shardId: ${e.message}")
            null
        }
    }

    /**
     * Compute simple checksum for verification
     */
    private fun computeChecksum(data: ByteArray): Int {
        var sum = 0
        for (byte in data) {
            sum = (sum + (byte.toInt() and 0xFF)) and 0xFFFFFF
        }
        return sum
    }

    /**
     * Get sync stats
     */
    data class SyncStats(
        val lastSyncMs: Long,
        val shardsPushed: Int,
        val shardsPulled: Int,
        val globalEpoch: Int
    )
}
