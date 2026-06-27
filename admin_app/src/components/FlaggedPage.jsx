import { useEffect, useState, useCallback } from "react";
import { Trash2, ShieldCheck, ShieldAlert, Loader2, BookOpen, FileText, Flag } from "lucide-react";
import { Button } from "./ui/Button";
import { Badge } from "./ui/Badge";
import { Checkbox } from "./ui/Checkbox";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "./ui/Table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "./ui/Dialog";
import {
  fetchCorpusContextChecks, setMarkedForDelete, deleteBook, deletePaper, UnauthorizedError,
} from "../api/client";
import { pollJobUntilDone } from "../lib/pollJob";

// scripts/check_corpus_context.py is what actually populates this list
// -- this page is purely a review-and-act surface for what that script
// already found, never a trigger for running it (it's a deliberately
// manual, periodic admin tool, not something meant to run from a
// button click here).
export default function FlaggedPage({ onSessionExpired }) {
  const [checks, setChecks] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);

  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deletePdf, setDeletePdf] = useState(false);
  const [deleteError, setDeleteError] = useState(null);
  const [deletingIds, setDeletingIds] = useState(new Set());

  const handleError = useCallback((err) => {
    if (err instanceof UnauthorizedError) onSessionExpired();
    else setLoadError(err.message);
  }, [onSessionExpired]);

  const load = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      const data = await fetchCorpusContextChecks();
      // Flagged items first, most-recently-checked first within each group --
      // the actionable candidates should be the first thing seen, not buried
      // among everything that already checked out fine.
      data.sort((a, b) => {
        if (a.marked_for_delete !== b.marked_for_delete) return a.marked_for_delete ? -1 : 1;
        return new Date(b.checked_at) - new Date(a.checked_at);
      });
      setChecks(data);
    } catch (err) {
      handleError(err);
    } finally {
      setIsLoading(false);
    }
  }, [handleError]);

  useEffect(() => {
    load();
  }, [load]);

  const toggleFlag = async (check) => {
    const checkKey = check.id;
    setChecks((prev) => prev.map((c) => (c.id === checkKey ? { ...c, marked_for_delete: !c.marked_for_delete } : c)));
    try {
      await setMarkedForDelete(check.id, !check.marked_for_delete);
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        onSessionExpired();
        return;
      }
      // Revert on failure -- the optimistic flip above was wrong if the request didn't actually succeed.
      setChecks((prev) => prev.map((c) => (c.id === checkKey ? { ...c, marked_for_delete: check.marked_for_delete } : c)));
      setLoadError(err.message);
    }
  };

  const confirmDelete = async () => {
    const check = deleteTarget;
    setDeleteError(null);
    try {
      const deleteFn = check.item_type === "book" ? deleteBook : deletePaper;
      const { task_id } = await deleteFn(check.item_id, { deletePdf });
      setDeleteTarget(null);
      setDeletingIds((prev) => new Set(prev).add(check.id));
      try {
        await pollJobUntilDone(task_id);
        await load();
      } finally {
        setDeletingIds((prev) => {
          const next = new Set(prev);
          next.delete(check.id);
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
        <h1 className="text-lg font-semibold text-foreground">Flagged for Review</h1>
        <p className="text-sm text-muted-foreground">
          From the last run of <code className="text-xs">check_corpus_context.py</code> -- whether the corpus's own
          retrieved content for each book/paper actually conveys what it's about, the same sense-check as asking a
          chat "what's this about?" Deleting here calls the exact same book/paper delete endpoints as their own pages.
        </p>
      </div>

      {loadError && (
        <p className="mb-4 text-sm text-destructive bg-destructive/10 rounded-md px-3 py-2">{loadError}</p>
      )}

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-10" />
              <TableHead>Title</TableHead>
              <TableHead>Type</TableHead>
              <TableHead>Context</TableHead>
              <TableHead>Why</TableHead>
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {checks.map((check) => {
              const isDeleting = deletingIds.has(check.id);
              return (
                <TableRow key={check.id} className={isDeleting ? "opacity-50" : undefined}>
                  <TableCell>
                    <Checkbox
                      checked={check.marked_for_delete}
                      onCheckedChange={() => toggleFlag(check)}
                      disabled={isDeleting}
                      title="Flagged for deletion -- toggle to remove from the candidate list without deleting anything"
                    />
                  </TableCell>
                  <TableCell className="font-medium text-foreground">{check.title}</TableCell>
                  <TableCell>
                    <Badge variant="secondary" className="gap-1">
                      {check.item_type === "book" ? <BookOpen className="h-3 w-3" /> : <FileText className="h-3 w-3" />}
                      {check.item_type}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {check.context_known ? (
                      <Badge variant="accent" className="gap-1">
                        <ShieldCheck className="h-3 w-3" /> Known
                      </Badge>
                    ) : (
                      <Badge variant="destructive" className="gap-1">
                        <ShieldAlert className="h-3 w-3" /> Unknown
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell className="text-muted-foreground max-w-xs truncate" title={check.explanation}>
                    {check.explanation || "—"}
                  </TableCell>
                  <TableCell>
                    {isDeleting ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                    ) : (
                      <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-destructive hover:text-destructive"
                        onClick={() => { setDeleteError(null); setDeletePdf(false); setDeleteTarget(check); }}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
            {checks.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                  <Flag className="h-4 w-4 mx-auto mb-2 opacity-50" />
                  No checks yet -- run <code className="text-xs">check_corpus_context.py</code> to populate this list.
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}

      <Dialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete {deleteTarget?.item_type}</DialogTitle>
            <DialogDescription>
              This permanently deletes "{deleteTarget?.title}" -- its Qdrant vectors, chunk file, and database row.
              This can't be undone.
            </DialogDescription>
          </DialogHeader>
          {deleteError && (
            <p className="text-sm text-destructive bg-destructive/10 rounded-md px-3 py-2">{deleteError}</p>
          )}
          <label className="flex items-center gap-2 cursor-pointer text-sm text-foreground">
            <Checkbox checked={deletePdf} onCheckedChange={setDeletePdf} />
            Also remove the original PDF
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
