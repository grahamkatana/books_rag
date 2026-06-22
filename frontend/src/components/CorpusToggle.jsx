import { BookOpen, FileText, Layers } from "lucide-react";
import { cn } from "../lib/utils";

const OPTIONS = [
  { value: "books", label: "Books", icon: BookOpen },
  { value: "papers", label: "Papers", icon: FileText },
  { value: "both", label: "Both", icon: Layers },
];

export default function CorpusToggle({ value, onChange, disabled }) {
  return (
    <div className="inline-flex items-center rounded-md border border-input bg-background p-0.5 h-8">
      {OPTIONS.map(({ value: optionValue, label, icon: Icon }) => (
        <button
          key={optionValue}
          type="button"
          disabled={disabled}
          onClick={() => onChange(optionValue)}
          className={cn(
            "flex items-center gap-1.5 rounded-sm px-2.5 h-7 text-xs font-medium transition-colors",
            value === optionValue
              ? "bg-accent text-accent-foreground"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          <Icon className="h-3.5 w-3.5" />
          {label}
        </button>
      ))}
    </div>
  );
}
