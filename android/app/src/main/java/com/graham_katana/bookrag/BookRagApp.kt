package com.graham_katana.bookrag

import android.app.Application
import com.graham_katana.bookrag.core.auth.KeystoreSecretStore
import com.graham_katana.bookrag.core.auth.Session
import com.graham_katana.bookrag.core.network.ApiClient
import com.graham_katana.bookrag.core.network.ServerSettings
import com.graham_katana.bookrag.feature.auth.AuthApi
import com.graham_katana.bookrag.feature.auth.HttpAuthApi
import com.graham_katana.bookrag.feature.chat.ChatApi
import com.graham_katana.bookrag.feature.chat.HttpChatApi
import com.graham_katana.bookrag.feature.library.HttpLibraryApi
import com.graham_katana.bookrag.feature.library.LibraryApi
import com.graham_katana.bookrag.feature.verify.HttpVerifyApi
import com.graham_katana.bookrag.feature.verify.VerifyApi

/**
 * Everything that lives as long as the app, built once and by hand. Four small
 * objects do not need a dependency-injection library; if this list grows past
 * what fits on a screen, that is the time to add one.
 */
class AppContainer(app: Application) {
    val session = Session(KeystoreSecretStore(app))
    val server = ServerSettings(app, defaultUrl = BuildConfig.API_BASE_URL, allowHttp = BuildConfig.DEBUG)
    private val client = ApiClient({ server.url.value }, session)
    val auth: AuthApi = HttpAuthApi(client, session)
    val chat: ChatApi = HttpChatApi(client)
    val library: LibraryApi = HttpLibraryApi(client)
    val verify: VerifyApi = HttpVerifyApi(client)
}

class BookRagApp : Application() {
    val container by lazy { AppContainer(this) }
}
