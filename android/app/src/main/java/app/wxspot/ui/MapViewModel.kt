package app.wxspot.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.wxspot.data.ApiException
import app.wxspot.data.ApiRepository
import app.wxspot.data.DraftStore
import app.wxspot.data.PlacesStore
import app.wxspot.data.Session
import app.wxspot.domain.AlertLifetime
import app.wxspot.domain.AnnotationElement
import app.wxspot.domain.Camera
import app.wxspot.domain.Comment
import app.wxspot.domain.Draft
import app.wxspot.domain.EditorState
import app.wxspot.domain.FrameReadiness
import app.wxspot.domain.FrameReadinessTracker
import app.wxspot.domain.GeoGeometry
import app.wxspot.domain.PlaceSearchResult
import app.wxspot.domain.PostCreate
import app.wxspot.domain.RadarFrame
import app.wxspot.domain.RadarStation
import app.wxspot.domain.ReplaySession
import app.wxspot.domain.SavedPlace
import app.wxspot.domain.Tool
import app.wxspot.domain.WeatherContext
import app.wxspot.domain.WeatherPost
import app.wxspot.domain.WeatherSelection
import app.wxspot.domain.mapFrame
import app.wxspot.domain.weatherModeFor
import java.time.Instant
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put

data class PendingMark(val point: List<Double>, val context: WeatherContext)

private fun radarProductTitle(product: String): String =
    when (product) {
        "reflectivity" -> "Reflectivity"
        "precip_rate" -> "Estimated precipitation rate"
        "precip_1h" -> "1-hour radar-only accumulation"
        "precip_3h" -> "3-hour radar-only accumulation"
        "precip_24h" -> "24-hour radar-only accumulation"
        "velocity" -> "Base radial velocity"
        "storm_relative_velocity" -> "Storm-relative velocity"
        "correlation_coefficient" -> "Correlation coefficient"
        "differential_reflectivity" -> "Differential reflectivity"
        "specific_differential_phase" -> "Specific differential phase"
        "geocolor" -> "GeoColor"
        "visible" -> "Visible · C02"
        "infrared" -> "Clean longwave IR · C13"
        "water_vapor_upper" -> "Upper water vapor · C08"
        "water_vapor_mid" -> "Middle water vapor · C09"
        "water_vapor_lower" -> "Lower water vapor · C10"
        "temperature" -> "2 m temperature"
        "dew_point" -> "2 m dew point"
        "wind" -> "10 m wind speed and direction"
        "gust" -> "Forecast surface gust"
        "precip_interval" -> "Precipitation · actual interval"
        "precip_total" -> "Precipitation · run total"
        "cape" -> "Surface-based CAPE"
        "cin" -> "Surface-based CIN"
        "pwat" -> "Precipitable water"
        else -> product.replace('_', ' ')
    }

data class UiState(
    val radarSourceId: String = "nws-ridge2",
    val site: String = "KCLX",
    val product: String = "reflectivity",
    val radarElevation: Double? = null,
    val availableElevations: List<Double> = emptyList(),
    val satelliteSector: String = "east",
    val modelName: String = "hrrr",
    val modelDomain: String = "conus",
    val modelRunTime: String? = null,
    val modelForecastHour: Int? = null,
    val weatherOptions: Map<String, JsonElement> = emptyMap(),
    val preparedFrameIds: Set<String> = emptySet(),
    val frames: List<RadarFrame> = emptyList(),
    val viewingId: String? = null,
    val displayedFrame: RadarFrame? = null,
    val selectionGeneration: Long = 0,
    val viewportGeneration: Long = 0,
    val displayedSelectionGeneration: Long? = null,
    val displayedViewportGeneration: Long? = null,
    val mapActive: Boolean = true,
    val sourceState: String = "loading",
    val rasterState: String = "loading",
    val camera: Camera = Camera(),
    val activeTab: String = "Radar",
    val weatherMode: String = "Radar",
    val savedPlaces: List<SavedPlace> = emptyList(),
    val metricUnits: Boolean = false,
    val selectedPoint: List<Double>? = null,
    val selectedSoundingPoint: List<Double>? = null,
    val selectingSounding: Boolean = false,
    val gpsPoint: List<Double>? = null,
    val gpsMessage: String? = null,
    val placeSearchResults: List<PlaceSearchResult> = emptyList(),
    val placeSearchState: String = "idle",
    val placeSearchMessage: String? = null,
    val radarStations: List<RadarStation> = emptyList(),
    val radarStationState: String = "idle",
    val bounds: List<Double> = listOf(-82.0, 31.5, -78.0, 34.5),
    val cameraRevision: Int = 0,
    val opacity: Double = 0.8,
    val posts: List<WeatherPost> = emptyList(),
    val socialState: String = "loading",
    val sort: String = "recent",
    val typeFilter: String? = null,
    val topicFilter: String? = null,
    val verifiedOnly: Boolean = false,
    val alerts: String = """{"type":"FeatureCollection","features":[]}""",
    val alertsState: String = "loading",
    val showAlerts: Boolean = true,
    val officialSelection: JsonObject? = null,
    val selected: WeatherPost? = null,
    val replay: ReplaySession? = null,
    val comments: List<Comment> = emptyList(),
    val commentsCursor: String? = null,
    val commentsLoading: Boolean = false,
    val draft: Draft? = null,
    val editor: EditorState = EditorState(),
    val tool: Tool = Tool.ARROW,
    val color: String = "#67E8F9",
    val stroke: Double = 3.0,
    val textLabel: String = "",
    val textPoint: List<Double>? = null,
    val pending: PendingMark? = null,
    val session: Session? = null,
    val sheet: String? = null,
    val cluster: List<WeatherPost> = emptyList(),
    val message: String? = null,
    val busy: Boolean = false,
    val playing: Boolean = false,
    val followLive: Boolean = true,
    val expandedPost: Boolean = false,
    val notifications: List<JsonObject> = emptyList(),
    val blockedPeople: List<JsonObject> = emptyList(),
    val feedItems: List<WeatherPost> = emptyList(),
    val feedCursor: String? = null,
    val feedScope: String = "nearby",
    val feedLoading: Boolean = false,
) {
    val timeline: List<RadarFrame>
        get() =
            draft?.let { draft ->
                val layer = draft.context.layers.first()
                val captured = layer.mapFrame("Captured frame")
                (frames + captured).distinctBy { it.id }.sortedBy { it.instant() }
            } ?: replay?.timeline ?: frames

    val requestedFrame: RadarFrame?
        get() =
            timeline.firstOrNull {
                it.id ==
                    (draft?.context?.layers?.first()?.frameId ?: replay?.viewingId ?: viewingId)
            }

    val currentFrame: RadarFrame?
        get() = displayedFrame

    val preloadFrames: List<RadarFrame>
        get() {
            val index = timeline.indexOfFirst { it.id == requestedFrame?.id }
            return FrameReadinessTracker.prefetchWindow(timeline, index) { it.id }
                .filter {
                    it.sourceType == "radar" ||
                        it.id in preparedFrameIds ||
                        it.id == draft?.context?.layers?.first()?.frameId ||
                        it.id == replay?.markedLayer?.frameId
                }
        }

    val requestedPrepared: Boolean
        get() =
            requestedFrame?.let {
                it.sourceType == "radar" ||
                    it.id in preparedFrameIds ||
                    it.id == draft?.context?.layers?.first()?.frameId ||
                    it.id == replay?.markedLayer?.frameId
            } ?: false

    fun weatherSelection() =
        WeatherSelection(
            sourceType =
                when (weatherMode) {
                    "Satellite" -> "satellite"
                    "Models" -> "model"
                    else -> "radar"
                },
            sourceId = radarSourceId,
            productId = product,
            site = site.takeIf { weatherMode == "Radar" && radarSourceId != "noaa-mrms" },
            elevation = radarElevation.takeIf { weatherMode == "Radar" },
            domain =
                when (weatherMode) {
                    "Satellite" -> satelliteSector
                    "Models" -> modelDomain
                    else -> null
                },
            model = modelName.takeIf { weatherMode == "Models" },
            runTime = modelRunTime.takeIf { weatherMode == "Models" },
            selectionGeneration = selectionGeneration,
        )

    val annotationElements: List<AnnotationElement>
        get() = if (draft != null) editor.elements else selected?.elements.orEmpty()
}

