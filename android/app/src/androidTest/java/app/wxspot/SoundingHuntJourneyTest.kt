package app.wxspot

import android.content.ContentValues
import android.os.Build
import android.os.SystemClock
import android.provider.MediaStore
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.click
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithContentDescription
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.performTouchInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.UiDevice
import app.wxspot.data.ApiException
import app.wxspot.domain.HuntChallenge
import java.io.File
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SoundingHuntJourneyTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()

    private fun snapshot(name: String) {
        val context = compose.activity.applicationContext
        val temporary = File(context.cacheDir, "$name.png")
        assertTrue(
            UiDevice.getInstance(InstrumentationRegistry.getInstrumentation())
                .takeScreenshot(temporary)
        )
        val values =
            ContentValues().apply {
                put(MediaStore.MediaColumns.DISPLAY_NAME, "$name.png")
                put(MediaStore.MediaColumns.MIME_TYPE, "image/png")
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                    put(MediaStore.MediaColumns.RELATIVE_PATH, "Pictures/WXspotAcceptance")
                }
            }
        val uri =
            requireNotNull(
                context.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values)
            ) {
                "Cannot persist visual acceptance screenshot: $name"
            }
        requireNotNull(context.contentResolver.openOutputStream(uri)).use { output ->
            temporary.inputStream().use { input -> input.copyTo(output) }
        }
        assertTrue(temporary.delete())
    }

    @Test
    fun dailyGuessRevealLeaderboardPersistenceAndPracticeIsolation() {
        val app = compose.activity.application as WxSpotApplication
        val api = app.api
        var readyChallenge: HuntChallenge? = null
        compose.waitUntil(10 * 60 * 1000L) {
            readyChallenge = runCatching { runBlocking { api.huntToday() } }.getOrNull()
            if (readyChallenge == null) SystemClock.sleep(1000)
            readyChallenge != null
        }
        val daily = requireNotNull(readyChallenge)
        compose.onNodeWithText("WXspot").assertIsDisplayed()
        compose.waitUntil(60_000) {
            compose
                .onAllNodesWithText(
                    if (daily.completed) "View today’s result" else "Play today’s hunt"
                )
                .fetchSemanticsNodes()
                .isNotEmpty()
        }
        snapshot("01-home")
        if (daily.completed) {
            compose.onNodeWithText("View today’s result").performClick()
            compose.onNodeWithText("SOUNDING REVEALED").assertIsDisplayed()
        } else {
            compose.onNodeWithText("Play today’s hunt").performClick()
            compose.onNodeWithText("UTC", substring = true).assertIsDisplayed()
            snapshot("02-sounding")
            compose.onNodeWithText("Choose location").performClick()
            val mapDescription =
                "Map of the contiguous United States. Tap to place or move your guess."
            compose.waitUntil(60_000) {
                compose
                    .onAllNodesWithContentDescription(mapDescription)
                    .fetchSemanticsNodes()
                    .isNotEmpty()
            }
            snapshot("03-guess-map")
            compose.onNodeWithContentDescription(mapDescription).performTouchInput {
                click(Offset(width * 0.52f, height * 0.48f))
            }
            compose.waitUntil(15_000) {
                runCatching { compose.onNodeWithText("Confirm final guess").assertIsEnabled() }
                    .isSuccess
            }
            compose.onNodeWithText("Confirm final guess").performClick()
            compose.onNodeWithText("Confirm guess").performClick()
            compose.waitUntil(60_000) {
                compose.onAllNodesWithText("SOUNDING REVEALED").fetchSemanticsNodes().isNotEmpty()
            }
            compose.onNodeWithText("SOUNDING REVEALED").assertIsDisplayed()
            val duplicate =
                runCatching { runBlocking { api.huntDailyGuess(daily.challengeDay, 39.0, -98.0) } }
                    .exceptionOrNull()
            assertEquals(409, (duplicate as? ApiException)?.status)
        }

        snapshot("04-result")
        compose.onNodeWithText("Leaderboard").performClick()
        compose.onNodeWithText("DAILY LEADERBOARD").assertIsDisplayed()
        snapshot("05-rankings")
        compose.activityRule.scenario.recreate()
        compose.onNodeWithText("Home").performClick()
        compose.waitUntil(60_000) {
            compose.onAllNodesWithText("View today’s result").fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText("View today’s result").performClick()
        compose.onNodeWithText("SOUNDING REVEALED").assertIsDisplayed()

        val rankedCountBeforePractice = runBlocking { api.huntProfile().dailyChallengesPlayed }
        compose.onNodeWithText("Home").performClick()
        compose.onNodeWithText("Play").performClick()
        snapshot("06-play")
        compose.onNodeWithText("Start practice  →").performClick()
        compose.waitUntil(60_000) {
            compose.onAllNodesWithText("PRACTICE").fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText("PRACTICE").assertIsDisplayed()
        snapshot("07-practice")
        compose.onNodeWithText("UTC", substring = true).assertIsDisplayed()
        compose.onNodeWithText("Choose location").performClick()
        compose.onNodeWithText("Latitude").performTextInput("39.0")
        compose.onNodeWithText("Longitude").performTextInput("-98.0")
        compose.onNodeWithText("Confirm final guess").performClick()
        compose.onNodeWithText("Confirm guess").performClick()
        compose.waitUntil(60_000) {
            compose.onAllNodesWithText("UNRANKED PRACTICE").fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText("UNRANKED PRACTICE").assertIsDisplayed()
        assertEquals(
            rankedCountBeforePractice,
            runBlocking { api.huntProfile().dailyChallengesPlayed },
        )
    }
}
