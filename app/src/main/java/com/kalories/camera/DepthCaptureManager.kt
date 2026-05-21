package com.kalories.camera

import android.content.Context
import android.util.Log
import com.google.ar.core.ArCoreApk
import com.google.ar.core.Config
import com.google.ar.core.Session
import com.google.ar.core.exceptions.NotYetAvailableException
import com.google.ar.core.exceptions.UnavailableException

private const val TAG = "DepthCaptureManager"

/**
 * Manages the ARCore session and captures a Depth16 raw depth map.
 *
 * Usage:
 *  1. Call [checkArCoreAvailability] in onCreate / before showing camera.
 *  2. Call [createSession] after CAMERA permission is granted.
 *  3. Call [captureDepthBytes] inside the CameraX Analyzer or a coroutine after capture.
 *  4. Call [destroy] in onDestroy.
 */
class DepthCaptureManager(private val context: Context) {

    private var session: Session? = null
    var isDepthSupported: Boolean = false
        private set

    // ------------------------------------------------------------------ //
    //  Session lifecycle
    // ------------------------------------------------------------------ //

    /**
     * Returns true if ARCore is installed and supported on this device.
     * Call from Activity.onResume(); prompt user to install if SUPPORTED_NOT_INSTALLED.
     */
    fun checkArCoreAvailability(): Boolean {
        val availability = ArCoreApk.getInstance().checkAvailability(context)
        return availability.isSupported
    }

    /**
     * Creates and configures the ARCore session with AUTOMATIC depth mode.
     * Must be called after the CAMERA permission is granted.
     */
    fun createSession() {
        if (session != null) return
        try {
            session = Session(context).also { s ->
                val config = Config(s).apply {
                    depthMode = if (s.isDepthModeSupported(Config.DepthMode.AUTOMATIC)) {
                        isDepthSupported = true
                        Config.DepthMode.AUTOMATIC
                    } else {
                        isDepthSupported = false
                        Config.DepthMode.DISABLED
                    }
                    updateMode = Config.UpdateMode.LATEST_CAMERA_IMAGE
                }
                s.configure(config)
                s.resume()
            }
            Log.i(TAG, "ARCore session created. Depth supported: $isDepthSupported")
        } catch (e: UnavailableException) {
            Log.w(TAG, "ARCore unavailable: ${e.message}")
            session = null
        }
    }

    /**
     * Captures a single Depth16 frame and returns the raw bytes.
     * Returns null if ARCore is not available or depth data not yet ready.
     *
     * Depth16 format: each pixel is uint16. Lower 13 bits = depth in mm.
     * Upper 3 bits = confidence (0 = invalid, 7 = highest confidence).
     */
    fun captureDepthBytes(): ByteArray? {
        val s = session ?: return null
        return try {
            val frame = s.update()
            val depthImage = frame.acquireDepthImage16Bits()
            val plane = depthImage.planes[0]
            val buffer = plane.buffer
            val bytes = ByteArray(buffer.remaining())
            buffer.get(bytes)
            depthImage.close()

            Log.d(TAG, "Depth map captured: ${bytes.size} bytes")
            bytes
        } catch (e: NotYetAvailableException) {
            Log.w(TAG, "Depth not yet available (ARCore warming up)")
            null
        } catch (e: Exception) {
            Log.e(TAG, "Depth capture error: ${e.message}")
            null
        }
    }

    /**
     * Reads the depth value at the plate centre (centre pixel of depth image).
     * Returns depth in millimetres, or null if unavailable.
     */
    fun getPlateCentreDepthMm(): Int? {
        val s = session ?: return null
        return try {
            val frame = s.update()
            val depthImage = frame.acquireDepthImage16Bits()
            val w = depthImage.width
            val h = depthImage.height
            val plane = depthImage.planes[0]
            val pixelStride = plane.pixelStride          // always 2 for Depth16
            val rowStride = plane.rowStride

            // Centre pixel index
            val cx = w / 2
            val cy = h / 2
            val offset = cy * rowStride + cx * pixelStride
            val buffer = plane.buffer

            // Read little-endian uint16
            val lo = buffer.get(offset).toInt() and 0xFF
            val hi = buffer.get(offset + 1).toInt() and 0xFF
            val raw = (hi shl 8) or lo
            val depthMm = raw and 0x1FFF   // lower 13 bits

            depthImage.close()
            if (depthMm == 0) null else depthMm
        } catch (e: Exception) {
            null
        }
    }

    fun pause() { session?.pause() }
    fun resume() { try { session?.resume() } catch (e: Exception) { Log.e(TAG, "resume: $e") } }
    fun destroy() { session?.close(); session = null }
}
