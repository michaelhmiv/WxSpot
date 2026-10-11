package app.wxspot.ui

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color as AndroidColor
import android.graphics.Paint
import android.graphics.Path
import android.os.Bundle
import android.widget.FrameLayout
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.getValue
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
import org.json.JSONArray
import org.json.JSONObject
import org.maplibre.android.MapLibre
import org.maplibre.android.camera.CameraPosition
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.geometry.LatLngBounds
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.MapView
import org.maplibre.android.maps.Style
import org.maplibre.android.module.http.HttpRequestUtil
import org.maplibre.android.style.layers.CircleLayer
import org.maplibre.android.style.layers.LineLayer
import org.maplibre.android.style.layers.PropertyFactory
import org.maplibre.android.style.layers.SymbolLayer
import org.maplibre.android.style.sources.GeoJsonSource

@Composable
fun SoundingHuntMap(
    api: ApiRepository,
    guess: Pair<Double, Double>?,
    answer: Pair<Double, Double>? = null,
    allowGuess: Boolean,
    modifier: Modifier = Modifier,
    onGuess: (latitude: Double, longitude: Double) -> Unit = { _, _ -> },
) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    var mapReady by remember(context) { mutableStateOf(false) }
    val native =
        remember(context) { HuntMapView(context, api, allowGuess, onGuess) { mapReady = true } }
    native.allowGuess = allowGuess
    native.onGuess = onGuess
    native.onReady = { mapReady = true }
    DisposableEffect(native, lifecycle) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_START -> native.syncLifecycle(Lifecycle.State.STARTED)
                Lifecycle.Event.ON_RESUME -> native.syncLifecycle(Lifecycle.State.RESUMED)
                Lifecycle.Event.ON_PAUSE -> native.syncLifecycle(Lifecycle.State.STARTED)
                Lifecycle.Event.ON_STOP -> native.syncLifecycle(Lifecycle.State.CREATED)
                else -> Unit
            }
        }
        lifecycle.addObserver(observer)
        native.syncLifecycle(lifecycle.currentState)
        onDispose {
            lifecycle.removeObserver(observer)
            native.destroy()
        }
    }
    AndroidView(
        factory = { native },
        update = { it.render(guess, answer) },
        modifier =
            modifier.semantics {
                contentDescription =
                    if (allowGuess) {
                        if (mapReady) {
                            "Map of the contiguous United States. Tap to place or move your guess."
                        } else {
                            "Loading map of the contiguous United States."
                        }
                    } else {
                        "Map showing your guess (G) and the sounding location (A), joined by distance."
                    }
            },
    )
}

