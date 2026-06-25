import { useEffect, useState, useCallback, useRef } from "react";
import { Upload, FileText, Loader2, AlertCircle, CheckCircle2, Trash2, LogOut, ShieldCheck } from "lucide-react";
import { Button } from "./ui/Button";
import { Badge } from "./ui/Badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "./ui/Dialog";
import { fetchDocuments, fetchDocument, uploadDocument, deleteDocument, UnauthorizedError } from "../api/client";
import { pollDocumentUntilDone } from "../lib/pollDocument";
import DocumentViewer from "./DocumentViewer";

const STATUS_LABELS = {
  uploaded: "Queued",
  converting: "Converting...",
  extracting_claims: "Extracting claims...",
  verifying: "Verifying claims...",
  done: "Done",
  failed: "Failed",
};

function StatusBadge({ status }) {
  if (status === "done") {
    return (
      <Badge variant="accent" className="gap-1">
        <CheckCircle2 className="h-3 w-3" /> Done
      </Badge>
    );
  }
  if (status === "failed") {
    return (
      <Badge variant="destructive" className="gap-1">
        <AlertCircle className="h-3 w-3" /> Failed
      </Badge>
    );
  }
  return (
    <Badge variant="secondary" className="gap-1">
      <Loader2 className="h-3 w-3 animate-spin" /> {STATUS_LABELS[status] || status}
    </Badge>
  );
}

