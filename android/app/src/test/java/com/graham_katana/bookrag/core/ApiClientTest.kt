package com.graham_katana.bookrag.core

import com.graham_katana.bookrag.core.auth.Account
import com.graham_katana.bookrag.core.auth.SecretStore
import com.graham_katana.bookrag.core.auth.Session
import com.graham_katana.bookrag.core.network.ApiClient
import com.graham_katana.bookrag.core.network.ApiException
import com.graham_katana.bookrag.core.network.SseEvent
import com.graham_katana.bookrag.feature.auth.HttpAuthApi
import com.graham_katana.bookrag.feature.chat.AskEvent
import com.graham_katana.bookrag.feature.chat.Citation
import com.graham_katana.bookrag.feature.chat.Corpus
import com.graham_katana.bookrag.feature.chat.HttpChatApi
import com.graham_katana.bookrag.feature.verify.HttpVerifyApi
import kotlinx.coroutines.flow.toList
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

class MemoryStore(private var value: String? = null) : SecretStore {
    override fun load() = value
    override fun save(value: String) { this.value = value }
    override fun clear() { value = null }
}

class ApiClientTest {
    private lateinit var server: MockWebServer
    private lateinit var session: Session
    private lateinit var client: ApiClient

    @Before fun setUp() {
        server = MockWebServer().apply { start() }
        session = Session(MemoryStore()).apply { start(Account("token-1", "ann@example.com")) }
        client = ApiClient({ server.url("/").toString() }, session)
    }

    @After fun tearDown() = server.shutdown()

    private fun json(body: String, code: Int = 200) = MockResponse().setResponseCode(code).setHeader("Content-Type", "application/json").setBody(body)

    @Test fun `logging in starts the session and sends no token`() = runTest {
        session.end()
        server.enqueue(json("""{"access_token":"fresh","email":"ann@example.com","is_admin":false}"""))
        HttpAuthApi(client, session).login("ann@example.com", "pw")
        assertEquals(Account("fresh", "ann@example.com"), session.account.value)
        val sent = server.takeRequest()
        assertEquals("/api/v1/auth/login", sent.path)
        assertNull(sent.getHeader("Authorization"))
        assertEquals("""{"email":"ann@example.com","password":"pw"}""", sent.body.readUtf8())
    }

    @Test fun `a wrong password shows the API's reason and does not end anything`() = runTest {
        session.end()
        server.enqueue(json("""{"code":401,"status":"Unauthorized","message":"Invalid email or password"}""", 401))
        val e = assertThrows(ApiException.Http::class.java) { runBlocking { HttpAuthApi(client, session).login("ann@example.com", "no") } }
        assertEquals("Invalid email or password", e.message)
    }

    @Test fun `a login survives a restart, and an unreadable one is treated as logged out`() {
        val store = MemoryStore()
        Session(store).start(Account("t", "ann@example.com"))
        assertEquals("ann@example.com", Session(store).account.value?.email)
        assertNull(Session(MemoryStore("not json")).account.value)
    }

    @Test fun `an expired token ends the session`() = runTest {
        server.enqueue(json("""{"msg":"Token has expired"}""", 401))
        assertThrows(ApiException.SessionExpired::class.java) { runBlocking { HttpChatApi(client).chats() } }
        assertNull(session.account.value)
        assertEquals("Bearer token-1", server.takeRequest().getHeader("Authorization"))
    }

    @Test fun `a server error never shows its body, and an unreachable server is a Network error`() = runTest {
        server.enqueue(MockResponse().setResponseCode(502).setBody("<html>Bad Gateway</html>"))
        val e = assertThrows(ApiException.Http::class.java) { runBlocking { HttpChatApi(client).chats() } }
        assertTrue(e.message!!.startsWith("Something went wrong"))
        server.shutdown()
        assertThrows(ApiException.Network::class.java) { runBlocking { HttpChatApi(client).chats() } }
    }

    @Test fun `events are split on blank lines, whatever their names`() = runTest {
        server.enqueue(MockResponse().setHeader("Content-Type", "text/event-stream").setBody("event: a\ndata: {\"x\": 1}\n\nevent: b\ndata: two\n\n"))
        assertEquals(listOf(SseEvent("a", """{"x": 1}"""), SseEvent("b", "two")), client.events("/x", ApiClient.EMPTY).toList())
    }