private class HuntMapView(
    context: Context,
    private val api: ApiRepository,
    var allowGuess: Boolean,
    var onGuess: (Double, Double) -> Unit,
    var onReady: () -> Unit,
) : FrameLayout(context) {
    private val mapView: MapView
    private var map: MapLibreMap? = null
    private var styleReady = false
    private var started = false
    private var resumed = false
    private var destroyed = false
    private var pendingGuess: Pair<Double, Double>? = null
    private var pendingAnswer: Pair<Double, Double>? = null
    private var lastReveal: Pair<Pair<Double, Double>, Pair<Double, Double>>? = null

    init {
        MapLibre.getInstance(context)
        HttpRequestUtil.setOkHttpClient(api.client)
        mapView = MapView(context)
        addView(mapView, LayoutParams(LayoutParams.MATCH_PARENT, LayoutParams.MATCH_PARENT))
        mapView.onCreate(Bundle())
        mapView.getMapAsync { readyMap ->
            map = readyMap
            readyMap.cameraPosition =
                CameraPosition.Builder().target(LatLng(39.0, -98.0)).zoom(3.0).build()
            readyMap.addOnMapClickListener { point ->
                if (allowGuess) onGuess(point.latitude, point.longitude)
                allowGuess
            }
            readyMap.setStyle(Style.Builder().fromUri(api.url("/weather/style/game"))) { style ->
                styleReady = true
                addGameLayers(style)
                render(pendingGuess, pendingAnswer)
                onReady()
            }
        }
    }

    fun syncLifecycle(state: Lifecycle.State) {
        if (destroyed) return
        if (state.isAtLeast(Lifecycle.State.STARTED) && !started) {
            mapView.onStart()
            started = true
        } else if (!state.isAtLeast(Lifecycle.State.STARTED) && started) {
            if (resumed) {
                mapView.onPause()
                resumed = false
            }
            mapView.onStop()
            started = false
        }
        if (state.isAtLeast(Lifecycle.State.RESUMED) && !resumed) {
            if (!started) {
                mapView.onStart()
                started = true
            }
            mapView.onResume()
            resumed = true
        } else if (!state.isAtLeast(Lifecycle.State.RESUMED) && resumed) {
            mapView.onPause()
            resumed = false
        }
    }

    fun render(guess: Pair<Double, Double>?, answer: Pair<Double, Double>?) {
        pendingGuess = guess
        pendingAnswer = answer
        if (!styleReady) return
        val style = map?.style ?: return
        style.getSourceAs<GeoJsonSource>("hunt-guess")?.setGeoJson(pointCollection(guess))
        style.getSourceAs<GeoJsonSource>("hunt-answer")?.setGeoJson(pointCollection(answer))
        style.getSourceAs<GeoJsonSource>("hunt-line")?.setGeoJson(lineCollection(guess, answer))
        if (guess != null && answer != null && lastReveal != (guess to answer)) {
            lastReveal = guess to answer
            val target = map ?: return
            if (guess.first == answer.first && guess.second == answer.second) {
                target.animateCamera(
                    CameraUpdateFactory.newLatLngZoom(LatLng(answer.first, answer.second), 5.0)
                )
            } else {
                val bounds =
                    LatLngBounds.Builder()
                        .include(LatLng(guess.first, guess.second))
                        .include(LatLng(answer.first, answer.second))
                        .build()
                post {
                    if (!destroyed) {
                        target.animateCamera(CameraUpdateFactory.newLatLngBounds(bounds, 64))
                    }
                }
            }
        }
    }

    private fun addGameLayers(style: Style) {
        style.addImage("wxspot-guess-pin", pinBitmap(guess = true))
        style.addImage("wxspot-answer-pin", pinBitmap(guess = false))
        style.addSource(GeoJsonSource("hunt-line", lineCollection(null, null)))
        style.addLayer(
            LineLayer("hunt-line-layer", "hunt-line")
                .withProperties(
                    PropertyFactory.lineColor("#286D90"),
                    PropertyFactory.lineWidth(3.0f),
                    PropertyFactory.lineOpacity(0.9f),
                )
        )
        style.addSource(GeoJsonSource("hunt-guess", pointCollection(null)))
        style.addLayer(
            CircleLayer("hunt-guess-halo", "hunt-guess")
                .withProperties(
                    PropertyFactory.circleColor("#F39B76"),
                    PropertyFactory.circleRadius(18f),
                    PropertyFactory.circleOpacity(0.22f),
                )
        )
        style.addLayer(
            SymbolLayer("hunt-guess-pin", "hunt-guess")
                .withProperties(
                    PropertyFactory.iconImage("wxspot-guess-pin"),
                    PropertyFactory.iconAnchor("bottom"),
                    PropertyFactory.iconSize(0.55f),
                    PropertyFactory.iconAllowOverlap(true),
                )
        )
        style.addSource(GeoJsonSource("hunt-answer", pointCollection(null)))
        style.addLayer(
            CircleLayer("hunt-answer-halo", "hunt-answer")
                .withProperties(
                    PropertyFactory.circleColor("#286A5F"),
                    PropertyFactory.circleRadius(18f),
                    PropertyFactory.circleOpacity(0.22f),
                )
        )
        style.addLayer(
            SymbolLayer("hunt-answer-pin", "hunt-answer")
                .withProperties(
                    PropertyFactory.iconImage("wxspot-answer-pin"),
                    PropertyFactory.iconAnchor("bottom"),
                    PropertyFactory.iconSize(0.55f),
                    PropertyFactory.iconAllowOverlap(true),
                )
        )
    }

    /** Bitmap symbols avoid requiring external glyph endpoints in a raster basemap style. */
    private fun pinBitmap(guess: Boolean): Bitmap {
        val bitmap = Bitmap.createBitmap(80, 96, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        val paint = Paint(Paint.ANTI_ALIAS_FLAG)
        val shape =
            Path().apply {
                moveTo(40f, 94f)
                cubicTo(14f, 64f, 10f, 57f, 10f, 37f)
                cubicTo(10f, 18f, 22f, 5f, 40f, 5f)
                cubicTo(58f, 5f, 70f, 18f, 70f, 37f)
                cubicTo(70f, 57f, 66f, 64f, 40f, 94f)
                close()
            }
        paint.style = Paint.Style.STROKE
        paint.strokeWidth = 6f
        paint.color = AndroidColor.WHITE
        canvas.drawPath(shape, paint)
        paint.style = Paint.Style.FILL
        paint.color = if (guess) AndroidColor.rgb(235, 133, 97) else AndroidColor.rgb(36, 119, 91)
        canvas.drawPath(shape, paint)
        paint.color = AndroidColor.WHITE
        if (guess) {
            // Compass crosshair: the player's editable location.
            paint.style = Paint.Style.STROKE
            paint.strokeWidth = 3f
            canvas.drawCircle(40f, 37f, 12f, paint)
            canvas.drawLine(40f, 19f, 40f, 55f, paint)
            canvas.drawLine(22f, 37f, 58f, 37f, paint)
        } else {
            // Star-shaped discovery badge: the observed answer, shown only on reveal.
            paint.style = Paint.Style.FILL
            val star =
                Path().apply {
                    moveTo(40f, 17f)
                    lineTo(46f, 31f)
                    lineTo(61f, 37f)
                    lineTo(46f, 43f)
                    lineTo(40f, 57f)
                    lineTo(34f, 43f)
                    lineTo(19f, 37f)
                    lineTo(34f, 31f)
                    close()
                }
            canvas.drawPath(star, paint)
        }
        return bitmap
    }

    private fun pointCollection(point: Pair<Double, Double>?): String {
        val features = JSONArray()
        if (point != null) {
            val coordinates = JSONArray().put(point.second).put(point.first)
            val geometry = JSONObject().put("type", "Point").put("coordinates", coordinates)
            features.put(JSONObject().put("type", "Feature").put("geometry", geometry))
        }
        return JSONObject().put("type", "FeatureCollection").put("features", features).toString()
    }

    private fun lineCollection(
        guess: Pair<Double, Double>?,
        answer: Pair<Double, Double>?,
    ): String {
        val features = JSONArray()
        if (guess != null && answer != null) {
            val coordinates =
                JSONArray()
                    .put(JSONArray().put(guess.second).put(guess.first))
                    .put(JSONArray().put(answer.second).put(answer.first))
            val geometry = JSONObject().put("type", "LineString").put("coordinates", coordinates)
            features.put(JSONObject().put("type", "Feature").put("geometry", geometry))
        }
        return JSONObject().put("type", "FeatureCollection").put("features", features).toString()
    }

    fun destroy() {
        if (destroyed) return
        destroyed = true
        if (resumed) mapView.onPause()
        if (started) mapView.onStop()
        mapView.onDestroy()
    }
}
