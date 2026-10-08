package app.wxspot.ui

import app.wxspot.domain.RadarFrame
import app.wxspot.domain.mapFrame
import org.junit.Assert.assertEquals
import org.junit.Test

class UiStateFrameIdentityTest {
    @Test
    fun satelliteAndModelContextSurviveCaptureAndReplayConversion() {
        for (frame in
            listOf(
                RadarFrame(
                    "goes:19:infrared:20262802326178:v1",
                    "2026-10-07T23:27:37Z",
                    "",
                    "infrared",
                    provider = "noaa-goes",
                    sourceType = "satellite",
                    satellite = "GOES-19",
                    channel = "C13",
                ),
                RadarFrame(
                    "model:gfs:20261007T1800Z:003:temperature:v1",
                    "2026-10-07T21:00:00Z",
                    "",
                    "temperature",
                    provider = "noaa-models",
                    sourceType = "model",
                    model = "gfs",
                    runTime = "2026-10-07T18:00:00Z",
                    forecastHour = 3,
                    verticalLevel = "2 m above ground",
                    domain = "global",
                ),
            )) {
            val captured = frame.layer(0.6)
            val restored = captured.mapFrame()
            assertEquals(frame.id, restored.id)
            assertEquals(frame.satellite, restored.satellite)
            assertEquals(frame.channel, restored.channel?.ifBlank { null })
            assertEquals(frame.model, restored.model)
            assertEquals(frame.runTime, restored.runTime)
            assertEquals(frame.forecastHour, restored.forecastHour)
            assertEquals(frame.verticalLevel, restored.verticalLevel)
        }
    }

    @Test
    fun requestedFrameCanAdvanceWhileThePreviousFrameRemainsDisplayed() {
        val previous = RadarFrame("scan:old", "2026-10-06T15:00:00Z", "KCLX", "reflectivity")
        val requested = RadarFrame("scan:new", "2026-10-06T15:05:00Z", "KCLX", "reflectivity")
        val state =
            UiState(
                frames = listOf(previous, requested),
                viewingId = requested.id,
                displayedFrame = previous,
                rasterState = "loading",
            )

        assertEquals(requested.id, state.requestedFrame?.id)
        assertEquals(previous.id, state.currentFrame?.id)
    }
}
