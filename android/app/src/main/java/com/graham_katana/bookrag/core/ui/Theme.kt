package com.graham_katana.bookrag.core.ui

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.ButtonDefaults
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

// The ground is a neutral paper (light) or ink (dark), following the phone. Blue is the brand
// colour from the logo and is used only where something is the main action or is yours:
// primary buttons, your own messages, selected chips. It is never a background.
private val Light = lightColorScheme(
    primary = Color(0xFF2563EB),
    onPrimary = Color.White,
    primaryContainer = Color(0xFFDBEAFE),
    onPrimaryContainer = Color(0xFF1E3A8A),
    secondaryContainer = Color(0xFFDBEAFE),
    onSecondaryContainer = Color(0xFF1E3A8A),
    background = Color(0xFFFAFAF8),
    onBackground = Color(0xFF1F2329),
    surface = Color(0xFFFFFFFF),
    onSurface = Color(0xFF1F2329),
    surfaceVariant = Color(0xFFF1F1EE),
    onSurfaceVariant = Color(0xFF656B74),
    surfaceContainerLowest = Color(0xFFFFFFFF),
    surfaceContainerLow = Color(0xFFFFFFFF),
    surfaceContainer = Color(0xFFFFFFFF),
    surfaceContainerHigh = Color(0xFFF1F1EE),
    surfaceContainerHighest = Color(0xFFE9E9E5),
    outline = Color(0xFFD5D5CF),
    outlineVariant = Color(0xFFE5E5E0),
    error = Color(0xFFB91C1C),
)

private val Dark = darkColorScheme(
    // A step lighter than the logo's blue: #2563EB is too dim on ink for a button to read as the main action.
    primary = Color(0xFF3B82F6),
    onPrimary = Color.White,
    primaryContainer = Color(0xFF1B2A4A),
    onPrimaryContainer = Color(0xFFDBEAFE),
    secondaryContainer = Color(0xFF1B2A4A),
    onSecondaryContainer = Color(0xFFDBEAFE),
    background = Color(0xFF101214),
    onBackground = Color(0xFFECEDEE),
    surface = Color(0xFF181B1F),
    onSurface = Color(0xFFECEDEE),
    surfaceVariant = Color(0xFF22262B),
    onSurfaceVariant = Color(0xFF9BA1A6),
    surfaceContainerLowest = Color(0xFF101214),
    surfaceContainerLow = Color(0xFF181B1F),
    surfaceContainer = Color(0xFF181B1F),
    surfaceContainerHigh = Color(0xFF22262B),
    surfaceContainerHighest = Color(0xFF2B3036),
    outline = Color(0xFF3A4047),
    outlineVariant = Color(0xFF2B3036),
    error = Color(0xFFF87171),
)

// Text fields use the theme's smallest shape. Rounding it brings them in line with the pill buttons;
// menus share the shape and look right with it too.
private val AppShapes = Shapes(extraSmall = RoundedCornerShape(16.dp))

@Composable
fun BookRagTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = if (isSystemInDarkTheme()) Dark else Light, shapes = AppShapes, content = content)
}

/** Text buttons that are not the main action read as text, not as blue links. */
@Composable
fun plainTextButton() = ButtonDefaults.textButtonColors(contentColor = MaterialTheme.colorScheme.onSurface)
