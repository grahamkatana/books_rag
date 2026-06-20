import { ChevronDown, X, Library } from "lucide-react";
import { Popover, PopoverTrigger, PopoverContent } from "./ui/Popover";
import { Checkbox } from "./ui/Checkbox";
import { Badge } from "./ui/Badge";
import { Button } from "./ui/Button";
import { cn } from "../lib/utils";

export default function MultiSelect({ books, selectedSources, onChange, disabled }) {
  const toggle = (sourceKey) => {
    if (selectedSources.includes(sourceKey)) {
      onChange(selectedSources.filter((s) => s !== sourceKey));
    } else {
      onChange([...selectedSources, sourceKey]);
    }
  };

  const selectedBooks = books.filter((b) => selectedSources.includes(b.source_key));

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          size="sm"
          disabled={disabled}
          className="h-8 max-w-full justify-between font-normal text-muted-foreground"
        >
          <span className="flex items-center gap-1.5 overflow-hidden">
            <Library className="h-3.5 w-3.5 shrink-0" />
            {selectedBooks.length === 0 ? (
              <span>All books</span>
            ) : (
              <span className="flex gap-1 overflow-hidden">
                {selectedBooks.slice(0, 2).map((b) => (
                  <Badge key={b.id} variant="accent" className="shrink-0">
                    {b.title.length > 24 ? b.title.slice(0, 24) + "…" : b.title}
                  </Badge>
                ))}
                {selectedBooks.length > 2 && (
                  <Badge variant="secondary" className="shrink-0">
                    +{selectedBooks.length - 2}
                  </Badge>
                )}
              </span>
            )}
          </span>
          <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>

      <PopoverContent className="w-72 p-0">
        <div className="flex items-center justify-between border-b border-border px-3 py-2">
          <span className="text-xs font-medium text-muted-foreground">Scope to books</span>
          {selectedSources.length > 0 && (
            <button
              onClick={() => onChange([])}
              className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              <X className="h-3 w-3" /> Clear
            </button>
          )}
        </div>

        <div className="max-h-64 overflow-y-auto thin-scrollbar p-1">
          {books.length === 0 && (
            <p className="px-2 py-3 text-xs text-muted-foreground">No books in the library yet.</p>
          )}
          {books.map((book) => {
            const checked = selectedSources.includes(book.source_key);
            return (
              <label
                key={book.id}
                className={cn(
                  "flex cursor-pointer items-start gap-2 rounded-sm px-2 py-1.5 text-sm hover:bg-accent"
                )}
              >
                <Checkbox
                  checked={checked}
                  onCheckedChange={() => toggle(book.source_key)}
                  className="mt-0.5"
                />
                <span className="flex flex-col">
                  <span className="leading-tight">{book.title}</span>
                  {book.edition && (
                    <span className="text-xs text-muted-foreground">{book.edition}</span>
                  )}
                </span>
              </label>
            );
          })}
        </div>
      </PopoverContent>
    </Popover>
  );
}
