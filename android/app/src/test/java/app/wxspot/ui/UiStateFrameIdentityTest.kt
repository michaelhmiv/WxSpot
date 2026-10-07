package app.wxspot.ui

import app.wxspot.domain.RadarFrame
import org.junit.Assert.assertEquals
import org.junit.Test

class UiStateFrameIdentityTest {
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
