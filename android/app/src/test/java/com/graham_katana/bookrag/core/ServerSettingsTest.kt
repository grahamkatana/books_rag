package com.graham_katana.bookrag.core.network

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ServerSettingsTest {
    private fun https(input: String) = ServerSettings.normalise(input, allowHttp = false)

    @Test fun `an address is tidied into one form`() {
        assertEquals("https://books.example.org", https("  books.example.org/ "))
        assertEquals("https://books.example.org", https("HTTPS://Books.Example.org"))
        assertEquals("https://example.org:8443/rag", https("https://example.org:8443/rag/"))
        assertEquals("https://example.org", https("https://example.org:443"))
    }

    @Test fun `plain http is refused in a release build and allowed in a debug one`() {
        assertNull(https("http://192.168.1.20:8000"))
        assertEquals("http://192.168.1.20:8000", ServerSettings.normalise("http://192.168.1.20:8000", allowHttp = true))
    }

    @Test fun `things that are not a server address are refused`() {
        listOf("", "   ", "not a url", "ftp://example.org", "https://", "https://user:pw@example.org", "https://example.org/?x=1", "https://example.org/#top", "javascript:alert(1)")
            .forEach { assertNull(it, https(it)) }
    }
}
