package app.wxspot

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import app.wxspot.ui.SoundingHuntApp
import app.wxspot.ui.theme.WxSpotTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.auto(0xFFF8F4E7.toInt(), 0xFF172537.toInt()),
            navigationBarStyle = SystemBarStyle.auto(0xFFFFFFFF.toInt(), 0xFF203045.toInt()),
        )
        setContent {
            WxSpotTheme {
                SoundingHuntApp()
            }
        }
    }
}
