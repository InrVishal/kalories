package com.kalories.scan

import android.Manifest
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.camera.view.PreviewView
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.slideInVertically
import androidx.compose.animation.slideOutVertically
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalLifecycleOwner
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.kalories.data.FoodItem
import com.kalories.data.ScanResult
import kotlin.math.roundToInt

@Composable
fun ScanScreen(viewModel: ScanViewModel = hiltViewModel()) {
    val uiState by viewModel.uiState.collectAsStateWithLifecycle()
    val context = LocalContext.current
    val lifecycleOwner = LocalLifecycleOwner.current

    // Camera permission launcher
    val permissionLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.RequestPermission()
    ) { granted ->
        if (granted) viewModel.onPermissionGranted()
        else viewModel.onPermissionDenied()
    }

    // Request permission on first launch
    LaunchedEffect(Unit) {
        permissionLauncher.launch(Manifest.permission.CAMERA)
    }

    Box(modifier = Modifier.fillMaxSize().background(Color.Black)) {

        // ── Camera preview (always visible once permission granted) ──────
        if (uiState != ScanUiState.Idle && uiState != ScanUiState.RequestingPermission) {
            AndroidView(
                factory = { ctx ->
                    PreviewView(ctx).also { previewView ->
                        viewModel.cameraManager.startCamera(lifecycleOwner, previewView)
                    }
                },
                modifier = Modifier.fillMaxSize(),
            )
        }

        when (val state = uiState) {

            ScanUiState.Idle, ScanUiState.RequestingPermission -> {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    CircularProgressIndicator(color = Color.White)
                }
            }

            ScanUiState.CameraReady -> {
                CameraOverlay(
                    depthSupported = viewModel.depthManager.isDepthSupported,
                    onCapture = viewModel::captureAndScan,
                )
            }

            ScanUiState.Capturing -> {
                CameraOverlay(depthSupported = viewModel.depthManager.isDepthSupported, onCapture = {})
                ScanningIndicator(label = "Capturing…")
            }

            ScanUiState.Uploading -> {
                CameraOverlay(depthSupported = viewModel.depthManager.isDepthSupported, onCapture = {})
                ScanningIndicator(label = "Analysing with AI…")
            }

            is ScanUiState.Success -> {
                CameraOverlay(depthSupported = viewModel.depthManager.isDepthSupported, onCapture = {})
                ResultBottomSheet(
                    result  = state.result,
                    onRescan = viewModel::reset,
                )
            }

            is ScanUiState.Error -> {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(32.dp)) {
                        Text("⚠️", fontSize = 48.sp)
                        Spacer(Modifier.height(12.dp))
                        Text(state.message, color = Color.White, textAlign = TextAlign.Center)
                        Spacer(Modifier.height(20.dp))
                        Button(onClick = viewModel::reset) { Text("Try Again") }
                    }
                }
            }
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
//  Camera overlay: reticle + depth badge + capture button
// ─────────────────────────────────────────────────────────────────────────────

@Composable
private fun CameraOverlay(
    depthSupported: Boolean,
    onCapture: () -> Unit,
) {
    Box(Modifier.fillMaxSize()) {

        // Top status bar
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .statusBarsPadding()
                .padding(horizontal = 16.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = "KALORIES",
                color = Color.White,
                fontWeight = FontWeight.Bold,
                fontSize = 16.sp,
                letterSpacing = 3.sp,
            )
            DepthBadge(supported = depthSupported)
        }

        // Scan reticle centred on screen
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            ScanReticle()
        }

        // Hint text just below reticle
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            Text(
                text = "Point at your food and tap capture",
                color = Color.White.copy(alpha = 0.7f),
                fontSize = 13.sp,
                modifier = Modifier.offset(y = 130.dp),
            )
        }

        // Capture button at bottom
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .align(Alignment.BottomCenter)
                .navigationBarsPadding()
                .padding(bottom = 40.dp),
            contentAlignment = Alignment.Center,
        ) {
            CaptureButton(onClick = onCapture)
        }
    }
}

