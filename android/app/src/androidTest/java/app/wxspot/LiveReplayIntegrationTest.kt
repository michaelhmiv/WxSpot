package app.wxspot

import android.content.Context
import android.content.pm.PackageManager
import android.graphics.BitmapFactory
import android.graphics.PointF
import android.os.ParcelFileDescriptor
import android.os.SystemClock
import android.view.InputDevice
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.view.inputmethod.InputMethodManager
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.semantics.SemanticsActions
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import app.wxspot.data.PlacesStore
import app.wxspot.domain.Camera
import app.wxspot.domain.SavedPlace
import app.wxspot.ui.MapViewModel
import java.util.UUID
import java.util.concurrent.atomic.AtomicReference
import java.util.regex.Pattern
import kotlin.math.log2
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.maplibre.android.camera.CameraUpdateFactory
import org.maplibre.android.geometry.LatLng
import org.maplibre.android.maps.MapLibreMap
import org.maplibre.android.maps.MapView
import org.maplibre.android.style.layers.LineLayer

/** Actual UI gestures plus API assertions, using real PostGIS and real NOAA scans. */
@RunWith(AndroidJUnit4::class)
class LiveReplayIntegrationTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    private lateinit var vm: MapViewModel

    @Before
    fun isolateActivityState() {
        compose.runOnUiThread {
            vm = ViewModelProvider(compose.activity)[MapViewModel::class.java]
            if (vm.state.value.draft != null) vm.discardDraft()
            vm.official(null)
            vm.sheet(null)
            vm.closePost()
            vm.navigate("Radar")
        }
    }

    @Test
    fun bottomShellSearchAndNearbyRadarUseLiveProviders() {
        compose.onNodeWithText("Satellite").performClick()
        assertEquals("Satellite", vm.state.value.weatherMode)
        compose.onNodeWithText("Models").performClick()
        assertEquals("Models", vm.state.value.weatherMode)
        compose.onNodeWithText("Radar").performClick()
        assertEquals("Radar", vm.state.value.weatherMode)

        compose.onNodeWithText("More").performClick()
        compose.onNodeWithText("Data sources and attribution").performClick()
        compose
            .onNodeWithText("Place search: OpenStreetMap contributors via Nominatim.")
            .assertExists()
        compose.runOnUiThread { vm.sheet("more") }
        compose.onNodeWithText("Search places").performClick()
        compose
            .onNodeWithText("City, address, or place")
            .performTextInput("Charleston, South Carolina")
        compose.onAllNodesWithText("Search", substring = false).onLast().performClick()
        compose.waitUntil(60_000) {
            vm.state.value.placeSearchState == "ready" &&
                vm.state.value.placeSearchResults.isNotEmpty()
        }
        assertTrue(vm.state.value.placeSearchResults.first().name.contains("Charleston"))
        compose.onAllNodesWithText("Show on map").onFirst().performClick()

        compose.onNodeWithText("Nearby").performClick()
        compose.waitUntil(60_000) {
            vm.state.value.radarStationState == "ready" &&
                vm.state.value.radarStations.any { it.id == "KCLX" }
        }
        val kclx = vm.state.value.radarStations.first { it.id == "KCLX" }
        compose.onNodeWithText("KCLX · ${kclx.name}").performClick()
        assertEquals("KCLX", vm.state.value.site)

        val firstPoint = listOf(-150.12345, 60.12345)
        val secondPoint = listOf(150.12345, -60.12345)
        val suffix = UUID.randomUUID().toString().take(8)
        val firstName = "Acceptance Place A $suffix"
        val secondName = "Acceptance Place B $suffix"
        val renamed = "Renamed Acceptance Place $suffix"
        assertFalse(
            vm.state.value.savedPlaces.any {
                (kotlin.math.abs(it.lon - firstPoint[0]) < 0.0001 &&
                    kotlin.math.abs(it.lat - firstPoint[1]) < 0.0001) ||
                    (kotlin.math.abs(it.lon - secondPoint[0]) < 0.0001 &&
                        kotlin.math.abs(it.lat - secondPoint[1]) < 0.0001)
            }
        )
        try {
            compose.runOnUiThread { vm.selectLocation(listOf(firstPoint[0], firstPoint[1])) }
            val newPlaceName = compose.onNodeWithText("Saved place name")
            newPlaceName.performTextClearance()
            newPlaceName.performTextInput(firstName)
            compose.onNodeWithText("Save place").performClick()
            compose.waitUntil(5_000) {
                vm.state.value.sheet == "places" &&
                    vm.state.value.savedPlaces.any { it.name == firstName }
            }
            compose.runOnUiThread { vm.addPlace(secondName, secondPoint) }
            compose.waitUntil(5_000) { vm.state.value.savedPlaces.any { it.name == secondName } }
            val firstId = vm.state.value.savedPlaces.first { it.name == firstName }.id
            val secondId = vm.state.value.savedPlaces.first { it.name == secondName }.id
            val firstIndex = vm.state.value.savedPlaces.indexOfFirst { it.id == firstId }
            val secondIndex = vm.state.value.savedPlaces.indexOfFirst { it.id == secondId }
            assertEquals("The acceptance places should be adjacent", firstIndex + 1, secondIndex)

            compose.onNodeWithContentDescription("Rename $firstName").performClick()
            val renamePlaceName = compose.onNodeWithText("Place name")
            renamePlaceName.performTextClearance()
            renamePlaceName.performTextInput(renamed)
            compose.onNodeWithText("Save name").performClick()
            assertEquals(renamed, vm.state.value.savedPlaces.first { it.id == firstId }.name)

            compose.onNodeWithContentDescription("Move $renamed down").performClick()
            compose.waitUntil(5_000) {
                vm.state.value.savedPlaces.indexOfFirst { it.id == secondId } <
                    vm.state.value.savedPlaces.indexOfFirst { it.id == firstId }
            }
            compose.onNodeWithContentDescription("Move $renamed up").performClick()
            compose.waitUntil(5_000) {
                vm.state.value.savedPlaces.indexOfFirst { it.id == firstId } <
                    vm.state.value.savedPlaces.indexOfFirst { it.id == secondId }
            }

            compose.onNodeWithContentDescription("Delete $renamed").performClick()
            assertFalse(vm.state.value.savedPlaces.any { it.id == firstId })
            compose.onNodeWithContentDescription("Delete $secondName").performClick()
            assertFalse(vm.state.value.savedPlaces.any { it.id == secondId })
        } finally {
            vm.state.value.savedPlaces
                .filter {
                    it.name == firstName ||
                        it.name == secondName ||
                        it.name == renamed ||
                        kotlin.math.abs(it.lon - firstPoint[0]) < 0.0001 &&
                            kotlin.math.abs(it.lat - firstPoint[1]) < 0.0001 ||
                        kotlin.math.abs(it.lon - secondPoint[0]) < 0.0001 &&
                            kotlin.math.abs(it.lat - secondPoint[1]) < 0.0001
                }
                .forEach { vm.deletePlace(it.id) }
        }
        compose.onNodeWithText("More").assertExists()
    }

    @Test
    fun foregroundPermissionDenialKeepsManualSearchAvailable() {
        val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
        val context = InstrumentationRegistry.getInstrumentation().targetContext
        device.executeShellCommand(
            "pm revoke ${context.packageName} android.permission.ACCESS_COARSE_LOCATION"
        )
        device.executeShellCommand(
            "pm revoke ${context.packageName} android.permission.ACCESS_FINE_LOCATION"
        )
        assertEquals(
            PackageManager.PERMISSION_DENIED,
            context.checkSelfPermission(android.Manifest.permission.ACCESS_COARSE_LOCATION),
        )
        assertEquals(
            PackageManager.PERMISSION_DENIED,
            context.checkSelfPermission(android.Manifest.permission.ACCESS_FINE_LOCATION),
        )
        compose.onNodeWithContentDescription("Use current location").performClick()
        val deny =
            device.wait(Until.findObject(By.text(Pattern.compile("(?i)don't allow|deny"))), 10_000)
        assertNotNull("Foreground location permission dialog must be shown", deny)
        deny!!.click()
        compose.waitUntil(10_000) { vm.state.value.gpsMessage?.contains("denied") == true }
        compose.onNodeWithText("Search", substring = false).performClick()
        compose.onNodeWithText("City, address, or place").assertExists()
    }

    @Test
    fun savedPlacesCameraAndUnitsSurviveStoreReconstruction() {
        val app =
            InstrumentationRegistry.getInstrumentation().targetContext.applicationContext
                as WxSpotApplication
        val preferencesName = "wxspot_places_acceptance_${UUID.randomUUID()}"
        val store = PlacesStore(app, app.api.json, preferencesName)
        val place = SavedPlace(name = "Acceptance place", lat = 40.7128, lon = -74.0060)
        val camera = Camera(center = listOf(-70.5, 40.5), zoom = 9.25, bearing = 32.0, pitch = 12.0)
        try {
            store.writePlaces(listOf(place))
            store.writeCamera(camera)
            store.writeMetricUnits(true)
            val restored = PlacesStore(app, app.api.json, preferencesName)
            assertEquals(place, restored.readPlaces().last())
            assertEquals(camera, restored.readCamera())
            assertEquals(true, restored.readMetricUnits())
        } finally {
            app.deleteSharedPreferences(preferencesName)
        }
    }

    @Test
    fun twoDeviceProfilesCapturePublishRestoreAdvanceAndReturnWithoutSignIn() {
        compose.runOnUiThread { vm = ViewModelProvider(compose.activity)[MapViewModel::class.java] }
        compose.waitUntil(120_000) { vm.state.value.frames.size >= 5 }
        compose.waitUntil(120_000) { vm.state.value.rasterState == "ready" }
        assertTrue(
            "Start close enough to inspect the selected radar",
            vm.state.value.camera.zoom > 6.0,
        )
        assertEquals(-80.18, vm.state.value.camera.center[0], 0.01)
        assertEquals(33.02, vm.state.value.camera.center[1], 0.01)
        compose.onNodeWithText("Sign in").assertDoesNotExist()
        compose.onNodeWithText("Email").assertDoesNotExist()
        compose.onNodeWithText("Passphrase").assertDoesNotExist()

        val displayedBeforeSwitch = vm.state.value.displayedFrame
        compose.runOnUiThread { vm.layer("KTLX", "velocity") }
        SystemClock.sleep(250)
        compose.runOnUiThread { vm.layer("KCLX", "reflectivity") }
        assertEquals("KCLX", vm.state.value.site)
        assertNotNull(
            "Keep the current frame visible while switching",
            vm.state.value.displayedFrame,
        )
        compose.waitUntil(30_000) {
            val state = vm.state.value
            state.site == "KCLX" &&
                state.product == "reflectivity" &&
                state.frames.size >= 5 &&
                state.rasterState == "ready" &&
                state.displayedFrame?.id == state.requestedFrame?.id
        }
        assertNotNull(displayedBeforeSwitch)
        screenshot("01-anonymous-map")
        compose.waitUntil(30_000) { vm.state.value.session != null }

        val initialState = vm.state.value
        val earlierIndex = (initialState.timeline.lastIndex - 1).coerceAtLeast(0)
        val cameraBeforePan = initialState.camera
        val viewportBeforePan = initialState.viewportGeneration
        compose.runOnUiThread { vm.scrub(earlierIndex) }
        compose.waitUntil(5_000) { vm.state.value.rasterState == "loading" }
        val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
        assertTrue(
            "Dispatch a real drag across the map",
            device.swipe(
                (device.displayWidth * .76f).toInt(),
                (device.displayHeight * .36f).toInt(),
                (device.displayWidth * .43f).toInt(),
                (device.displayHeight * .33f).toInt(),
                28,
            ),
        )
        compose.waitUntil(10_000) {
            vm.state.value.viewportGeneration > viewportBeforePan &&
                vm.state.value.camera.center != cameraBeforePan.center
        }
        compose.waitUntil(30_000) {
            val state = vm.state.value
            state.rasterState == "ready" &&
                state.displayedFrame?.id == state.requestedFrame?.id &&
                state.displayedViewportGeneration == state.viewportGeneration
        }
        compose.runOnUiThread { vm.live() }
        compose.waitUntil(30_000) {
            val state = vm.state.value
            state.rasterState == "ready" &&
                state.displayedFrame?.id == state.requestedFrame?.id &&
                state.displayedViewportGeneration == state.viewportGeneration
        }
        setDisplayName("Acceptance Author")
        val authorSession = vm.api.vault.current!!
        assertNotNull(authorSession.resumeKey)

        compose.onNodeWithContentDescription("Animate radar scans").performClick()
        compose.waitUntil(5_000) { vm.state.value.playing }
        var lastDisplayedId = vm.state.value.displayedFrame!!.id
        repeat(10) {
            compose.waitUntil(20_000) {
                val state = vm.state.value
                state.playing &&
                    state.rasterState == "ready" &&
                    state.requestedFrame?.id != lastDisplayedId &&
                    state.displayedFrame?.id == state.requestedFrame?.id
            }
            val rendered = vm.state.value
            assertNotNull(
                "A previous radar frame stays available during playback",
                rendered.displayedFrame,
            )
            assertEquals(rendered.requestedFrame?.id, rendered.displayedFrame?.id)
            lastDisplayedId = rendered.displayedFrame!!.id
        }
        compose.onNodeWithContentDescription("Pause radar animation").performClick()
        compose.onNodeWithTag("weather_timeline").performSemanticsAction(
            SemanticsActions.SetProgress
        ) {
            it((vm.state.value.frames.size - 4).toFloat())
        }
        val suffix = UUID.randomUUID().toString().take(8)
        val markedFrame = vm.state.value.currentFrame!!
        nativeLongPress()
        compose.waitUntil(5_000) { vm.state.value.pending != null }
        val captured = vm.state.value.pending!!.context
        assertEquals(markedFrame.validTime, captured.layers.first().validTime)
        compose.waitUntil(30_000) { vm.state.value.sheet == "mark" }
        assertEquals(captured, vm.state.value.pending!!.context)
        compose.onNodeWithText("Analysis").performClick()
        compose.waitUntil(5_000) { vm.state.value.draft != null }

        compose.onNodeWithText("Arrow").performScrollTo().performClick()
        compose.onNodeWithTag("weather_map").performTouchInput {
            swipe(Offset(width * .28f, height * .36f), Offset(width * .45f, height * .31f), 700)
        }
        compose.waitUntil(5_000) { vm.state.value.editor.elements.size == 2 }
        compose.onNodeWithText("Circle").performScrollTo().performClick()
        compose.onNodeWithTag("weather_map").performTouchInput {
            swipe(Offset(width * .55f, height * .35f), Offset(width * .74f, height * .46f), 700)
        }
        compose.waitUntil(5_000) { vm.state.value.editor.elements.size == 3 }
        compose.onNodeWithText("Undo").performClick()
        assertEquals(2, vm.state.value.editor.elements.size)
        compose.onNodeWithText("Redo").performClick()
        assertEquals(3, vm.state.value.editor.elements.size)
        compose.onNodeWithText("Text").performScrollTo().performClick()
        compose.onNodeWithTag("weather_map").performTouchInput {
            click(Offset(width * .30f, height * .20f))
        }
        compose.waitUntil(5_000) { vm.state.value.sheet == "text" }
        compose.onNodeWithText("Weather feature").performTextInput("Watch the leading edge")
        hideKeyboard()
        compose.onNodeWithText("Add label").performClick()
        compose.waitUntil(5_000) { vm.state.value.editor.elements.size == 4 }
        val drawn = vm.state.value.editor.elements
        assertEquals(setOf("pin", "arrow", "ellipse", "text"), drawn.map { it.tool }.toSet())
        assertEquals(captured, vm.state.value.draft!!.context)
        screenshot("02-geographic-editor")

        compose.onNodeWithText("Describe & publish", substring = true).performClick()
        val description =
            "Device acceptance $suffix: comparing this marked return with subsequent scans."
        compose.onNodeWithText("What are you seeing?").performTextInput(description)
        hideKeyboard()
        compose
            .onNodeWithText("Add title, topics & what to watch next")
            .performScrollTo()
            .performClick()
        compose
            .onNodeWithText("Why this matters (optional)")
            .performScrollTo()
            .performTextInput("Keep the original geographic position visible as weather evolves.")
        compose
            .onNodeWithText("What to watch next (optional)")
            .performScrollTo()
            .performTextInput("Compare the feature with the next available scans.")
        hideKeyboard()
        compose.onNodeWithText("Publish annotation").performScrollTo().performClick()
        compose.waitUntil(120_000) {
            vm.state.value.selected != null && vm.state.value.draft == null
        }
        val published = vm.state.value.selected!!
        // The API persists the capture clock at microsecond precision; radar valid time is exact.
        assertEquals(captured.copy(capturedAt = published.context.capturedAt), published.context)
        assertEquals(
            java.time.Instant.parse(captured.capturedAt)
                .truncatedTo(java.time.temporal.ChronoUnit.MICROS),
            java.time.Instant.parse(published.context.capturedAt),
        )
        assertEquals(drawn, published.elements)
        compose.waitUntil(30_000) { vm.state.value.posts.any { it.id == published.id } }
        screenshot("03-published-marked-frame")

        // A second content type makes the eventual map filter change observable.
        compose.onNodeWithContentDescription("Close annotation").performClick()
        nativeLongPress(.25f, .45f)
        compose.waitUntil(5_000) { vm.state.value.sheet == "mark" }
        compose.onNodeWithText("Observation").performClick()
        compose.onNodeWithText("Describe & publish", substring = true).performClick()
        compose
            .onNodeWithText("What are you seeing?")
            .performTextInput(
                "Device observation $suffix: a second content type for spatial discovery."
            )
        hideKeyboard()
        compose.onNodeWithText("Publish annotation").performScrollTo().performClick()
        compose.waitUntil(120_000) {
            vm.state.value.selected?.contentType == "observation" && vm.state.value.draft == null
        }
        val observation = vm.state.value.selected!!
        compose.waitUntil(30_000) {
            vm.state.value.posts.any { it.id == published.id } &&
                vm.state.value.posts.any { it.id == observation.id }
        }

        // A fresh install has an empty encrypted identity vault. Simulate that second device;
        // its profile must be issued by the actual API, without registration or login controls.
        compose.runOnUiThread { vm.api.vault.save(null) }
        compose.onNodeWithText("More").performClick()
        compose.onNodeWithText("Device profile").performClick()
        compose.waitUntil(30_000) {
            vm.state.value.session != null &&
                vm.state.value.session!!.userId != authorSession.userId &&
                vm.state.value.sheet == "account"
        }
        assertNotEquals(authorSession.resumeKey, vm.state.value.session!!.resumeKey)
        setDisplayName("Acceptance Viewer")
        compose.onNodeWithText("Feed").performClick()
        compose.waitUntil(30_000) { vm.state.value.feedItems.any { it.id == published.id } }
        compose.onNodeWithText(description).performScrollTo().performClick()
        compose.waitUntil(30_000) { vm.state.value.selected?.id == published.id }
        compose.waitUntil(120_000) { vm.state.value.rasterState == "ready" }
        val restored = vm.state.value
        assertEquals(published.context, restored.selected!!.context)
        assertCameraMatches(published.context.camera, restored.camera)
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
        compose.onNodeWithText("Latest").performClick()
        assertTrue(vm.state.value.replay!!.deltaMinutes > 0)
        assertEquals(published.elements, vm.state.value.annotationElements)
        compose.waitUntil(120_000) { vm.state.value.rasterState == "ready" }
        screenshot("04-later-frame-fixed-marks")
        compose.onNodeWithText("Return to marked frame").performScrollTo().performClick()
        compose.waitUntil(10_000) { vm.state.value.replay?.isMarked == true }
        assertTrue(vm.state.value.replay!!.isMarked)
        assertCameraMatches(published.context.camera, vm.state.value.camera)
        compose.waitUntil(120_000) { vm.state.value.rasterState == "ready" }
        screenshot("05-return-to-marked-frame")

        compose.onNodeWithContentDescription("Like annotation").performClick()
        compose.waitUntil(30_000) { vm.state.value.selected?.liked == true }
        compose.onNodeWithText("Follow").performClick()
        compose.waitUntil(30_000) { vm.state.value.selected?.followingAuthor == true }
        compose.onNodeWithText("replies · More", substring = true).performClick()
        compose
            .onNodeWithText("Add to the discussion")
            .performScrollTo()
            .performTextInput("What should we watch in the next scan?")
        hideKeyboard()
        compose.onNodeWithText("Post comment").performScrollTo().performClick()
        compose.waitUntil(30_000) { vm.state.value.comments.isNotEmpty() }
        screenshot("06-community-discussion")
        compose.onNodeWithContentDescription("Close annotation").performClick()
        compose.waitUntil(5_000) { vm.state.value.selected == null }
        compose.onNodeWithText("Radar").performClick()
        compose.waitUntil(5_000) { vm.state.value.activeTab == "Radar" }
        assertEquals("Radar", vm.state.value.weatherMode)
        screenshot("06b-map-actions")
        compose.onNodeWithContentDescription("Community map filters").assertIsDisplayed()
        compose.onNodeWithContentDescription("Community map filters").performClick()
        compose.waitUntil(5_000) { vm.state.value.sheet == "filters" }
        screenshot("06b-community-filters")
        compose.waitUntil(5_000) {
            compose
                .onAllNodesWithText("People you follow", useUnmergedTree = true)
                .fetchSemanticsNodes()
                .isNotEmpty()
        }
        compose.onNodeWithText("People you follow").performClick()
        compose.onAllNodesWithText("Analysis").onLast().performClick()
        compose.onNodeWithText("Return to map").performClick()
        assertEquals("following", vm.state.value.sort)
        assertEquals("analysis", vm.state.value.typeFilter)
        compose.waitUntil(30_000) {
            vm.state.value.posts.any { it.id == published.id } &&
                vm.state.value.posts.none { it.id == observation.id }
        }
        assertTrue(vm.state.value.posts.size <= 10)
        assertFalse(vm.state.value.posts.any { it.id == observation.id })
        screenshot("09-filtered-map")
    }

    @Test
    fun officialWarningsRenderAndOpenWithDistinctProvenance() {
        compose.runOnUiThread { vm = ViewModelProvider(compose.activity)[MapViewModel::class.java] }
        compose.waitUntil(120_000) { vm.state.value.alertsState == "ready" }
        // Complete the app's initial camera before positioning the actual warning for hit testing.
        compose.waitUntil(120_000) { vm.state.value.rasterState == "ready" }
        val features =
            vm.api.json
                .parseToJsonElement(vm.state.value.alerts)
                .jsonObject["features"]!!
                .jsonArray
                .map { it.jsonObject }
        val warning =
            features.first {
                it["properties"]!!
                    .jsonObject["event"]!!
                    .jsonPrimitive
                    .content
                    .contains("Warning") &&
                    (it["geometry"] as? JsonObject)?.get("type")?.jsonPrimitive?.content ==
                        "Polygon"
            }
        val ring =
            warning["geometry"]!!.jsonObject["coordinates"]!!.jsonArray.first().jsonArray.map {
                it.jsonArray.map { value -> value.jsonPrimitive.double }
            }
        val west = ring.minOf { it[0] }
        val east = ring.maxOf { it[0] }
        val south = ring.minOf { it[1] }
        val north = ring.maxOf { it[1] }
        val map = AtomicReference<MapLibreMap>()
        compose.runOnUiThread {
            val view = findMap(compose.activity.window.decorView)!!
            view.getMapAsync {
                map.set(it)
                it.moveCamera(
                    CameraUpdateFactory.newLatLngZoom(
                        LatLng((south + north) / 2, (west + east) / 2),
                        (log2(360 / maxOf(east - west, north - south)) - 1).coerceIn(3.0, 10.0),
                    )
                )
            }
        }
        val hit = AtomicReference<Offset>()
        compose.waitUntil(60_000) {
            compose.runOnUiThread {
                val m = map.get()
                val view = findMap(compose.activity.window.decorView)
                if (m?.style?.isFullyLoaded == true && view != null) {
                    assertNotNull(m.style!!.getSource("nws-alerts"))
                    val outline = m.style!!.getLayerAs<LineLayer>("nws-outline")!!
                    assertArrayEquals(arrayOf(3f, 2f), outline.lineDasharray.value)
                    val postMarkers =
                        vm.state.value.posts.map { post ->
                            m.projection.toScreenLocation(
                                LatLng(post.location[1], post.location[0])
                            )
                        }
                    val markerRadius = 40 * compose.activity.resources.displayMetrics.density
                    // Flood polygons can follow a narrow river; a few fixed sample points miss
                    // them. Avoid community markers and the covered lower map controls.
                    val mapLocation = IntArray(2)
                    view.getLocationOnScreen(mapLocation)
                    for (y in (view.height * .24f).toInt()..(view.height * .55f).toInt() step 8) {
                        for (x in (view.width * .10f).toInt()..(view.width * .90f).toInt() step 8) {
                            val point = PointF(x.toFloat(), y.toFloat())
                            val markerOverlap =
                                postMarkers.any { marker ->
                                    val dx = marker.x - point.x
                                    val dy = marker.y - point.y
                                    dx * dx + dy * dy < markerRadius * markerRadius
                                }
                            if (
                                !markerOverlap &&
                                    m.queryRenderedFeatures(point, "nws-fill").any {
                                        it.properties()
                                            ?.get("event")
                                            ?.asString
                                            .orEmpty()
                                            .contains("Warning")
                                    }
                            ) {
                                hit.set(Offset(mapLocation[0] + point.x, mapLocation[1] + point.y))
                                break
                            }
                        }
                        if (hit.get() != null) break
                    }
                }
            }
            hit.get() != null
        }
        screenshot("07-official-warning-polygons")
        val device = UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
        assertTrue(
            "Tap the warning on the live map",
            device.click(hit.get().x.toInt(), hit.get().y.toInt()),
        )
        compose.waitUntil(10_000) { vm.state.value.officialSelection != null }
        compose.onNodeWithText("OFFICIAL · NATIONAL WEATHER SERVICE").assertIsDisplayed()
        assertTrue(
            vm.state.value.officialSelection!!["event"]!!.jsonPrimitive.content.contains("Warning")
        )
        screenshot("08-official-warning-details")
    }

    private fun assertCameraMatches(expected: Camera, actual: Camera) {
        // Projection round-trips may change the last decimal; persisted context remains exact.
        expected.center.zip(actual.center).forEach { (e, a) -> assertEquals(e, a, 1e-8) }
        assertEquals(expected.zoom, actual.zoom, 1e-8)
        assertEquals(expected.bearing, actual.bearing, 1e-8)
        assertEquals(expected.pitch, actual.pitch, 1e-8)
    }

    private fun findMap(view: View): MapView? {
        if (view is MapView) return view
        if (view is ViewGroup)
            for (index in 0 until view.childCount) {
                findMap(view.getChildAt(index))?.let {
                    return it
                }
            }
        return null
    }

    private fun setDisplayName(name: String) {
        if (vm.state.value.sheet != "account") {
            compose.onNodeWithText("More").performClick()
            compose.onNodeWithText("Device profile").performClick()
        }
        compose.waitUntil(30_000) { vm.state.value.sheet == "account" }
        compose.onNodeWithText("Sign in").assertDoesNotExist()
        compose.onNodeWithText("Email").assertDoesNotExist()
        compose.onNodeWithText("Passphrase").assertDoesNotExist()
        compose.onNodeWithText("Display name").performTextClearance()
        compose.onNodeWithText("Display name").performTextInput(name)
        hideKeyboard()
        compose.onNodeWithText("Save profile").performClick()
        compose.waitUntil(30_000) {
            vm.state.value.session?.displayName == name && !vm.state.value.busy
        }
        compose.onNodeWithText("Return to map").performClick()
    }

    private fun hideKeyboard() {
        compose.runOnUiThread {
            val activity = compose.activity
            (activity.getSystemService(Context.INPUT_METHOD_SERVICE) as InputMethodManager)
                .hideSoftInputFromWindow(activity.window.decorView.windowToken, 0)
        }
        compose.waitForIdle()
    }

    private fun nativeLongPress(x: Float = .48f, y: Float = .42f) {
        // Native GestureDetector uses a real Handler deadline, not Compose's virtual event clock.
        val bounds = compose.onNodeWithTag("weather_map").fetchSemanticsNode().boundsInWindow
        val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
        val downTime = SystemClock.uptimeMillis()
        fun send(action: Int) {
            val event =
                MotionEvent.obtain(
                    downTime,
                    SystemClock.uptimeMillis(),
                    action,
                    bounds.left + bounds.width * x,
                    bounds.top + bounds.height * y,
                    0,
                )
            event.source = InputDevice.SOURCE_TOUCHSCREEN
            assertTrue(automation.injectInputEvent(event, true))
            event.recycle()
        }
        send(MotionEvent.ACTION_DOWN)
        SystemClock.sleep(850)
        send(MotionEvent.ACTION_UP)
        compose.waitForIdle()
    }

    private fun screenshot(name: String) {
        compose.waitForIdle()
        val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
        fun shell(command: String) {
            ParcelFileDescriptor.AutoCloseInputStream(automation.executeShellCommand(command)).use {
                it.readBytes()
            }
        }
        // Shared device files survive UTP's package uninstall and can be pulled by CI afterward.
        shell("mkdir -p /sdcard/wxspot-acceptance")
        shell("screencap -p /sdcard/wxspot-acceptance/$name.png")
    }
}
