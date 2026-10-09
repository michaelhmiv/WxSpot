package app.wxspot.data

import app.wxspot.domain.CommentsResponse
import app.wxspot.domain.FramesResponse
import app.wxspot.domain.HuntChallenge
import app.wxspot.domain.HuntLeaderboard
import app.wxspot.domain.HuntPractice
import app.wxspot.domain.HuntProfile
import app.wxspot.domain.HuntResult
import app.wxspot.domain.LocationSearchResponse
import app.wxspot.domain.PostCreate
import app.wxspot.domain.PostsResponse
import app.wxspot.domain.RadarFrame
import app.wxspot.domain.RadarStationResponse
import app.wxspot.domain.WeatherCatalogResponse
import app.wxspot.domain.WeatherFramesResponse
import app.wxspot.domain.WeatherPost
import app.wxspot.domain.WeatherPreparation
import app.wxspot.domain.WeatherSelection
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import okhttp3.FormBody
import okhttp3.HttpUrl.Companion.toHttpUrl
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody

class ApiException(val status: Int, message: String) : IOException(message)

class ApiRepository(val baseUrl: String, val vault: SessionStore, val json: Json) {
    private val identityMutex = Mutex()
    private val origin = baseUrl.toHttpUrl()
    val client =
        OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(90, TimeUnit.SECONDS)
            .callTimeout(100, TimeUnit.SECONDS)
            .build()

    fun url(path: String) = if (path.startsWith("http")) path else baseUrl.trimEnd('/') + path

    private fun sameOrigin(address: okhttp3.HttpUrl) =
        address.scheme == origin.scheme &&
            address.host == origin.host &&
            address.port == origin.port

    suspend fun locationWeather(point: List<Double>): app.wxspot.domain.LocationWeatherResponse =
        json.decodeFromString(
            request("/weather/locations/forecast?lat=${point[1]}&lon=${point[0]}")
        )

    suspend fun ensureDeviceProfile(rejectedToken: String? = null): Session =
        identityMutex.withLock {
            val existing = vault.current
            if (existing != null && (rejectedToken == null || existing.token != rejectedToken)) {
                return@withLock existing
            }
            val result =
                json
                    .parseToJsonElement(
                        requestOnce(
                            "/auth/guest",
                            "POST",
                            body(
                                buildJsonObject {
                                    existing?.resumeKey?.let { put("resume_key", it) }
                                }
                            ),
                        )
                    )
                    .jsonObject
            Session(
                    result.getValue("access_token").jsonPrimitive.content,
                    result.getValue("user_id").jsonPrimitive.content,
                    result.getValue("display_name").jsonPrimitive.content,
                    result.getValue("resume_key").jsonPrimitive.content,
                )
                .also(vault::save)
        }

    suspend fun request(path: String, method: String = "GET", body: RequestBody? = null): String {
        val address = url(path).toHttpUrl()
        val community =
            sameOrigin(address) &&
                !address.encodedPath.startsWith("/auth/") &&
                !address.encodedPath.startsWith("/weather/") &&
                address.encodedPath !in listOf("/health", "/openapi.json", "/docs")
        if (community) ensureDeviceProfile()
        val sentToken = vault.current?.token
        return try {
            requestOnce(path, method, body)
        } catch (error: ApiException) {
            if (!community || error.status != 401) throw error
            ensureDeviceProfile(rejectedToken = sentToken)
            requestOnce(path, method, body)
        }
    }

    private suspend fun requestOnce(
        path: String,
        method: String = "GET",
        body: RequestBody? = null,
    ): String =
        withContext(Dispatchers.IO) {
            val builder =
                Request.Builder()
                    .url(url(path))
                    .header("User-Agent", "WxSpot/0.1 (github.com/michaelhmiv/WxSpot)")
                    .method(
                        method,
                        if (method in listOf("POST", "PUT", "PATCH") && body == null) {
                            "".toRequestBody(null)
                        } else body,
                    )
            if (sameOrigin(builder.build().url)) {
                vault.current?.let { builder.header("Authorization", "Bearer " + it.token) }
            }
            client.newCall(builder.build()).execute().use { response ->
                val result = response.body?.string().orEmpty()
                if (!response.isSuccessful) {
                    val detail =
                        runCatching { json.parseToJsonElement(result).jsonObject["detail"] }
                            .getOrNull()
                    val message =
                        when (detail) {
                            is JsonPrimitive -> detail.contentOrNull.orEmpty()
                            is JsonObject ->
                                detail["message"]?.jsonPrimitive?.contentOrNull.orEmpty()
                            else -> ""
                        }.ifBlank {
                            if (response.code == 401) "Could not connect your profile. Try again."
                            else "Could not complete the request (${response.code})."
                        }
                    throw ApiException(response.code, message)
                }
                result
            }
        }

