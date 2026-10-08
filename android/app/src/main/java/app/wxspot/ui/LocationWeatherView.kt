package app.wxspot.ui

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import app.wxspot.data.ApiRepository
import app.wxspot.domain.*
import java.time.Duration
import java.time.Instant
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.math.roundToInt

@Composable
fun LocationWeatherContent(point: List<Double>, metric: Boolean, api: ApiRepository) {
    val weather: LocationWeatherViewModel =
        viewModel(
            key = "location-weather",
            factory =
                object : ViewModelProvider.Factory {
                    @Suppress("UNCHECKED_CAST")
                    override fun <T : ViewModel> create(modelClass: Class<T>): T =
                        LocationWeatherViewModel(api) as T
                },
        )
    val state by weather.state.collectAsStateWithLifecycle()
    var section by remember(point) { mutableStateOf("Now") }
    LaunchedEffect(point) { weather.load(point) }
    DisposableEffect(weather) { onDispose { weather.cancel() } }
    HorizontalDivider()
    Text("Location weather", style = MaterialTheme.typography.titleLarge)
    if (state.loading) LinearProgressIndicator(Modifier.fillMaxWidth())
    state.message?.let { Text(it) }
    val response = state.response
    if (response != null) {
        val zone =
            runCatching { ZoneId.of(response.timezone ?: "UTC") }.getOrDefault(ZoneId.of("UTC"))
        Text(
            "${response.placeName.orEmpty()} · ${zone.id}",
            style = MaterialTheme.typography.bodySmall,
        )
        response.message?.let { Text(it) }
        Row(Modifier.horizontalScroll(rememberScrollState())) {
            listOf("Now", "Hourly", "7 days", "Rainfall").forEach { title ->
                FilterChip(section == title, { section = title }, label = { Text(title) })
            }
        }
        val data =
            when (section) {
                "Hourly" -> response.hourly
                "7 days" -> response.daily
                "Rainfall" -> response.amounts
                else -> response.observation
            }
        Text(
            data.source + if (data.state == "stale") " · Older / cached data" else "",
            style = MaterialTheme.typography.titleSmall,
        )
        data.updatedAt?.let {
            Text(
                "${if (section == "Now") "Observed" else "Issued"} ${weatherTime(it, zone)}",
                style = MaterialTheme.typography.bodySmall,
            )
        }
        if (data.state in setOf("source_unavailable", "no_data"))
            Text(data.message ?: "No data is available for this section.")
        else data.message?.let { Text(it) }
        data.observation?.let { observation ->
            Text(
                "${observation.stationName} (${observation.station}) · ${"%.1f".format(observation.distance * if (metric) 1.0 else .621371)} ${if (metric) "km" else "mi"} away"
            )
            val age =
                runCatching {
                        Duration.between(Instant.parse(observation.observedAt), Instant.now())
                            .toMinutes()
                            .coerceAtLeast(0)
                    }
                    .getOrDefault(observation.ageMinutes.toLong())
            Text("Observation age: $age min · ${observation.description}")
            Text(
                "Station ${"%.4f".format(observation.sampledPoint[1])}, ${"%.4f".format(observation.sampledPoint[0])}",
                style = MaterialTheme.typography.bodySmall,
            )
            WeatherReading(observation, metric)
            Text("Rain in the last hour: ${rainAmount(observation.rainLastHour, metric)}")
        }
        data.periods.forEach { period ->
            HorizontalDivider()
            Text(
                (period.name.ifEmpty { weatherTime(period.start, zone) }) +
                    " · " +
                    if (section == "7 days") (if (period.daytime) "Daytime" else "Night")
                    else "Hourly forecast",
                style = MaterialTheme.typography.titleSmall,
            )
            if (section == "7 days")
                Text(
                    "${weatherTime(period.start, zone)} – ${weatherTime(period.end, zone)}",
                    style = MaterialTheme.typography.bodySmall,
                )
            Text(period.summary)
            WeatherReading(period, metric)
            Text(
                "Precipitation chance: ${period.rainChance?.roundToInt()?.let { "$it%" } ?: "Unavailable"}"
            )
            if (section == "7 days" && period.detail.isNotBlank())
                Text(
                    "NWS narrative (°F, mph): ${period.detail}",
                    style = MaterialTheme.typography.bodySmall,
                )
        }
        data.precipitation.forEach { amount ->
            HorizontalDivider()
            Text(
                "${weatherTime(amount.start, zone)} – ${weatherTime(amount.end, zone)}",
                style = MaterialTheme.typography.titleSmall,
            )
            Text("Rainfall total: ${rainAmount(amount.amount, metric)}")
        }
    }
    TextButton({ weather.load(point) }) { Text("Refresh weather") }
}

private fun weatherTime(time: String, zone: ZoneId): String =
    runCatching {
            DateTimeFormatter.ofPattern("EEE MMM d, HH:mm z", Locale.getDefault())
                .format(Instant.parse(time).atZone(zone))
        }
        .getOrDefault(time)

private fun temperature(value: Double?, metric: Boolean) =
    value?.let { "%.1f°%s".format(LocationUnits.temperature(it, metric), if (metric) "C" else "F") }
        ?: "Unavailable"

private fun rainAmount(value: Double?, metric: Boolean) =
    value?.let { "%.2f %s".format(LocationUnits.rain(it, metric), if (metric) "mm" else "in") }
        ?: "Unavailable"

private fun speed(value: Double?, metric: Boolean) =
    value?.let { "%.1f %s".format(LocationUnits.speed(it, metric), if (metric) "km/h" else "mph") }
        ?: "Unavailable"

@Composable
private fun WeatherReading(value: LocationReading, metric: Boolean) {
    Text(
        "Temperature ${temperature(value.temperature, metric)} · Dew point ${temperature(value.dewpoint, metric)}"
    )
    Text("Humidity ${value.humidity?.roundToInt()?.let { "$it%" } ?: "Unavailable"}")
    Text(
        "Wind ${value.direction.orEmpty()} ${speed(value.windLow, metric)}" +
            if (value.windHigh != null && value.windHigh != value.windLow)
                " – ${speed(value.windHigh, metric)}"
            else ""
    )
    Text("Gusts ${speed(value.gust, metric)}")
}