class MapViewModel(
    val api: ApiRepository,
    private val drafts: DraftStore,
    private val placesStore: PlacesStore,
) : ViewModel() {
    private val restored = drafts.read()
    private val savedPlaces = placesStore.readPlaces()
    private val mutable =
        MutableStateFlow(
            UiState(
                radarSourceId = restored?.context?.layers?.firstOrNull()?.provider ?: "nws-ridge2",
                site = restored?.context?.layers?.firstOrNull()?.radarSite ?: "KCLX",
                product = restored?.context?.layers?.firstOrNull()?.product ?: "reflectivity",
                radarElevation = restored?.context?.layers?.firstOrNull()?.elevation,
                weatherMode =
                    weatherModeFor(restored?.context?.layers?.firstOrNull()?.sourceType ?: "radar"),
                activeTab =
                    weatherModeFor(restored?.context?.layers?.firstOrNull()?.sourceType ?: "radar"),
                modelName = restored?.context?.layers?.firstOrNull()?.model ?: "hrrr",
                modelRunTime = restored?.context?.layers?.firstOrNull()?.runTime,
                modelForecastHour = restored?.context?.layers?.firstOrNull()?.forecastHour,
                session = api.vault.current,
                draft = restored,
                editor = EditorState(restored?.elements.orEmpty()),
                camera = restored?.context?.camera ?: placesStore.readCamera() ?: Camera(),
                savedPlaces = savedPlaces,
                metricUnits = placesStore.readMetricUnits(),
                sheet = if (restored != null) "resume" else null,
            )
        )
    val state = mutable.asStateFlow()
    private var viewportJob: Job? = null
    private var playbackJob: Job? = null
    private var frameJob: Job? = null
    private var preparationJob: Job? = null
    private val rememberedSelections = mutableMapOf<String, WeatherSelection>()
    private var searchJob: Job? = null
    private var stationJob: Job? = null
    private var searchGeneration = 0
    private var stationGeneration = 0

    init {
        refresh()
        task {
            api.ensureDeviceProfile()
            api.request("/account")
            mutable.update { it.copy(session = api.vault.current) }
            loadPosts()
        }
    }

    fun message(value: String) {
        mutable.update { it.copy(message = value) }
    }

    fun clearMessage() {
        mutable.update { it.copy(message = null) }
    }

    fun sheet(value: String?) {
        mutable.update { state ->
            state.copy(
                sheet = value,
                activeTab =
                    if (value == null && state.activeTab in setOf("Feed", "More")) state.weatherMode
                    else state.activeTab,
            )
        }
    }

    fun navigate(tab: String) {
        if (tab !in setOf("Radar", "Satellite", "Models", "Feed", "More")) return
        if (mutable.value.draft != null && tab !in setOf(mutable.value.weatherMode, "More")) {
            message("Finish or discard the saved annotation draft before changing modes.")
            return
        }
        when (tab) {
            "Feed" -> {
                mutable.update { it.copy(activeTab = "Feed") }
                feed()
            }
            "More" -> mutable.update { it.copy(activeTab = "More", sheet = "more") }
            else -> {
                if (mutable.value.weatherMode == tab && mutable.value.selected == null) {
                    mutable.update { it.copy(activeTab = tab, sheet = null) }
                    return
                }
                rememberedSelections[mutable.value.weatherMode] = mutable.value.weatherSelection()
                val selection =
                    rememberedSelections[tab]
                        ?: when (tab) {
                            "Satellite" ->
                                WeatherSelection(
                                    "satellite",
                                    "noaa-goes",
                                    "geocolor",
                                    domain = "east",
                                )
                            "Models" ->
                                WeatherSelection(
                                    "model",
                                    "noaa-models",
                                    "reflectivity",
                                    model = "hrrr",
                                    domain = "conus",
                                )
                            else ->
                                WeatherSelection(
                                    "radar",
                                    "nws-ridge2",
                                    "reflectivity",
                                    site = mutable.value.site,
                                )
                        }
                changeSelection(selection)
            }
        }
    }

    fun selectLocation(point: List<Double>) {
        if (point.size < 2) return
        val lon = point[0]
        val lat = point[1]
        if (lon !in -180.0..180.0 || lat !in -90.0..90.0) return
        if (mutable.value.selectingSounding) viewSoundingAt(listOf(lon, lat))
        else mutable.update { it.copy(selectedPoint = listOf(lon, lat), sheet = "location") }
    }

    fun viewSoundingAt(point: List<Double>) {
        navigate("Models")
        mutable.update {
            it.copy(selectedSoundingPoint = point, selectingSounding = false, sheet = "sounding")
        }
    }

    fun selectSoundingPoint(enabled: Boolean) {
        stopPlayback()
        mutable.update { it.copy(selectingSounding = enabled, sheet = null) }
    }

    fun gpsUnavailable(reason: String) {
        mutable.update { it.copy(gpsMessage = reason) }
        message(reason)
    }

    fun metricUnits(enabled: Boolean) {
        runCatching { placesStore.writeMetricUnits(enabled) }
            .onSuccess { mutable.update { it.copy(metricUnits = enabled) } }
            .onFailure { message(it.message ?: "Unable to save unit preferences on this device.") }
    }

    fun recenterOnGps(latitude: Double, longitude: Double) {
        if (latitude !in -90.0..90.0 || longitude !in -180.0..180.0) {
            gpsUnavailable("Current location is unavailable. Search or choose a saved place.")
            return
        }
        val point = listOf(longitude, latitude)
        mutable.update { state ->
            state.copy(
                gpsPoint = point,
                gpsMessage = null,
                selectedPoint = point,
                sheet = "location",
                camera = state.camera.copy(center = point, zoom = maxOf(state.camera.zoom, 8.0)),
                cameraRevision = state.cameraRevision + 1,
                viewportGeneration = state.viewportGeneration + 1,
            )
        }
    }

    fun searchPlaces(query: String) {
        val normalized = query.trim().replace(Regex("\\s+"), " ")
        if (normalized.length < 3) {
            mutable.update {
                it.copy(
                    placeSearchState = "no_results",
                    placeSearchMessage = "Enter at least three characters.",
                    placeSearchResults = emptyList(),
                )
            }
            return
        }
        val point =
            mutable.value.selectedPoint ?: mutable.value.gpsPoint ?: mutable.value.camera.center
        val generation = ++searchGeneration
        mutable.update {
            it.copy(
                placeSearchState = "loading",
                placeSearchMessage = null,
                placeSearchResults = emptyList(),
            )
        }
        searchJob?.cancel()
        searchJob =
            viewModelScope.launch {
                try {
                    val response =
                        api.searchLocations(normalized, point.getOrNull(1), point.getOrNull(0))
                    if (generation != searchGeneration) return@launch
                    mutable.update {
                        it.copy(
                            placeSearchState = response.state,
                            placeSearchMessage = response.message,
                            placeSearchResults = response.results,
                        )
                    }
                } catch (error: Exception) {
                    if (error is CancellationException) throw error
                    if (generation != searchGeneration) return@launch
                    mutable.update {
                        it.copy(
                            placeSearchState = "source_unavailable",
                            placeSearchMessage = error.message ?: "Place search is unavailable.",
                            placeSearchResults = emptyList(),
                        )
                    }
                }
            }
    }

    fun addPlace(name: String, point: List<Double>) {
        val cleanName = name.trim().take(80)
        if (cleanName.isBlank() || point.size < 2) {
            message("Add a name and location to save this place.")
            return
        }
        val lon = point[0]
        val lat = point[1]
        if (lon !in -180.0..180.0 || lat !in -90.0..90.0) return
        val existing =
            mutable.value.savedPlaces.firstOrNull {
                kotlin.math.abs(it.lat - lat) < 0.0001 && kotlin.math.abs(it.lon - lon) < 0.0001
            }
        val places =
            if (existing == null) {
                if (mutable.value.savedPlaces.size >= 100) {
                    message("You can save up to 100 places on this device.")
                    return
                }
                mutable.value.savedPlaces + SavedPlace(name = cleanName, lat = lat, lon = lon)
            } else {
                mutable.value.savedPlaces.map {
                    if (it.id == existing.id) it.copy(name = cleanName) else it
                }
            }
        persistPlaces(places)
        mutable.update { it.copy(sheet = "places") }
    }

    fun renamePlace(id: String, name: String) {
        val cleanName = name.trim().take(80)
        if (cleanName.isBlank()) return message("Place name cannot be blank.")
        persistPlaces(
            mutable.value.savedPlaces.map { if (it.id == id) it.copy(name = cleanName) else it }
        )
    }

    fun deletePlace(id: String) {
        persistPlaces(mutable.value.savedPlaces.filterNot { it.id == id })
    }

    fun movePlace(id: String, direction: Int) {
        val places = mutable.value.savedPlaces.toMutableList()
        val index = places.indexOfFirst { it.id == id }
        val target = index + direction.coerceIn(-1, 1)
        if (index < 0 || target !in places.indices) return
        val place = places.removeAt(index)
        places.add(target, place)
        persistPlaces(places)
    }

    private fun persistPlaces(places: List<SavedPlace>) {
        runCatching { placesStore.writePlaces(places) }
            .onSuccess { mutable.update { it.copy(savedPlaces = places) } }
            .onFailure { message(it.message ?: "Unable to save places on this device.") }
    }

    fun focusPlace(place: SavedPlace) {
        val point = listOf(place.lon, place.lat)
        mutable.update { state ->
            state.copy(
                selectedPoint = point,
                camera = state.camera.copy(center = point, zoom = maxOf(state.camera.zoom, 8.0)),
                cameraRevision = state.cameraRevision + 1,
                viewportGeneration = state.viewportGeneration + 1,
                sheet = null,
                activeTab = state.weatherMode,
            )
        }
    }

    fun loadNearbyRadarStations(point: List<Double> = mutable.value.camera.center) {
        if (point.size < 2) return
        val generation = ++stationGeneration
        val lon = point[0]
        val lat = point[1]
        mutable.update {
            it.copy(radarStationState = "loading", radarStations = emptyList(), sheet = "stations")
        }
        stationJob?.cancel()
        stationJob =
            viewModelScope.launch {
                try {
                    val response = api.nearbyRadarStations(lat, lon)
                    if (generation != stationGeneration) return@launch
                    mutable.update {
                        it.copy(
                            radarStationState = response.state,
                            radarStations = response.stations,
                            sheet = "stations",
                        )
                    }
                } catch (error: Exception) {
                    if (error is CancellationException) throw error
                    if (generation != stationGeneration) return@launch
                    mutable.update {
                        it.copy(
                            radarStationState = "source_unavailable",
                            message = error.message ?: "Radar stations are unavailable.",
                            sheet = "stations",
                        )
                    }
                }
            }
    }

    fun selectRadarStation(site: String) {
        sheet(null)
        layer(site, mutable.value.product)
    }

    fun expandedPost(value: Boolean) {
        mutable.update { it.copy(expandedPost = value) }
    }

    private fun task(action: suspend () -> Unit) {
        viewModelScope.launch {
            try {
                action()
            } catch (error: Exception) {
                if (error is CancellationException) throw error
                message(error.message ?: "Network unavailable. Try again.")
            } finally {
                mutable.update { it.copy(session = api.vault.current) }
            }
        }
    }

    private fun authenticated(action: () -> Unit) {
        if (api.vault.current != null) {
            mutable.update { it.copy(session = api.vault.current) }
            action()
        } else
            task {
                mutable.update { it.copy(busy = true) }
                try {
                    api.ensureDeviceProfile()
                    mutable.update { it.copy(session = api.vault.current) }
                    action()
                } finally {
                    mutable.update { it.copy(busy = false) }
                }
            }
    }

    fun refresh() {
        expireAlerts()
        loadFrames()
        loadPosts()
        task {
            try {
                val data = api.alerts()
                mutable.update {
                    it.copy(
                        alerts =
                            AlertLifetime.activeCollection(
                                data.getValue("collection").toString(),
                                Instant.now(),
                            ),
                        alertsState = data.getValue("state").jsonPrimitive.content,
                    )
                }
            } catch (error: Exception) {
                if (error is CancellationException) throw error
                mutable.update { it.copy(alertsState = "network_unavailable") }
            }
        }
    }

    fun expireAlerts() {
        val now = Instant.now()
        mutable.update {
            it.copy(
                alerts = AlertLifetime.activeCollection(it.alerts, now),
                officialSelection =
                    it.officialSelection?.takeIf { p -> AlertLifetime.isActive(p, now) },
            )
        }
    }

    private fun loadFrames() {
        val requested = mutable.value
        val selection = requested.weatherSelection()
        mutable.update { it.copy(sourceState = "loading") }
        frameJob?.cancel()
        preparationJob?.cancel()
        frameJob =
            viewModelScope.launch {
                try {
                    val frames: List<RadarFrame>
                    val sourceState: String
                    val responseMessage: String?
                    val options: Map<String, JsonElement>
                    if (selection.sourceId == "nws-ridge2") {
                        val response = api.frames(requested.site, selection.productId)
                        frames = response.frames
                        sourceState = response.state
                        responseMessage = response.message
                        options = emptyMap()
                    } else {
                        val response = api.weatherFrames(selection)
                        frames = response.frames.map { it.mapFrame(radarProductTitle(it.product)) }
                        sourceState = response.state
                        responseMessage = response.message
                        options = response.options
                    }
                    mutable.update { s ->
                        if (s.selectionGeneration != selection.selectionGeneration) s
                        else {
                            val replay =
                                s.replay?.let { r ->
                                    val validId =
                                        if (r.isMarked || frames.any { it.id == r.viewingId })
                                            r.viewingId
                                        else r.markedLayer.frameId
                                    r.copy(frames = frames, viewingId = validId)
                                }
                            val chosen =
                                when {
                                    s.draft != null -> s.draft.context.layers.first().frameId
                                    s.followLive || frames.none { it.id == s.viewingId } ->
                                        if (selection.sourceType == "model")
                                            frames.firstOrNull()?.id
                                        else frames.lastOrNull()?.id
                                    else -> s.viewingId
                                }
                            s.copy(
                                frames = frames,
                                sourceState = sourceState,
                                weatherOptions = options,
                                availableElevations =
                                    options["elevations"]
                                        ?.jsonArray
                                        ?.mapNotNull { it.jsonPrimitive.doubleOrNull }
                                        .orEmpty(),
                                modelRunTime =
                                    if (selection.sourceType == "model")
                                        frames.firstOrNull()?.runTime ?: s.modelRunTime
                                    else s.modelRunTime,
                                viewingId = chosen,
                                followLive =
                                    if (selection.sourceType == "model") false else s.followLive,
                                replay = replay,
                                preparedFrameIds =
                                    s.preparedFrameIds.intersect(frames.map { it.id }.toSet()),
                                rasterState =
                                    if (frames.isEmpty() && s.replay == null && s.draft == null)
                                        if (sourceState == "ready") "no_data" else sourceState
                                    else if (
                                        chosen != s.viewingId || s.displayedFrame?.id != chosen
                                    )
                                        "loading"
                                    else s.rasterState,
                            )
                        }
                    }
                    if (mutable.value.selectionGeneration == selection.selectionGeneration) {
                        if (responseMessage != null) message(responseMessage)
                        prepareWindow()
                    }
                } catch (error: Exception) {
                    if (error is CancellationException) throw error
                    mutable.update { s ->
                        if (s.selectionGeneration != selection.selectionGeneration) s
                        else
                            s.copy(
                                sourceState = "network_unavailable",
                                rasterState = "source_unavailable",
                            )
                    }
                }
            }
    }

    private fun prepareWindow() {
        preparationJob?.cancel()
        val snapshot = mutable.value
        val requested = snapshot.requestedFrame ?: return
        if (
            requested.sourceType == "radar" ||
                snapshot.draft != null ||
                snapshot.replay?.isMarked == true
        )
            return
        val generation = snapshot.selectionGeneration
        val window =
            FrameReadinessTracker.prefetchWindow(
                snapshot.timeline,
                snapshot.timeline.indexOfFirst { it.id == requested.id },
            ) {
                it.id
            }
        // Requested frame first; one lightweight polling request at a time, with at most four
        // shared jobs.
        val candidates = (listOf(requested) + window).distinctBy { it.id }
        preparationJob =
            viewModelScope.launch {
                val started = System.nanoTime()
                try {
                    while (
                        mutable.value.selectionGeneration == generation &&
                            mutable.value.requestedFrame?.id == requested.id
                    ) {
                        for (frame in candidates) {
                            if (frame.id in mutable.value.preparedFrameIds) continue
                            val result = api.prepareWeather(frame)
                            if (result.state == "ready") {
                                mutable.update { s ->
                                    if (s.selectionGeneration != generation) s
                                    else
                                        s.copy(
                                            preparedFrameIds = s.preparedFrameIds + frame.id,
                                            frames =
                                                s.frames.map {
                                                    if (it.id == frame.id)
                                                        it.copy(
                                                            metadata = it.metadata + result.metadata
                                                        )
                                                    else it
                                                },
                                        )
                                }
                            } else if (result.state !in setOf("preparing", "loading")) {
                                if (frame.id == requested.id) {
                                    mutable.update { s ->
                                        if (s.selectionGeneration != generation) s
                                        else
                                            s.copy(
                                                rasterState = "source_unavailable",
                                                playing = false,
                                            )
                                    }
                                    result.message?.let(::message)
                                    return@launch
                                }
                            }
                        }
                        if (candidates.all { it.id in mutable.value.preparedFrameIds })
                            return@launch
                        if ((System.nanoTime() - started) / 1_000_000_000 > 240) {
                            if (requested.id !in mutable.value.preparedFrameIds) {
                                mutable.update {
                                    it.copy(rasterState = "source_unavailable", playing = false)
                                }
                                message("Weather preparation is delayed. Retry this frame.")
                            }
                            return@launch
                        }
                        delay(3000)
                    }
                } catch (error: Exception) {
                    if (error is CancellationException) throw error
                    if (requested.id !in mutable.value.preparedFrameIds)
                        mutable.update { s ->
                            if (s.selectionGeneration != generation) s
                            else s.copy(rasterState = "source_unavailable", playing = false)
                        }
                }
            }
    }

    fun layer(site: String, product: String) =
        layer(mutable.value.radarSourceId, site, product, mutable.value.radarElevation)

    fun layer(sourceId: String, site: String, product: String, elevation: Double?) =
        changeSelection(
            WeatherSelection("radar", sourceId, product, site = site, elevation = elevation)
        )

    fun satelliteLayer(sector: String, product: String) =
        changeSelection(WeatherSelection("satellite", "noaa-goes", product, domain = sector))

    fun modelLayer(model: String, product: String, runTime: String? = null) =
        changeSelection(
            WeatherSelection(
                "model",
                "noaa-models",
                product,
                domain = "conus",
                model = model,
                runTime = runTime,
            )
        )

    private fun changeSelection(selection: WeatherSelection) {
        if (mutable.value.draft != null) return
        stopPlayback()
        preparationJob?.cancel()
        mutable.update { s ->
            s.copy(
                weatherMode = weatherModeFor(selection.sourceType),
                activeTab = weatherModeFor(selection.sourceType),
                radarSourceId = selection.sourceId,
                site = selection.site ?: s.site,
                product = selection.productId,
                radarElevation = selection.elevation,
                satelliteSector =
                    if (selection.sourceType == "satellite") selection.domain ?: "east"
                    else s.satelliteSector,
                modelName = selection.model ?: s.modelName,
                modelDomain =
                    if (selection.sourceType == "model") selection.domain ?: "conus"
                    else s.modelDomain,
                modelRunTime = selection.runTime,
                modelForecastHour = selection.forecastHour,
                availableElevations = emptyList(),
                weatherOptions = emptyMap(),
                preparedFrameIds = emptySet(),
                selectionGeneration = s.selectionGeneration + 1,
                replay = null,
                selected = null,
                frames = emptyList(),
                viewingId = null,
                sourceState = "loading",
                rasterState = "loading",
                followLive = true,
                sheet = null,
            )
        }
        loadFrames()
    }

    fun opacity(value: Double) {
        mutable.update { it.copy(opacity = value) }
    }

    fun showAlerts(value: Boolean) {
        mutable.update { it.copy(showAlerts = value) }
    }

    fun official(value: JsonObject?) {
        mutable.update { it.copy(officialSelection = value) }
    }

    fun viewport(camera: Camera, bounds: List<Double>) {
        mutable.update { s ->
            val changed = s.camera != camera || s.bounds != bounds
            s.copy(
                camera = camera,
                bounds = bounds,
                viewportGeneration =
                    if (changed) s.viewportGeneration + 1 else s.viewportGeneration,
                rasterState = if (changed && s.requestedFrame != null) "loading" else s.rasterState,
            )
        }
        runCatching { placesStore.writeCamera(camera) }
        if (mutable.value.draft != null) return
        viewportJob?.cancel()
        viewportJob =
            viewModelScope.launch {
                delay(350)
                loadPosts()
            }
    }

    fun filter(
        sort: String? = null,
        type: String? = mutable.value.typeFilter,
        topic: String? = mutable.value.topicFilter,
        verified: Boolean = mutable.value.verifiedOnly,
    ) {
        if (sort == "following" && mutable.value.session == null) {
            authenticated { filter("following", type, topic, verified) }
            return
        }
        mutable.update {
            it.copy(
                sort = sort ?: it.sort,
                typeFilter = type,
                topicFilter = topic,
                verifiedOnly = verified,
            )
        }
        loadPosts()
    }

    fun loadPosts() {
        val s = mutable.value
        val query =
            "bbox=${s.bounds.joinToString(",")}&sort=${s.sort}" +
                (s.typeFilter?.let { "&content_type=$it" } ?: "") +
                (s.topicFilter?.let { "&topic=$it" } ?: "") +
                "&verified_only=${s.verifiedOnly}&limit=10"
        task {
            try {
                val response = api.posts(query)
                mutable.update { current ->
                    if (
                        current.bounds != s.bounds ||
                            current.sort != s.sort ||
                            current.typeFilter != s.typeFilter ||
                            current.topicFilter != s.topicFilter ||
                            current.verifiedOnly != s.verifiedOnly
                    )
                        current
                    else current.copy(posts = response.items, socialState = "ready")
                }
            } catch (error: Exception) {
                if (error is CancellationException) throw error
                mutable.update { it.copy(socialState = "network_unavailable") }
                if (error is ApiException && error.status == 401) throw error
            }
        }
    }

    fun open(post: WeatherPost) {
        stopPlayback()
        val layer = post.context.layers.first()
        val fromFeed = mutable.value.activeTab == "Feed" || mutable.value.sheet == "feed"
        mutable.update {
            it.copy(
                selected = post,
                replay = ReplaySession(post, emptyList()),
                weatherMode = weatherModeFor(layer.sourceType),
                modelName = layer.model ?: it.modelName,
                modelRunTime = layer.runTime,
                modelForecastHour = layer.forecastHour,
                satelliteSector =
                    layer.metadata["satellite_sector"]?.jsonPrimitive?.content
                        ?: it.satelliteSector,
                camera = post.context.camera,
                cameraRevision = it.cameraRevision + 1,
                selectionGeneration = it.selectionGeneration + 1,
                viewportGeneration = it.viewportGeneration + 1,
                radarSourceId = layer.provider,
                site = layer.radarSite ?: it.site,
                product = layer.product,
                radarElevation = layer.elevation,
                availableElevations = emptyList(),
                opacity = layer.opacity,
                viewingId = layer.frameId,
                sheet = null,
                activeTab = if (fromFeed) "Feed" else weatherModeFor(layer.sourceType),
                comments = emptyList(),
                expandedPost = false,
                followLive = false,
                rasterState = "loading",
                officialSelection = null,
            )
        }
        loadFrames()
        loadComments()
    }

    fun open(id: String) {
        task { open(api.post(id)) }
    }

    fun closePost() {
        mutable.update {
            it.copy(
                selected = null,
                replay = null,
                expandedPost = false,
                followLive = true,
                activeTab = it.weatherMode,
            )
        }
        live()
    }

    fun cluster(posts: List<WeatherPost>) {
        if (posts.size == 1) open(posts.first())
        else mutable.update { it.copy(cluster = posts, sheet = "cluster") }
    }

    fun scrub(index: Int) {
        if (mutable.value.draft != null) return
        val frame = mutable.value.timeline.getOrNull(index) ?: return
        mutable.update {
            it.copy(
                viewingId = frame.id,
                replay = it.replay?.advance(frame.id),
                followLive = false,
                rasterState =
                    if (
                        it.displayedFrame?.id == frame.id &&
                            it.displayedSelectionGeneration == it.selectionGeneration &&
                            it.displayedViewportGeneration == it.viewportGeneration
                    )
                        "ready"
                    else "loading",
            )
        }
        prepareWindow()
    }

    fun marked() {
        stopPlayback()
        mutable.update { s ->
            val r = s.replay ?: return@update s
            s.copy(
                replay = r.returnToMarked(),
                radarSourceId = r.markedLayer.provider,
                site = r.markedLayer.radarSite ?: s.site,
                product = r.markedLayer.product,
                radarElevation = r.markedLayer.elevation,
                viewingId = r.markedLayer.frameId,
                camera = r.post.context.camera,
                cameraRevision = s.cameraRevision + 1,
                viewportGeneration = s.viewportGeneration + 1,
                rasterState = "loading",
                followLive = false,
            )
        }
    }

    fun live() {
        stopPlayback()
        val timeline = mutable.value.timeline
        scrub(timeline.lastIndex)
        mutable.update { it.copy(followLive = it.replay == null && it.weatherMode != "Models") }
    }

    fun play() {
        if (mutable.value.playing) {
            stopPlayback()
            return
        }
        mutable.update { it.copy(playing = true, followLive = false) }
        playbackJob =
            viewModelScope.launch {
                while (mutable.value.playing && mutable.value.mapActive) {
                    delay(1600)
                    val s = mutable.value
                    if (!s.playing || !s.mapActive || s.draft != null || s.timeline.size < 2) break
                    val current = s.timeline.indexOfFirst { it.id == s.requestedFrame?.id }
                    val index = (current.takeIf { it >= 0 } ?: s.timeline.lastIndex)
                    val nextIndex = (index + 1) % s.timeline.size
                    val targetId = s.timeline[nextIndex].id
                    scrub(nextIndex)
                    val rendered =
                        mutable.first { current ->
                            !current.playing ||
                                current.rasterState in
                                    setOf("source_unavailable", "render_error") ||
                                (current.displayedFrame?.id == targetId &&
                                    current.displayedSelectionGeneration ==
                                        current.selectionGeneration &&
                                    current.displayedViewportGeneration ==
                                        current.viewportGeneration)
                        }
                    if (!rendered.playing || rendered.rasterState != "ready") break
                }
                mutable.update { it.copy(playing = false) }
            }
    }

    fun stopPlayback() {
        playbackJob?.cancel()
        playbackJob = null
        mutable.update { it.copy(playing = false) }
    }

    fun mapActive(active: Boolean) {
        mutable.update { s ->
            if (s.mapActive == active) s
            else
                s.copy(
                    mapActive = active,
                    viewportGeneration =
                        if (active) s.viewportGeneration + 1 else s.viewportGeneration,
                    rasterState =
                        if (active && s.requestedFrame != null) "loading" else s.rasterState,
                    playing = if (active) s.playing else false,
                )
        }
        if (!active) {
            playbackJob?.cancel()
            playbackJob = null
        }
    }

    fun raster(readiness: FrameReadiness) {
        mutable.update { s ->
            val frame = s.requestedFrame
            if (
                readiness.sourceId != (frame?.provider ?: "nws-ridge2") ||
                    frame?.id != readiness.frameId ||
                    s.selectionGeneration != readiness.selectionGeneration ||
                    s.viewportGeneration != readiness.viewportGeneration
            )
                return@update s
            if (readiness.state == "ready") {
                s.copy(
                    rasterState = "ready",
                    displayedFrame = frame,
                    displayedSelectionGeneration = readiness.selectionGeneration,
                    displayedViewportGeneration = readiness.viewportGeneration,
                )
            } else {
                s.copy(rasterState = "source_unavailable", playing = false)
            }
        }
    }

    fun retryFrame() {
        mutable.update { state ->
            if (state.requestedFrame == null) state
            else
                state.copy(
                    selectionGeneration = state.selectionGeneration + 1,
                    rasterState = "loading",
                )
        }
        prepareWindow()
    }

    fun longPress(point: List<Double>, camera: Camera, bounds: List<Double>) {
        val s = mutable.value
        if (s.draft != null) return
        val frame = s.currentFrame ?: return message("Choose an available weather frame first.")
        if (s.replay?.isMarked == true && s.frames.none { it.id == frame.id }) {
            message(
                "This is a preserved scan. Advance to an available scan to create a new annotation."
            )
            return
        }
        stopPlayback()
        val context =
            WeatherContext(
                capturedAt = Instant.now().toString(),
                camera = camera,
                bounds = bounds,
                layers = listOf(frame.layer(s.opacity)),
            )
        mutable.update { it.copy(pending = PendingMark(point, context), followLive = false) }
        authenticated { sheet("mark") }
    }

    fun startDraft(type: String) {
        val pending = mutable.value.pending ?: return
        val pin =
            AnnotationElement(
                tool = "pin",
                geometry = GeoGeometry.of("Point", listOf(pending.point)),
            )
        val draft = Draft(pending.context, listOf(pin), contentType = type)
        mutable.update {
            it.copy(
                draft = draft,
                editor = EditorState().add(pin),
                tool = Tool.ARROW,
                selected = null,
                replay = null,
                sheet = null,
                pending = null,
                followLive = false,
                viewingId = pending.context.layers.first().frameId,
                camera = pending.context.camera,
                cameraRevision = it.cameraRevision + 1,
            )
        }
        drafts.save(draft)
    }

    fun resumeDraft() {
        val s = mutable.value
        val draft = s.draft ?: return
        val layer = draft.context.layers.first()
        mutable.update {
            it.copy(
                camera = draft.context.camera,
                cameraRevision = it.cameraRevision + 1,
                radarSourceId = layer.provider,
                site = layer.radarSite ?: it.site,
                product = layer.product,
                radarElevation = layer.elevation,
                availableElevations = emptyList(),
                viewingId = layer.frameId,
                followLive = false,
                sheet = null,
            )
        }
        loadFrames()
    }

    fun discardDraft() {
        drafts.save(null)
        mutable.update {
            it.copy(draft = null, editor = EditorState(), sheet = null, pending = null)
        }
        live()
    }

    fun tool(value: Tool) {
        mutable.update { it.copy(tool = value) }
    }

    fun color(value: String) {
        mutable.update { it.copy(color = value) }
        styleSelected()
    }

    fun stroke(value: Double) {
        mutable.update { it.copy(stroke = value) }
        styleSelected()
    }

    private fun styleSelected() {
        val s = mutable.value
        if (s.draft == null || s.tool != Tool.SELECT || s.editor.selectedId == null) return
        commit(
            s.editor.elements.map {
                if (it.id == s.editor.selectedId) it.copy(color = s.color, stroke = s.stroke)
                else it
            }
        )
    }

    fun select(id: String?) {
        mutable.update { it.copy(editor = it.editor.copy(selectedId = id)) }
    }

    fun commit(elements: List<AnnotationElement>) {
        mutable.update { it.copy(editor = it.editor.commit(elements)) }
        saveEditor()
    }

    fun add(element: AnnotationElement) {
        mutable.update { it.copy(editor = it.editor.add(element)) }
        saveEditor()
    }

    fun undo() {
        mutable.update { it.copy(editor = it.editor.undo()) }
        saveEditor()
    }

    fun redo() {
        mutable.update { it.copy(editor = it.editor.redo()) }
        saveEditor()
    }

    fun deleteElement() {
        mutable.update { it.copy(editor = it.editor.deleteSelected()) }
        saveEditor()
    }

    private fun saveEditor() {
        mutable.update { it.copy(draft = it.draft?.copy(elements = it.editor.elements)) }
        drafts.save(mutable.value.draft)
    }

    fun draft(value: Draft) {
        mutable.update { it.copy(draft = value) }
        drafts.save(value)
    }

    fun textPoint(point: List<Double>) {
        mutable.update { it.copy(textPoint = point, sheet = "text") }
    }

    fun addText(label: String) {
        mutable.value.textPoint?.let { point ->
            add(
                AnnotationElement(
                    tool = "text",
                    geometry = GeoGeometry.of("Point", listOf(point)),
                    color = mutable.value.color,
                    stroke = mutable.value.stroke,
                    label = label.trim(),
                )
            )
        }
        mutable.update { it.copy(textPoint = null, sheet = null) }
    }

    fun publish() {
        authenticated {
            task {
                val s = mutable.value
                val draft = s.draft ?: return@task
                if (draft.description.isBlank())
                    return@task message("Explain what you marked before publishing.")
                mutable.update { it.copy(busy = true) }
                try {
                    val published =
                        api.publish(
                            PostCreate(
                                contentType = draft.contentType,
                                description = draft.description.trim(),
                                title = draft.title.ifBlank { null },
                                whyItMatters = draft.whyItMatters.ifBlank { null },
                                watchNext = draft.watchNext.ifBlank { null },
                                topics = draft.topics,
                                context = draft.context,
                                elements = s.editor.elements,
                                photoIds = draft.photoIds,
                            )
                        )
                    drafts.save(null)
                    mutable.update { it.copy(draft = null, editor = EditorState(), sheet = null) }
                    open(published)
                    loadPosts()
                    message("Your annotation is on the map.")
                } finally {
                    mutable.update { it.copy(busy = false) }
                }
            }
        }
    }

    fun account() = authenticated {
        task {
            mutable.update { it.copy(session = api.vault.current, sheet = "account") }
            loadBlockedPeople()
        }
    }

    fun updateDisplayName(name: String) = authenticated {
        task {
            mutable.update { it.copy(busy = true) }
            try {
                val profile =
                    api.json
                        .parseToJsonElement(
                            api.request(
                                "/account",
                                "PATCH",
                                api.body(buildJsonObject { put("display_name", name.trim()) }),
                            )
                        )
                        .jsonObject
                api.vault.current?.let { saved ->
                    api.vault.save(
                        saved.copy(
                            displayName = profile.getValue("display_name").jsonPrimitive.content
                        )
                    )
                }
                mutable.update { it.copy(session = api.vault.current) }
                loadPosts()
                if (mutable.value.selected != null) refreshSelected()
                message("Profile saved.")
            } finally {
                mutable.update { it.copy(busy = false) }
            }
        }
    }

    private suspend fun loadBlockedPeople() {
        val data = api.json.parseToJsonElement(api.request("/account/blocks"))
        mutable.update {
            it.copy(
                blockedPeople =
                    (data as kotlinx.serialization.json.JsonArray).map { p -> p.jsonObject }
            )
        }
    }

    fun unblock(id: String) = authenticated {
        task {
            api.request("/profiles/$id/block", "DELETE")
            loadBlockedPeople()
            loadPosts()
            message("This person is unblocked.")
        }
    }

    fun like() = authenticated {
        task {
            val selected = mutable.value.selected ?: return@task
            api.request("/posts/${selected.id}/like", if (selected.liked) "DELETE" else "PUT")
            refreshSelected()
        }
    }

    fun follow() = authenticated {
        task {
            val selected = mutable.value.selected ?: return@task
            api.request(
                "/profiles/${selected.author.id}/follow",
                if (selected.followingAuthor) "DELETE" else "PUT",
            )
            refreshSelected()
        }
    }

    private suspend fun refreshSelected() {
        val id = mutable.value.selected?.id ?: return
        val post = api.post(id)
        mutable.update { s ->
            if (s.selected?.id != id) s
            else
                s.copy(
                    selected = post,
                    replay = s.replay?.copy(post = post),
                    posts = s.posts.map { if (it.id == id) post else it },
                )
        }
    }

    fun loadComments(more: Boolean = false) {
        val s = mutable.value
        val id = s.selected?.id ?: return
        mutable.update { it.copy(commentsLoading = true) }
        task {
            try {
                val response = api.comments(id, if (more) s.commentsCursor else null)
                mutable.update { current ->
                    if (current.selected?.id != id) current
                    else
                        current.copy(
                            comments =
                                (if (more) current.comments + response.items else response.items)
                                    .distinctBy { it.id },
                            commentsCursor = response.nextCursor,
                        )
                }
            } finally {
                mutable.update { it.copy(commentsLoading = false) }
            }
        }
    }

    fun comment(body: String, parent: String?) = authenticated {
        task {
            val id = mutable.value.selected?.id ?: return@task
            api.request(
                "/posts/$id/comments",
                "POST",
                api.body(
                    buildJsonObject {
                        put("body", body.trim())
                        if (parent != null) put("parent_id", parent)
                    }
                ),
            )
            loadComments()
            refreshSelected()
        }
    }

    fun removeComment(id: String) = authenticated {
        task {
            api.request("/comments/$id", "DELETE")
            loadComments()
            refreshSelected()
        }
    }

    fun report(type: String, id: String, reason: String) = authenticated {
        task {
            api.request(
                "/reports",
                "POST",
                api.body(
                    buildJsonObject {
                        put("target_type", type)
                        put("target_id", id)
                        put("reason", reason)
                    }
                ),
            )
            message("Report sent for review.")
        }
    }

    fun blockAuthor() = authenticated {
        task {
            val selected = mutable.value.selected ?: return@task
            api.request("/profiles/${selected.author.id}/block", "PUT")
            closePost()
            loadPosts()
            message("This account is blocked.")
        }
    }

    fun deletePost() = authenticated {
        task {
            val id = mutable.value.selected?.id ?: return@task
            api.request("/posts/$id", "DELETE")
            closePost()
            loadPosts()
        }
    }

    fun upload(data: ByteArray) = authenticated {
        task {
            mutable.update { it.copy(busy = true) }
            try {
                val id = api.upload(data)
                mutable.value.draft?.let { draft(it.copy(photoIds = it.photoIds + id)) }
            } finally {
                mutable.update { it.copy(busy = false) }
            }
        }
    }

    fun notifications() = authenticated {
        task {
            val data = api.json.parseToJsonElement(api.request("/notifications"))
            mutable.update {
                it.copy(
                    notifications =
                        (data as kotlinx.serialization.json.JsonArray).map { n -> n.jsonObject },
                    sheet = "notifications",
                )
            }
        }
    }

    fun feed(scope: String = "nearby", more: Boolean = false) {
        if (scope == "following" && mutable.value.session == null) {
            authenticated { feed(scope) }
            return
        }
        val s = mutable.value
        mutable.update {
            it.copy(sheet = "feed", activeTab = "Feed", feedScope = scope, feedLoading = true)
        }
        val sort = if (scope == "nearby") "recent" else scope
        val query =
            "sort=$sort&limit=20" +
                (if (scope == "nearby") "&bbox=${s.bounds.joinToString(",")}" else "") +
                (if (more && s.feedCursor != null) "&cursor=${s.feedCursor}" else "")
        task {
            try {
                val result = api.posts(query)
                mutable.update { current ->
                    if (current.feedScope != scope) current
                    else
                        current.copy(
                            feedItems =
                                (if (more) current.feedItems + result.items else result.items)
                                    .distinctBy { it.id },
                            feedCursor = result.nextCursor,
                        )
                }
            } finally {
                mutable.update { it.copy(feedLoading = false) }
            }
        }
    }

    fun openNotification(value: JsonObject) {
        task {
            api.request("/notifications/${value.getValue("id").jsonPrimitive.content}/read", "PUT")
            open(value.getValue("post_id").jsonPrimitive.content)
        }
    }
}
