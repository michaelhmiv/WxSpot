package app.wxspot.ui

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import app.wxspot.data.ApiRepository
import app.wxspot.domain.LocationWeatherResponse
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch

data class LocationWeatherUi(
    val point: List<Double>? = null,
    val loading: Boolean = false,
    val response: LocationWeatherResponse? = null,
    val message: String? = null,
)

class LocationWeatherViewModel(private val api: ApiRepository) : ViewModel() {
    private val mutable = MutableStateFlow(LocationWeatherUi())
    val state = mutable.asStateFlow()
    private var generation = 0L
    private var job: Job? = null

    fun cancel() {
        generation++
        job?.cancel()
    }

    fun load(point: List<Double>) {
        val current = ++generation
        job?.cancel()
        mutable.value =
            if (mutable.value.point == point) mutable.value.copy(loading = true, message = null)
            else LocationWeatherUi(point = point, loading = true)
        job =
            viewModelScope.launch {
                delay(200)
                try {
                    val response = api.locationWeather(point)
                    if (current == generation)
                        mutable.value = LocationWeatherUi(point, response = response)
                } catch (error: Exception) {
                    if (error is CancellationException) throw error
                    if (current == generation)
                        mutable.value =
                            mutable.value.copy(
                                loading = false,
                                message =
                                    "Unable to refresh weather. Previously loaded sections are shown with their original times.",
                            )
                }
            }
    }
}