    fun body(value: JsonElement) = value.toString().toRequestBody("application/json".toMediaType())

    fun body(value: String) = value.toRequestBody("application/json".toMediaType())

    suspend fun frames(site: String, product: String): FramesResponse =
        json.decodeFromString(request("/weather/radar/frames?site=$site&product=$product"))

    suspend fun weatherCatalog(): WeatherCatalogResponse =
        json.decodeFromString(request("/weather/catalog"))

    suspend fun sounding(parameters: Map<String, String>): app.wxspot.domain.SoundingResponse {
        val url = origin.resolve("/weather/soundings")!!.newBuilder()
        parameters.forEach { (key, value) -> url.addQueryParameter(key, value) }
        return json.decodeFromString(request(url.build().toString()))
    }

    suspend fun soundingStations(point: List<Double>): app.wxspot.domain.SoundingStations {
        val url =
            origin
                .resolve("/weather/soundings/stations")!!
                .newBuilder()
                .addQueryParameter("lon", point[0].toString())
                .addQueryParameter("lat", point[1].toString())
                .build()
        return json.decodeFromString(request(url.toString()))
    }

    suspend fun huntToday(): HuntChallenge =
        json.decodeFromString(request("/game/sounding-hunt/today"))

    suspend fun huntDailyChallenge(challengeDay: String): HuntChallenge =
        json.decodeFromString(request("/game/sounding-hunt/daily/$challengeDay"))

    suspend fun huntDailyGuess(
        challengeDay: String,
        latitude: Double,
        longitude: Double,
    ): HuntResult =
        json.decodeFromString(
            request(
                "/game/sounding-hunt/daily/$challengeDay/guess",
                "POST",
                coordinatesBody(latitude, longitude),
            )
        )

    suspend fun huntDailyResult(challengeDay: String): HuntResult =
        json.decodeFromString(
            request("/game/sounding-hunt/daily/$challengeDay/result")
        )

    suspend fun huntLeaderboard(challengeDay: String): HuntLeaderboard =
        json.decodeFromString(
            request("/game/sounding-hunt/leaderboard/$challengeDay")
        )

    suspend fun huntProfile(): HuntProfile =
        json.decodeFromString(request("/game/sounding-hunt/profile"))

    suspend fun huntPractice(): HuntPractice =
        json.decodeFromString(
            request("/game/sounding-hunt/practice", "POST", body(buildJsonObject {}))
        )

    suspend fun huntPracticeGuess(
        practiceId: String,
        latitude: Double,
        longitude: Double,
    ): HuntResult =
        json.decodeFromString(
            request(
                "/game/sounding-hunt/practice/$practiceId/guess",
                "POST",
                coordinatesBody(latitude, longitude),
            )
        )

    suspend fun huntPracticeResult(practiceId: String): HuntResult =
        json.decodeFromString(
            request("/game/sounding-hunt/practice/$practiceId/result")
        )

    private fun coordinatesBody(latitude: Double, longitude: Double) =
        body(
            buildJsonObject {
                put("latitude", latitude)
                put("longitude", longitude)
            }
        )

    suspend fun prepareWeather(frame: RadarFrame): WeatherPreparation {
        val endpoint =
            origin
                .resolve("/weather/prepare")!!
                .newBuilder()
                .addQueryParameter("source_type", frame.sourceType)
                .addQueryParameter("source_id", frame.provider)
                .addQueryParameter("frame_id", frame.id)
                .build()
        return json.decodeFromString(request(endpoint.toString()))
    }

    suspend fun searchLocations(
        query: String,
        latitude: Double? = null,
        longitude: Double? = null,
    ): LocationSearchResponse {
        val endpoint =
            origin
                .resolve("/weather/locations/search")!!
                .newBuilder()
                .addQueryParameter("q", query)
                .apply {
                    latitude?.let { addQueryParameter("lat", it.toString()) }
                    longitude?.let { addQueryParameter("lon", it.toString()) }
                }
                .build()
        return json.decodeFromString(request(endpoint.toString()))
    }

