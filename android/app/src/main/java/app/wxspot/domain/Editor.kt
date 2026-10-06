package app.wxspot.domain

import kotlin.math.cos
import kotlin.math.sin
import kotlinx.serialization.Serializable

enum class Tool(val label: String, val wire: String) {
    SELECT("Select", "select"),
    PIN("Pin", "pin"),
    ELLIPSE("Circle", "ellipse"),
    ARROW("Arrow", "arrow"),
    LINE("Line", "line"),
    POLYGON("Region", "polygon"),
    FREEHAND("Draw", "freehand"),
    TEXT("Text", "text"),
}

data class EditorState(
    val elements: List<AnnotationElement> = emptyList(),
    val selectedId: String? = null,
    val undo: List<List<AnnotationElement>> = emptyList(),
    val redo: List<List<AnnotationElement>> = emptyList(),
) {
    fun commit(next: List<AnnotationElement>): EditorState =
        if (next == elements) this
        else
            copy(elements = next, undo = (undo + listOf(elements)).takeLast(50), redo = emptyList())

    fun undo(): EditorState =
        if (undo.isEmpty()) this
        else copy(elements = undo.last(), undo = undo.dropLast(1), redo = redo + listOf(elements))

    fun redo(): EditorState =
        if (redo.isEmpty()) this
        else copy(elements = redo.last(), redo = redo.dropLast(1), undo = undo + listOf(elements))

    fun deleteSelected(): EditorState =
        commit(elements.filterNot { it.id == selectedId }).copy(selectedId = null)

    fun add(element: AnnotationElement): EditorState =
        commit(elements + element).copy(selectedId = element.id)
}

@Serializable
data class Draft(
    val context: WeatherContext,
    val elements: List<AnnotationElement>,
    val contentType: String = "observation",
    val description: String = "",
    val title: String = "",
    val whyItMatters: String = "",
    val watchNext: String = "",
    val topics: List<String> = emptyList(),
    val photoIds: List<String> = emptyList(),
)

object GeometryEditor {
    fun ellipse(a: List<Double>, b: List<Double>): GeoGeometry {
        val center = listOf((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        val rx = kotlin.math.abs(a[0] - b[0]) / 2
        val ry = kotlin.math.abs(a[1] - b[1]) / 2
        require(rx > 0.00001 && ry > 0.00001)
        val ring =
            (0 until 64).map { i ->
                val angle = i * 2 * Math.PI / 64
                listOf(center[0] + rx * cos(angle), center[1] + ry * sin(angle))
            }
        return GeoGeometry.of("Polygon", ring + listOf(ring.first()))
    }

    fun translate(element: AnnotationElement, delta: List<Double>): AnnotationElement =
        element.copy(
            geometry =
                GeoGeometry.of(
                    element.geometry.type,
                    element.geometry.vertices().map { p ->
                        listOf(
                            (p[0] + delta[0]).coerceIn(-180.0, 180.0),
                            (p[1] + delta[1]).coerceIn(-85.0, 85.0),
                        )
                    },
                )
        )

    fun handles(element: AnnotationElement): List<List<Double>> {
        val points = element.geometry.vertices()
        if (element.tool != "ellipse")
            return if (element.geometry.type == "Polygon") points.dropLast(1) else points
        val west = points.minOf { it[0] }
        val east = points.maxOf { it[0] }
        val south = points.minOf { it[1] }
        val north = points.maxOf { it[1] }
        return listOf(
            listOf(west, north),
            listOf(east, north),
            listOf(east, south),
            listOf(west, south),
        )
    }

    fun moveVertex(element: AnnotationElement, index: Int, point: List<Double>): AnnotationElement {
        if (element.tool == "ellipse") {
            val opposite = handles(element)[(index + 2) % 4]
            return runCatching { element.copy(geometry = ellipse(point, opposite)) }
                .getOrDefault(element)
        }

        val vertices = element.geometry.vertices().toMutableList()
        vertices[index] = point
        if (element.geometry.type == "Polygon" && (index == 0 || index == vertices.lastIndex)) {
            vertices[0] = point
            vertices[vertices.lastIndex] = point
        }
        return element.copy(geometry = GeoGeometry.of(element.geometry.type, vertices))
    }
}
