package com.graham_katana.bookrag.core.network

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

/**
 * Which server the app talks to: the one it was built for, unless a different
 * address was entered on the login screen (for someone running their own Book RAG
 * server). It can only be changed while logged out, so a login token is never
 * sent to a server other than the one that issued it.
 */
class ServerSettings(context: Context, val defaultUrl: String, private val allowHttp: Boolean) {
    private val prefs = context.getSharedPreferences("server", Context.MODE_PRIVATE)
    private val _url = MutableStateFlow(prefs.getString(KEY, null) ?: defaultUrl)
    val url: StateFlow<String> = _url.asStateFlow()

    val isCustom: Boolean get() = _url.value != defaultUrl

    /** Saves [input] as the server address. False, and nothing changes, if it is not a usable address. */
    fun set(input: String): Boolean {
        val address = normalise(input, allowHttp) ?: return false
        prefs.edit().putString(KEY, address).apply()
        _url.value = address
        return true
    }

    fun reset() {
        prefs.edit().remove(KEY).apply()
        _url.value = defaultUrl
    }

    companion object {
        private const val KEY = "base_url"

        /**
         * "books.example.org/" -> "https://books.example.org". Null when it is not an address
         * the app can use. Plain http is refused unless [allowHttp] (debug builds only): a
         * password must not cross the network unencrypted, and a release build cannot send it anyway.
         */
        fun normalise(input: String, allowHttp: Boolean): String? {
            val typed = input.trim()
            if (typed.isEmpty() || typed.any(Char::isWhitespace)) return null
            val parsed = (if ("://" in typed) typed else "https://$typed").toHttpUrlOrNull() ?: return null
            if (parsed.scheme != "https" && !(allowHttp && parsed.scheme == "http")) return null
            if (parsed.username.isNotEmpty() || parsed.query != null || parsed.fragment != null) return null
            val port = if (parsed.port == okhttp3.HttpUrl.defaultPort(parsed.scheme)) "" else ":${parsed.port}"
            return "${parsed.scheme}://${parsed.host}$port${parsed.encodedPath.trimEnd('/')}"
        }
    }
}
