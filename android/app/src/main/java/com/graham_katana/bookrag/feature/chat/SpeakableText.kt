package com.graham_katana.bookrag.feature.chat

/**
 * Turns an answer written in Markdown into text that sounds right when it is read aloud: no asterisks or
 * pound signs, no [Source 2] or [3] citation markers, links read as their words, table rows as short
 * comma-separated sentences, and code blocks left out.
 */
fun speakable(markdown: String): String {
    var t = markdown
    t = Regex("(?s)<CITATION>.*?</CITATION>").replace(t, " ")
    t = Regex("(?s)<CITATION.*$").replace(t, " ") // an unfinished tag while the answer is still arriving
    t = Regex("<(?:C(?:I(?:T(?:A(?:T(?:I(?:O)?)?)?)?)?)?)?$").replace(t, "") // or only the start of one
    t = Regex("(?s)```.*?```").replace(t, " ")
    t = Regex("(?s)```.*$").replace(t, " ") // an unfinished code block
    t = Regex("""\[\s*Sources?\s*\d+(?:\s*(?:,|;|and|&)\s*(?:Sources?\s*)?\d+)*\s*]""", RegexOption.IGNORE_CASE).replace(t, "")
    t = Regex("""\[\d+(?:\s*[,–-]\s*\d+)*]""").replace(t, "")
    t = Regex("""\[([^\]]+)]\([^)]*\)""").replace(t, "$1")
    t = Regex("""https?://\S+""").replace(t, "")
    return t.lines().mapNotNull { speakableLine(it) }.joinToString("\n")
}

private val TABLE_RULE = Regex("""^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?$""")
private val SENTENCE_END = Regex("""[.!?:;]["')\]”’]*(?=\s)|\n""")

private fun speakableLine(raw: String): String? {
    var s = raw.trim()
    if (s.isEmpty() || TABLE_RULE.matches(s)) return null
    s = s.replace(Regex("""^#{1,6}\s*"""), "")
    s = s.replace(Regex("""^[-*+•]\s+"""), "")
    if (s.contains('|')) s = s.trim('|').split('|').map { it.trim() }.filter { it.isNotEmpty() }.joinToString(", ")
    s = s.replace(Regex("""\*\*(.+?)\*\*"""), "$1").replace(Regex("""__(.+?)__"""), "$1")
    s = s.replace(Regex("""(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])"""), "$1")
    s = s.replace("`", "").replace(Regex("""\s+"""), " ").replace(Regex("""\s+([.,;:!?])"""), "$1").trim()
    if (s.isEmpty()) return null
    val core = s.trimEnd('"', '\'', ')', ']', '”', '’')
    return if (core.lastOrNull() in ".!?:;".toList()) s else "$s."
}

/**
 * The next piece of [text] (already run through [speakable]) that is safe to say, after the first [spoken]
 * characters, and the new count of characters spoken. While the answer is still arriving ([final] false)
 * only whole sentences are returned, so the voice never stops mid-sentence waiting for the rest.
 */
fun nextChunk(text: String, spoken: Int, final: Boolean): Pair<String, Int>? {
    val from = spoken.coerceIn(0, text.length)
    if (from >= text.length) return null
    val tail = text.substring(from)
    if (final) return tail.trim().takeIf { it.isNotEmpty() }?.let { it to text.length }
    val end = SENTENCE_END.findAll(tail).lastOrNull()?.range?.last?.plus(1) ?: return null
    val chunk = tail.substring(0, end).trim()
    return if (chunk.isEmpty()) null else chunk to (from + end)
}

/** Remembers how much of one streaming answer has been handed to the voice, and starts over for a new answer. */
class SpeechFeed {
    private var id = Long.MIN_VALUE
    private var spoken = 0

    fun next(messageId: Long, markdown: String, done: Boolean): String? {
        if (messageId != id) { id = messageId; spoken = 0 }
        val (chunk, now) = nextChunk(speakable(markdown), spoken, done) ?: return null
        spoken = now
        return chunk
    }

    fun reset() { id = Long.MIN_VALUE; spoken = 0 }
}

/** Splits [text] into pieces no longer than [max], at spaces, because speech engines refuse very long input. */
fun pieces(text: String, max: Int = 3000): List<String> {
    val out = mutableListOf<String>()
    var rest = text.trim()
    while (rest.length > max) {
        val cut = rest.lastIndexOf(' ', max).takeIf { it > 0 } ?: max
        out += rest.substring(0, cut).trim()
        rest = rest.substring(cut).trim()
    }
    if (rest.isNotEmpty()) out += rest
    return out
}
