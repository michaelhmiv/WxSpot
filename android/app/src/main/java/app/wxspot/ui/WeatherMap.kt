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
import android.os.Handler
import android.os.Looper
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
import app.wxspot.domain.GeoGeometry
import app.wxspot.domain.GeometryEditor
import app.wxspot.domain.Tool
import app.wxspot.domain.WeatherPost
import java.net.URI
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.sin
import okhttp3.HttpUrl.Companion.toHttpUrl
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

@Composable
fun WeatherMap(state: UiState, vm: MapViewModel, modifier: Modifier, ready: (NativeMap) -> Unit) {
    val context = LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val native = remember(context) { NativeMap(context, vm) }
    DisposableEffect(native, lifecycle) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_START -> native.mapView.onStart()
                Lifecycle.Event.ON_RESUME -> native.mapView.onResume()
                Lifecycle.Event.ON_PAUSE -> native.mapView.onPause()
                Lifecycle.Event.ON_STOP -> native.mapView.onStop()
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

class NativeMap(context: Context, private val vm: MapViewModel) : FrameLayout(context) {
    val mapView: MapView
    private val overlay: GeographicOverlay
    private var map: MapLibreMap? = null
    @Volatile private var pending = UiState()
    private var radarKey: String? = null
    private var alertsKey: String? = null
    private var cameraRevision = -1
    private var destroyed = false
    private val handler = Handler(Looper.getMainLooper())

    init {
        MapLibre.getInstance(context)
        val apiHost = vm.api.baseUrl.toHttpUrl().host
        val nativeClient =
            vm.api.client
                .newBuilder()
                .cache(
                    okhttp3.Cache(
                        java.io.File(context.cacheDir, "weather-tiles"),
                        50L * 1024 * 1024,
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
                    val time =
                        original.url.queryParameter("TIME")
                            ?: if (original.url.encodedPath.contains("/archives/")) {
                                pending.replay?.markedLayer?.validTime
                            } else null
                    try {
                        val response = chain.proceed(request)
                        if (
                            time != null &&
                                (!response.isSuccessful ||
                                    !response.header("Content-Type").orEmpty().contains("image"))
                        )
                            handler.post {
                                if (matchesRaster(original.url, time))
                                    vm.raster(time, "source_unavailable")
                            }
                        response
                    } catch (error: Exception) {
                        if (time != null)
                            handler.post {
                                if (matchesRaster(original.url, time))
                                    vm.raster(time, "network_unavailable")
                            }
                        throw error
                    }
                }
                .build()
        HttpRequestUtil.setOkHttpClient(nativeClient)
        mapView = MapView(context)
        overlay = GeographicOverlay(context, vm) { map }
        addView(mapView, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
        addView(overlay, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
        mapView.onCreate(Bundle())
        mapView.addOnDidFinishRenderingFrameListener { fully: Boolean, _: Double, _: Double ->
            overlay.invalidate()
            val frame = pending.currentFrame
            if (
                fully &&
                    pending.rasterState == "loading" &&
                    frame != null &&
                    map?.style?.getLayer("radar-layer") != null
            )
                vm.raster(frame.validTime, "ready")
        }
        mapView.addOnDidFailLoadingMapListener { message ->
            vm.message("Map source unavailable: $message")
        }
        mapView.getMapAsync { readyMap ->
            map = readyMap
            readyMap.uiSettings.setAttributionMargins(12, 0, 0, 220)
            readyMap.addOnCameraIdleListener {
                val c = readyMap.cameraPosition
                val bounds = readyMap.projection.visibleRegion.latLngBounds
                vm.viewport(
                    Camera(
                        listOf(c.target!!.longitude, c.target!!.latitude),
                        c.zoom,
                        c.bearing,
                        c.tilt,
                    ),
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
                    Camera(
                        listOf(c.target!!.longitude, c.target!!.latitude),
                        c.zoom,
                        c.bearing,
                        c.tilt,
                    ),
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

    fun render(state: UiState) {
        pending = state
        overlay.render(state)
        val readyMap = map ?: return
        val style = readyMap.style ?: return
        if (!style.isFullyLoaded) return
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
        val frame = state.currentFrame
        val archive =
            if (state.replay?.isMarked == true) {
                state.selected?.archives?.firstOrNull { it.layerId == state.replay.markedLayer.id }
            } else null
        val key = frame?.id + if (archive != null) ":preserved:${archive.url}" else ":live"
        if (key != radarKey) {
            radarKey = key
            style.removeLayer("radar-layer")
            style.removeSource("radar-source")
            if (archive != null) {
                val b = archive.bounds
                style.addSource(
                    ImageSource(
                        "radar-source",
                        LatLngQuad(
                            LatLng(b[3], b[0]),
                            LatLng(b[3], b[2]),
                            LatLng(b[1], b[2]),
                            LatLng(b[1], b[0]),
                        ),
                        URI(vm.api.url(archive.url)),
                    )
                )
                style.addLayerAbove(
                    RasterLayer("radar-layer", "radar-source")
                        .withProperties(
                            PropertyFactory.rasterOpacity(state.opacity.toFloat()),
                            PropertyFactory.rasterFadeDuration(0f),
                        ),
                    "basemap",
                )
            } else if (frame != null && frame.tileUrl.isNotEmpty()) {
                style.addSource(RasterSource("radar-source", TileSet("2.1.0", frame.tileUrl), 256))
                style.addLayerAbove(
                    RasterLayer("radar-layer", "radar-source")
                        .withProperties(
                            PropertyFactory.rasterOpacity(state.opacity.toFloat()),
                            PropertyFactory.rasterFadeDuration(0f),
                        ),
                    "basemap",
                )
            } else if (frame != null) {
                vm.raster(frame.validTime, "no_data")
            }
        }
        style
            .getLayerAs<RasterLayer>("radar-layer")
            ?.setProperties(PropertyFactory.rasterOpacity(state.opacity.toFloat()))
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

    private fun sameTime(a: String?, b: String?): Boolean =
        a != null &&
            b != null &&
            runCatching { java.time.Instant.parse(a) == java.time.Instant.parse(b) }
                .getOrDefault(false)

    private fun matchesRaster(url: okhttp3.HttpUrl, time: String): Boolean {
        val s = pending
        if (!sameTime(time, s.currentFrame?.validTime)) return false
        val archive =
            if (s.replay?.isMarked == true)
                s.selected?.archives?.firstOrNull { it.layerId == s.replay.markedLayer.id }
            else null
        if (archive != null) return url == vm.api.url(archive.url).toHttpUrl()
        val expected =
            s.currentFrame?.tileUrl?.takeIf { it.isNotBlank() }?.toHttpUrl() ?: return false
        return url.scheme == expected.scheme &&
            url.host == expected.host &&
            url.port == expected.port &&
            url.encodedPath == expected.encodedPath &&
            url.queryParameter("LAYERS") == expected.queryParameter("LAYERS")
    }

    fun destroy() {
        if (!destroyed) {
            destroyed = true
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