export default function VerifyApp({ user, onLogout, onSessionExpired }) {
  const [documents, setDocuments] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);

  const [selectedId, setSelectedId] = useState(null);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const [uploadStatus, setUploadStatus] = useState(null);
  const fileInputRef = useRef(null);

  const [deleteTarget, setDeleteTarget] = useState(null);
  const [deleteError, setDeleteError] = useState(null);

  const handleError = useCallback((err) => {
    if (err instanceof UnauthorizedError) onSessionExpired();
    else setLoadError(err.message);
  }, [onSessionExpired]);

  const loadDocuments = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      setDocuments(await fetchDocuments());
    } catch (err) {
      handleError(err);
    } finally {
      setIsLoading(false);
    }
  }, [handleError]);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  const selectDocument = async (id) => {
    setSelectedId(id);
    setDetailLoading(true);
    try {
      setSelectedDoc(await fetchDocument(id));
    } catch (err) {
      handleError(err);
    } finally {
      setDetailLoading(false);
    }
  };

  const handleFileSelected = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;

    setUploadStatus({ phase: "uploading", text: `Uploading ${file.name}...` });
    try {
      const { source_key } = await uploadDocument(file);
      const documentId = Number(source_key);
      setUploadStatus({ phase: "processing", text: `Verifying "${file.name}"...` });
      await loadDocuments();
      selectDocument(documentId);

      const finished = await pollDocumentUntilDone(documentId);
      setUploadStatus(
        finished.status === "failed"
          ? { phase: "error", text: finished.error_message || "Verification failed." }
          : { phase: "done", text: `"${file.name}" verified.` }
      );
      await loadDocuments();
      selectDocument(documentId); // show the result of what was just uploaded, regardless of what else might be selected by now
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        onSessionExpired();
        return;
      }
      setUploadStatus({ phase: "error", text: err.message });
    }
  };

  const confirmDelete = async () => {
    const doc = deleteTarget;
    setDeleteError(null);
    try {
      await deleteDocument(doc.id);
      setDeleteTarget(null);
      if (selectedId === doc.id) {
        setSelectedId(null);
        setSelectedDoc(null);
      }
      await loadDocuments();
    } catch (err) {
      if (err instanceof UnauthorizedError) onSessionExpired();
      else setDeleteError(err.message);
    }
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <aside className="w-72 shrink-0 border-r border-border bg-muted/40 flex flex-col">
        <div className="flex items-center gap-2 px-4 py-4 border-b border-border">
          <ShieldCheck className="h-5 w-5 text-primary" />
          <span className="text-sm font-semibold text-foreground">Book RAG Verify</span>
        </div>

        <div className="p-3">
          <Button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploadStatus?.phase === "uploading" || uploadStatus?.phase === "processing"}
            className="w-full gap-1.5"
          >
            <Upload className="h-3.5 w-3.5" />
            Upload document
          </Button>
          <input ref={fileInputRef} type="file" accept=".docx" className="hidden" onChange={handleFileSelected} />
        </div>

        {uploadStatus && (
          <p
            className={
              "mx-3 mb-2 flex items-center gap-2 text-xs rounded-md px-2.5 py-2 " +
              (uploadStatus.phase === "error"
                ? "text-destructive bg-destructive/10"
                : uploadStatus.phase === "done"
                ? "text-emerald-700 bg-emerald-50"
                : "text-foreground bg-accent")
            }
          >
            {(uploadStatus.phase === "uploading" || uploadStatus.phase === "processing") && (
              <Loader2 className="h-3 w-3 animate-spin shrink-0" />
            )}
            <span className="leading-snug">{uploadStatus.text}</span>
          </p>
        )}

        {loadError && (
          <p className="mx-3 mb-2 text-xs text-destructive bg-destructive/10 rounded-md px-2.5 py-2">{loadError}</p>
        )}

        <div className="flex-1 overflow-y-auto thin-scrollbar px-2 space-y-1">
          {isLoading ? (
            <p className="px-2 py-3 text-xs text-muted-foreground">Loading...</p>
          ) : documents.length === 0 ? (
            <p className="px-2 py-3 text-xs text-muted-foreground">No documents yet -- upload one to get started.</p>
          ) : (
            documents.map((doc) => (
              <button
                key={doc.id}
                onClick={() => selectDocument(doc.id)}
                className={
                  "w-full flex flex-col gap-1 rounded-md px-2.5 py-2 text-left transition-colors " +
                  (selectedId === doc.id ? "bg-accent" : "hover:bg-accent/60")
                }
              >
                <span className="flex items-center gap-1.5 text-sm font-medium text-foreground truncate">
                  <FileText className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <span className="truncate">{doc.filename}</span>
                </span>
                <span className="flex items-center justify-between">
                  <StatusBadge status={doc.status} />
                  <span className="text-xs text-muted-foreground">{doc.claim_count} claim{doc.claim_count === 1 ? "" : "s"}</span>
                </span>
              </button>
            ))
          )}
        </div>

        {user && (
          <div className="border-t border-border p-3 flex items-center justify-between">
            <span className="text-xs text-muted-foreground truncate" title={user.email}>
              {user.email}
            </span>
            <button onClick={onLogout} title="Log out" className="shrink-0 rounded-sm p-1 text-muted-foreground hover:bg-accent">
              <LogOut className="h-3.5 w-3.5" />
            </button>
          </div>
        )}
      </aside>

      <main className="flex-1 overflow-hidden flex flex-col">
        {!selectedId ? (
          <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
            Select a document, or upload a new one.
          </div>
        ) : detailLoading ? (
          <p className="p-6 text-sm text-muted-foreground">Loading...</p>
        ) : selectedDoc ? (
          <>
            <div className="flex items-start justify-between gap-4 px-6 py-4 border-b border-border shrink-0">
              <div>
                <h1 className="text-lg font-semibold text-foreground">{selectedDoc.filename}</h1>
                <div className="mt-1"><StatusBadge status={selectedDoc.status} /></div>
              </div>
              <Button
                variant="ghost"
                size="icon"
                className="text-destructive hover:text-destructive"
                onClick={() => { setDeleteError(null); setDeleteTarget(selectedDoc); }}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>

            {selectedDoc.error_message && (
              <p
                className={
                  "mx-6 mt-4 text-sm rounded-md px-3 py-2 shrink-0 " +
                  (selectedDoc.status === "failed"
                    ? "text-destructive bg-destructive/10"
                    : "text-amber-700 bg-amber-50")
                }
              >
                {selectedDoc.error_message}
              </p>
            )}

            {selectedDoc.claims.length === 0 ? (
              <p className="p-6 text-sm text-muted-foreground">
                {selectedDoc.status === "done"
                  ? "No checkable claims were found in this document."
                  : "Claims will appear here as they're extracted and verified."}
              </p>
            ) : !selectedDoc.markdown ? (
              // Status is still converting/extracting -- markdown isn't
              // ready yet, so there's nothing to annotate against. Fall
              // back to the same flat list a still-running document
              // already showed before DocumentViewer existed.
              <div className="flex-1 overflow-y-auto thin-scrollbar p-6 space-y-3 max-w-2xl mx-auto w-full">
                {selectedDoc.claims.map((claim) => (
                  <div key={claim.id} className="rounded-lg border border-border p-3">
                    <p className="text-sm text-foreground mb-1.5">{claim.text}</p>
                    <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                      <Loader2 className="h-3 w-3 animate-spin" /> Verifying...
                    </span>
                  </div>
                ))}
              </div>
            ) : (
              <div className="flex-1 overflow-hidden">
                <DocumentViewer markdown={selectedDoc.markdown} claims={selectedDoc.claims} />
              </div>
            )}
          </>
        ) : null}
      </main>

      <Dialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete document</DialogTitle>
            <DialogDescription>
              This permanently deletes "{deleteTarget?.filename}" and everything verified from it. This can't be undone.
            </DialogDescription>
          </DialogHeader>
          {deleteError && (
            <p className="text-sm text-destructive bg-destructive/10 rounded-md px-3 py-2">{deleteError}</p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button variant="destructive" onClick={confirmDelete}>Delete</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
