package app.wxspot.data

import app.wxspot.domain.WeatherSelection
import java.io.File
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.test.runTest
import kotlinx.serialization.json.Json
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test

class ApiRepositoryTest {
    private val server = MockWebServer()
    private val vault =
        object : SessionStore {
            override var current: Session? = null

            override fun save(value: Session?) {
                current = value
            }
        }
    private lateinit var api: ApiRepository

    @Before
    fun setup() {
        server.start()
        api = ApiRepository(server.url("/").toString(), vault, Json { ignoreUnknownKeys = true })
    }

    @After
    fun stop() {
        server.shutdown()
    }

    private fun respond(value: String, status: Int = 200) {
        server.enqueue(MockResponse().setResponseCode(status).setBody(value))
    }

    @Test
    fun anonymousBrowseDoesNotSendCredentials() = runTest {
        respond("{\"state\":\"no_data\",\"frames\":[]}")
        assertEquals("no_data", api.frames("KCLX", "reflectivity").state)
        assertNull(server.takeRequest().getHeader("Authorization"))
    }

    @Test
    fun genericWeatherFramesDecodeFromTheSharedContractFixture() = runTest {
        val contracts = File(System.getProperty("wxspot.contractsDir"))
        val fixture = contracts.resolve("weather-frames-response-v1.json").readText()
        respond(fixture)
        val response =
            api.weatherFrames(
                WeatherSelection(
                    sourceType = "radar",
                    sourceId = "nws-ridge2",
                    productId = "reflectivity",
                    site = "KCLX",
                )
            )
        assertEquals("ready", response.state)
        assertEquals(
            "radar:nws-ridge2:KCLX:reflectivity:2026-10-06T15:00:00.000Z",
            response.frames.single().id,
        )
        assertEquals("xyz", response.frames.single().render?.kind)
        assertEquals("dBZ", response.frames.single().units)
        val request = server.takeRequest()
        assertTrue(request.path.orEmpty().startsWith("/weather/frames?"))
        assertTrue(request.path.orEmpty().contains("source_id=nws-ridge2"))
        assertTrue(request.path.orEmpty().contains("site=KCLX"))
        assertNull(request.getHeader("Authorization"))
    }

    @Test
    fun registrationUsesLibraryLoginThenVerifiedAccountIdentity() = runTest {
        respond("{}", 201)
        respond("{\"access_token\":\"opaque-session\"}")
        respond("{\"id\":\"user-uuid\",\"display_name\":\"Display\"}")
        api.signIn(" email@example.com ", "long passphrase", "Display")
        assertEquals("/auth/register", server.takeRequest().path)
        val login = server.takeRequest()
        assertEquals("/auth/login", login.path)
        assertTrue(login.body.readUtf8().contains("username=email%40example.com"))
        assertEquals("Bearer opaque-session", server.takeRequest().getHeader("Authorization"))
        assertEquals(Session("opaque-session", "user-uuid", "Display"), vault.current)
    }

    @Test
    fun failedIdentityLookupClearsPartialSession() = runTest {
        respond("{\"access_token\":\"opaque\"}")
        respond("{\"detail\":\"Invalid session\"}", 401)
        val failure =
            runCatching { api.signIn("e@example.com", "passphrase", null) }.exceptionOrNull()
        assertEquals(401, (failure as ApiException).status)
        assertNull(vault.current)
    }

    @Test
    fun quotaAndWeatherFailurePreserveUsefulMessages() = runTest {
        vault.save(Session("opaque", "id", "Name"))
        respond("{\"detail\":{\"state\":\"no_data\",\"message\":\"Scan expired\"}}", 503)
        val error = runCatching { api.request("/posts", "POST") }.exceptionOrNull() as ApiException
        assertEquals(503, error.status)
        assertEquals("Scan expired", error.message)
    }

    @Test
    fun signOutRevokesBeforeRemovingDeviceSession() = runTest {
        vault.save(Session("opaque", "id", "Name"))
        respond("", 204)
        api.signOut()
        assertEquals("Bearer opaque", server.takeRequest().getHeader("Authorization"))
        assertNull(vault.current)
    }

