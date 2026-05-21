package com.kalories.data

import com.kalories.data.remote.KaloriesApi
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class ScanRepository @Inject constructor(
    private val api: KaloriesApi,
) {
    /**
     * Uploads the captured image + optional depth map to the backend.
     * Returns a domain [ScanResult] on success, or throws on network / API error.
     */
    suspend fun submitScan(
        imageBytes: ByteArray,
        depthBytes: ByteArray?,
        meta: CaptureMeta,
    ): ScanResult {
        // --- image part ---
        val imagePart = MultipartBody.Part.createFormData(
            name     = "image",
            filename = "photo.jpg",
            body     = imageBytes.toRequestBody("image/jpeg".toMediaType()),
        )

        // --- depth map part (nullable — sent only when ARCore provides it) ---
        val depthPart = depthBytes?.let {
            MultipartBody.Part.createFormData(
                name     = "depth_map",
                filename = "depth.bin",
                body     = it.toRequestBody("application/octet-stream".toMediaType()),
            )
        }

        // --- metadata part ---
        val metaJson = Json.encodeToString(meta)
        val metaPart = metaJson.toRequestBody("application/json".toMediaType())

        val response = api.postScan(imagePart, depthPart, metaPart)
        return response.toDomain()
    }
}
