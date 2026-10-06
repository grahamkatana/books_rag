package com.graham_katana.bookrag.feature.chat

/**
 * An answer ready to show: its text with each citation replaced by a numbered
 * marker, and the reference each number stands for ([references]`[0]` is `[1]`).
 */
data class RenderedAnswer(val text: String, val references: List<String>)

private const val OPEN_TAG = "<CITATION>"
private val CITATION = Regex("""<CITATION>(.*?)</CITATION>""", RegexOption.DOT_MATCHES_ALL)

/**
 * The model writes citations inline as `<CITATION>APA text</CITATION>`. A phone has
 * no room for the reference in the sentence, so each becomes `[n]` and the same
 * reference always gets the same number.
 *
 * While the answer is still arriving, the text can end part-way through a tag
 * (`...the risk.<CITAT`). That unfinished tail is held back, so raw tag text never
 * flashes on screen; it appears as a marker once the closing tag arrives.
 */
fun renderAnswer(raw: String): RenderedAnswer {
    val references = mutableListOf<String>()
    val text = StringBuilder()
    var last = 0
    for (match in CITATION.findAll(raw)) {
        text.append(raw, last, match.range.first)
        val reference = match.groupValues[1].trim()
        val number = references.indexOf(reference).takeIf { it >= 0 } ?: references.apply { add(reference) }.lastIndex
        if (text.isNotEmpty() && !text.last().isWhitespace()) text.append(' ')
        text.append('[').append(number + 1).append(']')
        last = match.range.last + 1
    }
    text.append(withoutUnfinishedTag(raw.substring(last)))
    return RenderedAnswer(text.toString(), references)
}

private fun withoutUnfinishedTag(tail: String): String {
    val opened = tail.indexOf("<CITATION")
    if (opened >= 0) return tail.substring(0, opened)
    for (length in minOf(OPEN_TAG.length - 1, tail.length) downTo 1) {
        if (tail.endsWith(OPEN_TAG.substring(0, length))) return tail.dropLast(length)
    }
    return tail
}