@Composable
private fun ScanReticle() {
    val green = Color(0xFF1D9E75)
    Box(
        modifier = Modifier
            .size(width = 220.dp, height = 160.dp)
            .border(width = 2.dp, color = green, shape = RoundedCornerShape(16.dp)),
        contentAlignment = Alignment.Center,
    ) {
        // Animated scan line
        val transition = rememberInfiniteTransition(label = "scan")
        val offsetY by transition.animateFloat(
            initialValue = -60f,
            targetValue  = 60f,
            animationSpec = infiniteRepeatable(
                animation  = tween(1800, easing = LinearEasing),
                repeatMode = RepeatMode.Reverse,
            ),
            label = "scanLine",
        )
        Box(
            modifier = Modifier
                .fillMaxWidth()
                .height(2.dp)
                .offset(y = offsetY.dp)
                .background(green.copy(alpha = 0.8f)),
        )
    }
}

@Composable
private fun DepthBadge(supported: Boolean) {
    val (label, bg) = if (supported)
        "ARCore Depth ON"  to Color(0xFF1D9E75)
    else
        "Depth: Fallback"  to Color(0xFFEF9F27)

    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(20.dp))
            .background(bg.copy(alpha = 0.85f))
            .padding(horizontal = 12.dp, vertical = 5.dp),
    ) {
        Text(label, color = Color.White, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
private fun CaptureButton(onClick: () -> Unit) {
    val green = Color(0xFF1D9E75)
    Button(
        onClick = onClick,
        shape = CircleShape,
        colors = ButtonDefaults.buttonColors(containerColor = green),
        modifier = Modifier.size(72.dp),
        contentPadding = PaddingValues(0.dp),
    ) {
        Text("📷", fontSize = 28.sp)
    }
}

@Composable
private fun ScanningIndicator(label: String) {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            CircularProgressIndicator(color = Color(0xFF1D9E75))
            Spacer(Modifier.height(16.dp))
            Text(label, color = Color.White, fontWeight = FontWeight.Medium)
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────────
//  Result bottom sheet
// ─────────────────────────────────────────────────────────────────────────────

@Composable
private fun ResultBottomSheet(result: ScanResult, onRescan: () -> Unit) {
    AnimatedVisibility(
        visible = true,
        enter   = slideInVertically(initialOffsetY = { it }),
        exit    = slideOutVertically(targetOffsetY  = { it }),
    ) {
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.BottomCenter) {
            Surface(
                modifier      = Modifier.fillMaxWidth(),
                shape         = RoundedCornerShape(topStart = 24.dp, topEnd = 24.dp),
                color         = MaterialTheme.colorScheme.surface,
                tonalElevation = 8.dp,
            ) {
                Column(modifier = Modifier.padding(24.dp)) {

                    // Handle
                    Box(
                        Modifier
                            .width(40.dp)
                            .height(4.dp)
                            .clip(CircleShape)
                            .background(MaterialTheme.colorScheme.onSurface.copy(alpha = 0.2f))
                            .align(Alignment.CenterHorizontally)
                    )
                    Spacer(Modifier.height(20.dp))

                    // Total calories hero
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("Total Calories", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            Text(
                                text  = "${result.totalKcal.roundToInt()} kcal",
                                style = MaterialTheme.typography.headlineLarge,
                                fontWeight = FontWeight.Bold,
                                color = Color(0xFF1D9E75),
                            )
                        }
                        result.depthMm?.let {
                            Column(horizontalAlignment = Alignment.End) {
                                Text("Depth", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                                Text("${it} mm", style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.Medium)
                            }
                        }
                    }

                    Spacer(Modifier.height(4.dp))
                    Text(
                        text  = "via ${result.model}",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.height(16.dp))
                    Divider()
                    Spacer(Modifier.height(12.dp))

                    // Food items list
                    LazyColumn(modifier = Modifier.heightIn(max = 280.dp)) {
                        items(result.items) { item -> FoodItemRow(item) }
                    }

                    result.libidoAnalysis?.let { libido ->
                        LibidoAnalysisCard(libido)
                    }

                    Spacer(Modifier.height(20.dp))

                    // Rescan button
                    Button(
                        onClick = onRescan,
                        modifier = Modifier.fillMaxWidth(),
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF1D9E75)),
                    ) {
                        Text("Scan Another", fontWeight = FontWeight.SemiBold)
                    }

                    Spacer(Modifier.height(8.dp))
                }
            }
        }
    }
}

