import { useState } from "react";
import { Copy, Check, Library } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeRaw from "rehype-raw";
import { sanitizeStreamingContent, stripCitationTags } from "../utils";
import CitationBadge from "./CitationBadge";

export default function MessageBubble({ message, onCitationClick }) {
  const isUser = message.role === "user";
  const content = sanitizeStreamingContent(message.content || "");
  const [copied, setCopied] = useState(false);

  let citationCounter = 0;

  // react-markdown lowercases unrecognized tag names, so "<CITATION>"
  // becomes a "citation" node here -- overriding it lets the custom tag
  // live inside otherwise-real markdown (bold, lists, etc.) rather than
  // needing to hand-roll markdown parsing ourselves.
  function CitationRenderer({ children }) {
    const apaText = String(children);
    return (
      <CitationBadge
        index={++citationCounter}
        onClick={() =>
          onCitationClick(
            message.citations?.find((c) => c.apa_text === apaText) || {
              apa_text: apaText,
              locator: null,
              book_id: null,
            }
          )
        }
      />
    );
  }

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(stripCitationTags(content));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard permission denied or unavailable -- not worth surfacing an error for
    }
  };

  if (isUser) {
    // User messages keep the ChatGPT bubble treatment: right-aligned,
    // colored, plain text (not markdown -- no reason to interpret
    // *asterisks* someone typed as formatting).
    return (
      <div className="flex justify-end">
        <div className="max-w-[75%] rounded-2xl rounded-br-sm bg-primary px-4 py-3 text-[15px] leading-relaxed text-primary-foreground whitespace-pre-wrap">
          {content}
        </div>
      </div>
    );
  }

  // Assistant messages: no bubble at all, matching ChatGPT -- a small
  // avatar, full-width plain text in the column, with a copy action that
  // reveals on hover.
  return (
    <div className="group flex gap-3">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent text-accent-foreground">
        <Library className="h-4 w-4" />
      </div>
      <div className="flex-1 text-[15px] leading-relaxed text-foreground">
        {!content ? (
          <span className="text-muted-foreground">Thinking…</span>
        ) : (
          <div className="prose prose-sm max-w-none prose-p:my-2 prose-ul:my-2 prose-ol:my-2 prose-li:my-0.5 prose-headings:my-2 prose-headings:font-semibold prose-strong:text-foreground prose-p:text-foreground prose-li:text-foreground prose-code:text-foreground prose-code:bg-muted prose-code:rounded prose-code:px-1">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              rehypePlugins={[rehypeRaw]}
              components={{ citation: CitationRenderer }}
            >
              {content}
            </ReactMarkdown>
          </div>
        )}

        {content && (
          <button
            onClick={copyToClipboard}
            className="mt-1 flex items-center gap-1 rounded-sm px-1.5 py-1 text-xs text-muted-foreground opacity-0 transition-opacity hover:bg-accent hover:text-accent-foreground group-hover:opacity-100"
            title="Copy"
          >
            {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            {copied ? "Copied" : "Copy"}
          </button>
        )}
      </div>
    </div>
  );
}
