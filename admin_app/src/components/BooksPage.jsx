import { useEffect, useState, useCallback } from "react";
import { Pencil, ShieldCheck, ShieldQuestion, BookOpen } from "lucide-react";
import { Button } from "./ui/Button";
import { Badge } from "./ui/Badge";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "./ui/Table";
import BookEditDialog from "./BookEditDialog";
import SearchBar from "./SearchBar";
import Pagination from "./Pagination";
import { useSearchAndPaginate } from "../hooks/useSearchAndPaginate";
import { fetchBooks, updateBook, UnauthorizedError } from "../api/client";

export default function BooksPage({ onSessionExpired }) {
  const [books, setBooks] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);

  const [editing, setEditing] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  const {
    query, setQuery, page, setPage, totalPages, totalCount, pageSize, items: pagedBooks,
  } = useSearchAndPaginate(books, { searchFields: ["title", "authors", "source_key"], pageSize: 10 });

  const load = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      setBooks(await fetchBooks());
    } catch (err) {
      if (err instanceof UnauthorizedError) onSessionExpired();
      else setLoadError(err.message);
    } finally {
      setIsLoading(false);
    }
  }, [onSessionExpired]);

  useEffect(() => {
    load();
  }, [load]);

  const submitEdit = async (fields) => {
    setIsSubmitting(true);
    setFormError(null);
    try {
      await updateBook(editing.id, fields);
      setEditing(null);
      await load();
    } catch (err) {
      if (err instanceof UnauthorizedError) onSessionExpired();
      else setFormError(err.message);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto thin-scrollbar p-6">
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-foreground">Books</h1>
        <p className="text-sm text-muted-foreground">
         Bibliography information for all ingested books. You can edit the metadata and bibliography verification status here. To add new books, run the ingestion pipeline from the command line.
        </p>
      </div>

      {loadError && (
        <p className="mb-4 text-sm text-destructive bg-destructive/10 rounded-md px-3 py-2">{loadError}</p>
      )}

      <div className="mb-4">
        <SearchBar value={query} onChange={setQuery} placeholder="Search by title, author, or filename..." />
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Authors</TableHead>
              <TableHead>Year</TableHead>
              <TableHead>Edition</TableHead>
              <TableHead>Bibliography</TableHead>
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {pagedBooks.map((b) => (
              <TableRow key={b.id}>
                <TableCell className="font-medium text-foreground">
                  <div className="flex items-center gap-2">
                    <BookOpen className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                    {b.title}
                  </div>
                </TableCell>
                <TableCell className="text-muted-foreground">{b.authors || "—"}</TableCell>
                <TableCell className="text-muted-foreground">{b.year || "—"}</TableCell>
                <TableCell className="text-muted-foreground">{b.edition || "—"}</TableCell>
                <TableCell>
                  {b.bibliography_verified ? (
                    <Badge variant="accent" className="gap-1">
                      <ShieldCheck className="h-3 w-3" /> Verified
                    </Badge>
                  ) : (
                    <Badge variant="secondary" className="gap-1">
                      <ShieldQuestion className="h-3 w-3" />
                      {b.bibliography_source === "auto_lookup" ? `Auto (${b.lookup_confidence})` : "Unverified"}
                    </Badge>
                  )}
                </TableCell>
                <TableCell>
                  <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => { setFormError(null); setEditing(b); }}>
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {pagedBooks.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                  {query ? "No books match your search." : "No books yet -- run the ingestion pipeline first."}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}

      <Pagination page={page} totalPages={totalPages} totalCount={totalCount} pageSize={pageSize} onPageChange={setPage} />

      <BookEditDialog
        open={!!editing}
        onOpenChange={(open) => !open && setEditing(null)}
        book={editing}
        onSubmit={submitEdit}
        isSubmitting={isSubmitting}
        error={formError}
      />
    </div>
  );
}
