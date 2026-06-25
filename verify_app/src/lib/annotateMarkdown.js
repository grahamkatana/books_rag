/**
 * Finds each claim's exact text within the raw markdown and wraps the
 * first occurrence in a <mark> tag carrying its claim id and verdict,
 * ready to be rendered as real HTML via rehype-raw. Claims whose text
 * can't be found verbatim (the model didn't quote it character-for-
 * character despite being instructed to, or markdown conversion
 * introduced whitespace differences) are simply left unmatched -- not
 * highlighted inline, but never dropped: the caller still has the full
 * claims list to fall back to, this only decides whether a claim gets
 * an inline highlight, not whether it's visible at all.
 *
 * Exact substring matching only, deliberately -- a fuzzy-matching
 * fallback would risk highlighting the wrong span of text, which is
 * worse than not highlighting at all for a feature whose entire point
 * is precision about exactly what was checked.
 */
export function annotateMarkdown(markdown, claims) {
  const found = [];
  for (const claim of claims) {
    if (!claim.text) continue;
    const start = markdown.indexOf(claim.text);
    if (start !== -1) {
      found.push({ claim, start, end: start + claim.text.length });
    }
  }

  // Sort by position, then drop anything that overlaps an
  // already-accepted match -- two claims should never legitimately
  // overlap, but if extraction ever produces one that's a substring of
  // another, this avoids generating malformed nested <mark> tags. The
  // dropped one keeps showing in the fallback list, same as any other
  // unmatched claim -- it isn't lost, just not inline-highlighted.
  found.sort((a, b) => a.start - b.start);
  const accepted = [];
  let cursor = -1;
  for (const m of found) {
    if (m.start >= cursor) {
      accepted.push(m);
      cursor = m.end;
    }
  }

  let html = "";
  let pos = 0;
  for (const { claim, start, end } of accepted) {
    html += markdown.slice(pos, start);
    const verdict = claim.verification ? claim.verification.verdict : "pending";
    html += `<mark data-claim-id="${claim.id}" data-verdict="${verdict}">${markdown.slice(start, end)}</mark>`;
    pos = end;
  }
  html += markdown.slice(pos);

  const matchedIds = new Set(accepted.map((m) => m.claim.id));
  return { annotated: html, matchedIds };
}
