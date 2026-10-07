from datetime import datetime, timezone

import requests

from app.config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, OPENAI_ADMIN_KEY

TIMEOUT = 10


def deepseek_balance(api_key: str, base: str = DEEPSEEK_BASE_URL) -> dict:
    """DeepSeek publishes a real balance endpoint: GET /user/balance."""
    r = requests.get(f"{base}/user/balance", headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"}, timeout=TIMEOUT)
    r.raise_for_status()
    body = r.json()
    return {"provider": "deepseek", "kind": "balance", "available": body.get("is_available"), "balances": body.get("balance_infos", [])}


def openai_month_spend(admin_key: str, now: datetime | None = None) -> dict:
    """OpenAI has no balance endpoint. The Costs API (admin key) reports spend, so this is month-to-date spend, not credit left."""
    now = now or datetime.now(timezone.utc)
    start = int(now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp())
    r = requests.get("https://api.openai.com/v1/organization/costs", params={"start_time": start, "bucket_width": "1d", "limit": 31},
                     headers={"Authorization": f"Bearer {admin_key}"}, timeout=TIMEOUT)
    r.raise_for_status()
    total = sum(float(x["amount"]["value"]) for b in r.json().get("data", []) for x in b.get("results", []))
    return {"provider": "openai", "kind": "month_spend", "month_to_date_usd": total}


def check_all() -> list[dict]:
    """Each configured provider is checked on its own; one failing never hides the others."""
    out: list[dict] = []
    for name, key, fn in (("deepseek", DEEPSEEK_API_KEY, deepseek_balance), ("openai", OPENAI_ADMIN_KEY, openai_month_spend)):
        if not key:
            continue
        try:
            out.append(fn(key))
        except Exception as exc:  # noqa: BLE001
            out.append({"provider": name, "kind": "error", "error": f"{type(exc).__name__}: {str(exc)[:120]}"})
    out.append({"provider": "openai", "kind": "unsupported_balance", "note": "OpenAI has no credit-balance API. Enter your top-up below for an estimate."})
    out.append({"provider": "gemini", "kind": "unsupported", "note": "Google's Gemini API has no balance endpoint; usage is counted here."})
    return out
