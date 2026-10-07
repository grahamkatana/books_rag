"""Counting and costing AI usage. record() is the only call the rest of the app needs."""

import calendar
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import Integer, cast, func, select

from app.db.session import SessionLocal
from app.models.usage import ModelPrice, ProviderCredit, UsageEvent

log = logging.getLogger("usage")


def estimate_tokens(text: str) -> int:
    """About four characters a token. Only used when a provider reports no usage."""
    return max(1, len(text) // 4)


def record(kind: str, provider: str, model: str, input_tokens: int, output_tokens: int = 0, estimated: bool = False) -> None:
    """Write one usage row in its own session. Never raises: counting spend must not break an answer."""
    try:
        with SessionLocal() as session:
            session.add(UsageEvent(kind=kind, provider=provider, model=model, input_tokens=int(input_tokens or 0),
                                   output_tokens=int(output_tokens or 0), estimated=estimated))
            session.commit()
    except Exception as exc:  # noqa: BLE001
        log.warning("usage not recorded: %s", exc)


def record_openai(kind: str, model: str, usage) -> None:
    """Record an OpenAI-style `usage` object (prompt_tokens / completion_tokens), if there is one."""
    if usage is not None:
        record(kind, "openai", model, getattr(usage, "prompt_tokens", 0), getattr(usage, "completion_tokens", 0) or 0)


def record_agent(kind: str, provider: str, model: str, result) -> None:
    """Record a pydantic-ai run's token usage. Anything that is not a real count (a test double) is ignored."""
    try:
        u = result.usage()
        if isinstance(u.input_tokens, int) and isinstance(u.output_tokens, int):
            record(kind, provider, model, u.input_tokens, u.output_tokens)
    except Exception as exc:  # noqa: BLE001
        log.warning("agent usage not recorded: %s", exc)


def cost_usd(input_tokens: int, output_tokens: int, price) -> float | None:
    if price is None:
        return None
    return (input_tokens * float(price[0]) + output_tokens * float(price[1])) / 1_000_000


def project_month(spent: float, now: datetime) -> float:
    """Month-end spend if the month carries on at its average daily rate so far."""
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    elapsed = (now.day - 1) + (now.hour + now.minute / 60) / 24
    return spent / max(elapsed, 1 / 24) * days_in_month


def _prices(session) -> dict:
    return {(p.provider, p.model): (p.input_per_million, p.output_per_million) for p in session.scalars(select(ModelPrice))}


def _grouped(session, start):
    day = func.date(UsageEvent.created_at)
    return session.execute(
        select(day, UsageEvent.kind, UsageEvent.provider, UsageEvent.model, func.sum(UsageEvent.input_tokens),
               func.sum(UsageEvent.output_tokens), func.count(), func.max(cast(UsageEvent.estimated, Integer)))
        .where(UsageEvent.created_at >= start).group_by(day, UsageEvent.kind, UsageEvent.provider, UsageEvent.model)
    ).all()


def summary(session, days: int = 30, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    price_map = _prices(session)
    by_day: dict[str, float] = {}
    by_model: dict[tuple, dict] = {}
    for day, kind, provider, model, i, o, calls, est in _grouped(session, now - timedelta(days=days)):
        c = cost_usd(i, o, price_map.get((provider, model)))
        m = by_model.setdefault((provider, model, kind), {"provider": provider, "model": model, "kind": kind, "calls": 0, "input_tokens": 0,
                                "output_tokens": 0, "cost_usd": 0.0, "priced": c is not None, "estimated": False})
        m["calls"] += calls; m["input_tokens"] += i; m["output_tokens"] += o; m["estimated"] |= bool(est)
        if c is not None:
            m["cost_usd"] += c
            by_day[str(day)] = by_day.get(str(day), 0.0) + c
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_cost = sum(cost_usd(i, o, price_map.get((p, m))) or 0.0 for _d, _k, p, m, i, o, _c, _e in _grouped(session, month_start))
    return {
        "days": days,
        "by_model": sorted(by_model.values(), key=lambda m: -m["cost_usd"]),
        "by_day": [{"day": d, "cost_usd": c} for d, c in sorted(by_day.items())],
        "month_to_date_usd": month_cost,
        "projected_month_usd": project_month(month_cost, now),
        "unpriced": sorted({f"{m['provider']}/{m['model']}" for m in by_model.values() if not m["priced"]}),
    }


def list_prices(session) -> list[dict]:
    return [{"provider": p.provider, "model": p.model, "input_per_million": float(p.input_per_million),
             "output_per_million": float(p.output_per_million), "note": p.note} for p in session.scalars(select(ModelPrice))]


def set_price(session, provider: str, model: str, input_per_million: float, output_per_million: float, note: str = "") -> None:
    row = session.get(ModelPrice, (provider, model)) or ModelPrice(provider=provider, model=model)
    row.input_per_million, row.output_per_million, row.note = input_per_million, output_per_million, note
    row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    session.add(row)
    session.commit()


def set_credit(session, provider: str, amount_usd: float) -> None:
    row = session.get(ProviderCredit, provider) or ProviderCredit(provider=provider)
    row.amount_usd, row.as_of = amount_usd, datetime.now(timezone.utc).replace(tzinfo=None)
    session.add(row)
    session.commit()


def estimated_credit_left(session) -> list[dict]:
    """Manual top-up figure minus priced usage since it was entered: an estimate, for providers with no balance API."""
    price_map = _prices(session)
    out = []
    for c in session.scalars(select(ProviderCredit)):
        used = session.execute(select(UsageEvent.model, func.sum(UsageEvent.input_tokens), func.sum(UsageEvent.output_tokens))
                               .where(UsageEvent.provider == c.provider, UsageEvent.created_at >= c.as_of).group_by(UsageEvent.model)).all()
        spent = sum(cost_usd(i, o, price_map.get((c.provider, m))) or 0.0 for m, i, o in used)
        out.append({"provider": c.provider, "entered_usd": float(c.amount_usd), "as_of": c.as_of.isoformat(),
                    "spent_since_usd": spent, "estimated_left_usd": float(c.amount_usd) - spent})
    return out
