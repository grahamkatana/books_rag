package com.graham_katana.bookrag.feature.chat

import com.graham_katana.bookrag.core.network.ApiException
import com.graham_katana.bookrag.feature.library.Book
import com.graham_katana.bookrag.feature.library.LibraryApi
import com.graham_katana.bookrag.feature.library.Paper
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.consumeAsFlow
import kotlinx.coroutines.flow.emptyFlow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOf
import kotlinx.coroutines.test.UnconfinedTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

private class FakeChatApi : ChatApi {
    var chatList = listOf<ChatSummary>()
    val details = mutableMapOf<Long, ChatDetail>()
    var answer: Flow<AskEvent> = emptyFlow()
    val asked = mutableListOf<List<Any?>>()
    val deleted = mutableListOf<Long>()

    override suspend fun chats() = chatList
    override suspend fun chat(id: Long) = details[id] ?: throw ApiException.NotFound(null)
    override suspend fun deleteChat(id: Long) { deleted += id; chatList = chatList.filterNot { it.id == id } }
    override fun ask(question: String, chatId: Long?, corpus: Corpus, sources: List<String>?): Flow<AskEvent> {
        asked += listOf(question, chatId, corpus, sources)
        return answer
    }
}

private class FakeLibraryApi : LibraryApi {
    val hull = Book(3, "hull-2018", "Options, Futures", authors = "Hull, J.", year = 2018, bibliographyVerified = true)
    val fama = Paper(9, "fama-1970", "Efficient Capital Markets", authors = "Fama, E.", year = 1970)
    override suspend fun books() = listOf(hull)
    override suspend fun papers() = listOf(fama)
    override suspend fun book(id: Long) = hull.takeIf { it.id == id } ?: throw ApiException.NotFound(null)
    override suspend fun paper(id: Long) = fama.takeIf { it.id == id } ?: throw ApiException.NotFound(null)
}

@OptIn(ExperimentalCoroutinesApi::class)
class ChatViewModelTest {
    private val api = FakeChatApi()
    private val library = FakeLibraryApi()

    @Before fun setUp() = Dispatchers.setMain(UnconfinedTestDispatcher())
    @After fun tearDown() = Dispatchers.resetMain()

    private fun vm() = ChatViewModel(api, library)

    @Test fun `an answer streams in, the chat is created, and its citations arrive at the end`() {
        val citation = Citation("Hull (2018).", "p. 12", bookId = 3)
        api.answer = flowOf(AskEvent.Chat(7), AskEvent.Delta("Risk is priced."), AskEvent.Delta("<CITATION>Hull (2018).</CITATION>"), AskEvent.Done(listOf(citation)))
        api.chatList = listOf(ChatSummary(7, "What is risk?"))
        val vm = vm()
        vm.send("  What is risk?  ")

        val state = vm.state.value
        assertEquals(7L, state.chatId)
        assertFalse(state.isStreaming)
        assertEquals(listOf("What is risk?", "Risk is priced.<CITATION>Hull (2018).</CITATION>"), state.messages.map { it.text })
        assertEquals(listOf(citation), state.messages.last().citations)
        assertEquals(listOf(ChatSummary(7, "What is risk?")), state.chats)
        assertEquals(listOf<Any?>("What is risk?", null, Corpus.BOOKS, null), api.asked.single())
    }

    @Test fun `the corpus and chosen sources go with the question, and changing corpus drops the choice`() {
        val vm = vm()
        vm.toggleSource("hull-2018")
        vm.send("q1")
        assertEquals(listOf("hull-2018"), api.asked.last()[3])

        vm.setCorpus(Corpus.PAPERS)
        assertTrue(vm.state.value.selectedSources.isEmpty())
        assertEquals(listOf(library.fama), vm.state.value.pickableSources)
        vm.setCorpus(Corpus.BOTH)
        assertTrue(vm.state.value.pickableSources.isEmpty())
        vm.send("q2")
        assertEquals(listOf<Any?>("q2", null, Corpus.BOTH, null), api.asked.last())
    }

    @Test fun `a failure is shown in the answer, whether thrown, sent as an event, or a silent stop`() {
        val vm = vm()
        api.answer = flow { throw ApiException.Network() }
        vm.send("a")
        assertTrue(vm.state.value.messages.last().error!!.contains("Can't reach"))

        api.answer = flowOf(AskEvent.Chat(1), AskEvent.Failed("Chat not found"))
        vm.send("b")
        assertEquals("Chat not found", vm.state.value.messages.last().error)

        api.answer = flowOf(AskEvent.Chat(1))
        vm.send("c")
        assertTrue(vm.state.value.messages.last().error!!.startsWith("Sorry"))
        assertFalse(vm.state.value.isStreaming)
    }

    @Test fun `an answer still arriving for a chat you left is ignored`() {
        val channel = Channel<AskEvent>(Channel.UNLIMITED)
        api.answer = channel.consumeAsFlow()
        val vm = vm()
        vm.send("slow question")
        channel.trySend(AskEvent.Chat(7))
        vm.newChat()
        channel.trySend(AskEvent.Delta("late text"))
        channel.close()
        assertNull(vm.state.value.chatId)
        assertTrue(vm.state.value.messages.isEmpty())
    }

    @Test fun `tapping a marker opens its reference and then the book behind it`() {
        val citation = Citation("Hull (2018).", "p. 12", bookId = 3)
        api.details[7] = ChatDetail(7, "t", listOf(ChatMessage(1, "user", "q"), ChatMessage(2, "assistant", "A<CITATION>Hull (2018).</CITATION> B<CITATION>Unknown (n.d.).</CITATION>", listOf(citation))))
        val vm = vm()
        vm.openChat(7)
        val answer = vm.state.value.messages.last()

        vm.openCitation(answer, 1)
        assertEquals(OpenCitation(1, citation, library.hull), vm.state.value.openCitation)

        // A reference the API could not tie to a book or paper still shows its text.
        vm.openCitation(answer, 2)
        assertEquals(OpenCitation(2, Citation("Unknown (n.d.).")), vm.state.value.openCitation)
        vm.closeCitation()
        assertNull(vm.state.value.openCitation)
    }

    @Test fun `deleting the open chat starts a new one, and a chat that is gone is dropped`() {
        api.chatList = listOf(ChatSummary(7, "a"), ChatSummary(8, "b"))
        api.details[7] = ChatDetail(7, "a", listOf(ChatMessage(1, "user", "q")))
        val vm = vm()
        vm.openChat(7)
        vm.deleteChat(7)
        assertEquals(listOf(7L), api.deleted)
        assertNull(vm.state.value.chatId)
        assertEquals(listOf(ChatSummary(8, "b")), vm.state.value.chats)

        vm.openChat(99) // deleted elsewhere
        assertNull(vm.state.value.chatId)
        assertFalse(vm.state.value.isLoadingChat)
    }
}
