import { useState } from "react";
import { Button } from "./ui/Button";
import MultiSelect from "./MultiSelect";

export default function ChatInput({ onSend, disabled, books, selectedSources, onSourcesChange }) {
  const [value, setValue] = useState("");

  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  };

  return (
    <div className="border-t border-border bg-background px-4 py-3">
      <div className="max-w-2xl mx-auto mb-2">
        <MultiSelect
          books={books}
          selectedSources={selectedSources}
          onChange={onSourcesChange}
          disabled={disabled}
        />
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
