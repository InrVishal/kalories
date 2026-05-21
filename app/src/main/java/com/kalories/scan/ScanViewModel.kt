package com.kalories.scan

import android.content.Context
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.kalories.camera.CameraManager
import com.kalories.camera.DepthCaptureManager
import com.kalories.data.CaptureMeta
import com.kalories.data.ScanRepository
import com.kalories.data.ScanResult
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

sealed interface ScanUiState {
    data object Idle : ScanUiState
    data object RequestingPermission : ScanUiState
    data object CameraReady : ScanUiState
    data object Capturing : ScanUiState
    data object Uploading : ScanUiState
    data class Success(val result: ScanResult) : ScanUiState
    data class Error(val message: String) : ScanUiState
}

@HiltViewModel
class ScanViewModel @Inject constructor(
    @ApplicationContext private val context: Context,
    private val scanRepository: ScanRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow<ScanUiState>(ScanUiState.Idle)
    val uiState = _uiState.asStateFlow()

    val cameraManager = CameraManager(context)
    val depthManager = DepthCaptureManager(context)

    // Called once camera permission is granted
    fun onPermissionGranted() {
        depthManager.createSession()
        _uiState.value = ScanUiState.CameraReady
    }

    fun onPermissionDenied() {
        _uiState.value = ScanUiState.Error("Camera permission is required to scan food.")
    }

    /**
     * Main capture → upload flow:
     * 1. Capture JPEG via CameraX
     * 2. Capture Depth16 bytes via ARCore (nullable)
     * 3. Read plate-centre depth in mm for metadata
     * 4. Upload to backend
     * 5. Publish result to UI
     */
    fun captureAndScan() {
        if (_uiState.value is ScanUiState.Capturing || _uiState.value is ScanUiState.Uploading) return

        viewModelScope.launch {
            try {
                _uiState.value = ScanUiState.Capturing

                // Step 1 – capture image
                val imageBytes = cameraManager.captureImageBytes()

                // Step 2 – capture depth (null on unsupported devices)
                val depthBytes = depthManager.captureDepthBytes()
                val depthMm    = depthManager.getPlateCentreDepthMm()

                _uiState.value = ScanUiState.Uploading

                // Step 3 – upload
                val meta = CaptureMeta(
                    depthMm        = depthMm,
                    depthSupported = depthManager.isDepthSupported,
                )
                val result = scanRepository.submitScan(imageBytes, depthBytes, meta)

                _uiState.value = ScanUiState.Success(result)

            } catch (e: Exception) {
                _uiState.value = ScanUiState.Error(e.message ?: "Scan failed. Please try again.")
            }
        }
    }

    fun reset() {
        _uiState.value = ScanUiState.CameraReady
    }

    override fun onCleared() {
        super.onCleared()
        cameraManager.shutdown()
        depthManager.destroy()
    }
}
