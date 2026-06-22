import sys
sys.path.insert(0, ".")

from app.retrieval.citations import (
    paper_author_citation_label, format_apa_paper, render_citation,
    full_apa_reference_paper, build_locator,
)
from app.models.paper import Paper

# --- APA's real multi-author in-text rule: 1 -> surname, 2 -> "A & B", 3+ -> "A et al." ---
assert paper_author_citation_label(Paper(source_key="p1", title="Solo Paper", authors="Becker, F.")) == "Becker"
assert paper_author_citation_label(Paper(source_key="p2", title="Two", authors="Becker, F.; Sergeyuk, A.")) == "Becker & Sergeyuk"
assert paper_author_citation_label(
    Paper(source_key="p3", title="Five", authors="Becker, F.; Sergeyuk, A.; Titov, A.; Eliseeva, A.; Bryksin, T.")
) == "Becker et al."
assert paper_author_citation_label(Paper(source_key="p4", title="No Authors Known")) == "No Authors Known"
print("paper_author_citation_label assertions passed.")

p = Paper(source_key="p3", title="Five Authors",
          authors="Becker, F.; Sergeyuk, A.; Titov, A.; Eliseeva, A.; Bryksin, T.", year=2026)
assert format_apa_paper(p, "p. 12") == "(Becker et al., 2026, p. 12)"
assert format_apa_paper(p, None) == "(Becker et al., 2026)"
assert format_apa_paper(None, "p. 12", fallback_source="unknown-paper") == "(unknown-paper, n.d.)"
print("format_apa_paper assertions passed.")

# --- locator: real page first, section-name fallback when no page exists at all ---
assert build_locator({"printed_page": "7"}) == "p. 7"
assert build_locator({"section": "Related Work"}) == '"Related Work" section'
assert build_locator({"printed_page": None, "section": "Methodology"}) == '"Methodology" section'
assert build_locator({}) is None
print("build_locator section-fallback assertions passed.")

# --- render_citation dispatches correctly between Book/Paper/None ---
rendered = render_citation({"source": "p3", "printed_page": "12"}, p)
assert rendered.apa_text == "(Becker et al., 2026, p. 12)"
assert rendered.paper is p
assert rendered.book is None

rendered_none = render_citation({"source": "some-key"}, None)
assert rendered_none.apa_text == "(some-key, n.d.)"
assert rendered_none.book is None and rendered_none.paper is None
print("render_citation dispatch assertions passed.")

# --- full reference: the double-period bug a real test caught and fixed ---
ref = full_apa_reference_paper(p)
assert ref == "Becker, F., Sergeyuk, A., Titov, A., Eliseeva, A., & Bryksin, T. (2026). Five Authors.", \
    f"double-period regression: {ref!r}"

p.venue = "ICSE 2026"
p.doi = "10.1145/3744916.3787811"
ref2 = full_apa_reference_paper(p)
assert ref2 == ("Becker, F., Sergeyuk, A., Titov, A., Eliseeva, A., & Bryksin, T. (2026). "
                 "Five Authors. ICSE 2026. https://doi.org/10.1145/3744916.3787811")

ref3 = full_apa_reference_paper(Paper(source_key="p5", title="Anonymous Report", year=2020))
assert ref3 == "Anonymous Report. (2020)."
print("full_apa_reference_paper assertions passed (including the double-period regression).")

print("\nAll paper citation assertions passed.")