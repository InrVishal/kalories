package com.kalories.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

// ------------------------------------------------------------------ //
//  API response models (matches FastAPI backend response)
// ------------------------------------------------------------------ //

@Serializable
data class ScanResponse(
    @SerialName("scan_id")   val scanId: String,
    val status: String,
    val items: List<FoodItemResponse>,
    @SerialName("total_kcal") val totalKcal: Float,
    @SerialName("total_macros") val totalMacros: MacrosResponse,
    @SerialName("depth_mm")  val depthMm: Int? = null,
    val model: String = "ensemble",
)

@Serializable
data class FoodItemResponse(
    val food: String,
    @SerialName("portion_g") val portionG: Float,
    val kcal: Float,
    val confidence: Float,
    val macros: MacrosResponse,
)

@Serializable
data class MacrosResponse(
    val protein: Float = 0f,
    val carbs: Float = 0f,
    val fat: Float = 0f,
    val fiber: Float = 0f,
)

// ------------------------------------------------------------------ //
//  Domain model shown in UI
// ------------------------------------------------------------------ //

data class ScanResult(
    val scanId: String,
    val items: List<FoodItem>,
    val totalKcal: Float,
    val depthMm: Int?,
    val model: String,
)

data class FoodItem(
    val name: String,
    val portionGrams: Float,
    val kcal: Float,
    val confidence: Float,
    val protein: Float,
    val carbs: Float,
    val fat: Float,
)

// ------------------------------------------------------------------ //
//  Capture metadata sent alongside the image
// ------------------------------------------------------------------ //

@Serializable
data class CaptureMeta(
    @SerialName("depth_mm")      val depthMm: Int?,
    @SerialName("depth_supported") val depthSupported: Boolean,
    @SerialName("device_model")  val deviceModel: String = android.os.Build.MODEL,
    @SerialName("os_version")    val osVersion: Int = android.os.Build.VERSION.SDK_INT,
)

// ------------------------------------------------------------------ //
//  Mapping: API → Domain
// ------------------------------------------------------------------ //

fun ScanResponse.toDomain() = ScanResult(
    scanId    = scanId,
    items     = items.map { it.toDomain() },
    totalKcal = totalKcal,
    depthMm   = depthMm,
    model     = model,
)

fun FoodItemResponse.toDomain() = FoodItem(
    name         = food,
    portionGrams = portionG,
    kcal         = kcal,
    confidence   = confidence,
    protein      = macros.protein,
    carbs        = macros.carbs,
    fat          = macros.fat,
)
