package com.graham_katana.bookrag.feature.chat

import org.junit.Assert.assertEquals
import org.junit.Test

class CitationsTest {
    @Test fun `citations become numbered markers and the same reference keeps its number`() {
        val answer = renderAnswer("Risk is priced.<CITATION>Hull (2018).</CITATION> Markets differ <CITATION>Fama (1970).</CITATION> and again<CITATION>Hull (2018).</CITATION>.")
        assertEquals("Risk is priced. [1] Markets differ [2] and again [1].", answer.text)
        assertEquals(listOf("Hull (2018).", "Fama (1970)."), answer.references)
    }

    @Test fun `text with no citations is left alone`() {
        assertEquals(RenderedAnswer("**Bold** and 2 < 3.", emptyList()), renderAnswer("**Bold** and 2 < 3."))
    }

    @Test fun `a tag still arriving is held back at every length`() {
        val full = "Done.<CITATION>Hull (2018).</CITATION>"
        for (cut in "Done.".length until full.length) {
            assertEquals("cut at $cut", RenderedAnswer("Done.", emptyList()), renderAnswer(full.substring(0, cut)))
        }
        assertEquals(RenderedAnswer("Done. [1]", listOf("Hull (2018).")), renderAnswer(full))
    }

    @Test fun `a reference that spans lines is still one reference`() {
        assertEquals(listOf("Hull, J.\n(2018)."), renderAnswer("A<CITATION>Hull, J.\n(2018).</CITATION>").references)
    }
}
