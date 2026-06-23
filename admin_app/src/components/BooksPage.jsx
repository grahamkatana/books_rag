import { useEffect, useState, useCallback } from "react";
import { Pencil, Trash2, ShieldCheck, ShieldQuestion, BookOpen, Loader2 } from "lucide-react";
import { Button } from "./ui/Button";
import { Badge } from "./ui/Badge";
import { Checkbox } from "./ui/Checkbox";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "./ui/Table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "./ui/Dialog";
import BookEditDialog from "./BookEditDialog";
import SearchBar from "./SearchBar";
import Pagination from "./Pagination";
import { useSearchAndPaginate } from "../hooks/useSearchAndPaginate";
import { fetchBooks, updateBook, deleteBook, UnauthorizedError } from "../api/client";
import { pollJobUntilDone } from "../lib/pollJob";

export default function BooksPage({ onSessionExpired }) {
  const [books, setBooks] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);

  const [editing, setEditing] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deletePdf, setDeletePdf] = useState(false);
  const [deleteError, setDeleteError] = useState(null);
  // A Set of book ids currently mid-delete (job enqueued, awaiting the
  // poll result) -- lets each row show its own "Deleting..." state
  // independently, since a delete here is a background job, not
  // something that finishes by the time the request returns.
  const [deletingIds, setDeletingIds] = useState(new Set());

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

  const confirmDelete = async () => {
    const book = deleteTarget;
    setDeleteError(null);
    try {
      const { task_id } = await deleteBook(book.id, { deletePdf });
      setDeleteTarget(null);
      setDeletingIds((prev) => new Set(prev).add(book.id));
      try {
        await pollJobUntilDone(task_id);
        await load();
      } finally {
        setDeletingIds((prev) => {
          const next = new Set(prev);
          next.delete(book.id);
          return next;
        });
      }
    } catch (err) {
      if (err instanceof UnauthorizedError) onSessionExpired();
      else setDeleteError(err.message);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto thin-scrollbar p-6">
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-foreground">Books</h1>
        <p className="text-sm text-muted-foreground">
          Deleting a book runs as a background job -- its Qdrant vectors, chunk file, and
          database row are all cleaned up together, not just the row.
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
              <TableHead className="w-20" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {pagedBooks.map((b) => {
              const isDeleting = deletingIds.has(b.id);
              return (
                <TableRow key={b.id} className={isDeleting ? "opacity-50" : undefined}>
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
                    {isDeleting ? (
                      <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                        <Loader2 className="h-3.5 w-3.5 animate-spin" /> Deleting...
                      </span>
                    ) : (
                      <div className="flex items-center gap-1">
                        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => { setFormError(null); setEditing(b); }}>
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-destructive hover:text-destructive"
                          onClick={() => { setDeleteError(null); setDeletePdf(false); setDeleteTarget(b); }}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
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

      <Dialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete book</DialogTitle>
            <DialogDescription>
              This permanently deletes "{deleteTarget?.title}" -- its Qdrant vectors, chunk file,
              and database row. This can't be undone.
            </DialogDescription>
          </DialogHeader>
          {deleteError && (
            <p className="text-sm text-destructive bg-destructive/10 rounded-md px-3 py-2">{deleteError}</p>
          )}
          <label className="flex items-center gap-2 cursor-pointer text-sm text-foreground">
            <Checkbox checked={deletePdf} onCheckedChange={setDeletePdf} />
            Also remove the original PDF from pdfs/books/
          </label>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button variant="destructive" onClick={confirmDelete}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
