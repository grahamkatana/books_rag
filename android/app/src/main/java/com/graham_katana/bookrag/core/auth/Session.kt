package com.graham_katana.bookrag.core.auth

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.serialization.Serializable
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

@Serializable
data class Account(val accessToken: String, val email: String)

/** Where the login is kept between launches. The real one encrypts it; tests use a plain one. */
interface SecretStore {
    fun load(): String?
    fun save(value: String)
    fun clear()
}

/**
 * The one place that knows whether somebody is logged in. Screens watch [account];
 * the API client ends the session when the server says the token is no longer good,
 * so every screen returns to login the same way without each one checking for it.
 */
class Session(private val store: SecretStore) {
    private val _account = MutableStateFlow(read())
    val account: StateFlow<Account?> = _account.asStateFlow()

    val token: String? get() = _account.value?.accessToken

    fun start(account: Account) {
        store.save(Json.encodeToString(account))
        _account.value = account
    }

    fun end() {
        store.clear()
        _account.value = null
    }

    private fun read(): Account? = store.load()?.let { runCatching { Json.decodeFromString<Account>(it) }.getOrNull() }
}

/**
 * Encrypts with an AES key that lives in the Android Keystore. The key never leaves
 * the keystore, so SharedPreferences holds ciphertext only. Backups are disabled in
 * the manifest so the ciphertext is not copied off the device. Nothing is logged.
 */
class KeystoreSecretStore(context: Context) : SecretStore {
    private val prefs = context.getSharedPreferences("session", Context.MODE_PRIVATE)

    override fun load(): String? {
        val stored = prefs.getString(KEY_BLOB, null) ?: return null
        return try {
            val bytes = Base64.decode(stored, Base64.NO_WRAP)
            val cipher = Cipher.getInstance(TRANSFORMATION).apply {
                init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(TAG_BITS, bytes.copyOfRange(0, IV_BYTES)))
            }
            String(cipher.doFinal(bytes, IV_BYTES, bytes.size - IV_BYTES), Charsets.UTF_8)
        } catch (e: Exception) {
            // Unreadable (e.g. the keystore key was reset): treat as logged out rather than crash.
            clear()
            null
        }
    }

    override fun save(value: String) {
        try {
            val cipher = Cipher.getInstance(TRANSFORMATION).apply { init(Cipher.ENCRYPT_MODE, key()) }
            val sealed = cipher.iv + cipher.doFinal(value.toByteArray(Charsets.UTF_8))
            prefs.edit().putString(KEY_BLOB, Base64.encodeToString(sealed, Base64.NO_WRAP)).apply()
        } catch (e: Exception) {
            // A keystore that refuses to work must not block logging in: the session then lasts until the app closes.
            clear()
        }
    }

    override fun clear() {
        prefs.edit().remove(KEY_BLOB).apply()
    }

    private fun key(): SecretKey {
        val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        (keyStore.getKey(ALIAS, null) as? SecretKey)?.let { return it }
        return KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE).run {
            init(
                KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setKeySize(256)
                    .build()
            )
            generateKey()
        }
    }

    private companion object {
        const val ANDROID_KEYSTORE = "AndroidKeyStore"
        const val ALIAS = "book_rag_session_key"
        const val KEY_BLOB = "account"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val IV_BYTES = 12
        const val TAG_BITS = 128
    }
}
