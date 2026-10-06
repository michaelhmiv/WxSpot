package app.wxspot.data

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
}
