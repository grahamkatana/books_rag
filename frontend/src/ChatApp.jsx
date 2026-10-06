import { useEffect, useState, useCallback } from "react";
import { Menu, Plus } from "lucide-react";
import Sidebar from "./components/Sidebar";
import ChatWindow from "./components/ChatWindow";
import CitationPanel from "./components/CitationPanel";
import ReleasesPage from "./components/ReleasesPage";
import {
  fetchChats, fetchChat, fetchBook, fetchBooks, fetchPaper, fetchPapers,
  deleteChat, streamAsk, UnauthorizedError,
} from "./api/client";

let nextLocalId = -1; // negative ids for optimistic, not-yet-persisted messages

export default function ChatApp({ user, onSessionExpired, onLogout }) {
  const [chats, setChats] = useState([]);
  const [books, setBooks] = useState([]);
  const [papers, setPapers] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [selectedCitation, setSelectedCitation] = useState(null);
  const [selectedBook, setSelectedBook] = useState(null);
  const [selectedPaper, setSelectedPaper] = useState(null);
  const [selectedSources, setSelectedSources] = useState([]); // empty = search every item in the current corpus
  const [corpus, setCorpus] = useState("books"); // "books" | "papers" | "both"
  const [navOpen, setNavOpen] = useState(false); // mobile only: the sidebar is a slide-in drawer below md
  const [showReleases, setShowReleases] = useState(false); // the "Android app" page, shown in place of the chat

  const handleError = useCallback((err) => {
    if (err instanceof UnauthorizedError) {
      onSessionExpired();
    } else {
      console.error(err);
    }
  }, [onSessionExpired]);

  const loadChats = useCallback(async () => {
    try {
      setChats(await fetchChats());
    } catch (err) {
      handleError(err);
    }
  }, [handleError]);

  useEffect(() => {
    loadChats();
    fetchBooks().then(setBooks).catch(handleError);
    fetchPapers().then(setPapers).catch(handleError);
  }, [loadChats, handleError]);

  const selectChat = async (chatId) => {
    setNavOpen(false);
    setShowReleases(false);
    setActiveChatId(chatId);
    setSelectedCitation(null);
    setSelectedSources([]); // scope isn't persisted per chat -- always reopen unscoped
    try {
      const data = await fetchChat(chatId);
      setMessages(data.messages);
    } catch (err) {
      handleError(err);
    }
  };

  const startNewChat = () => {
    setNavOpen(false);
    setShowReleases(false);
    setActiveChatId(null);
    setMessages([]);
    setSelectedCitation(null);
    setSelectedSources([]);
  };

  const handleDeleteChat = async (chatId) => {
    try {
      await deleteChat(chatId);
      setChats((prev) => prev.filter((c) => c.id !== chatId));
      if (chatId === activeChatId) {
        startNewChat();
      }
    } catch (err) {
      handleError(err);
    }
  };

  const handleCitationClick = async (citation) => {
    setSelectedCitation(citation);
    setSelectedBook(null);
    setSelectedPaper(null);
    // Mutually exclusive on the backend (a Citation resolves to at most
    // one of book_id/paper_id) -- mirrored here the same way rather than
    // guessing which fetch to make.
    try {
      if (citation.paper_id != null) {
        setSelectedPaper(await fetchPaper(citation.paper_id));
      } else if (citation.book_id != null) {
        setSelectedBook(await fetchBook(citation.book_id));
      }
    } catch (err) {
      handleError(err);
    }
  };

  const sendMessage = (question) => {
    const userMsg = { id: nextLocalId--, role: "user", content: question, citations: [] };
    const assistantMsg = { id: nextLocalId--, role: "assistant", content: "", citations: [] };
    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setIsStreaming(true);

    streamAsk(
      {
        question,
        chat_id: activeChatId,
        sources: selectedSources.length ? selectedSources : null,
        corpus,
      },
      {
        onChatId: (id) => {
          if (!activeChatId) setActiveChatId(id);
        },
        onDelta: (text) => {
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            updated[updated.length - 1] = { ...last, content: last.content + text };
            return updated;
          });
        },
        onDone: (payload) => {
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            updated[updated.length - 1] = { ...last, citations: payload.citations || [] };
            return updated;
          });
          setIsStreaming(false);
          loadChats();
        },
        onError: (err) => {
          setIsStreaming(false);
          if (err instanceof UnauthorizedError) {
            onSessionExpired();
            return;
          }
          // Surface the failure in the empty assistant bubble instead of
          // leaving it stuck on "Thinking…". Transport/HTTP errors carry
          // useless strings ("Request failed: 500", "Failed to fetch",
          // "network error") -- show a human line for those, but keep a
          // genuine backend message ("Chat not found") as-is.
          const TRANSPORT_ERROR = /Request failed|Failed to fetch|network error|Load failed|NetworkError|HTTP2/i;
          const message =
            err?.message && !TRANSPORT_ERROR.test(err.message)
              ? err.message
              : "Sorry, I couldn't get an answer. Please try again.";
          setMessages((prev) => {
            const updated = [...prev];
            const last = updated[updated.length - 1];
            updated[updated.length - 1] = { ...last, content: message };
            return updated;
          });
        },
      }
    );
  };

  return (
    <div className="flex h-dvh w-full flex-col overflow-hidden md:flex-row">
      <div className="flex h-12 shrink-0 items-center justify-between border-b border-border px-2 md:hidden">
        <button onClick={() => setNavOpen(true)} title="Chats" className="rounded-md p-2 text-muted-foreground hover:bg-accent">
          <Menu className="h-5 w-5" />
        </button>
        <span className="text-sm font-semibold text-foreground">Book RAG</span>
        <button onClick={startNewChat} title="New chat" className="rounded-md p-2 text-muted-foreground hover:bg-accent">
          <Plus className="h-5 w-5" />
        </button>
      </div>
      {navOpen && <div className="fixed inset-0 z-30 bg-black/40 md:hidden" onClick={() => setNavOpen(false)} />}
      <Sidebar
        open={navOpen}
        chats={chats}
        activeChatId={activeChatId}
        onSelectChat={selectChat}
        onNewChat={startNewChat}
        onDeleteChat={handleDeleteChat}
        onOpenReleases={() => { setNavOpen(false); setSelectedCitation(null); setShowReleases(true); }}
        user={user}
        onLogout={onLogout}
      />
      {showReleases ? (
        <ReleasesPage user={user} onBack={() => setShowReleases(false)} onSessionExpired={onSessionExpired} />
      ) : (
      <ChatWindow
        messages={messages}
        isStreaming={isStreaming}
        onSend={sendMessage}
        onCitationClick={handleCitationClick}
        books={books}
        papers={papers}
        selectedSources={selectedSources}
        onSourcesChange={setSelectedSources}
        corpus={corpus}
        onCorpusChange={setCorpus}
      />
      )}
      {selectedCitation && (
        <CitationPanel
          citation={selectedCitation}
          book={selectedBook}
          paper={selectedPaper}
          onClose={() => setSelectedCitation(null)}
        />
      )}
    </div>
  );
}
