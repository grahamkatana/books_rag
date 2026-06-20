import { useEffect, useState, useCallback } from "react";
import Sidebar from "./components/Sidebar";
import ChatWindow from "./components/ChatWindow";
import CitationPanel from "./components/CitationPanel";
import { fetchChats, fetchChat, fetchBook, fetchBooks, deleteChat, streamAsk, UnauthorizedError } from "./api/client";

let nextLocalId = -1; // negative ids for optimistic, not-yet-persisted messages

export default function ChatApp({ user, onSessionExpired, onLogout }) {
  const [chats, setChats] = useState([]);
  const [books, setBooks] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [selectedCitation, setSelectedCitation] = useState(null);
  const [selectedBook, setSelectedBook] = useState(null);
  const [selectedSources, setSelectedSources] = useState([]); // empty = search all books

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
  }, [loadChats, handleError]);

  const selectChat = async (chatId) => {
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
    if (citation.book_id != null) {
      try {
        setSelectedBook(await fetchBook(citation.book_id));
      } catch (err) {
        handleError(err);
      }
    }
  };

  const sendMessage = (question) => {
    const userMsg = { id: nextLocalId--, role: "user", content: question, citations: [] };
    const assistantMsg = { id: nextLocalId--, role: "assistant", content: "", citations: [] };
    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setIsStreaming(true);

    streamAsk(
      { question, chat_id: activeChatId, sources: selectedSources.length ? selectedSources : null },
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
          handleError(err);
        },
      }
    );
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden">
      <Sidebar
        chats={chats}
        activeChatId={activeChatId}
        onSelectChat={selectChat}
        onNewChat={startNewChat}
        onDeleteChat={handleDeleteChat}
        user={user}
        onLogout={onLogout}
      />
      <ChatWindow
        messages={messages}
        isStreaming={isStreaming}
        onSend={sendMessage}
        onCitationClick={handleCitationClick}
        books={books}
        selectedSources={selectedSources}
        onSourcesChange={setSelectedSources}
      />
      {selectedCitation && (
        <CitationPanel
          citation={selectedCitation}
          book={selectedBook}
          onClose={() => setSelectedCitation(null)}
        />
      )}
    </div>
  );
}
