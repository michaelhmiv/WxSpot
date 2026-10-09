package app.wxspot.ui.components

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import app.wxspot.ui.theme.WxGame

/**
 * Original WXspot vector illustration, made from geographic/weather motifs.
 * This is decorative art, not a radar, satellite, model or observed-weather layer.
 */
@Composable
fun WeatherWorldBanner(modifier: Modifier = Modifier) {
    Canvas(
        modifier.fillMaxWidth().height(154.dp).clip(RoundedCornerShape(22.dp))
    ) {
        val w = size.width
        val h = size.height
        drawRect(Brush.verticalGradient(listOf(Color(0xFF90D8F7), Color(0xFFD6F4F2))))
        drawCircle(Color(0xFFFFD16A), radius = h * .23f, center = Offset(w * .8f, h * .25f))
        fun cloud(x: Float, y: Float, scale: Float) {
            drawCircle(Color.White.copy(alpha=.89f), h * .10f * scale, Offset(x, y))
            drawCircle(Color.White.copy(alpha=.89f), h * .13f * scale, Offset(x + h * .08f * scale, y - h * .035f * scale))
            drawCircle(Color.White.copy(alpha=.89f), h * .09f * scale, Offset(x + h * .18f * scale, y + h * .01f * scale))
        }
        cloud(w * .13f, h * .2f, .8f)
        cloud(w * .54f, h * .36f, .56f)
        val far = Path().apply {
            moveTo(0f, h*.79f)
            lineTo(w*.16f,h*.5f)
            lineTo(w*.37f,h*.76f)
            lineTo(w*.56f,h*.42f)
            lineTo(w*.77f,h*.78f)
            lineTo(w,h*.55f)
            lineTo(w,h)
            lineTo(0f,h)
            close()
        }
        drawPath(far, Color(0xFF91CDB4))
        val near = Path().apply {
            moveTo(0f,h*.82f)
            lineTo(w*.18f,h*.64f)
            lineTo(w*.38f,h*.85f)
            lineTo(w*.66f,h*.61f)
            lineTo(w*.86f,h*.83f)
            lineTo(w,h*.72f)
            lineTo(w,h)
            lineTo(0f,h)
            close()
        }
        drawPath(near, Color(0xFF4C9C83))
        drawLine(Color(0xFFEEFAE5), Offset(w*.08f,h*.91f), Offset(w*.35f,h*.91f), strokeWidth=4f)
        // Sounding balloon and basket: decorative only, never tied to a real station.
        val p=Offset(w*.45f,h*.32f)
        drawCircle(Color(0xFFFAF0D7), h*.15f, p)
        drawArc(Color(0xFFF49B7D), 70f, 160f, useCenter=false,
            topLeft=Offset(p.x-h*.15f,p.y-h*.15f),size=androidx.compose.ui.geometry.Size(h*.3f,h*.3f),
            style=Stroke(width=5f))
        drawLine(Color(0xFF596A77),Offset(p.x-h*.07f,p.y+h*.12f),Offset(p.x-h*.035f,p.y+h*.22f),2f)
        drawLine(Color(0xFF596A77),Offset(p.x+h*.07f,p.y+h*.12f),Offset(p.x+h*.035f,p.y+h*.22f),2f)
        drawRect(Color(0xFF885D3C),topLeft=Offset(p.x-h*.045f,p.y+h*.21f),
            size=androidx.compose.ui.geometry.Size(h*.09f,h*.065f))
    }
}

@Composable
fun QuestEyebrow(text: String, modifier: Modifier = Modifier) {
    Box(
        modifier.clip(RoundedCornerShape(12.dp))
            .background(MaterialTheme.colorScheme.primaryContainer)
            .padding(horizontal = 12.dp, vertical = 7.dp)
    ) {
        Text(text, color = MaterialTheme.colorScheme.onPrimaryContainer,
            style=MaterialTheme.typography.labelMedium, fontWeight=FontWeight.Bold)
    }
}

@Composable
fun ScoreMedallion(score: Int?, modifier: Modifier = Modifier) {
    val color = WxGame.colors.sun
    Column(modifier, verticalArrangement=Arrangement.spacedBy(2.dp)) {
        Text(score?.toString() ?: "—", color=color,
            style=MaterialTheme.typography.displayLarge, fontWeight=FontWeight.Black)
        Text("OF 5,000 POINTS", color=WxGame.colors.muted,
            style=MaterialTheme.typography.labelMedium)
    }
}
