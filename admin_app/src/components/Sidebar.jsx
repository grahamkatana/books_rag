import { Users, BookOpen, FileText, MessageSquare, LogOut, ShieldCheck } from "lucide-react";
import { cn } from "../lib/utils";

const NAV_ITEMS = [
  { key: "users", label: "Users", icon: Users },
  { key: "books", label: "Books", icon: BookOpen },
  { key: "papers", label: "Papers", icon: FileText },
  { key: "chats", label: "Chats", icon: MessageSquare },
];

export default function Sidebar({ user, onLogout, activePage, onNavigate }) {
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
