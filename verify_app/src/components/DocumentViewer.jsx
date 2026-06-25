import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { FileQuestion } from "lucide-react";
import { annotateMarkdown } from "../lib/annotateMarkdown";
import ClaimPanel from "./ClaimPanel";

// Lighter, background-only treatment than VerdictBadge's standalone
// chips -- these sit inline in running prose, so they need to read as
// "highlighted text" first and "a verdict" second, not compete with
// the sentence around them. "pending" (no verification yet) gets a
// neutral blue rather than any of the four real verdict colors, since
// it isn't a finding at all yet.
const HIGHLIGHT_CLASSES = {
  supported: "bg-emerald-100/70 hover:bg-emerald-200/70",
  partially_supported: "bg-amber-100/70 hover:bg-amber-200/70",
  contradicted: "bg-red-100/70 hover:bg-red-200/70",
  unverifiable: "bg-gray-200/50 hover:bg-gray-300/50",
  error: "bg-red-100/70 hover:bg-red-200/70 ring-1 ring-red-300",
  pending: "bg-blue-100/50 hover:bg-blue-200/50",
};

export default function DocumentViewer({ markdown, claims }) {
  const [selectedClaimId, setSelectedClaimId] = useState(null);

  const { annotated, matchedIds } = useMemo(
    () => annotateMarkdown(markdown || "", claims),
    [markdown, claims]
  );

  const claimsById = useMemo(() => new Map(claims.map((c) => [c.id, c])), [claims]);
  const unmatchedClaims = claims.filter((c) => !matchedIds.has(c.id));
  const selectedClaim = selectedClaimId != null ? claimsById.get(selectedClaimId) : null;

  return (
    <div className="flex h-full">
      <div className="flex-1 overflow-y-auto thin-scrollbar">
        <div className="prose prose-sm max-w-2xl mx-auto py-6 px-4">
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeRaw]}
            components={{
              mark: ({ node, ...props }) => {
                const claimId = Number(props["data-claim-id"]);
                const verdict = props["data-verdict"] || "pending";
                return (
                  <mark
                    className={`cursor-pointer rounded px-0.5 not-italic transition-colors ${HIGHLIGHT_CLASSES[verdict] || HIGHLIGHT_CLASSES.pending}`}
                    onClick={() => setSelectedClaimId(claimId)}
                  >
                    {props.children}
                  </mark>
                );
              },
            }}
          >
            {annotated}
          </ReactMarkdown>

          {unmatchedClaims.length > 0 && (
            <div className="mt-8 pt-6 border-t border-border not-prose">
              <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground mb-3">
                <FileQuestion className="h-3.5 w-3.5" />
                {unmatchedClaims.length} more claim{unmatchedClaims.length === 1 ? "" : "s"} couldn't be matched to an
                exact spot in the text
              </p>
              <div className="space-y-2">
                {unmatchedClaims.map((claim) => (
                  <button
                    key={claim.id}
                    onClick={() => setSelectedClaimId(claim.id)}
                    className="w-full text-left text-sm rounded-md border border-border px-3 py-2 hover:bg-accent/60 transition-colors"
                  >
                    {claim.text}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {selectedClaim && <ClaimPanel claim={selectedClaim} onClose={() => setSelectedClaimId(null)} />}
    </div>
  );
}
