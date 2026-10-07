package app.wxspot

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.SystemBarStyle
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.ui.graphics.Color
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import app.wxspot.ui.MainScreen
import app.wxspot.ui.MapViewModel

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge(
            statusBarStyle = SystemBarStyle.dark(0xB30B1220.toInt()),
            navigationBarStyle = SystemBarStyle.dark(0xB30B1220.toInt()),
        )
        val application = application as WxSpotApplication
        val vm =
            ViewModelProvider(
                this,
                object : ViewModelProvider.Factory {
                    @Suppress("UNCHECKED_CAST")
                    override fun <T : ViewModel> create(modelClass: Class<T>): T =
                        MapViewModel(application.api, application.drafts, application.places) as T
                },
            )[MapViewModel::class.java]
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
                MainScreen(vm)
            }
        }
    }
}
