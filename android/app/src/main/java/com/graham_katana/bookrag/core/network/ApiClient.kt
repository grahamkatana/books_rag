package com.graham_katana.bookrag.core.network

import com.graham_katana.bookrag.core.auth.Session
import java.io.IOException
import java.util.concurrent.TimeUnit
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.withContext
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.contentOrNull
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response

/** Everything the API can refuse with, already worded for the person reading it. */
sealed class ApiException(message: String) : Exception(message) {
    class SessionExpired : ApiException("Your session has expired. Please log in again.")
    class Network : ApiException("Can't reach the server. Check your connection and try again.")
    class NotFound(detail: String?) : ApiException(detail ?: "Not found.")
    class Http(val code: Int, detail: String?) : ApiException(
        // A 5xx body is for the server's log, not for the person: it can be a stack trace or a proxy's HTML.
        if (code >= 500 || detail == null) "Something went wrong on the server. Please try again." else detail
    )
}

/** One server-sent event: its name and its `data:` payload. */
data class SseEvent(val event: String, val data: String)

/**
 * The HTTP plumbing every feature shares: the address, the login header, JSON,
 * and turning a refusal into an [ApiException]. It knows nothing about chats or
 * documents; each feature's own API class says which paths it calls.
 *
 * The API issues one access token and no refresh token, so a 401 on a logged-in
 * call simply ends the [session] and the app returns to the login screen.
 */
class ApiClient(
    /** Asked on every call, so a server address changed on the login screen takes effect at once. */
    private val baseUrl: () -> String,
    private val session: Session,
    private val http: OkHttpClient = defaultHttp(),
) {
    private val base: String get() = baseUrl().trimEnd('/')
    val json = Json { ignoreUnknownKeys = true; explicitNulls = false }

    suspend inline fun <reified T> get(path: String): T = call("GET", path) { json.decodeFromString<T>(it) }

    suspend inline fun <reified T> post(path: String, body: RequestBody = EMPTY, authed: Boolean = true): T =
        call("POST", path, body, authed) { json.decodeFromString<T>(it) }

    suspend fun delete(path: String) = call("DELETE", path) { }

    inline fun <reified B> jsonBody(value: B): RequestBody = json.encodeToString(value).toRequestBody(JSON_TYPE)

    suspend fun <T> call(method: String, path: String, body: RequestBody? = null, authed: Boolean = true, parse: (String) -> T): T =
        withContext(Dispatchers.IO) {
            execute(method, path, body, authed).use { response ->
                if (!response.isSuccessful) throw failure(response, authed)
                parse(response.body?.string().orEmpty())
            }
        }

    /** A POST whose answer arrives as server-sent events, one emitted per event as it arrives. */
    fun events(path: String, body: RequestBody): Flow<SseEvent> = flow {
        execute("POST", path, body, authed = true).use { response ->
            if (!response.isSuccessful) throw failure(response, authed = true)
            val lines = response.body!!.source()
            var event = "message"
            val data = StringBuilder()
            while (true) {
                val line = try { lines.readUtf8Line() } catch (e: IOException) { throw ApiException.Network() } ?: break
                when {
                    line.isEmpty() -> {
                        if (data.isNotEmpty()) emit(SseEvent(event, data.toString()))
                        event = "message"
                        data.clear()
                    }
                    line.startsWith("event:") -> event = line.substring(6).trim()
                    line.startsWith("data:") -> data.append(line.substring(5).trim())
                }
            }
        }
    }.flowOn(Dispatchers.IO)

    private fun execute(method: String, path: String, body: RequestBody?, authed: Boolean): Response {
        val request = Request.Builder().url("$base$path").method(method, body)
        if (authed) request.header("Authorization", "Bearer ${session.token ?: throw ApiException.SessionExpired()}")
        return try {
            http.newCall(request.build()).execute()
        } catch (e: IOException) {
            throw ApiException.Network()
        }
    }

    private fun failure(response: Response, authed: Boolean): ApiException {
        val detail = messageOf(response)
        return when {
            // Flask-JWT answers 401 for a missing or expired token and 422 for one it cannot read at all.
            authed && response.code == 401 -> { session.end(); ApiException.SessionExpired() }
            response.code == 404 -> ApiException.NotFound(detail)
            else -> ApiException.Http(response.code, detail)
        }
    }

    /** The API's errors carry a `message`; Flask-JWT's own carry `msg`. */
    private fun messageOf(response: Response): String? = try {
        val body = json.parseToJsonElement(response.body!!.string()) as? JsonObject
        ((body?.get("message") ?: body?.get("msg")) as? JsonPrimitive)?.contentOrNull
    } catch (e: Exception) {
        null
    }

    companion object {
        val JSON_TYPE = "application/json".toMediaType()
        val EMPTY: RequestBody = ByteArray(0).toRequestBody(null)

        fun defaultHttp(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .writeTimeout(2, TimeUnit.MINUTES) // a document upload on a slow connection
            // An answer can take a while to start (retrieval, then the model) and then trickles in.
            .readTimeout(3, TimeUnit.MINUTES)
            .build()
    }
}
