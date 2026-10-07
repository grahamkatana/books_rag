import { useEffect, useState } from "react";
import { Menu } from "lucide-react";
import Login from "./components/Login";
import Sidebar from "./components/Sidebar";
import UsersPage from "./components/UsersPage";
import BooksPage from "./components/BooksPage";
import PapersPage from "./components/PapersPage";
import ChatsPage from "./components/ChatsPage";
import FlaggedPage from "./components/FlaggedPage";
import UsagePage from "./components/UsagePage";
import { fetchMe, getToken, logout as apiLogout } from "./api/client";

export default function App() {
  const [authState, setAuthState] = useState("checking"); // checking | authed | anon
  const [user, setUser] = useState(null);
  const [activePage, setActivePage] = useState("users");
  const [navOpen, setNavOpen] = useState(false); // mobile only: the sidebar is a slide-in drawer below md

  const checkAuth = async () => {
    if (!getToken()) {
      setAuthState("anon");
      return;
    }
    try {
      const me = await fetchMe();
      if (!me.is_admin) {
        apiLogout();
        setAuthState("anon");
        return;
      }
      setUser(me);
      setAuthState("authed");
    } catch {
      setAuthState("anon");
    }
  };

  useEffect(() => {
    checkAuth();
  }, []);

  const handleLogout = () => {
    apiLogout();
    setUser(null);
    setAuthState("anon");
  };

  if (authState === "checking") {
    return (
      <div className="flex h-dvh w-full items-center justify-center text-sm text-muted-foreground">
        Loading…
      </div>
    );
  }

  if (authState === "anon") {
    return <Login onSuccess={checkAuth} />;
  }

  return (
    <div className="flex h-dvh w-full flex-col overflow-hidden bg-background md:flex-row">
      <div className="flex h-12 shrink-0 items-center gap-2 border-b border-border px-2 md:hidden">
        <button onClick={() => setNavOpen(true)} title="Menu" className="rounded-md p-2 text-muted-foreground hover:bg-accent">
          <Menu className="h-5 w-5" />
        </button>
        <span className="text-sm font-semibold text-foreground">Book RAG Admin</span>
      </div>
      {navOpen && <div className="fixed inset-0 z-30 bg-black/40 md:hidden" onClick={() => setNavOpen(false)} />}
      <Sidebar
        open={navOpen}
        user={user}
        onLogout={handleLogout}
        onSessionExpired={handleLogout}
        activePage={activePage}
        onNavigate={(page) => { setNavOpen(false); setActivePage(page); }}
      />
      {activePage === "users" && <UsersPage currentUser={user} onSessionExpired={handleLogout} />}
      {activePage === "books" && <BooksPage onSessionExpired={handleLogout} />}
      {activePage === "papers" && <PapersPage onSessionExpired={handleLogout} />}
      {activePage === "chats" && <ChatsPage onSessionExpired={handleLogout} />}
      {activePage === "usage" && <UsagePage onSessionExpired={handleLogout} />}
      {activePage === "flagged" && <FlaggedPage onSessionExpired={handleLogout} />}
    </div>
  );
}
