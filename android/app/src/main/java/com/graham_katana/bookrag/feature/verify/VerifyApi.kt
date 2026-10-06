package com.graham_katana.bookrag.feature.verify

import com.graham_katana.bookrag.core.network.ApiClient
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody

/** A draft whose claims are being, or have been, checked against the library. */
@Serializable
data class VerificationDocument(
    val id: Long,
    val filename: String,
    /** "done" and "failed" are final; anything else means the pipeline is still working on it. */
    val status: String,
    @SerialName("error_message") val errorMessage: String? = null,
    @SerialName("claim_count") val claimCount: Int = 0,
    /** Present on a single document, absent in the list. */
    val claims: List<Claim> = emptyList(),
) {
    val isFinished: Boolean get() = status == "done" || status == "failed"
}

@Serializable
data class Claim(
    val id: Long,
    val text: String,
    @SerialName("order_index") val orderIndex: Int = 0,
    /** Null until this claim has been checked: the count of non-null ones is the progress. */
    val verification: ClaimVerification? = null,
)

@Serializable
data class ClaimVerification(
    val verdict: String,
    val confidence: String? = null,
    val explanation: String = "",
    val evidence: List<Evidence> = emptyList(),
    @SerialName("cross_check") val crossCheck: CrossCheck? = null,
)

@Serializable
data class Evidence(
    val title: String? = null,
    val excerpt: String = "",
    val locator: String? = null,
    @SerialName("web_url") val webUrl: String? = null,
)

/** A second model's independent opinion on a verdict. */
@Serializable
data class CrossCheck(
    val agrees: Boolean,
    val verdict: String,
    val confidence: String? = null,
    val explanation: String = "",
    @SerialName("is_checkable_claim") val isCheckableClaim: Boolean = true,
    val model: String = "",
)

interface VerifyApi {
    suspend fun documents(): List<VerificationDocument>
    suspend fun document(id: Long): VerificationDocument
    /** Both return the new document's id; its claims and verdicts then appear on the document itself. */
    suspend fun upload(fileName: String, bytes: ByteArray): Long
    suspend fun submitText(text: String, title: String?): Long
    suspend fun delete(id: Long)
    suspend fun rerun(id: Long, fromExtraction: Boolean)
    /** Returns the ids of the claims the second model will look at. */
    suspend fun crossCheck(id: Long): List<Long>
}

class HttpVerifyApi(private val client: ApiClient) : VerifyApi {
    @Serializable private data class Queued(@SerialName("source_key") val sourceKey: String)
    @Serializable private data class CrossCheckQueued(@SerialName("claim_ids") val claimIds: List<Long> = emptyList())
    @Serializable private data class TextBody(val text: String, val title: String?)

    override suspend fun documents(): List<VerificationDocument> = client.get("$PATH/")
    override suspend fun document(id: Long): VerificationDocument = client.get("$PATH/$id")

    override suspend fun upload(fileName: String, bytes: ByteArray): Long {
        val body = MultipartBody.Builder().setType(MultipartBody.FORM)
            .addFormDataPart("file", fileName, bytes.toRequestBody(DOCX))
            .build()
        return client.post<Queued>("$PATH/", body).sourceKey.toLong()
    }

    override suspend fun submitText(text: String, title: String?): Long =
        client.post<Queued>("$PATH/text", client.jsonBody(TextBody(text, title))).sourceKey.toLong()

    override suspend fun delete(id: Long) = client.delete("$PATH/$id")

    override suspend fun rerun(id: Long, fromExtraction: Boolean) {
        client.post<Queued>("$PATH/$id/rerun?from_extraction=$fromExtraction")
    }

    override suspend fun crossCheck(id: Long): List<Long> = client.post<CrossCheckQueued>("$PATH/$id/cross-check").claimIds

    private companion object {
        const val PATH = "/api/v1/verification"
        val DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document".toMediaType()
    }
}
