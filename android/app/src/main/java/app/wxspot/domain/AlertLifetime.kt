package app.wxspot.domain

import java.time.Instant
import java.time.OffsetDateTime
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonPrimitive

/** Cached official geometry must stop displaying even when its next fetch fails. */
object AlertLifetime {
    fun isActive(properties: JsonObject, now: Instant): Boolean =
        runCatching {
                properties["expires"]
                    ?.jsonPrimitive
                    ?.contentOrNull
                    ?.let { OffsetDateTime.parse(it).toInstant() }
                    ?.isAfter(now) ?: false
            }
            .getOrDefault(false)

    fun activeCollection(collection: String, now: Instant): String {
        val source = Json.parseToJsonElement(collection) as JsonObject
        val features = source["features"] as? JsonArray ?: JsonArray(emptyList())
        val active =
            features.filter { feature ->
                val properties = (feature as? JsonObject)?.get("properties") as? JsonObject
                properties != null && isActive(properties, now)
            }
        return JsonObject(source + ("features" to JsonArray(active))).toString()
    }
}
