package com.graham_katana.bookrag.feature.chat

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class SpeakableTextTest {
    @Test fun `markdown and citation markers are removed`() {
        val md = "## Summary\nNet sales were **\$391.0 billion** [Source 2, Source 3].\n- iPhone rose [1].\n- Services rose [2, 3]."
        assertEquals("Summary.\nNet sales were \$391.0 billion.\niPhone rose.\nServices rose.", speakable(md))
    }

    @Test fun `table rows become short sentences and the rule row is dropped`() {
        assertEquals("Segment, Sales.\niPhone, 201.", speakable("| Segment | Sales |\n|---|---|\n| iPhone | 201 |"))
    }

    @Test fun `links are read as their words and bare addresses are dropped`() {
        assertEquals("See the 10-K now.", speakable("See [the 10-K](https://example.com/a) now https://example.com/b"))
    }

    @Test fun `code blocks and unfinished ones are left out`() {
        assertEquals("Use this:\nDone.", speakable("Use this:\n```kotlin\nval a = 1\n```\nDone."))
        assertEquals("Done.", speakable("Done.\n```kotlin\nval a"))
    }

    @Test fun `citation tags are left out, finished or not`() {
        assertEquals("The risk is high.", speakable("The risk is high.<CITATION>Smith (2020). Title.</CITATION>"))
        assertEquals("The risk is high.", speakable("The risk is high.<CITATI"))
    }

    @Test fun `arithmetic asterisks and snake case stay`() {
        assertEquals("5 * 3 * 2 = 30.", speakable("5 * 3 * 2 = 30"))
        assertEquals("Call fetch_data now.", speakable("Call fetch_data now"))
    }

    @Test fun `only whole sentences are spoken while the answer streams`() {
        val feed = SpeechFeed()
        assertNull(feed.next(1, "First point", false))
        assertEquals("First point.", feed.next(1, "First point. Second is half wri", false))
        assertNull(feed.next(1, "First point. Second is half written", false))
        assertEquals("Second is done.", feed.next(1, "First point. Second is done. Third", false))
        assertEquals("Third", feed.next(1, "First point. Second is done. Third", true)?.trimEnd('.'))
        assertNull(feed.next(1, "First point. Second is done. Third", true))
    }

    @Test fun `decimals are not sentence ends`() {
        assertEquals("Sales were 391.0 billion.", SpeechFeed().next(1, "Sales were 391.0 billion. Next", false))
    }

    @Test fun `a new answer starts from the beginning`() {
        val feed = SpeechFeed()
        feed.next(1, "One. Two.", true)
        assertEquals("Fresh start.", feed.next(2, "Fresh start.", true))
    }

    @Test fun `a final call says everything left`() {
        assertEquals("No full stop here.", SpeechFeed().next(5, "No full stop here", true))
    }

    @Test fun `long text is split at spaces`() {
        val parts = pieces("word ".repeat(1000), max = 100)
        assertEquals(true, parts.all { it.length <= 100 })
        assertEquals("word ".repeat(1000).trim(), parts.joinToString(" "))
    }
}
