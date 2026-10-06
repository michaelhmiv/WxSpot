package app.wxspot

import android.graphics.BitmapFactory
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import app.wxspot.domain.AnnotationElement
import app.wxspot.domain.GeoGeometry
import app.wxspot.domain.GeometryEditor
import app.wxspot.ui.MapViewModel
import java.util.UUID
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Requires the real API/PostGIS and real NOAA source; never runs against an invented scan. */
@RunWith(AndroidJUnit4::class)
class LiveReplayIntegrationTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()

    @Test
    fun twoAccountsCapturePublishRestoreAdvanceAndReturn() {
        lateinit var vm: MapViewModel
        compose.runOnUiThread { vm = ViewModelProvider(compose.activity)[MapViewModel::class.java] }
        assertNull(vm.state.value.session)
        compose.waitUntil(120_000) { vm.state.value.frames.size >= 5 }
        compose.waitUntil(120_000) { vm.state.value.rasterState == "ready" }
        val suffix = UUID.randomUUID().toString().take(8)
        compose.runOnUiThread {
            vm.signIn(
                "author-$suffix@example.com",
                "An acceptance test passphrase!",
                "Acceptance Author",
            )
        }
        compose.waitUntil(30_000) { vm.state.value.session != null }
        compose.runOnUiThread {
            vm.scrub(vm.state.value.frames.size - 4)
            val s = vm.state.value
            vm.longPress(s.camera.center, s.camera, s.bounds)
            vm.startDraft("analysis")
            val p = s.camera.center
            vm.add(
                AnnotationElement(
                    tool = "arrow",
                    geometry = GeoGeometry.of("LineString", listOf(p, listOf(p[0] + .1, p[1] + .1))),
                )
            )
            vm.add(
                AnnotationElement(
                    tool = "ellipse",
                    geometry =
                        GeometryEditor.ellipse(
                            listOf(p[0] - .1, p[1] - .1),
                            listOf(p[0] + .1, p[1] + .1),
                        ),
                )
            )
            vm.add(
                AnnotationElement(
                    tool = "text",
                    geometry = GeoGeometry.of("Point", listOf(p)),
                    label = "Watch the leading edge",
                )
            )
            vm.draft(
                vm.state.value.draft!!.copy(
                    description =
                        "Integration test: watch how this return evolves through the next scans.",
                    whyItMatters = "Compare the marked position with subsequent returns.",
                    watchNext = "Watch whether the leading edge moves east.",
                )
            )
            vm.publish()
        }
        compose.waitUntil(120_000) {
            vm.state.value.selected != null && vm.state.value.draft == null
        }
        val published = vm.state.value.selected!!
        compose.waitUntil(30_000) { vm.state.value.posts.any { it.id == published.id } }
        compose.runOnUiThread { vm.signOut() }
        compose.waitUntil(30_000) { vm.state.value.session == null }
        compose.runOnUiThread {
            vm.signIn(
                "viewer-$suffix@example.com",
                "Another acceptance passphrase!",
                "Acceptance Viewer",
            )
        }
        compose.waitUntil(30_000) { vm.state.value.session != null }
        compose.runOnUiThread { vm.open(published.id) }
        compose.waitUntil(30_000) { vm.state.value.selected?.id == published.id }
        compose.waitUntil(120_000) { vm.state.value.rasterState == "ready" }
        val restored = vm.state.value
        assertEquals(published.context, restored.selected!!.context)
        assertEquals(published.context.camera, restored.camera)
        assertEquals(published.elements, restored.annotationElements)
        assertTrue(restored.replay!!.isMarked)
        assertEquals(published.context.layers.first().product, restored.product)
        runBlocking {
            val archive = published.archives.single()
            vm.api.client
                .newCall(okhttp3.Request.Builder().url(vm.api.url(archive.url)).build())
                .execute()
                .use {
                    assertTrue(it.isSuccessful)
                    assertNotNull(BitmapFactory.decodeStream(it.body!!.byteStream()))
                }
        }
        compose.waitUntil(90_000) {
            vm.state.value.timeline.any {
                it.instant() >
                    published.context.layers.first().validTime.let(java.time.Instant::parse)
            }
        }
        compose.runOnUiThread { vm.scrub(vm.state.value.timeline.lastIndex) }
        assertTrue(vm.state.value.replay!!.deltaMinutes > 0)
        assertEquals(published.elements, vm.state.value.annotationElements)
        compose.runOnUiThread { vm.marked() }
        assertTrue(vm.state.value.replay!!.isMarked)
        assertEquals(published.context.camera, vm.state.value.camera)
        compose.runOnUiThread {
            vm.like()
            vm.follow()
            vm.comment("What should we watch in the next scan?", null)
        }
        compose.waitUntil(30_000) {
            vm.state.value.selected?.liked == true &&
                vm.state.value.selected?.followingAuthor == true &&
                vm.state.value.comments.isNotEmpty()
        }
        compose.runOnUiThread { vm.filter(sort = "following", type = "analysis") }
        compose.waitUntil(30_000) { vm.state.value.posts.any { it.id == published.id } }
        assertTrue(vm.state.value.posts.size <= 10)
    }
}
