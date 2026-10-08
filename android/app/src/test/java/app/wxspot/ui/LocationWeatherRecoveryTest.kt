package app.wxspot.ui

import app.wxspot.data.ApiRepository
import app.wxspot.data.Session
import app.wxspot.data.SessionStore
import app.wxspot.domain.LocationForecastPeriod
import app.wxspot.domain.LocationWeatherResponse
import app.wxspot.domain.LocationWeatherSection
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withTimeout
import kotlinx.serialization.json.Json
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.Assert.*
import org.junit.Test

@OptIn(ExperimentalCoroutinesApi::class)
class LocationWeatherRecoveryTest {
    @Test
    fun failedRefreshRetainsIntervalsAndMarksThemStaleUntilRecovery() = runBlocking {
        val server = MockWebServer()
        val json = Json { encodeDefaults = true }
        val vault =
            object : SessionStore {
                override val current: Session? = null

                override fun save(value: Session?) = Unit
            }
        val period =
            LocationForecastPeriod(
                start = "2026-10-08T12:00:00Z",
                end = "2026-10-08T13:00:00Z",
                daytime = true,
                temperature = 22.0,
                rainChance = null,
            )
        val response =
            LocationWeatherResponse(
                state = "ready",
                requestedPoint = listOf(-80.18, 33.02),
                observation = LocationWeatherSection("no_data", message = "No station reading"),
                hourly =
                    LocationWeatherSection(
                        "ready",
                        updatedAt = "2026-10-08T11:00:00Z",
                        periods = listOf(period),
                    ),
                daily = LocationWeatherSection("source_unavailable"),
                amounts = LocationWeatherSection("no_data"),
            )
        Dispatchers.setMain(Dispatchers.Unconfined)
        server.start()
        val vm = LocationWeatherViewModel(ApiRepository(server.url("/").toString(), vault, json))
        suspend fun finish() = withTimeout(10_000) { while (vm.state.value.loading) delay(10) }
        try {
            server.enqueue(MockResponse().setBody(json.encodeToString(response)))
            vm.load(response.requestedPoint)
            finish()
            assertEquals(response, vm.state.value.response)
            server.enqueue(MockResponse().setResponseCode(503).setBody("{}"))
            vm.load(response.requestedPoint)
            finish()
            val stale = vm.state.value.response!!
            assertEquals("stale", stale.state)
            assertEquals("stale", stale.hourly.state)
            assertEquals(response.hourly.updatedAt, stale.hourly.updatedAt)
            assertEquals(listOf(period), stale.hourly.periods)
            assertNull(stale.hourly.periods.single().rainChance)
            assertEquals("no_data", stale.observation.state)
            assertEquals("source_unavailable", stale.daily.state)
            assertNotNull(vm.state.value.message)
            server.enqueue(MockResponse().setBody(json.encodeToString(response)))
            vm.load(response.requestedPoint)
            finish()
            assertEquals(response, vm.state.value.response)
            assertNull(vm.state.value.message)
        } finally {
            vm.cancel()
            server.shutdown()
            Dispatchers.resetMain()
        }
    }
}
