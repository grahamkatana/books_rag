import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { FileQuestion, Maximize2, Minimize2, Info } from "lucide-react";
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

export default function DocumentViewer({
  markdown,
  claims,
  documentContext,
  isPresentationMode = false,
  onTogglePresentationMode,
}) {
  const [selectedClaimId, setSelectedClaimId] = useState(null);

  const { annotated, matchedIds } = useMemo(
    () => annotateMarkdown(markdown || "", claims),
    [markdown, claims]
  );

  const claimsById = useMemo(() => new Map(claims.map((c) => [c.id, c])), [claims]);
  const unmatchedClaims = claims.filter((c) => !matchedIds.has(c.id));
  const selectedClaim = selectedClaimId != null ? claimsById.get(selectedClaimId) : null;

  // Presentation mode widens the reading column and bumps the type up
  // a size, the same two changes that make the most difference for an
  // actual "reader" feel -- everything else about the rendering stays
  // identical, it's still the same annotated document underneath.
  const proseWidth = isPresentationMode ? "max-w-3xl" : "max-w-2xl";
  const proseSize = isPresentationMode ? "prose-base" : "prose-sm";

  return (
    <div className="relative flex h-full">
      {onTogglePresentationMode && (
        <button
          onClick={onTogglePresentationMode}
          title={isPresentationMode ? "Exit presentation mode" : "Presentation mode"}
          className="fixed top-4 right-4 z-50 flex h-8 w-8 items-center justify-center rounded-full bg-card border border-border shadow-sm text-muted-foreground hover:text-foreground hover:bg-accent transition-colors"
        >
          {isPresentationMode ? <Minimize2 className="h-3.5 w-3.5" /> : <Maximize2 className="h-3.5 w-3.5" />}
        </button>
      )}

      <div className="flex-1 overflow-y-auto thin-scrollbar">
        <div className={`prose ${proseSize} ${proseWidth} mx-auto py-6 px-4`}>
          {documentContext && (
            <p className="not-prose flex items-start gap-2 text-xs text-muted-foreground bg-muted/50 border border-border rounded-md px-3 py-2 mb-6">
              <Info className="h-3.5 w-3.5 shrink-0 mt-0.5" />
              {documentContext}
            </p>
          )}

          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeRaw]}
            components={{
              mark: ({ node, ...props }) => {
                const claimId = Number(props["data-claim-id"]);
                const verdict = props["data-verdict"] || "pending";
                const crossChecked = props["data-cross-checked"] === "true";
                return (
                  <mark
                    className={
                      `cursor-pointer rounded px-0.5 not-italic transition-colors ${HIGHLIGHT_CLASSES[verdict] || HIGHLIGHT_CLASSES.pending}` +
                      (crossChecked ? " ring-1 ring-offset-1 ring-violet-400" : "")
                    }
                    title={crossChecked ? "Cross-checked by a second model" : undefined}
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

      {selectedClaim && (
        <ClaimPanel
          claim={selectedClaim}
          onClose={() => setSelectedClaimId(null)}
          overlay={isPresentationMode}
        />
      )}
    </div>
  );
}
