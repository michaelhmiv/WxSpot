package app.wxspot.ui

import android.graphics.Paint
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.awaitEachGesture
import androidx.compose.foundation.gestures.awaitFirstDown
import androidx.compose.foundation.gestures.calculatePan
import androidx.compose.foundation.gestures.calculateZoom
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.DrawScope
import androidx.compose.ui.graphics.drawscope.clipRect
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import app.wxspot.domain.*
import app.wxspot.ui.theme.WxGame
import java.time.Duration
import java.time.Instant
import kotlin.math.*
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive

@Composable
fun SoundingHuntChart(sounding: HuntSounding, reset: Int) {
    val profile =
        remember(sounding) {
            SoundingProfile(
                identity = "hunt:" + sounding.observationTime,
                kind = "observed",
                source = "Observed radiosonde",
                validTime = sounding.observationTime,
                sampledPoint = emptyList(),
                terrain = 0.0,
                method = "IGRA observation",
                fetchedAt = sounding.observationTime,
                levels =
                    sounding.levels.map { level ->
                        SoundingLevel(
                            pressure = level.pressureHpa,
                            temperature = level.temperatureC,
                            dewpoint = level.dewpointC,
                            height = level.heightMAGL,
                            u = level.uMs,
                            v = level.vMs,
                        )
                    },
            )
        }
    SoundingChart(
        profile = profile,
        diagnostics = null,
        hodo = false,
        reset = reset,
        dragMotion = false,
        customMotion = { _, _ -> },
    )
}

