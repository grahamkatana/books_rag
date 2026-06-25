import { X, Loader2 } from "lucide-react";
import { Button } from "./ui/Button";
import VerdictBadge from "./VerdictBadge";

export default function ClaimPanel({ claim, onClose }) {
  if (!claim) return null;

  return (
    <aside className="w-96 shrink-0 border-l border-border bg-card h-full flex flex-col">
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
          </>
        )}
      </div>
    </aside>
  );
}
