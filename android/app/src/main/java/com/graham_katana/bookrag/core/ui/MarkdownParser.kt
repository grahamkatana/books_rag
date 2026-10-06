package com.graham_katana.bookrag.core.ui

/**
 * A deliberately small markdown reader for answers: headings, paragraphs,
 * bullet and numbered lists, tables, and **bold** / *italic* / `code` inside
 * text. Pure Kotlin so it can be unit tested. An unfinished marker (the answer
 * is still streaming in) is shown as plain text, never as a broken style.
 */
data class Span(val text: String, val bold: Boolean = false, val italic: Boolean = false, val code: Boolean = false)

sealed interface MdBlock {
    data class Heading(val level: Int, val spans: List<Span>) : MdBlock
    data class Paragraph(val spans: List<Span>) : MdBlock
    data class Bullets(val items: List<List<Span>>) : MdBlock
    data class Numbered(val items: List<List<Span>>) : MdBlock
    data class Table(val header: List<List<Span>>, val rows: List<List<List<Span>>>) : MdBlock
}

private val HEADING = Regex("""^(#{1,6})\s+(.*)$""")
private val BULLET = Regex("""^\s*[-*+]\s+(.*)$""")
private val NUMBERED = Regex("""^\s*\d+[.)]\s+(.*)$""")
private val TABLE_SEPARATOR = Regex("""^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$""")

fun parseMarkdown(text: String): List<MdBlock> {
    val lines = text.replace("\r\n", "\n").split("\n")
    val blocks = mutableListOf<MdBlock>()
    val paragraph = mutableListOf<String>()
    fun flushParagraph() {
        if (paragraph.isNotEmpty()) blocks += MdBlock.Paragraph(parseInline(paragraph.joinToString("\n")))
        paragraph.clear()
    }

    var i = 0
    while (i < lines.size) {
        val line = lines[i]
        val heading = HEADING.matchEntire(line)
        when {
            line.isBlank() -> { flushParagraph(); i++ }
            heading != null -> {
                flushParagraph()
                blocks += MdBlock.Heading(heading.groupValues[1].length, parseInline(heading.groupValues[2].trim()))
                i++
            }
            line.trimStart().startsWith("|") && i + 1 < lines.size && TABLE_SEPARATOR.matches(lines[i + 1]) -> {
                flushParagraph()
                val header = cells(line)
                i += 2
                val rows = mutableListOf<List<List<Span>>>()
                while (i < lines.size && lines[i].trimStart().startsWith("|")) rows += cells(lines[i++])
                blocks += MdBlock.Table(header, rows)
            }
            BULLET.matches(line) -> {
                flushParagraph()
                val items = mutableListOf<List<Span>>()
                while (i < lines.size && BULLET.matches(lines[i])) items += parseInline(BULLET.matchEntire(lines[i++])!!.groupValues[1])
                blocks += MdBlock.Bullets(items)
            }
            NUMBERED.matches(line) -> {
                flushParagraph()
                val items = mutableListOf<List<Span>>()
                while (i < lines.size && NUMBERED.matches(lines[i])) items += parseInline(NUMBERED.matchEntire(lines[i++])!!.groupValues[1])
                blocks += MdBlock.Numbered(items)
            }
            else -> { paragraph += line; i++ }
        }
    }
    flushParagraph()
    return blocks
}

private fun cells(row: String): List<List<Span>> =
    row.trim().removePrefix("|").removeSuffix("|").split("|").map { parseInline(it.trim()) }

fun parseInline(text: String): List<Span> {
    val spans = mutableListOf<Span>()
    val plain = StringBuilder()
    fun flushPlain() {
        if (plain.isNotEmpty()) spans += Span(plain.toString())
        plain.clear()
    }
    var i = 0
    while (i < text.length) {
        val rest = text.substring(i)
        when {
            rest.startsWith("**") -> {
                val end = text.indexOf("**", i + 2)
                if (end > i + 2) { flushPlain(); spans += Span(text.substring(i + 2, end), bold = true); i = end + 2 } else { plain.append("**"); i += 2 }
            }
            rest.startsWith("`") -> {
                val end = text.indexOf('`', i + 1)
                if (end > i + 1) { flushPlain(); spans += Span(text.substring(i + 1, end), code = true); i = end + 1 } else { plain.append('`'); i++ }
            }
            // "*" is italic only when it hugs the text ("*word*"), so "5 * 3" stays arithmetic.
            rest.startsWith("*") && i + 1 < text.length && !text[i + 1].isWhitespace() -> {
                val end = text.indexOf('*', i + 1)
                if (end > i + 1 && !text[end - 1].isWhitespace()) { flushPlain(); spans += Span(text.substring(i + 1, end), italic = true); i = end + 1 } else { plain.append('*'); i++ }
            }
            else -> { plain.append(text[i]); i++ }
        }
    }
    flushPlain()
    return spans
}
