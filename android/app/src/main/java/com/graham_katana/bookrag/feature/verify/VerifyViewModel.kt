package com.graham_katana.bookrag.feature.verify

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.graham_katana.bookrag.core.network.ApiException
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withTimeoutOrNull

data class VerifyUiState(
    val documents: List<VerificationDocument> = emptyList(),
    val isLoading: Boolean = true,
    /** The open document. Only its id and name are known until its claims have loaded. */
    val open: VerificationDocument? = null,
    val isLoadingOpen: Boolean = false,
    /** True from sending a draft until the API has accepted it. */
    val isSubmitting: Boolean = false,
    /** Ids of claims a second opinion has been asked for and has not arrived yet. */
    val awaitingCrossCheck: Set<Long> = emptySet(),
    val openClaim: Claim? = null,
    val error: String? = null,
)

/**
 * Verification runs on the server for minutes, and its result is the document
 * itself: claims appear, then each gains a verdict. So "progress" here is just
 * reading the document again every [POLL_MS] until it says it is finished.
 */
class VerifyViewModel(private val api: VerifyApi) : ViewModel() {
    private val _state = MutableStateFlow(VerifyUiState())
    val state: StateFlow<VerifyUiState> = _state.asStateFlow()

    /** The one document being watched. Opening another, or closing this one, stops the watching. */
    private var watching: Job? = null

    init {
        refresh()
    }

    fun refresh() = attempt(onFailure = { _state.update { it.copy(isLoading = false) } }) {
        val documents = api.documents()
        _state.update { it.copy(documents = documents, isLoading = false) }
    }

    fun open(document: VerificationDocument) {
        _state.update { it.copy(open = document.copy(claims = emptyList()), isLoadingOpen = true, awaitingCrossCheck = emptySet(), openClaim = null, error = null) }
        watch(document.id)
    }

    fun close() {
        watching?.cancel()
        _state.update { it.copy(open = null, isLoadingOpen = false, awaitingCrossCheck = emptySet(), openClaim = null) }
        refresh() // the list shows status and claim counts that changed while the document was open
    }

    fun upload(fileName: String, bytes: ByteArray) = submit { api.upload(fileName, bytes) to fileName }

    fun submitText(text: String, title: String) = submit { api.submitText(text.trim(), title.trim().ifEmpty { null }) to title.trim().ifEmpty { "Pasted text" } }

    private fun submit(send: suspend () -> Pair<Long, String>) {
        if (_state.value.isSubmitting) return
        _state.update { it.copy(isSubmitting = true, error = null) }
        attempt(onFailure = { _state.update { it.copy(isSubmitting = false) } }) {
            val (id, name) = send()
            _state.update { it.copy(isSubmitting = false) }
            open(VerificationDocument(id, name, status = "pending"))
        }
    }

    fun delete(id: Long) = attempt {
        try { api.delete(id) } catch (e: ApiException.NotFound) { /* already gone, which is what was asked for */ }
        if (_state.value.open?.id == id) close() else refresh()
    }

    /** [fromExtraction] finds the claims again from scratch; otherwise the existing claims are only re-checked. */
    fun rerun(fromExtraction: Boolean) {
        val id = _state.value.open?.id ?: return
        attempt {
            api.rerun(id, fromExtraction)
            // The API accepted it but the status may not have left "done" yet, so say so here rather than wait a poll.
            _state.update { s -> if (s.open?.id == id) s.copy(open = s.open.copy(status = "pending"), awaitingCrossCheck = emptySet()) else s }
            watch(id)
        }
    }

    fun crossCheck() {
        val id = _state.value.open?.id ?: return
        attempt {
            val claimIds = api.crossCheck(id)
            if (claimIds.isEmpty()) {
                _state.update { it.copy(error = "There are no verified claims to cross-check yet.") }
                return@attempt
            }
            // A second opinion never changes the document's status, so these ids are the only sign that it is still running.
            _state.update { s -> if (s.open?.id == id) s.copy(awaitingCrossCheck = claimIds.toSet()) else s }
            watch(id)
        }
    }

    fun openClaim(claim: Claim) = _state.update { it.copy(openClaim = claim) }
    fun closeClaim() = _state.update { it.copy(openClaim = null) }
    fun dismissError() = _state.update { it.copy(error = null) }

    private fun watch(id: Long) {
        watching?.cancel()
        watching = viewModelScope.launch {
            try {
                val finished = withTimeoutOrNull(TIMEOUT_MS) {
                    while (true) {
                        val document = api.document(id)
                        _state.update { s ->
                            if (s.open?.id != id) return@update s
                            val checked = document.claims.filter { it.verification?.crossCheck != null }.map { it.id }.toSet()
                            s.copy(
                                open = document,
                                isLoadingOpen = false,
                                awaitingCrossCheck = s.awaitingCrossCheck - checked,
                                // Keep an open claim sheet showing the newest verdict for that claim.
                                openClaim = s.openClaim?.let { shown -> document.claims.firstOrNull { it.id == shown.id } },
                            )
                        }
                        if (document.isFinished && _state.value.awaitingCrossCheck.isEmpty()) break
                        delay(POLL_MS)
                    }
                }
                if (finished == null) _state.update { it.copy(awaitingCrossCheck = emptySet(), error = "This is taking longer than expected. Open the document again later to see the result.") }
            } catch (e: CancellationException) {
                throw e
            } catch (e: ApiException) {
                _state.update { s ->
                    if (s.open?.id != id) s
                    else if (e is ApiException.NotFound) s.copy(open = null, isLoadingOpen = false, error = "That document no longer exists.")
                    else s.copy(isLoadingOpen = false, awaitingCrossCheck = emptySet(), error = e.message)
                }
                if (e is ApiException.NotFound) refresh()
            }
        }
    }

    private fun attempt(onFailure: () -> Unit = {}, block: suspend () -> Unit) {
        viewModelScope.launch {
            try {
                block()
            } catch (e: CancellationException) {
                throw e
            } catch (e: ApiException) {
                onFailure()
                _state.update { it.copy(error = e.message) }
            }
        }
    }

    private companion object {
        const val POLL_MS = 2_000L
        const val TIMEOUT_MS = 15 * 60 * 1_000L
    }
}
