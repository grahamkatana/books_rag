/**
 * Sanitizes streamed message content for markdown rendering.
 *
 * The model emits real markdown (bold, lists, etc.) with citations
 * embedded as "<CITATION>apa text</CITATION>" tags -- react-markdown
 * (with rehype-raw) renders both correctly when "citation" is overridden
 * in the components prop, INCLUDING handling an unclosed tag gracefully
 * on its own (verified: it doesn't swallow unrelated content after an
 * unclosed tag, even across paragraph breaks).
 *
 * But while a message is still streaming, a delta chunk can land mid-tag
 * -- e.g. content ending in "...the risk.<CITAT" for a moment before the
 * rest of the tag arrives -- and rehype-raw's graceful-but-imperfect
 * handling of that briefly renders the partial tag's raw text inside a
 * citation badge until the closing tag shows up. This trims a trailing,
 * not-yet-complete "<CITATION" prefix of any length before rendering, so
 * that flash never happens at all; the citation appears cleanly once the
 * closing tag arrives and the full content re-renders.
 */
const OPEN_TAG = "<CITATION>";

function trimTrailingPartialTag(text) {
  const fullIdx = text.indexOf("<CITATION");
  if (fullIdx !== -1) {
    return text.slice(0, fullIdx);
  }
  const maxLen = Math.min(OPEN_TAG.length - 1, text.length);
  for (let len = maxLen; len > 0; len--) {
    if (text.slice(-len) === OPEN_TAG.slice(0, len)) {
      return text.slice(0, text.length - len);
    }
  }
  return text;
}

export function sanitizeStreamingContent(content) {
  const CITATION_RE = /<CITATION>(.*?)<\/CITATION>/gs;
  let lastIndex = 0;
  let match;
  while ((match = CITATION_RE.exec(content)) !== null) {
    lastIndex = match.index + match[0].length;
  }
  const head = content.slice(0, lastIndex);
  const trailing = trimTrailingPartialTag(content.slice(lastIndex));
  return head + trailing;
}

/** Strips <CITATION> tags entirely, leaving just the prose -- used for
 * copy-to-clipboard, where the raw tags would be visual noise. */
export function stripCitationTags(content) {
  return content.replace(/<CITATION>.*?<\/CITATION>/gs, "").replace(/\s{2,}/g, " ").trim();
}
