package app.wxspot.domain

import java.time.Instant
import java.util.UUID
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.double
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonPrimitive

@Serializable
data class Camera(
    val center: List<Double> = listOf(-80.18, 33.02),
    val zoom: Double = 7.5,
    val bearing: Double = 0.0,
    val pitch: Double = 0.0,
)

@Serializable
data class WeatherLayer(
    val id: String = "radar",
    val provider: String = "nws-ridge2",
    @SerialName("source_type") val sourceType: String = "radar",
    val product: String,
    @SerialName("frame_id") val frameId: String,
    @SerialName("valid_time") val validTime: String,
    val opacity: Double = 0.8,
    @SerialName("radar_site") val radarSite: String? = null,
    val elevation: Double? = null,
    val model: String? = null,
    @SerialName("run_time") val runTime: String? = null,
    @SerialName("forecast_hour") val forecastHour: Int? = null,
    @SerialName("vertical_level") val verticalLevel: String? = null,
    val satellite: String? = null,
    val metadata: Map<String, JsonElement> = emptyMap(),
)

@Serializable
data class WeatherContext(
    val version: Int = 1,
    @SerialName("captured_at") val capturedAt: String,
    val camera: Camera,
    val bounds: List<Double>,
    val layers: List<WeatherLayer>,
)

@Serializable
data class GeoGeometry(val type: String, val coordinates: JsonElement) {
    fun vertices(): List<List<Double>> =
        when (type) {
            "Point" -> listOf(coordinates.jsonArray.map { it.jsonPrimitive.double })
            "LineString" ->
                coordinates.jsonArray.map { p -> p.jsonArray.map { it.jsonPrimitive.double } }
            "Polygon" ->
                coordinates.jsonArray.first().jsonArray.map { p ->
                    p.jsonArray.map { it.jsonPrimitive.double }
                }
            else -> emptyList()
        }

    companion object {
        fun of(type: String, points: List<List<Double>>): GeoGeometry {
            fun coordinate(p: List<Double>) = JsonArray(p.map { JsonPrimitive(it) })
            val array = JsonArray(points.map { coordinate(it) })
            return GeoGeometry(
                type,
                when (type) {
                    "Point" -> coordinate(points.first())
                    "Polygon" -> JsonArray(listOf(array))
                    else -> array
                },
            )
        }
    }
}

@Serializable
data class AnnotationElement(
    val id: String = UUID.randomUUID().toString(),
    val tool: String,
    val geometry: GeoGeometry,
    val color: String = "#67E8F9",
    val stroke: Double = 3.0,
    val label: String? = null,
)

@Serializable
data class Profile(
    val id: String,
    @SerialName("display_name") val displayName: String,
    @SerialName("self_role") val selfRole: String = "enthusiast",
    @SerialName("verified_role") val verifiedRole: String? = null,
)

@Serializable
data class LayerArchive(
    @SerialName("layer_id") val layerId: String,
    val url: String,
    val bounds: List<Double>,
)

@Serializable
data class WeatherPost(
    val id: String,
    val author: Profile,
    @SerialName("content_type") val contentType: String,
    val title: String? = null,
    val description: String,
    @SerialName("why_it_matters") val whyItMatters: String? = null,
    @SerialName("watch_next") val watchNext: String? = null,
    val topics: List<String> = emptyList(),
    @SerialName("created_at") val createdAt: String,
    val context: WeatherContext,
    val elements: List<AnnotationElement>,
    val location: List<Double>,
    val archives: List<LayerArchive> = emptyList(),
    val photos: List<String> = emptyList(),
    @SerialName("like_count") val likeCount: Int = 0,
    @SerialName("comment_count") val commentCount: Int = 0,
    val liked: Boolean = false,
    @SerialName("following_author") val followingAuthor: Boolean = false,
)

@Serializable
data class RadarFrame(
    val id: String,
    @SerialName("valid_time") val validTime: String,
    val site: String,
    val product: String,
    val title: String = "",
    @SerialName("tile_url") val tileUrl: String = "",
    val attribution: String = "NOAA / National Weather Service",
    val units: String = "",
    @SerialName("legend_url") val legendUrl: String = "",
    val provider: String = "nws-ridge2",
    @SerialName("source_type") val sourceType: String = "radar",
    val elevation: Double? = null,
    val metadata: Map<String, JsonElement> = emptyMap(),
) {
    fun layer(opacity: Double) =
        WeatherLayer(
            provider = provider,
            sourceType = sourceType,
            product = product,
            frameId = id,
            validTime = validTime,
            radarSite = site.ifBlank { null },
            elevation = elevation,
            opacity = opacity,
            metadata = metadata +
                mapOf(
                    "attribution" to JsonPrimitive(attribution),
                    "units" to JsonPrimitive(units),
                    "legend_url" to JsonPrimitive(legendUrl),
                    "elevation" to (elevation?.let(::JsonPrimitive) ?: JsonPrimitive("")),
                ),
        )

    fun instant(): Instant = Instant.parse(validTime)
}

@Serializable
data class FramesResponse(
    val state: String,
    val frames: List<RadarFrame>,
    val message: String? = null,
)

@Serializable
data class PostsResponse(
    val items: List<WeatherPost>,
    @SerialName("next_cursor") val nextCursor: String? = null,
)

@Serializable
data class Comment(
    val id: String,
    @SerialName("parent_id") val parentId: String? = null,
    val author: Profile,
    val body: String,
    @SerialName("created_at") val createdAt: String,
)

@Serializable
data class CommentsResponse(
    val items: List<Comment>,
    @SerialName("next_cursor") val nextCursor: String? = null,
)

@Serializable
data class PostCreate(
    @SerialName("content_type") val contentType: String,
    val description: String,
    val title: String? = null,
    @SerialName("why_it_matters") val whyItMatters: String? = null,
    @SerialName("watch_next") val watchNext: String? = null,
    val topics: List<String> = emptyList(),
    val context: WeatherContext,
    val elements: List<AnnotationElement>,
    @SerialName("photo_ids") val photoIds: List<String> = emptyList(),
)
