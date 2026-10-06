package app.wxspot.ui

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Path
import android.graphics.PointF
import android.graphics.RectF
import android.os.Bundle
import android.os.Debug
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.MotionEvent
import android.view.View
import android.widget.FrameLayout
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import app.wxspot.domain.AnnotationElement
import app.wxspot.domain.Camera
import app.wxspot.domain.FrameReadiness
import app.wxspot.domain.FrameReadinessTracker
import app.wxspot.domain.FrameRequestKey
import app.wxspot.domain.GeoGeometry
import app.wxspot.domain.GeometryEditor
import app.wxspot.domain.Tool
import app.wxspot.domain.WeatherLoadingPolicy
import app.wxspot.domain.WeatherTileEvent
import app.wxspot.domain.WeatherTileKey
import app.wxspot.domain.WeatherPost
import java.net.URI
import java.security.MessageDigest
import java.util.LinkedHashMap
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.sin
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.Dispatcher
import org.maplibre.android.MapLibre
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.geometry.LatLngQuad
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.Style
import org.maplibre.android.module.http.HttpRequestUtil
import org.maplibre.android.style.expressions.Expression
import org.maplibre.android.style.layers.FillLayer
import org.maplibre.android.style.layers.LineLayer
import org.maplibre.android.style.layers.PropertyFactory
import org.maplibre.android.style.layers.RasterLayer
import org.maplibre.android.style.sources.GeoJsonSource
import org.maplibre.android.style.sources.ImageSource
import org.maplibre.android.style.sources.RasterSource
import org.maplibre.android.style.sources.TileSet
import org.maplibre.android.tile.TileOperation

@Composable
fun WeatherMap(state: UiState, vm: MapViewModel, modifier: Modifier, ready: (NativeMap) -> Unit) {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val native = remember(context) { NativeMap(context, vm) }
    DisposableEffect(native, lifecycle) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_START -> {
                    native.mapView.onStart()
                    vm.mapActive(true)
                }
                Lifecycle.Event.ON_RESUME -> {
                    native.mapView.onResume()
                    vm.mapActive(true)
                }
                Lifecycle.Event.ON_PAUSE -> {
                    vm.mapActive(false)
                    native.mapView.onPause()
                }
                Lifecycle.Event.ON_STOP -> {
                    vm.mapActive(false)
                    native.mapView.onStop()
                }
                else -> Unit
            }
        }
        lifecycle.addObserver(observer)
        onDispose {
            lifecycle.removeObserver(observer)
            native.destroy()
        }
    }
    AndroidView(
        factory = { native.also { ready(it) } },
        modifier = modifier,
        update = { it.render(state) },
    )
}

private data class FrameMapSource(
    val sourceId: String,
    val layerId: String,
    val frame: app.wxspot.domain.RadarFrame,
    val requestKey: FrameRequestKey?,
    val archiveUrl: String?,
)

class NativeMap(context: Context, private val vm: MapViewModel) : FrameLayout(context) {
    val mapView: MapView
    private val overlay: GeographicOverlay
    private var map: MapLibreMap? = null
    @Volatile private var pending = UiState()
    private var alertsKey: String? = null
    private var cameraRevision = -1
    private var destroyed = false
    private val handler = Handler(Looper.getMainLooper())
    private val frameSources = LinkedHashMap<String, FrameMapSource>()
    private val readiness = FrameReadinessTracker()
    private val weatherDispatcher =
        Dispatcher().apply {
            maxRequests = WeatherLoadingPolicy.MAX_CONCURRENT_REQUESTS
            maxRequestsPerHost = WeatherLoadingPolicy.MAX_REQUESTS_PER_ORIGIN
        }
    private var peakPssKb = 0
    private var activeRequestKey: FrameRequestKey? = null
    private var lastReportedRequestKey: FrameRequestKey? = null
    private var lastRenderFully = false
    private var readinessTimeout: Runnable? = null

