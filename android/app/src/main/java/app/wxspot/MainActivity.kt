package app.wxspot

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import app.wxspot.ui.SoundingHuntApp
import app.wxspot.ui.theme.WxSpotTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val preferences = getSharedPreferences("wxspot-appearance", MODE_PRIVATE)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.light(0xFFF8F4E7.toInt(), 0xFF263547.toInt()),
            navigationBarStyle = SystemBarStyle.light(0xFFFFFFFF.toInt(), 0xFF263547.toInt()),
        )
        setContent {
            var appearance by remember {
                mutableStateOf(preferences.getString("appearance", "light") ?: "light")
            }
            val dark =
                when (appearance) {
                    "dark" -> true
                    "system" -> isSystemInDarkTheme()
                    else -> false
                }
            LaunchedEffect(dark) {
                enableEdgeToEdge(
                    statusBarStyle =
                        if (dark) SystemBarStyle.dark(0xFF172537.toInt())
                        else SystemBarStyle.light(0xFFF8F4E7.toInt(), 0xFF263547.toInt()),
                    navigationBarStyle =
                        if (dark) SystemBarStyle.dark(0xFF203045.toInt())
                        else SystemBarStyle.light(0xFFFFFFFF.toInt(), 0xFF263547.toInt()),
                )
            }
            WxSpotTheme(useDarkTheme = dark) {
                SoundingHuntApp(
                    appearance = appearance,
                    onAppearanceChange = { next ->
                        if (next in setOf("light", "dark", "system")) {
                            preferences.edit().putString("appearance", next).apply()
                            appearance = next
                        }
                    },
                )
            }
        }
    }
}
