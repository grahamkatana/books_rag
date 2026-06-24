import { useState } from "react";
import { Users, BookOpen, FileText, MessageSquare, LogOut, ShieldCheck, RefreshCw, Loader2 } from "lucide-react";
import { cn } from "../lib/utils";
import { triggerIngest } from "../api/client";
import { pollJobUntilDone } from "../lib/pollJob";

const NAV_ITEMS = [
  { key: "users", label: "Users", icon: Users },
  { key: "books", label: "Books", icon: BookOpen },
  { key: "papers", label: "Papers", icon: FileText },
  { key: "chats", label: "Chats", icon: MessageSquare },
];

export default function Sidebar({ user, onLogout, activePage, onNavigate }) {
  // null, or { phase: "running" | "done" | "error", text } -- both
  // pipelines are polled together since the button represents "ingest
  // everything," not either one individually; see BooksPage/PapersPage
  // for the single-corpus upload flow, which tracks its own status the
  // same way but scoped to just the one pipeline it triggered.
  const [ingestStatus, setIngestStatus] = useState(null);
  const isRunning = ingestStatus?.phase === "running";

  const handleIngest = async () => {
    setIngestStatus({ phase: "running", text: "Running both pipelines..." });
    try {
      const { books_task_id, papers_task_id } = await triggerIngest();
      const results = await Promise.allSettled([
        pollJobUntilDone(books_task_id, { timeoutMs: 10 * 60 * 1000 }),
        pollJobUntilDone(papers_task_id, { timeoutMs: 10 * 60 * 1000 }),
      ]);
      const [booksResult, papersResult] = results;
      if (booksResult.status === "rejected" || papersResult.status === "rejected") {
        const failures = [
          booksResult.status === "rejected" ? `books: ${booksResult.reason.message}` : null,
          papersResult.status === "rejected" ? `papers: ${papersResult.reason.message}` : null,
        ].filter(Boolean);
        setIngestStatus({ phase: "error", text: failures.join(" | ") });
      } else {
        setIngestStatus({ phase: "done", text: "Both pipelines finished." });
      }
    } catch (err) {
      setIngestStatus({ phase: "error", text: err.message });
    }
  };

  return (
    <aside className="w-56 shrink-0 border-r border-border bg-muted/40 h-full flex flex-col">
      <div className="flex items-center gap-2 px-4 py-4 border-b border-border">
        <ShieldCheck className="h-5 w-5 text-primary" />
        <span className="text-sm font-semibold text-foreground">Book RAG Admin</span>
      </div>

      <nav className="flex-1 px-2 py-3 space-y-0.5">
        {NAV_ITEMS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            onClick={() => onNavigate(key)}
            className={cn(
              "w-full flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              activePage === key
                ? "bg-accent text-accent-foreground"
                : "text-muted-foreground hover:bg-accent/60 hover:text-accent-foreground"
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </nav>

      <div className="px-2 pb-2 space-y-1.5">
        <button
          onClick={handleIngest}
          disabled={isRunning}
          title="Run the full books + papers ingestion pipelines now"
          className={cn(
            "w-full flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
            "border border-input text-foreground hover:bg-accent/60",
            isRunning && "opacity-60"
          )}
        >
          {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Ingest
        </button>
        {ingestStatus && (
          <p
            className={cn(
              "px-1 text-xs leading-snug",
              ingestStatus.phase === "error" ? "text-destructive" : "text-muted-foreground"
            )}
          >
            {ingestStatus.text}
          </p>
        )}
      </div>

      {user && (
        <div className="border-t border-border p-3 flex items-center justify-between">
          <span className="text-xs text-muted-foreground truncate" title={user.email}>
            {user.email}
          </span>
          <button
            onClick={onLogout}
            title="Log out"
            className="shrink-0 rounded-sm p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            <LogOut className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
    </aside>
  );
}
