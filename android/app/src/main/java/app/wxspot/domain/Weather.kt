package app.wxspot.domain

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonElement

@Serializable
data class WeatherSelection(
    @SerialName("source_type") val sourceType: String,
    @SerialName("source_id") val sourceId: String,
    @SerialName("product_id") val productId: String,
    val site: String? = null,
    val domain: String? = null,
    val elevation: Double? = null,
    val channel: String? = null,
    val model: String? = null,
    @SerialName("run_time") val runTime: String? = null,
    @SerialName("forecast_hour") val forecastHour: Int? = null,
    @SerialName("vertical_level") val verticalLevel: String? = null,
    @SerialName("selection_generation") val selectionGeneration: Long = 0,
)

@Serializable
data class RenderDescriptor(
    val kind: String,
    @SerialName("url_template") val urlTemplate: String? = null,
    @SerialName("image_url") val imageUrl: String? = null,
    @SerialName("tile_size") val tileSize: Int? = null,
    @SerialName("min_zoom") val minZoom: Int? = null,
    @SerialName("max_zoom") val maxZoom: Int? = null,
    val bounds: List<Double>? = null,
    @SerialName("content_version") val contentVersion: String,
)

@Serializable
data class WeatherFrame(
    val id: String,
    @SerialName("source_type") val sourceType: String,
    val provider: String,
    val product: String,
    @SerialName("valid_time") val validTime: String,
    val render: RenderDescriptor? = null,
    @SerialName("coverage_bounds") val coverageBounds: List<Double>? = null,
    val attribution: String,
    val units: String? = null,
    @SerialName("legend_url") val legendUrl: String? = null,
    val state: String = "ready",
    val site: String? = null,
    val elevation: Double? = null,
    val model: String? = null,
    val domain: String? = null,
    @SerialName("run_time") val runTime: String? = null,
    @SerialName("forecast_hour") val forecastHour: Int? = null,
    @SerialName("vertical_level") val verticalLevel: String? = null,
    val satellite: String? = null,
    val channel: String? = null,
    val metadata: Map<String, JsonElement> = emptyMap(),
)

@Serializable
data class WeatherProduct(
    @SerialName("source_type") val sourceType: String,
    val provider: String,
    @SerialName("source_id") val sourceId: String,
    @SerialName("product_id") val productId: String,
    @SerialName("display_name") val displayName: String,
    val units: String? = null,
    val attribution: String,
    @SerialName("legend_url") val legendUrl: String? = null,
    @SerialName("coverage_bounds") val coverageBounds: List<Double>? = null,
    val capabilities: Map<String, JsonElement> = emptyMap(),
)

@Serializable
data class WeatherCatalogResponse(
    val state: String,
    val products: List<WeatherProduct>,
    @SerialName("fetched_at") val fetchedAt: String? = null,
)

@Serializable
data class WeatherFramesResponse(
    val state: String,
    val frames: List<WeatherFrame>,
    @SerialName("fetched_at") val fetchedAt: String? = null,
    val message: String? = null,
)

@Serializable
data class WeatherTimeline(
    val selection: WeatherSelection,
    val frames: List<WeatherFrame>,
    @SerialName("requested_frame_id") val requestedFrameId: String? = null,
    @SerialName("displayed_frame_id") val displayedFrameId: String? = null,
    val state: String = "loading",
    @SerialName("viewport_generation") val viewportGeneration: Long = 0,
) {
    init {
        require(frames.map { it.id }.distinct().size == frames.size) {
            "Frame IDs must be unique in a timeline."
        }
        require(
            frames.all {
                it.sourceType == selection.sourceType &&
                    it.provider == selection.sourceId &&
                    it.product == selection.productId
            }
        ) {
            "A timeline can contain frames from only its selected source and product."
        }
        require(requestedFrameId == null || frames.any { it.id == requestedFrameId }) {
            "The requested frame must belong to the selected timeline."
        }
        require(displayedFrameId == null || frames.any { it.id == displayedFrameId }) {
            "The displayed frame must belong to the selected timeline."
        }
        require(viewportGeneration >= 0 && selection.selectionGeneration >= 0) {
            "Generation values cannot be negative."
        }
    }
}

@Serializable
data class FrameReadiness(
    @SerialName("source_id") val sourceId: String,
    @SerialName("frame_id") val frameId: String,
    @SerialName("selection_generation") val selectionGeneration: Long,
    @SerialName("viewport_generation") val viewportGeneration: Long,
    val state: String,
    val error: String? = null,
)
