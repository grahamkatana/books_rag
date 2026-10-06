package com.graham_katana.bookrag.feature.chat

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.graham_katana.bookrag.core.network.ApiException
import com.graham_katana.bookrag.feature.library.Book
import com.graham_katana.bookrag.feature.library.LibraryApi
import com.graham_katana.bookrag.feature.library.LibraryItem
import com.graham_katana.bookrag.feature.library.Paper
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class UiMessage(
    val id: Long,
    val fromUser: Boolean,
    /** As the API sent it, citation tags included; [renderAnswer] turns it into what is shown. */
    val text: String,
    val citations: List<Citation> = emptyList(),
    val error: String? = null,
)

/** The reference sheet: the citation, and the book or paper behind it once that has loaded. */
data class OpenCitation(val number: Int, val citation: Citation, val item: LibraryItem? = null)

data class ChatUiState(
    val chatId: Long? = null,
    val messages: List<UiMessage> = emptyList(),
    val chats: List<ChatSummary> = emptyList(),
    val isStreaming: Boolean = false,
    val isLoadingChat: Boolean = false,
    val corpus: Corpus = Corpus.BOOKS,
    val books: List<Book> = emptyList(),
    val papers: List<Paper> = emptyList(),
    /** Source keys the next question is limited to; empty searches the whole corpus. */
    val selectedSources: Set<String> = emptySet(),
    val openCitation: OpenCitation? = null,
) {
    /** What the source picker offers. "Both" has no single list to pick from, so it offers nothing. */
    val pickableSources: List<LibraryItem> get() = when (corpus) {
        Corpus.BOOKS -> books
        Corpus.PAPERS -> papers
        Corpus.BOTH -> emptyList()
    }
}

class ChatViewModel(private val api: ChatApi, private val library: LibraryApi) : ViewModel() {
    private val _state = MutableStateFlow(ChatUiState())
    val state: StateFlow<ChatUiState> = _state.asStateFlow()

    /** Bumped whenever the visible chat changes, so an answer still arriving for the old one is ignored. */
    private var turn = 0
    private var nextLocalId = -1L

    init {
        refreshChats()
        // The lists only feed the source picker; asking works without them, so a failure here stays quiet.
        quietly { val books = library.books(); _state.update { it.copy(books = books) } }
        quietly { val papers = library.papers(); _state.update { it.copy(papers = papers) } }
    }

    fun refreshChats() = quietly {
        val chats = api.chats()
        _state.update { it.copy(chats = chats) }
    }

    fun newChat() {
        turn++
        _state.update { it.copy(chatId = null, messages = emptyList(), isStreaming = false, isLoadingChat = false, selectedSources = emptySet(), openCitation = null) }
    }

    fun openChat(id: Long) {
        val mine = ++turn
        // The source limit is not saved with a chat, so reopening one always starts unlimited.
        _state.update { it.copy(chatId = id, messages = emptyList(), isStreaming = false, isLoadingChat = true, selectedSources = emptySet(), openCitation = null) }
        viewModelScope.launch {
            try {
                val detail = api.chat(id)
                if (mine == turn) _state.update { it.copy(messages = detail.messages.map(::toUi), isLoadingChat = false) }
            } catch (e: ApiException) {
                if (mine != turn) return@launch
                if (e is ApiException.NotFound) { newChat(); refreshChats() } else {
                    _state.update { it.copy(isLoadingChat = false, messages = listOf(UiMessage(nextLocalId--, fromUser = false, text = "", error = e.message))) }
                }
            }
        }
    }

    fun deleteChat(id: Long) {
        viewModelScope.launch {
            try {
                api.deleteChat(id)
            } catch (e: ApiException) {
                if (e !is ApiException.NotFound) return@launch // still there; leave the list alone
            }
            _state.update { it.copy(chats = it.chats.filterNot { chat -> chat.id == id }) }
            if (_state.value.chatId == id) newChat()
        }
    }

    fun setCorpus(corpus: Corpus) {
        // The two libraries hold different things, so a selection made in one means nothing in the other.
        if (corpus != _state.value.corpus) _state.update { it.copy(corpus = corpus, selectedSources = emptySet()) }
    }

    fun toggleSource(sourceKey: String) = _state.update {
        it.copy(selectedSources = if (sourceKey in it.selectedSources) it.selectedSources - sourceKey else it.selectedSources + sourceKey)
    }

    fun clearSources() = _state.update { it.copy(selectedSources = emptySet()) }

    fun send(question: String) {
        val query = question.trim()
        val before = _state.value
        if (query.isEmpty() || before.isStreaming || before.isLoadingChat) return

        val mine = turn
        val answerId = nextLocalId--
        _state.update {
            it.copy(isStreaming = true, messages = it.messages + UiMessage(nextLocalId--, fromUser = true, text = query) + UiMessage(answerId, fromUser = false, text = ""))
        }
        fun patch(change: (UiMessage) -> UiMessage) = _state.update { s -> s.copy(messages = s.messages.map { if (it.id == answerId) change(it) else it }) }

        viewModelScope.launch {
            try {
                api.ask(query, before.chatId, before.corpus, before.selectedSources.toList().ifEmpty { null }).collect { event ->
                    if (mine != turn) return@collect
                    when (event) {
                        is AskEvent.Chat -> if (_state.value.chatId == null) {
                            _state.update { it.copy(chatId = event.id) }
                            refreshChats() // the new chat appears in the list straight away
                        }
                        is AskEvent.Delta -> patch { it.copy(text = it.text + event.text) }
                        is AskEvent.Done -> patch { it.copy(citations = event.citations) }
                        is AskEvent.Failed -> patch { it.copy(error = event.message.ifBlank { GENERIC_FAILURE }) }
                    }
                }
                // A stream that just stops, with no answer and no error event, is a failure the person should see.
                if (mine == turn) patch { if (it.text.isEmpty() && it.error == null) it.copy(error = GENERIC_FAILURE) else it }
                refreshChats()
            } catch (e: CancellationException) {
                throw e
            } catch (e: ApiException) {
                if (mine == turn) patch { it.copy(error = e.message) }
            } finally {
                if (mine == turn) _state.update { it.copy(isStreaming = false) }
            }
        }
    }

    /** Opens the reference behind marker [number] of [message], then fills in the book or paper it points at. */
    fun openCitation(message: UiMessage, number: Int) {
        val apaText = renderAnswer(message.text).references.getOrNull(number - 1) ?: return
        // An answer that is still arriving has no structured citations yet; the reference text alone is still worth showing.
        val citation = message.citations.firstOrNull { it.apaText == apaText } ?: Citation(apaText)
        val open = OpenCitation(number, citation)
        _state.update { it.copy(openCitation = open) }
        quietly {
            val item = when {
                citation.paperId != null -> library.paper(citation.paperId)
                citation.bookId != null -> library.book(citation.bookId)
                else -> return@quietly
            }
            _state.update { if (it.openCitation == open) it.copy(openCitation = open.copy(item = item)) else it }
        }
    }

    fun closeCitation() = _state.update { it.copy(openCitation = null) }

    private fun toUi(message: ChatMessage) =
        UiMessage(message.id, fromUser = message.role.equals("user", ignoreCase = true), text = message.content, citations = message.citations)

    /** For calls whose failure is not worth interrupting the person for. An expired login still ends the session. */
    private fun quietly(block: suspend () -> Unit) {
        viewModelScope.launch {
            try { block() } catch (e: ApiException) { /* nothing to show */ }
        }
    }

    private companion object {
        const val GENERIC_FAILURE = "Sorry, I couldn't get an answer. Please try again."
    }
}
