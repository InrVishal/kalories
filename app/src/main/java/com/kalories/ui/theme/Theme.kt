package com.kalories.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val DarkColors = darkColorScheme(
    primary   = Color(0xFF1D9E75),
    secondary = Color(0xFFEF9F27),
    background = Color(0xFF0A1A13),
    surface    = Color(0xFF111F18),
)

@Composable
fun KaloriesTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = DarkColors,
        content     = content,
    )
}
