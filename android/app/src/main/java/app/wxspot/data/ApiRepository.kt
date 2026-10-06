package app.wxspot.data

import app.wxspot.domain.CommentsResponse
import app.wxspot.domain.FramesResponse
import app.wxspot.domain.PostCreate
import app.wxspot.domain.PostsResponse
import app.wxspot.domain.WeatherPost
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
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
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody

class ApiException(val status: Int, message: String) : IOException(message)

class ApiRepository(val baseUrl: String, val vault: SessionStore, val json: Json) {
    val client =
        OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(90, TimeUnit.SECONDS)
            .callTimeout(100, TimeUnit.SECONDS)
            .build()

    fun url(path: String) = if (path.startsWith("http")) path else baseUrl.trimEnd('/') + path

    suspend fun request(path: String, method: String = "GET", body: RequestBody? = null): String =
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
            vault.current?.let { builder.header("Authorization", "Bearer " + it.token) }
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
                            if (response.code == 401) "Sign in to continue."
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
            val me = json.parseToJsonElement(request("/account")).jsonObject
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
