package app.wxspot.domain

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

interface LocationReading {
    val temperature: Double?
    val dewpoint: Double?
    val humidity: Double?
    val windLow: Double?
    val windHigh: Double?
    val direction: String?
    val gust: Double?
}

@Serializable
data class LocationObservation(
    val station: String,
    @SerialName("station_name") val stationName: String,
    @SerialName("sampled_point") val sampledPoint: List<Double>,
    @SerialName("distance_km") val distance: Double,
    @SerialName("observed_at") val observedAt: String,
    @SerialName("age_minutes") val ageMinutes: Int,
    val description: String = "",
    @SerialName("temperature_c") override val temperature: Double? = null,
    @SerialName("dewpoint_c") override val dewpoint: Double? = null,
    @SerialName("humidity_percent") override val humidity: Double? = null,
    @SerialName("wind_low_ms") override val windLow: Double? = null,
    @SerialName("wind_high_ms") override val windHigh: Double? = null,
    @SerialName("wind_direction") override val direction: String? = null,
    @SerialName("gust_ms") override val gust: Double? = null,
    @SerialName("precipitation_last_hour_mm") val rainLastHour: Double? = null,
) : LocationReading

@Serializable
data class LocationForecastPeriod(
    @SerialName("start_time") val start: String,
    @SerialName("end_time") val end: String,
    val name: String = "",
    val daytime: Boolean,
    val summary: String = "",
    val detail: String = "",
    @SerialName("temperature_c") override val temperature: Double? = null,
    @SerialName("dewpoint_c") override val dewpoint: Double? = null,
    @SerialName("humidity_percent") override val humidity: Double? = null,
    @SerialName("wind_low_ms") override val windLow: Double? = null,
    @SerialName("wind_high_ms") override val windHigh: Double? = null,
    @SerialName("wind_direction") override val direction: String? = null,
    @SerialName("gust_ms") override val gust: Double? = null,
    @SerialName("precipitation_chance_percent") val rainChance: Double? = null,
) : LocationReading

@Serializable
data class LocationPrecipitation(
    @SerialName("start_time") val start: String,
    @SerialName("end_time") val end: String,
    @SerialName("amount_mm") val amount: Double? = null,
)

@Serializable
data class LocationWeatherSection(
    val state: String,
    val source: String = "National Weather Service",
    @SerialName("source_url") val sourceUrl: String? = null,
    @SerialName("fetched_at") val fetchedAt: String? = null,
    @SerialName("updated_at") val updatedAt: String? = null,
    val message: String? = null,
    val observation: LocationObservation? = null,
    val periods: List<LocationForecastPeriod> = emptyList(),
    val precipitation: List<LocationPrecipitation> = emptyList(),
)

@Serializable
data class LocationWeatherResponse(
    val state: String,
    @SerialName("requested_point") val requestedPoint: List<Double>,
    val timezone: String? = null,
    @SerialName("place_name") val placeName: String? = null,
    val grid: String? = null,
    val message: String? = null,
    val observation: LocationWeatherSection,
    val hourly: LocationWeatherSection,
    val daily: LocationWeatherSection,
    val amounts: LocationWeatherSection,
)

object LocationUnits {
    fun temperature(celsius: Double, metric: Boolean) = if (metric) celsius else celsius * 1.8 + 32

    fun speed(metresPerSecond: Double, metric: Boolean) =
        metresPerSecond * if (metric) 3.6 else 2.2369362921

    fun rain(millimetres: Double, metric: Boolean) = if (metric) millimetres else millimetres / 25.4
}
