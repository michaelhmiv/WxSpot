package app.wxspot.domain

import java.util.UUID
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class SavedPlace(
    val id: String = UUID.randomUUID().toString(),
    val name: String,
    val lat: Double,
    val lon: Double,
    val timezone: String? = null,
)

@Serializable
data class PlaceSearchResult(val id: String, val name: String, val lat: Double, val lon: Double)

@Serializable
data class LocationSearchResponse(
    val state: String,
    val results: List<PlaceSearchResult> = emptyList(),
    val message: String? = null,
    @SerialName("retry_after_seconds") val retryAfterSeconds: Int? = null,
    val attribution: String = "© OpenStreetMap contributors",
)

@Serializable
data class RadarStation(
    val id: String,
    val name: String,
    val lat: Double,
    val lon: Double,
    @SerialName("distance_km") val distanceKm: Double,
)

@Serializable
data class RadarStationResponse(
    val state: String,
    val stations: List<RadarStation> = emptyList(),
    @SerialName("fetched_at") val fetchedAt: String? = null,
    val message: String? = null,
    val attribution: String = "NOAA Office for Coastal Management",
)
