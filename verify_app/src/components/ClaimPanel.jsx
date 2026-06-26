import { X, Loader2, CheckCircle2, XCircle, OctagonAlert } from "lucide-react";
import { Button } from "./ui/Button";
import VerdictBadge from "./VerdictBadge";

function CrossCheckSection({ crossCheck }) {
  if (!crossCheck) return null;

  const AgreeIcon = crossCheck.agrees ? CheckCircle2 : XCircle;
  const agreeColor = crossCheck.agrees ? "text-emerald-600" : "text-amber-600";

  return (
    <div className="space-y-2 pt-3 border-t border-border">
      <p className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground uppercase tracking-wide">
        Cross-check ({crossCheck.model})
      </p>
      <div className="flex items-center gap-1.5">
        <AgreeIcon className={`h-4 w-4 shrink-0 ${agreeColor}`} />
        <span className={`text-sm font-medium ${agreeColor}`}>{crossCheck.agrees ? "Agrees" : "Disagrees"}</span>
        <span className="text-xs text-muted-foreground">-- its own verdict:</span>
      </div>
      <VerdictBadge verdict={crossCheck.verdict} confidence={crossCheck.confidence} />
      <p className="text-sm text-muted-foreground">{crossCheck.explanation}</p>
      {!crossCheck.is_checkable_claim && (
        <p className="flex items-start gap-1.5 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-md px-2.5 py-2">
          <OctagonAlert className="h-3.5 w-3.5 shrink-0 mt-0.5" />
          The cross-check model judges this isn't actually an externally-checkable claim at all.
        </p>
      )}
    </div>
  );
}

export default function ClaimPanel({ claim, onClose, overlay = false }) {
  if (!claim) return null;

  return (
    <aside
      className={
        "w-96 shrink-0 bg-card flex flex-col " +
        (overlay
          ? "fixed right-0 top-0 h-full border-l border-border shadow-2xl z-50"
          : "h-full border-l border-border")
      }
    >
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h2 className="text-sm font-semibold text-foreground">Claim</h2>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto thin-scrollbar p-4 space-y-4">
        <p className="text-sm text-foreground italic border-l-2 border-border pl-3">{claim.text}</p>

        {!claim.verification ? (
          <span className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <Loader2 className="h-3.5 w-3.5 animate-spin" /> Verifying...
          </span>
        ) : (
          <>
            <VerdictBadge verdict={claim.verification.verdict} confidence={claim.verification.confidence} />
            <p className="text-sm text-muted-foreground">{claim.verification.explanation}</p>

            {claim.verification.evidence.length > 0 && (
              <div className="space-y-3 pt-2 border-t border-border">
                <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide">Evidence</p>
                {claim.verification.evidence.map((ev, i) => (
                  <div key={i} className="text-sm border-l-2 border-border pl-3">
                    <p className="font-medium text-foreground">
                      {ev.title}
                      {ev.locator ? `, ${ev.locator}` : ""}
                    </p>
                    {ev.web_url && (
                      <a href={ev.web_url} target="_blank" rel="noreferrer" className="text-xs text-primary underline">
                        {ev.web_url}
                      </a>
                    )}
                    <p className="text-muted-foreground mt-1">{ev.excerpt}</p>
                  </div>
                ))}
              </div>
            )}

            <CrossCheckSection crossCheck={claim.verification.cross_check} />
          </>
        )}
      </div>
    </aside>
  );
}
