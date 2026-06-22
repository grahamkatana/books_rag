import { X, TriangleAlert } from "lucide-react";
import { Button } from "./ui/Button";

export default function CitationPanel({ citation, book, paper, onClose }) {
  if (!citation) return null;

  // A citation resolves to at most one of these, mirroring the backend's
  // own Citation model -- book_id and paper_id are mutually exclusive.
  const source = paper || book;
  const verified = source?.bibliography_verified;

  return (
    <aside className="w-80 shrink-0 border-l border-border bg-card h-full flex flex-col">
      <div className="flex items-center justify-between px-4 py-3 border-b border-border">
        <h2 className="text-sm font-semibold text-foreground">Source</h2>
        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={onClose} title="Close">
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="p-4 space-y-3 overflow-y-auto thin-scrollbar">
        <p className="text-sm text-foreground font-medium">{citation.apa_text}</p>

        {citation.locator && (
          <p className="text-xs text-muted-foreground">Location: {citation.locator}</p>
        )}

        {book && (
          <div className="mt-4 pt-4 border-t border-border space-y-1">
            <p className="text-sm font-semibold text-foreground">{book.title}</p>
            {book.authors && (
              <p className="text-xs text-muted-foreground">
                {book.authors}
                {book.is_editor ? " (Ed.)" : ""}
              </p>
            )}
            {book.publisher && (
              <p className="text-xs text-muted-foreground">
                {book.publisher}
                {book.year ? `, ${book.year}` : ""}
              </p>
            )}
            {book.edition && <p className="text-xs text-muted-foreground/70">{book.edition}</p>}
          </div>
        )}

        {paper && (
          <div className="mt-4 pt-4 border-t border-border space-y-1">
            <p className="text-sm font-semibold text-foreground">{paper.title}</p>
            {paper.authors && (
              <p className="text-xs text-muted-foreground">{paper.authors}</p>
            )}
            {(paper.venue || paper.year) && (
              <p className="text-xs text-muted-foreground">
                {paper.venue}
                {paper.venue && paper.year ? ", " : ""}
                {paper.year}
              </p>
            )}
            {paper.doi && (
              <a
                href={`https://doi.org/${paper.doi}`}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-primary hover:underline break-all"
              >
                doi.org/{paper.doi}
              </a>
            )}
            {paper.abstract && (
              <p className="text-xs text-muted-foreground/80 mt-2 leading-relaxed">
                {paper.abstract}
              </p>
            )}
          </div>
        )}

        {source && !verified && (
          <p className="flex items-center gap-1.5 text-xs text-amber-600 mt-2">
            <TriangleAlert className="h-3.5 w-3.5 shrink-0" />
            Bibliographic data not yet verified against the source
          </p>
        )}
      </div>
    </aside>
  );
}
