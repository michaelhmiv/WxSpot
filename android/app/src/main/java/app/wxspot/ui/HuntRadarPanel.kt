package app.wxspot.ui

import android.content.Context
import android.os.Bundle
import android.widget.FrameLayout
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Pause
import androidx.compose.material.icons.outlined.PlayArrow
import androidx.compose.material.icons.outlined.SkipNext
import androidx.compose.material.icons.outlined.SkipPrevious
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import app.wxspot.data.ApiRepository
import app.wxspot.domain.HuntRadarEvidence
import app.wxspot.domain.HuntRadarFrame
import kotlinx.coroutines.delay
import org.maplibre.android.MapLibre
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.Style
import org.maplibre.android.module.http.HttpRequestUtil
import org.maplibre.android.style.layers.PropertyFactory
import org.maplibre.android.style.layers.RasterLayer
import org.maplibre.android.style.sources.RasterSource
import org.maplibre.android.style.sources.TileSet

/** National historical radar, deliberately without any station or answer coordinates. */
@Composable
fun HuntRadarPanel(
    api: ApiRepository,
    evidence: HuntRadarEvidence?,
    modifier: Modifier = Modifier,
) {
    val frames = evidence?.frames.orEmpty()
    var index by
        remember(evidence?.observationTime) { mutableIntStateOf(evidence?.initialIndex ?: 0) }
    var playing by remember(evidence?.observationTime) { mutableStateOf(false) }
    LaunchedEffect(playing, frames.size) {
        while (playing && frames.size > 1) {
            delay(900)
            index = (index + 1) % frames.size
        }
    }
    Column(modifier) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("Historical U.S. radar", style = MaterialTheme.typography.titleSmall)
            Text(
                frames.getOrNull(index)?.time?.take(16)?.replace('T', ' ') ?: "Unavailable",
                style = MaterialTheme.typography.bodySmall,
            )
        }
        if (frames.isNotEmpty()) {
            HuntRadarMap(api, frames.getOrNull(index), Modifier.weight(1f))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                IconButton(
                    onClick = {
                        playing = false
                        index = (index - 1 + frames.size) % frames.size
                    }
                ) {
                    Icon(Icons.Outlined.SkipPrevious, contentDescription = "Earlier radar frame")
                }
                IconButton(onClick = { playing = !playing }) {
                    Icon(
                        if (playing) Icons.Outlined.Pause else Icons.Outlined.PlayArrow,
                        contentDescription = if (playing) "Pause radar" else "Animate radar",
                    )
                }
                IconButton(
                    onClick = {
                        playing = false
                        index = (index + 1) % frames.size
                    }
                ) {
                    Icon(Icons.Outlined.SkipNext, contentDescription = "Later radar frame")
                }
                IconButton(
                    onClick = {
                        playing = false
                        index = evidence?.initialIndex ?: 0
                    }
                ) {
                    Text("Launch", style = MaterialTheme.typography.labelSmall)
                }
            }
            Slider(
                value = index.toFloat(),
                onValueChange = {
                    playing = false
                    index = it.toInt().coerceIn(0, frames.lastIndex)
                },
                valueRange = 0f..frames.lastIndex.toFloat(),
                steps = (frames.size - 2).coerceAtLeast(0),
                modifier = Modifier.fillMaxWidth(),
            )
            Text(
                "Iowa Environmental Mesonet / NOAA · verified historical frames · UTC",
                style = MaterialTheme.typography.labelSmall,
            )
        } else {
            Box(Modifier.fillMaxSize().padding(12.dp)) {
                Text(
                    evidence?.message
                        ?: "Loading verified historical radar. Live radar will not be substituted.",
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
}

@Composable
private fun HuntRadarMap(api: ApiRepository, frame: HuntRadarFrame?, modifier: Modifier) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val native = remember(context) { HuntHistoricalMap(context, api) }
    DisposableEffect(native, lifecycle) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_START -> native.sync(Lifecycle.State.STARTED)
                Lifecycle.Event.ON_RESUME -> native.sync(Lifecycle.State.RESUMED)
                Lifecycle.Event.ON_PAUSE -> native.sync(Lifecycle.State.STARTED)
                Lifecycle.Event.ON_STOP -> native.sync(Lifecycle.State.CREATED)
                else -> Unit
            }
        }
        lifecycle.addObserver(observer)
        native.sync(lifecycle.currentState)
        onDispose {
            lifecycle.removeObserver(observer)
            native.destroy()
        }
    }
    AndroidView(
        factory = { native },
        update = { it.setFrame(frame) },
        modifier =
            modifier.semantics {
                contentDescription =
                    "Full United States historical radar. Zoom and pan to investigate the sounding."
            },
    )
}

private class HuntHistoricalMap(context: Context, private val api: ApiRepository) :
    FrameLayout(context) {
    private val view: MapView
    private var map: MapLibreMap? = null
    private var styled = false
    private var started = false
    private var resumed = false
    private var destroyed = false
    private var frame: HuntRadarFrame? = null
    private var drawnStamp: String? = null

    init {
        MapLibre.getInstance(context)
        HttpRequestUtil.setOkHttpClient(api.client)
        view = MapView(context)
        addView(view, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
        view.onCreate(Bundle())
        view.getMapAsync { readyMap ->
            map = readyMap
            readyMap.cameraPosition =
                CameraPosition.Builder().target(LatLng(39.0, -98.0)).zoom(2.8).build()
            readyMap.setStyle(Style.Builder().fromUri(api.url("/weather/style/game"))) {
                styled = true
                drawnStamp = null
                setFrame(frame)
            }
        }
    }

    fun setFrame(next: HuntRadarFrame?) {
        frame = next
        if (!styled || destroyed || next == null || drawnStamp == next.stamp) return
        val style = map?.style ?: return
        style.removeLayer("hunt-historical-radar-layer")
        style.removeSource("hunt-historical-radar")
        val tiles =
            TileSet("2.2.0", api.url(next.tileTemplate)).apply {
                attribution = "Iowa Environmental Mesonet / NOAA NEXRAD"
                setBounds(-130f, 20f, -60f, 55f)
                minZoom = 0f
                maxZoom = 9f
            }
        style.addSource(RasterSource("hunt-historical-radar", tiles, 256))
        style.addLayer(
            RasterLayer("hunt-historical-radar-layer", "hunt-historical-radar")
                .withProperties(PropertyFactory.rasterOpacity(0.86f))
        )
        drawnStamp = next.stamp
    }

    fun sync(state: Lifecycle.State) {
        if (destroyed) return
        if (state.isAtLeast(Lifecycle.State.STARTED) && !started) {
            view.onStart()
            started = true
        } else if (!state.isAtLeast(Lifecycle.State.STARTED) && started) {
            if (resumed) {
                view.onPause()
                resumed = false
            }
            view.onStop()
            started = false
        }
        if (state.isAtLeast(Lifecycle.State.RESUMED) && !resumed) {
            if (!started) {
                view.onStart()
                started = true
            }
            view.onResume()
            resumed = true
        } else if (!state.isAtLeast(Lifecycle.State.RESUMED) && resumed) {
            view.onPause()
            resumed = false
        }
    }

    fun destroy() {
        if (destroyed) return
        destroyed = true
        if (resumed) view.onPause()
        if (started) view.onStop()
        view.onDestroy()
    }
}
