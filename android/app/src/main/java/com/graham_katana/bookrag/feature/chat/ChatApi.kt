package com.graham_katana.bookrag.feature.chat

import com.graham_katana.bookrag.core.network.ApiClient
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.mapNotNull
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** Which library a question searches. The wire value is the lowercase name. */
enum class Corpus(val label: String) { BOOKS("Books"), PAPERS("Papers"), BOTH("Both") }

/** A reference the answer used. It points at a book or a paper, never both; sometimes neither can be resolved. */
@Serializable
data class Citation(
    @SerialName("apa_text") val apaText: String,
    val locator: String? = null,
    @SerialName("book_id") val bookId: Long? = null,
    @SerialName("paper_id") val paperId: Long? = null,
)

@Serializable
data class ChatSummary(val id: Long, val title: String? = null)

@Serializable
data class ChatMessage(val id: Long, val role: String, val content: String, val citations: List<Citation> = emptyList())

@Serializable
data class ChatDetail(val id: Long, val title: String? = null, val messages: List<ChatMessage> = emptyList())

/** What asking produces, in order: the chat's id once, the answer in pieces, then its citations. */
sealed interface AskEvent {
    data class Chat(val id: Long) : AskEvent
    data class Delta(val text: String) : AskEvent
    data class Done(val citations: List<Citation>) : AskEvent
    /** The stream had already started when something failed, so the API reports it as an event. */
    data class Failed(val message: String) : AskEvent
}

interface ChatApi {
    suspend fun chats(): List<ChatSummary>
    suspend fun chat(id: Long): ChatDetail
    suspend fun deleteChat(id: Long)
    /** [sources] limits the search to those books or papers (their source keys); null searches the whole corpus. */
    fun ask(question: String, chatId: Long?, corpus: Corpus, sources: List<String>?): Flow<AskEvent>
}

class HttpChatApi(private val client: ApiClient) : ChatApi {
    @Serializable private data class AskBody(val question: String, @SerialName("chat_id") val chatId: Long?, val sources: List<String>?, val corpus: String)
    @Serializable private data class ChatIdData(@SerialName("chat_id") val chatId: Long)
    @Serializable private data class DeltaData(val text: String = "")
    @Serializable private data class DoneData(val citations: List<Citation> = emptyList())
    @Serializable private data class ErrorData(val message: String = "")

    override suspend fun chats(): List<ChatSummary> = client.get("/api/v1/chats/")
    override suspend fun chat(id: Long): ChatDetail = client.get("/api/v1/chats/$id")
    override suspend fun deleteChat(id: Long) = client.delete("/api/v1/chats/$id")

    override fun ask(question: String, chatId: Long?, corpus: Corpus, sources: List<String>?): Flow<AskEvent> =
        client.events("/api/v1/ask/stream", client.jsonBody(AskBody(question, chatId, sources, corpus.name.lowercase()))).mapNotNull { event ->
            val json = client.json
            when (event.event) {
                "chat_id" -> AskEvent.Chat(json.decodeFromString<ChatIdData>(event.data).chatId)
                "delta" -> AskEvent.Delta(json.decodeFromString<DeltaData>(event.data).text)
                "done" -> AskEvent.Done(json.decodeFromString<DoneData>(event.data).citations)
                "error" -> AskEvent.Failed(json.decodeFromString<ErrorData>(event.data).message)
                else -> null // an event this version does not know about is not a reason to fail the answer
            }
        }
}
