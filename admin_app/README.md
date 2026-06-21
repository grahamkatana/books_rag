# Book RAG Admin

A standalone admin SPA for managing users via the book_rag API's
`/api/v1/admin/users/*` endpoints -- separate project, separate
deployment, deliberately not part of the main book_rag app or its
frontend. Same shadcn-style architecture as the main frontend: real
Radix UI primitives, `class-variance-authority`, the `cn()` utility, HSL
CSS-variable theming. Nothing here is a visual approximation of shadcn;
it's the same actual component pattern.

## What it does

- Login (JWT, against `/api/v1/auth/login` -- the same endpoint the main
  frontend uses, not the separate `/admin` session-based login).
- **Users**: list, create, edit (including resetting a password -- leave
  it blank to keep the existing one), and delete, via
  `/api/v1/admin/users/*`.
- **Books**: list and correct bibliography (title/authors/year/publisher/
  edition/work_key/edition preference), via `/api/v1/admin/books/*`.
  Deliberately no delete here -- a Book row has real Qdrant vectors and a
  chunk file that nothing currently cleans up, so removing just the row
  would leave those orphaned and still searchable. Saving an edit
  auto-marks the book `bibliography_verified` with `bibliography_source:
  "manual"`, same as the Flask-Admin panel's behavior.
- **Chats**: list every user's chat (with their email attached, for
  moderation context), view full message history, delete, via
  `/api/v1/admin/chats/*`. No edit -- there's nothing meaningful to
  rewrite in someone's conversation history, only view and remove.
- Surfaces the backend's own safety messages as-is (e.g. attempting to
  delete the last remaining admin) rather than re-implementing those
  rules client-side -- the API is the source of truth for what's allowed.
- Search and pagination on every page (`useSearchAndPaginate`), entirely
  client-side: none of the admin endpoints support server-side
  search/paging, they return the full list in one response, so this
  filters and slices in the browser instead. Fine for the data volumes
  an admin tool deals with; if a deployment's counts ever get large
  enough for that to matter, the real fix is server-side query params,
  not a smarter client-side hook.

## Local development

```bash
npm install
npm run dev   # http://localhost:5174, proxies /api/* to localhost:8000
```

Port `5174` on purpose, not `5173` -- so you can run this alongside the
main frontend's dev server at the same time without a clash.

## Docker

This ships its own `Dockerfile` (multi-stage: `npm run build`, then
nginx serves the static output) and `nginx.conf` (SPA fallback + `/api/`
proxied to a service literally named `api` on the same Docker network --
edit `nginx.conf` if your API service has a different name).

To add it to book_rag's existing `docker-compose.yml`, drop this
folder in next to `frontend/` (e.g. as `admin/`) and add a service
block like:

```yaml
  admin:
    build:
      context: ./admin
      dockerfile: Dockerfile
    container_name: book_rag_admin
    restart: unless-stopped
    ports:
      - "3002:80"   # :3000 is the main frontend, :3001 is Grafana if you added that too
    depends_on:
      - api
```

No new volumes, no new env vars -- it talks to the same `api` service
every other piece already depends on.
