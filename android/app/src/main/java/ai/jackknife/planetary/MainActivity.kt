/**
 * Planetary Hub - Main Activity
 *
 * Dashboard for monitoring and coordinating the Planetary Neuron mesh.
 *
 * π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA
 */

package ai.jackknife.planetary

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat
import ai.jackknife.planetary.mesh.MeshConnectionState
import ai.jackknife.planetary.mesh.PlanetaryMeshManager
import ai.jackknife.planetary.training.ContinuumBridge
import ai.jackknife.planetary.training.ShardCoordinator
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    private lateinit var meshManager: PlanetaryMeshManager
    private lateinit var continuumBridge: ContinuumBridge

    private val requestPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { permissions ->
        if (permissions.all { it.value }) {
            initializeMesh()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        meshManager = PlanetaryMeshManager(this)
        continuumBridge = ContinuumBridge()

        checkPermissions()

        setContent {
            MaterialTheme {
                PlanetaryHubScreen(
                    meshManager = meshManager,
                    continuumBridge = continuumBridge
                )
            }
        }
    }

    private fun checkPermissions() {
        val requiredPermissions = arrayOf(
            Manifest.permission.BLUETOOTH_SCAN,
            Manifest.permission.BLUETOOTH_CONNECT,
            Manifest.permission.ACCESS_FINE_LOCATION
        )

        val missingPermissions = requiredPermissions.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }

        if (missingPermissions.isEmpty()) {
            initializeMesh()
        } else {
            requestPermissionLauncher.launch(missingPermissions.toTypedArray())
        }
    }

    private fun initializeMesh() {
        meshManager.initialize()
    }

    override fun onDestroy() {
        super.onDestroy()
        meshManager.disconnect()
        continuumBridge.stopSync()
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun PlanetaryHubScreen(
    meshManager: PlanetaryMeshManager,
    continuumBridge: ContinuumBridge
) {
    val connectionState by meshManager.connectionState.collectAsState()
    val stats by meshManager.stats.collectAsState()
    val nodes by ShardCoordinator.nodes.collectAsState()
    val coherence by ShardCoordinator.meshCoherence.collectAsState()
    val globalEpoch by ShardCoordinator.globalEpoch.collectAsState()

    val scope = rememberCoroutineScope()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Planetary Hub") },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer
                )
            )
        }
    ) { padding ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp)
        ) {
            // Connection Status Card
            Card(
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(
                    modifier = Modifier.padding(16.dp)
                ) {
                    Text(
                        text = "Mesh Status",
                        style = MaterialTheme.typography.titleMedium
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    Text("State: ${connectionState.name}")
                    Text("Nodes: ${nodes.size}")
                    Text("Epoch: $globalEpoch")
                }
            }

            // Coherence Card
            Card(
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(
                    modifier = Modifier.padding(16.dp)
                ) {
                    Text(
                        text = "π×φ Resonance",
                        style = MaterialTheme.typography.titleMedium
                    )
                    Spacer(modifier = Modifier.height(8.dp))

                    // Coherence bar
                    LinearProgressIndicator(
                        progress = { coherence },
                        modifier = Modifier.fillMaxWidth(),
                    )
                    Spacer(modifier = Modifier.height(4.dp))
                    Text(
                        text = "Coherence: ${(coherence * 100).toInt()}%",
                        style = MaterialTheme.typography.bodySmall
                    )

                    val resonance = when {
                        coherence > 0.8f -> "φ (Golden Ratio)"
                        coherence > 0.5f -> "Ramping..."
                        else -> "Baseline"
                    }
                    Text(
                        text = "Resonance: $resonance",
                        style = MaterialTheme.typography.bodySmall
                    )
                }
            }

            // Stats Card
            Card(
                modifier = Modifier.fillMaxWidth()
            ) {
                Column(
                    modifier = Modifier.padding(16.dp)
                ) {
                    Text(
                        text = "Training Stats",
                        style = MaterialTheme.typography.titleMedium
                    )
                    Spacer(modifier = Modifier.height(8.dp))
                    val (shardCount, totalShards) = ShardCoordinator.getShardCoverage()
                    Text("Shards: $shardCount / $totalShards")
                    Text("Messages/sec: ${stats.messagesPerSecond.toInt()}")
                }
            }

            // Control Buttons
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                Button(
                    onClick = {
                        when (connectionState) {
                            MeshConnectionState.DISCONNECTED -> meshManager.startScanning()
                            MeshConnectionState.SCANNING -> meshManager.connect()
                            MeshConnectionState.CONNECTED -> meshManager.disconnect()
                            else -> {}
                        }
                    },
                    modifier = Modifier.weight(1f)
                ) {
                    Text(
                        when (connectionState) {
                            MeshConnectionState.DISCONNECTED -> "Scan"
                            MeshConnectionState.SCANNING -> "Connect"
                            MeshConnectionState.CONNECTED -> "Disconnect"
                            else -> "..."
                        }
                    )
                }

                Button(
                    onClick = { meshManager.broadcastAggregatedWeights() },
                    enabled = connectionState == MeshConnectionState.CONNECTED,
                    modifier = Modifier.weight(1f)
                ) {
                    Text("Broadcast")
                }
            }

            // Continuum Sync Button
            Button(
                onClick = {
                    scope.launch {
                        continuumBridge.syncNow()
                    }
                },
                modifier = Modifier.fillMaxWidth()
            ) {
                Text("Sync with Continuum")
            }

            // Node List
            if (nodes.isNotEmpty()) {
                Text(
                    text = "Active Neurons",
                    style = MaterialTheme.typography.titleMedium
                )
                nodes.values.forEach { node ->
                    Card(
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Row(
                            modifier = Modifier
                                .padding(12.dp)
                                .fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column {
                                Text("Node 0x${node.address.toString(16)}")
                                Text(
                                    "Epoch: ${node.epoch}",
                                    style = MaterialTheme.typography.bodySmall
                                )
                            }
                            Text(
                                "${node.loadPercent}% load",
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                    }
                }
            }
        }
    }
}
