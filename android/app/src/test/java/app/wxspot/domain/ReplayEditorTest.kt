package app.wxspot.domain

import kotlinx.serialization.json.Json
import org.junit.Assert.*
import org.junit.Test

class ReplayEditorTest {
    private val layer =
        WeatherLayer(
            product = "reflectivity",
            frameId = "scan:0",
            validTime = "2026-10-06T15:00:00Z",
            radarSite = "KCLX",
        )
    private val context =
        WeatherContext(
            capturedAt = "2026-10-06T15:02:00Z",
            camera = Camera(bearing = 24.0, pitch = 10.0),
            bounds = listOf(-81.0, 32.0, -79.0, 34.0),
            layers = listOf(layer),
        )
    private val arrow =
        AnnotationElement(
            tool = "arrow",
            geometry =
                GeoGeometry.of("LineString", listOf(listOf(-80.18, 33.02), listOf(-80.1, 33.1))),
        )
    private val post =
        WeatherPost(
            id = "post",
            author = Profile("author", "Author"),
            contentType = "analysis",
            description = "Watch this boundary",
            createdAt = "2026-10-06T15:02:00Z",
            context = context,
            elements = listOf(arrow),
            location = listOf(-80.18, 33.02),
        )
    private val later = RadarFrame("scan:1", "2026-10-06T15:12:00Z", "KCLX", "reflectivity")

    @Test
    fun replayAdvancesAndReturnsWithoutMovingGeographicMarks() {
        val initial = ReplaySession(post, listOf(later))
        val advanced = initial.advance(later.id)
        assertFalse(advanced.isMarked)
        assertEquals(12, advanced.deltaMinutes)
        assertEquals(context, advanced.post.context)
        assertEquals(arrow.geometry, advanced.post.elements.single().geometry)
        assertTrue(advanced.returnToMarked().isMarked)
        assertEquals(0, advanced.returnToMarked().deltaMinutes)
        assertTrue(initial.isMarked)
    }

    @Test
    fun expiredMarkedFrameIsStillInTimeline() {
        assertEquals(
            listOf(layer.frameId, later.id),
            ReplaySession(post, listOf(later)).timeline.map { it.id },
        )
    }

    @Test
    fun timelineDoesNotDuplicateMarkedScan() {
        val marked = later.copy(id = layer.frameId, validTime = layer.validTime)
        assertEquals(2, ReplaySession(post, listOf(later, marked)).timeline.size)
    }

    @Test(expected = IllegalArgumentException::class)
    fun replayRejectsUnknownFrame() {
        ReplaySession(post, listOf(later)).advance("invented")
    }

    @Test
    fun multilayerContextAndGeometryRoundTrip() {
        val model =
            WeatherLayer(
                id = "model",
                provider = "future",
                sourceType = "model",
                product = "cape",
                frameId = "hrrr:run:f03",
                validTime = later.validTime,
                model = "HRRR",
                runTime = "2026-10-06T12:00:00Z",
                forecastHour = 3,
                verticalLevel = "surface",
            )
        val value =
            Draft(
                context.copy(layers = listOf(layer, model)),
                listOf(arrow),
                description = "Keep me",
            )
        assertEquals(value, Json.decodeFromString<Draft>(Json.encodeToString(value)))
    }

    @Test
    fun editMoveDeleteUndoRedoRetainsExactGeometry() {
        val original = EditorState().add(arrow)
        val moved = GeometryEditor.translate(arrow, listOf(0.25, 0.5))
        val edited = original.commit(listOf(moved)).deleteSelected()
        assertTrue(edited.elements.isEmpty())
        assertEquals(moved, edited.undo().elements.single())
        assertEquals(arrow, edited.undo().undo().elements.single())
        assertTrue(edited.undo().redo().elements.isEmpty())
        assertTrue(edited.undo().commit(listOf(arrow)).redo.isEmpty())
    }

    @Test
    fun resizingPolygonKeepsRingClosed() {
        val ellipse =
            arrow.copy(
                tool = "ellipse",
                geometry = GeometryEditor.ellipse(listOf(-81.0, 32.0), listOf(-80.0, 33.0)),
            )
        assertEquals(65, ellipse.geometry.vertices().size)
        val resized = GeometryEditor.moveVertex(ellipse, 0, listOf(-81.5, 33.5))
        assertEquals(resized.geometry.vertices().first(), resized.geometry.vertices().last())
        assertEquals(4, GeometryEditor.handles(resized).size)
        assertEquals(65, resized.geometry.vertices().size)
    }

    @Test
    fun editHistoryIsBounded() {
        var state = EditorState()
        repeat(70) { state = state.commit(listOf(arrow.copy(stroke = it.toDouble()))) }
        assertEquals(50, state.undo.size)
    }
}
