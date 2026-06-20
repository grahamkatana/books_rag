# Book RAG — Architecture

This is the bird's-eye view: what exists, how data moves through it, and
where to start reading code if you want to trace something end to end.
For implementation-level detail on any specific piece, the README is
the source of truth — this document exists to make the *shape* of the
system legible first, since the README's section-by-section detail is
easy to get lost in without a map.

## 1. The system in one picture

```mermaid
flowchart LR
    subgraph Client
        FE[React Frontend<br/>:3000 or :5173]
    end

    subgraph Backend
        API[Flask API<br/>:8000]
        ADMIN[Flask-Admin panel<br/>/admin]
    end

    subgraph Data
        DB[(SQLite or Postgres<br/>books / chats / messages /<br/>citations / users)]
        QD[(Qdrant<br/>vector store<br/>:6333)]
    end

    subgraph External
        OAI[OpenAI<br/>embeddings + chat]
        BRAVE[Brave Search<br/>bibliography lookup]
    end

    FE -- JWT bearer token --> API
    API --> DB
    API --> QD
    API --> OAI
    ADMIN --> DB
    CLI[CLI / ingest.py] --> DB
    CLI --> QD
    CLI -- lookup-bibliography --> BRAVE
    CLI -- embed --> OAI
```

Two ways into the system: the **CLI** (`app/cli.py`, or the single-file
`ingest.py` wrapper) does ingestion — turning PDFs into searchable,
cited vectors. The **API** (Flask, behind the React frontend or any
other client) does retrieval — turning a question into an answer. They
share the same database and the same Qdrant collection, but otherwise
don't call into each other.

## 2. Ingestion: PDF → searchable, cited chunk

```mermaid
flowchart TD
    PDF[PDF dropped in pdfs/books/] --> REPORT[build_trust_report.py]
    REPORT -->|"trust_page_numbers?"| CSV[data/report.csv]
    CSV --> SEED[seed_books.py]
    SEED -->|"new file? create a Book row<br/>(filename-guessed, unverified)"| BOOKSTABLE[(books table)]
    SEED -->|existing row?| SKIP1[left untouched]
    BOOKSTABLE --> LOOKUP[lookup_bibliography.py]
    LOOKUP -->|"Brave search + LLM extraction"| BOOKSTABLE
    CSV --> CHUNKDECIDE{trust_page_numbers?}
    CHUNKDECIDE -->|true| CHUNKTRUSTED[chunk_trusted_books.py<br/>tiktoken windows, real page labels]
    CHUNKDECIDE -->|false| CHUNKUNTRUSTED[chunk_untrusted_books.py<br/>font-size heading detection]
    CHUNKTRUSTED --> JSONL[data/chunks/*.jsonl]
    CHUNKUNTRUSTED --> JSONL
    JSONL --> EMBED[embed_upload.py]
    EMBED -->|"OpenAI embeddings,<br/>skip unchanged chunks"| QDRANT[(Qdrant: book_library collection)]
```

The fork at "trust_page_numbers?" is the most important decision point
in ingestion, and it's made once, early, by literally checking whether
the PDF's `/PageLabels` metadata exists (`build_trust_report.py`) —
**not guessed**. Everything downstream depends on which path a given
book took:

- **Trusted books** get exact page citations (`p. 47`) because the PDF
  itself told us the real printed page number for every physical page.
- **Untrusted books** (no real page numbers in the PDF at all) get
  chapter/section citations instead (`"Stage 1: Specification" section,
  approx. PDF p.52`), built by detecting headings from font size, since
  there's no real page number to extract.

Both paths converge on the same `data/chunks/<book>.jsonl` format and
get embedded the same way — `embed_upload.py` doesn't know or care which
chunker produced a given file.

**Read these, in order, to understand ingestion fully:**
`app/ingestion/build_trust_report.py` → `seed_books.py` →
`lookup_bibliography.py` → `chunk_trusted_books.py` (and
`chunk_untrusted_books.py` for the no-real-pages case) → `embed_upload.py`.

## 3. Retrieval: question → cited answer

```mermaid
sequenceDiagram
    participant U as User
    participant API as Flask API (ask.py)
    participant QE as query_engine.py
    participant QD as Qdrant
    participant DB as Database
    participant LLM as OpenAI

    U->>API: POST /api/v1/ask (question, sources?, chat_id?)
    API->>API: jwt_required() -- who is this?
    API->>QE: answer_question(...)
    QE->>DB: get_or_create_chat (check ownership if chat_id given)
    QE->>LLM: embed_query(question)
    LLM-->>QE: query vector
    QE->>QD: search_chunks(vector, filters)
    QD-->>QE: top-k chunks (with page/chapter metadata)
    QE->>DB: look up each chunk's Book row
    QE->>QE: render_citation() per chunk -> "<CITATION>...</CITATION>" tags
    QE->>LLM: ask_llm(question, tagged context)
    LLM-->>QE: answer text, citation tags intact
    QE->>DB: save_turn() -- persist Message + parse tags into Citation rows
    QE-->>API: {chat_id, answer, citations}
    API-->>U: JSON (or SSE stream, for /ask/stream)
```

