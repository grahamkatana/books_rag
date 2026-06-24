import { useEffect, useState, useCallback, useRef } from "react";
import { Pencil, Trash2, ShieldCheck, ShieldQuestion, FileText, Loader2, Upload } from "lucide-react";
import { Button } from "./ui/Button";
import { Badge } from "./ui/Badge";
import { Checkbox } from "./ui/Checkbox";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "./ui/Table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "./ui/Dialog";
import PaperEditDialog from "./PaperEditDialog";
import SearchBar from "./SearchBar";
import Pagination from "./Pagination";
import { useSearchAndPaginate } from "../hooks/useSearchAndPaginate";
import { fetchPapers, updatePaper, deletePaper, uploadPaper, UnauthorizedError } from "../api/client";
import { pollJobUntilDone } from "../lib/pollJob";

export default function PapersPage({ onSessionExpired }) {
  const [papers, setPapers] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);

  const [editing, setEditing] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deletePdf, setDeletePdf] = useState(false);
  const [deleteError, setDeleteError] = useState(null);
  const [deletingIds, setDeletingIds] = useState(new Set());

  const [uploadStatus, setUploadStatus] = useState(null);
  const fileInputRef = useRef(null);

  const {
    query, setQuery, page, setPage, totalPages, totalCount, pageSize, items: pagedPapers,
  } = useSearchAndPaginate(papers, { searchFields: ["title", "authors", "source_key", "doi"], pageSize: 10 });

  const load = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      setPapers(await fetchPapers());
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
      await updatePaper(editing.id, fields);
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
    const paper = deleteTarget;
    setDeleteError(null);
    try {
      const { task_id } = await deletePaper(paper.id, { deletePdf });
      setDeleteTarget(null);
      setDeletingIds((prev) => new Set(prev).add(paper.id));
      try {
        await pollJobUntilDone(task_id);
        await load();
      } finally {
        setDeletingIds((prev) => {
          const next = new Set(prev);
          next.delete(paper.id);
          return next;
        });
      }
    } catch (err) {
      if (err instanceof UnauthorizedError) onSessionExpired();
      else setDeleteError(err.message);
    }
  };

  const handleFileSelected = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;

    setUploadStatus({ phase: "uploading", text: `Uploading ${file.name}...` });
    try {
      const { task_id, source_key } = await uploadPaper(file);
      setUploadStatus({ phase: "processing", text: `Processing "${source_key}" -- this runs the full pipeline (DOI lookup, Docling chunking, embedding)...` });
      await pollJobUntilDone(task_id, { timeoutMs: 10 * 60 * 1000 });
      setUploadStatus({ phase: "done", text: `"${source_key}" ingested successfully.` });
      await load();
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        onSessionExpired();
        return;
      }
      setUploadStatus({ phase: "error", text: err.message });
    }
  };

  return (
    <div className="flex-1 overflow-y-auto thin-scrollbar p-6">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold text-foreground">Papers</h1>
          <p className="text-sm text-muted-foreground">
            Deleting a paper runs as a background job -- its Qdrant vectors, chunk file, and
            database row are all cleaned up together, not just the row.
          </p>
        </div>
        <Button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploadStatus?.phase === "uploading" || uploadStatus?.phase === "processing"}
          className="shrink-0 gap-1.5"
        >
          <Upload className="h-3.5 w-3.5" />
          Upload paper
        </Button>
        <input ref={fileInputRef} type="file" accept=".pdf" className="hidden" onChange={handleFileSelected} />
      </div>

      {uploadStatus && (
        <p
          className={
            "mb-4 flex items-center gap-2 text-sm rounded-md px-3 py-2 " +
            (uploadStatus.phase === "error"
              ? "text-destructive bg-destructive/10"
              : uploadStatus.phase === "done"
              ? "text-emerald-700 bg-emerald-50"
              : "text-foreground bg-accent")
          }
        >
          {(uploadStatus.phase === "uploading" || uploadStatus.phase === "processing") && (
            <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" />
          )}
          {uploadStatus.text}
        </p>
      )}

      {loadError && (
        <p className="mb-4 text-sm text-destructive bg-destructive/10 rounded-md px-3 py-2">{loadError}</p>
      )}

      <div className="mb-4">
        <SearchBar value={query} onChange={setQuery} placeholder="Search by title, author, filename, or DOI..." />
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
              <TableHead>Venue</TableHead>
              <TableHead>Bibliography</TableHead>
              <TableHead className="w-20" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {pagedPapers.map((p) => {
              const isDeleting = deletingIds.has(p.id);
              return (
                <TableRow key={p.id} className={isDeleting ? "opacity-50" : undefined}>
                  <TableCell className="font-medium text-foreground">
                    <div className="flex items-center gap-2">
                      <FileText className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                      {p.title}
                    </div>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{p.authors || "—"}</TableCell>
                  <TableCell className="text-muted-foreground">{p.year || "—"}</TableCell>
                  <TableCell className="text-muted-foreground">{p.venue || "—"}</TableCell>
                  <TableCell>
                    {p.bibliography_verified ? (
                      <Badge variant="accent" className="gap-1">
                        <ShieldCheck className="h-3 w-3" /> Verified
                      </Badge>
                    ) : (
                      <Badge variant="secondary" className="gap-1">
                        <ShieldQuestion className="h-3 w-3" />
                        {p.bibliography_source === "doi_lookup" ? "Auto (DOI)" : "Unverified"}
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
                        <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => { setFormError(null); setEditing(p); }}>
                          <Pencil className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-7 w-7 text-destructive hover:text-destructive"
                          onClick={() => { setDeleteError(null); setDeletePdf(false); setDeleteTarget(p); }}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    )}
                  </TableCell>
                </TableRow>
              );
            })}
            {pagedPapers.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                  {query ? "No papers match your search." : "No papers yet -- upload one, or run the papers ingestion pipeline."}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}

      <Pagination page={page} totalPages={totalPages} totalCount={totalCount} pageSize={pageSize} onPageChange={setPage} />

      <PaperEditDialog
        open={!!editing}
        onOpenChange={(open) => !open && setEditing(null)}
        paper={editing}
        onSubmit={submitEdit}
        isSubmitting={isSubmitting}
        error={formError}
      />

      <Dialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete paper</DialogTitle>
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
            Also remove the original PDF from pdfs/papers/
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
