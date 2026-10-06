package com.graham_katana.bookrag.feature.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.graham_katana.bookrag.core.auth.Account
import com.graham_katana.bookrag.core.auth.Session
import com.graham_katana.bookrag.core.network.ApiClient
import com.graham_katana.bookrag.core.network.ApiException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable private data class LoginBody(val email: String, val password: String)
@Serializable private data class LoginReply(@SerialName("access_token") val accessToken: String, val email: String)

fun interface AuthApi {
    /** Logs in and starts the session, or throws an [ApiException] saying why not. */
    suspend fun login(email: String, password: String)
}

class HttpAuthApi(private val client: ApiClient, private val session: Session) : AuthApi {
    override suspend fun login(email: String, password: String) {
        val reply = client.post<LoginReply>("/api/v1/auth/login", client.jsonBody(LoginBody(email, password)), authed = false)
        session.start(Account(reply.accessToken, reply.email))
    }
}

data class LoginUiState(val isSubmitting: Boolean = false, val error: String? = null)

class LoginViewModel(private val api: AuthApi) : ViewModel() {
    private val _state = MutableStateFlow(LoginUiState())
    val state: StateFlow<LoginUiState> = _state.asStateFlow()

    fun submit(email: String, password: String) {
        if (_state.value.isSubmitting) return
        if (email.isBlank() || password.isEmpty()) {
            _state.update { it.copy(error = "Enter your email address and password.") }
            return
        }
        _state.value = LoginUiState(isSubmitting = true)
        viewModelScope.launch {
            try {
                api.login(email.trim(), password)
                // Nothing to do on success: the session starting is what moves the app past this screen.
                _state.value = LoginUiState()
            } catch (e: ApiException) {
                // 422 is the API rejecting the shape of the email address before it looks anyone up.
                val message = if (e is ApiException.Http && e.code == 422) "That doesn't look like an email address." else e.message
                _state.value = LoginUiState(error = message)
            }
        }
    }
}