The one subtlety worth internalizing: **the LLM never invents a
citation's content.** Every `<CITATION>...</CITATION>` tag it's allowed
to emit was already built by `render_citation()` *before* the LLM ever
sees the prompt — the model's only job is to copy the exact tag next to
whichever claim it's using. After the answer comes back,
`extract_citation_tags()` parses those tags back out and resolves each
one to a `Book` row for the structured `citations` array the API
returns. This is why citations can't drift from what was actually
retrieved.

**Read these to understand retrieval fully:**
`app/api/v1/ask.py` → `app/retrieval/query_engine.py` →
`app/retrieval/citations.py`.

## 4. Two separate auth systems

This trips people up, so it's worth being explicit: there are **two
independent login flows**, both checking the same `users` table, that
exist for different kinds of clients.

```mermaid
flowchart LR
    subgraph "JWT (API consumers)"
        L1[POST /api/v1/auth/login] -->|email+password| T[JWT access token]
        T -->|Authorization: Bearer ...| EP[Every other /api/v1/* endpoint]
    end

    subgraph "Session (admin panel)"
        L2[GET/POST /admin/login] -->|email+password, Flask-Login| S[Browser session cookie]
        S --> ADMINVIEWS["/admin/* views"]
    end

    USERS[(users table)] --> L1
    USERS --> L2
```

The React frontend (and the CLI's `ask`, sort of — it bypasses auth
entirely, creating ownerless chats) uses the JWT path. `/admin` uses its
own session-based login because it's a traditional server-rendered page,
not a stateless API client — there was no reason to force it through
JWT just for consistency's sake. Chats are scoped to whichever user's
token made the request; a mismatched `chat_id` comes back as 404 (not
403), so a request can't even confirm another user's chat exists.

**Read these:** `app/api/v1/auth.py` (JWT) and `app/admin/views.py`
(session + the actual admin CRUD views, via Flask-Admin).

## 5. Database schema

```mermaid
erDiagram
    USERS ||--o{ CHATS : owns
    CHATS ||--o{ MESSAGES : contains
    MESSAGES ||--o{ CITATIONS : has
    BOOKS ||--o{ CITATIONS : "cited by"

    USERS {
        int id
        string email
        string password_hash
        bool is_admin
    }
    CHATS {
        int id
        int user_id "nullable -- null for CLI-created chats"
        string title
    }
    MESSAGES {
        int id
        int chat_id
        string role "user or assistant"
        text content "still has raw CITATION tags"
    }
    CITATIONS {
        int id
        int message_id
        int book_id "nullable if unresolved"
        string apa_text
        string locator
    }
    BOOKS {
        int id
        string source_key "unique, matches Qdrant payload"
        string title
        string authors
        bool bibliography_verified
        string bibliography_source "filename_guess / auto_lookup / manual"
        string work_key "nullable -- groups editions"
        bool is_preferred_edition
        bool edition_pinned "deliberate human choice, separate from verified"
    }
```

`Book.source_key` is the join key between this relational data and
Qdrant — every chunk's payload in Qdrant carries a `source` field that
matches a `Book.source_key` exactly. Qdrant itself only stores chunk
text + locator metadata + the embedding vector; it has no idea what a
"book" or "citation" is. All of *that* structure lives here, in
`app/models/`, and gets reattached at query time in
`query_engine.build_context_and_lookup()`.

`work_key`, `is_preferred_edition`, and `edition_pinned` exist
specifically for multi-edition libraries — see the README's "Multiple
editions" section for the full reasoning. The short version: avoid
silently blending two editions of the same book into one answer, while
still letting a human override the automatic year-based choice when they
deliberately want to.

## 6. Where things physically run (Docker topology)

```mermaid
flowchart TD
    subgraph "docker-compose.yml"
        FE[frontend<br/>nginx, :3000->80]
        API[api<br/>gunicorn, :8000]
        PG[postgres<br/>:5432]
        QD[qdrant<br/>:6333, :6334]
    end

    FE -->|"proxy_pass /api/<br/>(nginx.conf)"| API
    API --> PG
    API --> QD
```

`api`'s `docker-entrypoint.sh` runs migrations and seeds the default
admin on every container start (idempotent after the first boot) before
starting gunicorn. The bare-host path (`uv run python server.py`) skips
all of that — it's meant for local dev, talks to SQLite by default
instead of Postgres, and you run migrations/seeding yourself.

## 7. If you only read five files

In rough order of "how central is this to understanding the system":

1. `app/config.py` — every setting the app reads, in one place. Start
   here to see what's configurable at all.
2. `app/retrieval/query_engine.py` — the actual core loop: embed,
   search, build citations, ask, persist. If you understand this file,
   you understand what the product *does*.
3. `app/models/book.py` and `app/models/chat.py` — the data model. Once
   you know the shape of `Book` and `Chat`/`Message`/`Citation`, most of
   the rest of the codebase is just "code that reads or writes these."
4. `app/cli.py` — the ingestion pipeline as a sequence of named steps;
   reading the `pipeline` command's step list is a faster way to learn
   the ingestion order than reading every ingestion file individually.
5. `app/api/factory.py` — how all the pieces (blueprints, JWT, CORS,
   the admin panel) get wired into one running Flask app.

For anything not covered here, the README is organized the same way
this document is (ingestion, retrieval, auth, frontend, deployment) —
treat this as the table of contents and the README as the chapters.