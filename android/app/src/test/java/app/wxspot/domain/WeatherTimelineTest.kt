package app.wxspot.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class WeatherTimelineTest {
    private val selection =
        WeatherSelection(
            sourceType = "radar",
            sourceId = "nws-ridge2",
            productId = "reflectivity",
            site = "KCLX",
            selectionGeneration = 3,
        )

    private val frame =
        WeatherFrame(
            id = "radar:nws-ridge2:KCLX:reflectivity:2026-10-06T15:00:00.000Z",
            sourceType = "radar",
            provider = "nws-ridge2",
            product = "reflectivity",
            validTime = "2026-10-06T15:00:00Z",
            render =
                RenderDescriptor(
                    kind = "xyz",
                    urlTemplate = "https://weather.example/{z}/{x}/{y}.png",
                    contentVersion = "fixture-v1",
                ),
            attribution = "NOAA / National Weather Service",
            units = "dBZ",
        )

    @Test
    fun timelineKeepsSelectionAndDisplayedFrameIdentityTogether() {
        val timeline =
            WeatherTimeline(
                selection = selection,
                frames = listOf(frame),
                requestedFrameId = frame.id,
                displayedFrameId = frame.id,
                state = "ready",
                viewportGeneration = 5,
            )

        assertEquals(selection, timeline.selection)
        assertEquals(frame.id, timeline.requestedFrameId)
        assertEquals(frame.id, timeline.displayedFrameId)
    }

    @Test
    fun timelineRejectsStaleDisplayedFrameIdentity() {
        assertThrows(IllegalArgumentException::class.java) {
            WeatherTimeline(
                selection = selection,
                frames = listOf(frame),
                displayedFrameId = "radar:nws-ridge2:KCLX:reflectivity:older",
            )
        }
    }
}
