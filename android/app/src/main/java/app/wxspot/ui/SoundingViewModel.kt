package app.wxspot.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.wxspot.data.ApiRepository
import app.wxspot.domain.SoundingResponse
import app.wxspot.domain.SoundingStation
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

class SoundingViewModel(private val api: ApiRepository) : ViewModel() {
    private val mutable = MutableStateFlow<SoundingResponse?>(null)
    val state = mutable.asStateFlow()
    private val stationMutable = MutableStateFlow<List<SoundingStation>>(emptyList())
    val stations = stationMutable.asStateFlow()
    private var job: Job? = null
    private var stationJob: Job? = null
    private var stationGeneration = 0L
    private var generation = 0L
    private var dataset: Map<String, String>? = null

    fun cancel() {
        generation++
        job?.cancel()
        stationGeneration++
        stationJob?.cancel()
    }

    fun nearby(point: List<Double>) {
        val current = ++stationGeneration
        stationJob?.cancel()
        stationMutable.value = emptyList()
        stationJob =
            viewModelScope.launch {
                try {
                    val response = api.soundingStations(point)
                    if (current == stationGeneration) stationMutable.value = response.stations
                } catch (error: Exception) {
                    if (error is CancellationException) throw error
                }
            }
    }

    fun load(parameters: Map<String, String>, point: List<Double>) {
        val current = ++generation
        job?.cancel()
        val requestedDataset =
            parameters.filterKeys {
                it !in setOf("parcel", "motion", "storm_u", "storm_v", "retry_failed")
            }
        mutable.value =
            if (dataset == requestedDataset)
                mutable.value?.copy(state = "preparing", diagnostics = null, message = null)
                    ?: SoundingResponse("preparing", requestedPoint = point)
            else SoundingResponse("preparing", requestedPoint = point)
        dataset = requestedDataset
        job =
            viewModelScope.launch {
                delay(300) // Coalesce rapid parcel/motion edits without new origin downloads.
                try {
                    val started = System.nanoTime()
                    var request = parameters
                    while (current == generation) {
                        val response = api.sounding(request)
                        request = request - "retry_failed"
                        if (current != generation) return@launch
                        mutable.value = response
                        if (response.state != "preparing") return@launch
                        if ((System.nanoTime() - started) / 1_000_000_000 > 540) {
                            mutable.value =
                                response.copy(
                                    state = "source_unavailable",
                                    message =
                                        "Profile preparation is delayed. Retry this selection.",
                                )
                            return@launch
                        }
                        delay(3000)
                    }
                } catch (error: Exception) {
                    if (error is CancellationException) throw error
                    if (current == generation)
                        mutable.value =
                            (mutable.value
                                    ?: SoundingResponse(
                                        "network_unavailable",
                                        requestedPoint = point,
                                    ))
                                .copy(
                                    state = "network_unavailable",
                                    message = "Sounding unavailable. Retry when connected.",
                                )
                }
            }
    }
}
