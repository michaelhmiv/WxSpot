package app.wxspot

import android.content.Context
import android.content.pm.PackageManager
import android.os.ParcelFileDescriptor
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import app.wxspot.data.DraftStore
import app.wxspot.data.PlacesStore
import app.wxspot.data.SessionVault
import app.wxspot.domain.AnnotationElement
import app.wxspot.domain.Draft
import app.wxspot.domain.GeoGeometry
import app.wxspot.domain.SavedPlace
import app.wxspot.domain.WeatherContext
import app.wxspot.ui.MapViewModel
import java.io.File
import java.security.MessageDigest
import java.time.Instant
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Invoked twice around a real adb install -r; ordinary device discovery skips this test. */
@RunWith(AndroidJUnit4::class)
class UpgradeAcceptanceTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()

    @Test
    fun profileDraftPlacesCameraAndUnitsSurviveApkReplacement() {
        val stage = InstrumentationRegistry.getArguments().getString("upgradeStage")
        assumeTrue(stage == "seed" || stage == "verify")
        val app = compose.activity.application as WxSpotApplication
        val expected = app.getSharedPreferences("upgrade_acceptance", Context.MODE_PRIVATE)
        val vault = SessionVault(app, app.api.json)
        val drafts = DraftStore(app, app.api.json)
        val places = PlacesStore(app, app.api.json)
        lateinit var vm: MapViewModel
        compose.runOnUiThread { vm = ViewModelProvider(compose.activity)[MapViewModel::class.java] }
        if (stage == "seed") {
            compose.waitUntil(120_000) {
                vm.state.value.rasterState == "ready" && vm.state.value.session != null
            }
            val frame = vm.state.value.currentFrame!!
            val camera = vm.state.value.camera
            val draft =
                Draft(
                    context =
                        WeatherContext(
                            capturedAt = Instant.now().toString(),
                            camera = camera,
                            bounds = listOf(-81.0, 32.0, -79.0, 34.0),
                            layers = listOf(frame.layer(0.65)),
                        ),
                    elements =
                        listOf(
                            AnnotationElement(
                                tool = "arrow",
                                geometry =
                                    GeoGeometry.of(
                                        "LineString",
                                        listOf(listOf(-80.18, 33.02), listOf(-80.10, 33.10)),
                                    ),
                            )
                        ),
                    contentType = "analysis",
                    description = "Unpublished draft retained through a real APK update.",
                    title = "Upgrade acceptance",
                    topics = listOf("boundary"),
                )
            drafts.save(draft)
            val saved =
                listOf(
                    SavedPlace(name = "Home acceptance", lat = 33.02, lon = -80.18),
                    SavedPlace(name = "Away acceptance", lat = 35.22, lon = -97.44),
                )
            places.writePlaces(saved)
            places.writeCamera(camera)
            places.writeMetricUnits(true)
            val session = SessionVault(app, app.api.json).current!!
            assertNotNull(session.resumeKey)
            assertTrue(
                expected
                    .edit()
                    .putString("profile", digest(session.userId))
                    .putString("credential", digest(session.resumeKey!!))
                    .putString("token", digest(session.token))
                    .putString(
                        "draft",
                        digest(File(app.filesDir, "annotation-draft.json").readText()),
                    )
                    .putString("places", app.api.json.encodeToString(saved))
                    .putString("camera", app.api.json.encodeToString(camera))
                    .putInt("version", BuildConfig.VERSION_CODE)
                    .putString("certificate", certificateDigest(app))
                    .commit()
            )
        } else {
            assertEquals(
                "The new APK must increment versionCode",
                expected.getInt("version", -1) + 1,
                BuildConfig.VERSION_CODE,
            )
            assertEquals(expected.getString("certificate", null), certificateDigest(app))
            val session = vault.current!!
            assertEquals(expected.getString("profile", null), digest(session.userId))
            assertEquals(expected.getString("credential", null), digest(session.resumeKey!!))
            assertEquals(expected.getString("token", null), digest(session.token))
            assertEquals(
                expected.getString("draft", null),
                digest(File(app.filesDir, "annotation-draft.json").readText()),
            )
            assertEquals(drafts.read(), vm.state.value.draft)
            assertEquals(drafts.read()!!.elements, vm.state.value.editor.elements)
            assertEquals("resume", vm.state.value.sheet)
            assertEquals(
                expected.getString("places", null),
                app.api.json.encodeToString(places.readPlaces()),
            )
            assertEquals(places.readPlaces(), vm.state.value.savedPlaces)
            assertEquals(
                expected.getString("camera", null),
                app.api.json.encodeToString(places.readCamera()!!),
            )
            assertTrue(places.readMetricUnits() && vm.state.value.metricUnits)
            // Renew through the real API using the retained encrypted credential, without forms.
            val renewed = runBlocking { app.api.ensureDeviceProfile(rejectedToken = session.token) }
            assertEquals(session.userId, renewed.userId)
            assertEquals(session.resumeKey, renewed.resumeKey)
            val automation = InstrumentationRegistry.getInstrumentation().uiAutomation
            for (command in
                listOf(
                    "mkdir -p /sdcard/wxspot-acceptance",
                    "screencap -p /sdcard/wxspot-acceptance/19-upgraded-draft-resume.png",
                )) {
                ParcelFileDescriptor.AutoCloseInputStream(automation.executeShellCommand(command))
                    .use { it.readBytes() }
            }
        }
    }

    private fun digest(value: String): String =
        MessageDigest.getInstance("SHA-256").digest(value.toByteArray()).joinToString("") {
            "%02x".format(it.toInt() and 0xff)
        }

    @Suppress("DEPRECATION")
    private fun certificateDigest(context: Context): String {
        val bytes =
            context.packageManager
                .getPackageInfo(context.packageName, PackageManager.GET_SIGNING_CERTIFICATES)
                .signingInfo!!
                .apkContentsSigners
                .single()
                .toByteArray()
        return MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") {
            "%02x".format(it.toInt() and 0xff)
        }
    }
}
