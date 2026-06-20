import { useEffect, useState } from "react";
import Login from "./components/Login";
import ChatApp from "./ChatApp";
import { fetchMe, getToken, logout as apiLogout } from "./api/client";

export default function App() {
  const [authState, setAuthState] = useState("checking"); // checking | authed | anon
  const [user, setUser] = useState(null);

  const checkAuth = async () => {
    if (!getToken()) {
      setAuthState("anon");
      return;
    }
    try {
      const me = await fetchMe();
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

  return <ChatApp user={user} onLogout={handleLogout} onSessionExpired={handleLogout} />;
}
