package app.wxspot.ui

import android.content.Context
import android.os.Bundle
import android.widget.FrameLayout
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Pause
import androidx.compose.material.icons.outlined.PlayArrow
import androidx.compose.material.icons.outlined.SkipNext
import androidx.compose.material.icons.outlined.SkipPrevious
import androidx.compose.material3.FilterChip
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import app.wxspot.data.ApiRepository
import app.wxspot.domain.HuntRadarEvidence
import app.wxspot.domain.HuntRadarFrame
import app.wxspot.domain.RadarStation
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

/** True historical radar, without ever receiving the correct station or answer coordinates. */
@Composable
fun HuntRadarPanel(
    api: ApiRepository,
    evidence: HuntRadarEvidence?,
    kind: String,
    identifier: String?,
    modifier: Modifier = Modifier,
) {
    val identity = "$kind:$identifier"
    var tapped by remember(identity) { mutableStateOf<Pair<Double, Double>?>(null) }
    var station by remember(identity) { mutableStateOf<RadarStation?>(null) }
    var product by remember(identity) { mutableStateOf("reflectivity") }
    var nationalProduct by remember(identity) { mutableStateOf("reflectivity") }
    var toolsExpanded by remember(identity) { mutableStateOf(false) }
    var rainfallEvidence by
        remember(identity, nationalProduct) { mutableStateOf<HuntRadarEvidence?>(null) }
    var tilt by remember(identity) { mutableIntStateOf(0) }
    var siteEvidence by
        remember(identity, station?.id, product, tilt) { mutableStateOf<HuntRadarEvidence?>(null) }
    LaunchedEffect(tapped) {
        tapped?.let { point ->
            val nearest =
                runCatching { api.nearbyRadarStations(point.first, point.second) }
                    .getOrNull()
                    ?.stations
                    ?.minByOrNull { it.distanceKm }
            if (nearest != null) {
                station = nearest
                product = "reflectivity"
                tilt = 0
                toolsExpanded = true
            }
        }
    }
    LaunchedEffect(identity, nationalProduct) {
        rainfallEvidence = null
        if (nationalProduct != "reflectivity" && identifier != null) {
            rainfallEvidence =
                runCatching { api.huntRadarRain(kind, identifier, nationalProduct) }
                    .getOrElse {
                        HuntRadarEvidence(
                            state = "unavailable",
                            source = "NOAA MRMS / Iowa Environmental Mesonet",
                            attribution = "NOAA MRMS / Iowa Environmental Mesonet",
                            product = nationalProduct,
                            observationTime = evidence?.observationTime.orEmpty(),
                            anchorTime = evidence?.anchorTime.orEmpty(),
                            message = "No verified archived MRMS scan for this sounding.",
                        )
                    }
        }
    }
    LaunchedEffect(identity, station?.id, product, tilt) {
        siteEvidence = null
        val radarSite = station
        if (radarSite != null && identifier != null) {
            siteEvidence =
                runCatching { api.huntRadarSite(kind, identifier, radarSite.id, product, tilt) }
                    .getOrElse {
                        HuntRadarEvidence(
                            state = "unavailable",
                            source = "NOAA / NEXRAD Level III",
                            attribution = "NOAA / NEXRAD",
                            product = product,
                            observationTime = evidence?.observationTime.orEmpty(),
                            anchorTime = evidence?.anchorTime.orEmpty(),
                            message =
                                "No verified historical scans for this product and radar site.",
                        )
                    }
        }
    }
    val selected =
        if (station != null) siteEvidence
        else if (nationalProduct == "reflectivity") evidence else rainfallEvidence
    val frames = selected?.frames.orEmpty()
    var index by
        remember(identity, station?.id, selected?.product, frames.firstOrNull()?.stamp) {
            mutableIntStateOf(selected?.initialIndex ?: 0)
        }
    var playing by remember(identity, station?.id, product, tilt) { mutableStateOf(false) }
    LaunchedEffect(playing, frames.size) {
        while (playing && frames.size > 1) {
            delay(900)
            index = (index + 1) % frames.size
        }
    }
    Column(modifier) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(
                if (station == null) "Historical U.S. radar" else "Radar " + station!!.id,
                style = MaterialTheme.typography.titleSmall,
            )
            Text(
                frames.getOrNull(index)?.time?.take(16)?.replace('T', ' ') ?: "UTC",
                style = MaterialTheme.typography.bodySmall,
            )
        }
        Box(Modifier.fillMaxWidth().weight(1f)) {
            HuntRadarMap(
                api = api,
                frame = frames.getOrNull(index),
                modifier = Modifier.fillMaxSize(),
                onMapTap = { lat, lon -> tapped = lat to lon },
            )
            Column(
                Modifier.align(Alignment.TopCenter)
                    .fillMaxWidth()
                    .background(MaterialTheme.colorScheme.surface.copy(alpha = 0.94f))
            ) {
                Row(
                    Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    FilterChip(
                        selected = toolsExpanded,
                        onClick = { toolsExpanded = !toolsExpanded },
                        label = {
                            Text(
                                if (toolsExpanded) "Hide radar layers"
                                else if (station != null) "Layers · " + station!!.id
                                else when (nationalProduct) {
                                    "rain_rate" -> "Layers · 2-min rain"
                                    "rain_1h" -> "Layers · 1h rain"
                                    "rain_3h" -> "Layers · 3h rain"
                                    "rain_24h" -> "Layers · 24h rain"
                                    else -> "Layers · CONUS"
                                }
                            )
                        },
                    )
                    Text(
                        "  Tap the map to choose a nearby radar",
                        style = MaterialTheme.typography.labelSmall,
                    )
                }
                if (toolsExpanded) {
                    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState())) {
                        listOf(
                                "reflectivity" to "CONUS",
                                "rain_rate" to "2-min rain",
                                "rain_1h" to "1h rain",
                                "rain_3h" to "3h rain",
                                "rain_24h" to "24h rain",
                            )
                            .forEach { (id, label) ->
                                FilterChip(
                                    selected = station == null && nationalProduct == id,
                                    onClick = {
                                        station = null
                                        nationalProduct = id
                                        product = "reflectivity"
                                        tilt = 0
                                        toolsExpanded = false
                                    },
                                    label = { Text(label) },
                                )
                            }
                    }
                    if (station != null) {
                        Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState())) {
                            listOf(
                                    "reflectivity" to "dBZ",
                                    "velocity" to "Velocity",
                                    "storm_relative_velocity" to "SRV",
                                    "correlation_coefficient" to "CC",
                                    "differential_reflectivity" to "ZDR",
                                    "specific_differential_phase" to "KDP",
                                )
                                .forEach { (id, title) ->
                                    FilterChip(
                                        selected = product == id,
                                        onClick = {
                                            product = id
                                            toolsExpanded = false
                                        },
                                        label = { Text(title) },
                                    )
                                }
                        }
                        Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState())) {
                            (0..3).forEach { angle ->
                                FilterChip(
                                    selected = tilt == angle,
                                    onClick = {
                                        tilt = angle
                                        toolsExpanded = false
                                    },
                                    label = { Text("N" + angle) },
                                )
                            }
                        }
                    }
                }
            }
            if (frames.isEmpty()) {
                Text(
                    selected?.message
                        ?: "Loading verified historical radar. Live data is never substituted.",
                    modifier =
                        Modifier.align(Alignment.Center)
                            .background(
                                MaterialTheme.colorScheme.surface.copy(alpha = 0.94f),
                                RoundedCornerShape(8.dp),
                            )
                            .padding(10.dp),
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            Column(
                Modifier.align(Alignment.BottomCenter)
                    .fillMaxWidth()
                    .background(MaterialTheme.colorScheme.surface.copy(alpha = 0.94f))
            ) {
                if (frames.isNotEmpty()) {
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        IconButton(onClick = {
                            playing = false
                            index = (index - 1 + frames.size) % frames.size
                        }) {
                            Icon(Icons.Outlined.SkipPrevious, contentDescription = "Earlier radar frame")
                        }
                        IconButton(onClick = { playing = !playing }) {
                            Icon(
                                if (playing) Icons.Outlined.Pause else Icons.Outlined.PlayArrow,
                                contentDescription = if (playing) "Pause radar" else "Animate radar",
                            )
                        }
                        if (frames.size > 1) {
                            Slider(
                                value = index.toFloat().coerceIn(0f, frames.lastIndex.toFloat()),
                                onValueChange = {
                                    playing = false
                                    index = it.toInt().coerceIn(0, frames.lastIndex)
                                },
                                valueRange = 0f..frames.lastIndex.toFloat(),
                                steps = (frames.size - 2).coerceAtLeast(0),
                                modifier = Modifier.weight(1f),
                            )
                        }
                        IconButton(onClick = {
                            playing = false
                            index = (index + 1) % frames.size
                        }) {
                            Icon(Icons.Outlined.SkipNext, contentDescription = "Later radar frame")
                        }
                        IconButton(onClick = {
                            playing = false
                            index = selected?.initialIndex ?: 0
                        }) {
                            Text("Launch", style = MaterialTheme.typography.labelSmall)
                        }
                    }
                }
                Text(
                    selected?.attribution ?: "Iowa Environmental Mesonet / NOAA",
                    style = MaterialTheme.typography.labelSmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }
}

@Composable
private fun HuntRadarMap(
    api: ApiRepository,
    frame: HuntRadarFrame?,
    modifier: Modifier,
    onMapTap: (Double, Double) -> Unit,
) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val native = remember(context) { HuntHistoricalMap(context, api) }
    native.onTap = onMapTap
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
    var onTap: (Double, Double) -> Unit = { _, _ -> }

    init {
        MapLibre.getInstance(context)
        HttpRequestUtil.setOkHttpClient(api.client)
        view = MapView(context)
        addView(view, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
        view.onCreate(Bundle())
        view.getMapAsync { readyMap ->
            map = readyMap
            readyMap.addOnMapClickListener { point ->
                onTap(point.latitude, point.longitude)
                true
            }
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
        if (!styled || destroyed) return
        val style = map?.style ?: return
        if (next != null && drawnStamp == next.stamp) return
        style.removeLayer("hunt-historical-radar-layer")
        style.removeSource("hunt-historical-radar")
        drawnStamp = null
        if (next == null) return
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