    init {
        MapLibre.getInstance(context)
        val apiHost = vm.api.baseUrl.toHttpUrl().host
        val nativeClient =
            vm.api.client
                .newBuilder()
                .dispatcher(weatherDispatcher)
                .cache(
                    okhttp3.Cache(
                        java.io.File(context.cacheDir, "weather-tiles"),
                        WeatherLoadingPolicy.TILE_CACHE_BYTES,
                    )
                )
                .addInterceptor { chain ->
                    val original = chain.request()
                    val request =
                        original
                            .newBuilder()
                            .header(
                                "User-Agent",
                                "WxSpot/0.1 (https://github.com/michaelhmiv/WxSpot)",
                            )
                            .apply {
                                if (original.url.host == apiHost)
                                    vm.api.vault.current?.let {
                                        header("Authorization", "Bearer " + it.token)
                                    }
                            }
                            .build()
                    chain.proceed(request)
                }
                .build()
        HttpRequestUtil.setOkHttpClient(nativeClient)
        mapView = MapView(context)
        overlay = GeographicOverlay(context, vm) { map }
        addView(mapView, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
        addView(overlay, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
        mapView.onCreate(Bundle())
        mapView.addOnDidFinishRenderingFrameListener { fully: Boolean, _: Double, _: Double ->
            lastRenderFully = fully
            overlay.invalidate()
            tryCompleteActiveRequest()
        }
        mapView.addOnTileActionListener { operation, x, y, z, wrap, overscaledZ, sourceId ->
            handler.post {
                handleTileAction(operation, x, y, z, wrap, overscaledZ, sourceId)
            }
        }
        mapView.addOnSourceChangedListener { sourceId ->
            handler.post { handleSourceChanged(sourceId) }
        }
        mapView.addOnDidFailLoadingMapListener { message ->
            vm.message("Map source unavailable: $message")
            activeRequestKey?.let { key ->
                readiness.fail(key, message)?.let(::reportReadiness)
            }
        }
        mapView.getMapAsync { readyMap ->
            map = readyMap
            readyMap.uiSettings.setAttributionMargins(12, 0, 0, 220)
            readyMap.addOnCameraIdleListener {
                // Ignore the renderer's initial world camera until our first camera is applied.
                if (cameraRevision < 0) return@addOnCameraIdleListener
                val c = readyMap.cameraPosition
                val bounds = readyMap.projection.visibleRegion.latLngBounds
                vm.viewport(
                    camera(c),
                    listOf(
                        bounds.longitudeWest,
                        bounds.latitudeSouth.coerceAtLeast(-85.0),
                        bounds.longitudeEast,
                        bounds.latitudeNorth.coerceAtMost(85.0),
                    ),
                )
            }
            readyMap.addOnMapLongClickListener { point ->
                val c = readyMap.cameraPosition
                val bounds = readyMap.projection.visibleRegion.latLngBounds
                vm.longPress(
                    listOf(point.longitude, point.latitude),
                    camera(c),
                    listOf(
                        bounds.longitudeWest,
                        bounds.latitudeSouth.coerceAtLeast(-85.0),
                        bounds.longitudeEast,
                        bounds.latitudeNorth.coerceAtMost(85.0),
                    ),
                )
                true
            }
            readyMap.addOnMapClickListener { point ->
                val features =
                    readyMap.queryRenderedFeatures(
                        readyMap.projection.toScreenLocation(point),
                        "nws-fill",
                    )
                val properties = features.firstOrNull()?.properties()
                if (properties != null)
                    vm.official(
                        vm.api.json.parseToJsonElement(properties.toString())
                            as kotlinx.serialization.json.JsonObject
                    )
                properties != null
            }
            readyMap.setStyle(Style.Builder().fromUri(vm.api.url("/weather/style"))) {
                render(pending)
            }
        }
    }

    private fun camera(position: CameraPosition) =
        Camera(
            listOf(position.target!!.longitude, position.target!!.latitude),
            position.zoom,
            // JSON/Postgres normalize negative zero, so normalize before capturing too.
            if (position.bearing == 0.0) 0.0 else position.bearing,
            position.tilt,
        )

    fun render(state: UiState) {
        pending = state
        overlay.render(state)
        val readyMap = map ?: return
        val style = readyMap.style ?: return
        if (!style.isFullyLoaded) return
        if (!state.mapActive) return
        readyMap.uiSettings.apply {
            isScrollGesturesEnabled = state.draft == null
            isRotateGesturesEnabled = state.draft == null
            isZoomGesturesEnabled = state.draft == null
            isTiltGesturesEnabled = state.draft == null
        }
        if (cameraRevision != state.cameraRevision) {
            cameraRevision = state.cameraRevision
            readyMap.cameraPosition =
                CameraPosition.Builder()
                    .target(LatLng(state.camera.center[1], state.camera.center[0]))
                    .zoom(state.camera.zoom)
                    .bearing(state.camera.bearing)
                    .tilt(state.camera.pitch)
                    .build()
        }
        renderWeatherFrames(state, style)
        val newAlerts = state.alerts + state.showAlerts
        if (newAlerts != alertsKey) {
            alertsKey = newAlerts
            val empty = """{"type":"FeatureCollection","features":[]}"""
            val collection = if (state.showAlerts) state.alerts else empty
            if (style.getSourceAs<GeoJsonSource>("nws-alerts") == null) {
                style.addSource(GeoJsonSource("nws-alerts", collection))
                val color =
                    Expression.match(
                        Expression.get("event"),
                        Expression.literal("#A78BFA"),
                        Expression.stop("Tornado Warning", "#FF4458"),
                        Expression.stop("Severe Thunderstorm Warning", "#FBBF24"),
                        Expression.stop("Flash Flood Warning", "#34D399"),
                    )
                style.addLayer(
                    FillLayer("nws-fill", "nws-alerts")
                        .withProperties(
                            PropertyFactory.fillColor(color),
                            PropertyFactory.fillOpacity(0.12f),
                        )
                )
                style.addLayer(
                    LineLayer("nws-outline", "nws-alerts")
                        .withProperties(
                            PropertyFactory.lineColor(color),
                            PropertyFactory.lineWidth(2.5f),
                            PropertyFactory.lineDasharray(arrayOf(3f, 2f)),
                        )
                )
            } else {
                style.getSourceAs<GeoJsonSource>("nws-alerts")?.setGeoJson(collection)
            }
        }
    }

    fun finishShape() = overlay.finishShape()

    private fun renderWeatherFrames(state: UiState, style: Style) {
        val requested = state.requestedFrame
        val displayed = state.currentFrame
        val needsReadiness =
            requested != null &&
                (displayed?.id != requested.id ||
                    state.displayedSelectionGeneration != state.selectionGeneration ||
                    state.displayedViewportGeneration != state.viewportGeneration ||
                    state.rasterState != "ready")
        val candidateArchive = requested?.let { archiveUrlFor(state, it) }
        val candidateId =
            if (needsReadiness && requested != null)
                frameMapSourceId(
                    requested,
                    state.selectionGeneration,
                    state.viewportGeneration,
                    candidateArchive,
                    prefetch = false,
                )
            else null
        val candidateKey =
            if (requested != null && candidateId != null)
                FrameRequestKey(
                    sourceId = "nws-ridge2",
                    frameId = requested.id,
                    selectionGeneration = state.selectionGeneration,
                    viewportGeneration = state.viewportGeneration,
                    mapSourceId = candidateId,
                )
            else null
        activateRequest(candidateKey)

        val desired = LinkedHashMap<String, FrameMapSource>()
        val displayedSelection = state.displayedSelectionGeneration ?: state.selectionGeneration
        val displayedViewport = state.displayedViewportGeneration ?: state.viewportGeneration
        if (displayed != null) {
            val archiveUrl = archiveUrlFor(state, displayed)
            val sourceId =
                frameMapSourceId(
                    displayed,
                    displayedSelection,
                    displayedViewport,
                    archiveUrl,
                    prefetch = false,
                )
            desired[sourceId] =
                FrameMapSource(
                    sourceId = sourceId,
                    layerId = "$sourceId-layer",
                    frame = displayed,
                    requestKey = candidateKey?.takeIf { it.mapSourceId == sourceId },
                    archiveUrl = archiveUrl,
                )
        }
        if (requested != null && candidateKey != null) {
            desired[candidateKey.mapSourceId] =
                FrameMapSource(
                    sourceId = candidateKey.mapSourceId,
                    layerId = "${candidateKey.mapSourceId}-layer",
                    frame = requested,
                    requestKey = candidateKey,
                    archiveUrl = candidateArchive,
                )
        }
        if (state.mapActive) {
            for (frame in state.preloadFrames) {
                if (frame.id == requested?.id || frame.id == displayed?.id) continue
                if (desired.size >= WeatherLoadingPolicy.MAX_PREFETCH_FRAMES) break
                val sourceId =
                    frameMapSourceId(
                        frame,
                        state.selectionGeneration,
                        state.viewportGeneration,
                        archiveUrl = null,
                        prefetch = true,
                    )
                desired[sourceId] =
                    FrameMapSource(
                        sourceId = sourceId,
                        layerId = "$sourceId-layer",
                        frame = frame,
                        requestKey = null,
                        archiveUrl = null,
                    )
            }
        }

        frameSources.keys.toList().filterNot(desired::containsKey).forEach { sourceId ->
            style.removeLayer("$sourceId-layer")
            style.removeSource(sourceId)
            frameSources.remove(sourceId)
        }
        desired.values.forEach { entry ->
            val valid = entry.archiveUrl != null || entry.frame.tileUrl.isNotBlank()
            if (valid) ensureFrameSource(style, entry)
        }

        val displayedSourceId =
            displayed?.let {
                frameMapSourceId(
                    it,
                    displayedSelection,
                    displayedViewport,
                    archiveUrlFor(state, it),
                    prefetch = false,
                )
            }
        desired.values.forEach { entry ->
            val opacity =
                if (entry.sourceId == displayedSourceId) state.opacity.toFloat() else 0.001f
            style.getLayerAs<RasterLayer>(entry.layerId)
                ?.setProperties(PropertyFactory.rasterOpacity(opacity))
        }

        if (candidateKey != null && candidateArchive == null && requested?.tileUrl.isNullOrBlank()) {
            readiness
                .fail(candidateKey, "The selected radar frame has no render URL")
                ?.let(::reportReadiness)
        }
    }

    private fun ensureFrameSource(style: Style, entry: FrameMapSource) {
        if (frameSources.containsKey(entry.sourceId)) {
            frameSources[entry.sourceId] = entry
            return
        }
        frameSources[entry.sourceId] = entry
        try {
            if (entry.archiveUrl != null) {
                val replay = pending.replay
                val layer = replay?.markedLayer ?: return
                val archive = pending.selected?.archives?.firstOrNull { it.layerId == layer.id } ?: return
                val bounds = archive.bounds
                style.addSource(
                    ImageSource(
                        entry.sourceId,
                        LatLngQuad(
                            LatLng(bounds[3], bounds[0]),
                            LatLng(bounds[3], bounds[2]),
                            LatLng(bounds[1], bounds[2]),
                            LatLng(bounds[1], bounds[0]),
                        ),
                        URI(vm.api.url(entry.archiveUrl)),
                    )
                )
            } else {
                style.addSource(
                    RasterSource(entry.sourceId, TileSet("2.1.0", entry.frame.tileUrl), 256)
                )
            }
            style.addLayerAbove(
                RasterLayer(entry.layerId, entry.sourceId)
                    .withProperties(
                        PropertyFactory.rasterOpacity(0.001f),
                        PropertyFactory.rasterFadeDuration(0f),
                    ),
                "basemap",
            )
        } catch (error: Exception) {
            Log.e("WxSpotWeather", "Could not add weather source ${entry.sourceId}", error)
            entry.requestKey?.let { key ->
                readiness.fail(key, "The weather source could not be added to the map")
                    ?.let(::reportReadiness)
            }
        }
    }

    private fun archiveUrlFor(state: UiState, frame: app.wxspot.domain.RadarFrame): String? {
        val replay = state.replay ?: return null
        if (replay.markedLayer.frameId != frame.id) return null
        return state.selected?.archives?.firstOrNull { it.layerId == replay.markedLayer.id }?.url
    }

    private fun frameMapSourceId(
        frame: app.wxspot.domain.RadarFrame,
        selectionGeneration: Long,
        viewportGeneration: Long,
        archiveUrl: String?,
        prefetch: Boolean,
    ): String {
        val variant = if (prefetch) "prefetch" else "frame"
        val identity =
            listOf(
                frame.id,
                frame.site,
                frame.product,
                selectionGeneration,
                if (prefetch) 0 else viewportGeneration,
                archiveUrl.orEmpty(),
                variant,
            ).joinToString("|")
        val digest = MessageDigest.getInstance("SHA-256").digest(identity.toByteArray())
        val token = digest.take(8).joinToString("") { "%02x".format(it.toInt() and 0xff) }
        return "wx-$token"
    }

    private fun activateRequest(key: FrameRequestKey?) {
        if (key == activeRequestKey) return
        readinessTimeout?.let(handler::removeCallbacks)
        readinessTimeout = null
        activeRequestKey = key
        lastReportedRequestKey = null
        lastRenderFully = false
        if (key == null) return
        readiness.begin(key)
        val timeout = Runnable {
            if (isCurrentRequest(key) && lastReportedRequestKey != key) {
                readiness
                    .fail(key, "Radar tiles did not become ready within 10 seconds")
                    ?.let(::reportReadiness)
            }
        }
        readinessTimeout = timeout
        handler.postDelayed(timeout, WeatherLoadingPolicy.FRAME_READY_TIMEOUT_MS)
    }

    private fun handleTileAction(
        operation: TileOperation,
        x: Int,
        y: Int,
        z: Int,
        wrap: Int,
        overscaledZ: Int,
        sourceId: String,
    ) {
        val entry = frameSources[sourceId] ?: return
        val key = entry.requestKey ?: return
        if (!isCurrentRequest(key) || lastReportedRequestKey == key) return
        val event =
            when (operation) {
                TileOperation.RequestedFromCache -> WeatherTileEvent.REQUESTED_FROM_CACHE
                TileOperation.RequestedFromNetwork -> WeatherTileEvent.REQUESTED_FROM_NETWORK
                TileOperation.LoadFromCache -> WeatherTileEvent.LOAD_FROM_CACHE
                TileOperation.LoadFromNetwork -> WeatherTileEvent.LOAD_FROM_NETWORK
                TileOperation.StartParse -> WeatherTileEvent.START_PARSE
                TileOperation.EndParse -> WeatherTileEvent.END_PARSE
                TileOperation.Error -> WeatherTileEvent.ERROR
                TileOperation.Cancelled -> WeatherTileEvent.CANCELLED
                TileOperation.NullOp -> return
            }
        readiness.observe(
            key,
            WeatherTileKey(x, y, z, wrap, overscaledZ),
            event,
        )
        if (event == WeatherTileEvent.END_PARSE || event == WeatherTileEvent.ERROR)
            tryCompleteActiveRequest()
    }

    private fun handleSourceChanged(sourceId: String) {
        val entry = frameSources[sourceId] ?: return
        val key = entry.requestKey ?: return
        if (entry.archiveUrl == null || !isCurrentRequest(key) || lastReportedRequestKey == key)
            return
        readiness.imageSourceChanged(key)
        tryCompleteActiveRequest()
    }

    private fun tryCompleteActiveRequest() {
        val key = activeRequestKey ?: return
        if (!isCurrentRequest(key) || lastReportedRequestKey == key) return
        readiness.finishRendering(key, lastRenderFully)?.let(::reportReadiness)
    }

    private fun isCurrentRequest(key: FrameRequestKey): Boolean {
        val state = pending
        return !destroyed &&
            state.mapActive &&
            activeRequestKey == key &&
            state.requestedFrame?.id == key.frameId &&
            state.selectionGeneration == key.selectionGeneration &&
            state.viewportGeneration == key.viewportGeneration
    }

    private fun reportReadiness(readinessState: FrameReadiness) {
        val key = activeRequestKey ?: return
        if (!isCurrentRequest(key) || lastReportedRequestKey == key) return
        lastReportedRequestKey = key
        readinessTimeout?.let(handler::removeCallbacks)
        readinessTimeout = null
        val stats = readiness.metrics()
        val memory = Debug.MemoryInfo()
        Debug.getMemoryInfo(memory)
        peakPssKb = maxOf(peakPssKb, memory.totalPss)
        val log =
            "frame=${key.frameId} state=${readinessState.state} elapsedMs=${stats.elapsedMillis} " +
                "parsed=${stats.parsedTiles} cacheEvents=${stats.cacheLoads} " +
                "networkEvents=${stats.networkLoads} cancelled=${stats.cancelledTiles} " +
                "failed=${stats.failedTiles} stall=${stats.elapsedMillis > 2_500} " +
                "runningRequests=${weatherDispatcher.runningCallsCount()} " +
                "queuedRequests=${weatherDispatcher.queuedCallsCount()} " +
                "pssKb=${memory.totalPss} peakPssKb=$peakPssKb"
        if (readinessState.state == "ready") Log.i("WxSpotWeather", log)
        else Log.w("WxSpotWeather", "$log error=${readinessState.error}")
        vm.raster(readinessState)
    }

    fun destroy() {
        if (!destroyed) {
            destroyed = true
            vm.mapActive(false)
            readinessTimeout?.let(handler::removeCallbacks)
            mapView.onPause()
            mapView.onStop()
            mapView.onDestroy()
        }
    }
}

@SuppressLint("ViewConstructor")
private class GeographicOverlay(
    context: Context,
    private val vm: MapViewModel,
    private val map: () -> MapLibreMap?,
) : View(context) {
    private val density = resources.displayMetrics.density
    private val paint = Paint(Paint.ANTI_ALIAS_FLAG)
    private var state = UiState()
    private var down = PointF()
    private var start: List<Double>? = null
    private var provisional: AnnotationElement? = null
    private var points = mutableListOf<List<Double>>()
    private var gesturePoints = mutableListOf<List<Double>>()
    private var original: AnnotationElement? = null
    private var vertex = -1
    private var markerHit: List<WeatherPost>? = null
    private var clusters = listOf<Pair<PointF, List<WeatherPost>>>()
    private var moved = false

    fun render(value: UiState) {
        if (state.tool != value.tool || state.draft != value.draft && value.draft == null) {
            points.clear()
            provisional = null
        }
        state = value
        invalidate()
    }

    private fun screen(point: List<Double>): PointF =
        map()!!.projection.toScreenLocation(LatLng(point[1], point[0]))

    private fun geographic(x: Float, y: Float): List<Double> {
        val point = map()!!.projection.fromScreenLocation(PointF(x, y))
        return listOf(point.longitude, point.latitude)
    }

    private fun distance(a: PointF, b: PointF): Float = hypot(a.x - b.x, a.y - b.y)

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (map() == null) return
        clusters = emptyList()
        if (state.draft == null) {
            val result = mutableListOf<Pair<PointF, MutableList<WeatherPost>>>()
            state.posts
                .filter { it.id != state.selected?.id }
                .forEach { post ->
                    val position = screen(post.location)
                    val near = result.firstOrNull { distance(it.first, position) < 40 * density }
                    if (near != null) near.second.add(post)
                    else result.add(position to mutableListOf(post))
                }
            clusters = result
            result.forEach { (point, posts) ->
                paint.style = Paint.Style.FILL
                paint.color = Color.rgb(11, 18, 32)
                canvas.drawCircle(point.x, point.y, 18 * density, paint)
                paint.style = Paint.Style.STROKE
                paint.strokeWidth = 2 * density
                paint.color = Color.parseColor("#67E8F9")
                canvas.drawCircle(point.x, point.y, 18 * density, paint)
                paint.style = Paint.Style.FILL
                paint.textSize = 13 * density
                paint.textAlign = Paint.Align.CENTER
                canvas.drawText(
                    if (posts.size > 1) posts.size.toString()
                    else
                        when (posts.first().contentType) {
                            "analysis" -> "A"
                            "question" -> "?"
                            "photo_report" -> "P"
                            else -> "O"
                        },
                    point.x,
                    point.y + 4.5f * density,
                    paint,
                )
            }
        }
        val elements =
            state.annotationElements.map { if (it.id == provisional?.id) provisional!! else it } +
                listOfNotNull(
                    provisional?.takeIf { p -> state.annotationElements.none { it.id == p.id } }
                )
        elements.forEach { drawElement(canvas, it) }
        if (points.isNotEmpty()) {
            drawElement(
                canvas,
                AnnotationElement(
                    tool = "line",
                    geometry = GeoGeometry.of("LineString", points),
                    color = state.color,
                    stroke = state.stroke,
                ),
            )
            paint.style = Paint.Style.FILL
            points.forEach { p ->
                val s = screen(p)
                canvas.drawCircle(s.x, s.y, 4 * density, paint)
            }
        }
    }

    private fun drawElement(canvas: Canvas, element: AnnotationElement) {
        val vertices = element.geometry.vertices().map(::screen)
        if (vertices.isEmpty()) return
        paint.color = Color.parseColor(element.color)
        paint.strokeWidth = element.stroke.toFloat() * density
        paint.style = Paint.Style.STROKE
        paint.strokeJoin = Paint.Join.ROUND
        paint.strokeCap = Paint.Cap.ROUND
        paint.textAlign = Paint.Align.LEFT
        if (element.tool == "pin") {
            canvas.drawCircle(vertices[0].x, vertices[0].y, 7 * density, paint)
            canvas.drawLine(
                vertices[0].x,
                vertices[0].y + 7 * density,
                vertices[0].x,
                vertices[0].y + 19 * density,
                paint,
            )
        } else if (element.tool == "text") {
            paint.style = Paint.Style.FILL
            paint.textSize = 16 * density
            paint.setShadowLayer(3 * density, 0f, 0f, Color.BLACK)
            canvas.drawText(element.label.orEmpty(), vertices[0].x, vertices[0].y, paint)
            paint.clearShadowLayer()
        } else {
            val path =
                Path().apply {
                    moveTo(vertices[0].x, vertices[0].y)
                    vertices.drop(1).forEach { lineTo(it.x, it.y) }
                    if (element.geometry.type == "Polygon") close()
                }
            canvas.drawPath(path, paint)
            if (element.tool == "arrow" && vertices.size >= 2) {
                val end = vertices.last()
                val previous = vertices[vertices.lastIndex - 1]
                val angle = atan2(end.y - previous.y, end.x - previous.x)
                val size = 15 * density
                for (offset in listOf(-0.48, 0.48)) {
                    canvas.drawLine(
                        end.x,
                        end.y,
                        end.x - (cos(angle + offset) * size).toFloat(),
                        end.y - (sin(angle + offset) * size).toFloat(),
                        paint,
                    )
                }
            }
        }
        if (
            state.draft != null &&
                state.editor.selectedId == element.id &&
                state.tool == Tool.SELECT
        ) {
            paint.style = Paint.Style.FILL
            paint.color = Color.WHITE
            GeometryEditor.handles(element).map(::screen).forEach {
                canvas.drawCircle(it.x, it.y, 5 * density, paint)
            }
        }
    }

    private fun hitElement(point: PointF): AnnotationElement? =
        state.editor.elements.asReversed().firstOrNull { element ->
            val vertices = element.geometry.vertices().map(::screen)
            if (vertices.any { distance(it, point) < 24 * density }) return@firstOrNull true
            val bounds = RectF()
            val path =
                Path().apply {
                    moveTo(vertices.first().x, vertices.first().y)
                    vertices.drop(1).forEach { lineTo(it.x, it.y) }
                }
            path.computeBounds(bounds, true)
            bounds.inset(-18 * density, -18 * density)
            bounds.contains(point.x, point.y)
        }

    @SuppressLint("ClickableViewAccessibility")
    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (map() == null) return false
        val point = PointF(event.x, event.y)
        if (state.draft == null) {
            if (event.action == MotionEvent.ACTION_DOWN) {
                markerHit =
                    clusters.firstOrNull { distance(it.first, point) < 24 * density }?.second
                down = point
                return markerHit != null
            }
            if (event.action == MotionEvent.ACTION_UP && markerHit != null) {
                if (distance(down, point) < 20 * density) {
                    performClick()
                    vm.cluster(markerHit!!)
                }
                markerHit = null
            }
            return markerHit != null || event.action == MotionEvent.ACTION_UP
        }
        when (event.action) {
            MotionEvent.ACTION_DOWN -> {
                down = point
                start = geographic(event.x, event.y)
                moved = false
                provisional = null
                gesturePoints = mutableListOf(start!!)
                original = if (state.tool == Tool.SELECT) hitElement(point) else null
                vertex = -1
                original?.let { element ->
                    vm.select(element.id)
                    vertex =
                        GeometryEditor.handles(element).map(::screen).indexOfFirst {
                            distance(it, point) < 15 * density
                        }
                }
                if (state.tool == Tool.SELECT && original == null) vm.select(null)
            }
            MotionEvent.ACTION_MOVE -> {
                if (distance(down, point) > 5 * density) moved = true
                val current = geographic(event.x, event.y)
                val first = start ?: return true
                when (state.tool) {
                    Tool.SELECT ->
                        original?.let {
                            provisional =
                                if (vertex >= 0) GeometryEditor.moveVertex(it, vertex, current)
                                else
                                    GeometryEditor.translate(
                                        it,
                                        listOf(current[0] - first[0], current[1] - first[1]),
                                    )
                        }
                    Tool.ELLIPSE ->
                        provisional =
                            runCatching {
                                    AnnotationElement(
                                        tool = "ellipse",
                                        geometry = GeometryEditor.ellipse(first, current),
                                        color = state.color,
                                        stroke = state.stroke,
                                    )
                                }
                                .getOrNull()
                    Tool.ARROW ->
                        provisional =
                            AnnotationElement(
                                tool = "arrow",
                                geometry = GeoGeometry.of("LineString", listOf(first, current)),
                                color = state.color,
                                stroke = state.stroke,
                            )
                    Tool.FREEHAND -> {
                        if (
                            gesturePoints.size < 1200 &&
                                distance(screen(gesturePoints.last()), point) >= 3 * density
                        )
                            gesturePoints.add(current)
                        if (gesturePoints.size > 1)
                            provisional =
                                AnnotationElement(
                                    tool = "freehand",
                                    geometry = GeoGeometry.of("LineString", gesturePoints.toList()),
                                    color = state.color,
                                    stroke = state.stroke,
                                )
                    }
                    else -> Unit
                }
                invalidate()
            }
            MotionEvent.ACTION_UP -> {
                performClick()
                val current = geographic(event.x, event.y)
                when (state.tool) {
                    Tool.SELECT ->
                        provisional?.let { changed ->
                            vm.commit(
                                state.editor.elements.map {
                                    if (it.id == changed.id) changed else it
                                }
                            )
                        }
                    Tool.PIN ->
                        if (!moved)
                            vm.add(
                                AnnotationElement(
                                    tool = "pin",
                                    geometry = GeoGeometry.of("Point", listOf(current)),
                                    color = state.color,
                                    stroke = state.stroke,
                                )
                            )
                    Tool.TEXT -> if (!moved) vm.textPoint(current)
                    Tool.LINE,
                    Tool.POLYGON ->
                        if (!moved) {
                            points.add(current)
                            invalidate()
                        }
                    else -> if (moved) provisional?.let(vm::add)
                }
                provisional = null
                original = null
                invalidate()
            }
            MotionEvent.ACTION_CANCEL -> {
                provisional = null
                original = null
                invalidate()
            }
        }
        return true
    }

    override fun performClick(): Boolean = super.performClick()

    fun finishShape() {
        if (
            state.tool == Tool.LINE && points.size >= 2 ||
                state.tool == Tool.POLYGON && points.size >= 3
        ) {
            val polygon = state.tool == Tool.POLYGON
            val vertices = if (polygon) points + listOf(points.first()) else points.toList()
            vm.add(
                AnnotationElement(
                    tool = state.tool.wire,
                    geometry = GeoGeometry.of(if (polygon) "Polygon" else "LineString", vertices),
                    color = state.color,
                    stroke = state.stroke,
                )
            )
            points.clear()
            invalidate()
        } else
            vm.message(
                "Add ${if (state.tool == Tool.POLYGON) "three" else "two"} points, then finish the shape."
            )
    }
}
