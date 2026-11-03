package com.aiemail.os.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

@Composable
fun OsTheme(mode: String = "system", content: @Composable () -> Unit) {
    val dark = if (mode == "system") isSystemInDarkTheme() else mode == "dark"
    val colors = if (dark) darkColorScheme(
        primary = Color(0xFFB6AAFF), secondary = Color(0xFF58E1CC),
        background = Color(0xFF0B1021), surface = Color(0xFF141B30), surfaceVariant = Color(0xFF222B45)
    ) else lightColorScheme(primary = Color(0xFF5944B9), secondary = Color(0xFF006B60),
        background = Color(0xFFF5F5FF), surface = Color.White)
    MaterialTheme(colorScheme = colors, typography = Typography(), content = content)
}
