package app.wxspot.domain

import java.time.Instant
import kotlinx.serialization.json.*
import org.junit.Assert.*
import org.junit.Test

class AlertLifetimeTest {
    private val now = Instant.parse("2026-10-06T18:00:00Z")

    @Test
    fun cachedCollectionExpiresAtDeadlineWithoutAnotherNetworkResponse() {
        val raw =
            """{"type":"FeatureCollection","features":[{"type":"Feature","id":"active","geometry":null,"properties":{"expires":"2026-10-06T19:00:00Z"}},{"type":"Feature","id":"expired","geometry":null,"properties":{"expires":"2026-10-06T18:00:00Z"}}]}"""
        val active = AlertLifetime.activeCollection(raw, now)
        assertEquals(
            "active",
            Json.parseToJsonElement(active)
                .jsonObject["features"]!!
                .jsonArray
                .single()
                .jsonObject["id"]!!
                .jsonPrimitive
                .content,
        )
        assertTrue(
            Json.parseToJsonElement(AlertLifetime.activeCollection(active, now.plusSeconds(3600)))
                .jsonObject["features"]!!
                .jsonArray
                .isEmpty()
        )
    }

    @Test
    fun invalidOrUnknownExpiryCannotKeepOfficialGeometryVisible() {
        listOf("""{}""", """{"expires":null}""", """{"expires":"not-a-time"}""").forEach {
            assertFalse(AlertLifetime.isActive(Json.parseToJsonElement(it).jsonObject, now))
        }
        assertTrue(
            AlertLifetime.isActive(
                Json.parseToJsonElement("""{"expires":"2026-10-06T15:01:00-03:00"}""").jsonObject,
                now,
            )
        )
    }
}