@Composable
fun SoundingPanel(mapState: UiState, vm: MapViewModel) {
    val point = mapState.selectedSoundingPoint ?: mapState.camera.center
    val sounding: SoundingViewModel =
        viewModel(
            key = "point-sounding",
            factory =
                object : ViewModelProvider.Factory {
                    @Suppress("UNCHECKED_CAST")
                    override fun <T : ViewModel> create(modelClass: Class<T>): T =
                        SoundingViewModel(vm.api) as T
                },
        )
    val response by sounding.state.collectAsStateWithLifecycle()
    val stations by sounding.stations.collectAsStateWithLifecycle()
    var kind by remember(point) { mutableStateOf("forecast") }
    var parcel by remember { mutableStateOf("sb") }
    var motion by remember { mutableStateOf("rm") }
    var stormU by remember { mutableStateOf("10") }
    var stormV by remember { mutableStateOf("5") }
    var station by remember(point) { mutableStateOf<String?>(null) }
    var launch by remember(station) { mutableStateOf<String?>(null) }
    val run = mapState.modelRunTime
    var hour by remember(point, run) { mutableIntStateOf(mapState.currentFrame?.forecastHour ?: 0) }
    var chart by remember { mutableStateOf("Skew-T") }
    var reset by remember { mutableIntStateOf(0) }
    var retry by remember { mutableIntStateOf(0) }
    val parameters = buildMap {
        put("kind", kind)
        put("lon", point[0].toString())
        put("lat", point[1].toString())
        put("parcel", parcel)
        put("motion", motion)
        if (retry > 0) put("retry_failed", "true")
        if (kind == "forecast" && run != null) {
            put("model", mapState.modelName)
            put("domain", "conus")
            put("run_time", run)
            put("forecast_hour", hour.toString())
        } else if (kind == "observed") {
            (station ?: stations.firstOrNull()?.id)?.let { put("station", it) }
            launch?.let { put("launch", it) }
        }
        if (motion == "custom") {
            stormU
                .toDoubleOrNull()
                ?.takeIf { it in -100.0..100.0 }
                ?.let { put("storm_u", it.toString()) }
            stormV
                .toDoubleOrNull()
                ?.takeIf { it in -100.0..100.0 }
                ?.let { put("storm_v", it.toString()) }
        }
    }
    val valid =
        (kind == "forecast" && run != null || kind == "observed" && "station" in parameters) &&
            (motion != "custom" || "storm_u" in parameters && "storm_v" in parameters)
    LaunchedEffect(point) { sounding.nearby(point) }
    LaunchedEffect(parameters, retry, valid) { if (valid) sounding.load(parameters, point) }
    DisposableEffect(sounding) { onDispose { sounding.cancel() } }
    Column(Modifier.fillMaxWidth().height(630.dp).imePadding().padding(horizontal = 12.dp)) {
        Column(
            Modifier.weight(1f).verticalScroll(rememberScrollState()),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text("Point sounding", style = MaterialTheme.typography.titleLarge)
            Row(Modifier.horizontalScroll(rememberScrollState())) {
                listOf("forecast" to "Forecast", "observed" to "Observed launch").forEach {
                    (id, text) ->
                    FilterChip(kind == id, { kind = id }, label = { Text(text) })
                }
            }
            if (kind == "observed") {
                Text("Nearby radiosonde stations · select a measured launch")
                Row(Modifier.horizontalScroll(rememberScrollState())) {
                    stations.forEach { s ->
                        FilterChip(
                            (station ?: stations.firstOrNull()?.id) == s.id,
                            { station = s.id },
                            label = { Text("${s.name} · ${s.distance?.roundToInt()} km") },
                        )
                    }
                }
                if (stations.isEmpty()) Text("Station inventory unavailable. Retry when connected.")
            }
            if (!valid)
                Text(
                    if (run == null && kind == "forecast") "Waiting for a published model run."
                    else "Enter valid east/north motion components (−100 to 100 m/s)."
                )
            val profile = response?.profile
            if (profile != null) {
                Text(
                    if (profile.kind == "forecast")
                        "${profile.model?.uppercase()} · ${profile.runTime?.take(16)} UTC · F${profile.forecastHour}"
                    else "${profile.stationName} · ${profile.station}"
                )
                val age =
                    runCatching {
                            Duration.between(Instant.parse(profile.validTime), Instant.now())
                                .toMinutes()
                        }
                        .getOrDefault(0)
                Text(
                    "Valid ${profile.validTime.take(16).replace('T', ' ')} UTC" +
                        if (kind == "observed") " · launch ${age / 60} h ${age % 60} min ago"
                        else ""
                )
                Text(
                    "Sample ${"%.4f".format(profile.sampledPoint[1])}, ${"%.4f".format(profile.sampledPoint[0])} · ${"%.1f".format(response?.distanceKm ?: 0.0)} km from requested point · terrain ${profile.terrain.roundToInt()} m MSL",
                    style = MaterialTheme.typography.bodySmall,
                )
                Row(Modifier.horizontalScroll(rememberScrollState())) {
                    listOf("Skew-T", "Hodograph").forEach { name ->
                        FilterChip(chart == name, { chart = name }, label = { Text(name) })
                    }
                }
                Text(
                    if (chart == "Skew-T")
                        "Temperature/dew point °C · pressure hPa · wind barbs knots. Two fingers zoom/pan; drag to read a level."
                    else
                        "Earth-relative winds m/s. Red <1 km, yellow 1–3, green 3–6, cyan 6–9, purple >9 km AGL. Drag with Custom motion to move its marker.",
                    style = MaterialTheme.typography.bodySmall,
                )
                SoundingChart(
                    profile,
                    response?.diagnostics,
                    chart == "Hodograph",
                    reset,
                    motion == "custom",
                ) { u, v ->
                    stormU = "%.1f".format(java.util.Locale.US, u.coerceIn(-100.0, 100.0))
                    stormV = "%.1f".format(java.util.Locale.US, v.coerceIn(-100.0, 100.0))
                }
                response?.diagnostics?.let { diagnostics ->
                    Text("Profile diagnostics", style = MaterialTheme.typography.titleMedium)
                    diagnostics.metrics.forEach { (name, metric) ->
                        Text(
                            "${name.replace('_', ' ').uppercase()} · ${metric.value?.let { "%.1f".format(it) } ?: "Unavailable"} ${metric.units}" +
                                if (metric.value == null) " · ${metric.reason.orEmpty()}" else "",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                    diagnostics.vectors.forEach { (name, vector) ->
                        Text(
                            "${name.replace('_', ' ')} u/v · ${vector?.let { "%.1f / %.1f m/s".format(it[0], it[1]) } ?: "Unavailable"}",
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                    diagnostics.quality.forEach {
                        Text(it, style = MaterialTheme.typography.bodySmall)
                    }
                    Text(diagnostics.method, style = MaterialTheme.typography.bodySmall)
                }
                Text(
                    profile.source + " · " + profile.method,
                    style = MaterialTheme.typography.bodySmall,
                )
                profile.quality.forEach { Text(it, style = MaterialTheme.typography.bodySmall) }
            }
            if (response?.state == "preparing") {
                LinearProgressIndicator(Modifier.fillMaxWidth())
                Text("Preparing profile and parcel diagnostics…")
            }
            response?.message?.let { Text(it) }
        }
        if (kind == "forecast") {
            val hours =
                response?.options?.get("forecast_hours")?.jsonArray?.mapNotNull {
                    it.jsonPrimitive.intOrNull
                } ?: mapState.frames.mapNotNull { it.forecastHour }.distinct().sorted()
            val index = hours.indexOf(hour)
            Row {
                TextButton({ hour = hours[index - 1] }, enabled = index > 0) {
                    Text("Previous hour")
                }
                Text("F$hour", Modifier.padding(12.dp))
                TextButton(
                    { hour = hours[index + 1] },
                    enabled = index >= 0 && index < hours.lastIndex,
                ) {
                    Text("Next hour")
                }
            }
        } else {
            val launches =
                response
                    ?.options
                    ?.get("launches")
                    ?.jsonArray
                    ?.map { it.jsonPrimitive.content }
                    .orEmpty()
            Row(Modifier.horizontalScroll(rememberScrollState())) {
                launches.asReversed().forEach { time ->
                    FilterChip(
                        (launch ?: response?.profile?.validTime) == time,
                        { launch = time },
                        label = { Text(time.take(16).replace('T', ' ') + " UTC") },
                    )
                }
            }
        }
        Row(Modifier.horizontalScroll(rememberScrollState())) {
            listOf("sb" to "SB", "ml100" to "ML100", "mu300" to "MU300").forEach { (id, title) ->
                FilterChip(parcel == id, { parcel = id }, label = { Text(title) })
            }
            listOf("rm" to "RM", "lm" to "LM", "custom" to "Custom motion").forEach { (id, title) ->
                FilterChip(motion == id, { motion = id }, label = { Text(title) })
            }
        }
        if (motion == "custom")
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                OutlinedTextField(
                    stormU,
                    { stormU = it.take(7) },
                    label = { Text("East u (m/s)") },
                    singleLine = true,
                    modifier = Modifier.weight(1f),
                )
                OutlinedTextField(
                    stormV,
                    { stormV = it.take(7) },
                    label = { Text("North v (m/s)") },
                    singleLine = true,
                    modifier = Modifier.weight(1f),
                )
            }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceEvenly) {
            TextButton({ reset++ }) { Text("Reset view") }
            TextButton({
                retry++
                sounding.nearby(point)
            }) {
                Text("Retry")
            }
            TextButton({ vm.sheet(null) }) { Text("Close") }
        }
    }
}

@Composable
private fun SoundingChart(
    profile: SoundingProfile,
    diagnostics: SoundingDiagnostics?,
    hodo: Boolean,
    reset: Int,
    dragMotion: Boolean,
    customMotion: (Double, Double) -> Unit,
) {
    var zoom by remember(profile.identity, hodo, reset) { mutableFloatStateOf(1f) }
    var pan by remember(profile.identity, hodo, reset) { mutableStateOf(Offset.Zero) }
    var cursor by remember(profile.identity, hodo, reset) { mutableStateOf<Offset?>(null) }
    var dimensions by remember { mutableStateOf(androidx.compose.ui.geometry.Size.Zero) }
    val coordinate = cursor?.let { (it - pan) / zoom }
    val transform = SkewTransform(dimensions.width.toDouble(), dimensions.height.toDouble())
    val level =
        coordinate
            ?.takeIf { !hodo && dimensions.height > 0 }
            ?.let { position ->
                val p = transform.pressure(position.y.toDouble())
                profile.levels.minByOrNull { abs(ln(it.pressure / p)) }
            }
    val scienceBackground = WxGame.colors.chart
    Column {
        Canvas(
            Modifier.fillMaxWidth()
                .height(310.dp)
                .semantics {
                    contentDescription =
                        if (hodo) "Interactive earth-relative hodograph"
                        else "Interactive Skew-T log-pressure chart"
                }
                .pointerInput(profile.identity, hodo, dragMotion, reset) {
                    awaitEachGesture {
                        val down = awaitFirstDown(requireUnconsumed = false)
                        cursor = down.position
                        do {
                            val event = awaitPointerEvent()
                            if (event.changes.count { it.pressed } > 1) {
                                zoom = (zoom * event.calculateZoom()).coerceIn(1f, 5f)
                                pan += event.calculatePan()
                            } else
                                event.changes
                                    .firstOrNull { it.pressed }
                                    ?.let { change ->
                                        cursor = change.position
                                        if (hodo && dragMotion && dimensions.width > 0) {
                                            val p = (change.position - pan) / zoom
                                            val scale =
                                                min(dimensions.width, dimensions.height) / 100f
                                            customMotion(
                                                ((p.x - dimensions.width / 2f) / scale).toDouble(),
                                                ((dimensions.height / 2f - p.y) / scale).toDouble(),
                                            )
                                        }
                                    }
                            event.changes.forEach { it.consume() }
                        } while (event.changes.any { it.pressed })
                    }
                }
        ) {
            dimensions = size
            drawRect(scienceBackground)
            clipRect {
                withTransform({
                    translate(pan.x, pan.y)
                    scale(zoom, zoom, pivot = Offset.Zero)
                }) {
                    if (hodo) drawHodograph(profile, diagnostics)
                    else drawSkew(profile, diagnostics)
                    coordinate?.let { p ->
                        drawLine(
                            Color.White.copy(alpha = .6f),
                            Offset(p.x, 0f),
                            Offset(p.x, size.height),
                        )
                        drawLine(
                            Color.White.copy(alpha = .6f),
                            Offset(0f, p.y),
                            Offset(size.width, p.y),
                        )
                    }
                }
            }
        }
        level?.let { l ->
            Text(
                "${l.pressure.roundToInt()} hPa · ${l.height?.minus(profile.terrain)?.roundToInt() ?: "—"} m AGL · T ${l.temperature?.let { "%.1f".format(it) } ?: "—"}°C · Td ${l.dewpoint?.let { "%.1f".format(it) } ?: "—"}°C · u/v ${l.u?.let { "%.1f".format(it) } ?: "—"} / ${l.v?.let { "%.1f".format(it) } ?: "—"} m/s",
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}

private fun DrawScope.label(text: String, point: Offset, color: Color = Color.LightGray) {
    val paint =
        Paint(Paint.ANTI_ALIAS_FLAG).apply {
            this.color =
                android.graphics.Color.rgb(
                    (color.red * 255).toInt(),
                    (color.green * 255).toInt(),
                    (color.blue * 255).toInt(),
                )
            textSize = 12.dp.toPx()
        }
    drawContext.canvas.nativeCanvas.drawText(text, point.x, point.y, paint)
}

private fun DrawScope.drawSkew(profile: SoundingProfile, diagnostics: SoundingDiagnostics?) {
    val transform = SkewTransform(size.width.toDouble(), size.height.toDouble())
    fun xy(t: Double, p: Double) = Offset(transform.x(t, p).toFloat(), transform.y(p).toFloat())
    listOf(1000, 850, 700, 500, 300, 200, 100).forEach { p ->
        val y = transform.y(p.toDouble()).toFloat()
        drawLine(Color(0xFF334155), Offset(0f, y), Offset(size.width, y))
        // The surface-pressure label otherwise collides with the bottom temperature ticks.
        val yLabel = if (p >= 1000) y - 18.dp.toPx() else y - 3f
        label("$p", Offset(2f, yLabel))
    }
    for (t in -100..50 step 10) {
        drawLine(Color(0xFF334155), xy(t.toDouble(), 1050.0), xy(t.toDouble(), 100.0))
        if (t >= -50) label("$t", xy(t.toDouble(), 1050.0).copy(y = size.height - 4))
    }
    diagnostics?.guides?.forEach { (name, lines) ->
        val color =
            when (name) {
                "dry" -> Color(0xFFAF705D)
                "moist" -> Color(0xFF447F87)
                else -> Color(0xFF566543)
            }.copy(alpha = .6f)
        lines.forEach { line ->
            line.zipWithNext().forEach { (a, b) ->
                drawLine(color, xy(a[1], a[0]), xy(b[1], b[0]), 1f)
            }
        }
    }
    diagnostics?.parcelTrace?.zipWithNext()?.forEach { (a, b) ->
        val path =
            Path().apply {
                moveTo(xy(a.parcelVirtual, a.pressure).x, xy(a.parcelVirtual, a.pressure).y)
                lineTo(xy(b.parcelVirtual, b.pressure).x, xy(b.parcelVirtual, b.pressure).y)
                lineTo(
                    xy(b.environmentVirtual, b.pressure).x,
                    xy(b.environmentVirtual, b.pressure).y,
                )
                lineTo(
                    xy(a.environmentVirtual, a.pressure).x,
                    xy(a.environmentVirtual, a.pressure).y,
                )
                close()
            }
        if (a.shade != null && a.shade == b.shade)
            drawPath(path, (if (a.shade == "cape") Color.Red else Color.Cyan).copy(alpha = .18f))
        drawLine(
            Color(0xFFFDE68A),
            xy(a.temperature, a.pressure),
            xy(b.temperature, b.pressure),
            2.dp.toPx(),
        )
    }
    for ((field, color) in
        listOf<(SoundingLevel) -> Double?>({ it.temperature }, { it.dewpoint })
            .zip(listOf(Color(0xFFFF7676), Color(0xFF60D99A)))) {
        profile.levels.zipWithNext().forEach { (a, b) ->
            val ta = field(a)
            val tb = field(b)
            if (ta != null && tb != null && a.pressure - b.pressure <= 150)
                drawLine(color, xy(ta, a.pressure), xy(tb, b.pressure), 2.dp.toPx())
        }
    }
    profile.levels
        .filter { it.u != null && it.v != null }
        .filterIndexed { index, _ -> index % max(1, profile.levels.size / 18) == 0 }
        .forEach { l ->
            val u = l.u!!
            val v = l.v!!
            val speed = hypot(u, v)
            if (speed < .3)
                drawCircle(
                    Color.White,
                    3f,
                    Offset(size.width - 18, transform.y(l.pressure).toFloat()),
                )
            else {
                val base = Offset(size.width - 18, transform.y(l.pressure).toFloat())
                val direction = Offset((-u / speed).toFloat(), (v / speed).toFloat())
                val end = base + direction * 24.dp.toPx()
                drawLine(Color.White, base, end, 1.5f)
                val normal = Offset(-direction.y, direction.x)
                var knots = (speed * 1.943844 / 5).roundToInt() * 5
                var distance = 0f
                while (knots >= 50) {
                    val at = end - direction * distance
                    val flag =
                        Path().apply {
                            moveTo(at.x, at.y)
                            lineTo((at + normal * 9.dp.toPx()).x, (at + normal * 9.dp.toPx()).y)
                            lineTo(
                                (at - direction * 5.dp.toPx()).x,
                                (at - direction * 5.dp.toPx()).y,
                            )
                            close()
                        }
                    drawPath(flag, Color.White)
                    distance += 6.dp.toPx()
                    knots -= 50
                }
                while (knots >= 5) {
                    val at = end - direction * distance
                    drawLine(
                        Color.White,
                        at,
                        at + normal * (if (knots >= 10) 8.dp.toPx() else 4.dp.toPx()),
                        1.5f,
                    )
                    distance += 3.dp.toPx()
                    knots -= if (knots >= 10) 10 else 5
                }
            }
        }
    diagnostics?.markers?.forEach { (name, marker) ->
        val p = marker["pressure_hpa"]
        val t = marker["temperature_c"]
        if (p != null && t != null) {
            val point = xy(t, p)
            drawCircle(Color(0xFFFDE68A), 4.dp.toPx(), point)
            label(name.uppercase(), point + Offset(6f, -6f))
        }
    }
}

private fun DrawScope.drawHodograph(profile: SoundingProfile, diagnostics: SoundingDiagnostics?) {
    val scale = min(size.width, size.height) / 100f
    val center = Offset(size.width / 2, size.height / 2)
    fun xy(u: Double, v: Double) = center + Offset(u.toFloat() * scale, -v.toFloat() * scale)
    drawLine(Color(0xFF64748B), Offset(0f, center.y), Offset(size.width, center.y))
    drawLine(Color(0xFF64748B), Offset(center.x, 0f), Offset(center.x, size.height))
    for (speed in 10..40 step 10) {
        drawCircle(
            Color(0xFF334155),
            speed * scale,
            center,
            style = androidx.compose.ui.graphics.drawscope.Stroke(1f),
        )
        val angle = Math.toRadians(45.0 + (speed / 10 - 1) * 90.0)
        label(
            "$speed",
            center +
                Offset(
                    (cos(angle) * speed * scale).toFloat(),
                    (sin(angle) * speed * scale).toFloat(),
                ),
        )
    }
    label("N (+v)", Offset(center.x + 4, 16.dp.toPx()))
    label("E (+u)", Offset(size.width - 45.dp.toPx(), center.y - 4))
    fun color(z: Double) =
        when {
            z < 1000 -> Color(0xFFFF7676)
            z < 3000 -> Color(0xFFFDE68A)
            z < 6000 -> Color(0xFF60D99A)
            z < 9000 -> Color.Cyan
            else -> Color(0xFFC084FC)
        }
    val levels = profile.levels.filter { it.u != null && it.v != null && it.height != null }
    levels.zipWithNext().forEach { (a, b) ->
        if (b.height!! - a.height!! in 0.0..1500.0)
            drawLine(
                color((a.height!! + b.height!!) / 2 - profile.terrain),
                xy(a.u!!, a.v!!),
                xy(b.u!!, b.v!!),
                2.5.dp.toPx(),
            )
    }
    for ((index, height) in listOf(0, 1, 3, 6, 9).withIndex()) levels
        .minByOrNull { abs(it.height!! - profile.terrain - height * 1000) }
        ?.takeIf { abs(it.height!! - profile.terrain - height * 1000) < 500 }
        ?.let {
            val point = xy(it.u!!, it.v!!)
            val title = Offset(6.dp.toPx(), (16 + index * 18).dp.toPx())
            val shade = color(height * 1000.0)
            drawCircle(shade, 3.dp.toPx(), point)
            drawLine(
                shade.copy(alpha = .25f),
                title + Offset(28.dp.toPx(), -4.dp.toPx()),
                point,
                1f,
            )
            label("$height km", title, shade)
        }
    diagnostics?.vectors?.get("selected")?.let { motion ->
        val point = xy(motion[0], motion[1])
        drawCircle(
            Color.White,
            6.dp.toPx(),
            point,
            style = androidx.compose.ui.graphics.drawscope.Stroke(2.dp.toPx()),
        )
        label("Motion", point + Offset(6f, -6f), Color.White)
    }
}
