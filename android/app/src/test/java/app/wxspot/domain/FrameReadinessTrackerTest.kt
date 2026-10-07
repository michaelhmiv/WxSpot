package app.wxspot.domain

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class FrameReadinessTrackerTest {
    private fun key(
        frame: String,
        product: String = "reflectivity",
        selection: Long = 1,
        viewport: Long = 2,
    ) =
        FrameRequestKey(
            sourceId = "nws-ridge2",
            frameId = "$product:$frame",
            selectionGeneration = selection,
            viewportGeneration = viewport,
            mapSourceId = "source-$product-$frame-$selection-$viewport",
        )

    private val tile = WeatherTileKey(x = 1, y = 2, z = 3, wrap = 0, overscaledZ = 3)

    @Test
    fun frameRequiresParsedTilesAndARenderAfterCandidateTiles() {
        var now = 100L
        val tracker = FrameReadinessTracker { now }
        val requested = key("same-time")
        tracker.begin(requested)
        tracker.observe(requested, tile, WeatherTileEvent.REQUESTED_FROM_NETWORK)

        assertNull(tracker.finishRendering(requested, renderedAfterCandidateTiles = true))
        tracker.observe(requested, tile, WeatherTileEvent.END_PARSE)
        assertNull(tracker.finishRendering(requested, renderedAfterCandidateTiles = false))
        now = 420L

        assertEquals(
            "ready",
            tracker.finishRendering(requested, renderedAfterCandidateTiles = true)?.state,
        )
        assertEquals(320L, tracker.metrics().elapsedMillis)
        assertEquals(1, tracker.metrics().parsedTiles)
        assertEquals(1, tracker.metrics().networkLoads)
    }

    @Test
    fun cacheLookupsWithoutLoadedTilesDoNotHoldReadiness() {
        val tracker = FrameReadinessTracker()
        val current = key("cache-lookup")
        val deferredCacheProbe = tile.copy(x = 2)
        tracker.begin(current)
        tracker.observe(current, deferredCacheProbe, WeatherTileEvent.REQUESTED_FROM_CACHE)
        tracker.observe(current, tile, WeatherTileEvent.REQUESTED_FROM_NETWORK)
        tracker.observe(current, tile, WeatherTileEvent.LOAD_FROM_NETWORK)
        tracker.observe(current, tile, WeatherTileEvent.END_PARSE)

        assertEquals(0, tracker.metrics().pendingTiles)
        assertEquals(1, tracker.metrics().parsedTiles)
        assertEquals("ready", tracker.finishRendering(current, true)?.state)
    }

    @Test
    fun lateProductAndGenerationCallbacksCannotCompleteTheCurrentRequest() {
        val tracker = FrameReadinessTracker()
        val old = key("2026-10-06T15:00Z", product = "reflectivity")
        val current = key("2026-10-06T15:00Z", product = "velocity", selection = 2)
        tracker.begin(old)
        tracker.observe(old, tile, WeatherTileEvent.END_PARSE)
        tracker.begin(current)

        assertFalse(tracker.observe(old, tile, WeatherTileEvent.ERROR))
        assertNull(tracker.finishRendering(old, renderedAfterCandidateTiles = true))
        assertNull(tracker.finishRendering(current, renderedAfterCandidateTiles = true))
        tracker.observe(current, tile, WeatherTileEvent.END_PARSE)
        assertEquals("velocity:2026-10-06T15:00Z", tracker.finishRendering(current, true)?.frameId)
    }

    @Test
    fun tileFailureIsReportedOnlyForTheCurrentFrame() {
        val tracker = FrameReadinessTracker()
        val current = key("current")
        val stale = key("stale")
        tracker.begin(current)
        assertNull(tracker.fail(stale, "late network error"))
        tracker.observe(current, tile, WeatherTileEvent.ERROR)

        val failure = tracker.finishRendering(current, renderedAfterCandidateTiles = true)
        assertEquals("error", failure?.state)
        assertEquals("One or more radar tiles failed", failure?.error)
    }

    @Test
    fun prefetchWindowIsBoundedAndContainsCurrentNextTwoAndPrevious() {
        val frames = (0..7).toList()
        val result = FrameReadinessTracker.prefetchWindow(frames, 5) { it.toString() }

        assertEquals(listOf(5, 6, 7, 4), result)
        assertEquals(WeatherLoadingPolicy.MAX_PREFETCH_FRAMES, result.size)
        assertTrue(
            WeatherLoadingPolicy.MAX_REQUESTS_PER_ORIGIN <
                WeatherLoadingPolicy.MAX_CONCURRENT_REQUESTS
        )
    }
}
