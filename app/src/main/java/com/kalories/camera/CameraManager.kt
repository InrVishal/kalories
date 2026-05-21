package com.kalories.camera

import android.content.Context
import android.util.Log
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageCapture
import androidx.camera.core.ImageCaptureException
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import kotlinx.coroutines.suspendCancellableCoroutine
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

private const val TAG = "CameraManager"

class CameraManager(private val context: Context) {

    private var imageCapture: ImageCapture? = null
    private val cameraExecutor: ExecutorService = Executors.newSingleThreadExecutor()

    /**
     * Binds CameraX Preview + ImageCapture to the given lifecycle and PreviewView.
     */
    fun startCamera(
        lifecycleOwner: LifecycleOwner,
        previewView: PreviewView,
    ) {
        val cameraProviderFuture = ProcessCameraProvider.getInstance(context)
        cameraProviderFuture.addListener({
            val cameraProvider = cameraProviderFuture.get()

            val preview = Preview.Builder()
                .build()
                .also { it.setSurfaceProvider(previewView.surfaceProvider) }

            imageCapture = ImageCapture.Builder()
                .setCaptureMode(ImageCapture.CAPTURE_MODE_MINIMIZE_LATENCY)
                .build()

            try {
                cameraProvider.unbindAll()
                cameraProvider.bindToLifecycle(
                    lifecycleOwner,
                    CameraSelector.DEFAULT_BACK_CAMERA,
                    preview,
                    imageCapture,
                )
                Log.i(TAG, "CameraX bound successfully")
            } catch (e: Exception) {
                Log.e(TAG, "Camera bind failed: ${e.message}")
            }
        }, ContextCompat.getMainExecutor(context))
    }

    /**
     * Captures a JPEG image and returns the raw bytes.
     * Suspends until the capture completes or throws on failure.
     */
    suspend fun captureImageBytes(): ByteArray =
        suspendCancellableCoroutine { cont ->
            val capture = imageCapture
                ?: run { cont.resumeWithException(IllegalStateException("Camera not started")); return@suspendCancellableCoroutine }

            capture.takePicture(
                cameraExecutor,
                object : ImageCapture.OnImageCapturedCallback() {
                    override fun onCaptureSuccess(image: ImageProxy) {
                        try {
                            val bytes = imageProxyToByteArray(image)
                            image.close()
                            cont.resume(bytes)
                        } catch (e: Exception) {
                            cont.resumeWithException(e)
                        }
                    }

                    override fun onError(exception: ImageCaptureException) {
                        Log.e(TAG, "Capture failed: ${exception.message}")
                        cont.resumeWithException(exception)
                    }
                }
            )
        }

    /**
     * Converts an ImageProxy (YUV_420_888 or JPEG depending on format) to JPEG bytes.
     * CameraX with CAPTURE_MODE_MINIMIZE_LATENCY returns JPEG directly.
     */
    private fun imageProxyToByteArray(image: ImageProxy): ByteArray {
        val buffer = image.planes[0].buffer
        val bytes = ByteArray(buffer.remaining())
        buffer.get(bytes)
        return bytes
    }

    fun shutdown() {
        cameraExecutor.shutdown()
    }
}
