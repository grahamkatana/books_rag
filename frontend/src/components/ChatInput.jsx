import { useState } from "react";
import { Button } from "./ui/Button";
import MultiSelect from "./MultiSelect";
import CorpusToggle from "./CorpusToggle";

export default function ChatInput({
  onSend, disabled, books, papers,
  selectedSources, onSourcesChange,
  corpus, onCorpusChange,
}) {
  const [value, setValue] = useState("");

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  };

  const handleCorpusChange = (next) => {
    onCorpusChange(next);
    onSourcesChange([]); // the available items differ per corpus -- a stale selection from the other one wouldn't make sense
  };

  return (
    <div className="border-t border-border bg-background px-4 py-3">
      <div className="max-w-2xl mx-auto mb-2 flex items-center gap-2">
        <CorpusToggle value={corpus} onChange={handleCorpusChange} disabled={disabled} />

        {/* Scoping to specific sources only makes sense within a single
            corpus -- with "both" selected there's no one list to pick
            from, so the picker steps aside rather than show something
            confusing. */}
        {corpus !== "both" && (
          <MultiSelect
            items={corpus === "papers" ? papers : books}
            selectedSources={selectedSources}
            onChange={onSourcesChange}
            disabled={disabled}
            label={corpus === "papers" ? "papers" : "books"}
          />
        )}
      </div>

      <div className="flex items-end gap-2 max-w-2xl mx-auto">
        <textarea
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder="Ask the library a question..."
          rows={1}
          className="flex-1 resize-none rounded-md border border-input bg-background px-3 py-2 text-[15px] shadow-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        <Button onClick={submit} disabled={disabled || !value.trim()}>
          Send
        </Button>
      </div>
    </div>
  );
}
