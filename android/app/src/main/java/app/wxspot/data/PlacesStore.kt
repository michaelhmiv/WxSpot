package app.wxspot.data

import android.content.Context
import app.wxspot.domain.Camera
import app.wxspot.domain.SavedPlace
import kotlinx.serialization.json.Json

/** Device-local saved places and last camera, deliberately separate from profile credentials. */
class PlacesStore(
    context: Context,
    private val json: Json,
    preferencesName: String = PREFERENCES_NAME,
) {
    private val preferences =
        context.applicationContext.getSharedPreferences(preferencesName, Context.MODE_PRIVATE)

    fun readPlaces(): List<SavedPlace> =
        runCatching {
                json.decodeFromString<List<SavedPlace>>(preferences.getString(PLACES_KEY, "[]")!!)
            }
            .getOrDefault(emptyList())

    fun writePlaces(places: List<SavedPlace>) {
        require(places.size <= MAX_SAVED_PLACES)
        require(places.map { it.id }.distinct().size == places.size)
        require(
            places.all { it.name.isNotBlank() && it.lat in -90.0..90.0 && it.lon in -180.0..180.0 }
        )
        check(preferences.edit().putString(PLACES_KEY, json.encodeToString(places)).commit()) {
            "Unable to save places on this device."
        }
    }

    fun readCamera(): Camera? =
        preferences.getString(CAMERA_KEY, null)?.let { value ->
            runCatching { json.decodeFromString<Camera>(value) }.getOrNull()
        }

    fun writeCamera(camera: Camera) {
        preferences.edit().putString(CAMERA_KEY, json.encodeToString(camera)).apply()
    }

    fun clearCamera() {
        preferences.edit().remove(CAMERA_KEY).commit()
    }

    fun readMetricUnits(): Boolean = preferences.getBoolean(METRIC_UNITS_KEY, false)

    fun writeMetricUnits(enabled: Boolean) {
        check(preferences.edit().putBoolean(METRIC_UNITS_KEY, enabled).commit()) {
            "Unable to save unit preferences on this device."
        }
    }

    private companion object {
        const val PREFERENCES_NAME = "wxspot_places"
        const val PLACES_KEY = "saved_places"
        const val CAMERA_KEY = "last_camera"
        const val METRIC_UNITS_KEY = "metric_units"
        const val MAX_SAVED_PLACES = 100
    }
}
