package app.wxspot

import android.os.SystemClock
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertIsEnabled
import androidx.compose.ui.test.click
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.compose.ui.test.onAllNodesWithText
import androidx.compose.ui.test.onNodeWithContentDescription
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import androidx.compose.ui.test.performTextInput
import androidx.compose.ui.test.performTouchInput
import androidx.test.ext.junit.runners.AndroidJUnit4
import app.wxspot.data.ApiException
import app.wxspot.domain.HuntChallenge
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class SoundingHuntJourneyTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()

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
        compose.waitUntil(60_000) {
            compose
                .onAllNodesWithText(
                    if (daily.completed) "View today’s result" else "Play today’s hunt"
                )
                .fetchSemanticsNodes()
                .isNotEmpty()
        }
        if (daily.completed) {
            compose.onNodeWithText("View today’s result").performClick()
            compose.onNodeWithText("SOUNDING REVEALED").assertIsDisplayed()
        } else {
            compose.onNodeWithText("Play today’s hunt").performClick()
            compose.onNodeWithText("UTC", substring = true).assertIsDisplayed()
            compose.onNodeWithText("Choose location").performClick()
            compose
                .onNodeWithContentDescription(
                    "Map of the contiguous United States. Tap to place or move your guess."
                )
                .performTouchInput { click(Offset(width * 0.52f, height * 0.48f)) }
            compose.onNodeWithText("Confirm final guess").assertIsEnabled().performClick()
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

        compose.onNodeWithText("Leaderboard").performClick()
        compose.onNodeWithText("Rankings").assertIsDisplayed()
        compose.activityRule.scenario.recreate()
        compose.waitUntil(60_000) {
            compose.onAllNodesWithText("View today’s result").fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText("View today’s result").performClick()
        compose.onNodeWithText("SOUNDING REVEALED").assertIsDisplayed()

        val rankedCountBeforePractice = runBlocking { api.huntProfile().dailyChallengesPlayed }
        compose.onNodeWithText("Home").performClick()
        compose.onNodeWithText("Play").performClick()
        compose.onNodeWithText("Start practice  →").performClick()
        compose.onNodeWithText("PRACTICE").assertIsDisplayed()
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
