package app.wxspot.domain

import kotlin.math.exp
import kotlin.math.ln
import kotlin.math.tan
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

@Serializable
data class SoundingLevel(
    @SerialName("pressure_hpa") val pressure: Double,
    @SerialName("temperature_c") val temperature: Double? = null,
    @SerialName("dewpoint_c") val dewpoint: Double? = null,
    @SerialName("height_m_msl") val height: Double? = null,
    @SerialName("u_ms") val u: Double? = null,
    @SerialName("v_ms") val v: Double? = null,
    val quality: List<String> = emptyList(),
)

@Serializable
data class SoundingProfile(
    val identity: String,
    val kind: String,
    val source: String,
    val model: String? = null,
    val domain: String? = null,
    @SerialName("run_time") val runTime: String? = null,
    @SerialName("forecast_hour") val forecastHour: Int? = null,
    @SerialName("valid_time") val validTime: String,
    val station: String? = null,
    @SerialName("station_name") val stationName: String? = null,
    @SerialName("sampled_point") val sampledPoint: List<Double>,
    @SerialName("terrain_m_msl") val terrain: Double,
    val method: String,
    @SerialName("fetched_at") val fetchedAt: String,
    val levels: List<SoundingLevel>,
    val quality: List<String> = emptyList(),
)

@Serializable
data class SoundingMetric(
    val value: Double? = null,
    val units: String,
    val reason: String? = null,
    val quality: String = "valid",
    val method: String = "",
)

@Serializable
data class SoundingTrace(
    @SerialName("pressure_hpa") val pressure: Double,
    @SerialName("temperature_c") val temperature: Double,
    @SerialName("environment_c") val environment: Double,
    @SerialName("virtual_difference_k") val difference: Double,
    @SerialName("environment_virtual_c") val environmentVirtual: Double,
    @SerialName("parcel_virtual_c") val parcelVirtual: Double,
    val shade: String? = null,
)

@Serializable
data class SoundingDiagnostics(
    val identity: String,
    val parcel: String,
    val motion: String,
    val metrics: Map<String, SoundingMetric>,
    val vectors: Map<String, List<Double>?>,
    @SerialName("parcel_trace") val parcelTrace: List<SoundingTrace> = emptyList(),
    val markers: Map<String, Map<String, Double?>> = emptyMap(),
    val guides: Map<String, List<List<List<Double>>>> = emptyMap(),
    val method: String,
    val quality: List<String> = emptyList(),
)

@Serializable
data class SoundingResponse(
    val state: String,
    val profile: SoundingProfile? = null,
    val diagnostics: SoundingDiagnostics? = null,
    @SerialName("requested_point") val requestedPoint: List<Double>,
    @SerialName("distance_km") val distanceKm: Double? = null,
    val message: String? = null,
    val options: Map<String, JsonElement> = emptyMap(),
)

@Serializable
data class SoundingStation(
    val id: String,
    val lat: Double,
    val lon: Double,
    val name: String,
    @SerialName("distance_km") val distance: Double? = null,
)

@Serializable
data class SoundingStations(
    val state: String,
    val stations: List<SoundingStation> = emptyList(),
    val message: String? = null,
)

/** Log pressure and an affine 30-degree skew, reversible in native chart pixels. */
class SkewTransform(val width: Double, val height: Double) {
    fun y(pressure: Double) = ln(pressure / 100.0) / ln(10.5) * height

    fun x(temperature: Double, pressure: Double) =
        (temperature + 50.0) / 100.0 * width + (height - y(pressure)) * tan(Math.PI / 6.0)

    fun pressure(y: Double) = 100.0 * exp(y / height * ln(10.5))

    fun temperature(x: Double, y: Double) =
        (x - (height - y) * tan(Math.PI / 6.0)) / width * 100.0 - 50.0
}