@Composable
private fun LibidoAnalysisCard(libido: com.kalories.data.LibidoAnalysis) {
    val directionColor = when (libido.impactDirection.lowercase()) {
        "boost" -> Color(0xFF1D9E75)
        "decrease" -> Color(0xFFD85A30)
        else -> Color(0xFFEF9F27)
    }
    
    val directionBg = directionColor.copy(alpha = 0.12f)

    Card(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 12.dp),
        shape = RoundedCornerShape(12.dp),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.3f)
        )
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Metabolic & Libido Impact",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.Bold,
                    color = MaterialTheme.colorScheme.onSurface
                )
                
                Box(
                    modifier = Modifier
                        .clip(RoundedCornerShape(20.dp))
                        .background(directionBg)
                        .padding(horizontal = 10.dp, vertical = 4.dp)
                ) {
                    Text(
                        text = libido.impactDirection.uppercase(),
                        color = directionColor,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.Bold,
                        letterSpacing = 1.sp
                    )
                }
            }

            Spacer(Modifier.height(12.dp))

            Row(verticalAlignment = Alignment.CenterVertically) {
                // Score indicator
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(
                        text = "${libido.impactPercent}%",
                        fontSize = 24.sp,
                        fontWeight = FontWeight.ExtraBold,
                        color = directionColor
                    )
                    Text(
                        text = "Impact Score",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }

                Spacer(Modifier.width(16.dp))
                Divider(
                    modifier = Modifier
                        .height(36.dp)
                        .width(1.dp),
                    color = MaterialTheme.colorScheme.outlineVariant
                )
                Spacer(Modifier.width(16.dp))

                // Key factors
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = "Key Physiological Factors",
                        style = MaterialTheme.typography.labelSmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        fontWeight = FontWeight.SemiBold
                    )
                    Spacer(Modifier.height(6.dp))
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(6.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        libido.keyFactors.take(3).forEach { factor ->
                            Box(
                                modifier = Modifier
                                    .clip(RoundedCornerShape(8.dp))
                                    .background(MaterialTheme.colorScheme.surfaceVariant)
                                    .padding(horizontal = 8.dp, vertical = 3.dp)
                            ) {
                                Text(
                                    text = factor,
                                    fontSize = 10.sp,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    fontWeight = FontWeight.Medium
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun FoodItemRow(item: FoodItem) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(item.name, fontWeight = FontWeight.Medium, fontSize = 15.sp)
            Text(
                text  = "${item.portionGrams.roundToInt()}g  ·  ${(item.confidence * 100).roundToInt()}% confident",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(4.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                MacroPill("P ${item.protein.roundToInt()}g", Color(0xFF378ADD))
                MacroPill("C ${item.carbs.roundToInt()}g",   Color(0xFFEF9F27))
                MacroPill("F ${item.fat.roundToInt()}g",     Color(0xFFD85A30))
            }
        }
        Text(
            text  = "${item.kcal.roundToInt()} kcal",
            fontWeight = FontWeight.Bold,
            color  = Color(0xFF1D9E75),
            fontSize = 15.sp,
        )
    }
    Divider(color = MaterialTheme.colorScheme.outlineVariant)
}

@Composable
private fun MacroPill(label: String, color: Color) {
    Box(
        modifier = Modifier
            .clip(RoundedCornerShape(20.dp))
            .background(color.copy(alpha = 0.12f))
            .padding(horizontal = 8.dp, vertical = 2.dp),
    ) {
        Text(label, fontSize = 10.sp, color = color, fontWeight = FontWeight.SemiBold)
    }
}
