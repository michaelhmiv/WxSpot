package app.wxspot.ui.theme

import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/**
 * WXspot's original weather-world design system. Decorative colors never encode measured data.
 * Prefer semantic roles rather than raw color literals in screens or maps.
 */
data class WxGameColors(
    val background: Color,
    val card: Color,
    val ink: Color,
    val muted: Color,
    val sky: Color,
    val grass: Color,
    val sun: Color,
    val land: Color,
    val accent: Color,
    val nav: Color,
    val selected: Color,
    val stroke: Color,
    val chart: Color,
    val chartInk: Color,
    val error: Color,
    val errorInk: Color,
)

private val day =
    WxGameColors(
        background = Color(0xFFF8F4E7),
        card = Color(0xFFFFFEF8),
        ink = Color(0xFF263547),
        muted = Color(0xFF526579),
        sky = Color(0xFF176387),
        grass = Color(0xFF286A5F),
        sun = Color(0xFF805517),
        land = Color(0xFFA4D98A),
        accent = Color(0xFF286D90),
        nav = Color(0xFFFFFFFF),
        selected = Color(0xFFDBEFF6),
        stroke = Color(0xFFD1DCD7),
        chart = Color(0xFF18283C),
        chartInk = Color(0xFFF2F7FA),
        error = Color(0xFFFFE4D8),
        errorInk = Color(0xFF87361E),
    )

private val night =
    WxGameColors(
        background = Color(0xFF172537),
        card = Color(0xFF25354B),
        ink = Color(0xFFF3F3EA),
        muted = Color(0xFFCFDCE6),
        sky = Color(0xFF9DDDFB),
        grass = Color(0xFF96E1B0),
        sun = Color(0xFFFFD786),
        land = Color(0xFF416B61),
        accent = Color(0xFF9DDDFB),
        nav = Color(0xFF203045),
        selected = Color(0xFF3E556C),
        stroke = Color(0xFF52657A),
        chart = Color(0xFF101C2B),
        chartInk = Color(0xFFF2F7FA),
        error = Color(0xFF5A3334),
        errorInk = Color(0xFFFFCFC3),
    )

val LocalWxGameColors = staticCompositionLocalOf { day }

object WxGame {
    val colors: WxGameColors
        @Composable get() = LocalWxGameColors.current
}

private val dayScheme =
    lightColorScheme(
        primary = Color(0xFF245F80),
        onPrimary = Color.White,
        primaryContainer = Color(0xFFD5F0F9),
        onPrimaryContainer = Color(0xFF243F52),
        secondary = Color(0xFF286A5F),
        onSecondary = Color.White,
        secondaryContainer = Color(0xFFDCF0DE),
        onSecondaryContainer = Color(0xFF1D4A40),
        tertiary = Color(0xFF805517),
        onTertiary = Color.White,
        background = Color(0xFFF8F4E7),
        onBackground = Color(0xFF263547),
        surface = Color(0xFFFFFEF8),
        onSurface = Color(0xFF263547),
        surfaceVariant = Color(0xFFEBF0E9),
        onSurfaceVariant = Color(0xFF475D68),
        outline = Color(0xFF627787),
        error = Color(0xFF9C3429),
    )

private val nightScheme =
    darkColorScheme(
        primary = Color(0xFF9DDDFB),
        onPrimary = Color(0xFF123047),
        primaryContainer = Color(0xFF305267),
        onPrimaryContainer = Color(0xFFF0F8FC),
        secondary = Color(0xFF96E1B0),
        onSecondary = Color(0xFF163C32),
        secondaryContainer = Color(0xFF2F534A),
        onSecondaryContainer = Color(0xFFF3F3EA),
        tertiary = Color(0xFFFFD786),
        onTertiary = Color(0xFF4A3413),
        background = Color(0xFF172537),
        onBackground = Color(0xFFF3F3EA),
        surface = Color(0xFF25354B),
        onSurface = Color(0xFFF3F3EA),
        surfaceVariant = Color(0xFF35475B),
        onSurfaceVariant = Color(0xFFDBE5EA),
        outline = Color(0xFFA1B3C4),
        error = Color(0xFFFFB4A7),
    )

private val gameShapes =
    Shapes(
        extraSmall = RoundedCornerShape(10.dp),
        small = RoundedCornerShape(14.dp),
        medium = RoundedCornerShape(18.dp),
        large = RoundedCornerShape(24.dp),
        extraLarge = RoundedCornerShape(28.dp),
    )

private val gameTypography =
    Typography(
        headlineLarge = Typography().headlineLarge.copy(fontWeight = FontWeight.ExtraBold),
        headlineMedium = Typography().headlineMedium.copy(fontWeight = FontWeight.ExtraBold),
        headlineSmall = Typography().headlineSmall.copy(fontWeight = FontWeight.Bold),
        titleLarge = Typography().titleLarge.copy(fontWeight = FontWeight.Bold),
        titleMedium = Typography().titleMedium.copy(fontWeight = FontWeight.SemiBold),
        labelLarge = Typography().labelLarge.copy(fontWeight = FontWeight.Bold),
    )

@Composable
fun WxSpotTheme(useDarkTheme: Boolean = isSystemInDarkTheme(), content: @Composable () -> Unit) {
    val colors = if (useDarkTheme) night else day
    CompositionLocalProvider(LocalWxGameColors provides colors) {
        MaterialTheme(
            colorScheme = if (useDarkTheme) nightScheme else dayScheme,
            typography = gameTypography,
            shapes = gameShapes,
            content = content,
        )
    }
}
