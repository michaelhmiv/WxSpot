package app.wxspot.ui

import android.content.Context
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
    val native = remember(context) {
        HuntMapView(context, api, allowGuess, onGuess) { mapReady = true }
    }
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
                        "Map showing your guess and the sounding location, joined by distance."
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
            readyMap.setStyle(Style.Builder().fromUri(api.url("/weather/style"))) { style ->
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
        if (guess != null && answer != null) {
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
        style.addSource(GeoJsonSource("hunt-line", lineCollection(null, null)))
        style.addLayer(
            LineLayer("hunt-line-layer", "hunt-line")
                .withProperties(
                    PropertyFactory.lineColor("#67E8F9"),
                    PropertyFactory.lineWidth(2.5f),
                    PropertyFactory.lineOpacity(0.9f),
                )
        )
        style.addSource(GeoJsonSource("hunt-guess", pointCollection(null)))
        style.addLayer(
            CircleLayer("hunt-guess-layer", "hunt-guess")
                .withProperties(
                    PropertyFactory.circleColor("#FDE68A"),
                    PropertyFactory.circleRadius(8f),
                    PropertyFactory.circleStrokeColor("#0B1220"),
                    PropertyFactory.circleStrokeWidth(2.5f),
                )
        )
        style.addSource(GeoJsonSource("hunt-answer", pointCollection(null)))
        style.addLayer(
            CircleLayer("hunt-answer-layer", "hunt-answer")
                .withProperties(
                    PropertyFactory.circleColor("#67E8F9"),
                    PropertyFactory.circleRadius(8f),
                    PropertyFactory.circleStrokeColor("#0B1220"),
                    PropertyFactory.circleStrokeWidth(2.5f),
                )
        )
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