    @Test fun `asking sends the question and scope, and reads the answer in order`() = runTest {
        server.enqueue(MockResponse().setHeader("Content-Type", "text/event-stream").setBody(
            "event: chat_id\ndata: {\"chat_id\": 7}\n\n" +
                "event: delta\ndata: {\"text\": \"Risk is \"}\n\n" +
                "event: delta\ndata: {\"text\": \"priced.\"}\n\n" +
                "event: later_addition\ndata: {}\n\n" +
                "event: done\ndata: {\"citations\": [{\"apa_text\": \"Hull (2018).\", \"locator\": \"p. 12\", \"book_id\": 3, \"paper_id\": null}]}\n\n"
        ))
        val events = HttpChatApi(client).ask("What is risk?", chatId = null, corpus = Corpus.PAPERS, sources = listOf("hull-2018")).toList()
        assertEquals(
            listOf(AskEvent.Chat(7), AskEvent.Delta("Risk is "), AskEvent.Delta("priced."), AskEvent.Done(listOf(Citation("Hull (2018).", "p. 12", bookId = 3)))),
            events,
        )
        val sent = server.takeRequest()
        assertEquals("/api/v1/ask/stream", sent.path)
        assertEquals("""{"question":"What is risk?","sources":["hull-2018"],"corpus":"papers"}""", sent.body.readUtf8())
    }

    @Test fun `a failure after the answer started arrives as an event, not an exception`() = runTest {
        server.enqueue(MockResponse().setBody("event: chat_id\ndata: {\"chat_id\": 7}\n\nevent: error\ndata: {\"message\": \"Chat not found\"}\n\n"))
        assertEquals(listOf(AskEvent.Chat(7), AskEvent.Failed("Chat not found")), HttpChatApi(client).ask("q", 7, Corpus.BOOKS, null).toList())
    }

    @Test fun `uploading a draft sends the file and returns the new document's id`() = runTest {
        server.enqueue(json("""{"task_id":"abc","source_key":"42","status":"queued"}""", 202))
        assertEquals(42L, HttpVerifyApi(client).upload("draft.docx", "PK-bytes".toByteArray()))
        val sent = server.takeRequest()
        assertEquals("POST /api/v1/verification/", "${sent.method} ${sent.path}")
        val body = sent.body.readUtf8()
        assertTrue(body.contains("name=\"file\"; filename=\"draft.docx\"") && body.contains("wordprocessingml") && body.contains("PK-bytes"))
    }

    @Test fun `rerun and second opinion call the right paths, and a document reads with its verdicts`() = runTest {
        val api = HttpVerifyApi(client)
        server.enqueue(json("""{"task_id":"a","source_key":"42","status":"queued"}""", 202))
        api.rerun(42, fromExtraction = false)
        assertEquals("/api/v1/verification/42/rerun?from_extraction=false", server.takeRequest().path)

        server.enqueue(json("""{"task_id":"a","document_id":42,"claim_ids":[5,6],"status":"queued"}""", 202))
        assertEquals(listOf(5L, 6L), api.crossCheck(42))
        assertEquals("/api/v1/verification/42/cross-check", server.takeRequest().path)

        server.enqueue(json("""{"id":42,"filename":"draft.docx","status":"done","error_message":null,"created_at":"x","claim_count":1,"markdown":"# Draft","claims":[
            {"id":5,"text":"TAM dates from 1989.","order_index":0,"verification":{"verdict":"supported","confidence":"high","explanation":"Yes.",
             "evidence":[{"book_id":1,"paper_id":null,"web_url":null,"title":"Davis","excerpt":"…","locator":"p. 319"}],
             "cross_check":{"agrees":true,"verdict":"supported","confidence":"high","explanation":"Agreed.","is_checkable_claim":true,"model":"deepseek"}}}]}"""))
        val document = api.document(42)
        assertEquals("GET /api/v1/verification/42", server.takeRequest().let { "${it.method} ${it.path}" })
        assertTrue(document.isFinished)
        assertEquals("p. 319", document.claims.single().verification!!.evidence.single().locator)
        assertTrue(document.claims.single().verification!!.crossCheck!!.agrees)

        server.enqueue(MockResponse().setResponseCode(204))
        api.delete(42)
        assertEquals("DELETE", server.takeRequest().method)
    }
}
