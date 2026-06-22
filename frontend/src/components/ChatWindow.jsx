import { useEffect, useRef } from "react";
import MessageBubble from "./MessageBubble";
import ChatInput from "./ChatInput";

export default function ChatWindow({
  messages,
  isStreaming,
  onSend,
  onCitationClick,
  books,
  papers,
  selectedSources,
  onSourcesChange,
  corpus,
  onCorpusChange,
}) {
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex-1 flex flex-col h-full bg-background">
      <div className="flex-1 overflow-y-auto thin-scrollbar px-4 py-6">
        <div className="max-w-2xl mx-auto space-y-6">
          {messages.length === 0 && (
            <div className="text-center text-muted-foreground mt-24">
              <p className="text-lg font-medium text-foreground/80">Ask your library something</p>
              <p className="text-sm mt-1">Answers cite the exact source and page they came from.</p>
            </div>
          )}
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} onCitationClick={onCitationClick} />
          ))}
          <div ref={bottomRef} />
        </div>
      </div>
      <ChatInput
        onSend={onSend}
        disabled={isStreaming}
        books={books}
        papers={papers}
        selectedSources={selectedSources}
        onSourcesChange={onSourcesChange}
        corpus={corpus}
        onCorpusChange={onCorpusChange}
      />
    </div>
  );
}
