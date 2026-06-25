"""
Cross-checks a document's claim verifications using a different model
provider (Claude/Anthropic) than the primary verification agent
(OpenAI) -- an independent second opinion on whether each verdict
actually follows from the evidence it cited. See
app/agents/cross_check_claim.py for the full reasoning.

Runs synchronously, in this process -- deliberately not enqueued via
Celery, since this is a manual dev/grounding tool you're running and
watching directly. The same operation is also available as
cross_check_document_task in app/worker/tasks.py for whenever this
gets wired into the API/UI.

Requires ANTHROPIC_API_KEY to be set.

Usage:
    uv run python scripts/cross_check_verification.py --document-id 7
    uv run python scripts/cross_check_verification.py --document-id 7 --verdicts contradicted supported
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.agents.cross_check_claim import cross_check_document, REVIEWABLE_VERDICTS


def main():
    parser = argparse.ArgumentParser(
        description="Cross-check a document's claim verifications using Claude as an independent second opinion."
    )
    parser.add_argument("--document-id", type=int, required=True)
    parser.add_argument(
        "--verdicts", nargs="+", choices=REVIEWABLE_VERDICTS, default=None,
        help=f"Only cross-check claims with these verdicts (default: all of {REVIEWABLE_VERDICTS})",
    )
    args = parser.parse_args()

    print(f"Document {args.document_id}: cross-checking "
          f"{'all reviewable verdicts' if not args.verdicts else ', '.join(args.verdicts)}...")

    result = cross_check_document(args.document_id, verdicts_to_check=args.verdicts)

    if "error" in result:
        print(f"Could not cross-check: {result['error']}")
        return

    print(f"Done. Checked {result['checked']}: {result['agreed']} agreed, {result['disagreed']} disagreed, "
          f"{result['flagged_not_checkable']} flagged as not actually checkable claims.")


if __name__ == "__main__":
    main()