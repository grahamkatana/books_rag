import { CheckCircle2, AlertTriangle, XCircle, HelpCircle, OctagonAlert } from "lucide-react";

// Deliberate color mapping, not arbitrary: green only for a genuinely
// clear "supported" -- partially_supported gets amber (it's a real,
// distinct middle category, not a lesser shade of "yes"), contradicted
// gets red as the one verdict that needs real attention, and
// unverifiable gets neutral gray since it's an absence of evidence,
// not a finding either way. "error" gets its own distinct treatment
// (not folded into unverifiable's fallback) since it means something
// different: the verification call itself broke (a rate limit, a
// quota), not that the agent looked and found nothing -- conflating
// the two would hide a real failure behind what looks like a normal,
// low-information result.
const VERDICT_STYLES = {
  supported: { label: "Supported", icon: CheckCircle2, className: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  partially_supported: { label: "Partially supported", icon: AlertTriangle, className: "bg-amber-50 text-amber-700 border-amber-200" },
  contradicted: { label: "Contradicted", icon: XCircle, className: "bg-red-50 text-red-700 border-red-200" },
  unverifiable: { label: "Unverifiable", icon: HelpCircle, className: "bg-gray-100 text-gray-600 border-gray-200" },
  error: { label: "Verification failed", icon: OctagonAlert, className: "bg-red-50 text-red-800 border-red-300 border-dashed" },
};

const CONFIDENCE_LABELS = { high: "High confidence", medium: "Medium confidence", low: "Low confidence" };

export default function VerdictBadge({ verdict, confidence }) {
  const style = VERDICT_STYLES[verdict] || VERDICT_STYLES.unverifiable;
  const Icon = style.icon;

  return (
    <span className="inline-flex items-center gap-2">
      <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium ${style.className}`}>
        <Icon className="h-3 w-3" />
        {style.label}
      </span>
      {confidence && (
        <span className="text-xs text-muted-foreground">{CONFIDENCE_LABELS[confidence] || confidence}</span>
      )}
    </span>
  );
}
