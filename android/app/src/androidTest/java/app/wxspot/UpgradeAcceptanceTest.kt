package app.wxspot

import android.content.Context
import android.content.pm.PackageManager
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import java.security.MessageDigest
import kotlinx.coroutines.runBlocking
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assume.assumeTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

/** Runs before and after a same-key test APK replacement; production signing is separate. */
@RunWith(AndroidJUnit4::class)
class UpgradeAcceptanceTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()

    @Test
    fun testSigningAndGuestIdentitySurviveApkReplacement() {
        val stage = InstrumentationRegistry.getArguments().getString("upgradeStage")
        assumeTrue(stage == "seed" || stage == "verify")
        val app = compose.activity.application as WxSpotApplication
        val expected = app.getSharedPreferences("upgrade_acceptance", Context.MODE_PRIVATE)
        val applicationId = BuildConfig.APPLICATION_ID
        assertEquals("app.wxspot.beta", applicationId)
        val certificate = certificateDigest(app)
        val session = runBlocking { app.api.ensureDeviceProfile() }
        assertNotNull(session.resumeKey)

        if (stage == "seed") {
            check(
                expected
                    .edit()
                    .putString("applicationId", applicationId)
                    .putInt("version", BuildConfig.VERSION_CODE)
                    .putString("certificate", certificate)
                    .putString("profile", digest(session.userId))
                    .putString("credential", digest(session.resumeKey!!))
                    .putString("token", digest(session.token))
                    .commit()
            )
        } else {
            assertEquals(applicationId, expected.getString("applicationId", null))
            assertEquals(expected.getInt("version", -1) + 1, BuildConfig.VERSION_CODE)
            assertEquals(expected.getString("certificate", null), certificate)
            assertEquals(expected.getString("profile", null), digest(session.userId))
            assertEquals(expected.getString("credential", null), digest(session.resumeKey!!))
            val restored = runBlocking {
                app.api.ensureDeviceProfile(rejectedToken = session.token)
            }
            assertEquals(session.userId, restored.userId)
            assertEquals(session.resumeKey, restored.resumeKey)
        }
    }

    private fun digest(value: String): String =
        MessageDigest.getInstance("SHA-256").digest(value.toByteArray()).joinToString("") {
            "%02x".format(it.toInt() and 0xff)
        }

    @Suppress("DEPRECATION")
    private fun certificateDigest(context: Context): String {
        val signatures =
            context.packageManager
                .getPackageInfo(context.packageName, PackageManager.GET_SIGNING_CERTIFICATES)
                .signingInfo!!
                .apkContentsSigners
        return MessageDigest.getInstance("SHA-256")
            .digest(signatures.single().toByteArray())
            .joinToString("") { "%02x".format(it.toInt() and 0xff) }
    }
}