    suspend fun nearbyRadarStations(latitude: Double, longitude: Double): RadarStationResponse {
        val endpoint =
            origin
                .resolve("/weather/radar/stations/nearby")!!
                .newBuilder()
                .addQueryParameter("lat", latitude.toString())
                .addQueryParameter("lon", longitude.toString())
                .build()
        return json.decodeFromString(request(endpoint.toString()))
    }

    suspend fun weatherFrames(selection: WeatherSelection): WeatherFramesResponse {
        val endpoint =
            origin
                .resolve("/weather/frames")!!
                .newBuilder()
                .addQueryParameter("source_type", selection.sourceType)
                .addQueryParameter("source_id", selection.sourceId)
                .addQueryParameter("product", selection.productId)
                .apply {
                    selection.site?.let { addQueryParameter("site", it) }
                    selection.domain?.let { addQueryParameter("domain", it) }
                    selection.elevation?.let { addQueryParameter("elevation", it.toString()) }
                    selection.model?.let { addQueryParameter("model", it) }
                    selection.runTime?.let { addQueryParameter("run_time", it) }
                    selection.forecastHour?.let {
                        addQueryParameter("forecast_hour", it.toString())
                    }
                    selection.verticalLevel?.let { addQueryParameter("vertical_level", it) }
                    selection.channel?.let { addQueryParameter("channel", it) }
                }
                .build()
        val response = json.decodeFromString<WeatherFramesResponse>(request(endpoint.toString()))
        return response.copy(
            frames =
                response.frames.map { frame ->
                    frame.copy(
                        render =
                            frame.render?.copy(
                                urlTemplate = absoluteWeatherUrl(frame.render.urlTemplate),
                                imageUrl = absoluteWeatherUrl(frame.render.imageUrl),
                            ),
                        legendUrl = absoluteWeatherUrl(frame.legendUrl),
                    )
                }
        )
    }

    private fun absoluteWeatherUrl(address: String?): String? {
        if (address == null || address.startsWith("http://") || address.startsWith("https://"))
            return address
        val base = origin.toString().trimEnd('/')
        return base + (if (address.startsWith("/")) address else "/$address")
    }

    suspend fun posts(query: String): PostsResponse =
        json.decodeFromString(request("/posts?$query"))

    suspend fun post(id: String): WeatherPost = json.decodeFromString(request("/posts/$id"))

    suspend fun publish(value: PostCreate): WeatherPost =
        json.decodeFromString(request("/posts", "POST", body(json.encodeToString(value))))

    suspend fun comments(id: String, cursor: String? = null): CommentsResponse =
        json.decodeFromString(
            request("/posts/$id/comments" + if (cursor != null) "?cursor=$cursor" else "")
        )

    suspend fun alerts(): JsonObject =
        json.parseToJsonElement(request("/weather/alerts")).jsonObject

    suspend fun signIn(email: String, password: String, name: String?) {
        if (name != null) {
            request(
                "/auth/register",
                "POST",
                body(
                    buildJsonObject {
                        put("email", email.trim())
                        put("password", password)
                        put("display_name", name.trim())
                    }
                ),
            )
        }
        val login =
            json
                .parseToJsonElement(
                    request(
                        "/auth/login",
                        "POST",
                        FormBody.Builder()
                            .add("username", email.trim())
                            .add("password", password)
                            .build(),
                    )
                )
                .jsonObject
        val token = login.getValue("access_token").jsonPrimitive.content
        vault.save(Session(token, "", name.orEmpty()))
        try {
            val me = json.parseToJsonElement(requestOnce("/account")).jsonObject
            vault.save(
                Session(
                    token,
                    me.getValue("id").jsonPrimitive.content,
                    me.getValue("display_name").jsonPrimitive.content,
                )
            )
        } catch (error: Exception) {
            vault.save(null)
            throw error
        }
    }

    suspend fun signOut() {
        request("/auth/logout", "POST")
        vault.save(null)
    }

    suspend fun upload(data: ByteArray): String {
        require(data.size <= 5 * 1024 * 1024) { "Choose a photo smaller than 5 MB." }
        val multipart =
            MultipartBody.Builder()
                .setType(MultipartBody.FORM)
                .addFormDataPart(
                    "file",
                    "photo",
                    data.toRequestBody("application/octet-stream".toMediaType()),
                )
                .build()
        return json
            .parseToJsonElement(request("/media", "POST", multipart))
            .jsonObject
            .getValue("id")
            .jsonPrimitive
            .content
    }
}