    private fun guestReply(token: String = "device-token", name: String = "Weather explorer") =
        """{"access_token":"$token","resume_key":"saved-device-key","user_id":"device-user","display_name":"$name"}"""

    @Test
    fun communityFeaturesCreateProfileWithoutRegistration() = runTest {
        respond(guestReply(), 201)
        respond("[]")
        assertEquals("[]", api.request("/notifications"))
        val create = server.takeRequest()
        assertEquals("/auth/guest", create.path)
        assertEquals("{}", create.body.readUtf8())
        assertEquals("Bearer device-token", server.takeRequest().getHeader("Authorization"))
        assertEquals(
            Session("device-token", "device-user", "Weather explorer", "saved-device-key"),
            vault.current,
        )
    }

    @Test
    fun expiredSessionResumesSameProfileAndRetriesAction() = runTest {
        vault.save(Session("expired", "device-user", "Saved name", "saved-device-key"))
        respond("{\"detail\":\"Unauthorized\"}", 401)
        respond(guestReply("renewed", "Saved name"))
        respond("{}")
        assertEquals("{}", api.request("/account"))
        assertEquals("Bearer expired", server.takeRequest().getHeader("Authorization"))
        val resume = server.takeRequest()
        assertEquals("/auth/guest", resume.path)
        assertTrue(resume.body.readUtf8().contains("saved-device-key"))
        assertEquals("Bearer renewed", server.takeRequest().getHeader("Authorization"))
        assertEquals("device-user", vault.current?.userId)
        assertEquals("saved-device-key", vault.current?.resumeKey)
    }

    @Test
    fun concurrentActionsShareOneDeviceProfile() = runTest {
        respond(guestReply(), 201)
        repeat(3) { respond("[]") }
        val responses = (1..3).map { async { api.request("/notifications") } }.awaitAll()
        assertEquals(listOf("[]", "[]", "[]"), responses)
        assertEquals("/auth/guest", server.takeRequest().path)
        repeat(3) {
            val action = server.takeRequest()
            assertEquals("/notifications", action.path)
            assertEquals("Bearer device-token", action.getHeader("Authorization"))
        }
        assertEquals(4, server.requestCount)
    }

    @Test
    fun unavailableResumeDoesNotDiscardOwnershipOrCreateReplacementProfile() = runTest {
        val saved = Session("expired", "device-user", "Saved name", "saved-device-key")
        vault.save(saved)
        respond("{\"detail\":\"Unauthorized\"}", 401)
        respond("{\"detail\":\"Could not restore this device profile\"}", 401)
        val error = runCatching { api.request("/account") }.exceptionOrNull() as ApiException
        assertEquals(401, error.status)
        assertEquals(saved, vault.current)
        assertEquals(2, server.requestCount)
    }

    @Test
    fun cachedProfileNeedsNoNewRegistration() = runTest {
        vault.save(Session("saved", "device-user", "Saved name", "saved-device-key"))
        respond("[]")
        api.request("/notifications")
        assertEquals("/notifications", server.takeRequest().path)
        assertEquals(1, server.requestCount)
    }

    @Test
    fun repeatedAuthorizationFailureStopsAfterOneRenewal() = runTest {
        vault.save(Session("expired", "device-user", "Saved name", "saved-device-key"))
        respond("{\"detail\":\"Unauthorized\"}", 401)
        respond(guestReply("renewed"))
        respond("{\"detail\":\"Unauthorized\"}", 401)
        assertEquals(
            401,
            (runCatching { api.request("/account") }.exceptionOrNull() as ApiException).status,
        )
        assertEquals(3, server.requestCount)
    }

    @Test
    fun externalHostReceivesNoDeviceCredentials() = runTest {
        vault.save(Session("saved", "device-user", "Saved name", "saved-device-key"))
        val external = MockWebServer()
        external.start()
        try {
            external.enqueue(MockResponse().setBody("{}"))
            api.request(external.url("/weather.png").toString())
            assertNull(external.takeRequest().getHeader("Authorization"))
            assertEquals(0, server.requestCount)
        } finally {
            external.shutdown()
        }
    }
}
