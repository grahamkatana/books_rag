import { useEffect, useState } from "react";
import Login from "./components/Login";
import Sidebar from "./components/Sidebar";
import UsersPage from "./components/UsersPage";
import BooksPage from "./components/BooksPage";
import PapersPage from "./components/PapersPage";
import ChatsPage from "./components/ChatsPage";
import { fetchMe, getToken, logout as apiLogout } from "./api/client";

export default function App() {
  const [authState, setAuthState] = useState("checking"); // checking | authed | anon
  const [user, setUser] = useState(null);
  const [activePage, setActivePage] = useState("users");

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
      <div className="flex h-screen w-screen items-center justify-center text-sm text-muted-foreground">
        Loading…
      </div>
    );
  }

  if (authState === "anon") {
    return <Login onSuccess={checkAuth} />;
  }

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background">
      <Sidebar user={user} onLogout={handleLogout} activePage={activePage} onNavigate={setActivePage} />
      {activePage === "users" && <UsersPage currentUser={user} onSessionExpired={handleLogout} />}
      {activePage === "books" && <BooksPage onSessionExpired={handleLogout} />}
      {activePage === "papers" && <PapersPage onSessionExpired={handleLogout} />}
      {activePage === "chats" && <ChatsPage onSessionExpired={handleLogout} />}
    </div>
  );
}
