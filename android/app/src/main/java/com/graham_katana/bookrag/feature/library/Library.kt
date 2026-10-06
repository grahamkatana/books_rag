package com.graham_katana.bookrag.feature.library

import com.graham_katana.bookrag.core.network.ApiClient
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** Something a question can be limited to, and a citation can point at: a book or a paper. */
sealed interface LibraryItem {
    val sourceKey: String
    val title: String
    val authors: String?
    val year: Int?
    val bibliographyVerified: Boolean
}

@Serializable
data class Book(
    val id: Long,
    @SerialName("source_key") override val sourceKey: String,
    override val title: String,
    override val authors: String? = null,
    @SerialName("is_editor") val isEditor: Boolean = false,
    override val year: Int? = null,
    val publisher: String? = null,
    val edition: String? = null,
    @SerialName("bibliography_verified") override val bibliographyVerified: Boolean = false,
) : LibraryItem

@Serializable
data class Paper(
    val id: Long,
    @SerialName("source_key") override val sourceKey: String,
    override val title: String,
    override val authors: String? = null,
    override val year: Int? = null,
    val venue: String? = null,
    val doi: String? = null,
    val abstract: String? = null,
    @SerialName("bibliography_verified") override val bibliographyVerified: Boolean = false,
) : LibraryItem

interface LibraryApi {
    suspend fun books(): List<Book>
    suspend fun papers(): List<Paper>
    suspend fun book(id: Long): Book
    suspend fun paper(id: Long): Paper
}

class HttpLibraryApi(private val client: ApiClient) : LibraryApi {
    override suspend fun books(): List<Book> = client.get("/api/v1/books/")
    override suspend fun papers(): List<Paper> = client.get("/api/v1/papers/")
    override suspend fun book(id: Long): Book = client.get("/api/v1/books/$id")
    override suspend fun paper(id: Long): Paper = client.get("/api/v1/papers/$id")
}
