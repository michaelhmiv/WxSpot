package app.wxspot

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.ui.graphics.Color
import app.wxspot.ui.SoundingHuntApp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(0xB30B1220.toInt()),
            navigationBarStyle = SystemBarStyle.dark(0xB30B1220.toInt()),
        )
        setContent {
            MaterialTheme(
                colorScheme =
                    darkColorScheme(
                        primary = Color(0xFF67E8F9),
                        secondary = Color(0xFFFDE68A),
                        background = Color(0xFF0B1220),
                        surface = Color(0xFF142033),
                        onPrimary = Color(0xFF08202A),
                        onSurface = Color(0xFFE7EFFA),
                    )
            ) {
                SoundingHuntApp()
            }
        }
    }
}
