import { Plus, MoreHorizontal, Trash2, LogOut } from "lucide-react";
import { Button } from "./ui/Button";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from "./ui/DropdownMenu";
import { cn } from "../lib/utils";

function groupChatsByDate(chats) {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfYesterday = new Date(startOfToday);
  startOfYesterday.setDate(startOfYesterday.getDate() - 1);
  const sevenDaysAgo = new Date(startOfToday);
  sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

  const groups = { Today: [], Yesterday: [], "Previous 7 days": [], Older: [] };
  for (const chat of chats) {
    const created = new Date(chat.created_at);
    if (created >= startOfToday) groups.Today.push(chat);
    else if (created >= startOfYesterday) groups.Yesterday.push(chat);
    else if (created >= sevenDaysAgo) groups["Previous 7 days"].push(chat);
    else groups.Older.push(chat);
  }
  return groups;
}

export default function Sidebar({ chats, activeChatId, onSelectChat, onNewChat, onDeleteChat, user, onLogout }) {
  const groups = groupChatsByDate(chats);

  return (
    <aside className="w-64 shrink-0 border-r border-border bg-muted/40 h-full flex flex-col">
      <div className="p-3">
        <Button variant="outline" size="sm" onClick={onNewChat} className="w-full justify-start gap-2 bg-card">
          <Plus className="h-4 w-4" /> New chat
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto thin-scrollbar px-2 pb-3 space-y-3">
        {Object.entries(groups).map(([label, group]) =>
          group.length === 0 ? null : (
            <div key={label}>
              <p className="px-3 pb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground/70">
                {label}
              </p>
              <div className="space-y-0.5">
                {group.map((chat) => (
                  <div
                    key={chat.id}
                    className={cn(
                      "group flex items-center rounded-md text-sm transition-colors",
                      chat.id === activeChatId
                        ? "bg-accent text-accent-foreground font-medium"
                        : "text-muted-foreground hover:bg-accent/60 hover:text-accent-foreground"
                    )}
                  >
                    <button
                      onClick={() => onSelectChat(chat.id)}
                      className="flex-1 truncate text-left px-3 py-2"
                    >
                      {chat.title || "Untitled chat"}
                    </button>

                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <button
                          onClick={(e) => e.stopPropagation()}
                          className="mr-1 shrink-0 rounded-sm p-1 opacity-0 group-hover:opacity-100 hover:bg-background/60 focus:opacity-100"
                          title="Chat options"
                        >
                          <MoreHorizontal className="h-3.5 w-3.5" />
                        </button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent>
                        <DropdownMenuItem
                          destructive
                          onClick={() => onDeleteChat(chat.id)}
                        >
                          <Trash2 className="h-3.5 w-3.5" /> Delete
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                ))}
              </div>
            </div>
          )
        )}

        {chats.length === 0 && (
          <p className="text-xs text-muted-foreground px-3 py-2">No chats yet</p>
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
