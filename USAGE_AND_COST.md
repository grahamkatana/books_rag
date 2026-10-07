# Usage and cost dashboard (admin) — 7 October 2026

**What it does.** Every OpenAI chat answer, embedding call, and agent run (claim extraction, verification, DeepSeek cross-check, document context) is counted in `usage_events`. The admin app has a **Usage & cost** page: month to date, projection to month end, cost per day, per-model table, balances, editable prices.

**Where.** `app/usage/` (record, summary, balances), `app/api/v1/admin_usage.py` (`/api/v1/admin/usage/*`), migration `d52e8b1f7c33`, hooks in `app/retrieval/query_engine.py`, `app/ingestion/embed_upload.py` and the four `app/agents/*`, page `admin_app/src/components/UsagePage.jsx`.

**Real vs estimated.**
- Token counts are the provider's own. Missing ones fall back to four characters a token and are flagged.
- Cost = tokens x the price you set. Only `text-embedding-3-large` ($0.13 per million) is seeded; enter the rest (gpt-5.4-mini, deepseek-chat, and so on) from each pricing page. No price means "no price" and $0 in totals.
- **Balances.** DeepSeek: real balance via `GET /user/balance` (uses `DEEPSEEK_API_KEY`, already deployed). OpenAI: no credit-balance API; set `OPENAI_ADMIN_KEY` (an organisation admin key, separate from the normal key) to show month-to-date spend from the Costs API. Gemini: nothing. For anything without an API, enter "credit left" on the page and priced usage since is subtracted.

**Check before relying on it.** The deployed `CONTEXT_MODEL` is `gemini-2.5-flash-lite`, but `build_context_agent` sends it to OpenAI (`openai-chat:` prefix; the Gemini version is commented out). If that call fails in production, document-context checks fail. Usage for it is recorded as provider `openai`. Not verified against the live service.

**Not done.** Per-user split; the CLI-only ingestion scripts (`lookup_*`) are not counted. Not deployed at the time of writing: needs the migration and an image build.

**Tested.** `tests/test_usage.py`, 10 tests on in-memory SQLite (run with `DATABASE_URL=sqlite:///:memory:`, never the real database); migration and queries also run on a throwaway Postgres 16, which caught a boolean `max()` bug SQLite hid. The older script-style tests were not run (they need tables and some hit the real database).
