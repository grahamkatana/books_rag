import { useEffect, useState, useCallback } from "react";
import { Eye, Trash2, MessageSquare, User as UserIcon } from "lucide-react";
import { Button } from "./ui/Button";
import { Badge } from "./ui/Badge";
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from "./ui/Table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "./ui/Dialog";
import SearchBar from "./SearchBar";
import Pagination from "./Pagination";
import { useSearchAndPaginate } from "../hooks/useSearchAndPaginate";
import { fetchChats, fetchChat, deleteChat, UnauthorizedError } from "../api/client";

export default function ChatsPage({ onSessionExpired }) {
  const [chats, setChats] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);

  const [viewing, setViewing] = useState(null);
  const [viewError, setViewError] = useState(null);

  const [deleteTarget, setDeleteTarget] = useState(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

  const {
    query, setQuery, page, setPage, totalPages, totalCount, pageSize, items: pagedChats,
  } = useSearchAndPaginate(chats, { searchFields: ["title", "user_email"], pageSize: 10 });

  const load = useCallback(async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      setChats(await fetchChats());
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

  const openView = async (chatSummary) => {
    setViewError(null);
    setViewing({ ...chatSummary, messages: null });
    try {
      const full = await fetchChat(chatSummary.id);
      setViewing(full);
    } catch (err) {
      if (err instanceof UnauthorizedError) onSessionExpired();
      else setViewError(err.message);
    }
  };

  const confirmDelete = async () => {
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await deleteChat(deleteTarget.id);
      setDeleteTarget(null);
      await load();
    } catch (err) {
      if (err instanceof UnauthorizedError) onSessionExpired();
      else setDeleteError(err.message);
    } finally {
      setIsDeleting(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto thin-scrollbar p-6">
      <div className="mb-6">
        <h1 className="text-lg font-semibold text-foreground">Chats</h1>
        <p className="text-sm text-muted-foreground">View or remove any user's conversation, for moderation.</p>
      </div>

      {loadError && (
        <p className="mb-4 text-sm text-destructive bg-destructive/10 rounded-md px-3 py-2">{loadError}</p>
      )}

      <div className="mb-4">
        <SearchBar value={query} onChange={setQuery} placeholder="Search by title or owner email..." />
      </div>

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading...</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Title</TableHead>
              <TableHead>Owner</TableHead>
              <TableHead>Messages</TableHead>
              <TableHead>Created</TableHead>
              <TableHead className="w-20" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {pagedChats.map((c) => (
              <TableRow key={c.id}>
                <TableCell className="font-medium text-foreground">
                  <div className="flex items-center gap-2">
                    <MessageSquare className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                    {c.title || "Untitled chat"}
                  </div>
                </TableCell>
                <TableCell>
                  {c.user_email ? (
                    <span className="flex items-center gap-1 text-sm text-muted-foreground">
                      <UserIcon className="h-3 w-3" /> {c.user_email}
                    </span>
                  ) : (
                    <Badge variant="outline">No owner (CLI)</Badge>
                  )}
                </TableCell>
                <TableCell className="text-muted-foreground">{c.message_count}</TableCell>
                <TableCell className="text-muted-foreground text-xs">
                  {new Date(c.created_at).toLocaleString()}
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-1">
                    <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => openView(c)}>
                      <Eye className="h-3.5 w-3.5" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7 text-destructive hover:text-destructive"
                      onClick={() => { setDeleteError(null); setDeleteTarget(c); }}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {pagedChats.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground py-8">
                  {query ? "No chats match your search." : "No chats yet."}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}

      <Pagination page={page} totalPages={totalPages} totalCount={totalCount} pageSize={pageSize} onPageChange={setPage} />

      <Dialog open={!!viewing} onOpenChange={(open) => !open && setViewing(null)}>
        <DialogContent className="max-w-lg max-h-[80vh] overflow-y-auto thin-scrollbar">
          <DialogHeader>
            <DialogTitle>{viewing?.title || "Untitled chat"}</DialogTitle>
            <DialogDescription>{viewing?.user_email || "No owner (CLI)"}</DialogDescription>
          </DialogHeader>
          {viewError && (
            <p className="text-sm text-destructive bg-destructive/10 rounded-md px-3 py-2">{viewError}</p>
          )}
          {viewing?.messages === null ? (
            <p className="text-sm text-muted-foreground">Loading...</p>
          ) : (
            <div className="space-y-3">
              {viewing?.messages?.map((m) => (
                <div key={m.id} className="rounded-md border border-border p-3">
                  <p className="text-xs font-medium text-muted-foreground mb-1 uppercase tracking-wide">
                    {m.role}
                  </p>
                  <p className="text-sm text-foreground whitespace-pre-wrap">{m.content}</p>
                </div>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete chat</DialogTitle>
            <DialogDescription>
              This permanently deletes "{deleteTarget?.title || "Untitled chat"}" and all its messages.
              This can't be undone.
            </DialogDescription>
          </DialogHeader>
          {deleteError && (
            <p className="text-sm text-destructive bg-destructive/10 rounded-md px-3 py-2">{deleteError}</p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>Cancel</Button>
            <Button variant="destructive" onClick={confirmDelete} disabled={isDeleting}>
              {isDeleting ? "Deleting..." : "Delete"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
