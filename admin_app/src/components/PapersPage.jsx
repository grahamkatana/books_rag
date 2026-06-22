import { useEffect, useState, useCallback } from "react";
import { Pencil, ShieldCheck, ShieldQuestion, FileText } from "lucide-react";
import { Button } from "./ui/Button";
import { Badge } from "./ui/Badge";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "./ui/Table";
import PaperEditDialog from "./PaperEditDialog";
import SearchBar from "./SearchBar";
import Pagination from "./Pagination";
import { useSearchAndPaginate } from "../hooks/useSearchAndPaginate";
import { fetchPapers, updatePaper, UnauthorizedError } from "../api/client";

export default function PapersPage({ onSessionExpired }) {
  const [papers, setPapers] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);

  const [editing, setEditing] = useState(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);

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

  return (
    <div className="flex-1 overflow-y-auto thin-scrollbar p-6">
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-foreground">Papers</h1>
        <p className="text-sm text-muted-foreground">
          Correct bibliography directly -- no delete here, for the same reason as Books: a paper's
          Qdrant vectors and chunk file aren't cleaned up by this yet.
        </p>
      </div>

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
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {pagedPapers.map((p) => (
              <TableRow key={p.id}>
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
                  <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => { setFormError(null); setEditing(p); }}>
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {pagedPapers.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-muted-foreground py-8">
                  {query ? "No papers match your search." : "No papers yet -- run the papers ingestion pipeline first."}
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
    </div>
  );
}
