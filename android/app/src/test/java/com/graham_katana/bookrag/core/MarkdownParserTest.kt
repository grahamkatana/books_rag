package com.graham_katana.bookrag.core.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class MarkdownParserTest {
    private fun texts(spans: List<Span>) = spans.map { it.text }

    @Test fun `bold, italic and code become styled spans`() {
        val spans = parseInline("Net sales were **$391.0 billion**, *up* 2% (`FY24`).")
        assertEquals(listOf("Net sales were ", "$391.0 billion", ", ", "up", " 2% (", "FY24", ")."), texts(spans))
        assertTrue(spans[1].bold && spans[3].italic && spans[5].code)
    }

    @Test fun `an unfinished marker while streaming stays plain text`() {
        assertEquals(listOf(Span("Total was **391")), parseInline("Total was **391"))
        assertEquals(listOf(Span("a `code")), parseInline("a `code"))
    }

    @Test fun `arithmetic asterisks are not italics`() {
        assertEquals(listOf(Span("5 * 3 * 2")), parseInline("5 * 3 * 2"))
    }

    @Test fun `headings, paragraphs, bullets and numbered lists`() {
        val blocks = parseMarkdown("## Summary\nTotal net sales rose.\n\n- iPhone\n- Services\n\n1. First\n2. Second")
        assertEquals(MdBlock.Heading(2, listOf(Span("Summary"))), blocks[0])
        assertEquals(MdBlock.Paragraph(listOf(Span("Total net sales rose."))), blocks[1])
        assertEquals(2, (blocks[2] as MdBlock.Bullets).items.size)
        assertEquals(listOf("First", "Second"), (blocks[3] as MdBlock.Numbered).items.map { texts(it).single() })
    }

    @Test fun `a table keeps its header, rows and bold cells`() {
        val blocks = parseMarkdown("Intro\n\n| Segment | FY2024 | FY2023 |\n|---|---|---|\n| iPhone | 201,183 | 200,583 |\n| **Services** | 96,169 | 85,200 |\n\nAfter")
        val table = blocks[1] as MdBlock.Table
        assertEquals(listOf("Segment", "FY2024", "FY2023"), table.header.map { texts(it).single() })
        assertEquals(2, table.rows.size)
        assertEquals("96,169", texts(table.rows[1][1]).single())
        assertTrue(table.rows[1][0].single().bold)
        assertEquals(MdBlock.Paragraph(listOf(Span("After"))), blocks[2])
    }

    @Test fun `a table that is still arriving is shown as text until its separator row appears`() {
        val blocks = parseMarkdown("| Segment | FY2024 |")
        assertTrue(blocks.single() is MdBlock.Paragraph)
    }

    @Test fun `windows line endings and blank input are handled`() {
        assertEquals(2, parseMarkdown("one\r\n\r\ntwo").size)
        assertTrue(parseMarkdown("").isEmpty())
    }
}
