package com.graham_katana.bookrag.feature.verify

import com.graham_katana.bookrag.core.network.ApiException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestScope
import kotlinx.coroutines.test.advanceTimeBy
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

private val SUPPORTED = ClaimVerification("supported", "high", "Yes.")
private val SECOND = CrossCheck(agrees = false, verdict = "unverifiable", explanation = "Not sure.")

private class FakeVerifyApi : VerifyApi {
    /** What the server holds. Tests change it between polls, the way the pipeline would. */
    val stored = mutableMapOf<Long, VerificationDocument>()
    var reads = 0
    val reruns = mutableListOf<Boolean>()
    var crossCheckIds = listOf<Long>()
    var uploadError: ApiException? = null

    override suspend fun documents() = stored.values.map { it.copy(claims = emptyList()) }
    override suspend fun document(id: Long): VerificationDocument { reads++; return stored[id] ?: throw ApiException.NotFound("Verification document not found") }
    override suspend fun upload(fileName: String, bytes: ByteArray): Long { uploadError?.let { throw it }; stored[42] = VerificationDocument(42, fileName, "pending"); return 42 }
    override suspend fun submitText(text: String, title: String?): Long { stored[43] = VerificationDocument(43, title ?: "from text", "pending"); return 43 }
    override suspend fun delete(id: Long) { stored.remove(id) ?: throw ApiException.NotFound(null) }
    override suspend fun rerun(id: Long, fromExtraction: Boolean) { reruns += fromExtraction }
    override suspend fun crossCheck(id: Long) = crossCheckIds
}

@OptIn(ExperimentalCoroutinesApi::class)
class VerifyViewModelTest {
    private val api = FakeVerifyApi()
    private val dispatcher = StandardTestDispatcher()
    private val scope = TestScope(dispatcher)

    @Before fun setUp() = Dispatchers.setMain(dispatcher)
    @After fun tearDown() = Dispatchers.resetMain()

    private fun TestScope.vm() = VerifyViewModel(api).also { runCurrent() }

    @Test fun `an upload opens the document and follows it until every claim has a verdict`() = scope.runTest {
        val vm = vm()
        vm.upload("draft.docx", ByteArray(1))
        runCurrent()
        assertEquals(42L, vm.state.value.open?.id)
        assertFalse(vm.state.value.open!!.isFinished)

        api.stored[42] = api.stored[42]!!.copy(status = "verifying", claims = listOf(Claim(1, "A"), Claim(2, "B", verification = SUPPORTED)))
        advanceTimeBy(2_001)
        assertEquals(listOf(null, "supported"), vm.state.value.open!!.claims.map { it.verification?.verdict })

        api.stored[42] = api.stored[42]!!.copy(status = "done", claims = listOf(Claim(1, "A", verification = SUPPORTED), Claim(2, "B", verification = SUPPORTED)))
        advanceTimeBy(2_001)
        assertTrue(vm.state.value.open!!.isFinished)

        // Finished means the reading stops.
        val reads = api.reads
        advanceTimeBy(60_000)
        assertEquals(reads, api.reads)
    }

    @Test fun `a refused upload says why and opens nothing`() = scope.runTest {
        api.uploadError = ApiException.Http(400, "Only .docx files are accepted.")
        val vm = vm()
        vm.upload("notes.pdf", ByteArray(1))
        runCurrent()
        assertEquals("Only .docx files are accepted.", vm.state.value.error)
        assertNull(vm.state.value.open)
        assertFalse(vm.state.value.isSubmitting)
    }

    @Test fun `pasted text is sent trimmed, and a blank title is left for the API to choose`() = scope.runTest {
        val vm = vm()
        vm.submitText("  TAM dates from 1989.  ", "   ")
        runCurrent()
        assertEquals("from text", api.stored[43]!!.filename)
        assertEquals(43L, vm.state.value.open?.id)
    }

    @Test fun `closing a document stops following it`() = scope.runTest {
        api.stored[42] = VerificationDocument(42, "draft.docx", "verifying")
        val vm = vm()
        vm.open(api.stored[42]!!)
        runCurrent()
        vm.close()
        runCurrent()
        val reads = api.reads
        advanceTimeBy(60_000)
        assertEquals(reads, api.reads)
        assertNull(vm.state.value.open)
    }

    @Test fun `a second opinion is followed until it lands on every claim it was asked about`() = scope.runTest {
        val checked = listOf(Claim(1, "A", verification = SUPPORTED), Claim(2, "B", verification = SUPPORTED))
        api.stored[42] = VerificationDocument(42, "draft.docx", "done", claims = checked)
        api.crossCheckIds = listOf(1, 2)
        val vm = vm()
        vm.open(api.stored[42]!!)
        runCurrent()
        vm.openClaim(vm.state.value.open!!.claims[0])

        vm.crossCheck()
        runCurrent()
        assertEquals(setOf(1L, 2L), vm.state.value.awaitingCrossCheck)

        api.stored[42] = api.stored[42]!!.copy(claims = listOf(checked[0].copy(verification = SUPPORTED.copy(crossCheck = SECOND)), checked[1]))
        advanceTimeBy(2_001)
        assertEquals(setOf(2L), vm.state.value.awaitingCrossCheck)
        // The claim sheet that was open shows the second opinion as soon as it exists.
        assertEquals(SECOND, vm.state.value.openClaim!!.verification!!.crossCheck)

        api.stored[42] = api.stored[42]!!.copy(claims = checked.map { it.copy(verification = SUPPORTED.copy(crossCheck = SECOND)) })
        advanceTimeBy(2_001)
        assertTrue(vm.state.value.awaitingCrossCheck.isEmpty())
        val reads = api.reads
        advanceTimeBy(60_000)
        assertEquals(reads, api.reads)
    }

    @Test fun `asking for a second opinion with nothing verified explains instead of waiting forever`() = scope.runTest {
        api.stored[42] = VerificationDocument(42, "draft.docx", "done")
        val vm = vm()
        vm.open(api.stored[42]!!)
        runCurrent()
        vm.crossCheck()
        runCurrent()
        assertTrue(vm.state.value.error!!.contains("no verified claims"))
        assertTrue(vm.state.value.awaitingCrossCheck.isEmpty())
    }

    @Test fun `a rerun shows as running straight away and is followed to the end`() = scope.runTest {
        api.stored[42] = VerificationDocument(42, "draft.docx", "done", claims = listOf(Claim(1, "A", verification = SUPPORTED)))
        val vm = vm()
        vm.open(api.stored[42]!!)
        runCurrent()

        api.stored[42] = api.stored[42]!!.copy(status = "verifying")
        vm.rerun(fromExtraction = false)
        runCurrent()
        assertEquals(listOf(false), api.reruns)
        assertFalse(vm.state.value.open!!.isFinished)

        api.stored[42] = api.stored[42]!!.copy(status = "done")
        advanceTimeBy(2_001)
        assertTrue(vm.state.value.open!!.isFinished)
    }

    @Test fun `deleting the open document returns to the list without it`() = scope.runTest {
        api.stored[42] = VerificationDocument(42, "draft.docx", "done")
        val vm = vm()
        vm.open(api.stored[42]!!)
        runCurrent()
        vm.delete(42)
        runCurrent()
        assertNull(vm.state.value.open)
        assertTrue(vm.state.value.documents.isEmpty())
    }

    @Test fun `a document that vanished while open is reported and closed`() = scope.runTest {
        val vm = vm()
        vm.open(VerificationDocument(77, "gone.docx", "verifying"))
        runCurrent()
        assertNull(vm.state.value.open)
        assertTrue(vm.state.value.error!!.contains("no longer exists"))
    }
}
