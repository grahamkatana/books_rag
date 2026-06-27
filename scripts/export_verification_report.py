"""
Exports a verification document's full report as a single, readable
Markdown file: the document's own markdown with each matched claim
marked inline (so a claim's surrounding context is visible, not just
the claim text in isolation), followed by every claim's verdict,
confidence, explanation, and evidence in full.

Built specifically so the pipeline's actual output can be checked by
hand against an independent reference -- reading the live UI claim by
claim works, but a single flat file is what you actually want to diff
against your own notes or hand to someone else for review.

The inline-matching logic deliberately mirrors verify_app's own
annotateMarkdown.js exactly: exact substring matching only (a fuzzy
match risks marking the wrong span, which is worse than not marking
one at all), first occurrence only, overlapping matches resolved by
keeping whichever comes first in the text. Claims that can't be found
verbatim in the markdown aren't dropped -- they still get their own
full section below, just without an inline marker pointing at a
specific spot in the prose.

Usage:
    uv run python scripts/export_verification_report.py --document-id 7
    uv run python scripts/export_verification_report.py --latest
    uv run python scripts/export_verification_report.py --document-id 7 --output my_report.md
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.session import get_session
from app.models.verification import VerificationDocument
from app.api.v1.serializers import verification_document_to_detail_dict

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "verification_reports"

VERDICT_LABELS = {
    "supported": "SUPPORTED",
    "partially_supported": "PARTIALLY SUPPORTED",
    "contradicted": "CONTRADICTED",
    "unverifiable": "UNVERIFIABLE",
    "error": "VERIFICATION FAILED",
}


def find_claim_matches(markdown: str, claims: list[dict]) -> list[dict]:
    """Same algorithm as verify_app's annotateMarkdown.js, in Python:
    exact substring match, first occurrence, drop anything that
    overlaps an already-accepted match (keeping whichever comes first
    in the text). Returns only the claims that matched, each with its
    start/end character offsets."""
    found = []
    for claim in claims:
        text = claim.get("text")
        if not text:
            continue
        start = markdown.find(text)
        if start != -1:
            found.append({"claim": claim, "start": start, "end": start + len(text)})

    found.sort(key=lambda m: m["start"])
    accepted = []
    cursor = -1
    for m in found:
        if m["start"] >= cursor:
            accepted.append(m)
            cursor = m["end"]
    return accepted


def build_annotated_markdown(markdown: str, claims: list[dict]) -> tuple[str, set]:
    """Wraps each matched claim's first occurrence in **bold** plus a
    footnote-style marker (e.g. [^3]) pointing at its full writeup
    further down the report. Returns the annotated text and the set of
    claim ids that were actually matched, so the caller knows which
    claims still need their own "couldn't be matched" note."""
    matches = find_claim_matches(markdown, claims)
    matched_ids = {m["claim"]["id"] for m in matches}

    pieces = []
    pos = 0
    for m in matches:
        pieces.append(markdown[pos:m["start"]])
        claim_id = m["claim"]["id"]
        pieces.append(f"**{markdown[m['start']:m['end']]}**[^{claim_id}]")
        pos = m["end"]
    pieces.append(markdown[pos:])
    return "".join(pieces), matched_ids


def format_evidence(evidence: list[dict]) -> str:
    if not evidence:
        return "*(no evidence cited)*"
    lines = []
    for i, e in enumerate(evidence, start=1):
        source = e.get("title") or "(untitled source)"
        if e.get("locator"):
            source += f", {e['locator']}"
        line = f"{i}. **{source}**"
        if e.get("web_url"):
            line += f" — [{e['web_url']}]({e['web_url']})"
        lines.append(line)
        if e.get("excerpt"):
            lines.append(f"   > {e['excerpt']}")
    return "\n".join(lines)


def format_cross_check(cross_check: dict | None) -> str:
    if cross_check is None:
        return ""

    agree_label = "AGREES" if cross_check["agrees"] else "DISAGREES"
    lines = [
        "",
        f"**Cross-check ({cross_check['model']}): {agree_label}** "
        f"-- its own verdict: {VERDICT_LABELS.get(cross_check['verdict'], cross_check['verdict'].upper())} "
        f"({cross_check['confidence']} confidence)",
        f"> {cross_check['explanation']}",
    ]
    if not cross_check["is_checkable_claim"]:
        lines.append("")
        lines.append("**⚠ Flagged: the cross-check model judges this isn't actually an externally-checkable claim at all.**")
    return "\n".join(lines)


def format_claim_section(claim: dict, matched: bool) -> str:
    verification = claim.get("verification")
    header = f"### Claim {claim['id']}"
    if not matched:
        header += " *(not found verbatim in the document text -- not inline-marked above)*"

    lines = [header, "", f"> {claim['text']}", ""]

    if verification is None:
        lines.append("**Status:** still pending -- not yet verified.")
        return "\n".join(lines)

    verdict_label = VERDICT_LABELS.get(verification["verdict"], verification["verdict"].upper())
    lines.append(f"**Verdict:** {verdict_label}  ({verification['confidence']} confidence)")
    lines.append("")
    lines.append(f"**Explanation:** {verification['explanation']}")
    lines.append("")
    lines.append("**Evidence:**")
    lines.append(format_evidence(verification.get("evidence", [])))
    cross_check_text = format_cross_check(verification.get("cross_check"))
    if cross_check_text:
        lines.append(cross_check_text)
    return "\n".join(lines)


def build_report(doc_dict: dict) -> str:
    markdown = doc_dict.get("markdown") or ""
    claims = doc_dict.get("claims", [])

    annotated, matched_ids = build_annotated_markdown(markdown, claims)

    verified_count = sum(1 for c in claims if c.get("verification") is not None)
    cross_checks = [
        c["verification"]["cross_check"] for c in claims
        if c.get("verification") and c["verification"].get("cross_check")
    ]

    sections = [
        f"# Verification Report: {doc_dict['filename']}",
        "",
        f"- **Document ID:** {doc_dict['id']}",
        f"- **Status:** {doc_dict['status']}",
        f"- **Created:** {doc_dict.get('created_at') or 'unknown'}",
        f"- **Claims:** {len(claims)} total, {verified_count} verified, "
        f"{len(matched_ids)} matched to a specific spot in the text",
    ]
    if cross_checks:
        disagreements = sum(1 for cc in cross_checks if not cc["agrees"])
        not_checkable = sum(1 for cc in cross_checks if not cc["is_checkable_claim"])
        sections.append(
            f"- **Cross-checked:** {len(cross_checks)} claim(s), {disagreements} disagreement(s), "
            f"{not_checkable} flagged as not actually checkable"
        )
    if doc_dict.get("error_message"):
        sections.append(f"- **Note:** {doc_dict['error_message']}")
    sections += ["", "---", "", "## Annotated Document", "", annotated, "", "---", "", "## Claims & Verdicts", ""]

    if not claims:
        sections.append("*No checkable claims were extracted from this document.*")
    else:
        for claim in claims:
            sections.append(format_claim_section(claim, claim["id"] in matched_ids))
            sections.append("")

    return "\n".join(sections)


def main():
    parser = argparse.ArgumentParser(description="Export a verification document's full report as a Markdown file.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--document-id", type=int, help="The VerificationDocument id to export")
    group.add_argument("--latest", action="store_true", help="Export the most recently created verification document")
    parser.add_argument("--output", type=str, default=None,
                         help=f"Output file path (default: {DEFAULT_OUTPUT_DIR}/<id>_<filename>.md)")
    args = parser.parse_args()

    with get_session() as session:
        if args.latest:
            doc = session.query(VerificationDocument).order_by(VerificationDocument.created_at.desc()).first()
            if doc is None:
                print("No verification documents exist yet.")
                return
        else:
            doc = session.get(VerificationDocument, args.document_id)
            if doc is None:
                print(f"No verification document with id {args.document_id}.")
                return

        doc_dict = verification_document_to_detail_dict(doc)

    report = build_report(doc_dict)

    if args.output:
        output_path = Path(args.output)
    else:
        DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        safe_stem = Path(doc_dict["filename"]).stem.replace(" ", "_")
        output_path = DEFAULT_OUTPUT_DIR / f"{doc_dict['id']}_{safe_stem}.md"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report, encoding="utf-8")
    print(f"Wrote report for document {doc_dict['id']} ({doc_dict['filename']}) to {output_path}")


if __name__ == "__main__":
    main()