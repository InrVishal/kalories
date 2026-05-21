package com.kalories.data.remote

import com.kalories.data.ScanResponse
import okhttp3.MultipartBody
import okhttp3.RequestBody
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part

interface KaloriesApi {

    /**
     * POST /scans
     *
     * Parts:
     *  - image      : JPEG bytes
     *  - depth_map  : Depth16 raw bytes (optional, null if not supported)
     *  - meta       : JSON string of CaptureMeta
     */
    @Multipart
    @POST("scans")
    suspend fun postScan(
        @Part image: MultipartBody.Part,
        @Part depthMap: MultipartBody.Part?,
        @Part("meta") meta: RequestBody,
    ): ScanResponse
}
